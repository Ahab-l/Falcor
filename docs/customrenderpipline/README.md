# CustomRenderPipline 使用指南

`customrenderpipline` 是 Falcor 的通用扩展，用脚本装配可组合的 RenderGraph Pass，并允许 consumer 自己定义材质数据和 GBuffer 编码。它负责资源契约、Pass 执行、Mesh 选择、观察和验证；它不规定 UE 的材质 ABI、深度约定、光照公式或后处理顺序。

## 1. 适用范围和边界

核心插件提供这些 Pass：

| Pass 类型 | 用途 |
| --- | --- |
| `CustomRenderPiplineGBufferPass` | 用 Falcor Scene 绘制可配置 MRT 和深度附件 |
| `CustomRenderPiplineMeshDrawPass` | 用自定义顶点/像素 Shader 绘制选定的三角形实例 |
| `CustomRenderPiplineComputePass` | 显式资源和 dispatch 的 Compute Pass |
| `CustomRenderPiplineFullscreenPass` | 全屏 Shader 和独立 MRT 输出 |
| `CustomRenderPiplineAssetPass` | 从文件复制不可变纹理或原始缓冲到图输出 |
| `CustomRenderPiplineHistoryReadPass` / `WritePass` | 跨帧保留上一帧资源 |

UE targetmap、UE MaterialProgram、Lighting、SkyLight 和具体 Schema/Codec 都应放在独立 consumer 中。它们可以使用本插件，但不应修改本插件来保存 UE 专有约定。

Shader 执行器和 Mesh 执行器当前要求 D3D12 与 Shader Model 6.6。精确 Depth/Stencil 平面读回也要求 D3D12。

## 2. 加载插件和创建图

在 Python 脚本中显式加载插件，然后按 Falcor 的普通方式创建图、Pass、边和输出：

```python
from falcor import *
import json

loadPlugin("customrenderpipline")
graph = RenderGraph("CustomMaterialGraph")
graph.setScene(scene)
```

`createPass()` 使用注册的类型名，`addPass()` 把实例加入图。插件不会自动连接资源，也不会自动标记输出：

```python
gbuf = createPass("CustomRenderPiplineGBufferPass", {
    "definition": "schemas/material_gbuffer.json",
})
graph.addPass(gbuf, "GBuffer")

lighting = createPass("CustomRenderPiplineFullscreenPass", {
    "shader": {"file": "shaders/lighting.slang", "pixel": "psMain"},
    "resources": [
        {"name": "baseColor", "direction": "input", "binding": "gBaseColor", "format": "RGBA16Float"},
        {"name": "normal", "direction": "input", "binding": "gNormal", "format": "RGBA16Float"},
        {"name": "output", "direction": "output", "binding": "gOutput", "format": "RGBA16Float", "slot": 0},
    ],
})
graph.addPass(lighting, "Lighting")
graph.addEdge("GBuffer.baseColor", "Lighting.baseColor")
graph.addEdge("GBuffer.normal", "Lighting.normal")
graph.markOutput("Lighting.output")
```

资源声明必须是显式的。核心 Pass 不接受 `schema` 或 `schema_expanded` 宏作为原生输入；如果 consumer 有 Schema，应在 consumer 层展开成附件、资源和 Shader 定义。

## 3. 用脚本路由 MeshPass

当不同 Mesh 需要不同 Shader、MRT 或固定功能状态时，调用：

```python
routes = [
    {
        "name": "opaque",
        "materials": ["OpaqueMaterial"],
        "properties": {
            "shader": {
                "file": "shaders/opaque_gbuffer.slang",
                "vertex": "vsMain",
                "pixel": "psMain",
            },
            "colorTargets": [
                {"name": "baseColor", "format": "RGBA16Float", "slot": 0},
                {"name": "normal", "format": "RGBA16Float", "slot": 1},
            ],
            "depthTarget": {"name": "depth", "format": "D32Float"},
            "state": {"depth_enabled": True, "depth_write": True, "cull_mode": "Back"},
        },
    },
    {
        "name": "hair",
        "materials": ["HairMaterial"],
        "properties": {
            "shader": {
                "file": "shaders/hair_gbuffer.slang",
                "vertex": "vsMain",
                "pixel": "psMain",
            },
            "colorTargets": [
                {"name": "baseColor", "format": "RGBA16Float", "slot": 0, "load": "load"},
                {"name": "normal", "format": "RGBA16Float", "slot": 1, "load": "load"},
            ],
            "depthTarget": {"name": "depth", "format": "D32Float", "load": "load"},
            "state": {"depth_enabled": True, "depth_write": False, "cull_mode": "None"},
        },
    },
]

receipt = customRenderPiplineAddMeshPasses(graph, scene, routes)
print(receipt)

graph.addEdge("opaque.baseColor", "lighting.opaqueBaseColor")
graph.addEdge("hair.baseColor", "lighting.hairBaseColor")
graph.markOutput("lighting.output")
```

