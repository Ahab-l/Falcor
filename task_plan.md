# customrenderpipline migration

## Current request: RDC temporal inputs authorized (2026-09-16)
- User explicitly instructs: 所有和时间累积相关的都直接使用rdc内的数值. This supersedes all historical source-only temporal restrictions and the unanswered time/frame question below. The prior missing-authorized-history blocker is removed; do not ask again.
- Target remains E:/rdc/ue/2.rdc E2793 shading before postprocessing. Current-frame geometry/material/direct/indirect computations remain our renderer; import time/frame/exposure and actual temporal/cached inputs with event/resource provenance. Never substitute target final HDR as computed output.
- [x] Inventory/export actual temporal resources and CB values; preserve originals. export51314596 unchangedRDC,21assets,actual event/resource/hash provenance.
- [x] Independent source-rdc-temporal-v2 uses existing Asset/native2D/Cube/3D/raw-buffer interfaces. GPUaudit147cf30b exact including48Cube subresources; three GPUconsumerconversion checks; no C++/DLLchanges.
- [x] Connect readyenvironmentCube/SH,exposure/time/frame,SSGI/SSD/SSR/DFAO/cloud histories andGlobalDFcachedatlas/PageTable/scroll. CapturedSSGIhistorymapping andpreviousview matrices replace source-history assumptions. No ownedHistoryread/write or fabricatedwarmup.
- [x] Finalfullruns e9844ac3/51e564d1 cleanlogs813/814,81rawindependentrepeat,79nondepthsame-state repeats each,3GPUconversionchecks,7geometrybuffers unchanged. FreezeANDfreshverify699identities/8strictchecks. E2793MAE0.000010058492469824558;opaqueMAE0.000010686465608617028;maxopaque.00390625;globalmax.02783203125. No fullparityclaim.
- [ ] Complete shading parity remains separate: current sky background4pixels>0.01 (worstx1339y92), currentSSGI/quantization opaque residual,minorDFAO/SSRarithmetic; formalentry/E2962acceptance stillopen. Temporalinputrequestimplemented; prior missing-authorized-history blocker removed.
- Report: build/targetmap-shading-a6/rdc-temporal-report.md; commands: build/targetmap-shading-a6/rdc-temporal/README.md. Finalcandidate frozen, create another for future shader edits. NoactiveGPU/replay/build/session; Cfree82.34GB,Efree2.07GB.
- Prior blocked audit reset by explicit user change. Work resumes with concrete permission; no newgoal or final-completionclaim. Coutputsavailable86GB,E2.2GB; GPU/replay/buildserial,noagents.

## Current continuation: target runtime-state dependency (2026-09-16)
- Previous goal turn NO_PROGRESS: originalSaved/logsearch did not recover targethistory; same missing dynamicstate count2. Earlier source-scheduled cache completed/frozen6875files. No live GPU/replay/build at restoration.
- Capture-exposure hypothesis rechecked against original ReflectionEnvironmentRealTimeCapture.cpp and VolumetricCloud.usf: main exposure retained for LUT inputs, independently fixed capture exposure used for cache output. Current bindings/formulas already implement this; prior generated4-to2ramp test covers the boundary. No new patch justified.
- Fresh lineageaudit PASS39identities and original scheduler execution. E2793readsready898withoutframewrite; raw899/work900 do not recover precedingready generation. No source-derived actual historicaltimeline available; capturedtime/frame permission unchanged/unanswered, not asked again.
- Third consecutive goal turn NO_PROGRESS: re-enumerated48originalSavedfiles, no recordingfiles, WorldState/3loghashesunchanged; no newinputauthorization or liveGPU/replay/build. FreshofflineHDRrecompute exactlymatchesMAE.004165376143300254/max.2099609375. Same missingrecoverable/authorizedtargetdynamicstate persists. update_goal(blocked) succeeded; objective unchanged, NOTcomplete.
- Renderer/source/DLL/frozenoutputs unchanged. No GPU run or liveprocess/session. Read-only path guesses CaptureCloudMedium.slang and CloudMaterial.slangh corrected/avoided; actualmediumCaptureMedium.slang. Missing reportnames resolved through rg inventory; no filecreated at guessedpaths.
- Resume dependent alignment with new targetstate/timeline evidence or explicit inputboundary decision; any newly evidenced independent algorithm failure remains actionable. Do not time-fit or claim completeparity from existing subtests.

## Current increment: source-scheduled environment cache implementation (2026-09-16)
- Previous goal turn PROGRESS: original scheduler/resource provenance audit. No live GPU/replay/build at restoration.
- [x] Inspect SSR temporal source: no confirmed omitted major stage; no speculative shader edit. Inspect actual environment graph: every frame currently recaptures and immediately consumes complete Cube/SH, unlike verified source time slicing.
- [x] Design within already-authorized source-alignment work: retain rawCube, two filteredCube generations and SH; original source CPU scheduler selects sky/cloud faces, mip/filter work and ready index. Initialize fully, swap only after completing cycle, reset on owned history reset. No captured times/states or C++ changes.
- [x] Missing schedule RED, capture_schedule.py GREEN against720 original C++ rows, budgets1..6; firstframe/reset contract explicit.
- [x] Missing storage shader RED ae683f71. Native storage5a7bbf5c/04f84888 PASS:48 Cube face/mip subresources and8float4SH exact across changing-owned-seed History and reset, Logger794/795clean. No C++ changes.
- [x] Integrate partial sky/fog/cloud/mip/filter updates: V2 compute gates retain implicit globals, resolving actual D3D12 CBV b1 root-signature mismatch. cycles63cb9b1e PASS35 executions (frames0..33 and reset), Logger800 clean,194.25s. Initial full capture byte-exact; ready publication only frames17/33. No C++ change.
- [x] Cycles independent fc63bd39 PASS35frames/18raw exact vs63cb9b1e; Logger801clean. Full source-environment-cache4b746cbf/83e13a51 exit0/Logger802,803clean,156raw repeat,7History valid/updates2. Fullgraphs equal expected cache transformation; GBuffer/direct/shadow/DFcones unchanged. C-drive outputs conserve E capacity.
- [x] Offline E2793 HDR MAE0.004165376143300254,opaque0.0028782424130313635,max0.2099609375,ownexposure1.379812479019165. Slightly worse than parent; retain source-behavior correction without formal/best-image promotion. Target cached generation remains unknown.
- [x] Freeze AND fresh verify-environment-cache.py PASS6875identities,10strictnumericchecks,35cycleframes/18raw and156fullraw independentrepeat,7History. Previous5886/39checkpoints intact. Fullmetrics retained honestly; noformalpromotion.
- [ ] Complete E2793 remains active: source-supported environment/DF cache histories, remaining indirect/exposure residuals and formal entry. No captured dynamic-state inputs authorized; do not retest closed storage/scheduling/CBV boundaries as presumed missing work.
- This goal turn PROGRESS (implemented source schedule, independently verified GPU cycles/fullgraph and frozen evidence). No live GPU/replay/build/toolsession after finalverification; Cfree86.64GB,Efree2.21GB. Noagents,originalUE/RDC/C++/DLLchanges.
- Native API findings: Python RenderGraph exposes execute/getOutput but not setInput; native History supports only one-mip 2D textures. Use existing History with explicit lossless typed-value packing, no undocumented native bindings.
- Read-only lookup errors: PowerShell literal wildcard supplied to rg (corrected -g); guessed df-native-volume-contract and Native/History paths do not exist (actual CustomRenderPiplineHistoryPass.cpp). No source mutation from lookups.
- Integration failure retained: b69291a5/traceec381ed4, Logger796/797. CDB584d5850/Logger798 identified added explicit cbuffer vs implicit globals mismatch; fixed in CacheDownsampleV2/CacheFilterV2/CacheDiffuseSHV2 only. 4fae6ddb timed out120s without numeric failure;360s bound permits complete successful run63cb9b1e. Old failed shaders retained as evidence.
- Storage harness errors corrected without shader changes: Mogwai display tried to Blit Cube first (made 2D atlas first); DLL provenance path lacked plugins/ (fixed before successful runs). No frozen production candidate changed.
- Recovery tooling errors: rg literal wildcard corrected with -g; old attribution script assumes half DFAO and rejects currentfloat32; existing analyze-shading-residual-formats.py used unchanged. Lineagecheckpoint uses identitiesdict rather thanfilesdict; new verifier handles both schemas explicitly. No evidence/tolerance changes.

## Current increment: environment cache lineage audit (2026-09-16)
- [x] Fresh direct/shadow verifier: 1,109 identities unchanged and 12 numeric checks pass. Direct zero remains an offline common-exposure/pre-draw/native-half-blend result; complete live Lighting is open.
- [x] Recover environment resource lineage evidence and original source scheduler. No renderer changes or captured GPU inputs.
- [x] E1318/E1327 bind raw899 -> work900 mip4/5, while E2793 reads ready898 with no frame write. Stored workmip4 differs72/1152RGB from ready; stored mip5 predates E1327 (not current output).
- [x] Execute original C++ scheduler:720 authored rows across face budgets1..6. Default2 produces16-frame cycles and ready cloudface ages24..26 atstate9, versus rawwork8..10. Conditional behavior only, not recovered RDC history.
- [x] Freeze AND fresh audit-environment-cache-lineage.py PASS39identities. Prior5886filecheckpoint freshlyhashesunchanged. CPUdiagnosticcompileonly; no GPU/replay/rendererbuild or renderer changes. Audit corrects comparison premise; no full-frame improvement claimed.
- [ ] Independently reproduce matching environment generation, remaining indirect/exposure/history, formal entry. Complete E2793 active; no capture-time/frame permission inferred.
- Lookup errors: omitted directory in first environment-textures lookup and PowerShell wildcard passed to rg as literal; use known exact paths or rg -g filters.
- Recovery also misplaced export result.json under reference; actual manifest is one directory above. No post-E1327 raw export exists; report explicitly distinguishes predispatch mip5.
- Checkpointinspection initially sliced files aslist; actualdict checked viaitems. Fresh5886hashespass. Finalprocessinventory0; Efree309882880bytes.

## Current increment: object AO world reconstruction (2026-09-16)
- [x] Previous goal turn PROGRESS: source cache lifecycle evidence froze/rechecked 5,014 identities; no live GPU/replay/build, E free665MB.
- [x] Source audit: original object trace uses FDFVector3 world position, float ScreenToRelativeWorld matrix products, FRenderBounds-derived high/low object bounds, and original affine matrix. Current float-only coordinate path is not covered by earlier simplified fastlength harness.
- [x] Six-mode original-coordinate/cone differential f6ad74bd/8f769861 repeats18raw; original CPU SSE matrix execution agrees with independent Python. Mode0 matches parent; source full mode differs1982combined/36bent components, globals unchanged.
- [x] Strict source contract RED1982/36 before isolated source-df-object-world; fullf60f0fff/ec3666f8 GREEN0,154raw independent repeat,10numeric checks,6History, unchangedGBuffer/depth/stencil/shadows/parent/globalfields/Cube/SH. No C++/DLL change; new64-byte ownedbounds and4matrixrows only.
- [x] Freeze AND fresh verify-df-object-world.py PASS5886identities, previous5014intact. Sourcealgorithm correction completed; completeE2793notaligned. HDRMAE.004156696263499199 slightlyworse vsparentbest.004156681778352205; keep bothfrozen, noformalpromotion.
- [ ] Continue main environmentalCube/SHdynamicstate and remaining indirect/exposure/history; distantcacheprofile remains diagnostic-only. Do not repeat closed object-world/cone boundary as the presumed major cause. Formalentry stillpending.
- Previousturn/currentturn classification: PROGRESS (sourceboundaryfix, original-sourceGPUcontract, fullrepeat andfreshfreeze). Final process inventory0; Efree310714368bytes. No activeGPU/replay/build/toolsession. Capturetime/frame authorization unchanged.
- Firstfreeze failed recipebyte identity because pre-runraw-bufferedits leftmixedlineendings. Recipe nowreproduces as-renderedsourcebytes; no source,output,tolerance edits to repair verifier.
- Recovery lookup DistanceFieldSceneData.h did not exist; original FPrimitiveAndInstance is ScenePrivate.h. Full E2793 ACTIVE; capture-time permission unchanged.

