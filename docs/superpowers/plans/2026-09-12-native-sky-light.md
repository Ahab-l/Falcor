# Native SkyLight resource and capture implementation plan

## User scope correction, 2026-09-12

The primary delivery is an extensible framework with script/declaration-owned
resources and passes. The specified UE scene and RDC are the concrete validation
case, not a requirement to reproduce every UE configuration. Keep framework
interfaces general and case parameters/branches in scene scripts and shaders.
Only implement paths, formats, materials and effects needed by that case.
Retain necessary correctness/regression checks; defer unrelated platforms,
configuration matrices and exhaustive coverage. Cloud/fog/GI/SSR scope depends
on evidence of contribution to the specified frame. RDC stays offline evidence.

Current case closure: resource views/structured buffers/observation and source
SkyLight capture pass; finish the actual lighting consumer and its required LUT,
then validate the combined scene and report remaining case-specific differences.

> **For agentic workers:** Use executing-plans for the coupled native changes and subagent-driven-development for independent source/API audits and reviews. No commits: the user's existing restriction overrides skill commit steps.

**Goal:** Render the source targetmap's realtime SkyLight through the native declared framework, reusing original UE capture, downsample, specular convolution and diffuse SH algorithms.

**Architecture:** Preserve real Cube textures and typed per-mip views. Graph declarations own allocation and dependencies; shaders own UE math. A separate source capture view/LUT at the SkyLight position drives the source sky material's reflection branch. The current main-view sky remains independent. Captured RDC resources and CPU readbacks never enter rendering.

**Tech stack:** Falcor D3D12/SM6.6, Slang, UE5 source excerpts, Python Schema/PassDefinition, native raw observation and GPU Atlas.

## Source decisions and alternatives

The exported SkyLight is movable, realtime, captured-scene, 128-square, at (0,0,600) cm. Its lower-hemisphere replacement is disabled. UE uses a separate SkyView LUT at CapturePosition with fixed forward=(1,0,0), right=(0,0,-1), reflection flags that suppress the sun disk and quantization noise, and emissive clamp 64512. These are source-derived values, not capture constants.

Real Cube SRV plus mip Texture2DArray UAV views preserve the original sampler and convolution behavior. Six independent 2D textures or a CPU atlas would require replacing cubemap sampling and would complicate seam behavior. Extend the existing native resource declarations instead of adding a renderer-specific upload/side graph. Preserve whole-resource allocation identity and validate each view's actual subresource range.

## Task 1: Native Cube/array/mip views

Files: `Source/RenderPasses/UELegacy/UELegacyShaderPass.cpp`, `UELegacyShaderBindings.h`, new `UELegacyTextureSubresources.h`; Falcor Texture/view/state code only where a native test proves a base defect. Test: new `scripts/ue_legacy/texture_views_smoke.py`.

- [x] Write an authored native producer that fills all six Cube faces at four mips with distinct face/mip values. A separate TextureCube consumer writes a 2D table; verify exact expected values without using readbacks as inputs. Include an SRV whose base mip is one, proving view-local LOD zero selects physical mip one.
- [x] Run the current native executable. It must reject `kind: textureCube` before implementing support. Save the actual failure.
- [x] Extend resources with `kind: texture2DArray | textureCube`, `array_size`, `mip_count`, and `view: {mip, mip_count, first_slice, slice_count}`. Existing 2D/raw declarations keep their defaults. The initial Cube contract is one Cube; array_size is the number of 2D layers for texture2DArray. SRV Cube views include all six faces. Writable views select one mip and a bounded slice range. All range validation precedes view creation, clearing and dispatch; no backend clamping is accepted as validation.
- [x] Match shader reflection dimensions/access/scalar type to the declared view. Allocate through ordinary RenderPassReflection.textureCube/texture2D(mipCount,arraySize); bind explicit SRV/UAV/RTV views. Dispatch extent and dynamic `source: extent` use the selected mip dimensions. Restrict fullscreen layered outputs to one explicitly selected face/layer; Mesh face views are handled in the capture task.
- [x] Verify native Cube subresource counts, all face view ranges and state tracking. Fix stock Cube count/view behavior only with direct failing/green native evidence; 2D/array behavior must remain valid.
- [x] Test a downsample-style read of mip N while writing mip N+1. Permit only proven disjoint view ranges; overlapping reads/writes reject before mutation. Test invalid mip, slice, Cube shape, shader dimension, layout and resource alias combinations, retaining active graph/output.
- [x] Build with pinned CMake, run the new native fixture and existing shader executor/alias regression. Keep GPU/build execution serial.

## Task 2: Source capture and original convolution

Files: native sky setup, primary/auxiliary Mesh view support, source excerpt exporter/tests, `Source/RenderPasses/UELegacy/Atmosphere` reflection shaders and `scripts/ue_legacy/sky_light.py`.

