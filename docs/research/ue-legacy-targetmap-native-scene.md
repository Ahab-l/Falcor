# targetmap 原始源场景 → 原生 Packed 闭环

2026-09-11。本阶段已接通原始 UE 资产、保存的场景变换、源材质程序、原生 GBuffer/Depth、方向光及自动曝光。没有读取或上传 RDC 几何、矩阵、常量、纹理、深度、阴影、曝光或历史。RDC 仍仅为后续离线比较目标；本文不声称整图已对齐。

## 源数据

- 地图：`E:/ue/project/shadingmodeltest/shadingmodel/Content/targetmap.umap`，SHA256 `ffa0412c6fcab14a2cdecf98d607dbf061af92a107b8a1db7af4eee190638490`。
- 网格隔离导出：`build/source-assets/run-gv53t5sm/assets.json`。四个原始 Engine LOD0 的数量验证通过：Sphere 559 顶点/960 三角形，Cube 54/48，Floor 90/96，SkySphere 2208/3968。
- 材质、函数、原始纹理导出：`build/source-project-inventory/targetmap-d8sdxilw/{inventory,materials,result}.json`。原资产和地图未保存、源文件哈希未变。
- 进一步阴影组件/CVar 源盘点：`build/source-project-inventory/targetmap-if86ulu1/inventory.json`。原项目未启动，隔离 commandlet 的有效 CVar 单独注明来源，不能称为截帧运行时设置。
- 原始源图导出 DDS 是 `Texture.Source`，512×512 BGRA8 sRGB 单 mip，SHA256 `41b07563c47dd9a9219da84a41247d67c62c92873ae8a8406a28d001e3d8c729`；不是 GPU 平台压缩纹理。转换为 TGA 只更换容器，原 BGRA 像素不变。

`build_targetmap_scene.py` 验证导出摘要、LOD 数量和受支持的静态开关，生成 `build/source-targetmap/Scene.json`。`targetmap.pyscene` 再验证网格文件；`targetmap_graph.py` 在冻结纹理之前验证其摘要，防止变更后的文件被错误地标为原始源内容。所有执行在独立 worktree `E:/Project/falcor/Falcor-m0`，没有修改 UE 源码/源项目或提交代码。

## 相机和几何

通过只读 `GETALL World EditorViews NAME=targetmap OUTER=/Game/targetmap`，在打开视口前读取地图内部的透视记录：位置 UE cm `(-1602.451350,-491.166987,290.018399)`，Pitch/Yaw/Roll `(-31.199898,85.400834,0)`。使用保存的 viewport FOV 90°、引擎 near 10 cm，验证尺寸 1421×1035。

编辑器用户配置另有一条相机。这里明确采用地图内部 `EditorViews[3]`；它没有被证明就是 `2.rdc` 截帧相机。当前几何验证针对这个有来源的视图，不通过 RDC View 数据补齐。

`source_scene.py` 解析原始 `_Internal.obj`，恢复 UV0，将 UE cm 换为 Falcor 米，保留三角形绕序、UV seam、硬法线与共享网格。实例变换单独计算，支持非均匀/负缩放与 UE Rotator；两个 Cube 复用一个 mesh。

Falcor 默认会预变换单实例静态网格，丢失原始对象原点/局部法线。本阶段加入可选 `SceneBuilderFlags.DontPretransformStaticMeshes`，配合 `DontOptimizeGraph` 和 `DontMergeMaterials` 使用。默认行为保持。独立 GPU 测试验证一个非均匀缩放的单实例保留源矩阵；原生 targetmap 验证五个实例的矩阵以及四个源 mesh。

SkySphere 已保留为独立场景角色，当前明确标记 `SkyDomePending`，不进入不透明 PrePass/BasePass；尚未替代 UE 天空材质。Opaque 绘制是两个 Cube、Sphere、Floor。

## 外部材质程序框架

原生 GBuffer 新增通用 `material_program="shader"` 模式。每个 BasePass 的不可变 Shader 提供 `UESurface ueEvaluateMaterial(VSOut, UESurface)`；它先获得共享的默认表面属性，再执行自定义程序，最终仍走公共 DBuffer 和 Schema/Codec。程序不定义 MRT 位布局，不要求新增 capture 特定的程序 ID。

PassDefinition 的 `materialBindings` 提供：

- `textures`：稳定资源 ID，对应 `file`、独立的可选 shader `binding`、`srgb` 和 `generateMips`。所有文件必须登记 `file_inputs`，按内容冻结，并在原生加载前后校验。DDS 请求完整 mip 链时必须本身包含该链，避免 Falcor 的 DDS 导入静默忽略 mip 生成参数。
- `samplers`：过滤、寻址、各向异性、LOD bias。
- `uniforms`：复用框架的显式类型/值/来源与 shader 反射校验。

