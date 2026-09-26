import unittest
import numpy as np
from sky_material_reference import (perspective_directions,sky_uv,sky_color,
    constant_sky_quantization_bounds,positive_half_toward_zero)


class SkyMaterialReferenceTests(unittest.TestCase):
    def test_quantization_enclosure_rejects_half_noise_amplitude(self):
        y,x=np.mgrid[:193,:257]
        uv=np.stack((x+.5,y+.5),axis=-1)
        noise=np.mod(52.9829189*np.mod(uv@np.array([.06711056,.00583715]),1),1)
        base=np.array([2,4,8])*np.float32(1.1);step=np.array([2,4,8])/1024
        lower,upper=constant_sky_quantization_bounds((257,193),0,[2,4,8],[1.1]*3)
        original=positive_half_toward_zero(base+step*noise[...,None])
        self.assertTrue(np.all((original>=lower)&(original<=upper)))
        wrong=positive_half_toward_zero(base+.5*step*noise[...,None])
        self.assertGreater(np.count_nonzero((wrong<lower)|(wrong>upper)),10000)

    def setup(self):
        setup=np.zeros((10,4),dtype=np.float32)
        setup[1]=[0,0,-1100000,1100000]
        setup[2:5,:3]=np.eye(3)
        setup[6,:3]=[1,0,0]
        setup[8]=[16,32,64,.12]
        return setup

    def test_center_ray_uses_native_falcor_to_ue_axes(self):
        rays=perspective_directions([0,0,0],[0,0,-1],[0,1,0],24,24,(5,3))
        np.testing.assert_array_equal(rays[1,2],[1,0,0])
        np.testing.assert_allclose(np.linalg.norm(rays,axis=-1),1,atol=1e-14)
        self.assertGreater(rays[1,4,1],0)
        self.assertGreater(rays[0,2,2],0)

    def test_ground_and_sky_map_to_opposite_halves(self):
        d=np.array([[.8,0,.6],[.8,0,-.6]])
        uv=sky_uv(d,self.setup(),10,(192,104))
        self.assertTrue(np.isfinite(uv).all())
        self.assertLess(uv[0,1],.5)
        self.assertGreater(uv[1,1],.5)

    def test_constant_transmittance_disk_and_exposure_are_analytic(self):
        directions=perspective_directions([0,0,0],[0,0,-1],[0,1,0],24,24,(5,3))
        setup=self.setup();sky=np.ones((8,16,3))*[2,4,8]
        trans=np.ones((8,16,3))*[.5,.75,1]
        physical={'BottomRadiusKm':10,'TopRadiusKm':12}
        a,_,disk=sky_color(directions,setup,physical,sky,trans,[1,1,1],1,0)
        np.testing.assert_allclose(disk[1,2],[4,18,64],atol=1e-12)
        self.assertTrue(np.all(disk[0,0]==0))
        b,_,_=sky_color(directions,setup,physical,sky*4,trans,[1,1,1],4,0)
        np.testing.assert_array_equal(b,a*4)
        c,_,_=sky_color(directions,setup,physical,sky,trans,[1,1,1],1,8)
        np.testing.assert_array_equal(c,a)
        setup[1,:3]=[1100000,0,0]
        _,_,blocked=sky_color(directions,setup,physical,sky,trans,[1,1,1],1,0)
        np.testing.assert_array_equal(blocked[1,2],0)


if __name__=='__main__':unittest.main()
