# UE Lighting 原码复用第二批

2026-09-10，本批已接入生产并通过所列回归。此批将 LightingCommon 中 Pow4/Pow5、sqrtFast、Lambert/GGX/Smith/Schlick、New_a2/EnergyNormalization/SpecularGGX 与 Capsule/CreateAreaLight 入口转为 UE 原函数调用。保留原源码，只适配必要的类型、字段、宏和绑定。

**RDC 与回归场景边界：** 用户再次指出，1.rdc 中没有 ClearCoat/Skin/Cloth。这份 Capture 的四个不透明 Mesh 均为 DefaultLit1；本批其他模型只用于检查此前已实现模型的共享函数回归，没有加入 RDC 重建场景，也不作为 RDC 对齐证据。后续主线优先推进该 Capture 实际使用的 DefaultLit、方向光 CSM 和上游光照，不扩展额外模型。

## 原码与适配

候选：`build/ue-lighting-closure-reuse/run-7896wpt0`，manifest SHA256 `481f548f8dcd833b9d1a1f32550470ab452a4746413ef9fbe58b28c0b39653cf`。新增 11 个 `.ush` 文件（30 段原字节）和两个适配头，只替换 Common 两个区间。此前 diffuse mad、F0 和原码 Init/Sphere 接口保持原字节。

保留原注释、版权、MIT notice、条件分支和 PC BRANCH 属性。局部命名空间把 half/MaterialFloat 映射为 PC float；GetCapsule 输入视图只提供实际读取的四字段，Area 包装投影现有八字段。这不代表完整 UE ABI，也不启用 Rect、各向异性或 Substrate。Schema 的布局、ID、资源和分派契约保持。

`scripts/ue_legacy/ue_lighting_sources.json` 固定两批共 13 个原码文件、32 段源字节；`import_ue_lighting.py` 可从固定引擎重建，在任何输出写入前验证所有输入，拒绝静默跟随源文件变化。

导入工具独立 CPU 审查：`build/ue-lighting-importer-independent-review/run-75cbd922/review.json`，SHA256 `1eed8567f8e4550ee209dd37623a43d44c4c6562a9d649300ace17a15d0eb518`。13 输出/32 区间对应原始来源，66 个故障探针全部拒绝且未写输出；正常校验不修改文件。该审查观察安装后 GREEN，安装前 RED 由根任务另行记录。

## 私有 GPU 验证

结果：`build/ue-lighting-closure-gpu/run-d1xl2w6b/result.json`，SHA256 `c73fe54cba1ab351859600de559ccb5ebeee39b94cac0ee4b7c195c4da8761f1`。运行器：`build/ue-lighting-closure-cache/run-ds_zo8r0`，退出 0。

- 两版各 224 个模型样本通过既有独立 oracle，输出逐位相同。
- 两版各 187 个 Capsule 样本通过原 area/context/energy/lobe 预算、sqrtFast 位型及零透射检查，输出逐位相同。生成显式使用私有 Codec root。
- RDC 的 13 份完整数组逐位相同，九份非 Lighting 数组和四份 Lighting alpha 有强保护。
- 运行期间生产、私有 Shader 及运行时身份保持。严格 E2655 HDR 仍有 31 像素/31 通道各差 1 half ULP，RGBA `[14,8,9,0]`。

独立回归（非 RDC）：`build/ue-lighting-closure-broader-gpu/run-f2izuhmo/result.json`，SHA256 `32b3e671ffa734663879be7145c95e6b022cc7e27d1ced05553db4c93ce9f345`。两个既有 seed 的四图中，每模型 256 点通过原预算，两对各 18 份原始数组逐位相同。模型包含 Coat 双法线/Skin/DefaultLit 和 Subsurface/Foliage/Cloth。这仅验证共享函数替换没有破坏既有路径。

独立准入审查：`build/ue-lighting-closure-independent-review/admission-review.json`，SHA256 `950bdf53ce0032c7ae53e90a33315b498de94f5b9beab7bc8b5c84004fcda4df`，173 个文件身份、原函数/适配/Schema、组件原始输出和独立 oracle 复算通过。

生产安装：`build/ue-lighting-closure-install/run-bx8c0ax9/receipt.json`。180 项既有 CPU 测试及新增安装/Schema依赖测试共 181 项通过；新测试在安装前因缺少原码文件正确失败。首次全套调用遗漏 NumPy 的 PYTHONPATH，发生两项导入错误，补回固定依赖路径后通过，未更改测试或预算。构建 `build/ue-lighting-closure-build/run-gwxye78_` 退出 0，使用锁定 CMake 3.24.1。

生产 RDC：`build/ue-lighting-closure-production/run-p1e3_dkq/result.json`，SHA256 `a58c7256615951c769031b64b272f65352ec4f8022280314d1dca2d9b28a9e7b`。完整生产 Codec 树与已验证私有候选同字节，Schema metadata 相同，13 份实际 RDC 输出逐位相同；仍为四个 DefaultLit Mesh、一盏方向光与显式阶段输入。严格 HDR 31 个残差保持，不宣称最终画面完成。

最终 Mesh/Adapter Schema 迁移：`build/ue-lighting-closure-migration/run-2qnqroga/result.json`，两路径各 14 项逻辑输出及物理映射通过，进程退出 0。该组只验证已有接口的布局/ID迁移，不是 RDC 新增光源。首个包装入口未传递 Mogwai 的 exit，导致测试完成后调用 Python SystemExit 而进程退出 1；失败运行保留在 cache/run-hhyk3nh0。新包装只补传原生 exit，重新执行通过，未修改测试/算法。18 份生产/部署原码、适配头和 Common 字节均已核对相同。

本批证据索引：[ue-legacy-lighting-source-reuse-closure-result.json](ue-legacy-lighting-source-reuse-closure-result.json)。索引绑定实际文件身份，详细原始输出保留在列出的 build 目录；不声称这是可脱离运行时独立回放的二进制包。

## 同期输入与阴影取证

初始 BxDF 观察：`build/lighting-dxil-prefix-generations/replay-md97pnx7/native-comparison-v3-archived-worker.json`，SHA256 `5a8cb62712c0c1489ce799d1a97b02f868b0ff039aa675d8d8db072abfddfce2`。固定 43 点的 signed NoL/NoV/VoL 共 129 项与 UE 实测相同。观察发生在 Init 后、Sphere 前，不证明 Sphere 结果相同。实际执行 worker 使用 plan 固定路径，事后归档副本的来源和时间另记于 worker-archive-receipt.json。

原生数据流审查：`build/lighting-bxdf-init-prefix-cache/run-4_jabzi2/native-dataflow-review.json`。观察来自实际上下文，12 个原输出表达式与分支保持。UE fast 与原生 precise 的静态差异仅是线索，不是残差成因或机器 ISA 证明。

阴影首次只读导出：`build/rdc-shadow-provenance/run-5pd03t_f/raw/replay-done.json`。保存四级 projection、atlas/writer 等 84 个不同 payload（484,707,412 原始字节），Capture 前后哈希相同。但 42 项导出缺失使整体未通过：38 项 buffer descriptor 范围和四项图形 draw 保留的 Compute 常量状态待核实，不能声称完整 caster 依赖齐备。实际 Lighting AO 为 FWhiteTexture；替换常量资源不等于实现 AO。移除 ShadowMask fixture 仍需要原生 cascade depth 及 UE projection/filter/fade。

完整 Lighting、阴影/GI/天空/自动曝光、Clustered、SSR、TSR、Web 与最终图像目标继续进行。自动曝光保留，UE/RDC 只读，无暂存、提交或合并。
