# targetmap / 2.rdc shading 对齐进度

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


## 已确认范围

用户确认 **E2962 最终验收、E2793 中间检查点**，不经过 Bloom、Tonemap、调色比较。生产路径复用原生 RenderGraph、customrenderpipline 通用 Pass、Schema/Slang，不恢复旧 Config/UE ABI/事务；捕获输出只作离线 oracle。

## 当前：A1 原生 GBuffer 已绘制并实测；完整 shading 未完成

2026-09-14：最初基线只新增 Python/JSON/Slang；后续为采样器配置增加了一个通用 C++ 包装字段 `max_anisotropy`（原生 Sampler API 本来已有）。未增加 targetmap 专属渲染 C++，没有恢复旧 UE ABI。

### 2026-09-15 后续：相机相对平移的舍入边界

- 实际native capture + CPU逐位复算确认，米单位translation×100与相机high合并计算改变了相对原点。局部保持源舍入边界后，两个Sphere最大depth点与参考逐位一致，reset7raw完全重复。
- Basic depth最大误差降至2.3469e-7、normal仅剩2个分量，**但这2个分量是同1像素的大法线跳变，不能说只差2LSB**。相对SNORM候选，整个source-order链仍有更广的depth差异；局部修复未新增这个已有跳变，仍不得合入。
- Cube/Cube2原始-240cm经float32米单位往返变成-240.000015cm。下一步独立保留源厘米origin并验证instance映射，而非从米矩阵反推精确值或对单个mesh调数。
- 新独立检查点 `translation-verification.json`：756文件，真实raw复算与新进程复验通过；旧199/381/688检查点保留。**A1、E2793/E2962验收均未完成。**

### 2026-09-15 最新：顶点法线与实际 VS 证据（尚未合入）

- Falcor 顶点解包会提前归一化 normal，且经过 half 存储；局部解码保留源长度、恢复源 SNORM8 code 后，Basic A 的差异由 **3074→1443→13**，前两步分别只改变 A.raw，另外六份 raw 不变。剩余13像素各差1code，新进程重复7raw一致。
- direct-cm 顶点属性没有解决最大深度误差，且使Floor材质回退，不合入。显式源XYZ累积顺序使Floor rough/metal/C降至124/463/177，Floor depth max减半至3.72529e-9，但Basic仍有15个normal分量差异和1.8496066e-6最大depth误差，同样不合入。
- 真E1437 oracle确认Sphere源IB2880indices和SNORM1677codes精确一致；OBJ位置仍丢低位。最大depth点在小三角形/轮廓附近，对1/256像素栅格量化敏感。E1437自身不写depth，下一步核对真正的E770 prepass。
- 对当前候选做了一帧独立native capture，输出与未捕获运行7raw完全相同；实际DXIL保留了显式累积顺序，不能把残差直接归咎编译器重排或靠盲加precise解决。
- 本轮无正式源码/二进制修改，118项原targetmap CPU测试通过；独立检查点 `build/targetmap-shading-a1/vertex-verification.json`，复验 `verify-vertex-checkpoint.py`。**A1和E2793/E2962完整shading仍未完成。**

### 先前：坐标与相机精度隔离验证（尚未合入正式入口）

- 源材质使用 SV_Position/depth 重建位置；旧基线使用插值绝对世界位置。只替换 PS 坐标路径后，Floor 的 rough/metal/C 分量差异由1069/2993/1350降至262/857/330。
- 独立源资产导出补齐相机 double 参数；按编辑器 float UE_PI、矩阵/viewport源码顺序重算后，重建矩阵16个float32值与离线参考逐位一致，没有上传捕获矩阵。
- PS 使用精确源相机后的差异为237/748/294，其他五个raw输出不变。材质保持cm计算的后续对照与其7raw完全相同，没有独立改善。
- 新源相对坐标 VS 候选进一步降至162/566/228；新进程重复7raw一致。仍有14个Floor B像素>1code（4个>2code，metal最大4）；Basic normal由3069变3074个分量不同，depth最大误差略增至1.8496066e-6。**有局部回退，未合入正式入口，不能称整个GBuffer修好。**
- 正式源码/二进制未变，旧199文件平台检查点保留；新诊断、实际源导出与复算证据见 `build/targetmap-shading-a1/coordinate-verification.json` 和 `coordinate-diagnostic-report.md`。A1、E2793/E2962均仍未完成。

### 已验证基线：源平台纹理 / Aniso


