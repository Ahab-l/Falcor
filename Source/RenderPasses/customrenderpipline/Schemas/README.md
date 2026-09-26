# Runtime schema and codec contract

`DefaultLit.json` describes the editable runtime storage and dispatch contract.
It is separate from `scripts/customrenderpipline/reference_profile.json`, which records
immutable capture evidence. Capture view rectangles, exposure, events, and evidence
files are not accepted runtime schema properties.

Run `python scripts/customrenderpipline/generate_schema.py --schema <schema.json> --output <directory>`
from the repository root. The output is `<directory>/<generation>/GBuffer.json`
and a self-contained `GBuffer.slangh`. `--codec-root` selects the codec directory.
The Python APIs are `generate(schema, codec_root=None)` and
`write_generation(schema, output_directory, codec_root=None)`. The latter returns
the metadata path and never modifies an existing generation. Existing snapshot
contents must match exactly; corruption is rejected.

## Storage

All object keys are validated; unknown keys are errors. Names are safe ASCII
shader identifiers; `depth`, `depthCopy`, `primaryCoverage`, `normalUE`, `baseColor`, `material` and
`positionW` are reserved native graph resources. Logical field names are separate
and may use these names.
`attachments` declares one through eight unique contiguous
MRT slots, resource names, Falcor formats, four clear values and four boolean
write masks. `channels` always means shader-visible RGBA, even for BGRA resources.
The runtime currently supports RGBA16Float, RGBA32Float, RGB10A2Unorm, RGBA8Unorm,
RGBA8UnormSrgb, BGRA8Unorm and BGRA8UnormSrgb. Depth/stencil uses D32FloatS8Uint
with zero depth and stencil clears, matching this runtime's infinite reversed-Z mode.

Each `fields` entry has a logical name/type, attachment resource and channel
swizzle. `float` through `float4` use whole channels. `uint` uses one linear UNORM
channel and explicit `bits: {offset, width}`. Overlapping fields and integer
fields routed through sRGB RGB are rejected. `value` optionally supplies a schema
constant; modelID is always a dynamic uint. Disabled channels cannot carry fields.
Unused bits and unassigned writable components are zero. Fully disabled targets
are present in `UERaw` and input declarations but absent from `UEPacked` outputs.

The default schema writes SceneColor radiance and zero alpha, encoded normal and
codec-encoded per-object data, metallic/specular/roughness, five model-ID bits, bit-seven
skip-velocity, linear base color via an sRGB view, and AO. GBufferD remains untouched.

## Codec and model interface

`UEFields` is generated from the logical field declarations. `Codecs/Surface.slangh`
defines `UESurface`; `Codecs/DefaultLit.slangh` owns DefaultLit normal and exposure
math and the initial AO=1 behavior. Codec shaders never name storage resources,
channels or MRT slots. All recursive quoted local includes are flattened into
the immutable output; external imports, macro includes, cycles and paths outside
the codec directory are rejected.

The schema's `codecs` registry selects a source file, a capability `contract`,
named encode/decode entry points and typed `required_fields`. The separate codec
contract must agree with that interface. Each registered model declares its ID,
codec, `valid_fields` and `material_constraints`. Valid fields must be supplied by
the codec, schema constants or generic model-ID routing. Every consumer's required
fields must be valid for every registered model. Model capability requirements
cannot be relaxed by editing schema constraints. AO is the only material equality
constraint currently enforced by this runtime, and the DefaultLit codec requires 1.

The primary encoding API is `encodeGBuffer(UESurface, UEEncodeContext)`.
The context carries pre-exposure, pixel-center position, frame index modulo eight,
primitive flags and an explicit quantization-dither enable. DefaultLit owns the
captured specular dithering math and capsule/contact-shadow flag conversion into
perObjectData; Schema only places that logical field. The compatibility overload
`encodeGBuffer(UESurface, float preExposure)` uses zero flags and no dither, preserving
the controlled numerical fixture. Other public APIs are
`decodeGBuffer(UERaw, float preExposure)`, `ueIsSupportedModel(uint)`, and
`ueIsFieldValid(uint modelID, uint fieldID)`. Generated `kModel_<name>` and
`kField_<name>` constants provide IDs. Field IDs are generation-local, ordered by
logical field name; consumers must use that generation's constants. Define
`UE_SCHEMA_DECLARE_INPUTS=1` to emit `ueInput_<resource>` declarations and
`ueLoadRaw(uint2)`. The default is zero for raster programs.

Unregistered model IDs do not dispatch to a fallback codec. Runtime material
validation must reject them before drawing; decode preserves an unknown packed
model ID so callers can display a diagnostic. Tests register IDs 0 and 2 as DefaultLit
aliases to verify generic dispatch. This fixture is not another UE shading model.

## Generation and integrity

`layout_hash` is SHA-256 of normalized storage, fields, codec registry, model
registration/validity and consumer requirements. It excludes material equality
constraints, runtime schema name, all codec source text, view and exposure.
`codec_hash` is SHA-256 of canonical path-to-source JSON for all recursive local
shader dependencies, including the logical surface definition. Codec capability
contracts are included in metadata and generation identity.

