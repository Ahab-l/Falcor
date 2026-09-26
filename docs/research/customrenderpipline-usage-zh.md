# customrenderpipline：框架职责与使用说明

> **2026-09-14 主线已更新：下文旧 SchemaPipeline/事务/UE 案例章节是历史设计，不是当前使用步骤。旧入口已退役，不要执行其中 minimal/targetmap 或旧 smoke 命令。** 当前使用 [描述式 Pass](customrenderpipline-native-pass-migration-zh.md)、[Asset/History](customrenderpipline-native-resources-history-zh.md)、[新 Schema](customrenderpipline-gbuffer-schema-zh.md) 和 [V4/CLI](customrenderpipline-schema-observer-zh.md)。[最新重新审计](customrenderpipline-modification-reaudit-20260914-zh.md) 与 [Todo](customrenderpipline-todo-zh.md) 为当前状态；历史正文保留用于来源对照。

## 历史正文（不再作为当前 API 文档）

**进度入口：[四项能力 Todo](customrenderpipline-todo-zh.md)。** 已完成、未完成、待讨论和暂缓项在此统一跟踪；整图回滚已按用户决定暂缓。

**2026-09-14 默认入口更新：** 描述式 Compute/Fullscreen 与通用 MeshDraw 已迁到中立 `pipeline.make_graph()` + 原生 Scene draw lists；不再强制旧 Config/SchemaPipeline/UE 材质或深度 ABI。[新用法与可运行示例](customrenderpipline-native-pass-migration-zh.md)。下文旧 SchemaPipeline/stage/snapshot 章节仅用于显式 UEReference 兼容路径，不是新框架的使用前提；Asset/History 与其他旧调用者尚未全部迁移。

核对日期：2026-09-12。实现工作树为 `E:/Project/falcor/Falcor-m0`，分支为 `codex/ue-legacy-m0`，基于 `eb540f67`。原 `E:/Project/falcor/Falcor` 的 master 源码没有这些修改。

**GBuffer 原生复用更新：** 普通 GBuffer 现在直接使用 [native_gbuffer.py](../../scripts/customrenderpipline/native_gbuffer.py)，由 Falcor 原生材质和渲染图驱动，JSON / Slang 定义附件及编码；不再需要旧 Schema / Scene JSON。旧材质写入器更名为 `UEReferenceGBufferPass`。完整配置与边界见 [原生 GBuffer 使用说明](customrenderpipline-native-gbuffer-zh.md)。下文 `SchemaPipeline` 的整图回滚能力尚未接入这一原生入口。

框架名称为 **`customrenderpipline`**，DLL 为 `customrenderpipline.dll`，原生 Pass 前缀为 `CustomRenderPipline`。框架本体负责三件事：

1. **自定义材质与 GBuffer**：定义颜色、粗糙度、法线等数据如何写入、编码和读取。
2. **可组合的 Pass**：读取管线和 Pass 描述，将 Shader、资源、参数与连接装配为渲染图。
3. **调试和验证**：观察各 Pass 输出、读取原始像素、比较误差。新 Shader 或配置失败时保留旧图的整图回滚扩展已[暂缓](customrenderpipline-memo-zh.md)，旧事务入口代码仍保留。

默认 `pipeline.SchemaPipeline` 只接受描述式图。天空、阴影、光照、曝光、头发是扩展或案例中的具体算法，由管线选择；不会因为加载了框架而自动启用。原 UE 材质函数与 `UESurface` 等 Shader ABI 暂时保留，用户可以指定自己的 Schema 和 codec 根目录。

先运行纯描述式示例：

```powershell
Set-Location E:\Project\falcor\Falcor-m0
& .\build\windows-vs2022\bin\Release\Mogwai.exe --script scripts/customrenderpipline/minimal.py
```