- `sampler-build-_fb6k9yy` 构建成功，`sampler-cpu-sekddk7z` 4 项真实 native CPU 测试通过。
- `sampler-gpu-aeto40k2`：D3D12 下 Compute / Fullscreen / MeshDraw 的 12 组结果全部与原生 `create_sampler()` oracle 精确一致，36 组非法配置拒绝；真实 Logger 无 GFX error。1→8 的输出确实改变，不是“参数接受了但未生效”。
- 新默认基线 `native-d94f6760` 的 7 份 raw 与 `native-f309d4b0` 逐字节相同，扩展未改变默认渲染。
- 隔离源导出 `export-_l124_46`、`export-lwut1xhz` 均正常退出，编译收尾 remaining=0，源资产/引擎受保护文件哈希未变；两份 BC1 sRGB 512² / 10mips / 174,776 bytes 逐字节相同。旧失败和 shutdown dump 保留；只在独立导出模块收尾，不修改原 UE 引擎。
- 真回放 `texture-19bca6a6` 导出 E1452 实际 Pixel t5 / Resource3905；双 shutdown、RDC 前后哈希通过。**两份独立源导出的全部10mips都与捕获压缩字节精确一致**，捕获数据仍仅用于离线比较。
- 单变量验证：`native-5ab7cda6` 只切源 DDS/mips、保持 Aniso1；`native-4cc2c229` 再单独改 Aniso8。独立源导出 + 新进程 `native-3c99e4f0` 重复后，7份raw逐字节相同。
- 地板 C 颜色差异从377,010个通道值降到**1,350**（450像素RGB，每通道最多2code）；B 粗糙度141,005→**1,069**，金属度155,898→**2,993**。B仍有40像素超过1code，最大粗糙度3/金属度11；不是可以直接忽略的量化误差。
- 当前 CPU 分组通过：targetmap118、source-platform16、native59；真实 nativeCPU4 + samplerGPU12对照/36拒绝。独立评审发现的导出时序/同读hash/旧结果重用三项P2已修复。当前checkpoint为 `platform-verification.json`（199文件身份验证）；初始`verification.json`仅保留为历史基线。

本段证据均位于实现树 `build/targetmap-shading-a1`，源导出位于 `build/source-platform-texture`。修改的是 `plugins/customrenderpipline.dll`；`Falcor.dll` 本次未改变。

初始两次 reset 基线：`build/targetmap-shading-a1/native-f309d4b0`、`native-e06eff41`。下表记录这些初始基线；源平台增量后的 Floor 数值以上段为准。所有实际native Logger无GFX validation error，仍保留原生Shader warning。这不是整个shading图的完成声明。

| E1452 检查项 | 当前实测 |
|---|---|
| Opaque coverage / stencil | **1,258,627 像素逐像素一致**，漏/多像素均0 |
| BasicShape 材质区域（203,219像素） | B/C 全通道原始值一致，即材质颜色、金属度、粗糙度、specular和模型/alpha；normal A仍有3,069个分量不同 |
| Floor材质区域（1,055,408像素） | normal A、specular、模型/alpha一致；颜色、粗糙度、金属度仍受纹理采样差异影响 |
| Depth | 全部opaque最大绝对误差`1.7620623e-6`；Floor区域最大`7.4505806e-9`，**不等于逐位一致** |
| SceneColor | Opaque全0一致；背景alpha及6,520像素的早期Editor天空内容尚未实现 |

材质区域是从GBufferC颜色分类且两端mask一致，不是primitive/object ID，也不保证每个像素是同一表面。Basic normal超过2code的差异仅有1个共享面边界像素；不能把它当作普通量化误差忽略。

已修的实际原因：源相机投影使用**未缩放2465×1795**，而非取整后的render1421×1035；allocation仍1424×1040。尺寸由独立Upscale marker/输出资源确定，再按UE源公式计算矩阵，未上传捕获矩阵。修正前漏117像素、depth max约`0.0128`；修正后coverage精确。源码frame index自主从0推进1后，specular抖动也逐像素一致。

脚本默认保留旧单mip基线便于差分；设置下面两个环境变量即启用已验证源BC1/mips/Aniso8。下一步排除剩余地板数学/插值差异、源几何/法线精度，再进入A2光照。不是恢复Falcor旧框架。最终E2793/E2962仍未验收。

重放与比较（在实现树执行；新输出由runner自动分配，有限帧后关闭）：

