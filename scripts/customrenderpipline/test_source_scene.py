"""Authored geometry/transform cases; no renderer or capture dependencies."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from source_scene import load_ue_internal_obj, parse_ue_internal_obj, ue_instance_transform


TRIANGLE = """# UnrealEd OBJ exporter (_Internal)
v 100 200 300
v 300 200 300
v 100 600 300
vt 0.125 0.75
vt 0.625 0.5
vt 0.375 0.125
vn 0 0 2
f 1/1/1 2/2/1 3/3/1
"""


class SourceMeshTests(unittest.TestCase):
    def test_asymmetric_positions_uvs_and_normals_use_source_conventions(self):
        mesh = parse_ue_internal_obj(TRIANGLE)
        np.testing.assert_array_equal(mesh.positions, [[3, 2, -1], [3, 2, -3], [3, 6, -1]])
        np.testing.assert_array_equal(mesh.texcoords, [[0.125, 0.25], [0.625, 0.5], [0.375, 0.875]])
        # Basis conversion preserves the original normal magnitude; no cm scale.
        np.testing.assert_array_equal(mesh.normals, [[2, 0, 0]] * 3)
        np.testing.assert_array_equal(mesh.triangles, [[0, 1, 2]])
        np.testing.assert_array_equal(mesh.source_indices, [[0, 0, 0], [1, 1, 0], [2, 2, 0]])

    def test_exported_winding_already_agrees_with_falcor_normals(self):
        mesh = parse_ue_internal_obj(TRIANGLE)
        a, b, c = mesh.positions[mesh.triangles[0]]
        self.assertGreater(np.dot(np.cross(b - a, c - a), mesh.normals[0]), 0)

    def test_uv_seams_and_separate_normal_indices_split_only_corner_tuples(self):
        mesh = parse_ue_internal_obj("""v 0 0 0