路由 helper 会为每条路由创建普通的 `CustomRenderPiplineMeshDrawPass`，不会创建隐藏调度器，也不会代替 RenderGraph 的边和输出管理。返回值包含每条路由的名称、解析出的实例数量和实例 ID。

选择器规则：

- `materials` 与 `instanceIDs` 必须二选一。
- `materials` 按当前 Scene 的材质名称快照解析为三角形实例 ID。
- `instanceIDs` 适合 consumer 已经有稳定选择结果的情况。
- 同一路由内的重复 ID 会去重。
- 不同路由包含同一实例、路由名重复、材质不存在、实例越界或不是三角形实例时，调用失败且已创建的路由会回滚。
- Scene 的材质成员关系变化后应重新建立路由表；普通变换更新会继续作用于已有 draw list。

这是 raster MeshPass，不是硬件 Mesh Shader 管线。

## 4. 自定义 GBuffer 和 Codec

`CustomRenderPiplineGBufferPass` 读取一个 JSON definition。definition 只描述附件和 Shader，字段值如何编码由 consumer Shader 决定：

```json
{
  "shader": "shaders/ue_targetmap_gbuffer.slang",
  "vertexEntry": "vsMain",
  "pixelEntry": "psMain",
  "depthFormat": "D32Float",
  "defines": {"GBUFFER_LAYOUT_REV": 3},
  "attachments": [
    {"name": "baseColorRoughness", "format": "RGBA16Float"},
    {"name": "normalMaterial", "format": "RGBA16Float"},
    {"name": "velocity", "format": "RG16Float"}
  ]
}
```

```python
gbuf = createPass("CustomRenderPiplineGBufferPass", {"definition": "schemas/ue_targetmap_gbuffer.json"})
graph.addPass(gbuf, "UEGBuffer")
```

输出端口是附件名称和 `depth`。GBuffer Pass 不自动生成 Codec，也不假设 UE 的 packed layout。建议把布局说明、编码 Shader 和解码 Shader 放在 consumer 目录，并在测试中同时检查：

1. 附件格式和 MRT slot；
2. 编码后的原始值；
3. 解码后的材质字段；
4. 位布局、量化范围和容差规则。

## 5. Compute、Fullscreen 和资源

Compute Pass 的资源方向、绑定名和 dispatch 是显式的：

```python
compute = createPass("CustomRenderPiplineComputePass", {
    "shader": {"file": "shaders/build_lut.slang", "compute": "main"},
    "resources": [
        {"name": "lut", "direction": "output", "format": "RGBA16Float", "size": [256, 256]},
    ],
    "uniforms": {"scale": {"value": 1.0}},
    "dispatch": {"threads": [256, 256, 1], "group": [8, 8, 1]},
})
graph.addPass(compute, "BuildLut")
```

`execution: "once"` 只适用于无输入、固定尺寸、单 mip 的纹理输出，并且 uniforms 必须是字面值。适合 LUT 或不可变初始化；动态资源应使用默认的 `every_frame`。

MeshPass 的 `colorTargets`、`depthTarget`、`state`、`resources`、`samplers` 和 `uniforms` 都属于该路由的 `properties`。附件支持 `clear/load`、write mask、additive/alpha blend、深度/模板状态、mip/array/cube 视图；资源和绑定名必须显式且不能覆盖内建变量。

## 6. Asset 和跨帧 History

Asset Pass 从文件加载一次，然后每帧只做 GPU copy，不依赖旧 Config 或快照：

```python
assets = createPass("CustomRenderPiplineAssetPass", {
    "assets": {
        "brdfLut": {
            "kind": "texture2D", "file": "data/brdf.dds",
            "format": "RGBA16Float", "size": [256, 256], "mip_count": 1,
        },
        "materialTable": {
            "kind": "raw_buffer", "file": "data/materials.bin", "bytes": 4096,
        },
    },
})
graph.addPass(assets, "Assets")
```

History 是普通跨帧资源，不是整图事务回滚：

