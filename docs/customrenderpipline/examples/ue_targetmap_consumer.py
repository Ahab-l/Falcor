from falcor import *
import json

# UE compatibility remains a consumer. The core plugin only receives explicit
# attachment formats and shaders; UE material/lighting code lives beside this script.
def ue_targetmap_graph(scene, gbuffer_definition):
    loadPlugin("customrenderpipline")
    g = RenderGraph("UE_TargetMap_Consumer")
    g.setScene(scene)

    # The restored UE consumer supplies this definition and its encode shader.
    gbuffer = createPass("CustomRenderPiplineGBufferPass", {
        "definition": gbuffer_definition,
    })
    g.addPass(gbuffer, "UEGBuffer")

    # This is the consumer's shading stage. The shader decodes the declared
    # packed fields and applies the restored UE lighting equations.
    shading = createPass("CustomRenderPiplineFullscreenPass", {
        "shader": {"file": "ue_consumer/shaders/targetmap_shading.slang", "pixel": "psMain"},
        "resources": [
            {"name": "packed0", "direction": "input", "binding": "gPacked0", "format": "RGBA16Float"},
            {"name": "packed1", "direction": "input", "binding": "gPacked1", "format": "RGBA16Float"},
            {"name": "depth", "direction": "input", "binding": "gDepth", "format": "D32Float"},
            {"name": "shading", "direction": "output", "binding": "gShading", "format": "RGBA16Float", "slot": 0},
        ],
    })
    g.addPass(shading, "UEShading")
    g.addEdge("UEGBuffer.baseColorRoughness", "UEShading.packed0")
    g.addEdge("UEGBuffer.normalMaterial", "UEShading.packed1")
    g.addEdge("UEGBuffer.depth", "UEShading.depth")
    g.markOutput("UEShading.shading")

    # Verification is inserted before Bloom/Tonemap/post-processing.
    catalog = json.loads(customRenderPiplineOutputCatalog(g))
    return g, catalog
