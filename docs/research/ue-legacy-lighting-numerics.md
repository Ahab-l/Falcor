# UE E2655 lighting numerical comparison

Historical evidence snapshot: 2026-09-09, before the vertex-flow correction. **The 29-pixel version discussed below is historical. Current production has 41/41 selected ScreenVector inputs exact and 31 pixels / 31 RGBA16F channels different from E2655; exact stage equivalence still has not passed.** See [current vertex/input report](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-interpolants.md). The historical 95-to-29 result below was not a subset of the old failures: 14 old mismatch locations remained and 15 were new. Its PS/BRDF source is unchanged by the later VS fix, but its recorded attachment arrays and runtime identities must not be presented as current-run results. Five deferred BxDF implementations and final / end-to-end rendering are outside this investigation.

This report records read-only source, disassembly, artifact, and NumPy analysis. GPU builds and runs were performed separately by the integration task; this report did not launch GPU work or modify production. See [capture boundaries](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-capture.md) and [UE source contract](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-direct-lighting-source.md) for the broader lighting setup.

## Evidence provenance

| Evidence | What it establishes | Limit |
|---|---|---|
| [Captured PS disassembly](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt) and [captured VS disassembly](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Vertex.txt) | Instruction structure of the shaders captured at E2655. | RenderDoc's text representation is not final vendor GPU ISA. |
| [Fast CLI DXIL](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS.dxil.txt), [source](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/source.slang) | Native Slang CLI compilation of the frozen baseline source and defines. | This is **not a runtime shader dump** and has not been proved byte-identical to Falcor's executing shader. |
| [Precise CLI DXIL](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt), [source](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/source-precise.slang) | Native Slang CLI compilation of the production precise source and defines. | Same provenance limit; source includes later geometry validity guards as well as `precise`. |
| [Four GPU PixelHistory probes](E:/Project/falcor/Falcor-m0/build/rdc-lighting-history/history.json) | RenderDoc PixelHistory `shaderOut` from instrumented GPU execution. | Instrumented shader output is distinct from the original attachment and from the shader interpreter. |
| [106-point PixelHistory comparison and actual IA/PostVS export](E:/Project/falcor/Falcor-m0/build/rdc-lighting-pixel-history-95/replay-z1hgoafm/comparison.json) | Real GPU shader output at the retained baseline's 95 mismatches plus controls; actual IA and PostVS bytes. | A census of this baseline's mismatch pixels, not whole-image float32 shader equivalence or a census of the new 29 residuals. |
| [Interpreter trace at 280,475](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/debug-280-475-states.json), [trace at 650,950](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/debug-650-950-states.json) | Intermediate values for local, controlled CPU arithmetic demonstrations. | **DebugPixel interpreter values are not a GPU numerical oracle.** |
| [Production result](E:/Project/falcor/Falcor-m0/build/rdc-lighting-render/lighting-result.json), [production arrays](E:/Project/falcor/Falcor-m0/build/rdc-lighting-render/outputs.npz) | Actual native output attachment versus the captured target over the full allocation. | Validates only the stated E2655 fixture-backed stage; exact lighting gate remains false. |

Both CLI compilations used the same installed Slang CLI, SM6.6, row-major layout, and default floating-point mode, with their respective source snapshots and shader defines. Their differences are useful compiler evidence, but they do not isolate a single source edit or establish the runtime binary. A filename containing `shader-dump` does not change this provenance.

E2655 additively blends into an existing RGBA16F SceneColor destination. The native reference mode explicitly consumes E2624 SceneColor plus shadow-stage and scene-AO fixtures. The **target E2655 color is comparison evidence, never a shader input**. A CPU `float16(before + shaderOut)` calculation does not reproduce every hardware blend result and is diagnostic only.

## Confirmed main-output reassociation

For one channel, let `C = lightColor * mask`, `D` and `S` denote the uncolored diffuse and specular lobes after their scales and surface shadow, and `E` denote pre-exposure. The fast CLI compiler uses separate arithmetic chains for the debug MRTs and the main output:

```text
debugDiffuse  = C * D
debugSpecular = C * S
main          = (E * C) * (S + D)
```

The [fast CLI terminal chain](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS.dxil.txt:974) computes red debug diffuse `%690 = %685 * %689` and debug specular `%697 = %696 * %685`. Main red instead adds the uncolored terms `%702 = %696 + %689`, forms `%707 = exposure * %685`, then computes `%708 = %707 * %702`. Green and blue use the same structure. DefaultLit transmission is zero on this branch.

