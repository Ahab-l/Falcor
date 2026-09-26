# Captured UE scene reconstruction

This package reconstructs the four opaque draws in `E:/rdc/ue/1.rdc` from their captured input assembly buffers, manual vertex-fetch tangent buffers, compressed GPUScene instance records, primitive records and View constant buffer. It does not use the unrelated blue/red cube smoke scene. The original capture and UE files are read only. The capture SHA-256, source-evidence hashes, resource IDs, byte offsets and EIDs are in `manifest.json`.

Run from the `Falcor-m0` worktree:

```powershell
python scripts/ue_legacy/extract_rdc_scene.py --replay
```

The command uses the existing `C:/Program Files/RenderDoc/qrenderdoc.exe` v1.45, starts its embedded Python process hidden, exports raw replay data, decodes the scene using numpy, and performs an independent CPU projection/depth check. The verified invocation returned exit 0 on 2026-09-09. Omit `--replay` to repeat decoding/checking with the existing raw files. `--capture`, `--out`, `--evidence` and `--renderdoc` make locations explicit. The decoder deliberately targets the four known draw contracts in this capture.

Generated assets live in `build/rdc-scene/`:

- `captured_scene.pyscene`: real Falcor meshes and camera; material names are stable for runtime routing.
- `mesh-{eid}-{name}.npz`: indexed local/world positions, packed-SNORM-derived normals/tangents, tangent sign, original decoded transform, and Falcor coordinates.
- `scene-manifest.json`, `view-uniforms.json`: exact view/projection values, transforms, captured material inputs, texture/sampler facts, source hashes and limitations.
- `raw/`: original IA/structured buffers, cbuffers, indexed postVS proof, all ten grid texture mips, DDS/PNG and captured depth.
- `reconstructed-coverage.png`, `depth-coverage-difference.png`, `reconstructed-depth.npy`, `object-id.npy`: independent verification output.

The durable manifest and View fields are mirrored in this directory. Asset paths in the manifest are relative to its `asset_paths_relative_to` directory.

## Geometry and camera

| BasePass EID | Prepass EID | Geometry | Vertices | Triangles | Primitive position, UE cm | Decoded scale |
|---|---|---|---:|---:|---|---|
| 1816 | 1023 | Sphere | 559 | 960 | (-690, -1030, 480) | (5, 5, 5) |
| 1827 | 1032 | Cube | 54 | 48 | (-1550, 30, 460) | (1, 3.25, 2.75) |
| 1838 | 1041 | Standing plane | 4 | 2 | (-1510, -380, 430) | (5.5, 4.25, 1), compressed rotation retained |
| 1853 | 1014 | Floor mesh | 90 | 96 | (0, 0, -0.5) | (8, 8, 8) |

The plane's decoded rotation maps local +X to world +Z and local +Z to world -X. Use the full decoded matrix, not scale alone. `SceneData.ush::DecodeTransform` is independently matched to the captured VS DXIL. PositionHigh plus relative translation forms the world translation. Decoded normal/tangent results are also checked against postVS.

`camera.translated_world_to_clip_row_major`, `camera.translated_world_to_view_row_major`, and `camera.projection_row_major` use row-vector multiplication, UE centimeters and +Z up:

```text
clip = [worldUECm + preViewTranslationHigh + preViewTranslationLow, 1] * translatedWorldToClip
```

The ViewRect is `[0,0,1421,1035]`; backing texture extent is `[1424,1040]`. The capture uses zero jitter, a 90-degree horizontal FOV, 10 cm near plane, infinite reverse-Z projection and pre-exposure `1.0749151706695557`. Source View fields come from a previously verified normalized layout prefix; exact originating shader-source identity remains unproven. Raw bytes are retained.

The Falcor adapter converts positions to `(UE.y, UE.z, -UE.x)/100` and directions to `(UE.y, UE.z, -UE.x)`. Its stock camera preserves view/FOV but uses a finite far plane and stock depth convention; the native UE runtime must consume the explicit captured matrices for exact reverse-Z. Mesh winding was checked against transformed normals and uses `frontFaceCW=False`.

## Projection evidence

The CPU path starts from original IA positions and decoded GPUScene matrices. It clips triangles in homogeneous D3D coordinates, culls using the captured `frontCCW=True`, and computes depth at pixel centers. PostVS is validation only and is never substituted for source geometry or shading inputs.

