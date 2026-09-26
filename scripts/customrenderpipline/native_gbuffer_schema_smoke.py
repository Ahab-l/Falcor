"""GPU acceptance of generated codecs and native MRT writes/reads."""
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT/'build/m0-evidence/python'))
import numpy as np
import falcor
from generate_native_gbuffer import generate
from gbuffer_schema import FORMATS
from test_native_gbuffer_schema import sample_schema

OUT = ROOT/'build/native-gbuffer-schema'
OUT.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix='gpu-', dir=OUT))
print('NATIVE_SCHEMA_EVIDENCE '+str(out), flush=True)
testbed = falcor.Testbed(create_window=False, width=128, height=72,
                         device_type=falcor.DeviceType.D3D12, enable_debug_layers=True)
device = testbed.device
assert all(hasattr(falcor.ResourceFormat, name) for name in FORMATS)


def structured(array, output=False):
    flags = falcor.ResourceBindFlags.UnorderedAccess if output else falcor.ResourceBindFlags.ShaderResource
    result = device.create_structured_buffer(array.shape[1]*4, array.shape[0], flags)
    if not output:
        result.from_numpy(np.ascontiguousarray(array))
    return result


def compute(source, bindings, count):
    program = falcor.ComputePass(device, string=source, cs_entry='main', shader_model=falcor.ShaderModel.SM6_6)
    for name, resource in bindings.items():
        program.globals[name] = resource
    program.execute(threads_x=count)
    return program


# Standard codecs: independent encode expectations and separately supplied decode words.
schema = sample_schema()
schema['name'] = 'StorageProbe'
schema['attachments'][0]['format'] = 'RGBA32Uint'
for name, field_type, channel, kind, bounds in (
    ('fullWord', 'uint', 'g', 'uint', [0, 2**32-1]),
    ('signedWord', 'int', 'b', 'sint', [-(2**31), 2**31-1])):
    schema['fields'].append({'name': name, 'type': field_type})
    schema['storage'].append({'name': name, 'attachment': 'packed', 'channels': channel,
                              'bits': {'offset': 0, 'width': 32}})
    schema['codecs'].append({'kind': kind, 'field': name, 'storage': name, 'range': bounds, 'overflow': 'reject'})
schema['fields'].append({'name': 'enabled', 'type': 'bool'})
schema['storage'].append({'name': 'flag', 'attachment': 'packed', 'channels': 'a', 'bits': {'offset': 0, 'width': 1}})
schema['codecs'].append({'kind': 'bool', 'field': 'enabled', 'storage': 'flag'})
path = out/'Probe.json'
path.write_text(json.dumps(schema), encoding='utf-8')
artifacts = generate(path, out/'probe')
roughness = np.array([-1, 0, .5/255, 1.5/255, .25, .5, 1, 2, np.nan, np.inf, 3*2.0**-128, .6], np.float32)
count = len(roughness)
floats = np.zeros((count, 4), np.float32)
floats[:, 0] = roughness
integers = np.zeros((count, 4), np.uint32)
integers[:, 0] = 42
integers[-1, 0] = 65536
integers[:, 1] = np.array([0, 0x80000000, 0xffffffff, 65535, 17, 42, 0xfffffffe, 5, 6, 7, 8, 9], np.uint32)
integers[:, 2] = np.array([-2147483648, -1, 0, 2147483647, -128, 127, -32768, 5, 6, 7, 8, 9], np.int32).view(np.uint32)
integers[:, 3] = np.arange(count, dtype=np.uint32) % 2
raw = np.array([[0x00345680, 0xffffffff, 0x80000000, 1],
                [0x00ffff00, 0x80000000, 0xffffffff, 0],
                [0x000000ff, 0, 0x7fffffff, 1]], np.uint32)
