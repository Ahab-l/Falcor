# Five remaining specular codes: captured debugger, actual Codec field, and copied arithmetic

The parent's controlled **`specular_precise`** experiment removes all remaining GBuffer B differences across the full allocation. It changes only the copied Codec's final `biasedSpecular` declaration to `precise`: the five affected actual Codec fields become **`0x3f000fff`**, and their actual stored specular codes become **127**, matching the capture. A separate identity-DBuffer normal experiment removes the single A difference while leaving the five B differences unchanged. Both experiment NPZs were independently rechecked offline against captured bytes.

The diagnostic baseline, fixed native snapshot **`7ebee38e1c79995a8292517627c917d32a26baf9539983b46e57a1f7bdb8c626`**, had captured code **127** versus native **128**. Its captured DebugPixel simulation returned final specular **`0x3f000fff`**, the actual native `ueEncodeDefaultLit` field returned **`0x3f001000`**, and the separately copied scalar calculation returned **`0x3f000fff`**. The copied chain must not be treated as actual Codec internal registers. Both floats map to 128 under ideal nearest UNORM8 conversion; the successful actual GPU experiment establishes the observed correction, without identifying a hardware conversion or instruction mechanism.

This is a read-only offline analysis. The parent task acquired and closed the GPU sessions for the RenderDoc traces and native MRT diagnostic. No production files, GPU work, or replay were performed by this analysis. `specular-quantization-traces.json` contains compact records for the five traces, exact bits, both native diagnostic paths, fixed-snapshot bytes, and input hashes. The sphere trace is outside this report's scope.

## Actual attachment evidence and native diagnostic integrity

The listed five coordinates are the complete B.g difference set between the fixed native NPZ and directly decompressed captured `1853-GBufferB.bin.gz`. All other B channels agree at these pixels.

| Pixel | Captured B BGRA | Native B BGRA |
|---|---|---|
| (4,567) | [152,127,19,129] | [152,128,19,129] |
| (280,610) | [122,127,35,129] | [122,128,35,129] |
| (1060,722) | [127,127,0,129] | [127,128,0,129] |
| (1359,882) | [127,127,0,129] | [127,128,0,129] |
| (878,930) | [166,127,0,129] | [166,128,0,129] |

`build/rdc-quantization-probe/result.json` reports all four original A/B/C/SceneColor allocations byte-identical to the fixed production snapshot. The diagnostic NPZ SHA-256 is `d23f73194fb8b467967a030dbfeaeff0fab0a247d004fc5e58d28299a36c7578`, and pipeline signature is `967d8396e42d80fdba066cfa265057d12c8d84a3ca8efce2eb58f5c15668b4f7`. This supports interpreting the added MRTs without an observed change to those four production attachments.

The source `scripts/ue_legacy/quantization_probe_smoke.py` defines the distinction precisely:

- `debug0.w` is `probeFields.specular`, returned by the actual `ueEncodeDefaultLit(surface, context, probeFields)` implementation.
- `debug1.xyzw` is a separately written scalar sequence's `inner`, `firstFrac`, `scaled`, and `noise`.
- `debug2.xyzw` is that copied sequence's `centered`, `quantizationBias`, `biased`, and original `surface.specular`.

Exporting extra intermediate values can change optimization opportunities. Agreement of the copied sequence with the debugger does not prove the actual Codec computes those same intermediate values.

## Exact float32 constants and inputs

The baseline `Codecs/DefaultLit.slangh` supplies these constants by `asfloat`. They match the captured E1853 DXIL literals exactly. LLVM's hexadecimal literals below are the textual floating-point encoding of the float32 value, not a different source precision.

| Purpose | Float32 bits | Exact float32 value | Captured LLVM literal |
|---|---|---:|---|
| Frame X offset | `0x4202a8f6` | 32.665000915527344 | `0x4040551EC0000000` |
| Frame Y offset | `0x413d0a3d` | 11.8149995803833 | `0x4027A147A0000000` |
| Dot X coefficient | `0x3d897143` | 0.0671105608344078 | `0x3FB12E2860000000` |
| Dot Y coefficient | `0x3bbf4590` | 0.005837149918079376 | `0x3F77E8B200000000` |
| Outer noise scale | `0x4253ee82` | 52.98291778564453 | `0x404A7DD040000000` |
| Quantization scale | `0x3b808081` | 0.003921568859368563 | `0x3F70101020000000` |
| Base specular / centering magnitude | `0x3f000000` | 0.5 | `5.000000e-01` |

