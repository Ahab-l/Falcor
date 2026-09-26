"""Finite headless native source GBuffer run. No RenderDoc/reference imports.

Run Mogwai --headless --enable-debug-layer --script <this file>.
CRP_TARGETMAP_NATIVE_OUT must name a new directory under build/targetmap-shading-a1.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts/customrenderpipline'), str(ROOT/'build/m0-evidence/python')]
import falcor
import numpy as np
from build_targetmap_scene import identity, verify
from generate_native_gbuffer import generate
from pipeline import make_graph
from targetmap_native_graph import graph_definition, FORMATS
from targetmap_native import read_source_json
from source_platform_texture import native_options


def run(out):
    platform_texture, anisotropy, platform_identities = native_options(ROOT, os.environ)
    scene_path = ROOT/'build/source-targetmap/Scene.json'
    source, scene_read_identity = read_source_json(scene_path)
    if source['capture_inputs'] is not False:
        raise ValueError('Not an original source scene')
    sources = [scene_path, ROOT/'scripts/customrenderpipline/targetmap.pyscene',
               Path(__file__), ROOT/'scripts/customrenderpipline/targetmap_native.py',
               ROOT/'scripts/customrenderpipline/targetmap_native_graph.py',
               ROOT/'scripts/customrenderpipline/source_platform_texture.py',
               ROOT/'scripts/customrenderpipline/source_scene.py']
    sources.extend(Path(entry['path']) for entry in platform_identities)
    for mesh in source['source_meshes'].values():
        sources.append(verify(mesh['file']))
    sources.append(verify(source['source_texture']['original_export']['source_image']))
    example = ROOT/'scripts/customrenderpipline/examples/targetmap_shading'
    sources.extend(example/name for name in ('Schema.json', 'SurfaceCodec.slangh', 'Material.slangh', 'Mesh.slang', 'RenderContext.json'))
    render_context, context_read_identity = read_source_json(example/'RenderContext.json')
    before = [identity(p) for p in sources]
    assert scene_read_identity in before and context_read_identity in before, 'Source JSON changed after parse'
    assert all(entry in before for entry in platform_identities), 'Source platform export changed after validation'
    generated = generate(example/'Schema.json', out/'generated')
    # Keep source loading pinned even when another invocation left the old env set.
    os.environ['UE_TARGETMAP_SCENE'] = str(scene_path)
    flags = (falcor.SceneBuilderFlags.DontPretransformStaticMeshes | falcor.SceneBuilderFlags.DontOptimizeGraph |
             falcor.SceneBuilderFlags.DontMergeMaterials)
    m.loadScene(str(ROOT/'scripts/customrenderpipline/targetmap.pyscene'), flags)
    m.resizeFrameBuffer(1424, 1040)
    m.clock.pause()
    m.clock.time = 0
    m.ui = False
    basic = list(m.scene.get_raster_instance_ids(['BasicShape']))
    floor = list(m.scene.get_raster_instance_ids(['ProcGrid']))
    assert len(basic) == 3 and len(floor) == 1, (basic, floor)
    definition = graph_definition(source, basic, floor, example/'Mesh.slang', generated.codec, render_context=render_context,
                                  platform_texture=platform_texture, max_anisotropy=anisotropy)
    definition_path = out/'Graph.json'
    definition_path.write_text(json.dumps(definition, indent=2), encoding='utf-8')
    graph = make_graph('TargetMapNativeGBuffer', definition_path)
    m.addGraph(graph)
    m.setActiveGraph(graph)
    m.renderFrame()
    # Advance an owned counter, rather than loading a captured Frame constant.
    # Save the executed final declaration as well as the initial frame graph.
    (out/'Graph-initial.json').write_bytes(definition_path.read_bytes())
    definition = graph_definition(source, basic, floor, example/'Mesh.slang', generated.codec,
                                  render_context=render_context, frame_index=1,
                                  platform_texture=platform_texture, max_anisotropy=anisotropy)
    for node in definition['nodes'][2:]:
        graph.updatePass(node['name'], node['properties'])
    definition_path.write_text(json.dumps(definition, indent=2), encoding='utf-8')
    m.renderFrame()
    outputs = []
    for name, fmt in FORMATS:
        tex = graph.getOutput('Floor.'+name)
        array = np.ascontiguousarray(tex.to_numpy())
        raw = array.tobytes()
        assert len(raw) == 1424*1040*(8 if name == 'sceneColor' else 4), (name, array.shape, array.dtype, len(raw))
        path = out/(name+'.raw')
        path.write_bytes(raw)
        outputs.append(dict(name=name, format=fmt, shape=list(array.shape), dtype=str(array.dtype), **identity(path)))
    planes = falcor.customRenderPiplineReadDepthStencil(graph.getOutput('Floor.depth'))
    assert (planes['width'], planes['height']) == (1424, 1040)
    assert planes['depth_row_bytes'] == 1424*4 and planes['stencil_row_bytes'] == 1424
    for name in ('depth', 'stencil'):
        path = out/(name+'.raw')
        path.write_bytes(planes[name])
        outputs.append(dict(name=name, format='float32' if name == 'depth' else 'uint8', **identity(path)))
    depth = np.frombuffer(planes['depth'], dtype='<f4').reshape(1040, 1424)
    assert np.isfinite(depth).all() and (depth >= 0).all() and (depth <= 1).all() and np.any(depth > 0)
    assert not depth[1035:, :].any() and not depth[:, 1421:].any()
    assert before == [identity(p) for p in sources], 'Source changed during rendering'
    return dict(status='rendered_not_parity', full_renderer_parity=False, capture_inputs=False,
                sources=before, generated=[identity(generated.codec), identity(generated.metadata)],
                binary=identity(ROOT/'build/windows-vs2022/bin/Release/Falcor.dll'),
                custom_pass_plugin=identity(ROOT/'build/windows-vs2022/bin/Release/plugins/customrenderpipline.dll'),
                graph=identity(definition_path), outputs=outputs, basic_ids=basic, floor_ids=floor,
                allocation=[1424, 1040], view_rect=[0, 0, 1421, 1035], render_context=render_context,
                platform_texture=platform_texture, grid_max_anisotropy=anisotropy,
                frames=2, source_frame_indices=[0, 1],
                covered_pixels=int(np.count_nonzero(depth)), limits=[
                    ('Verified source-built platform BC1 sRGB 10 mips; sampler anisotropy='+str(anisotropy)+'.'
                     if platform_texture else 'Source Texture.Source: single mip BGRA8 sRGB / linear-wrap, not platform BC1/aniso8.'),
                    'Source frame phase advances 0 then 1; no captured temporal history loaded.',
                    'Contact flag and Floor capsule flag use source-default hypotheses; map overrides not yet audited.',
                    'No early editor sky pass; SceneColor/GBuffer background clear not parity-certified.',
                    'Exposure 1 only for zero emission in this GBuffer graph; lighting exposure is unresolved.',
                    'Source OBJ/f16 normal precision and DBuffer renormalization require measurement.'])


out = None
owned_output = False
try:
    out = Path(os.environ['CRP_TARGETMAP_NATIVE_OUT']).resolve()
    parent = (ROOT/'build/targetmap-shading-a1').resolve()
    if out.parent != parent:
        raise ValueError('Output must be a fresh direct child of build/targetmap-shading-a1')
    out.mkdir(exist_ok=False)
    owned_output = True
    result = run(out)
except BaseException:
    result = {'status': 'failed', 'full_renderer_parity': False, 'error': traceback.format_exc()}
    traceback.print_exc()
if owned_output:
    with (out/'result.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
print('TARGETMAP_NATIVE_'+result['status'].upper(), flush=True)
exit()
