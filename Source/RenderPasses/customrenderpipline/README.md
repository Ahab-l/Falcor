# customrenderpipline core

This plugin contains the reusable framework for custom material/G-buffer
layouts, composable RenderGraph passes, resource/history inputs, mesh draw
selection, output observation, and asynchronous readback.

The plugin deliberately does not contain a concrete lighting, atmosphere,
targetmap, or UE compatibility pipeline. Those are consumers of this API and
can be kept in a separate application repository.

Registered pass types:

- `CustomRenderPiplineGBufferPass`
- `CustomRenderPiplineComputePass`
- `CustomRenderPiplineFullscreenPass`
- `CustomRenderPiplineMeshDrawPass`
- `CustomRenderPiplineAssetPass`
- `CustomRenderPiplineHistoryReadPass`
- `CustomRenderPiplineHistoryWritePass`

The plugin also exposes Python bindings for graph history, output catalogs,
RTV probes, and depth/stencil readback. Layout and codec code is supplied by a
consumer shader, so this core plugin has no fixed UE material or depth ABI.

## Scripted mesh routing

Use `customRenderPiplineAddMeshPasses()` when different mesh groups need
different raster shaders, attachments, or fixed-function state. Each route is
expanded into a normal `CustomRenderPiplineMeshDrawPass`; the helper does not
create a private dispatcher or connect graph edges for you.

```python
routes = [
    {
        "name": "opaque",
        "materials": ["OpaqueMaterial"],
        "properties": {
            "shader": {"file": "Opaque.slang", "vertex": "vsMain", "pixel": "psMain"},
            "colorTargets": [{"name": "gbuf", "format": "RGBA16Float", "slot": 0}],
            "depthTarget": {"name": "depth", "format": "D32Float"},
        },
    },
    {
        "name": "hair",
        "materials": ["HairMaterial"],
        "properties": {
            "shader": {"file": "Hair.slang", "vertex": "vsMain", "pixel": "psMain"},
            "colorTargets": [{"name": "gbuf", "format": "RGBA16Float", "slot": 0, "load": "load"}],
            "depthTarget": {"name": "depth", "format": "D32Float", "load": "load"},
        },
    },
]

created = customRenderPiplineAddMeshPasses(graph, scene, routes)
graph.add_edge("opaque.gbuf", "lighting.opaqueGBuffer")
graph.add_edge("hair.gbuf", "lighting.hairGBuffer")
graph.mark_output("lighting.output")
```

`materials` resolves a snapshot of native material names to triangle instance
IDs. A route can instead use `instanceIDs` for an explicit selection. The
helper returns a Python list containing each route name, resolved count, and
resolved IDs. Duplicate IDs inside a route are removed; the same instance in
two routes is rejected so an accidental configuration cannot submit the mesh
twice. If scene material membership changes, rebuild the route table. Scene
transform changes continue to update the existing raster draw lists.

This is a raster MeshPass facility. It is separate from hardware Mesh Shader
pipelines and does not imply support for a mesh-shader pipeline.

For the full scripting guide, API field reference, validation workflow, and
the restored UE targetmap consumer example, see
[`docs/customrenderpipline/README.md`](../../../docs/customrenderpipline/README.md).
