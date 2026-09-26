# customrenderpipline Todo：原生复用与剩余事项

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


更新：2026-09-14。实现工作树：`E:/Project/falcor/Falcor-m0`。

**最新（07:59）：原三项迁移与 C2 清理完成；Depth pending-drop / completed-task last-owner 加验完成。新发现并修复原生 GpuTimer resolve 状态错误、Windows CLI 回复暂时占用导致的偶发失败；V5 live 入口有原生重开按钮及同服务/idle 验证。当前严格 R4 为 55 native / 11 GPU suites / 372 CPU；Q1/R5/S4 为 13 native / 5 GPU suites / 372 CPU。两次 CPU 是同一测试集，不能相加。**

08:15 原三项及 372 Python tests 新鲜重放通过；08:16 完成同图 headless 帧时间/GPU 事件/进程内存测量，空闲没有新观察 dispatch/readback，但这个小场景未证明异步比同步更快。[性能数据与边界](customrenderpipline-application-performance-20260914-zh.md)。

**08:39 续验：** 指定原生等待 API 的耗时已用临时探针直接测量，探针完全还原并重新构建；当前严格 R4 `async-stage3-20260914-083244` 为55 native/11 GPU/372 CPU，Q1 `q1-r5-final-v5wxs5u3` 为13 native/5 GPU/372 CPU。[等待测量及边界](customrenderpipline-native-wait-measurement-20260914-zh.md)。

完整目标仍未完成：V5 真鼠标、同实例 ErrorMeasure UI 与最终完成签核仍待收尾。最新 live-fzedmw7h 看到锁屏背景，测试实例已正常关闭，没有发送输入；已请用户解锁。[当前进度与证据](customrenderpipline-native-completion-status-20260914-zh.md) · [Asset/History 用法](customrenderpipline-native-resources-history-zh.md)。旧 RED 与归档字节保留。

**长期原则：适配 UE 材质本身，尽量淘汰此前自研的重复 UE 实现。** 新框架不依赖旧材质 ABI、生成器或固定深度约定；需要的 UE 行为通过通用 Shader/codec/Pass 扩展表达。适配不能变成对旧模块的长期包装依赖。详见[项目备忘](customrenderpipline-memo-zh.md)。

这份清单跟踪用户提出的四项能力，后续按 **1 → 2 → 3 → 4** 逐项讨论和更新。`[x]` 表示条目所述范围已实现或已确认可复用；`[ ]` 后明确标注“未完成”“待讨论”“未验证”或“暂缓”。待讨论的扩展不自动成为必做功能。

资源迁移阶段历史验证：Release Mogwai/FalcorTest 构建、318 项 Python tests、15 组串行 D3D12 headless 脚本、18 项原生核心检查及 2 个独立 Sun/Sky 数学程序通过。完整删项与 test IDs 对账、结果及限制见 `build/resource-history-migration/verification.json`。

上一轮 P2/M2 历史验证（不是本轮测试总数）：Release Mogwai 构建、620 项 Python tests、9 组串行 D3D12/debug-layer headless GPU 用例通过，包括 indexed/nonindexed Mesh、新 Schema/observer 和代表性旧执行器回归。没有桌面交互或帧率测试；不代表所有旧 smoke、格式、平台和场景均已验收。索引：`build/native-pass-migration/verification.json`。

| 项目 | 已解决 | 剩余事项 |
| --- | --- | --- |
| 1. 自定义 GBuffer | 原生 Scene/材质/RenderGraph；JSON 附件；Schema 同源生成 encode/decode；位段/类型/声明范围校验；手写特殊 codec | G4/G5 本阶段已完成；任意 Shader 算法仍需自身参考测试，UE 材质迁移另见 A1 |
| 2. 输出观察与误差 | 复用 Mogwai、原生比较 Pass；特殊资源图集；Schema 字段解释、按字段容差、Python 与外部 CLI 访问；V5 UI 主体已实现 | V5 对话框错误/真实交互/最终回归和文档未闭环；Schema 解码目前限单采样二维 mip 0；旧封存图已退役 |
| 3. 原始读回 | 保留原生 `to_numpy()` 同步 API；Texture/Buffer/精确 D32S8 异步路径、按需共享有界池已验证 | R4 真实 UI/最终签核；headless 性能已测，其他格式/后端按 R5 的明确支持范围 |
| 4. 结构化缓冲与子资源 | 已补齐图层 stride/count 反射和分配；修复 Cube 面/mip/数组层及相关 view/barrier | 本轮有界 Vulkan 矩阵已完成；未列明/显式拒绝的组合不因此视为支持 |

