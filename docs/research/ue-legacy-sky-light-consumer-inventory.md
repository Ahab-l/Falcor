# UE legacy SkyLight consumer inventory

Source survey and integration contract, 2026-09-12. UE source root is
`E:/ue/engine/UnrealEngine`. This complements
[the capture/filter/SH inventory](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-sky-light-source-inventory.md).
It distinguishes a source-specialized DefaultLit consumer from the complete
deferred renderer. It does not establish source-frame or final-render parity.
The requested deliverable is the declared/script rendering framework; the
specified UE scene and RDC are validation cases. The broader source inventory
below records boundaries, not a requirement to implement all UE functionality
or exhaustively validate cases outside the specified scene.

## Source functions and dependency boundaries

Paths in this table are relative to `Engine/Shaders/Private` in the UE root.
Ranges include complete function bodies unless described as statement spans.

| Source | Lines | Contract and dependencies |
| --- | --- | --- |
| `ReflectionEnvironmentShared.ush` | 5-14 | Desktop `SkyIrradianceEnvironmentMap` maps to `View.SkyIrradianceEnvironmentMap`. Slot7.x is the cubemap's average brightness. |
| `ReflectionEnvironmentShared.ush` | 26-33 | Complete `ComputeReflectionCaptureMipFromRoughness`. Roughest mip1, roughness scale1.2; absolute level=`CubemapMaxMip-2+1.2*log2(max(roughness,.001))`. |
| `ReflectionEnvironmentShared.ush` | 43-50 | Complete `GetSkyLightReflection`: TextureCube sample at the above mip, RGB times `View.SkyLightColor.rgb`; average brightness times `Luminance(SkyLightColor)`. |
| `ReflectionEnvironmentShared.ush` | 52-67 | Complete blend-support helper. Real-time source setup cannot blend, so this is a recorded specialization boundary. |
| `ReflectionEnvironmentShared.ush` | 84-103 | Complete `GetSkySHDiffuse`: eight packed float4, linear dot products with `(N,1)`, quadratic dot products with `(xy,yz,z*z,zx)`, slot6.xyz times `(x*x-y*y)`, clamp final sum to nonnegative. Packed coefficients already include diffuse convolution and division by PI. |
| `ReflectionEnvironmentShared.ush` | 125-129 | Complete `GetOffSpecularPeakReflectionDir`: `a=roughness*roughness`; lerp N toward R with `(1-a)*(sqrt(1-a)+a)`. Do not add normalization to its returned direction. |
| `ReflectionEnvironmentShared.ush` | 131-134 | Complete `GetSpecularOcclusion`: `saturate(pow(NoV+AO,RoughnessSq)-1+AO)`. |
| `SkyLightingDiffuseShared.ush` | 25-83 | Visibility struct and complete `GetSkyLightVisibilityData`; source DFAO direction, contrast, exponent, minimum occlusion, tint and material/screen-AO combination. |
| `SkyLightingDiffuseShared.ush` | 85-142 | Complete diffuse driver. Uses clearcoat bottom normal, view direction, GGX energy preservation; separate foliage/subsurface/skin/hair/cloth branches; diffuse lookup/accumulation at130-133, desktop pre-exposure at135-137. |
| `ReflectionEnvironmentPixelShader.usf` | 93-120 | Complete `GatherRadiance`, delegating local captures and SkyLight to `CompositeReflectionCapturesAndSkylightTWS`. |
| `ReflectionEnvironmentPixelShader.usf` | 122-142 | Complete `CompositeReflections`. SSR/non-Lumen input alpha converts to remaining environment weight as `1-ReflectionInput.a`; RGB is preserved. |
| `ReflectionEnvironmentPixelShader.usf` | 144-293 | Complete reflection driver: reconstruct N/V, off-specular peak, SSR/Lumen composition, material-times-screen AO, local capture grid, pre-exposed Cube radiance, EnvBRDF, clearcoat layers, and final NaN/negative sanitize `-min(-Color.rgb,0)`. |
| `ReflectionEnvironmentComposite.ush` | 6-259 | Complete `CompositeReflectionCapturesAndSkylightTWS`. The no-local-capture specialization uses the blended path with zero capture count; the single-capture alternative assumes a valid capture. Dynamic sky bypasses static brightness normalization. |
| `ReflectionEnvironmentPixelShader.usf` | 295-309 | Complete cloud volumetric AO helper. Its sampling branch is under literal `#if 0`; this source returns1. Cloud capture is a separate feature. |
| `ReflectionEnvironmentPixelShader.usf` | 610-653 | Legacy pixel entry: decode GBuffer, skip Unlit, clearcoat remap, Point screen AO, optional bent normal, dynamic diffuse, LightAccumulator/subsurface handling, and specular for non-Hair. |
| `BRDF.ush` | 592-600 | Complete `EnvBRDF(SpecularColor,Roughness,NoV)`: bilinear PreIntegratedGF at `(NoV,Roughness)`; return `SpecularColor*A+saturate(50*SpecularColor.g)*B`. |
| `ClearCoatCommon.ush` | 5-56 | Bottom normal and clearcoat GBuffer remapping. These are real additional model contracts, not valid no-op stubs for a general consumer. |
| `ShadingEnergyConservation.ush` | 7-31 | Energy-conservation permutation selection. |
| `ShadingEnergyConservationTemplate.ush` | 40-44,66-86,126-139 | Energy-term struct and GGX functions; `ComputeEnergyPreservation` returns1 when `USE_ENERGY_CONSERVATION=0`. |

