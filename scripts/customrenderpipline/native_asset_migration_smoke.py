"""Native file assets: ordinary JSON, immutable allocations, explicit reloads.

Run with Mogwai --script. No Scene, Schema or transaction is constructed.
"""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts/customrenderpipline'), str(ROOT / 'build/m0-evidence/python')]
import falcor
import numpy as np
from pipeline import make_graph

PARENT = ROOT / 'build/resource-history-migration'
PARENT.mkdir(parents=True, exist_ok=True)
OUT = Path(tempfile.mkdtemp(prefix='native-assets-', dir=PARENT))
print('NATIVE_ASSET_EVIDENCE ' + str(OUT), flush=True)


def dds(path, dxgi, payload, *, size=4, mips=3, layers=1, cube=False):
    """Write a tiny DX10 DDS fixture, preserving authored subresource bytes."""
    header = [124, 0x2100f, size, size, size * 4, 0, mips] + [0] * 11
    header += [32, 4, int.from_bytes(b'DX10', 'little'), 0, 0, 0, 0, 0]
    header += [0x401008, 0xfe00 if cube else 0, 0, 0, 0]
    path.write_bytes(b'DDS ' + struct.pack('<31I', *header)
                     + struct.pack('<5I', dxgi, 3, 4 if cube else 0, layers, 0) + payload)


