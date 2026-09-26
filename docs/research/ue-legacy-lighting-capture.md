# UE E2655 directional-light capture evidence

Captured file: `E:/rdc/ue/1.rdc`, 217,008,048 bytes. Research/export date: 2026-09-09. The source RDC and UE tree were read-only. A hidden RenderDoc replay exported the inputs and stage boundaries; no lighting algorithm was implemented or replaced with captured output.

**E2655 is an additive fullscreen directional-light draw. Its destination already contains SSGI.** The preceding real draw is E2624, the final cascaded-shadow projection draw. E2520, the actual SSGI composite draw, and E2624 have byte-identical SceneColor. Comparing E2655 with E2624 isolates the change in the stored SceneColor attachment, subject to RGBA16F blend rounding.

The ready-to-load DDS fixtures are [indexed here](E:/Project/falcor/Falcor-m0/build/rdc-lighting/dds-inputs.json). They contain the pre-light destination, shadow-stage input, skin algorithm LUT, and scene-AO fallback. **The E2655 result and its delta are comparison evidence, not lighting inputs.** RenderDoc's shader interpreter trace is also not a GPU numerical oracle; a measured discrepancy is documented below.

## Export entry points and reproducibility

- [extract_rdc_lighting.py](E:/Project/falcor/Falcor-m0/scripts/ue_legacy/extract_rdc_lighting.py) launches a hidden `qrenderdoc.exe --python` process with `STARTF_USESHOWWINDOW`, `wShowWindow=0`, and `CREATE_NO_WINDOW`. Its offline mode verifies exports, decodes uniforms, and writes DDS input fixtures.
- [_extract_rdc_lighting_replay.py](E:/Project/falcor/Falcor-m0/scripts/ue_legacy/_extract_rdc_lighting_replay.py) performs the read-only replay. It bounds raw exports to 256 MiB, checks that the preceding draw is E2624, exports reflected 2D SRVs and their view subresources, and limits debugging to four pixels / 100 continuation batches each.
- [lighting-summary.json](E:/Project/falcor/Falcor-m0/build/rdc-lighting/lighting-summary.json) records stage comparisons, verified raw inputs, capture hash, script hashes, DDS payload proofs, and debug caveats.
- [replay-lighting.json](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/replay-lighting.json) retains the actual action ancestry, texture formats/dimensions, descriptor offsets and views, samplers, shader reflections, cbuffer bindings, resource usage, and PSO state.

From this worktree, `python -B scripts/ue_legacy/extract_rdc_lighting.py --replay` runs the replay and offline extraction. Omitting `--replay` only analyzes the existing exports. Evidence is written below `build/rdc-lighting`; the launcher rejects output directories outside this worktree's build directory. GPU replay has finished; subsequent DDS generation and report analysis were offline.

The RDC SHA-256 was identical before and after replay:

```text
822d41ea6ecb12633f42b18ed5ae1a3e7cea02653c9a72724f6e55e127d85fc9
```

The successful worker exported 77,319,604 uncompressed raw bytes, four cbuffer bindings, nine PS 2D SRVs, three SceneColor snapshots, VS/PS disassembly, and two complete 575-state pixel traces. The launcher verifies raw byte counts and SHA-256 for the texture, SceneColor, and cbuffer files. The raw texture API is RenderDoc `GetTextureData(resource, subresource)`; exports preserve the returned native subresource bytes rather than image previews or gamma-converted screenshots.

## Event boundary and compositing state

| Event | Actual action / role |
|---:|---|
| 2497 | Marker: `DiffuseIndirectComposite(DiffuseIndirect=SSGI UpscaleDiffuseIndirect ApplyAOToSceneColor) 1421x1035`. |
| 2520 | Three-index draw inside that SSGI composite marker; exports the pre-light background. |
| 2585 / 2598 / 2611 / 2624 | Four directional-light cascade projection draws, splits 3 / 2 / 1 / 0, into `ShadowMaskTexture`. |
| 2624 | Last real draw before the directional-light draw. Exported SceneColor is the same resource that E2655 subsequently blends into, even though E2624 itself binds the shadow target. |
| 2638 | Marker: `RenderLight Light::StandardDeferred: DirectionalLight`. |
| 2655 | `DrawIndexedInstanced`, three indices, one instance; directional-light contribution. |