```powershell
$env:CRP_TARGETMAP_SOURCE_PLATFORM_RUN='E:/Project/falcor/Falcor-m0/build/source-platform-texture/export-lwut1xhz'
$env:CRP_TARGETMAP_GRID_ANISOTROPY='8'
python build/targetmap-shading-a1/run-bounded.py native
python scripts/customrenderpipline/targetmap_gbuffer_compare.py build/targetmap-shading-a1/reference-ffeea6e8/reference/manifest.json build/targetmap-shading-a1/native-3c99e4f0/result.json
python build/targetmap-shading-a1/verify-platform-checkpoint.py
Remove-Item Env:CRP_TARGETMAP_SOURCE_PLATFORM_RUN
Remove-Item Env:CRP_TARGETMAP_GRID_ANISOTROPY
```

当前partition、源码/原始数据hash见`build/targetmap-shading-a1/platform-verification.json`；原`verification.json`保存早期基线。仅所述源DDC/reset重复性被验证；不是完全冻结全部工具链/驱动的hermetic构建。

## 已完成 A0：两截点 raw HDR 基准

- 两个独立隐藏 RenderDoc replay 正常退出。RDC 前后 SHA256 均为 `059eef7978d1c32039ad4bd21b5b0c59574c393996fb842b37f3a9e4a87edb2f`。
- 实测两截点均为 `ResourceId::955 SceneColor`，`R16G16B16A16_FLOAT`、单采样、mip/slice/sample=0。
- 实测 viewport/scissor `[0,0,1421,1035]`，allocation 1424×1040；有效 **1,470,735** 像素，padding **10,225** 像素。每份 raw RGBA16F 为 11,847,680 bytes。
- 两次独立回放的**有效区和 padding、RGB 和 alpha 均逐位一致**，MAE/RMSE/max/ULP 全0，无NaN/Inf，alpha全0。这只证明参考可重复，不证明Falcor对齐。
- 有效区最大RGB：E2793 `[2.5,2.16796875,2.0]`；E2962 `[2.4921875,2.16015625,1.994140625]`。没有转8bit或经过显示变换后验收。
- 新增 **43 个CPU合同测试**通过；每轮58份 artifacts 的尺寸/hash复核通过。这不是全量Falcor渲染回归。

## 相机与输入发现

将实际 E1452/E2793 Shader 的 `_hostlayout.View` 前103字段类型、2576-byte布局，与保留源布局核对；源hash、字段offset、实际绑定cbuffer字节均检查。

| 项目 | 本轮证据 |
|---|---|
| 捕获相机 UE cm | `[-1602.4513503884082,-491.1669873420692,290.0183994397671]` |
| 与保存地图位置最大分量差 | `4.3976712e-7 cm` |
| 朝向矩阵最大分量差 | `3.7431302e-8` |
| 水平FOV | 捕获约90.0000034°，保存90° |
| Near | 都是10cm |
| 当前/前帧 View、Projection | 字节解码数值相同 |
| PreExposure | `1.3405122756958008`；实际E2793 shader从cbuffer1 offset2568读取并参与乘法 |

保存的相机参数已有匹配证据；A1后续已逐像素测量新投影/Depth/GBuffer，范围及剩余差异如上。未改源Scene.json的自报标志。关闭后处理不能把shading内的PreExposure直接改成1。

实际SRV绑定还确认：
- SSGI读取上一帧SceneColor40828/Depth40816和TemporalAccumulation资源。
- DFAO读取BentNormal history。
- SSR TAA绑定EyeAdaptationBuffer1955及上一帧SSR.TemporalAA40834。

限制：字段名来自不同材质的源布局，实际类型/offset前缀一致不等于找到了capture完整同源Shader；静态使用绑定不证明每个像素的动态分支贡献。A0仅导出两张HDR oracle和常量审计数据；A1另导出GBuffer/Depth作为离线oracle，均未用作生产输入。历史贴图未导出或回灌。

## TODO

- [x] **A0**：固定事件/资源/视口/格式，raw HDR、输入身份、独立回放复验。
- [ ] **A1（进行中）**：源场景/新GBuffer接通，coverage/stencil及部分材质字段已逐像素匹配；源BC1/mips字节和Aniso已验证，继续地板残余数学/插值、源mesh法线与Depth精度、背景clear/Editor draw。不能提前关闭。
- [ ] **A2**：CSM/方向光数学适配中立Pass，阴影/GBuffer全部自产。
- [ ] **A3**：SSGI、DFAO、SSR及历史/滤波，明确可重建初始状态与PreExposure来源；验收E2793。
- [ ] **A4**：天空、雾、云复合；验收E2962。
- [ ] **A5**：从明确reset/baseline重跑全图，输出raw差异；容差须提前说明依据，不事后调宽。

