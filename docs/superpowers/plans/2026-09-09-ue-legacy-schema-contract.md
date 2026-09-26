# Schema / Codec 契约修正与下一步实施

2026-09-09。用户重申六项核心要求及实施顺序。本文件约束后续实现；当前 GPU 通过只证明固定 profile 的数值路径，不证明完整 Schema 架构已经完成。

## 修正前已核实的差距（历史记录）

- `generate_schema.py` 的 Python 字符串包含 DefaultLit 编解码公式；应由独立 Shader Codec 持有。
- `UELegacyConfig.cpp` 固定五 MRT 及 ID/mask，只能接受当前捕获配置；尚不支持仅改 Schema 后重建 Shader/RenderGraph。
- `reference_profile.json` 是原始捕获证据清单，部分字段语义只是描述文本；不能充当完整的机器可执行字段/bit/模型/路由 Schema。
- 当前生成的 codec_hash 对整个生成头求哈希，混入布局内容，且 LayoutHash 包含 view 数据；尚未实现职责独立的 LayoutHash/CodecHash/PipelineSignature。
- 未形成通用模型注册/分派、consumer 需求校验、generation 事务及失败回退。

## 下一项工作：在扩展模型及 Lighting 前完成

1. **分开证据与配置。** 保留不可变 capture profile 和其校验；新增运行时 `Schemas/*.json`，结构化定义 attachment roles/formats/transfer、字段/通道/位段、模型 ID 与有效字段、codec 入口、路由。选定 UE profile 对 Schema 施加兼容约束，但具体某个 capture 的矩形/事件号/曝光值不成为通用 Schema 的硬编码限制。
2. **Codec 数学归 Shader。** 建立 `Codecs/DefaultLit.slangh`；模型的 normal 编解码、属性变换/AO 等数学由此负责。MaterialProgram 仍只计算原始 UE 属性。初期 AO=1 限制保持，未移植的数学不能用占位近似冒充支持。
3. **生成公共接口与分派。** 生成器按 Schema 产生 MRT 声明、字段/bit 访问、模型常量/有效性、codec 注册和 encode/decode dispatch，不能继续内嵌各模型数学公式。Codec 通过逻辑字段接口访问布局；更改物理 slot/channel 时不改各模型公式。
4. **运行时 metadata 驱动。** C++ 根据 metadata 反射/分配资源、建立 BasePass 路由和状态；移除具体布局的重复硬编码，保留通用能力和 consumer 契约校验。增加新算法可改 C++，仅修改受支持 Schema 布局不要求重编 C++。
5. **共用 generation。** producer、Lighting/SSR 等 consumer 和原生格式 Adapter 使用同一 Schema/generation；独立计算规范化 LayoutHash、包含递归依赖的 CodecHash，PipelineSignature 再覆盖材质程序与路由/PSO。原生 Falcor GBuffer 只从显式 Adapter 接入。
6. **事务切换。** 校验→生成→编译候选→图重编译→帧边界整体切换；失败保留旧 generation。相关历史按 generation 失效，不能出现新 producer 配旧 consumer。
7. **验收。** 保留现有 DefaultLit 原始 buffer/GPU oracle；增加可支持的通道路由变更、字段/位重叠、未知 codec、缺 consumer 字段、注册模型分派、编译失败回退和独立 BasePass generation 一致性测试。Schema-only 改动须在不重编 C++ 的条件下完成受控切换。

## 当前主实施顺序（用户重申版本）

冻结 UE/Falcor 基线与 Capture → **DefaultLit GBuffer 闭环（包含以上 Schema 契约）** → 扩展模型 → Lighting → SSR → TSR → Web 调试。

该顺序优先于先前把扩展模型/SSR/TSR 延后到整个旧 M0–M4 之后的安排。保留既有技术内容；HZB、velocity、history、曝光等在其消费者前作为必要依赖实现，阴影/天空等功能保留需求并按所属阶段安排。

SSR、TSR、Clustered Lighting 保留目标 UE 算法，可以牺牲性能，不使用其他算法或 stock 同名近似替代。Web 仅控制/观察原生 Falcor，通过 GPU 可视化、Atlas、WebRTC 同时展示多输出；它不是浏览器渲染器移植。