Captured frame index comes from View cbuffer byte **2712** (`cb0[169].z`) and is **0** in the file and all five traces. The native definition also selects frame index 0 and enables quantization dither. Trace inputs are the expected absolute pixel centers `(x+0.5,y+0.5)`.

## Exact SSA chain

The captured container was disassembled offline as `build/rdc-pixel-trace/original-1853.ll`. The RenderDoc text is the preserved `shader-1853-Pixel.txt`. Naming offsets change after the branch/resource handles, so the mappings below are explicit.

| Meaning | Captured LLVM | RenderDoc | Existing native-mode0 LLVM |
|---|---|---|---|
| Pixel center x/y | `%15`, `%16` | `_129`, `_130` | `%11`, `%12` |
| Frame unsigned / float | `%308`, `%309` | `_422`, `_423` | `%148`, `%260` |
| Frame offset x/y | `%310`, `%311` | `_424`, `_425` | `%261`, `%263` |
| Offset pixel x/y | `%312`, `%313` | `_426`, `_427` | `%262`, `%264` |
| Dot2 inner | `%314` | `_428` | `%265` |
| First fraction | `%315` | `_429` | `%266` |
| Scaled fraction | `%316` | `_430` | `%267` |
| Noise fraction | `%317` | `_431` | `%268` |
| Selected pre-dither specular | `%399` | `_511` | Constant 0.5 |
| Noise minus 0.5 | `%409` | `_521` | `%269` |
| Quantization bias | `%410` | `_522` | `%270` |
| Saturated pre-dither specular | `%411` | `_523` | Constant 0.5 |
| Bitcast / magnitude / UMin / float nonzero | `%412..415` | `_524..527` | Constant-folded to 1 |
| Bias times nonzero | `%416` | `_528` | Folded to `%270` |
| Biased specular | `%417` | `_529` | `%271` |
| Saturated final specular | `%418` | `_530` | `%272` |
| Final output | SV_Target2.y = `%418` | SV_Target2.y = `_530` | `%274` then `%294` phi to SV_Target2.y |

The captured arithmetic is:

```text
frame = uint_to_float(cb0[169].z)
x = frame * frameOffsetX + SV_Position.x
y = frame * frameOffsetY + SV_Position.y
inner = dot2(x, y, coefficientX, coefficientY)
firstFrac = frac(inner)
scaled = firstFrac * outerScale
noise = frac(scaled)
centered = noise + (-0.5)
quantizationBias = centered * quantizationScale
clamped = saturate(selectedSpecular)
nonzero = float(umin(asuint(clamped) & 0x7fffffff, 1))
bias = quantizationBias * nonzero
biased = bias + clamped
final = saturate(biased)
```

Captured scalar `fmul`/`fadd` operations in this chain are `fast`; dot and fraction are DXIL intrinsics without `!dx.precise`. The existing native-mode0 chain uses the same constants, dot/fraction operations, and fast scalar arithmetic, with the constant-specular simplifications shown above. No constant mismatch or added precise boundary is present in that baseline noise/encoding chain. The later controlled correction explicitly adds a precise boundary and must be evaluated from its experiment, not attributed to this older IR.

The native IR cited here is `build/rdc-pixel-probe/native-mode0.ll:473–489`, from the earlier pixel diagnostic baseline `6cc418...`. Its Codec chain agrees with the pre-correction DefaultLit source snapshot, but it is **not a disassembly byte-bound to the final `7ebee38...` snapshot or the new quantization diagnostic**. The actual new diagnostic's measurements are preserved separately; exact machine lowering is not inferred from the older IR.

## Captured DBuffer path is active, but neutral at all five pixels

The floor primitive's flags are `0x02010a89`, so bit 8 is set; View cbuffer byte **3580** (`cb0[223].w`) is **1.0**. Thus captured condition `%336` / `_450` is true. Assuming the branch is disabled would skip part of the real specular dependency chain.

The relevant path samples t4 with SampleLevel0: LLVM `%357`, RenderDoc `_470`, resource **500**. Captured metadata names it **BlackAlphaOneDummy**, a **1×1** texture. All five actual debugger traces return **[0,0,0,1]**, so:

```text
green = %359 / _472 = 0
alpha = %361 / _474 = 1
scaledBase = %389 / _502 = alpha * 0.5 = 0.5
dbufferSpecular = %390 / _503 = scaledBase + green = 0.5
selectedSpecular = %399 / _511 = 0.5
```

