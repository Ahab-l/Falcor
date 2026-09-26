"""Non-launching cube-atlas helpers extracted from sky_light_capture_smoke.py.

Source provenance SHA-256: 388b8233cf4e92c2de68729a30701793484d685b01c959d20caec945c5da4a4b.
"""
import numpy as np
from sky_light_filter import SHADER_DIRECTORY

def add_cube_atlas(graph, source, name, width, output_format, *, mip=0):
    extent = width >> mip
    graph['nodes'].append({'name': name, 'type': 'CustomRenderPiplineComputePass', 'file_inputs': ['shader.file'], 'properties': {
        'shader': {'file': str(SHADER_DIRECTORY/'Readback.slang')},
        'resources': [{'name': 'cube', 'direction': 'input', 'binding': 'SourceCubemapTexture', 'kind': 'textureCube',
                       'format': output_format, 'size': [width, width], 'mip_count': width.bit_length(), 'view': {'mip': mip, 'mip_count': 1}},
                      {'name': 'atlas', 'direction': 'output', 'binding': 'Atlas', 'format': 'RGBA32Float', 'size': [6*extent, extent]}],
        'uniforms': {'ReadbackParameters.Width': {'type': 'uint', 'value': extent}},
        'samplers': {'SourceCubemapSampler': {'filter': 'Point', 'address': 'Clamp'}}, 'dispatch': {'extent': 'atlas'}}})
    graph['edges'].append([source, name+'.cube'])
    graph['outputs'].append(name+'.atlas')


def read_cube(graph, name, width):
    atlas = np.array(graph.getOutput(name+'.atlas').to_numpy(), copy=True).reshape(width, 6*width, 4)
    return atlas.reshape(width, 6, width, 4).transpose(1, 0, 2, 3)
