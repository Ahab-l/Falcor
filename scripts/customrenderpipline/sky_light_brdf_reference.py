"""Offline numerical oracle. These arrays are assertions, never GPU inputs.

NumPy expresses the CPU algorithm over the entire grid, with independently
computed bit reversal and FP32 arithmetic. This is not a captured UE texture;
CPU transcendental-library differences are reported by the native smoke.
"""
import math
import numpy as np


def correct_divide_candidate(numerator, denominator, candidate):
    """Validate the shader's midpoint correction over positive normal FP32 data.

    Each midpoint has at most25 significant bits; its product with a float
    denominator has at most49. These comparisons are exact in binary64.
    This helper tests the adapter; integrate_reference does not use it.
    """
    numerator = np.asarray(numerator, np.float32).astype(np.float64)
    denominator = np.asarray(denominator, np.float32).astype(np.float64)
    result = np.asarray(candidate, np.float32).copy()
    for _ in range(4):
        bits = result.view(np.uint32)
        lower = (bits - np.uint32(1)).view(np.float32).astype(np.float64)
        upper = (bits + np.uint32(1)).view(np.float32).astype(np.float64)
        low = (result.astype(np.float64) + lower) * .5 * denominator
        high = (result.astype(np.float64) + upper) * .5 * denominator
        odd = (bits & 1) != 0
        down = (numerator < low) | ((numerator == low) & odd)
        up = (numerator > high) | ((numerator == high) & odd)
        result = np.where(down, lower, np.where(up, upper, result)).astype(np.float32)
    return result


def correct_sqrt_candidate(value, candidate):
    """Midpoint-square comparisons are exact in binary64 (at most50 bits)."""
    value = np.asarray(value, np.float32).astype(np.float64)
    result = np.asarray(candidate, np.float32).copy()
    for _ in range(4):
        bits = result.view(np.uint32)
        lower = (bits - np.uint32(1)).view(np.float32).astype(np.float64)
        upper = (bits + np.uint32(1)).view(np.float32).astype(np.float64)
        low = (result.astype(np.float64) + lower) * .5
        high = (result.astype(np.float64) + upper) * .5
        odd = (bits & 1) != 0
        down = (value < low*low) | ((value == low*low) & odd)
        up = (value > high*high) | ((value == high*high) & odd)
        result = np.where(down, lower, np.where(up, upper, result)).astype(np.float32)
    return result


def source_cosine_polynomial(value):
    """CPU validation of the adapter over the source's bounded phase domain.

    Degree28 Taylor coefficients derive from factorials, not fitted LUT values.
    Binary64 is used only to evaluate cosf before its source float32 result.
    The full integrator uses math.cos and remains independent of this adapter.
    """
    value = np.asarray(value, np.float32).astype(np.float64)
    reduced = np.where(value > math.pi, value - 2*math.pi,
                       np.where(value < -math.pi, value + 2*math.pi, value))
    squared = reduced * reduced
    result = np.full_like(value, 1 / math.factorial(28))
    for order in range(13, -1, -1):
        result = result * squared + ((-1) ** order) / math.factorial(2 * order)
    return result.astype(np.float32)


def integrate_reference(*, dtype=np.float32):
    """Return source A/B before quantization; float64 is a numerical diagnostic."""
    t = np.dtype(dtype).type
    if np.dtype(dtype) not in (np.dtype('float32'), np.dtype('float64')):
        raise ValueError('reference dtype must be float32 or float64')
    roughness, nov = np.meshgrid((np.arange(32, dtype=dtype) + t(.5)) / t(32),
                                (np.arange(128, dtype=dtype) + t(.5)) / t(128), indexing='ij')
    alpha = roughness * roughness
    alpha2 = alpha * alpha
    vx = np.sqrt(t(1) - nov * nov)
    total_a = np.zeros_like(nov)
    total_b = np.zeros_like(nov)
    for index in range(128):
        # Independent radical inverse via the seven live binary digits.
        radical = t(sum(((index >> bit) & 1) * 2.0 ** (-bit - 1) for bit in range(7)))
        phase = t(t(2) * t(math.pi)) * t(t(index) / t(128))
        hz = np.sqrt((t(1) - radical) / (t(1) + (alpha2 - t(1)) * radical))
        radial = np.sqrt(t(1) - hz * hz)
        # FGenericPlatformMath::Cos(float) calls cosf. NumPy's float32 ufunc
        # differs from Windows UCRT cosf at22 of the128 source phases. The
        # double calculation rounded to float32 matches cosf at every phase;
        # the platform-specific CPU contract test checks this against UCRT.
        hx = radial * t(math.cos(float(phase)))
        # The omitted V.y * H.y is +0 for these source samples.
        vh = vx * hx + nov * hz
        nl = np.maximum((t(2) * vh) * hz - nov, t(0))
        nh = np.maximum(hz, t(0))
        vh = np.maximum(vh, t(0))
        visible = nl > t(0)
        smith_v = nl * (nov * (t(1) - alpha) + alpha)
        smith_l = nov * (nl * (t(1) - alpha) + alpha)
        vis = t(.5) / (smith_v + smith_l)
        weight = nl * vis * (t(4) * vh / nh)
        fresnel = t(1) - vh
        f2 = fresnel * fresnel
        fresnel = fresnel * (f2 * f2)
        total_a += np.where(visible, weight * (t(1) - fresnel), t(0))
        total_b += np.where(visible, weight * fresnel, t(0))
    return np.stack([total_a / t(128), total_b / t(128)], axis=-1)


def unorm16_codes(values):
    """Original half-up clamp/round, deliberately not NumPy's ties-to-even rint."""
    values = np.asarray(values, dtype=np.float32)
    return np.floor(np.clip(values, np.float32(0), np.float32(1)) * np.float32(65535) + np.float32(.5)).astype(np.uint16)


def parity_report(observed, reference):
    """Report all differences in storage codes without silently allowing an LSB."""
    observed, reference = np.asarray(observed), np.asarray(reference)
    if observed.shape != reference.shape or observed.ndim != 3 or observed.shape[-1] != 2:
        raise ValueError('parity arrays must have matching HxWx2 shapes')
    delta = observed.astype(np.int32) - reference.astype(np.int32)
    mismatches = [{'x': int(x), 'y': int(y), 'channel': int(c), 'observed': int(observed[y, x, c]),
                   'reference': int(reference[y, x, c]), 'difference': int(delta[y, x, c])}
                  for y, x, c in np.argwhere(delta != 0)]
    return {'exact': len(mismatches) == 0, 'mismatched_channels': len(mismatches),
            'max_code_difference': int(np.max(np.abs(delta))), 'mismatches': mismatches}
