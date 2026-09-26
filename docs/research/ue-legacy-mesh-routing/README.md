# Mesh 路由与整图 Pipeline 契约

实施位置为 `E:/Project/falcor/Falcor-m0`，分支 `codex/ue-legacy-m0`。本记录属于 DefaultLit/Mesh 骨干阶段，后续模型、Lighting、SSR、TSR、Web 仍须按用户顺序实施。

## 实际 Mesh Pass

`meshPolicyPath` 指向 version=1 的路由 JSON。主 BasePass 支持 instance/mesh/material/model/program ID、材质/模型/程序名、tags_any/all/none、PassMask 筛选。CPU 在提交前建立排序 draw 列表；最高优先级唯一归属，同级歧义、无默认归属、缺失 PrePass 覆盖显式报错。全局 enabled 与 main_enabled 分开记录；PrePass 选择独立。

每个 route 持有独立 Shader 文件、VS/PS 入口、编译定义、depth/stencil、cull、MRT 写掩码和 depends_on。Python 与原生分别检查依赖；原生也拒绝环。共享附件通过 RenderGraph 边逐节点保留，主表面写掩码必须满足公共 Schema 字段。

当前反向 Z 共享深度契约要求 PrePass GreaterEqual/write，BasePass Equal 或 GreaterEqual/readonly。其他深度比较被拒绝，避免将远处表面字段与近处深度配对。当前可配置 stencil 操作是 Keep/Replace/Zero/Invert，完整通用混合与其他附件布局仍需扩展。

独立 R32Uint `primaryCoverage` UAV 由 BasePass 的 earlydepthstencil Pixel Shader 写入，不占 MRT 槽。Decode 同时检查实际主表面覆盖和深度。仅参与辅助深度的物体不再被误当作清屏 ID 0 的合法主表面。自定义主 Shader 必须遵循覆盖写入和早期深度测试的接口；创建程序时检查 UAV 名称、维度、读写访问与 UInt32 元素类型。

## PipelineSignature

`pipeline_snapshot.py` 将项目 Shader 的递归本地 include 和材质/路由 JSON 保存到不可覆盖的内容目录。PipelineSignature 包含 Schema generation、项目源码、MaterialProgram 非数值元数据、PSO/defines/依赖/分区，以及 Falcor DLL、UELegacy DLL、运行时 Shader 树的指纹。材质数值、View、primitive flags、编码上下文、preExposure 另有 inputFingerprint。

原生 Config 校验精确 canonical checksum、冻结输入路径/字节、Schema/路由/源码匹配，保留 Shader 字符串并使用 addString 编译。各图节点校验相同 generation、PipelineSignature、inputFingerprint，以及节点名称/类型与其签名内的筛选配置。交换 BasePass 参数或移除筛选不能静默复用签名。

`SchemaPipeline.stage()` 验证候选整图的资源、Shader 特化、实际 GPU PSO 和执行；成功后才能 commit。源码损坏、混配或候选失败保留旧 activeGraph、输出和 history epoch。make_graph 的冻结重放入口还检查 Falcor 外部基线是否漂移。

Falcor import、实时 Scene 数据和纹理内容没有被复制为不可变资源。低层 createPass 用于测试，不替代完整图构建/重放入口。纹理与实时几何的完整输入指纹仍待补齐，不能将当前签名称作整帧所有外部资源的冻结。

## GPU 验证

RTX 4090 / D3D12 debug layer：

- `routing_smoke.py`：15 个筛选/组合用例，排序列表复用，真实 draw IDs/counts，拆分与并集 Packed Buffer 逐位一致；73 个原生配置拒绝、6 个执行拒绝。额外验证合法 ID 0 和辅助深度的覆盖区别、独立 Equal 状态与覆盖 UAV 要求。
- `pipeline_smoke.py`：真实项目 Shader 冻结后即使原文件变成 #error 仍能创建原候选；新候选失败保留旧输出；材质常量只改变输入指纹；混配输入、交换节点、移除签名筛选均拒绝。
- 78 项离线测试与原始 Capture 证据 hash 校验通过。旧 Schema/M1 GPU 回归另记录于各阶段报告。

结果位于 `build/routing-evidence/result.json`、`build/pipeline-evidence/result.json`；日志为 `build/m1-evidence/routing-context-final.log`、`pipeline-context-final.log`，两次进程退出 0。

## RDC 场景

真实 IA/法线/变换/View 数据构建四个物体，保留原始索引。第三个 MaterialProgram `rdc_grid` 使用捕获 BC1 sRGB 纹理的十级 mip 和 anisotropic8 wrap 采样器。原生视口为 1421×1035，分配为 1424×1040；投影使用捕获的 translated-world 矩阵和高低位平移。

DefaultLit Codec 接收 UEEncodeContext：精确的像素中心、frame modulo8、primitive flags、preExposure 与抖动启用状态。Specular 噪声和对象标志转换属于 Shader 数学，不写入 Schema 布局规则。

比较结果见 `../ue-legacy-rdc-scene/native-grid-context-final.md`：866,712 个覆盖像素无覆盖差异；model bits、per-object alpha 全部一致；GBufferB 865,348 像素完全一致，GBufferC 866,537 像素完全一致，D 全分配尺寸逐位一致。99% 深度误差约4.66e-9，两个物体边界仍存在较大深度差异。球面 normal RGB 存在量化差异。对象 SceneColor 一致，背景保留了捕获的引擎黄色警告文字差异。

这仅是 EID1853 BasePass 阶段。Lighting/SSGI/DFAO/天空云雾/SSR/曝光/ToneMap 之后的最终画面尚未实现和验收。
