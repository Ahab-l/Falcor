# CustomRenderPipline skill example: UE targetmap raw-to-shading check

# This is a consumer-side example. Replace `ue_schema.json` and shader paths with
# the restored UE targetmap consumer's files.
from falcor import *
import json

loadPlugin("customrenderpipline")
g = RenderGraph("UE_TargetMap_Check")
g.setScene(scene)
g.addPass(createPass("CustomRenderPiplineGBufferPass", {"definition": "ue_schema.json"}), "UEGBuffer")
g.addPass(createPass("CustomRenderPiplineFullscreenPass", {
    "shader": {"file": "ue_shading.slang", "pixel": "psMain"},
    "resources": [
        {"name": "baseColorRoughness", "direction": "input", "binding": "gBaseColorRoughness", "format": "RGBA16Float"},
        {"name": "normalMaterial", "direction": "input", "binding": "gNormalMaterial", "format": "RGBA16Float"},
        {"name": "depth", "direction": "input", "binding": "gDepth", "format": "D32Float"},
        {"name": "shading", "direction": "output", "binding": "gShading", "format": "RGBA16Float", "slot": 0},
    ],
}), "UEShading")
g.addEdge("UEGBuffer.baseColorRoughness", "UEShading.baseColorRoughness")
g.addEdge("UEGBuffer.normalMaterial", "UEShading.normalMaterial")
g.addEdge("UEGBuffer.depth", "UEShading.depth")
g.markOutput("UEGBuffer.baseColorRoughness")
g.markOutput("UEGBuffer.normalMaterial")
g.markOutput("UEGBuffer.depth")
g.markOutput("UEShading.shading")

print(json.loads(customRenderPiplineOutputCatalog(g)))
