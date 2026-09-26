# CustomRenderPipline Python/API 速查

## 绑定入口

| 入口 | 参数 | 结果 |
| --- | --- | --- |
| `customRenderPiplineAddMeshPasses(graph, scene, routes)` | RenderGraph、Scene、路由字典列表 | 路由 receipt 列表 |
| `customRenderPiplineBindHistory(graph)` | RenderGraph | 绑定同 key 的读/写节点 |
| `customRenderPiplineResetHistory(graph, key="")` | RenderGraph、可选 key | 清空指定或全部 History |
| `customRenderPiplineHistoryInfo(graph)` | RenderGraph | JSON 字符串，含 valid/updates/extent |
| `customRenderPiplineComputeDispatchCount(graph, name)` | RenderGraph、Compute 节点名 | 实际提交的 dispatch 次数 |
| `customRenderPiplineOutputCatalog(graph)` | RenderGraph | JSON 字符串，列出已标记输出 |
| `customRenderPiplineRenderAtlas(graph, layout_json)` | RenderGraph、JSON 字符串 | GPU 生成的 RGBA32Float Texture2D |
| `customRenderPiplineProbeRTV(graph, values)` | RenderGraph、float 列表 | RGB10A2/BGRA8/float/sRGB 原始 bytes |
| `customRenderPiplineReadDepthStencil(texture, mip=0, slice=0)` | 单采样 D32FloatS8Uint Texture | 同步 plane 字节字典 |
| `customRenderPiplineReadDepthStencilAsync(texture, mip=0, slice=0, max_bytes=64*1024*1024)` | 同上 | `DepthStencilReadbackTask` |

异步任务属性：`ready`、`staging_bytes`、`byte_size`、`result()`。`result()` 未就绪时不会等待，而是返回空的 plane 数据；调用者应轮询 `ready`。

## Mesh 路由字段

```text
route = {
  name: string,
  materials: string[] XOR instanceIDs: uint32[],
  properties: CustomRenderPiplineMeshDrawPass properties
}
```

`properties` 的常用字段：

- `shader`: `{file, vertex, pixel?, defines?}`；
- `colorTargets`: `{name, format, slot, load?, clear?, blend?, writeMask?, size?, kind?, array_size?, mip_count?, view?}[]`；
- `depthTarget`: `{name, format, load?, clear?, stencilClear?, size?, view?}`；
- `state`: 深度、模板、裁剪；
- `resources`: 只读 Texture2D 或 raw buffer 输入；
- `samplers`: 显式采样器描述；
- `uniforms`: 字面值或 `source: "extent"` 的受限 uniform；
- `view_projection` 与 `view_projection_binding`: 成对出现。

MRT slot 必须从 0 连续；颜色和深度 attachment 必须是图上的输出或 inputOutput；`load` attachment 必须由上游提供尺寸和内容。

## Shader Pass 资源字段

`CustomRenderPiplineComputePass` 的 `resources` 可以是 `texture2D`、`texture2DArray`、`textureCube`、`raw_buffer`、`structured_buffer`。Compute 输出通过 `direction: "output"` 或 `inputOutput` 声明；Fullscreen 输出需要 `slot` 和 MRT write mask。所有 `binding`、format、size、stride/count 都应显式提供。

Schema 不是原生资源字段。consumer 必须把 Schema 展开为实际 resources/attachments 和 Shader `defines`，再创建 Pass。

## 观察 Atlas 的 layout

```json
{
  "width": 1024,
  "height": 512,
  "tiles": [{
    "name": "Pass.output",
    "x": 0, "y": 0, "width": 512, "height": 512,
    "view": {"mip": 0, "slice": 0},
    "display": {
      "mode": "color|float|uint|sint|bytes|uint32|sint32|float32|depth",
      "channel": 0,
      "scale": 1.0,
      "bias": 0.0,
      "minmax": [0.0, 1.0]
    }
  }]
}
```

纹理 `mode` 必须匹配格式类型；raw/structured buffer 必须明确标量模式；Depth 只能用 `depth` 模式。tile 不能重叠，且必须位于 Atlas 范围内。

## 失败安全

- Mesh 路由在任何图修改前完成选择器和实例合法性检查；创建中途失败会移除已经创建的节点。
- History 在一次执行中先验证全部资源，再分配和发布，避免半完成状态。
- Asset 在任何 GPU copy 前验证所有目标资源，禁止目标与不可变源别名。
- Shader 热重载失败时，是否保留 consumer 的上一版图属于外部脚本/应用策略；不要把这个行为假设成核心插件契约。
