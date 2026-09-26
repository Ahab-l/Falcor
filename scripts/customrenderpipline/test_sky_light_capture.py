"""CPU contracts for source-position SkyLight Mesh capture."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

import numpy as np
from test_sky_view import source_scene
from sky_light_filter_reference import cube_directions

ROOT = Path(__file__).resolve().parents[2]


def scene_fixture():
    scene = source_scene()
    scene['source_environment']['actors'][0]['environment'][0]['sky_luminance_factor'] = [1., .5, .25, 1.]
    scene['source_environment']['actors'].append({'class': 'SkyLight', 'lights': [{
        'class': 'SkyLightComponent', 'world_location_cm': [120., -75., 610.],
        'intensity': 1.75, 'light_color': [255, 200, 100, 255],
        'real_time_capture': True, 'source_type': '<SkyLightSourceType.SLS_CAPTURED_SCENE: 0>',
        'cubemap': None, 'cubemap_resolution': 32, 'lower_hemisphere_is_black': False,
        'lower_hemisphere_color': [0., 0., 0., 1.]}]})
    scene['materials'] = {'SkyDomePending': {'shading_model': 'Unlit', 'material_program': 'shader', 'render_tags': ['Sky']}}
    scene['instances'] = [{'id': 'SourceSky', 'material': 'SkyDomePending',
                           'source_material': '/Engine/EngineSky/M_SimpleSkyDome.M_SimpleSkyDome'}]
    return scene


class SkyLightCaptureTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('sky_light_capture'), 'Source SkyLight capture graph is missing')
        import sky_light_capture
        return sky_light_capture

    def test_source_settings_retain_position_resolution_intensity_and_explicit_pending_scope(self):
        settings = self.module().source_sky_light_settings(scene_fixture())
        self.assertEqual(settings['position_cm'], [120., -75., 610.])
        self.assertEqual(settings['width'], 32)
        self.assertEqual(settings['intensity'], 1.75)
        self.assertEqual(settings['capture_pre_exposure'], 1/16)
        self.assertEqual(settings['cached_lighting_pre_exposure_ev'], 4.)
        self.assertFalse(settings['runtime_exposure_verified'])

    def test_six_face_matrices_match_cube_direction_and_reversed_depth(self):
        module = self.module()
        position = np.array([120., -75., 610.])
        matrices = module.capture_view_projections(position.tolist())
        directions = cube_directions(8, normalized=False)
        for face, matrix in enumerate(matrices):
            world_ue = position/100 + directions[face]*10
            world_falcor = np.stack([world_ue[..., 1], world_ue[..., 2], -world_ue[..., 0]], axis=-1)
            clip = np.concatenate([world_falcor, np.ones((8, 8, 1))], axis=-1) @ np.array(matrix).T
            ndc = clip[..., :3] / clip[..., 3, None]
            y, x = np.mgrid[:8, :8]
            np.testing.assert_allclose(ndc[..., 0], (x+.5)/4-1, atol=1e-12)
            np.testing.assert_allclose(ndc[..., 1], 1-(y+.5)/4, atol=1e-12)
            np.testing.assert_allclose(ndc[..., 2], .05/10, atol=1e-12)



    def test_capture_wrapper_keeps_original_material_blocks_and_exposure_clamp_order(self):
        module = self.module()
        shader = module.CAPTURE_SHADER.read_text()
        self.assertIn('#include "../Atmosphere/UESkyMaterialPerspective.ush"', shader)
        self.assertIn('v.RenderingReflectionCaptureMask = 1.0f;', shader)
        self.assertIn('v.RealTimeReflectionCapture = 1.0f;', shader)
        self.assertIn('1.0f / gSkyPreExposure.Load(int3(0,0,0))', shader)
        self.assertLess(shader.index('emissive *= capturePreExposure;'), shader.index('emissive = min(emissive, 64512.0f);'))
        self.assertNotIn('gSkyFrameStatus', shader)
        self.assertNotIn('intensity', shader)



if __name__ == '__main__':
    unittest.main()
