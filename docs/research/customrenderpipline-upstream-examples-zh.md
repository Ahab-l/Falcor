# Falcor 官方 GitHub：原生示例补充调查

查询日期：2026-09-12。通过 GitHub API 核对官方仓库、最新提交、tag，以及 master、4.4、3.2.1 的完整文件树；读取了相关 raw 源码和教程。

官方仓库为 [NVIDIAGameWorks/Falcor](https://github.com/NVIDIAGameWorks/Falcor)。查询时 master 最新提交是 [eb540f6748774680ce0039aaf3ac9279266ec521](https://github.com/NVIDIAGameWorks/Falcor/commit/eb540f6748774680ce0039aaf3ac9279266ec521)，日期 2025-01-07，与本地原始工作树的 HEAD 相同。当前官方示例大多已经在本地；之前列出的六个例子不是完整清单。最新 tag 列表包含 8.0，没有发现比本地基线更新的 master 实现。

## 当前版本最值得对照的内容

| 官方入口 | 内容与复用价值 |
| --- | --- |
| [自定义材质说明](https://github.com/NVIDIAGameWorks/Falcor/blob/master/docs/usage/materials.md) | 原生支持新增 Material 类型、自定义参数 payload、材质资源管理及 Shader 材质实现，不只是替换已有材质。教程部分接口名称旧，应以当前下列源码为准。 |
| [PBRTDiffuseMaterial.cpp](https://github.com/NVIDIAGameWorks/Falcor/blob/master/Source/Falcor/Scene/Material/PBRT/PBRTDiffuseMaterial.cpp)、[材质 Slang](https://github.com/NVIDIAGameWorks/Falcor/blob/master/Source/Falcor/Rendering/Materials/PBRT/PBRTDiffuseMaterial.slang)、[MaterialInstance/BSDF](https://github.com/NVIDIAGameWorks/Falcor/blob/master/Source/Falcor/Rendering/Materials/PBRT/PBRTDiffuseMaterialInstance.slang) | 完整原生参考：C++ 管参数、纹理槽、Shader module、type conformance 和 Python 绑定；Slang 做贴图/法线处理、`setupMaterialInstance()`，实例实现 BSDF 求值/采样。新增材质应该先检查这套原生接入方式能否满足。 |
| [实现 RenderPass 教程](https://github.com/NVIDIAGameWorks/Falcor/blob/master/docs/tutorials/02-implementing-a-render-pass.md)、[当前模板](https://github.com/NVIDIAGameWorks/Falcor/blob/master/Source/RenderPasses/RenderPassTemplate/RenderPassTemplate.cpp) | 插件注册、`reflect()` 声明输入/输出、`execute()` 使用 RenderData。已有生成工具和模板，不需要自己设计插件注册系统。 |
| [图编辑教程](https://github.com/NVIDIAGameWorks/Falcor/blob/master/docs/tutorials/03-creating-and-editing-render-graphs.md) | 原生 RenderGraphEditor 支持拖入 Pass、资源/执行依赖连线、标记输出、打开 Mogwai 和实时编辑。Python 图本身已经是可序列化描述；我们的 JSON 应作为薄装配层。普通编辑流程不具有自定义事务的失败回滚保证。 |
| [FLIP 图示例](https://github.com/NVIDIAGameWorks/Falcor/blob/master/tests/image_tests/renderpasses/graphs/FLIPPass.py) | 两个 ImageLoader 接入 FLIPPass，输出感知误差可视化。适合画面质量比较；它不等同于原始像素字节/整数编码比较。 |
| [SideBySide](https://github.com/NVIDIAGameWorks/Falcor/blob/master/tests/image_tests/renderpasses/graphs/SideBySide.py)、[SplitScreen](https://github.com/NVIDIAGameWorks/Falcor/blob/master/tests/image_tests/renderpasses/graphs/SplitScreen.py) | 原生双图并排、分屏比较，不必为普通图像对照另写显示系统。 |
| [TAA](https://github.com/NVIDIAGameWorks/Falcor/blob/master/tests/image_tests/renderpasses/graphs/TAA.py)、[SVGF](https://github.com/NVIDIAGameWorks/Falcor/blob/master/tests/image_tests/renderpasses/graphs/SVGF.py)、[图测试目录](https://github.com/NVIDIAGameWorks/Falcor/tree/master/tests/image_tests/renderpasses/graphs) | 除顶层演示外，测试目录包含大量小型原生组图用例，适合学习各 Pass 所需端口和组合方式。测试通常依赖媒体包/测试环境，不是每个都能无素材直接启动。 |
| [场景创建](https://github.com/NVIDIAGameWorks/Falcor/blob/master/docs/usage/scene-creation.md)、[场景脚本目录](https://github.com/NVIDIAGameWorks/Falcor/tree/master/scripts) | 原生场景、材质和渲染图脚本入口。普通场景属性优先使用已有 Scene/Material API，源引擎特有语义再由转换层补充。 |
| [Python 用法](https://github.com/NVIDIAGameWorks/Falcor/blob/master/docs/falcor-in-python.md)、[gaussian2d](https://github.com/NVIDIAGameWorks/Falcor/blob/master/scripts/python/gaussian2d/gaussian2d.py) | 独立 Python 调用、可微 Slang、PyTorch/CUDA 互操作和图像拟合。可参考资源绑定及 Python 驱动方式；不是当前自定义 GBuffer 的必要依赖。 |

## 官方历史版本里额外保留的渲染器

| 版本与示例 | 实际结构 | 如何使用 |
| --- | --- | --- |
| [3.2.1 SimpleDeferred](https://github.com/NVIDIAGameWorks/Falcor/tree/3.2.1/Samples/Core/SimpleDeferred) | 几何阶段写三张 RGBA16Float GBuffer 和 D32Float 深度；Fullscreen lighting 读取三张 GBuffer，有点光、方向光及调试模式。 | 适合对照“材质写 GBuffer→光照读取”最小流程。它使用旧 GraphicsVars/Fbo/Model API，不能直接拷进当前版本编译。 |
| [4.4 ForwardRenderer.py](https://github.com/NVIDIAGameWorks/Falcor/blob/4.4/Source/Mogwai/Data/ForwardRenderer.py) | 用图连接 DepthPrePass、SkyBox、ForwardLighting、CSM、ToneMapper、SSAO、FXAA、Blit。 | 明确展示具体效果是独立 Pass，通过边组合。相关库/API 属于 4.4，需要逐项迁移；不能当作当前 master 已有可直接调用的完整管线。 |

## 对当前框架判断的修正

之前将原生能力主要概括为“替换材质、固定 GBuffer”，对材质系统的介绍不完整。**Falcor 原生可扩展材质类型与 BSDF，也允许自定义材质参数数据。** 因此，独立材质类型分派、参数上传、贴图/采样器管理不能仅凭“自定义材质”四个字判定为必须重写。

仍需分别评估的需求是：外部 Shader/描述的装配；用户定义的 GBuffer 附件、通道及位编码；源引擎特有的材质/坐标/曝光约定；新 Shader/配置失败后的整图保留。原生材质 payload 不是屏幕空间的 GBuffer 附件布局，两者不应混为一谈。这个补充调查没有证明当前全部自定义材质代码都能直接删除，也没有验证原生 HairMaterial 能匹配 UE/FY1 的光照公式。

另一个实际发现是官方教程存在版本滞后：Mogwai 入门仍引用当前 master 已不存在的 `Source/Mogwai/Data/ForwardRenderer.py`；RenderPass 教程有旧 `SharedPtr/create(RenderContext*, Dictionary)` 写法；材质文档仍讲 `setupBSDF()`，当前 PBRT 示例已使用 `setupMaterialInstance()`。采用教程的组织思路，具体函数签名以当前模板和编译中的源码为准。

本轮只做官方源码/文档调查，没有升级、切换或修改 Falcor 渲染实现，也没有运行这些历史示例。GitHub 文件树与选读源码保存在 `build/github-falcor-examples`，与前一轮框架 GPU 验收证据分开。