The captured PS completes colored lobes first: `_3170` is diffuse, `_3174` is specular, and [line 3573](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:3573) adds diffuse and transmission. [Line 3602](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:3602) adds specular, and [line 3614](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:3614) applies exposure. These are different float32 rounding chains even when the real-number formulas agree.

**The demonstrated transformation is common-factor extraction / reassociation.** The native terminal chain has no explicit `FMad`. Its `fast` flags permit further backend transformations, but this evidence does not identify a final GPU ISA FMA. Writing rounded debug lobes does not require the main output to reuse those values. Nor does this comparison prove that adding debug outputs caused the optimization.

Production now contains [this accumulator](E:/Project/falcor/Falcor-m0/Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang:214):

```slang
precise float3 radiance = (specular + (diffuse + transmission)) * gPreExposure;
```

In the [precise CLI terminal chain](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:1113), `%787/%790/%796` are the colored red diffuse/specular/transmission values. `%799` adds diffuse and transmission, `%802` adds specular, and `%807` applies exposure. The debug writes use these same colored lobe values. This restores the captured terminal grouping, allowing commutation of a binary add or multiply on these finite values.

However, **`precise` propagates into the BxDF and its inputs**, removing `fast` from many operations and adding `!dx.precise` metadata to dot, square-root, and other intrinsics. It therefore changes more than the terminal sum. The 95-to-29 improvement cannot be attributed to a controlled experiment changing only three terminal instructions.

The precise CLI's explicit `FMad` calls are confined to [the inverse-VP reconstruction path](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:363), inactive for this captured-view configuration. Its only three remaining `fmul fast` instructions, [lines 686–688](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:686), normalize capsule line irradiance; that branch is inactive for captured `SourceLength = 0`.

## Remaining instruction-order differences

The following are observed compiled arithmetic chains, not predictions from source parentheses. `r` is clamped roughness; `d` is the GGX denominator's pre-square term; `D` in the specular row includes sphere energy normalization; `F` is Fresnel. `G = falloff * area.NoL`, which reduces to the captured wrapped `NoL` for this directional light's unit falloff. Comparisons below permit binary operand commutation but retain association.

| Quantity | Captured PS | Fast CLI | Precise CLI | Anchors: capture / fast / precise |
|---|---|---|---|---|
| SphereSinAlpha before saturation | `((1-r*r)*radius)*invDistance` | Same captured grouping | `(1-r*r)*(radius*invDistance)` | [945](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:945) / [711](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS.dxil.txt:711) / [780](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:780) |
| Lambert diffuse | `(diffuseColor*invPI)*NoL` | `(G*invPI)*diffuseColor` | `(diffuseColor*invPI)*G` | [1090](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:1090) / [852](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS.dxil.txt:852) / [975](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:975) |
| GGX denominator | `(d*d)*PI` | Same captured grouping | `(PI*d)*d` | [1134](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:1134) / [922](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS.dxil.txt:922) / [1047](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:1047) |
| Specular NoL weighting | `((D*Vis)*NoL)*F` | `((D*Vis)*G)*F` | `((D*Vis)*F)*G` | [1162](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:1162) / [951](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS.dxil.txt:951) / [1077](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:1077) |
| Smith visibility division | `0.5/sum` | `0.5/sum` | `(1/sum)*0.5` | [1147](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:1147) / [935](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS.dxil.txt:935) / [1060](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:1060) |

Thus the baseline compiler already matched capture for SphereSinAlpha, GGX denominator, and directional specular weighting despite different source grouping. Precise restored source grouping in these locations while fixing Lambert and the terminal accumulation. The visibility difference is lower priority: multiplication by a power of two often preserves normal IEEE rounding equivalence. No residual pixel is attributed to it here.

### Newton rotation and NoH numerator

Let `n = original NoL`, `v = original VoL`, `nv = NoV`, `A = cosAlpha`, `c = cosTheta`, `t = sinTheta`. `nT/vT` are the tangent terms before Newton rotation, and `nB/vB` are `NoBr/VoBr`. These operations precede the final reciprocal-length multiplication and saturation:

```text
Captured:
    v'            = (t*vB + A*v) + c*vT
    NoH numerator = ((A*n + nv) + t*nB) + c*nT

Fast CLI:
    v'            = (c*vT + A*v) + t*vB
    NoH numerator = ((A*n + nv) + c*nT) + t*nB

Precise CLI:
    v'            = A*v + (c*vT + t*vB)
    NoH numerator = (A*n + (c*nT + t*nB)) + nv
```

Captured `_1009/_1010` and `_1014/_1015` at [1070–1076](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:1070), fast `%546/%547/%551/%552` at [816–822](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS.dxil.txt:816), and precise `%624–635` at [934–945](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:934) establish the distinct chains.

`VoBr` also differs: the [capture](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Pixel.txt:1027) computes `((2*NoV)*rInvLengthT)*NxLoV`, while [precise CLI](E:/Project/falcor/Falcor-m0/build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt:895) computes `((rInvLengthT*NxLoV)*2)*NoV`. These are concrete remaining association differences. Their presence alone does not prove they explain all 29 production residuals.

## GPU attachment results and diagnostic variants

The [production result](E:/Project/falcor/Falcor-m0/build/rdc-lighting-render/lighting-result.json) identifies a 1424×1040 allocation and 1421×1035 viewport, with 866,712 covered pixels. Full-allocation raw RGBA16F mismatches are `[8,10,11,0]`; each mismatched channel is exactly one half-precision ULP from capture. Signed native-minus-reference half-bit steps are `-1: 9`, `+1: 20`. Maximum absolute error is `0.0009765625`.

All 29 residuals have surface-shadow debug alpha `1`. Their stored GBuffer roughness bytes are `0` at 23 pixels and `7, 9, 78, 106, 124, 218` at one pixel each. This is a distribution, not proof that roughness or shadowing causes the mismatch.

Background and pixels outside the viewport match exactly. GBuffer, native depth, depth copy, stencil, coverage, base surface SceneColor, and the source-identity gates pass. Both images change RGB at the same 821,054 pixels. All recorded gates are true **except `lighting_hdr_full_extent_half_bits_exact`**. `final_image_equivalence` and `end_to_end_render_complete` are false.

The old `build/rdc-lighting-render/outputs.npz` path has been overwritten by the production 29-difference result. For the baseline, use the retained [diagnostic arrays](E:/Project/falcor/Falcor-m0/build/rdc-lighting-diagnostic/native-outputs.npz), which still contain 95 attachment mismatches. In this diagnostic shader, `directTransmission.rgb` stores actual pre-exposed PS radiance, **not physical transmission**. Its HDR attachment was retained as the baseline comparison; the later PixelHistory report's `diagnostic_hdr_comparison_independent_files = false` must not be cited as a new independent-file equivalence check.

The following counts were recomputed from the retained arrays against the same captured `referenceAfter` half bits. Counts describe mismatch **pixel locations**, with one mismatched channel per pixel in these variants. Names are experiment labels, not claims about captured geometry or runtime instructions.

| Variant | Mismatches | Retained from baseline 95 | New versus baseline 95 | Pixels whose color differs from production 29 |
|---|---:|---:|---:|---:|
| Retained baseline diagnostic | 95 | 95 | 0 | 96 |
| Production precise | 29 | 14 | 15 | 0 |
| Diagnostic precise-final | 29 | 14 | 15 | 0 |
| Precise + sphere / denominator / specular weighting | 29 | 14 | 15 | 2 |
| Above + Newton grouping experiment | 26 | 15 | 11 | 13 |
| Precise + source-derived mirrored triangle | 35 | 18 | 17 | 40 |
| Above + matrix mad / denominator experiment | 36 | 18 | 18 | 39 |
| Triangle + matrix mad / view position / denominator / sphere / weighting / Newton experiment | 35 | 18 | 17 | 38 |

**Only the production precise change is adopted.** The 26-result Newton experiment and all triangle variants remain diagnostic and still fail exact comparison. The 29-result change eliminates 81 old mismatch locations and introduces 15 new ones; calling it a pure subset reduction is incorrect. Equal mismatch totals also do not imply equal output images, as the 29-result weighting variant shows.

### Actual GPU PixelHistory

