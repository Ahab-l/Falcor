# customrenderpipline: implementation and use

> **2026-09-14 主线已更新：下文旧 SchemaPipeline/事务/UE 案例章节是历史设计，不是当前使用步骤。旧入口已退役，不要执行其中 minimal/targetmap 或旧 smoke 命令。** 当前使用 [描述式 Pass](customrenderpipline-native-pass-migration-zh.md)、[Asset/History](customrenderpipline-native-resources-history-zh.md)、[新 Schema](customrenderpipline-gbuffer-schema-zh.md) 和 [V4/CLI](customrenderpipline-schema-observer-zh.md)。[最新重新审计](customrenderpipline-modification-reaudit-20260914-zh.md) 与 [Todo](customrenderpipline-todo-zh.md) 为当前状态；历史正文保留用于来源对照。

## 历史正文（不再作为当前 API 文档）

The framework is built on Falcor Scene, RenderPassReflection, RenderGraph, Program/Slang and GPU execution. The framework owns custom material/GBuffer contracts, described pass composition, immutable graph transactions, temporal publication, output observation and numeric comparison. Specific rendering algorithms belong to Extensions/UEReference or authored pass descriptions. Framework fixtures use independently authored scenes. They do not establish UE capture equivalence.

For the current file inventory, Chinese usage examples, launch command and FY1 status, see [Falcor 改动与使用说明](customrenderpipline-usage-zh.md). The September 12 resource and readback updates below supersede earlier capability limits.

The [native Falcor audit](customrenderpipline-native-falcor-audit-zh.md) records reuse decisions and current integration limits. Ordinary output viewing uses Mogwai; ordinary readback uses native `Texture.to_numpy()` / `Buffer.to_numpy()`; standard image comparison uses native ErrorMeasurePass. The observer retains metadata/view validation, explicit raw-array tolerances, specialized atlas display and exact D32S8 plane readback.

## Responsibilities

| Layer | Owns | Implementation |
|---|---|---|
| Schema | Packed attachment layout, fields/bit ranges, model IDs, resource requirements and generated dispatch | `generate_schema.py`, Schema JSON and generated definitions |
| Material/Codec | Material evaluation, encoding/decoding and model shading mathematics | Slang material modules and Shader codecs |
| PassDefinition | Nodes, source entries/defines, resources, properties, outputs and data/execution dependencies | `pass_definition.py`, `pipeline.py` |
| Falcor | Allocation, resource states, DAG compilation, Scene VAOs, shader compilation, GPU commands | Existing native infrastructure |
| Transaction | Immutable files, topology/properties, Scene identity, whole-candidate validation and commit/rollback | `pipeline_snapshot.py`, Config, GraphContract, SchemaPipeline |
| Temporal | Previous successful frame, generation/epoch/extent/continuity and isolated publication | `history_state.py`, HistoryRead/Write passes |
| Observation | Native output metadata, raw bytes, selectable GPU atlas | OutputCatalog, PipelineObserver, CustomRenderPiplineObserver |

Schema describes what each field means and where it is stored. It does not encode shader mathematics in JSON, select mesh geometry, or replace Falcor's scheduler.

## Declaring passes

A version 1 PassDefinition contains `nodes`, `edges`, and `outputs`. Node names are arbitrary identifiers. A node has `name`, `type`, `properties`; project file properties must also appear in `file_inputs` such as `["shader.file"]`. Shader local includes are recursively snapshotted. File paths resolve relative to the declaration. The resulting graph executes frozen source bytes even after the originals are deleted.

Edges such as `["Producer.color", "Consumer.input"]` carry resources. Bare `["Producer", "Consumer"]` edges order execution. `$packed` expands the Schema's physical attachments; `$field:baseColor` selects the attachment holding a field. Cycles, duplicate destinations, unknown fields and conflicting primary ownership reject before commit. Actual Falcor reflection validates physical resource compatibility.

Ordinary Falcor plugins use `inherit_pipeline: false`; they receive their declared properties. Their `getProperties()` must describe stable executable defaults. Known inferred settings should be explicitly declared. Custom algorithms can implement new native RenderPass classes and use the same declaration/transaction mechanism.

