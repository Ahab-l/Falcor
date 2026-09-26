# UE legacy model direct-lighting source findings

Research date: 2026-09-09. UE root: `E:/ue/engine/UnrealEngine`. Falcor worktree: `E:/Project/falcor/Falcor-m0`.

The seven registered models have distinct lighting capabilities. **Shared GBuffer storage does not imply a shared BxDF:** Subsurface, PreintegratedSkin, and TwoSidedFoliage share a storage codec but dispatch to three different transmission algorithms. A resource-free direct-light profile can implement Unlit, DefaultLit, Subsurface, ClearCoat, TwoSidedFoliage, and Cloth. PreintegratedSkin additionally requires the actual skin integration texture. Using DefaultLit for any missing model would not establish that model's lighting support.

This is source research and interface design. No Lighting shader implementation, UE capture comparison, build, or GPU execution was performed for this report. Existing codec evidence is documented in [the GBuffer report](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-model-codecs-source.md:1).

## 1. Source identity and bounded profile

[Build.version](E:/ue/engine/UnrealEngine/Engine/Build/Build.version:1) reports 5.8.1, `Changelist=0`, `CompatibleChangelist=55116800`, `BranchName="UE5"`. Local custom Toon paths show that this checkout is modified. The SHA-256 manifest below identifies the files actually inspected; it does not establish the identity of a captured engine executable.

The proposed first direct-light profile is PC deferred, non-Substrate, opaque, no anisotropy, `MATERIAL_ROUGHDIFFUSE=0`, `LEGACY_MATERIAL_ENERGYCONSERVATION=0`, no rect lights, no reference-quality Monte Carlo integration, no mobile visibility clamp, and identity development material overrides. Preserve the existing codec restrictions and five-bit model IDs. ClearCoat bottom-normal capability is explicit and independent of anisotropy.

At the BxDF boundary, inputs are decoded material values, normalized light/view directions in the same world-space basis as the normals, nonnegative incident RGB radiance, and separately defined surface/transmission shadow factors. A zero-size light has `SphereSinAlpha=0`, `SphereSinAlphaSoft=0`, `LineCosSubtended=1`, `DiffuseL=SpecularL=L`, and `NoL=saturate(dot(N,L))`. With those shape terms [EnergyNormalization](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:129) is one and leaves roughness unchanged. [EvaluateBxDF](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:1176) is a useful source boundary but does not itself perform all deferred light setup.

This bounded BxDF profile must not be described as complete UE directional/point-light equivalence. The deferred capsule wrapper first applies `max(GBuffer.Roughness, View.MinRoughness)` at [CapsuleLightIntegrate.ush:108](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/CapsuleLightIntegrate.ush:108); source geometry and inverse-squared attenuation are computed at lines 36–104. A port must record its minimum-roughness rule and whether attenuation was already folded into incident radiance. In particular, the capsule inverse-square branch uses `1/(distanceSquared+DistBiasSqr)`, with `DistBiasSqr=1` supplied by [GetCapsule](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:303). The rect wrapper instead clamps roughness to 0.02 at [RectLightIntegrate.ush:88](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/RectLightIntegrate.ush:88). Arbitrary roughness clamps change the reference.

## 2. Dispatch and model requirements

The authoritative legacy switch is [IntegrateBxDF](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:1137), lines 1137–1172. The non-Substrate deferred pixel shader only shades model IDs greater than zero at [DeferredLightPixelShaders.usf:429](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightPixelShaders.usf:429). Unlit has no special BxDF case and the switch's default is zero.

Here, “extra texture” means beyond the GBuffer/depth and any already-resolved incident light/shadow inputs, under the energy-off, non-rect profile.

