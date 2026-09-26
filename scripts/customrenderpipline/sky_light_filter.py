"""Declared source SkyLight mipgen/convolution/SH, starting at GPU capture mip zero.

The supplied capture port must expose one square Cube with the requested format,
the full log2(width)+1 mip chain, and initialized mip zero. Resource compatibility
and same-allocation nonoverlapping views are checked by the native executor.
This fragment does not implement capture, clouds, fog, or a lighting consumer.
"""
import math
from pathlib import Path
import re

SHADER_DIRECTORY = Path(__file__).resolve().parents[2] / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/SkyLight'
_IDENTIFIER = r'[A-Za-z_][A-Za-z0-9_]*'


def sky_light_filter_fragment(capture_cube, *, width, output_format, prefix='SkyLight'):
    """Return fresh PassDefinition data to merge with the capture declaration.

    Outputs are the completed raw Cube, the separate convolved Cube, and eight
    packed float4 SH/brightness values. Shader paths are explicit native inputs;
    this declaration does not snapshot files or provide a transaction.
    """
    if not isinstance(capture_cube, str) or re.fullmatch(_IDENTIFIER + r'\.' + _IDENTIFIER, capture_cube) is None:
        raise ValueError('capture_cube must identify one declared capture output port')
    if not isinstance(prefix, str) or re.fullmatch(_IDENTIFIER, prefix) is None:
        raise ValueError('prefix must be an ASCII identifier')
    if type(width) is not int or not 16 <= width <= 16384 or width & (width - 1):
        raise ValueError('Cube width must be a power of two in 16..16384')
    if output_format not in ('R11G11B10Float', 'RGBA32Float'):
        raise ValueError('Cube format must be source R11G11B10Float or diagnostic RGBA32Float')
    mip_count = width.bit_length()
    nodes, edges = [], []

    def cube(name, binding, direction, view):
        return {'name': name, 'binding': binding, 'direction': direction,
                'kind': 'textureCube', 'format': output_format, 'size': [width, width],
                'mip_count': mip_count, 'view': view}

    def node(name, shader, entry, resources, uniforms, threads):
        return {'name': name, 'type': 'CustomRenderPiplineComputePass', 'file_inputs': ['shader.file'],
                'properties': {'shader': {'file': str(SHADER_DIRECTORY / shader), 'compute': entry},
                               'resources': resources, 'uniforms': uniforms,
                               'samplers': {'SourceCubemapSampler': {'filter': 'Point', 'address': 'Clamp'}},
                               'dispatch': {'threads': threads}}}

    def mip_uniforms(mip):
        extent = width >> mip
        padded = ((extent + 7) // 8) * 8
        return {'MipIndex': {'type': 'uint', 'value': mip},
                'NumMips': {'type': 'uint', 'value': mip_count},
                'FaceThreadGroupSize': {'type': 'int', 'value': padded},
                'ValidDispatchCoord': {'type': 'int2', 'value': [extent, extent]}}, [6 * padded, padded, 1]

    previous = capture_cube
    for mip in range(1, mip_count):
        name = prefix + 'Downsample' + str(mip)
        uniforms, threads = mip_uniforms(mip)
        nodes.append(node(name, 'Downsample.slang', 'DownsampleCS', [
            cube('source', 'SourceCubemapTexture', 'input', {'mip': mip - 1, 'mip_count': 1}),
            cube('cube', 'OutTextureMipColor', 'inputOutput', {'mip': mip})], uniforms, threads))
        edges.extend([[previous, name + '.source'], [previous, name + '.cube']])
        previous = name + '.cube'
    raw_cube = previous
    convolved_cube = None
    for mip in range(mip_count):
        name = prefix + 'Filter' + str(mip)
        uniforms, threads = mip_uniforms(mip)
        uniforms['CubeFaceOffset'] = {'type': 'int', 'value': 0}
        nodes.append(node(name, 'Filter.slang', 'FilterCS', [
            cube('source', 'SourceCubemapTexture', 'input', {'mip': 0, 'mip_count': mip_count}),
            cube('cube', 'OutTextureMipColor', 'output' if mip == 0 else 'inputOutput', {'mip': mip})], uniforms, threads))
        edges.append([raw_cube, name + '.source'])
        if convolved_cube:
            edges.append([convolved_cube, name + '.cube'])
        convolved_cube = name + '.cube'
    name = prefix + 'DiffuseSH'
    nodes.append(node(name, 'DiffuseSH.slang', 'ComputeSkyEnvMapDiffuseIrradianceCS', [
        cube('source', 'SourceCubemapTexture', 'input', {'mip': 0, 'mip_count': mip_count}),
        {'name': 'sh', 'direction': 'output', 'binding': 'OutIrradianceEnvMapSH',
         'kind': 'structured_buffer', 'stride': 16, 'count': 8}],
        {'MipIndex': {'type': 'uint', 'value': mip_count - 5},
         'UniformSampleSolidAngle': {'type': 'float', 'value': 4 * math.pi / 64}}, [8, 8, 1]))
    edges.append([convolved_cube, name + '.source'])
    return {'version': 1, 'nodes': nodes, 'edges': edges,
            'outputs': [raw_cube, convolved_cube, name + '.sh']}
