"""CPU-only tests for explicit typed Schema field comparisons."""

import json
import unittest

import numpy as np

from observer import compare_arrays
from schema_observer_compare import compare_fields


class SchemaObserverCompareTests(unittest.TestCase):
    def compare(self, actual, reference, rule, mask=None):
        return compare_fields(
            {"field": actual}, {"field": reference}, {"field": rule}, mask
        )

    def test_exact_preserves_full_width_integer_differences(self):
        for dtype, values in (
            (np.uint32, [0, 2**24, 2**24 + 1, 2**32 - 1]),
            (np.int32, [-(2**31), -(2**24) - 1, 2**24, 2**31 - 1]),
            (np.uint64, [0, 2**53, 2**53 + 1, 2**64 - 1]),
            (np.int64, [-(2**63), -(2**53) - 1, 2**53, 2**63 - 1]),
        ):
            with self.subTest(dtype=dtype):
                reference = np.array([values], dtype=dtype)
                actual = reference.copy()
                actual[0, 2] += np.array(1, dtype=dtype)
                report = self.compare(actual, reference, {"kind": "exact"})
                self.assertIs(report["passed"], False)
                field = report["fields"]["field"]
                self.assertEqual(field["sample_count"], 4)
                self.assertEqual(field["failed_samples"], 1)
                self.assertEqual(field["sample_unit"], "components")

    def test_exact_boolean_vectors_count_components(self):
        reference = np.ones((1, 2, 3), dtype=np.bool_)
        actual = reference.copy()
        actual[0, 0, :2] = False
        report = self.compare(actual, reference, {"kind": "exact"})
        self.assertEqual(report["fields"]["field"]["sample_count"], 6)
        self.assertEqual(report["fields"]["field"]["failed_samples"], 2)

    def test_exact_noncontiguous_equal_arrays_pass_without_mutating_inputs(self):
        reference = np.arange(24, dtype=np.uint32).reshape(2, 4, 3)[:, ::2]
        actual = reference.copy()
        snapshot = actual.copy()
        report = self.compare(actual, reference, {"kind": "exact"})
        self.assertIs(report["passed"], True)
        np.testing.assert_array_equal(actual, snapshot)

    def test_numeric_uses_existing_error_statistics(self):
        reference = np.array([[[0.0, 2.0], [4.0, 8.0]]], dtype=np.float32)
        actual = reference + np.array([[[0.1, 0.15], [0.5, 1.0]]], dtype=np.float32)
        rule = {"kind": "numeric", "atol": 0.1, "rtol": 0.05}
        report = self.compare(actual, reference, rule)
        field = report["fields"]["field"]
        for key, value in compare_arrays(actual, reference, atol=0.1, rtol=0.05).items():
            self.assertEqual(field[key], value)
        self.assertEqual(field["sample_unit"], "components")
        self.assertIs(report["passed"], False)

    def test_numeric_accepts_explicit_tolerance_boundary(self):
        reference = np.array([[0.0, 2.0]], dtype=np.float64)
        actual = np.array([[0.25, 2.75]], dtype=np.float64)
        self.assertTrue(self.compare(actual, reference, {
            "kind": "numeric", "atol": 0.25, "rtol": 0.25
        })["passed"])

    def test_angle_reports_parallel_orthogonal_and_opposite_vectors(self):
        actual = np.array([[[8, 0, 0], [0, 7, 0], [-5, 0, 0]]], dtype=np.float64)
        reference = np.array([[[2, 0, 0]] * 3], dtype=np.float64)
        report = self.compare(actual, reference, {"kind": "angle", "max_degrees": 90})
        field = report["fields"]["field"]
        self.assertFalse(report["passed"])
        self.assertEqual(field["sample_count"], 3)
        self.assertEqual(field["failed_samples"], 1)
        self.assertEqual(field["sample_unit"], "vectors")
        self.assertEqual(field["max_angle_degrees"], 180.0)
        self.assertEqual(field["mean_angle_degrees"], 90.0)
        self.assertTrue(self.compare(actual, reference, {
            "kind": "angle", "max_degrees": 180
        })["passed"])

    def test_angle_normalization_handles_extreme_finite_magnitudes(self):
        actual = np.array([[[1e308, 1e308, 0], [1e-308, 0, 0]]], dtype=np.float64)
        reference = np.array([[[1.0, 1.0, 0], [1.0, 0, 0]]], dtype=np.float64)
        with np.errstate(all="raise"):
            report = self.compare(actual, reference, {"kind": "angle", "max_degrees": 0})
        self.assertTrue(report["passed"])
        self.assertEqual(report["fields"]["field"]["max_angle_degrees"], 0.0)

    def test_angle_preserves_small_angles_lost_by_arccos(self):
        degrees = 1e-8
        radians = np.deg2rad(degrees)
        actual = np.array([[[np.cos(radians), np.sin(radians), 0]]], dtype=np.float64)
        reference = np.array([[[1.0, 0.0, 0.0]]], dtype=np.float64)
        report = self.compare(actual, reference, {"kind": "angle", "max_degrees": degrees / 2})
        self.assertFalse(report["passed"])
        self.assertAlmostEqual(report["fields"]["field"]["max_angle_degrees"], degrees, places=14)

    def test_explicit_mask_ignores_unselected_nonfinite_and_zero_vectors(self):
        mask = np.array([[True, False]], dtype=np.bool_)
        for kind in ("numeric", "angle"):
            with self.subTest(kind=kind):
                actual = np.array([[[1.0, 0, 0], [np.nan, np.inf, 0]]])
                reference = np.array([[[1.0, 0, 0], [0.0, 0, 0]]])
                rule = ({"kind": "numeric", "atol": 0.0, "rtol": 0.0}
                        if kind == "numeric" else {"kind": "angle", "max_degrees": 0.0})
                report = self.compare(actual, reference, rule, mask)
                self.assertTrue(report["passed"])
                self.assertEqual(report["fields"]["field"]["sample_count"], 3 if kind == "numeric" else 1)

    def test_exact_mask_excludes_mismatching_pixel_components(self):
        actual = np.array([[[1, 2], [8, 9]]], dtype=np.int32)
        reference = np.array([[[1, 2], [0, 0]]], dtype=np.int32)
        report = self.compare(actual, reference, {"kind": "exact"}, np.array([[True, False]]))
        self.assertTrue(report["passed"])
        self.assertEqual(report["fields"]["field"]["sample_count"], 2)

    def test_combined_report_uses_rules_without_name_semantics_and_allows_reference_extras(self):
        actual = {"normal": np.array([[2]], dtype=np.uint32), "identifier": np.array([[1.5]])}
        reference = {"normal": np.array([[3]], dtype=np.uint32), "identifier": np.array([[1.5]]),
                     "coverage": np.array([[True]])}
        rules = {"normal": {"kind": "exact"}, "identifier": {"kind": "numeric", "atol": 0, "rtol": 0}}
        report = compare_fields(actual, reference, rules)
        self.assertFalse(report["passed"])
        self.assertEqual(set(report["fields"]), set(actual))
        self.assertEqual(json.loads(json.dumps(report, allow_nan=False)), report)

    def test_rejects_empty_field_selection_and_non_dictionary_inputs(self):
        for args in (({}, {}, {}), ([], {}, {}), ({}, [], {}), ({}, {}, [])):
            with self.subTest(args=args), self.assertRaises(ValueError):
                compare_fields(*args)

    def test_rejects_missing_reference_and_incomplete_or_extra_rules(self):
        actual = {"a": np.ones((1, 1), dtype=np.int32)}
        for reference, rules in (
            ({}, {"a": {"kind": "exact"}}),
            (actual, {}),
            (actual, {"a": {"kind": "exact"}, "b": {"kind": "exact"}}),
        ):
            with self.subTest(reference=reference, rules=rules), self.assertRaises(ValueError):
                compare_fields(actual, reference, rules)

    def test_rejects_malformed_rules_and_unknown_keys(self):
        data = np.ones((1, 1), dtype=np.float32)
        for rule in (
            None, [], {}, {"kind": "fuzzy"}, {"kind": []},
            {"kind": "exact", "atol": 0},
            {"kind": "numeric", "atol": 0},
            {"kind": "numeric", "atol": 0, "rtol": 0, "extra": 1},
            {"kind": "angle"}, {"kind": "angle", "max_degrees": 1, "rtol": 0},
        ):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                self.compare(data, data, rule)

    def test_rejects_nonfinite_negative_boolean_or_nonnumeric_tolerances(self):
        data = np.ones((1, 1), dtype=np.float32)
        for value in (-1, np.nan, np.inf, -np.inf, True, np.bool_(False), "0", None, 10**400):
            for key in ("atol", "rtol"):
                rule = {"kind": "numeric", "atol": 0, "rtol": 0, key: value}
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.compare(data, data, rule)

    def test_rejects_invalid_angle_limits(self):
        data = np.ones((1, 1, 3), dtype=np.float32)
        for value in (-1, 180.01, np.nan, np.inf, True, "5", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.compare(data, data, {"kind": "angle", "max_degrees": value})

    def test_rejects_shape_dtype_and_array_contract_mismatches(self):
        for actual, reference in (
            (np.zeros((1, 2)), np.zeros((2, 1))),
            (np.zeros((1, 2), dtype=np.float32), np.zeros((1, 2), dtype=np.float64)),
            (np.zeros((1, 2), dtype=np.uint32), np.zeros((1, 2), dtype=np.int32)),
            (np.zeros((1, 2), dtype=np.bool_), np.zeros((1, 2), dtype=np.uint8)),
            ([[1.0]], np.ones((1, 1))),
            (np.ones((1, 1)), [[1.0]]),
            (np.ones(2), np.ones(2)),
            (np.ones((1, 1, 1, 1)), np.ones((1, 1, 1, 1))),
            (np.ones((0, 2)), np.ones((0, 2))),
            (np.ones((1, 1, 0)), np.ones((1, 1, 0))),
        ):
            with self.subTest(actual=actual, reference=reference), self.assertRaises(ValueError):
                self.compare(actual, reference, {"kind": "numeric", "atol": 0, "rtol": 0})

    def test_mask_never_relaxes_shape_or_dtype_validation(self):
        actual = np.zeros((1, 2), dtype=np.float32)
        mask = np.array([[True, False]])
        for reference in (np.zeros((2, 1), dtype=np.float32), np.zeros((1, 2), dtype=np.float64)):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                self.compare(actual, reference, {"kind": "numeric", "atol": 0, "rtol": 0}, mask)

    def test_rejects_empty_invalid_or_nonboolean_masks(self):
        data = np.ones((1, 2, 3))
        for mask in (np.array([[False, False]]), np.ones((2, 1), dtype=bool),
                     np.ones((1, 2, 3), dtype=bool), np.array([[1, 0]]), [[True, False]]):
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                self.compare(data, data, {"kind": "numeric", "atol": 0, "rtol": 0}, mask)

    def test_rejects_dtype_incompatible_with_explicit_kind(self):
        for dtype, rule, shape in (
            (np.float32, {"kind": "exact"}, (1, 1)),
            (np.int32, {"kind": "numeric", "atol": 0, "rtol": 0}, (1, 1)),
            (np.bool_, {"kind": "numeric", "atol": 0, "rtol": 0}, (1, 1)),
            (np.complex64, {"kind": "numeric", "atol": 0, "rtol": 0}, (1, 1)),
            (object, {"kind": "exact"}, (1, 1)),
            (np.int32, {"kind": "angle", "max_degrees": 0}, (1, 1, 3)),
        ):
            data = np.ones(shape, dtype=dtype)
            with self.subTest(dtype=dtype, rule=rule), self.assertRaises(ValueError):
                self.compare(data, data, rule)

    def test_rejects_angle_arrays_that_are_not_pixel_float3(self):
        for shape in ((1, 3), (1, 1, 2), (1, 1, 4)):
            data = np.ones(shape, dtype=np.float32)
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                self.compare(data, data, {"kind": "angle", "max_degrees": 1})

    def test_selected_nonfinite_samples_fail_explicitly_with_field_context(self):
        for value in (np.nan, np.inf, -np.inf):
            for kind in ("numeric", "angle"):
                rule = ({"kind": "numeric", "atol": 0, "rtol": 0}
                        if kind == "numeric" else {"kind": "angle", "max_degrees": 180})
                bad = np.array([[[1.0, value, 0.0]]])
                good = np.array([[[1.0, 0.0, 0.0]]])
                for actual, reference in ((bad, good), (good, bad)):
                    with self.subTest(value=value, kind=kind), self.assertRaisesRegex(ValueError, "field.*finite"):
                        self.compare(actual, reference, rule)

    def test_selected_zero_vectors_fail_explicitly(self):
        zero = np.zeros((1, 1, 3), dtype=np.float32)
        nonzero = np.ones((1, 1, 3), dtype=np.float32)
        for actual, reference in ((zero, nonzero), (nonzero, zero), (zero, zero)):
            with self.subTest(actual=actual, reference=reference), self.assertRaisesRegex(ValueError, "field.*zero"):
                self.compare(actual, reference, {"kind": "angle", "max_degrees": 180})

    def test_numeric_arithmetic_overflow_is_explicit_error(self):
        large = np.array([[1e308]], dtype=np.float64)
        for actual, reference, rule in (
            (large, -large, {"kind": "numeric", "atol": 0, "rtol": 0}),
            (large, large, {"kind": "numeric", "atol": 0, "rtol": 1e308}),
        ):
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "field.*float64"):
                self.compare(actual, reference, rule)


if __name__ == "__main__":
    unittest.main()
