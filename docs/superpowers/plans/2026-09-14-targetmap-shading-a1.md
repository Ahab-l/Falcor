# targetmap A1: source-authored native raster and GBuffer

## 当前检查点：原材质与 GBuffer 对齐（2026-09-15）

- 已按用户要求读取原工程材质：Floor 为 MI_ProcGrid → M_ProcGrid → MF_ProcGrid，Sphere/Cube/Cube2 为 BasicShapeMaterial。13个原始资产身份和10份UE材质图导出已核对；实例参数无误。
- 地面残差根因定位到位置重建的浮点运算边界。独立候选将除法写为 precise rcp → precise multiply → precise camera subtraction；单独添加 precise 到原除法/减法的两个实验无效，已保留证据。
- 去掉 FloorProbe 的干净候选 floor-material-source，新进程 d96e34e8 / a8e6ce2e 所有 raw 逐 byte 重复。**整张1424×1040 allocation 的 GBuffer A/B/C/D、depth、stencil 与 E1452 逐位一致，包括padding**。覆盖1,258,627像素。Floor rough93、metal376、颜色49像素残差全部归零。
- 仅B/C相对旧939f4ccb变化；SceneColor仍有241,893分量差异。现有origin/vertex审计保留，无新增材质探针Pass/MRT。C++和二进制未改、无旧ABI或捕获输入；候选仍未迁入正式入口。
- 验证：四项GPU原始输出回归RED→GREEN，118原targetmap CPU与27候选CPU通过；实际Logger523/524无validation errors；旧1724文件检查点fresh PASS。
- **未完成**：A1背景/editor sky、源输入合同/正式入口迁移；A2主光/CSM；A3间接光/AO/SSR/history至E2793；A4 sky/fog/cloud至E2962；A5独立HDR验收。总对齐目标继续，不能把GBuffer对齐说成shading完成。
- 详细证据：build/targetmap-shading-a1/floor-material-diagnostic-report.md；新的floor-material-verification.json冻结2,323文件，fresh复核通过。以下较早的93/376/147残差说明为历史记录。


> Use subagent-driven-development for independent reference/evidence work; root alone runs GPU and integrates the native graph. No commits, merges or resets.

**Goal:** Independently render the four opaque source instances, using the saved source camera, then measure coverage, depth/stencil and GBuffer differences against E1452. This is a prerequisite, not E2793/E2962 completion.

**Architecture:** Existing Scene + MeshDraw + generated Schema codec + authored Slang. Capture resources only enter the offline comparator. No old Config, SchemaPipeline, UE ABI, Adapter or transaction. Source textures remain original assets, not captured SRVs.

**Tech stack:** Python/NumPy, JSON Schema, Slang, existing Falcor D3D12 runtime and read-only RenderDoc.

## Tasks
- [x] Confirm actual pipeline: 5 RTVs, D32S8, viewport 1421x1035 inside 1424x1040. E1452 writes only MRT0..3; MRT4 is bound but unwritten by this draw.
- [x] Reference worker (agent): TDD `_targetmap_gbuffer_replay.py`; export bounded raw reference, validate A0 identity, hashes, shutdown. Root replay reference-ffeea6e8 passed. Depth layout corroborated installed RenderDoc1.45 + official source + raw cross-channel masks; plane parity not claimed.
- [x] Source camera (root): `targetmap_native.py` + `test_targetmap_native.py`. Camera origin/basis, reverse infinite Z, separate unscaled projection/raster/allocation and source float parameter rounding verified. Unscaled2465x1795 independently identified by E4337/E4359/resource845, not fitted from a matrix. Original approved visible-aspect assumption was disproven and corrected.
- [x] Native graph initial baseline (root): source-only `targetmap_native_gbuffer.py`; generated Schema codec, authored Mesh shader, BasicShape/ProcGrid only, reverse-Z prepass. Two fresh final native processes emit byte-identical raw; GPU compile/runtime passed. Coverage/stencil exact, full GBuffer/shading still RED.
- [x] Material evidence (agent): actual shader/source mapping and typed neutral Slang implemented; frame counter advances0→1. Platform texture/default flag limits recorded. No old renderer ABI restored.
- [ ] Incrementally implement measured material/encoding differences in new authored Slang; test a single changed variable per run. No tuning to PNG.
- [x] Offline comparator: reports visible/padding/common coverage differences, depth/stencil and raw channel codes; typed native output metadata validated. Capture values only enter offline comparator. Material partitions are color proxies, not object IDs.
- [x] Initial-checkpoint CPU tests and independent reviews:96 scoped tests, source/result ownership/metadata/JSON snapshot defects fixed; initial/delta review in build/targetmap-shading-a1/python-review.md. This does not close remaining A1 texture/normal/depth/background work or A2–A5.

## Commands and gates
From `E:/Project/falcor/Falcor-m0`:
`python -B -W error -m unittest discover -s scripts/customrenderpipline -p 'test_targetmap_native.py' -v`
Initially must fail for missing new module; then pass numeric camera fixtures. Native runtime uses existing `build/windows-vs2022/bin/Release/Mogwai.exe --headless --enable-debug-layer --script <absolute-script>` with a finite script and owned-process timeout. Preserve stdout/stderr and actual native Logger. GPU failure is not replaced by CPU success.

Source scene: `build/source-targetmap/Scene.json`; A0 oracle: `build/targetmap-shading-a0/reference-a-0e5c7221/reference/manifest.json`. Outputs: fresh subdirectories of `build/targetmap-shading-a1`. No reference outputs in production script imports.

