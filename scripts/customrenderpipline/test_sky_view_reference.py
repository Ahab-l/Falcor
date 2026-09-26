"""Analytic checks of the independent SkyView integration, without GPU inputs."""
import unittest
import numpy as np
from test_atmosphere_reference import atmosphere
from sky_view_reference import sky_view_directions,sky_view_reference

SETTINGS={'size':[17,11],'min_samples':4.,'max_samples':17.,'distance_to_max_inv':.2,'luminance_factor':[1,1,1]}
class SkyViewReferenceTests(unittest.TestCase):
    def test_mapping_poles_horizon_and_unit_directions(self):
        directions=sky_view_directions(10.1,10.,[17,11])
        np.testing.assert_allclose(np.linalg.norm(directions,axis=-1),1,atol=5e-15)
        np.testing.assert_allclose(directions[0,:,2],1,atol=1e-15)
        np.testing.assert_allclose(directions[-1,:,2],-1,atol=1e-15)
        np.testing.assert_allclose(directions[:,0],directions[:,-1],atol=1e-14)
        # Source acosFast4 approximates the geometric tangent by < 7e-5 rad.
        horizon=-np.sqrt(10.1**2-10**2)/10.1
        np.testing.assert_allclose(directions[5,:,2],horizon,atol=7e-5)

    def test_vacuum_is_black_with_unit_transmittance(self):
        result=sky_view_reference(atmosphere(),SETTINGS,10.1,[0,0,1],[1,1,1],np.ones((5,7,3)),np.zeros((4,4,3)))
        np.testing.assert_array_equal(result[...,:3],0)
        np.testing.assert_array_equal(result[...,3],1)

    def test_constant_absorber_obeys_beer_law_for_variable_fractional_steps(self):
        p=atmosphere(MieExtinction=[.2]*3,MieAbsorption=[.2]*3,MieDensityExpScale=0.)
        result=sky_view_reference(p,SETTINGS,10.1,[0,0,1],[1,1,1],np.ones((5,7,3)),np.zeros((4,4,3)))
        directions=sky_view_directions(10.1,10.,SETTINGS['size'])
        z=directions[...,2];b=10.1*z
        top=-b+np.sqrt(b*b+12**2-10.1**2)
        disc=b*b+10**2-10.1**2;near=-b-np.sqrt(np.maximum(0,disc))
        distance=np.where((disc>=0)&(near>=0),near,top)
        np.testing.assert_allclose(result[...,3],np.exp(-.2*distance),rtol=2e-14)
        np.testing.assert_array_equal(result[...,:3],0)

    def test_scattering_is_linear_in_exposure_and_light_and_uses_ms(self):
        p=atmosphere(RayleighScattering=[.02]*3,RayleighDensityExpScale=0.)
        args=(p,SETTINGS,10.1,[0,0,1],[1,2,3],np.ones((5,7,3)))
        a=sky_view_reference(*args,np.zeros((4,4,3)))
        b=sky_view_reference(*args,np.ones((4,4,3))*.01)
        self.assertTrue(np.all(b[...,:3]>a[...,:3]))
        c=sky_view_reference(*args,np.ones((4,4,3))*.01,pre_exposure=3)
        np.testing.assert_allclose(c[...,:3],3*b[...,:3],rtol=1e-14)
        np.testing.assert_array_equal(c[...,3],b[...,3])

if __name__=='__main__':unittest.main()
