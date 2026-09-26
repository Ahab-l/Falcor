# 原生大气 LUT：实现、验证与剩余工作

2026-09-11。当前实现 Transmittance 和默认双射线 MultiScattering 两张二维 LUT。它们通过现有 PassDefinition / UELegacyComputePass 执行；没有添加专门的 LUT C++ Pass。完整天空、SkyLight、雾云和最终图像仍未完成。

## 输入与算法

物理介质来自保存的 SkyAtmosphereComponent。转换采用 UE 的 km 单位、原始 256 项 FLinearColor sRGB 字面量表、系数缩放/钳制及臭氧 tent 转换。Schema 继续只管理 Packed 数据契约，散射积分数学位于 Shader。

`export_atmosphere_source.py` 提取原始函数体并记录 UE 文件与片段 SHA256、签名和行号。`AtmosphereLuts.slang` 只提供资源、常量与排列适配。保留非线性 LUT 坐标、0.3 采样偏移、浮点采样数的向上取整循环、sqrt 透射率存储（先过滤再平方）、两条垂直各向同性散射射线、地面反射、行星遮挡及 1+r+r²+r³+r⁴ 有限散射级数。

主管线输出为 UE PF_FloatRGB 对应的 R11G11B10Float；RGBA32Float 仅用于分离积分与存储转换的诊断。HQ 多散射、小格式透射率、未验证工作色域或移动/alpha 格式分支明确拒绝。NullRHI 源 commandlet 的设置不等同于交互编辑器截帧的运行时覆盖。

RDC 的几何、矩阵、常量、纹理、LUT、深度、阴影、曝光与历史均不作为这些 Pass 的渲染输入。NumPy 参考输出和 GPU 读回只用于离线比较，不上传回渲染图。

## 数值验证

独立 NumPy oracle 验证真空、恒定吸收、正散射、编码、地面反射及参数变化。GPU 测试额外覆盖 31×9 / 7×3 奇数尺寸、10.5 / 15.5 非整数采样数、相位参数在各向同性分支下不变、散射因子缩放、跨帧重复性及原生存储转换。

硬件对 R11G11B10 的双线性过滤并不等于 FP64 理想插值。早期探针 `build/atmosphere-gpu/probe-yq6_2mep` 对原生 packed 与展开 float 纹理进行了隔离；只在离线积分中使用观测到的采样位置和光照后，MS 差异约为 4.2×10⁻⁷。没有修改生产 Shader 来强行消除采样器误差。

最新人工介质验证：

- Launcher：`build/ue-lighting-closure-cache/run-e57c2zeh/process-result.json`。
- 原始数组/布局/PNG：`build/atmosphere-gpu/run-0vpkrb5u`。
- 恒定介质透射率相对独立解析路径最大差异 1.40151×10⁻⁷。
- 地球半径人工介质的 MS 观测积分差异 3.86737×10⁻⁷；验收预算为 atol=10⁻⁶、rtol=10⁻⁵。
- 将观测半径代入独立介质方程，消光最大差异约 4.04×10⁻⁹；同时检查观测半径与原始位置的 FP32 运算包络。
- 地球半径透射率的理想 FP64 最大差异仍为 8.91×10⁻⁵。路径重建探针与生产编译器也可能采用不同收缩运算，因此该项使用由半径/路径/物理密度计算的保守空间误差区间，最大宽度约 0.00136。这是诊断性数值检查，不是逐指令误差证明或位精确一致。小行星恒定介质另有紧的解析检查，不能用宽区间替代。

验收不是只打印误差：medium、透射率区间和 MS witness 都有断言。`atmosphere_mutation_smoke.py` 只在隔离 Shader 副本中将原生及 float MS 输出同时清零，保留原始观察探针；验收因 0.06059196 最大偏差拒绝。成功拒绝证据为 `build/atmosphere-gpu/mutation-n91muvyj/result.json`，launcher `run-20z7ex7l`。独立规格/质量审查已通过人工介质部分。

## 源项目与集成状态

源配置盘点已完成：`build/source-project-inventory/targetmap-a92xs0p4/result.json`，进程退出 0，原项目文件与复制配置哈希均未变化。通过 UE 原生 GETALL/SHOWDEFAULTS 读取 CDO 的反射文本，再对照原始枚举声明解析；明确读得 sRGB、D3D12/SM6、Alpha CVars=0，选择 PF_FloatRGB。此前 Python 未导出类、属性别名及枚举转换失败已得到运行证据，因此不再依赖这些包装。

