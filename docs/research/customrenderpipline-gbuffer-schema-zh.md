# 原生 GBuffer：Schema 自动生成与布局校验

这套生成器对应 Todo 的 G4/G5：用同一份布局生成编码和解码，保留手写特殊 codec，并在生成前检查存储合同。生成结果直接交给现有 `CustomRenderPiplineGBufferPass`。无需旧 UE 材质表、`UESurface`、SchemaPipeline、旧生成器或旧深度约定；也没有新增 C++ 执行器。

## 直接运行

在 `E:/Project/falcor/Falcor-m0` 执行：

```powershell
& .\build\windows-vs2022\bin\Release\Mogwai.exe --script scripts/customrenderpipline/native_schema_gbuffer.py
```

[示例入口](../../scripts/customrenderpipline/native_schema_gbuffer.py) 使用纯 Falcor 场景和原生材质，先生成文件，再创建普通 RenderGraph，并用原生 BlitPass 显示颜色。输出还包括材质位字段、编码法线和深度。

也可以离线生成：

```powershell
& E:/IDE/Anaconda/python.exe scripts/customrenderpipline/generate_native_gbuffer.py scripts/customrenderpipline/examples/schema_gbuffer/Schema.json --output build/my-gbuffer
```

或在 Mogwai 脚本中调用：

```python
from generate_native_gbuffer import generate

artifacts = generate('MySchema.json', 'build/my-gbuffer')
gbuffer = createPass('CustomRenderPiplineGBufferPass', {
    'definition': str(artifacts.definition),
})
```

Python 模块在 `scripts/customrenderpipline`；外部脚本需将该目录加入 `sys.path`，示例已处理。文件路径相对 Schema 所在目录解析。

修改 Schema 后重新调用 `generate()`，并将新的 `artifacts.definition` 通过原生 `graph.updatePass('GBuffer', {'definition': str(artifacts.definition)})` 交给对应 Pass；布局端口变化时同时更新图连接和下游 Shader。现有原生 Pass 的 Reload 按钮读取生成后的 Layout.json，不会代替 Python 重新生成 Schema。

## 你需要定义什么

[完整 Schema 示例](../../scripts/customrenderpipline/examples/schema_gbuffer/Schema.json) 将语义值、存储位置和编码规则分开：

| 项目 | 作用 |
| --- | --- |
| `attachments` | MRT 名称和 Falcor 格式；数组顺序就是 `SV_Target` 顺序 |
| `fields` | 材质产生的逻辑字段，如 `float roughness`、`uint materialID`、`float3 normalW` |
| `storage` | 存储槽对应哪个附件、哪些 RGBA 通道，或通道里的哪段位 |
| `codecs` | 每组逻辑字段如何转换到存储槽，以及如何解码 |
| `producer` | 可选的手写材质求值文件和函数入口；有它才生成原生光栅 Pass 的 Shader/定义 |
| `depthFormat` | 可选的原生深度格式；省略使用现有原生 Pass 的 `D32Float` 默认值 |

例如，把粗糙度存入 `R32Uint` 的低 8 位，三部分分别是：

```json
{
  "field": {"name": "roughness", "type": "float"},
  "storage": {
    "name": "roughnessCode", "attachment": "materialBits", "channels": "r",
    "bits": {"offset": 0, "width": 8}
  },
  "codec": {
    "kind": "unorm", "field": "roughness", "storage": "roughnessCode",
    "range": [0, 1], "overflow": "clamp"
  }
}
```

上面是三段条目的说明，不是独立可运行的顶层 Schema；分别放入 `fields`、`storage`、`codecs` 数组。每个逻辑字段和存储槽必须由且仅由一个 codec 负责，不能漏配或重复分配。

## 常规编码与越界处理

| `kind` | 行为 |
| --- | --- |
| `uint` | 无符号整数存储，保留完整 32 位精度 |
| `sint` | 有符号整数用二进制补码存入无符号位槽，解码时符号扩展 |
| `bool` | 存为 0/1；逻辑字段类型必须为 bool |
| `unorm` | 将声明范围线性映射到无符号位槽，使用 round-to-nearest-even；解码执行逆映射 |
| `direct` | 同类型标量/向量直接写通道，由附件格式执行硬件量化或 sRGB 转换 |
| `custom` | 调用手写 Slang，可处理非线性、查表和多个字段联合编码 |

除 bool/custom 外，必须明确 `range` 和 `overflow`。`reject` 在运行时值超范围时返回失败；`clamp` 明确钳制到声明范围。内置浮点 codec 拒绝 NaN/Inf 及非零 float32 subnormal 输入，用原始位检查避免 GPU 将极小值当成零后悄悄接受；正负零均可用。特殊 codec 可自行声明并处理特殊数值域。声明的整数范围本身超过存储容量时，生成阶段就拒绝；不能靠 clamp 掩盖错误的容量声明。

生成 API 为 `bool NameEncode(NameFields value, out NamePacked packed)`。失败时 packed 全零。生成的光栅包装 Shader 对失败片元执行 discard；手写调用者可以检查 bool 并采用自己的诊断策略。这不会触发 CPU 同步，也不代表运行时图回滚。

`direct` 的范围也必须适合目标通道，如 UNORM 的 0–1、SNORM 的 -1–1、Float16 的有限范围。线性量化使用 float32，当前最多 24 位；跨度和半个量化步长必须能在 float32 正常数范围内表示。解码仍遵循 GPU float32 算术精度；涉及极端微小数值的算法应使用专门验证的 custom codec。完整 uint32 使用整数路径，不经过 float 转换。