## 2026-09-09 实施记录

Schema 基础闭环已完成代码实现与 GPU 验收，详见 [运行时闭环报告](../../research/ue-legacy-schema/README.md)。

- 步骤 1–3：独立 Schema、Shader Codec、Codec 能力声明、字段/bit/MRT 生成、模型 ID/有效性/分派已落地。
- 步骤 4：metadata 驱动附件反射/分配/slot/写掩码；只改受支持布局无需重编 C++。Mesh 路由、独立 Shader/PSO/依赖、主表面覆盖和真实 draw 缓存已通过 GPU 验收，当前深度状态有明确兼容限制。
- 步骤 5：独立 LayoutHash/递归 CodecHash、生产/消费共享 generation，以及项目源码/PSO/路由/节点分区的 PipelineSignature 已落地。Falcor import/实时 Scene/纹理没有全量冻结，显式原生格式 Adapter 仍待实施。
- 步骤 6：同步离屏候选验证、帧间整体提交、失败保留旧图、废弃旧 pending、防止代际混配已落地。没有自动文件监视或通用 temporal history 系统；新图独立分配资源并推进 history epoch。
- 步骤 7：33 项 Schema 测试、原有 21 项 Capture 测试；GPU 原始数据 oracle、MRT/字段/bit 迁移、测试别名模型分派、编译失败回退、多 BasePass 代际一致性均纳入验收。新增真实 UE 模型仍按后续阶段实现。

后续进展见 [Mesh 与整图报告](../../research/ue-legacy-mesh-routing/README.md)。Codec 新增 UEEncodeContext，负责捕获的 Specular 量化抖动和 primitive flags 编码，Schema 不持有这些数学。当前 38 项 Schema、19 项 Pipeline snapshot 和21项 Capture 测试通过。下一项仍在 DefaultLit/Mesh：原始 RDC 剩余数据差异、显式 Adapter 与剩余能力验收，然后进入模型扩展阶段。

## 后续状态更新

当前 Schema 边界已经进入实际普通 Lighting：七模型 GBuffer 与对应 Lighting Shader 的受支持 profile 已接入；LayoutHash、CodecHash、LightingHash 与 generation 分开记录，Lighting 直接读取 Packed。ClearCoat/Skin 的 LUT、双法线、Mesh/Adapter、迁移及失败回滚已做受控验收。正在调查的 float32 舍入属于 Shader 数学/编译边界，不往 Schema 生成器塞入公式。完整状态见 [Lighting 中间值调查](../../research/ue-legacy-lighting-prefix.md) 与 [ClearCoat/Skin](../../research/ue-legacy-coat-skin-lighting.md)；严格 HDR 仍 31 像素各差 1 half ULP，后续 Lighting → SSR → TSR → Web 顺序不变。

**2026-09-09最新：** [Lighting Schema契约](../../research/ue-legacy-lighting-schema.md) 已完成可选Lighting模型注册/分派、field/resource/profile校验与独立LightingHash；缺省Schema的生成字节不变。159离线、原生资源CPU测试、真实DefaultLit/Unlit基础GPU分派/ID迁移与既有Schema迁移/回滚回归通过。LightingPass集成和完整光照数值验收仍进行中，后续顺序保持Lighting → SSR → TSR → Web。

**上一批模型阶段：** [七模型GBuffer Codec验收](../../research/ue-legacy-model-codecs.md) 已通过真实模型编码/解码与Mesh/Adapter测试。Schema仅新增CustomData布局、每模型常量覆盖和consumer字段需求；数学仍全部在Shader Codec。131离线、18原生、8组模型GPU与6项最终回归通过，DefaultLit原始NPZ不变。详细机读记录及147份源码/证据CAS已保存。本批只完成七模型GBuffer子集，剩余模型资源、Lighting → SSR → TSR → Web和最终画面仍待实现。

**上一批资源阶段：** [参考场景资源与原生身份](../../research/ue-legacy-resource-identity.md) 已完成当前静态范围的资源冻结、独立封包与逐帧身份校验；102项离线、18项原生测试及Schema/Adapter/严格RDC回归通过。DefaultLit完整Packed A/B/C/D和原生depth/stencil保持逐位一致，Schema/Codec与默认generation未变。下一阶段进入实际Shading Model扩展；下列资源未冻结等描述保留其历史时间范围。