## 1. 自定义 GBuffer 附件、通道、位编码

- [x] **G1｜原生集成。** `CustomRenderPiplineGBufferPass` 使用 Falcor Scene、MaterialSystem、RenderGraph；普通入口不再依赖旧 Scene JSON、SchemaPipeline 或 Schema 生成器。
- [x] **G2｜附件配置。** JSON 声明 1–8 个颜色附件的名称/格式、深度格式、Shader 与入口；校验名称唯一、保留名、附件数量、GPU 格式绑定能力等。
- [x] **G3｜可改编码与解码。** Slang 决定通道、位段和编码公式；共享 codec 供后续 Pass 解码。已提供默认与 packed 两种布局，并验证原生材质对照、整数位字段和属性重建。修改布局时仍要同步 JSON 与 Shader 输出签名。
- [x] **G4｜完成：新入口的 Schema 自动生成。** 独立生成器从字段/存储/codec 描述生成同源 Slang encode/decode、元数据及现有原生 GBuffer Pass 的 JSON/Shader 定义。提供 uint/sint/bool/unorm/direct，并支持手写非线性量化与多字段 custom codec。示例用平方根粗糙度和八面体法线编码，无旧 UE 模块依赖。[使用说明](customrenderpipline-gbuffer-schema-zh.md)。
- [x] **G5｜完成：布局合同校验。** 检查名称/保留字、字段类型、位段重叠/容量、声明范围、完整且唯一的 codec 分配。运行时按声明 clamp/reject，拒绝非有限数、内置浮点 codec 的非零 subnormal 输入和 custom 越界存储；失败返回 false 和零输出。同名不同合同头在同一编译单元会冲突，包括直接 custom 源内容变化。独立旧消费 Shader 不会自动接受跨 Pass ABI 检查，特殊算法仍需参考测试；不是任意 Shader 的正确性证明。

使用：[原生 GBuffer 说明](customrenderpipline-native-gbuffer-zh.md)、[Packed.json](../../scripts/customrenderpipline/examples/native_gbuffer/Packed.json)、[codec 示例](../../Source/RenderPasses/customrenderpipline/NativeGBufferCodec.slangh)。

证据：[原生 GBuffer 验证](../../build/native-gbuffer-refactor/verification.json)。对照场景 4678 个覆盖像素的颜色、粗糙度、法线最大误差为 0；不是最终 RDC 画面对齐证明。示例材质 ID 只有低 16 位，不能直接当成任意材质 ABI。

G4/G5 历史证据（2026-09-12）：[Schema 生成与校验](../../build/native-gbuffer-schema/verification.json)。该次 495 项 Python 测试通过（新增 26 项），4 组 D3D12 GPU 脚本通过；新 UINT/UNORM 位附件分别在 2016 个覆盖像素上验证实际 MRT 写入和下游解码。该次 G4/G5 实现未改 C++，无需重编原生程序；生成 Slang 在该次验收中实际编译执行，不是本轮审计重新运行的 GPU 结果。

## 2. 查看输出、截图、并排/分屏、图像误差

