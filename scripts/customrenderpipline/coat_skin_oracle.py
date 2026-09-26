"""Independent CPU reference for the desktop legacy ClearCoat and Skin models.

Only NumPy and the earlier independent component references are used. No GPU
execution or production ClearCoat/Skin shader source is imported or inspected.
"""
import numpy as np

import capsule_lighting_smoke as capsule
import model_lighting_reference as legacy


def _lut_inputs(lut, uv):
    values = np.asarray(lut, dtype=np.float64)
    coords = np.asarray(uv, dtype=np.float64)
    if (values.ndim != 3 or min(values.shape[:2]) < 1
            or values.shape[2] not in (3, 4) or not np.isfinite(values).all()):
        raise ValueError('LUT must contain finite linear RGB or RGBA texels')
    if coords.shape != (2,) or not np.isfinite(coords).all():
        raise ValueError('UV must contain two finite normalized coordinates')
    # Texel centers have integer coordinates in this representation.
    position = coords * [values.shape[1], values.shape[0]] - 0.5
    if not np.isfinite(position).all():
        raise ValueError('LUT texel coordinates overflowed')
    return values, position


def _sample_texel(values, position):
    height, width = values.shape[:2]
    x, y = np.clip(position, [0, 0], [width - 1, height - 1])
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    x1, y1 = min(x0 + 1, width - 1), min(y0 + 1, height - 1)
    fx, fy = x - x0, y - y0
    row0 = (1 - fx) * values[y0, x0, :3] + fx * values[y0, x1, :3]
    row1 = (1 - fx) * values[y1, x0, :3] + fx * values[y1, x1, :3]
    return (1 - fy) * row0 + fy * row1


def sample_lut(lut, uv):
    """Ideal float64 bilinear-clamp RGB, with linearization already applied.

    The actual Skin LUT input is the 256x256x4 source SRV.Load readback.
    Smaller RGB/RGBA arrays are accepted for independent sampling checks.
    """
    values, position = _lut_inputs(lut, uv)
    return _sample_texel(values, position)


def sample_lut_bounds(lut, uv, texel_error=1 / 256):
    """RGB extrema for independent coordinate error of +/-texel_error.

    Error is measured in texels, not normalized UV units. The default covers
    one subtexel at the D3D minimum eight fractional bits; it assumes no fitted
    hardware rounding rule. These bounds cover coordinate uncertainty only,
    excluding filter arithmetic error, source decoding error and UV input error.
    """
    values, position = _lut_inputs(lut, uv)
    error = float(texel_error)
    if not np.isfinite(error) or error < 0:
        raise ValueError('Texel error must be finite and nonnegative')
    extent = np.array([values.shape[1] - 1, values.shape[0] - 1])
    lower = np.clip(position - error, 0, extent)
    upper = np.clip(position + error, 0, extent)

    def breakpoints(lo, hi):
        # Bilinear extrema lie at each clipped cell's corners, including the
        # interior grid intersections when the box crosses a cell boundary.
        integers = np.arange(np.ceil(lo), np.floor(hi) + 1)
        return np.unique(np.concatenate(([lo], integers, [hi])))

    candidates = np.asarray([
        _sample_texel(values, [x, y])
        for x in breakpoints(lower[0], upper[0])
        for y in breakpoints(lower[1], upper[1])
    ])
    return candidates.min(axis=0), candidates.max(axis=0)


def _ggx(a2, no_h, no_v, area_no_l):
    denominator = capsule.positive(1 - (1 - a2) * no_h ** 2, 'GGX denominator')
    alpha = np.sqrt(a2)
    visibility_denominator = capsule.positive(
        area_no_l * (no_v * (1 - alpha) + alpha)
        + no_v * (area_no_l * (1 - alpha) + alpha), 'Smith visibility denominator')
    return a2 / (np.pi * denominator ** 2), 0.5 / visibility_denominator, float(denominator)