它读取 [Pipeline.json](../../scripts/customrenderpipline/examples/minimal/Pipeline.json)，组合两个独立 Pass 描述和 Shader。在 Mogwai 中可选择 `Generate.color` 或 `Grade.color` 查看输出。

已有功能优先复用 Falcor：图调度/分配、Compute/Fullscreen 执行、普通输出窗口、`to_numpy()` 读回以及 Blit/ErrorMeasure 等原生 Pass。具体保留和精简依据见 [原生能力复用审计](customrenderpipline-native-falcor-audit-zh.md)。

## 1. 哪些已有代码被修改

后续新增了 [Scene 层 Mesh 绘制列表](customrenderpipline-native-mesh-selection-zh.md)：修改 `Source/Falcor/Scene/Scene.h/.cpp`，共享全场景/选中实例的间接绘制代码；修改官方 `GBufferRaster.h/.cpp`，让预深度和 GBuffer 阶段接受同一份 `instanceIDs`。这是本分支对 Falcor 核心的扩展，不是声称官方原版已有这些选择接口。

已有 Falcor 核心改动如下；新增框架、扩展和脚本位于后文列出的目录。下面路径均相对该工作树。

| 文件 | 改动与作用 |
| --- | --- |
| `Source/Falcor/Core/API/CopyContext.cpp` | 修正顶点/索引缓冲与 Shader 同时读取的 D3D12 状态、Cube 面与 mip 的 barrier、Depth/Stencil aspect、压缩纹理小 mip 的原始读回，以及 Vulkan 局部 UAV barrier。 |
| `Source/Falcor/Core/API/RenderContext.cpp` | 每次 D3D12 draw 检查 IA 资源状态；设置动态 stencil reference；输出无效 draw 的诊断，允许候选图因参数错误被拒绝。 |
| `Source/Falcor/Core/API/Texture.cpp`、`Texture.h` | 区分 Cube 数和实际六面层数，修正子资源数量、状态及 view 范围。 |
| `Source/Falcor/Core/API/ResourceViews.cpp` | 校验 Cube SRV 的完整六面范围，对当前后端不支持的 view 明确拒绝。 |
| `Source/Falcor/Core/API/ParameterBlock.cpp`、`ParameterBlock.h` | 按实际绑定的 mip/层范围转换状态，保证 UAV 写入顺序。 |
| `Source/Falcor/Core/API/FBO.cpp` | FBO 层范围检查使用物理层数，支持正确的 Cube 面附件。 |
| `Source/Falcor/Core/Program/ProgramReflection.cpp` | 从 Shader 资源的元素类型取得返回类型，以区分 float、uint、int 绑定。 |
| `Source/Falcor/RenderGraph/RenderGraph.cpp`、`RenderGraph.h` | 新增图拓扑查询、执行前验证回调、外部输入检测；初始化尚未确定的 viewport 尺寸；检查结构化缓冲连接。 |
| `Source/Falcor/RenderGraph/RenderGraphCompiler.cpp` | 正确反射外部 raw/structured buffer，检查大小、stride 和绑定能力。 |
| `Source/Falcor/RenderGraph/RenderPassReflection.cpp`、`RenderPassReflection.h` | 增加独立的 StructuredBuffer 类型，记录并校验 stride/count。 |
| `Source/Falcor/RenderGraph/ResourceCache.cpp` | 按反射信息分配真实结构化缓冲。 |
| `Source/Falcor/Scene/SceneBuilder.cpp`、`SceneBuilder.h` | 新增 `DontPretransformStaticMeshes`，保留模型局部坐标及实例变换，供依赖对象坐标的材质使用。 |
| `Source/Mogwai/Mogwai.cpp`、`Mogwai.h`、`MogwaiScripting.cpp` | 新增 `graphExecutionCallback`，让带历史的脚本执行替代默认执行，避免一帧绘制两次；修正回调切图后的显示与对象生命周期。 |
| `Source/RenderPasses/CMakeLists.txt` | 加入 CustomRenderPipline 插件构建。 |
| `Source/Tools/FalcorTest/CMakeLists.txt` | 加入原生测试与独立测试入口。 |
| `external/include/backward/backward.hpp` | 修复 Windows 栈解析的未初始化数据、空指针和字符串终止问题，避免报错过程中再次崩溃。 |

