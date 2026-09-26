# Native Pass Migration Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the isolated Python assembly task, then native Mesh policy integration; root implements shared C++ description/executor changes and owns serial builds/GPU runs. No concurrent implementation agents editing overlapping files. Independent review follows implementation.

**Goal:** Make described Compute/Fullscreen and selected native MeshDraw work without SchemaPipeline, old Config/material tables or UE depth/shader ABI.

**Architecture:** Reuse existing executors and RenderGraph. Extract neutral description/source context and an optional UEReference compatibility policy. Native Mesh submission uses existing Scene draw lists, not another selector.

**Tech Stack:** C++17/20 Falcor, Slang, Python unittest, D3D12 SM6.6, pinned CMake 3.24.1/MSVC.

## Task 1 — baseline and executable failing acceptance
- [x] Preserve current work in build/native-pass-migration/source-before.zip and verify hashes.
- [x] Run full Python baseline (605 expected) and add direct neutral GPU acceptance that currently fails on missing old Config.
- [x] Add structural CPU tests before changing main Python graph assembly.

## Task 2 — neutral Python graph assembly
Files: scripts/customrenderpipline/pipeline.py; extensions/ue_reference transaction integration; new test_native_pipeline.py; native described example.
- [x] Implement `make_graph(name, definition, *, base_directory=None)` for mapping/path input and native RenderGraph return; no snapshot/generate_schema/Config imports in the native call path.
- [x] Reuse structural/path parsing where independent; preserve origin of reusable pass files; do not accept schema macros as implicit UE compatibility.
- [x] Isolate old SchemaPipeline implementation with lazy backward compatibility for existing tests/entrypoints; run new and old CPU tests.

## Task 3 — neutral C++ context and ShaderPass
Files: CustomRenderPiplinePassDescription.h/.cpp; Extensions/UEReference/UEReferencePassCompatibility.h/.cpp; CustomRenderPiplineShaderPass.cpp; UEReferenceExtension.cpp; CMakeLists.txt.
- [x] Introduce a neutral description carrying public Properties/options, file-based shader loading, optional immutable extension sources and resource expansion. Extension provider recognizes explicit legacy inputs and runs existing Config validation; native inputs reject legacy-only macros and undeclared options.
- [x] Migrate ShaderPass to this context while retaining port parsing/reflection/resource views/dispatch checks/once cache. Direct Properties must construct normally. Native shader programs use file-based modules and no mandatory prefix.
- [x] Preserve getProperties/updatePass, validate legacy identity only when a compatibility context exists, and reject native exposure source without an explicit value.

## Task 4 — shared native MeshDraw submission
Files: CustomRenderPiplineMeshDrawPass.cpp; neutral compatibility policy interface and UEReference implementation; dedicated native mesh Shader/scene/GPU smoke.
- [x] Replace mandatory Config and old builtin handling with neutral description and optional compatibility policy. Move only old selection/builtin/draw behavior into UEReference; share targets/state/resource parsing and execution.
- [x] Native instanceIDs validate before clear, cached Scene draw list updates with scene assignment/topology/material state as required, submission uses Scene::rasterize. Native Shader has no mandatory UEMeshPass.
- [x] Preserve MRT clear/load/blend/masks, depth/stencil, viewport and typed input/sampler/uniform binding. Expose explicit optional view-projection binding and native clear=1/LessEqual defaults; legacy defaults unchanged in compatibility mode.

## Task 5 — validation, review and documentation
- [x] Build: `tools/.packman/cmake/bin/cmake.exe --build build/windows-vs2022 --config Release --target Mogwai --parallel 4`.
- [x] Run direct native GPU acceptance, selected Mesh acceptance and negative cases; run representative old shader_executor/auxiliary_mesh and new Schema/observer regressions serially.
- [x] Run full unittest discovery; independently review spec compliance then quality and fix important issues with tests.
- [x] Publish native described example and Chinese usage with concrete commands. Update P2/M2 and A1 partial scope, not wholesale Config/Adapter deletion or unrelated V5/RDC completion.
- [x] Record source diff hashes, exact commands/results and backup paths; do not claim inherited historical tests as fresh verification.

Final verification: build/native-pass-migration/verification.json; 620 CPU tests, 9 serial debug-layer GPU suites, Release Mogwai build and independent reviews passed. No commit/merge or old module deletion.
