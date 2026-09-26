---
name: customrenderpipline
description: Use when configuring, routing, inspecting, validating, or debugging Falcor CustomRenderPipline passes, MeshPasses, custom materials, GBuffer codecs, Asset/History resources, output atlases, raw readback, or shading comparisons. Also use when adapting a restored UE targetmap/material/lighting pipeline while keeping UE compatibility outside the reusable core.
compatibility: Requires a Falcor checkout with the customrenderpipline plugin; shader and Mesh executors require D3D12 and Shader Model 6.6.
---

# CustomRenderPipline Skill

Use this skill whenever a user asks to add, configure, route, inspect, validate, or debug a Falcor `CustomRenderPipline` pass, MeshPass, custom material, GBuffer, codec, asset/history resource, output atlas, raw readback, or shading comparison. Also use it when adapting a restored UE targetmap/material/lighting pipeline to Falcor while keeping UE compatibility code outside the reusable core. The primary result should be a concrete Python RenderGraph change, a diagnostic procedure, or a focused design/documentation update.

## Core principle

Treat `customrenderpipline` as a small native execution layer behind a scriptable RenderGraph. Keep the graph topology, resource edges, outputs, and consumer-specific material/codec semantics in the script or consumer repository. Do not reintroduce the retired UE ABI, old Config/snapshot contract, or RDC capture as a runtime dependency.

## Required workflow

1. Identify the requested stage: raster MeshPass, configurable GBuffer, Compute, Fullscreen, Asset, History, observation, or readback.
2. Check the relevant reference before editing:
   - `docs/customrenderpipline/README.md` for workflow and boundaries.
   - `docs/customrenderpipline/python-api.md` for field constraints.
   - `references/ue-targetmap-example.md` when the request mentions UE, targetmap, packed GBuffer, shading, or RDC alignment.
3. Prefer the existing Python entrypoint. Use `customRenderPiplineAddMeshPasses()` for multiple filtered raster passes, and ordinary `createPass()` plus `addPass()` for one pass.
4. Keep graph wiring explicit. The helper creates route nodes only; the caller must add edges and mark outputs.
5. Validate before running: D3D12/SM6.6 is required by shader and Mesh executors; resources must be explicit; attachments and formats must agree; outputs needed for inspection must be marked.
6. Verify the smallest useful artifact: route receipt, output catalog, Atlas, GPU error result, async readback task, or History status. Keep synchronous readback and Atlas generation out of the real-time path.
7. Report exact files, graph nodes, validation evidence, and any external UE dependencies. Do not claim full UE/RDC parity from a GBuffer or shading-only check.

## MeshPass routing pattern

```python
routes = [{
    "name": "opaque",
    "materials": ["OpaqueMaterial"],  # or use instanceIDs, never both
    "properties": {
        "shader": {"file": "opaque.slang", "vertex": "vsMain", "pixel": "psMain"},
        "colorTargets": [{"name": "gbuf", "format": "RGBA16Float", "slot": 0}],
        "depthTarget": {"name": "depth", "format": "D32Float"},
    },
}]
receipt = customRenderPiplineAddMeshPasses(graph, scene, routes)
```

Reject or explain duplicate route names, unknown materials, out-of-range/non-triangle IDs, and overlap between routes. Material selection is a Scene snapshot; rebuild the table after material membership changes. Do not confuse raster MeshPass with a hardware Mesh Shader.

## GBuffer and UE consumer pattern

A Schema belongs to the consumer. Expand its fields into explicit attachment declarations, Shader defines, and encode/decode code before constructing a native Pass. `CustomRenderPiplineGBufferPass` accepts a definition containing shader, attachments, optional defines/entry points, and depth format. For the restored UE targetmap example, keep MaterialProgram, packed field semantics, lighting, shadow, and comparison policy in the external UE consumer. The core plugin supplies Scene drawing, resource contracts, and graph execution.

Verification order for UE work:

1. Check attachment formats, slots, depth, and clear/load behavior.
2. Observe raw packed outputs before shading.
3. Decode fields in a separate consumer shader and compare representative pixels/fields.
4. Compare shading before Bloom/Tonemap/post-processing.
5. Only then investigate lighting, temporal history, or environment differences.

## Observation and readback

Mark outputs first, then call `customRenderPiplineOutputCatalog(graph)`. Use `customRenderPiplineRenderAtlas()` for a debug atlas with explicit texture view and display mode. Use `customRenderPiplineReadDepthStencilAsync()` for exact D32S8 planes and poll `task.ready`; synchronous `customRenderPiplineReadDepthStencil()` is for one-off diagnostics. For buffers, distinguish raw bytes from structured `stride/count` and choose a scalar display mode.

## History and failure behavior

Use a read/write History pair with the same key, connect the read before the write, mark `writer.status` as an output, and call `customRenderPiplineBindHistory(graph)` after graph edits. Reset on scene/extent/test-case changes. History preserves cross-frame resources; it is not old whole-graph transaction rollback. If Shader compilation fails, a consumer application may keep its previous graph, but this is not a native plugin guarantee.

## Common mistakes

- Adding a `schema` resource to a native Pass instead of expanding it in the consumer.
- Expecting the route helper to connect graph edges or mark outputs.
- Reusing an instance in multiple routes without intentionally creating ordinary MeshPass nodes.
- Comparing post-processed output when the requested acceptance point is shading.
- Calling synchronous readback or Atlas generation every frame.
- Treating a restored UE script or RDC as a core framework input.

## Output format

When implementing, report:

1. the changed script/pass and its graph edges;
2. the selected Mesh IDs or attachment/codec contract;
3. the validation command and result;
4. the exact observation/readback evidence;
5. remaining external consumer assumptions or limitations.
