# 原生 targetmap 方向光阴影

2026-09-11：源场景的常规 CSM 已通过现有声明框架运行：`ShadowSetup → Mesh 深度 × 4 → Fullscreen 投影 × 4 → Lighting`。全部参数来自源组件、引擎默认值和当前原生相机；全部深度由原生 Scene 索引绘制生成。没有读取 RDC，没有恢复退役的 captured CSM 实现，没有 HZB、遮挡剔除、缓存或 atlas packing 对齐。

## 输入与范围

源盘点为 `build/source-project-inventory/targetmap-if86ulu1`，来自只读 UE 项目的隔离副本。`build_targetmap_scene.py` 将组件阴影标志和源 CVar 默认值写入 `build/source-targetmap/Scene.json`。相机仍是保存的 targetmap 视图，未证明与 `2.rdc` 捕获视图相同。

当前 profile 是一个 Movable 方向光、1–4 级传统不透明 PCF 阴影，targetmap 使用 4 级、20000 cm、分布指数 3、过渡/距离淡出约 0.1、组件 bias/slope 0.5。有效 scratch 引擎默认 ShadowQuality=5、MaxCSMResolution=2048、depth bias=10、slope scale=3、receiver bias≈0.9。**这些是源引擎 commandlet 默认值，原交互编辑器的临时 CVar 覆盖尚未确认。** DF 阴影、far cascades、contact shadow、PCSS、大气/云投影等未实现的分支会被源图构建器拒绝。

主不透明 Pass 绘制四实例。阴影绘制考虑全部五个源 caster，包括不在主视图内的实例和不透明 Unlit SkySphere：源 `cast_shadow/cast_dynamic_shadow` 均为 true，UE `FMaterial::ShouldCastDynamicShadows()` 没有排除该不透明 Unlit 材质。天空材质没有 WPO；天空颜色仍未实现。组件双面 caster 独立分组，复用 Mesh `cull_mode`，不重复实现 Mesh 执行器。

## 框架与源码复用

`UELegacyShadowSetupPass` 每帧读取原生相机，输出 576 字节参数 buffer：64 字节 header，四条 128 字节级联记录。记录保存列向量矩阵行、split/fade、bias/transition、光方向以及原始/取整半径。数学内部保留 UE 厘米单位，矩阵输入才转换为 Falcor 世界米。

级联宽度是 `1:3:9:27`，边界为 `[10,509.75,2009,6506.75,20000] cm`。保留原始球半径用于 bias、`ceil(radius_cm)` 用于投影、至少 ±5000 cm 的深度范围、UE 光旋转轴，以及 `fmod(...,8/innerResolution)` 向零取余的 snapping。2048 纹理包含每侧 4 texel 边框；bias/snap 使用 2040 内部尺寸。深度使用 outer clip projection 和完整 2048 viewport，边框也有真实 caster 覆盖。

`Shadows/UECSMDepth.ush`、`UECSMFiltering.ush`、`UECSMEncode.ush` 保存八段未改写的 UE 函数/结构源码；`export_shadow_source.py` 可重复提取，`UECSMSource.json` 记录文件、行、源文件及段落 SHA256。Slang 适配器只处理 Scene/矩阵约定、参数读取和当前不透明分支。

- 深度直接调用原 `ComputeDepthBiasDirectionalSpot` / `TransformShadowDirectional`：clear=1、LessEqual、源 near clamp 和 VS slope bias。
- 顶点法线使用去除实例缩放的对象轴。直接解码 Falcor 存储的三个 f16 分量，避免 `PackedStaticVertexData.unpack()` 额外归一化改变源 TangentZ 长度。
- 投影直接调用原 36-tap `Manual5x5PCF` 和逐 tap 软比较，随后 sharpen → square → sqrt attenuation 编码。
- 四层从远到近以硬件 alpha blend 写 BGRA8 的 RG；每次 blend 保留 UNORM8 量化，BA 保持 1。新增 Fullscreen MRT `writeMask` 支持这一状态。
- `Lighting.nativeShadowLight` 指定接收原生 mask 的方向光索引，声明 `nativeShadowMask` 与 `nativeShadowParameters` 输入。Lighting 沿用既有 UE 阴影解码/距离淡出；其他灯继续使用自己的阴影状态。新增 shader binding 已保留，模型资源不能覆盖。

源码索引（相对本机 UE 根目录 `E:/ue/engine/UnrealEngine`）：

