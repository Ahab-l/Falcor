# UE Legacy 多模型 GBuffer 实施计划

> **For agentic workers:** 使用 subagent-driven-development / executing-plans，按步骤实现并以实际GPU与原始数据验收。工作目录为现有 `E:/Project/falcor/Falcor-m0`；不提交、不改动UE/RDC原件。

**Goal:** 在已确认的 Schema/Codec 架构中接入真实 UE 模型的 GBuffer 逻辑，保持当前 DefaultLit Capture 逐位一致，为后续模型Lighting分派提供正确数据。

**Architecture:** Packed Schema管理布局、模型ID、有效字段及常量/consumer路由；UESurface承载原始材质属性，Shader Codec实现UE编码/解码数学。扩展Schema与当前DefaultLit profile并存，新的MaterialProgram输入同时供Mesh与显式Adapter使用。

**Tech Stack:** 本机UE5.8.1 legacy Shader源码、Falcor/D3D12、Slang、Python生成器与GPU原始buffer oracle。

## 实施边界

本阶段针对Unlit、Subsurface、PreintegratedSkin、TwoSidedFoliage、ClearCoat及同族Cloth的真实GBuffer数据分支。保留5-bit模型ID。各模型Lighting、SubsurfaceProfile资源/条件降级、Hair/Eye/Water以及自定义Toon模型随其需要的资源/算法继续接入，不能把ID别名当作算法完成。当前不增加UE材质资产或捕获，新的数值证明注明来自本机源码与独立oracle，不能声称已有新模型UE GPU Capture。

Schema仍不承载sqrt、roughness clamp、octahedral normal等数学。Unlit所需的每模型Schema常量覆盖仅能覆盖已有Schema常量，不能覆盖Codec字段。Consumer可声明公共字段及按模型追加的字段，未提供字段必须在生成/原生加载阶段拒绝。

## 任务

- [x] 1. 固定源码依据：追踪ShadingModelsMaterial、DeferredShadingCommon与BasePassPixelShader，记录ID、CustomData、Unlit附件及编译条件；保存源码行号/哈希，决定每模型支持的完整分支边界。
- [x] 2. 先写Schema回归再实现 `models[].constant_overrides` 与 `consumers.*.required_fields_by_model`：覆盖未知模型/字段、常量类型/位宽、禁止覆盖数学、缺consumer字段、规范化哈希和未使用新特性的兼容性。原生Config同时校验每模型consumer需求。
- [x] 3. 扩展逻辑UESurface、原始材质输入和Mesh/Adapter绑定；新增专用Codec与契约、OpaqueModels Schema，GBufferD通过Schema字段路由。保持DefaultLit数值公式不变；必须显式验证不支持的条件，不能静默忽略。
- [x] 4. GPU验收：混合模型场景通过真正Mesh Pass生产Packed附件，按模型解析CustomData与原始UE材质值；独立CPU oracle比较原始字节/位和decode结果。覆盖Unlit ID0与背景区分、Subsurface颜色/opacity边界、ClearCoat粗糙度边界及底层法线分支，比较单节点/按模型拆分、Schema-only布局迁移和显式Adapter。
- [x] 5. 重新运行严格DefaultLit RDC、Schema、Adapter和相关资源身份回归；独立规格/质量审查后写报告、机器证据并同步主规划。若当前数值分支发现缺口，继续定位，不放宽到视觉近似。

## 验证命令

离线：`python -m unittest discover -s scripts/ue_legacy -p 'test_*.py'`。

构建：`tools/.packman/cmake/bin/cmake.exe --build build/windows-vs2022 --config Release --target UELegacy --parallel 8`。

GPU：使用 `build/windows-vs2022/bin/Release/Mogwai.exe --headless --device-type d3d12 --gpu 0 --enable-debug-layer --script <绝对脚本路径>`。先运行新的model_codec_smoke.py，再运行rdc_gbuffer_smoke.py、schema_smoke.py与adapter_smoke.py；GPU与构建顺序执行。

## 数值诊断记录（已解决）

131项离线测试通过。Schema扩展不承载新数学，真实七模型已编译；DefaultLit严格RDC原始NPZ仍为9bf18026…。多模型首轮raw失败已定位为CPU nearest-even假设与本机RTV的0.5量化边界差异（8bit127、10bit511）。独立fullscreen RTV探针完全绕过Material/Schema/Codec，并以RGBA32Float平行输出验证输入位未改；按D3D §3.2.3.6资格校验硬件转换，随后最终packed比较仍要求逐位相等。独立审查发现并修复JSON布尔数值误接受、可选normal字段和Schema float32溢出；其后8组模型GPU验收及最终回归均通过。

## 本批完成状态

本计划的七模型GBuffer范围已验收：131离线、18原生（17GPU+1CPU）、8模型GPU case、12原生非法输入、6项最终回归通过。保留DefaultLit NPZ 9bf18026…。当前DefaultLit generation为7a16385f…（共享Surface扩展改变CodecHash，数值未变）。源码与证据共147文件已CAS归档并校验。报告：`../../research/ue-legacy-model-codecs.md`。本批未完成额外资源/通道模型、各模型Lighting或整个骨干；原实施顺序和自动曝光要求持续有效。
