# Floor sampling residual: texture checks and the worst pixel's quad

The next useful diagnostic is the **native UV and derivative values before sampling in the complete 2×2 quad at (948,1016)**. The worst metallic residual, pixel (948,1017), is not close to an original triangle boundary. The texture file, all captured mip payloads, SRV range, and nominal sampler configuration agree with the current loading path.

This is an offline, read-only investigation of the `source-final` comparison, whose native NPZ SHA-256 is `91b7252c480f1c3262e5032c43bd29db7942df5f55e4093d125e249a1730e8c3`. The parent separately rebuilt the inverse-mask grouping edit and reported the same NPZ hash. No core edits, build, replay, or GPU execution were performed for this report.

## Texture and sampler checks

The material definition `build/rdc-render/materials.json` points the floor at `build/rdc-scene/raw/1853-grid.dds`. The DDS has a 148-byte DX10 header followed by 174,776 bytes of BC1 payload; total file size is 174,924 bytes. Its SHA-256 remains `73f03a677acf3b8b5803c9f9ebd4b6b9ee9a4216e5dadda5f3200de5f4f98aab`.

All ten contiguous DDS mip payloads were compared byte-for-byte with `raw/1853-grid-mip0.bin` through `raw/1853-grid-mip9.bin`, and all ten raw files passed the SHA-256 values recorded in `scene-manifest.json`. Mip byte counts are 131072, 32768, 8192, 2048, 512, 128, 32, 8, 8, and 8. Every DDS byte after its header is accounted for; no missing, reordered, or regenerated mip was found.

| Property | Captured event 1853 | Current native path |
|---|---|---|
| Dimensions | 512×512, one 2D slice | DDS header 512×512, one 2D slice |
| View format | BC1_UNORM_SRGB | DDS declares BC1_UNORM; `loadAsSrgb=true` selects BC1UnormSrgb |
| Mips exposed | First mip 0, count 10, min LOD clamp 0 | Default `getSRV(0)` expands to all ten mips |
| Component swizzle | Identity RGBA | Default identity view |
| Addressing | Wrap U/V/W | Sampler defaults are Wrap U/V/W |
| Filtering | Standard anisotropic, max anisotropy 8 | `setMaxAnisotropy(8)`, standard reduction |
| LOD | Min 0, max FLT_MAX, bias 0 | `setLodParams(0.f, FLT_MAX, 0.f)` |
| Comparison | Disabled | Disabled |

Relevant source locations are `UELegacyPasses.cpp:154–160`, `Texture.cpp:384`, `ImageIO.cpp:514–519`, `ImageIO.cpp:549–553`, `ImageIO.cpp:601`, `Sampler.h:123–137`, and `Sampler.cpp:97–116`. The DDS path copies compressed payload bytes directly into the texture; it changes the format to sRGB without decompressing, flipping, or regenerating mips. The current runtime also checks BC1UnormSrgb and ten mips. This review verifies file contents and source behavior, not a fresh readback of the live GPU resource or descriptor.

## The maximum residual is inside a complete quad

The quad origin is (948,1016), with lanes (948,1016), (949,1016), (948,1017), and (949,1017). All four captured/native depth values are bit-identical:

| Pixels | Reverse-Z float32 bits |
|---|---|
| (948,1016), (949,1016) | `0x3c583d71` |
| (948,1017), (949,1017) | `0x3c5897f6` |

Using the original captured floor clip positions and index buffer with the previously validated 1/256-pixel screen-coordinate model, all four centers are covered by original floor triangle **47**, source indices **[54,48,53]**. All three source local normals are `[0,0,1]`. Its projected vertices are approximately `(-7314.0625,3647.29296875)`, `(1248.875,1385.875)`, and `(717.65234375,596.41015625)`.

The nearest original triangle-edge distances are respectively 42.9983, 42.1686, 43.5566, and 42.7269 pixels. All four lanes are inside the ViewRect and on the floor top face. Thus an original primitive boundary or an uncovered lane within this quad is not supported by the geometry evidence. Even if the primitive were explicitly clipped to the viewport and triangulated as a quadrilateral, its two possible internal fan diagonals are approximately 6.87 and 479.68 pixels from the worst pixel, not within this quad. Actual GPU guard-band/clipping implementation was not observed here.

