import unittest
from exposure_graph import histogram_exposure_fragment

class MeteringTests(unittest.TestCase):
    def test_default_downsample_is_ue_raster_branch(self):
        from downsample import downsample_fragment
        node=downsample_fragment('Scene.color')['nodes'][0]
        self.assertEqual(node['type'],'CustomRenderPiplineFullscreenPass')

    def test_separate_metering_and_application_inputs(self):
        fragment=histogram_exposure_fragment('Scene.color',metering_source='Half.color',metering_format='R11G11B10Float')
        self.assertIn(['Half.color','ExposureScatter.sceneColor'],fragment['edges'])
        self.assertIn(['Half.color','ExposureConvert.sceneColor'],fragment['edges'])
        self.assertIn(['Scene.color','ExposureApply.sceneColor'],fragment['edges'])
        nodes={n['name']:n['properties'] for n in fragment['nodes']}
        self.assertEqual(nodes['ExposureScatter']['resources'][0]['format'],'R11G11B10Float')
        self.assertEqual(nodes['ExposureApply']['resources'][-1]['size'],{'relative_to':'sceneColor','divisor':[1,1]})

    def test_metering_format_requires_separate_input(self):
        with self.assertRaises(ValueError):
            histogram_exposure_fragment('Scene.color',metering_format='R11G11B10Float')

if __name__=='__main__':unittest.main()
