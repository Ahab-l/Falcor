# Native UE histogram automatic exposure

Current update: targetmap/2.rdc replaces the old reference; actual Histogram/LocalExposure/Bloom/Tonemap events are in `ue-legacy-capture2-baseline.md`. Confirmed backward.hpp memory defects are fixed with seven ASan tests and fresh native regressions passing (`ue-legacy-windows-stacktrace-fix.md`). The following earlier crash observations are historical.

Latest verification: `build/scene-exposure-gpu/run-ajyg44t0/result.json` (launch `run-4e07ih37`) passed Python preflight and independent native rejection for both Mesh and Adapter. CDB repetition `build/exposure-debug-2f0k61q0/result.json` completed 18 normal frames and six native rejection paths, exit 0, without an AV. The intermittent fault remains unexplained; repetitions are not a demonstrated fix. CPU exposure batch: 325 tests passed.

Implemented through the declared framework, without RDC rendering inputs. The first GPU fixture authors its own changing image; the second renders actual indexed geometry through Mesh GBuffer and the explicit Falcor Adapter, followed by native Lighting and exposure.

## Sources and retained algorithm

Engine custom5.8.1 HEAD `53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0`. `scripts/ue_legacy/ue_exposure_sources.json` records exact input byte spans, original file hashes and output hashes for `Histogram.usf`, `PostProcessHistogramCommon.ush` and `PostProcessEyeAdaptation.usf`. `test_exposure_sources.py` compares installed excerpts against the read-only engine files. Only resource/View/entry interfaces are adapted. Original binning, carry, percentile integration, linear/exponential adaptation and `EyeAdaptationCommon` bodies remain unchanged.

- Default PC atomic path: 64 threads per row, 64 bins, fractional Q13.19 weights in LDS, emulated 64-bit global scatter using low/high words in a 128x1 R32Uint texture.
- Convert produces 16x2 RGBA32Float: normalized histogram with UE's 0.5 compatibility factor in row 0; original previous exposure vector in row 1.
- Percentile clipping computes a weighted mean in log luminance. Equal percentiles and empty histograms retain UE's special cases.
- Native 2x1 exposure history stores `(smoothedScale,targetScale,averageLuminance,compensation)` and `(averageLocalExposure,0,0,0)`. With local exposure disabled the latter is `(1,0,0,0)`. Invalid history adapts zero-initialized framework storage to UE initialization and ForceTarget.
- Authored settings derive EV100/lens conversions, independent histogram and white-point limits, percentiles, compensation and transition slopes from `PostProcessEyeAdaptation.cpp:593–774`. The 1/60 constant shapes the transition slope only; actual integration uses local frame duration.
- Default luminance weights are uniform, speed up/down 3/1, lens attenuation .78, extended limits [-10,20], bias 1 EV. Tests explicitly author bias 0. Working-space luminance method requires authored coefficients, rather than approximating an unspecified color space. Speed domain >=.02 follows UE's authoring metadata.

## Framework improvements exercised

History supports fixed-size resources mixed with viewport-size resources. `frameTime` is a native 1x1 R32Float output; `SchemaPipeline.render_frame(...,delta_time=...)` accepts explicit simulation time, or measures clock progression. Paused/repeated/failed frames and rewinds have defined behavior. Mapped compute group axes follow resource size across resize. `max_size` rejects source dimensions beyond algorithm limits. For this Q13.19 implementation width must be <=8191 to avoid per-row LDS overflow.

Mesh GBuffer, Adapter, Decode and Lighting can receive the same declared `ueFramePreExposure`. A synchronous native readback populates their existing constant buffers; the next-frame value comes from successfully published native exposure. Native sealing rejects mismatched pre-exposure bindings on shared Packed resources. No immutable graph property is modified to change exposure, and no external graph input is used.

## Evidence and limits

- `build/exposure-gpu/run-uoh22qe0/result.json`: 11 frames covering black, uniform, bimodal, colored, upper-bin saturation, bright/dark changes, cut, repeat and zero duration. Full scatter/histogram/exposure arrays and CPU expectations are archived as NPZ. Power-of-two/black/saturation cases compare integer words exactly, including global carry. Other scatter comparisons allow at most two Q19 units per sample for CPU/GPU log/FMA differences. Histogram per-bin tolerance is 2e-6. Maximum exposure relative error is 3.07497e-6.
- `build/scene-exposure-gpu/run-9swxmxtk/result.json`: three frames each of Mesh and Adapter with actual DefaultLit geometry, authored directional Lighting, native pre-exposure feedback and per-frame oracle checks. Removing the Lighting exposure edge rejects; the active graph survives.
- `build/group-dispatch-gpu/run-rom4ifvc/result.json`: mapped group count, resize, invalid axes/counts, and exceeding then restoring a declared max_size.
- `build/history-resources-gpu/run-026rcqze/result.json`: mixed fixed/viewport history, variable duration, reset/cut/resize/gaps, late failure/retry and native invalid-time rejection.
- Native build: `build/exposure-final-build.log`. CPU suite: `build/exposure-all-cpu.log` (current count is in that log).

One scene integration run (`run-l8vnodb6`) exited with Windows access violation during the second invalid-candidate path after both normal scene sequences passed. An instrumented fresh-cache rerun (`run-0lgvgwj0`) passed both rejection paths. Investigation under a debugger is retained separately; do not claim this intermittent fault is explained merely from a passing rerun.

Current support is ordinary Histogram at authored input resolution, optional native half-resolution metering, neutral meter/curve textures, neutral tint/vignette/local exposure, and previous-successful-frame PreExposure. UE may have asynchronous exposure readback latency; the actual target branch still requires pairing. `ExposureApply.exposedLinear` is global exposure application only; UE film/tonemap, bloom and output encoding are not implemented by that shader. Asset curves, custom meter masks and local exposure are not claimed implemented.

The new source map targetmap and 2.rdc have been inventoried. Native sky/shadows, GI/AO/SSR, complete post-processing and WebRTC remain unfinished. Independent optimization alignment is excluded by the latest user instruction; no main-image TSR is present in the new capture. This exposure evidence does not establish final image equality.

## Metering downsample follow-up

Read-only source follow-up locates default PreferCompute=0, QuarterResolutionDownsample=0 and DownsampleQuality=0 in `PostProcessing.cpp:195–212`. Native Raster/Compute low/high half-resolution R11G11B10Float metering is now implemented with original source functions and a generic relative-size contract. Scatter/Convert can consume the reduced texture while Apply keeps full SceneColor dimensions. Full-viewport validation and open stability issues are detailed in `ue-legacy-metering-downsample.md`; this does not yet establish the captured frame's actual branch or final image equality.