This is not just an isolated interior outlier. Among all 401 metallic residual pixels, the same source-triangle calculation assigns every pixel to a positive-w front-facing floor triangle. Only 17 are within two pixels of an original triangle edge; 373 are farther than five pixels, and the median distance is 74.18 pixels. Primitive/helper-lane edges therefore do not explain most metallic residuals, although the 17 edge-adjacent pixels remain a separate diagnostic subset.

## Captured-data CPU baseline for the quad

These values are computed from captured float32 depth and the original `View.SVPositionToTranslatedWorld` at byte 704, using x multiply followed by y/z/w FMA, divide by w, subtract `View.RelativePreViewTranslationTO` at byte 2048, subtract floor origin `[0,0,-0.5]`, and multiply by captured float32 frequency 0.01. They are **CPU source-arithmetic predictions**, not a native or captured PS register readback. The captured GPU normalizes primitive axes `[8,0,0]`, `[0,8,0]`, `[0,0,8]`; this baseline uses the resulting mathematical unit axes.

| Pixel | U | V | W |
|---|---:|---:|---:|
| (948,1016) | -16.978164672851562 | -0.5449615120887756 | 0.000002441406195430318 |
| (949,1016) | -16.979944229125977 | -0.5344470143318176 | 0.000002441406195430318 |
| (948,1017) | -16.98982048034668 | -0.5511358380317688 | 0.0000030517576306010596 |
| (949,1017) | -16.99159812927246 | -0.5406383872032166 | 0.0000030517576306010596 |

At (948,1017), wrapped UV is `(0.010179519653320312, 0.4488641619682312)`. Multiplying the full-frequency XY differences by 512 gives the following base-mip texel-space gradients:

| Pair | dU × 512 | dV × 512 |
|---|---:|---:|
| Horizontal, top row | -0.9111328125 | 5.3834228515625 |
| Horizontal, bottom row | -0.91015625 | 5.37469482421875 |
| Vertical, left column | -5.9677734375 | -3.1612548828125 |
| Vertical, right column | -5.966796875 | -3.16998291015625 |

The horizontal and vertical derivatives differ slightly between the rows/columns because screen-position reconstruction divides by depth before forming UV. Consequently, coarse versus fine derivative choice is meaningful even inside this complete primitive quad. These numbers do not establish which derivatives the implicit Sample instruction actually used.

At the worst pixel the floor normal gives blendX=0 and blendZ=1, so the physically relevant metallic sample is full-frequency XY red, with the existing blend arithmetic. Its captured metallic code is 68 and native code 77. Captured roughness is 114 versus native 112, and C gray is 130 versus native 131. A nine-code metallic difference cannot be explained by the inverse-mask grouping, which metallic does not use.

## Next bounded diagnostic

Instrument the native floor shader for this quad and a small surrounding rectangle to export float32 bits for `positionUE`, `delta`, `uvw`, `ddx_fine(uvw.xy)`, `ddy_fine(uvw.xy)`, `ddx_coarse(uvw.xy)`, `ddy_coarse(uvw.xy)`, and the six sample channel results, together with primitive ID. Compute samples and derivatives before any coordinate-based diagnostic branch so the diagnostic itself does not introduce divergent derivatives. The first decisive comparison is native `uvw` against the four baseline rows above.

If native UV differs, inspect the emitted native IR at the original non-fast relative-translation subtraction and the subsequent delta/projection/multiply operations. The current matrix/FMA/divide helper is precise, but the subtraction at `UELegacyRaster.3d.slang:52` occurs outside that helper in an ordinary expression. Original LLVM performs the subtraction as non-fast `fsub`. This is a concrete source qualification difference, not yet proof of different machine results.

If UV agrees, compare native fine/coarse derivatives and the XY red return before blending. That separates coordinate formation from implicit derivative/filtering behavior. A later controlled SampleGrad experiment can use recorded derivatives, but changing the production sampler or Sample calls before this measurement would mix causes. Do not start with missing helper lanes at (948,1017): the source geometry gives a fully covered quad well inside one primitive.

No sampler, mip, format, or source-coordinate scale mismatch was found. The remaining uncertainty is the actual shader intermediate values and implicit texture sampling behavior; this report does not claim they have been proven equal.
