# 原生等待 API 实测与诊断还原

2026-09-14；`E:/Project/falcor/Falcor-m0`。这是临时诊断，不是增加生产接口或改变原生同步策略。

## 怎样测

在当前生产快照的四份 `.cpp` 上临时加探针：

1. `Fence::wait()` 区分已经完成而直接返回，以及实际进入 `gfx::IDevice::waitForFences()`。
2. `Profiler::endFrame()`、`Device::endFrame()`、`CopyContext::submit(true)`、同步 Texture task 只设置异常安全的调用点标签；另保留 Other 桶。
3. 单独记录 `synchronizeAndReset()` API 区间。

单份共享 thread-local POD 计数，无探针文件写入、分配、额外 wait 或 submit。使用 `steady_clock` 包住原 backend 调用；原参数、调用次数与错误检查保留，错误格式化在计时后。Python 在单帧计时外 reset/snapshot，检查 ABI size/version 和同一原生线程 ID。

**范围限制：** 记录的是指定 API 的 wall-time 区间，不是纯线程挂起时间。检查 fence 后它仍可能在真正调用前完成，所以 backend 调用次数不是“必然阻塞次数”。不包含 `getCurrentValue`、submit/驱动内部、Map/资源释放等全部停顿；heap 指标还包含 reset。headless 不涉及 swapchain acquire/present。GPU 队列等待也不属于此主机指标。

## 默认配置，每模式 900 帧

同此前两个 quad / 1280×800 / D3D12 场景，独立诊断构建的结果如下。这里不复用此前未插桩的帧时间来计算差值。

| 模式 | Profiler 调用数 | 已完成直接返回 | 进入 backend | backend 区间合计 ms |
| --- | ---: | ---: | ---: | ---: |
| 纯图 | 900 | 836 | 64 | 28.5640 |
| 服务-only 空闲 | 900 | 834 | 66 | 34.2432 |
| 隐藏面板挂接、空闲 | 900 | 835 | 65 | 34.0734 |
| 可见面板空闲 | 900 | 833 | 67 | 35.4780 |
| 异步查询，每 30 帧一次 | 900 | 826 | 74 | 37.3045 |
| 同步查询，每 30 帧一次 | 900 | 847 | 53 | 30.1102 |
| 面板按需查询，每 30 帧一次 | 900 | 821 | 79 | 36.4663 |

- 默认同步组 **30 次查询对应 30 次 `submit(true)` backend wait**，合计 **6.5682 ms**；仅这些实际进入 backend 的样本，p50 118.85 μs、p95 750.415 μs。
- 异步查询与面板按需查询没有 `submit(true)`、Texture blocking 或 Other fence wait 调用；像素 oracle 与完成次数仍通过。但原生 Profiler 等待仍存在，不是“整个程序无等待”。
- 包括默认、paused 对照及独立 Profiler capture，共 **7380 个测量帧**：每帧一次 frame-fence 调用，全部已经完成而直接返回；每帧一次 heap API。
- 默认各组 heap API 的 p50 为 **1.6–2.4 μs**、p95 为 **3.0–4.205 μs**。不能把全部区间叫作纯 GPU 等待。
- `paused=True` 对照和启用 Capture 的 instrumented 组单独保存，不混入上表。

**结论：** 异步路径移除了显式同步读回等待；当前 Falcor 原有的 Profiler 帧同步仍可观测到。不能据这个小负载宣称异步总帧时间一定更低，也没有理由为了得到“零等待”而直接关掉原生同步。

## 还原与证据

证据目录：`E:/Project/falcor/Falcor-m0/build/native-framework-completion/native-wait-probe-lm33yqli/`。

- `source-before.zip`、四文件 before/diagnostic hashes、`diagnostic.patch`、`NativeWaitProbe.h`、`runner-as-executed.py`、`wait-fixture.py`。
- `Falcor.production-before.dll` 与 `Falcor.diagnostic.dll` 分开保留；`run/result.json`、逐帧计数和实际 Mogwai Logger 副本。
- `build-diagnostic.log` 和 `build-restored.log`。退出诊断进程后按**当前快照**逐字节恢复，不回退 git HEAD；刷新源码 mtime 后重新编译四个对象与链接正式产物。
- 对实际 DLL 查询导出表：诊断 DLL 有三个 `CrpDiagnosticWait*`，正式 DLL 全部没有。生产源码也不再包含探针引用。还原后 DLL 的构建哈希改变，因此严格矩阵需要用当前构建新跑，不能拿旧二进制哈希冒充。

独立只读审查确认探针与数值口径可接受。审查另发现复用 runner 在部分源码写入失败时的还原问题；驱动脚本已改为逐文件跟踪，测试覆盖完整应用、中途写失败、外部修改保护。本次实跑没有触发该问题且四份源码确实完全恢复。

重放（会临时构建诊断版，再还原重建，不能与其他 build/GPU/UI 任务并行）：

```powershell
Set-Location E:\Project\falcor\Falcor-m0
python build/native-framework-completion/run-native-wait-probe.py
```

此测量完成指定原生等待 API 的耗时核对；桌面可见响应和真正鼠标验收仍是独立未完成项，不以该测试替代。
