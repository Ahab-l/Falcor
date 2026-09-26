# 原生 depth/stencil 与材质坐标精度验收

2026-09-09，实施目录 `E:/Project/falcor/Falcor-m0`。本阶段仍属于 **DefaultLit GBuffer 闭环**；Schema 管布局/位域/ID/分派、Shader Codec 管数学的边界保持不变。未完成整个骨干或最终画面对齐。

## 当前原始 Buffer 结果

对 `1.rdc` E1853 的原始附件做完整 allocation 对比，先验证捕获 raw 文件长度和 SHA256。1424×1040 共 1,480,960 像素，其中 866,712 个有效表面像素。

| 数据 | 当前结果 |
|---|---|
| 实际 D32S8 depth plane | 全 allocation 逐位一致，也与 PrePass depthCopy 逐位一致 |
| 实际 stencil plane | 全 allocation 一致；134 共 866,712 像素，0 共 614,248 像素 |
| GBufferA 法线 RGB | 有效表面 866,711 像素完全一致；剩 (341,534) 一个 X 通道码值差异 |
| GBufferA 对象标志 | 全 allocation 一致 |
| GBufferB | Metallic、Roughness、模型/选择位全 allocation 一致；Specular 剩 5 像素，捕获127/原生128 |
| GBufferC BaseColor/AO | 全 allocation 一致 |
| GBufferD | 全 allocation 一致 |
| SceneColor | 有效表面一致；捕获背景包含原生未绘制的引擎警告文字，完整附件不一致 |

剩余 Specular 坐标为 (4,567)、(280,610)、(1060,722)、(1359,882)、(878,930)。没有将一个量化码的差异算成相等，也没有放宽阈值。

独立完整比较：[原始附件报告](ue-legacy-rdc-scene/native-stencil-precision-final.md)。输出已保存为内容寻址快照 `build/rdc-render/snapshots/7ebee38e1c79995a8292517627c917d32a26baf9539983b46e57a1f7bdb8c626.npz`，报告使用快照，避免后续重渲染覆盖证据。

## 实现及根因

`UELegacyReadback.h` 新增项目内诊断回读；使用 D3D12 `GetCopyableFootprints` 查询真实 plane subresource，分别拷贝至 ReadBack buffer，提交并等待 GPU 后按行去除 padding。Python `ueLegacyReadDepthStencil()` 返回实际 depth/stencil 字节。相同 CopySource 状态连续读取仍会提交新 copy。

该接口只支持 D3D12、单 mip/层/采样的 D32S8 Texture2D。它补齐 CPU 原始证据，不代表已经实现 depth-plane SRV、只读深度/可写 stencil DSV 或完整 typeless ABI。

地板材质残差由重建位置最后一次减法的 float32 舍入边界引起。捕获 DXIL 保留非 fast 除法和减法，旧原生 IR 最后是 `fsub fast`。像素 (948,1017) 的实际 Capture 调试和独立 MRT 实验表明，保留减法精度后，相关纹理采样从 0.3017578125 恢复为捕获的 0.26806640625。生产代码将该运算集中到 `ueReconstructWorldPositionUE()` 的 `precise` 结果，Raster 与 Adapter 共用。

修复后，先前 GBufferB 489 个、C 60 个差异减少到 B 的 5 个 Specular 差异、C 完全一致。隐式纹理采样算法保持不变。证据支持舍入边界判断，没有观察到机器 ISA，不能归因于某条特定融合指令；部分原生中间寄存器仍与 RenderDoc 模拟值不同。详细证据：[像素追踪](ue-legacy-rdc-scene/grid-pixel-trace.md)。

Adapter 的新增地板验收进一步发现：精度限定沿依赖向上游传播，使同一 stock 几何在 constant/grid Shader 中算出不同深度。原先 121,706 个深度值不同，最大误差 2.7939677238464355e-9，而输入 posW、coverage、法线都相同。IR 中 constant 的深度路径使用 fast 算术，grid 对应运算非 fast。将所有 Adapter 材质共同的 `clip.z / clip.w` 结果标记 `precise` 后，两种材质的深度、coverage、法线和输入 posW 全部逐位一致。修复前后 JSON/NPZ 均保存在 `build/adapter-evidence`，哈希已入结果清单。

## 验证和身份

- 4 项 UELegacy D3D12 capability 均实际执行并通过。新增 37×19 独立 oracle 检验 depth reject、stencil 写掩码、重复读取、stencil-only clear 保留深度、read/draw/read，以及错误输入拒绝；检查 InfoQueue 的 error/corruption 和日志丢失。
- 最终 `rdc_gbuffer_smoke.py` 退出0；保留源几何对应关系与错误 sidecar 拒绝验收，收紧 Metallic/Roughness/模型位及 C 到全 allocation 精确一致。
- 最终 `adapter_smoke.py` 退出0：实际 stock GBuffer 输入、UE 材质显式映射、Schema-only 迁移、ID0 测试别名、编译失败回滚与混代拒绝继续通过。
- `adapter_view_smoke.py` 在最终深度修复后退出0：origin/inset 输出逐位平移、padding clear、实际 grid 程序执行和材质切换几何不变通过。该测试不宣称 stock 几何路径采样等于 RDC 原始 IA 路径。
- 本阶段 79 项离线测试通过。最终小改动为 Shader 精度及证据保存，相关 GPU 回归已覆盖。
- 原生回读及生产精度 helper 已通过限定范围独立审查；Adapter 诊断的 IR 根因经独立核验。

插件 SHA256 `9ed584df95b6d51a914c86abbe2e86e161dc9de366a062b48710b2c4bf5ff2d8`；Falcor.dll SHA256 `68ddc1613c296091d1a478269156989432c501a92d2c255b81fe1f0ef705a71b`。DLL 哈希不足以表示运行时 Shader，故 [机器结果清单](ue-legacy-stencil-precision-result.json) 同时记录 58 个源码/脚本与 10 个部署 Shader 文件哈希、测试日志和原始证据哈希。四个相关生产 Shader 的部署文件与源码字节一致。Capture SHA256 仍为 `822d41ea6ecb12633f42b18ed5ae1a3e7cea02653c9a72724f6e55e127d85fc9`。

## 后续顺序

继续剩余法线/Specular 原始值诊断和外部 Scene/纹理身份冻结，再进入真实模型扩展 → Lighting → SSR → TSR → Web。ID 别名测试不算实现新模型算法。SSR、TSR、Clustered Lighting 仍须保留目标 UE 算法；对齐该 Capture 最终画面还需 SSGI、DFAO、天空云雾、自动/局部曝光及 ToneMap。自动曝光保持启用。
