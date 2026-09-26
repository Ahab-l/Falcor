# Vertex source-fidelity analysis

This CPU-only investigation uses original indexed local positions and GPUScene transforms. PostVS data is used exclusively to check results.

| Object | Clip values different from captured using source arithmetic | Max baked-order clip error | Max translated-position error cm | Half normal error |
|---|---:|---:|---:|---:|
| sphere | 0 | 0.000183105469 | 0.000122070312 | 0.000238358974 |
| cube | 0 | 0 | 0 | 0 |
| standing_plane | 0 | 3.05175781e-05 | 1.52587891e-05 | 0 |
| grid_floor | 0 | 0.00048828125 | 0.00048828125 | 0 |

Every source-arithmetic clip component is bit-exact to the captured GPU postVS stream. This checks all four objects; it does not assert raster/GBuffer equality.

Falcor SceneTypes.slang stores normals as three float16 components, then explicitly normalizes the decoded vertex normal before interpolation. Tangents use octahedral 2×16 encoding; normals do not use quaternion packing. The captured UE VS keeps unnormalized SNORM8-derived normals until PS normalization. Both the half conversion and vertex normalization must be bypassed.

## Required operation order

```hlsl
float3 localLinear = localPosition.z * localLinearRow2;
localLinear = fma(localPosition.y, localLinearRow1, localLinear);
localLinear = fma(localPosition.x, localLinearRow0, localLinear);
float3 translation = ((preHigh + primitiveHigh) + preLow) + instanceRelativeTranslation;
float3 translated = localLinear + translation;
float4 clip = translated.x * translatedWorldToClipRow0;
clip = fma(translated.y, translatedWorldToClipRow1, clip);
clip = fma(translated.z, translatedWorldToClipRow2, clip);
clip = fma(1.0, translatedWorldToClipRow3, clip);
```

Use the original local float32 positions and separated primitive-high/relative translations; baking world meters then multiplying by 100 changes arithmetic and rounding. Keep the captured FMA order rather than allowing matrix multiplication to change association.

## Two depth boundary pixels

The captured depths at (1126,565) and (1123,597) belong to cube triangles 42 and 40. Their pixel centers are respectively 0.000729 pixels outside and 0.000398 pixels inside the unsnapped right edge. Rounding the captured screen coordinates to 1/256 pixel puts both centers inside; interpolated depth agrees with the captured value within one float32 ULP. The native snapshot instead contains floor depth at both locations.

The cube has identical source-local and baked-meter clip bits when both calculations use captured FMA order. Consequently, world-meter baking alone cannot explain these two pixels. Native matrix accumulation and raster setup require a GPU comparison. The CPU object-ID mask itself is sensitive to edge snapping and is not ground truth at these boundary pixels.

## Pixel position reconstruction

The original PS multiplies `[SV_Position.x,SV_Position.y,SV_Position.z,1]` directly by the captured View.SVPositionToTranslatedWorld matrix at cbuffer byte 704, using x multiply then y/z/w FMAs, divides xyz by w, and subtracts View.RelativePreViewTranslationTO at byte 2048. Both raw matrices and exact float32 values are in vertex-fidelity.json. Do not add a second half-pixel or normalize pixel coordinates for this direct matrix.

Computing a new inverse VP and normalizing coordinates first changes both the rounded matrix coefficients and per-pixel arithmetic. JSON quantifies coordinate and adjacent-pixel derivative differences on the same captured depth values, keeping geometry/depth differences separate. The native backend may choose a different multiplication association than this CPU model.

## Source buffer interface

The recommended 48-byte record is localPositionUECm(float3), sourceVertexID(uint), normalLocalUnnormalized(float3), tangentSign(float), tangentLocal(float3), padding(uint), at offsets 0/12/16/28/32/44. StructuredBuffer lookup bypasses PackedStaticVertexData. Keep Scene geometry/material IDs, draw list, index buffer, winding and draw arguments.

An explicit mapping from Scene-processed vertices to source vertices is required: SceneBuilder.processMesh can reorder/split vertices, and indexed draw SV_VertexID includes mesh.vbOffset. For these four UV-free draws, texC.x may carry the original numeric source ID through Scene processing (identity texture transform); otherwise provide an explicit remap buffer. Do not assume original source indexing survives preprocessing.

Per-instance data must retain scaled linear rows, primitive-high position and relative translation separately. For captured normal transformation divide each linear row by its absolute scale and apply the original unnormalized normal. Normalize only at the pixel stage. The instance packet also carries primitiveFlags and source vertex base/count.

Sphere pixel comparisons in JSON independently separate vertex-normalization-only and half-plus-normalization candidates. Their software UNORM rounding and floating interpolation are explicitly diagnostic, not substituted for GPU validation. No tolerances are relaxed.