The native actual surface specular is also 0.5. Therefore the active DBuffer path supplies no numerical specular difference at these five pixels. It is verified rather than assumed absent.

## Measured values and the remaining boundary

Each captured trace contains 547 states. The inner dot values are:

| Pixel | Captured debugger inner | Native copied-chain inner |
|---|---:|---:|
| (4,567) | 3.614579916000366 | 3.6145801544189453 |
| (280,610) | 22.388092041015625 | 22.388092041015625 |
| (1060,722) | 75.38809204101562 | 75.38809204101562 |
| (1359,882) | 96.38809204101562 | 96.38809204101562 |
| (878,930) | 64.38809204101562 | 64.38809204101562 |

At (4,567), captured firstFrac/scaled/noise are `0.6145799160003662 / 32.56223678588867 / 0.5622367858886719`. Its captured quantization bias is `0.00024406584270764142`. At the other four pixels, firstFrac/scaled/noise are `0.388092041015625 / 20.56224822998047 / 0.5622482299804688`, and bias is `0.0002441107208142057`. The native copied chain uses noise `0.5622482299804688` and bias `0.0002441107208142057` at all five points.

Despite the first point's different dot/fraction results, **all five captured debugger final outputs and copied-native biased results are the same**:

| Observation | Value | Float32 bits | Ideal value ×255 |
|---|---:|---|---:|
| Captured debugger final `%418` / `_530` | 0.5002440810203552 | `0x3f000fff` | 127.56224066019058 |
| Native copied scalar `debug2.z` | 0.5002440810203552 | `0x3f000fff` | 127.56224066019058 |
| Native actual Codec field `debug0.w` | 0.500244140625 | `0x3f001000` | 127.562255859375 |

The float difference is **2^-24 = 5.960464477539063e-08**, one float32 ULP in this range. Both ideal scaled values are above the 127.5 boundary and convert to 128. Consequently:

1. The copied sequence is insufficient evidence for the native Codec's final value; the new MRT directly demonstrates that distinction.
2. The captured debugger's final float plus ideal UNORM8 conversion does not reproduce the actual captured 127 at any of these five points. It is not an original GPU register readback.
3. The one-ULP Codec/debugger discrepancy is measured. The controlled experiment below establishes that the precision change alters both the actual Codec field and stored code; it does not identify a specific FMA grouping, reciprocal, half conversion, or rounding implementation.

## Controlled experiments and actual output codes

Both parent-run variants preserve the baseline inputs. Their `result.json` files and `outputs.npz` hashes are snapshotted in the compact JSON, and this analysis independently recomputed the full-allocation mismatch counts against the captured A/B/C bytes:

| Variant | Local change in diagnostic copy | A differing pixels | B differing pixels | C differing pixels |
|---|---|---:|---:|---:|
| Baseline | None | 1 | 5 | 0 |
| `specular_precise` | `precise float biasedSpecular = bias + clampedSpecular` | 1 | **0** | 0 |
| `dbuffer_normal` | Apply a second normal normalization after material evaluation | **0** | 5 | 0 |

`specular_precise` output SHA-256 is `7f5be88261b2e11dbc2b1876a53cfcb2a8ddd534e93be5ce86d969bb0a4edb4a`. Its real Codec field `debug0.w` is `0x3f000fff` at all five pixels, and actual stored B.g is 127. The originally unchanged A/C/SceneColor bytes remain unchanged. This is a direct GPU result, and it takes precedence over the ideal conversion approximation. It supports the bounded precision change in this tested configuration without treating the ideal converter as a hardware model.

`dbuffer_normal` output SHA-256 is `1583ae682ab01b4f95dc4a0f517baa7e208f53f347537356318e5bd876cd1916`. Its sphere pixel (341,534) encoded normal is `[0.12170413136482239,0.7822892665863037,0.33506083488464355]`; packed A changes to the captured word `1434222717`. B/C/SceneColor are unchanged. This experiment is evidence for the missing identity-DBuffer normal operation, not authorization to normalize every material unconditionally. The local UE source guards and dummy definitions are documented in `identity-dbuffer-source.md`.

The still-unmeasured explanatory boundary is the original GPU's shader-output register and target-conversion implementation. Further investigation of that mechanism would require actual output values paired with actual stored codes in a controlled configuration; a copied scalar chain or ideal UNORM conversion alone cannot supply it. Such an investigation is separate from the demonstrated packed-output corrections. Parent-owned production integration and acceptance remain outside this diagnostic report.
