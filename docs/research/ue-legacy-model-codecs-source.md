# UE legacy model GBuffer codecs: local source findings

Research date: 2026-09-09. Source root: `E:/ue/engine/UnrealEngine`. This is source analysis for the Falcor UE legacy pipeline, not an implementation or a new GPU/capture equivalence result.

This report covers the implementation's **seven registered models**: the existing DefaultLit reference plus Unlit, Subsurface, PreintegratedSkin, ClearCoat, TwoSidedFoliage, and Cloth. All seven have source-backed GBuffer encode/decode contracts that fit the existing A–D layout under the profile below. Subsurface / PreintegratedSkin / TwoSidedFoliage share one storage codec; Cloth shares their color transform but stores cloth weight instead of opacity. New-model lighting remains separate work. ClearCoat bottom-normal encoding fits in D and can accept a resolved world-space normal without requiring a tangent asset. Actual anisotropy requires additional storage and is outside this layout.

Two compatibility details require explicit handling: Unlit writes a zero model/flags byte, including a zero skip-velocity bit; and this local UE source has a stale `<< 4` in its generic decoder despite using a five-bit model / three-bit flag layout elsewhere. An implementation should preserve the agreed five-plus-three physical format and record that source inconsistency instead of silently copying it.

## 1. Source version and bounded contract

[Build.version](E:/ue/engine/UnrealEngine/Engine/Build/Build.version:1) reports UE **5.8.1**, `Changelist=0`, `CompatibleChangelist=55116800`, `BranchName="UE5"`. The shaders and generator include local modifications; these findings apply to the hashed files in section 10, not to an assumed stock release.

The initial codec profile is:

- PC deferred, non-Substrate, ordinary opaque geometry. The source also supports masked deferred materials, but coverage evaluation must remain a separate material/raster stage.
- GBuffer A `RGB10A2Unorm`, B `BGRA8Unorm`, C `BGRA8UnormSrgb`, D `BGRA8Unorm`; no integrated velocity or tangent target; static lighting disabled.
- `GBUFFER_HAS_DIFFUSE_SAMPLE_OCCLUSION=0`; initial material AO is 1. Disable bent-normal/specular-occlusion modifications that would subsequently change GBuffer AO.
- No anisotropy, first-person flag, forced-simple-shading / Substrate fast path, Nanite analytic SGGX, or derivative normal-curvature-to-roughness processing in the initial profile.
- Material inputs are resolved values at the codec boundary, with identity development overrides and no DBuffer changes unless the upstream evaluation has already incorporated them.
- For all seven registrations, the implemented initial SceneColor contract is **emissive-only**: resolved emissive times pre-exposure, alpha zero. UE equivalence requires no fog and no contributing sky, static, or other indirect BasePass lighting. `ALLOW_STATIC_LIGHTING=0` alone does not establish this condition, especially for Subsurface, PreintegratedSkin, and Cloth. The current Falcor SceneColor target is `RGBA16Float`; the UE layout generator's nominal lighting format is not evidence that every engine runtime uses that same SceneColor format.

These are explicit profile limits, not claims that the corresponding UE features cannot be supported later. [BasePassCommon.ush:43](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassCommon.ush:43) gates the GBuffer on SM4+, solid/masked materials, and deferred shading. Its custom-data and static-shadow-target conditions start at lines 46 and 50. [GBufferInfo.cpp:426](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/RenderCore/Private/GBufferInfo.cpp:426) selects the five-target no-velocity/no-tangent layout; its target definitions start at line 458.

## 2. Active encoding path and physical layout

The active BasePass calls **generated `EncodeGBufferToMRT`** at [BasePassPixelShader.usf:2374](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2374), inside `#if 1`. The older `EncodeGBuffer` call remains in the inactive `#else` at [line 2431](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2431). The older helper is useful corroboration for readable equations, but is not the active encoder. The generator emits `EncodeGBufferToMRT` at [ShaderGenerationUtil.cpp:807](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderGenerationUtil.cpp:807).