## Current increment: source cache lifecycle diagnostic (2026-09-16)
- [x] Fresh direct/shadow recheck: 1,109 identities and 12 numeric checks pass; zero direct-light difference remains an offline common-exposure/blend result, not complete live Lighting.
- [x] Corrected-parent mip probe 5ffd501c and source-sized atlas probe ec43f5cb agree in all 28 common raw outputs. Default atlas dimensions do not repair the distant residual.
- [x] Execute original C++ clip-update functions: frequencies/phases [1,0], [2,0], [4,1], [4,3]. An explicitly authored low-to-full streaming timeline yields mixed cached mips at frame1 and full residency by frame4. This is not recovered capture history.
- [x] Source-scheduled GPU lifecycle d8932a8d/477a0f0d: all four states match original global cone oracle, settled state reproduces frozen parent-cache outputs exactly; 16 raw independent repeat. Authored frame1 global MAE 0.00000855563/max 0.01443565/0 above .03 versus settled MAE 0.00007544149/max 0.03719991/21 above .03. No captured history reconstruction or renderer repair claim.
- [x] Independent residency 79deed10 and atlas 34b4db18 reproduce 5ffd501c/ec43f5cb: 28/29 raw repeat and all 28 common outputs exact. Freeze AND fresh verify-df-cache-lifecycle.py PASS 5,014 identities, including prior 4,749-file checkpoint intact.
- [ ] Next source-only object-cone/world-reconstruction diagnostic: original ScreenToRelativeWorld uses float-matrix multiply before DF world reconstruction; current candidate uses translated matrix plus float camera. Audit object bounds low parts and world-to-volume transforms before substituting. Do not promote a capture-matching cache profile or edit frozen candidates.
- Current goal turn PROGRESS (new independent source-state evidence and frozen diagnostics), complete E2793 ACTIVE. Own time0/frame0,1 remains; capture-time authorization unchanged, no agents or live GPU/replay/build.
- Initial C++ diagnostic compilation failed on JSON string escaping; failed source/log retained, raw-string repair compiled successfully. Complete E2793 remains ACTIVE.

## Current increment: actual R8 static-parent cache (2026-09-16)
- [x] Previous goal turn PROGRESS: completed the near-field voxel histogram, proving the +1 code discrepancy is not limited to the zero plane.
- [x] Source composition audit e21b4338/6d7a81a0: original clip-relative double-float coordinates/affine transform and brick UV variants all preserve the current four R8 volumes; independent 16-file repeat.
- [x] Root boundary found: actual R8 static cache in a separate dispatch versus software round/decode. Source probes5ba10ab4/fb12629c change [67,22,4,0] bytes; all1,263,616 valid near-clip voxels now match RDC offline. Distant cache/residency remains open.
- [x] Isolated source-df-parent-cache adds4native static-volume passes; changes only DFGlobal.slang,df_graph.py,run-native.py and addsDFGlobalStatic.slang. NoC++/DLL orfrozencandidatechanges.
- [x] Fulle83c99d0/51a1ebd0 exit0/Logger777,778clean;154raw repeat. Parent/global bytes equal independent source contract; old93bytesRED,new0GREEN. Prior largestcone3,y58,x119 nowbitexact. Globaldifferent10497->1955,max.1216982->.0371999. E2793viewMAE.00415668177835,opaquemae.00286808418851,max.2099609375.
- [x] Freeze AND fresh recheck df-parent-cache-checkpoint.json PASS:4,749file identities,10strictchecks,154rawrepeat,16+16diagnosticrepeats. Earlier3,844-file checkpoint intact.
- [ ] Continue distantcache/residency,environmentCube/SHdynamicstate,otherindirect/exposurehistories andformalentry. Full E2793 remains ACTIVE; this turn PROGRESS, not blocked.
- Firstfreeze failed invalid assumption of invariantCube: actual exposure graph feeds changed owned previous exposure into captureAP/skyview/cloudmedium. Raw/filteredCube302/304componentschanged,max.0009765625; SH/LUTunchanged. Corrected invariant, not data/tolerances; no checkpoint written by failure.

## Current increment: direct/shadow status and near-field localization (2026-09-16)
- [x] Fresh `verify-direct-shadow-zero.py` exit 0: 1,109 unchanged file identities and 12 numeric checks. Shadow atlas/mask bitwise equal; direct-light zero is the offline common-exposure/pre-draw-HDR/native-half-blend comparison, not complete live Lighting.
- [x] Recover and reproduce `df-clip0-voxel-localization.json` exactly without overwriting it. Clip0: 67 byte differences, 32 unique approximate positions; clip1: 22 differences, 15 positions. Every difference is own = reference + 1.
- [x] Full histogram: only 48/67 clip0 and 12/22 clip1 values are 128 vs 127 at approximate z=0; remaining differences occur away from that plane.
- [x] Independently test original global composition position/double-float transform/brick UV arithmetic on owned inputs; see newer R8-parent increment. Those substitutions preserve allR8values; actualstaticcacheboundary fixesnearfielderrors. Bbox-nearest labels remain hypotheses. Full E2793 remains ACTIVE.
- Recovery errors: relative runpy path changed the identity-map script key; absolute path reproduced the saved report. First planning patch failed context validation atomically; corrected using actual headings. No evidence changed.

## Latest increment: source global-DFAO coordinates and loop (2026-09-16)
- [x] Previous goal turn PROGRESS: original cloud-core/environment diagnostic, no production repair. No live process at restoration.
- [x] Recover prior DF residency/step/atlas experiments. Existing page-atlas probe changed storage layout but retained absolute-world/divide/saturate UV arithmetic; isolated clip0 cone outlier remains.
- [x] Original global sampler/cone contract: olde58f9c0f RED42666 of208260 values; corrected59dee904 GREEN0 with referenceoutputsunchanged. Own textures/zero-scrollsourceconstants; no capturedGPUinputs.
- [x] Independent source-df-global-source candidate restores translatedsourcecoordinates, CPUUVscale/bias, originalsampling/conetrace; own16MiBpageatlaspacked by existingnative3DPass. NoC++/DLLchanges.
- [x] Fullf6a5bef8/c0b4beb8:150rawbyteexact, packedatlasbyteexact, globalconesexactsourcecontract,10strictchecks,6History, preservedGBuffer/depth/stencil/DFNormal/4sourcevolumes/SH. Globaltargetdiff48195->10497;22largeglobaloutliersremain.
- [x] Final v2checkpoint freeze AND freshPASS3844identities. Initialv1manifestmissed8generatedreports, retainedunmodified; v2collectsreportsaftervalidators. See df-global-source-report-v2.md and verify-df-global-source-v2.py.
- [ ] CompleteE2793 remainsNOTaligned. FullMAE.00415686222019 slightlyworse than best.00415676307726; keep earlierbest frozen, noformalentrypromotion. MainremainingenvironmentCube/SHcachedstate,globalDFcache/residency/clip0outlier,otherindirect/exposurehistories.
- CurrentturnPROGRESS, notblocked. Capturetime/framequestionunchanged; own0/frame0,1. FinalGPU/replay/buildprocessinventory0; Efreeabout1.48GB after hash-preservingcompression of213ownedA4raw reclaimed1.04GB.

## Latest increment: original cloud ray-march core (2026-09-16)
- [x] Previous goal turn classified PROGRESS: original material translation and independent GPU material-boundary evidence, no renderer improvement.
- [x] Compare original VolumetricCloud.usf loop to actual CloudTrace on six64x64 source capture faces. Baseline color22,163 differing components/max1.4305115e-6; weighteddepth max5cm. No exact core parity claim.
- [x] Isolate translated-shadow and layer-exit hypotheses. Finalized three variants each repeat24raw across independent processes; source-order changes do not remove small residuals. No production candidate editing.
- [x] Original core in60-node own environment chain, fixedtime0: independent763e3479/c734662c repeat66raw. Raw/filteredCube each2componentschanged(max.00048828125); SH andsky-onlyunchanged. Baseline restore22raw matches frozen380118a3time0. TargetCube MAE effectively unchanged(.00373853494724 -> .00373853649944), no renderer improvement.
- [x] Freeze AND fresh recheck PASS:2825file identities, including prior2404file material/production proof. No source/binary/frozen candidate changes.
- [ ] Complete E2793 remains open; no captured runtime inputs or time fitting. GPU/build/replay serial, no agents. E free665329664bytes: small diagnostics only until capacity is addressed.
- Next: cached/dynamic environment state or a new independently supported source-state discrepancy; do not repeat currenttime0 material, shadowcoordinateorder or coreloop as the presumed main error. DFAOcache/clip0, otherindirect/exposure histories and formalentry still open.

## Current increment: cloud material semantics audit (2026-09-16)
- [x] Restore frozen cloud animation diagnostic: 418-file checkpoint freeze/fresh passed; authored time grid is diagnostic only, no production time selected.
- [x] Fresh region analysis: 47,212 of 98,304 raw Cube texels vary; these contain 99.9294% of RGB absolute error. Static-region MAE 5.07810e-6; SkyOnlyCube unchanged. This localizes error, not proof that time alone causes it.
- [x] Fresh direct/shadow verification: 1,109 file identities and 12 numeric checks pass. Scope remains exact shadow plus offline common-exposure/native-half-blend direct-light comparison.
- [x] Original UE material translation via isolated NullRHI source helper: 237,890-byte HLSL, exit0, protected originals unchanged. No original project launch/package save.
- [x] Original translator body vs current cloud material: 65,536 authored inputs each at time0/1/16/128. Density/extinction bit-exact at0 and1; nonzero residuals at16/128 remain recorded, no tolerance erasure or production time selection.
- [x] eb577ba7/0e209399 independent GPU processes:13raw byte-exact, Logger750/751 clean. 2404-file checkpoint freeze AND fresh recheck PASS; earlier1160/1312 production checkpoints unchanged.
- [ ] Full original cloud integration/cached dynamic state remains separate: material-input diagnostic is not original whole-shader execution or full-scene parity. Do not re-audit the proven current time0 material graph as the main error without new evidence.
- [ ] Complete E2793 parity, Cube/SH dynamic state, DFAO cache/clip0, indirect/exposure histories and formal entry remain open.
- Frozen production candidates unchanged; no captured runtime inputs, time/frame permission unchanged, no time fitting. Full goal ACTIVE.

## Current increment: distant capture fog origin override (2026-09-16)
- [x] Trace ViewOrigin -> WorldCameraOrigin -> relative SkyLightPosition override in the original source.
- [x] Actual shader/graph generated GPU contract: 24,576 cases, old 9,600 above fixed 2e-6 tolerance; corrected zero, max 1.1920929e-7.
- [x] New source-capture-fog-origin changes three files; all other fog users retain their original wrapper and inputs.
- [x] c48824ff/cd81a2d0: 149 raw outputs identical, 10 strict checks, six histories, upstream unchanged. 1312-file checkpoint frozen and fresh recheck PASS.
- [x] Source behavior corrected, but E2793 is worse: full MAE .00421213950890, opaque .00291071621057, max .2109375. Retain earlier candidates; do not call this closer-image alignment.
- [ ] Full parity, Cube/SH dynamic state and other documented residuals remain unresolved.

## Current increment: capture cloud FogStruct propagation (2026-09-16)
- [x] Source snapshot copies main-view precomputed fog density; cloud shader does not request the distant-fog origin override.
- [x] Actual capture graph contract: 18 differing source-view/capture/face cases RED -> GREEN.
- [x] New source-capture-cloud-fog changes only the six cloud-medium density uniforms; earlier candidates remain frozen.
- [x] bd10b4ad/507d5983: 149 raw independent-reset exact; 10 strict checks, six histories and upstream invariants pass. 1113-file checkpoint frozen and fresh verification PASS.
- [x] Metrics are mixed: full E2793 MAE .00417713405805 (worse), opaque .00285764844007 (better), max .208984375 (better). Not complete parity or overall improvement.
- [ ] Complete E2793 parity remains open. Separate distant-fog origin override arithmetic requires further source audit; do not bundle it into this fix.
- Disk cleanup: lossless NTFS compression of two named owned old runs reclaimed 714 MB, all 277 file hashes unchanged. No capture inputs, original assets or binaries changed.

## Latest increment: source sky reflection mip index (2026-09-16)
- [x] Original C++ passes max mip index, not mip count. Actual graph contract old4 failures -> new4 passing sizes.
- [x] New source-sky-reflection-mip changes one expression only. 0a6c9fd8/91bd6aab:149raw independent reset exact,10 strict checks,6 histories,upstream intact.1160-file checkpoint frozen and fresh check PASS.
- [x] E2793 full MAE .00415676307726 (-13.6%),opaque .00286885390876 (-16.6%);max .2099609375 is worse. Not full parity.
- [x] Offline reflection attribution localizes largest-error region to Cube inputs after the mip fix; SH remains major diffuse input residual. No reference inputs sent to GPU.
- [ ] Remaining: Cube/SH generation and dynamic state, DFAO cache/clip0, indirect/exposure/history, formal entry. Capture time/frame authorization unchanged; own time0/frame0,1.
- Current full goal remains ACTIVE; previous and current goal turns both PROGRESS. All prior candidates frozen.


