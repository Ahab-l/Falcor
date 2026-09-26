# 31 处 Lighting 残差的原始 DXIL 前缀观察

后续生产状态：BRDF 初始化和 SphereMaxNoH 已直接复用 UE 原函数体，13 份原生完整数值数组保持，严格 HDR 仍 31 处；180 项 CPU、构建与 Mesh/Adapter Schema 迁移通过。用户“尽可能复用源码”的要求已加入主规划。详见 [源码复用与当前验收](ue-legacy-source-reuse.md)。下文包括此次之前的历史调查状态。

2026-09-10 最新状态：diffuse 显式 mad 已进入生产，固定实际局部/贡献 172/172 相同；当前严格 HDR 为 31 像素各 1 half ULP，RGBA [14,8,9,0]。本文按调查先后保留旧报告，以下“未修改生产”等仅指对应历史回合，最新验证见文末。

2026-09-09。本轮在固定的 43 个像素上取得 UE 原始 DXIL 的 GPU 中间值观察，其中包含全部 31 个当前 HDR 残差。**baseColor.r、metallic、roughness、Area.NoL、N.xyz、V.xyz、原始 N/V 的 dot 值共 516 个 float32 标量，与 native 观察逐位一致。** 当前没有据此修改生产数学，严格 Capture 仍为 31 个像素各差 1 half ULP。

## Native 观察与独立复算

`lighting_ps_prefix_smoke.py` 使用当前插件对应的已验证 RDC 重建 Pipeline，创建正常、material、normal、view 四图。每个观察图仅改 `directTransmission` 的诊断写入，其余展开后的 Shader、Scene、Schema、输入、管线合同一致。四图的 12 份受保护完整缓冲均与当前生产基线逐位一致，正常图 transmission 也一致；运行期间源码与运行时身份不变。

`analyze_lighting_ps_prefix.py` 用实际读回的 `(baseColor.r, metallic, roughness, Area.NoL)`、光色和观测阴影项，按捕获的分步 float32 顺序复算 diffuse。43/43 个灰色材质像素的 RGB 与 native `directDiffuse` 逐位一致；两处全阴影控制点保留其零阴影乘数。这个复算只解释 native diffuse，不是 UE BxDF 正确性证明。

结果：`build/lighting-ps-prefix-evidence/run-fyg75a45/result.json`；复算：同目录 `native-diffuse-prefix-analysis.json`，SHA256 `74f6163cb25e31d7430d7d141ae650ca6951be740e2706830eaf593415c7e84f`。

## 原始 DXIL 与插桩方法

原 PS 为 E2655 / ResourceId::1721 / DeferredLightPixelMain。独立只读导出的 24,200 字节与此前 `replay-lighting.json` 内嵌的 `reflection.rawBytes` 完全一致，SHA256 `c081c8239cee2a69719a00fb4384d88485cc83a314113c059f9c3df36a3fd0c3`。

`build/dxil-prefix-tools/dxil_prefix.cpp` 使用官方 DXC API 反汇编、LLVM IR 重组与完整验证，不调用 HLSL 编译或优化接口。原模块要求 validator 1.8；Falcor 附带的 1.7 明确拒绝后，改用本机 SDK 26100 的配套 1.8 DLL。没有降低原 metadata 版本或跳过验证。新版 UTF-8 blob 创建时会增加单个终止 NUL，工具严格检查源字节与这个尾符，后续内存及原文件仍要求逐位不变；3 个正例、6 个负例验证通过。

原样重组前后 3327 行非注释 LLVM 文本完全一致，包含指令、fast-math flags、CFG 与 LLVM metadata。DXIL 容器没有逐字节保持：SFI0、PSV0、ISG1、OSG1 相同；HASH 与 DXIL 字节改变，PRIV 移除、STAT 新增。工具记录这些差异，不能把 LLVM 等价称为整个二进制相同。

