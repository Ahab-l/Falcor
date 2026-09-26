# Captured floor arithmetic and remaining packed differences

Read-only investigation of native NPZ SHA-256 `91b7252c480f1c3262e5032c43bd29db7942df5f55e4093d125e249a1730e8c3`. Original capture exports and reconstructed source buffers were read without modification. No replay, native build, or GPU work was performed.

The original event 1853 pixel shader is preserved in `E:/Project/falcor/Falcor/docs/research/captures/2026-09-09-1/reflection-1853-Pixel.json`, member `rawBytes`. Its 9,832-byte DXIL container has SHA-256 `3da8c2eec6f170de8e15f32dcc2e9d6bfad33581ff4a353ef209c0c604600bd7`. Windows SDK 10.0.26100.0 `dxc -dumpbin` decoded it offline through a temporary file, which was removed. LLVM excerpts below use that original container; the RenderDoc textual equivalent is `shader-1853-Pixel.txt`.

## Remaining physical channels

All listed mismatches have CPU object ID 4, the floor. Counts are pixels, with signed error defined as native minus captured.

| Attachment/channel | Different pixels | Signed integer errors |
|---|---:|---|
| B roughness, byte 0 | 141 | -2: 1; -1: 72; +1: 68 |
| B specular, byte 1 | 5 | +1: 5 |
| B metallic, byte 2 | 401 | -2: 6; -1: 188; +1: 198; +2: 8; +9: 1 |
| B model/flags, byte 3 | 0 | Exact |
| C base color, each RGB channel | 60 | -1: 24; +1: 36 |
| C AO, byte 3 | 0 | Exact |

B has 489 different pixels in total. All three C color channels differ together at the same 60 pixels. B/C overlap is 34 pixels; metallic/roughness overlap is 58; metallic/C overlap is 28. There are 83 roughness differences with unchanged metallic and 26 C differences with both metallic and roughness unchanged.

The largest residual is pixel `(948,1017)`: captured B BGRA `[114,127,68,129]`, native `[112,127,77,129]`; captured C `[130,130,130,255]`, native `[131,131,131,255]`. Its normal codes are `[511,511,1023]`, the floor top face.

## Explicit source association difference

Original LLVM lines 433–443 and 457 compute:

```llvm
%273 = fsub fast float %272, %268
%274 = fmul fast float %273, %233
%275 = fadd fast float %274, %268
%280 = fsub fast float %279, %275
%281 = fmul fast float %280, %244
%282 = fsub fast float 1.000000e+00, %275
%283 = fsub fast float %282, %281
%297 = fadd fast float %281, %275
```

Here `%275` is `gridMaskXZ_YZ`, `%279` is the full-frequency XY red sample, `%244` is `blendZ`, `%283` is the inverse grid mask, and `%297` is metallic before saturation. RenderDoc names the same values `_389`, `_393`, `_358`, `_397`, and `_411`.

`Source/RenderPasses/UELegacy/Materials/RDCGrid.slangh:93` instead forms the inverse after the sum: `1.0 - (gridMaskXZ_YZ + blendZ * (rxy - gridMaskXZ_YZ))`. The captured LLVM forms `(1.0 - gridMaskXZ_YZ) - blendZ * (rxy - gridMaskXZ_YZ)`.

The minimal independently testable recommendation is to replace only line 93 with:

```hlsl
float inverseGridMask = (1.0 - gridMaskXZ_YZ) - blendZ * (rxy - gridMaskXZ_YZ);
```

This preserves the source expression feeding base color and roughness. It does not change the metallic expression or specular dither. Both captured arithmetic and current material code permit fast-math reassociation, so emitted native IR must be inspected to establish whether this source edit survives compilation before interpreting an unchanged image.

With one million deterministic synthetic float32 sample triplets and the floor's axis-aligned blend weights, separately rounded evaluation of these two inverse expressions differs by at most `5.960464477539063e-08` (116,631 cases for blendX=0, blendZ=1; no differences for the two side-face selectors). These are synthetic inputs, not recovered GPU samples. This can move a value across a storage threshold but does not explain the metallic residuals.

## Roughness grouping already agrees

Original LLVM lines 461–466 are:

```llvm
%301 = fsub fast float %298, %300
%302 = fmul fast float %301, %247
%303 = fadd fast float %300, 0xBFD3333340000000
%304 = fadd fast float %303, %302
%305 = fmul fast float %304, %283
%306 = fadd fast float %305, 0x3FD3333340000000
```

This is exactly the current grouping at `RDCGrid.slangh:99`: `0.3 + inverse * ((r0 - 0.3) + checker * (r1 - r0))`. The original material cbuffer contains r1=`0.6499999761581421`, r0=`0.5`; the literal 0.3 is float32 `0.30000001192092896`. Replacing the current expression with a nested lerp would introduce a new association change rather than restore this captured LLVM.

## Sample-dependent and sample-independent residuals

Metallic uses the same red-sample blend expression in both sources and does not depend on inverseGridMask. Fifteen metallic pixels differ by more than one code, including the +9 case. With identical sample values in [0,1] and the captured floor's constant axis-aligned blend weights, ordinary float32 grouping errors in this short blend cannot produce a 9/255 change. The dominant metallic residual therefore requires different effective sampling inputs/results, or another upstream/backend difference; it cannot be attributed to the inverse-mask or roughness regrouping. There is no captured/native per-sample float readback here, so this investigation does not distinguish coordinates, implicit derivatives/filtering, or the texture-unit result.

The six original sample calls match the current shader's projection/channel contract: green at half-frequency XZ/YZ/XY, red at full-frequency XZ/YZ/XY. Captured axes derive from GPUScene columns `[8,0,0]`, `[0,8,0]`, `[0,0,8]`, each normalized by dot/rsqrt/multiply; the current evaluator uses unit axes. Primitive tile and View tile are zero, primitive relative origin is `[0,0,-0.5]`, and frequency is float32 `0.009999999776482582`. No incorrect coordinate scale or channel selection was found.

The View helper matches captured matrix offset 704, x multiply then y/z/w FMAs, and division. Captured LLVM then subtracts the relative translation using non-fast `fsub` at lines 277–279. Native subtraction occurs outside the precise helper at `UELegacyRaster.3d.slang:52` in an ordinary expression. This is a source precision-qualification difference worth checking in emitted native IR; it is not proof of an actual generated-code difference and is not the proposed edit above.

The five specular residual coordinates are `(4,567)`, `(280,610)`, `(1060,722)`, `(1359,882)`, and `(878,930)`, each capture 127 versus native 128. Specular is independent of the grid samples. CPU evaluation with separate dot terms and either FMA ordering produces the same final float32 `0.5002440810203552` at all five points. The first point has slightly different noise for one dot ordering, but that difference disappears at final float rounding. Thus a simple dot-FMA swap does not explain those five pixels in this CPU model. Their final shader-float/output-conversion boundary remains unmeasured; the current dither constants and source sequence match the captured PS.

No tolerances were relaxed and no residual is treated as equality. The recommended one-line inverse-mask edit is a bounded source-fidelity correction, not a claim that it will remove all floor differences.
