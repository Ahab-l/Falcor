"""Validate this observed capture contract; optionally verify the immutable evidence files."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

DEFAULT_PROFILE = Path(__file__).with_name("reference_profile.json")
FORMATS = [
    ("SceneColor", "R16G16B16A16_FLOAT", "R16G16B16A16_FLOAT", "RGBA16Float", "RGBA"),
    ("GBufferA", "R10G10B10A2_UNORM", "R10G10B10A2_UNORM", "RGB10A2Unorm", "R10G10B10A2"),
    ("GBufferB", "B8G8R8A8_TYPELESS", "B8G8R8A8_UNORM", "BGRA8Unorm", "BGRA"),
    ("GBufferC", "B8G8R8A8_TYPELESS", "B8G8R8A8_UNORM_SRGB", "BGRA8UnormSrgb", "BGRA"),
    ("GBufferD", "B8G8R8A8_TYPELESS", "B8G8R8A8_UNORM", "BGRA8Unorm", "BGRA"),
]

def require(condition, message):
    if not condition:
        raise ValueError(message)

def positive(value, label):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0, label + " must be positive and finite")

def _validate(p, evidence_dir):
    require(p["schema_version"] == 1, "unsupported schema version")
    require(p["profile_id"] == "ue-local-5bit-1rdc-opaque", "unsupported capture profile")
    capture = p["capture"]
    require(capture["sha256"] == "822d41ea6ecb12633f42b18ed5ae1a3e7cea02653c9a72724f6e55e127d85fc9" and
            capture["bytes"] == 217008048 and capture["frame_marker"] == 21880, "fixed capture identity mismatch")
    require(capture["api"] == "D3D12" and capture["shader_model"] == "6.6", "capture API/shader model mismatch")
    require(capture["api_frame_number"] is None, "NoFrameNumber sentinel must not be treated as a valid frame")
    require(capture["exact_source_binary_match"] is False, "source/binary identity is unproven")
    view = p["view"]
    require(len(view["extent"]) == 2 and all(type(v) is int and v > 0 for v in view["extent"]), "invalid extent")
    w, h = view["extent"]
    require(len(view["rect_min_max"]) == 4 and all(type(v) is int for v in view["rect_min_max"]), "invalid view rect")
    x0, y0, x1, y1 = view["rect_min_max"]
    require(0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h, "view rect exceeds allocation or is empty")
    require(view["samples"] == 1 and view["depth_convention"] == "infinite-reversed-z", "sample/depth convention mismatch")
    require(view["extent"] == [1424,1040] and view["rect_min_max"] == [0,0,1421,1035] and view["jitter"] == [0,0,0,0], "view differs from fixed capture")
    attachments = p["attachments"]
    require(len(attachments) == 5, "five attachments required")
    for slot, (a, expected) in enumerate(zip(attachments, FORMATS)):
        require(a["slot"] == slot, "attachment slots must be unique and ordered")
        actual = tuple(a[k] for k in ("name", "resource_format", "view_format", "falcor_format", "storage_order"))
        require(actual == expected, f"attachment {slot} format/storage mismatch")
        require(a["clear"] == ([0,0,0,1] if slot == 0 else [0,0,0,0]), f"attachment {slot} clear mismatch")
        require(a["valid_channels"] == ("RGBA" if slot < 4 else ""), "bound attachment does not imply valid shader output")
        require(a["rgb_transfer"] == ("srgb" if slot == 3 else "linear") and a["alpha_transfer"] == "linear", "sRGB applies to C RGB only")
    d = p["depth_stencil"]
    require((d["resource_format"], d["view_format"], d["falcor_format"]) ==
            ("R32G8X24_TYPELESS", "D32_FLOAT_S8X24_UINT", "D32FloatS8Uint"), "depth/stencil format mismatch")
    require(d["clear_depth"] == 0 and d["clear_stencil"] == 0, "reversed-Z clear mismatch")
    require(d["basepass_depth_read_only_view"] is True and d["basepass_stencil_read_only_view"] is False, "captured DSV access mismatch")
    model = p["shading_models"]
    id_mask, flags = model["id_mask"], model["flags_mask"]
    require(type(id_mask) is int and type(flags) is int and 0 <= id_mask <= 255 and 0 <= flags <= 255, "masks must be uint8")
    require(id_mask & flags == 0, "model and flag masks overlap")
    require(id_mask == 31 and flags == 224, "captured profile requires 5 model bits")
    require(model["observed_packed_alpha"] == 129 and model["default_lit_id"] == 1 and model["observed_surface_ids"] == [1], "observed model bytes mismatch")
    require(model["skip_velocity_mask_source_interpretation"] == 128 and
            (model["default_lit_id"] | model["skip_velocity_mask_source_interpretation"]) == model["observed_packed_alpha"],
            "skip-velocity flag contradicts observed packing")
    base = p["pso"]["basepass"]
    require(p["pso"]["prepass"] == {"depth_test": "GreaterEqual", "depth_write": True}, "prepass state mismatch")
    expected_state = {"depth_test": "GreaterEqual", "depth_write": False, "stencil_test": "Always", "stencil_pass": "Replace",
                      "stencil_fail": "Keep", "stencil_depth_fail": "Keep", "stencil_reference": 134,
                      "stencil_write_mask": 246, "stencil_read_mask": 255, "cull": "Back", "front_ccw": True,
                      "fill": "Solid", "blend": False, "attachment_write_masks": [15]*5, "shader_output_slots": [0,1,2,3]}
    require(base == expected_state, "captured BasePass state/output mismatch")
    exposure = p["exposure"]
    fields = ["pre_exposure", "inverse_pre_exposure", "current_eye_adaptation"]
    for field in fields:
        positive(exposure[field]["value"], field)
    require([exposure[f]["source"] for f in fields] == ["View.PreExposure", "View.OneOverPreExposure", "EyeAdaptation.float4[0].x"], "exposure sources must remain distinct")
    pre, inverse, current = [exposure[f]["value"] for f in fields]
    require(exposure["pre_exposure"]["byte_offset"] == 2568 and exposure["inverse_pre_exposure"]["byte_offset"] == 2572, "exposure View offsets mismatch")
    require(math.isclose(pre * inverse, 1, rel_tol=1e-6), "preExposure reciprocal mismatch")
    # Fixed-capture evidence values, not a rule that exposures must differ in every frame.
    require(math.isclose(pre, 1.0749151706695557, rel_tol=0, abs_tol=1e-8) and
            math.isclose(current, 1.0762039422988892, rel_tol=0, abs_tol=1e-8), "capture exposures changed or conflated")
    require(math.isclose(exposure["tonemap_global_multiplier"], current/pre, rel_tol=1e-6), "tonemap exposure ratio mismatch")
    require(exposure["automatic"] is True and exposure["local_exposure_active"] is True, "capture exposure features mismatch")
    stages = p["stages"]
    require(stages["opaque_end"] == max(stages["basepass_draws"]) == 1853, "opaque comparison boundary mismatch")
    require(stages["depth_clear"] < min(stages["prepass_draws"]) and
            max(stages["prepass_draws"]) < min(stages["attachment_clears"]) and
            max(stages["attachment_clears"]) < min(stages["basepass_draws"]), "invalid initialization order")
    require(stages["opaque_end"] < stages["sky_end"] < stages["stencil_only_clear"] < stages["ssgi_composite"] < stages["directional_light_end"] < stages["eye_adaptation"] < stages["tonemap_end"], "invalid stage order")
    require(exposure["current_eye_adaptation"]["event"] == stages["eye_adaptation"], "exposure event mismatch")
    files = p["evidence"]["files"]
    require(isinstance(files, list) and len(files) == 7 and len({f["path"] for f in files}) == 7, "seven unique evidence entries required")
    require({f["path"] for f in files} >= {"manifest.json", "analysis.json", "pipeline-1853.json", "view-layout-evidence.json"}, "missing evidence manifest entries")
    for entry in files:
        require(Path(entry["path"]).name == entry["path"] and re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]) is not None, "invalid evidence path/hash")
    if evidence_dir is not None:
        root = Path(evidence_dir).resolve()
        for entry in files:
            path = (root / entry["path"]).resolve()
            require(path.is_relative_to(root) and path.is_file(), "missing or out-of-root evidence: " + entry["path"])
            require(hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], "evidence hash mismatch: " + entry["path"])
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        analysis = json.loads((root / "analysis.json").read_text(encoding="utf-8"))
        require(capture["sha256"] == manifest["capture"]["Hash"].lower() and capture["bytes"] == manifest["captureBytes"], "capture identity mismatch")
        require(view["extent"] == analysis["extent"] and view["rect_min_max"] == analysis["viewRect"], "view differs from capture evidence")
        require(pre == analysis["exposure"]["preExposure"] and current == analysis["exposure"]["eyeAdaptation"]["float4"][0][0], "exposure differs from evidence")

def validate(profile, evidence_dir=None):
    try:
        _validate(profile, evidence_dir)
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("malformed or missing profile field: " + str(error)) from error

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path, nargs="?", default=DEFAULT_PROFILE)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        validate(profile, args.evidence_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f"INVALID: {error}\n")
    print("M0_REFERENCE_PROFILE_VALID" + (" (evidence hashes verified)" if args.evidence_dir else " (profile only)"))

if __name__ == "__main__":
    main()
