"""CPU contract tests for the source SkyLight filtering graph and adapters."""
import importlib.util
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SkyLightFilterTests(unittest.TestCase):
    def factory(self):
        self.assertIsNotNone(importlib.util.find_spec('sky_light_filter'),
                             'The reusable source SkyLight filtering graph is missing')
        from sky_light_filter import sky_light_filter_fragment
        return sky_light_filter_fragment

    def test_mip_generation_aliases_preceding_mip_and_convolution_uses_distinct_cube(self):
        graph = self.factory()('Capture.cube', width=32, output_format='R11G11B10Float')
        self.assertEqual(len(graph['nodes']), 12)
        by_name = {node['name']: node for node in graph['nodes']}
        previous = 'Capture.cube'
        for mip in range(1, 6):
            name = f'SkyLightDownsample{mip}'
            p = by_name[name]['properties']
            src, dst = p['resources']
            self.assertEqual(src['view'], {'mip': mip - 1, 'mip_count': 1})
            self.assertEqual(dst['view'], {'mip': mip})
            self.assertEqual(dst['direction'], 'inputOutput')
            self.assertIn([previous, name + '.source'], graph['edges'])
            self.assertIn([previous, name + '.cube'], graph['edges'])
            previous = name + '.cube'
        convolved = None
        for mip in range(6):
            name = f'SkyLightFilter{mip}'
            p = by_name[name]['properties']
            src, dst = p['resources']
            self.assertEqual(src['view'], {'mip': 0, 'mip_count': 6})
            self.assertIn([previous, name + '.source'], graph['edges'])
            self.assertEqual(dst['direction'], 'output' if mip == 0 else 'inputOutput')
            if convolved:
                self.assertIn([convolved, name + '.cube'], graph['edges'])
            convolved = name + '.cube'
        sh = by_name['SkyLightDiffuseSH']['properties']
        self.assertIn([convolved, 'SkyLightDiffuseSH.source'], graph['edges'])
        self.assertEqual(sh['resources'][1], {'name': 'sh', 'direction': 'output',
            'binding': 'OutIrradianceEnvMapSH', 'kind': 'structured_buffer', 'stride': 16, 'count': 8})
        self.assertEqual(sh['uniforms']['MipIndex'], {'type': 'uint', 'value': 1})
        self.assertEqual(sh['dispatch'], {'threads': [8, 8, 1]})
        self.assertAlmostEqual(sh['uniforms']['UniformSampleSolidAngle']['value'], 4 * math.pi / 64)
        self.assertEqual(graph['outputs'], [previous, convolved, 'SkyLightDiffuseSH.sh'])

    def test_dispatch_is_original_faces_along_x_including_padded_small_mips(self):
        graph = self.factory()('Capture.cube', width=16, output_format='RGBA32Float', prefix='Probe')
        for node in graph['nodes'][:-1]:
            p = node['properties']
            mip = p['uniforms']['MipIndex']['value']
            extent = 16 >> mip
            padded = ((extent + 7) // 8) * 8
            self.assertEqual(p['dispatch'], {'threads': [padded * 6, padded, 1]})
            self.assertEqual(p['uniforms']['FaceThreadGroupSize'], {'type': 'int', 'value': padded})
            self.assertEqual(p['uniforms']['ValidDispatchCoord'], {'type': 'int2', 'value': [extent, extent]})
            self.assertEqual(p['samplers'], {'SourceCubemapSampler': {'filter': 'Point', 'address': 'Clamp'}})
            for resource in p['resources']:
                self.assertEqual((resource['kind'], resource['size'], resource['mip_count']),
                                 ('textureCube', [16, 16], 5))
            self.assertEqual(node['file_inputs'], ['shader.file'])

    def test_rejects_incompatible_capture_contract(self):
        factory = self.factory()
        for width in (True, 0, 8, 17, 16.0, 32768):
            with self.subTest(width=width), self.assertRaisesRegex(ValueError, 'width'):
                factory('Capture.cube', width=width, output_format='RGBA32Float')
        for name in ('Capture', 'A.B.C', '', 'A.$packed'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'capture'):
                factory(name, width=16, output_format='RGBA32Float')
        for fmt in ('RGBA8Unorm', 'RGB32Float', None):
            with self.subTest(fmt=fmt), self.assertRaisesRegex(ValueError, 'format'):
                factory('Capture.cube', width=16, output_format=fmt)
        with self.assertRaisesRegex(ValueError, 'prefix'):
            factory('Capture.cube', width=16, output_format='RGBA32Float', prefix='bad.prefix')

    def test_original_kernels_are_retained_with_only_include_adaptation_for_sh(self):
        self.factory()
        directory = ROOT / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'
        adapter = directory / 'SkyLight'
        for name, original in (('Downsample.slang', 'UESkyLightDownsample.ush'),
                               ('Filter.slang', 'UESkyLightFilter.ush')):
            self.assertIn('#include "../' + original + '"', (adapter / name).read_text())
        expected = (directory / 'UESkyLightDiffuseSH.ush').read_text()
        expected = expected.replace('#include "SHCommon.ush"', '#include "Helpers.slangh"')
        expected = expected.replace('#include "MonteCarlo.ush"', '#include "Helpers.slangh"')
        self.assertEqual((adapter / 'DiffuseSHOriginal.slangh').read_text(), expected)
        platform = (adapter / 'Platform.slangh').read_text()
        self.assertIn('#include "../UESkyLightPlatformOriginal.ush"', platform)
        self.assertIn('#define PLATFORM_SUPPORTS_REAL_TYPES 0', platform)
        self.assertIn('#define PLATFORM_SUPPORTS_RELAXED_PRECISION 0', platform)


    def test_offline_cube_oracle_round_trips_all_faces_and_mips(self):
        self.assertIsNotNone(importlib.util.find_spec('sky_light_filter_reference'), 'Offline SkyLight oracle is missing')
        import numpy as np
        from sky_light_filter_reference import cube_directions, sample_cube
        for width in (1, 2, 16):
            values = np.arange(6 * width * width * 3).reshape(6, width, width, 3)
            np.testing.assert_array_equal(sample_cube([values], cube_directions(width), 0), values)

    def test_point_cube_candidates_only_admit_numerical_texel_and_face_ties(self):
        import numpy as np
        import sky_light_filter_reference as smoke
        self.assertTrue(hasattr(smoke, 'point_cube_candidates'), 'Point-Cube boundary oracle is missing')
        cube = np.arange(6*4*4*3).reshape(6,4,4,3)
        candidates = smoke.point_cube_candidates(cube, [1., 0., 0.])
        self.assertEqual(len(candidates), 4)
        self.assertEqual(len(smoke.point_cube_candidates(cube, [1., .01, .01])), 1)
        candidates = smoke.point_cube_candidates(cube, [1., 1., 0.])
        self.assertEqual(len(candidates), 4)
        self.assertTrue(all(any(np.array_equal(v, c) for c in cube.reshape(-1, 3)) for v in candidates))

    def test_downsample_acceptance_requires_a_whole_rgb_candidate(self):
        import numpy as np
        import sky_light_filter_reference as smoke
        self.assertTrue(hasattr(smoke, 'downsample_candidate_error'), 'Correlated RGB downsample oracle is missing')
        cube = smoke.authored_direction_color(smoke.cube_directions(4))
        expected = smoke.downsample_reference(cube)
        self.assertLess(smoke.downsample_candidate_error(cube, expected), 1e-12)
        altered = expected.copy()
        altered[0, 0, 0, 1] += .1
        self.assertGreater(smoke.downsample_candidate_error(cube, altered), .05)
        # Whole RGB boundary alternatives must never admit a different output
        # face or a neighboring output texel away from the specific tap ties.
        cube = smoke.authored_direction_color(smoke.cube_directions(8))
        expected = smoke.downsample_reference(cube)
        self.assertGreater(smoke.downsample_candidate_error(cube, np.roll(expected,1,axis=0)), .1)
        self.assertGreater(smoke.downsample_candidate_error(cube, np.roll(expected,1,axis=2)), .1)

    def test_direction_only_observation_adapters_preserve_source_without_unused_globals(self):
        adapter = ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/SkyLight'
        original = (adapter.parent/'UESkyLightCubeCommon.ush').read_text()
        start = original.index('float3 GetCubemapVector(')
        end = original.index('\nTextureCube SourceCubemapTexture;')
        self.assertTrue((adapter/'CubeDirections.slangh').read_text().rstrip().endswith(original[start:end].strip()))
        for filename in ('Fixture.slang', 'Readback.slang'):
            source = (adapter/filename).read_text()
            self.assertIn('#include "CubeDirections.slangh"', source)
            self.assertNotIn('#include "CubeCommon.slangh"', source)
            self.assertNotIn('SourceMipIndex', source)

    def test_offline_sh_oracle_has_source_brightness_and_directional_signs(self):
        self.assertIsNotNone(importlib.util.find_spec('sky_light_filter_reference'), 'Offline SkyLight oracle is missing')
        import numpy as np
        from sky_light_filter_reference import cube_directions, sh_reference
        directions = cube_directions(32)
        constant = np.broadcast_to([1., 2., 4.], directions.shape)
        sh = sh_reference([constant], 0)
        np.testing.assert_allclose(sh[7], (1 + 2 + 4) * .3333, atol=1e-12)
        self.assertEqual(sh[6, 3], 1.)
        gradient = constant + directions * .25
        sh = sh_reference([gradient], 0)
        for channel in range(3):
            self.assertGreater(sh[channel, channel], .14)
            for axis in range(3):
                if axis != channel:
                    self.assertLess(abs(sh[channel, axis]), 1e-12)


if __name__ == '__main__':
    unittest.main()
