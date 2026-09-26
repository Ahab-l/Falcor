import unittest
from output_catalog import OutputCatalog

class OutputViewTests(unittest.TestCase):
    def setUp(self):
        self.cube={'name':'Sky.cube','kind':'textureCube','format':'RGBA32Float','width':16,'height':16,'mip_count':4,'array_size':1}
        self.sh={'name':'Sky.sh','kind':'structured_buffer','format':'Unknown','bytes':128,'stride':16,'count':8}
    def test_cube_and_structured_metadata(self):
        c=OutputCatalog([self.cube,self.sh])
        self.assertEqual(c.outputs[0].mip_count,4)
        self.assertEqual(c.outputs[1].stride,16)
    def test_explicit_selected_mip_and_face(self):
        c=OutputCatalog([self.cube])
        layout=c.atlas_layout(['Sky.cube'],views={'Sky.cube':{'mip':2,'slice':5}})
        self.assertEqual(layout['tiles'][0]['view'],{'mip':2,'slice':5})
        for view in ({'mip':4},{'slice':6},{'slice':-1},{'mip':True},{'face':0}):
            with self.assertRaises(ValueError):c.atlas_layout(['Sky.cube'],views={'Sky.cube':view})
    def test_shape_validation(self):
        for value in ({**self.cube,'height':8},{**self.cube,'mip_count':6},{**self.cube,'array_size':2},
                      {**self.sh,'stride':12},{**self.sh,'count':True}):
            with self.assertRaises(ValueError):OutputCatalog([value])
    def test_structured_display_is_explicit(self):
        c=OutputCatalog([self.sh])
        with self.assertRaises(ValueError):c.atlas_layout(['Sky.sh'])
        self.assertEqual(c.atlas_layout(['Sky.sh'],displays={'Sky.sh':{'mode':'float32'}})['tiles'][0]['display']['mode'],'float32')
    def test_same_cube_distinct_views_in_one_atlas(self):
        c=OutputCatalog([self.cube])
        selections=[{'name':'Sky.cube','mip':1,'slice':face} for face in range(6)]
        layout=c.atlas_views_layout(selections,tile_extent=(8,8),columns=3)
        self.assertEqual((layout['width'],layout['height']),(24,16))
        self.assertEqual([t['view']['slice'] for t in layout['tiles']],list(range(6)))
        for invalid in ([selections[0],selections[0]],[{'name':'Sky.cube','slice':6}],
                        [{'name':'Sky.cube','extra':0}]):
            with self.assertRaises(ValueError):c.atlas_views_layout(invalid)
