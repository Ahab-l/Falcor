# 中立描述式 Pass 与原生 MeshDraw

本次迁移的是通用框架入口，不是 UE 效果算法：

| 能力 | 新默认入口 | 不再强制需要 |
|---|---|---|
| 描述组图 | `pipeline.make_graph()` → 原生 `RenderGraph` | `SchemaPipeline`、旧快照、旧 Scene/Schema JSON |
| Compute / Fullscreen | 普通 properties + 自己的 Slang 文件 | 旧 `Config`、UE shader 前缀、隐式曝光 |
| 专用 Mesh Pass | `CustomRenderPiplineMeshDrawPass` → `Scene::RasterDrawList` / `Scene::rasterize()` | 旧材质名称表、`UEMeshPass`、固定 reversed-Z |
| 自定义 GBuffer / 观察 | 继续用现有新 Schema/codec、原生 GBuffer、V4 observer/CLI | 旧 UE GBuffer/材质/深度 ABI |

原生 RenderGraph 负责资源分配、连接、调度；没有添加第二套调度器。可以直接使用 `createPass/addPass/addEdge/markOutput/updatePass` 编辑返回的图。这里的 Compute/Fullscreen/Mesh 是我们已有执行器的中立化，不是声称上游 Falcor 本来就有同名 JSON 执行器。

## 1. 运行交付示例

实际工作树是 `E:/Project/falcor/Falcor-m0`。示例把这些节点放在同一张图：

```text
新 Schema → GBuffer ─────────┐
指定 instanceIDs → MeshDraw ─┴→ Compute → Fullscreen → 原生 Blit
              GBuffer 附件 → 现有 Schema observer / CLI
```

PowerShell 中运行一次无窗口验证：

```powershell
Set-Location E:/Project/falcor/Falcor-m0
$env:CRP_NATIVE_EXAMPLE_TEST = '1'
& ./build/windows-vs2022/bin/Release/Mogwai.exe --headless --enable-debug-layer --script E:/Project/falcor/Falcor-m0/scripts/customrenderpipline/native_described_passes.py
Remove-Item Env:CRP_NATIVE_EXAMPLE_TEST
```

成功标记是 `NATIVE_DESCRIBED_EXAMPLE_PASSED`，结果写到 `build/native-pass-migration/example/result.json`。想交互查看时，不设置该环境变量、去掉 `--headless` 即可；本轮验收只运行 headless。

示例脚本：[native_described_passes.py](../../scripts/customrenderpipline/native_described_passes.py)。可修改的描述与 Shader：[Graph.json](../../scripts/customrenderpipline/examples/native_passes/Graph.json)、[Mesh.json](../../scripts/customrenderpipline/examples/native_passes/Mesh.json)、[Fullscreen.json](../../scripts/customrenderpipline/examples/native_passes/Fullscreen.json)。场景复用纯原生的 [Scene.pyscene](../../scripts/customrenderpipline/examples/schema_gbuffer/Scene.pyscene)，没有旧 Scene JSON 占位文件。

观察功能需要 Mogwai 的 Python 3.10 能导入 NumPy；本机使用已有 `build/m0-evidence/python` 依赖目录。组图器自身不依赖 NumPy，CLI 客户端只使用标准库。

## 2. 定义一张图

```python
from pipeline import make_graph
graph = make_graph('MyPipeline', 'E:/my_project/Graph.json')
m.addGraph(graph)
m.setActiveGraph(graph)
```

最小结构：

```json
{
  "version": 1,
  "nodes": [
    {"name": "Effect", "description": "passes/Effect.json"},
    {"name": "Copy", "type": "BlitPass", "properties": {"outputFormat": "RGBA32Float"}}
  ],
  "edges": [["Effect.color", "Copy.src"]],
  "outputs": ["Copy.dst"]
}
```

- 节点可直接写 `type/properties`，或复用含 `type/properties` 的 Pass JSON。节点上的 properties 递归覆盖复用描述，数组整体替换。
- `shader.file` 自动按**写出该属性的文件**解析相对路径；覆盖 Shader 路径时按图文件解析。其他文件属性用 `file_inputs: ["definition"]` 等 dotted 路径声明。
- dict 输入使用 `base_directory=...`；不传时使用当前目录。JSON 路径输入始终按该文件所在目录解析。
- `metadata` 仅作说明，不传给执行器。节点名/端口为 ASCII identifier。
- `edges` 支持资源边 `A.out → B.in`，也支持纯执行边 `A → B`。结构重复、循环、悬空节点、非法字段在创建图前拒绝；真实端口/格式兼容性由 Falcor 验证。
- 不接受旧 `schemaPath/sceneDefinition`、`$packed/$field:` 宏或 `inherit_pipeline=true`。新 Schema 的具体附件可以正常作为显式端口，不需要旧宏。

## 3. Compute / Fullscreen 怎么写

照示例声明 Shader、资源名称/格式/方向/绑定、uniforms 和 dispatch。资源 `binding` 必须匹配 Slang 反射；错误名称、structured stride、dispatch 或 state 被拒绝，不会静默忽略。

```json
"uniforms": {
  "Params.extent": {"type": "uint2", "source": "extent"},
  "Params.gain": {"type": "float", "value": 1.0}
}
```

原生 `source` 只接受 `extent`。曝光或其他效果参数由 `value` 或显式资源传入，不隐式采用旧 preExposure 约定。Fullscreen 未指定自定义 VS 时使用执行器提供的全屏三角形 VS；PS 默认入口 `main`。

