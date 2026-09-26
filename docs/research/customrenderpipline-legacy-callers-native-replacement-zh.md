# 旧模块调用者与原生替代路线

日期：2026-09-13。工作树：`E:/Project/falcor/Falcor-m0`。

这是删除第一批 8 个停用文件后的**源码调用链核对**，不是新的 GPU 验收，也没有执行后续迁移或删除。以下“调用者”表示当前代码中可达的入口/引用，不表示这些程序此刻正在运行。历史测试引用不等于当前成功的运行证据。

## 结论

**大部分框架执行能力可以复用 Falcor 原生功能；旧模块不是永久依赖。** 主要障碍是我们自己的通用执行器仍强制绑定旧配置，而不是 Falcor 缺少图、Shader、资源或场景渲染能力。

需要分清三层：

1. **上游 Falcor 已有**：RenderGraph、注册 RenderPass、Properties、ComputePass、FullScreenPass、Scene/MaterialSystem、资源加载与绘制 API。
2. **本分支已完成且仍需保留**：可配置 NativeGBuffer、新 Schema/codec 生成校验、观察/比较工具、接入 Scene 的 RasterDrawList 选择扩展。它们不等于上游原样已有，但已经不需要旧 UE 管线作为运行前提。
3. **不能自动替代的效果语义**：UE 材质算法、特定编码、深度/模板解释和曝光约定。需要的算法应迁成独立 Shader/codec/Pass，而不是继续依赖旧 Config 或反向转回旧 ABI。

## 1. SchemaPipeline：谁还用，如何替代

**仍有实际入口：**

- [minimal.py](../../scripts/customrenderpipline/minimal.py:9)：旧“最小示例”直接构造它，不是无 UE 依赖的最小入口。
- [targetmap_live.py](../../scripts/customrenderpipline/targetmap_live.py:54)：完整场景入口仍 `stage()` / `commit()`。
- [targetmap_graph.py](../../scripts/customrenderpipline/targetmap_graph.py:36)：通过 `translate_legacy_definition()` 组装旧 Init/Pre/GBuffer/Decode/Lighting 链，再接阴影、天空、SkyLight 和曝光。
- [extensions/ue_reference/pipeline.py](../../scripts/customrenderpipline/extensions/ue_reference/pipeline.py:241)：继承根 SchemaPipeline；其使用者包括 shader_executor、auxiliary_mesh、asset_source、history_resources 等功能 smoke，以及大量材质/光照研究用例。

**可以替代的部分：** 图装配直接用 `RenderGraph`、`createPass()`、`addPass()`、`addEdge()`、`markOutput()`；图调度和资源生命周期本来就由 Falcor 执行。JSON 的节点/边/路径解析保留为薄装配层，不再在组图前调用旧 snapshot/generator。

**已有替代入口：** [native_gbuffer.py](../../scripts/customrenderpipline/native_gbuffer.py:8) 和 [native_schema_observer.py](../../scripts/customrenderpipline/native_schema_observer.py:18) 已这样组图，后者使用新的 `generate_native_gbuffer`，不是旧 `generate_schema`。

**不是逐项等价替换：** 旧整图快照、封存、事务式 stage/commit/回滚不是普通 RenderGraph 的同义 API。用户已暂缓整图回滚，不应为了替代普通组图再次重建这些机制。仍需严格历史重放的用例可暂留研究层。

## 2. 旧 Config：真正阻碍删除的是这些 Pass

[Config 构造函数](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineConfig.cpp:83) 无默认值读取 `sceneDefinition/schemaPath`，并强制旧生成器 v2 metadata、旧材质表、`D32FloatS8Uint` 且 clear=0 等合同。

| 当前直接消费者 | 可复用能力 | 还要做的迁移 |
|---|---|---|
| Compute / Fullscreen：`CustomRenderPiplineShaderPass` | 原生 `ComputePass` / `FullScreenPass`；目前内部**已经在用** | 将 shader、资源、uniform、dispatch、输出状态从 Config 解耦；取消无条件拼接旧生成 shader。保留需要的资源类型/子资源校验 |
| `CustomRenderPiplineMeshDrawPass` | 原生 Scene、MaterialSystem、GraphicsState；本分支共享 RasterDrawList | 去掉强制旧材质名映射、`UEMeshPass.viewProjection` 和 reverse-Z 默认前提；筛选提交改用共享 Scene 接口。现有 instanceIDs 扩展不自动覆盖旧 model/program/tag 路由语义 |
| `CustomRenderPiplineAssetPass` | 普通图像用 `ImageLoader` / `Texture::createFromFile`；其他资源用原生 Buffer/Texture API | 通用多资源、结构化缓冲、Cube/子资源及可选 immutable 校验不能全用 ImageLoader 等价代替；保留必要 producer 包装，去 UE Config |
| HistoryRead / HistoryWrite | 原生纹理、copy/blit、Pass 自持历史；TAA/Accumulate 有各自的历史资源实现 | 普通跨帧资源可复用这种方式；现有“整帧成功才发布、epoch/连续帧校验”不是 TAA 的直接替代功能。是否保留该语义独立决策，不将它作为新主线强制门槛 |
| 旧 Init / Pre / UEReferenceGBuffer / Decode / Adapter | 新 NativeGBuffer + 新 Schema/decoder 覆盖普通自定义 GBuffer 用途 | 旧 UE 特殊行为如仍需要，应迁移并验证后才删旧实现 |
| UEReferenceLighting / ShadowSetup / SkyViewSetup | 原生灯光/场景/Shader 执行 API | setup 和 lighting 的效果参数/算法仍需独立描述；原生 API 不会自动算出同一套 UE 效果 |

