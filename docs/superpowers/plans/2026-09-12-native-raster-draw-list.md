# Native Scene raster draw-list integration

**Goal:** Integrate selected-instance rasterization into Falcor Scene, using its existing indirect draw machinery, and expose it through stock GBufferRaster and the configurable native-material GBuffer.

**Authorization:** The user requested integrating this capability into Falcor itself instead of maintaining an independent design. Implement locally in the existing Falcor-m0 worktree; no commits/merges. Whole-graph rollback is explicitly deferred.

**Architecture:** Scene creates an owned RasterDrawList from instance IDs, validates IDs and triangle geometry, and batches selected draw records by winding and index format. Scene::rasterize consumes that list through the same submission code used by its default full-scene path. Lists retain their Scene and are rebuilt only when the draw-record layout/winding changes. Existing overloads retain full-scene behavior. Pass-local selection does not mutate global scene visibility.

Compared alternatives: keep private per-instance submission in each plugin (duplicates native work); filter only in Shader (does not remove draw submissions); integrate selected indirect lists into Scene (chosen). The native API handles instance IDs; named-material grouping is a small Scene query and custom tags remain application metadata resolved to IDs, without adding UE Schema or routing policy to Falcor core.

**Public API:** Scene::createRasterDrawList(instanceIDs); Scene::rasterize overloads taking RasterDrawList; Scene::getRasterInstanceIDs(optional materialNames). Python exposes list creation/inspection and material-to-instance selection. GBufferRaster and CustomRenderPiplineGBufferPass accept optional instanceIDs Properties: absent means all, [] means none. Both stock depth and GBuffer stages use the same selected list.

**Scope boundaries:** Raster triangle geometry follows the native indexed/non-indexed paths. No RT instance masking, new material/tag registry, global pass-routing scheduler or per-frame Python callback. Legacy UE MeshDraw still owns its per-draw custom uniforms/state; do not erase its unmatched behavior or claim it has all migrated.

**Tech stack:** Falcor C++17, D3D12 indirect draws, Slang, native Python bindings and Mogwai acceptance.

- [x] Back up affected files; add a GPU acceptance that fails on the absent Scene API before implementing it.
- [x] Extend Scene.h/.cpp with the reusable list and common indirect argument builder/submission; preserve instance IDs, validate duplicates/ranges/geometry, guard cross-scene use and update winding revisions.
- [x] Add native Python bindings and optional instanceIDs support to stock GBufferRaster and the configurable GBuffer. Use shared native drawing rather than a second plugin draw loop.
- [x] Add native core GPU tests for ID preservation, subset/empty/full behavior, invalid/cross-scene selection, cache reuse and both 16/32-bit and non-indexed draws.
- [x] Run full Release build and sequential native selection/GBuffer/material/framework/mesh regressions; run 469-test Python suite. Verify unchanged defaults, no per-frame rebuilding with stable selection, and exclusive Pass output with complementary ID sets.
- [x] Document concrete scripting and C++ usage, what is now native core integration, what legacy code remains, and validation limits; update project progress.

Validation commands are run serially for builds/GPU work, from E:/Project/falcor/Falcor-m0. Full build uses tools/.packman/cmake/bin/cmake.exe --build build/windows-vs2022 --config Release --parallel 4. Native unit tests use FalcorTest.exe --device-type d3d12 --test-case SceneRasterDrawList. Mogwai GPU scripts use --headless --enable-debug-layer --verbosity 2. Python unit tests use Anaconda 3.11 with workspace TEMP and without the embedded 3.10 numpy PYTHONPATH.
