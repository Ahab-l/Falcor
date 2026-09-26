"""Mutation checks for the observation-only numerical acceptance gates."""
import copy
import unittest
import numpy as np
from atmosphere_validation import validate_medium, validate_transmittance_witness
from test_atmosphere_reference import atmosphere


def constant_observations():
    p = atmosphere(MieExtinction=[.1, .2, .3], MieAbsorption=[.1, .2, .3], MieDensityExpScale=0.)
    position = np.zeros((2, 2, 4), dtype=np.float32)
    position[..., 2:] = 11.
    path = np.zeros_like(position)
    path[..., 0] = 2.
    medium = np.ones_like(position)
    medium[..., :3] = p['MieExtinction']
    return p, {'probePosition': position, 'probePath': path, 'probeMedium': medium}


class AtmosphereValidationTests(unittest.TestCase):
    def test_medium_gate_detects_missing_extinction_or_bad_radius(self):
        p, o = constant_observations()
        validate_medium(p, o)
        for key, lane in [('probeMedium', 0), ('probePosition', 3)]:
            wrong = copy.deepcopy(o)
            wrong[key][..., lane] = 0
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate_medium(p, wrong)

    def test_transmittance_gate_rejects_zero_wrong_encoding_and_changed_density(self):
        p, o = constant_observations()
        expected = np.broadcast_to(np.exp(-np.array(p['MieExtinction'])), (1, 2, 3)).copy()
        validate_transmittance_witness(p, o, expected, (2, 1), 2.)
        for wrong in (np.zeros_like(expected), expected**2, np.sqrt(expected)):
            with self.assertRaises(AssertionError):
                validate_transmittance_witness(p, o, wrong, (2, 1), 2.)
        changed = copy.deepcopy(p)
        changed['MieExtinction'] = [v * 1.1 for v in p['MieExtinction']]
        with self.assertRaises(AssertionError):
            validate_transmittance_witness(changed, o, expected, (2, 1), 2.)


if __name__ == '__main__':
    unittest.main()
