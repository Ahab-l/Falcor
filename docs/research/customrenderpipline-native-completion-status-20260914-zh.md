# customrenderpipline 当前进度（2026-09-14）

实现树：`E:/Project/falcor/Falcor-m0`。没有提交、合并、恢复旧 ABI 或更改系统驱动。

**当前结论（08:39）：原三项迁移、旧源码清理、有限组合矩阵、异步整合、同图 headless 性能及指定原生等待 API 耗时测量已完成。临时探针已移除，正式 DLL 导出检查及还原后的完整严格回归通过。完整目标仍未完成：真实 V5 / ErrorMeasure UI 验收尚未通过，不能做最终完成签核。**

## 已完成的迁移和清理

| 项目 | 结果与边界 |
| --- | --- |
| 旧 UE 运行入口和 ABI-only 测试 | 已归档退出主线，插件只注册七个通用 Pass。C2 共归档移除 88 个旧源码路径和 24 个陈旧发布 Shader；18 个保留算法原文哈希不变。 |
| Asset | 普通文件资源输入，显式 reload，不需要旧 Config、快照或 SchemaPipeline。支持 raw buffer、2D/array/Cube 纹理和已有 mip。 |
| History | graph/key 隔离的上次 writer publication，支持 reset/resize/Scene/rebind 失效，不接回旧整图事务。当前仅单采样 SRV/UAV 二维纹理。 |
| GBuffer / Schema / 观察 | 新能力均保留，Schema 自动生成 codec、布局校验、V4 Python/CLI 接口不依赖旧 UE ABI。 |
| Q1/R5/S4 有限矩阵 | 多跳尺寸、inputOutput、Mesh、alias 拒绝/恢复、once 真热重载、GF，以及已列明格式/后端/子资源组合通过。不是无限组合或全 Vulkan 功能认证。 |

[Asset/History 用法](customrenderpipline-native-resources-history-zh.md) · [资源矩阵与明确边界](customrenderpipline-resource-matrix-20260914-zh.md)

## 本轮真正新增的修复

### Vulkan 首份 Buffer snapshot 全零

- 问题已用**不依赖 Falcor/GFX 的纯 Vulkan 程序**复现于 RTX 4090 / driver 616.56：Buffer 上传、Texture 上传、首次 Buffer 复制得到零。原同步 `getBlob()` 也受影响，不是仅新异步任务封装的问题。
- API trace 显示原来合法的 transfer RAW barrier；同步验证无错误。完整 RenderDoc 重放也失败，逐事件重放的额外同步会掩盖它。只扩大 stage 或 source write scope 无效；扩大 destination read scope 后得到正确字节。
- `CopyContext::bufferBarrier()` 仅对 Vulkan DeviceLocal Buffer 的 CopyDest→CopySource，复用 GFX General 扩大**目标 stage/access**（MEMORY_READ|WRITE / ALL_COMMANDS）；仍按 CopySource 跟踪。**没有新增 CPU wait、额外 submit 或 image layout 改动。** 这是一项有实测依据的驱动兼容处理，不把原规范合法的 barrier 说成应用错误。
- 正式 RED 的 Async/Sync 32B、1028B 失败已变 GREEN；65540B 与 Region 是额外覆盖。又增加第二份 snapshot、双非零 offset 和完整 sentinel 检查。两后端原生命周期/最后 Device owner 测试也通过；旧 Vulkan recovery 全零问题消失。

纯 Vulkan 可重放材料：`build/native-framework-completion/vulkan-mixed-copy-reproducer-zfpw03bu/`。实际修复 API trace：`transfer-fixed-api-dump-jp94gzzw/`。源码审查：`vulkan-transfer-visibility-review.md`。相关目录均在 `build/native-framework-completion/`。

### 合法 pending 测试和清理