- [x] **V1｜复用原生观察。** Mogwai 提供输出选择、Debug Windows、Save To File、PixelZoom；已有 `SideBySidePass`、`SplitScreenPass`。这些是原生功能，本轮确认源码存在，没有把它们记为我们新实现或新做过 UI 验收。
- [x] **V2｜比较工具。** 常规 RGB L1/MSE 与差分图复用原生 `ErrorMeasurePass`，已有 GPU 组合验证。补充的 `compare_arrays()` 支持 `abs(actual-reference) <= atol + rtol*abs(reference)`、失败样本数、最大误差和 RMSE；输入必须有限且编码/单位一致。
- [x] **V3｜特殊资源基本观察。** `PipelineObserver` 提供 raw/structured 数据、选定 mip/层/Cube 面以及 GPU 图集；已有 observer、structured buffer 和 24 个 Cube 面/mip 组合验收。
- [x] **V4｜完成：Schema 字段解释、按字段比较及外部程序访问。** `PipelineObserver.schema()` 接入 G4/G5 Metadata/decoder，提供完整附件绑定、GPU 解码、字段/存储槽/Texture.Load 值、整数精度保留及 exact/numeric/angle 比较。支持手写 custom decoder；颜色格式转换由硬件按声明格式执行，额外语义转换和容差由调用者明确配置。已提供运行中 Mogwai 实例的 CLI、JSON、NPZ/原始 bytes 导出及超时/退出码。Schema 字段观察目前限单采样非数组二维 mip 0；其他子资源继续使用已有原始读回入口。[使用说明](customrenderpipline-schema-observer-zh.md)。
- [ ] **V5｜实现中：Mogwai 原生 Schema Inspector。** 字段/附件预览、像素、容差比较、导出及异步 callback 生命周期已通过；Unicode 路径和对话框异常/取消/重试已修。真实鼠标尚未通过：最新 `live-fzedmw7h` 看到 Windows 锁屏，没有发送输入，已关闭测试实例。解锁后继续真实文件选择/比较/导出/关闭重开；callback 测试不能替代。
  - [x] 修复 Windows `open_file_dialog` 的路径编码与面板对话框异常提示；真实交互仍在下一项验收。此前 `live-0c9ds7bo` 仍为锁屏，无鼠标/键盘输入，测试实例已停止。
  - [ ] 完成真实点击/选取/文件选择、最终 V4/Schema GPU 回归、使用文档及源 hash 验证索引。程序化调用 click callback 不计真实鼠标验收。
- [x] **V6｜旧限制已退役。** 旧 SchemaPipeline 封存输出策略不再是当前入口；原生图可动态 markOutput。无需为旧入口继续实现动态输出封存。

V4 外部访问实现与验收：

- 提供进程内 Python API 和可从 CMD/PowerShell 调用的 CLI，复用同一套观察/比较逻辑。外部程序能列出可观察输出与字段、查询像素/区域原始值和解码字段、按规则执行参考比较及导出结果；无需依赖 UI 点击。
- 通过本地会话目录的原子 JSON 请求/响应访问已启动实例，请求明确指定实例和图；复用 Mogwai 图执行回调，在本帧渲染后有界处理命令。GPU 操作全部在渲染线程执行，一次结果内的附件来自同一帧。新增的原生 Python device/execute 绑定与回调版本标识用于设备访问和正确恢复原回调。
- CLI 标准输出提供带版本的 JSON，包含请求标识、状态、实例/图、帧标识、使用的布局标识与结果或结构化错误；日志走标准错误。定义稳定退出码区分成功、比较不通过和执行错误，并提供超时处理。大数组通过数据文件导出，JSON 返回路径、dtype 和 shape。
- 已从独立进程调用 CLI，验证与进程内 API 的结果一致、完整整数 ID 精度、custom decoder、按字段容差、坐标/字段/布局及超时错误。UINT 和 UNORM 位附件、BGRA sRGB、原始 bytes 与 typed NPZ 导出、背景 NaN 覆盖掩码及回调恢复均有真实 GPU 证据。无请求的预览帧没有观察 dispatch/readback；同步成本继续由 R4 跟踪。

