import unittest
import numpy as np
from downsample_reference import downsample_reference,pack_r11g11b10,unpack_r11g11b10

class DownsampleReferenceTests(unittest.TestCase):
    def test_odd_viewport_sample_centers_and_high_kernel(self):
        image=np.array([[[0],[1],[0]]],dtype=np.float32)
        np.testing.assert_array_equal(downsample_reference(image),[[[.25],[.25]]])
        np.testing.assert_array_equal(downsample_reference(image,'high'),[[[.375],[.375]]])

    def test_unsigned_float_known_codes_and_rounding(self):
        one=(15<<6)|((15<<6)<<11)|((15<<5)<<22)
        self.assertEqual(pack_r11g11b10([1,1,1]).item(),one)
        np.testing.assert_array_equal(unpack_r11g11b10(np.uint32(one)),[1,1,1,1])
        np.testing.assert_array_equal(unpack_r11g11b10(pack_r11g11b10([2**-20,2**-20,2**-19])),
                                      [2**-20,2**-20,2**-19,1])
        a=[1+3/128,1+3/128,1+3/64]
        np.testing.assert_array_equal(unpack_r11g11b10(pack_r11g11b10(a)),[1+2/64,1+2/64,1+2/32,1])
        np.testing.assert_array_equal(unpack_r11g11b10(pack_r11g11b10(a,rounding='toward_zero')),
                                      [1+1/64,1+1/64,1+1/32,1])

if __name__=='__main__':unittest.main()