这些底层改动会影响对应 Falcor API；上层渲染行为主要集中在新插件。RenderPassReflection 的布局发生了变化，修改底层后应连同 Mogwai 和全部插件一起构建，避免混用旧 DLL。

## 2. 新增代码放在哪里

| 位置 | 内容 |
| --- | --- |
| [Source/RenderPasses/customrenderpipline](../../Source/RenderPasses/customrenderpipline) | C++ Pass、Slang、UE 算法片段、Schema/codec 合同、来源记录及部分历史原型。文件存在不表示全部已注册启用。 |
| [scripts/customrenderpipline](../../scripts/customrenderpipline) | 图构建、场景转换、运行入口、验证脚本和测试。 |
| [Source/Tools/FalcorTest/Tests/Core](../../Source/Tools/FalcorTest/Tests/Core) | 新增 RenderGraphStructuredBuffers 和 CustomRenderPipline 的资源能力、Cube、外部输入、读回、光照配置、场景 identity 等测试。 |
| [Source/Tools/FalcorTest/Standalone](../../Source/Tools/FalcorTest/Standalone) | 4 个独立测试入口文件。 |
| [docs/research](.)、[docs/superpowers](../superpowers) | 实现说明、数值验证、来源、计划和未完成项。 |

框架在 [CustomRenderPiplinePasses.cpp](../../Source/RenderPasses/customrenderpipline/CustomRenderPiplinePasses.cpp) 注册 11 类通用 Pass：Init、PrePass、GBuffer、Decode、GBufferAdapter、Compute、Fullscreen、MeshDraw、Asset、HistoryRead、HistoryWrite。

[UEReferenceExtension.cpp](../../Source/RenderPasses/customrenderpipline/Extensions/UEReference/UEReferenceExtension.cpp) 另注册 4 类具体算法：`UEReferenceGBufferPass`、`UEReferenceLightingPass`、`UEReferenceShadowSetupPass`、`UEReferenceSkyViewSetupPass`。目前它们随同一个 DLL 构建，只有被图引用才执行。

## 3. 功能和入口

