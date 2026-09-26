# ClearCoat / PreintegratedSkin 的 Schema 与原生 Lighting

2026-09-09，实施目录 `E:/Project/falcor/Falcor-m0`，分支 `codex/ue-legacy-m0`。已有七模型 GBuffer 现在都有对应的普通 Lighting Shader：Unlit、DefaultLit、Subsurface、PreintegratedSkin、ClearCoat、TwoSidedFoliage、Cloth。本批完成 ClearCoat/Skin 的受控组件与原生集成验收；整个 Lighting、Clustered 与最终画面对齐仍未完成。

## Schema 与算法边界

`Schemas/OpaqueLightingModels.json` 注册七模型、逻辑字段、ID、Codec/Lighting 路由和消费者要求。生成器产生布局访问及模型分派；`Codecs/Lighting/ClearCoat.slangh`、`PreintegratedSkin.slangh` 实现实际 BxDF，`.lighting.json` 声明能力与资源合同。没有把数学搬入 Schema，也没有用 DefaultLit 替代这两个模型。

新 generation：`a4200f79df3b28506b0a54706388f27126ce03a7d7cf763f578a2967f446a893`。LightingHash：`3123fe1963e0a8def22c46524f1f1a946bd186d6e85122ecf0b8ade097be6a73`。现有 GBuffer Schema/Codec、Common 和此前模型数学未改。

Mesh 或显式 Adapter 写入 Packed，原生 Lighting 直接读取相同契约。Decode 是观察及验收支路。材质程序、材质实例、ShadingModelID、Mesh Pass 仍是不同概念；Mesh/Pipeline 继续负责筛选、Shader、PSO、MRT 和执行依赖。

| 模型 | 保留的目标 UE 行为 |
|---|---|
| ClearCoat | 双层 BRDF、底层法线路由、顶部 sphere/Newton 条件与恢复、折射多项式和 clamps、金属吸收、未折射 VoH 的底层 EnergyNormalization、Area.NoL visibility 与 coat=0 的共享折射 D/Vis |
| PreintegratedSkin | 独立 skinBRDF LUT，mip 0，UV 为 `(saturate(dot(N, DiffuseL)*.5+.5), 1-opacity)`，保留真实 diffuse/specular/transmission 数学 |

原生 Pass 增加 `gLightingBilinearClamp`：Linear min/mag、Point mip、Clamp UVW、LOD 0..FLT_MAX、bias 0；配置层保留该绑定名，拒绝纹理资源覆盖它。源 LUT 为捕获的 256×256、单 mip、BGRA8_UNORM_SRGB；DDS payload 与原始导出完全相同。

## 数值验证

- 新能力的五项离线测试先失败后通过；全套离线共 179 项。UELegacy 与 FalcorTest Release 构建通过，4 项原生 LightingConfig CPU 测试通过。绑定名冲突另有原生 RED/GREEN 记录。
- 224 个 GPU 组件样本，包括 166 个 ClearCoat、53 个 Skin、5 个旧模型控制，在两套模型 ID 下输出逐位一致。包含双法线、面积光与折射上下限、反射落在球内、正 NoL 下不同 DiffuseL/SpecularL 等分支。
- 原误差预算不变：diffuse/specular rtol=1e-3、transmission rtol=4e-5，atol=2e-6。Capture 门槛继续使用原始位型。
- 九组原生图：Mesh 的零灯/前灯/背灯/两灯/双法线/迁移双法线，Adapter 的两灯/双法线/迁移双法线；每图每可见模型选取 256 个确定像素，共 6912 个输出像素样本。其中零灯图 768 个校验零输出，其余 6144 个对照独立模型算术。
- 两条路径各有 15 项逻辑输出迁移检查；额外验证原始 B 的 ID 位段与非零 D 的通道重排。双法线使每条路径的 diffuse/specular/HDR 各改变 30,735 个通道，迁移后逻辑输出逐位一致。
- 两条路径缺失 Skin LUT 候选都被拒绝；立即读取和重渲染后，旧图、generation、history epoch 及全部原始输出保留。

Skin 的独立理想 CPU 双线性采样在最初两个样本失败。单独 GPU 采样观察确认：UV 一致，四源 texel Load、手工 lerp 与 float 纹理采样一致，而 sRGB 纹理 SampleLevel 的两个红通道高 `1/16384`。因此保留理想 CPU 预期与失败记录，以独立 CPU 算出的 UV 驱动无模型数学的 GPU 采样探针，再交给独立 CPU Skin 算术 oracle。这个范围是**给定独立硬件采样结果的算术验证**，不能称为纯 CPU 过滤等价或新模型 Capture 对齐；没有拟合舍入公式或放宽容差。

