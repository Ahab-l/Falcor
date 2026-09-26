import copy
import unittest
from test_atmosphere import inventory
from atmosphere import source_atmosphere
from sky_view import source_sky_view_settings


def source_scene():
    inv=inventory();component=inv['actors'][0]['environment'][0]
    component.update(world_location_cm=[0,0,-6000],transform_mode='<SkyAtmosphereTransformMode.PLANET_TOP_AT_COMPONENT_TRANSFORM: 1>',
        trace_sample_count_scale=1,sky_and_aerial_perspective_luminance_factor=[1,.5,.25,1])
    inv['atmosphere_source_defaults'].update({'r.SkyAtmosphere.FastSkyLUT'+k:v for k,v in
        {'':1,'.Width':192,'.Height':104,'.SampleCountMin':4,'.SampleCountMax':128,'.DistanceToSampleCountMax':150}.items()})
    physical,luts=source_atmosphere(inv)
    env={'actors':inv['actors'],'source_defaults':inv['atmosphere_source_defaults'],
        'defaults_provenance':'authored source settings','renderer_source_settings':inv['renderer_source_settings'],
        'atmosphere_parameters':physical,'atmosphere_lut_settings':luts}
    return {'source_environment':env,'lighting':{'lights':[{'direction_ue':[0,0,1],
        'source_sun':{'atmosphere':physical}}]}}


class SkyViewTests(unittest.TestCase):
    def test_source_sampling_applies_component_scale_and_clamps_in_ue_order(self):
        scene=source_scene();setup,settings=source_sky_view_settings(scene)
        self.assertEqual(setup['transform_mode'],1)
        self.assertEqual(setup['component_translation_cm'],[0,0,-6000])
        self.assertEqual(settings['size'],[192,104])
        self.assertEqual((settings['min_samples'],settings['max_samples']),(4,32))
        self.assertAlmostEqual(settings['distance_to_max_inv'],1/150)
        env=scene['source_environment'];env['actors'][0]['environment'][0]['trace_sample_count_scale']=0
        self.assertEqual(source_sky_view_settings(scene)[1]['max_samples'],4)
        env['source_defaults']['r.SkyAtmosphere.FastSkyLUT.SampleCountMin']=256
        self.assertEqual(source_sky_view_settings(scene)[1]['max_samples'],256)


    def test_invalid_settings_and_transform_modes_reject(self):
        for key,value in [('transform_mode','unsupported'),('trace_sample_count_scale',float('nan'))]:
            scene=source_scene();scene['source_environment']['actors'][0]['environment'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):source_sky_view_settings(scene)



if __name__=='__main__':unittest.main()
