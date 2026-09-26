# UE legacy ordinary deferred direct lighting: source and E2655 evidence

Research date: 2026-09-09. Scope: desktop legacy deferred `DefaultLit`, ordinary directional / point / spot lights, with the capsule/sphere approximation used by the local UE source. This report separates captured shader facts from local-source defaults. No UE files were modified, and this investigation did not build UE or replay the GPU capture.

## Result and provenance boundary

E2655 executes Lambert diffuse plus UE isotropic `D_GGX`, `Vis_SmithJointApprox` and the green-channel-gated `F_Schlick`, with sphere-source corrections. Its DefaultLit path does **not** apply the optional GGX multiple-scattering energy compensation or rough diffuse model. The minimum roughness is `0.019999999552965164`. The captured directional light has a **nonzero** source radius `0.006420149467885494`; treating it as punctual loses active code.

The local source root is [UnrealEngine](E:/ue/engine/UnrealEngine). `Engine/Build/Build.version` reports 5.8.1 and local HEAD is `53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0`. These identify the inspected checkout, not the captured executable. Local custom shading IDs are present. The capture reflection has no source files/PDB and only the `-T ps_6_6` command; the existing reference profile explicitly records `exact_source_binary_match: false`. Accordingly, complete original permutation defines cannot be recovered from this evidence. Algorithmic equivalence below is supported by the captured disassembly, not a claim that all source and binary bytes match.

Capture exports are in [2026-09-09-1](E:/Project/falcor/Falcor/docs/research/captures/2026-09-09-1). `1.rdc` SHA256 recorded by the reference profile is `822d41ea6ecb12633f42b18ed5ae1a3e7cea02653c9a72724f6e55e127d85fc9`; D3D12, SM6.6, RenderDoc 1.45. E2655 PS entry is `DeferredLightPixelMain`, shader's embedded hash is `6e0b306001ff1542a5714eb66ff4269f`.

**E2655 SceneColor is not isolated direct light.** It already includes the SSGI composite at E2497 and other earlier SceneColor content. A useful reference is the before/after difference of this specific draw, restricted to DefaultLit pixels, with the same shadow input, exposure and target format. Even that difference includes floating-point render-target addition/rounding. It must not be compared directly to a zero-initialized, unshadowed direct-light buffer as if the inputs were identical.

## Actual source chain

1. [LightRendering.cpp:1229](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/LightRendering.cpp:1229) registers `FDeferredLightPS` at `DeferredLightPixelMain`. [LightDataUniforms.ush:9](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/LightDataUniforms.ush:9) fills `FDeferredLightData`; `bInverseSquared = bIsRadial && FalloffExponent == 0`, directional source length is forced to zero.
2. [DeferredLightPixelShaders.usf:422](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightPixelShaders.usf:422) decodes screen-space GBuffer, rejects Unlit and custom toon early paths, reconstructs position/view, initializes light, applies profile/atmosphere/cloud color factors, obtains shadow attenuation, and calls `GetDynamicLighting` at line 454. Initial output is zero; this draw does not sample old SceneColor.
3. [DeferredLightingCommon.ush:316](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:316) sets `V=-CameraVector`, `N=GBuffer.WorldNormal` (ClearCoat has a separate bottom-normal override), applies local radius/cone mask, resolves shadow terms, and chooses capsule integration at line 404 when `REFERENCE_QUALITY=0` and the light is not rect.
4. [CapsuleLightIntegrate.ush:108](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/CapsuleLightIntegrate.ush:108) clamps roughness against `View.MinRoughness`, constructs `FAreaLight`, and dispatches the shading model. [ShadingModels.ush:1141](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:1141) sends DefaultLit to `DefaultLitBxDF` at line 212.
5. [DeferredLightingCommon.ush:408](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:408) applies light specular/diffuse scales, light-function atlas if enabled, and surface/transmission shadow multipliers during split accumulation. [DeferredLightPixelShaders.usf:464](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightPixelShaders.usf:464) multiplies output RGBA by `View.PreExposure`; raster blending adds this to existing SceneColor.

## Decoding and coordinate contract

[DeferredShadingCommon.ush:1089](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:1089) decodes ordinary normal as `2*A.rgb-1` and **normalizes the decoded vector**. `GetScreenSpaceData` defaults `bGetNormalizedNormal=true` at line 1346. Captured PS lines 158–163 and 191–195 show this exact decode followed by `rsqrt(dot(n,n))`. Normalization belongs to the lighting input, even when a raw GBuffer decode/debug output intentionally preserves UNORM quantization length.

