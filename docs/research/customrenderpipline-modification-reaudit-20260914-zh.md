# 所有修改重新判断：2026-09-14 资源迁移后

实现树：`E:/Project/falcor/Falcor-m0`。本报告替代旧审计的**当前状态判断**，不改写旧 CSV、捕获或历史测试结果。

## 结论

**框架需要的通用能力还在，Asset/History 已解耦，旧 UE 运行框架已退役。** 不表示每个旧 UE 效果已移植，也不表示目录里再没有旧源码。

| 模块/修改 | 当前判断 | 后续 |
| --- | --- | --- |
| 原生 GBuffer、原生材质接入 | 保留，现用 | 任意 UE 材质行为仍需独立实现/验证 |
| 新 Schema/codec 生成与布局校验 | 保留，现用；不依赖旧 generate_schema | 特殊算法自己提供参考测试 |
| JSON/dict 图装配、Compute/Fullscreen | 保留，中立原生入口 | 不重建另一套调度/事务系统 |
| MeshDraw + Scene RasterDrawList | 保留，共用原生绘制选择 | 混合索引/蒙皮等更多组合按需验证 |
| Asset | 已迁移；普通资源声明、构造加载、私有源恢复 | 当前支持资源形状见用法；不承诺零 copy |
| History | 已迁移；图内 key 配对、双缓冲、reset | 是上次 writer，不是上次成功整帧；当前只支持二维纹理 |
| V4 输出/Schema 观察、数值容差、CMD | 保留，现用 | 按需读回仍同步，R4 |
| V5 原生 UI/预览 | 代码保留，尚未收尾 | 路径编码、dialog 异常、真实鼠标验收，V5 |
| Cube/mip/array/view/barrier 修复 | 保留，新 Asset/观察/执行器均使用 | Vulkan 有未测及明确拒绝路径，R5/S4 |
| structured buffer 图反射/分配 | 保留，新原生执行器仍依赖 | 更多组合见 Q1 |
| SceneBuilder 不预变换静态 mesh | 保留，原生对象变换语义有价值 | 旧 identity 诊断脚本已退役，不删核心能力 |
| Mogwai 帧后回调/revision、device/execute/topology 绑定 | 保留，V4 和 History 在用 | 不因为旧封存图消失而连带删除 |
| RenderContext draw 错误检查 | 保留，Mesh 在 clear 前预检 PSO 仍用 | 不是任意运行错误可恢复的保证 |
| 旧 Config/SchemaPipeline/快照/事务/Adapter 运行层 | Python 已归档移除；C++ 停止编译/注册 | 不维护旧 ABI，不为旧 tests 恢复 runtime |
| 旧 SceneIdentity/FrameReadback/封存输入合同 tests | 退出默认 FalcorTest | BC4 原始 mip 读回已抽成独立 native test；不能丢通用验证 |
| 未编译旧 C++/header/Shader ABI | 保留为研究源，不是受支持 API | 可按 C2 继续物理清理；保留原字节来源 |
| Mesh/PassDescription 无注册 compatibility 抽象 | 残余代码，无旧 factory | C2，可按 hunk 清理，不算当前必需依赖 |
| RenderGraph validator/sealing policy hooks | 主线无旧 validator 安装者，当前多为空 hook | C2；与现用 getTopology/structured external input 区分 |
| UE 数学、源 Shader、来源/参考数据 | 保留，不是过时无用代码 | 按需接入新通用 Pass，不要求全面移植 |
| targetmap/FY1/旧 RDC 运行调用者 | 退役；提取工具/数学/原始证据保留或归档 | 最终效果对齐 F1 未完成，不能拿框架测试替代 |

## 精确文件覆盖

[本轮逐文件台账](customrenderpipline-modification-reaudit-20260914.csv) 覆盖当前 Git tracked diff + untracked 文件，并补列已移除路径及原工作树的研究文件。每项记录状态、模块、判断、TODO 和当前/归档 SHA-256；生成规则和计数见 `build/resource-history-migration/reaudit-coverage.json`。生成台账自身不参与自身 SHA-256。

核心 29 个 tracked 修改逐 hunk 复审见 `build/resource-history-migration/core-reaudit.md`。该只读复审时 29/29 与旧 CSV 一致；随后本轮仅继续修改 `Source/Tools/FalcorTest/CMakeLists.txt` 以隔离旧 tests、保留独立 BC4。最终 hash 以本轮台账为准，不继续声称最终 29/29 未变。

