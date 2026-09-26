"""Selected native Scene draw lists shared by stock and custom GBuffer passes."""
import json
from pathlib import Path
import sys
import tempfile
import runpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'build/m0-evidence/python'))
import numpy as np
import falcor

OUT = ROOT/'build/native-raster-draw-list'
OUT.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix='run-', dir=OUT))
print('NATIVE_MESH_SELECTION_EVIDENCE '+str(out), flush=True)
m.loadScene(str(ROOT/'scripts/customrenderpipline/reference_scene.pyscene'))
m.resizeFrameBuffer(128, 72)
m.clock.pause()
m.ui = False
m.renderFrame()
# RED must fail on the actually absent native Scene API, not on plugin configuration.
blue = m.scene.get_raster_instance_ids(['blue'])
all_ids = m.scene.get_raster_instance_ids()
assert blue and set(blue) < set(all_ids)
rest = sorted(set(all_ids)-set(blue))
selection = m.scene.create_raster_draw_list(blue+blue)
assert list(selection.instance_ids) == sorted(blue)
assert selection.draw_count == len(blue)
assert 0 < selection.batch_count <= 4
assert m.scene.create_raster_draw_list([]).draw_count == 0
try:
    m.scene.create_raster_draw_list([2**31])
except RuntimeError:
    pass
else:
    raise AssertionError('Accepted invalid instance ID')
for kind in ('GBufferRaster', 'CustomRenderPiplineGBufferPass'):
    for invalid in (None, 'blue', [-1], [2**32], [0.5], [True]):
        try:
            falcor.createPass(kind, {'instanceIDs': invalid})
        except RuntimeError:
            pass
        else:
            raise AssertionError('Accepted invalid instanceIDs: '+repr(invalid))

def render(label, ids=None):
    props = {} if ids is None else {'instanceIDs': ids}
    graph = falcor.RenderGraph(label)
    graph.addPass(falcor.createPass('CustomRenderPiplineGBufferPass', props), 'Custom')
    graph.addPass(falcor.createPass('GBufferRaster', {**props, 'samplePattern': 'Center'}), 'Stock')
    for port in ('colorRoughness', 'normal', 'depth'):
        graph.markOutput('Custom.'+port)
    for port in ('posW', 'diffuseOpacity', 'specRough', 'mtlData', 'depth'):
        graph.markOutput('Stock.'+port)
    m.addGraph(graph)
    m.setActiveGraph(graph)
    m.renderFrame()
    color = np.array(graph.getOutput('Custom.colorRoughness').to_numpy(), copy=True)
    mask = np.array(graph.getOutput('Custom.normal').to_numpy(), copy=True)[..., 3] > 0
    stock_mask = np.asarray(graph.getOutput('Stock.posW').to_numpy())[..., 3] > 0
    np.testing.assert_array_equal(mask, stock_mask)
    np.testing.assert_allclose(color[mask, :3], graph.getOutput('Stock.diffuseOpacity').to_numpy()[mask, :3], atol=2e-6, rtol=0)
    np.testing.assert_allclose(color[mask, 3], graph.getOutput('Stock.specRough').to_numpy()[mask, 3], atol=2e-6, rtol=0)
    depth = np.array(graph.getOutput('Custom.depth').to_numpy(), copy=True).reshape(72, 128)
    np.testing.assert_allclose(depth, graph.getOutput('Stock.depth').to_numpy().reshape(72, 128), atol=1e-6, rtol=0)
    saved = graph.getPass('Custom').getDictionary()
    assert saved == props
    stock_saved = graph.getPass('Stock').getDictionary()
    assert ('instanceIDs' in stock_saved) == (ids is not None)
    if ids is not None:
        assert stock_saved['instanceIDs'] == ids
    return graph, color, mask, depth

full, color_full, mask_full, depth_full = render('SelectionAll')
first, color_blue, mask_blue, depth_blue = render('SelectionBlue', blue)
second, color_rest, mask_rest, depth_rest = render('SelectionRest', rest)
empty, color_empty, mask_empty, depth_empty = render('SelectionEmpty', [])
assert mask_blue.any() and mask_rest.any() and not mask_empty.any()
assert not np.any(color_empty) and np.all(depth_empty == 1)
np.testing.assert_array_equal(mask_full, mask_blue | mask_rest)
np.testing.assert_allclose(depth_full, np.minimum(depth_blue, depth_rest), atol=1e-6, rtol=0)
blue_front = mask_blue & (depth_blue < depth_rest-1e-6)
rest_front = mask_rest & (depth_rest < depth_blue-1e-6)
assert blue_front.any() and rest_front.any()
np.testing.assert_allclose(color_full[blue_front], color_blue[blue_front], atol=2e-6, rtol=0)
np.testing.assert_allclose(color_full[rest_front], color_rest[rest_front], atol=2e-6, rtol=0)
# A selection is local to each pass and does not change another graph's Scene.
m.setActiveGraph(full)
m.renderFrame()
np.testing.assert_array_equal(full.getOutput('Custom.colorRoughness').to_numpy(), color_full)
empty.updatePass('Custom', {'instanceIDs': blue})
stock_settings = dict(empty.getPass('Stock').getDictionary())
stock_settings['instanceIDs'] = blue
empty.updatePass('Stock', stock_settings)
m.setActiveGraph(empty)
m.renderFrame()
np.testing.assert_array_equal(empty.getOutput('Custom.colorRoughness').to_numpy(), color_blue)
# Run the delivered example, including native Scene reload and complementary selections.
example = runpy.run_path(str(ROOT/'scripts/customrenderpipline/native_mesh_selection.py'), init_globals={'m': m})
m.renderFrame()
assert np.any(example['graph'].getOutput('Special.color').to_numpy())
assert np.any(example['graph'].getOutput('Ordinary.diffuseOpacity').to_numpy())
assert not (set(example['special_ids']) & set(example['ordinary_ids']))
(out/'result.json').write_text(json.dumps({'status': 'passed', 'native_scene_api': True,
    'stock_and_custom_share_selection': True, 'default_unchanged': True, 'empty_draws_none': True,
    'independent_pass_selection': True, 'property_update': True, 'delivered_example': True, 'blue_instances': blue,
    'other_instances': rest, 'visible_pixels': int(mask_full.sum())}, indent=2))
print('NATIVE_MESH_SELECTION_PASS', flush=True)
exit()