The full pixel shader's includes at34-52 bring many renderer systems. The bounded
adapter should retain complete small math helpers plus unchanged contiguous
statement spans for its supported branch, and explicitly describe the authored
driver and permutation assumptions in a source manifest. A trimmed driver is
not a verbatim complete `ReflectionEnvironment` or `SkyLightDiffuse` function.
Unsupported model helpers should not be replaced by dummy functions.

## Diffuse, specular and ambient occlusion

The DefaultLit diffuse branch is:

```text
DiffuseLookup = GetSkySHDiffuse(lookupNormal) * SkyLightColor
Diffuse = (lookupMultiplier * DiffuseLookup + lookupAdd) * DiffuseColor * DiffuseWeight
Diffuse *= framePreExposure
```

No extra inverse-PI belongs after the packed SH lookup. With source energy
conservation disabled, `DiffuseWeight=1`. With `APPLY_SKY_SHADOWING=0`, visibility
starts at1 and lookup normal is the material world normal. Both source AO modes
still use `min(GBufferAO,ScreenAO)`; mode0 combines that with sky visibility using
min, and mode1 multiplies it. Visibility tint adds
`(1-SkyVisibility)*OcclusionTint` before multiplying material diffuse color.

Specular uses **`GBufferAO*ScreenAO`**, then the complete specular-occlusion helper.
It is not the diffuse minimum. For dynamic sky and no local captures,
`ExtraIndirectSpecular` receives the SkyLight sample and the composite applies
the remaining reflection alpha. SSR RGB/coverage is therefore part of the
reflection contract. Disabling SSR or binding a GPU-authored black reflection
input is an explicit incomplete source feature, not final-scene equivalence.

The initial targetmap consumer can support DefaultLit and preserve Unlit. The
source also has two-sided foliage transmission, subsurface/skin additions, hair
environment shading, cloth fuzz, and clearcoat layered reflection. These remain
open until their source branches and parameter dependencies are implemented.

## Native setup, light color and pre-exposure

[GetSkyDiffuseLightingParameters](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/IndirectLightRendering.cpp:349)
(349-379) copies SkyLight contrast, exponent, tint, minimum occlusion and combine
mode, computes the CPU sigmoid remap, maps Minimum to0 and other modes to1,
sets bent-normal AO presence, and computes inverse specular-occlusion strength.
These are source parameters; current scene export does not include every one.

[SetupReflectionUniformParameters](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/IndirectLightRendering.cpp:666)
(666-757) starts with a trilinear sampler. The real-time ready convolved Cube path
at686-690 retains it and cannot blend. `SkyLightParameters` at737 contains
`[log2(width),applySkyMask,isDynamic,blend]`, hence `[7,1,1,0]` for the exported
movable128 Cube. PreIntegratedGF uses bilinear Clamp at756-757. Main-pass screen
AO and reflection samplers use Point near1980; absent reflection color binds
black. Capture mipgen/convolution/SH samplers are Point, which is a different
stage from this trilinear consumer.

[SceneRendering.cpp](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SceneRendering.cpp:2091)
(2091-2101) sets `SkyLightColor=GetEffectiveLightColor()/cachedLightingPreExposure
*SkylightScale` for real-time capture, gated by the SkyLighting show flag.
The ordinary frame pre-exposure is then applied once by each consuming lobe.
Capture's source cached-lighting default is1/16, so white intensity1 with unit
show/postprocess scales yields `SkyLightColor=(16,16,16)`. This compensates the
capture exposure; it is not a brightness adjustment inferred from an image.
Runtime CVar/postprocess overrides must be tracked separately from defaults.

[SkyLightComponent.cpp](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/Components/SkyLightComponent.cpp:231)
(231-234) computes effective color from `LightColor*GSkylightIntensityMultiplier
*SpecifiedCubemapColorScale`. `LightColor` at274 is the sRGB FColor converted to
linear times intensity. The CVar default is1 at85-90; specified-Cube color scale
defaults to White at324 and is reset at755. `IndirectLightingIntensity` is stored
separately at250 and is not an extra factor in these direct SH/specular helper
expressions. Do not multiply it again without a source call-site dependency.

