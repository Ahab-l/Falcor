"""Independent NumPy oracle for UE's default, scene-wide atmosphere LUTs.

This module evaluates the mathematics in SkyAtmosphere.usf and
SkyAtmosphereCommon.ush; it neither extracts/executes shader text nor reads a
capture. It is an offline validator, never an input to the renderer. Distances
are kilometers and the parameter names are UE's Atmosphere uniform fields.

Active defaults: a 0.3 sample offset, fixed *floating-point* sample count,
isotropic phase, two vertical multi-scattering rays, planet shadow with a
0.001 km center offset, Lambertian ground, rectangular MultiScatAs1 integration,
and the finite sum 1+r+r^2+r^3+r^4. No view, exposure, or light state is needed.

Numerical comparison strategy:
* float64 is the independent mathematical baseline; dtype=float32 diagnoses
  kilometer-radius cancellation, especially the first transmittance LUT row.
  float32 is not a promise of bit-exact GPU math (FMA/exp/sqrt can differ).
* Output arrays are values before render-target conversion. Quantize to the
  actual target format outside this module. Feed that storage-decoded, still
  sqrt-encoded transmittance texture to multi_scattering_reference. Do not
  square it first, since UE filters encoded values and only then squares.
* The default sampler is ideal linear clamp. sampler_fraction_bits=8 optionally
  rounds each bilinear fraction to the nearest 1/256 with ties to even. This
  models D3D's minimum fractional precision, not every vendor's exact sampler.
  Keep the ideal baseline and this explicitly selected diagnostic separate.
* Establish storage ULP and FP32/sampler envelopes separately from algorithm
  errors. Do not derive tolerance from a renderer capture or silently enlarge
  it to absorb a mismatch. Analytic tests use float64 tolerances near 1e-13.
"""

import math

import numpy as np


_VECTOR_FIELDS = (
    "GroundAlbedo", "RayleighScattering", "MieScattering", "MieAbsorption",
    "MieExtinction", "AbsorptionExtinction",
)
_SCALAR_FIELDS = (
    "BottomRadiusKm", "TopRadiusKm", "MultiScatteringFactor",
    "RayleighDensityExpScale", "MiePhaseG", "MieDensityExpScale",
    "AbsorptionDensity0LayerWidth", "AbsorptionDensity0LinearTerm",
    "AbsorptionDensity0ConstantTerm", "AbsorptionDensity1LinearTerm",
    "AbsorptionDensity1ConstantTerm",
)


def _float_type(dtype):
    dtype = np.dtype(dtype)
    if dtype not in (np.dtype(np.float32), np.dtype(np.float64)):
        raise ValueError("dtype must be float32 or float64")
    return dtype.type


def _prepare(parameters, size, sample_count, dtype):
    scalar = _float_type(dtype)
    if len(size) != 2 or any(not isinstance(v, (int, np.integer)) or v <= 0 for v in size):
        raise ValueError("size must be positive integer (width, height)")
    if not np.isfinite(sample_count) or sample_count <= 0:
        raise ValueError("sample_count must be finite and positive")
    count = scalar(sample_count)
    if not np.isfinite(count) or count <= 0:
        raise ValueError("sample_count must be representable in dtype")
    values = {key: scalar(parameters[key]) for key in _SCALAR_FIELDS}
    for key in _VECTOR_FIELDS:
        values[key] = np.asarray(parameters[key], dtype=scalar)
        if values[key].shape != (3,):
            raise ValueError(f"{key} must contain three channels")
    if any(not np.all(np.isfinite(value)) for value in values.values()):
        raise ValueError("atmosphere parameters must be finite")
    if not 0 < values["BottomRadiusKm"] < values["TopRadiusKm"]:
        raise ValueError("radii must satisfy 0 < BottomRadiusKm < TopRadiusKm")
    return values, count, scalar


def _pixel_uv(size, scalar):
    width, height = size
    x = (np.arange(width, dtype=scalar) + scalar(0.5)) * (scalar(1) / scalar(width))
    y = (np.arange(height, dtype=scalar) + scalar(0.5)) * (scalar(1) / scalar(height))
    return np.stack(np.broadcast_arrays(x[None, :], y[:, None]), axis=-1)


def _dot(a, b):
    return np.sum(a * b, axis=-1)


def _sphere_intersections(origin, direction, radius, center=0):
    """Quadratic near/far roots, including negative roots, as in Common.ush."""
    local = origin - center
    a = _dot(direction, direction)
    b = 2 * _dot(direction, local)
    c = _dot(local, local) - radius * radius
    discriminant = b * b - 4 * a * c
    root = np.sqrt(np.maximum(discriminant, 0))
    near = np.where(discriminant >= 0, (-b - root) / (2 * a), -1)
    far = np.where(discriminant >= 0, (-b + root) / (2 * a), -1)
    return near, far