E2655 uses SceneColor `ResourceId::3250395`, `R16G16B16A16_FLOAT`, extent 1424×1040, with viewport and scissor `(0,0,1421,1035)`. Its actual PSO is:

- Color blending: source **One**, destination **One**, operation **Add**.
- Alpha blending: source **One**, destination **One**, operation **Add**. RGBA write mask is 15.
- Depth test and depth writes disabled; configured comparison is `AlwaysTrue`. Stencil testing is disabled. Depth target is bound read-only.
- No culling, front-CCW flag true, sample mask `0xffffffff`, raster shading rate 1×1.

These enum names and the complete numeric state are recorded under `stateNames`, `outputMerger`, and `rasterizer` in [replay-lighting.json](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/replay-lighting.json). There is no SceneColor SRV in this PS's nine reflected texture reads: the old background participates through output-merger blending.

| Snapshot | SHA-256 of uncompressed RGBA16F bytes |
|---|---|
| E2520 SceneColor | `b94abac5af43e2ed7dc29263521e6a730653691e716368b3261b92a8be6f6f2b` |
| E2624 SceneColor | `b94abac5af43e2ed7dc29263521e6a730653691e716368b3261b92a8be6f6f2b` |
| E2655 SceneColor | `c27133f09390f85efbe46f9c537b6c3e38c2e91e9eabf809358118db6175c127` |

The last hash also matches the prior E2655 export in the original Falcor capture evidence. E2655 changes RGB in 821,054 pixels and changes alpha in zero pixels. The captured surface samples are DefaultLit; exporting this draw does not validate the newly registered non-DefaultLit lighting models.

## Bound textures and actual reads

All nine reflected PS SRVs are 2D, one slice and one mip. No VS texture SRVs were used. `access.staticallyUnused=false` identifies shader-accessed bindings, while execution of conditional model branches is a separate question. In both selected DefaultLit debug traces, results of t2–t8 reads are present; the t0 skin and t1 profile reads are not executed on those two paths. Both LUTs are nevertheless exported so that their actual bound contents are available.

The table gives the **view format**, which determines sampling, and the byte count of the uncompressed native export. Some underlying allocations are typeless; both allocation and view formats are retained in the manifest. BGRA bytes must be interpreted as BGRA storage even though shader component access uses logical RGBA.

| PS binding | Captured resource | View format | Extent | Raw bytes | Role |
|---|---|---|---|---:|---|
| t0 | `733 PreintegratedSkinBRDF` | `B8G8R8A8_SRGB` | 256×256 | 262,144 | Model-specific skin LUT, conditional read. |
| t1 | `928 SSProfiles` | `R16G16B16A16_UNORM` | 66×64 | 33,792 | Subsurface-profile table, conditional read. |
| t2 | `3250394 SceneDepthZ` | `D32S8` | 1424×1040 | 11,847,680 | Depth sampling / position reconstruction. |
| t3 | `3250396 GBufferA` | `R10G10B10A2_UNORM` | 1424×1040 | 5,923,840 | Surface normal / per-object data. |
| t4 | `3031572 GBufferB` | `B8G8R8A8_UNORM` | 1424×1040 | 5,923,840 | Material scalars / model / flags. |
| t5 | `3031576 GBufferC` | `B8G8R8A8_SRGB` | 1424×1040 | 5,923,840 | BaseColor / material AO. |
| t6 | `3031575 GBufferD` | `B8G8R8A8_UNORM` | 1424×1040 | 5,923,840 | Model-specific CustomData. |
| t7 | `351 FWhiteTexture` | `R8G8B8A8_UNORM` | 1×1 | 4 | Screen-space AO fallback, RGBA bytes all 255. |
| t8 | `3031645 ShadowMaskTexture` | `B8G8R8A8_UNORM` | 1424×1040 | 5,923,840 | Projected directional shadow mask. |

