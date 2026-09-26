"""CPU fixture tests; importing the smoke must not import Falcor or NumPy."""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("native_sampler_smoke.py")


class NativeSamplerFixtureTests(unittest.TestCase):
    def load_smoke(self):
        self.assertTrue(SCRIPT.is_file(), "The native sampler smoke is not implemented")
        spec = importlib.util.spec_from_file_location("sampler_fixture_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        before = set(sys.modules)
        spec.loader.exec_module(module)
        self.assertNotIn("falcor", set(sys.modules) - before)
        self.assertNotIn("numpy", set(sys.modules) - before)
        return module

    def test_dds_contains_exact_nine_authored_float_mips(self):
        smoke = self.load_smoke()
        with tempfile.TemporaryDirectory() as directory:
            files = smoke.write_fixtures(Path(directory))
            data = files["texture"].read_bytes()
            self.assertEqual(data[:4], b"DDS ")
            header = struct.unpack_from("<31I", data, 4)
            self.assertEqual((header[0], header[2], header[3], header[4], header[6]), (124, 256, 256, 4096, 9))
            self.assertEqual(struct.unpack_from("<5I", data, 128), (2, 3, 0, 1, 0))
            offset = 148
            colors = []
            for mip in range(9):
                color = struct.pack("<4f", mip / 8, (8 - mip) / 8, mip % 2, 1)
                length = (256 >> mip) ** 2 * 16
                self.assertEqual(data[offset:offset + length], color * ((256 >> mip) ** 2))
                offset += length
                colors.append(color)
            self.assertEqual(len(data), offset)
            self.assertEqual(len(set(colors)), 9)
            self.assertLess(len(data), 2 * 1024 * 1024)
            for kind in ("Compute", "Fullscreen", "Mesh"):
                shader = files[kind].read_text(encoding="utf-8")
                self.assertIn(".SampleGrad(", shader)
                self.assertIn("32.0 / 256.0", shader)
                self.assertIn("1.0 / 256.0", shader)
                self.assertIn(smoke.SAMPLE_SOURCE, shader)

    def test_properties_cover_all_executors_without_mutating_descriptors(self):
        smoke = self.load_smoke()
        for kind in ("Compute", "Fullscreen", "Mesh"):
            for descriptor in ({}, {"max_anisotropy": 1}, {"max_anisotropy": 8}, {"max_anisotropy": 16}):
                with self.subTest(kind=kind, descriptor=descriptor):
                    properties = smoke.pass_properties(kind, Path("fixture.slang"), descriptor)
                    self.assertEqual(properties["samplers"]["sourceSampler"], descriptor)
                    self.assertIsNot(properties["samplers"]["sourceSampler"], descriptor)
                    self.assertEqual(properties["resources"][0]["mip_count"], 9)
                    self.assertEqual(properties["resources"][0]["binding"], "sourceTexture")
                    if kind == "Compute":
                        self.assertEqual(properties["dispatch"], {"threads": [32, 16, 1]})
                    elif kind == "Mesh":
                        self.assertEqual(properties["colorTargets"][0]["size"], [32, 16])
                    else:
                        self.assertEqual(properties["resources"][1]["slot"], 0)

    def test_rejection_corpus_has_strict_types_bounds_and_closed_keys(self):
        smoke = self.load_smoke()
        cases = dict(smoke.invalid_samplers())
        for label in ("bool_true", "bool_false", "float_integral", "float_fractional", "zero", "seventeen", "negative", "null", "string", "array", "object", "unknown"):
            self.assertIn(label, cases)
        self.assertIs(cases["bool_true"]["max_anisotropy"], True)
        self.assertIs(type(cases["float_integral"]["max_anisotropy"]), float)
        self.assertEqual(cases["unknown"], {"max_anisotropy": 8, "unexpected": True})

    def test_embedded_numpy_search_path_is_added_before_gpu_imports(self):
        source = SCRIPT.read_text(encoding="utf-8")
        run = source[source.index("def run(host, output):"):]
        imports = run[:run.index("import numpy as np")]
        self.assertIn('ROOT / "build/m0-evidence/python"', imports)
        self.assertIn("sys.path.insert", imports)

    def test_output_directory_is_fresh_and_cannot_escape_owned_parent(self):
        smoke = self.load_smoke()
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "owned"
            first = smoke.create_output(parent)
            second = smoke.create_output(parent)
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, parent.resolve())
            sentinel = first / "sentinel"
            sentinel.write_text("do not overwrite", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                smoke.create_output(parent, first)
            with self.assertRaises(ValueError):
                smoke.create_output(parent, parent.parent / "outside")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not overwrite")


if __name__ == "__main__":
    unittest.main()
