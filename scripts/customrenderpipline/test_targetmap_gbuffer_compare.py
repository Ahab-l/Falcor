import unittest
import numpy as np

from targetmap_gbuffer_compare import compare_arrays, unpack_depth_stencil, unpack_normal


class CompareTests(unittest.TestCase):
    def test_native_metadata_matches_actual_storage_not_decoded_shape(self):
        from targetmap_gbuffer_compare import validate_native_output
        entry = {'name': 'gbufferA', 'format': 'RGB10A2Unorm', 'dtype': 'uint8', 'shape': [5923840]}
        validate_native_output(entry)
        for key, bad in [('format', 'RGBA8Unorm'), ('dtype', 'int8'), ('shape', [1, 1, 1])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_native_output(dict(entry, **{key: bad}))

    def test_depth_layout_is_not_silently_truncated(self):
        raw = np.array([0x3f000000, 134, 0, 0], dtype='<u4').tobytes()
        depth, stencil = unpack_depth_stencil(raw, 2, 1)
        np.testing.assert_array_equal(depth, [[.5, 0]])
        np.testing.assert_array_equal(stencil, [[134, 0]])
        with self.assertRaises(ValueError):
            unpack_depth_stencil(raw[:-1], 2, 1)
        with self.assertRaises(ValueError):
            unpack_depth_stencil(np.array([0, 256], dtype='<u4').tobytes(), 1, 1)

    def test_normal_component_order(self):
        normal = unpack_normal(np.array([[1 | (2 << 10) | (3 << 20) | (1 << 30)]], dtype='<u4'))
        np.testing.assert_array_equal(normal, [[[1, 2, 3, 1]]])

    def pair(self):
        reference = {'depth': np.array([[0, .5, 0], [0, .25, 0]], dtype='<f4'),
                     'stencil': np.array([[0, 134, 0], [0, 134, 0]], dtype='u1'),
                     'gbufferA': np.ones((2, 3, 4), dtype='u4')}
        return reference, {k: v.copy() for k, v in reference.items()}

    def test_crop_and_coverage_do_not_hide_missing_pixels(self):
        reference, native = self.pair()
        native['depth'][1, 1] = 0
        native['depth'][0, 0] = 1  # outside the visible rectangle
        result = compare_arrays(reference, native, [1, 0, 2, 2])
        self.assertEqual(result['coverage']['intersection'], 1)
        self.assertEqual(result['coverage']['reference_only'], 1)
        self.assertEqual(result['coverage']['native_only'], 0)
        self.assertEqual(result['padding']['depth']['different_values'], 1)
        self.assertFalse(result['all_visible_values_equal'])

    def test_equal_and_unsigned_difference(self):
        reference, native = self.pair()
        self.assertTrue(compare_arrays(reference, native, [0, 0, 3, 2])['all_visible_values_equal'])
        native['gbufferA'][0, 1, 0] = 0
        result = compare_arrays(reference, native, [0, 0, 3, 2])
        self.assertEqual(result['opaque_intersection']['gbufferA']['max_abs'], 1)
        self.assertEqual(result['opaque_intersection']['gbufferA']['different_values'], 1)

    def test_invalid_values_or_shapes_rejected(self):
        reference, native = self.pair()
        native['depth'][0, 1] = np.nan
        with self.assertRaises(ValueError):
            compare_arrays(reference, native, [0, 0, 3, 2])
        native['depth'] = np.ones((1, 1))
        with self.assertRaises(ValueError):
            compare_arrays(reference, native, [0, 0, 3, 2])


if __name__ == '__main__':
    unittest.main()
