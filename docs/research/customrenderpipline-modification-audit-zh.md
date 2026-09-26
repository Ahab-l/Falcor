# 全部修改审计：保留、淘汰与真正的 TODO

审计日期：2026-09-13。实现工作树：`E:/Project/falcor/Falcor-m0`；基线：upstream `eb540f6748774680ce0039aaf3ac9279266ec521`。

> 后续清理记录（2026-09-13）：用户随后授权删除本报告的 8 个 D 类文件，现已从源码树移除，原字节保存在[清理备份](../../build/retired-files-cleanup-20260913/removed-files.zip)，[清单](../../build/retired-files-cleanup-20260913/deleted-files.json)含完整路径及 SHA256。下文及 CSV 保留删除前的冻结审计状态，不改写历史证据；最新进度见 Todo C1。

## 结论

**不是“旧 UE 相关代码全部无用”，也不是“之前实现的全部都应继续完善”。目前是新主线和旧研究框架并存。**

1. **新原生 GBuffer、通用 Schema/codec、观察/CLI，以及通用 Falcor 核心修复值得保留。**
2. **旧 SchemaPipeline、旧 UE 材质/深度 ABI、Config 及依赖它们的执行器，是后续淘汰或解耦对象，不应再成为新功能的前提。** 但仍有调用者，不能现在整包删除。
3. **UE 光照、天空、阴影、曝光算法属于效果扩展/对照研究，不是框架本体，也不能用原生同名效果冒充等价替代。** 应保留必要算法，迁到独立 Pass/codec。
4. **确实已退出运行链的 CSM 原型可以归档；被主动封禁的捕获回放入口和旧测试不能继续算当前验收。** 部分脚本还含有有效 CPU 分析，不能整文件误删。
5. **最重要的缺口不只是 V5：通用“描述式 Pass”入口尚未真正摆脱旧 Schema/Scene 配置。** 新 GBuffer 的独立成功不能代替这项完成。

本次只审计和更新文档/清单，**未删除、改写渲染实现，未提交或合并**。

## 1. 范围与证据强度

### 全量覆盖

- Falcor-m0：**29 个 tracked 修改 + 656 个新增文件 = 685 个文件**，以开始审计时的清单冻结。
- 分组：插件目录 202 个；脚本/示例 278 个；文档/计划 161 个；其余核心代码、构建与原生测试 44 个。
- 原 `E:/Project/falcor/Falcor` checkout 没有 tracked 渲染源码修改；另有 **163 个新增研究/规划文件**（157 个截帧证据文件、3 个研究/设计文件、3 个规划文件），单列为离线证据保留，不混入实现完成度。
- [逐文件分类 CSV](customrenderpipline-modification-inventory.csv)覆盖上述 **848 个工作树文件**。文件级类别不是逐行正确性证明；混合文件必须按表中的功能边界处理。
- CSV 类别：`K` 主线保留、`K/M` 现用但含迁移职责、`M` 旧依赖/待解耦、`R` 效果/研究、`T` 测试支持、`U` V5 未闭环、`D` 明确归档候选、`X` 失效/封禁入口、`H` 文档/证据。**D 只有 8 个文件（4 个 CSM 原型文件 + 4 个旧产物），不把 65 个 M 文件误称“65 个死模块”。** K/M 的 30 行包含两个 Observer 文件，且构建测试文件单列 T，不能与 29 tracked 文件数直接比较。
- [原始清单](../../build/modification-audit/inventory.json)记录 SHA256；[原 checkout 清单](../../build/modification-audit/original-checkout-inventory.json)单列。
- 忽略的 `build/`、shader cache、二进制、生成代次和截帧导出不是新增运行模块；按证据/缓存生命周期处理。**不能批量删除 build：部分旧脚本直接引用其中的资产、生成代次或 Python 运行依赖。**

### 本轮实际验证

