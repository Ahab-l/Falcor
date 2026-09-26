# Native UE metering downsample

Current update: concrete backward.hpp memory defects were reproduced with ASan and fixed; fresh ordinary native regressions pass. See `ue-legacy-windows-stacktrace-fix.md`. Current target is targetmap/2.rdc; event3133 confirms Raster/Bilinear half downsample. Padded-resource ViewRect integration remains work. Current scope is `ue-legacy-capture2-baseline.md`; historical crash investigations below predate the fix.

Implemented through generic Fullscreen/Compute PassDefinition nodes; no capture inputs. The existing automatic exposure fragment can now meter a separate reduced texture while applying exposure to the original full-resolution SceneColor.

## Original source and branch selection

UE custom5.8.1 `53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0`:

- `PostProcessing.cpp:195–212`: PreferCompute=0, QuarterResolutionDownsample=0, DownsampleQuality=0. The ordinary default is Raster, half resolution, low quality.
- `PostProcessDownsample.cpp:108–123`: ceil-divided half extent, with optional format override. `ScreenPass.inl:5–10` clamps each extent to at least one.
- `PostProcessing.cpp:773` chooses PF_FloatRGB; `D3D12RHI.cpp:157–158` maps it to R11G11B10_FLOAT.
- `PostProcessDownsample.usf` SampleInput, DownsampleCommon and MainPS are vendored as exact source spans in UEDownsample.ush/UEDownsamplePS.ush. The shared exposure manifest and source test verify bytes and original hashes.

The Raster wrapper executes original MainPS. The Compute wrapper adapts the full-viewport CPU UV transform and 8×8 entry interface. Both use the original bilinear clamp and low/high sample math. No manual output quantization is inserted. The local D3D12 device stores both RTV and UAV R11/G11/B10 output with toward-zero rounding, verified against raw words; a CPU nearest-even assumption failed and was corrected in the offline oracle, not in rendering.

## Framework contract improvement

Generic output `size` now accepts `{relative_to: inputPort|$viewport, divisor:[x,y]}`. Output omission explicitly means viewport. Input omission accepts upstream; inputOutput omission inherits upstream. Fixed input dimensions assert compatibility. MeshDraw loaded color/depth attachments now also reflect upstream dimensions. Falcor owns allocation, compile retries and execution ordering. Invalid/cyclic local size references reject, and execution independently checks relative dimensions.

The RED fixture exposed two actual bugs: loss of fixed dimensions across generic inputOutput and across loaded Mesh attachments. Both were fixed. A fixed consumer cannot silently alter a viewport producer. External native passes remain responsible for accurate output reflection.

## Verification

- `build/relative-size-gpu/run-4f2s0528/result.json`, launch `run-bma77805`: four viewport sizes (17×9,32×18,1×1,29×7), chained/asymmetric divisors, fixed 23×13 producer, generic inputOutput and real loaded Mesh path, eight invalid/conflicting declarations. Passed. Independent read-only review found no remaining issue within the documented contract.
- `build/downsample-gpu/run-y8colyst/result.json`, launch `run-yrvfy616`: six frames, Raster/Compute × low/high, odd/even/single-pixel extents, native packed output, histogram, adaptation and full-resolution exposure application. Full NPZ arrays retained. Eight later runs with a test-only fault recorder also passed on the final native binary; last result is `build/downsample-gpu/run-9on6j5ap/result.json` (launch `run-5fb7n23e`). Batch receipts are under `build/downsample-dump-g1opr6v6` and their launch directories.
- Source/math/CPU suite: `build/downsample-cpu.log`, 330 tests. Build: `build/relative-size-final-build.log`.
- Final affected regressions: Mesh/Adapter exposure `build/scene-exposure-gpu/run-evzmc5ee/result.json` (launch `run-wet0p693`), History `build/history-resources-gpu/run-uh01keqc/result.json` (`run-p9lnsagr`), generic Shader `build/shader-executor-gpu/run-m8cewh_5/result.json` (`run-bc2iy8ap`), auxiliary Mesh launch `run-5srodfo0`. Each launcher completed with exit0. These are new scoped regressions; the historical framework acceptance index is unchanged.

Float sampling is compared with an independent double-precision bilinear oracle. The tolerance bounds the two-axis error from D3D's minimum eight fractional interpolation bits plus float arithmetic, using the authored image's channel range. Raw packed words compare exactly against quantization of the independently observed float-format GPU output. Histogram/adaptation then compare against the decoded packed texture oracle. This distinguishes sampling, output format and exposure errors; no oracle output enters a shader.

## Historical stability investigation and current limits

One early relative-size run (`run-b5ivbyxu`) and a final downsample run (`run-7d7qqcv7`, at resize to17×9) ended with Windows AV 0xc0000005, KERNELBASE.dll+0x1e0a0. This extends the earlier exposure candidate-rejection incident. CDB repetition `build/relative-debug-hyfnz7ya` completed140 rejection paths without AV. A test-only in-process unhandled exception recorder (`build/crash-recorder`, `build/run_downsample_dump.py`) completed eight fresh-process downsample runs without a fault, so no dump was produced. Root cause is not established. These passing runs do not demonstrate a crash fix; stability review remains open.

Supported viewport is the complete input texture. Inset viewport transforms, upscaler-supplied reduced inputs, local exposure and final tone mapping remain subsequent work. This is authored component/integration evidence, not final image equality. User supplied targetmap/2.rdc, both now inventoried; RDC remains offline-only.
