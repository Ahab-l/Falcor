# Framework before reproduction implementation plan

> For agentic workers: Continue authorized subagent-driven work. Root owns native edits and serial GPU/build; agents own bounded Python modules/reviews. No staging/commits/pushes, UE project edits, or capture-fed rendering.

**Goal:** Complete the requested extensible framework with authored synthetic scenes, then reconstruct the source UE project through it and compare against RDC offline.

**Architecture:** Reuse Falcor RenderPass/RenderPassReflection/RenderGraph and existing Schema/Codec, MeshPolicy, Pipeline transactions. Extend declarations and binding, not scheduling/resource allocation. Shader and CPU implementations retain algorithms; descriptors do not replace them.

**Tech Stack:** Falcor D3D12, C++/Slang, Python graph assembly and immutable snapshots.

**Current user steering:** Use saved targetmap and `E:/rdc/ue/2.rdc`, both inventoried read-only. Do not align HZB or independent optimization structures. Prioritize passes/algorithm stages affecting pixels. HZB work was cancelled and removed. Follow `docs/research/ue-legacy-capture2-baseline.md`; do not carry old capture TSR/Clustered milestones into current acceptance without observed need.

## Baseline and ordering

Existing Schema owns Packed layout/fields/IDs/codec and lighting dispatch/resource needs. Existing MeshPolicy owns pre-submit selection, entry/defines, constrained depth/stencil/cull and dependencies. Falcor owns registered passes, reflection, data/execution edges, DAG ordering and resources. These facilities are implemented and must be reused.

The first gap is the fixed graph roles/names in `pipeline.py` and native Config. Subsequent gaps include generic shader bindings, independent auxiliary Mesh attachments/state, explicit temporal and observer lifecycle.

CSM prototypes are unregistered/unbuilt. They depend on captured matrices, GPUScene and draw lists even if depth is locally rasterized. Capture-fed GBuffer/Lighting and Skin LUT render entries are retired; offline evidence remains readable. The initial retirement passed 184 CPU checks, build, 13 native rejections and authored Lighting/Schema relocation; those historical checks alone did not complete the framework.

## Mandatory framework gates

1. Declaration: arbitrary node names/types/properties, resource and execution edges, outputs and Schema references. Actual Falcor reflection validates physical resources.
2. Shader executors: reusable compute/fullscreen/mesh adapters for source/entry/defines, resource/uniform binding and dispatch/draw. Algorithms may still require custom C++.
3. Mesh execution: existing filters plus independent auxiliary passes with own MRT/depth/load/clear/blend. Shared Packed producers enforce complete writes and unique primary ownership.
4. Schema/material separation: layout/IDs/resources/dispatch in metadata, material evaluation and codec/shading math in Shader. Explicit Falcor Adapter remains.
5. Lifecycle: snapshot every declared project shader/input and topology; validate node/role/properties/source identities. Missing resources, cycles and invalid states reject a candidate; generation/extent/epoch changes invalidate history. Failed candidates retain active output.
6. Observation: all outputs selectable/readable/visualizable; native output atlas/control facilities support later Web/streaming without browser rendering.

Reproduction resumes only after these gates have independent fixtures. Source project assets/settings produce View, GPUScene, exposure, culling, cascades, depth and other buffers. RDC remains offline observation/comparison. SSR/TSR/Clustered algorithms are implemented as framework consumers without dummy/captured-history substitutions.

## First executable slice: general graph declaration

Files: create `scripts/ue_legacy/pass_definition.py`, `test_pass_definition.py`; extend `pipeline_snapshot.py`, `pipeline.py`, `UELegacyConfig.{h,cpp}` and existing pass role checks.

