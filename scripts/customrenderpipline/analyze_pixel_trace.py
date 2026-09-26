"""Compact the existing E1853 DebugPixel trace; no replay or GPU work.

The RenderDoc SSA names below belong to the captured shader-1853-Pixel.txt.
The native probe JSON must use the two layouts documented in pixel_probe_smoke.py.
"""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np


GROUPS = {
    "sv_position": [129, 130, 131],
    "homogeneous": [215, 219, 223, 227],
    "translated_world": [228, 229, 230],
    "position_ue": [231, 232, 233],
    "delta": [290, 292, 294],
    "axis_x": [306, 307, 308],
    "axis_y": [315, 316, 317],
    "axis_z": [324, 325, 326],
    "projected_delta": [309, 318, 327],
    "frequency": [329],
    "uvw": [330, 331, 332],
    "half_uvw": [333, 334, 335],
    "blend_x_z": [347, 358],
    "checker_mask": [361],
    "red_mix_z_contribution_inverse": [389, 395, 397],
    "base_color": [408, 409, 410],
    "metallic_roughness_dither": [411, 420, 431],
    "saturated_base_color": [432, 433, 434],
    "saturated_metallic_roughness": [435, 436],
    "overridden_roughness": [438],
}
SAMPLES = [
    ("half_xz_green", 338, 339, 224, 225, "gBufferD", 0),
    ("half_yz_green", 342, 343, 228, 229, "gBufferD", 1),
    ("half_xy_green", 353, 354, 239, 240, "gBufferD", 2),
    ("full_xz_red", 381, 382, 267, 268, "debug0", 0),
    ("full_yz_red", 385, 386, 271, 272, "debug0", 1),
    ("full_xy_red", 392, 393, 278, 279, "gBufferD", 3),
]


def compact(variable):
    if variable["members"]:
        return {member["name"]: compact(member) for member in variable["members"]}
    count = variable["rows"] * variable["columns"]
    result = {
        "type": variable["type"],
        "u32": variable["value"]["u32v"][:count],
    }
    if variable["type"] == 0:
        result["f32"] = variable["value"]["f32v"][:count]
    return result


def unorm8(value):
    # Ideal nearest conversion for this comparison, not a model of the GPU ROP.
    return int(np.rint(np.clip(value, 0.0, 1.0) * 255.0))


