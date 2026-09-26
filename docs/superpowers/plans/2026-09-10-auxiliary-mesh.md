# Independent auxiliary Mesh execution

Third framework gate. Reuse Falcor Scene raster modules, actual indexed scene geometry, existing MeshIdentity/filters, and RenderGraph allocation. No capture state or captured draw memberships.

Register `UELegacyMeshDrawPass` with an immutable shader.file/vertex/pixel/defines declaration. It owns a `filter` using existing MeshPolicy selectors, independent `colorTargets` (name/format/slot/load/clear/blend/writeMask), optional `depthTarget`, and depth/stencil/cull state. `load: load` is a reflected inputOutput dependency; `load: clear` is a new output initialized before drawing. A depth-only shader may omit pixel and color targets.

`UEMeshPass` shader bindings expose the native Scene viewProjection, material baseColor, modelID and instanceID. Arbitrary shader constants use the same typed uniform utility as compute/fullscreen executors. Every selected static triangle mesh is submitted through Falcor Scene's real 16/32-bit VAO and indexed draw range. Filtered meshes are excluded before submission. Primary Packed GBuffer remains implemented by UELegacyGBufferPass with its existing full-write/coverage contract; this auxiliary executor is for independent attachments.

- [x] RED authored GPU fixture: separate filtered color/depth target, then another Mesh Pass loads the target and blends; primary Packed buffers unchanged.
- [x] Implement resource reflection, filter reuse, Shader binding and draw submission.
- [x] Verify material/model/tag/instance filtering, real draw counts, depth-only path, own MRT/write masks and shader entry/defines.
- [x] Reject invalid states/attachments/aliases before commit and preserve active graph on failure.
- [x] Verify source deletion replay and Scene change invalidation; update evidence.

Evidence: `build/auxiliary-mesh-gpu/run-eb7ylwfd/result.json` for draws/blend/MRT/depth-only/stencil/filter/replay, `build/auxiliary-mesh-validation-gpu/run-twarkhnc/result.json` for all seven negative boundaries (including commit-time Scene change and re-seal downgrade), and final `build/mesh-inputs-gpu/run-89hitz1p/result.json` for sampled/raw inputs, feedback rejection and Packed Schema relocation. Draw code validates exact builtin ABI and lazy linked PSOs even for empty filters. New resources/samplers reuse shared reflection/uniform checks with compute/fullscreen, including rejection of sampler arrays. Immutable source files are still snapshotted through the declaration.

Dynamic/skinned/displaced geometry remains an explicit unsupported capability, matching the current primary mesh baseline. Temporal buffers and observation now have their own passing fixtures. Overall closure is tracked in `2026-09-10-framework-before-reproduction.md`.
