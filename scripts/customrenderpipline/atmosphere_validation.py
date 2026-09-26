"""Offline diagnostic graph and integration witnesses; never rendering inputs.

The oracle remains independent. These observations isolate GPU coordinate,
medium and sampler arithmetic from the scattering accumulation. Probe outputs
are read back only, with no edges leading back to the rendered LUTs.
"""
import copy
import math
import json
import struct
import zlib
from pathlib import Path
import numpy as np
from atmosphere_reference import _medium, _sphere_intersections

PROBE_SHADER = Path(__file__).resolve().parents[2] / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/AtmosphereProbe.slang'
OUTPUTS = ('probePosition', 'probePath', 'probeMedium', 'probeLight')


def save_atlas(observer, path, names, **options):
    """Save the native observation atlas, its layout and an RGB PNG preview."""
    path = Path(path)
    texture, layout = observer.atlas(names, **options)
    pixels = np.array(texture.to_numpy(), copy=True)
    np.save(path.with_suffix('.npy'), pixels)
    path.with_suffix('.json').write_text(json.dumps(layout, indent=2))
    rgb = np.rint(np.clip(pixels[..., :3], 0, 1) * 255).astype(np.uint8)

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

    path.with_suffix('.png').write_bytes(
        b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', rgb.shape[1], rgb.shape[0], 8, 2, 0, 0, 0)) +
        chunk(b'IDAT', zlib.compress(b''.join(b'\0' + row.tobytes() for row in rgb))) + chunk(b'IEND', b''))


def add_probes(declaration):
    """Append observation-only Compute nodes for the first native LUT pair."""
    for original in list(declaration['nodes'][:2]):
        node = copy.deepcopy(original)
        node['name'] = 'Probe' + node['name']
        props = node['properties']
        trans = props['shader']['defines']['TRANSMITTANCE_PASS'] == '1'
        props['shader']['file'] = str(PROBE_SHADER)
        extent = props['resources'][0]['size'][:]
        count = props['uniforms']['SkyAtmosphere.' + ('Transmittance' if trans else 'MultiScattering') + 'SampleCount']['value']
        extent[1] *= math.ceil(count) if trans else 2 * (math.ceil(count) + 1)
        props['resources'] = [r for r in props['resources'] if r['direction'] == 'input']
        props['resources'] += [dict(name=n, direction='output', binding=n, format='RGBA32Float', size=extent) for n in OUTPUTS]
        props['dispatch'] = {'extent': OUTPUTS[0]}
        declaration['nodes'].append(node)
        if not trans:
            declaration['edges'].append([original['name'].replace('MultiScattering', 'Transmittance') + '.lut', node['name'] + '.transmittance'])
        declaration['outputs'] += [node['name'] + '.' + n for n in OUTPUTS]


def read_probes(graph, tag):
    arrays = {}
    for name in OUTPUTS:
        texture = graph.getOutput('ProbeAtmosphere' + tag + '.' + name)
        arrays[name] = np.array(texture.to_numpy(), copy=True).reshape(texture.height, texture.width, 4)
    return arrays


def integration_witness(parameters, observations, size, count, transmittance):
    """Integrate measured sample positions/light in FP64, never upload values.

    Extinction is independently recalculated from positions. Comparing that
    quantity also separates medium math from sampler and loop accumulation.
    """
    p = {key: np.asarray(value, dtype=np.float64) for key, value in parameters.items()}
    width, height = size
    steps = math.ceil(count)
    paths = observations['probePath'].astype(np.float64)
    positions = observations['probePosition'][..., :3].astype(np.float64)
    lights = observations['probeLight'].astype(np.float64)
    scattering, extinction = _medium(positions, p)
    medium_error = float(np.max(abs(extinction - observations['probeMedium'][..., :3])))
    if transmittance:
        optical_depth = (extinction * paths[..., 0, None] / count).reshape(steps, height, width, 3).sum(axis=0)
        return np.exp(-0.5 * optical_depth), medium_error

    luminances, ratios = [], []
    for base in (0, height * (steps + 1)):
        through = np.ones((height, width, 3))
        luminance = np.zeros_like(through)
        ratio = np.zeros_like(through)
        dt = paths[base:base + height, :, 0, None] / count
        for step in range(steps):
            rows = slice(base + step * height, base + (step + 1) * height)
            position = positions[rows]
            radius = np.linalg.norm(position, axis=-1)
            up = position / radius[..., None]
            mu = lights[rows, :, 3]
            light = np.stack((mu * 0, np.sqrt(np.clip(1 - mu * mu, 0, 1)), mu), axis=-1)
            near, far = _sphere_intersections(position, light, p['BottomRadiusKm'], 0.001 * up)
            source = ((near < 0) & (far < 0))[..., None] * lights[rows, :, :3] * scattering[rows] / (4 * np.pi)
            segment = np.exp(-extinction[rows] * dt)
            luminance += through * (source - source * segment) / np.maximum(extinction[rows], 1e-9)
            ratio += through * scattering[rows] * dt
            through *= segment
        rows = slice(base + steps * height, base + (steps + 1) * height)
        ground = (paths[rows, :, 3] != 0)[..., None]
        luminance += ground * lights[rows, :, :3] * through * np.clip(lights[rows, :, 3, None], 0, 1) * p['GroundAlbedo'] / np.pi
        luminances.append(luminance)
        ratios.append(ratio)
    ratio = (ratios[0] + ratios[1]) * 0.5
    result = (luminances[0] + luminances[1]) * 0.5 * sum(ratio**order for order in range(5))
    return result * p['MultiScatteringFactor'], medium_error