`generation` is SHA-256 of canonical JSON containing the full runtime metadata
before identity/checksum fields and the exact flattened shader. The shader does
not embed `generation`, so the computation is noncircular. `shader_sha1` hashes
the exact UTF-8 shader bytes.

`metadata_canonical` contains sorted-key compact ASCII JSON of the metadata before
adding `metadata_canonical` and `metadata_sha1`. `metadata_sha1` hashes that exact
string. A consumer must verify the checksum and compare the parsed canonical
object to the outer JSON excluding those two fields; this avoids differences
between Python and C++ floating-point JSON serialization. These integrity checks
detect accidental mixing/corruption; they are not signatures or an authorization
boundary for untrusted source files.

Offline tests run with `python -m unittest discover -s scripts/customrenderpipline -p test_schema.py`.
Generated code still requires the runtime's offscreen shader compilation and GPU
execution checks before a candidate pipeline becomes active.

## Mesh pipeline identity

`pipeline_snapshot.py` freezes project material/pass shaders with recursive local
includes and JSON inputs. `PipelineSignature` covers Schema generation, project
sources, PSO settings, defines, routing, graph partitions and recorded Falcor runtime
identity. Material constants, captured View, primitive flags, encoding context and
preExposure also participate in a separate input fingerprint. The Falcor
shader/import runtime remains an external baseline. Strict static
reference scenes now freeze original vertex sidecars and texture resources into
content-addressed inputs and verify native Scene identity before execution.
Frozen replay through `make_graph` rejects a changed recorded Falcor baseline.
This does not provide a general dynamic-scene snapshot system; see
`docs/research/ue-legacy-resource-identity.md` for the accepted scope.

Each native node verifies generation, pipeline/input identity, node name/type and
its signed material filter. Source strings are retained by the native Config and
compiled directly. Stage prepares an entire offscreen graph; commit switches only
after success. Direct low-level createPass without pipelinePath remains a testing
interface and does not carry the full pipeline transaction contract.

BasePass coverage is an explicit R32Uint UAV, independent of MRT layout and depth.
Primary shaders must expose `gPrimaryCoverage` as RWTexture2D<uint>, use early
depth/stencil and write it only for pixels actually output to the GBuffer. Auxiliary
depth alone cannot qualify a registered model ID 0 as a written primary surface.

## Explicit native Adapter and original source vertices

`make_adapter_graph()` builds a distinct `CustomRenderPiplineGBufferAdapterPass` after stock
GBufferRaster. Geometry/final normals/UV/material identity/instance identity come
from its native outputs. Raw UE properties come from an explicit MaterialProgram
mapping; no inverse of stock BSDF diffuse/specular properties is implied. The
Adapter uses the same Schema/Codec generation and whole-graph transaction.
Its five `native*` input names cannot also name its packed attachments.

The primary Mesh pass optionally accepts checksummed original vertex sidecars,
preserving source precision before Falcor half-normal packing. Expected Scene
position and packed-normal correspondence reject destructive preprocessing of
the source index carrier/frame. These content-addressed inputs belong to the
scene input fingerprint, not the Schema. Captured screen-position matrices also
remain View data. See `docs/research/ue-legacy-adapter-fidelity.md` for limitations
and raw capture comparison evidence.

## Model Lighting contracts

`OpaqueModels.json` registers seven GBuffer models; `OpaqueLightingModels.json`
also registers their Lighting programs: Unlit, DefaultLit, Subsurface,
PreintegratedSkin, ClearCoat, TwoSidedFoliage and Cloth. `DirectLightingModels.json`
retains the earlier five-model subset. Shader BxDF math lives in
`Codecs/Lighting`, while each `.lighting.json` declares entry points, required
logical fields, resources and supported profile. Schema generates the shared
dispatch; it does not implement the model equations. `lighting_hash` tracks
Lighting dependencies separately from the GBuffer `codec_hash`.

PreintegratedSkin requires the explicit `skinBRDF` resource. The native pass
binds `gLightingBilinearClamp` with Linear min/mag, Point mip, Clamp addressing,
LOD 0..FLT_MAX and zero bias; this name is reserved against texture-binding
collisions. ClearCoat's dual-normal option belongs to the generated field/model
contract, and the Shader implements both layers using those logical fields.

Mesh and Adapter feed Packed attachments directly to Lighting. The current
implementation is ordinary per-light deferred rendering. Nine native graphs
verify the new models, dual normals, schema migration and missing-LUT rollback;
the Skin arithmetic oracle is conditioned on an independent GPU sampler probe.
The HDR interval check covers only non-dual Mesh zero/front/back/two graphs.
See `docs/research/ue-legacy-coat-skin-lighting.md` for complete evidence and the
remaining strict Capture residuals. Clustered/SSR/TSR/Web and native upstream
shadow/GI/sky/exposure producers remain part of the unfinished renderer goal.