资源绑定、Cube/mip/数组视图、structured buffer、once 缓存、MRT/writeMask 等沿用原执行器已支持的范围。本次没有把每个资源种类自动扩展到每类执行器：例如 Mesh 的额外输入仍只支持原有 Texture2D/raw buffer，附件保留其已有子资源支持。

Shader 使用 Falcor 的 file-based 程序加载，不再被冻结到旧快照。同一接口下的函数修改走 Falcor 原生 reload；若改了参数顺序、类型或资源布局，必须使用 `updatePass` 重建节点/ProgramVars，不能依赖 F5 自动迁移反射布局。本次 headless 验收未模拟 F5 键盘操作。本次不承诺 Shader/配置错误时自动保留整张旧图，整图回滚仍按用户决定暂缓。

## 4. 指定哪些 Mesh 参与

```python
ids = list(m.scene.get_raster_instance_ids())
# 也可用 Scene 的原生材质查询，或由应用直接管理这些 ID。
selected = ids[:1]
props = {
    'shader': {'file': 'E:/my_project/Mesh.slang', 'vertex': 'vsMain', 'pixel': 'psMain'},
    'instanceIDs': selected,
    'colorTargets': [{'name': 'color', 'format': 'RGBA32Float', 'slot': 0}],
    'depthTarget': {'name': 'depth', 'format': 'D32Float'},
    'state': {'cull_mode': 'Material'}
}
```

- 不写 `instanceIDs`：所有原生 raster triangle instances；写 `[]`：不提交几何，但按配置 clear/load。
- ID 必须为 uint32，并属于**当前 Scene 的几何实例**。Scene 重载后应用应重新查询选择；不是持久资产 ID。非法/非三角几何 ID 在 clear 前拒绝。
- 通用 Pass 不再按旧材质名称表取值；`cull_mode: Material` 读取原生 `Material::isDoubleSided()`，属性变化会改变绘制分组。`None/Back/Front` 为显式覆盖。
- Shader 仍遵循 **Falcor 原生 Scene raster ABI**：通过 `import Scene.Raster`（示例方式）或 `import Scene.Scene` 提供 `gScene` 参数块。这里去掉的是自研旧 UE ABI，并非绕过原生 Scene 数据接口；缺少该块在 clear 前拒绝，即使选择为空也如此。
- 原生默认深度 clear=1、比较 `LessEqual`。可在 `depthTarget.clear` 和 `state.depth_func/depth_write` 自定义，包括调用者自己的 reversed-Z，但不是框架强制约定。
- `view_projection` 是 4×4 行数组；只有同时提供 Shader 中的 `view_projection_binding`（如 `Transform.projection`）才能使用。Shader 自己决定这个矩阵如何作用；无需命名成 `UEMeshPass`。
- 原有 MRT、clear/load、blend/writeMask、depth/stencil、viewport、uniform/resource/sampler 检查继续共享。透明排序不在本次实现范围。

## 5. 程序与 CMD 观察

Python 直接复用：

```python
sample = observer.inspect([32, 20, 1, 1], fields=['roughness', 'normalW'])
raw = graph.getOutput('Combine.color').to_numpy()
```

要启用现有 V4 命令服务，用一个新的会话目录启动示例，且不要设置单次测试环境变量：

```powershell
$env:CRP_OBSERVER_SESSION = 'E:/Project/falcor/Falcor-m0/build/native-pass-session'
& E:/Project/falcor/Falcor-m0/build/windows-vs2022/bin/Release/Mogwai.exe --headless --script E:/Project/falcor/Falcor-m0/scripts/customrenderpipline/native_described_passes.py
```

另一个终端：

```powershell
python E:/Project/falcor/Falcor-m0/scripts/customrenderpipline/inspect_cli.py --session E:/Project/falcor/Falcor-m0/build/native-pass-session list --graph NativeDescribedPasses
python E:/Project/falcor/Falcor-m0/scripts/customrenderpipline/inspect_cli.py --session E:/Project/falcor/Falcor-m0/build/native-pass-session inspect --graph NativeDescribedPasses --region 32 20 1 1 --fields roughness normalW
python E:/Project/falcor/Falcor-m0/scripts/customrenderpipline/inspect_cli.py --session E:/Project/falcor/Falcor-m0/build/native-pass-session read --graph NativeDescribedPasses --output Combine.color
```

服务按需读回，空闲不做像素读回；字段比较/导出沿用 [V4 用法](customrenderpipline-schema-observer-zh.md)。不是新做一套观察 UI，也不代表 V5 鼠标验收已完成。

## 6. 旧代码与剩余范围

旧 `make_declared_graph/SchemaPipeline` 入口暂时保留为惰性兼容门面，事务实现迁到 `extensions/ue_reference/transaction.py`。C++ 的旧源展开、材质映射、旧 per-draw 写入和深度默认值由 UEReference compatibility policy 承接；普通 properties 不构造旧 Config。

因此：**通用能力已能绕开旧依赖，不等于所有旧调用者已经删除。** Asset/History 的旧 Config 迁移、实际 UE 效果算法迁移、旧 Adapter/生成器/测试退役，以及 UEReference 构建开关仍是 A1 后续项。本轮没改它们，也没改 V5、整图回滚或最终 RDC 对齐状态。

验证和本轮源码备份索引见 `build/native-pass-migration/verification.json`；原字节备份为 `source-before.zip`，未提交、未合并、未批量删除旧模块。当前执行器后端范围为 D3D12 / SM6.6，其他后端未验收。
