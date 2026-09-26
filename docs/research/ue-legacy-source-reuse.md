# UE Shader 源码复用

2026-09-10 后续：LightingCommon 其余 BRDF/能量归一化/Capsule 原函数已接入生产，详见 [第二批原码复用](ue-legacy-lighting-source-reuse-closure.md)。两批共 13 个原码文件/32 个原字节区间可由 `import_ue_lighting.py` 从固定引擎重建。生产 RDC 四个 Mesh 仍全为 DefaultLit；ClearCoat/Skin/Cloth 等只作为共享函数的独立回归，不是 Capture 内容或匹配证据。下文第一批数据保留其历史身份。

2026-09-10。用户明确要求：**可以复用源码的尽可能复用源码。** 后续首先尝试直接使用 UE 原始文件或原始函数体，兼容层只适配必要的类型、宏、结构、资源绑定和调用入口。不能仅因整文件依赖 UE 框架就把其中可分离的数学重新手写；确实必须改写的部分要记录原因、来源以及验证边界。

## 可用基线

- 引擎：`E:/ue/engine/UnrealEngine`，Build.version 为 5.8.1，HEAD `53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0`。
- 测试工程：`E:/ue/project/shadingmodeltest/shadingmodel`。
- Capture：`E:/rdc/ue/1.rdc`，217,008,048 字节，SHA256 `822d41ea6ecb12633f42b18ed5ae1a3e7cea02653c9a72724f6e55e127d85fc9`。

引擎、工程和 Capture 保持只读。源码用于保留算法，Capture 用于确定实际 draw/permutation、资源、参数和 GPU 结果；本地源码身份不能自动证明它就是 Capture 中 Shader 的编译输入。

## 已接入的直接复用

生产 `Codecs/Lighting/LightingCommon.slangh` 的手写 `ueInitBxDF` 和 `ueSphereMaxNoH` 已替换为薄适配入口，直接调用保留原字节的 UE 函数。其余 Lighting 数学仍保留原实现，后续逐项迁移。

| 原文件 | 原始字节范围（起含末不含） | 本地文件 | 切片 SHA256 |
|---|---:|---|---|
| `Engine/Shaders/Private/BRDF.ush` | `[0,4506)` | `Codecs/Lighting/UEBRDF.prefix.ush` | `7ddeb1bc1a0c143f754ef7019c11ba5af0250f6ad8b7161e34ee0f9e294510f7` |
| `Engine/Shaders/Private/Common.ush` | `[33108,33148)` | `Codecs/Lighting/UEPow2.scalar.ush` | `1fecb8d3b05f05cb732464d87fadcd672ffc5f6adc483e86bb710f6366f1e996` |

BRDF 原文件 SHA256 `0de81cc25c9b035a77aeb0e2f1be3e730c0f117f9250fe365104f30119b5e906`；Common 原文件 SHA256 `11184bf6e39a0065e66acd174e2b8407c89791a184a2ad9552a1f1d83669c84b`。BRDF 切片保留版权、注释、两组 Init、SphereMaxNoH 和原条件编译。

`UEBRDFPCCompat.slangh` 在局部 include 范围把 half/half3 映射为 float/float3，使用 `SUBSTRATE_ENABLED=0` 并在退出后清理自建宏；原标量 Pow2 也直接提取。这个 PC 类型策略有本地 `Public/Platform.ush` 的 float 分支和 E2655 float 运算证据，不能推广到所有 UE 平台或所有宏组合。

`UEBRDFBxDFAdapter.slangh` 只复制五个既有字段，补齐六个未使用的各向异性字段为零，调用原函数并回写。Sphere 包装不重跑 Init，因此保留 ClearCoat 预先构造的底层上下文；Newton 开关原样传入，没有增加 clamp、epsilon 或 normalize。各向异性 Init 虽保留在源片段中，当前 profile 仍不支持各向异性或 Substrate。

`scripts/ue_legacy/import_ue_brdf.py` 可以校验本地切片，或对照固定引擎源码重新提取这两个原字节区间。它在源文件哈希变化时拒绝执行，不默默跟随引擎升级。CMake 仅在 UELegacy 插件目录扩展 .ush 复制支持。

## 验证