```json
{
  "version":1,
  "nodes":[
    {"name":"Begin","type":"UELegacyInitPass","properties":{}},
    {"name":"OpaqueDepth","type":"UELegacyPrePass","properties":{}},
    {"name":"Opaque","type":"UELegacyGBufferPass","properties":{}},
    {"name":"Inspect","type":"UELegacyDecodePass","properties":{}}
  ],
  "edges":[
    ["Begin.depth","OpaqueDepth.depth"],
    ["Begin.depthCopy","OpaqueDepth.depthCopy"],
    ["Begin.$packed","Opaque.$packed"],
    ["Begin.primaryCoverage","Opaque.primaryCoverage"],
    ["OpaqueDepth.depth","Opaque.depth"],
    ["Opaque.$packed","Inspect.$packed"],
    ["Opaque.primaryCoverage","Inspect.primaryCoverage"],
    ["OpaqueDepth.depthCopy","Inspect.depthCopy"]
  ],
  "outputs":["Opaque.$packed","OpaqueDepth.depthCopy","Inspect.normalUE"]
}
```

`$packed` expands Schema attachment names in slot order; `$field:<fieldName>` resolves a field's physical attachment. Literal ports remain literal. Execution edges use node names without ports. Reject incompatible group selectors, duplicate destinations/edges/outputs, missing nodes/fields, self edges and cycles. Node properties cannot override transaction schemaPath/sceneDefinition/pipelinePath/pipelineNode/signatures/preExposure. Rendering origin policy remains enforced before snapshots/load.

API: `normalize_pass_definition(definition, metadata)` returns canonical normalized physical `nodes`, `edges`, `outputs` plus their source declaration and deterministic topological order. Nodes contain type/name/properties. Pure CPU validation does not import Falcor or read assets.

- [x] RED tests: renamed/reordered nodes and Schema relocation resolve expected physical edges; bad groups/cycles/missing fields/transaction overrides reject.
- [x] Implement deterministic normalization and validation in the independent module.
- [x] Snapshot original and expanded declarations, node properties and project sources; hash them into Pipeline identities.
- [x] Assemble Falcor passes/edges from normalized data; retain the old convenience graph through declaration translation.
- [x] Separate native pass role/type from graph name. Validate each actual class against its signed declaration and properties instead of a hardcoded node-name whitelist.
- [x] GREEN GPU: renamed/split graph preserves Packed output; Schema relocation needs no graph edits; rejected candidate leaves old graph active. All fixtures are authored independently.

Declaration evidence: `build/declared-pipeline-gpu/run-cldy35kp/result.json` and the hardened rerun launched in `build/ue-lighting-closure-cache/run-kbmx38q1`. File inputs copy bytes (shader local includes recursively flattened); native and Python verify SHA256 contract/input identities. Native graph validators run before each execute and commit, including direct builder callers, and freeze defaults/pass identities as well as declared parameters. Pure Falcor passes opt out of shared UE constructor properties with `inherit_pipeline:false`; their `getProperties()` must describe stable executable settings. Known inferred settings should be declared explicitly (for example ImageLoader outputFormat).

Native identity rejection fixture: `scripts/ue_legacy/declared_native_identity_smoke.py`, final rerun passed in launch `build/ue-lighting-closure-cache/run-n8pffccj`. Bool exposure, changed signature, Schema/material-program contract mismatch, and signed-zero input drift reject.

## Framework gate closure, 2026-09-10

All six gates have independent authored fixtures. Final cross-gate ownership review is closed: Python and native sealing reject overlapping producers on shared Packed resources, including Adapter writes. Native checks compare the executors' retained routing material maps as well as policy identity. External `RenderGraph::setInput()` bindings are not part of the declaration/snapshot ABI and reject at seal, commit and execution. The native extensible framework baseline is verified; source-project inventory/reconstruction can now proceed. This does not establish capture equivalence or complete the UE renderer algorithms.

