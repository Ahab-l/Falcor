# customrenderpipline：Falcor 原生能力复用审计

核对日期：2026-09-12。工作树：`E:/Project/falcor/Falcor-m0`；基线：`eb540f67`。检查的是本地这版 Falcor 的源码、示例和当前修改，没有假定其他版本具有相同接口。

结论：框架应继续只负责自定义材质/GBuffer 合同、描述式 Pass 装配及调试验证/失败回滚。Falcor 已有图调度、Shader 执行、普通资源读回、输出窗口和常规图像误差 Pass。本次删除了重复的普通原生读回实现，并验证原生 Pass 可以直接接入。其余保留项都有下表所列的能力差异，不能仅因名字相似而互相替换。

## 1. 原生实现与处理决定

| 需求 | 本地原生证据 | 当前决定及原因 |
| --- | --- | --- |
| 组合 Pass、资源连接和执行顺序 | [MinimalPathTracer.py](../../scripts/MinimalPathTracer.py)、[RenderGraphCompiler.cpp](../../Source/Falcor/RenderGraph/RenderGraphCompiler.cpp) 的 `resolveExecutionOrder()` | 继续调用 `RenderGraph/createPass/addPass/addEdge/markOutput`。不增加自己的运行时调度器或分配器。Python 的 Kahn 排序仅作无 GPU 的环检测和确定性构图顺序，保留这段小验证；真正执行顺序仍由 Falcor 编译器决定。 |
| 执行 Compute/Fullscreen Shader | [TinyBC.py](../../scripts/python/TinyBC/TinyBC.py)、[balls.py](../../scripts/python/balls/balls.py)、[ShaderToy.cpp](../../Source/Samples/ShaderToy/ShaderToy.cpp) | 通用执行器内部已调用原生 `ComputePass::create` / `FullScreenPass::create`。保留 JSON→反射、参数、资源绑定这一层，不再封装第二套 Shader 编译/执行系统。单个实验若不需要 Schema 和事务，直接用原生 Testbed/ComputePass。 |
| 拷贝、模糊、合成、累积、TAA、Tone mapping | [BlitPass](../../Source/RenderPasses/BlitPass)、[原生 RenderPass 目录](../../Source/RenderPasses) | 普通算法优先使用已有 Pass；描述节点设置 `inherit_pipeline: false`。不能为了统一前缀重新写一套。只有编码、公式或输入合同不同的效果才提供自己的 Shader。 |
| 普通二维输出、多窗口查看及保存 | [Mogwai.cpp](../../Source/Mogwai/Mogwai.cpp) 的 `graphOutputsGui/renderDebugWindow`；原生 PixelZoom | 使用 Mogwai 的 `Output`、`Show In Debug Window`、`Save To File`。自定义 atlas 仅补充 raw/structured buffer、Cube 面/mip 的指定视图以及脚本拼图；不再发展一套普通纹理窗口。封存图的输出限制见第 3 节。 |
| 普通纹理和缓冲原始读回 | [Texture.cpp](../../Source/Falcor/Core/API/Texture.cpp) 的 `to_numpy(mip_level, array_slice)`；[Buffer.cpp](../../Source/Falcor/Core/API/Buffer.cpp) 的 `to_numpy()` | **已精简。** 删除插件中的普通 `readOutput` C++ 实现、结果结构和 Python 绑定。`PipelineObserver.read()` 校验视图后调用上述原生方法，并保留输出元数据。 |
| 精确 Depth/Stencil 平面 | [CustomRenderPiplineReadback.h](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineReadback.h) | 保留 D32FloatS8Uint 专用平面读回。原生通用 numpy 接口不能代替这里对两个 plane、行字节和选定子资源的精确处理。其他格式继续走原生。 |
| 常规图像 L1/MSE 和差分图 | [ErrorMeasurePass.cpp](../../Source/RenderPasses/ErrorMeasurePass/ErrorMeasurePass.cpp) | 优先接入原生 Pass，本次已做 GPU 验证。它会执行带 CPU 结果的 ParallelReduction；`ComputeAverage: false` 也不关闭这次同步，不适合作为持续预览优化。 |
| 任意编码样本的容差比较 | [observer.py](../../scripts/customrenderpipline/observer.py) 的 `compare_arrays` | 保留小型、显式 CPU helper，处理相同编码/单位的数组、绝对/相对容差和最差位置。原生 ErrorMeasurePass 的 RGB 误差语义不同；PixelInspectorPass 也要求 `posW/mtlData` 等固定语义，不能直接解释任意 Packed GBuffer。 |
| 自定义材质与 GBuffer | [原生 GBufferRaster.cpp](../../Source/RenderPasses/GBuffer/GBuffer/GBufferRaster.cpp)、[原生复用更新](customrenderpipline-native-gbuffer-zh.md) | 已新增薄配置适配层，普通 `CustomRenderPiplineGBufferPass` 直接使用原生 Scene / MaterialSystem，以 JSON + Slang 定义附件和编码，无需 GBufferAdapter 或旧 Schema。原 UE 材质/坐标/模板算法更名为 `UEReferenceGBufferPass`，保留供 RDC 案例使用。 |
| Shader/配置失败后保留旧图 | [ProgramManager.cpp](../../Source/Falcor/Core/Program/ProgramManager.cpp)、[Program.cpp](../../Source/Falcor/Core/Program/Program.cpp)、[RenderGraph.cpp](../../Source/Falcor/RenderGraph/RenderGraph.cpp) | 保留独立 candidate 的 `stage/commit`。`reloadAllPrograms()` 调用 `reset()`，会清除活动版本；`RenderGraph::compile()` 在尝试编译前清空 `mpExe`。普通热重载不能替代整图事务。 |
| 历史纹理 | [TAA.cpp](../../Source/RenderPasses/TAA/TAA.cpp)、[CustomRenderPiplineHistoryPass.cpp](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineHistoryPass.cpp) | 私有 previous-frame texture 是原生已有模式，不是误用。标准 TAA/Accumulate 直接复用。自定义 HistoryRead/Write 只补充“上一成功帧”、事务 epoch、同帧重试和验证成功后发布；没有再实现一套 TAA 算法。 |
| 历史状态的 Python/C++ 两层 | [history_state.py](../../scripts/customrenderpipline/history_state.py)、[pipeline.py](../../scripts/customrenderpipline/pipeline.py) | Python 管提交、相机 cut/reset/帧连续性；C++ 管 GPU 双缓冲和发布，并拒绝错误的直接调用。确有重复的连续性检查，但 GPU 资源只有一套；保留接口边界检查，不合并成额外控制框架。 |
| 帧内诊断读回 | [CopyContext.cpp](../../Source/Falcor/Core/API/CopyContext.cpp)、[CustomRenderPiplineFrameReadback.cpp](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineFrameReadback.cpp) | 原生 `asyncReadTextureSubresource` 每次请求创建 task、submit 和 fence，不自动合并一帧多个检查。保留现有 FrameReadbackScope 合批；它仍有帧末等待，不能宣传为完全异步。普通观察不进入每帧循环。 |
| 不可变素材及一次性计算缓存 | [CustomRenderPiplineAssetPass.cpp](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineAssetPass.cpp)、[CustomRenderPiplineShaderPass.cpp](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplineShaderPass.cpp) | 保留私有源，再复制到图输出，避免下游 InputOutput/别名覆盖污染缓存；不长期持有分配器拥有的图输出。代价是额外显存和复制。仅适用于已声明的不可变素材/计算，不能将动态 SkyLight 误标为一次执行。 |
| UE 旧组图函数 | [extensions/ue_reference/pipeline.py](../../scripts/customrenderpipline/extensions/ue_reference/pipeline.py) | 默认入口已经改为显式声明。旧 replay/lighting builder 仍被光照证明和研究脚本使用，保留在 reference 扩展中；不能当作死代码删除，也不用于新的通用入口。 |

