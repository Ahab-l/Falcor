# UE legacy SkyLight source inventory

Read-only source survey, 2026-09-12. Source root: `E:/ue/engine/UnrealEngine`.
This document inventories the desktop realtime SkyLight capture, mip generation,
convolution, and SH contracts for subsequent exact-source extraction. It does not
establish rendering parity or a completed SkyLight implementation. No UE source,
project configuration, RDC, native code, build, or GPU job was changed for this
survey.

## Pipeline and extraction boundaries

The non-timesliced order is capture sky/clouds, generate raw Cube mips, convolve
all mips, then compute SH **from the convolved Cube**. The authoritative calls are
[ReflectionEnvironmentRealTimeCapture.cpp:1274](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ReflectionEnvironmentRealTimeCapture.cpp:1274),
lines 1274-1283.

| Extraction unit | Exact source spans | Contract |
| --- | --- | --- |
| Cube direction | [ReflectionEnvironmentShaders.usf:99](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShaders.usf:99), 99-130 | `GetCubemapVector` |
| Resources and sampling | [ReflectionEnvironmentShaders.usf:188](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShaders.usf:188), 188-189 and 245-267 | Cube texture/sampler, mip declarations, `SampleCubemap` overloads, compute dispatch declarations |
| `DownsampleCS` | [ReflectionEnvironmentShaders.usf:269](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShaders.usf:269), 269-332 | Complete compute/pixel conditional block; `USE_COMPUTE=1`, `THREADGROUP_SIZE=8` |
| `FilterCS` | [ReflectionEnvironmentShaders.usf:501](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShaders.usf:501), 501-651 | Hammersley selection macro plus complete compute/pixel conditional block; same compute defines; desktop `SHADING_PATH_MOBILE=0` |
| `ComputeSkyEnvMapDiffuseIrradianceCS` | [ReflectionEnvironmentShaders.usf:857](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShaders.usf:857), 857-1014 | `SHADER_DIFFUSE_TO_SH=1`, `THREADGROUP_SIZE_X=8`, `THREADGROUP_SIZE_Y=8` |
| CPU shader declarations | [ReflectionEnvironmentRealTimeCapture.cpp:82](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ReflectionEnvironmentRealTimeCapture.cpp:82), 82-179 | Parameter names/types, shader registration, compile defines |
| CPU resource and dispatch setup | [ReflectionEnvironmentRealTimeCapture.cpp:1038](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ReflectionEnvironmentRealTimeCapture.cpp:1038), 1038-1173 | SRV mip ranges, samplers, UAV views, dispatch sizes |

The downsample/filter signatures share braces and bodies with their pixel paths
across preprocessor conditionals. A naive function-brace extractor will not
capture the source correctly; retain the full conditional spans. The SH wrapper
must compile separately: its source defines `THREADGROUP_SIZE` as X times Y,
whereas the other wrappers define that name as 8.

The original top-level includes are at shader lines 7-18. The dependencies below
are the minimal live helper inventory; they are not a claim that including all of
`Common.ush` and its transitive renderer declarations in an external compiler is
necessary or sufficient.

## Texture, mip, and dispatch contract

- Shader resources are `TextureCube SourceCubemapTexture`,
  `SamplerState SourceCubemapSampler`, and, for mipgen/filter,
  `RWTexture2DArray<float4> OutTextureMipColor`.
- Mipgen/filter uniforms are `uint MipIndex`, `uint NumMips`,
  `int FaceThreadGroupSize`, and `int2 ValidDispatchCoord`. Filter also uses
  `int CubeFaceOffset`. CPU structs include `CubeFace`, but these compute paths
  derive the face from dispatch X. `SourceMipIndex` belongs to the non-compute
  `SampleCubemap` path; compute samples relative LOD zero.
- A face's width is `1 << (NumMips - MipIndex - 1)`.
  `FaceThreadGroupSize = ceil(width / 8) * 8`; bounds checks discard padded
  texels. Mipgen dispatches six faces. Filter supports a face offset and count.
- Mipgen binds a **mip-local SRV of the preceding source mip**, and samples LOD
  zero relative to that view. Its output is another mip of the same Cube.
- Filter binds the full source Cube and mip chain and writes a distinct convolved
  Cube. A single destination mip is viewed as six Texture2DArray slices.
- CPU mipgen, convolution, and SH all bind **`SF_Point`** at lines 1066, 1124,
  and 1161. The SH comment mentioning bilinear sampling at line 1167 is stale.
- The native Cube descriptor is **`PF_FloatR11G11B10`**, with full mips,
  independent array-slice render targets, shader-resource, UAV, and render-target
  flags: [SkyPassRendering.cpp:334](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SkyPassRendering.cpp:334),
  334-339. Format quantization is part of parity; float4 shader values do not imply
  an RGBA32F native storage format.