FY1和此前V5 UI阻塞目标独立，本轮未恢复。A1初始图仍是中立Python/JSON/Slang；后续通用sampler字段与隔离UE导出模块的C++增量如上。无commit/merge/reset。

## 文件与证据

实现树 `E:/Project/falcor/Falcor-m0`：
- collector：`scripts/customrenderpipline/_targetmap_shading_replay.py`
- 离线验证/比较：`scripts/customrenderpipline/targetmap_shading_reference.py`
- 原始A：`build/targetmap-shading-a0/reference-a-0e5c7221/reference/manifest.json`
- 原始B：`build/targetmap-shading-a0/reference-b-acc007f9/reference/manifest.json`
- 数值结果：`build/targetmap-shading-a0/final-repeatability.json`
- 输入审计：`build/targetmap-shading-a0/input-identity-audit.json`，执行脚本`audit-input-identity.py`在同目录。脚本拒绝覆盖已有审计。
- 两轮launch/result/stdout/stderr、CPU日志、RED/GREEN和review.md保留在build证据目录。

### 离线复核

```powershell
Set-Location E:/Project/falcor/Falcor-m0
python scripts/customrenderpipline/targetmap_shading_reference.py compare build/targetmap-shading-a0/reference-a-0e5c7221/reference/manifest.json build/targetmap-shading-a0/reference-b-acc007f9/reference/manifest.json
python -B -W error -m unittest discover -s scripts/customrenderpipline -p 'test_targetmap_shading_*.py' -v
```

`accepted=true`只代表参考raw重复性，`full_renderer_parity`明确false。`--out`必须是输入reference目录外的新文件，拒绝覆盖已有文件；默认输出stdout。

### 新建只读回放

确认没有本任务另一个replay运行后，每次使用新目录：

```powershell
Set-Location E:/Project/falcor/Falcor-m0
$script=(Resolve-Path scripts/customrenderpipline/_targetmap_shading_replay.py).Path
$out=Join-Path (Resolve-Path build/targetmap-shading-a0).Path ('reference-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $out | Out-Null
$env:CRP_TARGETMAP_REFERENCE_OUT=$out
$env:CRP_TARGETMAP_REFERENCE_SCRIPT=$script
try {
    $p=Start-Process 'C:/Program Files/RenderDoc/qrenderdoc.exe' -ArgumentList @('--python',$script) -WorkingDirectory $out -WindowStyle Hidden -RedirectStandardOutput "$out/stdout.log" -RedirectStandardError "$out/stderr.log" -PassThru
    if (!$p.WaitForExit(120000)) { Stop-Process -Id $p.Id; throw 'Owned replay timeout' }
    Get-Content "$out/result.json"
} finally {
    Remove-Item Env:CRP_TARGETMAP_REFERENCE_OUT,Env:CRP_TARGETMAP_REFERENCE_SCRIPT
}
```

必须检查新result的passed/capture_unchanged/shutdown及manifest，再运行离线validate，不只看exit0。导出上限64MiB，每轮实际25,004,923 bytes；这不是进程内存/显存测量。

## 本轮工具修复

- 首轮collector在capture打开前失败：qrenderdoc不设置`__file__`。改用显式script环境变量并加测试；顶层异常会退出，不再留下错误窗口。原失败记录保留；临时native日志退出后消失，仅保留当时读取的错误证据，不声称完整原日志已归档。
- `view_rect`从误用LTRB修成xywh，增加非零origin测试。
- review发现CLI `--out`可能覆盖基线，已RED/GREEN修复目录保护与exclusive创建，并独立复验。

2026-09-15 source-origin final root check: new934/prior756file checkpoints freshPASS;22diagnostic/118targetmapCPU PASS. Independent source-origin-runtime-review complete. FinalGPU/build/replayprocess inventory0. Frozen source-origins-verification.json and final-root-check index retained. FullgoalACTIVE; this turn made real GPU/differential/reset progress, not blocked/wait. No promotion/commit/merge/reset. Next A1 exactdepth/material/background andformalinputcontracts, thenA2-A5.