| Gate | Implementation / exercised behavior | Latest evidence |
|---|---|---|
| 1. Declaration | Arbitrary names/types/properties; Schema physical-port expansion; exact topology and effective-property sealing; failed-candidate retention | `build/declared-pipeline-gpu/run-m8mp52ac/result.json` |
| 2. Shader executors | Compute/fullscreen texture/raw bindings, samplers, uniforms, integer clears, dispatch, entry/defines, immutable includes, Schema relocation | `build/shader-executor-gpu/run-smb4nrhk/result.json`; constructor rejection launch `build/ue-lighting-closure-cache/run-jf5edx2v` |
| 3. Mesh | Pre-submit material/model/tag/instance filters, real indexed geometry, independent MRT/depth/load/blend/write masks, vertex-only depth, sampled/raw/Schema inputs | `build/auxiliary-mesh-gpu/run-eb7ylwfd/result.json`; `build/mesh-inputs-gpu/run-89hitz1p/result.json`; seven boundary rejections in `build/auxiliary-mesh-validation-gpu/run-twarkhnc/result.json` |
| 4. Schema/material | Layout/ID/resource contracts remain metadata, mathematics remain shaders; both Mesh and explicit Adapter survive full Schema relocation | `build/framework-adapter-schema-regression/result.json` (two generations for each producer) |
| 5. Lifecycle | Immutable sources/Scene/graph identity, rollback, paired native history, whole-frame publication, repeated/failed frames and epoch invalidation | `build/history-resources-gpu/run-es0eec8k/result.json`; identity launch `build/ue-lighting-closure-cache/run-n8pffccj`; Mesh re-seal/Scene-change rejection above |
| 6. Observation | Marked output catalog/raw bytes, depth/stencil planes, simultaneous GPU atlas, explicit raw interpretation and 2 MiB address-boundary case | `build/observer-gpu/run-vune1430/result.json` |

Final integration checks: 310 unique CPU tests passed (`build/framework-ownership-cpu.log`); UELegacy and FalcorTest builds succeeded (`build/framework-native-contract-build.log`, `build/framework-external-final-build.log`). Ownership regression: `build/primary-ownership-gpu/run-iji5kivf/result.json`, 12 native rejections and 6 valid cases, including common-policy distinct routes, differing retained material maps, and a source file changed between pass constructors. Routing GPU regression (`build/ue-lighting-closure-cache/run-ymd4gnna`, `build/routing-evidence/result.json`) keeps all 15 selector cases and exact Packed outputs. C++ D3D12 external-input test passed (`build/framework-external-inputs.log`, `.xml`), including the specific pre-compilation rejection reason and restoration after removing bindings. Latest no-capture-input regression: 13 native rejections plus authored directional/point/spot Lighting and Schema migration, `build/no-rdc-input-gpu/run-mc__4w21/result.json`. Tests use no RDC rendering inputs. The sampler-array review issue is closed: the shared helper rejects arrays before either Mesh or Compute/Fullscreen binding; negative and positive GPU fixtures pass.

The supported baseline is static indexed triangle geometry and direct texture2D/raw-buffer shader resources. Structured layouts, indirect work and other algorithms can use a declared custom native RenderPass. The observer is the native control/visualization foundation; WebRTC transport and browser UI remain subsequent work, as originally ordered. Auto exposure remains required and is not supplied by fixed-exposure fixtures. See `docs/research/ue-legacy-framework.md` for the public interfaces and exact capability boundaries.

Validation uses bundled Python+NumPy, pinned CMake and root-owned hidden Mogwai/fresh cache. Save full arrays and source identities. Never call retired RDC live replay.

Completed file-level plans are `2026-09-10-shader-executors.md`, `2026-09-10-auxiliary-mesh.md`, `2026-09-10-temporal-resources.md`, and `2026-09-10-output-observation.md`. Next: inspect and export source UE assets/settings using an isolated scratch project, construct the four-DefaultLit baseline through these interfaces, and generate all View/depth/lighting/history internally before offline comparison. Saved-source state may differ from the captured frame and must be recorded rather than corrected with captured intermediates.

Historical inventory found only old autosaves. The user now supplied targetmap and 2.rdc: isolated source loading and offline Capture metadata inventory passed with source files unchanged. The old map is no longer sought and was never a prerequisite for framework implementation. See `docs/research/ue-legacy-source-project-inventory.md`. Historical `build/framework-acceptance.json` is unchanged; fresh evidence is recorded in the capture2 and Windows stack-trace reports.
