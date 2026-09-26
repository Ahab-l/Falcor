# Native GBuffer Schema and codec contract

User authorization: implement G4/G5 now, with custom quantization and multi-field codecs. Adapt actual UE materials through generic contracts, without importing our old UE material/depth implementation. Work in the existing Falcor-m0 worktree; no commits or merges.

## Chosen scope

A standalone Python validator/generator produces Slang storage encode/decode and the existing native GBuffer definition. Falcor still owns shader compilation, materials, rasterization and RenderGraph. No new C++ generator, runtime scheduler, old SchemaPipeline dependency or whole-graph rollback.

Alternatives considered: importing the old generator also imports its model/depth contracts; a new C++ schema runtime duplicates tooling and adds per-load integration cost. The selected Python generation step feeds the already-supported native JSON/Slang entry and works offline as a CLI.

## Single source

Schema version 1 contains `name`, `attachments`, `fields`, `storage`, `codecs`, and optional `producer` / `depthFormat`. `fields` describes logical values. `storage` locates named scalar/vector slots in an attachment's RGBA channels, optionally using a scalar bit range. `codecs` assigns every field and slot exactly once. Attachment order is MRT order.

Built-ins: unsigned integer, signed integer, boolean, linear UNORM quantization, and direct typed channels. Quantization requires an explicit finite range and overflow policy (`reject` or `clamp`). Round-to-nearest-even is the documented quantization rule. Bit storage is supported in unsigned integer channels or linear UNORM channels; sRGB RGB bit fields are rejected because hardware transfer conversion changes numeric codes. Floating/vector slots route whole channels. Unsupported formats are explicitly rejected rather than guessed.

Custom codec blocks declare multiple logical fields and storage slots. The generator emits block-specific input/storage structs; authored Slang implements `bool encode(Input, out Storage)` and `Input decode(Storage)`. This supports nonlinear quantization, lookup functions and joint encodings such as octahedral normals. Custom algorithms retain responsibility for their semantic domain; the generated outer encoder also checks returned storage capacity and finiteness.

## Generated API and native integration

For schema `Example`, generate `ExampleFields`, `ExampleStorage`, `ExamplePacked`, `bool ExampleEncode(ExampleFields, out ExamplePacked)` and `ExampleFields ExampleDecode(ExamplePacked)`. Invalid input or rejected overflow returns false and a zero packed result. No silent integer truncation. Float channels are checked against their representable range before output.

With an authored producer, generate the native Scene raster wrapper. Producer signature: `ExampleFields evaluateGBuffer(ShadingData sd, uint materialID)`. Producer owns material evaluation; generated code owns layout. The raster wrapper discards fragments whose Encode returns false, and the API return value is available to custom consumers for other explicit handling. The producer can use Falcor material queries or authored material logic. The native definition references the generated wrapper and attachment list; it retains native depth defaults, with no UE depth requirement.

The header includes a schema/codec contract fingerprint and detects conflicting headers with the same schema name at compile time. Both directions come from the same validated contract; this does not detect a consumer that deliberately bypasses it or prove arbitrary custom Slang correct. Metadata carries layout and source hashes for downstream diagnostics; live transitive shader dependencies remain Falcor's responsibility.

Artifacts are written into content-addressed generation directories and a manifest is published last. Invalid schemas or missing files leave the previous manifest usable. This is file publication integrity, not runtime Shader/whole-graph rollback. Custom/producer includes remain ordinary Slang sources; no legacy snapshot engine is introduced.

## Validation

Reject unknown keys, duplicate/unsafe identifiers, absent attachments/channels, bit overflow/overlap, incompatible storage types, impossible declared ranges, incomplete or multiply-owned codec routing and missing custom source files. Distinguish declared-range checking from GPU runtime value checking. Zero initializes unassigned attachment channels/bits.

CPU tests cover rejection and deterministic generation. GPU tests compare encoded words against independently calculated constants, decode independently supplied words, exercise endpoints/rounding/overflow/non-finite values and custom nonlinear/multi-field codecs. Raster acceptance compares native material coverage/depth and expected quantization to stock GBufferRaster and runs a second Shader that reads actual MRT outputs through the generated decoder. A deliberately mismatched header must fail Shader compilation.

## Boundaries

No arbitrary Slang proof, schema-driven material importer, automatic UE asset loading, Vulkan acceptance claim, per-frame readback, legacy code purge or whole-graph rollback. Existing authored native GBuffer definitions continue working. Keep G4/G5 status separate from A1 migration and V4 semantic UI.