v 100 0 0
v 0 100 0
v 100 100 0
vt 0 0
vt 1 0
vt 0 1
vt 0.25 0.75
vn 0 0 1
vn 0.6 0 0.8
f 1/1/1 2/2/1 3/3/1
f 2/4/2 4/2/2 3/3/1
""")
        self.assertEqual(mesh.positions.shape, (5, 3))
        np.testing.assert_array_equal(mesh.triangles, [[0, 1, 2], [3, 4, 2]])
        np.testing.assert_array_equal(mesh.source_indices, [[0, 0, 0], [1, 1, 0], [2, 2, 0], [1, 3, 1], [3, 1, 1]])
        np.testing.assert_array_equal(mesh.positions[1], mesh.positions[3])
        np.testing.assert_array_equal(mesh.texcoords[3], [0.25, 0.25])
        np.testing.assert_array_equal(mesh.normals[3], [0.8, 0, -0.6])

    def test_negative_indices_resolve_at_each_face_not_at_end_of_file(self):
        source = TRIANGLE.replace("f 1/1/1 2/2/1 3/3/1", "f -3/-3/-1 -2/-2/-1 -1/-1/-1")
        source += "v 999 999 999\nvt 9 9\nvn 1 0 0\n"
        mesh = parse_ue_internal_obj(source)
        expected = parse_ue_internal_obj(TRIANGLE)
        for key in ("positions", "normals", "texcoords", "triangles", "source_indices"):
            np.testing.assert_array_equal(getattr(mesh, key), getattr(expected, key))

    def test_comments_metadata_and_utf8_bom_file(self):
        source = "\ufeffo SourceMesh\ng Group\ns off\n" + TRIANGLE.replace("v 100 200 300", "v\t100 200 300 # source cm")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Example_Internal.obj"
            path.write_text(source, encoding="utf-8")
            mesh = load_ue_internal_obj(path)
        np.testing.assert_array_equal(mesh.positions[0], [3, 2, -1])

    def test_zero_out_of_range_and_noninteger_corner_indices_are_rejected(self):
        for corner in ("0/1/1", "4/1/1", "-4/1/1", "1/0/1", "1/4/1", "1/-4/1",
                       "1/1/0", "1/1/2", "1/1/-2", "1.0/1/1", "1/1/x", "1//1", "1/1", "1"):
            with self.subTest(corner=corner), self.assertRaisesRegex(ValueError, "line"):
                parse_ue_internal_obj(TRIANGLE.replace("f 1/1/1", "f " + corner))

    def test_malformed_geometry_is_rejected_instead_of_silently_repaired(self):
        cases = ["", TRIANGLE.replace("v 100 200 300", "v nan 200 300"),
                 TRIANGLE.replace("vt 0.125 0.75", "vt 0.125 inf"),
                 TRIANGLE.replace("vn 0 0 2", "vn 0 0 0"),
                 TRIANGLE.replace("vn 0 0 2", "vn 0 inf 2"),
                 TRIANGLE.replace("v 100 200 300", "v 100 200"),
                 TRIANGLE.replace("f 1/1/1 2/2/1 3/3/1", "f 1/1/1 2/2/1 3/3/1 1/1/1"),
                 TRIANGLE + "curv 0 1 1 2 3\n"]
        for source in cases:
            with self.subTest(source=source[-50:]), self.assertRaises(ValueError):
                parse_ue_internal_obj(source)


class SourceInstanceTests(unittest.TestCase):
    def test_identity_and_translation_are_in_falcor_local_meters(self):
        identity = ue_instance_transform()
        np.testing.assert_array_equal(identity.matrix, np.eye(4))
        np.testing.assert_array_equal(identity.normal_matrix, np.eye(3))
        self.assertFalse(identity.reverses_winding)
        transform = ue_instance_transform(translation_cm=(125, 250, 375))
        np.testing.assert_array_equal(transform.matrix[:3, 3], [2.5, 3.75, -1.25])
        np.testing.assert_array_equal(transform.transform_positions([[3, 2, -1]]), [[5.5, 5.75, -2.25]])

    def test_each_ue_rotator_axis_has_the_correct_sign(self):
        cases = [((90, 0, 0), [0, 0, -1], [0, 1, 0]),
                 ((0, 90, 0), [1, 0, 0], [0, 0, 1]),
                 ((0, 0, 90), [1, 0, 0], [0, -1, 0])]
        for rotation, point, expected in cases:
            with self.subTest(rotation=rotation):
                result = ue_instance_transform(rotation_deg=rotation).transform_positions([point])
                np.testing.assert_allclose(result, [expected], atol=1e-14)

    def test_nonuniform_scale_then_rotator_then_translation(self):
        transform = ue_instance_transform(translation_cm=(11, 23, 37), rotation_deg=(90, 90, 90), scale=(2, 3, 4))
        # UE (100,200,300) -> scale (200,600,1200) -> rotate (-1200,600,200)
        # -> translate (-1189,623,237) -> Falcor (6.23,2.37,11.89).
        np.testing.assert_allclose(transform.transform_positions([[2, 3, -1]]), [[6.23, 2.37, 11.89]], atol=1e-13)

    def test_arbitrary_rotator_matches_independent_axis_rotations_in_ue_space(self):
        points_ue = np.array([[31, -72, 115], [-47, 83, 29]], dtype=float)
        scaled = points_ue * [2, 0.3, 4]
        pitch, yaw, roll = np.deg2rad([23, 47, -31])
        # Apply conventional right-handed rotations X(-roll), Y(-pitch), Z(yaw)
        # directly to UE numeric components, independent of the combined formula.
        x, y, z = scaled.T
        y, z = y * np.cos(roll) + z * np.sin(roll), -y * np.sin(roll) + z * np.cos(roll)
        x, z = x * np.cos(pitch) - z * np.sin(pitch), x * np.sin(pitch) + z * np.cos(pitch)
        x, y = x * np.cos(yaw) - y * np.sin(yaw), x * np.sin(yaw) + y * np.cos(yaw)
        translated = np.column_stack([x, y, z]) + [13, -29, 71]
        expected = np.column_stack([translated[:, 1], translated[:, 2], -translated[:, 0]]) / 100
        local = np.column_stack([points_ue[:, 1], points_ue[:, 2], -points_ue[:, 0]]) / 100
        transform = ue_instance_transform(translation_cm=(13, -29, 71), rotation_deg=(23, 47, -31), scale=(2, 0.3, 4))
        np.testing.assert_allclose(transform.transform_positions(local), expected, atol=1e-14)

    def test_oblique_normal_stays_perpendicular_under_nonuniform_rotated_scale(self):
        transform = ue_instance_transform(translation_cm=(9, -31, 73), rotation_deg=(23, 47, -31), scale=(2, 3, 0.25))
        normal = np.array([1, 2, 3], dtype=float)
        tangent_a = np.array([2, -1, 0], dtype=float)
        tangent_b = np.cross(normal, tangent_a)
        transformed = transform.transform_normals([normal])[0]
        self.assertAlmostEqual(np.linalg.norm(transformed), 1)
        for tangent in (tangent_a, tangent_b):
            self.assertAlmostEqual(np.dot(transformed, transform.matrix[:3, :3] @ tangent), 0, places=12)
        # Translation never enters normal transformation.
        other = ue_instance_transform(rotation_deg=(23, 47, -31), scale=(2, 3, 0.25))
        np.testing.assert_array_equal(transform.normal_matrix, other.normal_matrix)

    def test_negative_scale_reports_instance_winding_without_mutating_mesh(self):
        mesh = parse_ue_internal_obj(TRIANGLE)
        before = mesh.positions.copy()
        transform = ue_instance_transform(rotation_deg=(17, 29, 11), scale=(-2, 3, 4))
        self.assertTrue(transform.reverses_winding)
        positions = transform.transform_positions(mesh.positions)
        normal = transform.transform_normals(mesh.normals)[0]
        a, b, c = positions[mesh.triangles[0]]
        self.assertLess(np.dot(np.cross(b - a, c - a), normal), 0)
        self.assertGreater(np.dot(np.cross(c - a, b - a), normal), 0)
        np.testing.assert_array_equal(mesh.positions, before)
        np.testing.assert_array_equal(mesh.triangles, [[0, 1, 2]])
        self.assertFalse(ue_instance_transform(scale=(-2, -3, 4)).reverses_winding)

    def test_two_instances_reuse_the_same_immutable_local_mesh(self):
        mesh = parse_ue_internal_obj(TRIANGLE)
        instances = [(mesh, ue_instance_transform()), (mesh, ue_instance_transform(translation_cm=(0, 100, 0)))]
        self.assertIs(instances[0][0], instances[1][0])
        for array in (mesh.positions, mesh.normals, mesh.texcoords, mesh.triangles, mesh.source_indices):
            self.assertFalse(array.flags.writeable)
        first = instances[0][1].transform_positions(mesh.positions)
        second = instances[1][1].transform_positions(mesh.positions)
        np.testing.assert_array_equal(second - first, [[1, 0, 0]] * 3)

    def test_invalid_and_singular_instance_transforms_are_rejected(self):
        for options in ({"scale": (1, 0, 1)}, {"scale": (1, np.inf, 1)},
                        {"translation_cm": (1, 2)}, {"translation_cm": (0, np.nan, 0)},
                        {"rotation_deg": (0, 0, np.inf)}, {"rotation_deg": [[0, 0, 0]]}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                ue_instance_transform(**options)
        transform = ue_instance_transform()
        for normals in ([[0, 0, 0]], [[np.nan, 0, 1]], [1, 2, 3]):
            with self.subTest(normals=normals), self.assertRaises(ValueError):
                transform.transform_normals(normals)


if __name__ == "__main__":
    unittest.main()