def srgb(value):
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1.0 / 2.4) - 0.055


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=Path("build/rdc-pixel-trace"))
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--native-probe", type=Path, default=Path("build/rdc-pixel-probe/result.json"))
    parser.add_argument("--precise-probe", type=Path)
    parser.add_argument("--native-outputs", type=Path, default=Path("build/rdc-render/outputs.npz"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    evidence = {}

    def read_bytes(path):
        raw = path.read_bytes()
        evidence[str(path.resolve())] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        return raw

    def read_json(path):
        return json.loads(read_bytes(path).decode("utf-8"))

    metadata = read_json(args.trace / "result.json")
    states = read_json(args.trace / "states.json")
    trace = read_json(args.trace / "trace.json")
    probe = read_json(args.native_probe)
    outputs_bytes = read_bytes(args.native_outputs)
    assert metadata["event"] == 1853 and metadata["pixel"] == [948, 1017], metadata
    assert metadata["states"] == len(states)
    outputs_sha = hashlib.sha256(outputs_bytes).hexdigest()
    x, y = metadata["pixel"]
    pixel_key = str((x, y))
    mode0 = probe["modes"]["0"]["quad"][pixel_key]
    mode1 = probe["modes"]["1"]["quad"][pixel_key]

    values = {}
    for state in states:
        for change in state["changes"]:
            after = change["after"]
            # Empty after names delete a value from the live display. Retain its
            # last definition; SSA values remain useful after their lifetime ends.
            if after["name"]:
                values[after["name"]] = {
                    "step": state["stepIndex"],
                    "next_instruction": state["nextInstruction"],
                    "value": compact(after),
                }

    selected = {}
    for name, indices in GROUPS.items():
        records = {f"_{i}": values[f"_{i}"] for i in indices}
        selected[name] = {"f32": [records[f"_{i}"]["value"]["f32"][0] for i in indices], "records": records}
    samples = {}
    for name, result, scalar, llvm_result, llvm_scalar, attachment, channel in SAMPLES:
        captured_value = values[f"_{scalar}"]["value"]["f32"][0]
        native_value = mode1[attachment]["float"][channel]
        samples[name] = {
            "renderdoc_result": f"_{result}", "renderdoc_scalar": f"_{scalar}",
            "llvm_result": f"%{llvm_result}", "llvm_scalar": f"%{llvm_scalar}",
            "trace_result": values[f"_{result}"], "trace_scalar": values[f"_{scalar}"],
            "native_scalar": native_value, "native_minus_trace": native_value - captured_value,
            "equal": native_value == captured_value,
        }

    final = values["_OUT"]
    targets = final["value"]
    b = targets["SV_Target2"]["f32"]
    c = targets["SV_Target3"]["f32"]
    predicted = {
        "gBufferB": [unorm8(b[2]), unorm8(b[1]), unorm8(b[0]), unorm8(b[3])],
        "gBufferC": [unorm8(srgb(c[2])), unorm8(srgb(c[1])), unorm8(srgb(c[0])), unorm8(c[3])],
    }
    actual = {}
    with np.load(io.BytesIO(outputs_bytes)) as arrays:
        height, width = arrays["depth"].shape
        for name in ["gBufferA", "gBufferB", "gBufferC"]:
            filename = "1853-" + name[0].upper() + name[1:] + ".bin.gz"
            raw = gzip.decompress(read_bytes(args.capture / filename))
            captured = np.frombuffer(raw, np.uint8).reshape(height, width, 4)[y, x].tolist()
            native = arrays[name].reshape(height, width, 4)[y, x].tolist()
            layout = "packed_r10g10b10a2_bytes" if name == "gBufferA" else "bgra_bytes"
            actual[name] = {"captured_" + layout: captured, "current_native_" + layout: native}
            if name in predicted:
                actual[name]["trace_ideal_quantized_bgra"] = predicted[name]
                actual[name]["trace_quantization_matches_capture"] = predicted[name] == captured
        raw_depth = gzip.decompress(read_bytes(args.capture / "1853-SceneDepthZ.bin.gz"))
        depth_bits = np.frombuffer(raw_depth, "<u4").reshape(height, width, 2)[y, x, 0]
        actual["depth"] = {"capture_bits": int(depth_bits), "native_bits": int(arrays["depth"].view(np.uint32)[y, x]), "trace_bits": values["_131"]["value"]["u32"][0]}

    world_z = selected["position_ue"]["f32"][2]
    native_z = mode0["gBufferD"]["float"][2]
    for path in [args.capture / "shader-1853-Pixel.txt", args.capture / "reflection-1853-Pixel.json",
                 args.trace / "original-1853.ll", args.native_probe.parent / "native-mode0.ll"]:
        if path.exists():
            read_bytes(path)
    report = {
        "scope": "Offline extraction of existing debugger simulation and previously rendered native diagnostics; no replay or GPU work.",
        "trace_metadata": metadata, "trace_inputs": compact(trace["inputs"][0]),
        "selected": selected, "samples": samples, "final_outputs": final,
        "native_probe_snapshot": probe,
        "precise_probe_snapshot": read_json(args.precise_probe) if args.precise_probe else None,
        "current_native_outputs_sha256": outputs_sha,
        "current_native_outputs_matches_probe_baseline": outputs_sha == probe["baseline_npz_sha256"],
        "attachment_comparison": actual,
        "position_rounding_grid": {
            "step": 2.0 ** -14, "trace_z_divided_by_step": world_z * 16384,
            "native_z_divided_by_step": native_z * 16384,
            "meaning": "Separate rounded float32 translated Z near -644 minus captured float32 pre-view Z must produce an integer multiple of 2^-14. Native Z does not. This does not identify machine instructions.",
        },
        "trust_boundary": "B/C ideal quantization agrees with actual captured bytes for this pixel. This supports the traced material computation here; it does not prove every debugger intermediate or neighbor derivative equals original GPU execution. Native probe packed_equal is supplied by the parent rendering run.",
        "evidence": evidence,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.out.resolve()), "samples_equal": {k: v["equal"] for k, v in samples.items()}, "attachments": actual}, indent=2))


if __name__ == "__main__":
    main()
