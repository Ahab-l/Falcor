# UE 源工程独立盘点（2026-09-10）

**当前状态：** 用户确认旧关卡已删除，提供保存的 `Content/targetmap.umap` 与 `E:/rdc/ue/2.rdc`。隔离源盘点成功，11 Actor清单及源文件不变校验见 `build/source-project-inventory/targetmap-sl06pz8a`；新Capture元数据见 `build/capture2-inventory/run-yxfwg83_`。当前范围见 [capture2 baseline](ue-legacy-capture2-baseline.md)。下方自动保存盘点为历史，不再等待或查找旧关卡。

补查剩余 `Untitled_1_Auto1.umap`：隔离工程/NullRHI 成功加载，仅有 WorldDataLayers，无 Mesh/Light。`build/source-project-inventory/run-55iw3i2k/inventory.json` 和 `result.json` 记录 exit 0、源文件哈希均未改变。仍未找到与 1.rdc 配对的源关卡。

原生框架基线通过验收后，开始从 UE 源工程查找配对场景。此次盘点没有读取 RDC，也没有把导出结果送入 Falcor 渲染。

## 实际读取方式

- 源工程：`E:/ue/project/shadingmodeltest/shadingmodel`。
- 使用 `E:/ue/engine/UnrealEngine/Engine/Binaries/Win64/UnrealEditor-Win64-Debug-Cmd.exe` 的 Python commandlet，启用 `NullRHI` 和 `NoShaderCompile`。
- 将项目 Content 资产及三个 `Untitled_2` 自动保存关卡复制至 `build/source-project-inventory/run-uehoefyx/Scratch`。Python/EditorScripting 插件只在该临时工程启用，未启动或编辑原工程。
- 通过 UE 正常 package/World 加载读取 Actor、Mesh/Material 资产路径、Actor transform 与光源属性。
- 进程返回 0；三个关卡均加载成功，脚本没有读取错误。全部 17 个被复制的源文件运行前后 SHA256 相同。完整文件名单、命令和哈希见 `build/source-project-inventory/run-uehoefyx/result.json`；World/Actor 清单见同目录 `inventory.json`。

## 找到的关卡

源工程 `Content` 中没有保存的 `.umap`。`Saved/Autosaves/Temp` 中另有旧 `Untitled_1` 自动保存；本次加载的是以下三个 `Untitled_2` 文件。

| 自动保存文件 | 静态 Mesh Actor | 结论 |
|---|---|---|
| `Untitled_2_Auto1.umap` | Floor、SM_SkySphere、HairCards_14389 | 旧 HairCards 场景 |
| `Untitled_2_Auto2.umap` | Floor、SM_SkySphere、HairCards_14389 | 旧 HairCards 场景 |
| `Untitled_2_Auto3.umap` | Floor、SM_SkySphere、HairCards_14389、HairCards_14390 | 两个 HairCards 实例 |

这些关卡都包含 DirectionalLight、SkyLight、SkyAtmosphere、ExponentialHeightFog、VolumetricCloud 和 PlayerStart。源对象读取到 DirectionalLight intensity=6，SkyLight intensity=1。SkyLight 使用 `SLS_CAPTURED_SCENE`，未指定 cubemap；这里指 UE 自身的天空场景捕获模式，与 RenderDoc 无关。

Floor 引用 `/Engine/MapTemplates/SM_Template_Map_Floor` 和 `/Engine/OpenWorldTemplate/LandscapeMaterial/MI_ProcGrid`。HairCards 引用项目同名资产；部分贴图名称带 ResourceId，其来源尚未核定，不作为参考场景输入。

历史离线报告 `ue-legacy-rdc-scene/native-source-view.md` 包含 sphere/cube 区域，而上述三个自动保存关卡没有 Sphere/Cube Actor。不能把这些自动保存关卡当成已经配对的 `1.rdc` 源场景，也不能用旧捕获导出的几何/相机补齐缺失。

## 历史查找结论与当前源状态

旧关卡已由用户确认删除。源关卡便于取得相同作者输入，但不是框架/算法实现的前提；先前将它列为不可继续的条件不准确。现在使用新保存的targetmap，不再等待旧地图。

targetmap已在隔离副本读取资产引用、实例变换与灯光设置并记录来源。后续通过现有PassDefinition、Mesh/Schema/Codec、事务及历史接口生成实际View、Packed、depth、lighting和时间状态。全局自动曝光已有原码实现，完整后处理仍待补齐。RDC仅用于离线观察和比较自产输出。