decode_words = np.tile(raw, (4, 1))[:count].copy()
encoded = structured(np.zeros((count, 4), np.uint32), True)
decoded = structured(np.zeros((count, 4), np.uint32), True)
stats = structured(np.zeros((count, 4), np.float32), True)
shader = f'#include "{artifacts.codec.as_posix()}"\n'+r'''
StructuredBuffer<float4> gFloat;
StructuredBuffer<uint4> gInt;
StructuredBuffer<uint4> gRaw;
RWStructuredBuffer<uint4> gEncoded;
RWStructuredBuffer<uint4> gDecoded;
RWStructuredBuffer<float4> gStats;
[numthreads(1,1,1)] void main(uint3 tid : SV_DispatchThreadID)
{
    uint i = tid.x;
    StorageProbeFields f;
    f.roughness = gFloat[i].x; f.materialID = gInt[i].x;
    f.baseColor = float3(-1, 0.5, 2);
    f.fullWord = gInt[i].y; f.signedWord = asint(gInt[i].z); f.enabled = gInt[i].w != 0;
    StorageProbePacked p;
    bool ok = StorageProbeEncode(f, p);
    gEncoded[i] = p.packed;
    StorageProbePacked reference = (StorageProbePacked)0;
    reference.packed = gRaw[i];
    StorageProbeFields d = StorageProbeDecode(reference);
    gDecoded[i] = uint4(d.materialID, d.fullWord, asuint(d.signedWord), d.enabled ? 1u : 0u);
    gStats[i] = float4(ok ? 1 : 0, d.roughness, p.color.r, p.color.b);
}
'''
compute(shader, {'gFloat': structured(floats), 'gInt': structured(integers), 'gRaw': structured(decode_words),
                 'gEncoded': encoded, 'gDecoded': decoded, 'gStats': stats}, count)
got = np.frombuffer(encoded.to_numpy().tobytes(), np.uint32).reshape(count, 4)
magnitude = roughness.view(np.uint32) & 0x7fffffff
valid = np.isfinite(roughness) & (integers[:, 0] <= 65535) & ((magnitude == 0) | (magnitude >= 0x00800000))
expected = integers.copy()
expected[:, 0] = np.rint(np.clip(np.nan_to_num(roughness), 0, 1)*np.float32(255)).astype(np.uint32) | (integers[:, 0] << 8)
expected[~valid] = 0
np.testing.assert_array_equal(got, expected)
got_stats = np.frombuffer(stats.to_numpy().tobytes(), np.float32).reshape(count, 4)
np.testing.assert_array_equal(got_stats[:, 0], valid)
np.testing.assert_array_equal(got_stats[:, 2], 0)
np.testing.assert_array_equal(got_stats[:, 3], valid)
np.testing.assert_allclose(got_stats[:, 1], (decode_words[:, 0] & 255)/255, atol=1e-7, rtol=0)
expected_decode = decode_words.copy()
expected_decode[:, 0] = (decode_words[:, 0] >> 8) & 65535
np.testing.assert_array_equal(np.frombuffer(decoded.to_numpy().tobytes(), np.uint32).reshape(count, 4), expected_decode)

# Sub-word signed values must sign-extend, and both sides of the range reject.
signed_schema = copy.deepcopy(schema)
signed_schema['name'] = 'SignedProbe'
next(s for s in signed_schema['storage'] if s['name'] == 'signedWord')['bits']['width'] = 8
next(c for c in signed_schema['codecs'] if c.get('field') == 'signedWord')['range'] = [-128, 127]
signed_path = out/'Signed.json'
signed_path.write_text(json.dumps(signed_schema))
signed_artifacts = generate(signed_path, out/'signed')
signed_input = integers.copy()
signed_input[:, 0] = 42
signed_input[:, 2] = np.array([-129, -128, -1, 0, 127, 128, 5, 6, 7, 8, 9, 10], np.int32).view(np.uint32)
signed_float = floats.copy()
signed_float[:, 0] = .5
signed_raw = decode_words.copy()
signed_raw[:, 2] = np.resize(np.array([128, 255, 127], np.uint32), count)
signed_shader = shader.replace(artifacts.codec.as_posix(), signed_artifacts.codec.as_posix()).replace('StorageProbe', 'SignedProbe')
compute(signed_shader, {'gFloat': structured(signed_float), 'gInt': structured(signed_input), 'gRaw': structured(signed_raw),
                        'gEncoded': encoded, 'gDecoded': decoded, 'gStats': stats}, count)
signed_valid = (signed_input[:, 2].view(np.int32) >= -128) & (signed_input[:, 2].view(np.int32) <= 127)
expected_signed = signed_input.copy()
expected_signed[:, 0] = 128 | (42 << 8)
expected_signed[:, 2] &= 255
expected_signed[~signed_valid] = 0
np.testing.assert_array_equal(np.frombuffer(encoded.to_numpy().tobytes(), np.uint32).reshape(count, 4), expected_signed)
signed_decoded = np.frombuffer(decoded.to_numpy().tobytes(), np.uint32).reshape(count, 4)[:, 2].view(np.int32)
np.testing.assert_array_equal(signed_decoded, np.where(signed_raw[:, 2] >= 128, signed_raw[:, 2].astype(np.int64)-256, signed_raw[:, 2]))


