# Mesh 路由、状态与 RDC 场景重建

本轮继续全部目标。最终必须由真实 Falcor 场景和 UE 兼容管线重建用户 `1.rdc` 的内容，比较原始中间 Buffer 与最终输出。当前测试场景和绿色基础测试不构成目标完成证明。

## 实施

1. 增加独立 Mesh 路由 Schema：按 instance/mesh/material ID、材质名、着色模型、程序、tags、PassMask 过滤；主 BasePass 选唯一最高优先级，平级冲突和未路由显式报错，显式禁用有独立诊断。Depth 等辅助通道独立选择。
2. 每份 BasePass 配置独立持有 Shader 入口/定义、depth/stencil、raster、MRT 写掩码与依赖；共享字段仍受 GBuffer 契约限制。构建和复用排序后的真实 CPU draw 列表，保留 instanceID、16/32-bit 和变换绕序。
3. 扩展整图事务与 PipelineSignature，覆盖真实材质程序及递归源码、编译定义、参数接口、路由/PSO/依赖；改变源码或路由不能只保持 LayoutHash 就继续复用。材质参数与场景输入另存可比较指纹。
4. 并行从 `1.rdc` 的实际 IA/manual fetch/GPUScene/View 数据导出几何、UV/法线、变换、相机和材质事实，形成可重放场景。PostVS 仅验证投影，不代替真实世界几何着色。程序地板遵循实际 Shader 数学，不能以烘焙截图代替。
5. 对真实 GPU 验证单项筛选、优先级/冲突/默认/排除、辅助选择、实际 draw 数、独立状态、多节点共享保留；复用原有 raw oracle，并逐步将同样验证应用到真实 RDC 场景。

## 完整目标仍未满足的要求

本轮实施状态：步骤1/2/5的当前opaque/static范围通过GPU验证，包括73项原生拒绝、6项执行拒绝及15组筛选。步骤3已有项目源码/JSON快照、PipelineSignature/输入指纹、节点绑定、整图回退与基线漂移重放检查；外部纹理/实时Scene尚未全量冻结。步骤4已提取真实IA/法线/变换/View和地板纹理，原生Falcor渲染覆盖与RDC相同，原始GBuffer差异已逐项记录。DefaultLit Codec加入编码上下文，数学仍归Shader。详见 `../../research/ue-legacy-mesh-routing/README.md`。当前78项离线测试和四组GPU（routing/pipeline/M1/schema）均通过，实际RDC第五组渲染/比较也已执行；仍不标记完整目标完成。

DefaultLit/Mesh 契约之后继续显式 Adapter、模型扩展、Lighting/CSM/环境、空间与历史基础、Clustered/SSR/TSR 和 Web。为与该 RDC 最终画面一致，必须逐阶段处理其中实际活动的 SSGI、DFAO、天空/云/雾、自动和局部曝光、ToneMap 等；不能将旧骨干范围之外的效果直接忽略后声称整帧一致。最终比较必须记录捕获阶段、ViewRect/extent、曝光、几何/材质/光源/纹理、算法和数值误差。

原始需求文档路径在当前 workspace 不存在，现以用户六项要求、已确认设计和捕获事实为可用依据；不因此停止已明确的实施。