def validate_medium(parameters, observations):
    """Check the observed GPU radius and density equations independently.

    A dot/sqrt/subtract on a 6360 km planet loses altitude precision. Check
    radius against a conservative FP32 operation envelope, then evaluate the
    medium at that observed radius in FP64. This separates spatial precision
    from incorrect physical coefficients or density equations.
    """
    p = {key: np.asarray(value, dtype=np.float32).astype(np.float64) for key, value in parameters.items()}
    position = observations['probePosition'].astype(np.float64)
    radius = np.linalg.norm(position[..., :3], axis=-1)
    observed_radius = position[..., 3]
    eps = np.finfo(np.float32).eps
    np.testing.assert_array_less(abs(radius - observed_radius), 2 * eps * np.maximum(radius, 1))
    radial_position = np.zeros_like(position[..., :3])
    radial_position[..., 2] = observed_radius
    _, extinction = _medium(radial_position, p)
    actual = observations['probeMedium'][..., :3]
    np.testing.assert_allclose(actual, extinction, atol=1e-8, rtol=2e-6)
    return {'radius_max_abs_km': float(abs(radius - observed_radius).max()),
            'density_at_observed_radius_max_abs': float(abs(actual - extinction).max())}


def validate_transmittance_witness(parameters, observations, actual, size, count):
    """Conservative spatial-roundoff enclosure, plus an FP32 reduction budget.

    This diagnostic shader reconstructs the production sample paths; it is
    not an instruction-level trace. Compilers may contract their arithmetic
    differently. Perturb each sampled radius and path length by a fixed
    operation envelope 4*float_epsilon*(radius+path+bottom), then propagate the
    resulting extinction interval through Beer absorption. The budget is
    calculated from physical inputs, never fitted to the result or a capture.
    Compact constant media are additionally tested against analytic paths.
    """
    p = {key: np.asarray(value, dtype=np.float32).astype(np.float64) for key, value in parameters.items()}
    width, height = size
    steps = math.ceil(count)
    pos = observations['probePosition'][..., :3].astype(np.float64)
    end = observations['probePath'][..., 0].astype(np.float64)
    radius = np.linalg.norm(pos, axis=-1)
    delta = 4 * np.finfo(np.float32).eps * (radius + abs(end) + p['BottomRadiusKm'])
    low = np.maximum(radius - p['BottomRadiusKm'] - delta, 0)
    high = np.maximum(radius - p['BottomRadiusKm'] + delta, 0)

    def ozone(altitude):
        return np.clip(np.where(altitude < p['AbsorptionDensity0LayerWidth'],
            p['AbsorptionDensity0LinearTerm'] * altitude + p['AbsorptionDensity0ConstantTerm'],
            p['AbsorptionDensity1LinearTerm'] * altitude + p['AbsorptionDensity1ConstantTerm']), 0, 1)

    # A tent may attain its maximum between the two endpoints.
    oz0, oz1 = ozone(low), ozone(high)
    crosses = (low <= p['AbsorptionDensity0LayerWidth']) & (high >= p['AbsorptionDensity0LayerWidth'])
    peak = np.maximum(
        np.clip(p['AbsorptionDensity0LinearTerm'] * p['AbsorptionDensity0LayerWidth'] + p['AbsorptionDensity0ConstantTerm'], 0, 1),
        np.clip(p['AbsorptionDensity1LinearTerm'] * p['AbsorptionDensity0LayerWidth'] + p['AbsorptionDensity1ConstantTerm'], 0, 1))
    ext_low = (np.exp(p['MieDensityExpScale'] * high)[..., None] * p['MieExtinction'] +
               np.exp(p['RayleighDensityExpScale'] * high)[..., None] * p['RayleighScattering'] +
               np.minimum(oz0, oz1)[..., None] * p['AbsorptionExtinction'])
    ext_high = (np.exp(p['MieDensityExpScale'] * low)[..., None] * p['MieExtinction'] +
                np.exp(p['RayleighDensityExpScale'] * low)[..., None] * p['RayleighScattering'] +
                np.where(crosses, np.maximum(np.maximum(oz0, oz1), peak), np.maximum(oz0, oz1))[..., None] * p['AbsorptionExtinction'])

    def reduce(extinction, distance):
        return (extinction * distance[..., None] / count).reshape(steps, height, width, 3).sum(axis=0)

    lower = np.exp(-.5 * reduce(ext_high, end + delta))
    upper = np.exp(-.5 * reduce(ext_low, np.maximum(end - delta, 0)))
    # Tested counts are <=16. Allow 8 float eps for final exp/sqrt/reduction,
    # separately from the explicitly propagated spatial uncertainty.
    arithmetic = 8 * np.finfo(np.float32).eps
    assert np.isfinite(actual).all()
    np.testing.assert_array_less(lower - arithmetic, actual)
    np.testing.assert_array_less(actual, upper + arithmetic)
    return {'enclosure_max_width': float((upper - lower).max()), 'arithmetic_abs_budget': float(arithmetic)}