The expanded [106-point comparison](E:/Project/falcor/Falcor-m0/build/rdc-lighting-pixel-history-95/replay-z1hgoafm/comparison.json) passed its reference validation: sampled `preMod` and `postMod` round-trip to original E2624 and E2655 half bits, with valid single fragments. Among the baseline's 95 mismatch points, 133 of 285 shader RGB channels match bitwise, 135 differ by one float32 ULP, and 17 differ by two. None of the 95 has all three shader channels equal. Across all 106 unique points the counts are 158 equal, 142 at one ULP, and 18 at two ULPs. Probe/control groups overlap, so their pixel counts should not be summed.

The earlier four probes provide useful local examples:

| Pixel | Captured GPU shaderOut | Baseline native actual PS | Interpretation |
|---|---|---|---|
| `(768,653)` | RGB `(1.12109375, 0.9352384805679321, 0.7992108464241028)` | `(1.1210936307907104, 0.9352384209632874, 0.7992108464241028)` | Recombining the rounded baseline debug lobes and applying exposure matches capture at this pixel, while actual native PS differs. |
| `(280,475)` | R `1.3539273738861084` | R `1.353927493095398` | Native PS and debug-lobe recomposition both remain one float32 ULP above capture. |
| `(650,950)` | RGB `(0.2738017141819, 0.22841079533100128, 0.19518913328647614)` | Same RGB | A matching control, not universal proof. |
| `(291,668)` | RGB zero | RGB zero | Fully shadowed control. |

These samples support investigating arithmetic rounding without selecting a new universal formula from a few probes. In particular, the captured instructions apply exposure last; a coincidental match from exposure-before-sum is not evidence for changing that contract. Instrumented PixelHistory output and software half-blend predictions are separate evidence from the original attachment.

## Actual fullscreen geometry and CPU vertex check

The new export resolves the earlier geometry uncertainty with **actual IA bindings and RenderDoc GetPostVSData**, rather than source-code inference. E2655 has `IndexOffset = 6`, `VertexOffset = 0`, 16-bit index data, and drawn indices `[0,4,5]`. IA records have position XY `(1,1)`, `(-1,1)`, `(1,-1)`, respectively. Actual PostVS XY and screen-vector bits are:

| Draw vertex | Actual PostVS clip XY (`z=0,w=1`) | Actual screenVector float32 bits XYZ |
|---:|---|---|
| 0 | `(0.9999999403953552, -0.9999999403953552)` | `3f31db60 3f90dc59 bf602b68` |
| 1 | `(-3, -0.9999999403953552)` | `3fae5247 c033fbe8 bf602b68` |
| 2 | `(0.9999999403953552, 3)` | `3f926f6e 3f9a9691 40001495` |

The earlier source-derived assertion that viewport size times reciprocal produces exactly integer clip endpoints is **not established and is contradicted by these PostVS values**. Possible contraction or other backend behavior should remain a hypothesis until demonstrated. The source-derived mirrored-triangle experiments above do not themselves reproduce these captured bytes.

The [captured VS matrix chain](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/shader-2655-Vertex.txt:88) uses View cbuffer rows at byte offsets 832, 848, and 864. For each screenVector component, it computes `x*M0`, then `mad(y,M1,previous)`, then adds `M2`. The orthographic selector at byte 508 is zero, so this perspective matrix result is used.

A CPU check used the **actual PostVS clip XY**, the raw [captured VS View buffer](E:/Project/falcor/Falcor-m0/build/rdc-lighting/raw/2655-Vertex-cb1.bin), float64 for one fused multiply-add simulation, and float32 rounding at each indicated instruction. All nine resulting screenVector components match the exported PostVS bits. This verifies that the matrix and stated arithmetic path suffice for these inputs. It does not verify native VS output, derive the preceding clip-generation behavior, or establish identical raster interpolation at every pixel.

## Controlled CPU rounding examples

Reusing identical interpreter intermediate inputs and explicitly rounding each NumPy operation to float32 gives the following differences. These demonstrate association sensitivity; they are **not comparisons against actual GPU intermediate values**.

| Pixel / quantity | Source / precise-style grouping bits | Captured grouping bits |
|---|---|---|
| `(280,475)`, Newton NoH numerator | `3fdf94da` | `3fdf94db` |
| `(280,475)`, corrected VoL | `3f335742` | `3f335741` |
| `(280,475)`, red specular NoL weighting | `3c005867` | `3c005868` |
| `(650,950)`, GGX D with `(PI*d)*d` versus `(d*d)*PI` | `3d90fcac` | `3d90fcab` |

