# Source targetmap interactive preview performance repair

2026-09-12. The previous scratch launcher ran the validation executor in
Mogwai's scene-update callback, then Mogwai executed the complete graph again.
It also capped the loop at 15 FPS and logged every draw. Multiple source passes
independently read back all resident mesh bytes for identity validation. These
costs came from our integration, rather than the size of the Cube128 resource.

## Changes

- Optional `graphExecutionCallback(graph,time)` runs after normal scene updates.
  True replaces default execution; false/None preserves it. Live history now
  advances once per displayed frame. Other selected graphs execute normally.
  Switching/removing graphs from the scene callback presents the actual graph.
- Native `renderHistoryFrame` shares one Scene identity snapshot among its
  validators. Every new execution reads fresh resident GPU data; public
  `sceneIdentity()` is always uncached. Source inputs must remain immutable
  during that one graph execution.
- Opt-in Compute `execution='once'` keeps privately generated GPU outputs and
  restores destinations by GPU copy. It accepts fixed whole single-mip 2D
  outputs and literal uniforms. Compile, resize, destination replacement and
  program changes invalidate the cache. PreintegratedGF opts in; its precise
  arithmetic and Shader are unchanged. SkyLight capture/filter remains dynamic.
- The viewer removes the artificial cap, per-frame observation readbacks and
  verbose draw logging.

## Measurement and validation

Same saved camera, 1421x1035, source materials, four shadow cascades, Cube128 and
automatic exposure. Each headless run warms 8 frames then measures 48 with the
profiler disabled. A subsequent 16-frame profile is excluded from FPS.

| Execution | Mean frame | FPS |
|---|---:|---:|
| Retired double execution, uncached |83.82 ms|11.93|
| Single execution before validation/cache repair |59.35 ms|16.85|
| Single execution, scoped validation and cached GF |20.15 ms|49.63|

The first baseline varied noticeably (median 93.27 ms); these are bounded local
measurements. Final median 20.07 ms, p95 23.16 ms. GF dispatch count is 1;
ExposureApply count 73 is one stage preview plus 72 displayed frames.

The reopened visible window separately reached 1200 frames; its last two
reported intervals were 34.90 and 36.48 FPS. This includes presentation and
interaction and must not be described as the headless 49.63 FPS result. The
process had exited by final inspection, with empty stderr; exit origin was not
recorded. Evidence: `build/targetmap-live/run-4lpacryx` and its launcher log
`20260912-031707.stdout.log`.

`build/targetmap-live/comparison.json` records timings and byte comparisons.
Final versus earlier single-execution uncached outputs are byte-identical for
exposed color, combined lighting, pre-exposure, exposure history and GF. No
readback or captured resource enters rendering.

- 455 Python tests pass (`build/targetmap-live/python-tests.log`).
- 15 native Scene identity tests pass, including deduplication, nesting,
  next-frame GPU vertex mutation and strict/dynamic camera checks
  (`identity-native.log`/`.xml`).
- Host callback smoke: 6 scripted, 3 fallback, 2 ordinary frames execute once;
  outputs equal and scene-callback switch/removal works. The old switch path
  first failed with the wrong output name; fixed run `run-mbwcx5g2` passes.
- Cache GPU `build/immutable-compute-cache/run-w2_i8gmj`: repeated dispatch 1,
  downstream overwrite restored, resize and changed uniform/Shader regenerate,
  default execution unchanged, both GF outputs match uncached bytes, and 18
  native invalid declarations reject.
- History (`run-uz29wtai`) and Shader (`run-fq17uivb`) regressions pass.
  Independent spec/quality reviews found two callback selection issues; both
  were corrected.

## Remaining costs and launch

The subsequent [frame readback optimization](ue-legacy-frame-readback-performance.md)
consolidates native exposure/error diagnostics and mesh identity transfers.
Synchronous history publication remains.
SkyLight capture/filter still runs every frame. Stock Falcor examples were not
benchmarked, and this is not a claim that every stall is eliminated. Final RDC
alignment and complete postprocessing remain unfinished.

Run `scripts/ue_legacy/run_targetmap_live.ps1` for the rebuilt visible viewer.
The old scratch entry forwards to `targetmap_live.py`. No UE source, project or
RDC writes, commits or merges occurred.
