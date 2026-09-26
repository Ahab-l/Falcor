"""Ordinary Falcor graph: native scene/materials, configurable MRTs, stock BlitPass."""
from pathlib import Path
import falcor

ROOT = Path(__file__).resolve().parents[2]


def render_graph_native_gbuffer(packed=False):
    graph = falcor.RenderGraph('NativeGBuffer')
    props = {'definition': str(ROOT/'scripts/customrenderpipline/examples/native_gbuffer/Packed.json')} if packed else {}
    graph.addPass(falcor.createPass('CustomRenderPiplineGBufferPass', props), 'GBuffer')
    graph.addPass(falcor.createPass('BlitPass', {'outputFormat': 'RGBA32Float'}), 'Preview')
    graph.addEdge('GBuffer.color' if packed else 'GBuffer.colorRoughness', 'Preview.src')
    graph.markOutput('Preview.dst')
    graph.markOutput('GBuffer.normal')
    graph.markOutput('GBuffer.depth')
    if packed:
        graph.markOutput('GBuffer.materialBits')
    return graph


graph = render_graph_native_gbuffer()
try:
    m.addGraph(graph)
    m.loadScene(str(ROOT/'scripts/customrenderpipline/reference_scene.pyscene'))
except NameError:
    pass  # RenderGraphEditor imports the graph without Mogwai's global m.