- `NativeAsyncReadback`、`ErrorMeasureAsyncTests` 的未来 host timeline gate 已换成真实有界 GPU workload；保留前后 prerequisite marker 必须 pending、队列满仍更新 Difference、四份独立数值/CSV frame 等断言。
- 2M workload 曾因热态异常栈耗时越过约 18ms 窗口而正确失败；单变量 4M 校准后通过。现固定默认 4M（本机约 36ms），仍要求 GPU 时间 ≤100ms、真实 pending、无自动 retry。它只在测试中运行，不是每帧生产负载；poll_us 不冒充 API 提交耗时或首次冷异常耗时。
- 临时 barrier ENV、RenderDoc 注入代码、额外同步诊断已逐字节归档并从主线测试移除。运行时没有新增这些诊断依赖。
- 先前完成的 typed reduction、默认 GLSL→SPIR-V 路径、task-local fence deferred retirement 均纳入当前回归。显式 direct SPIR-V 实验路径仍有 bundled Slang 缺陷；不能据默认路径通过宣称 direct 已支持。

## 本次新增收尾（Depth / V5 / CLI）

- **Depth 生命周期**：真实有限 GPU workload prerequisite 在任务和源资源释放前后均 pending，之后双平面全像素恢复正确；独立 Device 仅由任务的两个 staging Buffer 持有时，再读两平面并释放最终 owner 通过。D3D12InfoQueue 无 error/corruption。不是任意机器确定性时延或全 live-object 泄漏认证。
- **原生 GpuTimer 修复**：新的严格 depth 测试暴露了时间戳 resolve 的旧状态错误。独立无 Shader/depth/task 的 Timer 用例复现 COMMON/COPY_DEST 及后续 source-copy 错误；只在 resolveQuery 前加入 CopyDest barrier，两后端 GREEN。没有新增 CPU wait/submit；合法 GPU barrier 不宣称零成本。证据 `vk-repair-timer-state-red-6h2aif7y`、`vk-repair-timer-state-green-cxh2by7l`、`vk-repair-timer-state-green-vulkan-4avijixa`。
- **V5 原生重开控件**：仅 live 验收入口增加 Reopen Inspector，callback 只排队，帧间复用服务重建；native smoke 验证同 graph callback、服务/CLI 保留及重开后三个 idle frame 无新观察 dispatch/readback。修复了新 generation 状态误配上一帧 PNG 的测试记录问题。真实鼠标验收仍未通过。
- **CLI Windows 回复占用**：最终矩阵曾在旧并发测试中失败；补完整回复后重现已准入请求读回复 errno13。真实 CreateFileW 共享锁复现相同边界；客户端只对回复读 PermissionError 按原 deadline 轮询，不重投、不改渲染 pump。37 个 transport tests 与20轮四客户端准入通过；永久回复权限拒绝现在到期返回 timeout，元数据错误仍立即返回。最初占锁者尚未确定，不冒充已识别外部进程。
- 独立只读审查无未解决 Critical/Important：`depth-timer-v5-review.md`。所有目录位于 `build/native-framework-completion/`。中间 CPU-failed `async-stage3-20260914-074652` 与正式 RED 原样保留，不改写成 GREEN。

## 最新严格验证

| 验证 | 新鲜结果 |
| --- | --- |
| 固定 Release 构建 | `native-wait-probe-lm33yqli/build-restored.log`，还原源码后四个对象重新编译，Mogwai + FalcorTest 成功 |
| R4 整合矩阵 | **55 native / 11 GPU suites / 372 CPU**，`async-stage3-20260914-083244/verification.json` |
| Q1/R5/S4 有限矩阵 | **13 native / 5 GPU suites / 372 CPU**，`q1-r5-final-v5wxs5u3/verification.json` |

每个 native/Mogwai 进程均采集新鲜原生 Logger、检查 GFX/VUID 错误，不只看 stdout/XML；当前二进制和两组有界源码哈希再次确认未变。两套中的 372 CPU 是同一测试集，不能相加成 744 个不同测试。非 error 的 shader/compiler warning 仍保留，不宣称 warning-free。

先前检查点 `depth-v5-transport-checkpoint-verification.json` 保留；当前证据另见 `build/native-framework-completion/native-wait-final-checkpoint-verification.json`。

### 本次进度核对与性能测量