- 全部 258 个 Python 文件可 AST 解析；建立[新入口的静态 import 闭包](../../build/modification-audit/native-python-closure.json)。这证明 Python 依赖边界，**不意味着 DLL 已物理拆包**。
- 本轮重新运行 **605 个 Python tests，通过**：[日志](../../build/modification-audit/python-current.log)。其中包含旧路径和纯 CPU 测试，不能当作 605 个 GPU 验收。
- 描述式入口的[只读 CPU 探针](../../build/modification-audit/neutral-description-probe.json)：不给旧 `schemaPath/sceneDefinition`，在构图前报 `KeyError('schemaPath')`。
- 两套旧 Generated 产物的[当前校验函数探针](../../build/modification-audit/stale-generation-probe.json)均实际报 `Schema shader checksum mismatch`；不只是从文件名推测过时。
- 读取既有 D3D12 结果及源文件 hash；本轮没有再启动 GPU/桌面验收。
- 原生 Mesh 证据索引的 12 项源 hash 与当前全部一致，但 Falcor/Mogwai 二进制已因后续工作变化。V4 18 项源 hash 中有 4 项随 V5 改变。旧“23 个核心修改/469 tests”报告不能覆盖当前 29 个 tracked 修改。
- V5 控件、预览和面板 headless 结果已通过，但结果明确写着 `mouse_driven_acceptance=false`；真实鼠标验收中止，最终 quality review/回归矩阵未关闭。

## 2. 应保留的新主线

| 模块 | 判断 | 边界/证据 |
| --- | --- | --- |
| `CustomRenderPiplineNativeGBuffer.*`、`NativeGBuffer.3d.slang`、`NativeGBufferCodec.slangh` | **保留**：原生 Scene/MaterialSystem 的可配置 MRT 写入 | 属性是 `definition/instanceIDs`；不构造旧 Config，不要求旧 Scene JSON。普通 authored Shader 路径与 Schema 自动生成路径是两种有用入口，不是无意义重复。 |
| `gbuffer_schema.py`、`gbuffer_codegen.py`、`generate_native_gbuffer.py` | **保留**：G4/G5 通用布局/编码合同 | 同源 encode/decode、位段/范围校验、手写 custom codec；不是旧 `generate_schema.py` 的包装。任意手写算法仍要参考验证，跨独立 Shader 的错误 ABI 不会自动被全部发现。 |
| `native_gbuffer.py`、`native_schema_gbuffer.py`、`native_mesh_selection.py` 与对应 examples | **保留**：最短原生入口与示例 | 普通例子复用原生 Blit/Scene，Schema 例子增加生成步骤；不强制使用事务框架。 |
| `observer.py`、`output_catalog.py`、native Observer 的目录/图集/D32S8 功能 | **保留**：普通 raw/特殊子资源观察 | 普通 bytes 已用原生 `to_numpy()`；特殊缓冲、Cube 图集和精确 D32S8 planes 不由普通 Mogwai 图片窗口完整替代。Observer 调用的旧 graph-contract 校验，与 Passes/History 中的 seal/prepare/history 职责应另拆，见下节。 |
| `schema_observer*.py` 中 codegen/observer/compare/service，`inspect_cli.py`、`observer_transport.py`、`observer_mogwai.py` | **保留**：V4 | 使用新生成 decoder、整数保持、字段比较、原子会话命令和帧后执行；CLI 不是依赖 UI 操作的壳。Schema 解码仅单采样、非数组二维 mip 0。 |
| V5 preview/model/panel/entry，Mogwai `screen` 和 PythonUI 新控件 | **保留，但标“未完成验收”** | 按需 GPU 预览，不为预览做 CPU 读回；像素/区域观察仍同步。缺点是 TODO，不是过时代码。 |
| `Scene::RasterDrawList` 与 stock/custom GBuffer 的 `instanceIDs` | **保留**：真正的 Scene 原生绘制筛选 | 两个 GBuffer 共用，不代表其他 Pass 已自动支持；旧 MeshDraw 仍有独立实现。 |

新 UI 入口的 Python 静态闭包不包含 `pipeline.py / pipeline_snapshot.py / generate_schema.py`。但是插件仍在同一 DLL 注册新旧 Pass，native Observer 也包含旧合同功能。**现在是执行入口局部独立，不是构建和模块边界已经完全独立。**

## 3. 应淘汰/解耦的旧框架，而不是立刻删文件