## 2. 核心补丁是否需要保留

当前已有核心文件改动共 23 个，以下分组覆盖全部。此次审计没有再改这些核心文件；本轮删除集中在插件 observer 和 Python 调用层。核心补丁与具体 UE 光照公式应保持分离。

| 文件组 | 缺口及决定 |
| --- | --- |
| `Texture.cpp/.h`、`ResourceViews.cpp`、`FBO.cpp` | 修正 Cube 数和六面物理层数的混用、子资源数量/view 范围。保留；不是增加一种新纹理系统。Cube SRV 要完整六面分组，不支持的 view 明确拒绝。 |
| `ParameterBlock.cpp/.h`、`CopyContext.cpp` 的 texture barrier | 按绑定 view 的 mip/layer 转换状态；正确处理 Depth/Stencil aspect、部分子资源保持 UAV 时的顺序。Vulkan 局部 UAV barrier 避免改变只读 mip 的 layout。保留；本轮 GPU 实测平台是 D3D12，不能据此宣称 Vulkan 已实测。 |
| `CopyContext.cpp` 的 buffer/readback 修复 | D3D12 IA 与 Shader 同时读取所需的组合状态，以及 gfx 对 BC 小 mip copy footprint 的缺口。保留有限后端补丁；若升级 gfx/Falcor，应先复跑相应回归再判断能否去掉原生 API 分支。 |
| `RenderContext.cpp` | 每次 D3D12 draw 校验可能已改变的 IA 状态、设置动态 stencil reference、使无效候选 PSO 的参数错误能进入拒绝路径。保留；设备移除等失败仍不属于可保证回滚的配置错误。 |
| `ProgramReflection.cpp` | 从 resource result element 获取 float/uint/int 类型，用于正确验证绑定。保留；原先从资源包装类型取标量类型不满足需求。 |
| `RenderPassReflection.cpp/.h`、`RenderGraphCompiler.cpp`、`ResourceCache.cpp` | 原生已经可以直接创建 structured buffer，但图字段/分配器缺少对应类型和 stride/count。保留这部分图资源反射支持；不要声称 StructuredBuffer 本身是框架发明的。 |
| `RenderGraph.cpp/.h` | 完整逻辑拓扑查询、执行前校验、外部输入检测支撑封存合同；初始化未知 viewport 为 0；校验 structured buffer 连接。原生编译器继续负责排序和分配。保留；输出集合也是合同的一部分。 |
| `SceneBuilder.cpp/.h` | `DontPretransformStaticMeshes` 保留静态 mesh 的局部坐标及实例矩阵；原 `DontOptimizeGraph` 不能跳过另一处显式预变换。保留，只有依赖对象坐标的场景才需要选择该标志。 |
| `Mogwai.cpp/.h`、`MogwaiScripting.cpp` | `graphExecutionCallback` 让完整历史执行替代默认执行，并处理回调导致的图生命周期变化。保留；在 sceneUpdateCallback 中先渲染再让 Mogwai 默认执行会画两次，是应避免的集成错误。普通无历史原生图仍用默认执行。 |
| `Source/RenderPasses/CMakeLists.txt`、`Source/Tools/FalcorTest/CMakeLists.txt` | 注册新插件和对应测试；保留。 |
| `external/include/backward/backward.hpp` | Windows 栈解析的返回值检查、零初始化、NUL 结尾字符串和空指针处理。属于报错路径健壮性补丁，保留；没有图渲染职责。以后更新第三方库时单独检查是否已被上游修复。 |