## HDR 与 DefaultLit 回归

三个 float32 debug lobes 的两灯和逐位相等。另有**给定独立单灯 GPU debug lobes 的 Mesh HDR 累加区间检查**：仅覆盖非双法线的前灯、背灯、两灯三图，每图 230,400 像素；每步 source conversion 与 half target addition 采用格式推导的向外 half 区间。所有像素均在区间内，alpha/背景逐位保留。两灯最大区间宽 `0.0068359375`；漏第二灯负例拒绝 9920 像素，漏 transmission 的区间在 13022 像素不相交。这不证明 half 位型完全一致、全图 BRDF、Adapter 或双法线 HDR 累加。

新运行时重新创建 Pipeline 并原生渲染真实 RDC 重建场景，13 份数值数组与上一版生产输出逐位一致；旧基线通过既有 CAS 绑定，不用新 DLL 认证旧 Pipeline。Packed A/B/C/D、实际 depth/stencil、覆盖与 BasePass 表面 HDR 继续通过原门槛。

严格 E2655 HDR 仍有 **31 个像素 / 31 个通道，各差 1 half ULP**，RGBA 为 `[13,8,10,0]`，最大绝对差 `0.0009765625`。阶段输入仍使用明确的 E2624 先前 HDR/阴影/AO fixture，E2655 目标只用于渲染后比较。生产外层 Shader hash 保持 `e307672ef52185b2f1a40c7bfb0e5e62bd632a8189e5bc643aa65327dcf36239`；新插件 hash 为 `8fbdbaccf347b095da0bfdbe90f9b8257d7dbe8e84a99c546f00fc960d8ed131`。

## 固定证据与后续

- 组件：`build/coat-skin-lighting-evidence/run-npj8920o/result.json`，SHA256 `9da9608e8fb96c1da5aeb60f29c43da9bdf2fd08aac461b271fbba897dda159e`。
- 原生：`build/coat-skin-lighting-pass-evidence/run-kq9iygrq/result.json`，SHA256 `a4b3e21efcaacc4bdc2887272c18fb207ed94414a55df4b2142db0afa6e3603d`。
- HDR：同目录 `hdr-accumulation-bounds-v2.json`，SHA256 `266ae4d6092a8015056c6fde59313b90170258526dec9be0ceb4db2201a6a22b`。原始图报告中的“无 HDR oracle”保留其生成时范围，由这个独立补充报告提供上述受限证明。
- DefaultLit：`build/coat-skin-defaultlit-regression/run-0fmjunbi/result.json`。
- [归档结果](ue-legacy-coat-skin-lighting-result.json) 保存源码、运行时、Schema/Pipeline/Scene/资源闭包、原始 NPZ 及历史基线关系。外部 Falcor shader/import 基线仍是外部依赖；CAS 是证据集合，不是完整可独立运行的环境包。

归档 SHA256：`960e9f7bbd710388f9cc75231007ba341191115f94dd8f489968df4d81f36b95`。522 条记录、368 个独立 CAS 文件、43 个观察节点闭包、26 份 NPZ 检查。归档复算使用原生执行时的 Python 3.10.11 / NumPy 1.26.4，保存的组件及原生独立预期严格相同；其他 Python/NumPy 组合曾产生约 `5.2e-17` 的 CPU 双精度差异，没有据此修改 GPU 验收门槛。

独立规格与质量审查通过上述有界范围。规格审查独立重建九图的采样位置、10,752 份逐灯输入与 CPU UV；保存输入及预期严格一致，并从物理 BGRA 独立核验底层法线。质量审查补正零灯样本的计数措辞，并独立复核 HDR 区间与 13 份 DefaultLit 回归数组。归档后重新运行的 179 项离线测试通过，补充日志为 `build/lighting-contract-evidence/coat-skin-offline-final.log`；最后的文档更新与这份日志不包含在此前冻结的运行目录记录中。

本批原生集成限于无阴影 Directional。普通逐灯光照不称为 Clustered；原生阴影/GI/天空/自动曝光、目标 UE Clustered、SSR、TSR、Web 和最终画面一致性继续保留在主线。下一步仍在 Lighting 阶段定位 31 处 PS 差异并实现缺失生产者，然后依序 SSR → TSR → Web。自动曝光需求不变；UE、测试工程与 RDC 保持只读，无暂存、提交或合并。
