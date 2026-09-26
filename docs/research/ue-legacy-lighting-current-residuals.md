# 当前 31 个 Lighting 残差的 GPU 取证

2026-09-09。当前生产 Shader 未作新的数学修改，严格 HDR 仍有 31 个像素各差 1 half ULP。新增证据表明：**这些残差点的 ScreenVector 初始输入均逐位匹配，而混合前的 float32 Shader RGB 均至少有一个不同分量。** 下一步继续定位 PS 运算和中间值；这不是 Lighting 验收通过。

## 原生 Shader 输出观察

`production_lighting_radiance_smoke.py` 重放已冻结的正常生产图，再复制相同 Shader，仅将 `directTransmission` 诊断 MRT 改写为曝光后的 `radiance`。生产 Shader、Schema、Codec 和渲染输入没有修改。两个图独立保存 NPZ；各自的 12 个未改输出，包括 HDR、Packed、depth/stencil、diffuse/specular，在全 allocation 上与已冻结生产输出逐位相等，正常图的原始 transmission 也一致。

实际 [原生结果](E:/Project/falcor/Falcor-m0/build/production-lighting-radiance-evidence/run-kp26g_ki/result.json) 记录运行时 Pipeline、Scene 和 Shader 来源。展开后的源码只多这一处诊断写入，其余 Shader、Schema、输入指纹、Scene 和恢复后的 Pipeline contract 相等。独立审查复核了所有数组及文件哈希。该等价性限制了插桩的影响，但不能作为运行时 Shader 二进制逐字节相同的证明。

诊断 NPZ 的 `directTransmission.rgb` 是混合前的曝光后光照值，**不是物理 transmission**。这些数据不回填任何渲染输入。

## UE PixelHistory

先冻结当前全部 31 个残差点、4 个固定探针和 8 个确定性控制点，共 43 点。该[采样计划](E:/Project/falcor/Falcor-m0/build/rdc-lighting-pixel-history-31/selection-plan.json) SHA256 为 `03c6312cf5cdb7edee4299c5f3957f161012458a8a33adcf6008bc71c5fab1fb`，没有按实验结果重新挑点。

只读 RenderDoc [回放比较](E:/Project/falcor/Falcor-m0/build/rdc-lighting-pixel-history-31/replay-bd2puocf/comparison.json) 取得实际 GPU PixelHistory。每点为一个有效 raster fragment，preMod/postMod 分别与原始 E2624/E2655 half 附件位型核对通过，RDC 前后 SHA256 不变。没有使用 DebugPixel 解释器计算 BRDF。

| 采样组 | 点数 | RGB 三分量全相同的点 | 相同 float32 分量 | 最大 float32 ULP 距离 |
|---|---:|---:|---:|---:|
| 当前 HDR 残差 | 31 | 0 | 48 / 93 | 5 |
| 固定探针 | 4 | 4 | 12 / 12 | 0 |
| 原本 HDR 相同的控制点 | 8 | 5 | 21 / 24 | 1 |
| 全部 | 43 | 9 | 81 / 129 | 5 |

31 个残差点的 RGB 分量中，48 个相同，33 个差 1 ULP，6 个差 2 ULP，3 个差 3 ULP，2 个差 4 ULP，1 个差 5 ULP。最大差异点为 `(966,1015)`，RGB 距离为 `[4,4,5]`；`(880,701)` 为 `[3,3,3]`。不能用相同 HDR 的控制点推断其所有 float32 计算相同。

PixelHistory 的 shaderOut 来自插桩 GPU 回放，不是原始命令输出的额外 float32 附件。CPU `float16(before + radiance)` 只在 43 点中的 5 个原生点、7 个 UE 点完全复现各自硬件 RGB 混合结果，因此没有把这个 CPU 预测作为混合的正确性 oracle。

## 补齐当前残差的初始输入

原先冻结的 41 点中，只有 18 点属于当前 31 个残差。因此不能直接把旧的 41/41 输入证明扩展为当前所有残差的证明。

新增[输入比较](E:/Project/falcor/Falcor-m0/build/rdc-current-lighting-inputs/run-s46woryu/comparison.json) 对同一 43 点复用 24 个已有 UE 初始输入，补采 19 个（13 个新残差点、6 个控制点）。原生值来自先前已证明 12 个未改输出相等的全 allocation ScreenVector NPZ；仅读取新 UE `DebugPixel` 的初始 `trace.inputs`，不执行 `ContinueDebug`。

最终 **43/43 输入向量、129/129 分量逐位一致，其中包含全部 31 个当前残差点，最大 ULP 距离为 0**。这个证明仍限于选定点和插桩回放输入，不能代表整幅图像或未插桩插值位型。

工具 `build/extend-current-lighting-inputs.py` 生成新的冻结 worker，仅将旧 worker 的残差计数检查从 29 改为 31，没有改原文件。首次启动因 launcher 使用错误环境变量而未完成取证，所属 qrenderdoc 进程经确认后被定向终止；失败目录 `run-d4b_pwqa` 保留，RDC 哈希不变。修正为 worker 实际要求的 `UE_SCREEN_VECTOR_RUN` 后，新目录 `run-s46woryu` 完成；失败运行不计作证据。

## 结论边界与后续

当前证据足以将全部 31 个选定残差点的 ScreenVector 值差异排除出已观测差异链；这些点在混合前已有 Shader RGB 差异。尚未证明差异出自哪一个具体 PS 操作，也未证明未采样像素或最终硬件混合完全等价。后续核对实际运行 Shader 与目标指令顺序、解码/归一化、Area/BxDF 中间值，保留 UE 数学和精度边界，不以降低残差数来挑选公式。

主计划任务 4–6、更多模型 BxDF、原生阴影/GI、Clustered、SSR、TSR、Web 以及最终画面仍未完成；自动曝光要求保留。

本批数值观察的 [独立归档](E:/Project/falcor/Falcor-m0/docs/research/ue-legacy-lighting-current-residuals-result.json) 保存 55 条文件记录，并复核父级输入/Schema 归档的全部 1,037 个 CAS 文件；原始 RDC 只校验哈希，不复制或修改。归档脚本重新计算原生 12 输出、43 点输入与 PixelHistory 比较，明确保持 `capture_equivalence=false`，不把观察完成作为算法验收。
