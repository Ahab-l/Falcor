# Lighting 的 Schema 契约与当前状态

2026-09-09，实施目录 `E:/Project/falcor/Falcor-m0`，分支 `codex/ue-legacy-m0`。

Schema 仍只管理 Packed GBuffer 布局、字段/位域、模型 ID、有效字段和路由。Shader Codec 实现编解码数学；独立 Lighting Shader 实现模型 BxDF。材质程序、材质实例、Shading Model 与 Mesh Pass 保持不同身份，Mesh Pass 的筛选、Shader、PSO、MRT 和依赖由 Mesh/Pipeline 契约配置。此项扩展不改变原先六项核心要求与实施顺序。

最新进度见 [ClearCoat/Skin 报告](ue-legacy-coat-skin-lighting.md)：`OpaqueLightingModels.json` 注册七个真实模型。ClearCoat 双层/底层法线、Skin 专用 LUT 保留各自 Shader 数学；224 组件样本及九原生图通过，双路径迁移与缺失 LUT 回滚通过。非双法线 Mesh HDR 通过单灯 GPU debug lobes 条件化区间检查，Capture 仍 31 处各差 1 half ULP；原生生产者和后续算法仍在实施。

## 新增可选注册

Schema 可声明 `lighting.programs` 和 `lighting.models`。每个 program 指向 `Codecs/Lighting` 中的 Shader 与 `.lighting.json`，声明入口与所需逻辑字段类型；models 必须完整覆盖 Schema 内已注册的模型。共享 GBuffer Codec 的模型可以使用各自的 Lighting 程序。

合同声明 `contract_version`、`entry`、`required_fields`、`required_resources` 和实际支持的 `profile`。本批目标 permutation 的 `energy_conservation`、`rough_diffuse`、`anisotropy`、`rect_light` 均为整数0。缺字段、字段类型失配、无效模型字段、缺 Lighting consumer、未知入口/模型、重复资源、合同失配、逃逸/循环 include 以及不支持的 profile 均拒绝。

生成器只生成 `ueIsLightingSupported()` 和 `ueShadeModel()` 等公共分派，Shader 内容由递归快照提供。未知模型的支持查询返回 false；原生 LightingPass 仍须在渲染前拒绝不支持的模型和缺失资源，不能把分派中的零值 default 当成能力实现。

| 身份 | 覆盖范围 |
|---|---|
| LayoutHash | GBuffer布局、模型/Codec路由，以及可选Lighting注册与映射 |
| CodecHash | GBuffer编码/解码Shader及其合同 |
| LightingHash | Lighting Shader递归依赖与合同，包括资源需求 |
| generation | 整份生成Shader与metadata |
| PipelineSignature / input fingerprint | 项目Shader/程序状态等结构与实际材质、光源、资源等输入分别记录 |

未声明 Lighting 的 Schema 不增加任何 Lighting metadata。既有 DefaultLit header、规范化 metadata 和最终序列化输出的字节黄金基线保持一致。`lightingColor`、`directDiffuse`、`directSpecular`、`directTransmission` 仅在启用 Lighting 的 Schema 中保留给 LightingPass 输出。

## Schema注册阶段的历史验证

- 159 项离线测试通过，包含 Schema、Lighting、Pipeline、资源及既有模型/Capture测试。
- UELegacy/FalcorTest Release 构建通过；原生资源引用 CPU 测试通过。
- `lighting_contract_smoke.py` 在 D3D12 debug 下编译真实 Common/DefaultLit/Unlit 与生成分派。两套模型ID（0/1、7/13）各12样本，迁移后输出逐位一致。
- 9个正入射点源样本使用独立双精度解析式 `diffuse = baseColor*(1-metallic)/pi`、`specular = F0/(4*pi*roughness^4)`，覆盖3个roughness与3个metallic；另检查Unlit、背光、未知模型支持标记与零贡献。容差固定为 `rtol=2e-6, atol=2e-7`，最大绝对误差约 `1.09322e-6`。
- `lighting.resources` 的所有纹理引用进入不可变资源快照与原生引用清单，支持JSON Pointer转义，拒绝遗漏/损坏。新增回归覆盖 `foo` 与 `foo_sha1` 同时作为合法纹理名；旧sidecar摘要检查保持原有行为。
- 既有Schema迁移/回滚回归再次通过，117087覆盖像素的逻辑结果逐位一致；Adapter资源身份回归通过。独立审查发现的纹理命名冲突与浮点位型比较问题均已修复。

结果与确切源码/证据哈希见 [机读记录](ue-legacy-lighting-schema-result.json)。GPU原始输入、结果、独立期望值保存在 `build/lighting-contract-evidence/{0,1}.npz`；生成Shader也单独保存。此处检查范围是实际Shader编译、分派及解析正入射点源极限，不是完整BRDF、胶囊面积光、阴影、LightingPass或Capture匹配验收。

## Capture 与下一步

[E2655 Capture取证](ue-legacy-lighting-capture.md) 已提取光源参数、PSO、前后SceneColor、Packed附件、阴影与LUT。[UE源码取证](ue-legacy-direct-lighting-source.md) 记录实际普通方向光/capsule/BRDF分支；[其他模型源码](ue-legacy-model-lighting-source.md) 记录真实模型差异与资源依赖。

四份DDS仅包装原始payload：E2624前置SceneColor、阴影、Skin专用LUT（保留sRGB视图）、白色场景AO。E2655最终SceneColor仅是验收目标，不作为Lighting算法输入。前置SceneColor已有SSGI，阴影也是显式阶段参考；后续必须由真正的GI/CSM等步骤生成。

原生 `UELegacyLightingConfig`、`UELegacyLightingPass` 与RenderGraph接线已实现，直接消费Schema的Packed附件、覆盖与深度。Lighting启用时生成`ueReadFields()`作为公共布局读取；HDR附件改名/通道迁移后零灯保留结果逐位一致。未启用Lighting的旧生成字节仍保持原契约。

此前受控方向/点/聚光、零/多灯、187样本capsule/BRDF检查，以及HDR异常候选回退验证已有记录，170项离线与4项LightingConfig CPU检查通过。后续VS输入修复后的当前E2655严格结果仍有31个half通道/像素各差1ULP；29为修复前历史版本，完整逐位验收尚未通过。ClearCoat/Skin BxDF/LUT、原生阴影/自动曝光、Clustered等仍在进行。最新行为和验证范围见 [原生Lighting阶段](ue-legacy-direct-lighting-pass.md)。上述159测试等归档记录只证明当时的Schema源码版本。

七模型GBuffer的历史验收仍见 [模型Codec报告](ue-legacy-model-codecs.md)。之后按 Lighting → SSR → TSR → Web 推进，自动曝光保留，最终画面对齐和整个骨干目标尚未完成。
