"""The retired replay inputs must fail before resources are read or snapshotted."""
import unittest
from render_input_policy import validate_render_inputs


class RenderInputPolicyTests(unittest.TestCase):
    def test_native_scene_and_authored_controls_remain_valid(self):
        validate_render_inputs({'materials': {}, 'lighting': {'lights': [], 'view': {'min_roughness': 0.02}}},
                               {'preExposure': 1.25})

    def test_retired_capture_state_is_rejected_without_opening_resources(self):
        scenes = [
            {'captured_view': {}}, {'source_geometry': {'0': {}}}, {'primitive_flags': {'0': 0x02010A89}},
            {'csm_projection': {}}, {'csm_depth': {}},
            {'lighting': {'input_mode': 'reference_fixture'}},
            {'lighting': {'coordinate_space': 'translated_ue_cm'}},
        ]
        scenes += [{'lighting': {'resources': {name: 'Z:/missing-capture.dds'}}} for name in
                   ('scene_color_before', 'shadow_mask', 'scene_ao')]
        scenes += [{'lighting': {'view': {name: []}}} for name in
                   ('screen_to_translated_world_row_major', 'translated_camera_origin_ue', 'inv_device_z_to_world_z')]
        for scene in scenes:
            with self.subTest(scene=scene), self.assertRaisesRegex(ValueError, 'comparison-only'):
                validate_render_inputs(scene, {})
        for key in ('projectionDefinitionPath', 'depthDefinitionPath', 'projectionValidationBranch', 'depthValidationBranch'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'comparison-only'):
                validate_render_inputs({}, {key: 'disabled'})



if __name__ == '__main__':
    unittest.main()
