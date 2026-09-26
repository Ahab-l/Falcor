# RDC 输入来源审计（历史实现与测试）

冻结日期：2026-09-10。只读代码和已有数据，未运行 GPU、RenderDoc replay、Shader 编译或 build，未修改生产实现。本次交付只新增本文；旧 GPU 证据不再完善或准入。

**结论：有。除了已披露的 SceneColor、ShadowMask、whiteAO、ShadowAtlas 和 CB，历史实现/测试还使用过捕获 Skin LUT、GPUScene 派生变换与 flags、级联 draw 归属/顺序、诊断 VS 的捕获 inverse-view-size 常量，以及 GPU observer 内的 PostVS 对照位。**

本文描述历史依赖，不表示这些入口目前仍可运行。源快照采样时，根代理正在实施输入拒绝，`rdc_lighting_smoke.run_native` 与 `rdc_gbuffer_smoke` 已先行抛错。本文不重新验证根代理报告的输入拒绝与 nativeLighting 回归，也不把历史捕获匹配当作新框架验收。

| ID | 数据 | 来源分类 | 历史用途 |
|---|---|---|---|
| I01 | E2624 SceneColorBefore | rendered intermediate image | direct GPU input to historical Lighting init |
| I02 | E2655 final ShadowMaskTexture | rendered intermediate image | direct GPU input to historical Lighting shader |
| I03 | E2655 ScreenSpaceAO white binding | capture-recovered constant fallback texture | direct GPU input |
| I04 | Captured 8192x2048 ShadowAtlas | rendered intermediate depth image | direct GPU input to completed historical projection probe |
| I05 | PreintegratedSkinBRDF LUT | capture-recovered precomputed algorithm table | direct GPU input in historical Skin/component/packed tests |
| I06 | PreExposure = 1.0749151706695557 | captured frame-generated renderer state | direct GPU constant in BasePass/Decode/Lighting |
| I07 | captured_view and lighting.view matrices | captured frame-generated renderer state | direct GPU view/position/ray constants |
| I08 | GPUScene transforms and packed instance state | captured generated scene buffer state | CPU decoding followed by direct GPU transform constants |
| I09 | primitive_flags = 0x02010A89 | captured packed primitive renderer flags | hardcoded direct GPU input to GBuffer encoding/DBuffer path |
| I10 | Light CB values converted to JSON | mixed captured light description and renderer-derived state | direct GPU light constants |
| I11 | Material CB values and RDCGrid parameters | capture-recovered material descriptors plus hardcoded object state | direct GPU material constants and shader literals |
| I12 | Mesh local IA/index/tangent buffers | capture-recovered original asset content | direct geometry input, with capture-derived world transforms |
| I13 | Resource7376 floor texture and captured mip chain | capture-recovered material texture asset | direct GPU material texture |
| I14 | CSM projection uniforms | captured algorithm-generated shadow/view constants | direct GPU CSM constants |
| I15 | CSM depth matrices and per-instance GPUScene records | captured algorithm-generated constants/buffers | planned native depth branch, not executed by this audit |
| I16 | CSM eleven-draw list and cascade membership | captured visibility/culling and submission decisions | planned GPU draw schedule |
| I17 | Quantization dither phase and DXIL arithmetic | capture-selected frame state plus algorithm evidence | frame phase GPU constant; arithmetic recomputed per pixel |
| I18 | Historical VS candidate inverse-view-size literals | captured CB state embedded in generated shader | direct GPU diagnostic rendering input |
| I19 | Historical PostVS expected bits in GPU observer | captured algorithm output used for GPU-side validation | direct GPU comparison constants; not raster output construction |
| I20 | Original local UE source imports | algorithm source code, not capture intermediate values | shader implementation source |
| I21 | GBuffer/depth/target color/PostVS CPU observations | captured outputs used for offline validation | CPU references in inspected main extraction/reporting chains |

## 来源边界

- View、PreExposure、GPUScene、阴影矩阵/偏置/fade、可见性列表是已生成的渲染器状态；放入 Scene.json、NPZ、sidecar、签名 Pipeline 仍保留捕获来源。
- 局部 IA 顶点/索引/SNORM 属性及地板材质纹理是从 RDC 恢复的资产内容，当前没有独立原 uasset/package 导入证明。烘焙 world/Falcor 顶点还包含捕获变换。
- 本地 Engine/Shaders 原文件导入的是算法代码。捕获 DXIL 转写也须区分算法常数与嵌入的场景/帧常数。
- 主网格提取中的 PostVS/深度、主报告中的目标 GBuffer/SceneColor用于 CPU 对比；历史 GPU observer、Lighting mask 分支是不能忽略的例外。
- 白 AO 是此捕获的 1x1 fallback，不能据此声称已实现 AO；静态 Skin LUT是算法预积分表，当前仍是捕获资源。

