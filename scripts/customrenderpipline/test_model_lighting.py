"""Contracts for real model Lighting programs; mathematical acceptance is GPU-side."""
import unittest


class ModelLightingTests(unittest.TestCase):
    def test_dark_absorption_keeps_target_hsv_denominator_behavior(self):
        import numpy as np
        from model_lighting_reference import absorption_color
        for color in ([.2,.1,.05],[.1,.2,.05],[.1,.05,.2]):
            actual=absorption_color(np.array(color),.05)
            self.assertTrue(np.all(actual>.19))
            self.assertAlmostEqual(float(actual.max()),.2)

if __name__ == '__main__':
    unittest.main()