All channel names below mean logical shader RGBA. A raw BGRA resource byte dump must be mapped to those logical channels before applying these equations. C applies the RTV/SRV sRGB transfer to RGB; its alpha remains linear. D is linear UNORM and must never receive that color transfer.

| Target | Common lit meaning before attachment conversion | Model-specific behavior |
|---|---|---|
| A.rgb | `normalUE * 0.5 + 0.5` | Unlit clears A and has no valid stored surface normal. |
| A.a | Per-object two-bit value, expressed as a normalized float | Unlit clears it. |
| B.r / g / b | Metallic / dithered specular / roughness | ClearCoat modifies base roughness. Unlit clears them. |
| B.a | Five-bit model ID plus three physical selective-output flags | Unlit writes byte 0. |
| C.rgb | Linear BaseColor supplied to an sRGB attachment | Unlit clears it. |
| C.a | GBuffer AO for this profile | Unlit clears it; that numeric zero is not meaningful Unlit material AO. |
| D.rgba | Four model-specific `CustomData` components | Required by IDs 2, 3, 4, 6, 8; semantically invalid for Unlit and unused by DefaultLit. |

The layout comes from [GBufferInfo.cpp:459](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/RenderCore/Private/GBufferInfo.cpp:459) for target formats and C's sRGB flag, [line 529](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/RenderCore/Private/GBufferInfo.cpp:529) for B material fields, [line 549](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/RenderCore/Private/GBufferInfo.cpp:549) for model/flag bit widths, [line 560](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/RenderCore/Private/GBufferInfo.cpp:560) for C RGB, and [line 633](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/RenderCore/Private/GBufferInfo.cpp:633) for all four D channels. Tangent and anisotropy use a separate target, as shown at [line 623](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/RenderCore/Private/GBufferInfo.cpp:623).

Attachment export is also permutation-dependent. [SetStandardGBufferSlots](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderGenerationUtil.cpp:2018) marks ordinary A/B/C fields; the [Unlit branch](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderGenerationUtil.cpp:2114) forces SceneColor usage but does not request CustomData. The [lit-model branches](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderGenerationUtil.cpp:2127) explicitly request CustomData for Subsurface, PreintegratedSkin, ClearCoat, and TwoSidedFoliage; [the Cloth branch](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderGenerationUtil.cpp:2163) does likewise. Target usage controls exported `PIXELSHADEROUTPUT_MRT*` defines at [line 2343](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderGenerationUtil.cpp:2343). A zero assignment to the logical D output therefore does not establish that an Unlit-only shader physically exports D. A common Falcor multi-model layout can write a canonical zero for Unlit D, while still marking its contents invalid for material interpretation.

## 3. Five-bit model IDs and selective flags

[ShadingCommon.ush:19](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingCommon.ush:19) defines the relevant IDs:

| Model | ID | B.a byte in the initial no-velocity profile |
|---|---:|---:|
| Unlit | 0 | `0x00` |
| DefaultLit, existing reference | 1 | `0x81` |
| Subsurface | 2 | `0x82` |
| PreintegratedSkin | 3 | `0x83` |
| ClearCoat | 4 | `0x84` |
| TwoSidedFoliage | 6 | `0x86` |
| Cloth | 8 | `0x88` |

The local mask is `SHADINGMODELID_MASK=0x1f`. Physical selective flags occupy bit 5 for anisotropy, bit 6 for skip-precomputed-shadow (or the first-person alias when static lighting is off), and bit 7 for skip-velocity. The declarations extend beyond the original sixteen-model range; this is not a four-bit-ID layout.

Using physical flag bits, the contract is:

```text
packedByte = (modelID & 0x1f) | (physicalFlags & 0xe0)
B.a = packedByte / 255

packedByte = uint(round(sampledB.a * 255))
modelID = packedByte & 0x1f
physicalFlags = packedByte & 0xe0
compactFlags = physicalFlags >> 5
```

The readable pack/unpack helpers implement the physical-mask convention at [DeferredShadingCommon.ush:295](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:295). The generated encoder instead receives a compact mask: [BasePassPixelShader.usf:877](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:877) defines offset 5 and the flag-selection logic; [line 1209](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1209) shifts physical flags right by 5 and optionally inserts first-person. Unsupported legacy anisotropy is removed at [line 1222](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1222). The no-velocity lit profile obtains physical `0x80`; the later Unlit override replaces the entire byte with zero.