- CPU chooses Cube width and `CeilLogTwo(width)+1` mips at
  [ReflectionEnvironmentRealTimeCapture.cpp:382](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ReflectionEnvironmentRealTimeCapture.cpp:382).
  The shader bit shifts require a power-of-two extraction contract; the SH mip
  selection additionally requires width at least 16.

## Downsample and specular convolution

Downsample uses **nine directional taps**: center weight 1, eight weights 0.375,
four diagonal offsets scaled by 0.7, four cardinal offsets, directional offset
`4 / MipSize`, and final normalization by one quarter. Preserve its tangent
construction and its use of the unnormalized Cube direction. An ordinary 2x2 box
mip generator is not equivalent.

The roughness convention is defined at
[ReflectionEnvironmentShared.ush:16](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShared.ush:16),
16-39:

```text
REFLECTION_CAPTURE_ROUGHEST_MIP = 1
REFLECTION_CAPTURE_ROUGHNESS_MIP_SCALE = 1.2
roughness = exp2((MipIndex - NumMips + 3) / 1.2)
```

The formula follows the actual filter call passing `NumMips - 1` as
`CubemapMaxMip`. Roughness is **not clamped to 1**; the last three mips enter the
cosine branch. The inverse material lookup function is at lines 26-33 and uses
`log2(max(Roughness, 0.001))`.

- Roughness below 0.01 copies source mip zero, then applies the source's
  `-min(-OutColor, 0)` sanitization expression.
- The desktop sample count is **32 for roughness below 0.1, otherwise 64**
  (shader line 574). The 1024-sample reference path is disabled. The mobile
  16/32/64 path is a distinct permutation.
- Roughness above 0.99 uses Hammersley points, cosine hemisphere samples,
  `PDF = NoL / PI`, and an unweighted average of sampled Cube values.
- Otherwise it scales `E.y` by **0.995**, samples GGX half vectors with
  `a2 = Pow4(Roughness)`, computes `L = 2 * H.z * H - (0,0,1)`, skips nonpositive
  `NoL`, and normalizes accumulated `NoL` weights.
- Keep `SolidAngleTexel = 4 * PI / (6 * CubeSize * CubeSize) * 2`, including
  the factor of 2. GGX PDF is `D_GGX(Pow4(Roughness), NoH) * 0.25`.
- Sample LOD is `0.5 * log2(SolidAngleSample / SolidAngleTexel)` with
  `SolidAngleSample = 1 / (NumSamples * PDF)`.
- `GetTangentBasis` constructs matrix rows, and the filter uses
  `mul(L, TangentToWorld)`. Preserve this multiplication convention.
- The final filter result also uses `-min(-OutColor, 0)` at lines 645-646.

## Minimal live helper dependencies

| Source | Required symbols and exact spans |
| --- | --- |
| [MonteCarlo.ush:13](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/MonteCarlo.ush:13) | `GetTangentBasis` 13-23; desktop `Hammersley` 58-63; `UniformSampleSphere` 214-228; `CosineSampleHemisphere` 248-262; `ImportanceSampleGGX` 368-384 |
| [BRDF.ush:311](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BRDF.ush:311) | `D_GGX` 311-315 |
| [Common.ush:133](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/Common.ush:133) | `PI` 133; scalar `Pow2` 1074-1077; scalar `Pow4` 1114-1118 |
| [ReflectionEnvironmentShared.ush:16](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShared.ush:16) | Roughness macros 16-17 and `ComputeReflectionCaptureRoughnessFromMip` 35-39 |
| [SHCommon.ush:38](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/SHCommon.ush:38) | SH structs 38-54; scalar `MulSH3` 96-103; scalar/RGB `AddSH3` 121-137; `SHBasisFunction3` 232-249 |
| [Platform.ush:348](E:/ue/engine/UnrealEngine/Engine/Shaders/Public/Platform.ush:348) | Precision aliases 348-374; desktop `UNROLL`, `LOOP`, `BRANCH` attributes 778-795 and fallbacks 811-824 |

`GetCubemapTangent`, `CubeTexelWeight`, and the RGB-vector `MulSH3` overload are not
live dependencies of these paths. `ConeAngle` in the filter is computed but unused;
preserve it when copying the exact source block.

Desktop Hammersley uses `reversebits` and zero random input in the filter.
`UniformSampleSphere` uses azimuth `2*PI*E.x` and `cosTheta=1-2*E.y`.
`CosineSampleHemisphere` uses `cosTheta=sqrt(E.y)`. These mappings and signs must
not be replaced with another statistically equivalent sampler for parity.

The SH basis is ordered as follows, with the source's decimal constants:

