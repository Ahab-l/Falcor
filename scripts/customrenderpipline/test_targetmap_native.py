"""Source-camera contract, intentionally independent of captured matrices."""
import copy
import math
import hashlib
from pathlib import Path
from unittest.mock import Mock
import unittest

import numpy as np

from targetmap_native import source_camera
from source_scene import ue_instance_transform


class SourceCameraTests(unittest.TestCase):
    def test_source_json_identity_uses_same_read_bytes_as_parse(self):
        from targetmap_native import read_source_json
        payload = b'{"camera": {"near_cm": 10}}'
        path = Mock()
        path.resolve.return_value = path
        path.read_bytes.return_value = payload
        path.__str__ = Mock(return_value='C:/source.json')
        data, identity = read_source_json(path)
        self.assertEqual(data['camera']['near_cm'], 10)
        self.assertEqual(identity['bytes'], len(payload))
        self.assertEqual(identity['sha256'], hashlib.sha256(payload).hexdigest())
        path.read_bytes.assert_called_once_with()
        path.stat.assert_not_called()

    def setUp(self):
        self.camera = dict(position_cm=[120, -30, 40], rotation_pitch_yaw_roll=[0, 0, 0],
                           near_cm=10, horizontal_fov_degrees=90, resolution=[1421, 1035])

    def test_origin_and_basis(self):
        result = source_camera(self.camera)
        origin = np.array(self.camera['position_cm'])[[1, 2, 0]] / 100
        origin[2] *= -1
        np.testing.assert_array_equal(result['origin_m'], origin)
        np.testing.assert_allclose(np.array(result['view_projection']) @ [*origin, 1], [0, 0, .1, 0], atol=1e-15)

    def test_reverse_infinite_depth(self):
        result = source_camera(self.camera)
        matrix = np.array(result['view_projection'])
        origin = np.array(result['origin_m'])
        for distance in (.1, 1, 100, 1e6):
            clip = matrix @ [*(origin + [0, 0, -distance]), 1]
            self.assertAlmostEqual(clip[2] / clip[3], .1 / distance)

    def test_horizontal_and_vertical_fov_use_visible_extent(self):
        result = source_camera(self.camera)
        origin = np.array(result['origin_m'])
        matrix = np.array(result['view_projection'])
        right = matrix @ [*(origin + [1, 0, -1]), 1]
        top = matrix @ [*(origin + [0, 1035 / 1421, -1]), 1]
        self.assertAlmostEqual(right[0] / right[3], 1)
        self.assertAlmostEqual(top[1] / top[3], 1)

    def test_arbitrary_saved_rotation(self):
        camera = copy.deepcopy(self.camera)
        camera['rotation_pitch_yaw_roll'] = [-31.199898, 85.400834, 0]
        result = source_camera(camera)
        origin = np.array(result['origin_m'])
        rotation = ue_instance_transform(rotation_deg=camera['rotation_pitch_yaw_roll']).matrix[:3, :3]
        point = origin + rotation @ [0, 0, -2]
        clip = np.array(result['view_projection']) @ [*point, 1]
        np.testing.assert_allclose(clip, [0, 0, .1, 2], atol=1e-14)

    def test_projection_aspect_is_independent_of_rounded_render_rect(self):
        camera = copy.deepcopy(self.camera)
        camera['projection_resolution'] = [1920, 1080]
        result = source_camera(camera)
        self.assertEqual(result['view_rect'], [0, 0, 1421, 1035])
        self.assertAlmostEqual(result['projection'][1][1] / result['projection'][0][0], 1920/1080, delta=1e-7)
        camera['projection_resolution'] = [0, 1080]
        with self.assertRaises(ValueError):
            source_camera(camera)

    def test_source_editor_float_parameters_before_double_matrix(self):
        self.camera['projection_resolution'] = [2465, 1795]
        for degrees in (90, 37):
            self.camera['horizontal_fov_degrees'] = degrees
            projection = np.array(source_camera(self.camera)['projection'])
            half_fov = float(np.float32(np.float32(degrees)*np.float32(math.pi))/np.float32(360))
            source_aspect = float(np.float32(2465 / 1795))
            self.assertEqual(projection[0, 0], 1/math.tan(half_fov))
            self.assertEqual(projection[1, 1], source_aspect/math.tan(half_fov))

    def test_invalid_source_parameters(self):
        for key, value in [('near_cm', 0), ('near_cm', float('nan')), ('horizontal_fov_degrees', 180),
                           ('resolution', [0, 1035]), ('resolution', [1.5, 2]), ('resolution', [True, 2]),
                           ('position_cm', [float('inf'), 0, 0])]:
            camera = copy.deepcopy(self.camera)
            camera[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                source_camera(camera)


if __name__ == '__main__':
    unittest.main()