| 文件/模块族 | 判断 | 现在为什么不能直接删；正确替代顺序 |
| --- | --- | --- |
| `pipeline.py` 的 `SchemaPipeline`、`pipeline_snapshot.py` | **退出默认架构；旧事务功能冻结，按需保留** | `stage()` 仍调用旧生成器，snapshot 强制旧 Schema/Scene、material program/深度/曝光等合同。旧回放/历史/研究仍调用；整体回滚已经被用户暂缓，不应为新入口重造这套重快照。 |
| `generate_schema.py`、旧 `Schemas/`、`Codecs/Surface.slangh` 和模型 packing codec | **迁移退役对象** | 绑定旧模型/`UESurface` 合同。旧生成器仍有 **74 个直接 Python importers**；新生成器不是其旧 ABI 的 drop-in replacement。先迁移必要消费者，再移除旧生成器及模型表。 |
| `pass_definition.py`、`pass_files.py` | **保留有用的 JSON/节点/路径解析能力，剥离旧 Schema 和 snapshot** | 这部分不是另一个 GPU 调度器；但当前 loader→snapshot→Config 链仍受旧约束。不能整体删掉而丢失用户要求的“描述式可插拔 Pass”。 |
| `CustomRenderPiplineConfig.*`、`GraphContract.h`、旧图 seal/validator | **旧路径专用，逐步退场或变可选严格模式** | Config 在通用 Compute/Fullscreen/Mesh/Asset/History 中仍被构造，必读旧 `sceneDefinition/schemaPath`。图 hash/封存/外部输入拦截不是新主线默认必须付出的成本。 |
| `CustomRenderPiplineShaderPass.*`（Compute/Fullscreen） | **保留执行能力，替换旧配置前提** | 内部原生 ComputePass/FullScreenPass 有价值，问题是旧 Config/Shader 源/材质 ABI 耦合，而非“Falcor 没有执行器”。应形成无旧 UE 文件也能运行的描述式 Pass。 |
| `CustomRenderPiplineMeshDrawPass.*`、`Geometry.*`、`Routing.*`、`Material*`、`View.slangh` | **高优先级解耦；旧 ABI/重复 mesh 状态最终退役** | 旧 MeshDraw 仍拼接 Config Shader、要求 `UEMeshPass.viewProjection`、默认 reversed projection、按旧材质名匹配并手动逐实例 draw；**没有复用新的 Scene::RasterDrawList**。不能宣称 Mesh 原生迁移已经覆盖这一类 Pass。 |
| `CustomRenderPiplineAdapter.*`、旧 Init/Pre/`UEReferenceGBufferPass`/Decode | **新主线不需要；仅旧兼容/研究保留** | 新 native GBuffer 已取代普通用途。但旧 UE packing/模板/深度行为尚未逐项移植；Adapter 不是“适配任意 UE 材质”的完成证明。是否续维护由 A1/L1 决定。 |
| `CustomRenderPiplineHistoryPass.*`、`history_state.py` | **冻结为可选旧能力，不优先继续扩展** | “上一成功帧”/epoch/retry 语义与普通 TAA 历史不同，不能以“原生已有历史”直接删。若项目不再用事务历史，连调用者一起退役；先不要把整图回滚重新列为必做。 |
| `CustomRenderPiplineAssetPass.*`、`resource_snapshot.py`、content hash/helpers | **保留必要资产/缓存能力，去旧配置依赖** | 私有 immutable 资源避免 allocator alias 污染，不是无效重复。严格路径/全插件 hash 只适合回放模式，不适合默认主线；无需再额外开发一个庞大缓存框架。 |
| `CustomRenderPiplineSceneIdentity.*`、FrameReadback/RTVProbe 等诊断 | **按使用者拆分，不全删也不主线强制** | identity 当前有 StandardMaterial、UDIM/light-profile 等 reference 限制；不是所有合法 Falcor Scene 的身份接口。帧内合批读回/诊断确有作用，但旧 ABI 检查消失后部分同步路径应一并退役。 |
| `extensions/ue_reference/pipeline.py`、declaration、`scene_package.py`、source helpers | **移到研究/回放层并保留有效用途** | 仍有 CLI/研究/CPU 校验，不以 import 数量为零判死。ScenePackage 是捕获资产的离线封装，不是新 Scene 系统。 |