```text
c0 =  0.282095
c1 = -0.488603 * y
c2 =  0.488603 * z
c3 = -0.488603 * x
c4 =  1.092548 * x*y
c5 = -1.092548 * y*z
c6 =  0.315392 * (3*z*z - 1)
c7 = -1.092548 * x*z
c8 =  0.546274 * (x*x - y*y)
```

## Precision and compile-environment caveat

`half` is platform-conditional, not an unconditional FP16 type. At
[Platform.ush:348](E:/ue/engine/UnrealEngine/Engine/Shaders/Public/Platform.ush:348),
348-374, relaxed-precision platforms map it to `min16float`; otherwise
`FORCE_FLOATS || !PLATFORM_SUPPORTS_REAL_TYPES` maps it and vector/matrix aliases
to `float`. Defaults for the two platform support flags are zero at 257-262.

D3D SM6.6+ enables `PLATFORM_SUPPORTS_REAL_TYPES` only when
`CFLAG_AllowRealTypes` is present:
[ShaderFormatD3D.cpp:244](E:/ue/engine/UnrealEngine/Engine/Source/Developer/Windows/ShaderFormatD3D/Private/ShaderFormatD3D.cpp:244).
The three realtime capture shader wrappers at CPU lines 82-179 do not request
that flag. Their ordinary desktop route therefore points to FP32 aliases; do not
silently substitute native Slang FP16. This is source evidence, not inspection of
the actual captured shader's preprocessed defines or compiler invocation. Pin the
real target permutation before claiming precision parity.

The shader's top-level lines 11-15 enable `NEED_SH_VECTOR_PADDING` when
`DXC_GROUPSHARED_ALIGNMENT_WORKAROUND` is enabled. SH structs include optional
padding; preserve the applicable compile environment and groupshared layout.

## SH sampling, reduction, and packed output

The active SH path uses **64 uniform sphere samples**, one per thread in a
single 8x8 group, at sample-cell centers, each weighted by `4*PI/64`.
CPU lines 1161-1172 use point sampling and select:

```text
MipIndex = uint(log2(CapturedCubeWidth)) - 4
```

The input is the **convolved Cube**. For a 128 Cube this is **mip 3**, a 16x16
face. The shader comment at line 887 saying mip 2 is stale. The supersampling
branch at 891-915 is inactive.

Reduction supports exactly 64 threads and uses `SV_DispatchThreadID` as its local
index, so the one-group CPU dispatch is essential. After reducing to 16 entries,
the source assumes wave lockstep and omits further group barriers (lines 936-953).
Record this portability assumption rather than silently rewriting the reduction
while claiming exact-source extraction.

Output is **8 float4 values, 128 bytes**, not nine raw RGB coefficients. Allocation
is verified at
[ReflectionEnvironment.cpp:786](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ReflectionEnvironment.cpp:786),
with the count defined at
[SceneView.h:877](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Engine/Public/SceneView.h:877).

Packing is at
[ReflectionEnvironmentShaders.usf:955](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShaders.usf:955),
955-1011. Define `C0=1/(2*sqrt(PI))`, `C1=sqrt(3)/(3*sqrt(PI))`,
`C2=sqrt(15)/(8*sqrt(PI))`, `C3=sqrt(5)/(16*sqrt(PI))`, and `C4=0.5*C2`.
For the raw projected coefficients `c0..c8` of each RGB channel:

- Slots 0/1/2, one per channel: `(-C1*c3, -C1*c1, C1*c2, C0*c0-C3*c6)`.
- Slots 3/4/5, one per channel: `(C2*c4, -C2*c5, 3*C3*c6, -C2*c7)`.
- Slot 6.xyz: `C4 * (R.c8, G.c8, B.c8)`; slot 6.w is 1.
- Slot 7 repeats average brightness in every component. Average RGB is recovered
  from raw band zero using `1/(SHBasisFunction3((0,0,1)).V0.x * 4*PI)`, then
  combined with `dot(avgRGB, .3333f)`. Preserve `.3333f`; this is neither luminance
  weighting nor exact division by three.

The consumer at
[ReflectionEnvironmentShared.ush:84](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShared.ush:84),
84-103, dots slots 0-2 with `(x,y,z,1)`, slots 3-5 with `(xy,yz,z*z,z*x)`, adds
slot 6.xyz times `(x*x-y*y)`, and clamps negative RGB to zero. Diffuse convolution
weights are already included. Their normalization is **irradiance divided by PI**
(band weights 1, 2/3, 1/4), so the packed consumer must not receive another
diffuse `1/PI` factor.

## Cube orientation

For `u,v = 2*(pixel+0.5)/faceExtent - 1`, with image v increasing downward:

| Slice | Direction |
| --- | --- |
| 0, +X | `(1,-v,-u)` |
| 1, -X | `(-1,-v,u)` |
| 2, +Y | `(u,1,v)` |
| 3, -Y | `(u,-1,-v)` |
| 4, +Z | `(u,-v,1)` |
| 5, -Z | `(-u,-v,-1)` |

