"""Build the FY1 posed-hair native scene and deferred graph from original assets."""
import hashlib
import json
from pathlib import Path
import shutil
import struct

import numpy as np


ROOT = Path(__file__).resolve().parents[2]


def _identity(path):
    payload = path.read_bytes()
    return {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding='utf-8')
    else:
        path.write_bytes(payload)


def _copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _surface(two_sided=False, tags=()):
    return {'shading_model': 'DefaultLit', 'material_program': 'constant', 'blend_mode': 'Opaque',
            'base_color_linear': [0.01, 0.02, 0.03], 'emissive_linear': [0, 0, 0],
            'metallic': 0, 'specular': .2, 'roughness': .4, 'ao': 1,
            'two_sided': two_sided, 'render_tags': list(tags)}


def _loader():
    return '''"""Generated posed FY1 geometry. Material evaluation is owned by HairBase.slang."""
from pathlib import Path
import json
import numpy as np
from falcor import *

root = Path(__file__).resolve().parent
data = json.loads((root/'Scene.json').read_text(encoding='utf-8'))
materials = {}
for name, source in data['materials'].items():
    material = StandardMaterial(name)
    material.baseColor = float4(*source['base_color_linear'], 1)
    material.roughness = source['roughness']
    material.metallic = source['metallic']
    material.indexOfRefraction = 1.5
    materials[name] = material
for source in data['instances']:
    positions = np.fromfile(root/source['positions'], dtype='<f4').reshape(-1, 3)
    indices = np.fromfile(root/source['indices'], dtype='<u2').reshape(-1, 3)
    mesh = TriangleMesh()
    for vertex_id, position in enumerate(positions):
        # texC.x preserves the original vertex identity after SceneBuilder packing.
        mesh.addVertex(float3(*map(float, position)), float3(0, 0, 1), float2(float(vertex_id), 0))
    for triangle in indices:
        mesh.addTriangle(*map(int, triangle))
    mesh.frontFaceCW = False
    node = sceneBuilder.addNode(source['id'], Transform())
    sceneBuilder.addMeshInstance(node, sceneBuilder.addTriangleMesh(mesh, materials[source['material']]))
camera = Camera('FY1CaptureView')
camera.position = float3(0, 0, 0)
camera.target = float3(0, 0, -1)
camera.up = float3(0, 1, 0)
camera.nearPlane = 20
camera.farPlane = 1000000
camera.aspectRatio = 2562/1441
camera.frameHeight = 24
camera.focalLength = 12 * 2.9001397593635065
sceneBuilder.addCamera(camera)
'''


def _texture_asset(name, file, format, size, mips):
    return name, {'kind': 'texture2D', 'file': str(file.resolve()), 'format': format,
                  'size': list(size), 'mip_count': mips}