Raw files follow `build/rdc-lighting/raw/2655-Pixel-tN-mip0-slice0.bin.gz`; exact binding descriptors, subresource selection, raw SHA-256, and sampler objects are linked by the manifest. The four GBuffer raw hashes equal the E1853 exports. The 32-bit depth plane also remains byte-identical; the stencil plane is now zero, so the combined depth/stencil raw hash differs from BasePass without implying a geometry-depth change.

The [captured PS](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:279) samples t7 and takes its red channel. This corresponds to `ScreenSpaceAOTexture` in [DeferredShadingCommon.ush:1346](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:1346). The binding is a white fallback in this pass, so its scene-AO multiplier is 1. This does not mean SSGI/AO was absent earlier: the preceding SSGI composite already modified SceneColor.

The shadow input has a further encoding step: [captured PS lines 391–399](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:391) sample t8 with sampler2 and **square each sampled RGBA component** before the lighting/shadow calculation. Do not feed the stored normalized byte directly as the decoded attenuation. Across the full texture, logical R ranges 0–255 and has 63,355 pixels below 255; G/B/A are all 255. Those 63,355 pixels are covered geometry. At `(291,668)`, logical mask RGBA is `(0,255,255,255)` and the E2655 SceneColor delta is zero.

The captured shader uses sampler1 for depth/GBuffer/AO, sampler2 for shadow attenuation, sampler0 for the conditional skin LUT, and an explicit texel load for the profile table. The sampler descriptors, including filtering, addressing, LOD bounds, and descriptor-store offsets, are exported without replacing them with assumed defaults.

## Light cbuffer and View values

[PS b1](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/2655-Pixel-cb1.bin) is 184 bytes from `ResourceId::790`, byte offset 1,524,992; SHA-256 `51afaea5fe7bdc5eaf6b855156a390938d221ca79aea815add4b2158bc6ae2b7`. The [decoded field table](E:/Project/falcor/Falcor-m0/build/rdc-lighting/light-uniforms.json) preserves offsets and numeric values.

The field names and packing are correlated against [LightRendering.h:23](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/LightRendering.h:23), [SceneManagement.h:1102](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Public/SceneManagement.h:1102), and the captured shader's actual b1 loads. RenderDoc reflection calls many fields `unknown`; the source correlation is stated explicitly instead of presenting those names as intact capture debug symbols. Padding bytes are not interpreted as light parameters.

| PS b1 byte offset | Field | Captured value |
|---:|---|---|
| 0 | ShadowMapChannelMask | `(0,0,0,1)` |
| 16 | DistanceFadeMAD | `(0.000500000024,-9)` |
| 24 / 28 / 32 | ContactShadowLength / casting intensity / noncasting intensity | `0 / 1 / 0` |
| 36 | VolumetricScatteringIntensity | `1` |
| 40 / 44 | ShadowedBits / LightingChannelMask, uint | `3 / 1` |
| 48 / 60 | TranslatedWorldPosition / InvRadius | `(2311.294921875,415.675872803,-643.488037109) / 0` |
| 64 | Color | `(5.662358284,4.723650932,4.036610126)` |
| 76 | FalloffExponent | `0` |
| 80 | Direction | `(-0.638741314,0.116178028,0.760599852)` |
| 92 / 96 | SpecularScale / DiffuseScale | `1 / 1` |
| 112 | Tangent | `(-0.638741314,0.116178028,0.760599852)` |
| 124 | SourceRadius | `0.006420149468` |
| 128 / 136 / 140 | SpotAngles / SoftSourceRadius / SourceLength | `(0,0) / 0 / 0` |
| 172 | IESAtlasIndex | `-1` |
| 176 / 180 | LightFunctionAtlasLightIndex / bAffectsTranslucentLighting, uint | `0 / 1` |

These are the shader-facing light parameters; no editor intensity, lux value, or color-temperature setting is inferred from them. The [captured b1 loads](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:354) directly anchor Color at byte 64, Direction at byte 80, SourceRadius at byte 124, and the scale/contact-shadow fields. The captured draw's directional-light ancestry supplies the light type.