V4 证据：[验证索引](../../build/native-schema-observer/verification.json)。575 项 Python 测试通过；2 组新 GPU/CLI 验收及 4 组现有 D3D12 GPU 回归通过，独立代码审查问题已修复。保留旧 UE 路径不变，V5 UI 与 R4 异步读回不因此标记完成。

使用：[observer.py](../../scripts/customrenderpipline/observer.py)、[中立描述式示例](../../scripts/customrenderpipline/native_described_passes.py)。证据：[原生复用审计验证](../../build/native-falcor-audit/verification.json)。

## 3. 原始纹理/缓冲读回与 Depth/Stencil

- [x] **R1｜普通读回复用原生。** observer 已改用 `Texture.to_numpy(mip_level, array_slice)` / `Buffer.to_numpy()`；重复的普通 C++ 读回实现已经移除。
- [x] **R2｜精确 D32S8 平面。** 保留 `customRenderPiplineReadDepthStencil()` 补充，分别读取 `D32FloatS8Uint` 的 Depth/Stencil 原始平面；这是当前分支的特殊处理，不是所有深度格式都已完整覆盖的承诺。
- [x] **R3｜同步热路径精简。** 保留按需观察；旧 Scene identity/事务准备/整帧 History 等待已退出主线，新 Asset/History 执行只有 GPU copy，不做 CPU 读回。历史优化数值不代表当前帧率。
- [ ] **R4｜默认异步和当前整合回归通过，最终收尾未完成。** Schema/raw/service/CLI/UI 默认异步、共享池 8 tasks / 64 MiB、D3D12 exact D32S8、512-task/满额池已有证据。本轮修复 Vulkan mixed-transfer 首份 Buffer snapshot，合法 workload 替代旧测试 gate；当前还原构建严格 55 native / 11 GPU suites / 372 CPU 通过。Depth pending-drop/last-owner、headless 性能及指定原生等待 API 实测也已完成；仍需真实 UI 与最终签核；见[当前进度](customrenderpipline-native-completion-status-20260914-zh.md)。
- [x] **R5｜本轮有限格式/后端矩阵完成。** 两后端颜色、BC1/3/4/5 tail、buffer、Cube/CubeArray 全 face/mip 的 sync/async bytes；MSAA raw 和 Vulkan exact D32S8 plane 明确拒绝后恢复。[精确范围](customrenderpipline-resource-matrix-20260914-zh.md)。不承诺其他 Depth/Stencil 格式或 Vulkan exact plane 支持；R4 新发现不因此关闭。

**R4 修复与剩余验收**：
- [x] ParallelReduction 按 FLOAT/SINT/UINT 使用匹配 intermediate，覆盖同实例类型切换和两块 ping-pong 分别扩容。
- [x] 默认 Vulkan Workgroup SPIR-V 通过真实 runtime 验证。显式 direct 实验路径的 bundled Slang 缺陷仍是已知限制，不宣称已修。
- [x] ReadTextureTask / ReadBufferTask pending 丢弃的 fence 按 Device 延迟释放；两后端 pending marker、非等待析构、源释放快照和最后 Device owner 均已过。
- [x] Vulkan Buffer CopyDest→CopySource 局部扩大 destination stage/access scope；纯 Vulkan RED/单变量 GREEN 和修复后实际 API trace 已保留。无新增 CPU wait/submit。
- [x] NativeAsyncReadback / ErrorMeasure 非法未来 host timeline 测试换成合法有界 workload；保留 pending 和四样本/队列满输出断言，实际 Logger 严格检查通过。
- [x] DepthStencil task 真实 pending-drop / completed-task 最后 Device owner 直接加验，两平面原始值及 D3D12InfoQueue 严格检查通过。最后 Device teardown 允许正常 drain，不外推 pending final-owner 非阻塞。
- [x] 同图 headless 帧时间、独立 GPU 事件和进程内存短区间测量；原始数组、真实 Logger、源码/二进制/生成物哈希均保留。
- [x] 指定原生 fence/heap API 直接计时，区分早返回/后端调用，归因到 Profiler/frame/同步读回；正式源码/DLL 已移除探针并完整重验。不冒充纯线程挂起或全部驱动停顿。
- [ ] 真鼠标 UI、同实例 ErrorMeasure 选项/CSV session 和最终完成签核。