[DeferredShadingCommon.ush:1147](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:1147) derives `F0=lerp(0.08*Specular, BaseColor, Metallic)` and `DiffuseColor=BaseColor-BaseColor*Metallic`. BaseColor is linear after the GBuffer C sRGB SRV; no manual second sRGB decode. E2655 contains development material overrides, but both captured float4 overrides equal `(0,0,0,1)`, so they are identity here. Exposing nonidentity overrides would require additional input/profile support.

[DeferredLightPixelShaders.usf:102](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightPixelShaders.usf:102) has distinct local and directional reconstruction paths. Directional: `TranslatedWorldPosition=ScreenVector*SceneDepth+TranslatedCameraPos`, `CameraVector=normalize(ScreenVector)`. Local: screen projection reconstructs through `View.ScreenToTranslatedWorld` then obtains camera vector. Portable mathematical inputs are normalized `N`, normalized point-to-camera `V`, and positions/vectors in a consistent UE coordinate space; matching captured pixels also requires the captured jitter, depth conversion and view reconstruction. The light uniform direction points from the surface toward the directional light; it is `-GetDirection()` in the C++ proxy.

For local lights, lengths and positions passed to these UE formulas are in centimeters. `DistBiasSqr=1` therefore means one square centimeter. A Falcor meter-space implementation must convert displacement/source lengths/radius to UE centimeters or consistently transform every distance-dependent term and photometric scale. Reusing the constant `1` in meters changes the law near a light. Prefer shader-ready UE light color; converting UI lumens/candelas/intensity requires the separate upstream light-component conversion and is outside this BRDF contract.

## Captured branch/profile evidence

All PS line references in this section refer to [shader-2655-Pixel.txt](E:/Project/falcor/Falcor/docs/research/captures/2026-09-09-1/shader-2655-Pixel.txt).

| Property | Captured fact | Local source / implication |
|---|---|---|
| Legacy DefaultLit path | ID is masked by `&31` at line 119; ID1 enters label53 via switch lines 952–955 | No Substrate closure decoding in this path |
| Normal precision | Float32 `rsqrt` and float arithmetic, lines 191–195 | Local `half` declarations do not justify a new fp16 implementation |
| Minimum roughness | b0 load byte 4400.w, lines 911–913; raw byte 4412 is `0.019999999552965164` | `max(rawRoughness, View.MinRoughness)`; not a hardcoded clamp of `a2` |
| Rough diffuse | Lambert multiply by reciprocal PI, lines 1090–1095 | Effective `MATERIAL_ROUGHDIFFUSE=0` |
| Anisotropy | ID1 block has isotropic dot context; no tangent/anisotropic branch or GBuffer F resource | Effective anisotropy disabled for this shader path; do not infer support in every UE permutation |
| Ordinary area approximation | Sphere horizon lines 923–944, sphere NoH context lines 989–1081 | `REFERENCE_QUALITY=0` behavior; no sampled reference integrator |
| GGX energy conservation | Complete ID1 result lines 1090–1167 proceeds to accumulation at 3504+ without LUT or preservation factor | Effective `USE_ENERGY_CONSERVATION=0` |
| Sphere energy normalization | Lines 1113–1129 include `asint >> 1` plus `532487669` | This is separate from the disabled multiple-scattering energy flag and must remain enabled |
| Visibility/Fresnel | `.5/(...)` at 1147 and `sat(50*F0.g)` at 1152–1159 | SmithJointApprox and UE F_Schlick |
| Light color and scales | b1 byte64 RGB, byte92 specular scale=1, byte96 diffuse scale=1 | Applied outside model BRDF |
| Pre-exposure | b0 byte2568=`1.0749151706695557`; lines 3612–3617 multiply final RGBA | Exactly once after direct-light assembly |
| SceneColor blend | One/One/Add for RGB and alpha, RGBA write mask15, RGBA16Float target; depth/stencil disabled | Additive draw, viewport 1421×1035 |