### Observed local decoder inconsistency

[GBufferHelpers.ush:403](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/GBufferHelpers.ush:403) correctly tests compact flags as `0x2` for precomputed shadows, `0x4` for velocity, and `0x1` for anisotropy. However, its final conversion at [line 478](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/GBufferHelpers.ush:478) retains an old four-plus-four comment and executes:

```text
Ret.SelectiveOutputMask = Ret.SelectiveOutputMask << 4
```

For example, compact skip-velocity `4` becomes physical `0x40`, while this tree's declarations, packing, and BasePass require `0x80`. This is an observed source inconsistency. The research does not modify UE or establish whether an existing captured shader executes that post-decode path. A Falcor codec targeting the agreed five-plus-three physical contract should reconstruct flags with `<< 5`, retain a regression test for it, and avoid claiming byte-for-byte equivalence to this erroneous final helper field. Material, normal, and CustomData decoding can be specified independently of that flag mismatch.

## 4. Shared lit fields and decoder semantics

[ShadingModelsMaterial.ush:27](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:27) copies normal, tangent, BaseColor, metallic, roughness, anisotropy, and model ID into `FGBufferData`; PC specular passes through `Dither8bits`. The GBuffer starts at zero at [BasePassPixelShader.usf:1146](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1146), then receives AO, per-object data, depth, and the model-specific assignments.

For the finite normalized material domain, PC specular dithering is:

```text
s = saturate(specular)
d = (InterleavedGradientNoise(pixelPosition, frameIndexMod8) - 0.5) * (1 / 255)
storedSpecular = saturate(s + d * isNonZero(s))
```

The noise call is at [BasePassPixelShader.usf:999](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:999), and the saturation/nonzero gate/scale are at [PackUnpack.ush:432](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/PackUnpack.ush:432). Zero specular stays zero. No corresponding custom-data dithering is applied by these model branches. Reuse the existing validated DefaultLit specular arithmetic and context rather than changing its floating-point operation order on the strength of a mathematically equivalent expression.

Normal encoding is affine, with no normalization in that helper: `encoded = N*0.5+0.5`, `decoded = encoded*2-1`; see [DeferredShadingCommon.ush:137](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:137) and [GBufferHelpers.ush:27](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/GBufferHelpers.ush:27). The generic decoder optionally normalizes afterward at [GBufferHelpers.ush:428](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/GBufferHelpers.ush:428). A codec must state whether its exposed normal is the raw affine result or the normalized result. Attachment quantization makes either an approximation to the original normal.

Per-object data is `(2*capsuleRepresentation + castContactShadow)/3`, from [SceneData.ush:514](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/SceneData.ush:514). BaseColor has identity shader encode/decode helpers at [DeferredShadingCommon.ush:192](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:192); the sRGB attachment performs the transfer, not an additional model-codec function.

Under both `ALLOW_STATIC_LIGHTING=0` and `GBUFFER_HAS_DIFFUSE_SAMPLE_OCCLUSION=0`, [BasePassPixelShader.usf:2378](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2378) writes `GenericAO=GBufferAO`. [GBufferHelpers.ush:414](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/GBufferHelpers.ush:414) decodes it as AO and sets indirect irradiance to 1. Static lighting being off alone is insufficient: diffuse-sample-occlusion mode repurposes that alpha channel. With no static lighting, precomputed shadow factors decode to 1 at [line 405](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/GBufferHelpers.ush:405). Bent-normal/specular occlusion can change AO earlier at [BasePassPixelShader.usf:1304](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1304), so the initial constant-AO profile must also constrain that stage.

