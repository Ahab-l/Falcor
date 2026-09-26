# 原生 depth/stencil 平面验收

继续已批准的 DefaultLit 原始 Buffer 闭环；不改 Schema 位布局、Codec 数学或实施顺序。

1. 项目内增加只支持 D3D12、单层单 mip 单采样 D32S8 Texture2D 的诊断回读。查询 native footprint，按真实 plane subresource 拷贝，等待 GPU 后去除 row padding。不依赖 stencil predicate 重建数据。
2. 独立 GPU capability 使用非256对齐宽度、多个已知 stencil 值、depth reject、写掩码及连续 read/draw/read 检验回读；读取 InfoQueue 拒绝 error/corruption 和日志丢失。
3. Python 诊断接口读取实际主 BasePass 深度附件，NPZ 保存原始 float32 depth 与 uint8 stencil。和不可变捕获输出逐像素比较，记录完整 allocation、ViewRect/背景等差异。
4. 若证据暴露渲染问题，先找根因再修复；不能把现有输出或由其推导的值当作期望模板。同步报告和进度。

该入口只用于 CPU 证据回读，不表示已提供 depth-plane SRV、只读深度/可写模板 DSV 或全部 typeless ABI。

## 2026-09-09 完成记录

步骤1–4已实施并验证，见 [原生平面与精度报告](../../research/ue-legacy-stencil-precision.md) 和对应结果 JSON。4项D3D12能力测试通过，其中新增37×19独立平面oracle；真实RDC depth/stencil在1,480,960像素完整allocation逐位一致。NPZ使用内容寻址快照保存。

同时依据实际Capture像素trace修复重建位置减法精度，C、Metallic、Roughness全部一致；Adapter补验揭示并修复材质变化引起的深度精度传播。Schema/Codec职责未变。DefaultLit仍有1法线/5Specular像素差异，后续模型和光照等未完成。