def run():
    raw = OUT / 'values.bin'
    raw_bytes = struct.pack('<4I', 3, 5, 0xffffffff, 0x80000000)
    raw.write_bytes(raw_bytes)
    rgba = OUT / 'rgba.dds'
    rgba_bytes = bytes([17, 33, 65, 255]) * 16 + bytes([71, 93, 115, 255]) * 4 + bytes([131, 157, 181, 255])
    dds(rgba, 28, rgba_bytes)
    bc = OUT / 'bc1.dds'
    bc_bytes = b''.join(struct.pack('<HHI', color, 0, 0) for color in (0xf800, 0x07e0, 0x001f))
    dds(bc, 71, bc_bytes)
    cube = OUT / 'cube.dds'
    cube_bytes = [bytes([face + 1, mip + 11, 127, 255]) * (max(1, 4 >> mip) ** 2)
                  for face in range(6) for mip in range(3)]
    dds(cube, 28, b''.join(cube_bytes), cube=True)
    array = OUT / 'array.dds'
    array_bytes = [bytes([layer + 21, mip + 31, 127, 255]) * (max(1, 4 >> mip) ** 2)
                   for layer in range(2) for mip in range(3)]
    dds(array, 28, b''.join(array_bytes), layers=2)

    shader = OUT / 'ReadAndDamage.slang'
    shader.write_text('''RWTexture2D<float4> image;
Texture2D<float4> compressed;
RWByteAddressBuffer raw;
RWTexture2D<uint4> result;
[numthreads(1,1,1)] void main(uint3 p:SV_DispatchThreadID) {
    result[uint2(0,0)] = uint4(round(image[uint2(0,0)] * 255));
    result[uint2(1,0)] = raw.Load4(0);
    for (uint mip = 0; mip < 3; ++mip)
        result[uint2(2+mip,0)] = uint4(round(compressed.Load(int3(0,0,mip)) * 255));
    image[uint2(0,0)] = 0;
    raw.Store4(0, uint4(0));
}
''')
    asset_properties = {'assets': {
        'image': {'kind': 'texture2D', 'file': rgba.name, 'format': 'RGBA8Unorm', 'size': [4, 4], 'mip_count': 3},
        'compressed': {'kind': 'texture2D', 'file': bc.name, 'format': 'BC1Unorm', 'size': [4, 4], 'mip_count': 3},
        'raw': {'kind': 'raw_buffer', 'file': raw.name, 'bytes': 16},
        'cube': {'kind': 'textureCube', 'file': cube.name, 'format': 'RGBA8Unorm', 'size': [4, 4], 'mip_count': 3},
        'array': {'kind': 'texture2DArray', 'file': array.name, 'format': 'RGBA8Unorm', 'size': [4, 4],
                  'mip_count': 3, 'array_size': 2},
    }}
    definition = {'version': 1, 'nodes': [
        {'name': 'Assets', 'type': 'CustomRenderPiplineAssetPass', 'properties': asset_properties,
         'file_inputs': ['assets.' + name + '.file' for name in asset_properties['assets']]},
        {'name': 'Read', 'type': 'CustomRenderPiplineComputePass', 'file_inputs': ['shader.file'], 'properties': {
            'shader': {'file': shader.name}, 'resources': [
                {'name': 'image', 'direction': 'inputOutput', 'binding': 'image', 'format': 'RGBA8Unorm',
                 'size': [4, 4], 'mip_count': 3},
                {'name': 'compressed', 'direction': 'input', 'binding': 'compressed', 'format': 'BC1Unorm',
                 'size': [4, 4], 'mip_count': 3},
                {'name': 'raw', 'direction': 'inputOutput', 'binding': 'raw', 'kind': 'raw_buffer', 'bytes': 16},
                {'name': 'result', 'direction': 'output', 'binding': 'result', 'format': 'RGBA32Uint', 'size': [5, 1]}],
            'dispatch': {'threads': [1, 1, 1]}}}],
        'edges': [['Assets.' + name, 'Read.' + name] for name in ('image', 'compressed', 'raw')],
        'outputs': ['Read.result', 'Read.image', 'Read.raw', 'Assets.compressed', 'Assets.cube', 'Assets.array']}
    graph_path = OUT / 'Graph.json'
    graph_path.write_text(json.dumps(definition, indent=2))
    # RED reaches the old mandatory Config through an otherwise valid native graph.
    graph = make_graph('NativeAssets', graph_path)
    assert not any(name in sys.modules for name in (
        'generate_schema', 'pipeline_snapshot', 'resource_snapshot',
        'extensions.ue_reference.transaction', 'extensions.ue_reference.pipeline'))
    properties = dict(graph.getPass('Assets').getDictionary())
    assert set(properties) == {'assets'}, properties
    for name, asset in properties['assets'].items():
        assert Path(asset['file']).resolve() == (OUT / asset_properties['assets'][name]['file']).resolve()

    m.resizeFrameBuffer(8, 8)
    m.clock.pause()
    m.ui = False
    m.addGraph(graph)
    m.setActiveGraph(graph)
    expected = np.array([[17, 33, 65, 255], [3, 5, 0xffffffff, 0x80000000],
                         [255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]], dtype=np.uint32)
    frames = 0

    def verify_frame(expected_result, expected_rgba, expected_bc):
        nonlocal frames
        m.renderFrame()
        frames += 1
        np.testing.assert_array_equal(graph.getOutput('Read.result').to_numpy(), expected_result)
        # The consumer really overwrote its graph aliases, not the private source.
        assert graph.getOutput('Read.raw').to_numpy().tobytes() == bytes(16)
        damaged = bytearray(expected_rgba[:64])
        damaged[:4] = bytes(4)
        assert graph.getOutput('Read.image').to_numpy(mip_level=0).tobytes() == bytes(damaged)
        for mip, start, length in ((1, 64, 16), (2, 80, 4)):
            assert graph.getOutput('Read.image').to_numpy(mip_level=mip).tobytes() == expected_rgba[start:start+length]
        for mip in range(3):
            assert graph.getOutput('Assets.compressed').to_numpy(mip_level=mip).tobytes() == expected_bc[mip*8:(mip+1)*8]
        for output, layers, payload in (('Assets.cube', 6, cube_bytes), ('Assets.array', 2, array_bytes)):
            for layer in range(layers):
                for mip in range(3):
                    assert graph.getOutput(output).to_numpy(mip_level=mip, array_slice=layer).tobytes() == payload[layer*3+mip]

    for _ in range(3):
        verify_frame(expected, rgba_bytes, bc_bytes)

    changed_raw = struct.pack('<4I', 23, 29, 31, 37)
    changed_rgba = bytes([101, 103, 107, 255]) * 16 + bytes([109, 113, 127, 255]) * 4 + bytes([131, 137, 139, 255])
    changed_bc = b''.join(struct.pack('<HHI', color, 0, 0) for color in (0x07e0, 0x001f, 0xf800))
    # Change exactly one authored file at a time; active GPU sources remain stable.
    raw.write_bytes(changed_raw)
    verify_frame(expected, rgba_bytes, bc_bytes)
    dds(rgba, 28, changed_rgba)
    verify_frame(expected, rgba_bytes, bc_bytes)
    dds(bc, 71, changed_bc)
    verify_frame(expected, rgba_bytes, bc_bytes)
    raw.unlink()
    verify_frame(expected, rgba_bytes, bc_bytes)
    raw.write_bytes(changed_raw)
    m.resizeFrameBuffer(16, 12)
    verify_frame(expected, rgba_bytes, bc_bytes)

    # Native updatePass recreates the pass from its ordinary properties.
    graph.updatePass('Assets', properties)
    changed_expected = expected.copy()
    changed_expected[0] = [101, 103, 107, 255]
    changed_expected[1] = [23, 29, 31, 37]
    changed_expected[2:] = [[0, 255, 0, 255], [0, 0, 255, 255], [255, 0, 0, 255]]
    verify_frame(changed_expected, changed_rgba, changed_bc)
    verify_frame(changed_expected, changed_rgba, changed_bc)

    rejections = []
    for label, mutate in (
        ('missing_assets', lambda p: p.clear()),
        ('empty_assets', lambda p: p.update(assets={})),
        ('assets_not_object', lambda p: p.update(assets=[])),
        ('unknown_top_level', lambda p: p.update(unrelated=True)),
        ('legacy_property', lambda p: p.update(schemaPath='retired.json')),
        ('invalid_name', lambda p: p['assets'].update({'bad.name': p['assets'].pop('raw')})),
        ('asset_not_object', lambda p: p['assets'].update(raw=False)),
        ('unknown_asset_key', lambda p: p['assets']['raw'].update(execution='once')),
        ('unknown_kind', lambda p: p['assets']['image'].update(kind='texture3D')),
        ('structured_buffer_not_supported', lambda p: p['assets']['raw'].update(kind='structured_buffer')),
        ('buffer_size', lambda p: p['assets']['raw'].update(bytes=12)),
        ('buffer_alignment', lambda p: p['assets']['raw'].update(bytes=15)),
        ('buffer_bool', lambda p: p['assets']['raw'].update(bytes=True)),
        ('buffer_overflow', lambda p: p['assets']['raw'].update(bytes=2**32)),
        ('texture_format', lambda p: p['assets']['image'].update(format='RGBA16Float')),
        ('texture_unknown_format', lambda p: p['assets']['image'].update(format='Unknown')),
        ('texture_mips', lambda p: p['assets']['image'].update(mip_count=2)),
        ('texture_mips_bool', lambda p: p['assets']['image'].update(mip_count=True)),
        ('texture_size', lambda p: p['assets']['image'].update(size=[8, 4])),
        ('texture_size_bool', lambda p: p['assets']['image'].update(size=[True, 4])),
        ('texture_layers', lambda p: p['assets']['array'].update(array_size=3)),
        ('texture_layers_bool', lambda p: p['assets']['array'].update(array_size=True)),
        ('texture_srgb_type', lambda p: p['assets']['image'].update(srgb=1)),
        ('missing_raw_file', lambda p: p['assets']['raw'].update(file=str(OUT / 'missing.bin'))),
        ('missing_texture_file', lambda p: p['assets']['image'].update(file=str(OUT / 'missing.dds'))),
        ('file_is_directory', lambda p: p['assets']['raw'].update(file=str(OUT))),
        ('empty_file', lambda p: p['assets']['image'].update(file='')),
    ):
        bad = copy.deepcopy(properties)
        mutate(bad)
        try:
            falcor.createPass('CustomRenderPiplineAssetPass', bad)
        except (RuntimeError, ValueError) as error:
            rejections.append({'case': label, 'message': str(error)})
        else:
            raise AssertionError('Accepted ' + label)
    verify_frame(changed_expected, changed_rgba, changed_bc)
    assert not any(name in sys.modules for name in (
        'generate_schema', 'pipeline_snapshot', 'resource_snapshot',
        'extensions.ue_reference.transaction', 'extensions.ue_reference.pipeline'))
    return {'status': 'passed', 'frames': frames, 'json_relative_files_to_gpu': True,
            'no_scene_schema_or_transaction': True, 'raw_bytes_exact': True,
            'rgba_and_bc_mips_byte_exact': True, 'cube_faces_and_array_layers_byte_exact': True,
            'consumer_damage_restored': True, 'file_edits_and_removal_isolated': True,
            'update_pass_reloads_files': True, 'rejections': rejections}


try:
    result = run()
except Exception as error:
    traceback.print_exc()
    result = {'status': 'failed', 'error': str(error)}
(OUT / 'result.json').write_text(json.dumps(result, indent=2))
print('NATIVE_ASSET_' + result['status'].upper(), flush=True)
exit()