复制源渲染配置后，资产加载会生成异步 MeshCard 任务。导出器在退出前调用引擎已有的 `Editor.AsyncAssetCompilationFinishAll`，解决本机退出时 `MeshCardRepresentation.cpp:624` 的队列断言；没有修改渲染 CVar、禁用资产构建或保存源包。有效配置及材质内容由 `build_targetmap_scene.py` 保留至 Scene.json。

源参数 LUT 运行：`build/atmosphere-gpu/run-7ie9tom4/result.json`，launcher `run-xiwniclg`。独立 MS 观测积分最大差异 4.14887×10⁻⁷，源透射率理想 FP64 差异 9.12063×10⁻⁵；后者保守区间最大宽度 0.001395，仍受上述数值解释限制。两张 LUT 的原生存储转换与重复帧逐位一致。

`targetmap_atmosphere_smoke.py` 已通过：证据 `build/targetmap-atmosphere/run-swz869i6/result.json`，launcher `run-hvp9k63x`。接入 LUT 前后的 Opaque/CSM/Exposure 初始原始输出一致；三帧自动曝光反馈及 LUT 稳定性通过，Depth/Base0/Base1 draw 数仍为 4/3/1。目录保存三帧数组和八格 GPU Atlas（BaseColor、Normal、Depth、Shadow、Lighting、曝光结果、Transmittance、MS）。此时 LUT 作为独立输出接入图，还没有天空背景/环境光消费。完整 CPU 回归 384 项通过，git diff --check 通过。

## 下一步

2026-09-12 更新：原始 SkyView 与 M_SimpleSkyDome 主视图材质已接入，太阳圆盘、原始量化噪声、共享深度和自动曝光通过组件控制及完整源分辨率集成。最新报告为 `ue-legacy-native-sky-material.md`，源 Atlas 为 `build/sky-material-gpu/run-ihue_hpu/atlas.png`。下方早期“下一步”叙述保留历史语境；当前后续是实时 SkyLight capture/convolution、空中透视与云雾等。source-planet 更广数值包络和最终 RDC 图像匹配仍未完成。

目标 M_SimpleSkyDome 的原始材质仅包含 SkyAtmosphereViewLuminance + SkyAtmosphereLightDiskLuminance。接下来的消费者为自产 SkyView LUT、天空材质与太阳圆盘，再扩展实时 SkyLight cubemap/convolution。SkyLight 的 realtime capture 分支不能用常量环境色代替。

源方向光的颜色缺口现已接通，见下节。下一步是随原生相机更新的视图参数、SkyView LUT 与天空材质；尚不能据此宣称天空或最终图像一致。

源相机、纹理平台构建/流送、天空/环境、SSGI/DFAO、SSR 内部 TAA、云雾、局部曝光、Bloom/Tonemap、最终图像及 WebRTC 仍是完整目标的一部分。没有 HZB 或优化结构的独立对齐任务。

## 原生太阳颜色与地面透射率（2026-09-11）

`UESunSetup.cpp` 接收源组件设置，通过未改写的 `CalcRgbToXYZ`、`MakeFromColorTemperature`、`GetAzimuthAndElevation`、`GetTransmittanceAtGroundLevel` 和原始 sRGB 字面量表计算太阳输入。`UESunSetupSource.json` 记录每段原始字节的偏移、长度、文件与片段哈希。兼容层保留 FVector/FVector2D 的 double、积分位置/颜色的 float、15 次 float 累加循环、500m 起点与最低太阳高度角。颜色矩阵采用 double 余子式逆矩阵适配，不宣称逐指令复现 UE SIMD 或位精确一致。

`LightingConfig` 新增方向光 `source_sun`，方向只来自该 light 的 `direction_ue`。原生适配拥有派生 `color/source_radius`，禁止同时指定覆盖值。源场景和 Falcor 的方向光对象均调用同一适配；`ueLegacySourceSun` 可观察相同源设置的计算结果。当前支持源 sRGB、首个太阳、非逐像素大气透射率分支。其他分支明确拒绝；可配置色域、soft source angle 和大气光方向覆盖等更广源设置仍需后续盘点及支持。