Local defaults independently agree with the captured effective energy/rough-diffuse behavior: `r.Material.EnergyConservation=0` at [ShadingEnergyConservation.cpp:71](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ShadingEnergyConservation.cpp:71); `r.Material.RoughDiffuse=0` at [RenderUtils.cpp:2147](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/RenderCore/Private/RenderUtils.cpp:2147). [ShaderCompiler.cpp:4170](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderCompiler.cpp:4170) and line 4194 map these to shader defines. [ShadingEnergyConservation.ush:15](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingEnergyConservation.ush:15) chooses effective energy mode; the disabled branch gives `W=1` at [ShadingEnergyConservationTemplate.ush:66](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingEnergyConservationTemplate.ush:66), diffuse preservation exactly 1 at line135, and conservation returns W at line142. `r.MinRoughnessOverride` defaults to zero at [SceneView.cpp:69](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/SceneView.cpp:69), but its uploaded value is clamped to `[0.02,1]` at line2921.

The portable profile must explicitly select `energy_conservation:0`, `rough_diffuse:0`, `anisotropy:0`, `rect_light:0`; unsupported changes must be rejected, rather than silently rendered through this profile.

## DefaultLit equations and operation order

Notation: `sat(x)=clamp(x,0,1)`, `r` is roughness after the View floor. Area construction supplies `Area.NoL`, `Area.SpecularL`, `Area.Falloff`, `Area.FalloffColor`, and angular/line terms. The material evaluation is zero unless `Area.NoL>0`.

[BRDF.ush:24](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:24) initializes context using dot identities rather than explicitly normalizing `V+L`:

```text
NoL = dot(N, Area.SpecularL); NoV = dot(N,V); VoL = dot(V,Area.SpecularL)
invLenH = rsqrt(2 + 2*VoL)
NoH = sat((NoL+NoV)*invLenH)
VoH = sat(invLenH + invLenH*VoL)
SphereMaxNoH(context, Area.SphereSinAlpha, true)
context.NoV = sat(abs(context.NoV) + 1e-5)
```

`SphereMaxNoH` is [BRDF.ush:63](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:63), including its Newton iteration. With a nonzero sphere, it moves the BRDF context toward the source direction that maximizes NoH; when reflected V intersects the sphere cone it sets `NoH=1` and `VoH=abs(NoV)`. The legacy branch does not add Substrate's later VoL clamp. Visibility uses **Area.NoL**, not the sphere-modified context.NoL. Preserve this distinction.

[ShadingModels.ush:129](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:129) computes finite-source energy normalization:

```text
a2 = r^4
if softSin > 0: a2 = sat(a2 + softSin^2 / (VoH*3.6 + 0.4))
newA2(a2,s,VoH) = a2 + 0.25*s*(3*sqrtFast(a2)+s)/(VoH+0.001)
sphereA2 = a2; energy = 1
if sphereSin > 0: sphereA2=newA2(a2,sphereSin,VoH); energy=a2/sphereA2
if lineCos < 1:
    lineTan = sqrt((1.0001-lineCos)/(1+lineCos))
    lineA2 = newA2(sphereA2,lineTan,VoH)
    energy *= sqrt(sphereA2/max(lineA2,1e-5))
```

Only the soft term changes the `a2` subsequently used in D and visibility. The sphere/line broadening terms change the energy ratio and the selected directions; do **not** replace the D roughness with sphereA2/lineA2. [FastMathThirdParty.ush:52](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/FastMathThirdParty.ush:52) defines `sqrtFast(x)=asfloat(0x1FBD1DF5+(asint(x)>>1))`. E2655 contains this bit-level approximation; replacing it with exact sqrt changes active behavior.

From [ShadingModels.ush:180](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:180), [BRDF.ush:311](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:311), [BRDF.ush:373](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:373), [BRDF.ush:403](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:403):

```text
d = (NoH*a2 - NoH)*NoH + 1
D = a2/(PI*d*d) * energy
a = sqrt(a2)
VisV = Area.NoL*(context.NoV*(1-a)+a)
VisL = context.NoV*(Area.NoL*(1-a)+a)
Vis = 0.5/(VisV+VisL)
Fc = (1-VoH)^5
F = sat(50*F0.g)*Fc + (1-Fc)*F0
geometric = Area.FalloffColor*(Area.Falloff*Area.NoL)
Diffuse = (DiffuseColor/PI)*geometric
Specular = geometric*((D*Vis)*F)
Transmission = 0
```