[私有 GPU 结果](../../build/ue-brdf-reuse-gpu/run-c8782hnp/result.json)，SHA256 `370b5e7b0a3cc8b4662ecc7d740b251771784b466ef471b6476f1ff1ed4d6dab`：224×2 组件样本均通过既有独立 oracle 预算，两版组件输出全字节一致；实际 RDC 的 13 份完整数值数组逐位相同。两个 Device 都是 RTX 4090，执行期间输入与生产代码保持原身份。

[独立审阅](../../build/ue-brdf-reuse-independent-review/run-3_8knvbq/review.json)，SHA256 `2cd6d89c25874ad1119c1d553fe45d9af2d35488a3984017027b5fb185949497`：142 个文件身份、独立 oracle 重算、原始数组与 Schema/Pipeline 合同通过。只更改 Common 子树和四个新增依赖；布局、模型、资源、路由与其他 Shader 保持。

[生产 GPU 结果](../../build/ue-brdf-reuse-production/run-66wvb9jc/result.json)，SHA256 `9529374cb55f7ccacac6e51fb74a3908ae8a2c02b47cf05b9ca9fcdab947851a`：实际生产 Codec 全树与已验证私有副本同字节，生成 Schema metadata 相同，13 份完整数值数组相同。180 项 CPU 测试通过，源码身份测试在未接入时先失败。构建用项目锁定 CMake 3.24.1 成功；首次误用 PATH 中较新 CMake 因 pybind11 旧策略失败，保留在 `build/ue-brdf-reuse-build/run-a9qdc0_1`，成功构建在 `run-szcxkjni`。

严格 E2655 HDR 仍有 31 像素/31 通道各差 1 half ULP，RGBA `[14,8,9,0]`。直接复用源码减少维护与移植偏差，不保证不同编译环境、驱动和指令结果逐位相同。本次没有证明机器 ISA、全材料域、其他后端或最终图像一致；阶段输入仍含 E2624 HDR、ShadowMask 和 AO fixture。

最终 Mesh/Adapter 迁移回归在 [新生产四图结果](../../build/ue-brdf-reuse-production-cache/run-g0r21kdq/migration/evidence/result.json)通过，每路径 14 项逻辑检查和对应物理映射保持。五份生产/部署 Shader 文件逐字节相同。

[冻结归档](ue-legacy-source-reuse-result.json)保存 435 条文件记录及 CAS，SHA256 `bead67445b4a74cf62ea0af7126200b38cf96038b74dcd0e3dd572bcbeccfdb3`。包含此次原码复用、生产验证和前一生产 diffuse 回合；旧版本源码按匹配哈希的冻结副本读取，不再从已改变的生产路径认证。归档不等于独立证明缓存对应某个 GPU draw。

## 后续顺序

1. 在当前 Lighting 中优先迁移 `BRDF.ush`、`CapsuleLight.ush`、`ShadingModels.ush` 的可分离原函数，以及必要的原 LUT/采样与辅助数学。保持现有 Shader Codec 对外接口，每批验证后替换手写部分。
2. GBuffer 数学以 UE 原编解码函数为来源，Schema 继续只管可配置字段/位段、ID、资源和分派；需要接入 Schema 访问器的部分采用薄包装，不能把固定 UE 布局重新硬编码为整个项目的唯一实现。
3. 真正 Clustered 保留 `LightGridInjection.usf`、`LightGridCommon.ush`、`ClusteredDeferredShadingPixelShader.usf` 的目标算法与回退分支。当前普通逐灯绘制仍不叫 Clustered。
4. SSR 按本地 `SSRT/SSRTReflections.usf`、`SSRT/SSRTRayCast.ush` 等实际路径接入；TSR 按 `TemporalSuperResolution` 内原 Shader 及其 history/velocity/exposure 契约接入。优先复用完整可适配 kernel，其次保留完整原函数体，再处理确实无法隔离的依赖。

主线顺序继续为基线/Capture → DefaultLit GBuffer → 模型 → Lighting → SSR → TSR → Web。Falcor 仍提供场景、资源、RenderGraph、Shader 编译和 GPU 执行；UE 兼容层承担调度与适配。自动曝光保留，完整骨干和最终图像仍未完成。
