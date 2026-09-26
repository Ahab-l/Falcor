"""Source input plumbing, independent of the native derived-color implementation."""
import unittest
import sun_setup

class SourceSunTests(unittest.TestCase):
    def test_source_settings_preserve_bytes_temperature_and_physical_parameters(self):
        light={'light_color':[128,64,196,255],'intensity':6,'use_temperature':True,'temperature':6500,
            'atmosphere_sun_light':True,'atmosphere_sun_light_index':0,'per_pixel_atmosphere_transmittance':False,
            'light_source_angle':.7,'light_source_soft_angle':0,'atmosphere_sun_disk_color_scale':[1,.5,.25,1]}
        component={'class':'SkyAtmosphereComponent','transmittance_min_light_elevation_angle':-90,
            'light_direction_overrides':[{'enabled':False},{'enabled':False}]}
        p={k:0 for k in sun_setup.ATMOSPHERE_FIELDS}
        env={'actors':[{'environment':[component]}],'atmosphere_parameters':p,'working_color_space':{'name':'sRGB'}}
        result=sun_setup.source_sun_settings(light,env)
        self.assertEqual(result['color_srgb'],[128,64,196])
        self.assertEqual(result['temperature_kelvin'],6500)
        self.assertEqual(result['atmosphere'],p)
        self.assertEqual(result['disk_color_scale'],[1,.5,.25])
        self.assertNotIn('direct_illuminance',result)
        self.assertNotIn('direction_ue',result)
        for key,value in [('per_pixel_atmosphere_transmittance',True),('atmosphere_sun_light_index',1),('light_source_soft_angle',1)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                sun_setup.source_sun_settings(dict(light,**{key:value}),env)
        component['light_direction_overrides'][0]['enabled']=True
        with self.assertRaises(ValueError):sun_setup.source_sun_settings(light,env)

if __name__=='__main__':unittest.main()