This profile adds no Fresnel attenuation to diffuse and no optional multiple-scattering factor. A generic PBR implementation using `(1-F)*diffuse`, Schlick-k visibility, exact Smith visibility, F90=1 unconditionally, or a different roughness clamp is not this captured model. These are source-level float operations; compiler contraction/reassociation, rsqrt precision, sampling, interpolation and RGBA16Float blend rounding remain relevant to numeric acceptance.

## Directional, point, spot and complete ordinary capsule construction

[DeferredLightingCommon.ush:303](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:303) forms endpoints `P0=ToLight-0.5*SourceLength*Tangent`, `P1=ToLight+0.5*SourceLength*Tangent`, sets Radius/SoftRadius and **DistBiasSqr=1**. Directional `ToLight=LightData.Direction`, sourceLength=0 and inverseSquared=false. Local ToLight is light position minus shaded position.

[CapsuleLightIntegrate.ush:36](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/CapsuleLightIntegrate.ush:36), [CapsuleLight.ush:60](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/CapsuleLight.ush:60), and [AreaLightCommon.ush:51](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/AreaLightCommon.ush:51) define the complete ordinary approximation:

```text
lineCos=1; falloffColor=1
if SourceLength>0:
    q0=rsqrt(dot(P0,P0)); q1=rsqrt(dot(P1,P1)); q=q0*q1
    lineCos=dot(P0,P1)*q
    falloff=q/(lineCos*0.5+0.5+DistBiasSqr*q)
    diffuseL=0.5*(P0*q0+P1*q1)
    NoL=dot(N,diffuseL)                 # before normalizing vector irradiance
    diffuseL=normalize(diffuseL)
else:
    falloff=1/(dot(P0,P0)+DistBiasSqr)
    diffuseL=P0*rsqrt(dot(P0,P0)); NoL=dot(N,diffuseL)
if Radius>0:
    s=sqrt(sat(Radius^2*falloff))
    if NoL<s: NoL=(s+max(NoL,-s))^2/(4*s)
NoL=sat(NoL)
falloff=inverseSquared ? falloff : 1
ToSpecular=P0
if SourceLength>0:
    R=reflect(-V,N); D=P1-P0; B=dot(R,D)
    t=sat(dot(P0,B*R-D)/(SourceLength^2-B*B))
    ToSpecular=P0+t*D
invDist=rsqrt(dot(ToSpecular,ToSpecular))
specularL=ToSpecular*invDist
sphereSin=sat(Radius*invDist*(1-r^2))
softSin=sat(SoftRadius*invDist)
```

The NoL horizon wrap uses the biased falloff **before** noninverse falloff is changed to 1. Capsule horizon clipping and alternate closest-point/reflection fixes seen in comments are inactive source branches and must not be accidentally enabled. The source also stores a diffuse micro-reflection weight `sat(1-max(length,radius)/20)`; it is unused by the selected rough-diffuse-off profile and omitted from the portable context. Source radius/length zero collapses to punctual formulas, but the implementation can retain the complete ordinary capsule path without a texture dependency.

[DirectionalLightComponent.cpp:402](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/Components/DirectionalLightComponent.cpp:402) converts directional SourceRadius to `sin(0.5*radians(LightSourceAngle))`; it is angular, not a centimeter radius. Soft radius is converted similarly. [PointLightSceneProxy.cpp:44](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/PointLightSceneProxy.cpp:44) and [SpotLightSceneProxy.cpp:27](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/SpotLightSceneProxy.cpp:27) supply local radius/length directly. Therefore no directional inverse-square attenuation is applied, but angular shape changes remain.

[DeferredLightingCommon.ush:246](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:246) computes a separate local light mask. With `d2=dot(ToLight,ToLight)`, `invR=1/attenuationRadius`:

```text
inverseSquared mask = sat(1-(d2*invR^2)^2)^2
noninverse mask = pow(1-sat(dot(ToLight*invR,ToLight*invR)),FalloffExponent)
spot mask multiplier = sat((dot(normalize(ToLight),LightData.Direction)-cosOuter)
                          /(cosInner-cosOuter))^2
```

