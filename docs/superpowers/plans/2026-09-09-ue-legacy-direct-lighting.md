# UE Legacy 普通 Deferred Lighting 实施计划

> **For agentic workers:** 使用 subagent-driven-development / executing-plans。在既有 Falcor-m0 worktree 分工源码取证、Schema 生成与原生 Pass 集成；GPU replay、构建、GPU测试顺序执行，不提交，不改 UE/RDC。

**Goal:** 将真实 Packed GBuffer 接入目标 UE 的普通方向/点/聚光及模型 BRDF，保留已有 SceneColor，并以独立数值与实际 Capture 光照增量证明实现；继续完成原始完整骨干与最终画面对齐目标。

**Architecture:** 可选 Lighting Schema 注册并生成模型分派，独立 Shader 实现 BRDF/面积光数学。原生 LightingPass 直接读取 Packed 及覆盖/深度，以 UE 原始 LightData 单位工作，输出逐灯累加的 HDR 和拆分贡献。捕获的阴影/先前 SceneColor 只作为阶段验证输入，后续仍需真正的 CSM/GI/天空生产者。

**Tech Stack:** 本机 UE5.8.1 源码与 E2655 DXIL、RenderDoc replay、Falcor/D3D12/Slang、Python Schema/Pipeline 与独立 oracle。

## 实施顺序与范围

七模型 GBuffer 扩展已完成本批验收，现在进入主设计的普通 deferred Lighting。第一条 Capture 路径是 DefaultLit 方向光；方向光、点光和聚光的普通无阴影受控配置以及其源代码规定的 capsule 面积修正必须实现。再为现有六个新增模型接入真实各自 BxDF 和必要 LUT；未实现模型不可静默使用 DefaultLit。额外资源模型与后续算法继续保留在完整目标内。

Capture E2655 前已有 SSGI。必须导出前后 SceneColor、ShadowMask、实际 LightData/PSO，比较 Shader 原始贡献和相同基底上的累计结果；不能把最终目标颜色直接接到算法输出。独立源 LUT 可以作为经过身份冻结的算法资产，ShadowMask 等阶段结果只有显式 reference fixture 可以外部注入。普通延迟循环不命名为 Clustered；后续 Clustered 要实现真实目标光网格、索引与 fallback。

## 任务

- [x] 1. 固定 E2655 输入、前后 HDR、阴影衰减通道、LightData、viewport/blend、关键 DebugPixel 与源函数/active permutation。记录原 RDC 前后哈希及与本地源码的证据边界。见 `../../research/ue-legacy-lighting-capture.md` 与 `../../research/ue-legacy-direct-lighting-source.md`；4份DDS保留原始payload，前置SceneColor为2624，不使用2655结果作为输入。
- [x] 2. TDD 扩展可选 Lighting Schema：完整模型映射、公共分派、字段/资源/profile 契约、独立 lighting_hash；未启用时保持现有生成结果。测试缺资源声明、未知模型/入口、错误字段类型和失配合同。旧DefaultLit生成header/metadata字节黄金基线通过；真实DefaultLit/Unlit Shader GPU分派及ID迁移基础检查通过。完整算法验收属于任务4–6。
- [x] 3. 新建 `UELegacyLightingConfig` / `UELegacyLightingPass` / `UELegacyLighting.3d.slang`，接入 Pipeline snapshot、整图构建及 generation/输入身份。显式 UE LightData、无灯保留 emissive、逐灯 One+One HDR 累加、原始 diffuse/specular/transmission 观察输出，拒绝未实现能力和非有限输入。受控6例、HDR异常8例及无效sceneDepth 2例GPU验证通过；此项完成仅指原生Pass集成，算法/更多模型与Capture验收仍见任务4–6。
- [ ] 4. 在 `Codecs/Lighting` 移植 DefaultLit 的实际 Lambert、SphereMaxNoH、EnergyNormalization、UE GGX/Smith/Fresnel、capsule 与径向/spot 衰减；不替换 sqrtFast 等目标精度逻辑。实现 Unlit 的无直接光分支。独立 GPU oracle 覆盖角度、金属度、roughness、距离、光锥、面积半径/长度、单灯/多灯和无灯。
- [x] 5. 按已有模型注册接入 Subsurface、Skin、Foliage、Cloth、ClearCoat 真正 BxDF 与资源；特别保留本地 Subsurface transmittance-distance/HSV 分支、Skin 专用 LUT、ClearCoat 双层及底层法线条件。各分支独立验证，GBuffer 共享数学不意味着 Lighting 共用。
- [ ] 6. 原生重建场景直接消费自产 Packed，对 E2655 阶段做逐层对比并解释精度差异；再运行 Schema 迁移/回滚、Adapter、DefaultLit RDC 与资源身份回归，独立审查，冻结日志/中间输出/源码，更新主规划。未完成的 Lighting 子任务保持进行中。

