# UE Legacy M0 执行记录

2026-09-09。实施目录 `E:/Project/falcor/Falcor-m0`，分支 `codex/ue-legacy-m0`，起点 `eb540f6748774680ce0039aaf3ac9279266ec521`。

## 当前状态

M0 的构建、原生光栅、GPU 能力探针、同源配对场景及捕获 profile 校验已运行通过。M1 首条 Packed BasePass 路径现已运行通过（见相邻 M1 记录）；原生资源/view 忠实度缺口仍存在，不能宣布完整 UE ABI 等价。继续完成 M1 的路由与完整验收。

工具链已发现 VS2022 Community 17.14、Windows SDK 10.0.19041.0 与 RTX 4090。当前 PATH 中 cl 来自 VS2019，所以使用 VS2022 CMake generator 明确选择编译器。

`setup.bat` 按仓库原始依赖清单初始化子模块和 Packman；日志位于 `build/m0-evidence/setup.log`。Packman bootstrap 自动将用户级 `PM_PACKAGES_ROOT` 设置为 `E:/packman-repo`。

原始研究、捕获导出保留在 `E:/Project/falcor/Falcor/docs/research/`。本次不更改原始 RDC、UE 源码和用户工程设置，保留自动曝光。

## 实测证据

所有生成日志/输出位于 `build/m0-evidence/`。

| 验证 | 结果 | 证据 |
|---|---|---|
| Release 构建 | Mogwai/GBuffer/PythonImporter/FalcorTest 通过 | build-raster.log、build-probe-fixed.log、后续 probe build 日志 |
| Stock GBufferRaster | RTX 4090、D3D12、640×360，3 帧；36103 覆盖像素，有限输出与单位法线通过 | raster-smoke.log、raster-smoke/ |
| GPU capabilities | 开启 D3D12 debug layer，2/2 通过 | capabilities.log、capabilities.xml |
| 配对 Falcor | 26 三角形；426 采样命中、437 未命中；位置最大误差 5.82725e-5 m、法线误差 5.96046e-8 | reference-raster.log、reference-pair/falcor-raster-result.json |
| 配对 UE | 隐藏 Debug 编辑器生成与独立新进程重载均 exit 0 | ue-reference-build.log、ue-reference-verify.log、reference-pair/ue-verified.json |
| 捕获 profile | 21 个正/负用例通过，7 份源证据 SHA256 验证通过 | scripts/ue_legacy/reference_profile.json、test_reference_profile.py |

两份 Falcor 法线图已目视核对。stock StandardMaterial 仅为基线适配，getter 报告保留其 float16 量化（例如 roughness 0.65 实际为 0.64990234375）；未来 UE 参数来自原始定义，不从 stock BSDF 反推。

## 探针与修复

MRT 为 RGBA16Float、RGB10A2Unorm、BGRA8Unorm、BGRA8UnormSrgb、BGRA8Unorm；DSV 为 D32FloatS8Uint。探针验证原始半精度/10:10:10:2/BGRA 数据、sRGB RGB 编解码、线性 alpha，以及一次清除后多区域绘制保留。slot 4 绑定但不输出，不宣称有有效 CustomData。

reverse-Z clear=0，PrePass GreaterEqual 写 0.75 并拒绝更远深度；BasePass GreaterEqual、不写深度、stencil Always/Replace，ref=0x86、writeMask=0xF6。正反 predicate 检验 0→0x86、0x09→0x8F、深度失败与未覆盖区域保留、只清 stencil 不破坏深度。

发现并修复 Falcor 既有缺陷：`GraphicsState::setStencilRef()` 原本未提交。`RenderContext::drawCallCommon()` 现在每次调用 `encoder->setStencilReference(pState->getStencilRef())`，同样覆盖共享此路径的 indirect draws。修复前 MRT 通过而 stencil 失败，保留 `capabilities-stencil-red.*`；修复后两项通过。未扩展公开 API。

早期全屏 draw E_INVALIDARG 源于 VS/PS 的 SV_Position 寄存器 linkage 不匹配，D3D12 InfoQueue message 660 确认；按 Falcor 全屏 VS 补齐 TEXCOORD 输入后解决。sRGB SRV 误差按 D3D 规范的理想重编码后 sRGB 侧 0.5 ULP 计算，不用任意线性绝对误差放宽标准。

## 原生能力差异及 M1 接续约束

