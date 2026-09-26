# 原生 Asset / History 与旧入口退役

更新：2026-09-14。实现树：`E:/Project/falcor/Falcor-m0`。

## 现在如何使用

```powershell
Set-Location E:\Project\falcor\Falcor-m0
& .\build\windows-vs2022\bin\Release\Mogwai.exe --script scripts/customrenderpipline/native_resource_history.py
```

示例不加载 Scene：**Asset 原始缓冲 → Compute 加上历史值 → HistoryWrite + 原生 Blit**。图在 `scripts/customrenderpipline/examples/native_resources/Graph.json`，算法在同目录 `Accumulate.slang`。入口仅在启动时生成一个 16-byte 示例资源；正式使用时换成自己的文件。

在 Mogwai 控制台调用 `reset_history()` 可清空累积。由于示例每次执行都累加，颜色最终超出 0–1 是预期行为，不是曝光算法。使用环境变量 `CRP_RESOURCE_EXAMPLE_TEST=1` 加 `--headless --enable-debug-layer` 会校验 1、2、3 次累积及重置后第 1 次的原始浮点值，然后退出。

## Asset：普通资源输入

```python
properties = {'assets': {
    'values': {'kind': 'raw_buffer', 'file': 'E:/assets/values.bin', 'bytes': 16},
    'image': {'kind': 'texture2D', 'file': 'E:/assets/image.dds',
              'format': 'RGBA8Unorm', 'size': [4, 4], 'mip_count': 3}
}}
asset = createPass('CustomRenderPiplineAssetPass', properties)
```

- 支持 `raw_buffer`、`texture2D`、`texture2DArray`、`textureCube`；数组额外声明 `array_size`。尺寸、格式、层数和 mip 必须与文件一致。
- JSON 图的相对文件需在节点 `file_inputs` 中列出，如 `assets.image.file`；路径相对声明该值的文件解析。直接 `createPass` 推荐绝对路径。
- **构造时加载一次**，使用原生 Texture/Buffer API；资源原件保存在 Pass 私有 GPU 分配中。执行时先校验全部目标再复制，避免下游写坏源数据。
- 执行阶段没有文件读取、重复上传、GPU 内容哈希或 CPU 等待；每帧仍有必要的 GPU copy，并非零开销。
- 修改/删除磁盘文件不会悄悄改变当前实例。显式 `graph.updatePass('Assets', new_properties)` 或重建 Pass 才重新加载；传入完整新 Properties。
- 不需要旧 Config、Scene JSON、Schema、资源快照或封存图。

## History：上次 writer 的资源，不是上次成功整帧

```python
settings = {'key': 'accumulation', 'resources': [
    {'name': 'color', 'format': 'RGBA32Float'},
    {'name': 'ids', 'format': 'RGBA32Uint', 'size': [2, 1]}
]}
g.addPass(createPass('CustomRenderPiplineHistoryReadPass', settings), 'Previous')
g.addPass(createPass('CustomRenderPiplineHistoryWritePass', settings), 'Save')
# 接入自己的算法：Previous.color -> Algorithm.previous -> Save.color，ids 同理。
g.markOutput('Save.status')  # 避免 writer 被 RenderGraph 裁剪。
customRenderPiplineBindHistory(g)  # 必须在节点、连接和输出完成后调用。
```

使用 `pipeline.make_graph()` 时，上述最后的配对绑定自动完成。原生 API 手工组图或替换 History 节点/改拓扑后，需要自己再次绑定。

- 同一个 graph/key 必须恰好一读一写，资源名称/格式/尺寸一致，读节点到写节点必须有可达的执行顺序。不同图、不同 key 不共享历史。
- 当前支持可 SRV/UAV 的单采样二维纹理；未写 `size` 跟随 framebuffer，写 `[width,height]` 则固定。Depth/Stencil、压缩格式、buffer、Cube/数组和 MSAA History 不在当前支持范围。
- 首次、reset、resize、setScene 或重新绑定后失效；reader 给零值。私有双纹理保存历史，writer 记录完全部 copy 后发布，供下次执行读取。
- **暂停时钟不暂停历史；每次实际执行 writer 都更新。** 后续 Pass 报错不撤销已发布历史；不提供旧事务式“整帧失败就不提交”。
- `customRenderPiplineResetHistory(g)` 重置所有 key；第二个参数可指定一个 key，未知 key 报错。
- `customRenderPiplineHistoryInfo(g)` 返回 JSON 字符串，包含 `valid/updates/extent`。
- `Previous.status/Save.status` 是 `RGBA32Uint` 的 1×1 输出：`(valid, updates低32位, 0, reader=0或writer=1)`。调试读取仍有同步成本，正常历史执行本身没有 CPU 读回/等待。

## 哪些接口不再支持

`SchemaPipeline`、旧 `generate_schema.py`、Config/快照事务 Python 层、旧 UE 运行入口及旧 ABI-only Python tests 已归档退役；旧 Init/Pre/Decode/Adapter/UE GBuffer/Lighting/ShadowSetup/SkyViewSetup 不再注册。不是为旧接口提供新的别名。

**新的 Schema 还在：** `gbuffer_schema.py`、`gbuffer_codegen.py`、`generate_native_gbuffer.py` 与新原生 GBuffer、V4 观察/CLI 均保留。新描述式 Compute/Fullscreen/Mesh/Asset/History 可直接组合原生 Pass。

资源迁移完成时，14 个旧 runtime C++ 文件和 4 个旧合同 C++ test 文件已停止编入插件/默认测试。后续 C2 又将旧源码和依赖旧 ABI 的 Shader 包装精确归档移出主线，清单见 `build/native-framework-completion/cleanup-removed-source.json` 与 `cleanup-wrapper-supplement.json`。独立 Sun/Sky 数学、Shader 来源和参考数据保留。旧研究片段不等于可在新入口原样运行；需要效果时再按新资源/Shader 接口接入。

## 验证与剩余工作

本轮日志、精确删项、测试 ID 对账、最终 source hashes 和 replay commands 见 `build/resource-history-migration/verification.json`。备份为同目录 `source-before.zip` 与退休归档；不要清理证据目录后再声称原字节仍可恢复。

这次迁移的支持范围以 D3D12/RTX 4090 实测为准；没有用迁移测试替代桌面交互或 UI 帧率验收。后续按需读回异步化和有限后端矩阵已经完成整合回归，headless 性能也另有测量；它们不是此历史迁移验证的测试总数。08:15 对本页三项再次运行当前构建，Asset/History/退役脚本及 372 Python tests 通过，含真实 Logger 检查：`build/native-framework-completion/migration-status-wpuoqxon/verification.json`。V5 真实交互仍未闭环，整图回滚按用户要求暂缓，最终 RDC 对齐独立跟踪。详见 [Todo](customrenderpipline-todo-zh.md) 与 [当前状态](customrenderpipline-native-completion-status-20260914-zh.md)。