- 新鲜原三项重放：`build/native-framework-completion/migration-status-wpuoqxon/verification.json`。Asset、History、旧入口退役三个 debug-layer Mogwai 脚本及 **372 Python tests** 通过；实际 Logger 已采集并检查，源码/二进制前后哈希一致。没有因测量而改动生产代码。
- 同图性能：`build/native-framework-completion/application-perf-2932i3td/verification.json`。各模式 900 帧；纯图 p50 0.135 ms，服务-only 空闲 0.372 ms，可见面板空闲 0.399 ms。空闲解码/readback/预览 dispatch 均为零，但不是零 CPU 开销。
- 每 30 帧一次单像素查询，异步 API p50 2.050 ms、同步 1.883 ms；这个轻量场景没有证明异步吞吐更快。异步的非等待语义不能被误写成所有负载均提速。
- 全进程 Working Set 905.07–909.13 MiB、Private Usage 1964.28–1972.73 MiB，不是显存或观察器单独占用。真实桌面 FPS 和长期内存仍未认证。
- [测量方法、全部数据与限制](customrenderpipline-application-performance-20260914-zh.md)。独立审查发现的 panel latency/oracle 口径问题已修复；旧测量保留，不用于当前 latency 结论。
- [新增等待 API 实测](customrenderpipline-native-wait-measurement-20260914-zh.md)：指定原生 fence/heap 调用点直接计时；默认同步组 30 次查询带来 30 次 backend wait，合计6.5682 ms，异步/面板需求没有该同步读回调用。原生 Profiler 等待仍存在；数据不是纯 OS 挂起或全部驱动停顿。探针已逐字节还原，正式 DLL 不含诊断导出。

## 仍需完成

- [x] 精确 Depth/Stencil 的 pending-drop / 最后 Device owner 直接加验。现有三项加两项新测全部通过；last-owner 是已完成任务，最终 Device teardown 允许 drain。没有因此修改 D3D12-only depth 任务生产实现。
- [ ] V5 真鼠标：预览选点、Source/Mapping、Unicode 文件选择、比较/导出、取消/错误恢复、关闭/重建面板。同实例 ErrorMeasure 选项/CSV session 也需真正 UI 验收。
- [x] 同图 headless 帧时间、独立 GPU 事件时间戳和进程内存有界测量。默认/Profiler capture 分组，空闲/需求计数和像素 oracle 通过。
- [x] 指定原生 wait/heap API 耗时直接测量、早返回/后端调用计数、临时探针还原和正式构建回归。不是源码推断，也不声称测全所有潜在驱动停顿。
- [ ] 可见窗口响应与最终真实 UI gate。8 tasks / 64 MiB 只是 staging 账本上限，不是进程总内存或 FPS 保证。
- [ ] 最终完成签核：逐项审计将真实 UI 标记为未通过，不用绿色 headless 测试代替。ErrorMeasure replacement 单测仍是直接 setScene(nullptr) 后未收集 generation 丢弃，不冒充完整 Scene A→B 场景切换。

最新 live：`build/native-schema-observer-ui/live-fzedmw7h/acceptance-status.json`。官方桌面工具再次看到锁屏背景而非 Inspector；没有发送鼠标/键盘输入，已通过 stop-file 正常退出并确认 `V5_LIVE_CLOSED`（pid100960 已退出）。已请用户解锁。callback PASS 不替代真实 UI。

已知支持范围继续按矩阵明确：Vulkan exact D32S8 planes、Cube RTV/DSV/UAV 等有显式拒绝；History 不自动扩展到 Buffer/Cube/Depth/array。D1 整图回滚按用户要求暂缓，F1 最终 RDC/FY1 对齐是独立任务。

## 重放

在实现树执行：

```powershell
& ./tools/.packman/cmake/bin/cmake.exe --build build/windows-vs2022 --config Release --target Mogwai FalcorTest --parallel 4
python build/native-framework-completion/run-async-stage3-verification.py
python build/native-framework-completion/run-q1-r5-verification.py
```

旧失败证据不改写：严格 R4 RED `async-stage3-20260914-053232`、formal transfer RED `vk-repair-mixed-formal-red-nauymq5n`、2M pending RED `vk-repair-legal-clean-NativeAsyncReadback-vulkan-5unhwlpq` 均保留。此前完整状态正文备份在 `status-before-transfer-final-20260914-072328.zip`，不再让已过时的“尚待修复”描述覆盖当前结果。
