# Native framework completion implementation plan

> Use subagent-driven-development for independently owned C2 cleanup and bounded V5 fixes; root owns async integration, all builds/GPU/UI and final evidence. Two-stage reviews before completion. No commits/merges.

**Goal:** Finish all four user-requested remaining areas without dropping functionality or narrowing acceptance.
**Architecture:** Native Falcor graph/Scene/resources, thin description and observer adapters; native fences/staging for asynchronous reads; existing native UI.
**Tech Stack:** C++/Slang/Python, pinned CMake 3.24.1, MSVC, RTX4090 D3D12 and supported Vulkan branches.

**Current gate (08:39):** cleanup/current strict CPU/GPU/headless performance/native wait-API measurements are complete within their documented bounds. Overall goal is NOT complete: real V5/ ErrorMeasure UI acceptance remains unverified because the latest live-fzedmw7h official capture sees the locked desktop. No input sent; process exited normally. Latest strict matrices: async-stage3-20260914-083244 and q1-r5-final-v5wxs5u3. Temporary native probe has been byte-exactly removed and formal DLL exports checked absent.

## 1. Baseline and current reachability
- [x] Archive 595 baseline files and verify every SHA-256; full 318-test Python baseline.
- [x] Read actual C2/V5/R4/Q1/R5/S4 source and separate uncompiled research from active consumers.
- [x] Store exact cleanup candidate/dependency manifest and use it as deletion checklist.

## 2. C2 source cleanup
- [x] Write structural regression asserting native pass declarations no longer expose compatibility factory or execution sealing; run before deletion for RED.
- [x] Remove dead policy branches and move private native helper aliases locally; preserve native external input/stride/view checks.
- [x] Archive exact obsolete source paths, verify, remove only listed leaves, update CMake/includes/tests. 88 source paths + 24 stale copied shaders; 18 algorithm counterparts unchanged.
- [x] Build Mogwai/FalcorTest and run native pass/mesh/asset/history/schema/observer/core acceptance. Final C2 review has no Critical/Important; c2-stage-verification.json records actual final scope.

## 3. V5 finish
- [x] Add failing file picker exception/cancel/Unicode and lifecycle tests to test_schema_observer_ui.py and native UI test support.
- [x] Fix PythonUI Unicode return and visible panel errors, run CPU green.
- [x] Build and run native widgets/panel/preview headless tests.
- [ ] Real Computer Use mouse/selection/Unicode picker/comparison/export/cancel/close-reopen validation; capture authoritative state and screenshots.

## 4. R4 native async primitive
- [x] Write native readiness/known-byte/invalid-range tests before implementation.
- [x] Add readiness/collect-only path to native texture task; staged buffer task and exact depth/stencil task with native fence completion.
- [x] Bind minimal native task methods to Python; implement bounded admission and resource lifetime ownership.
- [x] Validate one input -> GPU copy -> pending -> ready -> exact byte collection flow before expanding. Buffer/Texture primitive passed D3D12 and Vulkan; not yet the complete observer/service lifecycle.

## 5. R4 observer/service/UI/CLI integration
- [x] Separate Schema dispatch/staging from unpack/finite checking; freeze request identity and retain decoded data ownership.
- [x] Add bounded tickets for raw/inspect/compare/export with cancellation/timeout/resize/close tests.
- [x] Pump mailbox and panel without waiting on the rendering thread; preserve explicit synchronous compatibility calls.
- [x] External process CLI, GPU reference comparisons and native callback integration; idle and pending do not execute blocking readbacks. Current strict stage3 plus native wait-probe evidence.
- [ ] Actual mouse/picker/UI acceptance remains a separate mandatory gate; callback success does not close it.

## 6. Q1/R5/S4 matrix
- [x] Build finite Q1/R5/S4 case table and witnesses; resource-matrix-20260914-zh.md records exact scope.
- [x] Validate this finite matrix: current q1-r5-final-v5wxs5u3 has13 native +5 GPU suites +372 CPU with fresh native Logger files. R4 has its own strict matrix, not inferred from Q1 success.
- [x] Stress bounded queues, resource replacement/closure and measure submission/poll vs synchronous reference latency.512-task/full-budget evidence plus same-graph application-perf-2932i3td and native-wait-probe-lm33yqli; no desktop FPS claim.

## 7. Final audit
- [x] Independent reviews of completed code/measurements and current incomplete completion audit; substantive findings closed. Actual UI-specific review remains with the unmet UI gate.
- [x] Re-run complete build, retained CPU and serial native GPU matrices on restored current binaries;55native/11GPU/372CPU R4 and13native/5GPU/372CPU Q1. CPU suite overlaps.
- [ ] Complete real UI acceptance on final binaries.
- [ ] Publish archives, current source/ABI hashes, removed IDs, performance results, matrix and Chinese usage/Todo; keep goal incomplete for any missing requirement; external blockage follows the required repeated-blocker audit.

## Historical acceptance clarification (superseded by current gate above)

- Native ErrorMeasure/readback/ParallelReduction + owner pool pressure are now covered by stage3. Ordinary dynamic image contents do not invalidate all statistics; actual binding/config/Scene changes still do. Native fence tests cover queue-full without an expensive shader.
- C2, Asset/History retirement are complete; no old ABI/transaction restored. R4 is not complete solely because headless integration passes: V5 actual mouse and final whole-application measurement remain separate.
- V5 live-zyxcldjn could not activate Mogwai: Windows lock screen captured, no input sent, owned process stopped. Do not count callback integration as mouse acceptance.
- Q1/R5/S4 finite combination table is now accepted; existing tests must not be promoted to exhaustive coverage.

## Strict Logger repair checklist — updated to current results

- [x] Fix runner false-green: retain all new FalcorTest/Mogwai Logger files and scan `(Error) GFX Error`/VUID, not stdout alone; CPU discovery minimum 367.
- [x] Strict Q1/R5/S4 PASS: q1-r5-final-nafuwssh. New native reload counters 1,1,1,2,2,3,3; all native file logs checked.
- [x] Correct ParallelReduction float/sint/uint intermediate formats and both ping-pong buffer capacity transitions; actual two-backend tests pass.
- [x] Resolve default Vulkan Workgroup SPIR-V layout via explicit EmitSpirvViaGLSL; explicit direct path remains an unsupported experimental limitation, not silently certified.
- [x] Retain pending task fences with native deferred retirement; actual pending-drop/source recovery/last-owner tests pass. Exact-depth directly tested without presuming the Vulkan fence defect also affects its D3D12-only implementation.
- [x] Replace invalid future-host timeline fixtures with finite actual GPU workload and mandatory pending markers; strict two-backend verification passes.
- [x] Repeat strict R4/full integration after fixes. Current GREEN async-stage3-20260914-083244; original strict RED053232 and intermediate failures retained. Actual Logger checks remain mandatory.
- Latest real UI live-fzedmw7h saw locked desktop, zero inputs, normal stop confirmed. Headless gates are now done; full goal remains active for the unmet real-UI gate and final sign-off.