## Latest verified increment: source DFAO upsampling (2026-09-16)
- [x] Source UpsampleDFAO bodies, .51 UV clamp, float32 intermediate: generated GPU differences 4,408,028 -> 0.
- [x] Full b016a870/571b7ed6 independent resets: 149 raw files exact, 10 strict checks, 6 histories, upstream intact. New 1160-file checkpoint freeze and fresh PASS; source candidate frozen.
- [x] Direct/shadow 1109-file/12-check and SSR cold-input 1101-file checkpoints freshly passed.
- [x] Format-aware offline attribution validated on old f16 and new f32; major residual remains environmental inputs.
- [ ] Full E2793 parity: MAE .00481243531532, opaque .00343970608115, max .1953125. Cube/SH dynamic state, DFAO cache/clip0, indirect/exposure/history and formal entry remain.
- No new time/frame authorization, no captured renderer inputs. Existing candidates stay immutable. All native/GPU/replay/build sessions terminal; this turn made substantive progress, not a blocked turn.


## 当前增量：SSR 首帧输入与 DFAO 上采样（2026-09-16）
- [x] SSR cold input 修正已冻结：两次 149 raw 一致，1101 文件检查点；最终画面无明显改善。
- [x] DFAO 源函数、.51 UV clamp、f32 中间纹理专项 GPU RED/GREEN：4,408,028 分量差异降为 0。
- [ ] 完整候选运行与独立重启；阴影、混合、6 History、上游回归；新检查点和 fresh 验证。
- [ ] 完整 E2793 仍未完成：环境 Cube/SH 动态状态、DFAO 缓存/孤点、其余间接光/曝光历史、正式入口。
- 所有旧候选冻结。time/frame 无新授权，保持自产 time=0、frame=0/1。无捕获运行输入、无代理、GPU/replay/build 串行。


## 当前增量：环境光残差分解与最终混合边界（2026-09-16）
- [x] 云步数49152生成GPU case与源相同，排除此假设。
- [x] 最新分解：opaque radiance MAE .01182916，pre-sky .00121894，sky increment .01064860；离线仅换SH降为.00231913，环境输入是主要贡献，绝非渲染修复。
- [x] 8192像素GPU合同旧3f11bc79为12157分量不同，新aeefac07为0；独立CPU RTZ+RNE模型一致。
- [x] 新source-indirect-native-blend复用原生Fullscreen与Blit，diffuse/specular保持f32至单次相加；只新增2文件和修改run-native。SSR旧fallback保留作独立后续问题。无新C++/DLL，无RDC运行输入。
- [x] 1bfeb790/18079fb9两次149raw逐byte一致；10严格检查、6History和GBuffer/depth/stencil通过；1348文件检查点fresh PASS。全图MAE .0048508881→.0048150394，opaque略升.0034329137→.0034382677，max.1953125不变；63raw变化，SH不变。
- [ ] 完整E2793仍未完成；环境Cube/SH动态状态是主要残差，之后审计SSR无history输入顺序、DFAO缓存/孤点、其他间接光与曝光History、正式入口。无time/frame新许可，不读捕获作为输入。
- 磁盘满导致c9fb525e保存失败已保留；NTFS无损压缩17输出目录，2821冻结文件hash复核全不变；E盘余3993763840字节。报告indirect-native-blend-report.md，校验verify-indirect-native-blend.py。完整目标ACTIVE，本轮PROGRESS。


## 最新增量：Capture AP 原生三维采样与坐标（2026-09-16）

- [x] source-capture-ap-volume 使用现有 NativeVolumePass 接入原生Texture3D；生成65536查询旧201974分量不同→新0。数组控制cd734a60全部149raw等于旧候选；d88fb7d6/01f4653d两次原生运行149raw一致，12严格检查/6History通过；1556文件检查点fresh PASS。
- [x] source-capture-ap-coordinates 仅CaptureMedium恢复源length/normalize/acos和向量SubUV运算；32768射线源合同34744分量不同→0。2cfabf5c/3f85026f独立运行149raw一致，8严格检查/6History通过；1308文件检查点。当前场景全部raw仍等于前一3D候选，坐标修正无最终图改善。
- [ ] E2793未对齐：原生三维采样仅微降至MAE .00485088808850，opaque .00343291369758，max .1953125；SH .00082766391051。原GBuffer/depth/stencil、阴影、DFAOcones保持，完整环境光/间接光/曝光历史及正式入口仍待完成。
- [ ] 下一步实际云采样/步数与源CPU倒数、环境Cube/SH动态状态；DFAO缓存驻留/clip0孤点；其余间接光和正式入口。捕获time/frame权限仍未回复，继续自产time0/frame0,1。
- 报告capture-ap-volume-report.md、capture-ap-coordinates-report.md；复核对应verify脚本。所有源/DLL/RDC/UE工程冻结保持。完整目标ACTIVE，本轮为已验证修正进展，不是阻塞轮。


## 最新增量：环境 Cube 原生两次混合（2026-09-16）

- [x] 直接光/阴影1109文件+12数值检查 fresh PASS；阴影逐位一致，直接光为离线统一曝光/HDR混合后零差异，不扩大为完整live lighting。
- [x] 独立 NativeBlendPass 候选补齐通用显式 RGB/alpha 混合；生成8192像素与原生API全部一致，旧合并计算4977不同。六面Cube复制98304像素全部一致。正式Source/旧DLL未改。
- [x] source-capture-native-blend 接入每面雾/云两次R11写入。038a266d/2d4a063a独立重启149raw一致；8严格检查、6History、GBuffer/depth/stencil及DFAOcones通过；1319文件冻结检查点。
- [x] 云材质坐标32768生成射线全一致；纠正测试假设：Cube材质视图使用-capturePosition，只有单独大气视图用mainpretranslation。不改renderer坐标。
- [ ] E2793仍未完成：本轮MAE .0048957150906→.0048509723788，opaque .0035584759906→.0034330083406，max .1953125；SH MAE反增至.000827713377。旧pre-zero较低整图MAE候选仍保留。
- [ ] 下一步环境Cube/SH、实际云采样与动态状态；DFAO缓存驻留/clip0孤点；其余间接光/曝光/history及正式入口。捕获time/frame权限仍未回复，不采用捕获运行参数。
- 报告capture-native-blend-report.md；复核verify-capture-native-blend.py。完整目标ACTIVE，本轮为已证实原生混合修正进展，不是阻塞轮。


## 最新增量：有效零消光的云积分（2026-09-16）

- [x] source-cloud-zero-extinction 区分“材质拒绝采样”和“有效但消光为0”：后者照原源代码执行最小消光积分；阴影只在散射>0时计算，AP深度只在消光>0时累加。生成8192组GPU合同旧8192分量不同→新0；测试仅隔离控制流/透射/深度，不宣称实际材质采样一致。
- [x] 9866a5fb/fc578bce两次独立重启149raw一致，8严格阴影/混合/AP检查、6History、GBuffer/depth/stencil及DFAOcones保持；1230文件检查点。之前1232云层检查点保持冻结。
- [ ] 本次80raw变化，整图MAE .0047666285954→.0048957150906（变差）；opaque .0035615935653→.0035584759906、max .2001953125→.197265625（下降）；SH .000814982955，ownpreExposure1.3835818768。源码行为修正，不是整体画面改善，完整Shading仍未完成。旧较低整图MAE候选仍保留。
- [ ] 下一步实际source translated坐标/LWC材质采样、环境Cube/SH；DFAO缓存驻留历史/clip0孤点；其余间接光/曝光/history与正式入口。捕获time/frame权限仍待回复，未注入捕获运行数据。
- 报告 cloud-zero-extinction-report.md；复核 verify-cloud-zero-extinction.py。完整目标ACTIVE，本轮有实质修正，不是阻塞轮。


## 最新增量：源云层高度归一化（2026-09-16）

- [x] source-cloud-layer-source 按原源码分别将 bottom/top 转成float32厘米后求厚度、倒数和saturate。生成32768位置GPU合同：旧8190层内差异→新全部逐位一致；测试使用共享绝对位置，不扩大为完整坐标/材质采样一致。
- [x] d6268209/36733ec8两次独立运行149raw相同，8严格阴影/混合/AP检查、6History、GBuffer/depth/stencil通过。仅CloudTrace.slang改动，新1232文件检查点，旧候选冻结。
- [ ] 11云中间输出变化，最终E2793/Cube/SH/本帧曝光未变：MAE .004766628595377477，opaque .0035615935652898996，max .2001953125。完整Shading未完成，本次不宣称最终改善。
- [ ] 下一步源translated坐标/LWC材质输入和实际采样、环境Cube/SH；DFAO clip0孤点/缓存驻留历史；其余间接光/曝光/history及正式入口。捕获time/frame许可仍未回复，继续自产time0/frame0/1。
- 报告 cloud-layer-source-report.md；复核 verify-cloud-layer-source.py。完整目标ACTIVE，本轮有实质修正，不是阻塞轮。


## 最新增量：DFAO 源长度函数与变换（2026-09-16）

- [x] source-df-fastlength 恢复源lengthFast用于物体锥sample到clamp点的距离；源函数GPU合同15992不同→0。当前场景mip始终0，先前mip生命周期假设已排除，无对应改动。
- [x] 87d958dc/11f26728独立重启149raw相同，8严格检查、6History、GBuffer/depth/stencil保持通过；1160文件检查点。combined MAE .000508079724→.000106848633，超限32→6；E2793 MAE .0047666285954，opaque .0035615935653，max .2001953125。
- [x] 最新source-df-source-transform从源资产按f32矩阵运算生成独立80B物体描述；修正6字段，4对象56字段CPU和实际GPU输入逐位一致。defa6e9d/e38d9b95独立重启149raw相同，8严格检查、6History和上游通过；944文件检查点。
- [ ] 变换修正只改变9中间raw，最终E2793与fastlength逐字节相同；global仍22超限、combined6，最大.121698141。完整Shading未完成，正式入口未迁移。
- [x] 独立source-sized page atlas诊断0efd8b99：global MAE .000120135611，combined .000095756859；孤点和22global超限不变，未集成，不是正式HDR改善。
- [ ] 下一步global clip0那67个体素1code差异/孤点分支、global缓存加载历史、源云材质位置归一化与采样、环境Cube/SH、其余间接光/曝光及正式入口。捕获time/frame授权仍无答复，不采用捕获运行参数。
- 报告df-fastlength-report.md、df-source-transform-report.md；复核verify-df-fastlength.py、verify-df-source-transform.py。完整目标ACTIVE，本轮实质修正与诊断进展；所有候选和依赖冻结。


## 最新诊断：DFAO mip 驻留与跨帧缓存（2026-09-16）

- [x] df-step-audit / 807579d6 记录所有global cone steps，原bent/cones/globalCones逐byte不变。22超限=21条带+1孤点。
- [x] df-residency-audit / 39f16559 用源资产分别生成1/2/3驻留mips，3mip全部4volumes复现当前候选。clip0/1参考更接近3mip；clip2用1mip后体素差异20915→1493、max16→1code，clip3差异2801→793。
- [x] 仅诊断混合近3/远1mip / 4f7f89cd：global MAE .000132079309→.000065115562，超限22→1；max仍.121698141。不是正式renderer修复，不能写死该profile。
- [x] RDC当前帧GlobalDistanceFieldUpdate仅E231/E234 marker，无compose dispatch；源C++有staggered更新、NumMips==1反馈与延迟recache。支持历史驻留差异，尚未恢复真实历史序列。
- [ ] 下一步源streaming/cache生命周期、clip0孤点采样分支和object cones；其他云/环境/间接光/曝光及正式入口继续。实际renderer仍8991822d/28059e21，完整Shading未对齐。
- 报告 `build/targetmap-shading-a5/df-residency-audit-report.md`，`verify-df-residency-audit.py`，122文件新检查点；前1961检查点不动。


## 最新增量：DFAO 原生三维采样（2026-09-16）

- [x] source-df-native-volume 复用冻结 NativeVolumePass.dll，将4个global clipmap与物体brick atlas接到原生Texture3D；无新C++构建。array/global/all三个控制模式，捕获仍仅离线比较。
- [x] array a1d225b2与da621f7e原145raw完全相同；global d5dd5712；all 8991822d / 28059e21 独立重启149raw完全相同，Logger675–678 clean，16严格检查、6History及GBuffer/depth/stencil通过。新1961文件检查点。
- [x] 全局锥MAE .000343684702→.000132079309，max .183063090→.121698141；combined MAE .000701861014→.000508079724。采样维度问题改善。
- [ ] 全局仍22分量>.03、combined32分量>.03；原global诊断保持RED，不放宽门槛。E2793 MAE .0047683828769、opaque .0035798762680、max .2001953125，只有微小改善，完整Shading未对齐。
- [ ] 下一步检查source translated UV/稀疏page与局部锥残差，云材质位置/高度归一化（源层厚1000064cm vs包装1000000cm）、环境Cube/SH、其余间接光/曝光/History及正式入口。捕获time/frame许可仍未获答复。
- 报告 `build/targetmap-shading-a5/df-native-volume-report.md`；复核 `python build/targetmap-shading-a5/verify-df-native-volume.py`。完整目标ACTIVE。本轮原生资源接入已完成，不是阻塞轮；候选及DLL已冻结。


