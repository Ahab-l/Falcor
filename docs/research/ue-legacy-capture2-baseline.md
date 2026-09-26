# targetmap / 2.rdc：当前画面对齐基准

2026-09-10 用户指定 `targetmap` 和新 `2.rdc`，并明确：**不要 HZB，不做优化项的对齐，只做影响渲染结果的 Pass 对齐。** 本文覆盖旧捕获的当前执行顺序；`1.rdc` 只保留为历史。

## 已核实的来源

- 工程：`E:/ue/project/shadingmodeltest/shadingmodel`。
- 地图：`Content/targetmap.umap`，SHA256 `ffa0412c6fcab14a2cdecf98d607dbf061af92a107b8a1db7af4eee190638490`。
- 捕获：`E:/rdc/ue/2.rdc`，148,903,273 bytes，SHA256 `059eef7978d1c32039ad4bd21b5b0c59574c393996fb842b37f3a9e4a87edb2f`。
- 本机引擎 custom5.8.1 HEAD `53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0`。

地图通过独立 scratch 项目的 UE NullRHI 正常加载，读取 11 个 Actor；未启动原工程或保存资产，全部复制源文件前后哈希相同。证据：`build/source-project-inventory/targetmap-sl06pz8a/{inventory,launch,result}.json`。入口：`scripts/ue_legacy/inspect_targetmap.py`。

Capture 只读回放盘点 1,251 个 action、152 个 texture 的元数据；没有导出纹理、顶点、常量或历史等渲染输入，前后哈希相同。证据：`build/capture2-inventory/run-yxfwg83_/{inventory,result}.json`。

场景有两个 Cube、一个 Sphere、Floor，以及独立 SM_SkySphere。前三者使用 Engine BasicShapeMaterial，Floor 使用 MI_ProcGrid；与 BasePass 三个 draw（Cube 两实例、Sphere 一实例、Floor 一实例）对应。名称和实例数对应不等于材质参数、相机或最终数值已经对齐。

源 DirectionalLight intensity=6、4 级阴影、阴影距离20,000 cm；SkyLight intensity=1、实时天空捕获、无自定义 cubemap。项目配置 Nanite=false、VSM=0、GI method=2、reflection method=2、自动曝光=true、AA method=0。实际GPU分支以下列Capture事件为准。

## 影响画面的实际 Pass

| 功能 | 2.rdc 事件 | 当前要求 |
|---|---|---|
| BasePass / Packed | BasePass 1382；draw 1426/1437/1452 | 源 Mesh/Material 独立生成；保留 Schema/Codec |
| 方向光与阴影 | ShadowDepths 1539；四级投影2144–2188 | 自产阴影深度与投影；不恢复旧 capture-fed CSM |
| 间接光/AO | SSGI quality3、16 rays/pixel 2001；复合2069；DistanceFieldLighting 2420 | 保留采样、遮蔽、历史、滤波与复合 |
| 环境光/反射 | SkyLightDiffuse 2417；SSR quality2、1 ray/pixel 2721；SSR TAA 2751；反射复合2772 | 实现实际反射与环境光，保留SSR内部时域滤波 |
| 天空、云、雾 | 天空LUT1167；CloudView2846；SkyAtmosphere2892；Fog2920；云复合2946 | 从源参数生成，不加载Capture LUT或天空纹理 |
| 曝光与后处理 | 半分辨率PS downsample3133；LocalExposure3159；Histogram3191/3206；EyeAdaptation3342；Bloom3413–3716；Tonemap3747 | 全局曝光/降采样已有原码实现，继续局部曝光、Bloom、Tonemap和输出变换 |

主要场景ViewRect事件尺寸1421×1035，部分底层纹理1424×1040。后续需要正确处理有效区域和边界，不能混用分配尺寸。源相机状态及Falcor映射仍需核实，不上传Capture View矩阵。

未见主画面TSR；存在的TAA属于ScreenSpaceReflections。主画面TSR不作为本Capture当前对齐项。CullLights显示NumLights=0，不单独实施Clustered/LightGrid优化结构对齐。编辑器/UI开销不作为场景渲染管线复现目标。

## 后续顺序

1. 从保存的targetmap导出原资产、实例、材质、光照与可取得的源相机信息，完成新场景Packed/Depth闭环。
2. 方向光与自产传统阴影，再接SkyLight/天空。
3. SSGI、DFAO、SSR及其影响像素的时间/空间滤波；补齐云雾复合。
4. 自动与局部曝光、Bloom、Tonemap/输出；先比较自产原始Buffer，最后比较画面。
5. Web继续作为原生输出的控制与观察端。

不逐项复刻HZB、剔除、压缩draw list、并行调度、LightGrid等性能结构。允许更慢的直接路径；改变图像的数学、采样、滤波与状态仍需实现。复用PassDefinition、真正Mesh Pass、Packed Schema/Codec、显式Adapter及事务/历史框架。

本轮新增HZB C++/Shader/graph/oracle及配套mip观察扩展已撤回，不注册、不构建HZB Pass。build中的历史实验不作为当前交付。撤回后构建通过（`build/no-hzb-build.log`）、330 CPU通过（`build/no-hzb-cpu.log`）；原生观察与降采样/曝光回归：`build/observer-gpu/run-4xqhlziw/result.json`、`build/downsample-gpu/run-2ei_c0mc/result.json`。

完整renderer与最终画面对齐仍未完成。旧地图缺失不是框架实现的阻塞条件；现在已有新保存地图与Capture，不再查找旧地图。