## PreintegratedGF is a CPU source algorithm

The actual system lookup is generated in
[SystemTextures.cpp](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SystemTextures.cpp:534),
534-670. There is no original standalone PreintegratedGF shader in this source.
It selects filterable `PF_G16R16` when available, otherwise `PF_R8G8`; normal
extent is128x32, with NoV along x and roughness along y at pixel centers.

Its128 deterministic samples use `i/128` and `ReverseBits(i)/2^32`, GGX importance
sampling, and the approximate joint-Smith visibility at609-611. A/B accumulation
is FP32, including source cancellation near the smooth/grazing corner. The
source converts to16-bit integer storage by clamp, multiply65535, add0.5, truncate.
The computed diffuse C channel is not stored in the chosen RG format.

`AmbientCubemapComposite.usf::IntegrateBRDF` at365-425 uses64 randomized samples
and different operations. Its active visibility is also joint-Smith approximate;
the square-root Smith expressions at394-395 are unused. It is not this system
LUT generator. `EnvBRDFApprox` and the PreintegratedSkin texture are also separate.

The accepted implementation is an explicitly identified GPU port of the CPU
algorithm, retaining the unchanged original excerpt and provenance:

- [PreintegratedGF.slang](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Atmosphere/SkyLight/PreintegratedGF.slang)
- [PreintegratedGFSource.json](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Atmosphere/SkyLight/PreintegratedGFSource.json)
- [sky_light_brdf.py](E:/Project/falcor/Falcor-m0/scripts/ue_legacy/sky_light_brdf.py)

The standard fragment publishes `PreintegratedGF.preIntegratedGF` RG16Unorm128x32,
plus `PreintegratedGF.integratedAB` RG32Float for diagnostics. Both are GPU-authored;
neither accepts an upload. The strict smoke compares all8192 stored channel codes,
requires zero difference, and separately checks source rounding of observed A/B.
GPU transcendental behavior is not presumed equivalent to CPU FMath. The first
GPU run passed storage rounding/repeatability but failed241 channel codes with
maximum114; integration precision remains under investigation in
`build/sky-light-brdf/run-jfbhc82k`. This is not a passed LUT parity claim.

The intermediate GPU probe `build/sky-light-brdf/precision-a4vhxcbj` identifies
the first divergence: E2, m2, denominator and Phi all match the FP32 CPU reference
at every sample. The division ratio differs at1500 samples, by up to2 ULP;
CosTheta differs at1093 samples, by up to1 ULP. Subtraction before SinTheta
amplifies this to approximately0.000345 in that value and0.088 in sample weight.
The source-port `precise` local qualifiers alone therefore do not establish
CPU FMath operation equivalence. GPU cosine also differs from CPU cosf.

Explicit `FloatingPointModePrecise` in the Falcor ProgramDesc produced identical
observed intermediates and final A/B to the default-mode probe
(`precision-5n7a54e4`). The LUT declaration now retains that source compiler
contract explicitly, and the authored
[PreintegratedGFSourceMath.slangh](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Atmosphere/SkyLight/PreintegratedGFSourceMath.slangh)
preserves individual CPU operation semantics. Division and square-root hardware
seeds are corrected by exact binary64 midpoint comparisons, returning FP32 after
each source operation. The cosine uses range reduction and degree28 factorial
Taylor coefficients in binary64 before returning FP32. These are numerical
adapters; the integration and accumulation remain source FP32.

CPU tests cover8315 positive random/exponent-boundary values with five seed
offsets for both division and square root, plus16411 random/quadrant-boundary
cosine values against an independent double-cosine oracle. The polynomial matches
actual Windows UCRT `cosf` at all128 phases used by this source LUT. It is not
claimed to reproduce UCRT's approximation for every possible argument:20 of the
additional random values expose a one-ULP UCRT-versus-accurate-cosine difference.
No coefficient is fitted to LUT data and no GPU code mismatch is tolerated.

The local UE Editor build has explicit source precision evidence:
`Engine/Intermediate/Build/Win64/x64/UnrealEditor/Development/Renderer/Renderer.Shared.rsp`
line31 is `/fp:precise`; `Module.Renderer.33.cpp` line21 includes
`Runtime/Renderer/Private/SystemTextures.cpp`. The project Editor target uses
BuildSettingsVersion.V7. UBT `VCToolChain.cs`1322-1347 selects precise semantics
for V7 Editor/Program, while older/default imprecise targets can select `/fp:fast`.
This inventory's CPU oracle corresponds to the evidenced Editor precise build.

