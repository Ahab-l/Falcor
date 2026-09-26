# 指定源场景的 SkyLight 接入与内存修复

本阶段交付的是声明/脚本渲染框架的一条实际案例：源 targetmap 的天空材质捕获、原始 Cube 过滤、SH、DefaultLit 环境光照与自动曝光。不是完整 UE 渲染器或最终 RDC 图像一致性的声明。UE 源码、源项目和 RDC 均未修改，读回数据只用于离线比较。

## 调用方式

`targetmap_graph(scene_path, scene, shadows=True, sky_light=True, schema=active_schema)` 自动组合源天空材质、独立六面捕获、过滤/SH、PreintegratedGF 和环境光照 Pass。源场景先使用既有 `prepare_source_sky_material()` 与 loader 加载，图仍通过 `SchemaPipeline.stage()` / `commit()` / `render_frame()` 执行。

SkyLight 参数来自导出的场景配置；资源和依赖在 Python 声明中，UE 算法在独立 Shader 中。Falcor 原生补充的是通用 Cube/mip/face view、结构化缓冲、Mesh 独立视图、Observer 以及正确的帧/订阅生命周期。后续修改该案例参数和 Shader 无需为 SkyLight 重写一套 C++ 渲染入口。

最终环境光输出是 `SkyLightLighting.lightingColor`，同时可观察 `diffuse` 和 `specular`。它读取 `Base2.$packed`、`Decode.positionW`、主相机 setup、当前曝光、独立捕获 Cube 与 SH；曝光链所有 SceneColor 输入均接最终环境光结果。Unlit、背景和 alpha 保留。

## 实际 GPU 验证

- 源 Cube128 六面捕获、原始降采样/镜面过滤、8 个 float4 SH、DefaultLit 光照、自动曝光与相机控制：`build/sky-light-capture/run-3c9_s9wa`，launcher `run-u9scm60s`。连续 15 帧通过，20 个 Mesh Pass 的程序创建次数均保持 1。独立方向误差最大 2.84e-5，SH 最大误差约 1.51e-9。主曝光从 1 变化到 1.256887、1.263709。
- 消费端独立常量环境验证：`build/sky-light-lighting/run-n9bqhad0`，launcher `run-hjqjdqk4`。13,095 个 DefaultLit 像素与 2,265 个保留像素，漫反射/镜面反射分别比对，曝光变化和 alpha 保留通过。
- 当前场景所用 PreintegratedGF：`build/sky-light-brdf/run-jlpx82su`，launcher `run-jb566z8c`。GPU 自行生成 128×32 RG16Unorm；与源 CPU FP32 算法的 8,192 个通道码值及舍入前 A/B 全部一致。没有 CPU LUT 上传。
- 图替换/真实材质更新、Cube/结构化输出观察等证据见 `ue-legacy-sky-light-resources.md`。Python 全套 450 项通过：`build/sky-light-final-python.log`。
- 原始过滤的常量、方向和 HDR 输入在两种浮点格式下全部通过：`build/sky-light-filter/run-gwb27d_8`。Shader 执行/Schema 迁移、Observer、history 发布与拒绝、Mesh 程序复用最终回归分别通过 launcher `run-2e1x2ubf`、`run-5htnrxdk`、`run-2ub9da4u`、`run-hvp4vo9s`。

PreintegratedGF 原本由 UE CPU 生成；本实现明确标为 GPU 移植。默认 GPU 除法/开方/cos 近似曾造成 241 个码值不同，单独启用 precise 编译也未改变结果。独立数学适配保留每一步源 FP32 舍入，FP64 仅用于除法/开方舍入边界修正和本案例 cosf 求值。源 excerpt、编译模式证据及适配说明均保留在 `PreintegratedGFSource.json`，没有修改原始 UE helper 正文。

## 内存原因与实测

两张 Cube128 R11G11B10 的完整 mip 链合计约 1 MiB。明显的逐帧增长来自框架生命周期，而非 Cube 容量：

1. 新 Scene 的更新标记初始为 All；脚本直接执行图时未更新这个标记，旧代码每帧重建 Mesh Shader。改为每个 Pass 消费更新事件，并在销毁/换 Scene 时显式断开订阅。重复帧程序计数从 1/2/3/4 修正为始终 1，真实材质更新仍会触发一次重建。
2. 直接执行图绕过了 SampleApp 的 `Device::endFrame()`。仅 `wait()` 不会重置 GFX transient heap，修正重复编译后仍约增 100 MiB/帧。现在成功执行的直接帧补齐 `endFrame()` 与等待，history 在 GPU 完成后发布。

| 运行阶段 | 进程私有内存 |
| --- | ---: |
| 旧实现，第 1 帧 | 14.32 GiB，之后触发系统余量保护停止 |
| 只修重复编译，完整链路第 14 帧 | 9.71 GiB，仍逐帧增长 |
| 两项修复后，第 6 帧 | 8.438 GiB |
| 两项修复后，第 10 / 14 帧 | 8.438 / 8.438 GiB，字节数相同 |

最终运行峰值 9,059,045,376 bytes（约 8.44 GiB），耗时 47 秒。剩余常驻内存包含程序、编译器、场景和资源缓存；没有将这部分全部归因于某一种分配。测量是进程 private bytes，不是 Cube 大小或纯显存。

回归还发现两个相关框架问题并修正：`sigs::Connection` 是 shared_ptr，清空它不会自动取消回调；新 RenderGraph 在 addEdge 反射前尚未绑定 viewport，默认尺寸原本未初始化，现在为 0 表示待解析。消费 Shader 的混合全局资源结构改为显式 cbuffer 与顶层资源，原始 UE helper 保持逐字节一致。

## 观察图与后续边界

`build/sky-light-capture/run-3c9_s9wa/atlas.png` 第一行依次是最终环境光结果、原直接光、天空漫反射、天空镜面反射；第二行是捕获六面、过滤 mip 和主 SkyView LUT。图为线性观察预览，不是最终 tone-mapped RDC 对齐图。

后续围绕“框架能力 + 指定案例闭环”推进。云雾、GI、SSR 和后处理根据指定帧的实际贡献决定接入范围，案例之外的平台/组合与穷尽覆盖不作为当前完成条件。当前未声称最终 RDC 画面一致。
