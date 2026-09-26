# M1 第一条真实 Mesh Pass 路径

2026-09-09。实现位于 `E:/Project/falcor/Falcor-m0` / `codex/ue-legacy-m0`。**真实 Packed BasePass 已运行通过；完整 M1 和骨干 v1 尚未完成。**

## 已执行的代码

`Source/RenderPasses/UELegacy/` 注册四个实际 Pass：

- `UELegacyInitPass`：按生成 Schema metadata 初始化 MRT（默认 profile 为五个）、D32S8 和独立 R32Float depthCopy。
- `UELegacyPrePass`：Scene 公共 API、CPU 逐实例提交真实 mesh draw，自有无限远 reversed-Z 投影，写主深度及副本。
- `UELegacyGBufferPass`：CPU 材质筛选，保留 instanceID、16/32 位索引与绕序；constant/UV 各有独立 Program/Vars/PSO，原始 UE 参数经统一 codec 打包；GreaterEqual、depth-write=false、stencil ref86/maskF6。多个节点共享一次初始化的附件。
- `UELegacyDecodePass`：共享 codec 解包 UE 轴 normal、BaseColor、Metal/Spec/Rough/ModelID，从 depthCopy 重建 Falcor 米制位置；有深度的未知模型输出显式诊断。

蓝/红参数实例共用常量程序，地面另用 UV 程序；都写 DefaultLit=1。材质不使用 stock BSDF/半精度参数；emissive 乘显式 PreExposure，普通 GBuffer 属性不乘。`generate_schema.py` 从独立运行时 Schema 生成字段存储与模型分派；各模型数学位于 Shader Codec。Capture profile 保留为参考证据。详见 [Schema 运行时闭环](../ue-legacy-schema/README.md)。

## 实测

RTX 4090 / D3D12、640×360，开启 D3D12 debug layer，`scripts/ue_legacy/m1_smoke.py` exit 0，结果快照见 [first-path-result.json](first-path-result.json)。原始数据及图像在 `build/m1-evidence/`。

| 验证 | 结果 |
|---|---|
| CPU 射线与 GPU | 426 内部命中点（蓝39/红49/地面338）、437背景点 |
| 世界位置最大误差 | 5.06126e-5 m，约 0.051 mm |
| normal 最大分量误差 | 0.000977517，符合 UNORM10 预算 |
| 反向深度最大误差 | 1.00193e-7 |
| 单 BasePass vs blue / red+gray 两节点 | 所有 packed/decoded/depthCopy 逐位一致 |
| 默认16位 vs 强制32位索引 | 所有输出逐位一致，diagnostics 确认两类索引均实际提交 |
| CPU 筛选 | 并集实际3 draw，分区1+2 draw；未选对象不提交 |
| 材质/codec | B 字段、精确模型字节129、C sRGB/线性alpha、UV颜色及半精度自发光/曝光通过 |

首轮 oracle 误用 nearest-even 假设，失败日志为 `build/m0-evidence/m1-first-smoke.log`。D3D functional spec §3.2.3.6 允许 FLOAT→UNORM 误差0.6整数ULP，所以0.5可写127或128（原UE捕获也有两者）；模型字节仍要求精确。§3.2.2 的 float 降精度要求向零舍入，RGBA16F自发光现用独立CPU RTZ oracle精确比较。未修改源材质常量来迁就测试。规范：<https://microsoft.github.io/DirectX-Specs/d3d/archive/D3D11_3_FunctionalSpec.htm>。

## 未完成项

**Schema 基础闭环已实现：** 独立布局/bit/模型注册、Shader Codec、生成公共接口、metadata 驱动 MRT、整图 generation 与编译失败回退已通过 GPU 验收；详见 [Schema 运行时闭环](../ue-legacy-schema/README.md)。完整路由、PipelineSignature、Adapter 仍需补齐，再按“扩展模型→Lighting→SSR→TSR→Web”推进。第一条路径的通过不代表六项核心要求全部完成。

- 完整 mesh/model/tag/passmask 过滤、优先级/默认路由/冲突检测；持久 draw 队列与 PSO 排序。
- 负缩放/双面专项 GPU 验收、同一次绘制中的 mixed-index 场景；目前两种索引宽度分别已测。
- 完整 PipelineSignature 和原生 Falcor GBuffer Adapter。同步 frame-boundary Schema staging/commit 已验证；自动文件监视和后台编译尚未实现。
- 原生 typed/typeless、readonly DSV 和 D32S8 plane SRV 差异继续披露；副本没有替换主 D32S8。新配对 UE GPU capture 仍待补。
- 目前仅 opaque DefaultLit、AO=1、静态/刚体 indexed triangle；其他程序/模型、AO<1、dynamic/skinning/displacement/非opaque输入明确拒绝。AO multibounce尚未移植。
- M2光照、M3history/velocity/HZB、M4masked/纹理/CSM/天空未实现。BaseColor图是真实packed解码预览，不是最终光照画面。

## 复现

在实现 worktree 中运行，复用 M0 的工具链与隔离 NumPy：

```powershell
& .\tools\.packman\python\python.exe scripts\ue_legacy\generate_schema.py
& .\tools\.packman\cmake\bin\cmake.exe --preset windows-vs2022 -DFALCOR_ENABLE_USD=OFF -DCMAKE_CUDA_COMPILER=NOTFOUND
& .\tools\.packman\cmake\bin\cmake.exe --build build\windows-vs2022 --config Release --target UELegacy --parallel 8
& .\build\windows-vs2022\bin\Release\Mogwai.exe --headless --device-type d3d12 --gpu 0 --script scripts\ue_legacy\m1_smoke.py
```

测试生成原始材质参数到 `build/m1-evidence/scene-definition.json`，并导出 raw/decoded NPY、BaseColor预览及逐draw诊断；原始UE项目与RDC不改动。

固定 Capture 的 21 项 profile 校验继续约束观测字节129；可配置运行时 Schema 单独校验，不将捕获数据限制硬编码进通用布局。C++ 检测生成 metadata/Shader 混配。当前实现的实测记录见 Schema 报告，早期固定原型日志仍保留为历史证据。

M1第一条真实路径的独立规格与代码质量复核均通过；mask输入校验问题已关闭。此状态不扩展到本页列出的完整M1剩余项。