`pipeline.SchemaPipeline` requires an explicit graph declaration by default. `make_graph()` and `make_adapter_graph()` live in `extensions.ue_reference.pipeline` as reference-example convenience translations. Reusable node descriptions are loaded with `description: "passes/Effect.json"`; their files and property overrides are resolved before immutable snapshot publication. Packed producers remain `CustomRenderPiplineGBufferPass`; native Falcor GBuffer uses an explicit `CustomRenderPiplineGBufferAdapterPass`. Primary producers require full Schema field writes and unique ownership. An auxiliary Mesh pass does not become a primary producer merely by using similar attachments.

Without MeshPolicy, primary producers sharing any Packed attachment or coverage allocation require disjoint `includeMaterials` sets. A missing filter selects every material; `[]` selects none. The Adapter is unfiltered. Physical port edges determine sharing, including fanout and transitive inputOutput connections; independent allocations can render the same material. With MeshPolicy, distinct routes may share the Packed chain only under the same policy and retained material routing inputs. Both Python declarations and native graph sealing enforce ownership before execution.

## Reusable execution

`CustomRenderPiplineComputePass` declares a compute source/entry/defines, named texture2D, texture2DArray, textureCube or raw-buffer resources, typed constants, samplers, and either a texture extent or explicit thread counts. Texture allocation and selected mip/layer views are distinct; disjoint views can share an upstream allocation. `CustomRenderPiplineFullscreenPass` declares an optional vertex entry and a pixel entry, sampled inputs and its own contiguous MRT outputs, with disabled/additive/alpha blending. Layered fullscreen outputs select one face/layer. Its default vertex ABI exports only SV_Position; custom varyings require a matching explicit vertex entry. See `ue-legacy-texture-views.md` for the exact view contract, core Cube corrections and native validation evidence.

Constants support float/int/uint scalar/vector and bool scalar, with `value` or a generated `extent`/`preExposure` source. Exact types and ranges are checked; resource reflection checks dimensions, kind, access and scalar return type. Integer UAV clears retain bits. Integer RTV initialization uses a shader. Actual allocations are checked for incompatible read/write aliases before binding or clearing.

Texture dimensions belong to the producer. Generic Compute/Fullscreen `output` with omitted `size` explicitly uses viewport dimensions; `input` with omitted size accepts upstream dimensions; `inputOutput` inherits them. A fixed `size:[w,h]` on an input is a compatibility assertion, not permission to resize the producer. An output can use `size:{"relative_to":"inputPort","divisor":[2,2]}` for component-wise ceil division of an input texture's dimensions, or `relative_to:"$viewport"`. Divisors are positive uint32s; local references must name read-only textures. Chains resolve through Falcor reflection/compile retries before allocation, with actual-size validation before execution. MeshDraw loaded color/depth attachments propagate their upstream extent; cleared attachments use viewport dimensions. External native passes must accurately reflect their output size (or use an explicit Adapter); this layer does not infer hidden native alias relationships.

Compute group dispatch can map actual resource dimensions: `{"groups":{"extent":"sceneColor","axes":["height",1,1]}}` emits one group per input row. Each axis is `width`, `height` or a positive literal group count. The executor multiplies by the compiled kernel's group size and validates native limits. The uniform `extent` source still contains the named texture's dimensions. Texture resources may specify `max_size:[w,h]`; exceeding the bound rejects before dispatch/clear. The UE Q13.19 per-row histogram uses this contract to require width <=8191.

`CustomRenderPiplineMeshDrawPass` owns:

- A shader file, vertex/pixel entries, defines and typed uniforms.
- The existing MeshPolicy selectors: materials, material/model/program IDs/names, meshes, instances, tags and masks. Selection happens before submission.
- `resources` for sampled texture2D/raw-buffer inputs and `samplers`, including `{"schema":"$packed","direction":"input"}`. It shares binding/type checks with shader executors.
- `colorTargets` containing name, format, contiguous slot, `load` (`clear`/`load`), clear value, blend mode and four boolean write-mask lanes.
- Optional `depthTarget` and independent depth/stencil/cull state. Loaded attachments are reflected inputOutput dependencies. A depth-only pass omits the pixel entry and colors.

Shader builtins are declared in `cbuffer UEMeshPass`: `float4x4 viewProjection` is required; used material `float3 baseColor`, `uint modelID` and `uint instanceID` are optional. Arrays/wrong types and binding overrides reject. Custom constants belong to another cbuffer. Actual Scene 16/32-bit VAOs and indexed ranges are used, including geometry instance IDs and winding. Even an empty selection validates the backend pipeline. Zero-index validation submissions produce no fragments and are not counted as selected Mesh draws.