使用与证据：[读回实现](../../scripts/customrenderpipline/observer.py)、[已有读回性能记录](ue-legacy-frame-readback-performance.md)、[原生复用审计验证](../../build/native-falcor-audit/verification.json)。记录中的 18.47 → 16.49 ms 是既有同视图 headless 测量，本轮未重测，也不能视为当前窗口帧率。

## 4. 结构化缓冲、Cube、mip、数组层

- [x] **S1｜明确原生边界。** Falcor 原本已有结构化缓冲、Cube、mip 和数组纹理 GPU API；我们补的是图层反射/校验和已发现的子资源缺陷。
- [x] **S2｜结构化缓冲接入 RenderGraph。** 已补齐 structured 类型、stride/count、连接/外部输入验证和实际资源分配；已通过结构化缓冲 GPU 验收。
- [x] **S3｜已发现的子资源问题。** 已修复 Cube 数量与六面物理层计数、子资源索引、view/FBO 范围、选定面/mip 状态与 barrier 等；有 Cube、2DArray、面/mip 采样和读回证据。
- [x] **S4｜本轮有界 Vulkan 资源矩阵完成。** Cube/CubeArray SRV 全 face/mip/rebased view、raw bytes、2D-array UAV/RTV 及邻居、D32Float DSV→SRV 已验证且严格日志无 GFX Error。[矩阵](customrenderpipline-resource-matrix-20260914-zh.md)。不是全后端认证；此前 R4 mixed-transfer/非法 gate 问题已修复并纳入当前严格回归，升级 Falcor/gfx 或换显卡需重跑。
  - **明确不支持与未验收分开：** 当前 Vulkan Cube RTV/DSV/UAV、`Texture.generateMips()` 的 Cube 路径有显式拒绝。是否扩展由目标后端需求决定。

实现：[结构化缓冲测试](../../Source/Tools/FalcorTest/Tests/Core/RenderGraphStructuredBuffers.cpp)、[Cube 子资源测试](../../Source/Tools/FalcorTest/Tests/Core/CustomRenderPiplineCubeSubresources.cpp)。证据：[复用审计验证](../../build/native-falcor-audit/verification.json)、[历史 Cube 原生测试结果](../../build/cube-native-green.xml)。历史结果保留原 UE 名称，不改写旧证据。

## 相关事项

- [x] **A1｜通用框架与旧运行 ABI 解耦。** 下面按已退役运行入口、可选效果适配和剩余源码清理分别记录，不等同所有 UE 效果已移植。
  - [x] **A1.1：** Compute/Fullscreen/Mesh 的中立配置、Shader 与资源绑定已抽出；这些新默认入口不依赖旧 `Config/SchemaPipeline/sceneDefinition/UESurface`。Asset/History 另见 P3，不含整包删除。
  - [x] **A1.2：** 原生 MeshDraw 使用 Scene draw lists，不依赖旧材质名表/固定 View/深度；旧 compatibility factory 已不注册。
  - [x] **A1.3a：旧调用者退役。** SchemaPipeline/旧生成器/Adapter 运行脚本、旧 Config/事务 tests 已归档退出主线；复审发现的天空/阴影旧图 wrapper 同样退役，独立数学和来源数据保留。
  - [ ] **A1.3b｜按需而非必做：UE 效果适配。** 有实际需求时将保留算法接入新的资源/Shader/codec 接口；不恢复旧 UE ABI，也不要求把全部旧研究效果移植回来。
  - [x] **A1.4：旧构建/注册已退出。** 插件只注册七个 native 节点；14 个旧 runtime cpp 不再编入插件，4 个旧合同 C++ test 文件退出默认 FalcorTest。保留独立 Sun/Sky 数学。这里不是“可选开关已实现”。

