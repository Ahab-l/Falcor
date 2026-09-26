# 原生 ErrorMeasurePass 异步统计

**2026-09-14 最新验收：** 旧 runner 漏查 FalcorTest 文件内 GFX 错误的历史问题已修；typed buffer、默认 SPIR-V 生成路径、任务 fence 释放及测试 gate 队列链也已处理。当前 D3D12/Vulkan 的 ErrorMeasure 原生测试与实际 Logger 检查通过。显式 direct SPIR-V 实验路径仍不受此结论覆盖；当前矩阵、保留的历史 RED 和边界见 [当前进度](customrenderpipline-native-completion-status-20260914-zh.md)。

仍使用 Falcor 原生 `ErrorMeasurePass`，不是新的比较框架。连接 `Source`、可选 `Reference` / `WorldPosition`，输出 `Output` 的方式不变。

## 变化与用法

- Difference 图像每次执行都更新；统计分成 GPU 归约、提交读回、后续执行收集三个阶段，不再等待 CPU 同步读回。
- 每个 Pass 最多保留 **4 个统计任务 / 64 字节读回 staging**。队列满时跳过这次统计，**不跳过 Difference**。该上限不包含图像、归约工作缓冲、整个程序或多个 Pass 的内存。
- 相机移动、动画、上游普通刷新不会取消所有样本；换 Scene、绑定资源/尺寸/参考、统计配置和程序重载会使旧代际失效。失效的未完成任务仍占用队列，直到 fence 完成。
- 保留最后已完成的数值，并明确显示提交帧及结果年龄；它不是当前画面的同步数值。

已有图可以直接读取：

```python
statistics = dict(graph.get_pass('Error').statistics)
print(statistics['status'], statistics['pending_samples'])
if statistics['valid']:
    print(statistics['submitted_frame'], statistics['collected_frame'])
    print(statistics['error'], statistics['avg_error'])
```

`status` 为 `no_reference`、`pending`、`ready` 或 `backpressure`。查看属性本身不执行、提交或收集 GPU 工作。

`submitted_frame` 是 **这个 Pass 的 execute 序号**，不是 Mogwai 全局帧号；`submitted_time` 是 **从 Pass 构造起的单调时钟秒数**，不是场景动画时间。结果中的尺寸、误差算法等来自提交时快照。

## CSV v2

指定原生 `MeasurementsFilePath` 即可写 CSV。只在新样本完成时写一行，不把上次值重复写成当前帧结果。

前四列仍是平均/R/G/B 误差；后续增加 `schema_version`、提交/收集身份、尺寸、代际、`error_metric`、配置及计数。`schema_version=2`，逐行的 `error_metric`（`MSE` 或 `L1`）是算法权威标识，尤其是文件打开后通过 UI 切换选项时。旧脚本若固定依赖完整列数，需要适配。

## 同时修复的原生归约问题

当前 RTX 4090 D3D12 的二维线程组中，wave leader 的 group index 实测为 `0,16,64,80,...`，并非每 32 个连续 group index 构成一个 wave。原生 `ParallelReduction.cs.slang` 的 `groupThreadIdx / 32` 会覆盖部分中间结果；原生同步归约测试同样复现失败。

修复使用唯一 group-index 共享内存槽和完整 wave 汇总，不依赖上述映射或固定 wave 宽度。Sum 使用 16 KiB、MinMax 使用 32 KiB 线程组共享内存；不增加 CPU 同步。D3D12 与 Vulkan 的原生 Sum/MinMax 多格式测试通过。验证限定于本机后端，不宣称所有 Vulkan 设备及性能都已覆盖。

## 重放与边界

在 `E:/Project/falcor/Falcor-m0` 执行：

```powershell
& ./tools/.packman/cmake/bin/cmake.exe --build build/windows-vs2022 --config Release --target Mogwai FalcorTest --parallel 4
& ./build/windows-vs2022/bin/Release/FalcorTest.exe --device-type d3d12 --enable-debug-layer --test-suite ErrorMeasureAsyncTests --xml-report build/error-measure-d3d12.xml
& ./build/windows-vs2022/bin/Release/FalcorTest.exe --device-type vulkan --enable-debug-layer --test-suite ErrorMeasureAsyncTests --xml-report build/error-measure-vulkan.xml
python build/native-framework-completion/run-async-stage3-verification.py
```

原生测试每个后端有 4 项，涵盖真实有界 GPU workload 下队列满、Difference 继续更新、普通 Scene/refresh 不饿死，以及四组选项 × 两个非整齐尺寸的数值与 resize 检验。旧样本替换测试是直接 `setScene(nullptr)` 丢弃已完成但未收集的 generation，不是 GPU pending 时完整 Scene A→B 切换的证明。

`native_error_measure_async_smoke.py` 还验证 Python 只读统计、缺少 reference、Pass 替换、CSV 和压力。它的描述式输入生成器仅支持 D3D12；Vulkan 使用上述原生测试，不绕过生成器的后端限制。

尚未声称通过：同实例真实 UI 改配置/文件会话的鼠标验收，整个应用的最终 FPS/卡顿验收。V5 真鼠标验收仍单独跟踪。