## 最新增量：云介质各阶积分（2026-09-16）

- [x] source-cloud-media-order-unroll恢复源逐octave系数/消光累加和显式unroll；相同材质输入8192组GPU合同旧98570分量不同、新0差异。混合采样诊断的舍入差异单独记录，未声称全部云采样一致。
- [x] da621f7e/4ac18a13独立重启145raw相同，Logger672/673 clean；8严格检查、6History、GBuffer/depth/stencil保持通过。1313文件新检查点。
- [ ] E2793与前一原生3D候选逐字节相同：MAE .0047687151102、opaque .0035802657310、max .2001953125；本次未改善整图。13中间输出变化，环境Cube/SH及本帧曝光不变。
- [ ] 下一步：原UpdateMaterialCloudParam的位置/高度归一化和实际材质采样；环境输入及其余间接光/AO/曝光/History、正式入口。捕获time/frame权限仍未获回复。
- 报告 `build/targetmap-shading-a5/cloud-media-order-report.md`；复核 `python build/targetmap-shading-a5/verify-cloud-media-order.py`。完整目标ACTIVE，本轮为源积分修正和排除假设的进展。

## 最新增量：原生云噪声 Texture3D（2026-09-16）

- [x] 已复核直接光/阴影：1109文件、12项数值检查通过；精确范围是阴影逐位一致、直接光离线统一曝光+half混合后RGB零差异，不是完整live lighting。
- [x] 通用ShaderPass/AssetPass隔离候选支持固定单mip Texture3D；独立NativeVolumePass.dll，不覆盖冻结DLL。315体素native oracle、105体素DDS重复inputOutput、9项拒绝测试通过。
- [x] source-cloud-native-volume主视图+六capture正常GPU图直接采样源3D噪声。数组控制d9f3cb2b全145raw等于sphere基线；原生b70ea5fd/f283bfde独立重启145raw相同，12严格检查、6History及GBuffer/depth/stencil通过。新1378文件检查点。
- [ ] E2793仍未对齐：MAE .0047687151102，opaque .0035802657310，max .2001953125。全图微降、物体略升，不宣称整体改善。SH不变。
- [ ] 剩余源云逐octave消光/散射顺序、环境Cube/SH、间接光/AO/曝光/History与正式入口。捕获time/frame权限仍待回复，继续自产time0/frame0/1。
- 报告 `build/targetmap-shading-a5/cloud-native-volume-report.md`；复核 `python build/targetmap-shading-a5/verify-cloud-native-volume.py`。完整目标ACTIVE；本轮为原生GPU资源集成进展，不是阻塞轮。

## 最新增量：云层球面求交（2026-09-16）

- [x] `source-cloud-sphere` 恢复源二次方程的方向长度平方项；源提取 GPU 合同147456射线严格0差异，旧80939条不同。
- [x] dd4cd33a / 8de6cd32 独立重启145raw一致，Logger657/658 clean；既有GBuffer/depth/stencil、阴影/HDR混合/AP、6History通过，新922文件检查点。
- [ ] 完整E2793仍未对齐：MAE.0047703811476（比上一.0047703649679略升），opaque.0035787219705，max.2001953125。源求交更准确，但没有整图改善。
- [ ] 源多次散射的逐octave累加、原生Texture3D通用接入、环境Cube/SH及其余间接光/曝光/历史、正式入口仍未关闭；云动画时间/缓存状态待匹配，未获许可使用捕获时间/帧号。
- 报告 `build/targetmap-shading-a5/cloud-sphere-report.md`；复核 `python build/targetmap-shading-a5/verify-cloud-sphere.py`。GPU/replay均已退出；完整目标ACTIVE。本轮为实质源算法进展，不是阻塞轮。

## 最新复核与增量：云自阴影步进（2026-09-16）

- [x] 用户所问直接光/阴影：1109 文件、12 数值检查 fresh PASS；阴影逐位一致，直接光为离线统一曝光+原生 half blend 后全图零差异，不能扩大为完整 live lighting。
- [x] Linear/Aniso8 的 SampleLevel0 GPU 对照：生成数据和源2D/3D/Array共12项逐字节相同，当前误差不由此解释。
- [x] `source-cloud-shadow-steps`：云自阴影改回原源码的浮点步长累加；源提取合同316组严格0差异，旧29466分量不同。
- [x] 完整 e5346da5 / f1b40997 独立重启145raw一致；GBuffer/depth/stencil、阴影、原生混合、CaptureAP alpha和6History通过。964文件新检查点已保存。
- [x] 启动器固定并记录既有5项源配置，验证器比较新旧渲染图。早期漏选项的a03ca042/6bb79b85无效对比保留，不能当渲染回归。
- [ ] E2793仍未完成：本次最终HDR/SH/曝光相对上一相位候选逐字节不变，MAE仍.0047703649679，opaque.0035787070265，max.2001953125；本次不声称整图改善。
- [ ] 后续：源云逐octave消光累加、环境Cube/SH和其余间接光/曝光/历史；正式入口迁移。捕获时间/帧号的异步权限问题仍未获答复，继续自产time0。
- 报告 `build/targetmap-shading-a5/cloud-shadow-steps-report.md`；复核 `python build/targetmap-shading-a5/verify-cloud-shadow-steps.py`。GPU/replay均已退出。完整目标ACTIVE。

## 当前验收范围：Shading（用户最新确认，2026-09-15）

- E2793（SSGI、直接光、Sky diffuse、DFAO、SSR、环境反射之后）为最终验收点；E2962 不再是完成门槛。
- 材质/GBuffer/depth 保留逐位一致验收。继续检查 E2793 的物体着色、阴影、间接光和反射。
- E2793 之后的 Camera AP、画面雾、主视图体积云合成不再单独追求一致；保留现有实现。
- 环境 Cube 中的天空/云/雾、自产历史与曝光仍可能影响 E2793，按真实依赖排查，不将它们从着色输入中随意删除。
- 较早全链 source-dfao-fastmath / 0e425255：E2793 RGB MAE .006641043，E2962 .00639366（历史参考）。数值尚未完成。
- 已解决 SSDTemporal 边缘重复写：stable f1200d0c / a2bfef5b 的119raw独立进程逐byte一致。DFAO原生快速倒数修正将global MAE .012121->.000343685；仍有采样局部残差。
- source-shading-audit / 56163018 验证通过：119旧raw完全不变，BRDF积分表逐位一致；SH/Cube方向分布仍有差异。下一步修正影响 E2793 的天空环境光/反射，再处理其余局部残差；保留独立验收和正式入口迁移门槛。

- 前一阶段阴影检查点 source-direct-shadow-source-space / fc16c331：四级8192×2048 D16阴影atlas与最终RGBA8屏幕阴影遮罩均逐位一致（0差异）；原生HDR additive blend仍0差异，GBuffer/depth/stencil保持一致，6History验证通过。独立重启 b201b426 通过：121raw逐byte相同、360身份fresh校验、6History通过；新shadow-source-space检查点冻结。A2 source-shadow-normal-order / a2315958直接光离线比较仍有97个RGB分量（其中完全受光96个）不同；严格直接光与完整E2793尚未完成。当前E2793 MAE .006642181。旧冻结基线2fc8dea6/0dcf6ee3保留，不覆盖。

## 当前检查点：云相位函数（2026-09-16）

- [x] 修正 CloudTrace.slang 相位函数的方向约定和 pow 运算替代错误，直接采用原引擎公式。
- [x] GPU 源公式对照 520 点严格零差异（旧451点失败）；2fb60af4 / 83dcda2b 独立重启145raw一致；阴影/混合/AP、GBuffer/depth/stencil、6History回归通过。
- [x] 原生3D真实云试验已完成：数组模式与全链145raw一致，3D模式未解决主要环境误差。保留诊断，未正式接入，也未改C++。
- [ ] 完整 E2793 尚未对齐：view MAE .0047703650，opaque .0035787070，较上次下降约28%/26%；最大误差 .2001953125 和部分 Cube 方向仍未改善。
- [ ] 继续环境Cube/SH、算法/采样、间接光/AO/曝光/历史及正式入口。异步询问是否允许捕获时间/帧号作为运行参数，当前未获回复，保持捕获只用于离线比较。
- 报告：build/targetmap-shading-a5/cloud-source-phase-report.md；新922文件检查点，不覆盖旧检查点。完整目标 ACTIVE。

## 环境云当前检查点（2026-09-16）

- [x] CaptureCloud 内部保持未曝光 float32 辐射/透射率/weighted depth，AP/雾之后才应用输出规则；六面生成 GPU 合同 RED→GREEN。
- [x] source-capture-cloud-internal / 1fc1933b、83dfc38d 独立重启 145raw 一致，阴影、原生混合、CaptureAP alpha、GBuffer/depth/stencil 和 6History 回归通过；928 文件检查点保存。
- [ ] E2793 仍未对齐：view RGB MAE .0066389739，opaque .0048055360，max .1982421875。RawCube 顶面 MAE .0092480394，没有改善。
- [x] 原生 Texture3D 对照证明云噪声的 2D 数组手动插值不等价；源体素 Load 一致，262144 采样点 MAE .0001503152。1/256 Z 权重量化仍不等价，未接入 renderer。
- [ ] 下一步：实际云阶段原生3D采样对照/集成，再检查天空混合、动画/缓存时间、其余间接光和曝光/历史；正式入口迁移仍待完成。
- 报告：build/targetmap-shading-a5/capture-cloud-internal-report.md。完整目标 ACTIVE；不能将子阶段零差异扩大为完整 lighting 一致。

## 环境大气当前检查点（2026-09-16）

- [x] 只读阶段审计：基础大气透射与多次散射LUT逐位一致，主要Cube差异在过滤之前。
- [x] source-ap-start-depth：修复Capture AP的UV、曝光存储/采样约定、地平线中点运算次序、起始距离f32单位转换。
- [x] fed89af7 / bf7445ba独立重启145raw一致；全部16384 AP体素alpha逐位一致；8严格数值检查和6History通过。检查点922文件fresh验证通过，旧直接光检查点保留。
- [ ] 完整E2793仍未对齐：RGB MAE .0066487561，opaque .0048142127（与此前相比略升，不能宣称整图改善）。
- [ ] 下一步：云在AP/fog之前的float32辐射、transmittance、weighted depth边界；动画时间/缓存状态；其余间接光残差；正式入口迁移。
- 报告：build/targetmap-shading-a5/capture-ap-source-report.md。当前GPU/replay无运行中任务。

## 直接光与阴影当前检查点（2026-09-16）

- 当前环境阶段：新增离线 compare-environment-stages.py。RawCube 在过滤前已有主要方向误差，只加读回候选1f1e891c已通过，原121raw不变；大气透射和多次散射LUT逐位一致。下一步检查sky-only/AP/云/雾合成与动画时间状态。原帧缓存跨帧差异较小，尚非已证实根因。

- [x] 阴影：全8192×2048 D16 atlas与RGBA8屏幕mask逐位一致。
- [x] 直接光：source-direct-sphere-rotation / fdda3140、b5e026d2，离线统一曝光+原生half blend模型下整张1424×1040 allocation RGB零差异；25raw独立重启一致。不能将该验收扩大为内部float32或完整曝光链路逐位一致。
- [x] 完整候选 source-direct-shadow-zero / e05d294f、e83cdba7：121raw重启一致，361身份fresh核对，6History与nativeblend通过；GBuffer/depth/stencil不变。
- [ ] 完整E2793：MAE .00664217956，opaque .00480652601；环境Cube/SH、间接光/AO、自产曝光残差仍未关闭。
- [ ] 正式入口迁移尚未执行。当前仅build候选；新direct-shadow-zero检查点/可复现验证器保存，旧检查点不变。

## 当前光照推进（2026-09-15）

- [x] A1 full GBuffer/depth/stencil bitwise validation, frozen2323files.
- [x] A2 source CSM/direct and A3 atmosphere/sky/environment execute with preserved upstream outputs.
- [x] A4 source camera AP and height fog execute; source cloud material/platform/blue noise exported.
- [x] Source cloud trace/minmax/secondary, nativeHistory reconstruction, AP/fog/composition, capture360AP+6cloudfaces beforefilter/SH execute.
- [x] Source histogram exposure uses nativeHistory and cloudhistory exposure correction (f88ea2e6).
- [x] A2 direct offline exposure/blend comparison and shadows: zero differences, independent reset verified.
- [ ] A3 environment/indirect/AO/exposure numerical closure. A4 display composition parity is out of current scope.
- [x] SSGI/DFAO/SSR with owned color/depth/denoiser history execute; numeric closure remains separate.
- [ ] E2793 Shading HDR acceptance and independent reset, formal source-only entry promotion. E2962 is historical evidence only.

