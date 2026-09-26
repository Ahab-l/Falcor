"""Generate a generic layout, then use the ordinary native Falcor render graph."""
from pathlib import Path
import sys
import falcor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from generate_native_gbuffer import generate


def render_graph_schema_gbuffer(schema_path=None, output_dir=None):
    artifacts = generate(schema_path or HERE/'examples/schema_gbuffer/Schema.json',
                         output_dir or ROOT/'build/native-gbuffer-schema/demo')
    if artifacts.definition is None:
        raise ValueError('A native GBuffer example needs an authored producer in its Schema')
    graph = falcor.RenderGraph('SchemaGBuffer')
    graph.addPass(falcor.createPass('CustomRenderPiplineGBufferPass',
                                   {'definition': str(artifacts.definition)}), 'GBuffer')
    graph.addPass(falcor.createPass('BlitPass', {'outputFormat': 'RGBA32Float'}), 'Preview')
    graph.addEdge('GBuffer.color', 'Preview.src')
    for output in ('Preview.dst', 'GBuffer.materialBits', 'GBuffer.normal', 'GBuffer.depth'):
        graph.markOutput(output)
    return graph


graph = render_graph_schema_gbuffer()
try:
    m.addGraph(graph)
    m.loadScene(str(HERE/'examples/schema_gbuffer/Scene.pyscene'))
except NameError:
    pass
