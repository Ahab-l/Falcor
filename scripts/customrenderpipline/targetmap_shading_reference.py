"""Offline-only RGBA16F validation; never supplies renderer inputs or claims parity.

view_rect is [x, y, width, height], matching the captured viewport. Errors use
finite pairs only (null when none); nonfinites are counted independently. Numeric
equality uses IEEE == (signed zeros equal, NaNs unequal, same infinities equal).
Half ULP uses ordered finite bit ranks: -0 and +0 are adjacent, distance one.
Validation reports self-comparison metrics; acceptance also requires finite
visible values. Comparison requires exact visible bits, never a tolerance.
"""

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re

import numpy as np


CAPTURE_SHA256 = "059eef7978d1c32039ad4bd21b5b0c59574c393996fb842b37f3a9e4a87edb2f"
EVENTS = (2793, 2962)
MAX_RAW_BYTES = 64 * 1024 * 1024
MAX_DIMENSION = 16384
IDENTITY_KEYS = ("event", "resource", "format", "width", "height", "view_rect", "subresource")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value):
    return type(value) is int


def _raw_path(directory, filename):
    _require(isinstance(filename, str) and filename, "file must be a relative path")
    windows = PureWindowsPath(filename)
    relative = Path(filename.replace("\\", "/"))
    _require(not relative.is_absolute() and not windows.drive and not windows.root
             and ".." not in relative.parts, "raw file path escapes manifest directory")
    resolved = (directory / relative).resolve(strict=True)
    _require(resolved.is_relative_to(directory) and resolved.is_file(),
             "raw file path escapes manifest directory or is not a file")
    return resolved


def _load(path):
    try:
        manifest_path = Path(path).resolve(strict=True)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _require(isinstance(manifest, dict), "manifest must be an object")
        _require(manifest.get("schema") == "crp-rdc-shading-reference-v1", "invalid schema")
        _require(manifest.get("role") == "offline_reference_only", "invalid role")
        _require(manifest.get("full_renderer_parity") is False, "full_renderer_parity must be false")
        capture = manifest.get("capture")
        _require(isinstance(capture, dict) and capture.get("sha256") == CAPTURE_SHA256,
                 "capture sha256 does not match pinned capture")
        _require(isinstance(capture.get("path"), str) and capture["path"], "missing capture path")
        checkpoints = manifest.get("checkpoints")
        _require(isinstance(checkpoints, list) and len(checkpoints) == 2,
                 "exactly E2793 and E2962 checkpoints are required")
        _require(all(isinstance(c, dict) and _integer(c.get("event")) for c in checkpoints),
                 "checkpoint event must be an integer")
        _require(sorted(c["event"] for c in checkpoints) == list(EVENTS),
                 "exactly E2793 and E2962 checkpoints are required")
        loaded, total_bytes = [], 0
        for c in sorted(checkpoints, key=lambda c: c["event"]):
            _require(c.get("resource") == "ResourceId::955", "invalid resource identity")
            _require(c.get("format") == "R16G16B16A16_FLOAT", "invalid RGBA16F format")
            width, height = c.get("width"), c.get("height")
            _require(all(_integer(n) and 0 < n <= MAX_DIMENSION for n in (width, height)),
                     "dimensions must be positive bounded integers")
            expected = width * height * 8
            total_bytes += expected
            _require(total_bytes <= MAX_RAW_BYTES, "raw reference exceeds 64 MiB bound")
            _require(_integer(c.get("byte_size")) and c["byte_size"] == expected,
                     "byte_size does not match RGBA16F shape")
            rect = c.get("view_rect")
            _require(isinstance(rect, list) and len(rect) == 4 and all(map(_integer, rect)),
                     "view_rect must contain four integers: x, y, width, height")
            x, y, view_width, view_height = rect
            _require(x >= 0 and y >= 0 and view_width > 0 and view_height > 0
                     and x + view_width <= width and y + view_height <= height,
                     "view_rect must be positive and within texture bounds")
            sub = c.get("subresource")
            _require(isinstance(sub, dict) and set(sub) == {"mip", "slice", "sample"}
                     and all(_integer(n) and n == 0 for n in sub.values()),
                     "subresource mip/slice/sample must all be integer zero")
            digest = c.get("sha256")
            _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                     "invalid raw sha256")
            raw_path = _raw_path(manifest_path.parent, c.get("file"))
            _require(raw_path.stat().st_size == expected, "raw file length mismatch")
            with raw_path.open("rb") as stream:
                raw = stream.read(expected + 1)
            _require(len(raw) == expected, "raw file length mismatch")
            _require(hashlib.sha256(raw).hexdigest() == digest, "raw file sha256 mismatch")
            identity = {key: c[key] for key in IDENTITY_KEYS}
            loaded.append((identity, np.frombuffer(raw, dtype="<f2").reshape(height, width, 4)))
        return manifest_path, loaded
    except (OSError, TypeError, UnicodeError) as exc:
        raise ValueError(f"invalid reference {path}: {exc}") from exc


def _nonfinite(values):
    mask = ~np.isfinite(values)
    return {
        "nan": int(np.count_nonzero(np.isnan(values))),
        "positive_infinity": int(np.count_nonzero(np.isposinf(values))),
        "negative_infinity": int(np.count_nonzero(np.isneginf(values))),
        "scalar_count": int(np.count_nonzero(mask)),
        "pixel_count": int(np.count_nonzero(np.any(mask, axis=1))),
    }


