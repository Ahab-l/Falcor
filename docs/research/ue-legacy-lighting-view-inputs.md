# Lighting 输入修正与 Schema 非零灯迁移

2026-09-09。生产 Lighting 已采用实际 UE 全屏三角形顶点流程；41 个选定的 ScreenVector 输入逐位一致。Mesh 和 Adapter 的非零灯 Schema 迁移均通过逻辑与物理布局检查。**严格 E2655 HDR 验收仍失败：31 个像素各差 1 half ULP；普通 Lighting 及整个渲染骨干没有完成。**

## Schema 仍是主管线契约

Schema 描述附件格式、MRT slot、字段通道/位段、模型 ID、有效字段、模型入口、资源和路由；生成器生成公共定义、访问器及分派。MaterialProgram 计算原始材质属性，GBuffer Codec 编解码数学，Lighting Shader 实现模型 BxDF。三者职责不互相替代。

`UELegacyGBufferPass` 直接生成 Packed，Lighting 直接读取这些附件及 coverage/depth。Falcor 原生 GBuffer 通过显式 Adapter 接入相同契约；Decode 是观察端。Falcor 负责场景、资源、RenderGraph、Shader 编译和 GPU 执行。

[非零灯迁移结果](E:/Project/falcor/Falcor-m0/build/lighting-schema-migration-evidence/result.json) 包含 Mesh baseline/migrated 和 Adapter baseline/migrated 四个实际图。每图使用 Directional + Point 两盏灯，覆盖 117,087 个像素（106,842 DefaultLit、10,245 Unlit）。迁移只改变 Schema：

- 全部 5 个 MRT slot 和资源名称。
- normal/baseColor/初始 HDR 的 RGB 通道路由、metallic/roughness 通道。
- modelID 位段改为 offset 2、width 5；Unlit ID 改为 7，DefaultLit 改为 13。

两条路径各自的迁移前后均通过 14 项逻辑逐位比较，包含 Lighting HDR 及 diffuse/specular/transmission；另检查原始附件的精确排列及实际模型 ID 位型。该测试不要求 Mesh 与 Adapter 彼此逐位相同。格式和精度未变，CodecHash/LightingHash/数学与运行时文件在测试内未变；生成的 Schema、Pipeline、Scene、依赖及原始 NPZ 均记录身份。

独立只读复核重算四份 NPZ 的全部数组哈希及两路径比较，并逐项破坏 14 类逻辑、5 类物理结果验证拒绝；把基线与自身误比较也会被物理存储应有变化的断言拒绝。CustomData 在这些 DefaultLit/Unlit 场景中始终为零，该附件只证明槽位/名称迁移和清零保持，不证明非零 CustomData 或其它模型 BxDF。

## 生产输入修正

`UELegacyLighting.3d.slang` 使用实际 UE 顶点顺序、clip 融合运算和 View 矩阵分组。C++ 按当前有效 ViewRect 上传 `gInvViewSize`，该名字纳入资源绑定冲突拒绝。生产没有帧专用倒数、clip 或 ScreenVector 常量。`initPS` 至末尾 7,385 字节、18 份 Codec 和 2 份 Schema 保持不变。

[最终生产输入回归](E:/Project/falcor/Falcor-m0/build/production-lighting-input-evidence/run-1uao0dw5/result.json) 中，正常图和只观察 ScreenVector 的诊断图之间，12 个未改输出全 allocation 逐位相等。41 个预先冻结的采样点有 123/123 分量与 UE 初始调试输入相同，最大 float32 ULP 距离为 0。参考来自 RenderDoc 插桩回放；这不是所有像素或未插桩插值的独立证明。候选和生产证据详见 [输入取证](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-interpolants.md)。

同轮 Release 构建、170 项 Python 离线测试、4 项 LightingConfig CPU 测试通过。新生产版本上顺序重跑的六组直接光、八组 HDR 拒绝/回退、两组无效 sceneDepth 拒绝/回退均通过。已有 187 样本 Capsule、130 样本 LightTerms 组件证据对应其记录的历史源码身份，本次没有重复运行，也不替代 Capture 验收。

[本批归档](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-view-input-result.json) 保存当前 41 点输入、Schema 迁移及受控回归的源码/输入/运行记录，并通过旧 CAS 保留历史证据；不包含后续 43 点数值调查。49 个源码路径与执行记录绑定，另外 33 个只标为归档时源码快照。六例直接光旧报告没有记录逐 NPZ 哈希，因此这些原始包只有归档时哈希和人口计数交叉检查；构建/CPU/离线日志没有独立源码哈希证明。归档明确区分这些限制，不用当前运行库认证历史运行。

## 尚未通过的边界

[正常图严格报告](E:/Project/falcor/Falcor-m0/build/production-lighting-input-evidence/run-1uao0dw5/normal/lighting-result.json) 在 1424×1040 allocation 的 1,480,960 个像素上比较，RGBA 不同通道数为 `[13,8,10,0]`，共 31 个像素，每处 1 half ULP，最大绝对差 `0.0009765625`。唯一失败 gate 为 `lighting_hdr_full_extent_half_bits_exact`。Packed/depth/stencil/覆盖和 BasePass 表面 HDR 一致，颜色全有限。

E2624 初始 HDR、实际 ShadowMask 和白色 AO 是显式阶段 fixture；E2655 目标颜色仅用于渲染后的比较。当前只实现 DefaultLit/Unlit BxDF，执行方式是普通逐灯 raster。其它模型光照、原生阴影/GI、真实 Clustered、SSR、TSR、Web 及天空/云雾/曝光/ToneMap 仍需实现，自动曝光的用户要求保持有效。

任务 1–3 的阶段完成状态不改变任务 4–6 的未完成状态。后续独立的 [31 个当前残差取证](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-current-residuals.md) 已补齐 43 个采样点（含全部 31 个残差）的初始 ScreenVector 逐位证明，并确认残差点的混合前 Shader RGB 也有差异。该后续取证与本批 41 点输入/Schema 迁移证据分开，生产数学未修改。继续核对 PS 中间值及目标指令顺序，不按误差像素数试选公式，不放宽原始 Buffer 验收标准。
