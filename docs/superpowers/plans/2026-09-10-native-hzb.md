# Cancelled: Native UE HZB implementation plan

**Cancelled by explicit user instruction on 2026-09-10. Do not execute the historical plan below.** HZB C++/Shader/graph/oracle and related mip observation changes were removed. No HZB pass remains registered/built. Follow `docs/research/ue-legacy-capture2-baseline.md`: only align passes affecting rendered results, not optimization structures. Backward.hpp memory fixes are independent and retained. Removal was verified by native build, 330 CPU tests, Observer and downsample/exposure GPU regressions.

> For agentic workers: Use the already approved framework-first design and executing-plans/TDD. Root owns C++ and serial build/GPU execution; the existing agent owns only the independent CPU HZB oracle. No staging, commits, UE edits or capture-fed rendering.

**Goal:** Build UE's non-Nanite compute HZB from native depth, and make every resulting mip independently observable.

**Architecture:** A declared `UELegacyHZBPass` handles the algorithm-specific four-mip batches and texture views through Falcor. Its shader is an immutable project input containing original UE HZB/reduction source spans with a small platform adapter. Schema still owns Packed fields; HZB consumes the declared native depth edge. Falcor owns allocation, graph execution and resource barriers. HZB is a prerequisite component for later SSR, not a claim that SSR is implemented.

**Tech Stack:** C++/Slang/D3D12, original UE custom5.8.1 source, Python/NumPy offline oracle.

## Scope and acceptance

User is replacing the old capture because its map was deleted. Do not reconstruct or wait for the old map. Framework and algorithms continue on authored fixtures; target-branch pairing and final-image comparisons move to the new saved map/capture.

- [x] Finish native regressions after the backward.hpp ASan fixes: fresh downsample processes, relative-size rejection, Mesh/Adapter exposure rejection.
- [ ] Add `test_output_catalog_mips.py`: catalog mip count, validated read selection, Atlas display mip selection, legacy single-mip behavior.
- [ ] Extend `output_catalog.py`, `observer.py`, `UELegacyObserver.{h,cpp}` and Python binding: optional read mip index and Atlas display mip, validate against allocation. Preserve depth/stencil raw planes for mip0; reject unsupported depth mips explicitly.
- [ ] Create `hzb.py`: graph fragment declaring native depth input, original immutable shader and nearest/farthest outputs. Options are closest output, R16/R32Float output and an authored `[x,y,width,height]` ViewRect; omission uses the complete upstream texture.
- [ ] Create `hzb_reference.py` and `test_hzb_reference.py`: independently reduce arrays, preserve UE POT base dimensions, UE mip count, Gather edge clamp, four-level batches and conservative closest half rounding.
- [ ] Vendor original `HZB.usf` body and required `ReductionCommon.ush` functions under `Codecs/HZB`, with byte/hash provenance in `ue_hzb_sources.json` and `test_hzb_sources.py`. Reuse original entry and reduction functions; adapter supplies only platform defines and parameter declarations.
- [ ] Create/register `UELegacyHZBPass.{h,cpp}`: reflect upstream dimensions and actual mip count, validate ViewRect/format, execute up to four mips per dispatch using original UE parameter formulas. Use conservative groupshared synchronization rather than relying on implicit wave lockstep.
- [ ] GPU acceptance `hzb_gpu_smoke.py`: actual Mesh PrePass depth, odd/even/one-pixel axes and viewport resize, inset ViewRect, cross-batch mip chains, full-array raw comparisons and per-mip Atlas. Malformed contracts reject without replacing the active graph.
- [ ] Run scoped CPU/source, build and affected observer/shader regressions. Record exact evidence and limitations; do not overwrite historical acceptance receipts.

## Source behavior to preserve

`SceneTextureReductions.cpp::BuildHZB` rounds the viewport to powers of two then halves it, and uses `max(log2(max(baseExtent)),1)` levels (not the ordinary full chain). The first batch reads original native depth, later batches read the preceding stored mip; closest and furthest are separate textures. `HZB.usf::Gather4`, `RoundUpF16`, `OutputMipLevel`, `HZBBuildCS` remain original source. First-batch upper-bound clamping is `(ViewRect.Max-0.5)/SourceExtent`; subsequent batches use `1`. Closest rounding is performed on each stored mip, while each batch's LDS reductions continue with unrounded values.

Explicitly outside this component: Nanite VisBuffer, Froxels/VSM, level0-unscaled mode, previous-frame HZB retention, SSR itself and new-capture equivalence. No default/placeholder texture substitutes for depth.
