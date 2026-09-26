"""CPU source-formula endpoints and native Schema contract; no GPU or capture input."""
import json
import math
from pathlib import Path
import re
import unittest

from gbuffer_codegen import emit_codec
from gbuffer_schema import validate_layout


HERE = Path(__file__).resolve().parent / 'examples' / 'targetmap_shading'


class TargetMapMaterialTests(unittest.TestCase):
    def source(self, name):
        path = HERE / name
        self.assertTrue(path.is_file(), f'missing source-native material artifact: {path}')
        return path.read_text(encoding='utf-8')

    def scalar(self, name, **arguments):
        # Execute the actual authored single-return scalar Slang expression.
        # This deliberately avoids a second Python implementation of the formula.
        source = self.source('SurfaceCodec.slangh' if 'NormalComponent' in name else 'Material.slangh')
        match = re.search(r'float\s+' + name + r'\([^)]*\)\s*\{\s*return\s+([^;]+);\s*\}', source)
        self.assertIsNotNone(match, f'{name} must stay a pure scalar expression for CPU audit')
        expression = re.sub(r'(?<=[0-9])f\b', '', match.group(1))
        return eval(expression, {'__builtins__': {}, 'saturate': lambda x: min(1., max(0., x))}, arguments)

    def test_projection_weights_keep_interpolated_normal_length(self):
        for value, expected in [(0, 0), (1/3, 0), (.5, .5), (2/3, 1), (-.5, .5), (1, 1)]:
            self.assertAlmostEqual(self.scalar('sourceProjectionWeight', component=abs(value)), expected)

    def test_checker_color_endpoints(self):
        for weight, expected in [(0, .18), (1, .23), (.5, .205)]:
            self.assertAlmostEqual(self.scalar('sourceBlend', a=.18, b=.23, weight=weight), expected)

    def test_line_mask_uses_source_subtraction_order(self):
        for first, delta, expected in [(0, 0, 1), (1, 0, 0), (.2, .3, .5)]:
            self.assertAlmostEqual(self.scalar('sourceLineMask', firstBlend=first, secondWeightedDelta=delta), expected)

    def test_roughness_grid_and_line_endpoints(self):
        for line, checker, expected in [(0, 0, .3), (0, 1, .3), (1, 0, .5), (1, 1, .65), (.5, .5, .4375)]:
            self.assertAlmostEqual(self.scalar('sourceGridRoughness', lineMask=line, checker=checker,
                                   rough1=.5, rough2=.65, lineRoughness=.3), expected)

    def test_specular_dither_half_codes_and_zero(self):
        for noise, expected in [(0, 127), (.25, 127), (.75, 128), (1, 128)]:
            value = self.scalar('sourceSpecularDither', value=.5, noise=noise, nonZero=1.)
            self.assertEqual(math.floor(value * 255 + .5), expected)
        self.assertEqual(self.scalar('sourceSpecularDither', value=0., noise=1., nonZero=0.), 0)

    def test_linear_normal_codec_endpoints(self):
        for normal, expected in [(-1., 0.), (0., .5), (1., 1.)]:
            encoded = self.scalar('sourceEncodeNormalComponent', component=normal)
            self.assertEqual(encoded, expected)
            self.assertEqual(self.scalar('sourceDecodeNormalComponent', component=encoded), normal)
        self.assertIn('storage.normalEncoded = saturate(', self.source('SurfaceCodec.slangh'))

    def test_schema_generated_four_mrt_and_semantic_bits(self):
        schema = validate_layout(json.loads(self.source('Schema.json')))
        self.assertNotIn('producer', schema, 'native VSOut wrapper must bypass normalized ShadingData producer')
        self.assertEqual([(a['name'], a['format']) for a in schema['attachments']], [
            ('sceneColor', 'RGBA16Float'), ('gbufferA', 'RGB10A2Unorm'),
            ('gbufferB', 'BGRA8Unorm'), ('gbufferC', 'BGRA8UnormSrgb')])
        slots = {s['name']: s for s in schema['storage']}
        self.assertEqual(slots['modelCode']['bits'], {'offset': 0, 'width': 5})
        self.assertEqual(slots['skipVelocityCode']['bits'], {'offset': 7, 'width': 1})
        self.assertEqual(slots['objectCode']['bits'], {'offset': 0, 'width': 2})
        self.assertIn({'name': 'firstPerson', 'type': 'bool'}, schema['fields'])
        self.assertEqual(slots['firstPersonCode']['bits'], {'offset': 6, 'width': 1})
        self.source('SurfaceCodec.slangh')
        codec = emit_codec(schema, '0' * 64, {'SurfaceCodec.slangh': HERE / 'SurfaceCodec.slangh'})
        self.assertIn('gbufferC : SV_Target3', codec)
        self.assertNotIn('SV_Target4', codec)

    def test_wrapper_preserves_raw_vsout_and_owns_no_mrt_layout(self):
        source = self.source('Mesh.slang')
        self.assertIn('#include CRP_CODEC_HEADER', source)
        self.assertIn('TargetMapSurfaceEncode', source)
        self.assertIn('Transform.projection', source)
        self.assertNotIn('prepareShadingData', source)
        self.assertNotIn('SV_Target', source)
        self.assertNotIn('UESurface', source)
        material = self.source('Material.slangh')
        self.assertIn('ConstantBuffer<GridParams> ProcGridParams;', material)
        self.assertNotIn('Grid.tileSize', material)
        self.assertIn('transpose(objectLinear)', material)
        self.assertIn('input.normalW', material)
        self.assertEqual(material.count('gGrid.Sample('), 6)
        self.assertNotIn('SampleLevel', material)


if __name__ == '__main__':
    unittest.main()