def _path_end(origin, direction, parameters):
    bottom = parameters["BottomRadiusKm"]
    bn, bf = _sphere_intersections(origin, direction, bottom)
    tn, tf = _sphere_intersections(origin, direction, parameters["TopRadiusKm"])
    no_bottom = (bn < 0) & (bf < 0)
    no_top = (tn < 0) & (tf < 0)
    active = (_dot(origin, origin) > bottom * bottom) & ~no_top
    bottom_distance = np.where(no_bottom, 0, np.maximum(0, np.minimum(bn, bf)))
    distance = np.where(no_bottom, np.maximum(tn, tf), bottom_distance)
    distance = np.where(active, np.minimum(distance, 9000000), 0)
    ground = active & (distance == bottom_distance)
    return distance, ground


def _medium(position, parameters):
    altitude = np.maximum(np.sqrt(_dot(position, position)) - parameters["BottomRadiusKm"], 0)
    mie = np.exp(parameters["MieDensityExpScale"] * altitude)[..., None]
    rayleigh = np.exp(parameters["RayleighDensityExpScale"] * altitude)[..., None]
    ozone = np.where(
        altitude < parameters["AbsorptionDensity0LayerWidth"],
        parameters["AbsorptionDensity0LinearTerm"] * altitude + parameters["AbsorptionDensity0ConstantTerm"],
        parameters["AbsorptionDensity1LinearTerm"] * altitude + parameters["AbsorptionDensity1ConstantTerm"],
    )
    ozone = np.clip(ozone, 0, 1)[..., None]
    ray_scattering = rayleigh * parameters["RayleighScattering"]
    scattering = mie * parameters["MieScattering"] + ray_scattering
    extinction = mie * parameters["MieExtinction"] + ray_scattering + ozone * parameters["AbsorptionExtinction"]
    return scattering, extinction


def _transmittance_coordinates(radius, cosine, parameters):
    bottom, top = parameters["BottomRadiusKm"], parameters["TopRadiusKm"]
    horizon = np.sqrt(np.maximum(0, top * top - bottom * bottom))
    rho = np.sqrt(np.maximum(0, radius * radius - bottom * bottom))
    discriminant = radius * radius * (cosine * cosine - 1) + top * top
    distance = np.maximum(0, -radius * cosine + np.sqrt(discriminant))
    nearest = top - radius
    return np.stack(((distance - nearest) / (rho + horizon - nearest), rho / horizon), axis=-1)


def sample_encoded_transmittance(texture, uv, *, dtype=np.float64, sampler_fraction_bits=None):
    """Sample RGB sqrt-encoded storage values with linear clamp, then square.

    uv has shape (..., 2); the returned linear transmittance has shape (..., 3).
    Storage conversion (UNORM/half/R11G11B10) belongs to the caller.
    """
    scalar = _float_type(dtype)
    texture = np.asarray(texture, dtype=scalar)
    uv = np.asarray(uv, dtype=scalar)
    if texture.ndim != 3 or texture.shape[-1] != 3 or min(texture.shape[:2]) <= 0:
        raise ValueError("transmittance texture must have shape (height, width, 3)")
    if uv.ndim < 1 or uv.shape[-1] != 2:
        raise ValueError("uv must have shape (..., 2)")
    if not np.all(np.isfinite(texture)) or not np.all(np.isfinite(uv)):
        raise ValueError("texture values and uv must be finite")
    if sampler_fraction_bits is not None and (
        not isinstance(sampler_fraction_bits, (int, np.integer)) or not 0 <= sampler_fraction_bits <= 23
    ):
        raise ValueError("sampler_fraction_bits must be None or an integer from 0 through 23")
    height, width = texture.shape[:2]
    coordinates = uv * np.array([width, height], dtype=scalar) - scalar(0.5)
    coordinates = np.clip(coordinates, 0, np.array([width - 1, height - 1], dtype=scalar))
    lower = np.floor(coordinates).astype(np.int64)
    fraction = coordinates - lower.astype(scalar)
    if sampler_fraction_bits is not None:
        precision = scalar(2**sampler_fraction_bits)
        fraction = np.rint(fraction * precision) / precision
    x0, y0 = lower[..., 0], lower[..., 1]
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = fraction[..., 0, None], fraction[..., 1, None]
    row0 = texture[y0, x0] * (1 - fx) + texture[y0, x1] * fx
    row1 = texture[y1, x0] * (1 - fx) + texture[y1, x1] * fx
    encoded = row0 * (1 - fy) + row1 * fy
    return encoded * encoded