def _metrics(left, right):
    # uint16 views preserve signed zeros and NaN payloads; float64 avoids HDR overflow.
    left_bits, right_bits = left.view("<u2"), right.view("<u2")
    a, b = left.astype(np.float64), right.astype(np.float64)
    finite = np.isfinite(a) & np.isfinite(b)
    errors = np.abs(a[finite] - b[finite])
    ranks = []
    for bits in (left_bits, right_bits):
        bits = bits[finite].astype(np.int32)
        ranks.append(np.where(bits & 0x8000, (~bits) & 0xffff, bits | 0x8000))
    result = {
        "pixel_count": int(left.shape[0]), "scalar_count": int(left.size),
        "finite_pair_count": int(errors.size),
        "mae": float(np.mean(errors)) if errors.size else None,
        "rmse": float(np.sqrt(np.mean(errors * errors))) if errors.size else None,
        "max_abs": float(np.max(errors)) if errors.size else None,
        "max_ulp": int(np.max(np.abs(ranks[0] - ranks[1]))) if errors.size else None,
        "nonfinite": {"left": _nonfinite(a), "right": _nonfinite(b),
                      "pair_count": int(finite.size - np.count_nonzero(finite))},
    }
    for label, equal in (("numeric", a == b), ("bit", left_bits == right_bits)):
        scalar_equal = int(np.count_nonzero(equal))
        pixel_equal = int(np.count_nonzero(np.all(equal, axis=1)))
        exact_label = "numeric_equal" if label == "numeric" else "bit_exact"
        result[f"{exact_label}_scalar_count"] = scalar_equal
        result[f"{label}_mismatch_scalar_count"] = int(left.size) - scalar_equal
        result[f"{exact_label}_pixel_count"] = pixel_equal
        result[f"{label}_mismatch_pixel_count"] = int(left.shape[0]) - pixel_equal
    return result


def _checkpoint_metrics(identity, left, right):
    x, y, width, height = identity["view_rect"]
    mask = np.zeros(left.shape[:2], dtype=bool)
    mask[y:y + height, x:x + width] = True
    result = dict(identity)
    for name, selected in (("visible", mask), ("padding", ~mask)):
        a, b = left[selected], right[selected]
        result[name] = {"rgb": _metrics(a[:, :3], b[:, :3]),
                        "alpha": _metrics(a[:, 3:], b[:, 3:])}
    return result


def _report(operation, paths, pairs):
    checkpoints = [_checkpoint_metrics(identity, left, right) for identity, left, right in pairs]
    visible = [c["visible"][channel] for c in checkpoints for channel in ("rgb", "alpha")]
    exact = all(m["bit_mismatch_scalar_count"] == 0 for m in visible)
    finite = all(m["nonfinite"]["pair_count"] == 0 for m in visible)
    report = {"schema": "crp-rdc-shading-metrics-v1", "operation": operation,
              "role": "offline_reference_only", "full_renderer_parity": False,
              "accepted": exact and finite, "manifests": [str(path) for path in paths],
              "checkpoints": checkpoints}
    if operation == "compare":
        report["reference_repeatability_bit_exact_visible"] = exact
    return report


def validate_reference(path):
    """Validate manifest/raw identity; return self-metrics, including finite acceptance.

    Structural, containment, length and hash errors raise ValueError. The capture
    hash is pinned manifest provenance; this offline tool does not open the RDC.
    Small fixtures are allowed; the replay worker enforces actual capture size.
    """
    path, loaded = _load(path)
    return _report("validate", [path], [(identity, data, data) for identity, data in loaded])


def compare_references(left, right):
    """Compare two validated manifests; reject semantic mismatch before metrics."""
    left_path, left_items = _load(left)
    right_path, right_items = _load(right)
    for (left_identity, _), (right_identity, _) in zip(left_items, right_items):
        _require(left_identity == right_identity,
                 f"checkpoint semantic identity mismatch at E{left_identity['event']}")
    pairs = [(identity, a, b) for (identity, a), (_, b) in zip(left_items, right_items)]
    return _report("compare", [left_path, right_path], pairs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="operation", required=True)
    validate = subcommands.add_parser("validate")
    validate.add_argument("manifest")
    compare = subcommands.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")
    for command in (validate, compare):
        command.add_argument("--out", type=Path,
                             help="create a new JSON report outside input reference directories")
    args = parser.parse_args(argv)
    try:
        report = (validate_reference(args.manifest) if args.operation == "validate"
                  else compare_references(args.left, args.right))
        code = 0 if report["accepted"] else 1
    except ValueError as exc:
        report = {"schema": "crp-rdc-shading-metrics-v1", "operation": args.operation,
                  "accepted": False, "full_renderer_parity": False, "error": str(exc)}
        code = 2
    encoded = json.dumps(report, indent=2, allow_nan=False)
    if args.out:
        try:
            inputs = [args.manifest] if args.operation == "validate" else [args.left, args.right]
            output = args.out.resolve()
            directories = [Path(path).resolve().parent for path in inputs]
            _require(all(not output.is_relative_to(directory) for directory in directories),
                     "--out must be outside every input reference directory")
            # Exclusive creation also refuses existing files, hardlinks, and symlinks.
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
        except (OSError, ValueError) as exc:
            report.update(accepted=False, error=f"cannot write report: {exc}")
            encoded, code = json.dumps(report, indent=2, allow_nan=False), 2
    print(encoded)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
