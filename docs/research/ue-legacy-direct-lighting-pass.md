# 原生普通 Deferred Lighting：当前阶段

2026-09-09 最新：Schema 管布局、字段/位段、ID、资源需求与分派；Shader Codec 管数学，Packed 主管线与既定顺序保持不变。七模型 GBuffer 与对应普通 Lighting Shader 已接入；本批 ClearCoat/Skin 的 224 组件样本、九原生图、Mesh/Adapter 双法线/ID/MRT/CustomData 迁移及缺失 LUT 回滚通过。Mesh HDR 仅通过给定独立单灯 GPU debug lobes 的非双法线累加区间检查，不是 half 位型或全图 BRDF 证明。新运行时 13 份 RDC 数值数组与上一版逐位一致，严格 HDR 仍 31 个像素各差 1 half ULP。原生阴影/GI/天空/自动曝光、Clustered、SSR、TSR、Web 与最终图像仍未完成。详见 [ClearCoat/Skin 报告](ue-legacy-coat-skin-lighting.md)。下方旧阶段数值与状态按历史理解。

Falcor-m0 已接入 `UELegacyLightingPass`。它直接读取当前 Schema 的 Packed 附件、primaryCoverage 和 depthCopy；Decode 仍只是观察输出。Schema 负责字段访问、模型注册与分派，独立模型 Shader 实现光照数学。该阶段是逐灯普通 deferred raster，不是 Clustered Lighting。

## 已落地的行为

- 从 Schema 的 sceneRadiance/sceneAlpha 初始化 HDR，或使用显式 reference_fixture 的前置 HDR；零灯也验证模型与初始颜色并保留原值。
- 每灯独立全屏 draw，RGBA16Float HDR 使用 One+One；三个 RGBA32Float MRT 分别输出曝光前的 diffuse/specular/transmission。
- 方向光、点光、聚光使用 UE 单位和原始 Shader-ready LightData。包含普通 capsule 面积修正、逆平方窗口/幂衰减、spot cone、阴影 mask 解码、roughness 下限和 preExposure。
- 材质模型必须完整注册其 Lighting 程序、字段、资源和 profile。当前真实 Lighting 程序有 DefaultLit、Unlit、Subsurface、TwoSidedFoliage、Cloth；PreintegratedSkin 与 ClearCoat 的 Lighting 尚未实现。
- 整图 generation/Pipeline/输入身份校验、离屏候选执行与失败回退已接入。模型资源不可覆盖附件、depth、coverage、CB 或内部错误缓冲绑定；reference fixture 不可绕过显式模式限制。
- 检查初始 HDR、重建深度/几何与 Area 输出的有限值。检查范围不等于所有 UE BRDF 内部退化分支都被拒绝；不增加 epsilon 修改目标公式。

## 当前验证

最新[三模型Lighting验收](ue-legacy-model-lighting.md)：174项离线、115个组件样本和七个原生图通过。Mesh/Adapter两路径非零CustomData、ID位段、MRT名称/槽位迁移各15项逻辑检查逐位一致。三瓣float32 debug的两灯sum逐位一致；HDR只证明零灯/背景保存、非零响应和迁移一致，原生HDR多灯/透射独立oracle仍待补。其它灯型及阴影的新增模型原生验收也未完成。该批未改现有DefaultLit数学、未重跑Capture；下列此前各阶段证据仍按各自冻结版本理解。

最新生产输入和 Schema 非零灯迁移的完整边界见 [当前报告](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-view-inputs.md)。VS 修复后 41 个选定 ScreenVector 输入逐位对齐；受控六灯例、HDR 八例、几何两例均已在新生产版本重跑。下述 Capsule 组件为其冻结源码身份下的历史验证，未在本次重复执行。

170 项 Python 离线测试、4 项原生 LightingConfig CPU 测试通过。绑定名覆盖问题先由负测复现，再验证修复；主图输入不会被模型 DDS 替换。

`direct_lighting_smoke.py` 的六组真实图验证通过：零/一/两方向光、逆平方 Point、幂衰减 Point、Spot。每组有117,087覆盖像素，其中106,842 DefaultLit、10,245 Unlit。独立 NumPy 点源 BRDF/局部衰减 oracle、Unlit emissive/背景保留、逐灯计数及两灯累加通过；零灯 HDR 附件改名和rgb→bgr布局迁移后逻辑输出逐位一致。受控测试的误差界不是 Capture 的验收界。