每个标量变体仅将最终 alpha store 重定向到原有 SSA 值。遇到不支配最终出口的值，只增加经完整 CFG 分析和验证器确认的 phi 转发；原始算术、分支及三个 RGB store 保留。映射在 `build/dxil-prefix-tools/ue-prefix-map.json`，43 点、12 标量与 native 对应关系预先固定；额外的纯 phi 探针区分实际执行值和未执行路径占位。

## GPU 门槛与结果

`BuildTargetShader(DXIL)` → `ReplaceResource` → `PixelHistory.shaderOut` 取得 GPU float32 输出，不使用 DebugPixel 解释器计算 BRDF。原样重组、12 个标量及分支有效性共 14 个变体，每个变体都要求 43 点的原 RGB、preMod RGBA、postMod RGB 逐位相等。原样重组还要求完整观测记录相等。最后撤销替换、释放资源并重读原 Shader，恢复结果也完全一致；RDC 前后 SHA256 保持原值。

| 观察范围 | 对应标量数 | 逐位相同 |
|---|---:|---:|
| 材质与 Area.NoL | 172 | 172 |
| N.xyz 与原始 normal dot | 172 | 172 |
| V.xyz 与原始 ScreenVector dot | 172 | 172 |
| 全部当前残差点的上述标量 | 372 | 372 |

分支有效性在全部 43 点为 1，没有把 phi 的占位 0 当作原计算结果。回放耗时 290.453 秒，结束状态、资源恢复和文件哈希均通过。

- 生成计划：`build/lighting-dxil-prefix-generations/run-u_6i9q6i/plan.json`，SHA256 `2766baa56bac8306acc25bc05d01ffafada6a581a8b5e0b746c6aa3f2c611d4f`。
- GPU 回放：`build/lighting-dxil-prefix-generations/replay-8p2bod41/result.json`。
- [严格前缀比较](../../build/lighting-dxil-prefix-generations/replay-8p2bod41/native-comparison.json)，SHA256 `c0371bf3d0de4c9ec6edc898e0bcba1eb7b3f091038672d09abe44d2ae36a3c6`。

这些是经过输出不变门槛约束的 GPU 插桩观察，不声称读取了未插桩的硬件寄存器，也不推广到未采样像素。结果将当前所观测差异链收窄到后续 BxDF / 分量合成；下一步观察曝光前 diffuse/specular，而非根据 half 残差数挑选公式。Schema/Codec 分工、Packed 主管线、自动曝光需求和 Lighting → SSR → TSR → Web 顺序继续保持。

## 后续：diffuse 差异与被拒绝的 specular 探针

六分量计划 `run-1zrezkgq` 的回放 `replay-4v7w4_xf` 被门槛拒绝：`directSpecular_r` 在 `(998,923)` 改变原始 shaderOut.r 的 1 个 float32 ULP，混合后也改变 1 个 half ULP。该回合状态为 failed；清理没有报告异常，Capture 哈希不变，但没有完成恢复后的原始观测。**其 specular alpha 不作为可接受的原始 UE 中间值证据。** 三个 diffuse 探针的局部门槛虽通过，也不把整个失败回合计为成功验收。

随后独立计划 `run-himx4c4v` 只含 roundtrip、三个 diffuse 分量、`diffuseColor.r`（原 `%191`）和分支有效性。`replay-oweg0_0j` 完整完成 6 个变体、43 点的 RGB/pre/post 门槛及原始恢复，耗时 155 秒，Capture 哈希不变。三个曝光前 diffuse 分量与 native 的 129 个标量中有 6 个不同，仅位于下列两点：

| 像素 `(x,y)` | native−UE，RGB float32 位型差 | native BaseColor.r | native Metallic |
|---|---|---|---|
| `(880,701)` | `[-3,-2,-2]` | `0.26171875` | `0.4156862795352936` |
| `(966,1015)` | `[3,5,4]` | `0.318359375` | `0.8549019694328308` |

原 UE `%191` 在两点的 uint32 位型分别为 `1042061465`、`1027421492`。离线有限假设检验显示：分别舍入乘法及减法可复现 native diffuse，单次舍入可复现这里的 UE diffuse；但 `c * (1-m)` 在这两点也得到相同候选，不能仅凭这些点区分 FMA 与重结合，更不能据此声称已确认机器指令。

