"""Offline Cube/SH numerical reference extracted from sky_light_filter_smoke.py.

Source provenance: source-before.zip member scripts/customrenderpipline/sky_light_filter_smoke.py,
SHA-256 f25921f54b1c1de69dc20e5e44e63ae070636b89f3b1e183a810a280ff7dd71f.
No GPU runner or legacy SchemaPipeline dependency is retained here.
"""
import math
import numpy as np
from sky_light_filter import SHADER_DIRECTORY, sky_light_filter_fragment

def cube_directions(width, *, normalized=True):
    """D3D Cube face bases, independently expressed as center/right/down vectors."""
    centers = np.eye(3)[[0, 0, 1, 1, 2, 2]] * np.array([1, -1, 1, -1, 1, -1])[:, None]
    right = np.array([[0, 0, -1], [0, 0, 1], [1, 0, 0], [1, 0, 0], [1, 0, 0], [-1, 0, 0]])
    down = np.array([[0, -1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1], [0, -1, 0], [0, -1, 0]])
    uv = (np.arange(width) + .5) * 2 / width - 1
    d = centers[:, None, None, :] + uv[None, None, :, None] * right[:, None, None, :] + uv[None, :, None, None] * down[:, None, None, :]
    return d / np.linalg.norm(d, axis=-1, keepdims=True) if normalized else d


def sample_cube(mips, directions, lod):
    """Independent point/nearest-mip Cube addressing of observed RGB texels."""
    directions = np.asarray(directions, dtype=np.float64)
    shape = directions.shape[:-1]
    d = directions.reshape(-1, 3)
    major = abs(d).argmax(axis=1)
    face = major * 2 + (d[np.arange(len(d)), major] < 0)
    axis = abs(d[np.arange(len(d)), major])
    if np.any(axis == 0):
        raise ValueError('Cube sampling requires nonzero directions')
    u = np.choose(face, [-d[:, 2], d[:, 2], d[:, 0], d[:, 0], d[:, 0], -d[:, 0]]) / axis
    v = np.choose(face, [-d[:, 1], -d[:, 1], d[:, 2], -d[:, 2], -d[:, 1], -d[:, 1]]) / axis
    level = np.floor(np.clip(np.broadcast_to(lod, shape).reshape(-1), 0, len(mips) - 1) + .5).astype(int)
    result = np.empty((len(d), 3))
    for mip, values in enumerate(mips):
        select = np.flatnonzero(level == mip)
        width = values.shape[1]
        x = np.clip(np.floor((u[select] + 1) * width / 2).astype(int), 0, width - 1)
        y = np.clip(np.floor((v[select] + 1) * width / 2).astype(int), 0, width - 1)
        result[select] = values[face[select], y, x, :3]
    return result.reshape(shape + (3,))


def authored_direction_color(directions, scale=1.):
    x, y, z = np.moveaxis(directions, -1, 0)
    return scale * np.stack([1 + .31*x + .17*y + .09*z + .08*x*y,
                            2 - .11*x + .23*y + .07*z + .06*y*z,
                            3 + .13*x - .05*y + .29*z + .04*(x*x-y*y)], axis=-1)


def downsample_reference(previous):
    """Nine-tap numerical oracle, reading only the observed preceding mip."""
    width = previous.shape[1] // 2
    d = cube_directions(width, normalized=False)
    n = d / np.linalg.norm(d, axis=-1, keepdims=True)
    down = np.array([[0, -1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1], [0, -1, 0], [0, -1, 0]])
    tangent_x = np.cross(d + down[:, None, None, :], n)
    tangent_x /= np.linalg.norm(tangent_x, axis=-1, keepdims=True)
    tangent_y = np.cross(n, tangent_x)
    color = sample_cube([previous], d, 0)
    for x, y in [(-.7, -.7), (.7, -.7), (-.7, .7), (.7, .7), (0, -1), (-1, 0), (1, 0), (0, 1)]:
        color += .375 * sample_cube([previous], d + (x*tangent_x+y*tangent_y)*(4/width), 0)
    return color / 4


