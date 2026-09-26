# Native histogram automatic exposure implementation plan

> For agentic workers: Continue the authorized framework-first work using executing-plans. Root owns native edits, builds and GPU runs, serially. No staging/commits, source UE edits or capture-fed rendering.

**Goal:** Run UE's ordinary PC atomic-histogram automatic exposure on native SceneColor, with native temporal state and variable frame time, using the declared framework.

**Architecture:** Extend History resource descriptors with optional fixed `size:[w,h]`. Add native frame timing to the complete-frame entry point and expose it through a declared frame-state resource. Reuse exact UE source slices for histogram binning/conversion, percentile integration and time adaptation; thin wrappers adapt resources. Authored settings are frozen, per-frame state is internal, and only complete successful frames publish histories.

**Tech Stack:** Falcor D3D12/C++/Slang, Python PassDefinition and NumPy validation; UE custom5.8.1 at `53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0`.

## 1. Fixed dimensions in generic History

Files: `Source/RenderPasses/UELegacy/UELegacyHistoryPass.cpp`, extended `scripts/ue_legacy/history_resources_smoke.py`.

- [x] RED GPU fixture mixes viewport RGBA32Float color and fixed 2x1 RGBA32Float exposure data in one pair. The shader accumulates different values in each. Resize must change color dimensions and keep exposure at 2x1 while invalidating both. Exercise repeats, cut, skipped frames, late failure/retry, and rejected pair-size/format declarations.
- [x] Parse optional `size` as exactly two positive uint32 components; omitted dimensions follow viewport. Store `{name,format,size}` in the retained resource contract; compare the entire contract before binding pairs. Reflect and allocate resolved dimensions individually. Preserve viewport identity for invalidation of every resource, including fixed resources.
- [x] Build UELegacy and rerun the authored fixture plus existing history regression. Record the actual raw arrays and receipts.

## 2. Native frame state

Files: `UELegacyHistoryPass.{h,cpp}`, registration, `scripts/ue_legacy/pipeline.py`, `test_pipeline_history.py`, native timing fixture.

- [x] Add finite nonnegative `delta_time` to `SchemaPipeline.render_frame`; omitted measures renderer clock progression. Supply time only through complete-frame execution. Same frame/epoch must retain identical timing, including failed-frame retry. No resealing or external graph binding is used to update frame state.
- [x] A declared producer exposes frame time/index/validity for shader consumers. New candidates have invalid history; preview has zero duration and cannot publish. Validate timing before mutating pair state; restore temporary execution scope on success/failure.
- [x] Verify variable duration, zero duration, repeated frames, invalid/overflow/nonfinite time and failure cleanup on CPU and GPU. Preserve old callers of the native entry point through an explicit documented default.

## 3. Original-source histogram and adaptation

Files: `scripts/ue_legacy/exposure.py`, `test_exposure.py`, source manifest and tests, `Source/RenderPasses/UELegacy/Codecs/Exposure/`, GPU fixture.

- [x] Derive authored parameters from UE CPU formulas: EV100/lens conversion, independent histogram and adaptation ranges, clamped percentiles, compensation and uniform luminance weights by default. Speed authoring domain is finite >=0.02 (UE Scene.h); transition distance must be finite positive. Store source line/span/hashes and settings provenance.
- [x] Vendor exact byte slices from Histogram.usf, PostProcessHistogramCommon.ush and EyeAdaptationCommon in PostProcessEyeAdaptation.usf. Wrap UE resource/View interfaces only. Atomic scatter is 128x1 R32Uint, 64 bins/Q13.19 with carry, followed by 16x2 RGBA32Float conversion; no average-only replacement. Wave optimization can be disabled without changing arithmetic.
- [x] Feed previous native 2x1 exposure history. Invalid history gives original initialization semantics and ForceTarget. Reuse log-percentile integration and linear/exponential adaptation unchanged. No curve/mask uses UE's neutral white resources; optional local exposure is not claimed implemented.
- [x] Compare raw scatter low/high words, histogram bins, average luminance, target and adapted exposure against an independent CPU oracle over black/uniform/bimodal/overflow images and changing frame times. Verify source bytes independently.

## 4. Native scene integration

- [x] Build the histogram/adaptation chain as a reusable PassDefinition fragment with explicit SceneColor input and dimensions. Derive next-frame PreExposure from successfully published native exposure and use current exposure in display conversion. Validate invariance when SceneColor and PreExposure are scaled together.
- [x] Compare authored scenes and intermediate buffers; this is algorithm validation, not proof of capture equivalence. Actual capture map is still unpaired. Record downsampling/input resolution explicitly, because UE may use half/quarter/eighth SceneColor depending on its post-process branch.
- [x] Update framework docs and evidence with supported permutations and remaining full reproduction work. Keep the original overall objective active.

Implementation evidence: docs/research/ue-legacy-automatic-exposure.md. All four slices have authored fixtures; final runtime review remains open for intermittent Windows AV in candidate rejection and viewport resize. CDB repetition completed without reproducing the crash; a test-only unhandled exception recorder also did not reproduce it. Follow-up half-resolution metering is implemented and documented in ue-legacy-metering-downsample.md. No full capture-equivalence claim is made.

- [ ] Diagnose the intermittent candidate-rejection crash before closing final review.