`lighting_diffuse_prefix_smoke.py` 的两图回合 `build/lighting-diffuse-prefix-evidence/run-p883efur` 也保持 12 份完整保护缓冲逐位不变。它在诊断 MRT **重新调用** `ueComputeDiffuseColor`，43 点的调用结果与 UE `%191` 相等；这不代表生产 `ueShadeDefaultLit` 内实际用于光照的局部值相等。重新求值的表达式与 `precise radiance` 的依赖路径不同，可能发生不同舍入或被编译器复制。下一步直接传出实际源局部变量，并检查编译后 producer／flags／use 链；仍须保留输出不变门槛。

## 比较器补强与独立复核

独立审查直接读取前阶段原始回放及 native NPZ，重新核验 516/516 值、全部门槛及 IR 可逆性。同时发现旧比较器对缺失 probes、缺失 availability 或空 checks 可能出现空集通过。新增 `build/compare-lighting-dxil-prefix-v2.py`，旧工具与结果保持原哈希。

v2 强制绑定完整 plan、43 个唯一有序坐标、精确检查键和布尔类型、原始／roundtrip／restored 记录、实际 RGB/pre/post 值、有效分支，以及 native 全部 12 份保护数组；并复核文件身份、原文可逆和 assembled IR。18 项离线正负例通过。主代理另行运行：

- 前阶段 `replay-8p2bod41/native-comparison-v2-root.json`：516/516 相同，SHA256 `e145b029dc47dffecc312c12bffc3c6cf83ba5fe3e3f108e01bddc921749b067`。
- diffuse 阶段 `replay-oweg0_0j/native-comparison-v2-root.json`：172 项中 166 项相同，SHA256 `3fa804d9e4df60322581a4494eb3b1c063d3ac7d69aa3c5e6494d065c5466f10`。其中 43 项属于上述 helper 重算，只按其限定语义理解。

比较到差异属于调查结果；缺少证据、失败门槛或不完整回合则拒绝。生产 Shader、Schema 布局及运行时没有因本调查改变，严格 HDR 仍为 31 像素各差 1 half ULP，整个渲染目标尚未完成。

## 实际源局部值与 native DXIL

`lighting_local_prefix_smoke.py` 随后在私有 Codec 副本中给 `UEModelLighting` 添加诊断字段，并紧跟 DefaultLit 原有 `diffuseColor` 声明赋值导出；没有第二次调用 helper，也没有改公式或 precision 修饰。它通过正常生成器建立新的诊断 generation：LayoutHash、CodecHash、字段／MRT／ID 与资源合同全部保持；只有 LightingHash、对应源码依赖和必要的 generation／校验值改变。原始 Schema 可从 metadata 重建，生成字节与基线相等；新源编辑及头文件均可逆。CPU 自检与三项非法变化负例通过。

原生两图回合 `build/lighting-local-prefix-evidence/run-2kyijxfc` 的 12 份完整保护输出逐位相同，生产源码、插件、Scene 与资源身份稳定。导出的局部 `.r` 对 UE `%191` 为 41/43 相同，两点分别为：

| 像素 | native 局部值 uint32 | UE `%191` uint32 |
|---|---|---|
| `(880,701)` | `1042061464` | `1042061465` |
| `(966,1015)` | `1027421496` | `1027421492` |

本次使用全新 shader cache，旧 cache 未删除。`build/lighting-local-prefix-cache/run-7k8k96ft` 保存启动参数、日志、缓存与完整离线反汇编；其中两个 `lightPS` 的 Target3 数据流可识别基线和诊断版本。诊断版本的 `%680/681/682` 由无 fast 标志的独立 `fmul`、`fsub` 产生，同一 SSA 值既进入 Lambert／Target1 光照链，也经 phi 进入 Target3 诊断输出，没有在这份 DXIL 中另造一份 helper 求值。这里仍未将 cache 字节绑定到 native GPU Capture 的具体 draw，也没有证明驱动机器指令；结论保持在已观察 GPU 输出及这两份编译产物的范围内。