The generic `FGBufferData` decoder keeps **encoded** CustomData for models with custom GBuffer data; see [GBufferHelpers.ush:394](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/GBufferHelpers.ush:394). Model-specific semantic extraction is a second operation. Common derived fields are `F0=lerp(0.08*specular, BaseColor, metallic)` and `DiffuseColor=BaseColor-BaseColor*metallic`; see [ShadingCommon.ush:141](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingCommon.ush:141), [line 188](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingCommon.ush:188), and [GBufferHelpers.ush:444](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/GBufferHelpers.ush:444). With anisotropy absent, the latter helper zeros tangent/anisotropy at line 472. Computing these common fields does not implement a model's lighting response.

## 5. Unlit: valid data, SceneColor, and coverage

The active encoder explicitly clears A, C, and the logical custom/shadow outputs for Unlit at [BasePassPixelShader.usf:2389](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2389). B is passed to [SetGBufferForUnlit](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:523), which sets B to zero and encodes `(UNLIT, selectiveMask=0)` into its alpha. This clears all material fields and **all flags**, even when the preceding lit-style mask calculation set skip-velocity.

The codec should expose model ID and SceneColor as valid Unlit data, together with separately established raster depth/coverage. Surface normal, BaseColor, metallic, specular, roughness, AO, per-object data, and CustomData are not meaningful Unlit material values in those cleared attachments. Numerically decoding zero A gives `(-1,-1,-1)` before optional normalization; presenting that as the actual surface normal would be incorrect. D may be unexported in an Unlit-only permutation, as explained in section 2.

For ordinary opaque non-sky Unlit with the stated no-fog/no-indirect/development-override profile:

```text
SceneColor.rgb = resolvedEmissive * preExposure
SceneColor.a = 0
```

The lit indirect block is excluded by `MATERIAL_SHADINGMODEL_UNLIT` at [BasePassPixelShader.usf:1327](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1327). Emissive is read at [line 1633](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1633), added at [line 1694](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1694), and written through the opaque light accumulator at [line 2337](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2337). [LightAccumulator.ush:109](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/LightAccumulator.ush:109) initializes its result alpha to zero; subsurface-profile accumulation is a separate condition. The final non-sky opaque output multiplies all four components by `View.PreExposure` at [BasePassPixelShader.usf:2484](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2484). Negative emissive is normally clamped by the getter unless the corresponding material option allows it; see [MaterialTemplate.ush:3750](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/MaterialTemplate.ush:3750).

Opaque opacity does not alpha-blend or multiply this emissive result. Material opacity-mask clipping/coverage occurs separately at [BasePassPixelShader.usf:987](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:987). A black Unlit pixel can cover geometry while having zero SceneColor and zero model/flags byte. Neither `modelID != 0` nor SceneColor alpha/RGB can be used as a geometry-validity test. Preserve the existing depth/coverage-based validity and allow ID 0 to be a supported model.

## 6. Subsurface, PreintegratedSkin, and TwoSidedFoliage

These models have identical CustomData storage, while retaining distinct IDs and lighting behavior. Their assignments are directly visible in [ShadingModelsMaterial.ush:47](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:47), [line 54](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:54), and [line 125](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:125):

```text
CustomData.rgb = sqrt(saturate(subsurfaceColor))
CustomData.a = opacity
```

The square-root helper is [DeferredShadingCommon.ush:204](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:204). Material subsurface RGB and opacity getters already saturate at [MaterialTemplate.ush:4107](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/MaterialTemplate.ush:4107) and [line 3916](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/MaterialTemplate.ush:3916), respectively. At a raw-surface boundary, explicitly retain those domain rules; the model assignment itself does not add a separate opacity clamp. Linear UNORM attachment conversion happens after the square root.

Semantic decode is:

```text
subsurfaceColor = sampledD.rgb * sampledD.rgb
opacity = sampledD.a
```

This is [ExtractSubsurfaceColor](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredShadingCommon.ush:1184). Do not square CustomData in the generic decoder and then square it again in semantic extraction. Do not sRGB-decode D. Quantization occurs in square-root space, so the decoded color is the square of the quantized value, not a separately quantized linear source color.

For all three models, **opacity 0 preserves the model ID**. The opacity-threshold conversion to DefaultLit at [ShadingModelsMaterial.ush:65](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:65) belongs to SubsurfaceProfile, ID 5, which is outside this task. It must not be copied into IDs 2, 3, or 6. Opacity is also distinct from a masked material's opacity-mask input.

