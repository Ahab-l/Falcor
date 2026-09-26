# Native GBuffer reuse implementation plan

**Goal:** Apply the user's native-first removal rule to the first item under discussion: configurable GBuffer attachments/channels/bit encoding. Ordinary Falcor scenes must use native Scene/MaterialSystem/rasterize/RenderGraph without the old whole-pipeline JSON/snapshot/scene-definition prerequisites.

**Architecture:** The public CustomRenderPiplineGBufferPass becomes a normal RenderPass with a valid default, a JSON definition property, native reflection/allocation, and authored Slang codecs. The previous primary mesh implementation contains UE-specific material/coordinate/stencil/source-geometry behavior that stock Falcor does not reproduce; identify it explicitly as UEReferenceGBufferPass and migrate its existing research callers. Do not retain two generic default implementations. Further readback/Cube/history/core-patch removals belong to the subsequent items the user asked to discuss individually.

**Tech stack:** Falcor eb540f67, C++17/Slang, native RenderGraph and MaterialSystem, Windows D3D12, Python Mogwai acceptance.

- [x] Archive current tracked patch and affected untracked sources/scripts under build/native-gbuffer-refactor, verify archive hashes. Preserve original workspace, captured assets, research evidence and existing UE algorithms. No commits/merges.
- [x] Add native_gbuffer_smoke.py. First operation creates CustomRenderPiplineGBufferPass with empty Properties; current implementation must fail because it requires sceneDefinition/schemaPath. Acceptance then renders a stock scene, compares albedo/roughness/normal against GBufferRaster, creates a different three-attachment layout with integer bit packing, and verifies raw pixels and serialized Properties reconstruction using native graph APIs.
- [x] Implement CustomRenderPiplineNativeGBuffer.h/.cpp and native default/packed example Slang. Parse layout once at construction/UI selection, declare named attachment formats in reflect(), build native Scene programs, rasterize through Scene::rasterize(), expose definition selection through renderUI and getProperties. Changes in definition rebuild native resources. No custom scheduler, material table, raw readback or graph validator.
- [x] Rename the previous UE-specific primary writer to UEReferenceGBufferPass in active plugin/research scripts/tests and register it in UEReferenceExtension. Keep capture/source files unchanged. The existing generic Shader/History/Observer mechanisms remain for later discussion; do not claim they have been removed.
- [x] Add native_gbuffer.py as the normal GBuffer usage entry using RenderGraph/createPass/addEdge/markOutput. Document native material semantics and supported configuration; old UE/RDC cases explicitly use the reference writer.
- [x] Build serially, run the new native acceptance and relevant old framework/material/adapter regressions; run the full Python suite with Anaconda 3.11 and workspace TEMP without the embedded Python 3.10 numpy PYTHONPATH override. Check final diff and record exactly which old default dependencies were removed and which core patches remain.

Validation commands (working directory E:/Project/falcor/Falcor-m0):

```powershell
& .\tools\.packman\cmake\bin\cmake.exe --build .\build\windows-vs2022 --config Release --target customrenderpipline --parallel 4
& .\build\windows-vs2022\bin\Release\Mogwai.exe --headless --enable-debug-layer --script scripts/customrenderpipline/native_gbuffer_smoke.py
& E:/IDE/Anaconda/python.exe -X utf8 -m unittest discover -s scripts/customrenderpipline -p 'test_*.py'
```

This is the first native replacement, not authorization to erase unmatched UE rendering algorithms or to claim all 23 core patches have been removed. The new generic pass uses stock Falcor APIs; its execution in the existing patched build alone does not prove backend fixes unnecessary for the reference cases.

Validation note: the old adapter_smoke.py was attempted and rejected by pre-existing captured primitive_flags validation, confirmed byte-identical against before.zip. It is not counted as passed. Three applicable GPU suites and 469 Python tests passed; evidence index: build/native-gbuffer-refactor/verification.json.