# Actual native scene rasterization and a second GPU shader reading the real outputs.
testbed.load_scene(str(HERE/'examples/schema_gbuffer/Scene.pyscene'))
testbed.clock.pause()
scene_schema = json.loads((HERE/'examples/schema_gbuffer/Schema.json').read_text())
for item in scene_schema['codecs']:
    if item['kind'] == 'custom':
        item['file'] = str(HERE/'examples/schema_gbuffer'/item['file'])
scene_schema['producer']['file'] = str(HERE/'examples/schema_gbuffer/Material.slangh')

# Nonlinear/joint custom codec, including all octahedron hemispheres and rejection.
custom_path = out/'CustomProbe.json'
custom_config = copy.deepcopy(scene_schema)
custom_config.pop('producer')
custom_path.write_text(json.dumps(custom_config))
custom_artifacts = generate(custom_path, out/'custom')
directions = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [0, -1, 0], [0, 0, -1],
                       [1, 1, 1], [-1, -1, -1], [0, 0, 0], [0, 0, 1]], np.float32)
qvalues = np.array([0, .25, 1, -.5, 1.5, .5, .1, .9, .5, np.nan], np.float32)
custom_input = np.column_stack((directions, qvalues)).astype(np.float32)
oct_values = np.array([[1, .5], [.5, 1], [.5, .5], [0, .5], [.5, 0], [1, 1], [2/3, 2/3], [1/6, 1/6]], np.float32)
custom_raw = np.zeros((10, 4), np.float32)
custom_raw[:, :2] = np.resize(oct_values, (10, 2))
custom_raw[:, 2] = np.arange(10)*23
custom_words = structured(np.zeros((10, 4), np.uint32), True)
custom_floats = structured(np.zeros((10, 4), np.float32), True)
custom_decoded = structured(np.zeros((10, 4), np.float32), True)
custom_shader = f'#include "{custom_artifacts.codec.as_posix()}"\n'+r'''
StructuredBuffer<float4> gInput;
StructuredBuffer<float4> gRaw;
RWStructuredBuffer<uint4> gWords;
RWStructuredBuffer<float4> gFloats;
RWStructuredBuffer<float4> gDecoded;
[numthreads(1,1,1)] void main(uint3 tid : SV_DispatchThreadID)
{
    uint i = tid.x;
    SchemaMaterialFields f = (SchemaMaterialFields)0;
    f.normalW = gInput[i].xyz; f.roughness = gInput[i].w; f.coverage = 1;
    f.materialID = 31; f.emissive = true; f.baseColor = 0.5;
    SchemaMaterialPacked p;
    bool ok = SchemaMaterialEncode(f, p);
    gWords[i] = uint4(p.materialBits, ok ? 1u : 0u, 0, 0);
    gFloats[i] = float4(p.normal, p.color.a, 0);
    SchemaMaterialPacked raw = (SchemaMaterialPacked)0;
    raw.normal = gRaw[i].xy; raw.materialBits = uint(gRaw[i].z);
    SchemaMaterialFields decoded = SchemaMaterialDecode(raw);
    gDecoded[i] = float4(decoded.normalW, decoded.roughness);
}
'''
custom_bindings = {'gInput': structured(custom_input), 'gRaw': structured(custom_raw), 'gWords': custom_words,
                   'gFloats': custom_floats, 'gDecoded': custom_decoded}