证据：[ShaderPass 配置构造与拼接](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineShaderPass.cpp:112)、[原生执行器调用](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineShaderPass.cpp:203)、[MeshDraw 旧接口](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineMeshDrawPass.cpp:373)、[成功帧历史发布](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineHistoryPass.cpp:228)。

### “能用脚本”不等于“已有任意 Shader 的可插拔图节点”

原生 [ComputePass Python 绑定](../../Source/Falcor/Core/Pass/ComputePass.cpp:98) 可以直接创建、绑定并 dispatch，V4 已复用；但它继承 `Object`，**不是**可直接 `graph.addPass()` 的 `RenderPass`。当前 FullScreenPass 也不是现成的通用 JSON 图节点，本版本未提供对应的直接 Python 类绑定。

因此：普通组图可仅用脚本；要保留用户要求的任意 Compute/Fullscreen/Mesh **描述式图节点**，仍需要薄 RenderPass 包装。应精简/解耦已有 C++ 包装，而不是新造调度器，也不能宣称删掉包装后所有功能都能仅靠几行脚本无损保留。

## 3. 旧 UE 材质/深度 ABI：谁还消费

旧 `UEReferenceGBufferPass` / Adapter 生产 packed attachments、`primaryCoverage`、`depthCopy` 等数据；旧 Decode、[UEReferenceLighting Shader](../../Source/RenderPasses/customrenderpipline/Extensions/UEReference/UEReferenceLighting.3d.slang:133)、SkyLight、部分 Mesh/天空/阴影 Shader 消费其编码或相关 view/exposure 约定。`targetmap_live` 是这条组合链的重要保留入口，不能把它们全归为死测试。

替代办法是让必要效果读取**新 Schema 的字段及明确的深度/坐标约定**，将 UE 算法保留在独立 Shader 中。新 Schema 能定义存储和自定义 codec，但不会自动翻译 UE 材质图或证明与旧材质数值相同；Falcor `StandardMaterial` 也不是任意 UE 材质的等价替身。新 NativeGBuffer 当前默认 LessEqual/clear=1，更不能把它的深度直接交给旧 reversed-Z 解码器而不改消费者。

## 4. Adapter：主要是旧对照分支，不是当前主线必需

明确调用者包括：`adapter_smoke.py`、`adapter_view_smoke.py`、`adapter_resource_identity_smoke.py`、`dbuffer_identity_smoke.py`、`model_codec_smoke.py`，以及 reference graph builder、snapshot/声明/ownership 测试与插件注册。

它做的是 **stock GBufferRaster → 旧 UE packed/depth/material-name 映射**，不是“通用 UE 材质导入器”。新 NativeGBuffer/Schema/V4(V5) 入口不需要这个转换；`targetmap_graph` 当前默认采用旧 mesh writer 分支，也不是 Adapter 分支。

**普通用途可以退役 Adapter，而不是再找一个原生 Adapter 接替它。** 直接生产目标新 GBuffer，消费者读取新 codec 即可。旧对照用例中有价值的算法验证迁到新 producer/decoder；只验证旧 Adapter 行为的测试可随其一起退役。几个 adapter smoke 仍含已被输入策略禁止的 `primitive_flags/captured_view`，不能把“测试存在”当成“这条路径当前验收通过”。

## 5. 建议顺序与删除门槛

1. **先解除装配入口和 Compute/Fullscreen 的旧前提**：复用现有 JSON 解析 + 原生 RenderGraph；新最小图不需要旧 Schema/Scene JSON，也不接回整图事务。
2. **迁移 MeshDraw/资源与必要跨帧状态**：保留通用功能，旧 UE 参数/规则改成效果私有输入。
3. **迁移仍需要的 targetmap 材质/光照/阴影消费者**：新 codec + 明确深度/坐标/曝光合同；逐效果验证，避免同时换算法和数据含义。
4. **移除 Adapter 和只服务旧分支的测试/注册**；最后清空 Config/旧生成器/SchemaPipeline 的活跃调用链再删。纯研究/冻结证据可隔离归档，不必为其永久保留主线依赖。

当前 native 入口虽然运行时不构造旧 Config，但新旧类仍混编在同一插件，且注册集中在旧 `CustomRenderPiplinePasses.cpp`。删除源码还需同步清理注册/include/CMake；“运行不需要”不等于“现在删除旧文件后 DLL 仍可编译”。

## 取证与范围

- [Python 直接导入清单](../../build/legacy-caller-audit-20260913/python-imports.json) 来自当前 Python AST，不统计文档/注释字符串，也不把 import 数量解释成运行实例数。
- 直接导入 reference pipeline 模块的 85 个文件中，77 个是 smoke/validation、2 个是 unit test，其余 6 个为入口/研究 helper；它们导入的可能是 SchemaPipeline、builder 或 translator，不可笼统称为 85 个 SchemaPipeline 实例。
- 已用 `git show HEAD` 核对 ComputePass Python 执行绑定、Scene::rasterize、RenderGraph 组图 API 属于上游原有；RasterDrawList 子集选择属于本分支新增。
- 本轮仅更新说明/审计记录，未修改渲染源码，未构建或运行 GPU，也没有继续删除模块。原 Todo P2/A1/M2 等状态不因这份替代分析而变成已完成。