Current geometry baseline is static indexed triangles. Dynamic/skinned/displaced geometry explicitly rejects. Compute resources support `kind: "structured_buffer"` with explicit `stride` and `count`, validated against Slang's element stride. MeshDraw additionally supports an immutable `view_projection` matrix. Indirect dispatch and arbitrary matrix uniforms remain outside the generic contract; algorithms needing these can provide a native pass without changing Schema or graph assembly. See `ue-legacy-sky-light-resources.md` for the current structured/Cube interfaces.

## Staging and identity

```python
pipeline = SchemaPipeline(m, output_directory, graph_kind="declared")
pipeline.stage(schema, {
    "sceneDefinition": authored_scene_json,
    "graphDefinitionPath": passes_json,
})
pipeline.commit()
```

Staging executes a candidate offscreen and waits for GPU completion. Only a validated candidate can replace the active graph. Missing files, shader errors, invalid PSOs, mismatched contracts and topology/property changes reject. The old graph and its textures survive failed candidates. Sealed graphs validate before every execute and commit; re-sealing rechecks immutable inputs and cannot drop a prior Scene constraint by accepting modified files.

Falcor's external `RenderGraph::setInput()` bindings are outside this framework's declaration/snapshot contract and are rejected at seal and on subsequent validation. This prevents undeclared uploads and resource aliases from bypassing ownership or transactions. Use declared producer passes and registered immutable file inputs. External-input declarations would need their own identity and lifecycle contract before becoming supported.

An optional native `scene_identity` binds a strict static Scene reference. It includes actual Scene state/resources; a changed Scene must be rebound. Ordinary unbound scenes retain live camera/material behavior. Strict identities are checked before commit as well as execution. This is not a sandbox for malicious plugins or a provenance detector for arbitrarily relabelled external assets.

## Real temporal resources

Declare one `CustomRenderPiplineHistoryReadPass` and one `CustomRenderPiplineHistoryWritePass` per `key`, with matching `resources: [{"name":"color","format":"RGBA32Float"}]`. Add optional `size:[2,1]` for a fixed-size resource; omission follows the viewport. One pair can mix both forms, and resize invalidates all of them. Reader/writer contracts include size as well as name/format. Reader ports expose previous textures; writer ports consume current textures. An actual graph path must order reader before writer. Mark the writer's `status` output to retain execution.

Read `status` is a 1×1 RGBA32Uint texture: validity, epoch, frame index, role. The read role is 0, write role 1. Algorithms decide their invalid-history fallback; invalid previous textures are initialized to zero. These zeros are invalid storage, not substituted UE temporal results.

Two private textures per history field keep current writes separate from previous reads. Use `pipeline.render_frame(frame_index, reset=False, camera_cut=False, delta_time=None)` for complete-frame execution. A finite nonnegative explicit duration is local simulation time, canonicalized to float32. Omission measures advancement of Falcor's clock since commit/previous new frame; a paused clock produces zero and manual steps advance it. Clock rewind invalidates history. Repeating/retrying a frame retains its duration; changing it requires a new epoch. History exposes `frameTime`, a 1x1 R32Float resource, zero outside complete-frame execution. Native callers may pass the fifth duration argument to `customRenderPiplineRenderHistoryFrame`; its backward-compatible omitted default is zero. CPU TemporalEpoch is the sole epoch/validity controller; native code independently verifies that a claimed valid frame was actually published. A frame publishes only after every pass executes successfully and GPU work completes. Preview/candidate execution does not publish.

After commit, frame 0 cannot use history. Once frame 0 publishes, frame 1 can. Repeating frame 1 reads the same previous slot and publishes once. Resize, reset, camera cut, discontinuity or a new committed graph invalidates history. A late failed pass cannot publish a writer that executed earlier. History storage supports single-mip/layer sampled/UAV texture2D formats; depth history uses a float representation. There is no external history upload interface.

## Global automatic exposure consumer

`exposure_graph.histogram_exposure_fragment("Lighting.lightingColor", settings={"bias_ev":0}, source_format="RGBA16Float")` returns ordinary PassDefinition nodes/edges/outputs. It uses original UE atomic Histogram and global EyeAdaptation functions, native 2x1 history, a native PreExposure producer, and a linear exposure application output. Apply follows the full SceneColor dimensions. Optional `metering_source="Half.color", metering_format="R11G11B10Float"` supplies a reduced native input to Scatter/Convert only. Use `downsample.downsample_fragment("Lighting.lightingColor",source_format="RGBA16Float")` to create that producer. It defaults to UE's full-viewport Raster, low quality, half-resolution R11G11B10Float branch; Compute and high quality are also supported. Film/tonemap, local exposure, bloom and custom curve/meter assets remain unimplemented here. See `ue-legacy-metering-downsample.md` for source and GPU evidence.