compute(custom_shader, custom_bindings, 10)
cw = np.frombuffer(custom_words.to_numpy().tobytes(), np.uint32).reshape(10, 4)
expected_custom_code = np.rint(np.sqrt(np.clip(qvalues[:8], 0, 1))*np.float32(255)).astype(np.uint32)
np.testing.assert_array_equal(cw[:8, 0], expected_custom_code | (31 << 8) | (1 << 24))
np.testing.assert_array_equal(cw[:, 1], [1]*8+[0, 0])
np.testing.assert_array_equal(cw[8:], 0)
cf = np.frombuffer(custom_floats.to_numpy().tobytes(), np.float32).reshape(10, 4)
np.testing.assert_allclose(cf[:8, :2], oct_values, atol=1e-7, rtol=0)
np.testing.assert_array_equal(cf[8:], 0)
cd = np.frombuffer(custom_decoded.to_numpy().tobytes(), np.float32).reshape(10, 4)
reference_directions = directions[:8]/np.linalg.norm(directions[:8], axis=1, keepdims=True)
np.testing.assert_allclose(cd[:8, :3], reference_directions, atol=3e-7, rtol=0)
# Reciprocal/multiply lowering may differ from the correctly rounded float64 reference
# by a few float32 ULPs; this arithmetic budget is separate from quantization error.
np.testing.assert_array_max_ulp(cd[:, 3], ((custom_raw[:, 2].astype(np.float64)/255.0)**2).astype(np.float32), maxulp=3)

# A custom callback returning true must still respect declared storage capacity.
bad_custom = out/'BadCustom.slangh'
bad_custom.write_text('''bool encodeSurface(SchemaMaterial_surfaceInput value, out SchemaMaterial_surfaceStorage s)
{ s.roughnessCode = 300u; s.oct = float2(0.5, 0.5); return true; }
SchemaMaterial_surfaceInput decodeSurface(SchemaMaterial_surfaceStorage s)
{ return (SchemaMaterial_surfaceInput)0; }
''')
bad_config = copy.deepcopy(custom_config)
bad_config['codecs'][0]['file'] = str(bad_custom)
bad_path = out/'BadCustom.json'
bad_path.write_text(json.dumps(bad_config))
bad_artifacts = generate(bad_path, out/'bad-custom')
compute(custom_shader.replace(custom_artifacts.codec.as_posix(), bad_artifacts.codec.as_posix()), custom_bindings, 10)
np.testing.assert_array_equal(np.frombuffer(custom_words.to_numpy().tobytes(), np.uint32), 0)