[局部值独立归档](ue-legacy-lighting-local-prefix-result.json) 保存 222 条记录及原始数组、Schema／Pipeline 闭包、源码副本和缓存。SHA256 `b8ef0ce50c7b95a7d81e277cd8bcc33835415abab63e9d3e345f3fd7c1cb784a`。这将两个 diffuse 差异点收窄到材质派生值的舍入路径；下一步据此验证局部精度修正，并继续 specular 的有效取证，不能以剩余 half 像素数量挑选实现。

独立 [SSA 审阅补充](ue-legacy-lighting-local-prefix-review.json) 确认上述共用 producer，并比较两个 cold-cache `lightPS` 的全部 Target0／1／2 数据流：保留操作、常量、flags、intrinsic、metadata 和 phi 来源后，12 个输出表达式指纹逐项一致。审阅原文 SHA256 为 `a5fcc0df798bff08770916b160a3f258d7f1741a333e95e83558c02f0bb1d965`，其范围仍止于这些编译产物。

## 本批冻结结果

[前缀／diffuse 主归档](ue-legacy-lighting-prefix-result.json) SHA256 `4dd7ac079b9c583eee887e634bbf028d04c3ddd613fa827bf61e64cdd0c1718b`：573 条记录、272 个 CAS 对象、9 次 NPZ 数组检查与 19 个 Pipeline 闭包。516/516 和 172/166 的比较报告均从原始资料重新生成核对，失败 specular 回合另作失败证据保存。Capture 本体只核哈希，未另行复制。该主归档不覆盖后续局部变量诊断；后者使用上述独立归档和审阅补充。当前仍未改动生产数学或接受严格 HDR 残差。

## 2026-09-10：显式 multiply-add 候选及 BxDF 上游

**与用户 RDC 的对应范围。** 本节调查对象始终是 `1.rdc` 的 E2655 方向光。这里的 `UEAreaLight`／capsule／sphere 名称来自 UE 处理有限光源角尺寸的共用算法，不表示增加了 Rect Light 或场景物体。UE `DirectionalLightComponent.cpp` 将 `SourceRadius` 写为 `sin(0.5 * LightSourceAngle)`；当前捕获 Shader 确实读取该参数并执行 `SphereMaxNoH` 路径。Cloth／ClearCoat／Skin 则属于此前骨干模型扩展，用独立场景验收；此次对它们做回归是因为共享 helper 受影响，不能宣称这些模型都由 `1.rdc` 覆盖。当前 E2655 测试仍以捕获的 E2624 HDR、阴影与 AO 为阶段输入，不是整帧端到端复现。

Schema 边界保持：只在私有 Shader Codec 副本中将 `baseColor - baseColor * metallic` 替换为 `mad(-baseColor, metallic, baseColor)`。生成器仍只处理布局、字段、ID、资源、模型注册和分派；LayoutHash、CodecHash 不变，LightingHash 与依赖 generation 随 Shader 数学变化。此次重新运行 Schema 与 Lighting Schema 共 89 项离线测试通过。

独立固定样本检查先在原有 source-local 输出复现失败：43 点的 `diffuseColor.r` 和三个 directDiffuse 分量共 172 项中 164 项相同。私有候选三图回合 `build/lighting-diffuse-rounding-candidate/run-x4av2qdv` 将同一检查提升到 172/172；三图分别保持 13、11、12 份完整保护数组逐位相同。主代理重新运行比较器得到同样结果。候选严格 HDR 仍是 31 像素／31 通道各差 1 half ULP，RGBA 分布 `[14,8,9,0]`；生产版本仍是 `[13,8,10,0]`，没有晋升候选或通过严格 HDR 验收。