Connect `ExposureFrame.preExposure` to `ueFramePreExposure` on Mesh GBuffer (or Adapter), Decode and Lighting. Built-in consumers read these optional 1x1 R32Float textures directly in their Shaders; complete-frame execution batches validation snapshots and checks them after the frame completion wait, before history publication. Without an edge, a pass keeps its authored constant. Legacy external material programs retain their scalar ABI and may still read synchronously; native texture use is an explicit opt-in. CPU normalization and independent native sealing require built-in producers/consumers sharing a Packed allocation to use the same exposure resource or same constant. The read-only exposure input does not claim Packed write ownership. See `ue-legacy-frame-readback-performance.md` for compatibility and remaining waits.

Full source provenance, raw validation and capability limits are recorded in `docs/research/ue-legacy-automatic-exposure.md`. This is an authored algorithm baseline, not capture equivalence.

## Output controls and GPU atlas

```python
observer = PipelineObserver(pipeline.active[0])
catalog = observer.catalog()
raw = observer.read("Packed.gbufferA")
atlas, layout = observer.atlas(
    ["Packed.gbufferA", "Depth.depth", "Compute.debugValues"],
    tile_extent=(320, 180), columns=3,
    displays={"Compute.debugValues": {"mode": "uint32"}},
)
```

Use actual output names from `catalog`; names above are illustrative. The observer reads marked outputs. To inspect an unmarked output, stage a declaration with that output added. It never mutates sealed topology. Raw readback returns bytes with original format/extent metadata; D32FloatS8Uint returns separate depth/stencil planes and row byte counts.

For ordinary marked 2D textures, prefer Mogwai's Output/Debug Windows/Save To File. Selecting a previously unmarked output through List All Outputs changes the sealed topology and is rejected; adding every output also changes resource lifetimes and may activate pruned passes. Use atlas only when its specialized views or scripted composition are needed. Native ErrorMeasurePass performs a CPU reduction readback even with ComputeAverage disabled, so it should not be added to normal preview as a performance optimization.

GPU atlas output is RGBA32Float. Color, float/depth scalar, uint/sint and explicit raw bytes/uint32/sint32/float32 modes preserve their source interpretation. Scalars replicate to RGB with alpha 1. Color preserves source alpha. Display mapping applies `value * scale + bias`, then optional `minmax` normalization/clamping. Raw grids use tile width as their source row width and resample all rows; 64-bit coordinate intermediates avoid overflow for large buffers. Visual display conversion does not replace raw integer/float comparison.

Depth visualization copies the actual GPU depth plane into a device-local byte buffer and decodes it in compute; it performs no CPU readback/re-upload. Atlas generation leaves source contents intact. Native validation bounds layout dimensions, overlap, channels and formats. Current atlas allocation limit is 16 million pixels. Array/Cube faces and mips can be selected through `views` or `atlas_views`; structured buffers use explicit byte/scalar interpretation through a GPU raw view. MSAA still requires a resolve. See `ue-legacy-sky-light-resources.md` for examples.

The native atlas and controls are the foundation for later Web/WebRTC output. Transport and the browser UI are not implemented by these observer APIs. Mogwai's built-in image presenter expects a texture; raw-only graphs should execute through the pipeline/native entry point and display the atlas.

## Evidence and remaining rendering work

All listed fixtures are authored independently of RDC. Relevant scripts are `declared_pipeline_smoke.py`, `shader_executor_smoke.py`, `auxiliary_mesh_smoke.py`, `auxiliary_mesh_validation_smoke.py`, `primary_ownership_smoke.py`, `mesh_inputs_smoke.py`, `history_resources_smoke.py`, and `observer_smoke.py`. C++ external-binding checks use `CustomRenderPiplineExternalInputs.cpp`. The migration passed 466 CPU tests and eight GPU suites. The subsequent native-readback simplification passed 469 CPU tests and six relevant GPU suites; current evidence is indexed in `build/native-falcor-audit/verification.json`.

