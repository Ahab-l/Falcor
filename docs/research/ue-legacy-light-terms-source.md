# UE ordinary deferred local-light and shadow terms

2026-09-09. Implementation: [LightTerms.slangh](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/Codecs/Lighting/LightTerms.slangh). Source root is `E:/ue/engine/UnrealEngine`, local Build.version 5.8.1. This is a bounded specialization for desktop ordinary directional/point/spot lights with static lighting disabled and contact-shadow length zero. The broader BRDF/capture provenance is recorded in [ue-legacy-direct-lighting-source.md](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-direct-lighting-source.md). No build/GPU result is claimed here.

## Caller interface and explicit rejection

`kUELightTypeDirectional=0`, `kUELightTypePoint=1`, `kUELightTypeSpot=2` are the portable ABI's light-kind constants. They are separate from material model IDs. `UELocalLightTerms` contains `float3 toLight; float mask;`. `UEShadowTerms` is supplied by the existing `LightingCommon.slangh`.

```text
bool ueTryGetLocalLightTerms(
    uint lightType, float3 positionCm, float3 lightPositionCm, float invRadius,
    float3 direction, float2 spotAngles, float falloffExponent, bool inverseSquared,
    out UELocalLightTerms terms)

bool ueTryGetShadowTerms(
    uint lightType, float sceneDepthCm, float4 precomputedShadowFactors,
    float4 shadowMapChannelMask, float2 distanceFadeMAD, uint shadowedBits,
    uint perObjectFlags, float4 sampledShadowMask, float sceneAO,
    float contactShadowLength, bool allowStaticLighting, out UEShadowTerms shadow)
```

The local function accepts point/spot only; the shadow function accepts all three kinds. Both return false for an unsupported type, and the shadow function returns false for `contactShadowLength!=0` or `allowStaticLighting=true`. Failure initializes the output to zero solely to make its state defined; the caller must diagnose false rather than render that result as accepted lighting. Native validation rejects these unsupported requests before dispatch. Finite parameters, valid radius/cones and nondegenerate geometry are caller requirements. No new epsilon or corrective clamps alter the UE equations.

## Local light mask

[DeferredLightingCommon.ush:246](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:246) sets `toLight=lightPosition-position`, `d2=dot(toLight,toLight)`, `L=toLight*rsqrt(d2)` and returns:

```text
inverseSquared: mask = square(saturate(1-square(d2*square(invRadius))))
otherwise:      mask = pow(1-saturate(dot(toLight*invRadius,toLight*invRadius)),falloffExponent)
spot:           mask *= square(saturate((dot(L,direction)-spotAngles.x)*spotAngles.y))
```

The noninverse power law and spot multiplier come from [DynamicLightingCommon.ush:20](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DynamicLightingCommon.ush:20) and [DynamicLightingCommon.ush:58](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DynamicLightingCommon.ush:58). The implementation keeps both source negations: the local caller passes `-direction` to the spot helper, which computes `dot(L,-spotDirection)`. Thus direction is the UE shader uniform direction, the negative of the emitting axis. `spotAngles=(cosOuterCone,1/(cosInnerCone-cosOuterCone))`. The caller derives `inverseSquared=(falloffExponent==0)` for radial lights as [LightDataUniforms.ush:33](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/LightDataUniforms.ush:33) does.

Positions share one translated UE centimeter space; `invRadius` is inverse centimeters. This is the radius/cone mask only. Desktop `1/(d2+1)` belongs to the separate capsule integration and must not be applied twice. The mobile-only extra reciprocal and the rect-facing branch are excluded. Source formulas for local lights are established from the actual local UE files; the E2655 directional capture does not independently validate point/spot numerical output.

## Shadow mask decoding and composition

The caller samples **encoded/raw** ShadowMask using its intended UV/sampler, then passes the resulting float4. [Common.ush:1215](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/Common.ush:1215) decodes with a componentwise square. This layer performs that square exactly once, after sampling; already-linear attenuation must not be passed as the raw input.

Initialization follows [DeferredLightingCommon.ush:347](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:347): `(surface,transmission,optical)=(sceneAO,1,1)`. `sceneAO` is the separate screen-space AO input, not an automatic material GBuffer AO factor. For `shadowedBits==0` the initialized values remain. Otherwise [GetShadowTermsBase:90](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:90), specialized to `ALLOW_STATIC_LIGHTING=0`, produces:

```text
A = sampledShadowMask * sampledShadowMask
point/spot: surface=A.z; transmission=A.w; optical=A.w
directional:
    fade=saturate(sceneDepthCm*distanceFadeMAD.x+distanceFadeMAD.y)^2
    surface=lerp(A.x,1,fade)*A.z
    transmission=min(lerp(A.y,1,fade),A.w)*A.z
    optical=min(A.y,A.w)
```

Directional fade follows [DistanceFromCameraFade:38](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:38). Depth is **linear view depth in centimeters**, not device-Z or Euclidean camera distance. The shadowed branch replaces the initial sceneAO; it does not multiply it afterward. The optical term also does not receive the extra A.z multiplier.

The disabled static branch deliberately does not consume precomputedShadowFactors or shadowMapChannelMask. Current fixtures supply all-one precomputed factors, but a nonzero ignored channel mask alone is not an unsupported static-lighting request. `perObjectFlags` is unused in this contact-free base evaluation; the caller supplies zero. [GetShadowTerms:227](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DeferredLightingCommon.ush:227) normally calls the contact stage afterward. The ordinary models in this profile have contact length zero and therefore no contact modification. Hair/Eye automatic contact lengths and `MATERIAL_CONTACT_SHADOWS` are not represented by this API/profile; they need their own explicit implementation. No CSM rendering, contact ray marching, static shadow lookup, or texture sampling is implemented in this file.

## E2655 cross-check

[shader-2655-Pixel.txt:391](E:/Project/falcor/Falcor/docs/research/captures/2026-09-09-1/shader-2655-Pixel.txt:391) samples t8; lines396–399 square all four channels. Lines409–422 implement the directional fade and combinations above with static shadow1. With `shadowedBits==0`, the phi at line428 preserves the sampled t7 AO input.

The capture b1 uniform has `DistanceFadeMAD=(0.0005000000237487257,-9)` at byte16, `ContactShadowLength=0` at byte24 and integer `ShadowedBits=3` at byte40. Byte0 is `(0,0,0,1)`, matching the ShadowMapChannelMask field order in [LightRendering.h:23](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/LightRendering.h:23). **The captured PS never loads b1 byte0.** Its active static-shadow factor is1 despite the retained channel-mask bytes. Rejecting nonzero channel mask while static lighting is disabled would incorrectly reject this fixture. Raw ShadowMask and sceneAO remain external reference-fixture inputs; this establishes shadow-term composition, not a shadow-map producer.

## Byte provenance

The hashes below identify local source and exported capture bytes read for this port. The capture has no source/PDB provenance establishing an exact original-source match; E2655's active directional operations were cross-checked against its exported disassembly.

Verification performed: token-normalized comparison of the desktop local attenuation, static-off base shadow branch and directional fade against UE source after ABI renaming and removal of explicitly excluded branches/branch annotations; direct evaluation of the port's inverse-square radius-mask expression at inside/on/outside-radius samples; an independent directional fade vector; report links and all eight hashes. These checks passed. They do not compile or execute the Slang shader. Integration must include this outer-lighting dependency in its shader/pipeline identity; the existing DefaultLit/Common include graph was not modified by this task.

| File (relative to its root above) | SHA256 |
|---|---|
| `Engine/Build/Build.version` | `29f7a3e61c24327147037ee15928d1bd1603fb65bcd19058e8381e26a12d38bd` |
| `Engine/Shaders/Private/DeferredLightingCommon.ush` | `d3bcd5cf9c36cab57c281f6cad447816891836e3c05a67c8808cbb9ad83e2c46` |
| `Engine/Shaders/Private/DynamicLightingCommon.ush` | `c5cf14a7d7d276e9737ad9b2312fd422a313d2a72c965a789ca167db5b4dc987` |
| `Engine/Shaders/Private/Common.ush` | `11184bf6e39a0065e66acd174e2b8407c89791a184a2ad9552a1f1d83669c84b` |
| `Engine/Shaders/Private/LightDataUniforms.ush` | `4ec919e1f1055c19e65fde265da5671ab4dfd98f3cac9ccefd79b78e2dcc3226` |
| `Engine/Source/Runtime/Renderer/Private/LightRendering.h` | `6dc5e1806028a959cf378de90c0a6af4d0f89c60b6dd89bf20a970c2f63768c1` |
| `shader-2655-Pixel.txt` | `c4a958663f70f6271e05c254d25e372c88d3ef7e2d46a9b6d4e66e81662bdae8` |
| `cbuffer-2655-Pixel-1.bin` | `51afaea5fe7bdc5eaf6b855156a390938d221ca79aea815add4b2158bc6ae2b7` |
