"""CPU graph contract: source-only inputs, selected meshes, explicit storage."""
import json
from pathlib import Path
import unittest

from targetmap_native_graph import graph_definition

ROOT = Path(__file__).resolve().parents[2]


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT/'build/source-targetmap/Scene.json').read_text())
        self.graph = graph_definition(self.source, [1, 2, 3], [4], 'Mesh.slang', 'Codec.slangh')

    def test_only_original_asset_inputs(self):
        asset = self.graph['nodes'][0]['properties']['assets']['grid']
        self.assertEqual(asset['file'], self.source['source_texture']['original_export']['source_image']['path'])
        self.assertEqual(asset['mip_count'], 1)
        for term in ('SchemaPipeline', 'primitive_flags', '.rdc', 'reference-a-', 'Config.json'):
            self.assertNotIn(term, json.dumps(self.graph))

    def test_verified_source_platform_texture_and_anisotropy_are_independent(self):
        texture = {'capture_inputs': False, 'file': 'source/T_GridChecker_A.bc1.srgb.dds',
                   'format': 'BC1UnormSrgb', 'size': [512, 512], 'mip_count': 10, 'srgb': True}
        args = (self.source, [1, 2, 3], [4], 'Mesh.slang', 'Codec.slangh')
        one = graph_definition(*args, platform_texture=texture)
        eight = graph_definition(*args, platform_texture=texture, max_anisotropy=8)
        asset = one['nodes'][0]['properties']['assets']['grid']
        self.assertEqual(asset, {k:v for k,v in dict(texture, kind='texture2D').items() if k != 'capture_inputs'})
        floor = one['nodes'][3]['properties']
        self.assertEqual(floor['resources'][0]['format'], 'BC1UnormSrgb')
        self.assertEqual(floor['resources'][0]['mip_count'], 10)
        self.assertEqual(floor['samplers']['gGridSampler']['max_anisotropy'], 1)
        eight['nodes'][3]['properties']['samplers']['gGridSampler']['max_anisotropy'] = 1
        self.assertEqual(eight, one)
        for invalid in (True, 8.0, 0, 17):
            with self.assertRaises(ValueError):
                graph_definition(*args, max_anisotropy=invalid)
        for invalid in ({'capture_inputs': True}, {'mip_count': 1}, {'format': 'BGRA8UnormSrgb'}):
            with self.assertRaises(ValueError):
                graph_definition(*args, platform_texture=dict(texture, **invalid))

    def test_explicit_unscaled_frame_context(self):
        graph = graph_definition(self.source, [1, 2, 3], [4], 'Mesh.slang', 'Codec.slangh',
                                 render_context={'projection_resolution': [2465, 1795]})
        from targetmap_native import source_camera
        camera = dict(self.source['camera'], projection_resolution=[2465, 1795])
        self.assertEqual(graph['nodes'][1]['properties']['view_projection'], source_camera(camera)['view_projection'])
        self.assertNotIn('projection_resolution', self.source['camera'])

    def test_source_owned_frame_index(self):
        graph = graph_definition(self.source, [1, 2, 3], [4], 'Mesh.slang', 'Codec.slangh', frame_index=1)
        for node in graph['nodes'][2:]:
            self.assertEqual(node['properties']['uniforms']['Frame.phase']['value'], 1)
        for invalid in (-1, True, 2**32):
            with self.assertRaises(ValueError):
                graph_definition(self.source, [1], [2], 'Mesh.slang', 'Codec.slangh', frame_index=invalid)

    def test_viewport_depth_and_mesh_selection(self):
        pre = self.graph['nodes'][1]['properties']
        self.assertEqual(pre['instanceIDs'], [1, 2, 3, 4])
        self.assertEqual(pre['viewport'], [0, 0, 1421, 1035])
        self.assertEqual(pre['depthTarget']['size'], [1424, 1040])
        self.assertEqual(pre['depthTarget']['clear'], 0)
        self.assertTrue(pre['state']['depth_write'])
        self.assertEqual(pre['state']['depth_func'], 'GreaterEqual')
        for node, expected_ids in zip(self.graph['nodes'][2:], ([1, 2, 3], [4])):
            self.assertEqual(node['properties']['instanceIDs'], expected_ids)
            self.assertFalse(node['properties']['state']['depth_write'])
            self.assertEqual(node['properties']['depthTarget']['load'], 'load')

    def test_schema_slots_and_loaded_chain(self):
        basic, floor = (x['properties'] for x in self.graph['nodes'][2:])
        self.assertIn('ProcGridParams.tileSize', floor['uniforms'])
        self.assertNotIn('Grid.tileSize', floor['uniforms'])
        self.assertEqual([x['name'] for x in basic['colorTargets']], ['sceneColor', 'gbufferA', 'gbufferB', 'gbufferC', 'gbufferD'])
        self.assertEqual(basic['colorTargets'][3]['format'], 'BGRA8UnormSrgb')
        for item in floor['colorTargets']:
            self.assertEqual(item['load'], 'load')
            self.assertNotIn('clear', item)
            self.assertIn(['Basic.'+item['name'], 'Floor.'+item['name']], self.graph['edges'])

    def test_rejects_empty_or_overlapping_sets_and_capture_scene(self):
        for basic, floor in (([], [4]), ([1, 2], [2]), ([True], [4])):
            with self.assertRaises(ValueError):
                graph_definition(self.source, basic, floor, 'Mesh.slang', 'Codec.slangh')
        self.source['capture_inputs'] = True
        with self.assertRaises(ValueError):
            graph_definition(self.source, [1], [2], 'Mesh.slang', 'Codec.slangh')


if __name__ == '__main__':
    unittest.main()