| 功能 | 源文件 |
|---|---|
| 分割/球/过渡/光初始化 | `Engine/Source/Runtime/Engine/Private/Components/DirectionalLightComponent.cpp` 479、755–1011 |
| 深度范围、snap、outer projection | `Engine/Source/Runtime/Renderer/Private/ShadowSetup.cpp` 1037–1143 |
| bias/transition、RG blend | `Engine/Source/Runtime/Renderer/Private/ShadowRendering.cpp` 858–895、1957–2133 |
| 顶点偏置及 near clamp | `Engine/Shaders/Private/ShadowDepthVertexShader.usf` 97–143 |
| 去缩放及源法线长度 | `Engine/Shaders/Private/LocalVertexFactory.ush` 600–607、799–845、1210–1227 |
| PCF / encoding | `Engine/Shaders/Private/ShadowFilteringCommon.ush`、`ShadowProjectionPixelShader.usf`、`Common.ush`；精确段落见 manifest |

## 实测证据

最新 targetmap 整链：`build/targetmap-shadows/run-0o6uycs0/result.json`，launcher `build/ue-lighting-closure-cache/run-ydrkpj9_/process-result.json`。原始参数、四层 D32 深度、BGRA mask、位置/法线与有/无阴影直射光在 `raw.npz`；八输出可视化为 `atlas.png`。

- 四个 Mesh 深度节点各绘制 5 个 caster，索引数 `[144,144,288,2880,11904]`。
- CPU 源网格 oracle 检查 2324 个深度样本和 2412 个 clear 样本。深度最大误差 `3.5868e-6`；预算由三角形深度梯度和 D3D 八位子像素坐标精度计算，另加 `5e-7` 浮点误差。第 0 级最大误差 `4.2533e-7`。它曾发现并拒绝归一化法线导致的错误，修复后通过；没有修改渲染数值以满足比较。
- 1656 个位置的独立 36-tap PCF/逐级量化 oracle 与原生 mask 最大差 1 UNORM8。179329 个覆盖像素受到明显阴影影响。
- 全图 directDiffuse 与无阴影贡献乘以解码/距离淡出后的 mask 一致，预算 `atol=3e-6, rtol=5e-5`。这也检查没有把 CSM 写入 BA 后重复乘阴影。
- 同源相机矩阵/级联参数对照、重复帧稳定性、错误投影拒绝通过。参数最大绝对差 0.001953125 出现在厘米量，不能把它解读为全 buffer 位相等。
- 独立非静态封存 fixture：`run-_3jnw76b/process-result.json` 验证同一张图内原生相机移动/恢复及视口 resize 会更新 setup，未重新 stage。
- 框架 GPU：`run-jx_k9o9n` 检查独立 Mesh 尺寸、inset viewport、D32 采样和非法尺寸/viewport 回滚；`run-l09oxlzz` 检查 RG-only BGRA8 硬件混合。
- 354 项 Python CPU 测试通过（含 9 项级联源数学）；原生 `UELegacyLightingResourceBindings` 新增三种 binding 冲突在修复前失败、修复后通过。日志分别为 `build/native-shadow-cpu.log`、`native-shadow-bindings-red.log`、`native-shadow-bindings-green.log`。原生构建日志为 `native-shadow-final-build.log`。
- Packed 附件重命名为 `nativeShadowMask` 的测试在 `run-nzb9ts5f` 确实绕过了独立输入；修复后，最终整链拒绝 `nativeShadowMask/nativeShadowParameters` 两种重名并保持原图可用。检查只在启用原生阴影时生效，关闭时不占用这些 Schema 名称。最后构建为 `build/native-shadow-port-guard-build.log`。

严格参考 Scene identity 包含相机，修改该参考相机要重新 stage。没有指定严格 Scene identity 的动态图支持上述每帧移动。当前主 Mesh/Decode/Lighting 的投影是完整视口的对称透视，setup 会明确拒绝与之不一致的 camera aspect 或非对称投影；CPU 数学测试中的非对称视锥覆盖不等于主图已支持非对称投影。

## 仍未证明的部分

这些是自产场景/原始中间输出验证，**不是 `2.rdc` 的图像或位型一致性证明**。源 OBJ 只有六位小数，源 UE SNORM 法线经过 Falcor f16 传输也可能影响 bias；原相机、运行时 CVar、纹理平台压缩/mip/采样仍待匹配。当前源材质没有 masked/WPO，不把此深度 shader 推广成这些材质的实现。天空/云雾、环境光/SSGI/DFAO、SSR 及其 temporal、完整后处理和 WebRTC 仍在后续主线。

运行入口为 `targetmap_graph(..., shadows=True)`；`targetmap_native_smoke.py` 保留无阴影基线，`targetmap_shadow_smoke.py` 验证完整原生阴影图。下一步先实现源天空与环境照明输入，再继续图像差异分析；RDC 始终只是离线参考。