| Model / ID | UE entry and active lines in ShadingModels.ush | Decoded model inputs beyond ordinary lit material | Direct response and extra texture |
|---|---|---|---|
| Unlit / 0 | Deferred rejection; switch default 1170–1171 | None for direct light | Zero diffuse/specular/transmission; no texture. Emissive belongs to BasePass/composition. |
| DefaultLit / 1 | [DefaultLitBxDF:212](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:212), 212–293 | None | Lambert diffuse plus GGX specular; no texture. |
| Subsurface / 2 | [SubsurfaceBxDF:716](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:716), 716–750 | SubsurfaceColor, Opacity, GBufferAO; subsurface distance uniform and shadow transmittance | DefaultLit plus view-dependent in-scatter/wrapped backscatter, absorption hue adjustment; no texture. |
| PreintegratedSkin / 3 | [PreintegratedSkinBxDF:1051](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:1051), 1051–1061 | SubsurfaceColor, Opacity | DefaultLit plus skin LUT transmission; **View.PreIntegratedBRDF** required. |
| ClearCoat / 4 | [ClearCoatBxDF:358](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:358), 358–564 | ClearCoat amount, coat roughness, optional decoded bottom normal; original top normal remains available | Two GGX layers, refraction/Fresnel attenuation and metallic absorption; no texture. |
| TwoSidedFoliage / 6 | [TwoSidedBxDF:845](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:845), active branch 941–953 | SubsurfaceColor | DefaultLit plus wrapped back-facing GGX-shaped transmission; no texture. |
| Cloth / 8 | [ClothBxDF:674](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:674), 674–712 | FuzzColor, Cloth weight | Lambert diffuse with GGX/inverse-GGX specular blend; transmission zero; no texture. |

Physical fields remain Schema-owned. Ordinary lit inputs derive `DiffuseColor=BaseColor*(1-Metallic)` and `SpecularColor=lerp(0.08*Specular,BaseColor,Metallic)`: [DeferredShadingCommon.ush:1145](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:1145), [ComputeF0:188](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingCommon.ush:188), [DielectricSpecularToF0:141](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingCommon.ush:141). `ExtractSubsurfaceColor` squares stored D.rgb at [DeferredShadingCommon.ush:1184](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:1184). When a Falcor codec already exposes decoded subsurface/fuzz color, Lighting must not square it again.

## 3. Portable algorithm details

### DefaultLit

[DefaultLitBxDF:212](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:212) zeros all outputs and only evaluates its diffuse/specular lobes when `AreaLight.NoL>0`. It uses the area-light context and `SphereMaxNoH`, then `NoV=saturate(abs(NoV)+1e-5)`. The isotropic [SpecularGGX:179](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:179) uses roughness to the fourth power, area energy normalization, GGX distribution, approximate joint Smith visibility, and Schlick Fresnel.

For the zero-size, energy-off, Lambert profile:

- Diffuse is `incidentRGB * NoL * DiffuseColor / PI`.
- GGX distribution is `a2 / (PI * square((NoH*a2-NoH)*NoH+1))`, `a2=roughness^4`: [BRDF.ush:311](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:311).
- Visibility is `0.5 / (NoL*(NoV*(1-a)+a) + NoV*(NoL*(1-a)+a))`, `a=sqrt(a2)`: [Vis_SmithJointApprox:373](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:373).
- Fresnel is `saturate(50*SpecularColor.g)*Fc + (1-Fc)*SpecularColor`, `Fc=(1-VoH)^5`: [F_Schlick:403](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:403). Replacing the green-channel low-F0 suppression with unconditional F90=1 changes UE's result.
- Specular is incident RGB times NoL, distribution, visibility, Fresnel.

[Init:24](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:24) forms half-vector dot products through `rsqrt(2+2*VoL)`. Exact opposing directions and zero roughness need an explicit supported input domain or a documented numerical policy. A mathematically similar GGX implementation is not automatically numerically identical.

The `MATERIAL_ROUGHDIFFUSE` alternative uses `Diffuse_GGX_Rough` and the area-light diffuse microreflection weight. The anisotropic branch requires the selective mask, tangent, anisotropy, anisotropic distribution and visibility. Neither is enabled by the proposed first profile.

### Subsurface

The active [SubsurfaceBxDF:716](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:716) starts from DefaultLit and adds transmission:

```text
inScatter = saturate(dot(L,-V))^12 * lerp(3,0.1,opacity)
wrapped = saturate(dot(N,L)/1.5 + 0.5/1.5)^1.5 * (2.5/1.5)
backScatter = AO * lerp(1,wrapped,opacity) / (2*PI)
transmission = incidentRGB * lerp(backScatter,1,inScatter)
             * lerp(transmittedColor,subsurfaceColor,shadowTransmittance)
```