targetmap 的源参数给出：outer-space RGB `(6.2649326, 5.8996105, 6.2141571)`，ground transmittance `(0.9038179, 0.8006717, 0.6495829)`，direct RGB `(5.6623583, 4.7236509, 4.0366101)`。这些数值由项目源码/源参数运行得到，没有使用 RDC 常量。太阳圆盘外太空亮度及半张角也已计算，天空消费者尚待实现。

验证证据：

- 独立 native CPU 测试 `build/sun-setup/run-fqrprirl`：真空、恒定介质 Beer 定律、最低高度角、非白 FColor、6500K、温度钳制和无效设置。首次测试在缺少实现时失败，随后通过。
- `build/sun-final-tests.log`：5 项 LightingConfig 测试通过，包含原生源太阳输入与派生量冲突拒绝；两项过时的捕获输入测试已修正为期待拒绝，生产拒绝策略未放宽。
- 最终 GPU：`build/targetmap-sun/run-4w6ell2x/result.json`，launcher `run-qeaotzg6`，退出 0、PASS、空 stderr。源码太阳与独立 FP64 oracle 的 ground transmittance 最大差异约 `2.8961e-6`、direct RGB 约 `1.5097e-5`；source-radius 检查是保守数值诊断，不是精确匹配证明。
- 在同一源场景对比关闭色温/地面透射的控制组，直射 diffuse 完整数组按计算出的 RGB 比例变化（rtol `2e-6`、atol `3e-6`）；深度、材质、四层 CSM、mask、两张 LUT 原始数据逐位不变。验证脚本不把读取到的 GPU 数据重新上传。
- Atlas 的 BGRA 原始字节与 SRV 逻辑通道进行了独立核对：阴影 R 在原始 byte lane 2，Atlas 使用逻辑 channel 0。布局、NPY 和 PNG 均保留。
- 自动曝光集成：`build/targetmap-atmosphere/run-17sr7axi/result.json`，launcher `run-34qtboqi`。三帧反馈及 LUT 稳定通过。完整 Python 回归 `build/sun-all-cpu.log`：385 项通过，`git diff --check` 通过。

构建使用项目自带 `tools/.packman/cmake/bin/cmake.exe`（3.24.1）及 Python 3.10.11。系统 CMake 4 与旧依赖配置不兼容；本轮恢复项目工具并成功构建，没有修改外部依赖的版本要求。

## SkyView 源数据准备

最新有效盘点更新为 `build/source-project-inventory/targetmap-74faehp7`，退出 0，源文件与复制配置哈希未变。新增实际组件世界变换、太阳 soft angle、两个大气光方向覆盖查询和四个工作色域色度坐标。结果为标准 sRGB primaries/white、大气组件 `(0,0,-6000)` cm、soft angle=0、两个方向覆盖均为 false。源方向光组件和 Actor 旋转相等。导出查询不设置覆盖或修改属性；覆盖属于该隔离 commandlet 的瞬时状态，不能推断交互 Capture 的临时状态。

`source_atmosphere` 现同时验证色域枚举和四组色度坐标；`source_sun_settings` 对尚未支持的非零 soft angle、启用方向覆盖明确拒绝。当前 `Scene.json` 已使用最新盘点重新组装。相机/材质/实例/Lighting/物理介质/LUT 设置与最终太阳验证输入一致。新鲜组合验证 `build/targetmap-atmosphere/run-nc0j0erp/result.json`、launcher `run-7c9a9sqb` 通过，三帧曝光和 LUT 稳定性未回归。完整 CPU 回归 `build/sky-source-all-cpu.log` 仍为 385 项通过。

后续实施见 `docs/superpowers/plans/2026-09-11-native-sky-view.md`。下节更新 `ComputeViewData`、相机动态 setup buffer 与 SkyView LUT；天空材质仍未完成。

## 原生动态视图与 SkyView LUT（2026-09-11）

`UESkyViewSetupOriginal.inl` 保留原始 `UpdateTransform`、`ComputeViewData` 和单位常量。`UESkyViewSetupSource.json` 记录原字节偏移、长度及哈希；double 世界坐标、`double(float(0.00001))` 变换系数、float 转换位置、地表上方 5m 钳制均保留。普通 `(Forward,Left,Up)` 基底行列式为 −1，Duff 极点分支为 +1，测试保留这项原始行为，没有统一成另一种手性。独立原生测试 `build/sky-view-setup/run-vcebtwqj` 通过。