CPU rotations use the matching face directions and up vectors at
[ReflectionEnvironmentCapture.cpp:2262](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ReflectionEnvironmentCapture.cpp:2262),
2262-2304; reversed-Z Cube projection is at 2306-2309. Lower-hemisphere treatment
uses **world Z below zero**. Do not infer a Y/Z swizzle from the Cube face names.

## Capture inputs beyond the three compute kernels

The kernels above depend on an input Cube. Producing that Cube faithfully has
additional renderer dependencies:

- Capture position is `SkyLightProxy->CapturePosition`; view flags enable the
  reflection-capture mask and realtime reflection capture, disable holdout, and
  set emissive clamp 64512. See
  [ReflectionEnvironmentRealTimeCapture.cpp:550](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/ReflectionEnvironmentRealTimeCapture.cpp:550),
  550-578. The reflection-capture mask removes the atmosphere sun disk.
- Capture-specific atmosphere view LUT and 360-degree aerial-perspective LUT
  setup is at 580-625. Preserve the source's constant sky reference frame and
  exposure treatment instead of reusing a main-view sky LUT unconditionally.
- Cloud setup at 494-545 uses the original volumetric-cloud material, cloud
  renderer resources, reflection-capture flags, and optional opaque shadows.
  Cloud resolution divider defaults to 2 (65-69), opaque cloud shadows default
  off (50-54). The cloud target is RGBA16F and composition uses bilinear sampling.
- Height-fog rendering at 921-967 depends on fog uniforms, optional captured
  depth, and `SkyLightPosition`. The shader path is
  [ReflectionEnvironmentShaders.usf:1018](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/ReflectionEnvironmentShaders.usf:1018),
  1018-1075, including `HeightFogCommon.ush`, `ResolveView`,
  `ConvertFromDeviceZ`, `GetExponentialHeightFog`, and
  `ScreenVectorFromScreenRect`. The CPU explicitly states that volumetric fog
  is not supported in this realtime capture path (939-940).
- Cloud and lower-hemisphere composition is at CPU 976-1010 and shader 417-456.
  Dependencies include `LowResCloudTexture`, its sampler,
  `ApplyLowResCloudTexture`, `ApplyLowerHemisphereColor`,
  `LowerHemisphereSolidColor`, view exposure, and blend state. Preserve the
  source's effective `saturate(alpha)` coverage; a preceding `pow(...,2.2)`
  assignment is overwritten.

These cloud/fog/material paths are external to the three compute kernels and
must not be represented as completed merely because convolution and SH work.

## Exposure evidence and configuration check

Realtime capture pre-exposure is **not hardcoded to one** in this source tree.
[SceneRendering.cpp:2076](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/SceneRendering.cpp:2076)
assigns `EyeAdaptation::GetCachedLightingPreExposure()` to
`RealTimeReflectionCapturePreExposure`.

[PostProcessEyeAdaptation.cpp:201](E:/ue/engine/UnrealEngine/Engine/Source/Runtime/Renderer/Private/PostProcess/PostProcessEyeAdaptation.cpp:201),
201-207, declares `r.EyeAdaptation.CachedLightingPreExposure` with default EV 4.
Lines 235-242 clamp this EV to [-16,16] and return `exp2(-EV)`, so the **source
default multiplier is 1/16**. SceneRendering.cpp 2091-2101 applies its reciprocal
in `SkyLightColor` for realtime capture consumption. The sky base-pass selection
is at
[BasePassPixelShader.usf:2484](E:/ue/engine/UnrealEngine/Engine/Shaders/Private/BasePassPixelShader.usf:2484),
2484-2499; its comment referring to capture exposure one is stale. Final emissive
clamping is at line 2556.

A read-only, case-insensitive `rg --hidden --no-ignore` check on 2026-09-12 found
**no `CachedLightingPreExposure` occurrences** in either of these existing
locations:

- `E:/ue/project/shadingmodeltest/shadingmodel/Config`: `DefaultEditor.ini`,
  `DefaultEngine.ini`, `DefaultGame.ini`, and `DefaultInput.ini`.
- `E:/ue/engine/UnrealEngine/Engine/Config/ConsoleVariables.ini`.

The search exited 1 with no matches and no path errors. This checks only those
requested configuration locations. It does **not** establish the actual runtime
CVar value: console commands, command-line arguments, other configuration layers,
or code can override it. Capture metadata or a live read of the relevant runtime
must pin exposure before claiming parity; no runtime read was performed here.

## Evidence limits

Line spans refer to the local UE tree surveyed on 2026-09-12. This inventory does
not pin source hashes, the UE build, compiled shader permutations, active runtime
CVars, or captured binaries. Exact-source export should record those separately.
No rendered comparison or numerical GPU verification was performed by this
source survey.