| 功能 | 能做什么 | 主要入口或现有示例 |
| --- | --- | --- |
| 原生材质与可配置 GBuffer | JSON 定义附件名称/格式，Slang 定义 MRT 通道与位编码；原生 MaterialSystem 提供材质属性 | [native_gbuffer.py](../../scripts/customrenderpipline/native_gbuffer.py)、[配置说明](customrenderpipline-native-gbuffer-zh.md) |
| 旧 Schema / UE 编码案例 | 定义字段通道、位范围及 model ID，生成编码/解码分派；供旧 UEReference 案例使用 | [generate_schema.py](../../scripts/customrenderpipline/generate_schema.py)、[Schemas](../../Source/RenderPasses/customrenderpipline/Schemas) |
| 材质程序 | 常量材质、自定义 Shader、文件贴图、图内纹理/raw buffer、sampler 和参数绑定 | [material_shader_smoke.py](../../scripts/customrenderpipline/material_shader_smoke.py)、[material_graph_inputs_smoke.py](../../scripts/customrenderpipline/material_graph_inputs_smoke.py) |
| Mesh 路由与绘制 | 按材质、模型、实例、标签筛选，独立 MRT、深度、模板、混合、写掩码、viewport 和矩阵 | [auxiliary_mesh_smoke.py](../../scripts/customrenderpipline/auxiliary_mesh_smoke.py)、[mesh_views_smoke.py](../../scripts/customrenderpipline/mesh_views_smoke.py) |
| Compute / Fullscreen | 用 Shader 和声明添加计算/屏幕处理；支持资源依赖和按尺寸 dispatch | [shader_executor_smoke.py](../../scripts/customrenderpipline/shader_executor_smoke.py)、[pass_definition.py](../../scripts/customrenderpipline/pass_definition.py) |
| 文件素材 | DDS 完整 mip 链、原始 buffer 等作为不可变输入；每帧从私有 GPU 源复制，避免下游覆盖污染素材 | [asset_source_smoke.py](../../scripts/customrenderpipline/asset_source_smoke.py) |
| 结构化缓冲 | Pass 间传递 `StructuredBuffer<T>` / `RWStructuredBuffer<T>`，显式 stride/count，检查 Shader 布局 | [structured_buffers_smoke.py](../../scripts/customrenderpipline/structured_buffers_smoke.py) |
| Cube / mip / 层 | 对单独 Cube 面或 mip 绘制、采样和观察，供 SkyLight 捕获与过滤使用 | [资源接口说明](ue-legacy-sky-light-resources.md) |
| 历史资源 | 上一成功帧纹理、双缓冲、resize/camera cut/reset 失效、失败帧不发布 | [pipeline.py](../../scripts/customrenderpipline/pipeline.py)、[history_resources_smoke.py](../../scripts/customrenderpipline/history_resources_smoke.py) |
| 图替换与回滚 | 冻结 Shader/资源文件，候选图离屏验证，通过后整体切换，失败保留旧图 | [pipeline_snapshot.py](../../scripts/customrenderpipline/pipeline_snapshot.py)、`SchemaPipeline.stage/commit` |
| 输出观察与误差 | 普通二维输出用 Mogwai，常规图像误差用原生 ErrorMeasurePass；补充原始字节/Depth/Stencil、mip/面、GPU 图集及样本容差检查 | [observer.py](../../scripts/customrenderpipline/observer.py)、[native_reuse_smoke.py](../../scripts/customrenderpipline/native_reuse_smoke.py) |

以下为随附的 **UEReference 效果扩展与案例**，不属于框架本体的固定渲染功能：

| 效果 | 作用 | 扩展或案例入口 |
| --- | --- | --- |
| 延迟直接光 | GBuffer 消费、方向光/点光/聚光及已移植材质模型的光照分派 | [UEReferenceLightingPass.cpp](../../Source/RenderPasses/customrenderpipline/Extensions/UEReference/UEReferenceLightingPass.cpp)、[模型光照说明](ue-legacy-model-lighting.md) |
| 方向光阴影 | 当前原生相机的传统 CSM setup、1–4 级深度、PCF 投影与光照接入 | [shadow_graph.py](../../scripts/customrenderpipline/shadow_graph.py) |
| 大气与天空材质 | Transmittance、MultiScattering、SkyView LUT、源太阳计算及源天空材质 | [atmosphere.py](../../scripts/customrenderpipline/atmosphere.py)、[sky_view.py](../../scripts/customrenderpipline/sky_view.py) |
| SkyLight | 六面天空捕获、降采样、镜面过滤、SH、PreintegratedGF、DefaultLit 环境光 | [SkyLight 说明](ue-legacy-native-sky-light.md)、[targetmap_graph.py](../../scripts/customrenderpipline/targetmap_graph.py) |
| 自动曝光 | 直方图测光、EyeAdaptation、上一成功帧曝光、PreExposure、线性曝光输出 | [exposure_graph.py](../../scripts/customrenderpipline/exposure_graph.py)、[downsample.py](../../scripts/customrenderpipline/downsample.py) |

`OpaqueModels.json` 当前登记 Unlit、DefaultLit、Subsurface、PreintegratedSkin、ClearCoat、TwoSidedFoliage、Cloth。Schema 的登记和某个具体图启用哪些 Lighting 程序是两件事；不要只添加 model ID 就认为对应算法已经接通。targetmap 当前使用 DefaultLit/Unlit 路径。