[PS b0](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/2655-Pixel-cb0.bin) and VS b1 contain the same 6,748-byte View block, from resource 790 at byte offset 2,293,760. Its SHA-256 is `4045154c242f2bee105d25b8f17b4d52e3a00865e6bcb013d3d77eeca5ee05c6`. VS b0 is a separately exported 64-byte block. [view-uniforms.json](E:/Project/falcor/Falcor-m0/build/rdc-lighting/view-uniforms.json) decodes the established View-layout evidence while retaining its provenance; the complete raw block remains available when an offset is not named by that earlier layout.

| View offset | Value |
|---:|---|
| 1312, InvDeviceZToWorldZTransform | `(0,0,0.10000000149,-9.999999825e-14)` |
| 1360, TranslatedWorldCameraOrigin | `(0,0,0)` |
| 1408, PreViewTranslationHigh | `(2311.294921875,415.675872803,-643.488037109)` |
| 1424, PreViewTranslationLow | `(-2.1982818e-5,-9.4103016e-6,-1.4294488e-5)` |
| 2464, ViewRectMinAndSize | `(0,0,1421,1035)` |
| 2496, BufferSizeAndInvSize | `(1424,1040,0.0007022471982,0.0009615384624)` |
| 2568, PreExposure | `1.0749151706695557` |
| 2572, OneOverPreExposure | `0.9303059577941895` |

The full-screen [vertex shader](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Vertex.txt) is retained to reconstruct its UV/ray convention. The PS multiplies its final contribution by pre-exposure; the local legacy source does this at [DeferredLightPixelShaders.usf:461](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightPixelShaders.usf:461). Compare pre-exposed quantities consistently before blending into the captured destination.

## DDS input fixtures and payload proof

The launcher writes a 124-byte DDS header plus the 4-byte magic and 20-byte DX10 extension. Payload begins at **byte 148**. Each texture is 2D, array size 1, mip count 1. Native channel order and bytes are preserved; no gamma conversion, decompression/recompression, or float conversion is applied to the payload. Typeless capture allocations receive the captured concrete sampling/output format in the DDS header.

| Input name / file | DXGI format | DDS bytes | Intended use |
|---|---:|---:|---|
| [SceneColorBefore.dds](E:/Project/falcor/Falcor-m0/build/rdc-lighting/dds/SceneColorBefore.dds) | 10, RGBA16_FLOAT | 11,847,828 | E2624 reference destination containing prior SSGI. |
| [ShadowMaskTexture.dds](E:/Project/falcor/Falcor-m0/build/rdc-lighting/dds/ShadowMaskTexture.dds) | 87, BGRA8_UNORM | 5,923,988 | Explicit reference shadow-stage input. |
| [PreintegratedSkinBRDF.dds](E:/Project/falcor/Falcor-m0/build/rdc-lighting/dds/PreintegratedSkinBRDF.dds) | 91, BGRA8_UNORM_SRGB | 262,292 | Model algorithm LUT with captured sRGB interpretation. |
| [ScreenSpaceAO.dds](E:/Project/falcor/Falcor-m0/build/rdc-lighting/dds/ScreenSpaceAO.dds) | 28, RGBA8_UNORM | 152 | Captured white scene-AO fallback. |

[dds-inputs.json](E:/Project/falcor/Falcor-m0/build/rdc-lighting/dds-inputs.json) contains absolute paths, whole-DDS hashes, source raw hashes, DDS payload hashes, offset 148, and `payloadUnchanged=true` for all four. The header fields were independently parsed after writing, and payload hashes were compared to the original raw-export hashes. Falcor loader execution is left to the parent integration task; this extraction did not run a Falcor GPU load test after releasing the replay slot.

The pre-light destination and projected shadow mask are **explicit reference-stage fixtures**; their use does not claim implementation of SSGI or shadow-map generation. The skin texture is an algorithm LUT. None of these four DDS files contains the E2655 lighting result. `direct-light-delta.npy` is provided only for comparison and should not be connected as a shader input that replaces direct-light evaluation.