def _clear_coat(p):
    """UE ShadingModels.ush ClearCoatBxDF, isotropic non-rect legacy profile."""
    base, metal, rough = p[0, :3], p[0, 3], p[1, 3]
    coat, coat_rough = p[9, 1], max(p[9, 2], 0.02)
    has_bottom = bool(p[9, 3] != 0)
    top_n = capsule.unit(p[1, :3]) if has_bottom else p[1, :3]
    view, light = p[2, :3], p[4, :3]
    area = {'sphere': p[5, 3], 'soft': p[7, 0], 'line': p[7, 1]}
    area_no_l = p[3, 3]  # Caller-supplied: do not recompute or normalize bottomN.
    incident = p[5, :3] * p[4, 3]
    geometry = incident * area_no_l

    compensation_denominator = 1 - rough ** 2
    compensation = ((1 - coat_rough ** 2) / compensation_denominator
                    if compensation_denominator > 0 else 0.0)
    top_area = dict(area, sphere=float(np.clip(area['sphere'] * compensation, 0, 1)))
    top, top_branch = capsule.sphere_context(
        capsule.initial_context(top_n, view, light), top_area['sphere'], not has_bottom)
    top['NoV'] = float(np.clip(abs(top['NoV']) + 1e-5, 0, 1))
    top_fresnel = 0.04 + 0.96 * (1 - top['VoH']) ** 5
    top_a2, top_energy = capsule.energy_oracle(coat_rough, top['VoH'], top_area)
    top_d, top_vis, top_denominator = _ggx(top_a2, top['NoH'], top['NoV'], area_no_l)
    specular = geometry * coat * top_d * top_energy * top_vis * top_fresnel
    fresnel_coefficient = (1 - top_fresnel) ** 2

    # Without a bottom normal the top sphere-corrected context is retained.
    context, bottom_branch = dict(top), 'reuse_top'
    if has_bottom:
        bottom_n = p[10, :3]
        half_vector = capsule.unit(view + light)
        context = dict(
            NoH=float(np.clip(np.dot(bottom_n, half_vector), 0, 1)),
            NoV=float(np.clip(np.dot(bottom_n, view), 0, 1)),
            NoL=float(np.clip(np.dot(bottom_n, light), 0, 1)),
            VoL=float(np.clip(np.dot(view, light), 0, 1)),
            VoH=float(np.clip(np.dot(view, half_vector), 0, 1)))
        context, bottom_branch = capsule.sphere_context(context, area['sphere'], True)
        context['NoV'] = float(np.clip(abs(context['NoV']) + 1e-5, 0, 1))

    blend = (0.63 - 0.22 * context['VoH']) * context['VoH'] - 0.745
    projection = blend * context['NoH']
    refracted = dict(context)
    refracted['NoV'] = float(np.clip(context['NoV'] / 1.5 - projection, 0.001, 1))
    refracted['NoL'] = float(np.clip(context['NoL'] / 1.5 - projection, 0.001, 1))
    refracted['VoH'] = float(np.clip(context['VoH'] / 1.5 - blend, 0, 1))
    refracted['VoL'] = 2 * refracted['VoH'] ** 2 - 1

    transmittance = np.ones(3, dtype=np.float64)
    if metal > 0:
        thin_transmission = 1 / refracted['NoV'] + 1 / refracted['NoL']
        exponent = max(thin_transmission - 2, 0) / 2
        absorbed = np.maximum(base / np.pi, 0.0001) ** exponent
        transmittance += metal * (absorbed - 1)
    attenuation = fresnel_coefficient * transmittance
    diffuse = geometry * base * (1 - metal) / np.pi * ((1 - coat) + coat * attenuation)

    # Energy is evaluated with the unrefracted VoH and restored area sphere.
    bottom_a2, bottom_energy = capsule.energy_oracle(rough, context['VoH'], area)
    bottom_d, bottom_vis, bottom_denominator = _ggx(
        bottom_a2, refracted['NoH'], refracted['NoV'], area_no_l)
    f0 = (1 - metal) * (0.08 * p[2, 3]) + metal * base

    def fresnel(vo_h):
        grazing = (1 - vo_h) ** 5
        return np.clip(50 * f0[1], 0, 1) * grazing + (1 - grazing) * f0

    mixed_fresnel = ((1 - coat) * fresnel(context['VoH'])
                     + coat * attenuation * fresnel(refracted['VoH']))
    specular += geometry * bottom_energy * bottom_d * bottom_vis * mixed_fresnel
    details = dict(
        top_newton=not has_bottom, bottom_newton=has_bottom,
        top_branch=top_branch, bottom_branch=bottom_branch,
        top_context=top, unrefracted_context=context, refracted_context=refracted,
        top_sphere=top_area['sphere'], original_sphere=float(area['sphere']),
        roughness_compensation=float(compensation), coat_roughness=float(coat_rough),
        top_a2=float(top_a2), top_energy=float(top_energy),
        bottom_a2=float(bottom_a2), bottom_energy=float(bottom_energy),
        bottom_energy_voh=float(context['VoH']),
        top_ggx_d=top_denominator, bottom_ggx_d=bottom_denominator,
        top_fresnel=float(top_fresnel), fresnel_coefficient=float(fresnel_coefficient),
        metal_transmittance=transmittance.tolist())
    return np.asarray([diffuse, specular]), details