## 4. 运行 UEReference 场景案例

PowerShell：

```powershell
Set-Location E:\Project\falcor\Falcor-m0
& .\scripts\customrenderpipline\run_targetmap_live.ps1
```

这是已导出 targetmap 的可见原生预览，包含 CSM、天空/SkyLight 和自动曝光，显示 `ExposureApply.exposedLinear`。它使用 `build/source-targetmap/Scene.json`；当前磁盘上该文件、Mogwai 和 `bin/Release/plugins/customrenderpipline.dll` 均存在。运行日志在 `build/targetmap-live`。这是线性曝光结果，完整 tone mapping/后期对齐仍未完成。

修改 C++ 后先在该目录构建：

```powershell
& .\tools\.packman\cmake\bin\cmake.exe --build .\build\windows-vs2022 --config Release --parallel 4
```

入口脚本用 `graphExecutionCallback` 执行完整历史帧。新 viewer 应沿用这个入口方式；在 `sceneUpdateCallback` 中自行渲染，再让 Mogwai 默认渲染，会产生重复执行。

## 5. 修改材质

普通原生入口的材质在 Falcor Scene / `StandardMaterial` 或原生注册的材质类型中定义，写入规则在 GBuffer Slang 中定义。**本节以下的 Scene JSON、`UESurface` 与 Schema 是旧 UEReference 案例的用法。**

材质的职责分成四处：

1. **Scene JSON**：定义实例使用哪个材质名，材质的 `shading_model`、`material_program`、颜色、粗糙度、金属度、双面和标签。
2. **材质 Slang**：执行纹理采样、程序纹理、材质参数计算，生成 `UESurface`。
3. **Schema + codec**：规定这些表面属性如何写入/读出 GBuffer。
4. **Lighting Shader**：根据解码后的属性、光源和可见性计算光照。

常量材质示例（已有 Scene 的 `materials` 中的一项，名称要匹配实际 Falcor Scene 材质）：

```json
{
  "shading_model": "DefaultLit",
  "material_program": "constant",
  "base_color_linear": [0.18, 0.45, 0.8],
  "emissive_linear": [0, 0, 0],
  "roughness": 0.5,
  "metallic": 0,
  "specular": 0.5
}
```

程序材质设置 `material_program: "shader"`，在对应 `UEReferenceGBufferPass` 的 `shader.file` 指向 Slang，并在 `file_inputs` 登记该文件。最小的 evaluator 形式为：

```hlsl
import Scene.Raster;

UESurface ueEvaluateMaterial(VSOut input, UESurface surface)
{
    surface.baseColor = float3(0.18, 0.45, 0.8);
    surface.roughness = 0.5;
    return surface;
}

#include "RenderPasses/customrenderpipline/CustomRenderPiplineRaster.3d.slang"
```

`UESurface` 来自框架注入的 Schema。贴图、sampler、参数通过 Pass 的 `materialBindings` 声明，完整可运行绑定实例见 `material_shader_smoke.py`。依赖模型局部坐标时，用 `SceneBuilderFlags.DontPretransformStaticMeshes` 加载场景。

修改原始 JSON/Shader 后，需要重新 `stage()` 和 `commit()` 才会作用于已冻结的图。当前 targetmap 启动脚本会重新生成自己的声明，持久改动应放在 `targetmap_graph.py`、相应 Shader 或场景生成源中。

## 6. 添加一个 Compute Pass

示例：把解码后的 BaseColor 乘一个倍率。先保存 `Gain.slang`：

```hlsl
Texture2D<float4> gInput;
RWTexture2D<float4> gOutput;
cbuffer Params { uint2 extent; float gain; };

[numthreads(8, 8, 1)]
void main(uint3 tid : SV_DispatchThreadID)
{
    if (any(tid.xy >= extent)) return;
    float4 color = gInput[tid.xy];
    gOutput[tid.xy] = float4(color.rgb * gain, color.a);
}
```