The desktop local mask contains no `1/d2`. The reciprocal biased-square-distance factor comes from capsule integration once; for a punctual inverse-squared local light the combined attenuation is `mask/(d2+1)`. The mobile-only extra reciprocal at lines262–267 is excluded. For noninverse point/spot the capsule Falloff is 1. `SpotAttenuation` at [DynamicLightingCommon.ush:58](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DynamicLightingCommon.ush:58) negates its argument, and its caller passes `-LightData.Direction`: using the uniform direction directly in the simplified dot above is intentional. Cone inputs are shader-ready `(cosOuter,1/(cosInner-cosOuter))` derived after component cone clamping at [SpotLightSceneProxy.cpp:18](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/SpotLightSceneProxy.cpp:18).

## Shadow, exposure, resources and additive output

E2655 binds t0 PreintegratedSkinBRDF, t1 SSProfiles, t2 depth, t3 GBufferA, t4 B, t5 C, t6 D, t7 FWhiteTexture for screen-space AO and t8 ShadowMask. DefaultLit uses no skin/SSProfile LUT. No energy-conservation LUT is bound. Resource identities and view descriptors must come from the capture bindings/pipeline, not guessed register names. The captured b0 layout-prefix evidence from a different BasePass material covers only the first2576 bytes; the **MinRoughness byte4412 mapping here is independently established by the active max operation and raw value**, not extrapolated from that partial prefix.

| Captured scalar/vector | Buffer / byte offset | Value |
|---|---|---|
| PreExposure | b0 / 2568 | 1.0749151706695557 |
| OneOverPreExposure | b0 / 2572 | 0.9303059577941895 |
| DiffuseOverride | b0 / 2576 | (0,0,0,1) |
| SpecularOverride | b0 / 2592 | (0,0,0,1) |
| MinRoughness | b0 / 4412 | 0.019999999552965164 |
| DistanceFadeMAD | b1 / 16 | (0.0005000000237487257,-9) |
| ContactShadowLength | b1 / 24 | 0 |
| ShadowedBits | b1 / 40, int | 3 |
| Color | b1 / 64 | (5.662358283996582,4.723650932312012,4.036610126495361) |
| Direction | b1 / 80 | (-0.6387413144111633,0.11617802828550339,0.7605998516082764) |
| SpecularScale / DiffuseScale | b1 / 92,96 | 1,1 |
| SourceRadius / SoftSourceRadius | b1 / 124,136 | 0.006420149467885494,0 |

[Common.ush:1321](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/Common.ush:1321) samples and decodes light attenuation. The captured shadow sample at PS391 is squared channelwise at lines396–399; the exported raw ShadowMask must be squared exactly once before shadow-term use. With captured static shadow effectively1 and contact length0, [DeferredLightingCommon.ush:133](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:133) gives:

```text
atten = sampledShadowMask^2
fade = sat(SceneDepth*DistanceFadeMAD.x+DistanceFadeMAD.y)^2
surfaceShadow = lerp(atten.x,1,fade)*atten.z
transmissionShadow = min(lerp(atten.y,1,fade),atten.w)*atten.z
transmittanceOrOpticalThickness = min(atten.y,atten.w)
```

Captured PS409–422 confirms that fade and combination. DefaultLit has zero model transmission. For a controlled unshadowed fixture choose `ShadowedBits=0`, `ContactShadowLength=0`, AO=1, no static/precomputed shadow or lightfunction/IES/cloud/atmosphere factors, and all-one explicit shadow terms. Changing only a sampled mask to white does not generally disable contact shadows or static inputs in other permutations. Captured shadow terms are an independent input mode; they do not constitute a CSM implementation.

The outer DefaultLit RGB assembly is:

```text
lightRGB = Color * localRadiusAndSpotMask * otherEnabledLightColorFactors
directRGB = lightRGB * surfaceShadow * (DiffuseScale*Diffuse + SpecularScale*Specular)
PS.rgb = PreExposure * directRGB
SceneColor_after = targetFormatRound(SceneColor_before + PS.rgb)
```

DefaultLit alpha is zero in this captured path; the general source alpha carries separated subsurface/non-specular luminance when required by other model paths. Blend state is additive for both channels. [LightRendering.cpp:2890](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/LightRendering.cpp:2890) contains the ordinary additive `TStaticBlendState<CW_RGBA,BO_Add,BF_One,BF_One,BO_Add,BF_One,BF_One>`, consistent with the actual E2655 pipeline. BasePass already pre-exposes emissive; direct lighting must add its independently pre-exposed contribution without multiplying existing SceneColor again.

## Portable implementation boundary