The additional raw fields are `float3 subsurfaceColor` and `float opacity`, alongside the common lit fields. Define subsurface color at the resolved material boundary: BasePass applies the view diffuse override at [BasePassPixelShader.usf:1040](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1040), and DBuffer material processing can modify it at [line 1129](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1129). Either reproduce that evaluation upstream or constrain those operations to identity.

For TwoSidedFoliage, normal orientation is an upstream geometry/material evaluation issue. [MaterialTemplate.ush:4373](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/MaterialTemplate.ush:4373) distinguishes world-space normalization from conditional tangent-space/two-sided normal handling, and [line 4713](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/MaterialTemplate.ush:4713) computes facing signs. Do not introduce an unconditional normal flip solely because `modelID==6`. The codec receives the resolved normal. Nanite analytic SGGX can also add a foliage-specific output at [BasePassPixelShader.usf:2417](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2417), and is excluded from the unchanged A–D profile.

### Cloth: same color representation, different alpha meaning

[ShadingModelsMaterial.ush:139](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:139) assigns Cloth, ID 8, as `D.rgb=sqrt(saturate(subsurfaceColor))` and `D.a=saturate(clothWeight)`, where cloth weight comes from material CustomData0. Semantic decode squares D.rgb and returns D.a as cloth weight; opacity is not this alpha's meaning. Cloth weight zero preserves ID 8. The raw-surface fields are `subsurfaceColor` and `cloth` (the implementation's name for cloth weight), together with common lit inputs. BasePass resolves Cloth's subsurface RGB without the family diffuse override at [BasePassPixelShader.usf:1051](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1051). Its static/indirect-lighting caveat is traced in section 9; the GBuffer color transform alone is not the complete Cloth BasePass lighting calculation.

## 7. ClearCoat: two layers and optional bottom normal

The complete model assignment starts at [ShadingModelsMaterial.ush:91](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:91):

```text
D.r = saturate(clearCoat)
D.g = saturate(clearCoatRoughness)
baseRoughness = clamp(baseRoughness, 0, 254 / 255)
```

ClearCoat weight 0 still uses model ID 4. The base-roughness cap belongs to GBuffer encoding. By contrast, the `max(clearCoatRoughness, 0.02)` at [ShadingModels.ush:361](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:361) is a lighting/BxDF operation and should not be added to D.g encoding.

Ordering matters if geometric roughness AA is later enabled: [BasePassPixelShader.usf:1257](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1257) subsequently applies `max(baseRoughness, GeometricAARoughness)` and `max(D.g, GeometricAARoughness)`. The later base-roughness max can exceed the earlier `254/255` cap. The initial profile disables this derivative-dependent stage; a future implementation should represent its position in the pipeline explicitly.

### Bottom-normal modes and channel order

`CLEAR_COAT_BOTTOM_NORMAL` defaults to 0 in [Definitions.usf:228](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/Definitions.usf:228), but a shader permutation can enable it. The setting must be part of the codec configuration/signature. Material output presence is a separate condition.

| Bottom-normal mode | D.b | D.a | Semantic result |
|---|---|---|---|
| Feature disabled | 0 from initialized CustomData | 0 from initialized CustomData | Bottom normal equals supplied top normal. |
| Feature enabled, no material bottom-normal output | `128/255` | `128/255` | Neutral encoded delta; bottom normal follows decoded top normal, subject to arithmetic precision. |
| Feature enabled, explicit output | Encoded delta Y | Encoded delta X | Reconstruct an independent bottom normal. |

With an explicit output, [ShadingModelsMaterial.ush:104](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:104) computes:

```text
topOct = octEncode(topNormalUE)
bottomOct = octEncode(bottomNormalUE)
delta = (bottomOct - topOct) * 0.25 + 128 / 255
D.a = delta.x
D.b = delta.y
```

The logical pair is **D.(a,b)**, or `CustomData.(a,z)`, for X/Y. Treating D.b/a as X/Y would swap the bottom-normal components. No additional sRGB transfer or custom-data dithering is present.

