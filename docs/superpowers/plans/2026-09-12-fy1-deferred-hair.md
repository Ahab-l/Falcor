# FY1 Deferred Hair Implementation Plan

> Use subagent-driven-development for the independent Hair lighting formula port
> and read-only evidence review. Root owns native builds and GPU/replay runs,
> serialized. User request authorizes implementation; no extra approval or commits.

**Goal:** Render the referenced FY1 hair with our native deferred framework through
matching EID14389 Shading, excluding postprocessing.

**Architecture:** Original case assets feed declared native geometry/material
passes; generated GBuffer/depth feed an independent Hair lighting pass. Capture
intermediates are assertions only. Reuse current Falcor-m0 Mesh/Schema executors.

**Tech stack:** Falcor D3D12/Slang, JSON graph and Python asset/case scripts;
original RenderDoc exports and shader traces for evidence.

- [x] Locate referenced task, actual RDC/events, prior implementation and current worktree.
- [ ] Inventory exact geometry, UV/frame, textures/mips, material outputs, camera/light,
      visibility dependencies and reference raw arrays; record evidence and missing terms.
- [ ] Port Hair R/TT/TRT/diffuse/extra-R formulas to native Shader helper with
      independent trace-probe regression. Delegate this bounded subtask.
- [ ] Add necessary generic asset source capability, verify byte-preserving
      texture/buffer import and immutable graph resource ownership if existing
      interfaces cannot supply original file assets.
- [ ] Build Hair case asset preparation, native scene and graph; verify indexed
      geometry and capture projection before material comparisons.
- [ ] Port alpha/material-axis/basecolor/roughness and Hair GBuffer Schema/codec,
      generate native depth and required scene occluders; quantify union coverage
      and raw GBuffer errors, resolve rather than hide mismatches.
- [ ] Connect independent deferred lighting, native volume/depth bounds and needed
      shadow/visibility terms; compare lobes then final Shading against original.
- [ ] Native viewer, changed-input/camera behavior, full region pixel/visual checks,
      regression tests, independent spec/quality review and completion audit.

Tests/outputs: build/fy1-hair. Production case code: scripts/ue_legacy and
Source/RenderPasses/UELegacy/Cases/HairFY1. Generic capability changes get focused
native/Python/GPU coverage; do not repeat unrelated suites.
Completion requires the whole image/architecture target, not merely a working
graph, a few matching probes or old Web3D's passing tests.
