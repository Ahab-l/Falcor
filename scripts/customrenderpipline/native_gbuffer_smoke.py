"""Native graph/material acceptance; no SchemaPipeline or generated scene contract."""
import json
from pathlib import Path
import sys
import tempfile
import runpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'build/m0-evidence/python'))
import numpy as np
import falcor

out = Path(tempfile.mkdtemp(prefix='run-', dir=ROOT/'build/native-gbuffer-refactor'))
print('NATIVE_GBUFFER_EVIDENCE '+str(out), flush=True)
# This line failed against the old writer, which required sceneDefinition/schemaPath.
default_pass = falcor.createPass('CustomRenderPiplineGBufferPass', {})
m.loadScene(str(ROOT/'scripts/customrenderpipline/reference_scene.pyscene'))
m.resizeFrameBuffer(128, 72)
m.clock.pause()
m.ui = False

def render(name, props, outputs):
    graph = falcor.RenderGraph(name)
    graph.addPass(falcor.createPass('CustomRenderPiplineGBufferPass', props), 'Custom')
    graph.addPass(falcor.createPass('GBufferRaster', {'samplePattern': 'Center'}), 'Stock')
    for output in outputs:
        graph.markOutput('Custom.'+output)
    for output in ('diffuseOpacity', 'specRough', 'guideNormalW', 'mtlData', 'posW', 'depth'):
        graph.markOutput('Stock.'+output)
    m.addGraph(graph)
    m.setActiveGraph(graph)
    m.renderFrame()
    return graph

graph = render('NativeGBufferDefault', {}, ['colorRoughness', 'normal', 'depth'])
color = np.array(graph.getOutput('Custom.colorRoughness').to_numpy(), copy=True)
normal = np.array(graph.getOutput('Custom.normal').to_numpy(), copy=True)
mask = normal[..., 3] > 0
assert mask.sum() > 100
np.testing.assert_array_equal(mask, np.asarray(graph.getOutput('Stock.posW').to_numpy())[..., 3] > 0)
np.testing.assert_allclose(graph.getOutput('Custom.depth').to_numpy(), graph.getOutput('Stock.depth').to_numpy(), atol=1e-6, rtol=0)
reference = np.array(graph.getOutput('Stock.diffuseOpacity').to_numpy(), copy=True)
roughness = np.array(graph.getOutput('Stock.specRough').to_numpy(), copy=True)[..., 3]
reference_normal = np.array(graph.getOutput('Stock.guideNormalW').to_numpy(), copy=True)
np.testing.assert_allclose(color[mask, :3], reference[mask, :3], atol=2e-6, rtol=0)
np.testing.assert_allclose(color[mask, 3], roughness[mask], atol=2e-6, rtol=0)
np.testing.assert_allclose(normal[mask, :3], reference_normal[mask, :3], atol=2e-6, rtol=0)

definition = {
    'shader': str(ROOT/'Source/RenderPasses/customrenderpipline/NativeGBuffer.3d.slang'),
    'defines': {'PACKED_LAYOUT': '1'},
    'attachments': [
        {'name': 'materialBits', 'format': 'R32Uint'},
        {'name': 'color', 'format': 'RGBA8Unorm'},
        {'name': 'normal', 'format': 'RGBA16Float'},
    ],
}
path = out/'Packed.json'
path.write_text(json.dumps(definition), encoding='utf-8')
packed = render('NativeGBufferPacked', {'definition': str(path)}, ['materialBits', 'color', 'normal'])
words = np.array(packed.getOutput('Custom.materialBits').to_numpy(), copy=True).reshape(72, 128)
np.testing.assert_array_equal(words[mask] & 255, np.rint(roughness[mask]*255).astype(np.uint32))
ids = np.asarray(packed.getOutput('Stock.mtlData').to_numpy())[..., 0]
np.testing.assert_array_equal((words[mask] >> 8) & 65535, ids[mask])
assert not np.any(words[mask] & (1 << 24))  # This native fixture is not emissive.
assert packed.getOutput('Custom.color').format == falcor.ResourceFormat.RGBA8Unorm
assert packed.getOutput('Custom.normal').format == falcor.ResourceFormat.RGBA16Float
packed_normal = np.asarray(packed.getOutput('Custom.normal').to_numpy())
np.testing.assert_allclose(packed_normal[mask, :3], normal[mask, :3], atol=5e-4, rtol=0)
# Native serialization/recreation and marking an extra output work without sealing.
saved = dict(packed.getPass('Custom').getDictionary())
assert saved == {'definition': str(path)}
packed.updatePass('Custom', saved)
packed.markOutput('Custom.depth')
m.renderFrame()
assert packed.getOutput('Custom.depth') is not None
np.testing.assert_array_equal(packed.getOutput('Custom.materialBits').to_numpy().reshape(72, 128), words)

invalid = out/'Invalid.json'
bad = dict(definition)
bad['attachments'] = [{'name': 'duplicate', 'format': 'RGBA32Float'}]*2
invalid.write_text(json.dumps(bad))
try:
    packed.updatePass('Custom', {'definition': str(invalid)})
except RuntimeError:
    pass
else:
    raise AssertionError('Duplicate attachment names accepted')
m.renderFrame()
np.testing.assert_array_equal(packed.getOutput('Custom.materialBits').to_numpy().reshape(72, 128), words)
(out/'comparison.json').write_text(json.dumps({
    'covered_pixels': int(mask.sum()),
    'albedo_max_abs_error': float(np.max(np.abs(color[mask, :3] - reference[mask, :3]))),
    'roughness_max_abs_error': float(np.max(np.abs(color[mask, 3] - roughness[mask]))),
    'normal_max_abs_error': float(np.max(np.abs(normal[mask, :3] - reference_normal[mask, :3]))),
}, indent=2))

# Exercise the delivered entry and native BlitPass connection, including the relative JSON shader path.
entry = runpy.run_path(str(ROOT/'scripts/customrenderpipline/native_gbuffer.py'))
for use_packed in (False, True):
    preview = entry['render_graph_native_gbuffer'](use_packed)
    m.addGraph(preview)
    m.setActiveGraph(preview)
    m.renderFrame()
    pixels = np.asarray(preview.getOutput('Preview.dst').to_numpy())
    expected = reference if not use_packed else np.rint(np.clip(reference, 0, 1)*255)/255
    if np.issubdtype(pixels.dtype, np.integer):
        pixels = pixels.astype(np.float32)/255
    np.testing.assert_allclose(pixels[mask, :3], expected[mask, :3], atol=1/255, rtol=0)
    m.removeGraph(preview)
(out/'result.json').write_text(json.dumps({'status': 'passed', 'native_material_comparison': True,
    'layouts': 2, 'integer_bit_encoding': True, 'native_property_roundtrip': True,
    'native_output_edit': True, 'invalid_config_preserves_pass': True, 'delivered_demo_and_blit': True}, indent=2))
print('NATIVE_GBUFFER_PASS', flush=True)
exit()