在已有图的 `nodes` 中增加以下节点；把 `shader.file` 换成实际文件路径（相对路径按声明文件所在目录解析）：

```json
{
  "name": "Gain",
  "type": "CustomRenderPiplineComputePass",
  "file_inputs": ["shader.file"],
  "properties": {
    "shader": {"file": "Gain.slang", "compute": "main"},
    "resources": [
      {"name": "input", "binding": "gInput", "direction": "input", "format": "RGBA32Float"},
      {"name": "output", "binding": "gOutput", "direction": "output", "format": "RGBA32Float",
       "size": {"relative_to": "input", "divisor": [1, 1]}}
    ],
    "uniforms": {
      "Params.extent": {"type": "uint2", "source": "extent"},
      "Params.gain": {"type": "float", "value": 2.0}
    },
    "dispatch": {"extent": "output"}
  }
}
```

再给 `edges` 增加 `["Decode.baseColor", "Gain.input"]`，给 `outputs` 增加 `"Gain.output"`，然后重新 stage/commit。这个例子不需要修改 C++ 或 CMake。

换成 Fullscreen 时使用 `CustomRenderPiplineFullscreenPass`、pixel entry 和 `SV_Target0` 输出；Fullscreen 的输出资源用 `slot: 0`，不写 `binding`。绘制场景几何则使用 `CustomRenderPiplineMeshDrawPass`，其附件放在 `colorTargets`/`depthTarget` 中。

结构化缓冲端口的写法为 `{"name":"values","binding":"gValues","direction":"output","kind":"structured_buffer","stride":16,"count":8}`，对应 `RWStructuredBuffer<float4>`。消费端用相同 stride/count 的 input，Shader 为 `StructuredBuffer<float4>`；通过图 edge 连接，数据保留在 GPU。

## 7. 加载图、使用历史和观察输出

下面在已初始化 Falcor 场景和模块路径的 Mogwai 脚本中使用；路径替换为自己的文件。完整启动环境可参照 `targetmap_live.py`。

```python
import json
from pathlib import Path
from generate_schema import DEFAULT_SCHEMA
from pipeline import SchemaPipeline
from observer import PipelineObserver

pipeline = SchemaPipeline(m, Path("build/my-case/schemas"), graph_kind="declared")
pipeline.stage(json.loads(DEFAULT_SCHEMA.read_text()), {
    "sceneDefinition": str(Path("Scene.json").resolve()),
    "graphDefinitionPath": str(Path("Passes.json").resolve()),
})
pipeline.commit()
pipeline.render_frame(0, delta_time=1 / 60)

graph = pipeline.active[0]
print(graph.getTopology())
observer = PipelineObserver(graph)
raw = observer.read("Decode.baseColor")
atlas, layout = observer.atlas(["Decode.baseColor", "Decode.normalUE"], columns=2)
```

这个例子使用 DefaultLit Schema。需要其他模型或 Lighting 时，必须传入包含相应 codec/lighting 合同的 Schema，targetmap 的完整组合可参考其运行脚本。

自动曝光或其他时序效果需要 HistoryRead/HistoryWrite 成对连接，并用连续的 `render_frame` 帧号执行。相机跳切时使用 `pipeline.render_frame(next_frame, camera_cut=True, delta_time=1/60)`。这套接口管理历史有效性，本身不等于实现了 TAA/SSR 算法。

对 targetmap，`targetmap_graph(scene_path, scene, shadows=True, sky_light=True, schema=schema)` 会组合天空材质、大气、六面捕获、过滤/SH、环境光和曝光。`scene` 应先经过 `prepare_source_sky_material()`，并据此加载原生场景。

