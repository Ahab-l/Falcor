"""Analytic checks for the independent, offline atmosphere LUT oracle."""

import unittest

import numpy as np

from atmosphere_reference import (
    multi_scattering_reference,
    sample_encoded_transmittance,
    transmittance_reference,
)


def atmosphere(**changes):
    """Small planet with a vacuum; coefficients use UE's kilometer units."""
    parameters = {
        "BottomRadiusKm": 10.0,
        "TopRadiusKm": 12.0,
        "GroundAlbedo": [0.0, 0.0, 0.0],
        "MultiScatteringFactor": 1.0,
        "RayleighScattering": [0.0, 0.0, 0.0],
        "RayleighDensityExpScale": -0.125,
        "MieScattering": [0.0, 0.0, 0.0],
        "MieAbsorption": [0.0, 0.0, 0.0],
        "MieExtinction": [0.0, 0.0, 0.0],
        "MiePhaseG": 0.8,
        "MieDensityExpScale": -1.0 / 1.2,
        "AbsorptionExtinction": [0.0, 0.0, 0.0],
        "AbsorptionDensity0LayerWidth": 25.0,
        "AbsorptionDensity0LinearTerm": 1.0 / 15.0,
        "AbsorptionDensity0ConstantTerm": -2.0 / 3.0,
        "AbsorptionDensity1LinearTerm": -1.0 / 15.0,
        "AbsorptionDensity1ConstantTerm": 8.0 / 3.0,
    }
    parameters.update(changes)
    return parameters


def top_distances(size, bottom=10.0, top=12.0):
    """The LUT's x coordinate interpolates the two limiting path lengths."""
    width, height = size
    u = (np.arange(width) + 0.5) / width
    rho = np.sqrt(top**2 - bottom**2) * (np.arange(height) + 0.5) / height
    radii = np.hypot(rho, bottom)
    near = top - radii
    far = rho + np.sqrt(top**2 - bottom**2)
    return near[:, None] * (1.0 - u) + far[:, None] * u


class TransmittanceReferenceTests(unittest.TestCase):
    def test_vacuum_is_encoded_one(self):
        actual = transmittance_reference(atmosphere(), size=(9, 5))
        self.assertEqual(actual.dtype, np.dtype(np.float64))
        np.testing.assert_array_equal(actual, np.ones((5, 9, 3)))

    def test_constant_absorber_obeys_beer_law_and_sqrt_encoding(self):
        extinction = np.array([0.05, 0.1, 0.2])
        parameters = atmosphere(MieExtinction=extinction, MieDensityExpScale=0.0)
        actual = transmittance_reference(parameters, size=(7, 4))
        expected = np.exp(-0.5 * top_distances((7, 4))[..., None] * extinction)
        np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=1e-14)

    def test_fractional_count_keeps_step_length_and_ceiling_iterations(self):
        parameters = atmosphere(MieExtinction=[0.1] * 3, MieDensityExpScale=0.0)
        actual = transmittance_reference(parameters, size=(3, 2), sample_count=10.5)
        expected = np.exp(-0.5 * top_distances((3, 2)) * 0.1 * 11.0 / 10.5)
        np.testing.assert_allclose(actual[..., 0], expected, rtol=1e-13)

    def test_extinction_uses_mie_extinction_field(self):
        parameters = atmosphere(MieExtinction=[0.1] * 3, MieDensityExpScale=0.0)
        expected = transmittance_reference(parameters, size=(3, 2))
        parameters["MieAbsorption"] = [9.0, 8.0, 7.0]
        np.testing.assert_array_equal(transmittance_reference(parameters, size=(3, 2)), expected)

    def test_constant_rayleigh_mie_and_clamped_ozone_add(self):
        parameters = atmosphere(
            RayleighScattering=[0.02] * 3, RayleighDensityExpScale=0.0,
            MieExtinction=[0.03] * 3, MieDensityExpScale=0.0,
            AbsorptionExtinction=[0.05] * 3,
            AbsorptionDensity0LayerWidth=1.0,
            AbsorptionDensity0LinearTerm=0.0, AbsorptionDensity0ConstantTerm=2.0,
            AbsorptionDensity1LinearTerm=0.0, AbsorptionDensity1ConstantTerm=2.0,
        )
        actual = transmittance_reference(parameters, size=(5, 3))
        expected = np.exp(-0.5 * top_distances((5, 3)) * 0.1)
        np.testing.assert_allclose(actual[..., 0], expected, rtol=1e-13)

    def test_one_sample_uses_point_three_offset_and_exponential_density(self):
        # The single center texel defines one path. Its extinction is sampled
        # 30 percent along that path, not at its midpoint or either endpoint.
        parameters = atmosphere(MieExtinction=[0.1] * 3, MieDensityExpScale=-0.7)
        distance = top_distances((1, 1))[0, 0]
        radius = np.hypot(0.5 * np.sqrt(12.0**2 - 10.0**2), 10.0)
        cosine = (12.0**2 - radius**2 - distance**2) / (2.0 * radius * distance)
        t = 0.3 * distance
        altitude = np.sqrt(radius**2 + 2.0 * radius * t * cosine + t**2) - 10.0
        expected = np.exp(-0.5 * distance * 0.1 * np.exp(-0.7 * altitude))
        actual = transmittance_reference(parameters, size=(1, 1), sample_count=1.0)
        np.testing.assert_allclose(actual, expected, rtol=1e-13)

    def test_fp32_mode_is_explicit_and_preserves_output_type(self):
        actual = transmittance_reference(atmosphere(), size=(3, 2), dtype=np.float32)
        self.assertEqual(actual.dtype, np.dtype(np.float32))
        np.testing.assert_array_equal(actual, np.ones((2, 3, 3)))

    def test_invalid_inputs_fail_before_integration(self):
        for count in (0, -1, np.nan, np.inf):
            with self.subTest(count=count), self.assertRaises(ValueError):
                transmittance_reference(atmosphere(), sample_count=count)
        with self.assertRaises(ValueError):
            transmittance_reference(atmosphere(TopRadiusKm=9.0))
        with self.assertRaises(ValueError):
            transmittance_reference(atmosphere(), size=(0, 1))