The source does not saturate `inScatter` after its opacity-dependent multiplier; the lerp may extrapolate. A “cleanup” clamp changes its algorithm.

The local source's `transmittedColor` is significant: convert the subsurface color to extinction at `View.SubSurfaceColorAsTransmittanceAtDistanceInMeters`, evaluate transmittance at one meter, retain that result's HSV hue/saturation, and restore the original subsurface color's HSV value (max RGB, not physical luminance). [ParticipatingMediaCommon.ush:170](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ParticipatingMediaCommon.ush:170) clamps input transmittance to [1e-12,1] and thickness to at least 1e-12. The HSV helpers are at [ColorSpace.ush:235](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ColorSpace.ush:235) and 251. This is portable arithmetic, with one external scalar and a shadow term.

[SceneRendering.cpp:1976](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SceneRendering.cpp:1976) reads the intentionally misspelled CVar `r.SSS.SubSurfaceColorAsTansmittanceAtDistance`, clamps it to [0.05,1], and uses 0.15 if the CVar is absent. Unshadowed initialization gives `Shadow.TransmittanceOrOpticalThickness=1`; then the final color blend selects the original subsurface color. General shadow support still requires the absorption branch.

### PreintegratedSkin

[ShadingModels.ush:1058](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:1058) samples the skin integration texture at:

```text
uv = (saturate(dot(N,L)*0.5+0.5), 1-opacity)
transmission = incidentRGB * SampleLevel(skinLUT, uv, 0).rgb * subsurfaceColor
```

It does not multiply that transmission by saturated front-side NoL. A pass-wide “NoL <= 0 => zero” early-out would erase valid transmission in this model, Subsurface, and Foliage. DefaultLit's own lobe guard is narrower.

The skin LUT is not reconstructible from the GBuffer alone and is not interchangeable with the environment split-sum `PreIntegratedGF` texture in [BRDF.ush:586](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:586). It is also separate from SubsurfaceProfile's profile textures and screen-space SSS infrastructure.

### TwoSidedFoliage

The code under `#if 0` beginning at [ShadingModels.ush:849](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:849) is inactive SGGX experimentation. The active `#else` at [line 941](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:941) starts from DefaultLit and computes:

```text
wrapNoL = saturate((-dot(N,L)+0.5)/(1.5*1.5))
scatter = D_GGX(0.6*0.6, saturate(-dot(V,L)))
transmission = incidentRGB * wrapNoL * scatter * subsurfaceColor
```

The active BxDF does not read opacity or GBufferAO for this transmission, despite sharing Subsurface's encoded color/opacity storage. Other deferred shadow setup may still use CustomData.a, so this does not prove opacity is irrelevant to a complete engine rendering.

### Cloth

[ClothBxDF:674](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:674) uses `cloth=saturate(CustomData.a)`. Its first specular term is ordinary GGX (or rect LTC in that separate profile). The second uses [D_InvGGX:685](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:685), [Vis_Cloth:692](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:692), and Schlick with decoded FuzzColor. It blends the two specular terms by cloth weight, leaves diffuse Lambert, and returns zero transmission.

The local legacy shader does **not** use `D_Charlie` for this fuzz lobe. The mobile visibility saturation at line 696 is excluded from the PC profile. Energy-preservation weighting of diffuse follows the blend when energy conservation is enabled.

### ClearCoat

[ClearCoatBxDF:358](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:358) clamps the coat roughness to at least 0.02 and uses a top-layer F0 of 0.04 (IOR 1.5). Amount and roughness are CustomData.x/y. It computes separate top and bottom responses, adjusts/restores sphere angular extent for the two roughnesses, and handles base anisotropy only under its separate capability.

Bottom-normal handling is a caller contract: [DeferredLightingCommon.ush:325](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:325) reconstructs N from the encoded octahedral delta in D.a/D.z, while retaining `GBuffer.WorldNormal` as the top normal. The BxDF sets Nspec to that original top normal. Its bottom branch updates the context using the separate N at [ShadingModels.ush:448](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:448). A decoded surface interface should retain both normals and avoid repeating the storage decode in the BxDF.

[RefractClearCoatContext:337](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:337) uses the polynomial helper at 325 and eta=1/1.5 to refract dot products. Bottom NoV/NoL are clamped to [0.001,1]. The top Fresnel attenuation coefficient is squared; with energy enabled it comes from energy preservation, otherwise from 1-F.