`lighting_schema_migration_smoke.py` 进一步在 Mesh 和 Adapter 两条路径各自使用 Directional + Point 两盏非零灯。仅改 Schema 的全部 MRT 顺序/名称、字段通道及模型 ID 位段后，各路径的 14 项逻辑输出（含 Lighting）逐位相等，原始物理附件符合预期排列；CodecHash/LightingHash 与运行时在测试内保持不变。四个真实运行的 [结果](E:/Project/falcor/Falcor-m0/build/lighting-schema-migration-evidence/result.json) 分别保存实际生产者/消费者身份与原始 NPZ。

`capsule_lighting_smoke.py` 的187个真实GPU样本通过，分别观察 Area 几何、SphereMaxNoH、有限光源能量、DefaultLit各瓣和sqrtFast位型。包含81个Newton、30个反射内分支、71个线光、92个软半径样本；样本的条件数约束和预先声明的浮点误差界见脚本与结果。该检查不能替代低粗糙度 Capture 的逐位比较。

`lighting_fixture_rejection_smoke.py` 已在原生执行路径验证8组HDR拒绝：NaN RGB/Inf alpha × 0/1灯 × covered/background。各例均触发flags8，失败后立即读取及重新渲染的旧图、generation、输入身份与原始输出保持逐位一致。另一个按Decode.positionW放置Point的实验未证明lightPS的实际距离精确为零，不能作为“已复现并修复零距离”证据。

`lighting_geometry_rejection_smoke.py` 的两组原生GPU验证通过。正例使用同一RDC四网格、捕获相机及阶段输入，实际读回Depth.depthCopy；两组人工深度系数分别导致精确消去和正数乘法下溢。零灯候选通过原生配置且上游Packed/depth/coverage字节不变；同系数单灯候选在native execute触发flags16，失败后立即及重渲染的旧图、generation、输入身份和全部观察输出逐位保留。这仅证明无效sceneDepth防御，不代表物理相机有效或所有BRDF退化条件已覆盖。

## RDC E2655 数值状态

原生四Mesh自产A/B/C/D、D32S8深度/stencil、覆盖与BasePass表面HDR全部与原始Capture一致。Lighting使用E2624前置SceneColor、实际ShadowMask和白色AO作为显式阶段fixture；E2655目标输出仅供渲染后的CPU比较。真实阴影、SSGI和最终画面的其它生产者仍需实现。

历史首次Light draw比较有95个像素不同（94个1halfULP、1个2halfULP）。同版本Slang CLI对冻结Shader的DXIL表明，优化器把主输出的光色/曝光提为公因子，形成 `(exposure*lightColor*mask)*(specular+diffuse)`；Capture按各瓣乘光色、求和、最后曝光。`precise`约束最终累加并向其依赖链传播后，当时的生产版本还剩29个像素不同，全部1halfULP。对固定旧快照重算，其中14处原先已不同、15处是新增位置；不能只看差异总数声称所有位置改善。该历史归档为 [ue-legacy-direct-lighting-pass-result.json](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-direct-lighting-pass-result.json)，不得用来认证后续修改后的生产版本。

当前生产已修复实际观测到的顶点/插值输入差异，41 个选定输入逐位一致；PS/BRDF 源码保持不变。最新严格比较有 **31 个像素/31 个通道不同，RGBA 为 `[13,8,10,0]`，每处 1 half ULP**，完整1424×1040分配中最大绝对差为0.0009765625，alpha没有差异。当前生产结果在 `build/production-lighting-input-evidence/run-1uao0dw5/normal/{native-outputs.npz,outputs.npz,lighting-result.json}`。没有放宽到视觉近似，也没有把目标颜色作为输入。诊断临时Shader及CLI产物只是定位证据，不能冒充运行时Shader dump或独立完成证明。详见 [输入取证](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-interpolants.md)；`ue-legacy-lighting-numerics.md` 保留修复前的数学调查。

## 尚未完成

剩余数值差异、ClearCoat/PreintegratedSkin Lighting、原生HDR多灯/透射独立验证、真实阴影/GI/天空/自动曝光生产者与Clustered尚未完成。随后仍按SSR→TSR→Web推进，保留目标UE算法及自动曝光要求。整个渲染骨干与最终Capture图像一致性保持进行中。无提交、暂存、合并；UE源码与RDC保持只读。
