# Reduce synchronous frame readbacks

> Continue the existing source framework with subagent-driven-development for the independent GPU exposure consumer change. Root alone owns native builds and GPU execution; preserve all dirty work and do not commit.

**Goal:** reduce remaining CPU/GPU synchronization at the same 1421x1035 source view, automatic exposure and original Shader precision, with byte-identical output.

**Architecture:** direct Shader consumption of native pre-exposure avoids repeated single-texel readback/upload. Required resident source identity checks retain full coverage but batch mesh ranges in one readback. Preserve same-frame error rejection and history publication until data dependencies prove a safe change; do not simply disable checks or import captured data.

- [x] Record current same-view timing and synchronization sites before native changes.
- [x] GPU exposure subtask: optional native texture consumed in Mesh/Decode/Lighting/Adapter Shaders, preserving scalar fallback, validity rejection and original formulas; meaningful GPU tests and scope-specific CPU contracts.
- [x] Root: batch resident mesh identity readbacks without altering the serialized identity or hiding between-frame GPU mutations; native tests.
- [x] Root: inspect error-readback/history waits after these changes, consolidate where existing semantics permit; avoid weakening failure/rollback guarantees.
- [x] Root: serial build/GPU verification, compare exact raw outputs, profile and measure current same view, review, document results and remaining costs.

Previous repair measured20.15ms/49.63FPS headless and35-36FPS visible. Keep these measurement contexts distinct. Source UE/project/RDC remain read-only; no CPU/readback image data is a rendering input.

Final receipt: build/targetmap-live/readback-final-comparison.json. This phase's
fresh same-view baseline18.47ms/54.15FPS -> final16.49ms/60.65FPS headless;
five raw outputs and serialized scene identity exactly match. 457Python,
16native identity + diagnostic snapshots,11exposure GPU comparisons/14rejections,
failed-after-writer temporal exposure/retry and existing history/scene exposure
regressions pass. Independent spec review passes; quality direct-symbol ABI
finding reproduced RED, fixed with external Shader opt-in and verified GREEN.
Report: docs/research/ue-legacy-frame-readback-performance.md. No visible FPS
remeasurement; full RDC parity remains open. All root GPU test processes exited.
