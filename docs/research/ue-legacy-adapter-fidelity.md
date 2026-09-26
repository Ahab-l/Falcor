# DefaultLit Adapter 与原始顶点精度

本阶段仍执行用户规定的顺序：冻结基线/Capture → DefaultLit GBuffer 闭环 → 实际模型扩展 → Lighting → SSR → TSR → Web。主管线继续使用 `UELegacyGBufferPass`，没有改成 Falcor 原生 GBuffer。此处的两个新增入口都复用同一生成 Schema 与 Shader Codec。

## 显式 Adapter

`make_adapter_graph(name, props)` 建立 `Native(GBufferRaster) → Adapter → Decode`，另由 Init 提供 Schema 附件清除值、D32S8、depthCopy 和 primaryCoverage。`UELegacyGBufferAdapterPass` 是独立原生插件 Pass。

Native 提供 posW、最终 normW、texC、mtlData 与 vbuffer。项目按 stock material name 显式映射原始 UE MaterialProgram 输入；vbuffer 提供实例 ID，实例标志不会错误地合并为材质标志。Adapter 重新求值 MaterialProgram，然后调用生成的 encodeGBuffer。它不从 diffuseOpacity/specRough 反推已丢失的 UE 参数，不能无损转换任意 Falcor BSDF。

Adapter 输出 Schema 驱动的 Packed MRT、真实反向 D32S8 深度、独立可采样 depthCopy 和覆盖 UAV。Shader 采用晚深度、Always/write=true，背景和其他材质在写入之前 discard。Native normW 已是最终法线，Adapter 不重复翻转背面。主 Mesh 所需的原始顶点 sidecar 不能在原生 GBuffer 已光栅化之后应用，Adapter 对它明确拒绝。

PipelineSignature 纳入 graph kind、Adapter 及递归项目 Shader、Native GBufferRaster 固定配置和 GBuffer 插件基线。`SchemaPipeline(..., graph_kind="adapter")` 使用同样的离屏 stage/commit 与失败回滚。手动修改工厂返回的 stock Native Pass 属性不属于运行时签名校验范围；通过工厂构建的原始配置及冻结重放受校验。

`adapter_smoke.py` 覆盖实际 native outputs、constant/UV 程序、非单位曝光、共享材质但不同实例标志、Packed/Decode/深度/背景、缺失映射/输入/模型拒绝，以及 Schema 槽位/通道/位段迁移、ID 0 别名、混代拒绝和编译失败回滚。ID 别名仍使用 DefaultLit 算法，不是 Unlit 实现。`adapter_view_smoke.py` 使用真实捕获相机验证 ViewRect 位于较大 allocation 内的情况。

## 原始 IA 顶点入口

捕获差异来自两个已验证原因：Falcor PackedStaticVertexData 将法线压为三个 float16，并在顶点阶段归一化；CPU 将 UE 原始坐标烘焙为米、Shader 再还原厘米和使用普通矩阵累加，也会改变裁剪坐标的低位。

`source_geometry.py` 从已校验原始 IA/GPUScene 数据生成 32 字节顶点 sidecar（原始 local position、未归一化 normal、原始材质 UV），并分别保留预计 Scene local position 和 normal 的对应数据。文件名含内容 hash，已有同名文件必须字节一致。Scene 的 texcoord.x 携带原始顶点索引，避免依赖 SceneBuilder 的顶点重排顺序；Shader 读取 sidecar 后恢复材质 UV。

Config 校验绝对路径、长度、SHA1、有限值和索引范围，并保留内存副本。GPU Buffer 从该副本建立。提交前检查实际 Scene position 逐位一致及 normal 的三个半精度组件一致；stock texture transform 和 emissive texture 引起的索引变换/半精度量化被拒绝。SceneBuilder 在加载时烘焙的变换如果改变此对应关系会明确报错，包括位置不变但法线被镜像的平面。运行期实际 Scene global matrix 仍应用到源几何；捕获 identity 情况保留原始 UE float32/FMA 顺序。

该入口读取原始顶点和材质数据，未将捕获 postVS 或 GBuffer 当作渲染输入。postVS 仅用于独立证明：2,828 个 clip 组件与 2,121 个 normal 组件的 CPU 重放逐位相同。相关证明见 [顶点分析](ue-legacy-rdc-scene/vertex-fidelity.md) 和 [后续分析](ue-legacy-rdc-scene/vertex-fidelity-source.md)。

捕获 View 额外保留原始 `SVPositionToTranslatedWorld` 矩阵与 `RelativePreViewTranslation`。地板材质直接按捕获顺序从绝对 SV_Position 还原，避免重新求逆再经过 UV 转换造成的差异。这些数据属于 View/输入指纹，未进入 Schema 布局。

## 数值结果与剩余项

[当前原始 Buffer 比较](ue-legacy-rdc-scene/native-source-final.md) 保留完整区域与内部像素统计，不将误差阈值称为逐位相同：

| 866,712 个有效像素 | 结果 |
|---|---|
| Coverage、反向 depth | 全部逐位一致，原来两个边界深度异常消失 |
| GBufferA normal RGB | 866,711 个一致；剩余球体像素 (341,534) 的 R 相差 1 个 10-bit 码值 |
| GBufferA object data、模型位 | 全部一致 |
| GBufferB | 866,223 个一致 |
| GBufferC | 866,652 个一致 |
| GBufferD | 整个 allocation 逐位一致 |

仍需收敛法线最后一个码值、地板采样/粗糙度、原生 stencil-plane 读取比较、双面/负缩放/混合索引专项和外部纹理/场景资源完整身份。BasePass SceneColor 的捕获背景包含引擎警告文字，原生场景没有这些文字。

启用 D3D12 debug layer 本身不等于已经检查其 InfoQueue。Adapter 调试首次读取诊断队列，发现 Falcor 顶点/索引 Buffer 同时作为 SRV 时存在状态冲突；对应基础设施修复及独立 GPU 回归单独记录，不能沿用旧日志声称没有验证错误。

此冲突现已修复：D3D12 设备本地 IA/SRV Buffer 使用兼容读状态并准确记录进入/退出 UAV、CopyDest 的 native barrier；每次 draw 都检查 IA 状态，绑定缓存继续复用。Vulkan 路径保留原状。`UELegacySharedIABufferReadStates` 使用实际 16/32-bit 索引、重复 GSO、计算写入、copy 写入、同 command list 和 submit 边界以及逐像素整数 oracle，InfoQueue 无 corruption/error；实际 Adapter 图原先的状态错误也已消失。临时诊断 callback 已从插件删除。

最终构建及回归记录见 [阶段结果 JSON](ue-legacy-adapter-fidelity-result.json)。插件 SHA256 `b9570e6a94cd48435883b1bc1194e77a9e5d5bb8f6559890c1aad2af9756d140`：79 项离线、7 组原生渲染脚本、3 项 D3D12 capability 测试均通过。Schema、Adapter/原始顶点入口、D3D12 状态修复均完成限定范围的规格和代码质量审查；没有提交或合并。

最终光照画面尚未一致。目标仍包括实际 UE 模型、Lighting/Clustered、SSR、TSR、Web，以及这次 RDC 激活的 SSGI、DFAO、天空云雾、自动/局部曝光与 ToneMap。自动曝光保留启用，没有以固定显示曝光代替相关算法。