The independent CPU oracle now validates all128 source phases against actual
Windows UCRT `cosf`: NumPy's float32 cosine differs at22 phases and is not used as
the source cosine oracle. Double cosine rounded to FP32 matches all128 phases.
Full double integration is only a diagnostic; it differs materially from source
FP32 near the lowest-roughness/grazing corner.

## Existing native graph data is sufficient for the bounded consumer

| Needed value | Existing native source | Adapter contract |
| --- | --- | --- |
| Packed material fields | `{"schema":"$packed","direction":"input"}` | Use generated `decodeGBuffer(ueLoadRaw(pixel),framePreExposure)`; preserve schema snapshot and validity/model checks. |
| World position | `Decode.positionW`, RGBA32Float | Native depth/camera reconstruction in Falcor world meters; alpha indicates validity. Convert to UE cm as `float3(-p.z,p.x,p.y)*100`. |
| Main camera position | `AtmosphereSkyViewSetup.parameters`, raw160 | Row9.xyz is current main camera position in UE centimeters. This is the main setup, not fixed SkyLight capture setup. |
| View vector | Above two inputs | `normalize(mainCameraUE-positionUE)`, preserving current native camera motion. |
| Current frame exposure | `ExposureFrame.preExposure`, Texture2D<float> | Read directly on GPU. Avoid immutable uniform fallback and the old CPU readback exposure adapter. |
| Diffuse irradiance | Original SH output, StructuredBuffer<float4>, stride16,count8 | Bind original allocation as SRV; preserve ordering/scale and slot7 brightness. |
| Specular radiance | Original convolved Cube and full mip chain | TextureCube SRV, trilinear Clamp. Preserve R11G11B10 source storage. |
| BRDF factors | `PreintegratedGF.preIntegratedGF` | Texture2D<float2>, RG16Unorm128x32, bilinear Clamp. |
| Existing direct/emissive color | `Lighting.lightingColor` | Add environment RGB while preserving existing scene alpha and Unlit/invalid coverage. |

[UELegacyDecode.cs.slang](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/UELegacyDecode.cs.slang:65)
(65-76) is the native world-position authority. A new renderer-specific native
camera interface is unnecessary for this bounded script consumer.

Use a declared compute HDR output that preserves scene alpha, or a declared
fullscreen additive `inputOutput` color target with `load` behavior and
`writeMask:[true,true,true,false]`. A framebuffer inputOutput does not need a
feedback SRV. Diagnostic diffuse/specular outputs should remain separately
observable. All file inputs must pass through ordinary immutable shader snapshots.

The exposure histogram source in `targetmap_graph.py` currently points at
`Lighting.lightingColor`. Redirect it to the post-environment color so the
histogram meters both direct and environment lighting. The ExposureFrame port
reads previous-frame history, so this does not require a same-frame feedback
cycle. Apply frame exposure once per lobe and retain transactional history.

## Source target scope and remaining milestones

[Scene.json](E:/Project/falcor/Falcor-m0/build/source-targetmap/Scene.json:612)
(612-670) exports movable, real-time, captured-scene SkyLight at(0,0,600)cm,
white255, intensity1, indirect intensity1, Cube128, cast shadows, and no lower
hemisphere replacement. Exported visible opaque materials are BasicShape
DefaultLit roughness approximately.6407 and ProcGrid DefaultLit roughness.5;
SkyDomePending is Unlit. This supports beginning with a DefaultLit/Unlit consumer.

`E:/ue/project/shadingmodeltest/shadingmodel/Config/DefaultEngine.ini` sets static
lighting false, generated mesh distance fields true, GI method2, reflection
method2, ray tracing false and Substrate false. `EngineTypes.h`452-487 maps2 to
ScreenSpace GI and SSR, not Lumen. Configuration alone does not establish active
runtime/postprocess permutations. Legacy energy conservation defaults to0 in
`ShadingEnergyConservation.cpp`71-75; no project override was found.

The minimum validation sequence is source LUT storage parity; constant and
directional Cube/SH lighting; no extra PI factor; original roughness-to-mip slope;
zero/specular Fresnel response; diffuse-min versus specular-product AO; reciprocal
capture exposure plus one frame exposure; moving native camera; Unlit/coverage
and alpha preservation; source targetmap integration and post-environment
metering. Malformed declarations must reject without changing active outputs.

Cloud/fog participation in capture, full DFAO/SSAO production, SSGI, SSR/local
reflection captures, additional shading models, temporal publication and
postprocessing are separately bounded source features. Their presence in this
inventory does not expand the framework task into full UE compatibility; only
features required by the agreed validation case belong to its acceptance scope.
The literal disabled cloud-AO sampling branch in this consumer does
not justify adding an active substitute, and does not close cloud capture.