**真正的重叠是“旧配置/生成/合同/材质和 mesh 包装仍强制绑在通用执行器上”，不是所有 UE Shader 算法。**

## 4. 明确过时或失效的部分

### 4.1 可以优先归档的原型

`Extensions/UEReference/CustomRenderPiplineCSMDepthPass.{cpp,h}`、`CustomRenderPiplineCSMProjectionPass.{cpp,h}`：

- 四个原型文件不在当前 CMake 编译源及 Pass registry 中；当前 live 输入策略拒绝其捕获级联输入。
- 当前阴影走 `shadow_graph.py`、`UEReferenceShadowSetupPass` 与通用 Mesh/Fullscreen Pass，不走这两个类。
- **判断：退出运行链的旧原型，优先归档候选。** 归档前保留来源/验证记录、移除任何仅引用这些原型的文档入口。
- **不能扩展成“Shadows/ 整目录无用”。** 当前 CSM shader、UE 源片段和 setup 仍有实际消费者。

另有 **`Generated/803c111d…`、`Generated/940b1c6b…` 两套旧 `GBuffer.json/GBuffer.slangh`，共四个文件**：都是 `UEOpaqueDefaultLit` v2，不是新 native presets；当前 header SHA1 与 metadata 声明不匹配，会被 Config 的校验门拒绝。没有当前硬编码消费者，不在 CMake 源清单/默认 shader 拷贝中。**判断：校验已失效的旧派生产物，优先归档，不通过改 metadata hash 假装修复原快照。** CLI 默认写到 Generated 父目录不等于会读取这两个旧代次。精确 hash 见[插件审查](../../build/modification-audit/plugin-review.md)。

### 4.2 不能再当“当前 GPU 验收”的旧入口

| 入口族 | 当前事实 | 处理 |
| --- | --- | --- |
| `adapter_smoke.py`、`adapter_resource_identity_smoke.py`、`adapter_view_smoke.py` | 仍构造 `primitive_flags`；部分另有 `captured_view`，与当前输入禁用规则冲突 | 列为过期验收输入。若保留 Adapter，迁到 authored native scene；若退役 Adapter，归档测试，不为刷绿恢复被禁止输入。 |
| `rdc_gbuffer_smoke.py` | 顶层主动拒绝 captured input replay | 旧 GPU 执行入口已废止；不能拿历史 passed 证明现在可运行。 |
| `rdc_lighting_smoke.py::run_native()` | 主动拒绝 replay；CPU `--validate-only/--report-only` 仍有用 | 退役 GPU 入口，不整文件删除 CPU 分析。 |
| coat/skin 捕获 LUT 的 GPU 上传/Pass 验收、调用旧 `run_native` 的 diffuse production smoke | 依赖主动禁用的捕获路径 | 保留独立算术 oracle/来源记录，重建 native-input GPU 用例或归档旧执行入口。 |
| 从 `build/rdc-render/materials.json` 取旧捕获输入的 identity/pixel/quantization/scene-package smokes | 依赖外部生成文件及其中旧字段；不属于干净主线验收 | 逐项标注数据前提，不能整批称为可复现测试；有效拒绝测试与期望旧路径成功的测试分开维护。 |

**已删除的重复普通 C++ 读回实现不再列为“待删除”。** 当前 `observer.read()` 已复用原生 `to_numpy()`，只保留 D32S8 plane 补充；不要把历史报告中的候选删除项重复执行。

### 4.3 不属于无用代码的研究资料

- `Codecs/Lighting`、`Codecs/Exposure`、`Extensions/UEReference/Atmosphere/Materials/Shadows`：具体算法、源摘录、兼容 Shader、来源 JSON/notice，属于**效果层**。保留必要行为，迁移后才移除旧 ABI glue。
- 当前 `targetmap_graph.py` 已组装 CSM、天空/大气、SkyLight 与自动曝光；**不把旧日期的“尚未实现”继续抄成 TODO**。存在这些效果不等于已与目标 RDC 完整对齐。
- `extract_* / export_* / *_replay / analyze_* / candidate_* / *_reference / *_oracle`：离线取证、算法对照、曾被否定的数值候选。可以集中归档，但不是运行时模块，也不能为了整洁删除唯一证据。
- `Generated/` 旧产物、历史 build generation、失败日志、原始截帧：按生成物/证据管理，不能混入新主线或算未完成 feature；删除需先证明不再被重放入口引用且可重建。
- 历史 `ue-legacy-*` 文件名、旧分支名和源摘录的 UE 标识不是运行耦合证据；不做机械全局改名。