[SimpleClearCoatTransmittance:733](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:733) is analytic. It uses Metallic as coverage; extinction derives from `max(BaseColor/PI,0.0001)`; path length depends on reciprocal refracted NoL/NoV. No separate absorption texture is required. The diffuse lobe blends uncoated and Fresnel/absorption-attenuated responses. The lower specular term blends Fresnel choices while reusing refracted D/V, as the source comments at [ShadingModels.ush:557](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:557) explicitly describe.

Do not claim both specular lobes receive identical multiple-scattering compensation: the top lobe explicitly applies `ComputeEnergyConservation(EnergyTermsCoat)`; bottom energy terms at line 505 feed diffuse preservation, but the appended bottom specular at lines 518–561 does not apply the bottom conservation multiplier. `Lighting.Transmission` remains zero; “Transmission” inside this function is attenuation between its layers.

## 4. External resources and feature branches

| Branch / model | Required external resource or parameter | Source evidence and portability |
|---|---|---|
| Unlit; energy-off, non-rect DefaultLit / ClearCoat / Foliage / Cloth | No BRDF texture | Arithmetic described above. Incident light, camera and shadows are separate scene inputs. |
| Subsurface | Subsurface distance scalar and shadow transmittance | Analytic extinction/HSV path; no profile or skin texture. |
| PreintegratedSkin | RGB skin LUT, bilinear clamp sampler, mip 0 | [SceneRendering.cpp:2225](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SceneRendering.cpp:2225) binds GEngine->PreIntegratedSkinBRDFTexture to View.PreIntegratedBRDF. [SceneManagement.cpp:1282](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/SceneManagement.cpp:1282) initializes a white fallback and bilinear-clamp sampler. A white fallback is not evidence of correct skin shading. |
| Energy-enabled lit GGX lobes | View.ShadingEnergyGGXSpecTexture, bilinear clamp | [GGXEnergyLookup:70](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingEnergyConservation.ush:70), UV=(NoV,roughness), mip 0. |
| Energy-enabled Cloth | GGX LUT above plus View.ShadingEnergyClothSpecTexture | [ClothEnergyLookup:119](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingEnergyConservation.ush:119), same UV/sampler convention. |
| Rect GGX integration | View.GGXLTCMatTexture and View.GGXLTCAmpTexture; rect geometry and optional emitter texture | [GetRectLTC_GGX:262](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/RectLight.ush:262); UV=(roughness,sqrt(1-NoV))*63/64+0.5/64. [RectLightIntegrate.ush:59](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/RectLightIntegrate.ush:59) also samples emitter texture into FalloffColor. |
| Finite sphere/capsule | Radius, soft radius, length, positions and attenuation parameters | Portable area math, but cannot be reduced to a zero-size point response without changing the reference. See [CreateAreaLight:36](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/CapsuleLightIntegrate.ush:36). |
| Anisotropic DefaultLit / coat base | World tangent, anisotropy, selective bit and corresponding codec capability | Extra decoded material inputs/storage. Top clearcoat remains isotropic. |

The skin asset is configured at [BaseEngine.ini:167](E:/ue/engine/UnrealEngine/Engine/Config/BaseEngine.ini:167) as `/Engine/EngineMaterials/PreintegratedSkinBRDF.PreintegratedSkinBRDF` and loaded by [UEngine::ConditionallyLoadPreIntegratedSkinBRDFTexture:3879](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/UnrealEngine.cpp:3879). Its local package hash is included below. This research did **not** extract GPU texels or establish runtime dimensions, format, sRGB view state, mip contents, cooking transformations, or equivalence of the separate `PreintegratedSkinBRDF_Low` asset. Those properties must accompany a reusable imported LUT contract; package bytes alone are insufficient.

Energy conservation is selected by [ShadingEnergyConservation.ush:7](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingEnergyConservation.ush:7). In the ordinary non-Substrate profile it is off unless the legacy project material setting enables it (and the platform supports independent samplers). The file chooses 0 or 1, rejects an externally predefined `USE_ENERGY_CONSERVATION`, and contains analytic mode-2 fits that are not selected by that macro logic. Mode 2 is not an exact resource-free replacement for the normal LUT branch.

