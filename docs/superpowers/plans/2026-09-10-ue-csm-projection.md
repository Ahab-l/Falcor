# RDC CSM 投影实施计划

2026-09-10 已停止：用户要求框架先行，RDC中间结果仅供离线比较。本文的captured atlas、CB、固定draw列表路径不再适用；CSM原型未注册/未参与构建。转入 `2026-09-10-framework-before-reproduction.md`。以下仅保留历史设计。

> For agentic workers: 沿用已授权的 subagent-driven-development / executing-plans 分工。仅当前 Capture 实际路径；GPU/replay/build 串行，不提交，不改 UE/RDC。

**Goal:** 原生生成当前 RDC 的四级 CSM ShadowMask，随后接入 Lighting 并补齐原生阴影深度，逐步移除 shadow fixture。完整管线目标保持。

**Architecture:** 保留 UE 原 Manual5x5PCF 与投影、overblur、fade、attenuation 编码源码。新增原生 `UELegacyCSMProjectionPass`，从已有 Schema/Codec 读取自产 Packed 和 depthCopy，消费图输入 shadowAtlas，按 capture 顺序执行四次 BGRA8 的 RG SrcAlpha 混合，输出每级与最终 mask。先用明确标记的 captured atlas 验证 projection；之后由真正 CSM depth Mesh Pass提供同一输入。不能将本子阶段称完整原生阴影。

**Tech Stack:** Falcor D3D12/Slang、当前 UE5.8.1 原函数、RDC PS1718/VS1717、原 CB/PSO、Python 取证/验收。

## 已确定的接口与边界

- Capture 四个 opaque Mesh 均为 DefaultLit，不新增其他模型。projection 初期 host 显式拒绝其他模型；Schema ID可迁移，通过薄访问器转为原函数规范 ID1。
- 原 shader 显示9个Gather组成5×5 PCF、非PCSS、fade plane、普通deferred GBuffer。源码的quality≥4都进入同一分支，不声称已确定宏的精确数字。
- 8192×2048 R16 atlas经11次depth draw生成，无cache copy；E2059清65535。四projection为E2585/2598/2611/2624，均启用depthBounds并采用SrcAlpha RG blend，不使用推测的首级MIN。
- Falcor当前不暴露depth-bounds API。薄入口对原生depthCopy做相同闭区间筛选，保留像素选择算法；记录这是shader适配，不能声称硬件PSO逐字段相同。过滤、fade、格式量化仍由原函数及硬件blend执行。
- `UECSMSurface ueCSMLoadSurface(uint2)`连接Schema/Codec；不固定附件名/槽位/bit布局。`ConstantBuffer<CSMParameters> gCSM`及`ConstantBuffer<ViewParameters> gView`只提供原函数所读参数。
- 现有主Pipeline快照/事务保持。本阶段新节点先作为显式投影验证支路；进入正式Lighting前必须把节点/资源/源码加入Pipeline签名，禁止未签名节点悄悄替换正式输入。

## 执行任务

- [x] 从真实PS/PSO确认PCF路径、深度区间、blend、四级输入；原始payload已独立校验。
- [ ] 冻结原码切片及薄入口，导出原CB到具名参数；记录无法从优化IR唯一还原的宏信息。
- [ ] 新增上述原生Pass与最小GPU验收入口。验收先观察未注册的Pass失败，再实现；每级原始BGRA8与Capture逐字节比较，输出未混合投影值以定位偏差。原有Packed/depth不得变化。
- [ ] 串行验证15个实际depth/BasePass draw的最小GPUScene记录，避免读取两个2GiB完整allocation；primitive范围必须由实际header及IR证明。
- [ ] projection匹配后接入正式RenderGraph与Lighting。配置输入、源码、Pipeline签名与generation回退纳入已有机制；实际方向光HDR比较保留严格门槛。
- [ ] 实现当前11次draw对应的原生cascade depth，保留原几何/变换/裁剪/bias/atlas viewport，再比较每级R16深度和最终ShadowMask，移除atlas fixture。

## 验收与报告

测试场景只用当前RDC实际内容。对四级mask及atlas逐阶段比较；自动曝光保持；不使用目标mask作为算法输入，也不通过阈值、临时颜色或特殊像素修补对齐。只有对应GPU证据通过的子项才能标完成。下一主线仍为实际上游Lighting/SSGI/天空/曝光，再SSR/TSR/Web。