## I01 — E2624 SceneColorBefore

RDC-extracted RGBA16F SceneColor contains earlier lighting/SSGI. The DDS payload is copied unchanged, loaded with Texture::createFromFile, then scene_color_before.Load initializes the output.

后续边界：Reject captured image input; produce the preceding lighting state from the native graph.

来源：
- [scripts/ue_legacy/rdc_lighting_smoke.py:101](../../scripts/ue_legacy/rdc_lighting_smoke.py#L101)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L101)。
- [Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp:25](../../Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp#L25)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp#L25)。
- [Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang:97](../../Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang#L97)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang#L97)。
## I02 — E2655 final ShadowMaskTexture

The final BGRA8 mask was uploaded and sampled by the baseline Lighting branch. The later CSM probe did not feed that mask into CSM, but inherited and executed the baseline graph, so a global claim that expected masks were never graph inputs was too broad.

后续边界：Reject captured mask input; connect native shadow calculation to Lighting.

来源：
- [scripts/ue_legacy/rdc_lighting_smoke.py:102](../../scripts/ue_legacy/rdc_lighting_smoke.py#L102)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L102)。
- [Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang:184](../../Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang#L184)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang#L184)。
- [build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py:97](../../build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L97)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L97)。
## I03 — E2655 ScreenSpaceAO white binding

This particular binding is a 1x1 white engine fallback, not evidence that an AO image was computed. Its captured bytes were nevertheless uploaded as a fixture. Renaming it native AO would misstate provenance and algorithm coverage.

后续边界：Remove the captured DDS dependency. A native white fallback must be an explicit supported no-AO profile, not a claim of implemented AO.

来源：
- [scripts/ue_legacy/rdc_lighting_smoke.py:103](../../scripts/ue_legacy/rdc_lighting_smoke.py#L103)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L103)。
- [Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang:189](../../Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang#L189)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyLighting.3d.slang#L189)。
## I04 — Captured 8192x2048 ShadowAtlas

The probe converted captured depth words into an R16 DDS, loaded it with ImageLoader, and wired CapturedShadowAtlas.dst to CSM.shadowAtlas. Local PCF arithmetic did not establish native shadow-depth generation.

后续边界：Retire the captured-atlas acceptance branch; retain evidence only for offline comparison.

来源：
- [build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py:83](../../build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L83)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L83)。
- [build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py:121](../../build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L121)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L121)。
- [build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py:127](../../build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L127)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L127)。
## I05 — PreintegratedSkinBRDF LUT

The 256x256 BGRA8 sRGB LUT is extracted from E2655 t0 and uploaded with texture.from_numpy; packed Skin tests also load its captured DDS through lighting.resources.skinBRDF. The cross-model candidate reuses create_lut_and_probe. A static table is not automatically an independently sourced original asset; no such provenance is established by this path.

后续边界：Disable capture-backed LUT tests for native acceptance; independently source an original UE asset or regenerate the table from its documented algorithm.

来源：
- [scripts/ue_legacy/coat_skin_lighting_smoke.py:165](../../scripts/ue_legacy/coat_skin_lighting_smoke.py#L165)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/coat_skin_lighting_smoke.py#L165)。
- [scripts/ue_legacy/coat_skin_lighting_smoke.py:177](../../scripts/ue_legacy/coat_skin_lighting_smoke.py#L177)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/coat_skin_lighting_smoke.py#L177)。
- [scripts/ue_legacy/coat_skin_lighting_pass_smoke.py:382](../../scripts/ue_legacy/coat_skin_lighting_pass_smoke.py#L382)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/coat_skin_lighting_pass_smoke.py#L382)。
- [scripts/ue_legacy/lighting_diffuse_cross_model_candidate.py:413](../../scripts/ue_legacy/lighting_diffuse_cross_model_candidate.py#L413)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/lighting_diffuse_cross_model_candidate.py#L413)。
## I06 — PreExposure = 1.0749151706695557

View_PreExposure is read from the captured View CB and stored inside manifest.camera. The recipe passes it as preExposure; BasePass emission, Decode, and Lighting use it. Moving it into a Scene/Pipeline parameter and signing that parameter does not make it an authored scene value or native exposure calculation.

后续边界：Reject capture-derived exposure state; use an explicit native exposure policy and calculate any frame-dependent exposure locally.

来源：
- [scripts/ue_legacy/extract_rdc_scene.py:244](../../scripts/ue_legacy/extract_rdc_scene.py#L244)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L244)。
- [scripts/ue_legacy/rdc_lighting_smoke.py:322](../../scripts/ue_legacy/rdc_lighting_smoke.py#L322)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L322)。
- [Source/RenderPasses/UELegacy/UELegacyPasses.cpp:484](../../Source/RenderPasses/UELegacy/UELegacyPasses.cpp#L484)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyPasses.cpp#L484)。
- [Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp:160](../../Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp#L160)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp#L160)。
## I07 — captured_view and lighting.view matrices

Captured translated world-to-clip, screen/SV-position-to-translated-world, inverse depth transform, high/low pre-view translations, relative translation, rect, and extent drive rasterization and reconstruction. The Falcor camera descriptor is also derived from these CBs. Authorable camera pose/FOV must be distinguished from copying already-built View matrices and precision-split state.

后续边界：Use independently specified camera descriptors and native matrix/depth/jitter/high-low derivation; reject the captured_view and exact captured lighting transform interfaces.

来源：
- [scripts/ue_legacy/extract_rdc_scene.py:213](../../scripts/ue_legacy/extract_rdc_scene.py#L213)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L213)。
- [scripts/ue_legacy/rdc_lighting_smoke.py:124](../../scripts/ue_legacy/rdc_lighting_smoke.py#L124)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L124)。
- [Source/RenderPasses/UELegacy/UELegacyPasses.cpp:470](../../Source/RenderPasses/UELegacy/UELegacyPasses.cpp#L470)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyPasses.cpp#L470)。
- [Source/RenderPasses/UELegacy/UELegacyRaster.3d.slang:52](../../Source/RenderPasses/UELegacy/UELegacyRaster.3d.slang#L52)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyRaster.3d.slang#L52)。
## I08 — GPUScene transforms and packed instance state

The extractor reads captured instance indirection, GPUScene page layout, packed rotation/scale, relative instance translation and primitive high position. It decodes these into matrices, bakes world/Falcor mesh arrays, and supplies linear/normal rows and high/relative translation through source_geometry. Thus the local IA vertex path is not postVS injection, but its transforms still come from captured renderer buffers.

后续边界：Rebuild runtime transforms/precision splits/indirection from independently sourced object transforms, rather than importing GPUScene records or baked capture-derived transforms.

来源：
- [scripts/ue_legacy/extract_rdc_scene.py:267](../../scripts/ue_legacy/extract_rdc_scene.py#L267)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L267)。
- [scripts/ue_legacy/source_geometry.py:33](../../scripts/ue_legacy/source_geometry.py#L33)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/source_geometry.py#L33)。
- [Source/RenderPasses/UELegacy/UELegacyGeometry.cpp:152](../../Source/RenderPasses/UELegacy/UELegacyGeometry.cpp#L152)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyGeometry.cpp#L152)。
- [Source/RenderPasses/UELegacy/UELegacyGeometry.slangh:30](../../Source/RenderPasses/UELegacy/UELegacyGeometry.slangh#L30)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyGeometry.slangh#L30)。
## I09 — primitive_flags = 0x02010A89

All four instances receive the captured Resource806 primitive flags. The shader consumes bits 0x100/0x200 to encode per-object GBuffer data, and passes the flags to identity DBuffer handling. A user-authored casts-contact-shadow property is distinct from reusing the packed captured word.

后续边界：Reject baked packed words; derive the required bits from native object properties and supported features.

来源：
- [scripts/ue_legacy/rdc_lighting_smoke.py:155](../../scripts/ue_legacy/rdc_lighting_smoke.py#L155)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L155)。
- [Source/RenderPasses/UELegacy/UELegacyPasses.cpp:545](../../Source/RenderPasses/UELegacy/UELegacyPasses.cpp#L545)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyPasses.cpp#L545)。
- [Source/RenderPasses/UELegacy/Codecs/DefaultLit.slangh:46](../../Source/RenderPasses/UELegacy/Codecs/DefaultLit.slangh#L46)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/Codecs/DefaultLit.slangh#L46)。
- [Source/RenderPasses/UELegacy/UELegacyRaster.3d.slang:68](../../Source/RenderPasses/UELegacy/UELegacyRaster.3d.slang#L68)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyRaster.3d.slang#L68)。
## I10 — Light CB values converted to JSON

Color, direction, source radius/length, diffuse/specular scale, shadow channel mask, DistanceFadeMAD, ShadowedBits and channel mask are copied from captured CB fields. Some describe an authored light, but units/packing/preprocessing are not independently established here; source radius is 0.006420149467885494 and DistanceFadeMAD is [0.0005000000237487257,-9]. Derived fade/channel/shadow state must not be relabeled ordinary scene data.

后续边界：Source light descriptors independently; derive renderer units, direction, fade and shadow metadata from native state.

来源：
- [scripts/ue_legacy/rdc_lighting_smoke.py:129](../../scripts/ue_legacy/rdc_lighting_smoke.py#L129)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L129)。
- [scripts/ue_legacy/rdc_lighting_smoke.py:133](../../scripts/ue_legacy/rdc_lighting_smoke.py#L133)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L133)。
- [Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp:192](../../Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp#L192)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyLightingPass.cpp#L192)。
## I11 — Material CB values and RDCGrid parameters

Basic material baseColor/roughness/emissive facts are decoded from captured PS cb2. The floor evaluator hardcodes captured frequency, colors, roughness, axes and object origin (0,0,-0.5), and is transcribed from captured DXIL. Authored-looking material values are not screen-space outputs, but their current acquisition is RDC; the captured object origin is runtime scene state embedded in shader code.

后续边界：Use independent material/object descriptors; move object-dependent constants into native material inputs. Distinguish reconstructed arithmetic from original UE material source.

来源：
- [scripts/ue_legacy/extract_rdc_scene.py:122](../../scripts/ue_legacy/extract_rdc_scene.py#L122)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L122)。
- [scripts/ue_legacy/rdc_lighting_smoke.py:148](../../scripts/ue_legacy/rdc_lighting_smoke.py#L148)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L148)。
- [Source/RenderPasses/UELegacy/Materials/RDCGrid.slangh:42](../../Source/RenderPasses/UELegacy/Materials/RDCGrid.slangh#L42)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/Materials/RDCGrid.slangh#L42)。
- [Source/RenderPasses/UELegacy/UELegacyMaterial.slangh:52](../../Source/RenderPasses/UELegacy/UELegacyMaterial.slangh#L52)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyMaterial.slangh#L52)。
## I12 — Mesh local IA/index/tangent buffers

Positions come from bound IA vb0, triangles from original indices, and normals/tangents from bound SNORM buffers. They are local asset attributes, not postVS outputs. Original uasset/package identity is explicitly unestablished; UVs are unused zero placeholders. World/Falcor arrays in the NPZ already incorporate captured GPUScene transforms, so importing the NPZ does not remove the captured-state dependency.

后续边界：Obtain the original mesh assets independently and preserve local attributes; rebuild placements natively. Do not broadly reject ordinary mesh geometry just because a legacy adapter is named source_geometry.

来源：
- [scripts/ue_legacy/extract_rdc_scene.py:261](../../scripts/ue_legacy/extract_rdc_scene.py#L261)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L261)。
- [scripts/ue_legacy/extract_rdc_scene.py:250](../../scripts/ue_legacy/extract_rdc_scene.py#L250)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L250)。
- [scripts/ue_legacy/extract_rdc_scene.py:306](../../scripts/ue_legacy/extract_rdc_scene.py#L306)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L306)。
## I13 — Resource7376 floor texture and captured mip chain

raw/1853-grid.dds preserves all 10 captured mip levels and uses an explicit sRGB interpretation with the observed anisotropic sampler. It is material texture content, not a screen-space rendered image, but there is no independent original asset import in this chain. Captured cooked mips must not be described as newly generated native mips.

后续边界：Source the material texture/cooked asset independently or regenerate its mip chain with declared native rules.

来源：
- [scripts/ue_legacy/extract_rdc_scene.py:355](../../scripts/ue_legacy/extract_rdc_scene.py#L355)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L355)。
- [Source/RenderPasses/UELegacy/Materials/RDCGrid.slangh:6](../../Source/RenderPasses/UELegacy/Materials/RDCGrid.slangh#L6)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/Materials/RDCGrid.slangh#L6)。
- [scripts/ue_legacy/rdc_lighting_smoke.py:151](../../scripts/ue_legacy/rdc_lighting_smoke.py#L151)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L151)。
## I14 — CSM projection uniforms

The historical projection definition reconstructs exact float32 values from captured uniform records and submits ScreenToShadowMatrix, depth bias, fade, depth bounds, soft transition/sharpen and other cascade constants. Importing original PCF source does not regenerate these inputs.

后续边界：Build cascades and projection/bias/fade parameters from native camera/light/scene state.

来源：
- [build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py:78](../../build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L78)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/build/ue-csm-projection-gpu/run-dmh61eno/probe-executed.py#L78)。
- [Source/RenderPasses/UELegacy/UELegacyCSMProjectionPass.cpp:98](../../Source/RenderPasses/UELegacy/UELegacyCSMProjectionPass.cpp#L98)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyCSMProjectionPass.cpp#L98)。
- [Source/RenderPasses/UELegacy/UELegacyCSMProjectionPass.cpp:207](../../Source/RenderPasses/UELegacy/UELegacyCSMProjectionPass.cpp#L207)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyCSMProjectionPass.cpp#L207)。
## I15 — CSM depth matrices and per-instance GPUScene records

The stopped depth branch parses captured ProjectionMatrix/ViewMatrix/ShadowParams/near-clamp state and per-draw InstanceHeader, RotationScale, translation and primitive IDs. Its output atlas would be locally rasterized, but its setup is still capture-conditioned.

后续边界：Do not build or admit this path as native depth completion; implement native shadow setup and scene-state derivation first.

来源：
- [Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp:88](../../Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L88)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L88)。
- [Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp:107](../../Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L107)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L107)。
- [Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp:190](../../Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L190)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L190)。
## I16 — CSM eleven-draw list and cascade membership

The depth branch requires exactly 11 declared draws and trusts captured event order, split, instance and index counts. Replaying cascade membership is another algorithm output dependency beyond textures and CBs; native culling/selection is not implemented by that list.

后续边界：Derive cascade visibility and draw submission from native scene geometry and native cascade frusta.

来源：
- [Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp:94](../../Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L94)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L94)。
- [Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp:100](../../Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L100)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L100)。
- [Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp:192](../../Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L192)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyCSMDepthPass.cpp#L192)。
## I17 — Quantization dither phase and DXIL arithmetic

The recipe fixes frame_index_mod8=0 and enables the dither path to match this captured frame; it does not derive the phase from a native frame counter. DefaultLit code documents arithmetic constants/operation order from E1816 DXIL. Arithmetic constants are algorithm evidence rather than copied per-pixel noise samples; the captured/selected temporal phase is a separate provenance issue.

后续边界：Derive temporal phase from native frame state; retain only justified algorithm constants/source arithmetic.

来源：
- [scripts/ue_legacy/rdc_lighting_smoke.py:154](../../scripts/ue_legacy/rdc_lighting_smoke.py#L154)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L154)。
- [Source/RenderPasses/UELegacy/UELegacyPasses.cpp:485](../../Source/RenderPasses/UELegacy/UELegacyPasses.cpp#L485)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/UELegacyPasses.cpp#L485)。
- [Source/RenderPasses/UELegacy/Codecs/DefaultLit.slangh:10](../../Source/RenderPasses/UELegacy/Codecs/DefaultLit.slangh#L10)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/Source/RenderPasses/UELegacy/Codecs/DefaultLit.slangh#L10)。
## I18 — Historical VS candidate inverse-view-size literals

vertex_input_proof reads captured VS cb0 words 12:14 and inserts them as asfloat(hex) inverseViewSize literals. These construct clipXY and ScreenVector. candidate_ps_input_proof reuses the uninstrumented candidate VS, so removing its comparison bitmap does not remove this captured constant dependency.

后续边界：Retire capture-constant candidate shaders from native acceptance and compute inverse size natively.

来源：
- [scripts/ue_legacy/vertex_input_proof.py:76](../../scripts/ue_legacy/vertex_input_proof.py#L76)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/vertex_input_proof.py#L76)。
- [scripts/ue_legacy/vertex_input_proof.py:145](../../scripts/ue_legacy/vertex_input_proof.py#L145)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/vertex_input_proof.py#L145)。
- [scripts/ue_legacy/candidate_ps_input_proof.py:74](../../scripts/ue_legacy/candidate_ps_input_proof.py#L74)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/candidate_ps_input_proof.py#L74)。
## I19 — Historical PostVS expected bits in GPU observer

vertex_input_proof extracts 15 PostVS component words, embeds expected[15] in a GPU observation function, and writes equality flags. This is direct GPU use of captured postVS data, although it does not determine position/ScreenVector/color and is distinct from feeding postVS geometry. Thus a repo-wide claim that PostVS is only CPU data would be false.

后续边界：Keep captured output comparisons offline on CPU under the new no-intermediate-input rule; do not reuse this GPU observer.

来源：
- [scripts/ue_legacy/vertex_input_proof.py:131](../../scripts/ue_legacy/vertex_input_proof.py#L131)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/vertex_input_proof.py#L131)。
- [scripts/ue_legacy/vertex_input_proof.py:101](../../scripts/ue_legacy/vertex_input_proof.py#L101)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/vertex_input_proof.py#L101)。
- [scripts/ue_legacy/vertex_input_proof.py:109](../../scripts/ue_legacy/vertex_input_proof.py#L109)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/vertex_input_proof.py#L109)。
## I20 — Original local UE source imports

import_ue_lighting and import_ue_brdf read local Engine/Shaders source files and authenticate pinned hashes/ranges before copying code. The CSM candidate likewise slices local UE source. This differs from copying a captured texture, buffer or generated constant; source reuse itself is not an intermediate-result shortcut.

后续边界：Retain authenticated original algorithm source; independently derive its runtime inputs. Do not claim captured-DXIL material transcription has the same original-source provenance.

来源：
- [scripts/ue_legacy/import_ue_lighting.py:36](../../scripts/ue_legacy/import_ue_lighting.py#L36)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/import_ue_lighting.py#L36)。
- [scripts/ue_legacy/import_ue_brdf.py:36](../../scripts/ue_legacy/import_ue_brdf.py#L36)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/import_ue_brdf.py#L36)。
## I21 — GBuffer/depth/target color/PostVS CPU observations

The main mesh extractor compares reconstructed geometry to PostVS and CPU raster depth. rdc_lighting reporting compares final E2655 color, E1853 packed GBuffer/depth/stencil after native outputs. reconstructed-depth.npy/object-id.npy are CPU analysis products; no upload is observed in the inspected main recipe. This limited finding does not erase the separately documented GPU VS observer, baseline mask or captured view/geometry dependencies.

后续边界：Retain offline reference comparisons with explicit provenance; never use them to seed render graph resources or hidden renderer constants.

来源：
- [scripts/ue_legacy/extract_rdc_scene.py:289](../../scripts/ue_legacy/extract_rdc_scene.py#L289)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L289)。
- [scripts/ue_legacy/extract_rdc_scene.py:351](../../scripts/ue_legacy/extract_rdc_scene.py#L351)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/extract_rdc_scene.py#L351)。
- [scripts/ue_legacy/rdc_lighting_smoke.py:203](../../scripts/ue_legacy/rdc_lighting_smoke.py#L203)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/rdc_lighting_smoke.py#L203)。
- [scripts/ue_legacy/candidate_ps_input_proof.py:141](../../scripts/ue_legacy/candidate_ps_input_proof.py#L141)；[审计采样原文](../../build/rdc-direct-input-audit/run-84ke6lm7/frozen/scripts/ue_legacy/candidate_ps_input_proof.py#L141)。

## 框架先行的承接边界

不恢复捕获 projection/depth 准入。后续框架测试使用独立编写的场景与输入；重现时从原 UE 项目资产/描述重新生成 View、曝光、GPUScene、剔除、级联及图像资源，RDC仅作为离线观察/对比数据。不得通过重命名资源、签名副本、Shader 十六进制常量或普通场景参数隐藏捕获中间量。

本次文档生成验证了 50 份已采样源文件 SHA-256 及各引用的精确唯一行。原文件正在被根代理修复，行号可能后移，因此每条附采样原文。原采样记录：[source-receipt.json](../../build/rdc-direct-input-audit/run-84ke6lm7/source-receipt.json)、[supplement](../../build/rdc-direct-input-audit/run-84ke6lm7/source-receipt-supplement.json)。这是一份有限范围的来源审计，不是全仓库无 RDC 输入证明。