## 5. 核心修改：29 个 tracked 文件的判断

下表按功能覆盖全部 29 个 tracked 文件；混合文件的详细调用者/移除 gate 见[核心审查明细](../../build/modification-audit/core-review.md)。

| tracked 文件组 | 数量 | 判断 |
| --- | ---: | --- |
| API `Texture.cpp/.h`、`ResourceViews.cpp`、`FBO.cpp` | 4 | **保留** Cube/physical-layer/subresource/view 修复，不属于旧 UE 材质重复实现。 |
| `ParameterBlock.cpp/.h`、`CopyContext.cpp` | 3 | **保留** view 范围 barrier、UAV 顺序、D3D12 IA/Shader 组合状态、BC 小 mip copy 等；后端/版本升级后再逐 hunk 验证可否移除。 |
| `RenderContext.cpp` | 1 | **保留有调用的 IA/stencil/错误处理**；部分候选 draw 错误可恢复不等于整个 native indirect draw/设备错误都可回滚。 |
| `ProgramReflection.cpp` | 1 | **保留** resource element 标量类型修复。 |
| `RenderPassReflection.cpp/.h`、`RenderGraphCompiler.cpp`、`ResourceCache.cpp` | 4 | **保留** structured buffer 图反射、stride/count 校验及分配。 |
| `RenderGraph.cpp/.h` | 2 | **拆 hunk**：V4 `device/execute`、structured 支持保留；保留的 Observer 仍用 `getTopology().outputs`，拓扑查询须保留或先替换观察枚举。validator/外部输入限制待旧合同及其他消费者迁完才可退役，不能整文件撤回。 |
| `Scene.cpp/.h`、stock `GBufferRaster.cpp/.h` | 4 | **保留**共享 native draw list/instance selection。 |
| `SceneBuilder.cpp/.h` | 2 | **保留可选** `DontPretransformStaticMeshes`，只在依赖 object-space/instance transform 时启用。 |
| `PythonUI.cpp/.h` | 2 | **保留 V5 通用控件和生命周期修复**；Windows path encoding/错误提示及交互验收未闭环。 |
| `Mogwai.cpp/.h`、`MogwaiScripting.cpp` | 3 | **保留** once-per-frame 图执行接入、callback revision、V5 screen/framebuffer；新 observer 仍直接使用。 |
| 两个 `CMakeLists.txt`（RenderPasses、FalcorTest） | 2 | **保留插件/测试 wiring，后续支持拆包**。 |
| `external/include/backward/backward.hpp` | 1 | **保留为独立第三方健壮性补丁**，不是渲染 feature/TODO；升级第三方时复验。 |
| **合计** | **29** | **没有整组核心补丁能仅凭“已用原生”直接撤回。** |

## 6. 真正的 TODO：按价值而不是按历史顺序追加

优先级只表示建议顺序，不是授权本轮实现所有项目。