At mode 0, [ComputeGGXSpecEnergyTerms:66](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingEnergyConservationTemplate.ush:66) produces W=1; [ComputeEnergyPreservation:126](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingEnergyConservationTemplate.ush:126) returns 1. Cloth also produces W=1. At mode 1, conservation/preservation use table energy terms; development shaders additionally honor View runtime flags at lines 55 and 130. Both compile profile and those flags must therefore be recorded when enabled.

The CPU default legacy project CVar is zero at [ShadingEnergyConservation.cpp:71](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ShadingEnergyConservation.cpp:71). Resource creation can use runtime tables or precomputed engine assets; [lines 581–584](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ShadingEnergyConservation.cpp:581) identify GGXReflectionEnergyTexture and SheenEnergyTexture. Asset names appear at [BaseEngine.ini:174](E:/ue/engine/UnrealEngine/Engine/Config/BaseEngine.ini:174). CPU format/capability selection begins at [ShadingEnergyConservation.cpp:441](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ShadingEnergyConservation.cpp:441); one cannot infer every runtime table's format from a CVar comment. View bindings are at [SceneRendering.cpp:2308](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SceneRendering.cpp:2308).

GGXGlass, GGXMaxSpec, diffuse-energy textures, the environment PreIntegratedGF, profile textures, and Sheen LTC are not minimum direct resources for these seven models in the stated profile. For example, diffuse-energy sampling is commented out at [ShadingEnergyConservation.ush:137](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingEnergyConservation.ush:137); GGXMaxSpec belongs to additional local model paths. Resource requirements should follow active call paths.

## 5. Accumulation and composition contract

[AccumulateDynamicLighting:316](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:316) uses V=-CameraVector; establishes the model's shading normal; resolves light attenuation; initializes separate surface and transmission shadows; and dispatches rect/capsule integration. Unshadowed terms start as SurfaceShadow=AmbientOcclusion, TransmissionShadow=1, TransmittanceOrOpticalThickness=1 at lines 346–350.

After the BxDF, lines 408–410 apply SpecularScale to specular and DiffuseScale to both diffuse and transmission. Lines 416 and 429 then accumulate reflected and transmitted light with **different shadow factors**. Returning diffuse/specular/transmission separately in `UEModelLighting` preserves this behavior. Applying a single outer NoL or a single surface shadow to all three is incorrect for the transmitting models.

[DeferredLightPixelShaders.usf:454](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightPixelShaders.usf:454) accumulates the direct radiance, then multiplies output RGBA by pre-exposure at line 464; [GetExposure:132](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightPixelShaders.usf:132) returns View.PreExposure. The existing Falcor BasePass SceneColor contract is emissive times pre-exposure. Composition should therefore add pre-exposed direct RGB once to that SceneColor, or decode both terms into a declared common domain before composing. Adding emissive per light or exposing an already exposed BasePass value again is wrong.

A direct raw-light input may supply normalized directions, resolved incident RGB, and resolved shadow terms. If so, its descriptor must explicitly state units/basis, attenuation ownership, normal orientation, minimum roughness, exposure domain, and which UE stages have already been evaluated. Such an input is a useful bounded interface; it does not itself provide shadow maps, light functions, IES profiles, lighting-channel filtering, static/indirect lighting, fog, or final tonemapping. Alpha requires a separate contract because the UE light accumulator may store non-specular luminance there.

## 6. Schema registration and consumer capability

The pre-extension generator rejects unknown top-level, codec, model and consumer keys. At the inspected baseline, validation is in [generate_schema.py:120](E:/Project/falcor/Falcor-m0/scripts/ue_legacy/generate_schema.py:120); per-model consumer requirements are checked at line 237. The following is the agreed extension design, not a claim that the baseline already accepts these keys:

```json
{
  "lighting": {
    "programs": {
      "DefaultLit": {
        "file": "Lighting/DefaultLit.slangh",
        "contract": "Lighting/DefaultLit.lighting.json",
        "entry": "ueShadeDefaultLit",
        "required_fields": {
          "normalEncoded": "float3",
          "baseColor": "float3",
          "metallic": "float",
          "specular": "float",
          "roughness": "float"
        }
      }
    },
    "models": {
      "DefaultLit": "DefaultLit"
    }
  }
}
```