首次动态图运行在相机移动时被旧的完整 Scene identity 拒绝。这暴露了静态参考图与原生相机运行的区别。现新增显式 `scene_identity_policy: dynamic_view`；默认 strict 不变，图封装及 Config 消费者共用校验。`build/sky-view-setup-gpu/run-jypkx60a` / launcher `run-cf_qjni8` 验证同一图内平移、转向、恢复、camera cut、材质变更拒绝及默认 strict 拒绝。SkyView/CSM setup 与原生深度响应相机变化，恢复后原始输出一致；自动曝光运行、普通运动延续历史、camera cut 递增 epoch 并使历史失效。原生 identity 回归 14 项通过。

Setup 输出 10 个 float4（160 字节）：天空平移相机；平移星球中心与高度；4 行原始 referential；太阳方向；外太空照度；圆盘亮度与半角；实际 UE cm 相机位置。它不保存预曝光；SkyView 的 Compute 节点显式读取本帧 `ExposureFrame.preExposure`。

`SkyViewLut.slang` 通过现有通用 Compute 执行。`UESkyViewHelpers.ush` / `UESkyViewLut.ush` 保留原始 `acosFast4`、UV 映射、普通视图坐标 helper、大气边界移动、MS 采样及 `RenderSkyViewLutCS`，并继续使用未改写的共享积分函数。来源见 `UESkyViewLutSource.json`；FastMath 的第三方声明保存在旁边。保留非线性距离采样、浮点 sample count 和最后的部分区间、0.3 采样偏移、HG/Rayleigh 相位、行星阴影、MS 及源亮度因子。此时为单太阳、无云/不透明物体大气阴影分支。原始 SkyView 永远传 FarDepthValue，因此适配层编译掉共享积分器中不可达的场景深度分支，没有伪造深度函数。后续云雾、天空 AO 与其他消费者仍需实现相应分支。

当前源 FastSky 结果：192×104，Min=4、Max=min(32×组件 scale,128)=32，距离倒数为 float32(1/150)。原生 R11G11B10 输出与相同浮点诊断计算的存储量化逐位一致；曝光反馈下恢复未曝光亮度的误差在 rtol 3e−6 / atol 1e−6 内，转向改变 LUT。最新证据 `build/sky-view-lut-gpu/run-xoyx14yo` / launcher `run-tahjn__2`：退出 0、PASS、空 stderr，保存每帧原始 LUT/Setup 与 Atlas。

独立 FP64 oracle `sky_view_reference.py` 不执行 Shader 文本。其 CPU 解析检查覆盖单位方向/极点/地平线、Beer 定律、曝光线性与 MS 响应。原生控制证据 `build/sky-view-controls/run-ia78h9t_` / launcher `run-2l4alhst`：真空零误差，恒定吸收的透射率最大差异 4.8471e−7，紧凑半径散射 RGB 最大差异 4.3710e−8；另含夜侧与大气层外视角。GPU readback 仅用于离线 oracle 观察，未上传回图。紧凑半径 gate 使用明确的数值容差，不证明源星球尺度逐位一致。将 MS 禁用或把 MS 响应缩小到 1e−20 的独立临时 Shader 都触发控制断言失败（launchers `run-hq9_9mnp` / `run-edpon_b2`）；生产源码未被修改。

完整 Python 回归 394 项通过。源场景天空材质/太阳圆盘、实时 SkyLight、SSGI/DFAO、SSR、云雾与后处理、WebRTC、相机/贴图平台构建匹配及 2.rdc 最终图像一致性仍未完成。主 Mesh 的外部材质图资源输入现已补齐（见下段）；接下来让原始 Sky 材质消费本帧 Setup/LUT，并进入共享 Packed/Depth/曝光链。

主材质新增 `materialBindings.resources`，可声明只读 Texture2D 或有明确字节长度的原生 raw Buffer，通过正常 RenderGraph 边连接。原有文件纹理/采样器/常量路径不变。`run-0g1obn2m` 验证原生历史驱动的逐帧生产者 → 真正 BasePass → Packed 解码颜色，共三帧；八项非法配置（含别名读取正在写入的主 MRT）拒绝且旧图原始输出不变。原有文件材质回归 `run-meavcwjl` 通过，最新完整 CPU 回归仍为 394。该框架入口已能供天空使用；原始天空采样和太阳圆盘函数仍未接入材质程序。
