# DefaultLit Mesh 几何专项

新增 `mesh_acceptance_scene.pyscene` 与 `mesh_acceptance_smoke.py`，使用现有原生 `UELegacyPrePass → UELegacyGBufferPass → Decode`。没有修改 Mesh 生产代码或 Schema/Codec 契约。

三个 Mesh 各有四个实例，SceneBuilder 日志确认它们保留为三个 instanced meshes，没有将变换烘焙掉。大型 Mesh 有 66,053 个实际引用的唯一顶点和 393,222 个索引；66,049 个网格顶点位于视野外，随后追加的四个高编号顶点构成整个可见四边形，截断到 16 位会将其错误连接到视野外。SceneBuilder 按三角形第一次使用顺序分配顶点，网格先于可见四边形；测试同时验证实际 Scene vertex_count。原生 draw diagnostics 确认同一 Scene 同时执行 16/32 位索引。每组实例覆盖正面、镜像正面、背面和镜像背面；非均匀缩放同时检验逆转置法线。单面材质背面应被剔除，双面材质背面应翻转着色法线。

解析 oracle 直接由相机和平面方程计算屏幕像素对应的覆盖、世界坐标、反向深度与法线，不使用生产矩阵、Scene GPU 数据或 Decode 输出推导期望值。Packed 材质、模型位、背景清除和保留的 GBufferD 也被检查。

| 验收项 | 实测结果 |
|---|---|
| 解析覆盖 | 30,720 像素完全一致；两个单面背面无覆盖 |
| 反向深度 | 最大误差 0 |
| 世界位置 | 最大组件误差 4.7684e-7 米 |
| 10-bit packed 法线 | 最大组件误差 0.000803693，小于一个存储码值步长 2/1023 |
| 同一图重复执行 | 全部读取输出逐位一致 |
| 拆成三个 BasePass | 全部读取输出逐位一致 |
| 混合索引与强制全部 32 位 | 全部读取输出逐位一致 |

结果保留在 [JSON](ue-legacy-mesh-acceptance-result.json)，包括逐实例计数、两阶段 draw diagnostics、所有输出 hash 和运行时身份。测试启用 D3D12 debug layer，但本脚本不读取 InfoQueue，因此这里不额外声称诊断队列无错误；基础设施队列验证仍以既有独立 capability 测试为准。

初跑先发现测试材料漏填必需的 shading_model；补齐后数值断言均通过，但结果记录的插件路径错误。修正为 `Release/plugins/UELegacy.dll` 后完整脚本退出 0。这两项均为测试配置错误，没有据此修改生产路径。

审查进一步发现初版网格的高编号三角形低于像素尺寸，且没有检查拆分节点的选择集。已改为上述高编号可见四边形，并逐一核验 split Base0/1/2 只提交各自材质的四个实例。补强后的最终脚本退出 0，限定独立复审通过；文档结果副本与实际执行脚本 hash 和 pipeline identity 已核对一致。

## 捕获地板运算顺序

同时完成 [原始 DXIL 只读审查](ue-legacy-rdc-scene/grid-arithmetic-final-review.md)。材质的 inverseGridMask 改成与捕获源码相同的两次减法分组，roughness 原有分组已经正确。该数学仍留在 MaterialProgram，未进入 Schema 生成器。

重新构建、运行实际 RDC GPU 脚本并进行完整 raw 比较后，输出 NPZ SHA-256 仍为 `91b7252c480f1c3262e5032c43bd29db7942df5f55e4093d125e249a1730e8c3`，所有原始字节与修改前相同，见 [完整比较](ue-legacy-rdc-scene/native-grid-association.md)。因此这只是源码分组对齐，没有消除新的残差；尚未用 native IR 判定编译器是否重新结合了表达式。

DefaultLit 仍剩 1 个法线像素、GBufferB 489 个像素、GBufferC 60 个像素不同。B 的 metallic 有 401 个差异像素，最大 +9 码，不经过此次 inverseGridMask 表达式，仍须检查实际采样输入/导数/过滤结果。没有放宽阈值或将这些差异当作相同。

当前仍按基线/Capture → DefaultLit → 实际模型扩展 → Lighting → SSR → TSR → Web 推进。stencil-plane、外部 Scene/纹理身份以及整个后续渲染骨干未完成，最终光照画面尚未一致。