def point_cube_candidates(cube, direction, *, allow_texel_ties=True):
    """RGB texels admitted only at FP32 coordinate/major-axis boundaries.

    64 FP32 epsilons bound the short normalize/cross/project chain. This is
    a coordinate uncertainty, never a radiance tolerance. Full RGB samples
    remain correlated; no independent channel intervals are introduced.
    """
    d = np.asarray(direction, dtype=float)
    magnitude = abs(d).max()
    if magnitude == 0:
        raise ValueError('Cube sampling requires nonzero directions')
    epsilon = 64*np.finfo(np.float32).eps
    width = cube.shape[1]
    values = []
    for axis in np.flatnonzero(magnitude-abs(d) <= epsilon*magnitude):
        face = 2*axis+int(d[axis] < 0)
        u = [-d[2], d[2], d[0], d[0], d[0], -d[0]][face]/abs(d[axis])
        v = [-d[1], -d[1], d[2], -d[2], -d[1], -d[1]][face]/abs(d[axis])
        x, y = (np.array([u, v])+1)*width/2
        delta = epsilon*width if allow_texel_ties else 0
        xs = np.unique(np.clip(np.floor([x-delta, x+delta]).astype(int), 0, width-1))
        ys = np.unique(np.clip(np.floor([y-delta, y+delta]).astype(int), 0, width-1))
        values.extend(cube[face, yy, xx, :3] for yy in ys for xx in xs)
    return np.unique(np.asarray(values, dtype=float), axis=0)


def downsample_candidate_error(previous, observed, *, quantized=False, scale=1.):
    """Maximum distance to a complete nine-tap RGB result, across all pixels."""
    width = previous.shape[1]//2
    d = cube_directions(width, normalized=False)
    n = d/np.linalg.norm(d, axis=-1, keepdims=True)
    down = np.array([[0,-1,0], [0,-1,0], [0,0,1], [0,0,-1], [0,-1,0], [0,-1,0]])
    tx = np.cross(d+down[:,None,None,:], n)
    tx /= np.linalg.norm(tx, axis=-1, keepdims=True)
    ty = np.cross(n, tx)
    taps = [d]+[d+tx*(x*4/width)+ty*(y*4/width) for x,y in
                [(-.7,-.7),(.7,-.7),(-.7,.7),(.7,.7),(0,-1),(-1,0),(1,0),(0,1)]]
    largest = 0.
    for pixel in np.ndindex(6, width, width):
        sums = np.zeros((1,3))
        for tap, directions in enumerate(taps):
            # Center coordinates are exact binary fractions. Side taps pass
            # through normalization and admit either side of numerical ties.
            candidates = point_cube_candidates(previous, directions[pixel], allow_texel_ties=tap != 0)
            sums = (sums[:,None,:]+candidates[None,:,:]*(.25 if tap == 0 else .09375)).reshape(-1,3)
        if quantized:
            from downsample_reference import pack_r11g11b10, unpack_r11g11b10
            sums = unpack_r11g11b10(pack_r11g11b10(sums, rounding='toward_zero'))[...,:3]
        largest = max(largest, float(np.min(np.max(abs(sums-observed[pixel]), axis=-1)))/scale)
    return largest


def filter_reference(mips, mip, directions):
    """Double-precision CPU quadrature with an independent Cube sampler.

    This transcribes the source's deterministic sample sequence and LOD equation;
    it is not an independent implementation of the full UE capture pipeline.
    """
    n = np.asarray(directions)
    n = n / np.linalg.norm(n, axis=-1, keepdims=True)
    roughness = 2 ** ((mip - len(mips) + 3) / 1.2)
    if roughness < .01:
        return np.maximum(sample_cube(mips, n, 0), 0)
    count = 32 if roughness < .1 else 64
    index = np.arange(count)
    e_x = index / count
    e_y = np.array([int(f'{i:032b}'[::-1], 2) / 2**32 for i in index])
    sign = np.where(n[..., 2] >= 0, 1., -1.)
    a = -1 / (sign + n[..., 2])
    b = n[..., 0] * n[..., 1] * a
    tx = np.stack([1+sign*a*n[..., 0]**2, sign*b, -sign*n[..., 0]], axis=-1)
    ty = np.stack([b, sign+a*n[..., 1]**2, -n[..., 1]], axis=-1)
    phi = e_x * (2*math.pi)
    if roughness > .99:
        z = np.sqrt(e_y)
        radial = np.sqrt(1-e_y)
        local = np.stack([radial*np.cos(phi), radial*np.sin(phi), z], axis=-1)
        pdf = z / math.pi
        weights = np.ones(count)
    else:
        e_y *= .995
        a2 = roughness**4
        z = np.sqrt((1-e_y)/(1+(a2-1)*e_y))
        radial = np.sqrt(1-z*z)
        h = np.stack([radial*np.cos(phi), radial*np.sin(phi), z], axis=-1)
        local = 2*z[:, None]*h - [0, 0, 1]
        pdf = a2/(math.pi*((z*a2-z)*z+1)**2)*.25
        weights = np.maximum(local[:, 2], 0)
    d = local[:, 0, None]*tx[..., None, :] + local[:, 1, None]*ty[..., None, :] + local[:, 2, None]*n[..., None, :]
    solid_angle_texel = 4*math.pi/(6*mips[0].shape[1]**2)*2
    with np.errstate(divide='ignore'):
        lod = .5*np.log2(1/(count*pdf)/solid_angle_texel)
    colors = sample_cube(mips, d, lod)
    return np.maximum(np.sum(colors*weights[:, None], axis=-2)/weights.sum(), 0)


