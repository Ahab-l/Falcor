# customrenderpipline：Q1 / R5 / S4 有界组合验证

实现树：`E:/Project/falcor/Falcor-m0`。本轮新增回归测试，没有重新引入旧 UE ABI、Config、SchemaPipeline 或整图事务，也没有为了刷绿修改渲染算法。

## 结果和范围

本机 RTX 4090、Release、debug layer 下，本页 **13 项原生检查**（D3D12 6 项，Vulkan 7 项）、**5 组 GPU 脚本**已在当前还原构建重新通过，连同当前 **372 项保留 CPU 测试**；初次矩阵是 367 项 CPU。这关闭了本轮列出的 Q1/R5/S4 有限组合缺口，**不是所有显卡、格式、平台或整个框架的 Vulkan 认证**。真实 UI 仍未验收；headless 性能与指定等待 API 区间另有实测。

| 类别 | 实际验证 | 结论 / 不应扩大声称 |
| --- | --- | --- |
| 相对尺寸 | 三跳资源相对尺寸，逐级向上取整；viewport 97×61 → 113×79；固定 53×37 源另走同样链 | 最终 allocation 尺寸和 GPU 写入的尺寸数据精确匹配 |
| inputOutput / Mesh | inputOutput 继承末级尺寸并修改同一资源；Mesh `load` 继承半尺寸附件，固定 Mesh 保持 19×13 | Mesh 有真实覆盖像素，load 背景保持前 Pass 数据；不添加第二套 Mesh 相对尺寸语法 |
| buffer alias | raw / structured 各测试只读双绑定、SRV/UAV 冲突、双 writer 冲突 | 只读结果精确；冲突在 clear 前拒绝，sentinel 原样保留；改成只读后恢复 |
| dispatch / loader | 非法轴、0 / 65536 groups、uint32 rounding；max_size；同一目标有两个 producer | 错误有明确原因；max_size 拒绝前不清输出；有效 group 恢复精确 24 次写入；loader 去除冲突后恢复 |
| once / 属性替换 | uniform、shader.file、shader.compute 单变量替换；不写 execution 时默认每帧；resize 后重算 | 同时检查 dispatch count、最终像素和下游污染后的缓存恢复 |
| 真正 Shader 热重载 | 同一 Pass / 同一输出 allocation，文件 1 → 2 → 3；原生 ProgramManager reload；正常通知和漏 graph 通知 | 七步 dispatch count 必须为 `1,1,1,2,2,3,3`，每步 64 个像素精确；不是用 updatePass 冒充热重载 |
| 保留 GF 算法 | 真实 `PreintegratedGF.slang`，once / every_frame 各 5 帧含 resize | RG16Unorm 的 8192 个通道 code 与独立 CPU 精确相同；两种执行方式的 RG16Unorm / RG32Float bytes 完全相同；量化前 CPU 浮点 atol=2e-6 |
| 颜色纹理 | R8Unorm、RGBA8Unorm、R32Uint、RG16Float、RGBA32Uint；13×7、1 / 3 层、4 mip；两后端 | 同步 / 异步 / 重复收集、tail 覆写前快照与全部邻居 bytes 精确；浮点格式此处验证存储，不验证所有数学运算 |
| BC tail | BC1 / BC3 / BC4 / BC5；8×8 → 4×4 → 2×2 → 1×1，2 层；两后端 | 独立 block 大小 oracle，原始 bytes 精确；不代表纹理解压或过滤算法逐像素验证 |
| buffer bytes | raw、R32Uint typed、RGBA32Uint typed、stride=12 structured；两后端 | 预算拒绝不改变状态，部分区间快照、覆写、后续有效读取精确 |
| Cube / CubeArray | 1 / 2 个 Cube，全部物理面、4 mip；全 SRV、rebased mip SRV、第二个 Cube 的完整六面视图；两后端 | 初始化 / 读回 bytes 和 GPU 面中心采样精确；不包含面内旋转、seam 和所有过滤模式 |
| MSAA 原始读回 | 两后端创建真实 4× MSAA RTV，再请求 sync / async raw readback | 明确拒绝，状态不变，单采样读回恢复；**没有新增 MSAA raw 支持** |
| Vulkan Cube writable view | RTV / DSV / UAV、generateMips 与自动 mip 生成 | 当前明确拒绝；有效 Cube SRV 和 2D-array UAV / RTV 后续可用，目标及邻居 bytes 检查通过 |
| Vulkan 深度边界 | 有效 D32S8 array / mip 调用 exact plane API；随后普通 D32Float DSV → SRV 采样 | D32S8 plane API 明确要求 D3D12；D32Float 采样值 0.625 精确恢复；**不是 Vulkan D32S8 plane 支持** |