def build_case(reference, output):
    reference, output = Path(reference).resolve(), Path(output).resolve()
    capture = json.loads((reference/'geometry_7861/capture_mesh.json').read_text(encoding='utf-8'))
    occluders = json.loads((reference/'scene_occluders/view_meshes.json').read_text(encoding='utf-8'))
    if capture['eventId'] != 7861 or capture['vertexCount'] != 13828 or capture['indexCount'] != 53676:
        raise ValueError('Unexpected FY1 hair geometry identity')
    if [(m['eventId'], m['vertexCount'], len(m['indices'])) for m in occluders['meshes']] != [
            (4205, 7115, 41400), (4316, 201, 1140)]:
        raise ValueError('Unexpected FY1 occluder geometry identity')
    output.mkdir(parents=True, exist_ok=True)
    positions = np.asarray(capture['viewPositions'], dtype='<f4')
    if positions.size != capture['vertexCount'] * 3 or not np.isfinite(positions).all():
        raise ValueError('Invalid FY1 hair positions')
    _write(output/'hair_positions.bin', positions.tobytes())
    source_indices = reference/capture['index']['path']
    indices = np.frombuffer(source_indices.read_bytes(), dtype='<u2')
    if indices.size != capture['indexCount'] or int(indices.max()) >= capture['vertexCount']:
        raise ValueError('Invalid FY1 hair indices')
    _copy(source_indices, output/'hair_indices.bin')
    instances = [{'id': 'FY1Hair', 'material': 'FY1Hair', 'positions': 'hair_positions.bin',
                  'indices': 'hair_indices.bin'}]
    occluder_manifest = []
    for mesh in occluders['meshes']:
        event = mesh['eventId']
        p = np.asarray(mesh['viewPositions'], dtype='<f4')
        i = np.asarray(mesh['indices'], dtype='<u2')
        if p.size != mesh['vertexCount']*3 or i.size % 3 or int(i.max()) >= mesh['vertexCount']:
            raise ValueError(f'Invalid FY1 occluder {event}')
        _write(output/f'occluder_{event}_positions.bin', p.tobytes())
        _write(output/f'occluder_{event}_indices.bin', i.tobytes())
        instances.append({'id': f'Occluder{event}', 'material': f'Occluder{event}',
                          'positions': f'occluder_{event}_positions.bin', 'indices': f'occluder_{event}_indices.bin'})
        occluder_manifest.append({'event_id': event, 'vertices': mesh['vertexCount'], 'indices': i.size})
    _copy(reference/'geometry_7861/postvs.bin', output/'postvs.bin')
    texture_sources = {
        'fiber.dds': reference/'textures_7861/t04_T_ShortHair_Fiber_ResourceId_1421739.dds',
        'gradient.dds': reference/'textures_7861/t08_T_ShortHair_Gradient_ResourceId_1421736.dds',
        'alpha_modifier.dds': reference/'textures_7861/t12_None_ResourceId_465226.dds',
        'alpha.dds': reference/'textures_7861/t13_T_ShortHair_Alpha_ResourceId_1421732.dds',
        'tiling_noise.png': reference/'textures_7861/t09_Good64x64TilingNoiseHighFreq_ResourceId_14578.png',
    }
    for name, source in texture_sources.items():
        _copy(source, output/name)
    scene = {'version': 1, 'id': 'fy1-native-deferred-hair-v1', 'capture_inputs': False,
             'materials': {'FY1Hair': _surface(True, ('Hair',)),
                           'Occluder4205': _surface(False, ('DepthOccluder',)),
                           'Occluder4316': _surface(False, ('DepthOccluder',))},
             'instances': instances,
             'camera': {'position': [0, 0, 0], 'forward': [0, 0, -1], 'near': 20,
                        'projection': capture['camera']['d3dProjectionMatrixRowMajor'],
                        'viewport': [0, 0, 2562, 1441], 'allocation': [2568, 1448]},
             'provenance': {'capture': r'E:\rdc\fy\fy1.rdc', 'base_event': 7861,
                            'lighting_event': 14389, 'posed_geometry_only': True,
                            'captured_gbuffer_depth_shadow_shading_inputs': False}}
    _write(output/'Scene.json', json.dumps(scene, indent=2))
    _write(output/'HairFY1.pyscene', _loader())
    assets = dict([
        _texture_asset('fiber', output/'fiber.dds', 'BC1Unorm', (1024, 1024), 11),
        _texture_asset('gradient', output/'gradient.dds', 'BC1Unorm', (1024, 1024), 11),
        _texture_asset('alphaModifier', output/'alpha_modifier.dds', 'BC1Unorm', (512, 512), 10),
        _texture_asset('alpha', output/'alpha.dds', 'BC1Unorm', (1024, 1024), 11),
        _texture_asset('tilingNoise', output/'tiling_noise.png', 'RGBA8Unorm', (64, 64), 1),
    ])
    assets['postVS'] = {'kind': 'raw_buffer', 'file': str((output/'postvs.bin').resolve()),
                        'bytes': (output/'postvs.bin').stat().st_size}
    asset_file_inputs = [f'assets.{name}.file' for name in assets]
    projection = np.asarray(capture['translatedWorldToClipRowVector'], dtype=np.float32).T.tolist()
    extent = [2568, 1448]
    viewport = [0, 0, 2562, 1441]
    base_inputs = [
        {'name': 'postVS', 'direction': 'input', 'binding': 'gPostVS', 'kind': 'raw_buffer', 'bytes': assets['postVS']['bytes']},
        *[{'name': name, 'direction': 'input', 'binding': 'g'+name[0].upper()+name[1:],
           'format': value['format'], 'size': value['size'], 'mip_count': value['mip_count']}
          for name, value in assets.items() if value['kind'] == 'texture2D']]
    targets = [
        {'name': 'sceneColor', 'slot': 0, 'format': 'RGBA16Float', 'size': extent, 'clear': [0, 0, 0, 0]},
        {'name': 'gbufferA', 'slot': 1, 'format': 'RGB10A2Unorm', 'size': extent, 'clear': [0, 0, 0, 0]},
        {'name': 'gbufferB', 'slot': 2, 'format': 'BGRA8Unorm', 'size': extent, 'clear': [0, 0, 0, 0]},
        {'name': 'gbufferC', 'slot': 3, 'format': 'BGRA8UnormSrgb', 'size': extent, 'clear': [0, 0, 0, 0]},
        {'name': 'gbufferD', 'slot': 4, 'format': 'BGRA8Unorm', 'size': extent, 'clear': [0, 0, 0, 0]},
    ]
    depth = {'name': 'depth', 'format': 'D32FloatS8Uint', 'size': extent, 'clear': 0, 'stencilClear': 0}
    graph = {'version': 1, 'nodes': [
        {'name': 'Assets', 'type': 'CustomRenderPiplineAssetPass', 'file_inputs': asset_file_inputs,
         'properties': {'assets': assets}},
        {'name': 'OccluderDepth', 'type': 'CustomRenderPiplineMeshDrawPass', 'file_inputs': ['shader.file'],
         'properties': {'shader': {'file': str((ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Cases/HairFY1/Depth.slang').resolve()),
                                   'vertex': 'vsMain'},
                        'filter': {'tags_all': ['DepthOccluder']}, 'colorTargets': [], 'depthTarget': depth,
                        'viewport': viewport, 'view_projection': projection,
                        'state': {'depth_func': 'GreaterEqual', 'depth_write': True, 'cull_mode': 'Back'}}},
        {'name': 'HairBase', 'type': 'CustomRenderPiplineMeshDrawPass', 'file_inputs': ['shader.file'],
         'properties': {'shader': {'file': str((ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Cases/HairFY1/Base.slang').resolve()),
                                   'vertex': 'vsMain', 'pixel': 'psMain'},
                        'filter': {'materials': ['FY1Hair']}, 'resources': base_inputs,
                        'samplers': {'gWrapSampler': {'filter': 'Linear', 'address': 'Wrap'}},
                        'colorTargets': targets,
                        'depthTarget': {key: value for key, value in depth.items()
                                        if key not in ('clear', 'stencilClear')} | {'load': 'load'},
                        'viewport': viewport, 'view_projection': projection,
                        'state': {'depth_func': 'GreaterEqual', 'depth_write': True, 'cull_mode': 'None'}}},
        {'name': 'HairLighting', 'type': 'CustomRenderPiplineFullscreenPass', 'file_inputs': ['shader.file'],
         'properties': {'shader': {'file': str((ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Cases/HairFY1/Deferred.slang').resolve()),
                                   'pixel': 'main'},
                        'resources': [
                            {'name': 'gbufferA', 'direction': 'input', 'binding': 'gGBufferA', 'format': 'RGB10A2Unorm', 'size': extent},
                            {'name': 'gbufferB', 'direction': 'input', 'binding': 'gGBufferB', 'format': 'BGRA8Unorm', 'size': extent},
                            {'name': 'gbufferC', 'direction': 'input', 'binding': 'gGBufferC', 'format': 'BGRA8UnormSrgb', 'size': extent},
                            {'name': 'depth', 'direction': 'input', 'binding': 'gDepth', 'format': 'D32FloatS8Uint', 'size': extent},
                            {'name': 'shading', 'direction': 'output', 'binding': 'gShading', 'format': 'RGBA16Float', 'size': extent, 'slot': 0}],
                        'samplers': {'gPointSampler': {'filter': 'Point', 'address': 'Clamp'}}}}
    ], 'edges': [], 'outputs': ['HairBase.gbufferA', 'HairBase.gbufferB', 'HairBase.gbufferC',
                                'HairBase.gbufferD', 'HairBase.depth', 'HairLighting.shading']}
    graph['edges'] += [[f'Assets.{name}', f'HairBase.{name}'] for name in assets]
    graph['edges'].append(['OccluderDepth.depth', 'HairBase.depth'])
    graph['edges'] += [[f'HairBase.{name}', f'HairLighting.{name}'] for name in ('gbufferA', 'gbufferB', 'gbufferC', 'depth')]
    _write(output/'Passes.json', json.dumps(graph, indent=2))
    files = {str(path.relative_to(output)).replace('\\', '/'): _identity(path)
             for path in output.rglob('*') if path.is_file() and path.name != 'manifest.json'}
    manifest = {'target_stage': 'EID14389 independent deferred Shading', 'capture_inputs_in_production': False,
                'resolution': extent, 'viewport': viewport,
                'hair': {'vertices': capture['vertexCount'], 'indices': capture['indexCount']},
                'occluders': occluder_manifest, 'files': files}
    _write(output/'manifest.json', json.dumps(manifest, indent=2))
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=Path(r'D:/BaiduNetdiskDownload/RenderDocPro_1.44.0-pro.4_64/analysis/hair_fy1'))
    parser.add_argument('--output', type=Path, default=ROOT/'build/fy1-hair/case')
    args = parser.parse_args()
    print(json.dumps(build_case(args.reference, args.output), indent=2))