def sh_reference(mips, mip):
    """Project 64 cell-center sphere samples and independently pack diffuse SH."""
    u, v = np.meshgrid((np.arange(8)+.5)/8, (np.arange(8)+.5)/8)
    z = 1-2*v.ravel()
    radial = np.sqrt(1-z*z)
    x, y = radial*np.cos(2*math.pi*u.ravel()), radial*np.sin(2*math.pi*u.ravel())
    colors = sample_cube(mips, np.stack([x, y, z], axis=-1), mip)
    basis = np.stack([np.full(64, .282095), -.488603*y, .488603*z, -.488603*x,
                      1.092548*x*y, -1.092548*y*z, .315392*(3*z*z-1),
                      -1.092548*x*z, .546274*(x*x-y*y)], axis=1)
    raw = colors.T @ basis * (4*math.pi/64)
    c0, c1, c2, c3 = 1/(2*math.sqrt(math.pi)), math.sqrt(3)/(3*math.sqrt(math.pi)), math.sqrt(15)/(8*math.sqrt(math.pi)), math.sqrt(5)/(16*math.sqrt(math.pi))
    result = np.empty((8, 4))
    result[:3] = np.stack([-c1*raw[:, 3], -c1*raw[:, 1], c1*raw[:, 2], c0*raw[:, 0]-c3*raw[:, 6]], axis=1)
    result[3:6] = np.stack([c2*raw[:, 4], -c2*raw[:, 5], 3*c3*raw[:, 6], -c2*raw[:, 7]], axis=1)
    result[6] = [*(.5*c2*raw[:, 8]), 1]
    result[7] = np.sum(raw[:, 0]/(.282095*4*math.pi))*.3333
    return result


def fixture_definition(width, output_format, *, pattern, color, scale):
    graph = sky_light_filter_fragment('Capture.cube', width=width, output_format=output_format)
    capture = {'name': 'Capture', 'type': 'CustomRenderPiplineComputePass', 'file_inputs': ['shader.file'],
               'properties': {'shader': {'file': str(SHADER_DIRECTORY/'Fixture.slang')},
                'resources': [{'name': 'cube', 'direction': 'output', 'binding': 'FixtureCube', 'kind': 'textureCube',
                               'format': output_format, 'size': [width, width], 'mip_count': width.bit_length(), 'view': {'mip': 0}}],
                'uniforms': {'FixtureParameters.Width': {'type': 'uint', 'value': width},
                             'FixtureParameters.Pattern': {'type': 'uint', 'value': pattern},
                             'FixtureParameters.ConstantColor': {'type': 'float3', 'value': list(color)},
                             'FixtureParameters.Scale': {'type': 'float', 'value': scale}},
                'dispatch': {'threads': [width, width, 6]}}}
    graph['nodes'].insert(0, capture)
    for label, source in zip(('Raw', 'Convolved'), graph['outputs'][:2]):
        for mip in range(width.bit_length()):
            extent = width >> mip
            name = label + 'Read' + str(mip)
            graph['nodes'].append({'name': name, 'type': 'CustomRenderPiplineComputePass', 'file_inputs': ['shader.file'],
                'properties': {'shader': {'file': str(SHADER_DIRECTORY/'Readback.slang')},
                    'resources': [{'name': 'cube', 'direction': 'input', 'binding': 'SourceCubemapTexture', 'kind': 'textureCube',
                                   'format': output_format, 'size': [width, width], 'mip_count': width.bit_length(),
                                   'view': {'mip': mip, 'mip_count': 1}},
                                  {'name': 'atlas', 'direction': 'output', 'binding': 'Atlas', 'format': 'RGBA32Float', 'size': [6*extent, extent]}],
                    'uniforms': {'ReadbackParameters.Width': {'type': 'uint', 'value': extent}},
                    'samplers': {'SourceCubemapSampler': {'filter': 'Point', 'address': 'Clamp'}}, 'dispatch': {'extent': 'atlas'}}})
            graph['edges'].append([source, name+'.cube'])
            graph['outputs'].append(name+'.atlas')
    return graph