def oracle(p, model, lut_linear=None):
    """Return unshadowed diffuse/specular/transmission rows and diagnostics.

    Input is an 11x4 float32 fixture, promoted to float64. Rows 0..8 follow
    model_lighting_smoke.pack; row 9 is model ID, coat amount, coat roughness,
    bottom-normal flag; row 10.xyz is the caller-supplied bottom normal. Row
    1.xyz is topN; it is normalized only by ClearCoat with a bottom normal.
    Row 3.w is the supplied saturated area NoL and is never recomputed here.
    Shadow factors in row 8 are applied by the caller, outside this model.
    """
    p = np.asarray(p, dtype=np.float64)
    if p.shape != (11, 4) or not np.isfinite(p).all():
        raise ValueError('Component inputs must be a finite 11x4 array')
    if not float(np.float32(0.02)) <= p[1, 3] <= 1:
        raise ValueError('Base roughness must be in the supported [0.02, 1] profile')
    if not (0 <= p[3, 3] <= 1 and 0 <= p[5, 3] <= 1
            and 0 <= p[7, 0] <= 1 and -1 < p[7, 1] <= 1):
        raise ValueError('Invalid saturated area inputs or singular line angle')
    result = np.zeros((3, 4), dtype=np.float64)
    result[0, 3] = 1
    if model == 'ClearCoat':
        result[:2, :3], details = _clear_coat(p)
    elif model in ('PreintegratedSkin', 'Skin'):
        if lut_linear is None:
            raise ValueError('Skin requires linear source LUT texels')
        result[:2, :3], details = legacy.default_or_cloth(p, False)
        uv = [float(np.clip(np.dot(p[1, :3], p[3, :3]) * 0.5 + 0.5, 0, 1)),
              float(1 - p[6, 3])]
        brdf = sample_lut(lut_linear, uv)
        result[2, :3] = p[5, :3] * p[4, 3] * brdf * p[6, :3]
        details.update(lut_uv=uv, lut_rgb=brdf.tolist())
    else:
        raise ValueError('Unsupported ClearCoat/Skin oracle model: ' + str(model))
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite ClearCoat/Skin oracle result')
    return result, details