`RenderPassReflection` 的 ABI 已变化，应完整构建 Falcor、Mogwai 和插件。不要把旧 DLL 混入这套构建。

## 3. 已发现的限制和复杂度成本

**原生输出窗口与封存输出。** 在图描述 `outputs` 中只声明需要观察的端口，重新 stage/commit，再从 Mogwai 选择这些端口。多个 Debug Window 可同时查看已声明的二维纹理。勾选 `List All Outputs` 本身不改图，但选择未声明端口会调用 `markOutput` 并被封存校验拒绝；修改已封存的 Pass 属性也应重新 stage。这是当前集成限制。动态标记可能激活被裁剪节点、重新分配或延长资源寿命，因此本轮没有放宽校验或自动 mark 所有端口。

**快照指纹范围过宽。** `_external_baseline()` 对全部已构建插件 DLL 和整个 runtime shader tree 求指纹，无关插件重建也会使旧快照失效。实测该函数单次约 **470–482 ms**，扫描 **34 个二进制、762 个 Shader 文件**；这是工作区已使用后的三次顺序测量，既不是完整 stage 时间，也不是帧时间。记录在 [baseline-cost.json](../../build/native-falcor-audit/baseline-cost.json)。当前没有公开 Python API 能准确列出 Pass→DLL 及传递 Shader import 闭包，因此保留明确的严格基线，不再为此添加缓存/依赖管理子系统。stage/replay 时才执行这些哈希；它不能解释为“每帧扫描整个 Shader 目录”。