Scene、View、共享 MaterialCB、几何和 coverage 绑定受保护。即使选中的 Mesh 为空，声明的外部材质也要编译、验证绑定。实时材质变化会重新准备绘制列表和所需程序。Adapter 当前明确拒绝外部 evaluator，避免静默执行不同数学；该类材质使用主 Mesh Pass。

## ProcGrid 有效分支

实现来自原始 `MI_ProcGrid → M_ProcGrid → MF_ProcGrid` 与其 `CheapContrast` 函数图。实例开启 ObjectAligned、TriPlanar，关闭 Side Tint、Water Tint；源码组装器拒绝不同开关组合。

坐标按 Actor 原点减世界位置、投影至归一化对象 XYZ 轴，再除 TileSize=100 cm。因此对象缩放影响纹理覆盖的世界尺寸，不能直接使用完整 inverse object transform。当前 loader 明确拒绝 Actor 与 component 原点不同的源实例。

局部法线使用插值后的原始局部法线；主 Raster 保持插值世界法线未归一化，乘对象矩阵转置恢复局部法线。`saturate(lerp(-1,2,abs(n.x/z)))` 得到两级投影权重。纹理 R 对 q 的三投影产生 Wire，G 对 q×0.5 产生 Checker；隐式导数采样保留 mip 选择。

`lineMask=1-Wire`；BaseColor 为线色与两棋盘色的混合；Roughness 为 0.3 与 0.5/0.65 棋盘混合；Metallic 为 `1-lineMask`。参数来自源图默认值和实例覆盖，不使用旧 `RDCGrid` 的数值。BasicShapeMaterial 使用实际源默认色约 0.9、Roughness 0.6407、默认 Specular 0.5。

源节点索引（相对导出 Materials 目录）：`M_ProcGrid.t3d` 228/237/246/255/399/406/435/485；`MF_ProcGrid.t3d` 181/319/348/356/424/433/442/451/462/570/691/705/719/727–775/781/816/829；`CheapContrast.t3d` 29/37/81/111。实际导出文件名含 `Engine__...` 前缀，清单保存准确路径。

## 实测

- 15 项新增 CPU 源转换测试，包含独立组合旋转、错误绕序/单位/法线变异验证；当前 CPU 合计 345 项通过。
- `build/targetmap-object-space-build.log`、`build/targetmap-final-build.log` 保存原生构建输出。
- 外部材质 GPU 验证 `build/ue-lighting-closure-cache/run-8gxjbqua/process-result.json`：原始线性纹理/参数进入浮点 Packed 测试格式，源文件变更不影响当前快照，reserved/空选择未知 binding 拒绝，live constant→shader 变更通过。它隔离了外部 evaluator，不将硬件 sRGB 解码近似称为 float 精确一致。
- 单实例对象坐标：`build/ue-lighting-closure-cache/run-1isy93c3/process-result.json`。
- targetmap 原生证据：`build/targetmap-gpu/run-3j5ox9q0/result.json`，对应 launcher `run-zxk5kgib`，保存全部 Packed MRT、实际 Depth/Stencil planes 与三帧数组。Depth/Base0/Base1 实测 draw 数 4/3/1，index 数 144、144、288、2880，没有 sourceGeometry sidecar。
- 从原始网格独立构建 CPU 射线，与 native Decode 比较 819 个非边界覆盖样本：Floor 691、Sphere 15、Cube 52、Cube2 61；最大位置误差 0.00049894 米，法线分量最大误差 0.00097752。这个预算覆盖源 OBJ 六位小数与 Falcor 打包法线，不声称原始 float 位型一致。
- 3 帧 Packed/Depth/Decoded 几何不变，方向光进入已有 UE Lighting 数学，自动曝光历史反馈生效。Atlas 六格为 BaseColor、UE Normal、Material、Depth、未加阴影的 Directional Lighting、Coverage。

## 当前限制和下一步

这里已实现源场景闭环；后续同日的自产 CSM 已完成并接入 Lighting，详见 [原生阴影与验证](ue-legacy-native-csm.md)。天空/GI/SSR、完整后处理及 WebRTC 尚未实现。原纹理在 Falcor 中生成 mip；UE 平台压缩、mip 构建、流送和完整 sampler/ViewMipBias 还没有证明一致。源相机也未与 capture 配对，不能以此报告宣称 `2.rdc` 图像对齐。

当前场景方向光级联参数、深度、PCF、过渡及 Lighting 阴影消费均来自原生管线。下一步继续源天空与环境照明；不做 HZB、剔除、LightGrid、atlas packing 等优化结构的独立对齐。