Results from the verified end-to-end replay:

- Captured coverage: **866,712** pixels. Reconstructed coverage: **866,711** pixels.
- Coverage IoU: **0.999998846214198**. One coverage mismatch at `(421,466)`.
- Depth error on shared coverage: p99 **3.36838e-8**, mean **2.00017e-8**.
- One depth error above `1e-6`: cube boundary `(1126,565)`, captured `0.01217195764184`, reconstructed floor `0.00346503136462`.
- Largest front-facing vertex screen error versus postVS: sphere `0.0001064` px, cube `0.0001288` px, plane `0.00003605` px, floor `0.0020676` px.
- Largest normal component difference versus postVS: `2.91e-8`; largest tangent component difference: `1.22e-7`.

The CPU rasterizer does not emulate hardware subpixel snapping or the top-left edge tie rule. Both boundary discrepancies remain in the manifest and difference image. This is strong geometry/camera reconstruction evidence, not a claim of pixel equality or final shaded-image equality.

## Material inputs and grid evaluator

Sphere, cube and plane share raw linear BaseColor `(0.8999999762, 0.8999999762, 0.8999999762)`, Roughness `0.6406999826`, Metallic `0`, Specular `0.5` and zero emissive. These values come from cbuffer2 and captured DXIL constants, before Falcor material packing or GBuffer quantization.

The floor's material is a texture-backed triplanar grid. `Source/RenderPasses/UELegacy/Materials/RDCGrid.slangh` implements the isolated raw material evaluation; it has no physical GBuffer output. It compiles successfully with the bundled Slang 2024.1.34 compiler to DXIL `ps_6_6`. The compilation harness and result are `build/rdc-scene/validate_grid.ps.slang` and `validate_grid.dxil`. Native program-2 integration and full render verification belong to the runtime task.

API:

```hlsl
RDCGridMaterialInputs evaluateRDCGridMaterial(
    float3 positionWorldUECm, float3 normalLocal,
    Texture2D<float4> gridTexture, SamplerState gridSampler,
    RDCGridParameters parameters);
```

`capturedRDCGridParameters()` supplies the exact captured uniform values. Outputs are raw baseColor, metallic, roughness, specular and emissive. Position should ideally be reconstructed from `SV_Position` as in the original PS. The original uses the View tile-relative camera position and primitive origin; in this capture both tile positions are zero and floor origin is `(0,0,-0.5)` cm. `normalLocal` is the un-normalized packed local normal carried by `TEXCOORD0`; floor local and UE world axes coincide.

Captured texture t5 is ResourceId 7376, **BC1_UNORM_SRGB**, 512×512 with all ten captured mips. The exported DDS header is **BC1_UNORM (DXGI 71)**: explicitly create an **sRGB SRV** when loading it. Preserve the captured mips. Sampler s0 uses wrap U/V/W, anisotropic min/mag/mip, maximum anisotropy 8, bias 0 and LOD range `[0,FLT_MAX]`.

The math follows captured DXIL `_309.._420`:

1. Subtract primitive origin, project onto normalized primitive axes, multiply by frequency `0.00999999977648` per cm.
2. Sample green on XZ, YZ and XY at half frequency. Blend XZ→YZ with `saturate(abs(normalLocal.x)*3-1)`, then blend toward XY with `saturate(abs(normalLocal.z)*3-1)`.
3. Sample red with the same projections/blends at full frequency.
4. Green blends checker BaseColor `0.18→0.23` and checker Roughness `0.5→0.65`. Red blends toward grid BaseColor `0.33854201436` and Roughness `0.3`; Metallic is the saturated red mask. Specular is `0.5`; emissive is zero.

Post-material view roughness overrides are `(0,1)` in this capture, so raw roughness is unchanged. Decal/GBuffer encoding/specular dither and pre-exposure are outside this material evaluator.

No shader among these four draws reads mesh UVs. No UV SRV is bound. The export records zero UV as an explicit unused placeholder; it does not claim UV recovery. The procedural floor uses position-derived coordinates. Original asset/package identities and final shaded-image equality remain unproven. The standalone Falcor scene's floor StandardMaterial is explicitly a placeholder until the native runtime routes the captured grid program.