观察功能只访问 `outputs` 中声明的端口。读取原始数据用 `read`，选 mip/面用 `read(name, mip=2, slice=5)`，同时显示多个面用 `atlas_views`。`read`/`to_numpy()` 属于显式 GPU→CPU 观察，不应塞进正常预览的每帧循环。

普通二维纹理直接在 Mogwai 的 `Output` 中选择，用 `Show In Debug Window` 同时打开多个输出，`Save To File` 保存。应选择描述里已经标记的端口；`List All Outputs` 下选择未声明的端口会改变图输出并触发封存校验。需要新输出时，修改描述后重新 stage/commit，不必为此编写显示 Pass，也不要默认把所有端口都标为输出。

## 8. 性能修复与当前边界

已做的集成修复包括：避免一帧重复执行整图；停止每帧重建相同 Mesh Shader；正确断开 Scene 更新订阅；在直接帧执行中结束 GPU 临时分配生命周期；缓存不可变 PreintegratedGF；在同次执行内共享场景 identity；合批 mesh 读回；曝光改为 Shader 直接读 GPU 纹理；把曝光/错误检查的快照合并到帧末验证。

最近已保存的同视图无窗口对比为 **18.47 ms → 16.49 ms**，约 **54.15 → 60.65 FPS**，五份观测输出字节完全一致。这里引用已有结果，本次说明整理没有重新跑 GPU 基准。有窗口最近记录约 35–36 FPS，属于更早测量；不能把 headless 数值当成实时窗口帧率。详见 [读回优化](ue-legacy-frame-readback-performance.md) 和 [交互性能](ue-legacy-interactive-performance.md)。

仍有帧完成等待、场景/纹理 identity 检查和旧自定义材质 scalar ABI 的同步路径。当前不是完全异步渲染流水线。SkyLight 捕获/过滤仍每帧运行。

当前主要使用与验证平台是 Windows D3D12 / SM6.6。UE 框架 Mesh 路径支持静态索引三角形；原生 Falcor 的其他几何功能并不因此消失，但还没有接进这条 UE 路径。Indirect、通用蒙皮/动画、完整 GI/SSR、完整后期及 WebRTC 尚未形成这里的完整工作流。

**FY1 头发还未完成整图。** 当前已存在 [Lighting.slangh](../../Source/RenderPasses/customrenderpipline/Extensions/UEReference/Cases/HairFY1/Lighting.slangh)、原素材 Asset Pass、[case builder](../../scripts/customrenderpipline/build_fy1_hair_case.py) 和 17 组头发光照 GPU 条件测试记录；`Depth.slang`、`Base.slang`、`Deferred.slang` 尚未落地，Hair Schema 和原生阴影/全图对齐仍待完成。builder 中的 DefaultLit 材质目前只是场景路由占位。生成了 case 文件不能视为已经有可运行的完整头发预览。

RDC 的 GBuffer/Depth/Shadow/Shading 用于离线比较；原始贴图、材质参数、允许的姿态几何可以作为素材输入。框架数值测试通过不等于最终 RDC 画面对齐。


## 9. 读取可复用的 Pass 描述

图节点可以直接给出 `type/properties/file_inputs`，也可以引用描述文件：

```json
{
  "version": 1,
  "nodes": [
    {"name": "Generate", "description": "passes/Pattern.json"},
    {"name": "Grade", "description": "passes/Grade.json",
     "properties": {"uniforms": {"Settings.gain": {"value": 0.75}}}}
  ],
  "edges": [["Generate.color", "Grade.source"]],
  "outputs": ["Grade.color", "Generate.color"]
}
```

描述文件声明 `type`、`properties`、`file_inputs`，可选 `inherit_pipeline`。节点的 `properties` 递归覆盖描述中的默认参数；Shader、贴图等文件相对于定义该值的 JSON 解析。展开后的描述、Shader include 和资源一起进入不可变快照。修改或删除原始描述不会污染已经提交的图，再次 `stage()` 才会加载新内容。