Input conversion depends on the material normal convention. A tangent-space bottom-normal output is transformed by `MaterialParameters.TangentToWorld` and normalized at [line 108](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:108). A world-space output is used directly at [line 110](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:110), without another normalization in that branch. For operation-order matching, do not insert a normalization that the source did not perform. Require finite nonzero normal inputs at the resolved-surface boundary.

[GetClearCoatBottomNormal](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ClearCoatCommon.ush:5) reconstructs:

```text
if modelID == 4 and bottomNormalFeatureEnabled:
    bottomOct = (float2(sampledD.a, sampledD.b) * 4 - 512 / 255)
                + octEncode(decodedTopNormal)
    bottomNormal = octDecode(bottomOct)
else:
    bottomNormal = decodedTopNormal
```

Use the source arithmetic order for precision comparisons. The encoded difference uses the pre-quantized top normal, whereas decode adds the octahedral projection of the top normal reconstructed from A. Therefore this is an approximate two-normal round trip even before considering D's UNORM quantization. BasePass also uses the same reconstruction before its bent-normal/AO processing at [BasePassPixelShader.usf:1298](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1298).

The octahedral functions at [OctahedralCommon.ush:18](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/OctahedralCommon.ush:18) are:

```text
octEncode(N):
    xy = N.xy / dot(1, abs(N))
    if N.z <= 0:
        xy = (1 - abs(xy.yx)) * componentwiseSelect(xy >= 0, +1, -1)
    return xy

octDecode(o):
    N = float3(o, 1 - dot(1, abs(o)))
    t = max(-N.z, 0)
    N.xy += componentwiseSelect(N.xy >= 0, -t, +t)
    return normalize(N)
```

The `<= 0` lower-hemisphere branch and sign convention at zero are part of the contract. The enabled/no-output sentinel is specifically byte 128 in both channels, rather than an arbitrary approximation to 0.5. Feature-disabled zeros and feature-enabled neutral bytes must remain distinguishable through configuration.

Raw fields should add `clearCoat`, `clearCoatRoughness`, and optional `clearCoatBottomNormalUE`, with explicit output presence plus a feature-mode setting. A resolved world-space bottom normal lets the codec support the complete D representation before reconstructing tangent-space material graphs. A tangent basis is required upstream only when such a graph supplies a tangent-space output. This is separate from anisotropic lighting: actual tangent/anisotropy GBuffer storage requires the additional target described in section 2.

## 8. Raw-surface contract and implementation units

The shared [UESurface](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Codecs/Surface.slangh:6) retains BaseColor, normal, metallic, specular, roughness, emissive, AO, and model ID, and now carries the additional model fields below. Its encoding context supplies pre-exposure, pixel coordinates, frame index, primitive flags, and the dithering switch. These remain useful shared inputs.

| Model | Required additional surface data | Configuration / validity requirements |
|---|---|---|
| DefaultLit, existing reference | None beyond the common lit fields | ID 1; D is unused; existing validated common packing remains the reference. |
| Unlit | None for GBuffer material data; resolved emissive for initial SceneColor | ID 0 supported; flags forced to zero; raster coverage independent; cleared material fields invalid. |
| Subsurface | `float3 subsurfaceColor`, `float opacity` | ID 2; all four D channels valid. |
| PreintegratedSkin | Same subsurface fields | ID 3; same storage, distinct model registration. |
| TwoSidedFoliage | Same subsurface fields | ID 6; resolved normal includes material/facing evaluation; no analytic SGGX in initial profile. |
| ClearCoat | `float clearCoat`, `float clearCoatRoughness`, optional `float3 clearCoatBottomNormalUE` | ID 4; explicit bottom-normal feature and output-presence modes; tangent-space conversion handled upstream if needed. |
| Cloth | `float3 subsurfaceColor`, `float cloth` | ID 8; D.a stores cloth weight; separate indirect-lighting behavior is excluded from emissive-only SceneColor. |

