# Floor pixel trace: the position subtraction needs its original rounding boundary

At captured event **1853**, pixel **(948,1017)**, the full-frequency XY red sample is **0.26806640625** in the existing RenderDoc DebugPixel trace. Its final material outputs quantize to the actual captured GBuffer B and C bytes. The original native diagnostic returns **0.3017578125** for that sample. Extending `precise` through the final reconstructed-position subtraction in the parent's isolated diagnostic restores the sample to **0.26806640625** and eliminates the diagnostic's floor material differences: B has only the five existing specular differences, and C is exact over all 866,712 covered pixels.

This analysis only parsed existing files and disassembled the original DXIL offline. It did not edit core shaders, build, replay, or run the GPU. The rendering experiments and their attachment comparisons were run by the parent task. Compact SSA values, complete four-lane native diagnostic snapshots, source-file hashes, and actual attachment bytes are in `grid-pixel-trace.json`; the repeatable extractor is `scripts/ue_legacy/analyze_pixel_trace.py`.

## Position and sampling evidence

The trace contains 547 states. Its input SV_Position is `[948.5,1017.5,0.013219824060797691,756.4397583007812]`; captured depth, native depth, and the trace input share float32 bits `0x3c5897f6`. The original native diagnostic reports primitive **47** for every lane of the quad at origin (948,1016), consistent with the earlier source-triangle analysis.

| Value at (948,1017) | Captured debugger | Original native probe | Precise-position probe |
|---|---:|---:|---:|
| positionUE.x | -1698.982177734375 | -1698.9822998046875 | -1698.982177734375 |
| positionUE.y | -55.11358642578125 | -55.11357116699219 | -55.113555908203125 |
| positionUE.z | -0.49969482421875 | -0.499737411737442 | -0.499755859375 |
| delta.z | 0.00030517578125 | 0.0002625882625579834 | 0.000244140625 |
| U | -16.98982048034668 | -16.989822387695312 | -16.98982048034668 |
| V | -0.5511358380317688 | -0.5511357188224792 | -0.5511355400085449 |
| W | 0.0000030517576306010596 | 0.000002625882643769728 | 0.000002441406195430318 |

The debugger's homogeneous xyzw is `[0.8094666004180908,0.47665703296661377,-0.8513405323028564,0.0013219824759289622]`; after division, translated position is `[612.3126831054688,360.5622863769531,-643.9877319335938]`. The projection axes evaluate to the identity axes, and frequency is the captured float32 `0.009999999776482582`. BlendX=0 and blendZ=1, so full-frequency XY supplies the relevant final red value.

The two variable naming schemes were checked against `shader-1853-Pixel.txt` and a fresh offline `dxc -dumpbin` of the DXIL bytes from `reflection-1853-Pixel.json`. The resulting disassembly is `build/rdc-pixel-trace/original-1853.ll`; the DXIL container SHA-256 is `3da8c2eec6f170de8e15f32dcc2e9d6bfad33581ff4a353ef209c0c604600bd7`.

| Sample channel used | RenderDoc result / scalar | Original LLVM result / scalar | Debugger | Original native | Precise native |
|---|---|---|---:|---:|---:|
| Half-frequency XZ green | `_338` / `_339` | `%224` / `%225` | 0.5 | 0.5 | 0.5 |
| Half-frequency YZ green | `_342` / `_343` | `%228` / `%229` | 0.5 | 0.5 | 0.5 |
| Half-frequency XY green | `_353` / `_354` | `%239` / `%240` | 0 | 0 | 0 |
| Full-frequency XZ red | `_381` / `_382` | `%267` / `%268` | 1 | 1 | 1 |
| Full-frequency YZ red | `_385` / `_386` | `%271` / `%272` | 1 | 1 | 1 |
| Full-frequency XY red | `_392` / `_393` | `%278` / `%279` | 0.26806640625 | 0.3017578125 | 0.26806640625 |

Only the channels used by the material are compared: the full returned float4 values from the debugger are preserved in JSON, while the native diagnostic exports only the selected channels. For example, the debugger's full-frequency YZ sample returns green `0.501953125`, but the material uses that sample's red channel.

The debugger computes checkerMask `_361`=0, redMix `_389`=1, Z contribution `_395`=-0.73193359375, inverse `_397`=0.73193359375, metallic `_411`=0.26806640625, baseColor `_408..410`=0.2224997878074646, and roughness `_420`=0.4463867247104645. The corresponding material LLVM values are `%247`, `%275`, `%281`, `%283`, `%297`, `%294..296`, and `%306`.