Framework checks do not complete UE reproduction. The saved targetmap's original meshes, transforms, BasicShape/ProcGrid material programs and source camera now render through the primary Packed pipeline (see `ue-legacy-targetmap-native-scene.md`). Native CSM setup/depth/projection is documented in `ue-legacy-native-csm.md`; source sky material, six-face capture, filtering/SH and DefaultLit environment lighting are implemented in `ue-legacy-native-sky-light.md`. GI/SSR, complete postprocessing, WebRTC and final comparisons remain unfinished. Global histogram exposure is implemented above; fixed-preExposure fixtures alone do not validate it. The targetmap/2.rdc case covers passes affecting pixels, excluding independent HZB/culling/LightGrid optimization alignment. Main-image TSR is absent from this capture, while SSR temporal filtering remains required. See `ue-legacy-capture2-baseline.md`. The additional FY1 case remains in progress, as recorded in `ue-legacy-usage-zh.md`. Captured intermediate GBuffer/depth/shadow/shading arrays remain offline comparison targets and are not production inputs.

## External material programs and source object coordinates

Primary Mesh materials may select `material_program: "shader"` (slot 3). Each BasePass selects its immutable `shader.file`, supplying `UESurface ueEvaluateMaterial(VSOut, UESurface)` after common material defaults and before common DBuffer/Schema encoding. `materialBindings` declares textures by stable resource ID with separate shader `binding`, file, sRGB and mip policy, samplers, and typed uniforms. Register every texture path under `file_inputs`; snapshots verify file content and retain shader dependencies. Built-in Scene/View/Material/geometry bindings cannot be replaced. Bindings are validated even for an empty selection, and draw-list changes rebuild variants. The explicit Falcor Adapter rejects this Mesh-only external evaluator.

`SceneBuilderFlags.DontPretransformStaticMeshes` preserves singleton object coordinates, which source ActorPosition/object-axis materials require. Pair it with suitable graph/material merge flags when source identity matters. Default SceneBuilder behavior remains unchanged. Source export precision and texture platform-build limitations are recorded in the targetmap report.

## Independent Mesh extents and fullscreen channel writes

Mesh color/depth attachments accept optional `size: [width,height]`; omitted cleared attachments follow viewport dimensions and omitted loaded attachments inherit upstream dimensions. `viewport: [x,y,width,height]` uses bounded integer pixels inside the common attachment extent. Depth outputs also expose a sampled depth SRV. Custom mesh shaders may consume native setup buffers for their own view transform while retaining shared Scene indexed drawing/filtering/state.

Fullscreen MRT resource declarations accept `writeMask: [r,g,b,a]` booleans. This applies to hardware blending as well as unblended writes; it allows directional CSM to blend encoded RG while preserving the other attenuation channels. GPU evidence: Mesh size/viewport/depth sampling `run-jx_k9o9n`, RG-only BGRA8 alpha blending `run-l09oxlzz`, both under `build/ue-lighting-closure-cache/` with process receipts.

`UEReferenceLightingPass.nativeShadowLight` opts a specific directional-light index into native CSM consumption through `nativeShadowMask` (BGRA8Unorm) and `nativeShadowParameters` (576-byte raw buffer). These input names must not collide with Packed attachment names when enabled. Models cannot bind files over the outer native shader symbols. `shadow_graph.py` demonstrates composition of a native camera setup pass with the existing Mesh and Fullscreen executors; it introduces no captured rendering inputs.

## Declared atmosphere LUT composition

`atmosphere_lut_fragment(parameters, ...)` supplies the source Transmittance → MultiScattering resource dependency using existing `CustomRenderPiplineComputePass` nodes, typed physical uniforms, native R11G11B10Float formats and a linear-clamp sampler. `targetmap_graph(..., shadows=True, atmosphere_luts=True)` composes these outputs with source Mesh/Packed/CSM/Exposure. No atmosphere-specific LUT executor or schema math was introduced. Source/configuration validation, exact UE excerpts, numerical precision limits and native composition evidence are documented in `ue-legacy-native-atmosphere.md`. Their subsequent source sky/environment consumers are documented in `ue-legacy-native-sky-light.md`; the LUT milestone alone did not establish a complete sky renderer.

Directional lights may supply `source_sun` instead of derived `color`/`source_radius`. The native source adapter decodes FColor bytes, optional working-space temperature and atmosphere ground transmittance using original UE CPU bodies. `direction_ue` remains the single light-direction field; duplicating it inside `source_sun` is rejected. Derived values cannot override this contract. Source settings participate in the existing immutable Scene/Lighting configuration. `customRenderPiplineSourceSun(json)` observes the same calculation for tooling and subsequent sky consumers. This extends light setup, not Packed schema layout or shader Codec responsibilities. See the native-atmosphere report for supported source branches and numeric/runtime evidence.

