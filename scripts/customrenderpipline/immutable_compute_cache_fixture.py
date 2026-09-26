"""Immutable-compute declaration fixtures extracted from immutable_compute_cache_smoke.py.

Source provenance SHA-256: 7d5d2a8ef09d05ff4623f72cb81ecda6d79618e13e15466ad8c1975de2daac02.
Pure declaration construction only; it does not launch Falcor.
"""
import copy

GENERATOR = '''RWTexture2D<uint> result;
cbuffer Params { uint value; };
[numthreads(4,4,1)] void main(uint3 p:SV_DispatchThreadID) {
    if (p.x < 8 && p.y < 8) result[p.xy] = value + p.x + 8*p.y;
}
'''


CONSUMER = '''RWTexture2D<uint> shared;
RWTexture2D<uint> observed;
[numthreads(4,4,1)] void main(uint3 p:SV_DispatchThreadID) {
    if (p.x < 8 && p.y < 8) { observed[p.xy] = shared[p.xy]; shared[p.xy] = 999999; }
}
'''


def declaration(shader, consumer, execution='once', value=17):
    def resource(name, direction='output'):
        return {'name': name, 'binding': name, 'direction': direction,
                'kind': 'texture2D', 'format': 'R32Uint', 'size': [8, 8]}
    properties = {'shader': {'file': str(shader)}, 'resources': [resource('result')],
                  'uniforms': {'Params.value': {'type': 'uint', 'value': value}},
                  'dispatch': {'threads': [8, 8, 1]}}
    if execution is not None:
        properties['execution'] = execution
    return {'version': 1, 'nodes': [
        {'name': 'Generate', 'type': 'CustomRenderPiplineComputePass', 'file_inputs': ['shader.file'],
         'properties': properties},
        {'name': 'Consume', 'type': 'CustomRenderPiplineComputePass', 'file_inputs': ['shader.file'],
         'properties': {'shader': {'file': str(consumer)},
                        'resources': [resource('shared', 'inputOutput'), resource('observed')],
                        'dispatch': {'threads': [8, 8, 1]}}}],
        'edges': [['Generate.result', 'Consume.shared']],
        'outputs': ['Consume.observed', 'Consume.shared']}


def invalid_declarations(valid):
    """Cases shared by CPU and native rejection checks."""
    cases = {}
    for value in ('sometimes', True, 0, None):
        bad = copy.deepcopy(valid)
        bad['nodes'][0]['properties']['execution'] = value
        cases['mode_' + repr(value)] = bad
    for direction in ('input', 'inputOutput'):
        bad = copy.deepcopy(valid)
        bad['nodes'][0]['properties']['resources'][0]['direction'] = direction
        cases[direction] = bad
    for source in ('extent', 'preExposure'):
        bad = copy.deepcopy(valid)
        bad['nodes'][0]['properties']['uniforms']['Params.value'] = {'type': 'uint', 'source': source}
        cases[source] = bad
    for label, changes in (
        ('viewport', {'size': None}),
        ('relative', {'size': {'relative_to': '$viewport', 'divisor': [1, 1]}}),
        ('array', {'kind': 'texture2DArray', 'array_size': 2}),
        ('cube', {'kind': 'textureCube'}),
        ('mips', {'mip_count': 2}),
        ('partial_view', {'view': {'mip': 1}}),
        ('raw_buffer', {'kind': 'raw_buffer', 'bytes': 256}),
        ('structured_buffer', {'kind': 'structured_buffer', 'stride': 4, 'count': 64}),
    ):
        bad = copy.deepcopy(valid)
        port = bad['nodes'][0]['properties']['resources'][0]
        port.update(changes)
        if port.get('size') is None:
            port.pop('size', None)
        if 'buffer' in label:
            port.pop('format'); port.pop('size')
        cases[label] = bad
    bad = copy.deepcopy(valid)
    bad['nodes'][0]['properties']['resources'] = [{'schema': '$packed', 'direction': 'input'}]
    cases['schema_inputs'] = bad
    bad = copy.deepcopy(valid)
    bad['nodes'][0]['type'] = 'CustomRenderPiplineFullscreenPass'
    bad['nodes'][0]['properties'].pop('dispatch')
    cases['fullscreen'] = bad
    return cases
