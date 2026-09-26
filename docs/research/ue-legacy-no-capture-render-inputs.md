# Corrected input boundary

2026-09-10: Framework first, then source-project reconstruction. RDC intermediate results are observation/offline comparison only. Previous capture-fed stage isolation is retired.

| Prior dependency | Previous use | Required independent producer |
|---|---|---|
| E2624 SceneColor | Initial Lighting HDR | BasePass/sky/GI/composition |
| E2655 ShadowMask | Light attenuation | Native shadow depth/projection |
| E2655 white AO | Scene AO fixture | Native default resource or active AO algorithm |
| Captured R16 atlas | CSM projection test | Native allocation/caster selection/depth |
| View matrices/PreView/inverse depth | Geometry and reconstruction | Authored camera and UE View setup |
| PreExposure 1.0749151706695557 | Material/lighting exposure | Exposure/history algorithm |
| GPUScene transforms/high-relative positions/packed flags | Source sidecars | Actor TRS and native scene encoding |
| Cascade matrices/bias/fixed 11 draws | Proposed native-depth inputs | CSM setup/culling/submission |
| PreintegratedSkinBRDF LUT | Separate model regression | Independent source asset or generated LUT |
| Mesh/grid texture/material/light parameters | Capture reconstruction | Source-project assets/settings export |
| PostVS expected values and inverse view size | Historical GPU diagnostic observers/VS probes | CPU-only capture comparisons; native inputs in rendering |

Original local UE functions remain valid implementation sources. Actual Mesh draws produced GBuffer/depth, but captured camera/instance state means those results did not prove independent generation of their upstream inputs.

Known live replay interfaces are rejected by Python snapshot/replay and native Config before their resources are consumed. Reference Lighting mode is disabled without an override. CSM prototypes are unregistered/unbuilt; the newly drafted depth pass was never compiled or GPU executed. RDC live GBuffer/Lighting and captured Skin LUT upload/test entries fail explicitly. Independent synthetic tests use authored exposure 1.25; automatic exposure is still unimplemented and the UE project was unchanged.

Validation: 184 CPU tests (`build/no-rdc-input-cpu-all-v2.log`), native build, 13 runtime rejection cases and authored-scene Lighting/Schema HDR relocation (`build/no-rdc-input-gpu/run-auan5v4k/result.json`) passed. This does not authenticate arbitrary relabeled external resources/custom shaders or complete source-project import/framework/final rendering.

Current plan: `docs/superpowers/plans/2026-09-10-framework-before-reproduction.md`. Existing Schema/MeshPolicy and Falcor graph infrastructure are retained; generalized assembly continues the original multi-BasePass design.
