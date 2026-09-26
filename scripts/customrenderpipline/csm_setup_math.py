"""Independent CPU oracle for UEReferenceShadowSetupPass's bounded directional CSM.

Ports DirectionalLightComponent.cpp (ComputeAccumulatedScale,
GetShadowSplitBoundsDepthRange, GetShadowSplitBounds, initializer and distance
fade), ShadowSetup.cpp (SetupWholeSceneProjection), ShadowRendering.h
(FShadowProjectionMatrix), and ShadowRendering.cpp (bias/transition size).
Defaults are source settings, not measurements of capture runtime state.
Only native perspective cameras and 1-4 dynamic shadow cascades are supported.
Input view/projection matrices use Falcor column vectors and meter positions;
the source sphere, snap and bias calculations use centimeters.
"""
import math

import numpy as np


DEFAULTS = dict(distance_cm=20000, cascades=4, distribution_exponent=3,
                transition_fraction=0.1, fade_fraction=0.1, depth_bias=10,
                slope_scale=3, max_slope=1, receiver_bias=0.9,
                component_bias=0.5, component_slope_bias=0.5,
                bias_distribution=1, sharpen=0, resolution=2048, border=4)


def _settings(shadow):
    if not isinstance(shadow, dict) or set(shadow) - (set(DEFAULTS) | {"direction"}):
        raise ValueError("unsupported shadow property")
    result = {**DEFAULTS, **shadow}
    for name in DEFAULTS:
        value = result[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(name + " must be a finite scalar")
        if value < 0 or value > np.finfo(np.float32).max:
            raise ValueError(name + " is outside the supported range")
    for name, low, high in [("cascades", 1, 4), ("resolution", 8, 16384), ("border", 0, 8191)]:
        if not isinstance(result[name], int) or not low <= result[name] <= high:
            raise ValueError(name + " must be a supported integer")
    for name in ("transition_fraction", "fade_fraction", "receiver_bias", "component_bias",
                 "component_slope_bias", "bias_distribution"):
        if result[name] > 1:
            raise ValueError(name + " must be in [0,1]")
    if not 1 <= result["distribution_exponent"] <= 16 or not 0 < result["distance_cm"] <= 1e8:
        raise ValueError("unsupported distribution or shadow distance")
    if result["resolution"] - 2 * result["border"] < 8:
        raise ValueError("shadow inner resolution must be at least eight texels")
    direction = np.asarray(result.get("direction", []), dtype=float)
    if direction.shape != (3,) or not np.isfinite(direction).all() or np.linalg.norm(direction) < 1e-8:
        raise ValueError("direction must be a finite nonzero surface-to-light vector")
    result["direction"] = direction / np.linalg.norm(direction)
    return result


def split_distances(near_cm, distance_cm, count, exponent):
    """UE geometric widths, rather than the common uniform/logarithmic blend."""
    weights = exponent ** np.arange(count, dtype=float)
    scales = np.r_[0, np.cumsum(weights)] / np.sum(weights)
    return near_cm + scales * (distance_cm - near_cm)


def snap_shadow_center(scaled_center, inner_resolution):
    """FMath::Fmod has the dividend's sign; floor/remainder changes negatives."""
    result = np.array(scaled_center, dtype=float, copy=True)
    result[:2] -= np.fmod(result[:2], 8 / inner_resolution)
    return result


def _light_axes(surface_to_light):
    # Falcor = (UE.Y, UE.Z, -UE.X). GetDirection() is light propagation.
    direction = -np.array([-surface_to_light[2], surface_to_light[0], surface_to_light[1]])
    yaw = math.atan2(direction[1], direction[0])
    pitch = math.atan2(direction[2], math.hypot(direction[0], direction[1]))
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    # FInverseRotationMatrix(direction.Rotation()) * FaceMatrix, expressed as
    # three row-vector covectors for column-vector input positions.
    ue = np.array([[cy * sp, sy * sp, -cp], [-sy, cy, 0], [cy * cp, sy * cp, sp]])
    return ue[:, [1, 2, 0]] * [1, 1, -1]


def setup_cascades(*, view_matrix, projection_no_jitter, near_m, shadow):
    settings = _settings(shadow)
    view, projection = np.asarray(view_matrix, dtype=float), np.asarray(projection_no_jitter, dtype=float)
    if (view.shape != (4, 4) or projection.shape != (4, 4) or
            not np.isfinite(view).all() or not np.isfinite(projection).all() or
            not np.allclose(view[3], [0, 0, 0, 1], atol=1e-6) or
            not np.allclose(view[:3, :3] @ view[:3, :3].T, np.eye(3), atol=1e-5)):
        raise ValueError("camera requires a finite rigid native view")
    if (projection[0, 0] <= 0 or projection[1, 1] <= 0 or
            not np.allclose(projection[3], [0, 0, -1, 0], atol=1e-6) or
            any(abs(projection[i, j]) > 1e-6 for i, j in [(0, 1), (1, 0), (0, 3), (1, 3), (2, 0), (2, 1)])):
        raise ValueError("camera requires a supported perspective projection without jitter")
    if not math.isfinite(near_m) or not 0 < near_m * 100 < settings["distance_cm"]:
        raise ValueError("near plane must be positive and precede shadow distance")
    right, up, forward = view[0, :3], view[1, :3], -view[2, :3]
    position_m = -view[:3, :3].T @ view[:3, 3]
    origin = position_m * 100
    tan_x, tan_y = 1 / projection[0, 0], 1 / projection[1, 1]
    asym_x, asym_y = -projection[0, 2], -projection[1, 2]
    axes = _light_axes(settings["direction"])
    inner_resolution = settings["resolution"] - 2 * settings["border"]
    splits = split_distances(near_m * 100, settings["distance_cm"], settings["cascades"], settings["distribution_exponent"])
    parameters = np.zeros((36, 4), dtype="<f4")
    parameters[0] = [*position_m, settings["cascades"]]
    parameters[1] = [*forward, settings["distance_cm"] / 100]
    parameters[2] = [settings["resolution"], settings["border"], settings["sharpen"], 0]
    fade_length = settings["distance_cm"] * settings["fade_fraction"]
    parameters[3] = [(settings["distance_cm"] - fade_length) / 100, 100 / max(fade_length, 1e-4), 0, 0]
    cascades = []
    for index in range(settings["cascades"]):
        near, nominal_far = splits[index:index + 2]
        extension = (nominal_far - near) * settings["transition_fraction"]
        far = nominal_far + extension if index + 1 < settings["cascades"] else nominal_far
        fade_start = nominal_far if index + 1 < settings["cascades"] else nominal_far - extension
        corners = np.array([origin + forward * depth + right * depth * tan_x * (x - asym_x) +
                            up * depth * tan_y * (y - asym_y)
                            for depth in (near, far) for x, y in [(1, 1), (1, -1), (-1, 1), (-1, -1)]])
        diagonal_a = (tan_x * far) ** 2 + (tan_y * far) ** 2
        diagonal_b = (tan_x * near) ** 2 + (tan_y * near) ** 2
        optimal_offset = (diagonal_b - diagonal_a) / (2 * (far - near)) + (far - near) * 0.5
        center = origin + forward * np.clip(far - optimal_offset, near, far)
        raw_radius = max(np.max(np.linalg.norm(corners - center, axis=1)), 1)
        radius = math.ceil(raw_radius)
        min_z, max_z = -max(radius, 5000), max(radius, 5000)
        depth_range = max_z - min_z
        scale = np.array([1 / radius, 1 / radius, 1])
        q = snap_shadow_center((axes @ center) * scale, inner_resolution)
        snapped_center = axes.T @ (q / scale)
        matrix = np.eye(4)
        matrix[0, :3], matrix[0, 3] = axes[0] * (100 / radius), -q[0]
        matrix[1, :3], matrix[1, 3] = axes[1] * (100 / radius), -q[1]
        matrix[2, :3], matrix[2, 3] = axes[2] * (-100 / depth_range), (max_z + q[2]) / depth_range
        base_bias = settings["depth_bias"] / depth_range
        texel_scale = raw_radius / inner_resolution
        depth_bias = base_bias * (1 + (texel_scale - 1) * settings["bias_distribution"]) * settings["component_bias"]
        transition = max(base_bias * texel_scale * settings["component_bias"], 1e-5)
        bias = np.array([depth_bias, depth_bias * settings["slope_scale"] * settings["component_slope_bias"],
                         settings["max_slope"], 1 / transition])
        split = np.array([near / 100, far / 100, fade_start / 100, 100 / max(far - fade_start, 1e-4)])
        offset = 4 + index * 8
        parameters[offset:offset + 4] = matrix
        parameters[offset + 4], parameters[offset + 5] = split, bias
        parameters[offset + 6] = [*settings["direction"], settings["receiver_bias"]]
        parameters[offset + 7] = [raw_radius, radius, min_z, max_z]
        cascades.append(dict(matrix=matrix, split=split, bias=bias, corners_cm=corners, center_cm=center,
                             snapped_center_cm=snapped_center, axes=axes,
                             raw_radius_cm=raw_radius, radius_cm=radius))
    if not np.isfinite(parameters).all():
        raise ValueError("shadow setup produced nonfinite parameters")
    return dict(parameters=parameters, cascades=cascades)
