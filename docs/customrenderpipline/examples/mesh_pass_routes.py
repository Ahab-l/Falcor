from falcor import *
import json

# 这是可复制的脚本骨架。把 shader 路径和 scene 替换成 consumer 的资源。
loadPlugin("customrenderpipline")
g = RenderGraph("MeshRoutes")
g.setScene(scene)

routes = [
    {
        "name": "opaque",
        "materials": ["OpaqueMaterial"],
        "properties": {
            "shader": {"file": "shaders/opaque.slang", "vertex": "vsMain", "pixel": "psMain"},
            "colorTargets": [
                {"name": "gbuf0", "format": "RGBA16Float", "slot": 0},
                {"name": "gbuf1", "format": "RGBA16Float", "slot": 1},
            ],
            "depthTarget": {"name": "depth", "format": "D32Float"},
        },
    },
    {
        "name": "hair",
        "materials": ["HairMaterial"],
        "properties": {
            "shader": {"file": "shaders/hair.slang", "vertex": "vsMain", "pixel": "psMain"},
            "colorTargets": [
                {"name": "gbuf0", "format": "RGBA16Float", "slot": 0, "load": "load"},
                {"name": "gbuf1", "format": "RGBA16Float", "slot": 1, "load": "load"},
            ],
            "depthTarget": {"name": "depth", "format": "D32Float", "load": "load"},
            "state": {"depth_enabled": True, "depth_write": False, "cull_mode": "None"},
        },
    },
]

receipt = customRenderPiplineAddMeshPasses(g, scene, routes)
assert [r["name"] for r in receipt] == ["opaque", "hair"]

# The helper only creates passes. The graph author owns connections and outputs.
# g.addEdge("opaque.gbuf0", "Lighting.opaqueGBuffer")
# g.addEdge("hair.gbuf0", "Lighting.hairGBuffer")
# g.markOutput("Lighting.output")