**最新：** [Capture DefaultLit逐位对齐](../../research/ue-legacy-defaultlit-exact.md) 已完成A/B/C/D及实际depth/stencil全allocation一致。最后6点通过Codec精度边界及显式identity DBuffer步骤修复，Schema布局保持不变。默认generation为`cee97e8b24948a570d3ce8398172fea557966a92040e27c1ee08e8c55d525ea1`，Schema-only迁移/回滚、两路径DBuffer门控和Adapter回归通过。下文剩余6点为历史状态；接下来仍需外部资源身份冻结，然后进入真实模型扩展。

上述实施记录保留当时状态；显式 Adapter 现已完成，见 [Adapter 与原始顶点精度报告](../../research/ue-legacy-adapter-fidelity.md)。它与主管线复用同一 Schema/Codec，实际 stock 几何与身份通过显式 UE MaterialProgram 映射后写入 Packed 输出。最近该阶段共 38 项 Schema、20 项 Pipeline snapshot、21 项 Capture 离线测试，7 组 GPU 脚本、3 项 D3D12 capability 通过。

新增 [Mesh 几何专项](../../research/ue-legacy-mesh-acceptance.md) 验证同一 Scene 的混合 16/32 位索引、非均匀负缩放、正背面与双面材质，以及拆分 BasePass 的逐位一致性。Schema/Codec 职责不变，DefaultLit 原始 GBuffer 数值差异、stencil-plane 对比与外部资源完整身份仍有剩余项。实际模型扩展尚未开始，ID 别名验收不计作模型算法实现。

最新 [原生平面与精度验收](../../research/ue-legacy-stencil-precision.md) 已完成实际depth/stencil的完整allocation逐位对比，并恢复捕获位置运算的舍入边界。BaseColor/AO、Metallic、Roughness、模型/对象位和D全部一致，法线剩1像素、Specular剩5像素各差1码。Adapter新增grid程序验收，修复其材质变化导致深度精度变化的问题；最终迁移/回滚和4项D3D12 capability通过。Schema位布局和Codec数学在此阶段未改。外部资源身份及剩余6像素继续在DefaultLit阶段处理。

## 2026-09-10 当前 Shader 数学验证

当前最新：用户要求可复用 UE 源码尽可能复用。BRDF 两个入口的原码复用已进入生产 Codec，新增四个 Shader include 进入 Lighting 依赖闭包；LayoutHash/CodecHash/ID/字段/资源保持。生产 GPU、180 项 CPU、构建和 Mesh/Adapter 四图迁移通过。Schema 不负责把原 Shader 数学翻译成另一套公式，适配保持在 Codec/兼容层。见 [源码复用](../../research/ue-legacy-source-reuse.md)。以下段落保留先后阶段状态。

后续更新：该单行 diffuse mad 已晋升生产，当前生产 13 份完整数组与已审阅候选相同，实际 diffuse 局部及贡献 172/172 与固定 UE 样本相同。179 项 CPU 和新生产 Mesh/Adapter Schema 迁移回归通过。LayoutHash/CodecHash 保持，LightingHash/generation 随数学更新；当前严格 HDR 仍 31 处，RGBA [14,8,9,0]。UE 原函数体直接复用原型处于私有验证，数学仍位于 Codec，类型/宏/结构适配不归 Schema。下段为此前候选阶段记录。

Schema／Lighting Schema 89 项重新验证通过。显式 multiply-add 仅在私有 Lighting Codec 候选中，固定 diffuse 172/172 与共享模型224组件／四原生图的有限回归通过；LayoutHash／CodecHash 不变，只有LightingHash及其generation变化。尚未晋升生产，严格HDR仍31处各1halfULP。该步骤没有把数学写入Schema。详细结果、失败首轮和归档边界见 [Lighting 中间值调查](../../research/ue-legacy-lighting-prefix.md)。当前所称area／sphere路径是RDC已有方向光的有限角尺寸修正；独立测试场景的Cloth／Coat／Skin不冒充RDC覆盖。