## 验收原则

先比较原始 GBuffer、LightData、光照几何量、拆分贡献，再比较半精度 HDR 累加；图像仅辅助观察。硬件格式转换沿用独立探针，数学差异不能通过放宽到视觉近似掩盖。M2 单帧光照不等于阴影/天空/完整骨干完成；自动曝光保持启用。下一主线仍为 Lighting → SSR → TSR → Web。

## 当前交接（2026-09-09）

2026-09-10 第二批：LightingCommon 的共享BRDF/能量/Capsule数学已复用原字节UE函数并通过生产验证，见 [本批结果](../../research/ue-legacy-lighting-source-reuse-closure.md)。用户再次强调RDC不含Coat/Skin/Cloth；这些只属既有共享函数回归，不得作为RDC证据或加到重建场景。下一步优先该帧真实DefaultLit/方向光CSM与上游光照，不扩展额外模型。四级projection输入已导出，完整GPUScene深度producer依赖仍待补；严格HDR31处和完整骨干目标未完成。

2026-09-10 后续完成：BRDF 初始化/SphereMaxNoH 已直接使用原字节 UE 源码及薄适配，180 项 CPU、构建、生产 RDC 13 数组与 Mesh/Adapter Schema 迁移通过；严格 HDR 仍 31 处各 1 half ULP。用户已明确要求所有可复用源码尽可能复用；任务 4/5 中其余手写函数后续逐批替换为 UE 原函数，继续原始数值门槛与任务 6。见 [来源、范围与验收](../../research/ue-legacy-source-reuse.md)。下段私有准备描述为先前状态。

2026-09-10 最新：显式 diffuse mad 已进入生产并完成当前 GPU 回归，固定 172 项 UE diffuse 实测全部相同；179 项 CPU 与 Mesh/Adapter Schema 迁移通过。当前严格 HDR 为 31 像素各 1 half ULP，RGBA [14,8,9,0]。任务 4/6 继续进行，下一项以原字节 UE BRDF 初始化/SphereMaxNoH 加薄适配层验证直接源码复用，随后继续镜面链取证。完整 Shader 的 UE 资源/宏/材质生成依赖由兼容层适配；Schema/Codec 架构与主线顺序不变。下文未改生产等描述保留为历史，详见 [当前记录](../../research/ue-legacy-lighting-prefix.md)。

2026-09-09 当前调查：Schema／Codec 职责及实施顺序不变；原始 DXIL 的材质、N/V 与 Area.NoL 在 43 点共 516 个标量与 native 逐位一致。独立 diffuse 回放确认两点共 6 个分量不同；specular 探针因改变原 RGB 被拒绝，helper 重算也不能冒充生产局部值。已补强比较器并保留失败证据，生产数学未改，严格 HDR 仍 31 像素各差 1 half ULP。后续源局部值两图通过完整保护输出检查；两个 diffuseColor 差异点已观察，冷 cache 的 DXIL 显示局部值与光照输出共用独立乘减 producer。下一步验证局部精度修正并继续 specular 取证。详见 [Lighting 中间值调查](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-prefix.md)。完整管线与最终图像仍未完成。

