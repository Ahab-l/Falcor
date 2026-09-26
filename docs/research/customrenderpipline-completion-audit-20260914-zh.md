# 完成性审计：仍未满足最终完成条件

实现树：`E:/Project/falcor/Falcor-m0`，2026-09-14 08:39。

用户目标保持完整：**旧源码进一步清理、V5 收尾、异步读回和更广组合验证，全部做完。** 下列通过项不能替代真实 UI gate；目前不能将目标标记完成。

| 要求 | 权威证据与覆盖 | 判断 |
| --- | --- | --- |
| 旧 UE 入口、Config/SchemaPipeline/Adapter 及 ABI-only tests 退役 | 当前退休脚本在 R4 通过；插件仅注册七个 native Pass。C2 四份清单再次核对：88 旧源码路径、24 发布 Shader 均不在主线；归档逐文件 SHA256 匹配，18 算法原文当前 hash 不变 | 本轮清理范围完成 |
| 保留 Asset/History 能力且不恢复旧事务 | 当前 R4 的 Asset/History/retirement 三个独立 Mogwai 用例与原始数值；普通文件输入、显式 reload、graph/key 隔离、writer publication、reset/resize/Scene/rebind 失效 | 完成；History 仅已声明的单采样2D资源，不扩张为任意资源 |
| 新 GBuffer、Schema、codec/布局校验、描述式 Pass/Mesh、观察/CLI 保留 | 当前 CPU372、GPU observer UINT/UNORM、panel、Mesh、Q1 composition/once/resource tests；原生图与 Scene 能力仍在，旧 UE ABI 不在依赖链 | 所列合同完成，不等于全部 UE 效果已移植 |
| V5 原生面板、Unicode/error/cancel、生命周期实现 | CPU 测试、native PythonUI 与 panel/preview callback smoke、同服务重建与三个 idle frame 的无新观察计数 | 实现及程序化集成通过 |
| V5 真鼠标最终验收 | 最新 live-fzedmw7h；官方 sky 对返回的 Mogwai window2172876 截图仍为 Windows 锁屏，零输入；pid100960 正常退出，V5_LIVE_CLOSED | **未通过**，不能以内部 PNG/callback 冒充 |
| R4 原始 Texture/Buffer/exact Depth、ready-only、队列与生命周期 | 当前 R4 55 native/11 GPU；真实有限 GPU workload 的前后 pending markers；depth双平面、last-owner、512-task、真实满额池、取消/关闭/timeout、帧/布局身份冻结 | 所列后端/资源合同通过；最终 Device teardown 可正常 drain |
| R4 观察/service/外部CLI/ErrorMeasure接入 | UINT/UNORM 独立进程CLI、真实回复共享锁回归、ErrorMeasure两后端四样本/CSV身份/队列满仍更新Difference、typed reduction跨类型与扩容 | 当前严格整合通过；同实例真实 UI 选项/CSV操作仍未验收 |
| 整体性能而非中间计数 | application-perf-2932i3td 同图默认帧时间/独立GPU capture/进程内存；native-wait-probe-lm33yqli 原生 fence/heap API直接计时、早返回与backend区分 | 有界 headless 测量完成；不是桌面 FPS、纯线程挂起、全部驱动停顿或长期无泄漏证明 |
| Q1/R5/S4 更广组合 | 当前13 native/5 GPU/372 CPU；资源矩阵逐行定义的层/mip/面、stride、alias、relative size、once热重载、GF oracle与失败恢复 | **定义的有限矩阵完成**，不以显式拒绝冒充 Vulkan exact D32S8/Cube writable 支持 |
| 最终源码/构建/实际 Logger/证据保留 | 临时探针四份源码原字节还原、四对象重编、正式 DLL 不含三个诊断导出；还原后完整严格 R4/Q1新跑，当前 hash/Logger复核；原 RED 与归档保留 | 当前非 UI 验证闭环；最终完成签核受未通过 UI gate 阻止 |

## 当前严格结果

- R4：`build/native-framework-completion/async-stage3-20260914-083244/verification.json`，55 native / 11 GPU suites / 372 CPU。
- Q1/R5/S4：`build/native-framework-completion/q1-r5-final-v5wxs5u3/verification.json`，13 native / 5 GPU suites / 372 CPU。
- 两份 CPU 是同一套，不能相加成744。非 error warnings 保留，未称 warning-free。
- 当前清理复核：`build/native-framework-completion/current-cleanup-audit-after-wait.json`。
- 原生等待探针与复原：`build/native-framework-completion/native-wait-probe-lm33yqli/verification.json`；诊断产物与正式产物分开。

## 尚需的真实交互清单

1. Source/Mapping 切换、预览像素选点及数值对应。
2. Unicode 文件选择、参考/规则输入，比较通过与不通过，decoded/raw 导出。
3. 取消、错误反馈/恢复、关闭后重开，继续复用原服务与 CLI。
4. 同实例原生 ErrorMeasure UI 选项切换、CSV session 交互。
5. 可见窗口响应核对及最终 UI 证据索引/签核。

已请用户解锁桌面。本次没有越过锁屏发送输入，也不保留后台渲染程序空转。下一步仅在可交互桌面上完成这些项；若解锁后暴露真实问题，应按失败输入修复并重验，不能预先判定它们会通过。

## 明确不混入目标的事项

- 整图回滚：用户明确暂缓，不恢复旧事务。
- 最终 RDC/FY1 图像对齐、所有旧 UE 效果移植、透明排序 Pass：独立研究或待讨论项。
- 所有后端/显卡/资源任意组合：不是本轮有界矩阵承诺；显式 direct SPIR-V 已知限制继续保留。

以上不是缩小目标来宣称完成：**V5/R4 的真实 UI gate 仍保留为未完成，该锁屏条件跨至少三个连续目标回合仍未解决；非 UI 必做项闭环后，完整目标已标为 blocked，等待用户解锁，不宣称完成。**