最新成功10帧 ssgi-a5-native-dc788b00；候选source-lighting-warmup。2帧alpha修复c95aa656；E2962 RGB MAE .0064289435，仍未对齐。主要光照链路全部接通：SSGI、SSR、DFAO、直接光、天空/云/雾、自产history/exposure。仅代表运行通过，E2793/E2962数值对齐、history收敛、reset/正式入口仍未完成。DFNormal全图bitexact；DFAO锥追踪有残差，正在离线检查源atlas采样边界。

## 当前检查点：原材质与 GBuffer 对齐（2026-09-15）

- 已按用户要求读取原工程材质：Floor 为 MI_ProcGrid → M_ProcGrid → MF_ProcGrid，Sphere/Cube/Cube2 为 BasicShapeMaterial。13个原始资产身份和10份UE材质图导出已核对；实例参数无误。
- 地面残差根因定位到位置重建的浮点运算边界。独立候选将除法写为 precise rcp → precise multiply → precise camera subtraction；单独添加 precise 到原除法/减法的两个实验无效，已保留证据。
- 去掉 FloorProbe 的干净候选 floor-material-source，新进程 d96e34e8 / a8e6ce2e 所有 raw 逐 byte 重复。**整张1424×1040 allocation 的 GBuffer A/B/C/D、depth、stencil 与 E1452 逐位一致，包括padding**。覆盖1,258,627像素。Floor rough93、metal376、颜色49像素残差全部归零。
- 仅B/C相对旧939f4ccb变化；SceneColor仍有241,893分量差异。现有origin/vertex审计保留，无新增材质探针Pass/MRT。C++和二进制未改、无旧ABI或捕获输入；候选仍未迁入正式入口。
- 验证：四项GPU原始输出回归RED→GREEN，118原targetmap CPU与27候选CPU通过；实际Logger523/524无validation errors；旧1724文件检查点fresh PASS。
- **未完成**：A1背景/editor sky、源输入合同/正式入口迁移；A2主光/CSM；A3间接光/AO/SSR/history至E2793；A4 sky/fog/cloud至E2962；A5独立HDR验收。总对齐目标继续，不能把GBuffer对齐说成shading完成。
- 详细证据：build/targetmap-shading-a1/floor-material-diagnostic-report.md；新的floor-material-verification.json冻结2,323文件，fresh复核通过。以下较早的93/376/147残差说明为历史记录。


## 当前检查点：源 local position 精度（2026-09-15）

- 总目标 ACTIVE：E2793 中间、E2962 后处理前 HDR 最终验收。当前是 A1 几何/GBuffer 阶段进展，不是完成；旧 UI 目标独立。
- 工作目录 E:/Project/falcor/Falcor-m0，分支 codex/ue-legacy-m0。保持原生 Scene 米单位，独立源厘米顶点表只供自定义 VS 投影；没有捕获输入、旧 ABI、正式入口/C++/二进制改动或 commit/merge/reset。
- Mode0 f2805d78 与旧 c8c37a9a 的7raw逐字节一致；source-cm 939f4ccb/reset d8f25635 的7raw相同；当前自捕获 e5a45f33 同样7raw一致。模式切换仅3个 SOURCE_LOCAL_CM define，只有 depth/B/C 改变。
- **全分配区 depth/stencil/GBuffer A/D 与 reference 逐位一致**；覆盖1,258,627像素。Basic代理203,219像素A/B/C/D/depth全部一致。Floor B仍93/0/376/0分量不同、C147分量不同；SceneColor241,893分量差异保持原状。材质/背景未完成。
- 实际D3D12 SV_VertexID为draw-local；错误减vbOffset导致depth0，已通过独立ID捕获定位并修复。当前GPU逐顶点审计验证4个opaque draws、757vertices完整索引/owner/cm/meter bits。Floor90x4clip与source Prepass exact；Sphere仍18个X分量差异，不扩大为所有属性精确。
- 新 local-positions-verification.json 冻结1,724文件并重算源表、GPU映射、fullraw/ULP/delta/reset；此前934等检查点不改。27候选CPU、2GPU证据负例测试、118原targetmap测试通过。所有成功native退出0、实际Logger无validation errors。
- 下一步：Floor实际PS z/q/导数/采样边界；背景/editor sky；源输入合同/正式迁移；A2自产CSM/direct，A3自产GI/AO/SSR/history/PreExposure到E2793，A4 sky/fog/cloud到E2962，A5独立reset HDR验收。
- 详细证据：build/targetmap-shading-a1/local-positions-diagnostic-report.md；local-position-gpu-audit.json。PS只读诊断单独存储，不改已冻结候选。


## Latest continuation — source-origin precision (2026-09-15)

- Full A1/E2793/E2962 remains ACTIVE. Source-only scratch mechanism; no formal promotion/source/binary changes or old ABI restoration.
- Source cm table keyed by actual addNode NodeID and GPU globalMatrixID verified across all5instances, including Sky. Mapping0->0 Sky,1->1 Floor,2->3 Sphere,3->2 Cube,4->4 Cube2. Strict flags/epoch/static-root scope; no captured renderer inputs or mesh-specific fitted offsets.
- Audit-only c51995d1 repeats prior b7f36f3a all7raw exactly. Source-cm7572ed23/resetc8c37a9a each exit0/actualLogger no validation errors; all7raw resetexact. Mode0->1 only3sourceorigin defines; onlyA/depthrawchange.
- Basic material proxy A/B/C/D nowexact, oldlargeface-normaljump gone; depth>1e-7 4375->0, max3.725290298462e-9. Still339depthpixels differ1..2ULP. Floor272396depthpixels differ1..2ULP, Brough124/metal463/C177component residuals (11Bpixels>1code); notwholeimageparity.
- Coverage1258627/stencil exact. Source matrixprecision fixesdonotclose background/editor sky/materialresidual/formalsourcecontract/promotion/A2-A5. E2793intermediate/E2962final remainopen.
- Failed4ad5f695 integerRTVclear andbf5da295 auditshape1-height assumption preserved withdiagnostic-inputs; correctedusingnativefloatnumericIDsand5x4to_numpyshape, noC++workaround.22diagnosticCPU/118targetmapCPU pass. Earliertranslation756recheckedunchanged.
- Evidence: build/targetmap-shading-a1/source-origins-diagnostic-report.md; newsource-originscheckpoint recomputesGPUmapping/table/raw/ULP/delta/reset. Next exactdepth/materialchain andbackground, not prematurelightingacceptance.


## Latest continuation — translation precision boundary (2026-09-15)

- Full A1/E2793/E2962 remains ACTIVE. All changes still isolated; no formal source/binary promotion. Earlier vertex688 checker is frozen; new translation756 checks full source/raw/log identity and reset.
- Actual nativecapture fea15ab9/replay512c88d3 proves source XYZ projection retained. CPU source+Graph model reproduces559x4clip bits exactly only with fused meter*100+CameraHigh origin (separate model658 components differ); root reran the frozen agent snippet successfully. Driver/compiler contraction location not asserted from DXIL alone.
- Candidate vertex-translation-boundary,82c58f7a/b7f36f3a adds only local precise originCm/relativeOrigin. Both processesexit0/Logger clean,7raw reset exact; twoSphere depthhotspots(714,396)/(651,463) nowbitwise reference. Basicdepthmax2.346932888e-7 vs1.849606633e-6,normal2components.
- DO NOT PROMOTE: those2components are ONE LARGE normal jump at(1064,689), ref[511,0,511,1] vs[511,511,1023,1], already present in c33dacbf. Basicdepth>1e-7counts35a=44,c33=4419,82=4375; localprecise fixesSphere relativec33, but full candidate retains earlier broader regression. Floor unchanged124/463/177,maxdepth3.72529e-9.
- Next source precision: Cube/Cube2 T.y=-240cm cannot be recovered from nativef32 -2.4m*100=-240.0000152588. Preserve source-authored float32 cmorigins independently with verified Sceneinstance mapping, not per-mesh fitted nudges/capture inputs. ActualsourceE770 depthwriter/othermeshes remain to audit. SphereOBJ exactposition6708B export onlyifnextconfirmedgapneedsit.
- Current scene.instances[0] is Sky, not Floor. Frozen cm diagnostic's mislabeledFloor CPU fixture actually selectedSky; new external named-ID test coversFloor/Cube/Sphere/Cube2,15diagnosticCPU PASS. Runtimealwaysloadedallsource instances. Preserve old688, don't rewrite history.
- Reports: translation-diagnostic-report.md / mesh-native-runtime-evidence.md / translation-verification.json. Original118targetmapCPU andprior199/381/688checkerspass; current756freshrecheckpasses. No builds/newframeworkcode,oldUEABI,commit,merge,reset. Next A1 precision+background,thenA2-A5; not fullshadingdone.

## Latest continuation — 2026-09-15 vertex-normal/runtime diagnostics

- Full A1/E2793/E2962 goal remains ACTIVE, not complete. No formal renderer/Falcor source or binary changes in this increment; all candidates stay in build/targetmap-shading-a1.
- Raw f16 normal without VS normalization reduces Basic A3074->1443; source SNORM8 lattice restoration reduces1443->13 (13pixels, each1code). Each step changes only A.raw; six others identical. SNORM reset35a23c4e/a384d355 repeats7raw.
- Source-cm attributes do not resolve depthmax and regress Floor materials; explicit source-axis projection order improves Floor124/463/177/depthmax3.72529e-9 but Basic normal15/depthmax1.8496066e-6 remain. Projection resetc33dacbf/ddaa8f81 repeats7raw. Neither promoted.
- New actual E1437 oracle proves source/capture IB2880 and normal codes1677 exactly; postVS typed normal conversion is exactfloatdivision, not reciprocal multiplication. SourceOBJcmf32 loses265positioncomponents, max9.5367e-7cm; not automatically rootcause.
- Native finite capturefea15ab9 14.8MB has7raw equal uninstrumentedc33dacbf; actual native prepass/baseVS1177/1416 DXIL retains requested source-axis accumulation. Investigate actualnative intermediates plus sourceE770 depthwriter, not guessed compiler reorder/precise. AllGPU/replay processes bounded and exited.
- Separate vertex-verification.json + verify-vertex-checkpoint.py rehash identities/recompute raw and geometry proofs. Original platform199/coordinate381 remain frozen. First3variant CPU review vertex-normal-review.md; newestoracle analysis separate. Formal118targetmapCPU again PASS. Next actualprepass/vertex precision, sourcecontract/promotion gates, Editorbackground, A2-A5.

## Latest continuation — 2026-09-15 coordinate/source-camera diagnostics

- Full E2793/E2962 shading goal ACTIVE; A1 not complete. Formal sources/binaries unchanged by this increment; isolated candidates live in build/targetmap-shading-a1/coordinate-*.
- Source exact camera export source-camera-module-hyw85bej passes isolated3-action build and NullRHI commandlet,8views/48doubles384B JSON/raw exact, original map/engine unchanged. Failed Python reflection and wrong4-view expectation retained separately.
- Actual PS screen reconstruction, exact asset camera and float UE_PI editor rotation now reproduce16/16 matrix bits independently; no captured matrices/texture/depth/HDR supplied to renderer.
- PS-only candidate Floor rough/metal/C237/748/294 vs baseline1069/2993/1350, all5otherraw unchanged. Source-relative VS candidate162/566/228 repeats7raw in separate processes374420d5/2b125054, but Basic normals3074 vs3069 and depth1.8496066e-6 vs1.7620623e-6 slightly worse. Not promoted and not full parity.
- Keep separate checkpoints: original platform-verification199 files; coordinate-verification recomputes raw partitions/residuals and full source identities. Next source mesh/vertex/raster precision, formal PS-only promotion tests; editor background and A2-A5 still open.

## Latest continuation — source platform texture / sampler (2026-09-14)