- [x] **P1｜原生 Pass 组合与旧描述层接入。** 原生 RenderGraph 承担连接、调度和资源分配；旧描述层接入 Blit/ErrorMeasure 有 GPU 证据。纯原生图直接使用 `createPass/addPass/addEdge/markOutput`。此完成项**不包含 P2 的中立描述层**。
- [x] **P2｜中立描述式 Pass。** `pipeline.make_graph()` 直接从 JSON/dict 创建普通 RenderGraph，复用 Pass 描述并按属性来源解析文件；Compute/Fullscreen 不再需要旧 Config 或 UE Shader 前缀。交付示例已贯通新 Schema GBuffer + Mesh → Compute → Fullscreen → Blit → 观察，不提供旧 UE Schema/Scene 占位文件。[用法](customrenderpipline-native-pass-migration-zh.md)。
- [x] **P3｜Asset/History 已迁移。** Asset 普通文件资源、构造时加载、显式更新重载；History 图内 key 配对、上次 writer 资源、reset/resize/setScene/rebind 失效，无旧 Config/快照/整帧事务。[用法](customrenderpipline-native-resources-history-zh.md)。
- [x] **M1｜Mesh 绘制筛选。** 已集成 `Scene::RasterDrawList`；原生 `GBufferRaster` 与自定义 GBuffer 共用 `instanceIDs`。其他 Pass 需主动调用该接口，不能表述成所有 Pass 已自动支持。[说明及限制](customrenderpipline-native-mesh-selection-zh.md)。
- [x] **M2｜通用 MeshDraw 接入原生 Scene。** `instanceIDs`、原生 Material 双面筛选与 `Scene::rasterize()` 共用 M1；原有资源/附件/state 保留，自定义矩阵用显式 binding，默认 clear=1/LessEqual。Scene/material 变化、显式 VP/depth/viewport、clear前错误拒绝、indexed/nonindexed 均已验证。Shader 需原生 `gScene` ABI，不需旧 `UEMeshPass`。
- [ ] **D1｜暂缓：整图回滚。** 用户明确暂时不需要。旧事务入口已退役并归档；新原生入口和 History 不保证整帧失败回滚。[备忘](customrenderpipline-memo-zh.md)。
- [x] **L1｜旧 Adapter 测试已退役。** 过期 primitive_flags 不再是待修复兼容项；不恢复旧 ABI 来刷绿。新 GBuffer/Schema 保留独立验收。
- [x] **L2｜测试分组与删项对账。** 旧 ABI tests 与独立数学/新 native tests 分离；精确路径、原字节和 test IDs 在本轮证据目录。新原生 once/structured/Cube/observer/dispatch/relative-size/write-mask 覆盖核心能力，未重跑每个旧组合。
- [x] **C2｜源码瘦身完成。** 82 个旧源码路径、3 个旧 Shader 包装、3 个孤立 LightingConfig/旧合同测试共 88 项已精确归档移出主线，18 个算法原文哈希保持不变；24 个残留发布 Shader 副本也在归档后删除。compatibility/sealing policy hooks 已移除，保留 getTopology、Scene draw lists、资源/view/barrier 修复。相对 include 回归与 native MeshRasterizers 修复通过；最终有界源码审查无 Critical/Important，Release 构建、325 Python tests、10 GPU 脚本及 23 原生检查通过。证据 `build/native-framework-completion/c2-stage-verification.json`。这不表示 V5/R4/更广矩阵已完成。
- [x] **Q1｜本轮更广组合覆盖完成。** 三跳相对尺寸、固定源、inputOutput/Mesh 继承、raw/structured alias 冲突 clear 前拒绝/恢复、group/max_size、once 替换与真热重载、GF 独立 CPU 和 raw bytes 对照均通过。[范围与证据](customrenderpipline-resource-matrix-20260914-zh.md)。不是旧 UE 图恢复或无限组合穷举。
- [x] **C1｜2026-09-13 已按用户要求清理。** 删除两个不编译/注册的 CSM 原型（4 个 C++/header 文件）和两套失效 `Generated/` 旧 GBuffer 代次（4 个文件）。先逐文件校验备份，再删除；[原字节归档](../../build/retired-files-cleanup-20260913/removed-files.zip)、[路径/哈希清单](../../build/retired-files-cleanup-20260913/deleted-files.json)。当前 Shadows Shader/Setup、Schema 生成器、Config、Adapter 未删除，旧 metadata 未改写。
- [ ] **T1｜待讨论：光栅半透明 Pass。** 原生物理透射/Alpha Test 已有；透明绘制排序和 Alpha 混合 Pass 未在本次 Mesh 筛选中实现。此前只是能力讨论，尚未列为当前必做实现。
- [ ] **F1｜独立未完成任务：FY1 / 最终 RDC 画面对齐。** 不用框架测试通过替代最终图像验收；具体效果继续在原研究记录中跟踪。
  - **2026-09-14 当前执行 targetmap/2.rdc**：E2962最终、E2793中间，排除后处理。A0已完成。**F1-A1原生GBuffer实测进行中**：source Mesh+Schema已绘制；unscaled投影修正后coverage1,258,627像素/stencil精确。通用sampler包装新增max_anisotropy，4nativeCPU+3执行器12GPU对照/36拒绝验证通过；新默认baseline7raw与旧基线逐字节同。Basic区域B/C、Floor区域A/specular/model已匹配。两个独立源BC1/10mips导出均正常退出、收尾remaining=0，全部mip字节与离线RDC oracle一致；sourceDDS/aniso1→8单变量及新进程复验完成，7raw重复完全相同。Floor仍有rough1069/metal2993、C1350分量不同（最大3/11/2code），不能视作全≤1LSB。尚待材质坐标重建/插值调查、mesh normal/depth精度、背景Editor输出；当前199文件检查点platform-verification.json。之后A2阴影/方向光 → A3 GI/AO/SSR历史 → A4天空云雾 → A5 reset最终验收，尚无整图shading一致结论，见[当前进度](customrenderpipline-targetmap-shading-zh.md)。
  - **2026-09-15 F1-A1 增量**：源 double 相机导出与 float UE_PI/屏幕位置重建已独立验证，16/16矩阵位一致；PS-only Floor rough/metal/C237/748/294。源相对VS候选162/566/228且reset7raw一致，但Basic normal/depth轻微回退，仍隔离未合入。不能勾掉A1；下一步查源mesh/vertex/raster精度，见coordinate诊断报告。
  - **2026-09-15 F1-A1 顶点增量**：raw normal/SNORM8恢复令Basic A3074→1443→13（剩13像素各1code），新进程7raw重复；源axis累积候选Floor124/463/177、depthmax减半但Basic误差仍在，均未合入。实际E1437/nativeVS和IB/normal oracle已取，下一步真正E770 depthwriter/实际native顶点精度。Formal118CPU PASS；新vertex检查点保留旧platform199/coordinate381，不勾掉A1。
  - **后续舍入边界诊断（未合入）**：局部源origin rounding令两个Sphere depth热点逐位相同，Basic max降2.3469e-7/reset7raw一致；但剩1像素大法线跳变及source-order已有广度回退，不能只看normal2分量或max下降。下一步源cm origins独立输入+instance映射，不反推float32米矩阵；真E770prepass等仍待核对。当前translation756检查点；A1仍未完成。
  - FY1 builder 引用的 `Depth.slang/Base.slang/Deferred.slang` 当前缺失；存在捕获 view/postVS/projection 输入与 `capture_inputs=False` 自报不一致。已有 17-case lighting 算术通过不等于整图通过。
  - 旧 targetmap 运行入口已退役；CSM/天空/SkyLight/曝光算法和来源仍保留，不等于在新框架完整重现。最终图像验收仍需新的端到端证据。

