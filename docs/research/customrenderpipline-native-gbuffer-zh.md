# 使用原生 Falcor 实现自定义 GBuffer

**G4/G5 更新：** 新增独立的通用 [Schema 生成入口](customrenderpipline-gbuffer-schema-zh.md)，可自动生成布局读写代码及原生 Pass 定义，检查位段/类型/声明范围，并保留手写特殊 codec。下文直接手写 JSON/Slang 的入口仍有效，不要求使用生成器；这里新增的生成器不依赖旧 UE SchemaPipeline。

本轮只替换正在讨论的第一项：自定义 GBuffer 附件、通道和位编码。普通场景使用 `CustomRenderPiplineGBufferPass`，通过 Falcor 原生 Scene、MaterialSystem 和 RenderGraph 执行。第一次编译插件之后，调整附件和编码只需修改 JSON / Slang，无需继续修改 C++。

后续已将 Mesh 选择接入 Falcor Scene 层：本 Pass 和官方 `GBufferRaster` 都支持可选 `instanceIDs` 属性，未提供时仍绘制全场景，空数组不绘制任何实例。用法与边界见 [Scene 绘制列表说明](customrenderpipline-native-mesh-selection-zh.md)。

## 直接运行

```powershell
Set-Location E:\Project\falcor\Falcor-m0
& .\build\windows-vs2022\bin\Release\Mogwai.exe --script scripts/customrenderpipline/native_gbuffer.py
```

入口 [native_gbuffer.py](../../scripts/customrenderpipline/native_gbuffer.py) 使用原生 `createPass/addPass/addEdge/markOutput`，将 GBuffer 输出连接到原生 `BlitPass`。可以在 Mogwai 加载其他 Falcor 场景，并在输出列表选择法线或深度。

```python
g = RenderGraph('Example')
g.addPass(createPass('CustomRenderPiplineGBufferPass', {}), 'GBuffer')
g.markOutput('GBuffer.colorRoughness')
```

默认输出 `colorRoughness: RGBA32Float`、`normal: RGBA32Float` 和 `depth: D32Float`。前三个颜色通道是原生材质的 **diffuseReflectionAlbedo**，alpha 是原生 BSDF roughness；它们与原生 `GBufferRaster.diffuseOpacity.rgb/specRough.a` 对应。法线是世界空间 guide normal，alpha 为覆盖标记。diffuseReflectionAlbedo 不能当成任意材质未经处理的 baseColor。

## 配置附件和编码

传入 `{'definition': '绝对路径/Layout.json'}`。示例 [Packed.json](../../scripts/customrenderpipline/examples/native_gbuffer/Packed.json)：

```json
{
  "shader": "MyGBuffer.3d.slang",
  "defines": {"PACKED_LAYOUT": 1},
  "attachments": [
    {"name": "materialBits", "format": "R32Uint"},
    {"name": "color", "format": "RGBA8Unorm"},
    {"name": "normal", "format": "RGBA16Float"}
  ],
  "depthFormat": "D32Float"
}
```

`shader` 相对定义文件所在目录解析。附件数组顺序对应 Shader 的 `SV_Target0/1/2`，支持 1–8 个颜色附件；`depth` 是保留的深度输出。名称必须唯一，格式须支持对应 GPU 绑定。可选 `vertexEntry/pixelEntry` 默认为 `vsMain/psMain`。

[NativeGBuffer.3d.slang](../../Source/RenderPasses/customrenderpipline/NativeGBuffer.3d.slang) 展示原生材质查询和 MRT 写入；[NativeGBufferCodec.slangh](../../Source/RenderPasses/customrenderpipline/NativeGBufferCodec.slangh) 展示编码/解码函数：粗糙度占 0–7 位，材质 ID 的低 16 位占 8–23 位，发光标记占第 24 位。材质 ID 超过 65535 时需自行扩大编码，不能把此示例当成全局材质 ABI。后续 Pass 读取整数附件并调用同一 codec，即可按相同规则解码。

直接手写模式下，改布局时同步修改 JSON 和 Shader 输出签名；配置层校验名称、格式等结构，Shader 编译由 Falcor 负责。需要同源生成位布局与读写函数时，使用上面的独立 Schema 生成入口。两种方式都复用原生资源分配、材质绑定、绘制和图调度。

Pass 自带 `Load GBuffer definition` / `Reload GBuffer definition` 按钮，原生 `getProperties()` 支持图导出和 `updatePass()` 重建。原生图编辑器可枚举这个 Pass、连接端口和标记输出。切换附件名称后需要同步更新图连接。

## 与旧实现的关系

普通 GBuffer 不再要求 `sceneDefinition`、`schemaPath`、生成的 Schema、自定义材质表、Mesh 路由、`SchemaPipeline` 或图封印。没有另写调度器或读回接口；原始像素使用原生 `to_numpy()`。

旧实现包含 UE 材质公式、坐标、反向深度、模板和捕获几何处理，原生功能不能等价替代这些算法。它已更名为 **`UEReferenceGBufferPass`**，由 UEReference 扩展注册，旧 RDC 脚本明确引用它。旧 Schema/codec 生成器仍供这些案例使用；它们没有被伪称为已经删除。

本轮没有撤销之前的 23 个核心文件补丁；结构化缓冲、Cube、特殊平面读回和整图回滚属于后续逐项评估范围。新 Pass 仅调用上游已有接口，但在当前有补丁的构建中通过测试，不等于已证明所有底层补丁都可删除。

原生 `updatePass()` 在构造失败时保留旧 Pass，因此无效 JSON 可安全拒绝。**这不等于 Shader 编译失败、实时编辑或 F5 重载具备整图回滚保证。** 新原生入口尚未接入候选图验证和切换机制，原有事务入口仍保留供已有案例使用。

**2026-09-12 用户决策：整图回滚暂时不需要。** 当前采用 Falcor 原生报错与重载流程，修正后再运行；此功能不再作为新入口的当前必做项或验收阻塞。后续需求记录在[项目备忘](customrenderpipline-memo-zh.md)。

GPU 验收入口为 [native_gbuffer_smoke.py](../../scripts/customrenderpipline/native_gbuffer_smoke.py)：同场景比较原生材质输出、检查两种布局及位编码、属性重建、动态标记深度输出、拒绝无效配置。

2026-09-12 验证结果：完整 Release 构建通过，469 项 Python 测试通过；新原生 GBuffer、既有框架/回滚、UE 材质 Shader 三组 D3D12 debug-layer 验收通过。原生对照场景的 4678 个覆盖像素，颜色、粗糙度和法线最大误差均为 0；这不是任意场景或最终 RDC 画面对齐证明。旧 `adapter_smoke.py` 仍因注入 `primitive_flags` 被既有接口拒绝，其拒绝逻辑与本轮备份一致，未计为通过。证据索引为 `build/native-gbuffer-refactor/verification.json`。