- Full shading goal ACTIVE: E2793 intermediate/E2962 final, no post-processing. A1 still incomplete.
- Generic max_anisotropy1..16/default1 implemented in shared MeshDraw/ShaderPass sampler parsing. Build sampler-build-_fb6k9yy and4 real nativeCPU sampler-cpu-sekddk7z pass. D3D12 sampler-gpu-aeto40k2 passes12 native-oracle comparisons/36 rejections, zero GFX errors. Default targetmap native-d94f6760 seven raw outputs byte-identical to prior baseline; sampler-baseline-regression.json.
- Actual changed render binary is plugins/customrenderpipline.dll SHA0a1ea540cc074ead4846949d1413258dc4b8b7ee7afc4d65f33aa11cda9bd8e2; Falcor.dll remains755b362f... . Earlier no-C++ baseline wording below is historical. No old UE ABI restored.
- Source exports _l124_46 andlwut1xhz nowcleanexit0/drainremaining0,BC1sRGB512²10mips174776Bbyte-identical;allsourceblocks exactlymatchactualread-onlytexture-19bca6a6captureoracle. Originalsource/engineprotectedidentities unchanged. EarlierNullRHI/NoShaderCompile/GCcrash retained asfailures;noacceptedmanifestforthose. Sourcehelperpost-maincompilationdrain fixesreproductionwithoutoriginalenginechange.
- Source launcher3 independent P2s fixed under CPU RED/GREEN: stale export preflight, same-read parse/hash plus byte rechecks, protection verification before success publication. FinalPython118targetmap/16platform/59native pass. SourceDDSaniso1native-5ab7cda6,thenaniso8native-4cc2c229,independentexport/processnative-3c99e4f0repeat7rawsame. FloorresidualBrough1069/metal2993,C1350;maxB3/11,C2. Coverage/stencilunchanged. Basicnormal/depthandbackgroundremain.
- Current checkpoint platform-verification.json,verify-platform-checkpoint.py revalidates199filesplusmatrices/sourceoracle. Fullrendererparityfalse,A1false. Root remains exclusive owner of all build/GPU/replay;allcurrentownedprocessesexited. Next finish residualfloor math/interpolation, A1 normal/depth/editor fields, thenA2-A5lighting/history/finalHDR.

## Prior baseline — 2026-09-14 targetmap shading, A1 native baseline checkpoint

User confirmed E:/rdc/ue/2.rdc E2962 final and E2793 intermediate, excluding post-processing. This is separate from the older BLOCKED V5 UI goal; that goal has not been resumed or completed.
- Current shading goal ACTIVE, not complete. A1 new source-only Mesh+Schema graph renders in existing Falcor (no C++ changes/rebuild). Latest reset runs native-f309d4b0/native-e06eff41 produce all seven raw outputs byte-identically; 96 scoped CPU tests pass. Reference E1452 is reference-ffeea6e8; actual capture unchanged. Evidence build/targetmap-shading-a1.
- Fixed source projection versus rounded raster aspect using independently identified unscaled frame2465x1795, plus source float FOV/aspect rounding. Coverage1258627 pixels and stencil now exact. Native phases0→1 are generated by own two-frame sequence, not captured constants. Basic-material proxy203219 pixels: GBufferB/C exact; floor proxy1055408 pixels: GBufferA/specular/model/alpha exact. These proxies are not object/face IDs.
- A1 remains incomplete: Basic normals3069 differing components (one same-material shared-face boundary >2codes), depth max1.7620623e-6; floor depth max7.4505806e-9 and source texture vs platform BC1/mips/aniso mismatch; background SceneColor alpha/editor-sky pass not reproduced. Full E2793/E2962 lighting/history/sky validation is still pending. No captured GBuffer/depth/history/HDR fed into native graph. Current plans/docs below supersede A0-only next-step wording.
- A0 raw HDR baseline and input-identity audit complete. Two fresh hidden read-only replays reference-a-0e5c7221 / reference-b-acc007f9: same capture hashes, explicit shutdown,58 artifacts/25,004,923 exported bytes each; RGBA16F visible/padding bits identical at both events.43 scoped CPU tests pass, independent spec/quality reviews closed.
- Saved camera position/rotation/FOV match capture at export/float precision. A1 additionally checks source-derived projection and native GBuffer as summarized above (not complete equality). PreExposure1.3405122756958008 and temporal SRV bindings remain offline A0 evidence. No captured history/GBuffer/depth/shadow used as production inputs.
- A0 changed only four Python diagnostic/contract files, approved spec/plan and docs. A1 now adds source-native Python/Schema/Slang and offline comparison; still no C++ change/rebuild or commit/merge/reset. All owned GPU/replay processes exited.
- Current report docs/research/customrenderpipline-targetmap-shading-zh.md; evidence build/targetmap-shading-a1 (A0 retained separately). Next finish A1 texture/geometry/GBuffer precision, then A2 CSM/direct, A3 indirect/history E2793, A4 sky/fog/cloud E2962, A5 clean baseline verification.


## Latest authoritative state — 2026-09-14 08:49 wait/strict-regression/completion audit

- Full user goal is BLOCKED (not complete), waiting for an unlocked desktop after the same UI condition persisted across at least3 consecutive goal turns: old-source cleanup, V5, async readback and broader validation are all retained. No commit/merge/reset or old UE ABI/transaction restoration. This goal turn made real wait-measurement, restored-build, verification and completion-audit progress.
- Implementation tree E:/Project/falcor/Falcor-m0, branch codex/ue-legacy-m0. All root-owned builds/GPU/UI have exited; three verified idle MSBuild workers were stopped. No stale window/session may be reused.
- Current strict R4 async-stage3-20260914-083244:55 native/11 GPU suites/372 CPU PASS. Q1/R5 q1-r5-final-v5wxs5u3:13 native/5 GPU suites/372 CPU PASS. Rechecked66+49 current source/binary files and31+8 actual Logger copies. CPU suites overlap; non-error warnings retained.
- Build native-wait-probe-lm33yqli/build-restored.log is current. Temporary Fence/Device/CopyContext/Profiler source probes are restored byte-exactly; all four objects rebuilt. Actual formal DLL has none of the3 diagnostic exports, diagnostic DLL has them. Formal Falcor.dll SHA256755b362f3efcf824a7e5890791b2499da7b0134031e5fd88e0a3929b8421d024; old matrices with pre-rebuild hashes are historical.
- Native wait measurement covers7380 instrumented frames: frame-fence always early-completed, heap once/frame. Default sync30queries ->30backend waits totaling6.5682ms; async/panel submit_true/texture_blocking/other calls0. Native profiler can still wait even when event profiling disabled. These are specified API intervals, not pure OS suspension/all driver stalls; heap includes reset.
- Preserved native-wait-probe-lm33yqli source/diff/header/runner-as-executed/diagnostic DLL/raw results/Logger. Reusable runner partial-write restore P2 fixed; exact restore prefix tested for all-applied, middle-write-failed and concurrent-edit protection. This fix did not change the measured native patch.
- Prior default application-perf-2932i3td remains the uninstrumented headless timing/memory evidence. Do not replace it with diagnostic wall times. Small workload does not prove async faster than sync or desktop FPS.
- Cleanup re-audit:88 source paths and24 stale published shaders absent; four archives match every listed byte hash;18 retained algorithm hashes unchanged. current-cleanup-audit-after-wait.json.
- Latest real UI live-fzedmw7h pid100960/window2172876: official sky capture sees Windows lock screen,0inputs; stop-file V5_LIVE_CLOSED and process exit confirmed. User asked to unlock. Prior blocked UI state also persisted through two immediately preceding goal turns; current remaining gate is external UI access.
- Completion audit: docs/research/customrenderpipline-completion-audit-20260914-zh.md. Non-UI gates closed within documented scopes; actual V5 mouse/Unicode picker/compare/export/cancel/error/close-reopen, same-instance ErrorMeasure UI/CSV, visible response and final UI sign-off remain UNVERIFIED. No additional all-format/backend/OS-scheduling scope is inferred.
- Current exact checkpoint native-wait-final-checkpoint-verification.json, recheck with verify-native-wait-checkpoint.py. First temporary aggregation failed only due invalid encoding alias utf8-sig; corrected utf-8-sig, full verification passed without changing test results.
- Independent reviewer cleared native patch/measurement; final audit's two stale entrypoints (this block and Todo R4 line) are synchronized. Final goal completion is forbidden until genuine UI gate passes. Lock-only blocker audit must follow actual consecutive-goal-turn evidence, not endless repeated status or artificial new work.

## Historical checkpoints (superseded by the current block above)

### Prior 08:20 migration/performance checkpoint

- Full user goal remains ACTIVE: C2 old-source cleanup, V5, async readback and broader validation. No commit/merge/reset or old UE ABI/transaction restoration. This continuation made new performance/verification/documentation progress; no production changes, no repeated locked-UI attempt.
- Implementation tree E:/Project/falcor/Falcor-m0, branch codex/ue-legacy-m0. Default cwd is a different checkout. Root serially owns every build/GPU/UI process; all current sessions have completed, no Mogwai/FalcorTest/MSBuild left running. Do not reuse old handles.
- Current strict R4 async-stage3-20260914-075416:55 native/11 GPU suites/372 CPU PASS. Q1/R5 q1-r5-final-zw25eqty:13 native/5 GPU suites/372 CPU PASS. Current binary/source scopes and all39 native Logger copies rehashed unchanged. Do not sum the duplicate CPU suite or claim warning-free.
- Two new depth cases pass: real pending-drop with pre/post prerequisite markers and exact recovery; separate Device completed-task last-owner refCount()==2 and both planes remapped after releasing other owners. Depth production header unchanged. Final Device teardown may drain.
- New D3D12InfoQueue coverage found native GpuTimer::resolve state error, independently RED without shaders/depth/tasks. One CopyDest barrier before raw query resolve fixes first/reuse on D3D12/Vulkan; no added wait/submit. CopyContext has comment clarification only in this increment.
- V5 fixture adds deferred native Reopen Inspector on the same service; graph callback unchanged,3 actual idle frames do not dispatch/readback. Review P2 JSON/PNG generation timing fixed by tick-before-render and reopen_visible key. Production panel/service unchanged. Not actual mouse acceptance.
- CPU concurrency initially failed in strict R4 074652. Full envelopes isolated reply-read errno13 (not queue overflow/timeout); real Win32 sharing lock reproduces it. Client now retries reply PermissionError under original deadline only; metadata/admission/pump unchanged.37 transport tests/20 four-process rounds PASS. Permanent reply permission denial becomes timeout; original locking actor not identified.
- Backups, RED/GREEN and scoped independent reviews: build/native-framework-completion/depth-v5-transport-checkpoint-verification.json and depth-timer-v5-review.md. Old failures retained. Build build-timer-state-green.log is current.
- Latest official sky live-e975ai8n (pid95456/window11082268) again displayed lock background; zero inputs, stop-file shutdown/V5_LIVE_CLOSED verified. Process exited. User unlock is still needed for real UI, not justification to stop remaining headless work.
- Fresh original-three replay migration-status-wpuoqxon passes Asset/History/retirement +372 Python, real Logger scans and before/after source/binary hashes. Runner now includes strict native Logger collection. It does not claim all R4/V5 acceptance.
- Real application measurement application-perf-2932i3td:7 modes x3x300 default headless frames, two profiler-paused controls, four separate119-sample native GPU captures. No timed sleeps/screenshots; idle observer counts zero, every demand pixel oracle exact and pool drained. Pure graph p50 .135ms, service-only .372ms, visible idle panel .399ms; process WS905.07-909.13MiB/private1964.28-1972.73MiB. Small workload async API p50 2.050ms vs sync1.883ms: not a speedup claim. Actual Logger and source/binary/generated hashes retained.
- Independent performance review closed P2 panel-latency oracle contamination by moving timestamp before verification; added true service-only listener removal, retained hidden-panel mode and documented wrapper boundaries. Old application-perf-riholqur retained but not used for panel-latency conclusion. No remaining P1/P2 in scoped review.
- Next: actual native wait-blocking duration attribution and visible interaction acceptance; static waits and wall-minus-GPU are not direct wait measurements. Profiler::endFrame wait even with enabled=False and Device frame/heap synchronization match HEAD. Native capture root timestamps may include submission gaps; headless throughput is not desktop FPS.
- Real V5 picker/compare/export/cancel/error/close-rebuild, same-instance ErrorMeasure options/CSV, full-objective audit/docs still remain. Optional direct SPIR-V remains unsupported; final RDC and deferred rollback stay separate.



### Prior 06:05 compiler checkpoint

- New real Falcor shader RED/GREEN: NativeWorkgroupLayout default emitted invalid Workgroup ArrayStride (runtime blob spirv-val=1), explicit EmitSpirvViaGLSL in ProgramManager now gives val=0 and zero native GFX errors. Environment/per-program direct opt-in preserved; explicit environment direct remains RED, not certified. Offline evidence: `spirv-path-8g021zox`; runtime: `vk-repair-workgroup-red-m0nyvcq4`, `vk-repair-workgroup-green-1u8g19u1`, `vk-repair-workgroup-optin-red-an5bahq1`.
- Typed reduction buffers now match float/int/uint and independently resize both ping-pong buffers. Expanded fixture includes buf1-only growth (16400 -> 16416 B). Strict dual-backend 2 cases / 18 reductions each passed: `vk-repair-typed-expanded-vulkan-868f41ti`, `vk-repair-typed-expanded-d3d12-xp5l3cje`. Original reduction and D3D12 ErrorMeasure also passed focused replay. These runs still report non-error compiler/maintenance5 warnings; do not call them warning-free.
- Fresh post-emitter Q1/R5 bounded replay passed 13 native / 5 GPU / 367 CPU: `q1-r5-final-oh6477x5`. New subsequent lifecycle fixtures are not covered by that snapshot.
- ErrorMeasure Vulkan still RED, now only queue-chain VUIDs 03238/00067 in `vk-repair-error-measure-vulkan-y1lvw4zb`; shader layout/type errors disappeared. Proposed host VkEvent gate was itself disproven by pilot 01158/09543 and DebugPrintf error (`vk-repair-gate-pilot-i253_60r`). Do not run drop tests using it. Agent preparing bounded real GPU workload + independent pre-task pending marker; no validation disabling, host event or fake pending assertion.
- Ordinary 256 KiB ungated requests completed before poll (pending 0/4), so that diagnostic did not reproduce pending. Preserve its failed record `vk-repair-ungated-drop-red-x_24_o2i` and exact fixture archive `ungated-drop-diagnostic-retired`; remove diagnostic from active tests, not weaken assertions into PASS.
- Fresh official sky capture of new live window 1254364 still showed Windows lock screen. `live-x5xh0wg2/acceptance-status.json` incomplete; zero input, stop-file shutdown confirmed V5_LIVE_CLOSED. User asked asynchronously to unlock; continue headless work. No overall blocked/complete claim.

