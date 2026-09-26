# UE Legacy：七模型 GBuffer Codec 验收

2026-09-09。实现工作区 `E:/Project/falcor/Falcor-m0`，分支 `codex/ue-legacy-m0`。本阶段完成七个模型在当前 opaque、无间接光的 GBuffer profile 中的编码与解码，**不是完整多模型 Lighting 或最终 Capture 画面完成**。机器证据见同目录 `ue-legacy-model-codecs-result.json`；本机 UE 源码位置、分支与文件哈希见 `ue-legacy-model-codecs-source.md`。

## Schema 与 Codec 的边界

`Schemas/DefaultLit.json` 保留原 profile；新增 `Schemas/OpaqueModels.json`。Schema 定义附件格式、MRT slot、字段通道与位段、模型 ID、有效字段、Codec 入口和 consumer 需求。生成器产生公共访问与分派，不实现 sqrt、roughness clamp 或八面体法线数学。

新增逻辑字段 `customDataEncoded: float4`，由 Schema 路由至 `gBufferD.rgba`。`models[].constant_overrides` 只能覆盖 Schema 已有常量，Unlit 用它把 skipVelocity 清零；`required_fields_by_model` 允许 Unlit 不承诺法线和 BaseColor。未知字段/模型、重复需求、超位宽或 float32 有限范围的常量、Codec 字段覆盖及不一致能力声明都会拒绝。

材质程序计算原始 UE 属性；Mesh 与 Adapter 绑定相同属性，参数值改变 input fingerprint，不伪造新的材质程序身份。Codec 数学如下：

| 模型 | ID | 独立 Shader Codec 的行为 |
|---|---:|---|
| Unlit | 0 | 保留 emissive SceneColor；A/B/C/D 规范化为零，独立 coverage 保留实际表面 |
| DefaultLit | 1 | 沿用已对齐 Capture 的公共编码，原有数学未改变 |
| Subsurface | 2 | CustomData RGB = sqrt(saturate(subsurfaceColor))，alpha = opacity |
| PreintegratedSkin | 3 | 与 Subsurface 共享这段源码数学，保留独立模型 ID |
| ClearCoat | 4 | 饱和 coat/coat roughness；基底 roughness 上限 254/255 |
| TwoSidedFoliage | 6 | 与 Subsurface 共享 CustomData 编码；后续光照分派独立 |
| Cloth | 8 | 相同颜色编码，alpha 是 cloth weight；不作为 opacity 解码 |

ClearCoat 默认匹配 `r.ClearCoatNormal=0`；独立 `ClearCoatBottomNormal` Codec 变体通过双向 capability 声明启用。它接受已解析的 UE 世界空间底层法线，实现 UE 的 oct 差量编码、a/z 排列、128/255 无自定义输出哨兵与逆变换。切换该变体替换 ID 4 的 Codec，不增加重复 ID。默认 Codec 拒绝底层法线输入。

`Decode.subsurface`、`Decode.coat`、`Decode.coatNormalUE` 用于观察对应语义。最后一个输出的 w 只在启用底层法线 Codec 的 ClearCoat 上为 1，包括无自定义输出的 fallback；Unlit 无有效法线，`normalUE.w=0`。最小 Unlit Schema 可以完全没有 normal/custom 字段。

## GPU 与原始数据证据

512×512 场景由 Falcor 实际 indexed Mesh 绘制，21 个材质、131,712 个覆盖像素；数值参考独立计算几何覆盖、相机、UV、各模型 UE 数学和存储路由。

八组场景全部通过：混合模型、七个模型分拆节点、21 个材质分拆节点、MRT/通道及 B/D 布局迁移、底层法线 Codec、stock GBuffer → Adapter、底层法线 Adapter、最小 Unlit Schema。同图重复执行也保持原始输出不变。

所有场景的五个 Packed 附件、coverage、原生 stencil、原生 depth/copy 均满足各自独立参考的严格相等要求；分拆节点和 Adapter 的 Packed 输出与相同模型 Mesh 输出逐位一致。常规解码误差为零，底层法线最大误差为 `5.960464477539063e-8`。黑色 emissive 的 Unlit 仍保留 6,272 个表面像素，不会按 ID 或颜色误判为背景。

### 独立格式转换探针

首轮测试发现 CPU nearest-even 不能直接预测本机 UNORM 边界：精确 0.5 的 8/10/2 bit 输出为 127/511/1；理想 sRGB 解码也与硬件 SRV 存在允许的差异。依据本地 D3D 规范 §3.2.3.6/7，新增 `UELegacyRTVProbe.h` 的独立 Shader：直接把 CPU oracle 计算的 float 输入写到三个 RTV，并用平行 RGBA32Float 验证输入位保持不变；另上传完整 0..255 字节 ramp，通过独立 SRV.Load 读取 sRGB 转换。

287 个输入的 UNORM 转换表验证端点、单调性和规范的 0.6 code 预算；sRGB ramp 验证原始上传字节和 0.5 code re-encode 预算。模型原始输出不参与建立参考表。**最终 Packed 比较仍是逐位相等，Decode 容差没有放宽**。该探针只用于诊断，不进入主管线或 Codec，也不把本机舍入行为推广为通用规则。

## 回归与审查

131 项离线测试通过；18 项原生测试通过（17 GPU、1 CPU，无跳过）。12 个原生加载反例覆盖非法底层法线、非有限数值、float32 溢出和 JSON bool 等。审查发现并修复了 bool 被数值转换接受、可选法线字段被无条件引用及 Schema 常量 float32 溢出的问题；源码数学、Schema 边界、独立 oracle 与探针另行审查通过。

严格 DefaultLit RDC、Schema 迁移/回滚、Adapter 迁移/回滚、Scene 身份、独立 Scene package 与 Adapter 资源保留回归通过。原始 RDC 的 A/B/C/D、原生 depth/stencil 完整 1,480,960 像素逐位一致，覆盖表面 SceneColor half bits 一致；原始输出 NPZ 仍为 `9bf1802691adbf0e4cbb0aaae86a49dbdb9eb556483c303d482b6f5499878841`。

## 仍待实现

本批是源代码依据与独立 GPU oracle 证明，没有新增七模型 UE GPU Capture。范围限 ordinary opaque、AO=1、无各模型间接/天空贡献的 SceneColor；Cloth 的间接光改动、Profile 资源、Hair/Eye/Water、anisotropy/tangent 及本机 Toon 模型不在本批完成项中。局部 UE 源码的旧 `SelectiveOutputMask << 4` 与五位模型布局不一致，已记录，未修改 UE 原件。

完整骨干仍按冻结基线/Capture → DefaultLit → 模型扩展 → Lighting → SSR → TSR → Web 推进。后续模型所需资源及数学要明确接入；Clustered Lighting、SSR、TSR 必须移植目标算法。最终 Capture 还需要其 SSGI/DFAO、天空云雾、自动及局部曝光和 ToneMap；自动曝光继续保留。Falcor 原生 view/typeless 的既有能力边界也仍保留。
