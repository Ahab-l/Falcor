# E2655 Lighting 的 ScreenVector 输入取证

2026-09-09 当前状态：已将实际 UE 顶点流程接入生产 Lighting，41 个预先选定的 PS ScreenVector 输入全部逐位一致，123 个分量最大 float32 ULP 距离为 0。严格 Capture 验收仍未通过：最新 HDR 有 31 个像素/31 个通道各差 1 half ULP。下文先保留修复前 29 个残差版本的历史取证，再记录候选和生产回归；不可将旧残差数作为当前结果。

## 历史：修复前的观察结果

固定采样由29个生产残差点、4个固定点和8个控制点组成，共41点。原生Falcor仅将复制Shader的 `directTransmission` 诊断MRT写入替换为 `float4(input.screenVector, 1)`；同一场景、Schema、输入指纹及其余Shader均校验不变。全分配范围内的12个未改输出，包括Packed、depth/stencil、HDR和diffuse/specular，与冻结生产版本逐位一致。

UE的2点复用已有调试记录，39点由只读RenderDoc回放取得。仅读取 `DebugPixel` 返回的初始 `trace.inputs.TEXCOORD1`，没有执行 `ContinueDebug` 或使用解释器的BRDF中间结果。RDC前后SHA256一致。这些输入来自RenderDoc插桩回放，不是对未插桩插值位型的独立证明。

41点的ScreenVector均至少有一个分量不同，123个分量中52个逐位相同。最大绝对差为 `2.384185791015625e-7`，最大float32 ULP距离为90，后者位于(666,417)的接近零的z分量。三个分量最大绝对差分别为 `5.960464477539063e-8`、`5.960464477539063e-8`、`2.384185791015625e-7`。

差异在控制点也存在，因此不能把“输入不同”直接解释为29处HDR残差的全部原因。下一步先独立核对原生VS输出与实际UE三角形，再检查插值与BRDF运算顺序。没有按残差数量选优或把目标像素值作为渲染输入。

## 顶点运算的CPU复现

实际UE IA是(1,1)、(-1,1)、(1,-1)，ViewSize为1421×1035，分配尺寸为1424×1040。实际PostVS的单位边界为 `0.9999999403953552`，不是数学上的1。

读取实际VS常量，将 `2 * InvViewSize` 先舍入到float32，再对 `scale * (IA * ViewSize) - 1` 做单次融合乘加舍入，可复现全部6个实际clip.xy分量；分步乘法/减法只复现2个。这个CPU实验说明融合舍入与实际结果一致，尚未证明原生Falcor顶点或插值已对齐。

## 原生VS验证的后续结果

新增三个固定GPU探针，通过VS向原生Lighting已绑定的诊断UAV写入执行标记、三个顶点的seen位及15个分量的差异位。生产表达式RED返回 `0x00ffffe0`；UE流程候选返回 `0x00f00000`，表示3个顶点均执行、clip.xy和screenVector.xyz的15个分量全部一致；故意只改错vertex0 clip.x参考一位的负例返回 `0x00f00020`，准确报告该差异。原有PS错误位均为0。

这是原生VS执行时的相等性位图验证，没有读取整份原始PostVS输出，也不验证UV或PS插值。参考顶点位型只参与比较，不构造Shader输出；该历史候选将实际捕获的InvViewSize作为诊断参数，当时生产实现尚未接入该流程。三个探针的PS/BRDF源码保持不变，未按HDR残差数选择变体。

冻结[VS探针计划](E:/Project/falcor/Falcor-m0/build/rdc-vs-input-proof/plan.json)与[GPU验证结果](E:/Project/falcor/Falcor-m0/build/rdc-vs-input-proof/native-run-0qkmht5k/done.json)。后续成对候选在 `build/rdc-candidate-ps-proof/native-run-suhoe2b7/done.json` 证明 12 个未改输出相等、41 个 PS 输入全部匹配。这些历史探针只适用于各自冻结源码与运行时身份。

## 当前：生产接入与输入回归

