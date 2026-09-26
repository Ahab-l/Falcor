"""CPU geometry/ABI tests for source-authored CSM setup; no capture or GPU inputs."""
import math
import unittest

import numpy as np

from csm_setup_math import setup_cascades, snap_shadow_center, split_distances


def camera(position=(0, 0, 0), forward=(0, 0, -1), asymmetric=(0, 0)):
    position = np.asarray(position, dtype=float)
    forward = np.asarray(forward, dtype=float)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 1, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    view = np.eye(4)
    view[:3, :3] = [right, up, -forward]
    view[:3, 3] = -view[:3, :3] @ position
    projection = np.zeros((4, 4))
    projection[0, 0], projection[1, 1] = 1.0, 1.6
    projection[0, 2], projection[1, 2] = asymmetric
    projection[2, 2], projection[2, 3], projection[3, 2] = -1.001, -0.1001, -1
    return dict(view_matrix=view, projection_no_jitter=projection, near_m=0.1)


class CSMSetupMathTests(unittest.TestCase):
    def test_geometric_split_widths_are_one_three_nine_twenty_seven(self):
        np.testing.assert_allclose(split_distances(10, 20000, 4, 3),
                                   [10, 509.75, 2009, 6506.75, 20000], rtol=0, atol=1e-10)
        np.testing.assert_allclose(np.diff(split_distances(10, 20000, 4, 3)) / 499.75,
                                   [1, 3, 9, 27])
        np.testing.assert_allclose(split_distances(10, 20000, 4, 1),
                                   [10, 5007.5, 10005, 15002.5, 20000])

    def test_overlap_extends_inner_cascades_and_last_fade_moves_inward(self):
        result = setup_cascades(**camera(), shadow={"direction": [0, 1, 0]})
        split = np.array([c["split"] for c in result["cascades"]])
        np.testing.assert_allclose(split[:, :3], np.array([
            [10, 559.725, 509.75], [509.75, 2158.925, 2009],
            [2009, 6956.525, 6506.75], [6506.75, 20000, 18650.675]]) / 100)
        np.testing.assert_allclose(split[:, 3], 100 / np.array([49.975, 149.925, 449.775, 1349.325]))
        np.testing.assert_allclose(result["parameters"][3], [180, 0.05, 0, 0])

    def test_frustum_corners_fit_raw_sphere_for_rotated_asymmetric_camera(self):
        result = setup_cascades(**camera((-23, 4, -9), (0.3, -0.2, -1), (0.27, -0.14)),
                                shadow={"direction": [0.3, 0.8, -0.4]})
        for cascade in result["cascades"]:
            distances = np.linalg.norm(cascade["corners_cm"] - cascade["center_cm"], axis=1)
            self.assertLessEqual(max(distances), cascade["raw_radius_cm"] + 1e-8)
            self.assertAlmostEqual(max(distances), cascade["raw_radius_cm"], places=8)
            self.assertEqual(cascade["radius_cm"], math.ceil(cascade["raw_radius_cm"]))
            # Snapping can displace the projected bounds by fewer than four texels.
            corners_m = cascade["corners_cm"] / 100
            clip = np.c_[corners_m, np.ones(8)] @ cascade["matrix"].T
            self.assertLessEqual(np.max(np.abs(clip[:, :2])), 1 + 8 / 2040 + 1e-8)
            self.assertGreaterEqual(np.min(clip[:, 2]), -1e-8)
            self.assertLessEqual(np.max(clip[:, 2]), 1 + 1e-8)

    def test_ue_light_rotation_and_reversed_depth_have_known_cardinal_axes(self):
        cascade = setup_cascades(**camera(), shadow={"direction": [0, 0, 1]})["cascades"][0]
        matrix, radius = cascade["matrix"], cascade["radius_cm"]
        np.testing.assert_allclose(matrix[0, :3], [0, -100 / radius, 0], atol=1e-12)
        np.testing.assert_allclose(matrix[1, :3], [100 / radius, 0, 0], atol=1e-12)
        np.testing.assert_allclose(matrix[2, :3], [0, 0, 0.01], atol=1e-12)
        for z_cm, expected in [(-5000, 1), (5000, 0)]:
            point_m = (cascade["snapped_center_cm"] + cascade["axes"][2] * z_cm) / 100
            clip = matrix @ np.r_[point_m, 1]
            np.testing.assert_allclose(clip, [0, 0, expected, 1], atol=1e-12)

    def test_bias_uses_raw_radius_over_inner_resolution_and_centimeter_depth(self):
        cascade = setup_cascades(**camera(), shadow={"direction": [0, 1, 0]})["cascades"][0]
        expected = (10 / 10000) * (cascade["raw_radius_cm"] / 2040) * 0.5
        np.testing.assert_allclose(cascade["bias"], [expected, expected * 1.5, 1, 1 / expected])
        self.assertNotAlmostEqual(expected, (10 / 10000) * (2 * cascade["radius_cm"] / 2040) * 0.5)
        unscaled = setup_cascades(**camera(), shadow={"direction": [0, 1, 0], "bias_distribution": 0})["cascades"][0]
        self.assertAlmostEqual(unscaled["bias"][0], 10 / 10000 * 0.5)
        self.assertAlmostEqual(unscaled["bias"][3], cascade["bias"][3])

    def test_signed_fmod_snap_truncates_negative_positions_toward_zero(self):
        step = 8 / 2040
        q = np.array([-3.7 * step, 2.9 * step, -123.4])
        np.testing.assert_allclose(snap_shadow_center(q, 2040), [-3 * step, 2 * step, -123.4])
        np.testing.assert_allclose(snap_shadow_center(-q, 2040), -snap_shadow_center(q, 2040))

    def test_buffer_abi_camera_motion_and_inactive_records(self):
        result = setup_cascades(**camera((-3, 4, -5)), shadow={"direction": [0, 1, 0], "cascades": 2})
        buffer = result["parameters"]
        self.assertEqual(buffer.shape, (36, 4))
        self.assertEqual(buffer.dtype, np.dtype("<f4"))
        self.assertEqual(len(buffer.tobytes()), 576)
        np.testing.assert_array_equal(buffer[0], [-3, 4, -5, 2])
        np.testing.assert_array_equal(buffer[1], [0, 0, -1, 200])
        np.testing.assert_array_equal(buffer[2], [2048, 4, 0, 0])
        np.testing.assert_array_equal(buffer[20:], 0)
        moved = setup_cascades(**camera((-13, 7, -5)), shadow={"direction": [0, 1, 0], "cascades": 2})
        rotated = setup_cascades(**camera((-3, 4, -5), (0.4, 0, -1)), shadow={"direction": [0, 1, 0], "cascades": 2})
        self.assertFalse(np.array_equal(buffer[4:8], moved["parameters"][4:8]))
        self.assertFalse(np.array_equal(buffer[4:8], rotated["parameters"][4:8]))

    def test_zero_bias_and_zero_fade_stay_finite(self):
        result = setup_cascades(**camera(), shadow={"direction": [0, 1, 0], "depth_bias": 0,
                                                   "transition_fraction": 0, "fade_fraction": 0})
        self.assertTrue(np.isfinite(result["parameters"]).all())
        for cascade in result["cascades"]:
            np.testing.assert_allclose(cascade["bias"], [0, 0, 1, 100000])

    def test_invalid_settings_and_nonperspective_camera_are_rejected(self):
        for override in [{"cascades": 5}, {"cascades": 0}, {"cascades": 2.5}, {"direction": [0, 0, 0]},
                         {"resolution": 8}, {"border": 1024}, {"distance_cm": 5},
                         {"distribution_exponent": 0}, {"receiver_bias": 1.1}, {"depth_bias": float("nan")},
                         {"camera_matrix": []}, {"resolution": True}]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                setup_cascades(**camera(), shadow={"direction": [0, 1, 0], **override})
        ortho = camera()
        ortho["projection_no_jitter"] = np.eye(4)
        with self.assertRaises(ValueError):
            setup_cascades(**ortho, shadow={"direction": [0, 1, 0]})


if __name__ == "__main__":
    unittest.main()
