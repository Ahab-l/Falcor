# Schema / Codec 运行时闭环

2026-09-09，实施目录 `E:/Project/falcor/Falcor-m0`，分支 `codex/ue-legacy-m0`。

**当前最新：** 2026-09-09 最新：Schema 管布局、字段/位段、ID、资源需求与分派；Shader Codec 管数学，Packed 主管线与既定顺序保持不变。七模型 GBuffer 与对应普通 Lighting Shader 已接入；本批 ClearCoat/Skin 的 224 组件样本、九原生图、Mesh/Adapter 双法线/ID/MRT/CustomData 迁移及缺失 LUT 回滚通过。Mesh HDR 仅通过给定独立单灯 GPU debug lobes 的非双法线累加区间检查，不是 half 位型或全图 BRDF 证明。新运行时 13 份 RDC 数值数组与上一版逐位一致，严格 HDR 仍 31 个像素各差 1 half ULP。原生阴影/GI/天空/自动曝光、Clustered、SSR、TSR、Web 与最终图像仍未完成。详见 [ClearCoat/Skin 报告](../ue-legacy-coat-skin-lighting.md)。下方旧阶段数值与状态按历史理解。

最新状态：[原生平面与精度验收](../ue-legacy-stencil-precision.md) 已完成实际depth/stencil全allocation逐位对比，C、Metallic、Roughness、模型/对象位和D一致；法线剩1像素、Specular剩5像素。Adapter已通过最终Shader下的布局迁移/回滚及grid几何不变验收。Schema/Codec职责保持不变，真实模型扩展仍未开始。

后续进展：显式原生 GBuffer Adapter 已接入相同 Schema/Codec 和整图事务；原始 IA 精度路径已使 RDC 深度逐位一致。Adapter 的 Schema-only 迁移、ID 0、回滚及 ViewRect 测试已有实测。详见 [Adapter 与精度报告](../ue-legacy-adapter-fidelity.md)。下文先前将 Adapter 标为待完成的内容是历史阶段状态。

本轮后续状态：Schema/Codec 已加入 UEEncodeContext，Specular 抖动和对象标志转换由 DefaultLit Codec 执行；Mesh 路由与项目源码 PipelineSignature 见 [整图契约报告](../ue-legacy-mesh-routing/README.md)。最新默认 generation 为 `803c111d2a7bf0ca417006e8d20417e7204f0c4e4f75967848e71851f33c6d34`。38 项 Schema、19 项 Pipeline snapshot、21 项 Capture 测试通过；`m1-context-final.log` 与 `schema-context-final.log` 两组 GPU 回归退出0，Schema-only 迁移仍保持117,087覆盖像素逻辑输出逐位一致，DLL在该测试内未改变。下文基础闭环记录中的早期 generation 和日志为历史证据。

这一步将第一条 DefaultLit 真实 Mesh Pass 从固定 Capture profile 原型迁移到独立 Schema。原始 Capture 和 `reference_profile.json` 仍是不可变参考证据，原有 21 项校验与证据文件 hash 校验保留。

## 职责与数据流

| 文件或层 | 责任 |
|---|---|
| `Source/RenderPasses/UELegacy/Schemas/DefaultLit.json` | 附件格式、MRT slot、写掩码、逻辑字段至 RGBA 通道和 bit range 的映射、模型 ID、有效字段和 Codec 注册、consumer 需求 |
| `Codecs/DefaultLit.slangh` | 原始 UE 属性至逻辑存储字段的数学，例如 normal 编解码、emissive/preExposure；不引用物理 attachment/channel |
| `Codecs/DefaultLit.codec.json` | Codec 的入口、字段需求和实际能力；当前 AO=1，Schema 不能修改声明来冒充 AO 算法已实现 |
| `scripts/ue_legacy/generate_schema.py` | 校验布局和字段覆盖，生成 MRT、字段/bit 访问、模型分派与有效性公共接口；没有各模型的着色数学 |
| `UELegacyConfig` / Passes | 从生成 metadata 反射和分配附件、建立 MRT 顺序和写掩码；Shader 使用通过 hash 校验的内存快照 |
| `scripts/ue_legacy/pipeline.py` | 构建完整图，生成候选、离屏编译执行、帧间提交整张图 |

MaterialProgram 继续负责求原始材质属性。constant 与 UV 仍是独立 Shader Program/Vars/PSO，模型 ID 从注册表解析后作为材质属性传入。相同着色模型可对应多个 MaterialProgram。

Schema 支持一至八个连续 MRT slot，支持的浮点/UNORM/sRGB 格式由通用能力表约束。BGRA 格式的路由名称仍是 Shader 逻辑 RGBA；CPU 原始字节保持 BGRA。整数位段只允许在线性 UNORM 通道，禁止经 sRGB RGB 转换。字段通道/位段重叠、越界、未知 Codec、缺失字段、能力不符均拒绝。

## Generation 与受控切换

