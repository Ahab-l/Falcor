# Native resources, history and caller retirement implementation plan

> Use subagent-driven-development for isolated Asset work and read-only retirement inventory; root owns History/integration and serial builds/GPU. Independent spec then quality review. No commits or merges.

**Goal:** Retire old UE callers and migrate Asset/History without old Config/Scene/Schema/transaction prerequisites.
**Architecture:** Existing native RenderGraph/Texture/Buffer APIs, a thin Asset producer and a scoped paired History store. No replacement scheduler or legacy ABI emulation.
**Tech stack:** Falcor C++/Slang/Python, pinned CMake 3.24.1, MSVC, D3D12/SM6.6 headless.

## 1. Preserve and inventory
- [x] Verify byte-complete scoped backup and run existing 620-test baseline.
- [x] Produce path/reason dependency inventory for old runtime callers, old-only tests and retained native/algorithm artifacts.

## 2. Native Asset
- [x] Add native_asset_migration_smoke.py; direct construction must fail against the old binary before implementation.
- [x] Remove mandatory Config from CustomRenderPiplineAssetPass.cpp, keep ordinary assets Properties and native loading/copy validation.
- [x] Validate DDS mips/raw bytes, graph composition, consumer damage restoration, file reload by pass recreation and malformed inputs.

## 3. Native History
- [x] Add native_history_migration_smoke.py and Python loader tests before implementation; direct creation/assembly without old props is RED.
- [x] Replace HistoryPass.h/.cpp transaction-specific storage/render API with ordinary key/resources configuration, native paired read/write buffers, explicit reset and info.
- [x] Bind pairs only for history-bearing make_graph declarations; direct graph helper available; missing/duplicate/incompatible/pruned/unordered pairs rejected.
- [x] Verify per-execution known sequences, graph/key isolation, reset, scene/resize/rebind and failure boundary. No wait/readback in runtime history code.

## 4. Retirement integration
- [x] Create and hash-check retirement archive with original paths and reasons before exact-path removal; retain useful algorithms/reference data.
- [x] Remove old active entry/ABI-only discovery paths, resolve retained tests' shared helpers and public documentation; clean retired runtime registration/compatibility as needed without deleting native capabilities.
- [x] Record removed test IDs and replacement coverage explicitly; no test skips or compatibility re-enabling to hide failures.

## 5. Acceptance
- [x] Build with `tools/.packman/cmake/bin/cmake.exe --build build/windows-vs2022 --config Release --target Mogwai --parallel 4`.
- [x] Run retained Python discovery and serial new/native GPU regression matrix with actual result JSON validation.
- [x] Independent spec/quality review and fixes with regression evidence.
- [x] Deliver native resource/history example, usage and Todo update. Write verification.json, current source hashes/diff, archives, command/results and remaining constraints.
