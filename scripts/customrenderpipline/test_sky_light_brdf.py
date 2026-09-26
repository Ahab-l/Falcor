"""Source-algorithm and declaration contracts for the GPU PreintegratedGF port."""
import importlib.util
import ctypes
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


class SkyLightBRDFTests(unittest.TestCase):
    def factory(self):
        self.assertIsNotNone(importlib.util.find_spec('sky_light_brdf'), 'GPU PreintegratedGF graph is missing')
        from sky_light_brdf import sky_light_brdf_fragment
        return sky_light_brdf_fragment

    def test_source_storage_and_dispatch(self):
        graph = self.factory()()
        self.assertEqual(graph['edges'], [])
        self.assertEqual(graph['outputs'], ['PreintegratedGF.preIntegratedGF', 'PreintegratedGF.integratedAB'])
        node, = graph['nodes']
        self.assertEqual(node['file_inputs'], ['shader.file'])
        p = node['properties']
        self.assertEqual(p['dispatch'], {'threads': [128, 32, 1]})
        self.assertEqual(p['shader']['floating_point_mode'], 'precise')
        self.assertEqual(p['resources'], [
            {'name': 'preIntegratedGF', 'binding': 'gPreintegratedGF', 'direction': 'output',
             'kind': 'texture2D', 'format': 'RG16Unorm', 'size': [128, 32]},
            {'name': 'integratedAB', 'binding': 'gIntegratedAB', 'direction': 'output',
             'kind': 'texture2D', 'format': 'RG32Float', 'size': [128, 32]}])
        self.assertNotIn('uniforms', p)
        self.assertEqual(self.factory()(prefix='Probe')['outputs'][0], 'Probe.preIntegratedGF')
        for name in ('', 'A.B', '1Probe', None):
            with self.assertRaisesRegex(ValueError, 'prefix'):
                self.factory()(prefix=name)


    def test_source_export_reproduces_checked_in_evidence(self):
        self.factory()
        from export_sky_light_brdf_source import export, DEST
        with tempfile.TemporaryDirectory() as directory:
            export(Path(directory))
            for path in Path(directory).iterdir():
                self.assertEqual(path.read_bytes(), (DEST / path.name).read_bytes(), path.name)
        manifest = json.loads((DEST / 'PreintegratedGFSource.json').read_text())
        self.assertEqual(manifest['implementation'], 'GPU port of the original CPU algorithm')
        self.assertEqual(manifest['contract']['sample_count'], 128)
        self.assertFalse(manifest['capture_inputs'])
        for item in manifest['excerpts']:
            original = Path(item['source']).read_bytes()
            selected = original[item['byte_offset']:item['byte_offset'] + item['bytes']]
            excerpt = (DEST / item['output']).read_bytes()
            self.assertEqual(selected, excerpt[item['output_byte_offset']:item['output_byte_offset'] + item['bytes']])

    def test_independent_reference_and_half_up_storage(self):
        self.factory()
        from sky_light_brdf_reference import integrate_reference, unorm16_codes
        values = integrate_reference()
        self.assertEqual(values.shape, (32, 128, 2))
        self.assertEqual(values.dtype, np.float32)
        self.assertTrue(np.isfinite(values).all())
        self.assertTrue((values >= 0).all())
        codes = unorm16_codes(values)
        self.assertEqual(codes.dtype, np.uint16)
        self.assertGreater(int(codes[0, -1, 0]), 65000)
        self.assertLess(int(codes[0, -1, 1]), 2)
        self.assertGreater(int(codes[0, 0, 1]), 50000)
        self.assertEqual(unorm16_codes(np.array([-1, 0, .5, 1, 2], np.float32)).tolist(),
                         [0, 0, 32768, 65535, 65535])
        double = integrate_reference(dtype=np.float64)
        # Source FP32 GGX cancellation at the roughness/grazing corner is real.
        # A double oracle must not silently replace the original FP32 contract.
        delta = abs(values - double)
        self.assertEqual(np.unravel_index(delta.argmax(), delta.shape), (0, 0, 1))
        self.assertGreater(float(delta[0, 0, 1]), 1e-3)

    def test_parity_report_preserves_every_quantized_mismatch(self):
        self.factory()
        from sky_light_brdf_reference import parity_report
        observed = np.array([[[10, 20], [30, 40]]], dtype=np.uint16)
        reference = np.array([[[10, 21], [28, 40]]], dtype=np.uint16)
        report = parity_report(observed, reference)
        self.assertFalse(report['exact'])
        self.assertEqual(report['mismatched_channels'], 2)
        self.assertEqual(report['max_code_difference'], 2)
        self.assertEqual(report['mismatches'], [
            {'x': 0, 'y': 0, 'channel': 1, 'observed': 20, 'reference': 21, 'difference': -1},
            {'x': 1, 'y': 0, 'channel': 0, 'observed': 30, 'reference': 28, 'difference': 2}])

    @unittest.skipUnless(os.name == 'nt', 'Windows UE source uses the UCRT float cosine')
    def test_reference_cosine_matches_actual_source_cosf_at_all_128_phases(self):
        from sky_light_brdf_reference import source_cosine_polynomial
        native = ctypes.CDLL('ucrtbase')
        native.cosf.argtypes = [ctypes.c_float]
        native.cosf.restype = ctypes.c_float
        for index in range(128):
            phase = (np.float32(2) * np.float32(math.pi)) * (np.float32(index) / np.float32(128))
            self.assertEqual(np.float32(math.cos(float(phase))), np.float32(native.cosf(float(phase))), index)
            self.assertEqual(source_cosine_polynomial(phase), np.float32(native.cosf(float(phase))), index)

    def test_source_math_adapter_corrects_quotient_and_sqrt_seed_errors(self):
        import sky_light_brdf_reference as reference
        self.assertTrue(hasattr(reference, 'correct_divide_candidate'), 'Source FP32 rounding adapter is missing')
        rng = np.random.default_rng(719)
        a = np.exp2(rng.uniform(-20, 20, 8192)).astype(np.float32)
        b = np.exp2(rng.uniform(-20, 20, 8192)).astype(np.float32)
        # Powers of two and their nearest neighbors exercise exponent boundaries.
        powers = np.exp2(np.arange(-20, 21)).astype(np.float32)
        a = np.concatenate([a, powers, np.nextafter(powers, np.float32(0)), np.nextafter(powers, np.float32(np.inf))])
        b = np.concatenate([b, np.ones(123, dtype=np.float32)])
        quotient, root = a / b, np.sqrt(a)
        for offset in (-2, -1, 0, 1, 2):
            qseed = (quotient.view(np.int32) + offset).view(np.float32)
            sseed = (root.view(np.int32) + offset).view(np.float32)
            np.testing.assert_array_equal(reference.correct_divide_candidate(a, b, qseed), quotient)
            np.testing.assert_array_equal(reference.correct_sqrt_candidate(a, sseed), root)

    def test_source_cosine_adapter_across_domain_and_quadrant_boundaries(self):
        import sky_light_brdf_reference as reference
        self.assertTrue(hasattr(reference, 'source_cosine_polynomial'), 'Source cosine rounding adapter is missing')
        random = np.random.default_rng(131).uniform(-2*math.pi, 2*math.pi, 16384).astype(np.float32)
        quadrants = (np.arange(-4, 5) * (math.pi / 2)).astype(np.float32)
        values = np.concatenate([random, quadrants, np.nextafter(quadrants, np.float32(-np.inf)),
                                 np.nextafter(quadrants, np.float32(np.inf))])
        # Generic mathematical accuracy uses an independent high-precision
        # calculation. UCRT cosf itself differs by one ULP at20 of these random
        # values; exact source-cosf equivalence is separately checked for all
        #128 actual source phases, without fitting any polynomial coefficient.
        expected = np.array([math.cos(float(x)) for x in values], np.float32)
        np.testing.assert_array_equal(reference.source_cosine_polynomial(values), expected)


if __name__ == '__main__':
    unittest.main()