## Agreement with actual rendered bytes

The debugger's final Target2 RGBA is `[0.26806640625,0.4998202323913574,0.4463867247104645,0.5058823823928833]`. Ideal nearest UNORM8 conversion gives B **BGRA `[114,127,68,129]`**, exactly the directly decompressed captured bytes. Target3 RGB is `0.2224997878074646` with alpha1; linear-to-sRGB followed by ideal UNORM8 gives C **BGRA `[130,130,130,255]`**, also exactly captured. The original native output was B `[112,127,77,129]` and C `[131,131,131,255]`.

These B/C conversions are consistency checks on this pixel, not a complete model of GPU render-target conversion. In particular, the trace's normal output is not used to assert bit-exact R10G10B10A2 conversion at half-step values. The actual capture and native A bytes were read and recorded independently.

The original native diagnostic's `packed_equal` flags show both diagnostic modes preserved all bytes of A/B/C/SceneColor relative to the parent's production baseline, SHA-256 `6cc418d24dca7d035dee9b8aa4924a7202ee1dfe201e8e64849254e64b93f029`. The production NPZ was subsequently replaced during parent work. The extraction therefore records the current NPZ's own hash and explicitly says whether it matches the original probe baseline; it does not silently associate later output bytes with the earlier probe.

## Float32 subtraction boundary

Original LLVM uses non-fast `fdiv` for `%114..116` and non-fast `fsub` for `%117..119`. In contrast, `build/rdc-pixel-probe/native-mode0.ll:264–273` contains non-fast `fdiv` `%61..63`, followed by **`fsub fast`** `%68..70`. This is an observed IR qualification difference.

There is a corresponding numerical constraint. Both the translated Z near -643.99 and the captured pre-view Z -643.488037109375 are in the float32 exponent interval with spacing **2^-14**. If division first produces a rounded float32 translated Z, subtracting the float32 pre-view Z must yield an integer multiple of 2^-14; the nearby subtraction is exact. Captured debugger positionUE.z ×16384 is **-8187**, and precise-native positionUE.z ×16384 is **-8188**. Original-native positionUE.z ×16384 is **-8187.69775390625**, which is not an integer.

Thus the original native result does not preserve that standalone float32 intermediate rounding boundary. The emitted fast subtraction and the controlled precise-position result support this diagnosis. This does **not** identify a particular reciprocal, FMA, division, or machine instruction sequence; machine code was not observed.

## Controlled precise-position diagnostic

The parent changed only the final `positionUE` variable to `precise` in an isolated diagnostic shader and supplied `build/rdc-pixel-probe-precise/result.json`. Both modes report the same capture-exact counts over the 866,712 covered pixels:

| Attachment | Exact pixels | Residual |
|---|---:|---|
| A | 866,711 | Existing one normal-code pixel |
| B | 866,707 | Existing five specular pixels |
| C | 866,712 | None |
| SceneColor | 866,712 | None |

At the target pixel, original-native implicit/fine-gradient/coarse-gradient red values are `0.3017578125 / 0.298583984375 / 0.3017578125`; precise-native values are `0.26806640625 / 0.30029296875 / 0.26806640625`. The reported LOD changes from `2.125` to `2.109375`. In both recorded quads, implicit results agree with the explicit coarse-gradient sample at each lane. Switching to fine gradients alone would not reproduce this pixel. These observations support preserving the captured position computation while leaving the production implicit Sample calls intact.

Precise-native V and W still differ from debugger values. The experiment therefore demonstrates restored material results and the subtraction boundary, **not identical debugger and native intermediate registers**. GPU division accuracy and debugger arithmetic can differ; their exact contribution here was not isolated. The single-pixel captured DebugPixel trace does not provide directly observed captured-neighbor register values or derivatives. Parent-owned production reruns and final acceptance reports remain the authority for full production results.

To regenerate the compact extraction from these files:

```powershell
python scripts/ue_legacy/analyze_pixel_trace.py --capture E:/Project/falcor/Falcor/docs/research/captures/2026-09-09-1 --precise-probe build/rdc-pixel-probe-precise/result.json --out docs/research/ue-legacy-rdc-scene/grid-pixel-trace.json
```