The illustration is only the optional section for a one-model schema. When enabled, the mapping must cover **every model registered in that schema**, and every target must be a declared program. A DefaultLit/Unlit Lighting schema should register those two models; it should not register seven models while silently falling back for five.

A companion source contract is:

```json
{
  "contract_version": 1,
  "entry": "ueShadeDefaultLit",
  "required_fields": {
    "normalEncoded": "float3",
    "baseColor": "float3",
    "metallic": "float",
    "specular": "float",
    "roughness": "float"
  },
  "required_resources": [],
  "profile": {
    "energy_conservation": 0,
    "rough_diffuse": 0,
    "anisotropy": 0,
    "rect_light": 0
  }
}
```

The current contract supports exactly integer zero for these known profile capabilities. Future implementations can explicitly extend accepted profiles. Schema need not duplicate those capability fields; normalized contract metadata supplies native preflight. Skin's required resource identifier must be declared even in the all-zero profile. Resolved light/shadow input requirements belong to the common pass/context contract, while model-specific resources belong to model programs.

Recommended validation and generation behavior:

1. Require a Lighting consumer whenever lighting registration is present. Check its common/per-model logical fields, program field existence and types, and each mapped model's valid fields. Consumer coverage must include the program's requirements. A full composition consumer may require modelID and sceneRadiance globally; Unlit must not be forced to claim a normal. Required fields describe storage validity; they are not BRDF formulas.
2. Snapshot lighting program files and recursive local includes/contracts beneath the same permitted codec root, using the existing path containment, cycle and file checks. Keep contracts synchronized with entry and required_fields declarations. Reject unknown profile/resource declarations and missing resources before clearing or mutating output.
3. Preserve a separate program for each distinct lighting model even when codecs are shared. Runtime mapping is from the schema's model registry to lighting entry, never from codec name to BxDF.
4. Place `UEModelLighting`, `UEDirectLightingContext` and shared arithmetic in `LightingCommon.slangh`; emit source after existing codec math and generate `ueShadeModel(UESurface,UEDirectLightingContext)` plus `ueIsLightingSupported(uint)`. The dispatch default returns zero so a caller can diagnose an unknown ID. `ueIsLightingSupported` means compiled registration, not that current resource bindings are valid.
5. Put enabled registration/dispatch identity into LayoutHash. Compute an independent lighting_hash from recursive lighting source/contract identity; do not add lighting source bytes to CodecHash. Full generated shader identity/generation must change when lighting code changes.
6. With no lighting key, preserve old header and metadata bytes, hashes and generator_version exactly. Do not insert empty lighting objects, optional comments, helper stubs, additional source dependencies, or unconditional version changes. This needs a byte comparison against the existing DefaultLit baseline.
7. Reject missing model mappings, missing required fields/resources, contract mismatch, unsupported profile values and unsafe include paths. Test stable normalization and mutation-sensitive lighting hashes independently of CodecHash.

These checks establish a declared capability and a reproducible generated program. They do not prove the shader's math matches its contract; source review and numeric/capture validation remain separate.

## 7. Evidence and remaining validation

The portable algorithms, active compile branches and minimum resource bindings above are source-backed. Exact UE image equivalence remains unverified. The next validation should exercise each model with a common decoded surface, front/back lights, grazing view, roughness/amount endpoints, separate surface/transmission shadows, and ClearCoat dual normals. A CPU oracle should follow the actual selected UE equations; GPU checks should include the actual skin LUT sampling contract when Skin is enabled.

Profile-off behavior must be tested explicitly; a successful DefaultLit image does not validate Subsurface transmission, Skin sampling, Foliage wrap, Cloth fuzz, ClearCoat refraction, or Unlit rejection. For any enabled resource branch, preserve actual texture contents, dimensions, format/view, sampler and compile/runtime flags with the pipeline identity.

The report's only authored artifact is this Markdown file. Source and asset reads/hashes are read-only; the skin package was hashed, not decoded. File links and source line bounds were checked after writing.

## 8. SHA-256 source manifest

Paths in this table are relative to `E:/ue/engine/UnrealEngine`. Hashes cover raw bytes, including line endings. The skin package is an asset identity, not a texel-content validation.