生产 VS 采用捕获 IA 的顶点顺序、由 ViewRect 尺寸与运行时倒数计算 clip 的融合乘加，以及先 x 乘法、再 y 融合乘加、最后加常量项的矩阵计算。`UELegacyLightingPass` 上传 `gInvViewSize = 1 / ViewSize`，Config 和资源冲突负测保留该绑定名。生产没有捕获专用倒数、clip 或 ScreenVector 常量。

`initPS` 至文件末尾的 7,385 字节没有变化，18 份 Codec 与 2 份 Schema 也没有变化。生产 Shader SHA256 为 `e307672ef52185b2f1a40c7bfb0e5e62bd632a8189e5bc643aa65327dcf36239`。

最终 [生产回归](E:/Project/falcor/Falcor-m0/build/production-lighting-input-evidence/run-1uao0dw5/result.json) 校验了候选 VS 全文与生产参数化版本的对应关系；脚本 SHA256 为 `9441f1ef6a846619ea50cf5b47fe856eca1eda5ad1fffa0c217b44f7c1eb286a`。正常图和只输出 ScreenVector 的诊断图之间，全 allocation 的 12 个未改输出逐位相等；原先冻结的 41 个采样输入全部匹配 UE 初始调试输入。该结论限于这些样本，不是全图插值位型证明，UE 参考仍来自插桩回放。

同一次正常生产图的 [严格 HDR 报告](E:/Project/falcor/Falcor-m0/build/production-lighting-input-evidence/run-1uao0dw5/normal/lighting-result.json) 仍失败：RGBA 分别有 `[13,8,10,0]` 个通道不同，总计 31 个像素，每处 1 half ULP，最大绝对差 `0.0009765625`。所有值有限，上游 Packed/depth/stencil/覆盖及 BasePass 表面 HDR 保持一致。输入测试退出 0 只表示这个有界输入测试通过，不能覆盖内嵌的 Capture 失败状态。

剩余工作为 PS 数学和实际 GPU 中间值取证，不按残差数量选择公式。完整阶段与 Schema 非零灯迁移见 [当前报告](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-view-inputs.md)。

后续单独取证已对当前 31 个残差及控制点共 43 点补齐初始输入，43/43 ScreenVector 逐位相同，其中包含全部 31 个残差；同点 PixelHistory 显示残差点混合前 RGB 仍有差异。详见 [当前残差调查](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-current-residuals.md)。这不改变本节原有 41 点回归的冻结身份或 Capture 失败状态。

## 冻结证据

- [采样与源身份计划](E:/Project/falcor/Falcor-m0/build/rdc-screen-vector-29/selection-plan.json)，SHA256 `c0753e24bf69758daf9c9e1c59f61607b0cdbb43b5b67c4eaf83fe2e3e8b541d`。
- [原生观察结果](E:/Project/falcor/Falcor-m0/build/rdc-screen-vector-29/native-run-xn9np2d7/done.json)及[原始输出](E:/Project/falcor/Falcor-m0/build/rdc-screen-vector-29/native-run-xn9np2d7/outputs.npz)。`screenVector`键对应临时诊断MRT。
- [UE回放记录](E:/Project/falcor/Falcor-m0/build/rdc-screen-vector-29/ue-run-p842gndl/done.json)及[39点输入](E:/Project/falcor/Falcor-m0/build/rdc-screen-vector-29/ue-run-p842gndl/inputs.json)。采样计划另引用2点缓存输入。
- [完整41点比较](E:/Project/falcor/Falcor-m0/build/rdc-screen-vector-29/comparison-zd6ig9_b/comparison.json)。这里的 `status=complete` 仅指完成采样比较，不表示输入相同、Lighting或整个目标完成。
- [CPU clip舍入实验](E:/Project/falcor/Falcor-m0/build/rdc-lighting-clip-arithmetic.json)及[复现脚本](E:/Project/falcor/Falcor-m0/build/check-ue-lighting-clip.py)。

工具为 `scripts/ue_legacy/screen_vector_evidence.py`、`screen_vector_native_smoke.py`、`_screen_vector_replay.py`，其哈希记录在采样计划内。这批诊断与受控Lighting验收归档分开记录，后续修改不能覆盖本轮冻结计划或既有运行目录。