## Numeric samples and debug limits

All values below are pre-exposed linear RGB read from the RGBA16F attachment. Full values and alpha are retained in [lighting-summary.json](E:/Project/falcor/Falcor-m0/build/rdc-lighting/lighting-summary.json).

| Sample | E2624 RGB | E2655 RGB | Stored RGB increment |
|---|---|---|---|
| Sphere `(280,475)` | `(0.06011963,0.05279541,0.04876709)` | `(1.41406250,1.181640625,1.013671875)` | `(1.35394287,1.12884521,0.96490479)` |
| Plane `(600,550)` | `(0.01329041,0.01168823,0.01071167)` | `(1.138671875,0.95019531,0.8125)` | `(1.12538147,0.93850708,0.80178833)` |
| Cube `(975,550)` | `(0.00265121,0.00230598,0.00212860)` | `(1.125,0.93896484,0.80224609)` | `(1.12234879,0.93665886,0.80011749)` |
| Floor `(650,950)` | `(0.04824829,0.04220581,0.03860474)` | `(0.32202148,0.27050781,0.23364258)` | `(0.27377319,0.22830200,0.19503784)` |
| Shadow `(291,668)` | `(0.01319122,0.01209259,0.01189423)` | Same | `(0,0,0)` |
| Sky `(650,150)` | `(0.10546875,0.19189453,0.35546875)` | Same | `(0,0,0)` |

Two debug traces were captured: sphere `(280,475)` and floor `(650,950)`, each 575 states. The [compact debug summary](E:/Project/falcor/Falcor-m0/build/rdc-lighting/debug-pixel-summary.json) preserves the final interpreter output, selected sampled DXIL values, and its prediction versus the actual attachment. Full `debug-*-trace.json` and `debug-*-states.json` files remain in the raw evidence directory.

At the sphere sample, RenderDoc's interpreted PS output is `(1.353927493,1.129472852,0.965194523,0)`. Adding the true pre-light destination and converting to half predicts G=`1.1826171875`; the actual captured G is `1.181640625`, one half ULP lower. At the floor sample the corresponding B prediction is also one half ULP high. The trace's C sample for the sphere is `0.89453125`, whereas stored sRGB byte 243 maps to approximately `0.89626935` under the standard analytic transfer curve. These differences are recorded, not fitted away.

Use the traces to locate branches, bindings, operation ordering, AO=1, and white-shadow sample paths. Do not require all trace float values to match GPU execution exactly, and do not adjust a lighting implementation merely to reproduce the interpreter's values. The primary capture comparison is the actual GPU attachment using the captured raw input formats and view semantics; the subtraction of two half attachments also has its own rounding limit.

## Source fingerprints and remaining scope

The source names/offsets above were checked in this local custom UE tree. SHA-256 fingerprints:

| Source | SHA-256 |
|---|---|
| `Engine/Source/Runtime/Renderer/Private/LightRendering.h` | `6dc5e1806028a959cf378de90c0a6af4d0f89c60b6dd89bf20a970c2f63768c1` |
| `Engine/Source/Runtime/Engine/Public/SceneManagement.h` | `c90f5b5f57bd82176ee7c7f96c1bfe4b808fb5f63fd8c590cb041b1447f53efd` |
| `Engine/Shaders/Private/DeferredLightPixelShaders.usf` | `ea29963960fbc0fe3b2b07418c780652037a641f7dc672565f7c8c05ff307df5` |
| `Engine/Shaders/Private/DeferredShadingCommon.ush` | `bd4974524abfb1229fa4abf790a57325080cc0ea809b942c7ac43b1b0ebc5791` |

This work identifies one captured directional-light draw and produces its immutable-input candidates and validation evidence. Direct-light model equations, Falcor rendering integration, CAS ingestion, full shadow generation, SSGI, other light types, and validation of non-DefaultLit lighting are separate implementation responsibilities. The source RDC/UE files and existing extraction scripts were not modified; no commit was made.