`LayoutHash` 来自规范化布局、ID 和注册契约，不包含 View、Capture EID 或曝光值。`CodecHash` 来自递归 Shader 依赖快照，改物理路由不会改变它。generation 覆盖完整运行时 metadata 与生成 Shader。每代发布到独立内容寻址目录，重复生成会验证现有字节，禁止覆写。

C++ 检验 manifest canonical payload 与外层数据相等，再校验 payload 和 Shader 的 SHA1，随后将 Shader 字符串保存在 Config 中。这里 SHA1 用于检测文件混配，不用作安全签名；generation/LayoutHash/CodecHash 使用 SHA256。曝光通过独立运行时参数传递。

`SchemaPipeline.stage()` 在渲染线程两次 `renderFrame()` 之间运行。它建立新图并交给原生 `ueLegacyPrepareGraph()` 离屏执行，实际创建资源、编译 Shader 特化与 GPU PSO。旧图仍是显示中的 activeGraph。`commit()` 才切换整张已验证图，更新 history epoch，新图具有独立资源，不复制旧 history。失败会清理候选并保留旧图。每个 Mesh/Decode Pass 在执行前检查图的 generation，拒绝生产和消费双方混配。

这是同步的受控切换 API。自动文件监视、后台编译、通用历史重投影系统尚未实现。

## 验收与范围

两组 GPU 测试均使用 RTX 4090 / D3D12 debug layer：

- `m1_smoke.py`：保留 426 个内部采样点的独立 CPU 几何及原始 packing oracle、437 背景点、多 BasePass 与单 BasePass、16/32 位索引逐位对照。
- `schema_smoke.py`：仅改 Schema，将材质数据从 B 移至 D、交换 MRT 0/4、交换 normal/BaseColor 通道和 metallic/roughness 通道，将 modelID bit offset 从 0 改为 1；117,087 个覆盖像素的逻辑输出保持逐位相等；检查原始 D 的字段与新模型字节 130。整个测试内 DLL SHA256 不变。
- 用同一个 DefaultLit Codec 注册 ID 0 和 ID 2，验证生成分派；有深度的 ID 0 与背景分别判定。UE 的 Unlit 定义为 0，因此通用注册范围包含 0。这是测试 fixture，不代表实现了第二种 UE 着色算法。
- 注入真实 Slang `#error`，候选失败后旧图全部输出逐位不变；手动将不同 generation 的 BasePass 拼入同一图被运行时拒绝。

最终 33 项 Schema 测试、21 项 Capture profile 测试以及原始证据 hash 校验通过。

持久结果：[Schema GPU 验收](schema-gpu-result.json)、[DefaultLit 原始数据 oracle](defaultlit-oracle-result.json)。最终日志为 `build/m1-evidence/schema-gpu-final.log`、`build/m1-evidence/smoke-schema-final.log`，两次进程均退出 0。当前默认 generation 为 `940b1c6bc65479c3798467c62081fd3fb08292e37b456c71b035c4c79d2a29c9`。

新请求在生成校验前就丢弃旧 pending；验证失败后禁止误提交旧候选。该边界先由实际 GPU 回归复现（`schema-stale-pending-red.log` 退出 1），修复后的最终验收同时检查 activeGraph、history epoch 和全部输出不变。

独立规格审查和代码质量审查均通过上述限定范围。ID 0 的补充回归已完成离线红绿测试和最终 GPU 验收；没有将测试别名的 DefaultLit 编解码宣称为 Unlit 算法。

材质/model/tag/passmask 路由、冲突检测和项目 MaterialProgram/PSO/路由的 PipelineSignature 已在后续实现，详见开头报告；原生 Falcor GBuffer Adapter、外部实时资源完整指纹与剩余 DefaultLit 数值验收仍待完成。后续 Lighting/SSR 消费者接入同一生成契约。目前只有 DefaultLit、opaque、AO=1、静态 indexed triangle。原生 typeless/readonly DSV/depth plane SRV 差异及新配对 UE capture 的缺口没有因本次改动消失。

## 复现

在实施 worktree 运行：

```powershell
& .\tools\.packman\python\python.exe scripts\ue_legacy\test_schema.py
& .\tools\.packman\python\python.exe scripts\ue_legacy\generate_schema.py
& .\tools\.packman\cmake\bin\cmake.exe --build build\windows-vs2022 --config Release --target UELegacy --parallel 8
& .\build\windows-vs2022\bin\Release\Mogwai.exe --headless --device-type d3d12 --gpu 0 --enable-debug-layer --script E:/Project/falcor/Falcor-m0/scripts/ue_legacy/m1_smoke.py
& .\build\windows-vs2022\bin\Release\Mogwai.exe --headless --device-type d3d12 --gpu 0 --enable-debug-layer --script E:/Project/falcor/Falcor-m0/scripts/ue_legacy/schema_smoke.py
```

后两条测试会直接生成测试所需 generation；Schema/Codec 改动无需再次执行 C++ build。
