"""GPU-authored UE PreintegratedGF: a port of SystemTextures.cpp's CPU algorithm.

The original source creates RG16Unorm128x32 with 128 samples. No captured LUT,
CPU array, or readback is an input. The extra RG32Float output diagnoses the
integration before explicit source UNORM16 rounding. Consumers use bilinear
clamp sampling at (NoV, Roughness).
"""
from pathlib import Path
import re

SHADER_DIRECTORY = Path(__file__).resolve().parents[2] / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/SkyLight'


def sky_light_brdf_fragment(*, prefix='PreintegratedGF'):
    """Return a fresh standalone PassDefinition fragment with no external inputs."""
    if not isinstance(prefix, str) or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', prefix) is None:
        raise ValueError('prefix must be an ASCII identifier')
    return {'version': 1, 'nodes': [
        {'name': prefix, 'type': 'CustomRenderPiplineComputePass', 'file_inputs': ['shader.file'],
         'properties': {'execution': 'once',
                        'shader': {'file': str(SHADER_DIRECTORY / 'PreintegratedGF.slang'),
                                    'compute': 'main', 'floating_point_mode': 'precise'},
                        'resources': [
                            {'name': 'preIntegratedGF', 'binding': 'gPreintegratedGF', 'direction': 'output',
                             'kind': 'texture2D', 'format': 'RG16Unorm', 'size': [128, 32]},
                            {'name': 'integratedAB', 'binding': 'gIntegratedAB', 'direction': 'output',
                             'kind': 'texture2D', 'format': 'RG32Float', 'size': [128, 32]}],
                        'dispatch': {'threads': [128, 32, 1]}}}],
            'edges': [], 'outputs': [prefix + '.preIntegratedGF', prefix + '.integratedAB']}