## 下一步讨论位置

**G4/G5、V4、P2/M2/P3 已完成；旧入口退出主线。** 用户已授权继续完成 C2、V5、R4 和 Q1/R5/S4，整体目标进行中，不再停留在方向讨论。D1 暂缓，F1 独立。

## 更新记录

- 2026-09-14（资源与退役轮）：Asset/History 脱离 Config；旧 runtime 与 ABI tests 归档退役；保留新 GBuffer/Schema/V4。完成 CPU 删项对账与 native GPU 回归；详细命令、结果和限制见 `build/resource-history-migration/verification.json`。

- 2026-09-14：完成用户授权的 P2/M2，A1.1/A1.2 按明确范围关闭，新增 P3 标记未迁移的 Asset/History。620 CPU tests、9 组串行 debug-layer GPU、Release Mogwai 构建通过；独立规格/质量审查关闭，新增缺失 gScene 的 clear 前拒绝回归。没有删除仍使用的旧模块，没有提交或合并。[验证索引](../../build/native-pass-migration/verification.json)。

- 2026-09-13（后续授权清理）：删除 C1 的 8 个停用文件，逐文件备份并校验。项目自带 CMake 3.24.1 的 Release Mogwai 构建通过，删除后 605 项 Python 测试通过；未做新的 GPU/桌面验收，未清理仍有调用者的模块。[本轮验证记录](../../build/retired-files-cleanup-20260913/verification.json)。

