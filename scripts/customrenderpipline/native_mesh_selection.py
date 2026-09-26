"""Two independent mesh selections using Falcor Scene's native draw-list API."""
from pathlib import Path
import falcor

ROOT = Path(__file__).resolve().parents[2]
m.loadScene(str(ROOT/'scripts/customrenderpipline/reference_scene.pyscene'))
special_ids = m.scene.get_raster_instance_ids(['blue'])
ordinary_ids = sorted(set(m.scene.get_raster_instance_ids()) - set(special_ids))

graph = falcor.RenderGraph('NativeMeshSelection')
graph.addPass(falcor.createPass('GBufferRaster', {'instanceIDs': ordinary_ids}), 'Ordinary')
graph.addPass(falcor.createPass('CustomRenderPiplineGBufferPass', {
    'instanceIDs': special_ids,
    'definition': str(ROOT/'scripts/customrenderpipline/examples/native_gbuffer/Packed.json'),
}), 'Special')
graph.markOutput('Ordinary.diffuseOpacity')
graph.markOutput('Special.color')
graph.markOutput('Special.materialBits')
m.addGraph(graph)
m.setActiveGraph(graph)