For reproduction, run the following read-only code with NumPy from this worktree. It prints the baseline/production mismatch sets, the local CPU examples, and the nine-component vertex comparison without writing files or running a GPU:

```python
from pathlib import Path
import json
import numpy as np

root = Path("E:/Project/falcor/Falcor-m0")
f = np.float32
bits = lambda x: f"{f(x).view(np.uint32):08x}"
prod = np.load(root / "build/rdc-lighting-render/outputs.npz")
base = np.load(root / "build/rdc-lighting-diagnostic/native-outputs.npz")
reference = prod["referenceAfter"].view(np.uint16)
old = np.any(base["lightingColor"].view(np.uint16) != reference, axis=2)
new = np.any(prod["lightingColor"].view(np.uint16) != reference, axis=2)
print("baseline, production, retained, new:",
      old.sum(), new.sum(), (old & new).sum(), (~old & new).sum())

for xy in ("280-475", "650-950"):
    states = json.loads((root / f"build/rdc-lighting/raw/debug-{xy}-states.json").read_text())
    v = {c["after"]["name"]: f(c["after"]["value"]["f32v"][0])
         for state in states for c in state["changes"]}
    n_source = f(f(v["_969"] + f(f(v["_1004"] * v["_949"])
                  + f(v["_1002"] * v["_965"]))) + v["_923"])
    n_capture = f(f(f(v["_969"] + v["_923"])
                   + f(v["_1002"] * v["_965"])) + f(v["_1004"] * v["_949"]))
    vl_source = f(v["_972"] + f(f(v["_1004"] * v["_955"])
                              + f(v["_1002"] * v["_968"])))
    vl_capture = f(f(f(v["_1002"] * v["_968"]) + v["_972"])
                   + f(v["_1004"] * v["_955"]))
    dv = f(v["_1061"] * v["_1071"])
    s_source = f(f(dv * v["_1083"]) * v["_914"])
    s_capture = f(f(dv * v["_914"]) * v["_1083"])
    d, pi = v["_1057"], f(np.pi)
    d_source = f(v["_1040"] / f(f(pi * d) * d))
    d_capture = f(v["_1040"] / f(f(d * d) * pi))
    print(xy, [(bits(a), bits(b)) for a, b in
               [(n_source, n_capture), (vl_source, vl_capture),
                (s_source, s_capture), (d_source, d_capture)]])

report = json.loads((root / "build/rdc-lighting-pixel-history-95/replay-z1hgoafm/comparison.json").read_text())
view = np.frombuffer((root / "build/rdc-lighting/raw/2655-Vertex-cb1.bin").read_bytes(), dtype="<f4")
matrix = view[832 // 4:880 // 4].reshape(3, 4)[:, :3]
fma = lambda a, b, c: f(np.float64(a) * np.float64(b) + np.float64(c))
assert view[508 // 4] == 0
for vertex in report["fullscreen_triangle"]["postvs"]["draw_vertices"]:
    words = np.array(vertex["record_words"]["uint32"], dtype=np.uint32)
    x, y = words.view(np.float32)[:2]
    calculated = np.array([f(fma(y, matrix[1, j], f(x * matrix[0, j]))
                            + matrix[2, j]) for j in range(3)], dtype=np.float32)
    print("vertex", vertex["draw_vertex_ordinal"],
          [bits(x) for x in calculated],
          (calculated.view(np.uint32) == words[6:9]).tolist())
```

## Next validation priorities

1. Obtain the actual native runtime VS/PS binaries or intermediate output probes before treating the CLI arithmetic as an exact account of runtime execution. The actual captured geometry and successful CPU matrix check provide concrete comparison inputs; native vertex outputs and raster interpolation remain unverified.
2. Investigate the verified Newton association differences with controlled native experiments and actual GPU values. Preserve immutable output hashes and inspect the full mismatch sets, including newly introduced pixels. The unadopted 26-result experiment is a lead, not an exact fix.
3. Keep the full-allocation raw half-bit gate. Do not replace it with a tolerance, visual similarity, target-derived shader inputs, CPU interpreter equality, or fitted parameters. Completion requires zero differences within the declared stage contract; it still would not establish full-render equivalence.

## Artifact identity

Paths below are relative to `E:/Project/falcor/Falcor-m0` only to shorten this manifest. Hashes identify the snapshot, because generic output paths can be overwritten by later runs.