def transmittance_reference(parameters, size=(256, 64), sample_count=10.0, *, dtype=np.float64):
    """Return (height, width, 3) sqrt-encoded transmittance before storage conversion."""
    parameters, count, scalar = _prepare(parameters, size, sample_count, dtype)
    uv = _pixel_uv(size, scalar)
    bottom, top = parameters["BottomRadiusKm"], parameters["TopRadiusKm"]
    horizon = np.sqrt(top * top - bottom * bottom)
    rho = horizon * uv[..., 1]
    radius = np.sqrt(rho * rho + bottom * bottom)
    nearest = top - radius
    distance = nearest + uv[..., 0] * (rho + horizon - nearest)
    cosine = (horizon * horizon - rho * rho - distance * distance) / (2 * radius * distance)
    cosine = np.clip(np.where(distance == 0, 1, cosine), -1, 1)
    origin = np.zeros(radius.shape + (3,), dtype=scalar)
    origin[..., 2] = radius
    direction = np.zeros_like(origin)
    direction[..., 1] = np.sqrt(1 - cosine * cosine)
    direction[..., 2] = cosine
    end, _ = _path_end(origin, direction, parameters)
    step = end / count
    optical_depth = np.zeros_like(origin)
    for index in range(math.ceil(float(count))):
        distance = end * (scalar(index) + scalar(0.3)) / count
        _, extinction = _medium(origin + distance[..., None] * direction, parameters)
        optical_depth += extinction * step[..., None]
    return np.sqrt(np.exp(-optical_depth))


def _integrate_vertical(origin, direction, light, parameters, count, texture, scalar, sampler_fraction_bits):
    end, hits_ground = _path_end(origin, direction, parameters)
    step = end / count
    throughput = np.ones_like(origin)
    luminance = np.zeros_like(origin)
    scattering_ratio = np.zeros_like(origin)
    phase = scalar(1) / (scalar(4) * scalar(np.pi))

    def light_transmittance(position):
        radius = np.sqrt(_dot(position, position))
        up = position / radius[..., None]
        cosine = _dot(light, up)
        uv = _transmittance_coordinates(radius, cosine, parameters)
        transmittance = sample_encoded_transmittance(
            texture, uv, dtype=scalar, sampler_fraction_bits=sampler_fraction_bits
        )
        return transmittance, up, cosine

    for index in range(math.ceil(float(count))):
        distance = end * (scalar(index) + scalar(0.3)) / count
        position = origin + distance[..., None] * direction
        scattering, extinction = _medium(position, parameters)
        segment_transmittance = np.exp(-extinction * step[..., None])
        to_light, up, _ = light_transmittance(position)
        near, far = _sphere_intersections(
            position, light, parameters["BottomRadiusKm"], scalar(0.001) * up
        )
        unshadowed = (near < 0) & (far < 0)
        source = unshadowed[..., None] * to_light * (scattering * phase)
        scattering_ratio += throughput * scattering * step[..., None]
        segment_luminance = (source - source * segment_transmittance) / np.maximum(extinction, scalar(1e-9))
        luminance += throughput * segment_luminance
        throughput *= segment_transmittance

    ground_position = origin + end[..., None] * direction
    to_light, _, cosine = light_transmittance(ground_position)
    bounce = to_light * throughput * np.clip(cosine, 0, 1)[..., None] * parameters["GroundAlbedo"] / scalar(np.pi)
    luminance += np.where(hits_ground[..., None], bounce, 0)
    return luminance, scattering_ratio


def multi_scattering_reference(
    parameters, transmittance, size=(32, 32), sample_count=15.0, *, dtype=np.float64, sampler_fraction_bits=None
):
    """Return linear RGB multi-scattering LUT values before storage conversion.

    transmittance is an H,W,3 array after storage decoding, still sqrt-encoded.
    The two LUTs may have different dimensions. MiePhaseG and MieAbsorption are
    accepted UE fields but do not affect these active isotropic LUT paths;
    extinction is taken directly from MieExtinction.
    """
    parameters, count, scalar = _prepare(parameters, size, sample_count, dtype)
    uv = _pixel_uv(size, scalar)
    cosine = uv[..., 0] * 2 - 1
    light = np.zeros(cosine.shape + (3,), dtype=scalar)
    light[..., 1] = np.sqrt(np.clip(1 - cosine * cosine, 0, 1))
    light[..., 2] = cosine
    origin = np.zeros_like(light)
    origin[..., 2] = parameters["BottomRadiusKm"] + uv[..., 1] * (
        parameters["TopRadiusKm"] - parameters["BottomRadiusKm"]
    )
    direction = np.zeros_like(origin)
    direction[..., 2] = 1
    up_luminance, up_ratio = _integrate_vertical(
        origin, direction, light, parameters, count, transmittance, scalar, sampler_fraction_bits
    )
    down_luminance, down_ratio = _integrate_vertical(
        origin, -direction, light, parameters, count, transmittance, scalar, sampler_fraction_bits
    )
    solid_angle = scalar(4) * scalar(np.pi)
    luminance = ((solid_angle / 2) * (up_luminance + down_luminance)) * (scalar(1) / solid_angle)
    ratio = (up_ratio + down_ratio) * scalar(0.5)
    squared = ratio * ratio
    series = 1 + ratio + squared + ratio * squared + squared * squared
    return luminance * series * parameters["MultiScatteringFactor"]