原 `E:/Project/falcor/Falcor` 工作树的研究/文档文件另列，**不把它的离线证据当作实现树的运行完成度**。

## 实际退役边界

- 主批 125 个 Python 文件已按 `python-retirement.json` 校验原字节后移除。
- 复审额外发现的 runtime caller 和旧 ABI-only tests 见 `supplemental-retirement.json`；还从混合模块中抽掉旧图 wrapper，保留独立 settings、Cube 投影、SH/光照数学等。
- 原先新抽出的 `sky_light_lighting_fixture.py` 仍拼旧 ABI，已再次退役；不把“改名/拆文件”当成真正解耦。
- `observer_views_smoke.py` 不是删除对象：它的旧动态脚本依赖已改接原生图，保留 24 个 face/mip 原始读回与 atlas 验证。
- 插件不再编译 14 个旧 runtime cpp，只注册 7 个 native nodes；旧 UE 注册/bind/seal/prepare/renderHistoryFrame 不再导出。
- 默认 FalcorTest 不再编译 4 个旧合同 test 文件及其内部实现。纯 BC4 tail-mip 字节测试抽至 `NativeTextureReadback.cpp`；Sun/Sky 独立 C++ 数学测试保留并重新编译执行。
- **未物理删除旧 C++ 包、未提交/合并、未恢复旧 runtime、未做整图回滚。**

## 通用旧测试的替代与未覆盖项

| 旧覆盖 | 新验证 |
| --- | --- |
| asset source/mips/cube/raw | `native_asset_migration_smoke.py`；已知字节、损坏恢复、显式 reload |
| history/resources/publication | `native_history_migration_smoke.py`；配对、reset/resize/scene/rebind、图/key 隔离、writer 后失败不回滚 |
| described graph/shader execution | `native_pass_migration_smoke.py`、`native_described_passes.py` |
| Mesh selection/view/depth | `native_mesh_draw_migration_smoke.py` indexed/nonindexed、`native_mesh_selection_smoke.py` |
| immutable compute once | `native_once_cache_migration_smoke.py`；跨帧 cache 恢复、resize 重算、非法声明拒绝 |
| structured buffers、Cube face/mip、mapped groups、relative size、fullscreen mask | `native_resource_shapes_migration_smoke.py` |
| Cube 原始观察/atlas | `observer_views_smoke.py` 改用原生 fixture |
| 新 Schema/V4/CLI | `native_gbuffer_schema_smoke.py`、`native_schema_observer_smoke.py` UINT/UNORM |
| Core Cube/structured/draw lists/BC4 | 对应保留的 FalcorTest suites |

**没有声称逐条复刻所有旧测试。** Q1 仍含多跳/固定/inputOutput/Mesh 相对尺寸组合、部分 raw alias-writer 拒绝、group max_size 越界后重建、once shader/uniform 替换/default every-frame、GF 专用结果对照等。旧事务回滚、Scene identity、旧封存策略与旧材质 ABI 测试是主动退役，不是待恢复的能力。

完整 Python discovery 从原 620 项下降，是旧 ABI/事务/图 wrapper tests 退出，不是跳过失败用例。精确旧 ID、保留 ID、新增/改名 ID、总数均记录于 `python-test-accounting.json`；不可用旧 620 作为本轮保留测试数。

## 真正仍需讨论/实施的 TODO

1. **V5**：UI 错误展示/路径编码、真实交互及最终验收。
2. **C2**：物理清理未编译旧源码及无消费者策略钩子；本轮运行解耦已完成。
3. **R4**：按需 observer/schema/DepthStencil 读回异步化；旧事务等待不再是当前热路径。
4. **R5/S4/Q1**：特殊格式/后端与更广组合覆盖；按目标平台需求排优先级。
5. **A1.3b/T1**：按需 UE 效果适配、透明 Pass，不自动列为全部必做。
6. **D1**：整图回滚继续暂缓。**F1**：最终 RDC/完整效果对齐独立未完成。

## 证据与运行限制

本轮最终验收：`build/resource-history-migration/verification.json`；运行日志、鲜活 result.json、archive/hash 与重放命令一并索引。

只做 headless D3D12/debug-layer GPU 和 CPU 验证，没有操作桌面或测量当前交互帧率。构建沿用项目 CMake 3.24.1；Agility SDK warning 为既有环境提示。未验证其他 GPU/后端，不以 exit 0、旧日志或中间结果代替 PASS marker + 新结果文件校验。
