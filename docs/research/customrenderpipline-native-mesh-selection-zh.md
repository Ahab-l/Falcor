# 接入 Falcor Scene 的 Mesh 绘制列表

这是我们对当前 Falcor 分支的核心扩展，不代表官方原版已经提供了这些新接口。实现位于 `Source/Falcor/Scene/Scene.h/.cpp`，复用原有的间接绘制参数构建和提交过程。核心接口不依赖 customrenderpipline 的 Schema、UE 材质或路由配置。

## 在脚本中使用

加载 Scene 后，用原生材质名称取得实例 ID，分别交给需要它们的 Pass：

```python
special = m.scene.get_raster_instance_ids(['blue'])
ordinary = sorted(set(m.scene.get_raster_instance_ids()) - set(special))

g = RenderGraph('Example')
g.addPass(createPass('GBufferRaster', {'instanceIDs': ordinary}), 'Ordinary')
g.addPass(createPass('CustomRenderPiplineGBufferPass', {
    'instanceIDs': special,
    'definition': 'E:/MyPipeline/SpecialGBuffer.json',
}), 'Special')
```

`SpecialGBuffer.json` 选择自己的 Slang 和输出格式。上面两个 Pass 对同一个 Scene 使用互补的绘制列表；Special 对象不在 Ordinary 的预深度和 GBuffer 绘制列表中。管线不再依赖 Shader discard 来实现这项排除。

完整示例：[native_mesh_selection.py](../../scripts/customrenderpipline/native_mesh_selection.py)。在 `E:/Project/falcor/Falcor-m0` 运行：

```powershell
& .\build\windows-vs2022\bin\Release\Mogwai.exe --script scripts/customrenderpipline/native_mesh_selection.py
```

在 Mogwai 输出列表切换 `Ordinary.diffuseOpacity` 和 `Special.color`，分别查看普通对象和特殊对象。它展示两个集合的输出，不包含最终光照或合成。

## 选择规则

- Pass 不传 `instanceIDs`：保留原先的全场景绘制。
- `instanceIDs: []`：该 Pass 不提交任何场景实例，输出仍执行正常清除。
- 重复 ID：去重并按 Scene ID 排序；Shader 仍收到原始实例 ID，不会重编号。
- 越界 ID、非三角形几何、将列表交给另一 Scene：报错。
- `get_raster_instance_ids()` 返回当前 Scene 的所有可光栅化三角实例；传材质名称列表时限制到这些材质；传空列表则返回空集合，未知名称报错。
- ID 和材质查询结果属于当前 Scene 的快照。重建或替换 Scene 后，应重新查询和分配。自定义标签仍可由脚本/应用维护，再解析为实例 ID；核心没有新增 UE 标签注册表。

目前已将 `instanceIDs` 属性接入官方 `GBufferRaster` 与可配置 `CustomRenderPiplineGBufferPass`；官方 Pass 的预深度和材质阶段共用同一个列表。其他 Pass 需要显式调用下述接口；没有修改所有官方 Pass 的默认可见性。

## 原生 C++ 接口

```cpp
// 创建一次，保存到 Pass 的成员中。
auto selection = scene->createRasterDrawList(instanceIDs);

// 每帧使用原生 Scene 光栅化；也有接受 CW/CCW RasterizerState 的重载。
scene->rasterize(context, state, vars, selection, RasterizerState::CullMode::Back);
```

`Scene::RasterDrawList` 保留所属 Scene 的引用与选中 ID。它使用原生的 16/32 位索引、CW/CCW 绕序分组，有索引的场景最多四个批次，无索引的场景最多两个批次；这些是间接调用的批次数，不是模型或三角形数量上限。

全场景和子集共用 `createDrawArgs()` 和 `rasterizeDrawArgs()`。每个 Pass 持有自己的列表，不在 Scene 上反复修改一个全局选择。稳定列表复用 GPU 参数缓冲；通过正常 `Scene::update()` 检测到影响绕序分组的实例标志变化时，列表下次使用会重建。默认全场景列表也同步更新。

脚本也可通过 `create_raster_draw_list(ids)` 查看 `instance_ids`、`draw_count`、`batch_count`、`build_count`。图中的 Pass 属性保存 ID；C++ 插件直接保存并提交列表对象。

## 当前边界

新接口沿用原生光栅三角网格路径，不再施加旧 MeshDraw 执行器的“只允许静态带索引网格”限制；实际测试覆盖范围以验收记录为准。它不是光线追踪实例掩码，不会改变阴影射线或其他未接入 Pass 的对象集合。

绘制顺序遵循原生绕序/索引格式分组，不提供透明物体的深度排序。

旧 `CustomRenderPiplineMeshDrawPass` 暂时保留，因为它还设置每次绘制的 UE 自定义常量、材质状态和特殊附件。不能把这一轮说成旧执行器已全部删除；新原生 GBuffer 和官方 GBufferRaster 的筛选执行已共享 Scene 层实现。

验收脚本为 [native_mesh_selection_smoke.py](../../scripts/customrenderpipline/native_mesh_selection_smoke.py)，原生核心测试为 [SceneRasterDrawList.cpp](../../Source/Tools/FalcorTest/Tests/Scene/SceneRasterDrawList.cpp)。本轮不涉及已暂缓的整图回滚。

## 验证结果（2026-09-12）

完整 Release 构建通过，469 项 Python 单元测试通过。3 项 D3D12 核心 GPU 测试覆盖 16 位索引、32 位索引、无索引路径；每项检查空/全/子集、原始实例 ID、重复 ID、无效和跨场景使用、缓存复用及负缩放后的绕序更新。尚未专项验收蒙皮、混合索引格式同场景或 Vulkan。

5 组 Mogwai debug-layer 验收通过：native_mesh_selection_smoke、native_gbuffer_smoke、framework_smoke、material_shader_smoke、auxiliary_mesh_smoke。前者同时验证官方预深度/GBuffer 与可配置 GBuffer 的选择一致、互补集合重建全场景结果、属性往返更新和实际示例运行。

证据索引：`build/native-raster-draw-list/verification.json`。这些结果证明本次选择与绘制接入正确，不是大场景帧率测试或最终 RDC 画面对齐结论。
