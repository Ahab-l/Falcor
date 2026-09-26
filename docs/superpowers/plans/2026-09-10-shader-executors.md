# Reusable shader executors

This is the second framework gate from the approved framework-before-reproduction plan. No capture inputs or UE feature alignment are part of this slice. Reuse Falcor ComputePass, FullScreenPass and RenderGraph resource allocation.

## Interface

Register `UELegacyComputePass` and `UELegacyFullscreenPass`, both inheriting the frozen Pipeline context. A common implementation accepts:

- `shader`: immutable `file`, entry (`compute` or `pixel`, optional fullscreen `vertex`), string `defines`. The declaration registers `shader.file` in `file_inputs`.
- `resources`: texture2D or raw-buffer input/output/inputOutput declarations. Explicit names, formats, bindings, dimensions/byte size, optional clear; fullscreen color outputs have unique contiguous MRT slots. Schema Packed inputs can expand through `schema: "$packed"`, using Schema names/formats/shader bindings.
- `uniforms`: shader member paths with explicit scalar/vector types and values; built-in extent/preExposure bindings are declared explicitly.
- `samplers`: named sampler bindings with filter/address settings.
- `dispatch`: compute thread counts or the extent of a declared texture. Falcor derives thread-group counts from shader reflection.

Validate unknown properties, formats, binding names and state before any candidate commits. Fullscreen execution binds its own FBO; compute outputs use UAVs. Both stay subject to graph/source/effective-property validation. Algorithms remain in authored shaders or specialized native passes.

## Verification

- [x] RED GPU fixture: authored compute pattern -> fullscreen transform with uniform/sampler binding, exact independent CPU expected array, no capture reader.
- [x] Implement shared parser/reflection/binding and both registered executors.
- [x] Verify schema Packed input binding, explicit dimensions, raw buffer producer/consumer, actual entry/define changes.
- [x] Reject missing shader members, incompatible formats, duplicate slots and invalid dispatch without replacing active output.
- [x] Verify immutable replay after original shader/include deletion.

Latest GPU evidence: `build/shader-executor-gpu/run-smb4nrhk/result.json`, with full arrays. Includes integer clear value 16777217, unchanged Schema decoder after MRT/channel/model-ID relocation, deleted-source replay, and a native vertex/pixel linkage rejection followed by an unchanged active graph render. Constructor-only negative tests in `shader_executor_validation_smoke.py` reject resource kind/access/format mismatch, dispatch overflow/group-limit cases, uint64-to-int overflow and sampler arrays; launch `build/ue-lighting-closure-cache/run-jf5edx2v`.

The default fullscreen vertex entry exports only SV_Position; shaders requiring varyings declare a matching vertex entry. Uniforms currently cover float/int/uint scalar/vector and scalar bool, with explicit extent/preExposure sources. Integer compute clears preserve bits; integer render-target clears require an explicit shader. Compute thread rounding uses validated 64-bit group bounds before Falcor dispatch. Raw buffers are byte-addressed; structured-buffer layouts and indirect dispatch remain explicit future extensions.

Falcor resource reflection now reads a texture/buffer's resource result scalar type, instead of asking the resource object itself (which returned Unknown). Invalid D3D12 draw arguments log driver validation and throw so a candidate can be rejected; device-loss errors retain Falcor's fatal handling.

Auxiliary Mesh, temporal history and observation are now independently verified in their respective subplans. Overall closure is tracked in `2026-09-10-framework-before-reproduction.md`.