The model function takes decoded material values and the context `(N,V,AreaLight,ShadowTerms,subsurfaceTransmittanceDistanceM)` and returns separate diffuse/specular/transmission. For DefaultLit the shadow argument is unused internally: the caller applies surface shadow together with light color and per-lobe scales after the model. The caller normalizes decoded normal, supplies any ClearCoat bottom-normal override, and applies the View roughness floor before constructing AreaLight. The common capsule helper retains finite length/radius/soft-radius, horizon wrap, closest-to-reflection specular direction, SphereMaxNoH and finite-source energy normalization. It has no resource dependency.

Initial fixture acceptance should cover unshadowed directional, point and spot; a separate captured-shadow mode can compare the E2655 draw with its actual mask and preexisting SceneColor. Real shadow rendering/CSM, rect LTC, anisotropy, rough diffuse, optional energy tables, alternate development overrides, light profiles/functions/atmosphere/clouds, and UI photometric conversion require explicit contracts and their own validation. No claim that the three ordinary light types or finite-area branches have been GPU-validated follows from source tracing alone.

### Implemented shader interface

[LightingCommon.slangh](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Codecs/Lighting/LightingCommon.slangh) supplies the capsule/BRDF math and these types. The module intentionally has no shadow-texture, light-color, exposure or render-target dependency:

```text
UEModelLighting: float3 diffuse, specular, transmission
UEShadowTerms: float surfaceShadow, transmissionShadow, transmittanceOrOpticalThickness
UEAreaLight: float sphereSinAlpha, sphereSinAlphaSoft, lineCosSubtended;
             float3 diffuseL, specularL; float NoL, falloff; float3 falloffColor
UEDirectLightingContext: float3 N,V; UEAreaLight area; UEShadowTerms shadow;
                         float subsurfaceTransmittanceDistanceM
UEBxDFContext: float NoV,NoL,VoL,NoH,VoH
ueMakeCapsuleAreaLight(float roughness,float3 N,float3 V,float3 toLight,float3 tangent,
                      float sourceLength,float sourceRadius,float softSourceRadius,
                      bool inverseSquared) -> UEAreaLight
```

[DefaultLit.slangh](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Codecs/Lighting/DefaultLit.slangh) exports `ueShadeDefaultLit(UESurface,UEDirectLightingContext) -> UEModelLighting`. [Unlit.slangh](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Codecs/Lighting/Unlit.slangh) exports `ueShadeUnlit` with the same signature, returning three zero lobes, matching the source entry's `ShadingModelID>0` gate. Existing emissive is preserved by outer additive composition. Sidecar `.lighting.json` contracts declare required logical fields, an empty resource list, and the four disabled profile flags. Model files include `../Surface.slangh` and `LightingCommon.slangh`; generated snapshots must preserve/resolve these includes. Integration compilation and GPU acceptance are separate work; this source-only task does not claim either has passed.

## SHA256 evidence

Hashes below identify the actual bytes read on 2026-09-09; they include local modifications if present. They do not assert an unmodified UE distribution or original captured-source provenance.

