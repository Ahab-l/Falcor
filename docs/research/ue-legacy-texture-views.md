# Native declared texture subresources

This extends the existing immutable `UELegacyComputePass` and `UELegacyFullscreenPass` resource declarations for the source SkyLight pipeline. It does not implement SkyLight capture or convolution itself. RDC intermediates are never rendering inputs.

## Allocation and view contract

`kind` accepts `texture2D` (default), `texture2DArray`, `textureCube`, or the existing `raw_buffer`. Texture declarations add `array_size`, `mip_count` and an optional `view` object. Allocation dimensions stay at mip zero; the selected view controls shader binding and dispatch extent.

```json
{
  "name": "filtered",
  "direction": "inputOutput",
  "binding": "target",
  "kind": "textureCube",
  "format": "R11G11B10Float",
  "size": [128, 128],
  "array_size": 1,
  "mip_count": 8,
  "view": {"mip": 1, "first_slice": 0, "slice_count": 6}
}
```

- `textureCube` currently declares one square cube. Its `array_size` is 1 and physical slices are faces 0 through 5. Core Falcor supports cube arrays, but the initial declared contract deliberately exposes a single cube.
- `texture2DArray` has 2 through 2048 physical layers. `texture2D` has one layer. The allocation has 1 through 15 mips, bounded by its dimensions; dimensions cannot exceed 16384.
- View keys are `mip`, `mip_count`, `first_slice`, and `slice_count`. Indices are zero based. Omitted ranges extend to the end, except writable views default to one mip and must select exactly one mip.
- Read-only Cube bindings use `TextureCube`; their view includes all six faces. Writable Cube bindings use `RWTexture2DArray`. Array bindings retain array shader dimensions even when one layer is selected. `SampleLevel(..., 0)` selects the SRV's first physical mip.
- Fullscreen color outputs select exactly one physical face/layer. MRT widths and heights must match at the selected mips. Clears apply to the selected view.
- `dispatch.extent` and uniform `source: extent` use the selected mip's width/height. Compute extent dispatch includes the selected number of layers. `dispatch.groups.axes` accepts `width`, `height`, `layers`, or fixed group counts.
- Allocation, format, ranges, aliases, dispatch limits and MRT extents validate before clears/draws. Malformed numeric ranges are rejected before Falcor view clamping. Raw buffers do not accept texture view properties.

An input SRV of mip N and an inputOutput UAV of mip N+1 can share the same upstream allocation through ordinary graph edges. Both declarations must describe the same full allocation. Their views must be disjoint. Multiple read-only bindings may overlap; any overlapping view with a writer rejects. Views do not create separate graph allocations, and callers still provide graph dependencies for ordering passes.

## Falcor core correction

Pinned Slang/GFX 2024.1.34 counts cubes in `ITextureResource::Desc.arraySize`, then expands each cube into six native layers. Falcor previously multiplied by six before that expansion: one requested cube allocated 36 native layers, while its tracker stored only one face's mip states. Cube view clamping also used the logical cube count.

`Texture::getArraySize()` retains logical cube-count semantics. `getArrayLayerCount()` exposes physical layers for subresource counts/state storage, view ranges, FBO bounds, uploads and ndarray face selection. The allocation descriptor now passes the cube count directly. Cube SRVs require aligned, complete groups of six faces, including direct factory calls.

`ParameterBlock` now passes actual SRV/UAV view ranges into resource barriers. Previously, reading one mip and writing another transitioned the entire allocation to UAV state. Existing UAV ordering remains conservative: when any selected subresource was already a UAV, D3D12 gets a resource-wide UAV memory barrier without changing mip states. Mixed-state Vulkan barriers are scoped to tracked UAV subresources to preserve other layouts.

The existing `Texture::generateMips()` blit samples a Texture2D and cannot expose one Cube face that way. Cube calls, including automatic initialization with `kMaxPossible`, now reject explicitly; automatic calls reject before allocation/upload. Source SkyLight will use its original explicit Cube filtering kernels. Pinned GFX Vulkan cannot create the required Cube writable views, so Cube UAV/RTV/DSV creation rejects there. D3D12 is the declared renderer's supported backend; this work does not establish Vulkan support.

## Evidence

The initial native declaration smoke failed on the old executor's unknown `mip_count` property (`build/ue-lighting-closure-cache/run-nmjs6yy3`). Native base-API tests against unchanged core then failed in five of six cases (`build/cube-native-red.log`, `build/cube-native-red.xml`): measured layers 36/72 instead of 6/12, missing face state storage, and an independent ordinary-array mip alias state error. The ordinary-array face/tracker control passed.

GREEN verification passed on 2026-09-12:

- Pinned CMake Release build of FalcorTest and UELegacy succeeded (`build/cube-native-green-build.log`).
- Nine native Cube tests passed with the D3D12 debug layer (`build/cube-native-green.log/.xml`). Sixteen existing TextureTests, TextureArrays, BlitTests, BufferAccessTests and UELegacyExternalInputs cases passed (`build/cube-regression-*.cpp.log/.xml`). An initial combined-suite regex selected zero tests because Falcor uses basic regular expressions; the five explicit suite runs are the acceptance evidence.
- Authored six-face/four-mip sampling and mip-local SRV LOD passed: `build/texture-views/run-34jfo6kv`, launcher `run-ojdwjn5g` (3.42 seconds, peak private 4.05 GB). The first post-build attempt `run-rt_ynfde` reached correct GPU values but failed a fixture shape assertion: Falcor's ndarray binding removes singleton spatial dimensions. The fixture now restores the known requested shape.
- Cube, ordinary array and mipped 2D allocation/view tests passed: `build/texture-views-validation/run-82mg1vh2`, launcher `run-ful6rglc` (24.27 seconds, peak private 5.62 GB). Every face/mip was compared. All 26 rejection cases passed, including three overlapping-access cases and a later MRT extent mismatch that leave the GPU-authored upstream allocation unchanged before any clear.
- Existing Shader executor passed (`build/shader-executor-gpu/run-ch757mue`, launcher `run-oz7qk_jl`), including the intentional invalid VS/PS linkage and feedback-alias rejection. Constructor-validation smoke passed (`build/shader-executor-validation/run-7w3aekbe`, launcher `run-c2v80tyk`).
- Full Python suite including the new SkyLight source provenance tests: 412 passed (`build/cube-sky-light-source-python-tests.log`). Independent spec/code review reported no actionable findings; `git diff --check` passed.

Fixtures are `UELegacyCubeSubresources.cpp/.slang`, `texture_views_smoke.py`, and `texture_views_validation_smoke.py`. The declared fixtures author all input texels on the GPU; readbacks only assert results. They cover face/mip values, view-local LOD, disjoint mip access, single-face clears/fullscreen writes, invalid declarations and unchanged active/upstream resources after rejection. Build/GPU jobs were serial; no unrelated applications were terminated.

Cube/mip selection in the higher-level Observer/GPU Atlas is a separate pending step. Texture ndarray readback can address an explicit face/mip, but that does not establish Observer support, source SkyLight completion, or final RDC image matching.