```python
read = createPass("CustomRenderPiplineHistoryReadPass", {
    "key": "taa", "resources": [{"name": "color", "format": "RGBA16Float"}],
})
write = createPass("CustomRenderPiplineHistoryWritePass", {
    "key": "taa", "resources": [{"name": "color", "format": "RGBA16Float"}],
})
graph.addPass(read, "HistoryRead")
graph.addPass(write, "HistoryWrite")
graph.addEdge("HistoryRead.color", "TAA.previous")
graph.addEdge("TAA.color", "HistoryWrite.color")
graph.markOutput("HistoryWrite.status")
customRenderPiplineBindHistory(graph)

# 场景、分辨率或测试用例切换时
customRenderPiplineResetHistory(graph, "taa")
print(customRenderPiplineHistoryInfo(graph))
```

读节点必须在依赖图上先于写节点，写节点的 `status` 必须是图输出。第一次读取返回清零资源；状态包含 `valid` 和更新次数。

## 7. 观察、截图和误差验证

观察前先把目标端口标记为输出，然后读取资源目录：

```python
catalog = json.loads(customRenderPiplineOutputCatalog(graph))
for item in catalog:
    print(item)
```

`catalog` 会区分 `texture2D`、`texture2DArray`、`textureCube`、`raw_buffer` 和 `structured_buffer`，并返回格式、尺寸、mip/array、字节数、stride 和 count。

可用 `customRenderPiplineRenderAtlas()` 在 GPU 上把多个输出拼成一个 `RGBA32Float` 图集：

```python
layout = {
    "width": 1024, "height": 512,
    "tiles": [
        {"name": "UEGBuffer.baseColorRoughness", "x": 0, "y": 0,
         "width": 512, "height": 512,
         "display": {"mode": "color", "scale": 1.0, "bias": 0.0}},
        {"name": "UEGBuffer.depth", "x": 512, "y": 0,
         "width": 512, "height": 512,
         "display": {"mode": "depth", "scale": 1.0, "bias": 0.0}},
    ],
}
atlas = customRenderPiplineRenderAtlas(graph, json.dumps(layout))
```

Atlas 支持普通浮点/整数纹理通道、raw/structured buffer 的 bytes/uint32/sint32/float32 显示、Depth、mip 和 array/cube face。它会等待 GPU，适合调试和证据生成，不应放在实时帧路径。

Depth/Stencil 精确读回：

```python
# 同步版本：会等待 GPU，适合一次性诊断
planes = customRenderPiplineReadDepthStencil(depth_texture, 0, 0)

# 异步版本：提交后轮询，不在 result() 中等待
pending = customRenderPiplineReadDepthStencilAsync(depth_texture, 0, 0, 64 * 1024 * 1024)
if pending.ready:
    planes = pending.result()
```

Depth/Stencil 返回原生 plane bytes、row bytes、native format 和尺寸。普通纹理/缓冲的比较应优先使用 GPU 侧误差 Pass 或单次批量读回，避免每个像素同步 `map()`。

## 8. UE targetmap consumer 示例

之前还原的 UE targetmap 管线可以作为 consumer 使用本框架：

1. UE 兼容层负责材质参数求值、Packed GBuffer Codec、光照和阴影 Shader；
2. `CustomRenderPiplineGBufferPass` 或脚本 MeshPass 负责把这些 Shader 接入 RenderGraph；
3. lighting Pass 只读取定义好的附件和解码结果；
4. 观察器在 shading 输出之后、Bloom/Tonemap 之前生成 Atlas 和误差证据；
5. RDC 只作为离线参考，不作为核心运行时输入。

一个 consumer 图的骨架见 [`examples/ue_targetmap_consumer.py`](./examples/ue_targetmap_consumer.py)。该示例只依赖通用插件接口；真正的 UE 参数和 Shader 路径由外部管线提供。

## 9. 常见错误和处理顺序

- **Pass 类型未知**：先 `loadPlugin("customrenderpipline")`，再创建 Pass。
- **资源没有输出**：观察器只能读取 `graph.markOutput()` 后的资源。
- **路由重叠**：检查材质解析后的实例 ID，必要时改用显式 `instanceIDs`。
- **附件尺寸不一致**：确认 producer 的 size 和 consumer 的反射尺寸，不要在 consumer 端静默缩放。
- **History 没有状态**：确认 reader/writer 使用同一个 key，且 writer.status 已标记输出。
- **Shader 编译失败**：保留上一次可运行的 consumer 图，由外部脚本负责回退；核心插件不提供旧 UE 整图事务。
- **性能下降**：把 Atlas、同步读回和误差比较移出实时路径；优先异步任务或 GPU 侧比较。

更多字段约束见 [`python-api.md`](./python-api.md)，可复制示例见 [`examples/mesh_pass_routes.py`](./examples/mesh_pass_routes.py)。
