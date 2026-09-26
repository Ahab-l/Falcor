# 参考场景资源冻结与原生身份验收

2026-09-09，实施目录 `E:/Project/falcor/Falcor-m0`。本阶段完成了当前静态 RDC 参考场景的文件资源冻结、独立场景包和运行时 Scene 身份校验。DefaultLit 的 Packed GBuffer 数值闭环保持逐位一致。机器证据见 [结果清单](ue-legacy-resource-identity-result.json)。整个渲染骨干与最终光照画面仍未完成。

## 与 Schema 的关系

Schema 继续管理附件格式、slot/channel、位布局、ShadingModel ID、字段及路由，生成公共定义和分派；Shader Codec 继续管理各模型的编码、解码数学。生产者、Decode、显式 Adapter 共用 generation。Lighting、SSR 等后续消费者接入这一 Packed 契约。

本阶段没有修改 Schema 布局、Codec 或材质程序算法。默认 generation 仍为 `cee97e8b24948a570d3ce8398172fea557966a92040e27c1ee08e8c55d525ea1`。本次新增的是 Pipeline 输入与实际 Scene 之间的可验证绑定。

## 已实现的边界

- `resource_snapshot.py` 将材质 `grid_texture` 和三类 `source_geometry` sidecar 复制到内容寻址目录，重写路径并记录字节数、SHA1、SHA256。Python 验证精确 JSON pointer 登记集合及两种哈希；原生 Config 验证完整 pointer 集合、字节数和 SHA1，并在纹理文件载入前后再检查。
- `scene_package.py` 保存四个 NPZ、DDS、12 个 sidecar、manifest、原始定义、原始 loader、生成模板及包内入口。旧输入文件改变或消失后仍能独立加载。已冻结定义的旧 `resource_files` 先验证，再从运行定义移除，由 Pipeline 根据包内路径重建；原始字节保留在 provenance。包使用绝对路径，迁移目录需重新发布。
- `ueLegacySceneIdentity()` 读取实际 GPU 顶点/索引，以及材质和环境纹理所有 mip、array layer、cube face 的内容。实例变换、材质有效字段、采样器、相机输入与当前 view/projection、analytic light、环境参数进入规范化身份。材质/灯光 padding 不参与，纹理和采样器的运行时表索引不参与。
- 定义中的可选 `scene_identity` 将身份纳入 Pipeline 输入指纹。严格参考图的 Init 在清理任何输出前检查当前 Scene；改变输入须重新绑定。普通未绑定图保持普通行为。调用者需先完成 Scene 同步，再绑定参考帧。
- 已准备的 Mesh/Adapter 持有载入资源。Adapter 在材质 dirty flag 或 Scene 映射刷新时保留其不可变项目纹理；新图仍拒绝缺失或损坏的快照资源。

## 验证及修复证据

102 项离线测试通过；18 项原生测试通过，包含 17 项 GPU、1 项 CPU，零跳过。新增回归先复现了持久相机矩阵漏检、相机延迟更新混入旧值、材质/灯光 padding、Uniform texture handle 残留 ID、cube 尾面漏检、共享文件引用登记缺失；修复后全部通过。真实 16/32 位 VB/IB、采样器、纹理 mip/layer 修改与恢复均纳入测试。

实际场景 GPU 验证覆盖相机、材质、纹理变换、GPU 纹理第 0/9 级 mip 内容变化，以及实际几何的独立重载。失配时 A/B/C/D、SceneColor、coverage、depthCopy、原生 depth/stencil 全部原始字节保持不变；恢复后复用原图成功。

独立场景包验收先破坏并删除专用临时源输入，再从包加载；第二次独立加载分别复用旧 graph 和旧 Pipeline 创建的新 graph。三次渲染 A/B/C/D、depth/stencil 全 allocation、表面 SceneColor 与指定参考快照逐位一致，后两次的全部输出与第一次逐字节相同。实际包 ID 为 `e5d84e8d0d040ac3985979f50df4841d4c753bf3b1209f3695ff1c371e205fb5`，持久入口记录在结果清单中。

Adapter 专项仅删除测试自己的临时 CAS DDS，确认旧图经材质修改/恢复后仍能渲染，18 个输出保持原始字节一致，新图拒绝损坏快照。用户原始资产、UE 工程与 RDC 未被改变。

压缩纹理测试发现 Falcor/gfx 回读小于压缩块的 mip 尾部会退出。D3D12 压缩纹理现在用 `GetCopyableFootprints` 和整子资源 `CopyTextureRegion`，按原生行跨度去除 padding，并沿用队列/fence 同步。实际十级 DDS 和独立 BC4 的 4×4、2×2、1×1 原始块 oracle 均通过。非压缩纹理及 Vulkan 原路径保持原有行为。

最终重跑 Schema-only 布局迁移、模型测试别名分派、编译失败回滚、混代拒绝及 Adapter 契约回归均通过。严格 RDC 验收仍得到同一个 NPZ：`9bf1802691adbf0e4cbb0aaae86a49dbdb9eb556483c303d482b6f5499878841`。完整 1424×1040 的 A/B/C/D、实际 depth/stencil 与 Capture 逐位相同；有效表面 866,712 像素的 SceneColor half bits 相同。

本阶段通过独立规格与代码质量审查。源码、运行时及验证日志哈希在结果清单中；插件为 `8fd87f82a77e2ba3abc821c19a5008454a0080160c1917ea21a4c3e82c44df80`，Falcor.dll 为 `f0f0fd228faf58b832ff4013e50432d44eacf05c440e78376fda22e68879e0e1`。

## 支持范围与下一阶段

严格身份当前覆盖完成同步的静态、未位移三角形与 StandardMaterial carrier。其他材质的 sideband、UDIM/profile、skinned/dynamic/displaced、curves/SDF/custom/grid volumes 明确拒绝。它不是任意 Falcor Scene 的全状态快照，也不提供动画/时间历史或并发 GPU 写入下的原子快照；每次校验执行多次同步 GPU 回读，性能成本很高。Falcor/Python/Shader import 运行时仍属于已记录的外部基线。

完整 SceneColor 仍缺少 Capture 背景中的引擎警告文字，后续光照/最终图像尚未对齐。typeless、readonly DSV、depth-plane SRV 的原生能力边界继续保留到相应消费者接入前验收。当前资源阶段不代表这些能力已经完成。

下一阶段按权威顺序进入实际 Shading Model 扩展，然后 Lighting → SSR → TSR → Web；模型测试别名不计作算法实现。Clustered Lighting、SSR、TSR 保留目标 UE 算法。最终 Capture 对齐还需要其 SSGI/DFAO、天空云雾、自动/局部曝光与 ToneMap，自动曝光继续启用。