D3D12 exact D32S8 及 Cube barrier 继续使用独立 R4 测试（24 views / 48 tasks），不重复计成本轮新增功能。既有 `CustomRenderPiplineCubeSampleMipView` 已明确检查 base mip=2，不以测试名称推断覆盖。

## 过程中发现并修正的测试问题

- Falcor `to_numpy()` 会去掉长度为 1 的维度。1×8 sentinel 对比显式 reshape 后仍逐值精确，不修改预期 bytes。
- Vulkan R8 1×1 tail 的 staging 恰好为 1 B，`max_bytes=1` 本来合法。预算负例改用独立能证明至少 3 B 的 mip；所有 tail、mixed-state、邻居断言保持不变。
- 原 native reload 测试只有正确像素，不能排除每帧重算。独立 spec 审查要求补七步 dispatch count，已加入并实际执行。
- FalcorTest 先导入 `falcor` 包、再加载插件，晚注册 binding 位于 `falcor.falcor_ext`；测试从实际模块读取现有计数接口，不新增生产绑定。
- 整合 runner 不接受 `Ran 0 tests ... OK` 或部分 CPU discovery。当前基线至少 367 项，0 / 366 / FAILED 负控制拒绝，367 / 368 正控制接受。

上述失败日志与修正前文件保留，没有将失败运行覆盖为成功。

## 使用与重放

```powershell
cd E:/Project/falcor/Falcor-m0
& ./tools/.packman/cmake/bin/cmake.exe --build build/windows-vs2022 --config Release --target Mogwai FalcorTest --parallel 4
python build/native-framework-completion/run-q1-r5-verification.py
python build/native-framework-completion/run-async-stage3-verification.py
```

runner 串行运行，检查退出码、PASS marker、新鲜 JSON、XML 非零精确测试数及 debug-layer 错误；最后核对源码 hash 未在验证期间变化。Native reload 的临时 Shader、像素和结果还会按 SHA-256 校验复制进本轮证据目录。

新增入口：
- `scripts/customrenderpipline/native_resource_composition_smoke.py`
- `scripts/customrenderpipline/native_once_extended_smoke.py`
- `Source/Tools/FalcorTest/Tests/Core/NativeOnceReload.cpp`
- `Source/Tools/FalcorTest/Tests/Core/NativeResourceBackendMatrix.cpp` / `.slang`

当前还原构建的严格通过索引：`build/native-framework-completion/q1-r5-final-v5wxs5u3/verification.json`，含每个进程的新 Logger 文件及 hash。原 nafuwssh 及早期 euk3ztwl / 42rh6nnt 索引保留，历史运行不代替当前二进制验收。独立审查：`build/native-framework-completion/q1-r5-spec-review.md`、`q1-r5-quality-review.md`。

**当时同时发现的 R4 问题已修复并独立重验**：旧 runner 漏查文件日志确实产生过错误结论；严格 RED 原样保留。typed reduction、默认 SPIR-V 路径、pending fence 生命周期、非法 gate 和 mixed-transfer 修复已纳入当前 `async-stage3-20260914-083244` 的 55 native / 11 GPU suites / 372 CPU 严格回归。这不扩张本表资源支持范围，显式 direct SPIR-V 仍未认证。详见[当前进度](customrenderpipline-native-completion-status-20260914-zh.md)和 [Todo](customrenderpipline-todo-zh.md)。
