import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_fy1_hair_case import build_case


REFERENCE = Path(r'D:/BaiduNetdiskDownload/RenderDocPro_1.44.0-pro.4_64/analysis/hair_fy1')


class FY1HairCaseTests(unittest.TestCase):
    def test_builds_native_geometry_material_and_deferred_graph(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            manifest = build_case(REFERENCE, output)
            self.assertEqual(manifest['hair']['vertices'], 13828)
            self.assertEqual(manifest['hair']['indices'], 53676)
            self.assertEqual([(m['event_id'], m['vertices'], m['indices']) for m in manifest['occluders']],
                             [(4205, 7115, 41400), (4316, 201, 1140)])
            self.assertFalse(manifest['capture_inputs_in_production'])
            self.assertEqual(manifest['target_stage'], 'EID14389 independent deferred Shading')
            self.assertEqual(manifest['resolution'], [2568, 1448])
            self.assertEqual(manifest['viewport'], [0, 0, 2562, 1441])
            for name, identity in manifest['files'].items():
                path = output/name
                self.assertTrue(path.is_file(), name)
                self.assertEqual(path.stat().st_size, identity['bytes'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), identity['sha256'])
            scene = json.loads((output/'Scene.json').read_text())
            self.assertEqual([i['material'] for i in scene['instances']], ['FY1Hair', 'Occluder4205', 'Occluder4316'])
            self.assertTrue(scene['materials']['FY1Hair']['two_sided'])
            graph = json.loads((output/'Passes.json').read_text())
            self.assertEqual([n['type'] for n in graph['nodes']],
                             ['CustomRenderPiplineAssetPass', 'CustomRenderPiplineMeshDrawPass', 'CustomRenderPiplineMeshDrawPass', 'CustomRenderPiplineFullscreenPass'])
            self.assertEqual([n['name'] for n in graph['nodes']], ['Assets', 'OccluderDepth', 'HairBase', 'HairLighting'])
            hair_depth = graph['nodes'][2]['properties']['depthTarget']
            self.assertEqual(hair_depth['load'], 'load')
            self.assertNotIn('clear', hair_depth)
            self.assertNotIn('stencilClear', hair_depth)
            edges = {tuple(edge) for edge in graph['edges']}
            self.assertIn(('OccluderDepth.depth', 'HairBase.depth'), edges)
            for port in ('gbufferA', 'gbufferB', 'gbufferC', 'depth'):
                self.assertIn((f'HairBase.{port}', f'HairLighting.{port}'), edges)
            serialized = json.dumps(graph).lower()
            for forbidden in ('coverage_7861', 'capture_shading', 'scenecolor14389', 'shadow.virtual.maskbits',
                              't2_scenedepthz', 't3_gbuffera', 't4_gbufferb', 't5_gbufferc'):
                self.assertNotIn(forbidden, serialized)
            self.assertIn('postvs.bin', serialized)
            self.assertIn('alpha.dds', serialized)


if __name__ == '__main__':
    unittest.main()