现有原生 Falcor Pass 也可作为节点，使用 `inherit_pipeline: false`。新增算法一般只需要描述和 Shader，特殊 GPU 操作才需要 C++ Pass。UE 便利组图函数已经移到 `extensions.ue_reference.pipeline`；新项目默认使用 `pipeline.SchemaPipeline`。

例如图像复制直接使用 `BlitPass`，常规模糊/合成/累积/TAA/Tone mapping 优先检查对应原生 Pass。它们的 `getProperties()` 必须返回稳定的可执行参数；图已提交后修改这些参数，也需重新 stage。完整原生 Blit 与误差组合见 [native_reuse_smoke.py](../../scripts/customrenderpipline/native_reuse_smoke.py)。

## 10. 原始像素与误差比较

普通纹理/缓冲由 `PipelineObserver.read()` 调用 Falcor 原生 `Texture.to_numpy(mip_level, array_slice)` / `Buffer.to_numpy()`；保留元数据，不另实现一条普通原生读回路径。只有 D32FloatS8Uint 的精确双平面读取使用插件补充。

常规 RGB L1/MSE 和差分图优先接入原生 `ErrorMeasurePass`；它包含 CPU 统计读回，即便 `ComputeAverage: false` 仍会同步。以下 helper 用于明确指定编码的原始样本容差比较，适合离线验证。

```python
from observer import PipelineObserver, compare_arrays

observer = PipelineObserver(pipeline.active[0])
raw = observer.read("Grade.color")
# expected 为相同尺寸、编码和单位的参考数组。
report = observer.compare("Grade.color", expected, dtype="<f4", atol=1e-6, rtol=0)
# 已有 CPU 数组也可直接比较：
report = compare_arrays(actual, expected, atol=1e-6)
```

结果包含 `passed`、`max_abs`、`mae`、`rmse`、`failed_samples` 和 `worst_index`，判据为 `abs(actual-reference) <= atol + rtol*abs(reference)`。维度不匹配、空数组、NaN/Inf 或超出数值范围会报错。

`compare()` 按调用者指定的 dtype 解释原始字节，不隐式转换 sRGB、通道顺序、Packed 编码或法线。Packed 格式和带 padding 的 Depth/Stencil 应先用 `read()` 取得原始平面，自行解码后再调用 `compare_arrays()`。读回与比较是显式调试操作，不加入每帧预览循环。

## 11. 迁移注意事项

- 新源码目录：`Source/RenderPasses/customrenderpipline`；新脚本目录：`scripts/customrenderpipline`。
- 新绑定前缀：`customRenderPipline`；太阳算法查询属于扩展，名为 `ueReferenceSourceSun`。
- 历史分析文档、构建证据和旧快照不作改写。旧图的路径/DLL 指纹已经失效，需要从原始配置重新生成。
- 旧 `UELegacy.dll/pdb` 已移至 `build/customrenderpipline-migration/retired-plugin`，避免与新插件同时加载。
- 框架验收脚本为 [framework_smoke.py](../../scripts/customrenderpipline/framework_smoke.py)，覆盖描述组合、真实 GPU 输出、误差比较，以及坏 Shader/坏描述/坏绑定保留旧图。

本次迁移已完成全量 Release 构建、466 项 Python 回归和 8 组 GPU 验收（描述/回滚、Shader 执行器、材质、结构化缓冲、输出观察、历史资源、参考光照、天空 setup）。GPU 回归中发现并修复了离屏执行时材质改名未触发 Shader 变体更新的崩溃。验证索引位于 `build/customrenderpipline-migration/verification.json`。

随后完成的原生能力审计删除了重复读回实现，通过全量 Release 构建、469 项 Python 回归和 6 组相关 GPU 验收。最新精简与限制见 [审计报告](customrenderpipline-native-falcor-audit-zh.md)，验证索引为 `build/native-falcor-audit/verification.json`。本轮没有重新测实时帧率。