### Prior authoritative snapshot (05:35)

- Original requested migration is complete and now strict-Logger rechecked: `build/native-framework-completion/migration-strict-hv1ypoy6/verification.json` (Asset, History, retirement). Keep GBuffer/Schema/observer; no legacy ABI restored.
- Q1/R5/S4 finite matrix complete: `q1-r5-final-nafuwssh/verification.json`, 13 native / 5 GPU / 367 CPU; current source and binary hashes rechecked. Overall goal remains ACTIVE, not complete or blocked.
- IMPORTANT: old stage3 stdout/XML green omitted file-only FalcorTest GFX diagnostics. The new common `validation_log_guard.py` copies/scans actual native logger files and rejects them. Strict stage3 `async-stage3-20260914-053232/verification.json` is RED at ErrorMeasure Vulkan. Do not repeat old Vulkan validation-clean claims.
- Next root work: fix separate R4 typed reduction buffers, SPIR-V Workgroup layout, pending-task fence retirement, and Vulkan GFX timeline-gate/binary-chain fixture issue; then full strict matrix. See `vulkan-reduction-validation-findings.md` and `vulkan-fence-validation-findings.md` under build/native-framework-completion.
- Fence lifetime fix must be nonblocking and respect member destruction order: tasks have weak Device in fence, staging buffer owns Device, buffer currently dies before fence. Cover Texture/Buffer/exact-depth tasks; do not blindly change global Fence destructor or weaken pending tests.
- V5 live-0c9ds7bo still showed lock screen via official sky. No mouse/key input; owned process stopped. Real picker/compare/export/close-reopen, same-instance ErrorMeasure UI and final application performance remain.
- No build/GPU/UI processes left running; no commit/merge/reset. root owns all such executions serially. This turn made material test/validation progress and found actionable defects, not a repeated blocked turn.

## Active goal — C2 cleanup, V5 completion, asynchronous readback and broader validation (2026-09-14)

User explicitly requested all four remaining workstreams; keep the full goal active until each is implemented and verified. No commits/merges; preserve actual material/Schema/Pass/observer capabilities and algorithm/reference provenance. Original checkout remains untouched. Prior headless-only constraint applied to resource migration; V5 now explicitly includes real UI acceptance via official Computer Use, stopping if user interrupts.
- [x] Revalidate workspace/current TODO and archive exact baseline before edits (build/native-framework-completion).
- [x] C2: archive/remove uncompiled old glue/ABI source and obsolete tests; remove no-consumer compatibility and graph sealing hooks without losing native graph APIs. 88 source paths archived, 18 algorithm counterparts unchanged; 24 stale copied shader assets also archived/removed. Final bounded source review has no Critical/Important findings; Release build, 325 CPU tests, native GPU/core regression PASS (build/native-framework-completion/c2-stage-verification.json).
- [ ] V5: Unicode file picker, visible dialog errors, lifecycle; actual mouse/selection/file/export/close-reopen acceptance, docs and review.
- [ ] R4: native-first nonblocking staged texture/buffer/depth-stencil readback; bounded tickets; connect Schema, observer, UI and CLI; preserve explicit synchronous compatibility APIs.
  - Native Buffer/Texture D3D12/Vulkan and D32S8 D3D12 plane tasks are verified; fixed Cube stencil plane stride and GenericRead state mapping. Schema/raw/service/CLI/UI default async, explicit sync compatibility retained. Shared owner pool 8 tasks/64 MiB retains pending cancellation charges. GPU scratch snapshots, 512-task lifecycle, UINT/UNORM external CLI and panel callback tested. ContractGuard rechecks hashes without redundant semantic/codegen work, including alias checks.
  - ErrorMeasure native async statistics implemented and GPU-verified, including continuous Scene/refresh starvation fix, frozen CSV identity and deterministic 4-task queue-full Difference recovery. Also reproduced/fixed native ParallelReduction wave-index collision on D3D12; native original tests pass both backends. Full 64-MiB staging batches now tested on both backends; not a process memory/FPS guarantee. Final integrated stage and review are being recorded; actual UI acceptance and broader combinations remain open.
- [ ] Q1/R5/S4: enumerate and validate remaining documented combinations and backend/format boundaries; fix reachable defects, distinguish unsupported from unverified.
- [ ] Final build/regression/performance evidence, reviews, fresh complete hashes/archives and Todo audit. Do not count partial checks or still-pending mouse validation as completion.

Evidence: build/native-framework-completion. Four independent specifications/plans will record exact contracts. Existing rollback and RDC goals remain deferred/separate rather than silently added.

Latest status-request recheck: build/native-framework-completion/migration-status-zij2hgvy/verification.json. Current 346 Python tests and 3 serial Asset/History/retirement debug-layer GPU suites PASS with fresh reports. This is not an expanded-goal completion or new build/UI acceptance. Status documents backed up alongside that index.


## Completed implementation — Asset/History migration and old UE caller retirement (2026-09-14)

User explicitly authorized retiring old UE callers and migrating Asset/History, retaining useful algorithms/reference data. Spec: docs/superpowers/specs/2026-09-14-resources-history-retirement-design.md. Plan: docs/superpowers/plans/2026-09-14-resources-history-retirement.md. Evidence/backup: build/resource-history-migration.
- [x] Back up sources and classify old callers vs useful algorithms/native tests.
- [x] Native Asset ordinary resource Properties and known-byte GPU coverage.
- [x] Native History scoped GPU storage, ordinary execution, explicit reset and no old transaction ABI.
- [x] Archive/remove retired callers and old-only tests; reconcile native dependencies and test accounting.
- [x] Build, serial GPU/CPU regressions, independent reviews, examples/docs/Todo and verification.
- [x] User follow-up: re-audit every modification family and publish a fresh keep/retire/TODO ledger, including native core fixes and unfinished V5/readback work.

This authorization supersedes earlier instructions to keep legacy callers working. Preserve native GBuffer/Schema/observer/core functionality, useful algorithms and reference data. No commit/merge, desktop interaction, unrelated V5/rollback or UE effect translation.

Final: Asset/History/native registration and caller retirement verified. Release Mogwai/FalcorTest build; 318 Python tests, 15 serial headless D3D12 script suites, 18 native core checks and 2 independent Sun/Sky math executables pass. Full manifest: build/resource-history-migration/verification.json. New usage/example and re-audit ledger delivered. Old C++ sources remain uncompiled research material; V5/R4/R5/S4/Q1/C2/D1/F1 are separate. No commit/merge/desktop actions.

## Completed implementation — native described passes and MeshDraw (2026-09-14)

User explicitly authorized completing the two migrations explained in the previous response. Scope/design: docs/superpowers/specs/2026-09-13-native-pass-migration-design.md. Plan: docs/superpowers/plans/2026-09-13-native-pass-migration.md. Evidence: build/native-pass-migration.
- [x] Preserve and hash-verify current source backup; keep Falcor-m0 worktree and unrelated work.
- [x] Native JSON graph loader without required legacy transaction/schema/scene.
- [x] Compute/Fullscreen neutral description and optional legacy bridge.
- [x] MeshDraw uses shared Scene selection/rasterization without mandatory UE material/view/depth ABI.
- [x] RED/GREEN tests, serial build/GPU regressions, independent review and usage/Todo evidence.

Final: pinned CMake Release Mogwai build passed; 620 CPU tests and 9 serial D3D12/debug-layer headless GPU suites passed. Spec and quality reviews closed; missing native gScene now rejects before clear, with RED/GREEN sentinel evidence. Delivered native_described_passes.py, examples/native_passes, Chinese usage and verification index under build/native-pass-migration. Asset/History and UE algorithm/caller retirement remain P3/A1; no commit/merge/deletion/desktop interaction.

Do not implement UE algorithms or whole-graph rollback, modify V5, delete still-used legacy modules wholesale, or commit/merge. Prior discussion entries below are historical and no longer prohibit the specifically authorized implementation.

## Current discussion — remaining legacy callers and native replacements (2026-09-13)

User asks which current callers still use SchemaPipeline, legacy Config, UE material/depth ABI and Adapter, and whether Falcor's existing functionality can replace them. This is a caller/native-capability audit, not authorization for further deletion or implementation.
- [x] Trace concrete callers and separate active framework entrypoints, reference/research graphs and tests.
- [x] Match each required behavior to existing native APIs; distinguish upstream behavior, our reusable extensions and missing UE-specific algorithms.
- [x] Record replacement order and remaining gates with current source evidence; answer the annotated question. Report: docs/research/customrenderpipline-legacy-callers-native-replacement-zh.md; AST inventory: build/legacy-caller-audit-20260913/python-imports.json.

No render source changes, builds, GPU/desktop actions or additional deletion required for this discussion.

## Latest result — authorized retired-file cleanup completed (2026-09-13)

User authorized deleting the eight confirmed retired files only, in Falcor-m0.
- [x] Recheck exact file hashes and active references; archive and verify all eight original byte streams.
- [x] Remove four unbuilt/unregistered CSM prototype source/header files and four invalid Generated snapshot files; update C1 and preserve the frozen audit ledger.
- [x] Verify Release Mogwai build with project-pinned CMake 3.24.1. PATH CMake 4.3.3 failed on pybind11's minimum-version compatibility check; switching only the executable resolved it. No dependency-source or policy workaround.
- [x] Repeat the complete Python suite after build: 605 tests passed in 16.972 s.
- [x] Complete final source/backup integrity checks and publish verification index: all 8 removals/ZIP hashes match; 524 baseline source files checked; zero active references; only the expected CMake comment differs outside removals.

Preserve active Shadows/Setup, native Schema and generator, SchemaPipeline, Config and Adapter. No commit/merge, GPU/desktop actions or additional cleanup. Evidence: build/retired-files-cleanup-20260913.

## Previous result — full-modification audit completed (2026-09-13)

The user requested classification of all changes, not implementation of all remaining TODOs. Completed current source/caller/evidence review across 685 m0 files and 163 original-checkout evidence files; 29/29 tracked diffs covered. Report: docs/research/customrenderpipline-modification-audit-zh.md; exact ledger: docs/research/customrenderpipline-modification-inventory.csv; verification: build/modification-audit/verification.json. 605 fresh CPU tests passed; no fresh GPU/desktop run. No render source changed/deleted/committed. V5 and architecture migration remain explicitly unfinished implementation items. Earlier plans below are historical.


## Completed implementation: V4 (2026-09-12)

User authorized Schema observation/comparison plus external CMD/program access. Completed docs/superpowers/plans/2026-09-12-v4-schema-observer.md. Native ComputePass consumes verified generated codecs; Python and independent CLI expose typed fields/storage/attachment-load values, raw exports and explicit per-field comparisons. Atomic local mailbox is pumped on the render thread after graph execution. Thin RenderGraph device/execute Python bindings and a Mogwai callback revision support integration without old UE contracts. Evidence: build/native-schema-observer/verification.json; 575 CPU tests and 6 D3D12 GPU suites pass. No commits/merges. V5 UI discussion is next; R4 asynchronous readback, R5 broader format/backend coverage, A1 migration, rollback and final RDC remain separate.

## Completed implementation: G4/G5 (2026-09-12)

User explicitly authorized implementation. Completed docs/superpowers/plans/2026-09-12-native-gbuffer-schema.md: independent generic Schema validation/code generation, custom codec extension, native GBuffer integration and CPU/GPU acceptance. The priority-only discussion below is historical. No dependency on the old UE generator/material/depth contracts; no commits/merges or unrelated cleanup. Evidence: build/native-gbuffer-schema/verification.json (495 Python tests; 4 D3D12 GPU suites; independent review closed). No C++ changes or build required; generated Slang compiled and executed. Next discussion point is Todo V4/V5; A1 migration and deferred rollback remain separate.

