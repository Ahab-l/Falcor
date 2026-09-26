# 原生 GBuffer Adapter 与捕获精度

**目标：** 在保持用户六项架构要求的前提下，将 Falcor 原生 GBuffer 的几何/材质身份显式接入同一 Packed UE 契约，并继续收敛实际 RDC 的数据差异。此前一轮属于实质进展：完成 Mesh/整图事务与真实捕获场景、五组 GPU 验证；本轮没有活跃 GPU 进程需要等待。

**已授权设计的具体化：** 主路径仍是 UELegacyGBufferPass。Adapter 是独立 RenderPass，不让消费者猜测输入格式。Falcor 的 diffuseOpacity/specRough 是计算后的 BSDF 属性，不充当 UE raw BaseColor/Metallic/Specular。Adapter 使用 GBufferRaster 的 posW/normW/texC/mtlData 和 vbuffer，在显式 UE 材质映射下重新求值 MaterialProgram，经相同 Schema/Codec 产生 Packed MRT、UE depthCopy 和 coverage。缺失映射、不支持的模型/输入明确报错。这是可验证的几何/身份适配，不能宣称能恢复任意 Falcor 材质丢失的 UE 参数。

## 实施步骤

- [x] 读取原生 GBufferRaster/GBufferHelpers/HitInfo 实际格式与字段语义；写 adapter 的 GPU 红测试：当前没有 UELegacyGBufferAdapterPass，创建失败。
- [x] 新建 UELegacyAdapter.h/.cpp/.3d.slang。全屏绘制按 stock MaterialID 筛选像素，绑定 UE 材质实例；写入相同生成 UEPacked。深度由 world position 与目标 UE View 推导，背景保持 Init clear。instanceID 来自真实 vbuffer，primitive flags 路由一致。原生 normW 是最终世界空间法线，不再当作切线空间法线。
- [x] 注册/构建插件；新增明确 make_adapter_graph 工厂，将 Native GBuffer → Init/Adapter → UE Decode 接线。PipelineSignature 纳入 adapter 源码、图类型和原生 GBuffer 配置；节点身份校验涵盖 Adapter。
- [x] GPU 验证 constant/UV、两个模型注册 ID（算法仍 DefaultLit）、非单位曝光、原始附件与 Decode；与主 Mesh 管线比较内部像素几何/原始值，分别记录原生输入量化误差。修改 schema 的 slot/channel/bit 后 Adapter 与消费者保持同代，缺映射/混配拒绝。
- [x] 独立分析捕获法线与两个边界差异：检查 Falcor 的 PackedStaticVertexData 压缩、UE 原始 SNORM 顶点、原始局部变换及 CPU 米↔厘米转换。用原始几何/属性改善，禁止读取捕获 GBuffer 作为渲染替代输入。
- [x] 按变化范围构建并运行现有 M1/Schema/路由/整图回归；保留错误分布与历史证据，不以放宽阈值代替修复。更新阶段状态，随后继续模型扩展与 Lighting。

实现仍在 E:/Project/falcor/Falcor-m0；UE、原工程和 RDC 只读。自动曝光启用，离线固定实测 preExposure 只用于捕获阶段复现。没有提交/合并要求。

## 本阶段验收结果

最终插件 SHA256：`b9570e6a94cd48435883b1bc1194e77a9e5d5bb8f6559890c1aad2af9756d140`。79 项离线、7 组 GPU 渲染脚本、3 项 GPU capability 测试均通过；原始 Capture 证据 hash 仍通过。额外修复了 D3D12 IA/SRV 同时读取的状态冲突，独立 InfoQueue 测试覆盖实际写入及提交边界。规格和代码质量审查通过限定范围。

持久结果：`docs/research/ue-legacy-adapter-fidelity-result.json`；数据误差：`docs/research/ue-legacy-rdc-scene/native-source-final.md`。上述步骤完成表示本阶段的 Adapter、原始 IA 精度改善和回归完成；不是全部 M1 或最终图像等价完成。继续当前计划剩余的 DefaultLit 数值/能力项，再按用户顺序进入真实模型扩展与 Lighting。
