# Identity DBuffer is an explicitly enabled base-pass operation

The local legacy UE DBuffer path normalizes the material world normal when the material's **normal decal-response bit** is enabled, even when the sampled DBuffer is numerically neutral. An identity-DBuffer entry point should represent that source operation and its applicable context. It should not add unconditional normalization to every material or to a path whose normal has already passed through the corresponding operation.

These source references were read from `E:/ue/engine/UnrealEngine`. This local source tree's identity to the captured executable is **not proven**; the captured DXIL, bindings, named 1×1 resources, and debugger values independently corroborate the specific legacy path described here. No UE source or production files were changed. Source hashes are preserved with the quantization evidence JSON.

## Conditions in local UE source

[`BasePassPixelShader.usf:1106`](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1106) includes the operation only for `USE_DBUFFER`, excluding translucent materials and single-layer water. [`BasePassPixelShader.usf:1113`](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:1113) then requires both `GetPrimitiveData(...).Flags & PRIMITIVE_SCENE_DATA_FLAG_DECAL_RECEIVER` and `View.ShowDecalsMask > 0`.

The receiver flag is **0x8**, defined in [`SceneDefinitions.h:36`](E:/ue/engine/UnrealEngine/Engine/Shaders/Shared/SceneDefinitions.h:36). The base pass intersects `GetDBufferTargetMask(pixel)` with `MATERIALDECALRESPONSEMASK`, and calls the legacy ApplyDBufferData only when the result is nonzero and Substrate is disabled. These are compilation, view/primitive, and target/material response conditions; they should not be replaced by a material-program-name test.

[`DBufferDecalShared.ush:53`](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DBufferDecalShared.ush:53) selects the target mask from render-target write masks or a per-pixel mask when supported, otherwise returns 0x07 for the enabled texture path. The exact mask implementation is platform dependent. The captured shader's unconditional three DBuffer samples inside the receiver/show-decals branch provide direct evidence for the observed compiled path.

## Dummy resources and application arithmetic

[`DBufferTextures.cpp:127`](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/DBufferTextures.cpp:127) initializes A and C to `SystemTextures.BlackAlphaOne`, B to `SystemTextures.DefaultNormal8Bit`, and the render mask to white. At line136 it replaces these with real DBuffer textures only when that set is valid.

[`SystemTextures.cpp:294`](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SystemTextures.cpp:294) creates BlackAlphaOneDummy as a 1×1 PF_B8G8R8A8 texture with `FColor(0,0,0,255)`. [`SystemTextures.cpp:314`](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SystemTextures.cpp:314) creates DefaultNormal8Bit as the same format and dimensions with `FColor(128,128,128,255)`.

[`DBufferDecalShared.ush:428`](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DBufferDecalShared.ush:428) decodes the sampled normal as `DBufferB.rgb * 2 - (256.0 / 255.0)` and reads normal opacity from alpha. At [`DBufferDecalShared.ush:517`](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DBufferDecalShared.ush:517), material response bit0x2 applies:

```hlsl
WorldNormal = normalize(WorldNormal * DBufferData.NormalOpacity
                        + DBufferData.PreMulWorldNormal);
```

The neutral decoded normal is zero and opacity is one, so this operation reduces mathematically to a second normalization. It still changes some floating-point values. The decoded identity values should come from the sampled dummy contract above. The un-sampled fallback literals in GetDBufferData include `128.f / 255.5f` components in this local source and are a separate branch; they should not be substituted for the captured sampled dummy.

Material response bit0x1 applies color; bit0x4 applies roughness, metallic, and specular. [`DBufferDecalShared.ush:522`](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/DBufferDecalShared.ush:522) computes specular as `Specular * RoughnessOpacity + PreMulSpecular`. The sampled neutral C has zero RGB and alpha1, which preserves specular numerically.

## Captured and diagnostic correspondence

For E1853, captured flags are `0x02010a89` and View's ShowDecalsMask slot is 1.0. Its bindings use Resource500 (BlackAlphaOneDummy) for A/C and Resource502 (DefaultNormal8Bit) for B; both are 1×1. The five specular traces take the DBuffer branch and confirm C=[0,0,0,1], preserving specular=0.5. Thus identity resource contents do not mean the DBuffer application was skipped.

The parent's separate normal diagnostic adds the second normalization only in an isolated copy. It changes the one sphere A residual into equality across the full allocation while leaving B/C/SceneColor unchanged. This supports implementing the explicit identity-DBuffer operation for an opted-in captured-source context with the appropriate receiver and response conditions. It does not establish that a general Adapter or every independently evaluated material needs that operation.