| Path | Bytes | SHA-256 |
|---|---:|---|
| `Engine/Build/Build.version` | 187 | `29f7a3e61c24327147037ee15928d1bd1603fb65bcd19058e8381e26a12d38bd` |
| `Engine/Shaders/Private/ShadingModels.ush` | 44108 | `74fa44bc4633e695db936b25909c1cbab3d2a85cb768f184c92862eb136e810a` |
| `Engine/Shaders/Private/BRDF.ush` | 32031 | `0de81cc25c9b035a77aeb0e2f1be3e730c0f117f9250fe365104f30119b5e906` |
| `Engine/Shaders/Private/ShadingCommon.ush` | 10345 | `12e9d8e9989e7f6935f739f4c446e423358d9fab1ad56ef59a90ee2033050fd8` |
| `Engine/Shaders/Private/DeferredShadingCommon.ush` | 47446 | `bd4974524abfb1229fa4abf790a57325080cc0ea809b942c7ac43b1b0ebc5791` |
| `Engine/Shaders/Private/DeferredLightingCommon.ush` | 24838 | `d3bcd5cf9c36cab57c281f6cad447816891836e3c05a67c8808cbb9ad83e2c46` |
| `Engine/Shaders/Private/DeferredLightPixelShaders.usf` | 27277 | `ea29963960fbc0fe3b2b07418c780652037a641f7dc672565f7c8c05ff307df5` |
| `Engine/Shaders/Private/ShadingEnergyConservation.ush` | 9538 | `d7c107e45eb4f5684c04afbe4905b9342473af257dbee1e468ea39f067d9ea2a` |
| `Engine/Shaders/Private/ShadingEnergyConservationTemplate.ush` | 4584 | `735bc2c6c16471db7f2a623df9fc520ca2ca0d810b382f70eb951af94aa4604c` |
| `Engine/Shaders/Private/ParticipatingMediaCommon.ush` | 18430 | `3b5f52a05c9981d4669f7f8a84a7458e182c9a9cf1fb19a4f17edec865d6384f` |
| `Engine/Shaders/Private/ColorSpace.ush` | 8171 | `ed93b03b354cba139274d8de0b91a1a4ddefdab27fc16d7bae140ccfdf6839a7` |
| `Engine/Shaders/Private/AreaLightCommon.ush` | 1694 | `259c3f81da7c5b2c22176949d838113b74059d310fa4dcce56995955227f08a7` |
| `Engine/Shaders/Private/CapsuleLightIntegrate.ush` | 8436 | `ab9b14123ead4faec6604000a05abbcb3ea1ab832b9cdea2dab6772a2ca5a591` |
| `Engine/Shaders/Private/RectLightIntegrate.ush` | 6655 | `3e1a7ea5661c0aa464c72cbb58d80c88b14c08209271f2ec4ac1764a77e4886e` |
| `Engine/Shaders/Private/RectLight.ush` | 24577 | `b2ce43c186e92877b6bed31c551143066b0bf865394b71d741d5bcac5e8dfb02` |
| `Engine/Source/Runtime/Renderer/Private/SceneRendering.cpp` | 282284 | `2eb88532f231849cfeda84d690b62bb8aa996570accfb95068696753870b7aa8` |
| `Engine/Source/Runtime/Renderer/Private/ShadingEnergyConservation.cpp` | 28955 | `8825f9d5c7028ab6ab070a597fe5dc153c6c731ffc109b6c1bdca17badae9e21` |
| `Engine/Source/Runtime/Engine/Private/SceneManagement.cpp` | 68254 | `8fe3c6a25ff160bbcf1fd152edb4ae191d9bbb31e5d9baca82f2a5dc546c4d95` |
| `Engine/Source/Runtime/Engine/Private/UnrealEngine.cpp` | 698948 | `fbc122433b3fdfe47b1f4dd0f246eebf0e14b7a957676b5a11e02b031c654109` |
| `Engine/Config/BaseEngine.ini` | 255207 | `b876e27ea1372b43d9aafd7b78f8e6ae3cb13f48f638618308dbbe1af78232b8` |
| `Engine/Content/EngineMaterials/PreintegratedSkinBRDF.uasset` | 23348 | `7fc4088ba8e955bb55aa36af17c2f2c4438e57a5f87f7cb026609ca1d1c64891` |