- 2026-09-13：完成全部修改判断，核对 29 个 tracked 修改与所有新增 module families；另列原 checkout 的研究证据。新增 P2/M2/L2/C1 和 A1 子项，纠正 V5/旧 GPU/FY1 完成度。本轮 605 项 CPU tests 通过，未改渲染代码、未删除模块、未运行 GPU/桌面。

- 2026-09-12：用户授权后完成 V4：Schema GPU 观察、按字段比较、Python/CLI、本地帧后命令服务、原始/typed 数据导出及文档。575 项 Python 测试和 6 组 D3D12 GPU 验收/回归通过；仅新增原生脚本薄绑定与回调版本标识，未改旧 UE 算法，未提交或合并。

- 2026-09-12：用户补充 V4 必须能够通过 CMD 等方式供外部程序访问。已将 CLI、机器可读 JSON、运行中实例访问、明确帧边界及独立进程验收纳入待实现范围；本次仅更新要求，未实现命令服务或修改渲染代码。

- 2026-09-12：用户授权后完成 G4/G5。独立生成/校验模块、原生示例与文档落地；495 项 Python 测试及 4 组 D3D12 GPU 脚本通过。独立审查问题已修复并关闭，验证/备份记录在 build/native-gbuffer-schema。未改 C++，未提交/合并，未移除旧 UE 路径。

- 2026-09-12：按用户澄清记录“适配 UE 材质本身，不依赖之前自研的旧 UE 材质和深度约定”；新增 A1，明确后续尽量淘汰重复旧代码，不能把兼容层做成旧实现的长期包装。未删除代码。

- 2026-09-12：讨论 G4/G5 的实施时机。核对旧 generate_schema.py 已有位段重叠、位宽和 codec 合同检查，但绑定 UE 模型/深度约定；推荐先做通用存储布局生成与校验，保留手写特殊 codec。仅调整下一优先项建议，没有标记实现完成。

- 2026-09-12：建立四项能力清单；核对原生/扩展代码、3 份既有验证索引及 observer/structured/Cube 日志。普通 observer 的 Python 与 C++ 文件哈希匹配原审计记录。未重新运行 GPU 验收，未修改渲染源码。

2026-09-15 source-origin final root check: new934/prior756file checkpoints freshPASS;22diagnostic/118targetmapCPU PASS. Independent source-origin-runtime-review complete. FinalGPU/build/replayprocess inventory0. Frozen source-origins-verification.json and final-root-check index retained. FullgoalACTIVE; this turn made real GPU/differential/reset progress, not blocked/wait. No promotion/commit/merge/reset. Next A1 exactdepth/material/background andformalinputcontracts, thenA2-A5.