**通用入口仍有集成成本。** `SchemaPipeline` 面向自定义材质/GBuffer 事务，stage 接口仍要求 Schema 和 Scene 描述；通用 Shader 示例也提供了这些文件。纯 Compute 学习程序可以直接使用原生示例，不必承担这一层。UEReference 目前和框架共用一个 DLL，`UESurface`、曝光输入等兼容约定仍在；按图选择执行已经分离，二进制完全拆包和任意材质 ABI 尚未完成。

**原生插件可插拔也有条件。** `inherit_pipeline: false` 避免把自定义属性塞给原生 Pass。插件应通过 `getProperties()` 返回稳定、可重建的可执行参数；会在运行中推导并改变参数的 Pass 应显式声明相应设置。封存图禁止绕过描述调用外部 `setInput`；文件 Shader/素材应登记 `file_inputs`。这不是所有第三方 Pass 在任何状态下都能零适配接入的承诺。

**观察功能的成本。** `to_numpy/read/compare` 会同步读回；atlas 占用一张额外 GPU 纹理；ErrorMeasurePass 每次执行也会读 CPU 统计。按需使用，不常驻预览。已有帧完成等待、Scene identity 检查和旧材质 scalar ABI 的同步路径仍在；本轮只去除重复实现，没有测出新的实时帧率提升。

## 4. 直接使用原生 Pass

已有图的 `nodes` 可以加入：

```json
{
  "name": "Copy",
  "type": "BlitPass",
  "inherit_pipeline": false,
  "properties": {"filter": "Point", "outputFormat": "RGBA32Float"}
}
```

添加 edge `["Generate.color", "Copy.src"]`，再把 `"Copy.dst"` 加入 outputs，然后重新 stage/commit。无需新的 C++ 类或复制 Shader。

[native_reuse_smoke.py](../../scripts/customrenderpipline/native_reuse_smoke.py) 是完整可运行用例：从最小描述加载 Pattern/Grade，再接入原生 BlitPass 和 ErrorMeasurePass。它验证拷贝逐元素相等，以及原生 RGB 平方差图相等；差分输出 alpha 为 0。

```powershell
Set-Location E:\Project\falcor\Falcor-m0
& .\build\windows-vs2022\bin\Release\Mogwai.exe --headless --enable-debug-layer --script scripts/customrenderpipline/native_reuse_smoke.py
```

## 5. 本轮验证

- 全量 Release 构建成功；[构建日志](../../build/native-falcor-audit/build-readback.log)。
- **469 项 Python 测试通过**，包含三个新增原生读回边界测试；[测试日志](../../build/native-falcor-audit/python-tests.log)。首次误把 Mogwai 的 Python 3.10 numpy 目录加到 Anaconda 3.11 的 PYTHONPATH 导致 import 失败；移除该环境覆盖后全量通过，未修改实现来绕过测试。
- **6 组 D3D12 GPU 验收通过**：原生 Pass 组合、框架描述/坏更新回滚、普通 observer、structured buffer、素材读回、Cube/mip observer。均 headless、启用 debug layer、串行运行并正常退出；Cube 用例覆盖 24 个面/mip 组合。
- 迁移任务已有的 8 组 GPU 结果与本轮结果分开记录；本次不借用旧测试数量充当新验证。

验证索引：[verification.json](../../build/native-falcor-audit/verification.json)。没有提交或合并代码，没有改原 UE 源码/RDC。此审计和精简完成，不代表 FY1 头发或最终 RDC 画面对齐完成。
