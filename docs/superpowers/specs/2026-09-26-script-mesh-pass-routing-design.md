# Script MeshPass Routing

## Goal

Allow a Falcor script to declare multiple mesh routes. Each route creates one independent `CustomRenderPiplineMeshDrawPass`, selects a subset of raster triangle instances, and keeps its own shader, attachments, resources, samplers, uniforms, and fixed-function state.

## Public script API

The customrenderpipline plugin exposes:

```python
created = customRenderPiplineAddMeshPasses(graph, scene, routes)
```

Each route is an object with:

- `name`: unique RenderGraph node name.
- `materials`: optional list of native material names used to resolve triangle instance IDs.
- `instanceIDs`: optional explicit list of triangle instance IDs.
- `properties`: the existing `CustomRenderPiplineMeshDrawPass` properties, excluding `instanceIDs` when a selector is used.

Exactly one selector is required. `materials` and `instanceIDs` cannot both be supplied. The helper resolves material selectors using the current Scene snapshot, injects `instanceIDs` into the pass properties, and calls the normal RenderGraph `createPass()` path with type `CustomRenderPiplineMeshDrawPass`.

The return value is a Python list of records containing the created pass name, resolved instance count, and resolved instance IDs. This gives scripts a deterministic validation receipt without adding a new pass ABI.

## Validation and ownership

- The graph must have the same Scene object passed to the helper.
- Route names must be unique and must not already exist in the graph.
- Material names must exist and resolve only triangle raster instances.
- Explicit IDs must be in range and refer only to triangle geometry.
- Duplicate IDs within one route are removed deterministically.
- By default, an instance may occur in only one route. Any overlap is rejected with both route names and the duplicate IDs. This prevents accidental duplicate draws; callers that intentionally need overlap can still create ordinary MeshPass nodes directly.
- `properties` are validated by the existing MeshPass constructor. The helper does not reinterpret shader, target, or state fields.
- The helper does not add graph edges or mark outputs. Routes remain ordinary composable graph nodes and scripts decide their resource/execution dependencies.

Selectors are a snapshot at helper invocation. Scene transform updates continue to refresh existing `RasterDrawList` draw arguments; material reassignment or route membership changes require rebuilding the routes, which avoids hidden graph mutation during execution.

## Implementation boundaries

- Add a small reusable route helper in the customrenderpipline plugin and its Python binding.
- Reuse `Scene::getRasterInstanceIDs()` and `Scene::createRasterDrawList()` through the existing pass `instanceIDs` property.
- Do not introduce a central dispatcher or merge several routes into one C++ pass.
- Do not add UE-specific material or depth semantics.

## Test plan

1. A native/Python binding test creates two material routes and verifies two independent pass nodes and disjoint resolved IDs.
2. Explicit `instanceIDs` routes produce the same result as material routes.
3. Unknown materials, invalid/non-triangle IDs, duplicate pass names, missing selectors, both selectors, and route overlap fail before graph execution.
4. The existing single `CustomRenderPiplineMeshDrawPass` tests continue to pass.
5. A small graph execution fixture verifies that each route retains its own shader/attachment properties and only its selected draw list is submitted.

## Example

```python
routes = [
    {
        "name": "opaque",
        "materials": ["OpaqueMaterial"],
        "properties": {
            "shader": {"file": "Opaque.slang", "vertex": "vsMain", "pixel": "psMain"},
            "colorTargets": [{"name": "gbuf", "format": "RGBA16Float", "slot": 0}],
            "depthTarget": {"name": "depth", "format": "D32Float", "load": "load"},
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
```