| 顺序/ID | 要做什么 | 完成标准 |
| --- | --- | --- |
| **1 / P2、A1.1** | **中立描述式装配 + 通用执行器去旧 Config/Schema/深度依赖** | 最小 JSON 声明原生 Pass 和自定义 Compute/Fullscreen，不提供旧 `schemaPath/sceneDefinition/UESurface` 也能创建、执行、观察；native scene + 新 codec 可独立选择。留住描述能力，不接回旧整图事务。 |
| **2 / A1.2、M2** | MeshDraw 去旧材质名表、UEMeshPass/reversed-depth 强制接口，复用 Scene draw-list | 专用 Pass 的 mesh 筛选/绘制不需要旧 UE material table；新旧有效案例分别验证，不能把 stock/custom GBuffer 的完成泛化到 MeshDraw。 |
| **3 / V5** | 收尾已写的 Inspector | 修复 Windows 对话框路径编码与面板异常提示；真实点击/选取/文件选择验收；补最终 V4/Schema GPU 回归、文档/源 hash 索引。现有 headless 和 605 CPU 不能替代这些。 |
| **4 / A1.3、L1** | 确定并迁移必要 UE 行为，退役旧生成/Adapter/Config glue | 每个仍需的材质/深度/模板行为有新 codec/Pass 和参考验证；研究侧保留对照，默认构建/入口不再依赖旧 ABI；淘汰过期成功测试，不恢复捕获输入。 |
| **5 / R4** | 只优化仍在主线的按需读回 | 明确 GPU/CPU 同步点和数据寿命；若要无阻塞再引入异步队列。旧 seal/history/scalar ABI 即将退役的成本优先通过退役解决，不继续堆优化层。 |
| **6 / R5、S4** | 后端/特殊资源验收 | 对支持范围提供 Vulkan、Depth/Stencil、array/mip/sample 的明确矩阵；Vulkan Cube RTV/DSV/UAV 及 `Texture.generateMips()` 的 Cube 路径当前明确拒绝，不只是“没测”。未测/不支持分开记录，不据此删除 D3D12 已证实必要修复。 |
| **独立 / F1** | FY1 与最终 RDC | 完整当前 shaders/资产/图可运行；用 scene/material 输入重建，不以捕获中间结果自报 `capture_inputs=False`；最终图像证据不能用局部算术通过替代。 |
| **暂缓 / D1** | 整图回滚 | 用户明确暂不需要，不阻塞当前主线，不主动接回新入口。 |
| **低优先 / V6** | 旧 sealed graph 的动态输出 UI | 只影响旧入口；新原生图可 markOutput。优先退役封存依赖，而非为旧框架继续发展 UI。 |
| **可选 / T1** | 半透明排序/Alpha blend Pass | 原先是能力讨论；未承诺本阶段实现，不把原生透射/Alpha Test 当已实现该 Pass。 |

### FY1 必须单独纠正完成度

当前 `build_fy1_hair_case.py` 引用 `Depth.slang / Base.slang / Deferred.slang`，该目录实际只有 `Lighting.slangh`；同时使用 captured `viewPositions/postvs/projection` 等输入。现有测试检查 manifest/布尔声明不等于验证输入来源和 referenced Shader 存在。已有 GPU `passed` 是 17 个 lighting 算术案例，记录明确 `full_image_parity=false`。

因此 **FY1 是“可复用部分算法 + 尚未成立的完整渲染入口”，不是“框架已做好，只差调小误差”**。这项与通用框架的发布/验收分开管理，具体证据见[研究审查明细](../../build/modification-audit/research-review.md)。

## 7. 建议的清理顺序与防误删门槛

1. 先标记入口：`native_* / 新 Schema / V4(V5 未完成)` 是主线；旧 `minimal.py` 仍经过旧 SchemaPipeline，不能继续作为“最小无 UE 依赖”示例推荐。
2. 把两个未编译 CSM 类和已封禁 GPU 回放入口移到归档候选表；保留它们的 CPU 分析/来源数据。
3. 完成中立描述/执行器后，逐 family 迁移调用者；最后才删除旧 Config/generator/材质 ABI。每一步检查 imports、Pass 注册、shader include、JSON path、CLI/测试和已有资产依赖。
4. 独立效果插件可以拆包，但**拆 DLL 只是物理组织，不会自动解除旧 ABI 依赖**。
5. 历史成功记录不改写；新验证要记录当前源 hash、输入前提、命令和结果。备份、证据、缓存分别管理。

### 审计附录

- [核心逐功能审查](../../build/modification-audit/core-review.md)
- [插件/旧 ABI 与通用执行器审查](../../build/modification-audit/plugin-review.md)
- [效果研究/原型/过期测试审查](../../build/modification-audit/research-review.md)
- [逐文件分类 CSV](customrenderpipline-modification-inventory.csv)
- [能力 Todo](customrenderpipline-todo-zh.md)

本报告完成的是**判断与任务边界整理**，不是宣称上述 TODO 已完成，也不是一次未经验证的删库重构。
