# 三种模型接入 Schema 与原生 Lighting（历史阶段）

当前七模型 Lighting 状态见 [ClearCoat/Skin 报告](ue-legacy-coat-skin-lighting.md)。以下保留三模型新增阶段的源码身份与验收范围；其中未完成项以新报告为准。

2026-09-09，实施目录 `E:/Project/falcor/Falcor-m0`，分支 `codex/ue-legacy-m0`。本批在已有 DefaultLit/Unlit 上新增 Subsurface、TwoSidedFoliage、Cloth 的真实 Lighting Shader。七模型 GBuffer 编解码与五模型 Lighting 是不同进度；ClearCoat、PreintegratedSkin 的 Lighting 尚未完成。

## Schema 分工保持不变

`Schemas/DirectLightingModels.json` 声明五个模型、存储字段、ID、消费者要求与 Lighting 程序路由；`Codecs/Lighting/*.slangh` 实现各自数学。Subsurface 与 Foliage 共享 GBuffer Codec，但分派到不同的 Lighting Shader。添加或迁移 ID 不修改模型公式。

原生链路为 Mesh/显式 Adapter → Packed 附件与 depthCopy → Lighting。Decode 只是观察和测试采样支路。材质程序负责产生表面属性，Mesh/Pipeline 契约负责选择 Mesh、Shader、PSO、MRT 与依赖；它们与 ShadingModelId、GBuffer Codec 分开。

新 Schema generation 为 `89e19699064e7cfe036ada4e4ba19a94ce37c3930acb5c9fa019654f079b3944`，LightingHash 为 `7f6edf7f72a50a49332d9c2683a91622b830e3ddcfb4b48943a0aa060a50d8a6`。原 OpaqueModels 与无 Lighting 默认生成契约保持不变，默认 generation 仍是 `7a16385f8892c70736c9f5ec0915b925bc6a95d8b5529d3143354b387a170910`。

## 保留的 UE 数学

| 模型 | 实际实现 |
|---|---|
| Subsurface | DefaultLit 表面瓣，DiffuseL 背散射与 InScatter，允许 InScatter 超过 1；透射距离/消光/HSV 色彩恢复，保留 1e-12 与 1e-10 原始分母规则 |
| TwoSidedFoliage | 当前 UE 活跃分支的 wrapped diffuse 与 GGX 散射，使用 DiffuseL；其 BxDF 透射不依赖 opacity/AO |
| Cloth | 普通 GGX 与 inverse GGX fuzz，实际 PC Vis_Cloth、Schlick 和饱和 cloth 权重；使用 SpecularL 与共享面积修正 |

依据本机 UE5.8.1 的 `ShadingModels.ush`（Cloth 674、Subsurface 716、Foliage 活跃分支 941），`BRDF.ush` 685–695、`ColorSpace.ush` 227–255、`ParticipatingMediaCommon.ush` 170–185。受支持 profile 继续关闭 energy conservation、rough diffuse、anisotropy、rect light；缺少的模型/profile 必须拒绝，不能静默退成 DefaultLit。

现有生产 Lighting 外层、Common、DefaultLit、Unlit 数学未修改。外层 Shader SHA256 仍为 `e307672ef52185b2f1a40c7bfb0e5e62bd632a8189e5bc643aa65327dcf36239`。

## 验证与范围

- 174 项离线检查通过，含模型路由、必要字段合同和 ID 迁移；缺实现的测试曾先失败。
- 115 个组件样本在两套模型 ID 下运行 GPU，原始输出逐位相同。独立双精度 oracle 覆盖正/背光、面积修正、DiffuseL/SpecularL 分离、吸收/HSV、AO 与 cloth 权重边界及 PC grazing visibility。误差预算预先规定为表面瓣 rtol=1e-3/atol=2e-6、透射 rtol=4e-5/atol=2e-6，不改变 Capture 逐位门槛。
- 七个原生图通过：Mesh 零灯/正向/反向/两灯/迁移两灯，Adapter 两灯/迁移两灯。每图 117,087 覆盖像素，三模型分别为 10,245/13,022/93,820；每模型最多 256 个确定采样点与独立 oracle 比较。
- 两条路径分别迁移全部五个资源名称/MRT 槽位、CustomData rgba→bgra、模型位段至 offset=2/width=5，以及 ID 至 15/17/19。15 项逻辑检查逐位一致；非零原始 D 通道重排、B 模型位段和逐像素模型路由均检查。CodecHash/LightingHash 不变。
- 实际 producer/Decode/Lighting 的 generation、Pipeline 与输入身份一致；运行时前后哈希不变。新归档重新核验 21 个观察节点对应的 Pipeline/Scene/资源闭包，156 条记录、117 个独立 CAS 文件，并从原始 NPZ 重算组件/采样 oracle 与迁移检查。

两灯逐位求和只证明三个 float32 调试瓣的累加。HDR 目前证明零灯/背景保存、非零响应和布局迁移一致；原生 HDR 多灯/透射的独立累加 oracle 仍待补。旧原生报告中的 conservation/accumulation 措辞过宽，新归档的 `native_scope_correction` 明确收窄为上述范围；旧报告和冻结脚本保持原样，当前脚本只修改说明文字。

本批原生模型集成限于无阴影 Directional。Subsurface 的吸收/阴影透射参数在组件层验证；它不证明原生阴影生产者已存在。组件与抽样验证也不等于全图 BRDF 或新模型 Capture 等价。

## 固定证据

[新归档报告](ue-legacy-model-lighting-result.json) SHA256：`0a25ce41d20bf9289b56f440a2a30183884200bd0cb808ad1271314e2d9b7ebd`。各文件按内容寻址保存于 `build/model-lighting-acceptance/archive`。报告区分运行时已记录的依赖身份与归档时额外源码快照。

独立规格及质量审查在上述受限范围通过；复核115组件、七图共5376个采样、迁移、九份NPZ、522条记录身份边与21节点闭包。646个运行时Shader/import的外部基线仍标记为external；117个CAS文件不是完整可独立运行的环境包。当前脚本与冻结执行版除顶层docstring外AST一致。

- 组件：`build/model-lighting-evidence/run-r9b4y5wd/result.json`，SHA256 `c759167927f6d6630f3424d6b110d75d56bdbf29e8aac0db11ae14356378e72b`。
- 原生：`build/model-lighting-pass-evidence/run-scw83nty/result.json`，SHA256 `30879adb29dc3c46256162d8dcee6321a9e8f9a140641c38f0e6a0c0b4b4d4f7`。
- 日志：`build/lighting-contract-evidence/model-lighting-{offline,component-final-gpu,pass-accepted-gpu}.log`。

此前失败或运行中编辑过检查器的目录不作为最终证据。归档工具只重验现有输出，没有重跑 GPU 或 RenderDoc。

## 未完成项与顺序

DefaultLit 当前严格 E2655 结果仍有 31 个像素/31 个通道各差 1 half ULP，本批未重跑或认证新的 Capture 数值；其生产路径未变。继续补 ClearCoat 双层/底层法线、Skin 专用 LUT、原生 HDR 累加验证、这 31 处 PS 数值差异及阴影/GI/天空/自动曝光生产者。普通逐灯延迟光照仍需扩展成目标 UE Clustered 算法。

主顺序保持 Lighting → SSR → TSR → Web；自动曝光需求保留。整个骨干与最终图像一致性仍未完成。
