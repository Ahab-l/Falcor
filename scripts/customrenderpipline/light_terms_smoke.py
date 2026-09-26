"""Bounded acceptance for the real UE legacy LightTerms shader functions.

Inside headless Mogwai this executes a separate falcor.Device GPU compute probe.
Ordinary Python defaults to an oracle-only self-check and never imports falcor.
Use --oracle-only explicitly for offline checks; --gpu opts into device execution.
GPU evidence: build/light-terms-evidence/{kernel.cs.slang,raw.npz,result.json}.
This does not validate BRDF, sqrtFast, shadow production, or the LightingPass.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

EMBEDDED = "m" in globals()
ROOT = Path.cwd().resolve() if EMBEDDED else Path(__file__).resolve().parents[2]
BIN = ROOT / "build/windows-vs2022/bin/Release"
if EMBEDDED:
    sys.path.insert(0, str(BIN / "python"))
    sys.path.insert(0, str(ROOT / "build/m0-evidence/python"))
import numpy as np

SEED = 26550909
INPUT_ROWS = 9
OUTPUT_ROWS = 3
RTOL = 4e-6
ATOL = 1e-6

KERNEL = r"""
StructuredBuffer<float4> gInput;
RWStructuredBuffer<float4> gResult;
[numthreads(1,1,1)] void main(uint3 tid : SV_DispatchThreadID)
{
    const uint i = tid.x;
    const uint base = i * 9;
    const float4 positionType = gInput[base];
    const float4 lightRadius = gInput[base + 1];
    const float4 directionExponent = gInput[base + 2];
    const float4 coneInverseDepth = gInput[base + 3];
    const float4 sampledMask = gInput[base + 4];
    const float4 aoBitsContactStatic = gInput[base + 5];
    const float4 fadeFlags = gInput[base + 6];
    const uint lightType = uint(positionType.w);
    UELocalLightTerms localTerms;
    const bool localValid = ueTryGetLocalLightTerms(lightType, positionType.xyz,
        lightRadius.xyz, lightRadius.w, directionExponent.xyz, coneInverseDepth.xy,
        directionExponent.w, coneInverseDepth.z != 0.0, localTerms);
    UEShadowTerms shadow;
    const bool shadowValid = ueTryGetShadowTerms(lightType, coneInverseDepth.w,
        gInput[base + 7], gInput[base + 8], fadeFlags.xy, uint(aoBitsContactStatic.y),
        uint(fadeFlags.z), sampledMask, aoBitsContactStatic.x, aoBitsContactStatic.z,
        aoBitsContactStatic.w != 0.0, shadow);
    gResult[i * 3] = float4(localTerms.toLight, localTerms.mask);
    gResult[i * 3 + 1] = float4(shadow.surfaceShadow, shadow.transmissionShadow,
        shadow.transmittanceOrOpticalThickness, float(localValid));
    gResult[i * 3 + 2] = float4(float(shadowValid), 0.0, 0.0, 0.0);
}
"""


def case(name, **overrides):
    value = dict(name=name, type=1, position=[0, 0, 0], light_position=[0, 0, 5],
                 inv_radius=0.1, direction=[0, 0, 1], spot_angles=[0.5, 4.0],
                 falloff_exponent=0.0, inverse_squared=True, scene_depth_cm=0.0,
                 shadow_mask=[1, 1, 1, 1], ao=1.0, shadowed_bits=0,
                 contact_shadow_length=0.0, allow_static_lighting=False,
                 distance_fade_mad=[0.0005, -9.0], per_object_flags=0,
                 precomputed_shadow_factors=[1, 1, 1, 1], shadow_map_channel_mask=[0, 0, 0, 1])
    value.update(overrides)
    return value


def make_cases():
    cases = []
    for inverse in (False, True):
        for distance in (1, 5, 9, 10, 11, 20):
            cases.append(case(f"point_inverse_{int(inverse)}_distance_{distance}",
                              inverse_squared=inverse, falloff_exponent=0 if inverse else 2,
                              light_position=[0, 0, distance]))
        for cosine in (-1, 0.25, 0.5, 0.625, 0.75, 1):
            cases.append(case(f"spot_inverse_{int(inverse)}_cosine_{cosine}", type=2,
                              direction=[float(np.sqrt(1 - cosine * cosine)), 0, cosine],
                              inverse_squared=inverse, falloff_exponent=0 if inverse else 2))
    cases.append(case("translated_point_3_4_0", position=[1024, -512, 256], light_position=[1027, -508, 256]))
    for kind in (0, 1, 2):
        for bits in (0, 1, 3):
            for raw in (0.0, 0.5, 1.0):
                cases.append(case(f"raw_type_{kind}_bits_{bits}_mask_{raw}", type=kind,
                                  shadowed_bits=bits, shadow_mask=[raw] * 4, ao=0.3))
        for bits in (0, 3):
            cases.append(case(f"ao_type_{kind}_bits_{bits}", type=kind, ao=0.125,
                              shadowed_bits=bits, shadow_mask=[0.5, 0.25, 0.75, 1.0]))
    for bits in (1, 3):
        for depth in (0, 17000, 18000, 18500, 19000, 19500, 20000, 21000):
            cases.append(case(f"directional_bits_{bits}_depth_{depth}", type=0, scene_depth_cm=depth,
                              shadowed_bits=bits, ao=0.2, shadow_mask=[0.5, 0.25, 0.75, 0.8]))
    for kind in (0, 1, 2):
        for bits in (0, 3):
            for length in (-1.0, 0.25):
                cases.append(case(f"reject_contact_type_{kind}_bits_{bits}_length_{length}",
                                  type=kind, shadowed_bits=bits, contact_shadow_length=length))
            cases.append(case(f"reject_static_type_{kind}_bits_{bits}", type=kind,
                              shadowed_bits=bits, allow_static_lighting=True))
    for kind in (3, 31):
        for bits in (0, 3):
            cases.append(case(f"reject_unknown_type_{kind}_bits_{bits}", type=kind, shadowed_bits=bits))
    for ignored in (False, True):
        cases.append(case(f"static_off_ignored_fields_{int(ignored)}", type=0, shadowed_bits=3,
                          scene_depth_cm=19000, ao=0.15, shadow_mask=[0.25, 0.5, 0.75, 1],
                          precomputed_shadow_factors=[0, 0.2, 0.4, 0.6] if ignored else [1] * 4,
                          shadow_map_channel_mask=[1, 0, 0, 0] if ignored else [0, 0, 0, 1],
                          per_object_flags=255 if ignored else 0))
    rng = np.random.default_rng(SEED)
    for index in range(32):
        position = rng.uniform(-2048, 2048, 3)
        displacement = rng.normal(size=3)
        displacement *= rng.uniform(1, 500) / np.linalg.norm(displacement)
        direction = rng.normal(size=3)
        direction /= np.linalg.norm(direction)
        outer = float(rng.uniform(0.1, 0.7))
        inner = float(rng.uniform(outer + 0.05, 0.98))
        inverse = bool(index % 2)
        cases.append(case(f"random_seed_{SEED}_{index:02d}", type=index % 3,
                          position=position.tolist(), light_position=(position + displacement).tolist(),
                          direction=direction.tolist(), inv_radius=float(1 / rng.uniform(20, 600)),
                          spot_angles=[outer, 1 / (inner - outer)], inverse_squared=inverse,
                          falloff_exponent=0 if inverse else float(rng.choice([0.5, 1, 2, 4])),
                          shadow_mask=rng.uniform(0, 1, 4).tolist(), ao=float(rng.uniform(0, 1)),
                          shadowed_bits=[0, 1, 3][index % 3], scene_depth_cm=float(rng.uniform(17000, 21000))))
    return cases


def pack_inputs(cases):
    rows = []
    for c in cases:
        rows.append([list(c["position"]) + [c["type"]], list(c["light_position"]) + [c["inv_radius"]],
                     list(c["direction"]) + [c["falloff_exponent"]],
                     list(c["spot_angles"]) + [c["inverse_squared"], c["scene_depth_cm"]],
                     c["shadow_mask"], [c["ao"], c["shadowed_bits"], c["contact_shadow_length"], c["allow_static_lighting"]],
                     list(c["distance_fade_mad"]) + [c["per_object_flags"], 0],
                     c["precomputed_shadow_factors"], c["shadow_map_channel_mask"]])
    return np.asarray(rows, dtype=np.float32)


def oracle(inputs):
    """Independent NumPy equations from UE, without reading/translating Slang.

    Inputs are the exact uploaded float32 values. Store toLight at its explicit
    float32 subtraction boundary, then use float64 reference math; comparisons
    allow GPU rsqrt/pow/FMA rounding, including cancellation in the depth fade.
    """
    result = np.zeros((len(inputs), OUTPUT_ROWS, 4), dtype=np.float64)
    for index, packed in enumerate(inputs):
        p = packed.astype(np.float64)
        kind = int(p[0, 3])
        local_valid = kind in (1, 2)
        shadow_valid = kind in (0, 1, 2) and p[5, 2] == 0 and p[5, 3] == 0
        result[index, 1, 3] = int(local_valid)
        result[index, 2, 0] = int(shadow_valid)
        if local_valid:
            delta = np.subtract(packed[1, :3], packed[0, :3], dtype=np.float32).astype(np.float64)
            distance_squared = np.dot(delta, delta)
            if distance_squared <= 0:
                raise ValueError("oracle fixtures must not contain a zero-distance local light")
            if p[3, 2] != 0:
                mask = np.clip(1 - (distance_squared * p[1, 3] ** 2) ** 2, 0, 1) ** 2
            else:
                normalized_delta = delta * p[1, 3]
                mask = (1 - np.clip(np.dot(normalized_delta, normalized_delta), 0, 1)) ** p[2, 3]
            if kind == 2:
                cone_cosine = np.dot(delta / np.sqrt(distance_squared), p[2, :3])
                mask *= np.clip((cone_cosine - p[3, 0]) * p[3, 1], 0, 1) ** 2
            result[index, 0] = [*delta, mask]
        if shadow_valid:
            shadow = np.array([p[5, 0], 1.0, 1.0])
            if int(p[5, 1]) != 0:
                a = np.square(p[4])
                if kind in (1, 2):
                    shadow = np.array([a[2], a[3], a[3]])
                else:
                    fade = np.clip(p[3, 3] * p[6, 0] + p[6, 1], 0, 1) ** 2
                    shadow = np.array([(a[0] + (1 - a[0]) * fade) * a[2],
                                       min(a[1] + (1 - a[1]) * fade, a[3]) * a[2], min(a[1], a[3])])
            result[index, 1, :3] = shadow
    return result


def oracle_self_check(cases, inputs, expected):
    assert len(cases) >= 30 and inputs.shape == (len(cases), INPUT_ROWS, 4)
    assert len({c["name"] for c in cases}) == len(cases)
    assert len({row.tobytes() for row in inputs}) == len(cases), "duplicate input cases"
    assert np.isfinite(inputs).all() and np.isfinite(expected).all()
    by_name = {c["name"]: expected[i] for i, c in enumerate(cases)}
    np.testing.assert_allclose(by_name["point_inverse_1_distance_5"][0], [0, 0, 5, 0.87890625], rtol=0, atol=2e-8)
    np.testing.assert_allclose(by_name["point_inverse_0_distance_5"][0, 3], 0.5625, rtol=0, atol=2e-8)
    for inverse in (0, 1):
        assert by_name[f"point_inverse_{inverse}_distance_20"][0, 3] == 0
        assert by_name[f"spot_inverse_{inverse}_cosine_-1"][0, 3] == 0
        ratio = by_name[f"spot_inverse_{inverse}_cosine_0.625"][0, 3] / by_name[f"point_inverse_{inverse}_distance_5"][0, 3]
        np.testing.assert_allclose(ratio, 0.25, rtol=0, atol=1e-14)
    np.testing.assert_array_equal(by_name["raw_type_1_bits_3_mask_0.5"][1, :3], [0.25] * 3)
    np.testing.assert_array_equal(by_name["raw_type_0_bits_3_mask_0.5"][1, :3], [0.0625, 0.0625, 0.25])
    for kind in (0, 1, 2):
        np.testing.assert_array_equal(by_name[f"ao_type_{kind}_bits_0"][1, :3], [0.125, 1, 1])
    np.testing.assert_array_equal(by_name["static_off_ignored_fields_0"], by_name["static_off_ignored_fields_1"])
    for i, c in enumerate(cases):
        if c["name"].startswith("reject_"):
            assert expected[i, 2, 0] == 0
            np.testing.assert_array_equal(expected[i, 1, :3], 0)
        if c["type"] not in (1, 2):
            assert expected[i, 1, 3] == 0
            np.testing.assert_array_equal(expected[i, 0], 0)
    return {"samples": len(cases), "seed": SEED, "local_valid": int(expected[:, 1, 3].sum()),
            "shadow_valid": int(expected[:, 2, 0].sum()), "offline_self_check": "passed"}


def shader_snapshot():
    """Read and flatten the real local dependency graph once, without editing it."""
    root = (ROOT / "Source/RenderPasses/customrenderpipline/Codecs").resolve()
    active, emitted, hashes = set(), set(), {}
    include = re.compile(r'^\s*#\s*include\s+"([^"\r\n]+)"[ \t]*$', re.MULTILINE)

    def visit(path):
        path = path.resolve()
        if not path.is_relative_to(root) or path in active:
            raise ValueError("shader include escapes codec root or creates a cycle: " + str(path))
        if path in emitted:
            return ""
        active.add(path)
        data = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
        source = include.sub(lambda match: visit(path.parent / match[1]), data.decode("utf-8"))
        if re.search(r'^\s*(?:#\s*include\b|import\b)', source, re.MULTILINE):
            raise ValueError("only quoted local includes are supported by this probe")
        active.remove(path)
        emitted.add(path)
        return f"// Source: {path.relative_to(ROOT).as_posix()}\n{source}\n"

    return visit(root / "Lighting/LightTerms.slangh") + KERNEL, hashes


def comparison(actual, expected, cases):
    finite = np.isfinite(actual).all(axis=(1, 2))
    # toLight is one float32 subtraction, so require exact uploaded-coordinate results.
    displacement = (actual[:, 0, :3].view(np.uint32) == expected[:, 0, :3].astype(np.float32).view(np.uint32)).all(axis=1)
    mask = np.isclose(actual[:, 0, 3], expected[:, 0, 3], rtol=RTOL, atol=ATOL)
    shadow = np.isclose(actual[:, 1, :3], expected[:, 1, :3], rtol=RTOL, atol=ATOL).all(axis=1)
    validity = (actual[:, 1, 3] == expected[:, 1, 3]) & (actual[:, 2, 0] == expected[:, 2, 0])
    padding = (actual[:, 2, 1:] == 0).all(axis=1)
    rejected = np.ones(len(cases), dtype=bool)
    local_invalid, shadow_invalid = expected[:, 1, 3] == 0, expected[:, 2, 0] == 0
    rejected[local_invalid] &= (actual[local_invalid, 0] == 0).all(axis=1)
    rejected[shadow_invalid] &= (actual[shadow_invalid, 1, :3] == 0).all(axis=1)
    checks = dict(finite=finite, displacement_bits=displacement, local_mask=mask,
                  shadow=shadow, validity=validity, padding=padding, rejected_outputs_zero=rejected)
    passed = np.logical_and.reduce(list(checks.values()))
    absolute = np.abs(actual.astype(np.float64) - expected)
    return {"passed": bool(passed.all()), "rtol": RTOL, "atol": ATOL,
            "max_local_mask_absolute_error": float(absolute[:, 0, 3].max()) if finite.all() else None,
            "max_shadow_absolute_error": float(absolute[:, 1, :3].max()) if finite.all() else None,
            "cases": [{"index": i, "name": c["name"], "passed": bool(passed[i]),
                       "failed_checks": [name for name, values in checks.items() if not values[i]]}
                      for i, c in enumerate(cases)]}


def run_gpu(cases, inputs, expected, self_check, out):
    import falcor

    out.mkdir(parents=True, exist_ok=True)
    shader, hashes = shader_snapshot()
    shader_path, raw_path = out / "kernel.cs.slang", out / "raw.npz"
    shader_path.write_text(shader, encoding="utf-8")
    script_path = ROOT / "scripts/customrenderpipline/light_terms_smoke.py"
    ue_root = Path(os.environ.get("UE_SOURCE_ROOT", "E:/ue/engine/UnrealEngine"))
    ue_paths = [ue_root / "Engine/Shaders/Private" / name for name in
                ("DeferredLightingCommon.ush", "DynamicLightingCommon.ush", "Common.ush")]
    result = {"status": "running", "scope": "real LightTerms standalone StructuredBuffer GPU probe",
              "capture_equivalence": False, "native_lighting_pass_complete": False, **self_check,
              "source_hashes": hashes, "script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
              "kernel_sha256": hashlib.sha256(shader.encode("utf-8")).hexdigest(),
              "ue_source_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in ue_paths},
              "raw_npz": str(raw_path), "input_rows": INPUT_ROWS, "output_rows": OUTPUT_ROWS,
              "output_layout": ["toLight.xyz, mask", "surface, transmission, optical, localValid", "shadowValid, 0, 0, 0"],
              "case_inputs": cases}
    actual = None
    failure = None
    try:
        device = falcor.Device(type=falcor.DeviceType.D3D12, gpu=0, enable_debug_layer=True)
        src = device.create_structured_buffer(16, len(cases) * INPUT_ROWS, falcor.ResourceBindFlags.ShaderResource)
        dst = device.create_structured_buffer(16, len(cases) * OUTPUT_ROWS, falcor.ResourceBindFlags.UnorderedAccess)
        src.from_numpy(inputs.reshape(-1, 4))
        compute = falcor.ComputePass(device, string=shader, cs_entry="main", shader_model=falcor.ShaderModel.SM6_6)
        compute.globals["gInput"] = src
        compute.globals["gResult"] = dst
        compute.execute(threads_x=len(cases))
        actual = np.frombuffer(dst.to_numpy().tobytes(), dtype=np.float32).reshape(expected.shape).copy()
        result["comparison"] = comparison(actual, expected, cases)
        if not result["comparison"]["passed"]:
            raise AssertionError("LightTerms GPU comparison failed; inspect per-case result and raw NPZ")
        result["status"] = "passed"
    except Exception as error:
        failure = error
        result.update(status="failed", error_type=type(error).__name__, error=str(error))
    finally:
        arrays = dict(inputs=inputs, expected=expected, names=np.asarray([c["name"] for c in cases]))
        if actual is not None:
            arrays.update(actual=actual, actual_bits=actual.view(np.uint32))
        np.savez_compressed(raw_path, **arrays)
        result["raw_npz_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        dll = BIN / "Falcor.dll"
        result["falcor_dll_sha256"] = hashlib.sha256(dll.read_bytes()).hexdigest() if dll.is_file() else None
        (out / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("LIGHT_TERMS_GPU_" + result["status"].upper() + " " + json.dumps({
        "samples": len(cases), "result": str(out / "result.json"), "raw": str(raw_path)}))
    if failure is not None:
        raise failure
    return result


def main(gpu=False, out=None):
    cases = make_cases()
    inputs = pack_inputs(cases)
    expected = oracle(inputs)
    self_check = oracle_self_check(cases, inputs, expected)
    # Self-test the comparator's ability to detect representative algorithm errors.
    assert comparison(expected.astype(np.float32), expected, cases)["passed"]
    broken = expected.astype(np.float32)
    broken[0, 0, 3] += 0.01
    broken[1, 2, 0] = 0.0
    assert not comparison(broken, expected, cases)["passed"]
    shader, hashes = shader_snapshot()
    if not gpu:
        print("LIGHT_TERMS_ORACLE_PASSED " + json.dumps({**self_check, "gpu_executed": False,
              "source_hashes": hashes, "kernel_sha256": hashlib.sha256(shader.encode()).hexdigest()}))
        return self_check
    return run_gpu(cases, inputs, expected, self_check, out or ROOT / "build/light-terms-evidence")


if __name__ == "__main__" or EMBEDDED:
    if EMBEDDED:
        main(gpu=True)
        exit()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--oracle-only", action="store_true", help="offline only (default); no evidence files or device")
        mode.add_argument("--gpu", action="store_true", help="explicitly execute the GPU probe; Mogwai selects this automatically")
        parser.add_argument("--output", type=Path, help="GPU evidence output directory")
        args = parser.parse_args()
        main(gpu=args.gpu, out=args.output)