| 项目 | 当前事实 | 后续处理 |
|---|---|---|
| Native allocation | MRT DXGI 10/24/87/91/87、depth 20，均 typed；UE B/C/D、depth 为 typeless | 数值格式可用；原生一致性需要后端 typeless/view reinterpret 支持 |
| Depth-read-only、stencil-writable DSV | Slang gfx view Desc 无 aspect readonly flags，Falcor 使用 DepthWrite 状态 | depth write mask=false 仅保证行为；M1 禁止同时以 SRV 读取该 DSV，原生 view 忠实路径仍待后端扩展 |
| D32S8 plane SRV | depthToColorFormat 不支持组合格式，没有 stencil plane selector | M1 采用明确命名的独立 R32Float 深度读取副本，验证其与 DSV 一致；保留主 D32S8，不替换 ABI 附件 |
| 捕获 binary/source/PDB 身份 | 本机源码可交叉解释，精确匹配未证明 | 保留捕获 shader 与源指纹，不宣称 upstream 通用 ABI |

深度副本是待实现的明确适配路径，不是已经完成的功能。这些缺口不能由行为测试推断为已支持。

## 配对输入与曝光

`reference_scene.json` 提供两端同源顶点、索引、UV、参数、光和相机。UE 厘米/X forward/Z up 转 Falcor 米 `(Y,Z,-X)/100`；两个 cube 与地面，水平 FOV 60°，方向光 10000 lux。

UE 写入隔离 `build/m0-evidence/ue-reference/M0Reference.uproject`。新进程重载验证完整拓扑/UV、法线重算设置、材质连接/数值、实例绑定/变换、相机/光属性与曝光设置。尚未执行该新场景 UE GPU 截帧/法线对比；NullRHI 不作为渲染证明。

自动曝光 Histogram、bias=0、EV100 范围 [-10,20]，override/范围/CVar 均回读。简化场景局部曝光通过中性对比度/detail 与空曲线关闭（无有效 `r.LocalExposure=0` CVar）。原始工程和 1.rdc 的自动/局部曝光保持不变。profile 分别记录 PreExposure=1.0749151706695557、当前 EyeAdaptation=1.0762039422988892，SSGI 已进入方向光后 SceneColor 的事实也保留。

## 复现命令

在 `E:/Project/falcor/Falcor-m0` 执行。工具链：VS2022/MSVC 19.44、SDK 10.0.19041.0、CMake 3.24.1、Slang 2024.1.34、Python 3.10.11。可选 USD/CUDA 关闭；NVAPI/OptiX 不可用不影响本次路径。setup 中一次 nanovdb SSL 失败重试后成功。

```powershell
& .\tools\.packman\cmake\bin\cmake.exe --preset windows-vs2022 -DFALCOR_ENABLE_USD=OFF -DCMAKE_CUDA_COMPILER=NOTFOUND
& .\tools\.packman\cmake\bin\cmake.exe --build build\windows-vs2022 --config Release --target Mogwai GBuffer PythonImporter FalcorTest --parallel 8
& .\tools\.packman\python\python.exe -m pip install --target build\m0-evidence\python numpy==1.26.4
& .\build\windows-vs2022\bin\Release\Mogwai.exe --headless --device-type d3d12 --gpu 0 --script scripts\ue_legacy\raster_smoke.py
& .\build\windows-vs2022\bin\Release\FalcorTest.exe --device-type d3d12 --gpu 0 --test-case UELegacy --enable-debug-layer --xml-report build\m0-evidence\capabilities.xml
& .\build\windows-vs2022\bin\Release\Mogwai.exe --headless --device-type d3d12 --gpu 0 --script scripts\ue_legacy\reference_raster.py
& .\tools\.packman\python\python.exe scripts\ue_legacy\prepare_reference.py
& scripts\ue_legacy\run_ue_reference.ps1 -Mode build
& scripts\ue_legacy\run_ue_reference.ps1 -Mode verify
& .\tools\.packman\python\python.exe scripts\ue_legacy\test_reference_profile.py
& .\tools\.packman\python\python.exe scripts\ue_legacy\validate_reference.py --evidence-dir E:/Project/falcor/Falcor/docs/research/captures/2026-09-09-1
```

UE runner 可用 `-EngineRoot` 指定路径；默认 Debug 编辑器与本机 Python 插件 BuildId 匹配。commandlet 缺少生成器需要的编辑器子系统，故用自动退出的 `-ExecutePythonScript`。本机 Debug 编辑器日志有 AutomationTest 注册错误；Python marker、独立核对和退出码通过不等于整个 UE 编辑器测试套件通过。
