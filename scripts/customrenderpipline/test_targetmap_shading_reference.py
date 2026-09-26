"""CPU-only manifest and raw half-float reference contracts (no replay imports)."""

from contextlib import redirect_stdout
import hashlib
import importlib
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

try:
    reference = importlib.import_module("targetmap_shading_reference")
except ModuleNotFoundError as exc:
    if exc.name != "targetmap_shading_reference":
        raise
    reference = None


CAPTURE_HASH = "059eef7978d1c32039ad4bd21b5b0c59574c393996fb842b37f3a9e4a87edb2f"


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(reference, "offline reference module is not implemented")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self, name="left", values=None, view_rect=None):
        directory = self.root / name
        directory.mkdir()
        if values is None:
            values = np.ones((2, 3, 4), dtype="<f2")
        raw = np.asarray(values, dtype="<f2").tobytes()
        checkpoints = []
        for event in (2793, 2962):
            filename = f"E{event}-SceneColor.rgba16f"
            (directory / filename).write_bytes(raw)
            checkpoints.append({
                "event": event, "resource": "ResourceId::955",
                "format": "R16G16B16A16_FLOAT", "width": values.shape[1],
                "height": values.shape[0], "view_rect": view_rect or [0, 0, 2, 1],
                "subresource": {"mip": 0, "slice": 0, "sample": 0},
                "file": filename, "byte_size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        manifest = {
            "schema": "crp-rdc-shading-reference-v1", "role": "offline_reference_only",
            "capture": {"path": "E:/rdc/ue/2.rdc", "sha256": CAPTURE_HASH},
            "full_renderer_parity": False, "checkpoints": checkpoints,
        }
        path = directory / "manifest.json"
        self.save(path, manifest)
        return path, manifest

    @staticmethod
    def save(path, manifest):
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def directory_link(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if sys.platform != "win32":
                raise
            subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
                           check=True, capture_output=True, timeout=10)
        self.addCleanup(link.rmdir if link.is_dir() and not link.is_symlink() else link.unlink)

    @staticmethod
    def cli(*args):
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = reference.main([str(arg) for arg in args])
        return code, json.loads(stdout.getvalue())

    def test_validate_tiny_reference_has_json_safe_region_and_channel_counts(self):
        path, _ = self.fixture()
        report = reference.validate_reference(path)
        self.assertTrue(report["accepted"])
        self.assertFalse(report["full_renderer_parity"])
        self.assertEqual(report["operation"], "validate")
        self.assertEqual([c["event"] for c in report["checkpoints"]], [2793, 2962])
        visible = report["checkpoints"][0]["visible"]
        padding = report["checkpoints"][0]["padding"]
        self.assertEqual(visible["rgb"]["pixel_count"], 2)
        self.assertEqual(visible["rgb"]["scalar_count"], 6)
        self.assertEqual(visible["alpha"]["scalar_count"], 2)
        self.assertEqual(padding["rgb"]["pixel_count"], 4)
        self.assertEqual(padding["alpha"]["scalar_count"], 4)
        self.assertEqual(visible["rgb"]["bit_exact_scalar_count"], 6)
        self.assertEqual(visible["rgb"]["mae"], 0.0)
        json.dumps(report, allow_nan=False)

    def test_reject_wrong_top_level_identity(self):
        path, manifest = self.fixture()
        cases = [("schema", "other"), ("role", "production_input"),
                 ("full_renderer_parity", True), ("full_renderer_parity", 0),
                 ("capture", {"path": "E:/rdc/ue/2.rdc", "sha256": "0" * 64})]
        for field, value in cases:
            changed = dict(manifest, **{field: value})
            with self.subTest(field=field, value=value):
                self.save(path, changed)
                with self.assertRaises(ValueError):
                    reference.validate_reference(path)

    def test_reject_wrong_checkpoint_contract(self):
        path, manifest = self.fixture()
        checkpoint = manifest["checkpoints"][0]
        cases = [("event", 2794), ("event", 2793.0),
                 ("resource", "ResourceId::956"), ("format", "RGBA8_UNORM"),
                 ("sha256", "0" * 64), ("byte_size", 49), ("byte_size", 48.0),
                 ("width", 0), ("width", True), ("height", -1),
                 ("width", 1000000), ("height", 3),
                 ("view_rect", [-1, 0, 2, 1]), ("view_rect", [0, 0, 4, 1]),
                 ("view_rect", [1, 0, 3, 1]), ("view_rect", [0, 1, 2, 0]),
                 ("view_rect", [0, 0, 2.0, 1]), ("view_rect", [0, 0, 2]),
                 ("subresource", {"mip": 1, "slice": 0, "sample": 0}),
                 ("subresource", {"mip": 0, "slice": 1, "sample": 0}),
                 ("subresource", {"mip": 0, "slice": 0, "sample": 1}),
                 ("subresource", {"mip": 0, "slice": 0, "sample": False})]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                manifest["checkpoints"][0] = dict(checkpoint, **{field: value})
                self.save(path, manifest)
                with self.assertRaises(ValueError):
                    reference.validate_reference(path)

    def test_reject_duplicate_missing_or_extra_event(self):
        path, manifest = self.fixture()
        original = manifest["checkpoints"]
        for checkpoints in ([], original[:1], [original[0], original[0]],
                            original + [original[0]]):
            with self.subTest(count=len(checkpoints)):
                self.save(path, dict(manifest, checkpoints=checkpoints))
                with self.assertRaises(ValueError):
                    reference.validate_reference(path)

    def test_reject_actual_file_length_and_hash_tampering(self):
        path, manifest = self.fixture()
        raw_path = path.parent / manifest["checkpoints"][0]["file"]
        original = raw_path.read_bytes()
        for raw in (original[:-1], original + b"\x00", b"\x00" * len(original)):
            with self.subTest(length=len(raw)):
                raw_path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    reference.validate_reference(path)

    def test_reject_path_traversal_absolute_and_windows_paths(self):
        path, manifest = self.fixture()
        outside = self.root / "outside.rgba16f"
        outside.write_bytes((path.parent / manifest["checkpoints"][0]["file"]).read_bytes())
        for filename in ("../outside.rgba16f", "..\\outside.rgba16f", str(outside),
                         "C:\\outside.rgba16f", "\\\\server\\share\\raw"):
            with self.subTest(filename=filename):
                manifest["checkpoints"][0]["file"] = filename
                self.save(path, manifest)
                with self.assertRaises(ValueError):
                    reference.validate_reference(path)

    def test_reject_symlink_escape(self):
        path, manifest = self.fixture()
        outside = self.root / "outside"
        outside.mkdir()
        raw_path = path.parent / manifest["checkpoints"][0]["file"]
        (outside / "raw.rgba16f").write_bytes(raw_path.read_bytes())
        link = path.parent / "link"
        # A Windows junction covers resolved containment without symlink privilege.
        self.directory_link(link, outside)
        manifest["checkpoints"][0]["file"] = "link/raw.rgba16f"
        self.save(path, manifest)
        with self.assertRaises(ValueError):
            reference.validate_reference(path)

    def test_visible_nonfinites_fail_validation_even_if_self_bit_exact(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            for channel in (0, 3):
                with self.subTest(value=value, channel=channel):
                    values = np.ones((2, 3, 4), dtype="<f2")
                    values[0, 0, channel] = value
                    path, _ = self.fixture(f"nonfinite-{channel}-{value}", values)
                    report = reference.validate_reference(path)
                    self.assertFalse(report["accepted"])
                    group = "rgb" if channel == 0 else "alpha"
                    metrics = report["checkpoints"][0]["visible"][group]
                    self.assertEqual(metrics["nonfinite"]["left"]["scalar_count"], 1)
                    self.assertEqual(metrics["bit_mismatch_scalar_count"], 0)
                    json.dumps(report, allow_nan=False)

    def test_padding_nonfinites_are_explicit_but_do_not_fail_visible_acceptance(self):
        values = np.ones((2, 3, 4), dtype="<f2")
        values[1, 1] = [np.nan, np.inf, -np.inf, np.nan]
        path, _ = self.fixture(values=values)
        report = reference.validate_reference(path)
        self.assertTrue(report["accepted"])
        counts = report["checkpoints"][0]["padding"]["rgb"]["nonfinite"]["left"]
        self.assertEqual(counts, {"nan": 1, "positive_infinity": 1,
                                 "negative_infinity": 1, "scalar_count": 3, "pixel_count": 1})
        json.dumps(report, allow_nan=False)

    def test_compare_identical_visible_bits_ignores_raw_filenames_and_event_order(self):
        left, _ = self.fixture()
        right, manifest = self.fixture("right")
        checkpoint = manifest["checkpoints"][0]
        (right.parent / checkpoint["file"]).rename(right.parent / "renamed.raw")
        checkpoint["file"] = "renamed.raw"
        manifest["checkpoints"].reverse()
        self.save(right, manifest)
        report = reference.compare_references(left, right)
        self.assertTrue(report["accepted"])
        self.assertTrue(report["reference_repeatability_bit_exact_visible"])
        self.assertFalse(report["full_renderer_parity"])
        self.assertEqual(report["operation"], "compare")

    def test_compare_rejects_different_semantic_identity(self):
        left, _ = self.fixture()
        right, _ = self.fixture("right", view_rect=[1, 0, 2, 1])
        with self.assertRaisesRegex(ValueError, "identity"):
            reference.compare_references(left, right)

    def test_compare_rejects_different_shape_even_with_same_byte_length(self):
        left, _ = self.fixture()
        right, _ = self.fixture("right", np.ones((3, 2, 4), dtype="<f2"))
        with self.assertRaisesRegex(ValueError, "identity"):
            reference.compare_references(left, right)

    def test_signed_zero_is_numerically_equal_but_one_bit_rank_ulp_apart(self):
        values = np.zeros((2, 3, 4), dtype="<f2")
        left, _ = self.fixture(values=values)
        values[0, 0, 0] = -0.0
        right, _ = self.fixture("right", values)
        report = reference.compare_references(left, right)
        metrics = report["checkpoints"][0]["visible"]["rgb"]
        self.assertFalse(report["accepted"])
        self.assertFalse(report["reference_repeatability_bit_exact_visible"])
        self.assertEqual(metrics["numeric_equal_scalar_count"], 6)
        self.assertEqual(metrics["numeric_equal_pixel_count"], 2)
        self.assertEqual(metrics["bit_exact_scalar_count"], 5)
        self.assertEqual(metrics["bit_exact_pixel_count"], 1)
        self.assertEqual(metrics["max_ulp"], 1)
        self.assertEqual(metrics["max_abs"], 0.0)

    def test_one_half_ulp_and_alpha_error_have_separate_exact_metrics(self):
        left, _ = self.fixture()
        values = np.ones((2, 3, 4), dtype="<f2")
        values[0, 0, :2] = np.nextafter(np.float16(1), np.float16(2))
        values[0, 1, 3] = 2
        right, _ = self.fixture("right", values)
        report = reference.compare_references(left, right)
        rgb = report["checkpoints"][0]["visible"]["rgb"]
        alpha = report["checkpoints"][0]["visible"]["alpha"]
        self.assertEqual(rgb["numeric_mismatch_scalar_count"], 2)
        self.assertEqual(rgb["numeric_mismatch_pixel_count"], 1)
        self.assertEqual(rgb["bit_mismatch_scalar_count"], 2)
        self.assertEqual(rgb["bit_mismatch_pixel_count"], 1)
        self.assertEqual(rgb["max_ulp"], 1)
        self.assertAlmostEqual(rgb["mae"], (2 / 1024) / 6)
        self.assertAlmostEqual(rgb["rmse"], ((2 / 1024**2) / 6) ** 0.5)
        self.assertEqual(rgb["max_abs"], 1 / 1024)
        self.assertEqual(alpha["mae"], 0.5)
        self.assertEqual(alpha["max_abs"], 1)

    def test_padding_bit_differences_do_not_count_as_visible_mismatch(self):
        left, _ = self.fixture()
        values = np.ones((2, 3, 4), dtype="<f2")
        values[1, 2, 0] = 7
        right, _ = self.fixture("right", values)
        report = reference.compare_references(left, right)
        self.assertTrue(report["accepted"])
        self.assertTrue(report["reference_repeatability_bit_exact_visible"])
        self.assertEqual(report["checkpoints"][0]["padding"]["rgb"]["bit_mismatch_scalar_count"], 1)

    def test_all_nonfinite_and_empty_padding_remain_json_safe(self):
        values = np.full((1, 1, 4), np.nan, dtype="<f2")
        left, _ = self.fixture(values=values, view_rect=[0, 0, 1, 1])
        right, _ = self.fixture("right", values, view_rect=[0, 0, 1, 1])
        report = reference.compare_references(left, right)
        self.assertFalse(report["accepted"])
        self.assertTrue(report["reference_repeatability_bit_exact_visible"])
        visible = report["checkpoints"][0]["visible"]["rgb"]
        padding = report["checkpoints"][0]["padding"]["rgb"]
        self.assertEqual(visible["finite_pair_count"], 0)
        self.assertIsNone(visible["mae"])
        self.assertIsNone(visible["max_ulp"])
        self.assertEqual(padding["scalar_count"], 0)
        self.assertIsNone(padding["rmse"])
        json.dumps(report, allow_nan=False)

    def test_nonzero_view_origin_is_respected(self):
        values = np.ones((2, 3, 4), dtype="<f2")
        left, _ = self.fixture(values=values, view_rect=[1, 1, 2, 1])
        values[0, 0, 0] = np.nan
        right, _ = self.fixture("right", values, view_rect=[1, 1, 2, 1])
        report = reference.compare_references(left, right)
        self.assertTrue(report["accepted"])
        self.assertEqual(report["checkpoints"][0]["visible"]["rgb"]["pixel_count"], 2)

    def test_nonzero_view_extent_includes_its_last_pixel(self):
        values = np.ones((2, 3, 4), dtype="<f2")
        left, _ = self.fixture(values=values, view_rect=[1, 1, 2, 1])
        values[1, 2, 0] = 7
        right, _ = self.fixture("right", values, view_rect=[1, 1, 2, 1])
        report = reference.compare_references(left, right)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["checkpoints"][0]["visible"]["rgb"]["bit_mismatch_pixel_count"], 1)
        self.assertEqual(report["checkpoints"][0]["padding"]["rgb"]["bit_mismatch_pixel_count"], 0)

    def test_final_checkpoint_is_not_skipped(self):
        left, _ = self.fixture()
        right, manifest = self.fixture("right")
        checkpoint = manifest["checkpoints"][1]
        values = np.ones((2, 3, 4), dtype="<f2")
        values[0, 0, 3] = 2
        raw = values.tobytes()
        (right.parent / checkpoint["file"]).write_bytes(raw)
        checkpoint["sha256"] = hashlib.sha256(raw).hexdigest()
        self.save(right, manifest)
        report = reference.compare_references(left, right)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["checkpoints"][0]["visible"]["alpha"]["bit_mismatch_scalar_count"], 0)
        self.assertEqual(report["checkpoints"][1]["visible"]["alpha"]["bit_mismatch_scalar_count"], 1)

    def test_negative_half_ulp_and_cross_zero_rank(self):
        values = np.zeros((2, 3, 4), dtype="<f2")
        values[0, 0, :3] = [-1, -np.nextafter(np.float16(0), np.float16(1)), -0.0]
        left, _ = self.fixture(values=values)
        values[0, 0, :3] = [np.nextafter(np.float16(-1), np.float16(-2)),
                            np.nextafter(np.float16(0), np.float16(1)), +0.0]
        right, _ = self.fixture("right", values)
        metrics = reference.compare_references(left, right)["checkpoints"][0]["visible"]["rgb"]
        self.assertEqual(metrics["max_ulp"], 3)  # -minsub, -0, +0, +minsub
        self.assertEqual(metrics["numeric_mismatch_scalar_count"], 2)
        self.assertEqual(metrics["bit_mismatch_scalar_count"], 3)

    def test_nan_payloads_remain_bit_distinct_and_right_nonfinites_are_counted(self):
        values = np.ones((2, 3, 4), dtype="<f2")
        values.view("<u2")[0, 0, 0] = 0x7c01  # signaling NaN payload
        left, _ = self.fixture(values=values)
        values.view("<u2")[0, 0, 0] = 0x7e02
        values[0, 1, 0] = np.inf
        right, _ = self.fixture("right", values)
        report = reference.compare_references(left, right)
        metrics = report["checkpoints"][0]["visible"]["rgb"]
        self.assertFalse(report["accepted"])
        self.assertEqual(metrics["bit_mismatch_scalar_count"], 2)
        self.assertEqual(metrics["nonfinite"]["left"]["scalar_count"], 1)
        self.assertEqual(metrics["nonfinite"]["right"]["scalar_count"], 2)
        self.assertEqual(metrics["nonfinite"]["pair_count"], 2)
        self.assertEqual(metrics["finite_pair_count"], 4)
        json.dumps(report, allow_nan=False)

    def test_hdr_error_accumulation_does_not_overflow_half(self):
        values = np.full((2, 3, 4), 65504, dtype="<f2")
        left, _ = self.fixture(values=values)
        right, _ = self.fixture("right", -values)
        metrics = reference.compare_references(left, right)["checkpoints"][0]["visible"]["rgb"]
        self.assertEqual(metrics["mae"], 131008)
        self.assertEqual(metrics["rmse"], 131008)
        self.assertEqual(metrics["max_abs"], 131008)

    def test_malformed_or_missing_manifest_fields_raise_value_error(self):
        path, manifest = self.fixture()
        for text in ("{", "[]", "null", json.dumps(dict(manifest, capture=[])),
                     json.dumps(dict(manifest, checkpoints=[None, None]))):
            with self.subTest(text=text[:40]):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    reference.validate_reference(path)

    def test_cli_validate_and_compare_output_and_exit_status(self):
        left, _ = self.fixture()
        values = np.ones((2, 3, 4), dtype="<f2")
        values[0, 0, 0] = 2
        right, _ = self.fixture("right", values)
        script = str(Path(reference.__file__))
        cases = [("validate", [left], 0), ("compare", [left, left], 0),
                 ("compare", [left, right], 1),
                 ("validate", [self.root / "missing" / "manifest.json"], 2)]
        for index, (operation, paths, code) in enumerate(cases):
            with self.subTest(operation=operation, code=code):
                output = self.root / f"report-{index}.json"
                result = subprocess.run([sys.executable, script, operation, *map(str, paths),
                                         "--out", str(output)], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, code, result.stderr)
                stdout = json.loads(result.stdout)
                self.assertEqual(stdout, json.loads(output.read_text(encoding="utf-8")))
                self.assertEqual(stdout["accepted"], code == 0)
                self.assertFalse(stdout["full_renderer_parity"])

    def test_cli_out_cannot_overwrite_manifest_or_raw_reference(self):
        for kind in ("manifest", "raw"):
            with self.subTest(kind=kind):
                path, manifest = self.fixture(kind)
                output = path if kind == "manifest" else path.parent / manifest["checkpoints"][0]["file"]
                original = {p: p.read_bytes() for p in path.parent.iterdir()}
                code, report = self.cli("validate", path, "--out", output)
                self.assertEqual({p: p.read_bytes() for p in original}, original)
                self.assertEqual(code, 2)
                self.assertFalse(report["accepted"])

    def test_cli_out_cannot_create_any_file_inside_reference_directory(self):
        path, _ = self.fixture()
        directory = path.parent / "audit"
        directory.mkdir()
        output = directory / "new-report.json"
        code, report = self.cli("validate", path, "--out", output)
        self.assertFalse(output.exists())
        self.assertEqual(code, 2)
        self.assertFalse(report["accepted"])

    def test_cli_compare_out_protects_both_reference_directories(self):
        left, _ = self.fixture()
        right, _ = self.fixture("right")
        for path in (left, right):
            with self.subTest(reference=path.parent.name):
                output = path.parent / "new-report.json"
                code, report = self.cli("compare", left, right, "--out", output)
                self.assertFalse(output.exists())
                self.assertEqual(code, 2)
                self.assertFalse(report["accepted"])

    def test_cli_out_rejects_symlink_or_junction_alias_into_reference(self):
        path, _ = self.fixture()
        alias = self.root / "alias"
        self.directory_link(alias, path.parent)
        code, report = self.cli("validate", path, "--out", alias / "new-report.json")
        self.assertFalse((path.parent / "new-report.json").exists())
        self.assertEqual(code, 2)
        self.assertFalse(report["accepted"])

    def test_cli_out_preserves_any_preexisting_external_output(self):
        path, _ = self.fixture()
        output = self.root / "existing-output.json"
        sentinel = b"immutable existing evidence\n"
        output.write_bytes(sentinel)
        code, report = self.cli("validate", path, "--out", output)
        self.assertEqual(output.read_bytes(), sentinel)
        self.assertEqual(code, 2)
        self.assertFalse(report["accepted"])

    def test_cli_out_cannot_replace_invalid_manifest_or_create_missing_manifest(self):
        for exists in (False, True):
            with self.subTest(exists=exists):
                directory = self.root / str(exists)
                directory.mkdir()
                path = directory / "manifest.json"
                if exists:
                    path.write_bytes(b"{invalid original evidence")
                code, report = self.cli("validate", path, "--out", path)
                if exists:
                    self.assertEqual(path.read_bytes(), b"{invalid original evidence")
                else:
                    self.assertFalse(path.exists())
                self.assertEqual(code, 2)
                self.assertFalse(report["accepted"])

    def test_cli_stdout_only_does_not_create_output(self):
        path, _ = self.fixture()
        original = sorted(self.root.rglob("*"))
        code, report = self.cli("validate", path)
        self.assertEqual(code, 0)
        self.assertTrue(report["accepted"])
        self.assertEqual(sorted(self.root.rglob("*")), original)


if __name__ == "__main__":
    unittest.main()