2026-09-09 最新：Schema 管布局、字段/位段、ID、资源需求与分派；Shader Codec 管数学，Packed 主管线与既定顺序保持不变。七模型 GBuffer 与对应普通 Lighting Shader 已接入；本批 ClearCoat/Skin 的 224 组件样本、九原生图、Mesh/Adapter 双法线/ID/MRT/CustomData 迁移及缺失 LUT 回滚通过。Mesh HDR 仅通过给定独立单灯 GPU debug lobes 的非双法线累加区间检查，不是 half 位型或全图 BRDF 证明。新运行时 13 份 RDC 数值数组与上一版逐位一致，严格 HDR 仍 31 个像素各差 1 half ULP。原生阴影/GI/天空/自动曝光、Clustered、SSR、TSR、Web 与最终图像仍未完成。详见 [ClearCoat/Skin 报告](../../research/ue-legacy-coat-skin-lighting.md)。下方旧阶段数值与状态按历史理解。 任务5受支持 profile 的模型移植和有界验收已完成；任务4及6保持进行中。

任务5已有三模型子集：Subsurface保留透射距离/消光/HSV分支，Foliage使用活跃wrapped diffuse/GGX分支，Cloth使用PC inverse GGX/Vis_Cloth。115组件样本与七原生图通过，非零CustomData/ID/MRT迁移在Mesh及Adapter各自通过15项逻辑与原始物理检查；174项离线检查通过。严格两灯sum限于三个float32调试瓣；HDR零灯/背景保存、非零/迁移通过，HDR多灯/透射独立oracle仍待补。任务5的ClearCoat双层/底层法线及Skin专用LUT尚未实现，任务4–6保持未完成。最新固定归档见 `../../research/ue-legacy-model-lighting.md`。以下是此前阶段的交接记录。

任务3原生LightingConfig/LightingPass/3d Shader、Mesh及Adapter图接线已经落地；候选整图执行、输入身份和资源绑定名冲突防护已接入。任务4的DefaultLit/Unlit与方向/点/聚光受控6例、187样本capsule组件GPU检查通过；未按这些子集测试宣称完整Lighting已验收。8个HDR异常fixture及2个人工无效sceneDepth的真实GPU执行拒绝与原图/generation回退通过；后者复用实际RDC相机/几何，以GPU读回深度证明精确消去/下溢，不是物理相机有效性或所有内部BRDF退化条件验收。按Decode位置放Point的实验仍不能证明lightPS精确零距离。

任务6已渲染真实RDC场景的E2655 Lighting：Packed/depth/stencil/覆盖和BasePass表面HDR全部一致。生产VS采用实际UE顶点流程及运行时gInvViewSize后，41个选定ScreenVector输入逐位一致，PS/BRDF源码未改；最新Lighting还剩31个像素各1halfULP不同（RGBA为13/8/10/0），逐位验收仍失败。29个残差的旧生产版本及其归档保留为历史，不能认证新实现。继续取证PS中间值及运算分组，不按残差数量选择公式。

新增非零Lighting Schema迁移已在Mesh/Adapter各自的baseline/migrated四图实测：Directional+Point两灯、全部MRT顺序/名称、normal/baseColor/HDR路由、metallic/roughness通道及modelID位段/ID迁移，各路径14项逻辑输出与物理排列逐位通过；CodecHash/LightingHash、数学和运行时在测试内不变。新生产版本的六组直接光、八组HDR拒绝/回退、两组无效sceneDepth拒绝/回退，以及170项离线/4项CPU测试均有记录。任务4–6仍未完成，任务5其它模型真实BxDF尚未实现。最新阶段见 `../../research/ue-legacy-lighting-view-inputs.md`，主线仍继续Lighting→SSR→TSR→Web。

后续任务6定位进展：新正常/仅radiance诊断图各12个未改输出与冻结production逐位相等；UE PixelHistory覆盖31个当前残差+12控制点，31个残差在混合前RGB均有不同，最大5float32ULP，pre/post附件核验通过。复用24个旧输入并补采19个后，同43点ScreenVector全部逐位一致，包含全部31个残差。取证没有修改生产数学，下一步继续实际PS中间值/运算顺序。见 `../../research/ue-legacy-lighting-current-residuals.md`。
