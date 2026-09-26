# Frame readback optimization

2026-09-12. Follow-up to the interactive preview repair. The target remains the
same authored targetmap view at 1421x1035, with automatic exposure, four shadow
cascades, Cube128 capture/filter and unchanged Shader precision.

## Changes

- Mesh, Adapter, Decode and Lighting consume the native R32Float pre-exposure
  texture in their Shaders. The constant fallback and legacy/custom material
  ABI remain supported.
- Each native exposure consumer records a GPU copy of the texel at its own
  command position. Lighting similarly snapshots its error flags. A frame-local
  readback arena combines these records without submitting or waiting per Pass.
  Validation occurs after the existing end-of-frame completion wait and before
  history publication. Exposure errors are checked before downstream errors.
- Staging and temporal execution own the arena through exception cleanup.
  Standalone graph execution retains synchronous validation. Invalid values are
  rejected even with no covered pixels; later writes cannot erase diagnostics.
- Scene identity gathers every resident mesh vertex/index range, copies all of
  them into one ReadBack buffer and waits once. Byte coverage, SHA1 serialization,
  16-bit index offsets in 32-bit words, empty index ranges and between-frame
  GPU mutation detection remain unchanged. Material textures retain full
  subresource validation.

## Evidence

`build/targetmap-live/readback-final-comparison.json` contains the same-view
baseline and final optimized timing and exact comparisons. Both use 8 warmup frames and 48
measured frames without the profiler; the following profile is excluded.

| Same-view headless run | Mean | Median | p95 | FPS |
|---|---:|---:|---:|---:|
| Before this phase (`run-r7x5yfqd`) |18.47 ms|18.38 ms|19.39 ms|54.15|
| Initial optimized (`run-e6by8p6l`) |15.94 ms|15.92 ms|16.65 ms|62.75|
| Final, compatibility fix (`run-xtjya_zx`) |16.49 ms|16.43 ms|17.30 ms|60.65|

The final run reduces measured frame time by 10.7% (the initial optimized run
measured 13.7%). These are bounded local
headless measurements, not visible-window FPS. The previous phase's 35–36 FPS
visible observation is a separate measurement and has not been remeasured here.

Five outputs are byte-identical: `ExposureApply.exposedLinear`,
`SkyLightLighting.lightingColor`, `ExposureFrame.preExposure`,
`ExposureAdapt.exposure`, and `PreintegratedGF.preIntegratedGF`. The serialized
native scene identity also matches exactly. No captured resource or CPU oracle
is introduced into rendering.

Verification receipts:

- 457 Python tests on the final implementation: `build/targetmap-live/readback-python-final.log`.
- 16 native scene identity tests plus diagnostic snapshot test with D3D12 debug
  layer: `readback-identity.xml`, `readback-diagnostics.xml`. The extended
  multimesh vertex/index mutation test also passes (`readback-mesh-ranges.xml`).
- Final exposure consumer GPU: 11 exact comparison cases and 14 rejected
  declarations/values, including direct custom exposure, explicit native opt-in,
  declared scalar uniforms and frozen Shader wrappers:
  `build/frame-exposure-consumers/run-hybn8z4b`. Direct-symbol RED receipt:
  `build/targetmap-live/readback-exposure-direct-red.stderr.log`.
- Runtime invalid exposure after a history writer, preserved previous history,
  unchanged same-frame duration contract, successful retry and following frame:
  `build/frame-exposure-history/run-71l7lsp_`.
- Existing history and automatic scene exposure GPU regressions:
  `build/targetmap-live/readback-history.stdout.log` and
  `readback-scene-exposure.stdout.log`.

Independent spec review found no issues. Quality review identified direct
`gPreExposure` reads in custom material Shaders as a compatibility case. The new
regression reproduced an output mismatch before the fix. Existing external
material programs now keep their scalar ABI by default. SourceProcGrid and
SourceSky explicitly opt into the native texture ABI. The new GPU regression
passes after the fix, and quality re-review approves with no remaining findings.

For an external material to use the native texture ABI, define
`UE_MATERIAL_NATIVE_FRAME_EXPOSURE 1` before including the shared material/raster
wrapper, and resolve current exposure with `ueFramePreExposure(gPreExposure)`
(or its declared native exposure texture). A direct `gPreExposure` read in that
opted-in program is the scalar fallback. Declared `source: preExposure` uniforms
and old frozen wrappers retain the legacy CPU value path.

## Remaining synchronization

History publication still waits for the completed frame so GPU errors reject
before publication. Full resident scene identity remains fresh: the Python
history-info query and native execution each capture it, with one mesh batch
per capture. Scenes containing material/environment textures still read their
subresources. Legacy scalar material ABIs and standalone graph execution may
still read exposure synchronously. Observer readbacks are explicitly requested
diagnostics and are outside the live loop.

SkyLight capture/filter remains dynamic. This work does not establish final RDC
image parity or finish the remaining postprocessing. No commits or merges, and
no UE source, source project or RDC writes.