| Local UE source (relative to source root) | SHA256 |
|---|---|
| `Engine/Build/Build.version` | `29f7a3e61c24327147037ee15928d1bd1603fb65bcd19058e8381e26a12d38bd` |
| `Engine/Shaders/Private/DeferredLightPixelShaders.usf` | `ea29963960fbc0fe3b2b07418c780652037a641f7dc672565f7c8c05ff307df5` |
| `Engine/Shaders/Private/DeferredLightingCommon.ush` | `d3bcd5cf9c36cab57c281f6cad447816891836e3c05a67c8808cbb9ad83e2c46` |
| `Engine/Shaders/Private/DeferredShadingCommon.ush` | `bd4974524abfb1229fa4abf790a57325080cc0ea809b942c7ac43b1b0ebc5791` |
| `Engine/Shaders/Private/LightDataUniforms.ush` | `4ec919e1f1055c19e65fde265da5671ab4dfd98f3cac9ccefd79b78e2dcc3226` |
| `Engine/Shaders/Private/DynamicLightingCommon.ush` | `c5cf14a7d7d276e9737ad9b2312fd422a313d2a72c965a789ca167db5b4dc987` |
| `Engine/Shaders/Private/CapsuleLightIntegrate.ush` | `ab9b14123ead4faec6604000a05abbcb3ea1ab832b9cdea2dab6772a2ca5a591` |
| `Engine/Shaders/Private/CapsuleLight.ush` | `707055ac0395142ca9cff7df4e183658c6db2a8830d72cd79fe4278cee8960fe` |
| `Engine/Shaders/Private/AreaLightCommon.ush` | `259c3f81da7c5b2c22176949d838113b74059d310fa4dcce56995955227f08a7` |
| `Engine/Shaders/Private/ShadingModels.ush` | `74fa44bc4633e695db936b25909c1cbab3d2a85cb768f184c92862eb136e810a` |
| `Engine/Shaders/Private/BRDF.ush` | `0de81cc25c9b035a77aeb0e2f1be3e730c0f117f9250fe365104f30119b5e906` |
| `Engine/Shaders/Private/FastMathThirdParty.ush` | `4f0a38c0d37d1c5ba0d2b9a7cac89e6596a9403ba637088bc450910f1b0f03bc` |
| `Engine/Shaders/Private/ShadingEnergyConservation.ush` | `d7c107e45eb4f5684c04afbe4905b9342473af257dbee1e468ea39f067d9ea2a` |
| `Engine/Shaders/Private/ShadingEnergyConservationTemplate.ush` | `735bc2c6c16471db7f2a623df9fc520ca2ca0d810b382f70eb951af94aa4604c` |
| `Engine/Shaders/Private/Common.ush` | `11184bf6e39a0065e66acd174e2b8407c89791a184a2ad9552a1f1d83669c84b` |
| `Engine/Shaders/Private/ShadingCommon.ush` | `12e9d8e9989e7f6935f739f4c446e423358d9fab1ad56ef59a90ee2033050fd8` |
| `Engine/Source/Runtime/Renderer/Private/LightRendering.cpp` | `44fc8a637fd0bc68645a09b1bc5a354b0aaab9e3a670e3ea1c05321908250f54` |
| `Engine/Source/Runtime/Renderer/Private/ShadingEnergyConservation.cpp` | `8825f9d5c7028ab6ab070a597fe5dc153c6c731ffc109b6c1bdca17badae9e21` |
| `Engine/Source/Runtime/Engine/Private/SceneView.cpp` | `93c64b3ea812b4ab3c673dfb9c0deadc3e30e150508e31b2295eff7b47926b9d` |
| `Engine/Source/Runtime/RenderCore/Private/RenderUtils.cpp` | `a6c9ac81ffd37d7414df7716141b5b8acb89edd7fb97905d2ebb691ca67f2ccd` |
| `Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderCompiler.cpp` | `652761908e350f2361d3a76d561c36f0f1b084111be9aef439796c902c256dde` |
| `Engine/Source/Runtime/Engine/Private/Components/DirectionalLightComponent.cpp` | `bf207d146b7bb0e791c7a4fbc7325b521a86eddc61f51249292c5c68aaec3f17` |
| `Engine/Source/Runtime/Engine/Private/PointLightSceneProxy.cpp` | `470e3d397380c870d743834bbfae97c4c04fe988423e0469f004149c2f3a6620` |
| `Engine/Source/Runtime/Engine/Private/SpotLightSceneProxy.cpp` | `caadd559d8333d6ee9751db848d3902a30a6586f4dcfd75507342a388d809fdd` |

| Capture export | SHA256 |
|---|---|
| `shader-2655-Pixel.txt` | `c4a958663f70f6271e05c254d25e372c88d3ef7e2d46a9b6d4e66e81662bdae8` |
| `reflection-2655-Pixel.json` | `35e47d51db1bd1ef3e7bf7058193504bddbb1da29f2cba1da4653c8c38fc1582` |
| `pipeline-2655.json` | `55598bfc78bc73658f22e7fc2c25213b353e78d90b77b5b4f174cab5f1734783` |
| `bindings-2655-Pixel.json` | `5438a63320cd7c25b3f815302974d856e2df13d22a8b6a85b410e15ba76068a4` |
| `cbuffer-2655-Pixel-0.bin` | `4045154c242f2bee105d25b8f17b4d52e3a00865e6bcb013d3d77eeca5ee05c6` |
| `cbuffer-2655-Pixel-1.bin` | `51afaea5fe7bdc5eaf6b855156a390938d221ca79aea815add4b2158bc6ae2b7` |
