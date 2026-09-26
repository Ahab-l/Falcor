import math,unittest
from exposure import HistogramExposureSettings as Settings

class ExposureSettingsTests(unittest.TestCase):
    def test_default_ev_units_and_independent_ranges(self):
        p=Settings.from_dict({}).parameters(delta_time=0.25,history_valid=True)
        self.assertAlmostEqual(p['EyeAdaptation_MinAverageLuminance'],0.18/1024)
        self.assertAlmostEqual(p['EyeAdaptation_MaxAverageLuminance'],0.18*1048576,places=1)
        self.assertAlmostEqual(p['EyeAdaptation_HistogramScale'],1/30)
        self.assertAlmostEqual(p['EyeAdaptation_HistogramBias'],1/3)
        self.assertEqual(p['EyeAdaptation_ExposureCompensationSettings'],2)
        self.assertEqual(p['EyeAdaptation_DeltaWorldTime'],0.25)
        self.assertEqual(p['EyeAdaptation_ForceTarget'],0)
        self.assertEqual(p['EyeAdaptation_LuminanceWeights'],[1/3]*3)
        q=Settings.from_dict({'min_brightness':0,'max_brightness':2}).parameters(delta_time=0,history_valid=True)
        self.assertEqual(q['EyeAdaptation_HistogramScale'],p['EyeAdaptation_HistogramScale'])
        self.assertAlmostEqual(q['EyeAdaptation_MaxAverageLuminance'],0.72)

    def test_lens_units_shift_histogram_and_white_point_consistently(self):
        p=Settings.from_dict({'lens_attenuation':0.39}).parameters(delta_time=0,history_valid=True)
        self.assertEqual(p['EyeAdaptation_LuminanceMax'],2)
        self.assertAlmostEqual(p['EyeAdaptation_LuminanceMin'],2/1024)
        self.assertAlmostEqual(p['EyeAdaptation_HistogramBias'],9/30)
        self.assertAlmostEqual(p['EyeAdaptation_MinAverageLuminance'],0.36/1024)

    def test_percentile_and_range_degeneracy_follow_ue(self):
        s=Settings.from_dict({'low_percent':200,'high_percent':-5,'min_brightness':4,'max_brightness':2,
                             'histogram_min':30,'histogram_max':20})
        p=s.parameters(delta_time=0,history_valid=True)
        self.assertEqual(p['EyeAdaptation_ExposureLowPercent'],0.01)
        self.assertEqual(p['EyeAdaptation_ExposureHighPercent'],0.01)
        self.assertEqual(p['EyeAdaptation_ForceTarget'],1)
        self.assertEqual(p['EyeAdaptation_MinAverageLuminance'],p['EyeAdaptation_MaxAverageLuminance'])
        self.assertEqual(p['EyeAdaptation_HistogramScale'],1)
        self.assertEqual(p['EyeAdaptation_HistogramBias'],-19)

    def test_transition_slope_matches_linear_at_one_sixtieth_second(self):
        p=Settings.from_dict({}).parameters(delta_time=0.137,history_valid=True)
        for which in ('Up','Down'):
            speed=p['EyeAdaptation_ExposureSpeed'+which]
            movement=p['EyeAdaptation_StartDistance']*(1-2**(-speed/60))*p['EyeAdaptation_Exponential'+which+'M']
            self.assertAlmostEqual(movement,speed/60)
        self.assertEqual(p['EyeAdaptation_DeltaWorldTime'],0.137)

    def test_cut_and_invalid_history_force_target(self):
        s=Settings.from_dict({})
        for kwargs in ({'history_valid':False},{'history_valid':True,'camera_cut':True}):
            self.assertEqual(s.parameters(delta_time=0,**kwargs)['EyeAdaptation_ForceTarget'],1)

    def test_working_space_method_requires_authored_coefficients(self):
        with self.assertRaises(ValueError):Settings.from_dict({'luminance_method':2})
        weights=[0.25,0.625,0.125]
        p=Settings.from_dict({'luminance_method':2,'working_luminance_weights':weights}).parameters(delta_time=0,history_valid=True)
        self.assertEqual(p['EyeAdaptation_LuminanceWeights'],weights)

    def test_invalid_authoring_and_nonfinite_derived_values_reject(self):
        for settings in ({'speed_up':0},{'speed_down':0.019},{'transition_distance':0},{'lens_attenuation':float('nan')},
                         {'bias_ev':10000},{'max_brightness':10000},{'min_brightness':-10000},
                         {'speed_up':True},{'unknown':1},{'extended':1},{'black_bucket_influence':2},
                         {'luminance_method':True}):
            with self.subTest(settings=settings),self.assertRaises(ValueError):Settings.from_dict(settings)
        s=Settings.from_dict({})
        for dt in (True,-1,float('inf')):
            with self.assertRaises(ValueError):s.parameters(delta_time=dt,history_valid=True)

if __name__=='__main__':unittest.main()
