# UE targetmap consumer reference

This reference is for tasks that adapt the previously restored UE targetmap/material/lighting pipeline. The files in the restored pipeline are consumer code; they are not required by the reusable core plugin and should not be copied into the core branch merely to make an example work.

## Mapping

| UE consumer responsibility | CustomRenderPipline boundary |
| --- | --- |
| Material parameter evaluation and shading model | consumer Shader/CPU code |
| Packed field names, bit layout, quantization and decode | consumer Schema/codec files |
| Scene triangle selection | `materials`/`instanceIDs` route selectors |
| MRT/depth allocation and raster execution | `CustomRenderPiplineGBufferPass` or `MeshDrawPass` |
| Lighting/shadow/sky equations | consumer Compute/Fullscreen/Mesh Passes |
| Raw output catalog, Atlas and readback | core observation bindings |
| Frame history storage | core History read/write pair |

## Skeleton for the restored UE graph

```python
def make_restored_ue_targetmap(scene, definition):
    loadPlugin("customrenderpipline")
    graph = RenderGraph("UE_TargetMap")
    graph.setScene(scene)

    gbuffer = createPass("CustomRenderPiplineGBufferPass", {"definition": definition})
    graph.addPass(gbuffer, "UEGBuffer")

    shading = createPass("CustomRenderPiplineFullscreenPass", {
        "shader": {"file": "ue_consumer/TargetMapShading.slang", "pixel": "psMain"},
        "resources": [
            {"name": "packed0", "direction": "input", "binding": "gPacked0", "format": "RGBA16Float"},
            {"name": "packed1", "direction": "input", "binding": "gPacked1", "format": "RGBA16Float"},
            {"name": "depth", "direction": "input", "binding": "gDepth", "format": "D32Float"},
            {"name": "shading", "direction": "output", "binding": "gShading", "format": "RGBA16Float", "slot": 0},
        ],
    })
    graph.addPass(shading, "UEShading")
    graph.addEdge("UEGBuffer.baseColorRoughness", "UEShading.packed0")
    graph.addEdge("UEGBuffer.normalMaterial", "UEShading.packed1")
    graph.addEdge("UEGBuffer.depth", "UEShading.depth")
    graph.markOutput("UEShading.shading")
    return graph
```

The real restored consumer may add CSM, SkyLight, temporal history, or comparison passes. Keep each stage as an ordinary graph node and keep the acceptance point explicit. For a shading-only acceptance, inspect `UEShading.shading` before Bloom, Tonemap, exposure, or other post-processing. For a raw GBuffer acceptance, inspect `UEGBuffer.*` and compare encoded fields before decoding.

## Migration checklist

- Replace old adapter/config entrypoints with explicit native resources and pass properties.
- Keep UE compatibility algorithms and reference data in the consumer tree.
- Route only the Mesh groups needed by each stage; do not submit every Mesh to every specialized pass accidentally.
- Rebuild material route receipts when Scene membership changes.
- Use `customRenderPiplineResetHistory()` when camera/scene/extent changes invalidate temporal state.
- Record output catalog and readback evidence with the graph revision and schema revision.