### A1 coordinate-path diagnostic (2026-09-14)
- [x] Revalidate current platform checkpoint (199 files); preserve baseline sources and outputs.
- [x] Identify actual divergence: E1452 SV_Position -> source SVPositionToTranslatedWorld versus native interpolated posW. Source SceneView.cpp:2650-2664 defines float viewport scales times double inverse camera matrix, cast float32; Common.ush:1507-1511 divides homogeneous world position.
- [x] In build/targetmap-shading-a1/coordinate-diagnostic only, test source-only reconstruction with synthetic camera points, varying viewport/projection sizes and translation invariance. CPU RED/GREEN before native experiment.
- [x] Copy the current example/runner into that owned directory, preserve original hashes, change only Floor position evaluation to the source screen reconstruction; retain source platform DDS/aniso8, geometry/depth/dither/normal/codec unchanged. No captured input read by renderer.
- [x] Root launch one finite hidden native run; strict native Logger, all outputs, exact executed inputs recorded. Offline partition comparison determines whether hypothesis helps; do not promote or relax tolerances merely because differences decrease.
- [x] Record residual pattern and next uncertainty, verify baseline checkpoint still unchanged. Full A1/E2793/E2962 remain open.


2026-09-15 checkpoint: coordinate-verification.json rehashes381files and recomputes all7 raw partitions. Source helper hyw85bej supplies exact source camera doubles (8views/384B), source float-pi screen matrix16/16 bits. Six native diagnostic launches all exit0/Logger clean; final reset7raw identical. PS-only improvement retained separately; VS candidate worsens Basic normal/depth slightly and is not promoted. Original platform199-file checkpoint unchanged,118 original targetmap CPU tests rerun pass. A1 material/vertex/background task and A2-A5 remain open.

### 2026-09-15 Mesh/vertex precision continuation
Previous turn is PROGRESS: real source camera export and differential/reset rendering changed the next investigation. Current root-owned render/build processes have exited.
- [x] Source audit finds Falcor PackedStaticVertexData::unpack converts stored f16 normals and **normalizes before interpolation**, although defaultVS itself does not normalize. Source Sphere OBJ normals instead have lengths0.9934..1.00618 and lie on a SNORM8/127 lattice; conversion to f16 and nearest lattice reconstruction recovers all original quantized codes offline. Cube normals are exact axes. This is an actual input-path discrepancy; do not globally change Falcor unpack.
- [x] Isolate custom VS raw-f16-normal decoding with a new source-owned shader under build; preserve all existing sources/checkpoints, run only this changed variable.
- [x] If supported by actual captured/source normal format, independently test lossless recovery of source SNORM8 code lattice, then compare actual GBuffer/depth with unchanged geometry.
- [ ] Continue source mesh/vertex/raster evidence for remaining depth and same-face attribution; do not promote all-pass projection with Basic regression or substitute these diagnostics for E2793/E2962.

2026-09-15 vertex checkpoint: raw normal3074->1443->13 verified onGPU, two resets7raw exact; source-cm/source-order remain unpromoted. ActualE1437 and source-ownednativecapture oracle establishIB/normal/VS and retainedcompiledorder. Next sourceE770 prepass and nativevertex intermediate differences; no blindprecision edits. See vertex-diagnostic-report.md / vertex-verification.json.

### Source-origin continuation (existing source-only architecture)
- [x] Record actualaddNode NodeIDs with sourcecentimeterorigin values; encode boundedtypedrawbuffer, rejectduplicates/nonfinite/stale/incomplete mappings.
- [x] Separate tinyMeshDraw GPUaudit ofactualinstance->globalMatrixID->source table; comparewithsame-source native-metertranslation onlyasidentitycheck. Preserve Scene mesh/materialdraworder.
- [x] Baselineoriginmode0 reproduces prior7raw; sourceoriginmode1 changesonlyorigininput, thenofflinefullraw/threshold/normalmagnitudediff andreset.
- [ ] Keepformalentry unchanged untilremainingboundariesverified; ifneededactualE770depthwriter/sourcegeometryprecision, thenA1background/A2-A5.

Source-origin checkpoint: c51995d1 baselineexact;7572ed23/c8c37a9a resetexact. Basic A/B/C/D exact; Basic339/Floor272396depthpixels remain1..2ULP, Floor124/463/177materialcomponents remain. NotA1/E2793/E2962complete. See source-origins-diagnostic-report.md; no formalpromote.

### Source-local-position precision continuation
- [x] Actual source E770 prepass clip/IB/View identical to E1437; own current native capture7raw matches c8c37a9a.
- [x] Source+Graph CPU model reproduces all native Sphere/Floor clip bits. Source-meterroundtrip causes79/77clip differences; sourcecm-text reducesSphere to18 andFloor to0.
- [x] Preserve native Scene meters. Add independent sourcecm localposition raw table keyed verified NodeID and draw-local native SV_VertexID (actual D3D12 audit, no vbOffset subtraction), owner/count/meter-input checks; no captured data.
- [x] Mode0 input/audit-only baseline must repeat7raw. Mode1 onlyswitchlocalposition; compareallraw/depth/material, newprocessreset.
- [x] Actual audit postVS must validate every submittedsourcevertex mapping, not just5instancepixels. Retain legacy934 unchanged, freeze new evidence separately. Remaining exactSphere lowbits/promotion/background/A2-A5 not waived.

Local-position result: mode0 f2805d78 baselineexact;939f4ccb/d8f25635 resetexact;e5a45f33 captureexact. Entiredepth/stencil/A/D exact; BasicallGBufferexact. FloorB93/0/376/0,C147remain. GPU757vertices fullyaudited. New1724checkpoint frozen; nextPSboundary/background/promotion/A2-A5 remainopen.