## 特殊量化和联合 codec

[SurfaceCodec.slangh](../../scripts/customrenderpipline/examples/schema_gbuffer/SurfaceCodec.slangh) 同时处理粗糙度和法线：

- 粗糙度使用 `round(sqrt(r) × 255)` 编码，解码为 `(q / 255)²`。
- 法线使用八面体编码，将 float3 方向变换为两个 UNORM 通道。

Schema 的 custom 条目声明其 `fields` 和 `storage` 名单。生成器先生成专属 Input/Storage 结构，再包含你的 Shader；接口示例：

```slang
bool encodeSurface(SchemaMaterial_surfaceInput value,
                   out SchemaMaterial_surfaceStorage storage);
SchemaMaterial_surfaceInput decodeSurface(SchemaMaterial_surfaceStorage storage);
```

Input 只含该 codec 声明的逻辑字段，Storage 只含它负责的存储槽。生成器会进一步检查输出存储值的容量及有限性：即使 custom 返回 true，也不能把 300 塞进 8 位槽后静默截断。

特殊算法的输入域、单位、量化公式和需要的位宽由作者负责。改变位宽或重命名 Schema 后，需要同步与之有关的手写部分并重新验证。静态布局检查不会分析任意 Slang 算法来证明其可逆或正确。

## 材质求值仍由你控制

[Material.slangh](../../scripts/customrenderpipline/examples/schema_gbuffer/Material.slangh) 实现：

```slang
SchemaMaterialFields evaluateGBuffer(ShadingData sd, uint materialID);
```

示例查询原生 MaterialSystem 的 BSDF 属性，把它们填写为逻辑字段。示例里的 `baseColor` 实际取 `diffuseReflectionAlbedo`，不应误认为所有材质未经处理的 baseColor 贴图值。适配 UE 材质时可以在求值 Shader 和 codec 中表达需要的实际行为，通用生成器不登记 UE 模型，也不要求旧材质 ABI。

当前光栅包装继续采用原生 Scene 可见性、顶点处理和 Alpha Test；`depthFormat` 只选择格式。任意深度算法、反向 Z 状态或材质导入不属于这次 G4/G5，仍由相应 Pass 配置/实现负责。

## 下游如何读取

生成目录包含：

- `Codec.slangh`：`NameFields`、`NameStorage`、带 MRT 语义的 `NamePacked` 和同源 encode/decode。
- `Layout.json`、`GBuffer.3d.slang`：存在 producer 时生成，供现有原生 GBuffer Pass 使用。
- `Metadata.json`：字段/存储映射、布局哈希、声明源文件哈希，供检查工具使用。

下游 Shader 包含同一个 `Codec.slangh`，按附件类型读取纹理，填入 `NamePacked` 后调用 `NameDecode()`。真实示例见[GPU 验收脚本](../../scripts/customrenderpipline/native_gbuffer_schema_smoke.py)：读取生成的 UINT/UNORM 位附件、颜色和 RG16Unorm 法线，再用第二个 Shader 解码。

合同哈希包含 Schema 和直接自定义 codec 源文件的内容哈希。同名但不同合同的两个生成头若被包含到同一 Shader 编译单元，会报冲突，包括相同文件名但不同自定义实现。独立编译、故意使用过期头或绕过生成接口的第三方 Pass 不会自动接受跨 Pass 语义检查；变更布局时应让生产端与消费端一起使用本次生成结果。[V4 观察接口](customrenderpipline-schema-observer-zh.md) 已接入 Metadata/decoder，提供 Python 和外部 CLI 的字段查询、导出、比较；原生像素检查 UI 仍由 V5 跟踪。

## 文件更新与边界

生成目录按内容标识，根目录 `manifest.json` 最后发布；非法 Schema、缺失源文件或已被改写的生成文件会被拒绝，之前的 manifest 保留。不要手工修改生成文件。

producer/custom 文件通过普通 Slang include 引用。Metadata 中的源哈希反映生成时的直接源文件，未封存所有传递依赖；修改源文件后重新生成，Shader 编译和重载仍交给 Falcor。生成成功不等于 Shader 已编译成功，也不提供整图回滚保证。

普通 `to_numpy()` 对部分 UNORM/packed 格式返回原始字节，CPU 观察时要按附件格式解释。GPU 解码应使用与附件格式匹配的 Texture2D 类型；sRGB 纹理采样会执行硬件转换。位槽支持 UINT 和线性 UNORM，sRGB 的 RGB 位槽会被拒绝，alpha 位槽不受 RGB 转换影响。

已测试范围和当前状态记录在[验证索引](../../build/native-gbuffer-schema/verification.json)。本次主要验收 D3D12；不把这些结果作为 Vulkan、任意格式或最终 RDC 图像对齐证明。

2026-09-12 完成结果：495 项 Python 测试通过，其中新增 Schema 测试 26 项；4 组 D3D12 debug-layer GPU 脚本通过。覆盖整数/量化/特殊 codec、真实 UINT/UNORM MRT 写入和下游解码，以及原生 GBuffer/Mesh 筛选回归。独立代码审查提出的问题已修复并关闭；本轮没有修改 C++ 或旧 UE 实现。