class TransmittanceSamplingTests(unittest.TestCase):
    def test_encoded_values_are_interpolated_before_squaring(self):
        texture = np.repeat(np.array([[0.0, 0.5], [0.5, 1.0]])[..., None], 3, axis=2)
        actual = sample_encoded_transmittance(texture, np.array([[0.5, 0.5]]))
        np.testing.assert_array_equal(actual, [[0.25] * 3])

    def test_linear_sampler_clamps_edges_and_hits_texel_centers(self):
        texture = np.repeat(np.array([[0.25, 0.75]])[..., None], 3, axis=2)
        actual = sample_encoded_transmittance(texture, np.array([[-1.0, 0.5], [0.75, 0.5], [2.0, 0.5]]))
        np.testing.assert_array_equal(actual[:, 0], np.square([0.25, 0.75, 0.75]))

    def test_optional_d3d_fraction_precision_is_explicit(self):
        texture = np.repeat(np.array([[0.0, 1.0]])[..., None], 3, axis=2)
        uv = np.array([[(0.123 + 0.5) / 2.0, 0.5]])
        ideal = sample_encoded_transmittance(texture, uv)[0, 0]
        quantized = sample_encoded_transmittance(texture, uv, sampler_fraction_bits=8)[0, 0]
        self.assertAlmostEqual(ideal, 0.123**2)
        self.assertEqual(quantized, (31.0 / 256.0)**2)
        self.assertNotEqual(ideal, quantized)


class MultiScatteringReferenceTests(unittest.TestCase):
    def test_vacuum_with_black_ground_is_zero(self):
        actual = multi_scattering_reference(atmosphere(), np.ones((4, 8, 3)), size=(8, 4))
        np.testing.assert_array_equal(actual, np.zeros((4, 8, 3)))

    def test_vacuum_ground_bounce_has_two_ray_weight_and_light_cosine(self):
        albedo = np.array([0.2, 0.4, 0.8])
        parameters = atmosphere(GroundAlbedo=albedo, MultiScatteringFactor=0.7)
        actual = multi_scattering_reference(parameters, np.ones((4, 8, 3)), size=(8, 4))
        mu = np.maximum(2.0 * (np.arange(8) + 0.5) / 8.0 - 1.0, 0.0)
        expected = np.broadcast_to(mu[None, :, None] * albedo * 0.7 / (2.0 * np.pi), actual.shape)
        np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=1e-15)

    def test_constant_absorption_attenuates_ground_bounce(self):
        extinction = np.array([0.05, 0.1, 0.2])
        parameters = atmosphere(GroundAlbedo=[0.4] * 3, MieExtinction=extinction, MieDensityExpScale=0.0)
        # A constant encoded 0.5 texture supplies exactly 0.25 light transmittance.
        actual = multi_scattering_reference(parameters, np.full((4, 8, 3), 0.5), size=(8, 4), sample_count=15.5)
        altitude = (np.arange(4) + 0.5) / 4.0 * 2.0
        mu = np.maximum(2.0 * (np.arange(8) + 0.5) / 8.0 - 1.0, 0.0)
        expected = (np.exp(-altitude[:, None, None] * extinction * 16.0 / 15.5)
                    * mu[None, :, None] * 0.4 * 0.25 / (2.0 * np.pi))
        np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=1e-15)

    def test_constant_scattering_matches_finite_series_with_rectangle_ratio(self):
        sigma = np.array([0.1, 0.3, 0.7])
        parameters = atmosphere(RayleighScattering=sigma, RayleighDensityExpScale=0.0)
        actual = multi_scattering_reference(parameters, np.ones((2, 4, 3)), size=(2, 1))
        # At the middle altitude, both vertical paths are exactly 1 km long.
        # The sunlit column has mu=0.5; isotropic scattering is independent of it.
        first_order = -np.expm1(-sigma) / (4.0 * np.pi)
        ratio = sigma / 15.0 * (-np.expm1(-sigma)) / (-np.expm1(-sigma / 15.0))
        expected = first_order * sum(ratio**order for order in range(5))
        np.testing.assert_allclose(actual[0, 1], expected, rtol=1e-13)
        parameters["MiePhaseG"] = -0.7
        np.testing.assert_array_equal(
            multi_scattering_reference(parameters, np.ones((2, 4, 3)), size=(2, 1)), actual
        )

    def test_planet_blocks_single_scattering_on_thin_atmosphere_night_side(self):
        parameters = atmosphere(TopRadiusKm=10.01, RayleighScattering=[0.1] * 3, RayleighDensityExpScale=0.0)
        actual = multi_scattering_reference(parameters, np.ones((2, 4, 3)), size=(2, 1))
        np.testing.assert_array_equal(actual[0, 0], [0.0] * 3)
        self.assertTrue(np.all(actual[0, 1] > 0.0))


if __name__ == "__main__":
    unittest.main()