`mad` 在这里仅称为显式乘加，不能据其名称声称可移植的单次舍入或 UE 驱动的 FMA 指令。冷 cache 审查确认候选使用 DXIL opcode 46 FMad，带 `!dx.precise`；候选 source-local 的同一 SSA producer 同时供 Lambert、光照与诊断输出使用。候选正常／诊断版本 Target0/1/2 的全部 12 个输出表达式一致。详见 `build/lighting-diffuse-candidate-cache/run-6gpoohug/native-dataflow-review.json`（SHA256 `55212f962a7131f3c8ebb096a017e5b5715df04d9579d0c0ebbdf16e89659025`）。cache 字节尚未绑定原生 Capture 的具体 draw，驱动机器指令仍未证明。共享 helper 的跨模型验证正在补充，包含原生 Cloth 和 ClearCoat 双法线路径。

镜面链使用原始 UE DXIL 的 alpha-only 探针，以及 native 已有源局部值导出，新增两个独立回合：

| 观察量 | 相同比较数 | 最大 float32 ULP |
|---|---:|---:|
| post-sphere NoV | 43/43 | 0 |
| post-sphere NoH | 24/43 | 3 |
| post-sphere VoH | 25/43 | 2 |
| capsule specularL.xyz | 129/129 | 0 |
| capsule sphereSinAlpha | 43/43 | 0 |

BxDF 回合为 `replay-6cs_xqo4`，面积光输入回合为 `replay-anvonqh2`。后者耗时 154.265 秒，roundtrip、四字段和 availability 共六变体全部通过实际 RGB/pre/post 检查，结束后原始记录完全恢复，Capture 哈希不变。v3 比较器继续执行 v2 的完整门槛，仅接受新增 source-local native 状态；没有将不执行分支的零哨兵当成测量。全部 43 点为 DefaultLit，且 Area.NoL 为正。

这把已观察的镜面差异收窄到面积光输入之后。下一步对照 `ueInitBxDF` 返回的初始 NoL/NoV/VoL 与 SphereMaxNoH 内部计算，不根据最终 half 残差数量枚举公式。

[本次独立归档](ue-legacy-lighting-bxdf-area-result.json) SHA256 `7863f9ff44fb634d299a880485bd942ece27f767ce2b29cf9120393daeb60ad1` 保存 364 条记录；归档时从原始资料重算 diffuse 红／绿检查、三图完整保护数组和两个 UE/native 前缀比较。它不覆盖随后跨模型回归或冷 cache 的新 SSA 审阅。此前两个冻结归档保持原字节。生产数学、严格 HDR 和完整管线的完成状态均没有改变。

### 跨模型回归及审阅补充

共享 diffuse helper 的候选回归已完成。`lighting_diffuse_cross_model_candidate.py` 固定 224 个原有组件样本，分别运行 baseline／candidate；两者均通过既有独立 oracle 预算，specular、transmission 和支持标志 alpha 逐位不变。四个原生图是 ClearCoat 双法线场景与 Cloth 场景的各一对 baseline／candidate，合计覆盖六个受影响模型；每对 16 份完整保护数组与两个目标的 alpha 逐位相同，全部浮点数组有限，既有模型采样 oracle 通过。两个场景的 half HDR 与各自 baseline 相同，仅作为观测记录，不用于选择公式。

第一次进程 `run-sj3t4jaz` 未在 Mogwai 启动时启用调试层，第二 Device 启用调试层后出现主 Device removed；它只留下两份组件结果，原生图为零，**整轮失败，不作为 RTX 4090 回归证据**。原始日志及部分结果保留。相同冻结脚本改用 `--enable-debug-layer` 启动后，`run-xb6bzhgu` 日志确认两个 Device 均为 RTX 4090，完整结果为 `build/lighting-diffuse-cross-model-candidate/run-rcheox_z/result.json`，SHA256 `475a9682707969f4f46ab2cc540ed63f8496359f088d28113a9fbb054c49677f`。主代理独立重读原始 NPZ、完整保护数组、目标 alpha、有限值与文件身份；复核记录 SHA256 `6a5607daa227b0e680e5e59986be7e27a9d3f89583fe6dee971f2f6beac0e058`。