- [x] Extract exact original `DownsampleCS`, `FilterCS`, diffuse SH kernel and transitive helpers with byte/source hashes and notices; maintain source function boundaries and compile-time branches. Read their CPU parameter setup and record sample/mip conventions.
- [x] Build the source capture setup from the exported SkyLight component, not main-camera matrices. Reuse ComputeViewData and original SkyView integrator; force source reflection exposure/flags. Verify six face orientation and seam consistency against independent directions.
- [x] Render the original sky mesh/material for each source capture face through Mesh passes with the original reflection flags, depth and source visibility rules. Verify no disk/dither and exact clamp, while retaining main-view results.
- [ ] Apply original cubemap mip generation, specular convolution and diffuse SH reduction. Check constant/radiance-gradient/directional inputs and source-sun movement. Retain actual R11G11B10 storage/sampler limits separately from ideal math.
- [ ] Connect original environment-light consumers to Packed GBuffer with source intensity/color and AO/reflection contracts. Clouds/fog contribution stays an explicit pending source feature until implemented; do not call atmosphere-only output complete SkyLight or final alignment.

## Task 3: Observation, history and source integration

Files: `UELegacyObserver.cpp`, readback helper, Python output_catalog/observer, history resource declarations where required, source integration/report.

- [x] Extend output metadata and explicit read/display selection for Cube face and mip. Validate dimensions/ranges natively and in Python. GPU Atlas samples selected views without CPU round trips and leaves source resources unchanged.
- [x] Retain full-frame initial cube initialization before exposing lighting. Implement source-required temporal publication using existing history transactions; incomplete generations cannot become visible. Independent time-slicing performance parity is not required, but image-affecting history is.
- [ ] Integrate with the real source scene/automatic exposure and capture only offline comparison data. Verify camera-independent capture position, scene identity, regeneration/rejection, and unchanged main sky/opaque inputs where no environment consumer is enabled.
- [ ] Run full Python/native regressions, inspect the source Atlas, update the full goal's persistent plan/evidence. Keep source-planet wider numerical validation, clouds/fog/GI/SSR/postprocessing/final comparison and WebRTC explicitly open until independently achieved.

Commands (from Falcor-m0): `tools/.packman/cmake/bin/cmake.exe --build build/windows-vs2022 --config Release --target UELegacy --parallel 2`; `tools/.packman/python/python.exe build/run_sky_memory_validation.py scripts/ue_legacy/texture_views_smoke.py`; Python unittest discovery with `PYTHONPATH=build/m0-evidence/python`. No simultaneous native build/GPU/UE jobs and no termination of other applications.


## 2026-09-12 resource milestone

Task 1 passed: nine native Cube tests plus sixteen existing native regressions, six-face/four-mip sampling, all three declared texture kinds, 26 rejection/rollback controls and both existing shader executor smokes. Build, fixture directories and evidence limits are recorded in `docs/research/ue-legacy-texture-views.md`. Full Python suite: 412 passed. No commits; full renderer goal remains active.

Task 2 source extraction is complete only as provenance: 39 exact excerpts, nine generated outputs, seven dedicated CPU tests. `UESkyLightSource.json` explicitly leaves runtime support unestablished. Next work is the source capture view/material branch and original mipgen/filter execution; SH requires a proper `RWStructuredBuffer<float4>` binding plus unchanged source include adapters. Do not substitute a 2D atlas or CPU upload for Cube filtering.

Source survey correction: realtime capture cached-lighting pre-exposure defaults to exp2(-4)=1/16, compensated in consuming SkyLightColor. No override found in the requested project Config or Engine/Config/ConsoleVariables.ini; runtime CVar value remains unverified. All three source filtering paths bind Point sampling; SH reads the convolved cube at log2(width)-4 and emits eight packed float4. Preserve evidenced desktop FP32 half aliases. See `docs/research/ue-legacy-sky-light-source-inventory.md`.

### 2026-09-12 SkyLight case integration verified
Source capture -> original mipgen/specular filtering/SH -> DefaultLit environment lighting -> automatic exposure now passes in targetmap. Factory: targetmap_graph(...,sky_light=True,schema=active_schema). Full15frame evidence build/sky-light-capture/run-3c9_s9wa, launcher run-u9scm60s;20Mesh program counters remain1; automatic exposure1->1.256887->1.263709; final main camera restored for Atlas. Two memory defects fixed: repeated Mesh program creation, and direct frames bypassing Device::endFrame transient-heap rotation/reset. Final private bytes plateau9059045376(8.44GiB), frame10=frame14; peak same,47seconds. Two Cube128 mip chains only~1MiB. Graph replacement callback UAF fixed by explicit disconnect; initial RenderGraph viewport dimensions initialized0 before reflection.
Source GF GPU128x32RG16Unorm all8192codes AND prequantizationAB exactlymatch FP32 source (run-jlpx82su,run-jb566z8c). Independent consumer constant-env GPU passes(run-n9bqhad0/run-hjqjdqk4); source filter6cases pass(run-gwb27d_8/run-iz617j_a). FinalShader/Observer/history/Meshreuse regressions pass(run-2e1x2ubf,run-5htnrxdk,run-2ub9da4u,run-hvp4vo9s). Native4structured+10Cube/depth tests pass(sky-final-*-native.log);450Python tests pass(sky-light-final-python.log). Independent read-only review found no actionable defect. No build/GPU process left running; no commits/merges or UE/project/RDC writes.
Report: E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-native-sky-light.md. Broader completion remains framework + specified-case closure: assess actual frame contributions before extending cloud/fog/GI/SSR/post; do not demand universal UE compatibility, and do not claim final RDC image parity from this SkyLight milestone.
