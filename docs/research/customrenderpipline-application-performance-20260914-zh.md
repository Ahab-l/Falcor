# customrenderpipline 应用开销实测

2026-09-14；实现树 `E:/Project/falcor/Falcor-m0`。本轮只增加测量脚本、改进证据记录和更新文档，没有新增生产代码修改。

## 范围与方法

- 当前 Release Mogwai、D3D12 / RTX 4090，`--headless`，不启 debug layer。严格 debug-layer 正确性回归另有记录。
- 1280×800、原生 Schema GBuffer 的两个材质 quad；同一进程、同一图、暂停时钟、热缓存。不代表游戏场景、桌面呈现帧率或输入响应认证。
- 7 个模式各预热 60 帧、测量 300 帧，正序/倒序/正序共 3 轮。查询每 30 帧一次；每个查询都核对同一覆盖像素的全部字段。空闲计数、需求次数、池最终清空均有断言。
- 计时区间为一次 `m.renderFrame()` 的 wall time，包含应用、Python、驱动、原生同步和调度。oracle 比较、进程内存采样在单帧计时之外；计时帧无 sleep 或截图。
- 纯图仍保留预热后的观察器、面板资源分配，但不调用观察服务。`service_only_idle` 移除面板 listener；`service_idle` 保留隐藏面板 listener；两者均保留测量 wrapper。图执行的 Python callback 开销不能全归为 mailbox 成本。

## 默认配置的帧时间

以下是每模式 900 个样本合并后的分位数，单位 ms。原始数据也分别保留每轮结果；小场景/短测量有系统噪声，不据微小差值做普遍性能承诺。

| 模式 | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| 纯图，观察回调关闭 | 0.135 | 0.355 | 0.967 |
| 服务空闲，面板 listener 移除 | 0.372 | 0.651 | 1.093 |
| 服务空闲，隐藏面板仍挂接 | 0.373 | 0.648 | 1.113 |
| 面板可见，无观察请求 | 0.399 | 0.697 | 1.279 |
| 直接异步单像素查询，每 30 帧一次 | 0.363 | 0.976 | 2.674 |
| 直接同步单像素查询，每 30 帧一次 | 0.349 | 0.956 | 2.567 |
| 面板按需预览刷新＋像素查询，每 30 帧一次 | 0.407 | 1.172 | 5.776 |

**能确认：** 三种空闲观察模式的解码 dispatch/readback/预览 dispatch 增量全部为零，但服务不是零 CPU 开销。服务-only callback 的 p50 约 0.131 ms，包含计时 wrapper/计账探针。

**不能确认“异步总是更快”：** 各 30 次直接查询中，异步 API 调用 p50 为 2.050 ms，同步为 1.883 ms。异步避免等待结果的语义已有独立 pending 测试，但资源绑定、合同校验、dispatch/submit、结果整理仍有成本；本轮没有逐项归因这些成本。这个小场景没有证明异步吞吐更快。面板需求还包含整幅预览刷新，不能和直接查询视为等量工作。

## GPU、等待与内存

- GPU 时间另开 4 个 instrumented 模式。每次调用 120 帧，原生 Capture 丢弃首样本，保留 119 条；启用原生 Profiler UI/时间戳，不与默认 wall time 混在一起。
- 稳定 GBuffer 事件时间戳区间均值约 0.0127–0.0166 ms；图执行事件约 0.0240–0.0283 ms。这些是区间而非纯 GPU busy 时间。外层 `onFrameRender` 跨 CPU 录制/submit，可包含 GPU 队列空档；不能据其差值计算额外 Shader 工作量。
- Capture 使用前一帧 GPU 数据，首帧固定 lane；稀疏按需事件可能缺失或保留旧值。不得把 records 与本帧 wall time 机械对应，也不得把 stale lane 累加成实际重复任务。
- 源码审查确认：`Profiler::endFrame()` 在 `enabled=False` 但 `paused=False` 时仍会等待先前 fence；`Device::endFrame()` 还有在途帧与 transient heap 同步。这些路径与 git HEAD 一致，不是本框架新增的同步。额外的 `paused=True` 对照组不是默认产品配置。
- 本页未插桩数据本身不包含 wait 时长，`wall−GPU` 也不是 CPU 等待时间。后续已用临时原生探针直接测量指定 fence/heap API 区间并还原，详见 [等待 API 实测](customrenderpipline-native-wait-measurement-20260914-zh.md)。它仍不等于纯线程挂起或全部驱动停顿。
- 默认 21 个阶段中，进程 Working Set 为 **905.07–909.13 MiB**，Private Usage 为 **1964.28–1972.73 MiB**。这是整个已预热进程，不是 GPU VRAM、纯观察器占用或长期无泄漏证明；纯图也保留预热分配，因此不能相减估算观察器初始内存。
- 本次单像素查询的池记账峰值为 1 task / 104 bytes，最后归零。8 tasks / 64 MiB 是共享 staging 账本上限，不是整个进程的内存上限。

## 证据与重放

当前结果：`E:/Project/falcor/Falcor-m0/build/native-framework-completion/application-perf-2932i3td/verification.json`。

其中包括 `result.json` 原始逐帧数据、`phase-progress.json`、stdout、实际 Mogwai Logger 副本、源码/二进制/生成物 SHA256。进程退出码为 0，结果为 `measured`；不是完整目标 `passed`。未发现所检查的原生错误；非 error Shader warnings 保留，未启 debug layer 的性能跑不能单独作为 validation-clean 证明。

初版 `application-perf-riholqur` 保留：其 service-idle 含隐藏面板，panel latency 还包含测试 oracle；不再用该版 panel latency 作为当前结论。审查后已修计时止点并新增无面板 listener 对照，而不是重跑挑快的数据。

```powershell
Set-Location E:\Project\falcor\Falcor-m0
python build/native-framework-completion/run-native-framework-performance.py
```

真实鼠标、文件选择、可见窗口响应和同实例 ErrorMeasure UI 仍需单独验收。没有用 native callback 调用或 headless 内部绘制冒充鼠标证据。
