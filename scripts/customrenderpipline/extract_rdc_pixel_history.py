"""Bounded E2655 GPU PixelHistory evidence, never a rendering algorithm input.

Default/--prepare-only is CPU-only: freeze 95 mismatch pixels, four fixed probes,
and eight deterministic covered matching controls, with full input hashes.
--replay explicitly launches one hidden qrenderdoc worker, then compares its
E2655 preMod/shaderOut/postMod on CPU. --analyze-only reuses an existing run.

  python -B scripts/customrenderpipline/extract_rdc_pixel_history.py --prepare-only
  python -B scripts/customrenderpipline/extract_rdc_pixel_history.py --replay
  python -B scripts/customrenderpipline/extract_rdc_pixel_history.py --analyze-only

To retain the original 95-pixel baseline after the normal run is replaced, pass
--native build/rdc-lighting-diagnostic/native-outputs.npz explicitly. This uses
only that file's HDR as the baseline and records that the baseline itself is
diagnostic; its HDR equality check is then not an independent two-file check.

PixelHistory uses instrumented GPU replay, not the DebugPixel interpreter. Its
shaderOut is a RenderDoc intermediate, not a raw original-command attachment.
preMod/postMod are independently checked against the raw half attachments.
The diagnostic NPZ's directTransmission.rgb was deliberately replaced with
pre-exposed shader radiance; it is NOT the ordinary transmission contribution.
No extracted or diagnostic values are written to a rendering input or DDS.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_HASH = "822d41ea6ecb12633f42b18ed5ae1a3e7cea02653c9a72724f6e55e127d85fc9"
FIXED = ((280, 475), (650, 950), (768, 653), (291, 668))
MAX_POINTS = 128
CONTROL_COUNT = 8
METHOD_LIMITS = [
    "Read-only RenderDoc PixelHistory GPU replay; earlier events may replay internally, but only E2655 is exported.",
    "PixelHistory shaderOut is an instrumented GPU intermediate, distinct from DebugPixel interpreter results and original raw attachments.",
    "preMod and postMod must round-trip to the original E2624 and E2655 RGBA16Float bits at every selected pixel.",
    "One fragment per selected pixel is required for this fullscreen draw; discarded/failed fragments invalidate the comparison.",
    "Selected mismatch pixels are a census for the hashed baseline; matching controls are sparse deterministic samples, not whole-image shader proof.",
    "Diagnostic directTransmission.rgb is substituted pre-exposed radiance, not normal transmission. HDR equality is independently checked.",
    "CPU half-blend predictions are diagnostic only; GPU blend rounding and replay instrumentation constrain interpretation.",
    "Outputs are CPU comparison evidence only and cannot establish final-render equivalence or be consumed as algorithm inputs.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_json(path, value, immutable=False):
    payload = json_bytes(value)
    path = Path(path)
    if immutable and path.exists():
        require(path.read_bytes() == payload, "Existing evidence plan changed; use a new --out directory: " + str(path))
    else:
        path.write_bytes(payload)


def file_record(path):
    path = Path(path).resolve()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha_file(path)}


def raw_color(directory, replay, event):
    entry = next(e for e in replay["sceneColor"] if e["event"] == event)
    path = (directory / entry["file"]).resolve()
    require(path.is_relative_to(directory.resolve()), "Raw capture file escaped the evidence directory")
    payload = gzip.decompress(path.read_bytes())
    require(len(payload) == entry["byteSize"] and sha_bytes(payload) == entry["sha256"], "Raw capture hash/size mismatch")
    require(entry["resource"] == "ResourceId::3250395" and [entry["width"], entry["height"]] == [1424, 1040], "Unexpected SceneColor")
    return np.frombuffer(payload, dtype="<f2").reshape(1040, 1424, 4), {**file_record(path), "raw_sha256": entry["sha256"]}


def select_pixels(mismatch, coverage, controls=CONTROL_COUNT):
    height, width = mismatch.shape
    mismatch_yx = np.argwhere(mismatch)
    mismatches = [(int(x), int(y)) for y, x in mismatch_yx]  # Complete row-major census.
    fixed = list(FIXED)
    require(all(0 <= x < width and 0 <= y < height for x, y in fixed), "Fixed probes outside allocation")
    pool = np.flatnonzero(coverage & ~mismatch)
    pool = pool[~np.isin(pool, [y * width + x for x, y in fixed])]
    require(len(pool) >= controls, "Not enough covered matching control pixels")
    # Integer quantile centers in row-major order, no random state or platform RNG.
    chosen_indices = [int(pool[((2 * i + 1) * len(pool)) // (2 * controls)]) for i in range(controls)]
    chosen = [(i % width, i // width) for i in chosen_indices]
    selected = list(dict.fromkeys(mismatches + fixed + chosen))
    require(len(selected) <= MAX_POINTS, "All mismatches/probes/controls exceed the hard 128-pixel replay bound")
    return mismatches, fixed, chosen, selected


def prepare(args):
    raw_dir = args.raw.resolve()
    sources = {"baseline_native_npz": file_record(args.native), "diagnostic_npz": file_record(args.diagnostic),
        "diagnostic_shader": file_record(args.diagnostic_shader), "raw_replay_manifest": file_record(raw_dir / "replay-lighting.json")}
    shader = args.diagnostic_shader.read_text(encoding="utf-8")
    require("result.transmission = float4(radiance, shading.shadow.transmissionShadow);" in shader,
            "Diagnostic shader no longer exposes radiance in the transmission output")
    replay = read_json(raw_dir / "replay-lighting.json")
    require(replay["event"] == 2655 and replay["previousDrawEvent"] == 2624, "Unexpected capture stage chain")
    before, sources["raw_before_e2624"] = raw_color(raw_dir, replay, 2624)
    target, sources["raw_after_e2655"] = raw_color(raw_dir, replay, 2655)
    with np.load(args.native, allow_pickle=False) as normal, np.load(args.diagnostic, allow_pickle=False) as diagnostic:
        actual = normal["lightingColor"].copy()
        diagnostic_hdr = diagnostic["lightingColor"].copy()
        ps = diagnostic["directTransmission"].copy()
        coverage = normal["primaryCoverage"].reshape(1040, 1424) != 0
        require(actual.dtype == np.dtype("<f2") and actual.shape == target.shape and np.isfinite(actual).all(), "Invalid baseline native HDR")
        require(diagnostic_hdr.dtype == actual.dtype and diagnostic_hdr.shape == actual.shape
                and diagnostic_hdr.tobytes() == actual.tobytes(), "Diagnostic HDR does not match the selected baseline")
        require(ps.dtype == np.dtype("<f4") and ps.shape == actual.shape and np.isfinite(ps).all(), "Invalid diagnostic shader-radiance output")
        native_context, diagnostic_context = json.loads(str(normal["context_json"])), json.loads(str(diagnostic["context_json"]))
    require(np.array_equal(before.view("<u2")[..., 3], target.view("<u2")[..., 3]), "Unexpected E2655 alpha modifications")
    mismatch = np.any(actual.view("<u2") != target.view("<u2"), axis=-1)
    require(int(mismatch.sum()) == args.expect_mismatch_pixels, "Mismatch census changed: expected {}, got {}".format(args.expect_mismatch_pixels, int(mismatch.sum())))
    require(np.all(coverage[mismatch]), "Expected only covered mismatch pixels for this bounded light draw")
    mismatches, fixed, controls, selected = select_pixels(mismatch, coverage)
    for name, record in sources.items():
        require(sha_file(record["path"]) == record["sha256"], "Source changed while preparing evidence: " + name)
    capture = file_record(args.capture)
    require(capture["sha256"] == CAPTURE_HASH, "Unexpected capture SHA256")
    samples = []
    for x, y in selected:
        roles = [name for name, points in (("mismatch", mismatches), ("fixed_probe", fixed), ("matching_control", controls)) if (x, y) in points]
        samples.append({"xy": [x, y], "roles": roles,
            "before_half_bits_rgba": before.view("<u2")[y, x].astype(int).tolist(),
            "target_half_bits_rgba": target.view("<u2")[y, x].astype(int).tolist(),
            "native_half_bits_rgba": actual.view("<u2")[y, x].astype(int).tolist(),
            "diagnostic_shader_radiance_float32_bits_rgb": ps.view("<u4")[y, x, :3].astype(int).tolist()})
    return {"version": 1, "event": 2655, "resource": replay["sceneColorResource"], "extent": [1424, 1040],
        "capture": capture, "sources": sources, "mismatch_pixel_count": len(mismatches),
        "mismatch_pixels_xy": mismatches, "fixed_probe_pixels_xy": fixed, "matching_control_pixels_xy": controls,
        "selected_pixels_xy": selected, "selected_count": len(selected), "hard_max_points": MAX_POINTS,
        "selection_order": "all row-major mismatches, fixed probes in listed order, then integer-quantile covered matching controls; deduplicated",
        "diagnostic_hdr_full_allocation_bitwise_equal": True, "samples": samples,
        "baseline_source_is_diagnostic": args.native.resolve() == args.diagnostic.resolve(),
        "diagnostic_hdr_comparison_independent_files": args.native.resolve() != args.diagnostic.resolve(),
        "native_context": native_context, "diagnostic_context": diagnostic_context,
        "diagnostic_shader_output_meaning": "directTransmission.rgb is replaced by pre-exposed direct shader radiance; not ordinary transmission",
        "tool_hashes": {"launcher": sha_file(Path(__file__)), "worker": sha_file(Path(__file__).with_name("_extract_rdc_pixel_history_replay.py"))},
        "method_boundaries": METHOD_LIMITS, "algorithm_input": False, "capture_equivalence": False}


def float32_ulps(a, b):
    def ordered(values):
        bits = np.asarray(values, dtype="<f4").view("<u4").astype(np.int64)
        return np.where(bits & 0x80000000, 0x80000000 - (bits & 0x7fffffff), 0x80000000 + bits)
    return np.abs(ordered(a) - ordered(b))


def compare_entries(plan, entries):
    expected = {tuple(sample["xy"]): sample for sample in plan["samples"]}
    require(len(entries) == len(expected) and len({tuple(e["xy"]) for e in entries}) == len(expected), "Incomplete/duplicate PixelHistory selection")
    results = []
    for probe in entries:
        xy = tuple(probe["xy"])
        require(xy in expected and len(probe["history"]) == 1, "Unexpected history point or fragment count")
        entry, sample = probe["history"][0], expected[xy]
        require(entry["eventId"] == 2655, "Export contains another event")
        flags = {key: value for key, value in entry.items() if isinstance(value, bool)}
        require(not any(flags.values()), "PixelHistory contains a failed/discarded/non-raster modification")
        values = {}
        for field in ("preMod", "shaderOut", "postMod"):
            values[field] = np.array(entry[field]["col"]["floatValue"], dtype="<f4")
            require(values[field].shape == (4,) and np.isfinite(values[field]).all(), "Invalid PixelHistory float vector")
            require(values[field].view("<u4").astype(int).tolist() == entry[field]["col"]["uintValue"], "Float/uint PixelHistory representations disagree")
        before_bits = np.array(sample["before_half_bits_rgba"], dtype="<u2")
        target_bits = np.array(sample["target_half_bits_rgba"], dtype="<u2")
        native_bits = np.array(sample["native_half_bits_rgba"], dtype="<u2")
        ps_native = np.array(sample["diagnostic_shader_radiance_float32_bits_rgb"], dtype="<u4").view("<f4")
        ps_capture = values["shaderOut"][:3]
        before_valid = np.array_equal(values["preMod"].view("<u4"), before_bits.view("<f2").astype("<f4").view("<u4"))
        post_valid = np.array_equal(values["postMod"].view("<u4"), target_bits.view("<f2").astype("<f4").view("<u4"))
        native_prediction = (values["preMod"][:3] + ps_native).astype("<f2").view("<u2")
        capture_prediction = (values["preMod"][:3] + ps_capture).astype("<f2").view("<u2")
        results.append({"xy": list(xy), "roles": sample["roles"], "pre_mod_matches_e2624_half_bits": bool(before_valid),
            "post_mod_matches_e2655_half_bits": bool(post_valid), "shader_out_alpha_zero": bool(values["shaderOut"][3] == 0),
            "capture_gpu_shader_out_rgba": values["shaderOut"].astype(float).tolist(),
            "capture_gpu_shader_out_float32_bits_rgba": values["shaderOut"].view("<u4").astype(int).tolist(),
            "native_diagnostic_shader_radiance_rgb": ps_native.astype(float).tolist(),
            "native_minus_capture_shader_rgb": (ps_native.astype(np.float64) - ps_capture.astype(np.float64)).tolist(),
            "shader_float32_ulp_distance_rgb": float32_ulps(ps_native, ps_capture).astype(int).tolist(),
            "shader_raw_equal_rgb": (ps_native.view("<u4") == ps_capture.view("<u4")).tolist(),
            "target_half_bits_rgba": target_bits.astype(int).tolist(), "native_half_bits_rgba": native_bits.astype(int).tolist(),
            "cpu_native_shader_blend_prediction_matches_native_rgb": (native_prediction == native_bits[:3]).tolist(),
            "cpu_capture_shader_blend_prediction_matches_capture_rgb": (capture_prediction == target_bits[:3]).tolist(),
            "cpu_blend_comparison_is_diagnostic_only": True})
    groups = {}
    for role in ("all", "mismatch", "fixed_probe", "matching_control"):
        group = [p for p in results if role == "all" or role in p["roles"]]
        ulps = np.array([p["shader_float32_ulp_distance_rgb"] for p in group], dtype=np.int64)
        groups[role] = {"pixels": len(group), "shader_raw_equal_pixels": sum(all(p["shader_raw_equal_rgb"]) for p in group),
            "shader_raw_equal_channels": sum(sum(p["shader_raw_equal_rgb"]) for p in group),
            "max_shader_float32_ulp": int(ulps.max()) if ulps.size else None,
            "shader_float32_ulp_counts": {str(i): int(np.count_nonzero(ulps == i)) for i in range(5)},
            "shader_float32_ulp_over_4": int(np.count_nonzero(ulps > 4))}
    valid = all(p["pre_mod_matches_e2624_half_bits"] and p["post_mod_matches_e2655_half_bits"] and p["shader_out_alpha_zero"] for p in results)
    return {"status": "complete" if valid else "reference_validation_failed", "reference_validation_passed": valid,
        "method_boundaries": METHOD_LIMITS, "groups": groups, "pixels": results,
        "algorithm_input": False, "capture_equivalence": False}


def analyze(plan_path, run):
    plan = read_json(plan_path)
    done = read_json(run / "replay-done.json")
    require(done["ok"] is True and done["capture_unchanged"] is True and done["capture_sha256_before"] == done["capture_sha256_after"] == CAPTURE_HASH,
            "Worker did not verify unchanged capture")
    require(done["plan_sha256"] == sha_file(plan_path) and done["history_sha256"] == sha_file(run / "history.json")
            and done["api_sha256"] == sha_file(run / "api.json") and done["point_count"] == plan["selected_count"], "PixelHistory provenance mismatch")
    require(done["fullscreen_triangle_sha256"] == sha_file(run / "fullscreen-triangle.json"), "Fullscreen triangle provenance mismatch")
    triangle = read_json(run / "fullscreen-triangle.json")
    require(triangle["event"] == 2655 and triangle["total_raw_bytes"] <= 1024, "Unexpected fullscreen geometry evidence")
    for entry in triangle["files"]:
        path = (run / entry["file"]).resolve()
        require(path.is_relative_to(run.resolve()) and path.stat().st_size == entry["byteSize"]
                and sha_file(path) == entry["sha256"], "Fullscreen triangle raw buffer changed")
    report = compare_entries(plan, read_json(run / "history.json"))
    report.update(plan_sha256=sha_file(plan_path), history_sha256=done["history_sha256"], run=str(run),
        source_hashes=plan["sources"], capture=plan["capture"], selected_pixels_xy=plan["selected_pixels_xy"],
        baseline_source_is_diagnostic=plan["baseline_source_is_diagnostic"],
        diagnostic_hdr_comparison_independent_files=plan["diagnostic_hdr_comparison_independent_files"], fullscreen_triangle=triangle)
    write_json(run / "comparison.json", report)
    print(json.dumps({"status": report["status"], "report": str(run / "comparison.json"), "groups": report["groups"], "algorithm_input": False}))
    require(report["reference_validation_passed"], "PixelHistory pre/post values differ from raw capture; inspect saved comparison")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--replay", action="store_true")
    mode.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--native", type=Path, default=ROOT / "build/rdc-lighting-render/native-outputs.npz")
    parser.add_argument("--diagnostic", type=Path, default=ROOT / "build/rdc-lighting-diagnostic/native-outputs.npz")
    parser.add_argument("--diagnostic-shader", type=Path, default=ROOT / "build/rdc-lighting-diagnostic/LightingRadiance.3d.slang")
    parser.add_argument("--raw", type=Path, default=ROOT / "build/rdc-lighting/raw")
    parser.add_argument("--capture", type=Path, default=Path("E:/rdc/ue/1.rdc"))
    parser.add_argument("--out", type=Path, default=ROOT / "build/rdc-lighting-pixel-history")
    parser.add_argument("--renderdoc", type=Path, default=Path("C:/Program Files/RenderDoc/qrenderdoc.exe"))
    parser.add_argument("--expect-mismatch-pixels", type=int, default=95)
    parser.add_argument("--run", type=Path, help="specific existing replay directory for --analyze-only")
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.is_relative_to((ROOT / "build").resolve()), "Evidence output must stay inside this worktree build directory")
    out.mkdir(parents=True, exist_ok=True)
    plan_path = out / "selection-plan.json"
    if args.analyze_only:
        run = args.run.resolve() if args.run else Path(read_json(out / "latest-run.json")["run"]).resolve()
        require(run.is_relative_to(out) and run != out, "Replay directory escaped the selected output directory")
        analyze(plan_path, run)
        return
    plan = prepare(args)
    write_json(plan_path, plan, immutable=True)
    print("PIXEL_HISTORY_SELECTION_READY " + json.dumps({"plan": str(plan_path), "plan_sha256": sha_file(plan_path),
        "mismatch_pixels": plan["mismatch_pixel_count"], "selected_pixels": plan["selected_count"], "max_pixels": MAX_POINTS,
        "baseline_npz": plan["sources"]["baseline_native_npz"], "baseline_source_is_diagnostic": plan["baseline_source_is_diagnostic"],
        "gpu_executed": False, "algorithm_input": False}), flush=True)
    if not args.replay:
        return
    require(args.renderdoc.is_file(), "RenderDoc launcher not found")
    run = Path(tempfile.mkdtemp(prefix="replay-", dir=out)).resolve()
    write_json(out / "latest-run.json", {"run": str(run), "plan_sha256": sha_file(plan_path)})
    environment = dict(os.environ, UE_RDC_PIXEL_HISTORY_PLAN=str(plan_path), UE_RDC_PIXEL_HISTORY_OUT=str(run),
        UE_RDC_PIXEL_HISTORY_PLAN_SHA256=sha_file(plan_path))
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    capture_before = sha_file(args.capture)
    launch_error = None
    try:
        with (run / "process.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run([str(args.renderdoc.resolve()), "--python", str(Path(__file__).with_name("_extract_rdc_pixel_history_replay.py"))],
                env=environment, startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=log, stderr=subprocess.STDOUT, timeout=960, check=False)
    except Exception as error:
        launch_error = repr(error)
    finally:
        capture_after = sha_file(args.capture)
        write_json(run / "launcher-result.json", {"capture_sha256_before": capture_before,
            "capture_sha256_after": capture_after, "capture_unchanged": capture_after == capture_before,
            "error": launch_error})
    require(capture_after == capture_before == CAPTURE_HASH, "Capture changed during launcher execution")
    require(launch_error is None, "RenderDoc launch failed: " + str(launch_error))
    if (run / "replay-error.json").exists():
        raise RuntimeError(read_json(run / "replay-error.json")["error"])
    require(completed.returncode == 0, "RenderDoc worker failed; inspect " + str(run / "process.log"))
    analyze(plan_path, run)


if __name__ == "__main__":
    main()