All six lit registrations retain the common lit material inputs, including base roughness distinct from coat roughness. Keep source-resolved logical quantities in `UESurface`; attachment channels and bit ranges belong to the schema. Keep encoded `CustomData` distinguishable from extracted semantic fields in decoder APIs. This prevents accidental double extraction and makes model validity explicit.

Five codec implementation units cover the seven registrations without conflating model semantics:

1. **DefaultLit:** the existing reference and shared common lit field mathematics.
2. **Unlit:** model-specific flags/validity, cleared exported GBuffer channels, and the bounded emissive SceneColor path.
3. **Subsurface-family storage:** common lit encoding plus square-root color/opacity CustomData; separate registrations for IDs 2, 3, and 6.
4. **Cloth:** common lit encoding plus square-root color/cloth-weight CustomData for ID 8.
5. **ClearCoat:** common lit encoding plus coat fields, roughness ordering, and explicit bottom-normal modes selected by codec contract.

Sharing common lit packing and identical subsurface-storage helpers is supported by source. Registering these IDs as aliases of DefaultLit without their custom-data and validity rules is not a complete codec.

The current [DefaultLit schema](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Schemas/DefaultLit.json:9) disables all D write channels. Its [skipVelocity field](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Schemas/DefaultLit.json:21) is a global constant 1, and its [DefaultLit field-validity declaration](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Schemas/DefaultLit.json:35) assumes the common lit material fields. A multi-model schema must enable D, describe model-specific CustomData, and allow the Unlit flag override and valid-field set. The consumer must branch on those validity rules before requiring a normal/material/AO value. The existing [decode validity predicate](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/UELegacyDecode.cs.slang:46) already combines depth with supported-model membership; preserve that structure when registering ID 0.

## 9. Lighting boundary and evidence needed next

Source-backed GBuffer encoding/extraction is feasible for all seven registered models within the stated profile. It does not establish support for new models' final lighting, full material evaluation, indirect light, or all UE permutations. DefaultLit remains the existing reference, rather than a newly validated model in this source survey.

The lighting paths are observably different: [SubsurfaceBxDF](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:716) includes transmission math and this tree's local extinction/color changes; [TwoSidedBxDF](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:845) has its own transmission/SGGX behavior; [PreintegratedSkin](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModels.ush:1051) samples `View.PreIntegratedBRDF` with `(saturate(NdotL*0.5+0.5), 1-opacity)` and multiplies the subsurface color. A storage codec does not supply that LUT. ClearCoat uses a separate multilayer BxDF, including the lighting-only roughness rule cited above. Subsurface and PreintegratedSkin also add subsurface color to indirect diffuse at [BasePassPixelShader.usf:1332](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1332). Consequently, emissive-only SceneColor is a controlled initial setup for the lit models, not a general BasePass equivalence claim.

For Cloth, [ShadingModelsMaterial.ush:144](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ShadingModelsMaterial.ush:144) also executes `GBuffer.IndirectIrradiance *= 1-D.a`. That assignment alone does not establish an attenuation in the active BasePass's final stored irradiance: the caller initializes `FGBufferData` to zero before model assignment, then overwrites `GBuffer.IndirectIrradiance` from the separately computed local value at [BasePassPixelShader.usf:2371](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2371). In the no-static-lighting/no-diffuse-sample-occlusion profile, C.a stores AO regardless. For actual SceneColor, the non-Substrate Cloth branch adds `SubsurfaceColor * saturate(CustomData0)` to indirect diffuse color at [line 1341](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1341), calls the precomputed-indirect/sky evaluator at [line 1362](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1362), and accumulates its result at [line 1380](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1380). Static lighting disabled is therefore insufficient evidence that all indirect/sky contributions are zero. The unweighted Cloth addition around line 2023 is in a separate Substrate export path and should not replace this legacy branch.

Before claiming implementation completion, a useful validation sequence is:

1. Offline packing/extraction cases for all seven IDs and the full five-plus-three flag boundary, including Unlit's zero flags and the compact-flag conversion inconsistency.
2. Subsurface colors at 0/1, fractional values, and UNORM boundaries; opacity and cloth-weight 0/1 with ID retention; explicit linear-D versus sRGB-C handling.
3. ClearCoat weight 0, both roughness limits, disabled/enabled-default/enabled-explicit bottom-normal modes, byte-128 sentinels, asymmetric delta components, and lower-hemisphere/sign-boundary normals. Check expected quantization error using the decoded top normal.
4. GPU attachment-byte and semantic-decode comparisons against controlled UE reference materials/permutations, including a black-emissive Unlit surface with valid depth/coverage. Confirm actual MRT write masks and the selected decoder's normal-normalization policy.

No build, GPU run, capture mutation, UE edit, or codec implementation was performed for this report. Existing DefaultLit capture evidence can support reuse of unchanged common helpers; it does not by itself validate the newly described model branches. Lighting support should continue to be reported as unimplemented until its own source inputs, model functions, and rendering evidence exist.

## 10. Source fingerprint manifest

SHA-256 values identify the local files examined. Paths below are relative to `E:/ue/engine/UnrealEngine`; shader filenames are expanded under `Engine/Shaders/Private/`.

| Source file | SHA-256 |
|---|---|
| `Engine/Build/Build.version` | `29f7a3e61c24327147037ee15928d1bd1603fb65bcd19058e8381e26a12d38bd` |
| `Engine/Shaders/Private/ShadingCommon.ush` | `12e9d8e9989e7f6935f739f4c446e423358d9fab1ad56ef59a90ee2033050fd8` |
| `Engine/Shaders/Private/ShadingModelsMaterial.ush` | `0336e3f7d6dbf3557ce1448191f7dc00b9568379612067f2031ad66ebf0d1be3` |
| `Engine/Shaders/Private/DeferredShadingCommon.ush` | `bd4974524abfb1229fa4abf790a57325080cc0ea809b942c7ac43b1b0ebc5791` |
| `Engine/Shaders/Private/GBufferHelpers.ush` | `8db2f7821e9aa2e8a8a422360a69698d96a810c6950a4dc1157b4e3e3fc6fb7a` |
| `Engine/Shaders/Private/BasePassCommon.ush` | `27011c26c4ae069f98ceec24894eed32ff2419239cb4a11d3c530146d0a31094` |
| `Engine/Shaders/Private/BasePassPixelShader.usf` | `9a555efaafd5909e2c9c30861f6dcc5a246a96976f23040797b02ec5cc17e22b` |
| `Engine/Shaders/Private/PackUnpack.ush` | `9bd794cede44edadf6b1e7f86656faf49cfd39211cbd0b7225189ea520f03e17` |
| `Engine/Shaders/Private/OctahedralCommon.ush` | `694e2cc1a06d9820edf0c299c9406364609adac83131d5e78fddd65fbd70e0f5` |
| `Engine/Shaders/Private/ClearCoatCommon.ush` | `b895d4ee5430330d2c8f80466dd480cfaefaf53f7bbe534eb3d71f220cffd66c` |
| `Engine/Shaders/Private/MaterialTemplate.ush` | `2d237cc8c53a024341a6a3828a251a655fbc9a266c0a2d7ed7e244be90bf292d` |
| `Engine/Shaders/Private/LightAccumulator.ush` | `9f566d9cece2b2a7c2b4be13937cac2e0e4b480cfbe0a4797ecda71547b2ef82` |
| `Engine/Shaders/Private/ShadingModels.ush` | `74fa44bc4633e695db936b25909c1cbab3d2a85cb768f184c92862eb136e810a` |
| `Engine/Shaders/Private/Definitions.usf` | `893637dc21e437503ada28e846f2fe1c9becefeffc6ac5ae746180082a3aecc0` |
| `Engine/Shaders/Private/SceneData.ush` | `0aeeae950b54c2391af85d825ad2d7aab5757e660800abd3ff19813a65a54fda` |
| `Engine/Source/Runtime/RenderCore/Private/GBufferInfo.cpp` | `0d926149edb80bab0a1a49ac40f76ff29d65e80c55a599841b8e544ffe9411e9` |
| `Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderGenerationUtil.cpp` | `43f3ba128f896610a4f51d3d96e09c856b4d218e4092321a4b6fb539c61ba31d` |
