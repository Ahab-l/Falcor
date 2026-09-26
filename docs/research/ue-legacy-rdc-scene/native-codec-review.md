# Captured encoding evidence and first native-grid comparison

This is the review snapshot for native NPZ SHA-256 `9f107b7b2202372bd264ceaeed35c0376a7ffc9c06da81e3755f61c5513c7806`. The independent comparator is `scripts/ue_legacy/compare_rdc_gbuffer.py`; run `python scripts/ue_legacy/compare_rdc_gbuffer.py --label <run-name>` after a completed native render. This performs no GPU work. Reports are `native-<run-name>.json` and `.md`; labels keep later changes separate from this baseline.

The comparator uses the customized Schema's five shading-model bits (`0x1f`) and three selective-output bits (`0xe0`). It compares original physical bytes rather than screenshots or decoded Falcor diagnostic textures. Every captured source passed its recorded raw-size/SHA-256 check. Native NPZ bytes are snapshotted once before decoding, protecting the report from later replacements of the render output.

## Per-object alpha: captured buffer and DXIL proof

The captured flags are in the primitive structured buffer, not a material cbuffer. Pixel SRV1 and Vertex SRV2 refer to ResourceId 806 with byte offset zero. The relevant first uint of each primitive's 44-float4 record is:

| BasePass EID | Primitive ID | Byte offset in Resource 806 | Flags |
|---|---:|---:|---|
| 1816 | 18 | 12672 | `0x02010a89` |
| 1827 | 19 | 13376 | `0x02010a89` |
| 1838 | 20 | 14080 | `0x02010a89` |
| 1853 | 17 | 11968 | `0x02010a89` |

Raw files are `build/rdc-scene/raw/{eid}-Vertex-srv2.bin` and `{eid}-Pixel-srv1.bin`. The binding resource IDs, byte ranges and hashes are in `raw/replay-draws.json`. The shader extracts flag `0x100` and `0x200`, chooses 2 or 0 from the former and 1 or 0 from the latter, then multiplies their sum by float32 `1/3` (`0x3eaaaaab`). Every object has `0x100` clear and `0x200` set, producing `0.3333333432674408` and stored A-alpha two-bit value **1**.

This mapping is explicit in original captured PS LLVM, `native-captured-1816-ps.ll` lines 410–421, and in the RenderDoc disassembly `_354.._364`. Local UE `SceneDefinitions.h` lines 41–42 names these flags `HAS_CAPSULE_REPRESENTATION` and `HAS_CAST_CONTACT_SHADOW`; `SceneData.ush::GetPrimitive_PerObjectGBufferData_FromFlags()` performs the same mapping. A capture-specific Schema constant of 1/3 is therefore supported for these four objects. A general scene needs per-primitive data.

## Specular dither: original captured DXIL constants

`reflection-1816-Pixel.json` preserves the original shader container in `rawBytes`. It was extracted to `build/rdc-scene/captured-1816-ps.dxil` and disassembled **offline**, using installed Windows SDK dxc 10.0.26100.0. `native-captured-1816-ps.ll` contains the full precise LLVM constants, avoiding the rounded floats printed by RenderDoc's text disassembler.

| Constant | Exact float32 value | Float32 bits |
|---|---:|---|
| Dot X | 0.0671105608344078 | `0x3d897143` |
| Dot Y | 0.005837149918079376 | `0x3bbf4590` |
| Outer multiplier | 52.98291778564453 | `0x4253ee82` |
| Frame offset X | 32.665000915527344 | `0x4202a8f6` |
| Frame offset Y | 11.8149995803833 | `0x413d0a3d` |
| Quantization step | 0.003921568859368563 | `0x3b808081` |

Exact captured operation order, LLVM lines 315–324:

```hlsl
float frame = float(ViewStateFrameIndexMod8);
float offsetX = frame * asfloat(0x4202a8f6u);
float offsetY = frame * asfloat(0x413d0a3du);
float x = offsetX + SvPosition.x;
float y = offsetY + SvPosition.y;
float inner = dot(float2(x, y), float2(asfloat(0x3d897143u), asfloat(0x3bbf4590u)));
float firstFrac = frac(inner);
float scaled = firstFrac * asfloat(0x4253ee82u);
float noise = frac(scaled);
```

`SV_Position.xy` already contains pixel centers, including `.5`; do not add another half pixel. Captured View cbuffer byte offset **2712** (register169 component2) is uint **0**, so this capture has no frame offset. The source corroboration is `RandomInterleavedGradientNoise.ush`.

LLVM lines 422–430 then subtract 0.5, multiply the quantization step, and multiply `IsNonZeroFast(saturate(rawSpecular))`, before adding saturated raw specular and saturating the result:

```hlsl
float centered = noise - 0.5f;
float quantizationBias = centered * asfloat(0x3b808081u);
float clampedSpecular = saturate(rawSpecular);
float nonzero = float(min(asuint(clampedSpecular) & 0x7fffffffu, 1u));
float encodedSpecular = saturate(quantizationBias * nonzero + clampedSpecular);
```

The captured IR uses `fast` multiplication/addition and `dx.op.dot2`; backend contraction remains a compiler/driver concern. Keeping the intrinsic and this order is the supported translation, not an assertion that an arbitrary reassociation produces identical bits. Raw material Specular remains 0.5. This dither belongs in the material-to-GBuffer encoding context. Source corroboration: `ShadingModelsMaterial.ush::SetGBufferForShadingModel()` and `PackUnpack.ush::DitherXbits()`.

## Baseline differences retained

The first native captured-grid comparison has exact coverage (866,712 pixels) and exact model bits on every covered pixel. It reports:

- A normal RGB exact on 860,808 covered pixels. Apart from two depth boundary pixels, normal components differ by at most one ten-bit step. Cube, plane and floor interiors are exact; sphere differences remain within one step.
- A-alpha differs on all covered pixels: captured 1, native 0. This matches the proven primitive-metadata omission above.
- Native specular storage is **127 on every covered pixel**. Capture is 127 on 487,489 pixels and 128 on 379,223 pixels. Most B mismatches are this missing encoding behavior.
- BaseColor C differs on 175 covered pixels: 173 one-byte-step differences and two depth boundaries. Basic-shape interiors match exactly. Floor interior has 168 one-step BaseColor differences, 32 Metallic differences above one step (maximum9), and one Roughness difference above one step (maximum2). These sampling/rounding differences remain reported.
- D is byte-identical over the complete 1424×1040 extent. SceneColor is half-bit-identical on all covered geometry.
- Two depth outliers remain at `(1126,565)` and `(1123,597)`; the exact captured/native values are in `native-grid-initial.json`.

SceneColor has **13,062 full-frame mismatched background pixels**, all captured `(1,0.75,0.25,1)` yellow text. Visual inspection of the original `1853-SceneColor.png` confirms the repeated engine warning: “YOUR SCENE CONTAINS A SKYDOME MESH WITH A SKY MATERIAL BUT IT DOES NOT COVER THAT PART OF THE SCREEN...”. This is engine warning text, not object emissive or scene lighting. The comparator keeps it in the full-frame error counts and separately reports geometry/background. It does not silently copy or suppress it.

Read-only native integration review found the captured matrix transpose convention consistent with the successful depth result; grid inverse-clip position reconstruction subtracts high preview translation only, matching the captured PS. Texture loading enforces BC1 sRGB with all ten mips, and sampler defaults plus anisotropy8/LOD[0,FLT_MAX] match the capture. The two encoding omissions above were reported for the runtime owner to fix. This review does not claim final shaded-image equality or native stencil equivalence (the NPZ has no stencil plane).
