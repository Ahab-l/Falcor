# Capture DefaultLit Packed GBuffer 逐位一致

2026-09-09，实施目录 `E:/Project/falcor/Falcor-m0`。`1.rdc` E1853 的 **GBuffer A/B/C/D、实际 depth/stencil，在完整 1424×1040 allocation 上逐位一致**。有效表面 866,712 像素，背景及padding 614,248 像素。独立报告：[完整原始比较](ue-legacy-rdc-scene/native-defaultlit-exact.md)；机器证据：[结果清单](ue-legacy-defaultlit-exact-result.json)。

这完成了本 Capture 的 DefaultLit Packed Buffer 数值对齐，不等于整个 DefaultLit 阶段、完整骨干或最终光照画面完成。SceneColor 的有效表面 half bits 一致；捕获背景包含13,062个引擎警告文字像素，完整SceneColor仍不同。

## 本次修复

五个Specular差异来自实际Codec返回值的精度边界。新DebugPixel trace排除了DBuffer修改Specular：输入均为0.5。原生MRT同时观察到真实Codec字段为`0x3f001000`，独立复制算术链为`0x3f000fff`，后者与Capture调试最终值相同。对诊断Codec最后的bias加法保留`precise`后，真实字段变为`0x3f000fff`，实际B字节也全部匹配；其余附件不变。随后相同改动进入生产Codec。

理想UNORM公式会把这两个候选值都量化为128，因此不能用它解释真实GPU的127/128分界。本次修复依据实际MRT和全allocation对比，不宣称识别了驱动的具体融合指令或输出转换实现。证据：[五点追踪与独立实验](ue-legacy-rdc-scene/specular-quantization-traces.md)。

法线的单点差异是漏掉了本Capture执行的identity DBuffer法线归一化。捕获中DBufferB使用默认normal纹理，解码法线增量为0、opacity为1，但UE的ApplyDBufferData仍执行normalize。生产实现新增显式`dbuffer: {"mode": "identity"}`，默认disabled；仅当primitive接收decal的flag8及材质`decal_response_mask`的normal位2都启用时，才在MaterialProgram之后、Codec之前应用。Raster和Adapter共用同一个Shader函数。

当前只支持disabled/identity，未知模式及额外纹理参数被拒绝；没有实现实际decal纹理生产和采样。模式表示上层已选择启用DBuffer及显示decal，不从数值残差推断是否启用。材质响应掩码默认7，可设置0–7。代码依据：[DBuffer源码与捕获分支](ue-legacy-rdc-scene/identity-dbuffer-source.md)。

## Schema 边界和验证

Schema布局、物理通道、位域及模型ID未修改。精度改动属于Codec数学；DBuffer属于材质修饰步骤。默认generation更新为`cee97e8b24948a570d3ce8398172fea557966a92040e27c1ee08e8c55d525ea1`。Layout与Codec仍分开计算，生产者、Decode和Adapter消费同一代契约。

- 严格RDC验收先失败再通过；当前直接断言完整A packed word、B/C/D所有字节、实际depth位和stencil全allocation一致，以及有效表面SceneColor half bits。比较器报告不承担代替这些断言的职责。
- identity DBuffer实际GPU门控通过：Mesh的一个packed法线像素发生预期变化；关闭mode/receiver/normal response恢复原值，normal-only response保持启用结果。Adapter原10位量化不足以观察额外归一化，测试通过Schema将同一法线字段移到RGBA32Float，观察到1,565像素变化，门控关系相同。其余Buffer和深度逐位不变；6个非法输入拒绝。
- Schema-only MRT/通道/模型位迁移通过，无需重编C++，117,087个覆盖像素逻辑输出逐位不变；ID0测试别名、编译失败回滚、混代拒绝和废弃pending检查通过。测试别名不算新增UE模型算法。
- Adapter原生映射、布局迁移/回滚和ViewRect/grid回归通过。79项离线测试通过。同轮前一阶段的4项原生D3D12 capability通过，相关能力代码未再修改。
- 诊断重放能重新产生保存的修复前输出，原始实验文件未被覆盖。生产代码通过限定独立审查；审查发现的完整A/D/depth断言缺口已补齐并重跑通过。

最终插件SHA256：`37e2d7a51d942c3cab29a210cde6f74f071c2521022a680f7daa2a88b58a0da8`。最终NPZ保存为内容寻址快照`build/rdc-render/snapshots/9bf1802691adbf0e4cbb0aaae86a49dbdb9eb556483c303d482b6f5499878841.npz`。结果清单同时记录源码、部署Shader和日志哈希；部署目录中保留的旧`Generated/GBuffer.slangh`也单独标识，当前路径使用经过验证的generation内存源码。

## 下一项

继续冻结外部Scene/纹理完整身份，并保留原生view/typeless能力边界，然后进入真实模型扩展 → Lighting → SSR → TSR → Web。SSR、TSR、Clustered Lighting继续保留目标UE算法；对齐最终Capture还需SSGI、DFAO、天空云雾、自动/局部曝光及ToneMap。自动曝光保持启用。