Latest architecture clarification (2026-09-12): adapt actual UE materials through the generic framework, without depending on our previously developed legacy UE material ABI or depth conventions. Prefer native Falcor capabilities and progressively replace/remove duplicated legacy code after equivalent behavior is verified. An adapter must not merely wrap the old implementation into a permanent dependency. Required UE algorithms may migrate into independent shaders/codecs/Passes. This supersedes any earlier wording that suggests preserving the old custom implementation is itself the compatibility goal. See docs/research/customrenderpipline-memo-zh.md and Todo A1.

## Current follow-up: capability Todo (2026-09-12)

User requested a persistent checklist of completed and unresolved work for four topics: configurable GBuffer, output inspection/error comparison, raw readback, and structured buffers/Cube/mip/array layers. This is a status audit and discussion tracker, not authorization to implement every possible extension.

- [x] Recover existing plans, decisions and recorded verification.
- [x] Check the four topics against code and evidence; distinguish native reuse, branch extensions, incomplete integration and unverified coverage.
- [x] Publish a Chinese checklist and link it from the current project entry documents.
- [x] Publish the checklist link and prepare the status summary; opening it in the Codex panel is queued.

Whole-graph rollback remains deferred. Native Mesh selection is completed within its documented scope. Existing historical implementation checklists below are retained.

Persistent user-facing tracker: [customrenderpipline Todo](docs/research/customrenderpipline-todo-zh.md). Discussion order: configurable GBuffer → inspection/comparison → readback → structured buffers/subresources. Current discussion point: G4/G5, optional Schema generation and semantic validation for the native GBuffer entry.

G4/G5 priority recommendation: implement shared storage-layout generation and validation together before expanding downstream consumers. Preserve authored special quantization and multi-field codecs. Define the contract from generic needs; the old generator may inform small verified utilities, but must not become a dependency or impose its material/depth conventions. This remains a scope/priority discussion; implementation has not started.

Current user-approved scope: custom material/GBuffer definitions and codecs, composable described passes, output inspection/raw reads/error comparison. Exact public spelling: `customrenderpipline`.

User-requested native integration (2026-09-12): selected Mesh drawing belongs in Falcor Scene and should be shared by Passes, instead of being implemented independently in each plugin. Implementation/validation plan: docs/superpowers/plans/2026-09-12-native-raster-draw-list.md. The stock GBufferRaster and configurable native-material GBuffer now use the same Scene draw-list API. Legacy UE per-draw state remains separate.

Integration completed: full Release build, 3 native core GPU tests, 5 Mogwai GPU suites and 469 Python tests passed. See docs/research/customrenderpipline-native-mesh-selection-zh.md and build/native-raster-draw-list/verification.json for behavior and limits.

Latest decision (2026-09-12): whole-graph transactional rollback is deferred at the user's request. Do not treat integration into the new native entry as required work or an acceptance blocker. Use Falcor's native error/reload workflow for now. Existing rollback code is unchanged. See [project memo](docs/research/customrenderpipline-memo-zh.md). This decision supersedes the earlier requirement to provide rollback in every entry below.

- [x] Rename active plugin, source paths, class/binding prefixes, scripts and tests; preserve original UE excerpts and historical evidence.
- [x] Make the framework entry require a graph description. Move implicit UE graph construction and rendering effects into an explicit reference extension/example.
- [x] Load reusable JSON pass descriptions with relative file resolution through existing immutable snapshots.
- [x] Add generic explicit numeric error comparison and tests for descriptions, comparison and rollback.
- [x] Build and run CPU/GPU regression checks serially; update Chinese usage documentation.

Workspace: E:/Project/falcor/Falcor-m0, existing uncommitted work retained. No commits/merges. Historical build snapshots remain unchanged. FY1 hair/deferred/shadow/full-image alignment remains a separate unfinished task.

## Native Falcor usage audit (completed)

Objective: investigate existing Falcor examples and APIs, identify incorrect usage and overdevelopment in customrenderpipline, reuse native facilities where they meet the requirement, and reduce avoidable complexity.

- [x] Compare graph declaration/scheduling, shaders/material/GBuffer execution, history, inspection/readback, error measurement, hot reload and core modifications with native examples and implementations.
- [x] Record evidence per component: native alternative, exact capability gap, retain/simplify/remove decision and risk.
- [x] Implement justified simplifications and usage corrections without losing custom material/GBuffer, described Pass composition or failed-update rollback.
- [x] Run relevant native-vs-custom validation, inspect the final diff, and publish an actionable Chinese audit with accurate limits.

The migration above is complete. Do not use its green tests as evidence that this audit or simplification is complete.

Audit deliverables: docs/research/customrenderpipline-native-falcor-audit-zh.md and build/native-falcor-audit/verification.json. This audit removed redundant ordinary C++ readback, documented native-first output/error/pass usage and reviewed all 23 existing core-file patches. Fresh full Release build, 469 Python tests and six D3D12 GPU suites passed. Remaining integration limits and strict snapshot cost are recorded explicitly; no new dependency cache, scheduler or viewer subsystem was added. FY1/final RDC alignment remains separate and unfinished.

## First native replacement: configurable GBuffer

- [x] Back up current work and verify archive hashes.
- [x] Replace ordinary GBuffer with native Scene/MaterialSystem/RenderGraph and a thin JSON/Slang MRT adapter; no old Scene JSON, Schema generation or transaction prerequisites.
- [x] Rename the old UE-specific writer to UEReferenceGBufferPass and migrate existing callers; retain the non-equivalent UE algorithms.
- [x] Deliver native_gbuffer.py, packed layout example and Chinese documentation.
- [x] Validate native material comparison, integer layout, Properties/updatePass, dynamic outputs and stock Blit composition; pass 469 CPU tests and existing framework/material GPU regressions.

Evidence: build/native-gbuffer-refactor/verification.json. Legacy adapter_smoke.py uses now-rejected captured primitive_flags and did not pass; the rejection predates this change. Other core patches remain subsequent discussion items. Whole-graph rollback integration into the new native entry is explicitly deferred; see the latest decision above.

## 2026-09-13 — Completed full-modification audit

User goal: classify all current modifications as mainline/retire/obsolete/research support and identify real TODOs. This is an audit, not permission for bulk deletion or implementation of all optional features. Earlier V5 implementation is paused; include its actual incomplete status.
- [x] Inventory all tracked diffs and untracked source/module families against HEAD; identify ignored generated evidence separately.
- [x] Inspect native core patch purposes and current callers; distinguish reusable fixes from legacy coupling.
- [x] Trace native-first Python/plugin entrypoints and old UE framework consumers; prove any obsolete candidates rather than relying on names.
- [x] Check research/effect prototypes, tests, examples, docs and prior validation provenance against current files.
- [x] Publish a full classification report with evidence, retention/deletion gates and prioritized TODOs; update capability tracker contradictions.
- [x] Verify inventory coverage and report links, preserve implementation code, then report outcome and complete the audit goal.

## Current action — exact-depth lifecycle direct coverage
- [x] Add D3D12 pending-drop with real finite workload, mandatory pre/post pending markers, debug-queue errors and exact recovery planes.
- [x] Add last-Device-owner depth/stencil data access and teardown; assert the two staging buffers are the only Falcor Device owners.
- [x] Build/run strict native cases before any production change; inspect actual native logs and include depth header/test hashes in runners.
- [x] Record depth outcome/review and V5 fixture lifecycle. Final performance remains next.

## Active performance execution — 2026-09-14
- [ ] Same-process/same-graph 1280x800 native Schema scene: graph-only, service idle, Inspector snapshot idle, direct async/sync pixel reads and real panel demand at a fixed cadence. Warm each mode; record full per-frame arrays, p50/p95/p99, callback/API cost, request latency and process working set/private bytes.
- [ ] Idle counts must stay fixed; async/sync values must equal an oracle; pool must remain bounded and drain. No sleeping/screenshot/readback outside requested action in timed frames. No optional expensive synthetic GPU workload.
- [ ] Separate default-profiler wall timing from native GPU capture, because start_capture enables native profiler UI/timestamps. Profile pause diagnostic is a separate counterfactual, not the shipped default.
- [ ] Verify Logger/source/binary freshness, independent measurement review, then investigate actual waits with scoped native evidence if timing exposes a stall. Headless numbers do not close visible desktop responsiveness acceptance.


2026-09-15 source-origin final root check: new934/prior756file checkpoints freshPASS;22diagnostic/118targetmapCPU PASS. Independent source-origin-runtime-review complete. FinalGPU/build/replayprocess inventory0. Frozen source-origins-verification.json and final-root-check index retained. FullgoalACTIVE; this turn made real GPU/differential/reset progress, not blocked/wait. No promotion/commit/merge/reset. Next A1 exactdepth/material/background andformalinputcontracts, thenA2-A5.

2026-09-15 user requests complete lighting. A2 active under approved source-only RenderGraph design; plan docs/superpowers/plans/2026-09-15-targetmap-lighting-a2.md. Current source light has4CSM/20000cm/exponent3/angularradius, retained native sun/atmosphere algorithms. SourceBRDF remains but wrappers retired. 2.rdc directdrawE2227 followsSSGIcomposite; comparepre/post separately, never comparefullHDRtoisolateddirect. NeedownedSSGI/DFAO/SSRhistory andcloud/fog; no capture resource input.


2026-09-15 lighting continuation: A2 native1a1e0502 PASS execution, all13 A1raw unchanged; extra GPU depth export matches original D32S8 plane exactly. Native D32S8 SRV error proven under own cdb76941d83, resolved by native Equal-depth MeshDraw to R32 (no core build). Source sun RGB/radius matchE2227. Offline shadow BGRA->RGBA comparison4240px differ1code; directMAE0.0001023354/max0.00623196 includeshalfblend andmask residuals, not parity. A3 source environment88de2fb3 executes32.19s/Logger531clean, all25A2raw unchanged; ownatmosphere LUTs,6faceCube128,filter/SH/BRDF,mainSky/environmentlighting run. Original sky numerichelper builtinscratch; native sourceCPU smokeqkt1mdwvPASS. NoSSGI/DFAO/SSR/history/exposure/fog/cloud closure yet. A4 read-only2909/2935 referencee7eea9abPASS; sourceonlyvolume/fognext. No promotion/commit/merge/reset; A1frozen2323unchanged.


2026-09-15 A4 continued: original atmosphere volume shader adapted to explicit native resources/cbuffers; failed syntax fafd2092, helper-view b2ec9c63, root-signature d7c783e8/cdb1ef5c463 preserved. Actual D3D12 diagnosis proves implicit-global CBV block mismatch, corrected with explicit AtmosphereDispatch. Native2f1c1c3d executes31.57s, exit0/Logger536 no validation errors; all34 A3raw unchanged. Own DistantSky, CameraAP, AerialApply, HeightFog now run; not yet numeric parity. Clouds/GI/AO/SSR/history/exposure and finalE2793/E2962 still open. FrozenA1 untouched; no corebinary/source build or commit/merge/reset.


2026-09-16 resumed sampler audit: fresh direct-shadow-zero verification passes 1109 identities and 12 numeric checks; exact scope remains offline exposure/blend direct RGB plus bitwise atlas/mask, not full lighting. Source material instance overrides only RefractionDepthBias=0, no lighting scalar/vector overrides; source texture exports match instance textures. Capture axes/origin/resolution match source. E2858 material uses sampler5 Wrap/Aniso8 with explicit SampleLevel0; source World texture group is aniso, quality3 max8. Native wrapper is Linear Wrap. Isolated generated/source GPU sampler probe will test this difference; no frozen candidate modified, no captured runtime input. Source shadow-step accumulation and per-octave extinction order remain audit leads. Pending time/frame permission remains unanswered.

2026-09-16 cloud-shadow sample contract: initial d0fa4720 invalid reference extraction omitted PreviousNormT update; preserved but not evidence. Corrected bf70d390 RED on old candidate: 248/316 cases, 29466 components, source count10 profile63 differences across4 distances. Generated source sample positions match original float increment semantics. New isolated source-cloud-shadow-steps modifies only main CloudTrace shadow-loop advancement, not frozen candidate. GPU source contract and full-chain results pending.

2026-09-16 stepcontract b7968415 GREEN316cases exact, Logger650 clean. Fulla03ca042/6bb79b85 are INVALID comparisons: inherited launcher lacked five source profile env options, so grid fell back to original unmipped BGRA, anisotropy1, sourceorigin/localcm0. Graph diff proves this configuration drift (no frozen source change; prior922phasecheckpoint freshPASS). Their MAE.010961 is not a shader regression measurement. New candidate launcher pins and records SOURCE_PLATFORM_RUN=build/source-platform-texture/export-lwut1xhz, GRID_ANISOTROPY=8, SOURCE_ORIGIN_CM=1, SOURCE_LOCAL_CM=1, FRAMES=2. Retry full runs with exact baseline profile; keepinvalidartifacts fortraceability.
