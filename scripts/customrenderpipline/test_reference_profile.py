"""Regression cases for dangerous capture-contract mistakes; runs without GPU or UE."""
import copy
import json
from pathlib import Path
import unittest
from validate_reference import DEFAULT_PROFILE, validate

class ReferenceProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))

    def rejected(self, mutate, message):
        mutated = copy.deepcopy(self.profile)
        mutate(mutated)
        with self.assertRaisesRegex(ValueError, message):
            validate(mutated)

    def test_valid_capture(self):
        validate(self.profile)

    def test_missing_depth_stencil(self):
        self.rejected(lambda p: p.pop("depth_stencil"), "missing")

    def test_color_view_cannot_replace_srgb(self):
        self.rejected(lambda p: p["attachments"][3].update(view_format="B8G8R8A8_UNORM"), "format")

    def test_depth_format_cannot_lose_stencil(self):
        self.rejected(lambda p: p["depth_stencil"].update(falcor_format="D32Float"), "format")

    def test_out_of_bounds_view(self):
        self.rejected(lambda p: p["view"].update(rect_min_max=[0,0,1425,1035]), "exceeds")

    def test_empty_view(self):
        self.rejected(lambda p: p["view"].update(rect_min_max=[0,0,0,1035]), "empty")

    def test_model_flag_overlap(self):
        self.rejected(lambda p: p["shading_models"].update(flags_mask=240), "overlap")

    def test_upstream_four_bit_mask_is_wrong_for_this_capture(self):
        self.rejected(lambda p: p["shading_models"].update(id_mask=15, flags_mask=240), "5 model bits")

    def test_bound_target_is_not_valid_customdata(self):
        self.rejected(lambda p: p["attachments"][4].update(valid_channels="RGBA"), "valid shader output")

    def test_alpha_remains_linear(self):
        self.rejected(lambda p: p["attachments"][3].update(alpha_transfer="srgb"), "C RGB only")

    def test_no_basepass_depth_write(self):
        self.rejected(lambda p: p["pso"]["basepass"].update(depth_write=True), "state")

    def test_exposure_sources_cannot_be_aliased(self):
        self.rejected(lambda p: p["exposure"]["current_eye_adaptation"].update(source="View.PreExposure"), "distinct")

    def test_exposure_values_cannot_be_conflated(self):
        self.rejected(lambda p: p["exposure"]["current_eye_adaptation"].update(value=p["exposure"]["pre_exposure"]["value"]), "conflated")

    def test_nonfinite_exposure(self):
        self.rejected(lambda p: p["exposure"]["pre_exposure"].update(value=float("nan")), "finite")

    def test_final_frame_is_not_opaque_end(self):
        self.rejected(lambda p: p["stages"].update(opaque_end=4193), "opaque")

    def test_capture_identity(self):
        self.rejected(lambda p: p["capture"].update(sha256="0"*64), "identity")

    def test_missing_evidence(self):
        self.rejected(lambda p: p["evidence"].update(files=[]), "evidence")

    def test_evidence_path_traversal(self):
        self.rejected(lambda p: p["evidence"]["files"][-1].update(path="../unrelated"), "path/hash")

    def test_late_color_clear(self):
        self.rejected(lambda p: p["stages"]["attachment_clears"].__setitem__(-1,5000), "initialization")

    def test_late_depth_clear(self):
        self.rejected(lambda p: p["stages"].update(depth_clear=1900), "initialization")

    def test_skip_velocity_mask_matches_observed_packing(self):
        self.rejected(lambda p: p["shading_models"].update(skip_velocity_mask_source_interpretation=32), "skip-velocity")

if __name__ == "__main__":
    unittest.main()
