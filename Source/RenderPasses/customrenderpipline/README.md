# customrenderpipline

框架负责 **自定义材质/GBuffer、描述式可组合 Pass、输出观察与验证**。具体光照/阴影等算法由选用的 Shader/Pass 决定，不内置旧 UE 材质或深度约定。

## 当前入口（2026-09-14）

| 能力 | 入口 |
| --- | --- |
| 普通原生 Scene/Material GBuffer | `scripts/customrenderpipline/native_gbuffer.py` |
| 可选 Schema 生成/验证/自定义 codec | `native_schema_gbuffer.py`、`gbuffer_schema.py`、`gbuffer_codegen.py` |
| JSON/dict → 原生 RenderGraph | `pipeline.make_graph()`、`native_pipeline.py` |
| 描述式 Compute/Fullscreen/Mesh | `native_described_passes.py` |
| 独立文件 Asset 与跨执行 History | `native_resource_history.py` |
| 输出、原始数据、字段与误差比较、CMD | `native_schema_observer.py`、`inspect_cli.py` |

运行示例：在 `E:/Project/falcor/Falcor-m0` 执行 `build/windows-vs2022/bin/Release/Mogwai.exe --script scripts/customrenderpipline/native_resource_history.py`。

插件仅注册 GBuffer/Compute/Fullscreen/MeshDraw/Asset/HistoryRead/HistoryWrite 七个通用节点；可组合其它原生插件。MeshDraw 与原生 GBuffer 使用共享 Scene 绘制列表。History 保存上次 writer 的输出，提供显式 reset，不保证整帧回滚。

旧 SchemaPipeline/Config/Adapter/UE 运行调用者已退出主线。旧 C++ glue 和旧 ABI 包装源码已归档移出主线；算法原文、来源和历史证据仍保留，不支持直接重启旧案例。完整归档与新验证索引见 `build/native-framework-completion/c2-stage-verification.json`。旧 Shader 包装的可阅读副本位于 `docs/research/archive/ue-legacy-wrappers`，不参与 Shader 发布；`Extensions/UEReference` 中保留的算法资产也不等于已迁移的完整 UE 运行入口。

- [资源与 History 用法](../../../docs/research/customrenderpipline-native-resources-history-zh.md)
- [描述式 Pass 与 Mesh](../../../docs/research/customrenderpipline-native-pass-migration-zh.md)
- [新 Schema](../../../docs/research/customrenderpipline-gbuffer-schema-zh.md)
- [观察与 CMD](../../../docs/research/customrenderpipline-schema-observer-zh.md)
- [当前 Todo](../../../docs/research/customrenderpipline-todo-zh.md)
- [全量重新审计](../../../docs/research/customrenderpipline-modification-reaudit-20260914-zh.md)

V5 UI 仍待收尾；同步按需读回仍存在；整图回滚暂缓；未宣称 Vulkan 或最终 RDC 对齐通过。