| Artifact | SHA-256 |
|---|---|
| `build/rdc-lighting-shader-dump/lightPS.dxil.txt` | `796cd66b16d09756c2bd7a7463499570fdf23fb7e98f329fda7f4158dc8385b5` |
| `build/rdc-lighting-shader-dump/lightPS-precise.dxil.txt` | `a427a8508f6e083541a9caf7f332bc11a729b3feb4f9d48de47f7c26a2177419` |
| `build/rdc-lighting-shader-dump/source.slang` | `21d5f713ce3ee1c8cf74929ac71bc4831a8088804070e0ea505ab90983213317` |
| `build/rdc-lighting-shader-dump/source-precise.slang` | `2fed838876bd11afc2e396e95f9fd0b20a7313d69a22d36508654c4688880c98` |
| `build/rdc-lighting/raw/shader-2655-Pixel.txt` | `c4a958663f70f6271e05c254d25e372c88d3ef7e2d46a9b6d4e66e81662bdae8` |
| `build/rdc-lighting/raw/shader-2655-Vertex.txt` | `50b2745a3314aa82af49d4bf1f53d88a02afad54ed11ad347b66a62685e14c65` |
| `build/rdc-lighting/raw/2655-Vertex-cb1.bin` | `4045154c242f2bee105d25b8f17b4d52e3a00865e6bcb013d3d77eeca5ee05c6` |
| `build/rdc-lighting-history/history.json` | `dbf4f28cb1d9925961d6facae5ea599dd10e76f11d9c2c1133aba4589fd8d1a1` |
| `build/rdc-lighting-pixel-history-95/replay-z1hgoafm/comparison.json` | `d0cf73c86d82dd919b02331681ae2f6f1ff36986c1bacf248291ca13584ad236` |
| `build/rdc-lighting-render/lighting-result.json` | `2199f3329f13c24e85a35e01c67635f108bf3aee6dec8a86fb3bf7e7fa9fc907` |
| `build/rdc-lighting-render/outputs.npz` | `3c7285b9e771fbaa791fd8306b8a1fb6416c9bfd7ba2fb14835524e440351c0b` |
| `build/rdc-lighting-diagnostic/native-outputs.npz` | `98cec8117275d5f41b92a9b759da8e50fe692ffd82dfe7c93a37d20b8609e195` |
| `build/rdc-lighting-diagnostic-precise-final/native-outputs.npz` | `5ccf2295006ad83080d5fbeb9ebc645568caa015c98dcb47e52d4acc30b4c781` |
| `build/rdc-lighting-diagnostic-precise-final-dmul-sphere-weighted/native-outputs.npz` | `fcf25ed0d25fec6c7e3e9120ce4090cc676a4b9e24588d3838d1ec02e4a240c3` |
| `build/rdc-lighting-diagnostic-precise-final-dmul-sphere-weighted-newton/native-outputs.npz` | `b3970e00dc3470bddacc9b98f3cb5c2fbe81a41a43ebdf6ed62236c74525b68c` |
| `build/rdc-lighting-diagnostic-precise-ue-triangle/native-outputs.npz` | `b4c22f0ffadae664ca8997e22806509ca873cf0642810cc9d3d58f2ed296a816` |
| `build/rdc-lighting-diagnostic-precise-ue-triangle-mad-dmul/native-outputs.npz` | `aa9a0a4479d51606d6114c5008bffa028ea24868aa40d7151aebaf7361148c0b` |
| `build/rdc-lighting-diagnostic-precise-ue-triangle-mad-viewpos-dmul-sphere-weighted-newton/native-outputs.npz` | `0eb72dcdfde22829c0a1e2c298fe91ff7992d89f59354c1c66ab91690759e4a4` |

The production result further records lighting identity `4ed8ffbd01ca8fdc36147e5dc9cd498ecf1c1a9620e930f1d8ba85b4fa167270`, schema generation `c94b253a0b27aee0a3e35a00a93bf323d380ef1270718c888359b3b53b791fdd`, pipeline generation `25893346894d2ec322a87757a016e9545466f6cc31a0db7dd496ec4c63651894`, input generation `78bdf9ea8958905c20e730a680b62f5c3b7d2397cc0b6e45106baa605bb80132`, and plugin SHA-256 `bcf58af5f9a18626cd726e0775d59274652de294f70313f7f8ccfea7a286b697`. These identify the reported precise-29 run; no later diagnostic result supersedes its production status here.