raster_results = []
for unorm_bits in (False, True):
    config = copy.deepcopy(scene_schema)
    if unorm_bits:
        config['attachments'][0]['format'] = 'RGBA8Unorm'
        config['storage'][1].update(channels='g', bits={'offset': 0, 'width': 8})
        config['storage'][2].update(channels='b', bits={'offset': 0, 'width': 1})
        config['codecs'][1]['range'] = [0, 255]
    schema_path = out/('Unorm.json' if unorm_bits else 'Raster.json')
    schema_path.write_text(json.dumps(config), encoding='utf-8')
    generated = generate(schema_path, out/('unorm' if unorm_bits else 'raster'))
    graph = testbed.create_render_graph('SchemaRaster'+str(unorm_bits))
    graph.create_pass('Generated', 'CustomRenderPiplineGBufferPass', {'definition': str(generated.definition)})
    graph.create_pass('Stock', 'GBufferRaster', {'samplePattern': 'Center'})
    for port in ('materialBits', 'color', 'normal', 'depth'):
        graph.mark_output('Generated.'+port)
    for port in ('diffuseOpacity', 'specRough', 'guideNormalW', 'mtlData', 'posW', 'depth'):
        graph.mark_output('Stock.'+port)
    testbed.render_graph = graph
    testbed.frame()
    color = np.frombuffer(graph.getOutput('Generated.color').to_numpy().tobytes(), np.uint8).reshape(72, 128, 4)
    mask = color[..., 3] > 0
    stock_mask = np.asarray(graph.getOutput('Stock.posW').to_numpy())[..., 3] > 0
    print('SCHEMA_RASTER_COVERAGE '+json.dumps({'generated': int(mask.sum()), 'stock': int(stock_mask.sum()),
          'format': str(color.dtype), 'depth_min': float(np.min(graph.getOutput('Generated.depth').to_numpy()))}), flush=True)
    assert mask.sum() > 100, 'Generated native raster has insufficient coverage'
    np.testing.assert_array_equal(mask, np.asarray(graph.getOutput('Stock.posW').to_numpy())[..., 3] > 0)
    np.testing.assert_allclose(graph.getOutput('Generated.depth').to_numpy(), graph.getOutput('Stock.depth').to_numpy(), atol=1e-6, rtol=0)
    expected_rough = np.asarray(graph.getOutput('Stock.specRough').to_numpy())[..., 3]
    ids = np.asarray(graph.getOutput('Stock.mtlData').to_numpy())[..., 0]
    codes = np.rint(np.sqrt(np.clip(expected_rough, 0, 1))*np.float32(255)).astype(np.uint32)
    raw_words = np.asarray(graph.getOutput('Generated.materialBits').to_numpy())
    if unorm_bits:
        raw_words = np.frombuffer(raw_words.tobytes(), np.uint8).reshape(72, 128, 4)
        np.testing.assert_array_equal(raw_words[mask, 0], codes[mask])
        np.testing.assert_array_equal(raw_words[mask, 1], ids[mask])
        texture_type = 'float4'
    else:
        np.testing.assert_array_equal(raw_words.reshape(72, 128)[mask], codes[mask] | (ids[mask] << 8))
        texture_type = 'uint'
    output = structured(np.zeros((128*72, 4), np.float32), True)
    normal_output = structured(np.zeros((128*72, 4), np.float32), True)
    consumer = f'''#include "{generated.codec.as_posix()}"
Texture2D<{texture_type}> gBits;
Texture2D<float4> gColor;
Texture2D<float2> gNormal;
RWStructuredBuffer<float4> gResult;
RWStructuredBuffer<float4> gNormals;
[numthreads(1,1,1)] void main(uint3 tid:SV_DispatchThreadID)
{{
    int3 pixel = int3(tid.x % 128, tid.x / 128, 0);
    SchemaMaterialPacked p;
    p.materialBits = gBits.Load(pixel); p.color = gColor.Load(pixel); p.normal = gNormal.Load(pixel);
    SchemaMaterialFields f = SchemaMaterialDecode(p);
    gResult[tid.x] = float4(f.baseColor, f.roughness);
    gNormals[tid.x] = float4(f.normalW, float(f.materialID));
}}
'''
    compute(consumer, {'gBits': graph.getOutput('Generated.materialBits'), 'gColor': graph.getOutput('Generated.color'),
                       'gNormal': graph.getOutput('Generated.normal'), 'gResult': output, 'gNormals': normal_output}, 128*72)
    result = np.frombuffer(output.to_numpy().tobytes(), np.float32).reshape(72, 128, 4)
    normals = np.frombuffer(normal_output.to_numpy().tobytes(), np.float32).reshape(72, 128, 4)
    stock_color = np.asarray(graph.getOutput('Stock.diffuseOpacity').to_numpy())
    stock_normal = np.asarray(graph.getOutput('Stock.guideNormalW').to_numpy())
    np.testing.assert_allclose(result[mask, :3], stock_color[mask, :3], atol=1/255, rtol=0)
    np.testing.assert_allclose(result[mask, 3], (codes[mask]/255.0)**2, atol=2e-7, rtol=0)
    np.testing.assert_allclose(normals[mask, :3], stock_normal[mask, :3], atol=6e-5, rtol=0)
    np.testing.assert_array_equal(normals[mask, 3], ids[mask])
    raster_results.append({'bit_storage': 'UNORM' if unorm_bits else 'UINT', 'pixels': int(mask.sum()),
                           'normal_max_error': float(np.max(np.abs(normals[mask, :3]-stock_normal[mask, :3])))})
    testbed.render_graph = None


# Incompatible versions of the same named layout cannot be included together.
different = copy.deepcopy(schema)
different['storage'][1]['bits']['offset'] = 9
other_path = out/'Different.json'
other_path.write_text(json.dumps(different))
other = generate(other_path, out/'different')
try:
    compute(f'#include "{artifacts.codec.as_posix()}"\n#include "{other.codec.as_posix()}"\n'
            '[numthreads(1,1,1)] void main() {}', {}, 1)
except RuntimeError as error:
    assert 'Conflicting GBuffer layout' in str(error), str(error)
else:
    raise AssertionError('Conflicting layouts were accepted by Slang')

(out/'result.json').write_text(json.dumps({'status': 'passed', 'standard_encode_cases': count,
    'independent_decode_cases': count, 'full_uint32_and_signed_int32': True, 'invalid_input_zero_output': True,
    'signed8_encode_decode_and_overflow': True, 'custom_encode_decode_cases': 10, 'custom_storage_overflow_rejected': True,
    'layout_mismatch_rejected': True, 'native_raster_and_downstream_decode': raster_results}, indent=2))
print('NATIVE_GBUFFER_SCHEMA_PASS', flush=True)
exit()