def self_test():
    """Pure CPU checks; no evidence files or production inputs are modified."""
    lut = np.zeros((2, 2, 4), dtype=np.float32)
    lut[:, :, 0] = [[0, 2], [4, 6]]
    lut[:, :, 1] = [[1, 0], [0, 1]]
    lut[:, :, 2] = 0.5
    lut[:, :, 3] = 1
    np.testing.assert_array_equal(sample_lut(lut, [0, 0]), [0, 1, 0.5])
    np.testing.assert_array_equal(sample_lut(lut, [1, 1]), [6, 1, 0.5])
    np.testing.assert_array_equal(sample_lut(lut, [-2, 3]), [4, 0, 0.5])
    np.testing.assert_array_equal(sample_lut(lut, [0.25, 0.25]), [0, 1, 0.5])
    np.testing.assert_array_equal(sample_lut(lut, [0.5, 0.5]), [3, 0.5, 0.5])
    np.testing.assert_array_equal(sample_lut(lut, [0.375, 0.625]), [3.5, 0.375, 0.5])
    peak = np.zeros((3, 3, 4), dtype=np.float32)
    peak[1, 1, :3] = 10
    lower, upper = sample_lut_bounds(peak, [0.5, 0.5])
    # The uncertainty box crosses a texel-center peak: four outer corners
    # alone would miss the maximum at its interior cell boundary.
    np.testing.assert_array_equal(upper, [10, 10, 10])
    assert np.all(lower < upper)
    lower, upper = sample_lut_bounds(lut, [0.37, 0.62], 0)
    np.testing.assert_array_equal(lower, upper)
    np.testing.assert_array_equal(lower, sample_lut(lut, [0.37, 0.62]))
    rng = np.random.default_rng(26550064)
    random_lut = rng.uniform(0, 1, (5, 7, 4)).astype(np.float32)
    for index in range(48):
        uv = rng.uniform(-0.25, 1.25, 2)
        error = (0, 1 / 256, 0.75, 2)[index % 4]
        lower, upper = sample_lut_bounds(random_lut, uv, error)
        for perturbation in rng.uniform(-error, error, (12, 2)):
            sampled = sample_lut(random_lut, uv + perturbation / [7, 5])
            assert np.all(sampled >= lower - 2e-15)
            assert np.all(sampled <= upper + 2e-15)

    base = legacy.case('cpu-self-check', 'DefaultLit', sphere=0.04, soft=0.02, line=0.8)
    packed = np.zeros((11, 4), dtype=np.float32)
    packed[:9] = legacy.pack(base)[:9]
    packed[9] = [4, 0.7, 0.15, 0]
    packed[10, :3] = packed[1, :3]
    zero = packed.copy()
    zero[9, 1] = 0
    zero_result, zero_details = oracle(zero, 'ClearCoat')
    default, _ = legacy.default_or_cloth(zero.astype(np.float64), False)
    np.testing.assert_allclose(zero_result[0, :3], default[0], rtol=1e-14, atol=1e-16)
    assert not np.allclose(zero_result[1, :3], default[1], rtol=1e-6, atol=1e-10)
    low, floor = packed.copy(), packed.copy()
    low[9, 2], floor[9, 2] = 0, 0.02
    np.testing.assert_array_equal(oracle(low, 'ClearCoat')[0], oracle(floor, 'ClearCoat')[0])
    nonmetal = packed.copy()
    nonmetal[0, 3] = 0
    np.testing.assert_array_equal(oracle(nonmetal, 'ClearCoat')[1]['metal_transmittance'], np.ones(3))
    altered_shadow = packed.copy()
    altered_shadow[8, :3] = [0, 0, 0]
    np.testing.assert_array_equal(oracle(packed, 'ClearCoat')[0], oracle(altered_shadow, 'ClearCoat')[0])
    both = packed.copy()
    both[9, 3] = 1
    both[1, :3] = [0, 0, 2]
    both[10, :3] = legacy.unit([0.2, 0, 1])
    both[3, 3] = np.clip(np.dot(both[10, :3], both[3, :3]), 0, 1)
    _, two_details = oracle(both, 'ClearCoat')
    assert two_details['top_newton'] is False and two_details['bottom_newton'] is True
    assert two_details['bottom_energy_voh'] == two_details['unrefracted_context']['VoH']
    assert two_details['bottom_energy_voh'] != two_details['refracted_context']['VoH']
    unit_top = both.copy()
    unit_top[1, :3] = [0, 0, 1]
    np.testing.assert_array_equal(oracle(both, 'ClearCoat')[0], oracle(unit_top, 'ClearCoat')[0])
    supplied_bottom = both.copy()
    supplied_bottom[5, 3] = 0
    supplied_bottom[10, :3] = [0, 0, 0.7]
    supplied_bottom[3, 3] = 0.3
    _, supplied_details = oracle(supplied_bottom, 'ClearCoat')
    expected_no_v = np.clip(
        np.dot(supplied_bottom[10, :3].astype(np.float64), supplied_bottom[2, :3]), 0, 1)
    assert supplied_details['unrefracted_context']['NoV'] == min(expected_no_v + 1e-5, 1)

    # An independently simplified normal-incidence result checks both layers
    # against a closed form, including extrapolation of the unclamped amount.
    normal = packed.copy()
    normal[1, :3] = normal[2, :3] = normal[3, :3] = normal[4, :3] = [0, 0, 1]
    normal[3, 3] = 1
    normal[5, 3] = normal[7, 0] = 0
    normal[7, 1] = 1
    for amount in (-0.2, 0, 0.7, 1, 1.2):
        normal[9, 1] = amount
        q = normal.astype(np.float64)
        result, details = oracle(normal, 'ClearCoat')
        tint = (1 - q[0, 3]) * (0.08 * q[2, 3]) + q[0, 3] * q[0, :3]
        throughput = 1 - q[9, 1] + q[9, 1] * 0.96 ** 2
        incoming = q[5, :3] * q[4, 3]
        expected_diffuse = incoming * q[0, :3] * (1 - q[0, 3]) / np.pi * throughput
        expected_specular = incoming / (4 * np.pi) * (
            q[9, 1] * 0.04 / q[9, 2] ** 4 + throughput * tint / q[1, 3] ** 4)
        np.testing.assert_allclose(result[0, :3], expected_diffuse, rtol=1e-13, atol=1e-16)
        np.testing.assert_allclose(result[1, :3], expected_specular, rtol=1e-12, atol=1e-16)
        np.testing.assert_array_equal(details['metal_transmittance'], np.ones(3))
    skin = packed.copy()
    skin[3, :3] = [0, 0, -1]
    skin[3, 3] = 0
    skin[6, 3] = 1
    result, details = oracle(skin, 'PreintegratedSkin', lut)
    np.testing.assert_array_equal(details['lut_uv'], [0, 0])
    np.testing.assert_allclose(result[2, :3], skin[5, :3] * skin[4, 3] * skin[6, :3] * [0, 1, 0.5], rtol=1e-7)
    assert result[0, 3] == 1 and not np.any(result[:2, :3])
    for opacity, expected_uv_y in ((-0.5, 1.5), (0, 1), (1, 0), (1.5, -0.5)):
        skin[6, 3] = opacity
        result, details = oracle(skin, 'PreintegratedSkin', lut)
        assert details['lut_uv'][1] == expected_uv_y
        expected_texel = lut[0 if opacity >= 1 else -1, 0, :3].astype(np.float64)
        q = skin.astype(np.float64)
        np.testing.assert_array_equal(result[2, :3], q[5, :3] * q[4, 3] * expected_texel * q[6, :3])
    skin[8, :3] = 0
    np.testing.assert_array_equal(oracle(skin, 'PreintegratedSkin', lut)[0], result)
    print('COAT_SKIN_CPU_SELF_CHECK_PASSED')


if __name__ == '__main__':
    self_test()
