# SkyLight native resource interfaces

These interfaces provide GPU resources and views for script-declared UE SkyLight work. They do not by themselves establish complete SkyLight or targetmap image parity. UE, the source project and RDC remain read-only; readbacks only support offline assertions.

## Structured buffers

`UELegacyComputePass` resources accept `kind: structured_buffer`, positive `stride` (a multiple of four), and positive `count`. Byte size is exactly stride × count, bounded by uint32. Buffer ports do not accept texture shape, texture views, clears or a separate byte count. A whole buffer may bind as an ordinary `StructuredBuffer<T>` input or `RWStructuredBuffer<T>` output/inputOutput. The declared stride must match Slang's element **stride**, which may differ from element size for padded structs. Overlapping writer aliases reject before mutation.

RenderPassReflection now represents structured buffers distinctly from raw buffers. ResourceCache creates actual structured allocations. External native graph Buffer reflection preserves stride and byte count. Declared immutable pipelines retain their existing external-input restrictions.

Example SH output: `{"name":"sh","binding":"OutIrradianceEnvMapSH","direction":"output","kind":"structured_buffer","stride":16,"count":8}`.

## Independent Mesh views

Mesh color/depth attachments reuse the allocation/view contract in `ue-legacy-texture-views.md`: `kind`, `array_size`, `mip_count`, and `view`. Each Mesh attachment selects exactly one face/layer at one mip. All selected attachment dimensions must match; viewport bounds use those selected dimensions. Same-allocation target aliases are accepted only for disjoint subresources. Allocation shape, format, ranges, extents, aliases, uniforms and linked state are validated before clearing.

`view_projection` is an optional immutable array of four rows of four finite float32 values. It multiplies Falcor world-space positions in meters and leaves the Scene camera intact. Omission preserves the existing native reversed perspective camera path.

`UELegacySkyViewSetupPass` accepts optional `sky.view` with `position_cm`, `forward_ue` and `right_ue`. It evaluates the unchanged source ComputeViewData with that position/basis and **main camera** pretranslation, as the original capture callers do. Output row 9 is the selected camera position in UE centimeters. Main-view setup retains its existing behavior.

## Observation

The catalog identifies texture2D, texture2DArray, textureCube, raw_buffer and structured_buffer, including allocation mip/array shape or structured stride/count. `PipelineObserver.read(name, mip=..., slice=...)` reads one physical face/layer and mip. Depth/stencil plane readback computes D3D12 plane indices using the entire allocation's mip/layer counts.

`observer.atlas(..., views={name:{"mip":2,"slice":5}})` selects one view per output. `observer.atlas_views([{"name":"Sky.cube","mip":0,"slice":face} for face in range(6)])` displays multiple distinct views of one output. Cube views are copied to transient 2D textures on the GPU for display. Structured buffers are copied to a raw GPU view for explicit scalar/byte interpretation. Neither route uploads a readback or writes source texels.

## Verified resource evidence (2026-09-12)

- Structured-buffer fixture: `build/structured-buffers/run-tox3v_zh`, launcher `run-avpjio00`. Exact producer → structured SRV, observer read and GPU Atlas; 29 rejection/rollback controls.
- Mesh fixture: `build/mesh-views/run-92zxp8en`, launcher `run-5jwcihwo`. Six faces, selected mip, unchanged other mip, independent matrix shift, Scene camera independence, selected mip depth/stencil read and six rejection controls. D3D12 stderr is clean.
- Explicit capture setup: launcher `run-g8ysyxlt`. Fixed capture position/basis and source main-camera pretranslation passed.
- Cube observer: launcher `run-gmbwzyq3`. All 24 face/mip readbacks and GPU Atlas exact. The later Python `atlas_views()` convenience method also passed GPU verification in launcher `run-pb5flw9v`.
- Native: four structured reflection/allocation/external tests (`build/sky-light-structured-all.*`), ten Cube/depth tests (`build/sky-light-cube-depth-native.*`), and sixteen existing texture/array/Blit/buffer/external regressions (`build/sky-light-regression-*`).

The Mesh D32S8 mip test exposed another base defect: GFX subresource barriers with a default aspect selected depth but omitted stencil. Direct native RED failed (`sky-depth-red.*`); setting explicit DepthStencil/Depth aspects passed (`sky-depth-aspect.*`). This preserves the backend's own plane handling instead of implementing independent native barrier indexing.

Changing RenderPassReflection changes the native plugin ABI. An initial UELegacy-only build left old DebugPasses unable to load; **all** installed plugins and Mogwai were rebuilt successfully (`build/sky-light-all-build.log`). This loader failure is not shader/GPU algorithm evidence.

Source capture, original filtering, packed SH, the source PreintegratedGF port and lighting consumption subsequently passed their numerical/integration acceptance. See `ue-legacy-native-sky-light.md` for the final source-case evidence and memory plateau; this resource milestone alone did not establish those results.

## Scene program lifetime and memory evidence

Direct graph staging/rendering does not run `Scene::update()`. A newly loaded
Scene therefore retains its initial `All` update flags. The primary and auxiliary
Mesh executors previously polled these flags and recreated their programs every
frame, including unchanged scenes. Each executor now accumulates Scene update
signal events and consumes them after handling its dependencies, following
Falcor's GBufferBase pattern. Scene replacement disconnects the old subscription.

The regression first failed with program counts 1, 2, 3, 4 on all three Mesh
passes (`build/mesh-program-reuse/run-5_33ro4j`, launcher `run-e4w9g5zo`). The
same fixture passed with counts remaining 1 and exactly unchanged pixels
(launcher `run-thwphcx9`). Build: `build/sky-program-reuse-green-build.log`.

The full source capture then passed at Cube128
(`build/sky-light-capture/run-ha80zo1_`, launcher `run-hdhpbhd8`): all six faces
covered; independent directions within 2.84e-5; source LUT/capture radiance
comparison passed; packed SH error at most 1.51e-9; fixed capture survives main
camera yaw/translation. Automatic pre-exposure advanced from 1 to 1.296858 and
1.304670. All 20 Mesh program counts remained 1.

Private process memory after staging was 8,700,092,416 bytes; frames 0/1/2 were
8,799,576,064 / 8,943,222,784 / 9,071,443,968 bytes. Peak was 9,097,633,792 bytes
over 133 seconds, without the memory-reserve stop. The earlier failing run had
already reached 15,375,863,808 bytes at frame 1 and was stopped near 17.5 GB.
This proves removal of the large per-frame recompilation growth, not a complete
long-running memory audit. Two Cube128 R11G11B10 full mip chains total about
1 MiB; process/compiler overhead dominates these measurements.

The later integrated 15-frame run exposed transient heaps still growing about
100 MiB/frame because direct execution bypassed SampleApp's Device::endFrame().
Both successful direct frame entry points now retire those heaps before waiting
and publishing history. Final source+consumer run `run-u9scm60s` plateaued at
9,059,045,376 private bytes; frame 10 and frame 14 have identical byte counts.
The new callback subscriptions explicitly disconnect on destruction as well:
`sigs::Connection` is a shared_ptr, not an automatic subscription guard.
