"""Explicit CPU comparisons of decoded, typed Schema field arrays.

Arrays have shape (H, W) or (H, W, C). A boolean (H, W) mask selects
pixels; finiteness and nonzero-vector checks apply only to selected data.
Original shapes and dtypes are always checked before selection.
"""

import math
from numbers import Real

import numpy as np

from observer import compare_arrays


def _nonnegative(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite and nonnegative")
    try:
        value = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be finite and nonnegative") from error
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return value


def _validate_rule(rule):
    if not isinstance(rule, dict):
        raise ValueError("Comparison rule must be a dictionary")
    kind = rule.get("kind")
    allowed = {
        "exact": {"kind"},
        "numeric": {"kind", "atol", "rtol"},
        "angle": {"kind", "max_degrees"},
    }
    if not isinstance(kind, str) or kind not in allowed:
        raise ValueError("Unknown comparison kind; expected exact, numeric, or angle")
    if set(rule) != allowed[kind]:
        raise ValueError(f"{kind} rule requires exactly {sorted(allowed[kind])}")
    if kind == "numeric":
        return {"kind": kind, "atol": _nonnegative(rule["atol"], "atol"),
                "rtol": _nonnegative(rule["rtol"], "rtol")}
    if kind == "angle":
        degrees = _nonnegative(rule["max_degrees"], "max_degrees")
        if degrees > 180:
            raise ValueError("max_degrees must be between 0 and 180")
        return {"kind": kind, "max_degrees": degrees}
    return {"kind": kind}


def _unit_vectors(values):
    with np.errstate(over="ignore", under="ignore"):
        values = values.astype(np.float64)
        if not np.isfinite(values).all():
            raise ValueError("Angle samples must be finite in float64")
        scale = np.max(np.abs(values), axis=-1, keepdims=True)
        if np.any(scale == 0):
            raise ValueError("Angle comparison rejects zero vectors")
        scaled = values / scale
        return scaled / np.hypot.reduce(scaled, axis=-1, keepdims=True)


def _compare_field(actual, reference, rule, mask):
    if not isinstance(actual, np.ndarray) or not isinstance(reference, np.ndarray):
        raise ValueError("Comparison requires NumPy arrays")
    if actual.shape != reference.shape or actual.ndim not in (2, 3) or actual.size == 0:
        raise ValueError("Comparison requires equal, nonempty (H, W) or (H, W, C) shapes")
    if actual.dtype != reference.dtype:
        raise ValueError("Comparison requires identical dtypes")
    kind = rule["kind"]
    if kind == "exact":
        if actual.dtype.kind not in "biu":
            raise ValueError("Exact comparison requires integer or boolean arrays")
    elif actual.dtype.kind != "f":
        raise ValueError(f"{kind} comparison requires floating-point arrays")
    if kind == "angle" and (actual.ndim != 3 or actual.shape[-1] != 3):
        raise ValueError("Angle comparison requires pixel float3 arrays shaped (H, W, 3)")
    if mask is not None:
        if mask.shape != actual.shape[:2]:
            raise ValueError("Coverage mask must match pixel dimensions (H, W)")
        actual, reference = actual[mask], reference[mask]

    if kind == "exact":
        # Preserve original integer precision, including IDs beyond 2**53.
        failed = int(np.count_nonzero(actual != reference))
        return {"kind": kind, "passed": failed == 0,
                "sample_count": int(actual.size), "failed_samples": failed,
                "sample_unit": "components"}

    if not np.isfinite(actual).all() or not np.isfinite(reference).all():
        raise ValueError("Comparison requires finite selected samples")
    if kind == "numeric":
        report = compare_arrays(actual, reference, atol=rule["atol"], rtol=rule["rtol"])
        return {"kind": kind, "sample_unit": "components", **report}

    actual, reference = _unit_vectors(actual), _unit_vectors(reference)
    # atan2 retains tiny angles for which acos(dot) would round to zero.
    with np.errstate(under="ignore"):
        cross_length = np.hypot.reduce(np.cross(actual, reference), axis=-1)
        dot = np.sum(actual * reference, axis=-1)
        angles = np.rad2deg(np.arctan2(cross_length, dot))
    failed = int(np.count_nonzero(angles > rule["max_degrees"]))
    return {"kind": kind, "passed": failed == 0,
            "sample_count": int(angles.size), "failed_samples": failed,
            "sample_unit": "vectors", "max_degrees": rule["max_degrees"],
            "max_angle_degrees": float(angles.max()),
            "mean_angle_degrees": float(angles.mean())}


def compare_fields(
    actual: dict[str, np.ndarray],
    reference: dict[str, np.ndarray],
    rules: dict[str, dict],
    mask=None,
) -> dict:
    """Compare selected fields using exact, numeric, or angle rules.

    ``rules`` must cover exactly the nonempty field set in ``actual``.
    ``reference`` may contain additional arrays, such as an NPZ coverage mask.
    Both arrays for a field must have exactly the same shape and dtype.

    Exact rules require integer/bool arrays. Numeric rules require float arrays
    and explicit finite, nonnegative ``atol`` and ``rtol``. Their sample counts
    and failed counts refer to scalar components, including vector channels.
    Numeric statistics come from :func:`observer.compare_arrays`; with a mask,
    ``worst_index`` indexes the selected array (pixels, optional channels).

    Angle rules require float3 arrays and explicit ``max_degrees`` in [0, 180].
    Their counts refer to pixel vectors. Selected vectors must be finite and
    nonzero; scale-first normalization makes their magnitude irrelevant.

    An optional NumPy boolean (H, W) mask must select at least one pixel.
    Only selected samples undergo finite/nonzero checks. Invalid inputs raise
    ValueError; valid comparisons return a JSON-serializable pass/fail report.
    No field names imply semantics or conversions, and no inputs are modified.
    """
    if not all(isinstance(value, dict) for value in (actual, reference, rules)):
        raise ValueError("actual, reference, and rules must be dictionaries")
    if not actual:
        raise ValueError("Comparison requires a nonempty selected field set")
    if any(not isinstance(name, str) or not name for name in actual):
        raise ValueError("Selected field names must be nonempty strings")
    if set(rules) != set(actual):
        raise ValueError("Rules must cover exactly the selected actual fields")
    if mask is not None:
        if not isinstance(mask, np.ndarray) or mask.dtype.kind != "b" or mask.ndim != 2:
            raise ValueError("Coverage mask must be a boolean NumPy array shaped (H, W)")
        if not np.any(mask):
            raise ValueError("Coverage mask must select at least one pixel")

    fields = {}
    for name, samples in actual.items():
        try:
            if name not in reference:
                raise ValueError("Missing reference field")
            rule = _validate_rule(rules[name])
            fields[name] = _compare_field(samples, reference[name], rule, mask)
        except ValueError as error:
            raise ValueError(f"Field {name!r}: {error}") from error
    return {"passed": all(report["passed"] for report in fields.values()), "fields": fields}