## Dynamic native view and SkyView LUT

`Scene.json.scene_identity_policy` defaults to `strict`. Explicit `dynamic_view` retains the complete native identity snapshot and compares every field except camera scalars, view and projection matrices. Geometry/index/texture bytes, transforms, material and light settings remain checked. Missing full identities, unknown policies, fixed `captured_view`, and conflicting sealed-graph policies reject. `Config::validateSceneIdentity` is shared by Mesh, Init and native setup passes; the sealed graph applies the same comparison. Normal camera motion preserves history; the existing `camera_cut=True` call invalidates history for discontinuities. This is not support for animated or edited scene content.

`UEReferenceSkyViewSetupPass` computes original UE planet/view setup from the actual camera every frame, outputting 160 raw bytes. `sky_view_lut_fragment` declares Setup → Compute and inputs from native Transmittance, MultiScattering and `ExposureFrame.preExposure`. `targetmap_graph(..., sky_view=True)` includes this composition. The shader uses original SkyView mapping/integration and source FastSky parameters; the source scene's LUT is 192×104 R11G11B10Float. No RDC inputs or HZB were added.

Evidence: `build/sky-view-setup-gpu/run-jypkx60a`, native identity tests `build/dynamic-view-native-tests.log` (14 passed), source LUT `build/sky-view-lut-gpu/run-xoyx14yo`, independent controls `build/sky-view-controls/run-ia78h9t_`, and Python suite `build/sky-view-all-cpu.log` (394 passed at that stage). See the atmosphere report for numeric limits. The original sky mesh material and disk now use the shared Packed/Depth contract and pass source integration (`build/sky-material-gpu/batch-tp4a295z`). Realtime SkyLight, wider source-planet numerical validation and final image matching remain pending.

## Primary material graph inputs

`CustomRenderPiplineGBufferPass.materialBindings.resources` declares read-only graph inputs alongside file textures, samplers and uniforms. Each entry uses `name` (graph port) and `binding` (shader symbol), with `format` and optional `size: [width,height]` for a Texture2D, or `kind: raw_buffer` and exact positive `bytes` divisible by four. Optional `direction` must be `input`. Connect native producer outputs using ordinary graph edges. These properties and shaders are frozen by the existing Pipeline snapshot; no resource upload API or special sky bypass was introduced.

Reflection declares the ports, and the normal material binding path validates shader kind/access/scalar type, resource format/extent, single-layer/sample textures and raw-buffer length before Mesh draws. Packed/depth/coverage/exposure port names and common shader builtins remain reserved. Duplicate/overlapping shader bindings reject. Runtime identity checks prohibit reading a primary MRT/depth/coverage resource while writing that same resource through another port. Empty material selections still validate their binding program.

`material_graph_inputs_smoke.py` first failed on the missing `resources` support, then passed: `build/material-graph-inputs/run-0g1obn2m` / launcher `run-b4law0s8`. A native history-backed producer changes its texture and raw-buffer outputs across three frames; primary material evaluation and decoded Packed base color match independent expected values. Eight invalid configurations reject without replacing or changing the active graph's outputs, including primary-MRT feedback aliasing. Existing file texture/sampler/uniform materials, immutable snapshots, empty-selection errors and live material-program transitions also pass (`build/material-shader-gpu/run-meavcwjl`, launcher `run-d3lktv57`). Build passed and `build/material-inputs-all-cpu.log` contains 394 passing Python tests.

### Material output-format assumptions

Optional `materialBindings.fieldFormats` maps logical Schema field names to required physical attachment formats. For example, the source sky declares `{"sceneRadiance":"RGBA16Float"}` because its original noise quantization uses the PF_FloatRGBA error. Native validation follows generated metadata from field to resource to attachment; it does not assume a particular resource name, slot or model ID. Mismatched formats, absent fields and invalid declarations reject before drawing, including empty material selections.

`material_field_formats_smoke.py` passed after the native build: `build/material-field-formats/run-2m3g4i6x`, launcher `run-ugmxss0y`. It verifies six rejection cases and successful relocation of `sceneRadiance` while the old `sceneColor` deliberately has the wrong format. Every rejected candidate preserves the active graph and its raw output. This constraint validates an authored material assumption; it does not automatically derive shader constants for arbitrary output formats.
