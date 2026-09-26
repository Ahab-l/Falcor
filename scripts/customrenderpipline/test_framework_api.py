"""Framework requirements independent of reference rendering algorithms."""
import unittest


class FrameworkApiTests(unittest.TestCase):
    def test_comparison_reports_error_and_tolerance_failures(self):
        from observer import compare_arrays
        result = compare_arrays([[1, 2], [3, 4]], [[1, 2.1], [3, 4]], atol=0.05)
        self.assertFalse(result['passed'])
        self.assertEqual(result['failed_samples'], 1)
        self.assertEqual(result['worst_index'], [0, 1])
        self.assertAlmostEqual(result['max_abs'], 0.1)
        self.assertAlmostEqual(result['mae'], 0.025)
        self.assertAlmostEqual(result['rmse'], 0.05)
        self.assertTrue(compare_arrays([100], [101], rtol=0.01)['passed'])

    def test_comparison_rejects_undefined_inputs(self):
        from observer import compare_arrays
        for actual, expected, kwargs in [([float('nan')], [0], {}), ([float('inf')], [0], {}),
                                          ([], [], {}), ([1], [[1]], {}), ([1], [1], {'atol': -1})]:
            with self.subTest(actual=actual, expected=expected):
                with self.assertRaises(ValueError):
                    compare_arrays(actual, expected, **kwargs)

    def test_comparison_does_not_round_large_integer_ids_into_equality(self):
        from observer import compare_arrays
        with self.assertRaisesRegex(ValueError, 'exact float64'):
            compare_arrays([2**53 + 1], [2**53])


if __name__ == '__main__':
    unittest.main()