[跨模型独立归档](ue-legacy-lighting-diffuse-cross-model-result.json) SHA256 `2e27f8e43c61586e217051574f56c556b55f278e50fc1000fd3f4c3f72d31749` 保存 695 条记录、失败首轮和成功重跑。候选 generation 按其私有 Codec 根目录重新生成核验，不能拿生产 Codec 路径认证私有数学。这是有限样本验证：多数非 ClearCoat 组件模型仅有一个 metallic 样本，原生场景 metallic 为 0.3，不能声称全材料域等价。生产 helper 尚未修改；后续可依据固定 diffuse 样本和受影响模型回归决定单行晋升，并重新生成、验证生产 Schema／Lighting。

三个 cold-cache 的完整静态审阅及原始编译产物已单独保存到 [缓存审阅归档](ue-legacy-lighting-cold-cache-review-result.json)，SHA256 `694253617e63840d690532dd5e577a578df9ecaeaf509820bde755b0a57106c5`，306 条记录。BxDF 的 NoV/NoH/VoH、方向光有限角尺寸修正的四个输入都与各自生产输出共用 SSA producer；各 baseline／diagnostic 的 Target0/1/2 表达式一致。结论仍只针对已检查 DXIL，尚无 cache→draw 或驱动 ISA 证明。

`build/lighting-bxdf-area-acceptance/independent-review.json`（SHA256 `3385203b4487785d960a5361ce66af4942a74e9d464e24321663a2488b7c9af5`）独立重核 364 条记录、172 个 CAS、保护数组、红／绿比较和全部 replay 门槛通过。其边界说明：旧 red NPZ 沿用前一份 local-prefix 归档，补充归档不是脱离历史证据即可运行的单独包。

下一份初始 BxDF 探针对应 NoL `%775`、NoV `%805`、VoL `%806`，使用 DefaultLit-family 专属四层 phi 与分支有效性标记。计划 `build/lighting-dxil-prefix-generations/run-gkaz86ve/plan.json`（SHA256 `afa59a6ef9a713b1ba5505e23961c4b1d6eb70b83a8e8746355cf8a53c39bd32`）已经完成五变体的组装、官方验证及可逆性检查；尚未回放或取得 native 初始化局部值。

## 2026-09-10：生产 diffuse 验证

在固定 172 样本及共享模型回归通过后，生产 `LightingCommon.slangh` 只修改 diffuse 表达式为 `mad(-baseColor, metallic, baseColor)`，文件 SHA256 为 `1c601c648119a5f8fe6298072332031560e5200a913cef113f8ef812c9479613`。理由是已接受的实际源局部值和贡献证据，不依据 HDR 残差数选式；显式 mad 仍不构成跨驱动单次舍入承诺。

[新生产结果](../../build/lighting-diffuse-production-evidence/run-oqjvsqnv/result.json)，SHA256 `7058d8af6a1e65d2ba38c6c0e88af8275233205ca4719f6ca21fb26295d57699`：新正常图的 13 份完整数组与私有候选逐位一致，局部导出图的 12 份保护数组与正常图逐位一致，实际 diffuse 局部及贡献共 172/172 与固定 UE 实测相同。所有非 HDR 严格门槛通过；HDR 仍为 31 像素/31 通道各差 1 half ULP，RGBA [14,8,9,0]，max abs 0.0009765625。没有增加像素补丁或目标颜色输入，E2624 HDR/阴影/AO 仍是显式阶段 fixture。

179 项 Python unittest 通过；[新生产 Schema 迁移](../../build/lighting-diffuse-production-migration/run-5b9_1wao/evidence/result.json)在 Mesh/Adapter 各 baseline/migrated 两图通过，每路径 14 项逻辑检查。旧归档及其源码哈希保持原字节，历史版本应通过其冻结副本认证。

用户提出直接复用 UE Shader 后，正在私有副本验证 `BRDF.ush` 的 BxDFContext、两组 Init 和 SphereMaxNoH 原始字节，以及 Common.ush 的 Pow2；外部仅适配 PC float 类型、legacy 宏、命名空间和结构。原码复用不等于整个 UE Pass 即插即用，也不自动证明与 Capture 数值一致。此阶段尚未把这两个生产手写函数替换为复用版本。
