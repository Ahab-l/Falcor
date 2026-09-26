"""Generic storage contracts: invalid layouts fail before any GPU work."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


def sample_schema():
    return {
        'version': 1, 'name': 'TestLayout',
        'attachments': [{'name': 'packed', 'format': 'R32Uint'},
                        {'name': 'color', 'format': 'RGBA8Unorm'}],
        'fields': [{'name': 'roughness', 'type': 'float'},
                   {'name': 'materialID', 'type': 'uint'},
                   {'name': 'baseColor', 'type': 'float3'}],
        'storage': [{'name': 'roughnessCode', 'attachment': 'packed', 'channels': 'r',
                     'bits': {'offset': 0, 'width': 8}},
                    {'name': 'idCode', 'attachment': 'packed', 'channels': 'r',
                     'bits': {'offset': 8, 'width': 16}},
                    {'name': 'rgb', 'attachment': 'color', 'channels': 'rgb'}],
        'codecs': [{'kind': 'unorm', 'field': 'roughness', 'storage': 'roughnessCode',
                    'range': [0, 1], 'overflow': 'clamp'},
                   {'kind': 'uint', 'field': 'materialID', 'storage': 'idCode',
                    'range': [0, 65535], 'overflow': 'reject'},
                   {'kind': 'direct', 'field': 'baseColor', 'storage': 'rgb',
                    'range': [0, 1], 'overflow': 'clamp'}],
    }


class NativeSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec('gbuffer_schema') is None:
            return
        from gbuffer_schema import validate_layout
        cls.validate = staticmethod(validate_layout)

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('gbuffer_schema'),
                             'G4/G5 generic layout validator is not implemented')

    def rejects(self, change, message):
        schema = sample_schema()
        change(schema)
        with self.assertRaisesRegex(ValueError, message):
            self.validate(schema)

    def test_generic_schema_without_ue_model_or_depth_contract(self):
        schema = sample_schema()
        before = copy.deepcopy(schema)
        result = self.validate(schema)
        self.assertEqual(schema, before)
        self.assertEqual(result['name'], 'TestLayout')

    def test_overlapping_bits(self):
        self.rejects(lambda s: s['storage'][1]['bits'].update(offset=7), 'overlap')

    def test_channel_capacity(self):
        self.rejects(lambda s: s['storage'][1]['bits'].update(offset=24), 'capacity')

    def test_impossible_declared_integer_range(self):
        self.rejects(lambda s: s['codecs'][1].update(range=[0, 65536]), 'range')

    def test_float_range_must_be_ordered_finite_and_float32_representable(self):
        for bounds in ([1, 1], [2, 1], [0, float('nan')], [0, float('inf')], [-1e40, 1e40]):
            with self.subTest(bounds=bounds):
                self.rejects(lambda s: s['codecs'][0].update(range=bounds), 'range')

    def test_direct_float32_supports_its_full_signed_range(self):
        from gbuffer_schema import FLOAT32_MAX
        schema = sample_schema()
        schema['attachments'][1]['format'] = 'RGBA32Float'
        schema['codecs'][2]['range'] = [-FLOAT32_MAX, FLOAT32_MAX]
        self.validate(schema)

    def test_quantization_rejects_denormal_span(self):
        self.rejects(lambda s: s['codecs'][0].update(range=[0, 1e-40]), 'range')

    def test_quantization_rejects_denormal_steps_even_with_normal_span(self):
        self.rejects(lambda s: s['codecs'][0].update(range=[0, float.fromhex('0x1p-126')]), 'range|step')

    def test_one_bit_quantization_rejects_denormal_midpoint(self):
        schema = sample_schema()
        schema['storage'][0]['bits']['width'] = 1
        schema['codecs'][0]['range'] = [0, float.fromhex('0x1p-126')]
        with self.assertRaisesRegex(ValueError, 'step|range'):
            self.validate(schema)

    def test_unknown_schema_and_nested_keys(self):
        for change in (lambda s: s.update(models=[]),
                       lambda s: s['storage'][0].update(offset=4),
                       lambda s: s['storage'][0]['bits'].update(stride=1)):
            self.rejects(change, 'unknown')

    def test_storage_has_to_reference_existing_attachment_channel(self):
        self.rejects(lambda s: s['storage'][0].update(attachment='absent'), 'attachment')
        self.rejects(lambda s: s['storage'][0].update(channels='a'), 'channel')

    def test_duplicate_or_unsafe_names(self):
        for name in ('packed', 'depth', 'bad.name', 'float', '__crp_internal'):
            self.rejects(lambda s: s['attachments'][1].update(name=name), 'name|identifier|duplicate')

    def test_language_keywords_rejected_for_every_identifier_role(self):
        for keyword in ('break', 'continue', 'do', 'let', 'half', 'register', 'groupshared'):
            for role in ('schema', 'attachment', 'field', 'storage', 'producer', 'custom'):
                with self.subTest(keyword=keyword, role=role):
                    schema = sample_schema()
                    if role == 'schema':
                        schema['name'] = keyword
                    elif role == 'attachment':
                        schema['attachments'][0]['name'] = keyword
                    elif role == 'field':
                        schema['fields'][0]['name'] = keyword
                        schema['codecs'][0]['field'] = keyword
                    elif role == 'storage':
                        schema['storage'][0]['name'] = keyword
                        schema['codecs'][0]['storage'] = keyword
                    elif role == 'producer':
                        schema['producer'] = {'file': 'Producer.slangh', 'entry': keyword}
                    else:
                        schema['codecs'][:2] = [{'kind': 'custom', 'name': 'joint', 'file': 'Joint.slangh',
                                                'encode': keyword, 'decode': 'decodeJoint',
                                                'fields': ['roughness', 'materialID'], 'storage': ['roughnessCode', 'idCode']}]
                    with self.assertRaisesRegex(ValueError, 'identifier|name'):
                        self.validate(schema)

    def test_codecs_have_complete_exclusive_ownership(self):
        self.rejects(lambda s: s['codecs'].pop(), 'unassigned')
        self.rejects(lambda s: s['codecs'].append(copy.deepcopy(s['codecs'][0])), 'owned')

    def test_mismatched_codec_type(self):
        self.rejects(lambda s: s['fields'][0].update(type='float2'), 'type|scalar')

    def test_explicit_overflow_policy(self):
        self.rejects(lambda s: s['codecs'][1].pop('overflow'), 'missing')
        self.rejects(lambda s: s['codecs'][1].update(overflow='truncate'), 'overflow')

    def test_bool_is_not_bit_width(self):
        self.rejects(lambda s: s['storage'][0]['bits'].update(width=True), 'integer')

    def test_raw_bits_in_linear_unorm_but_not_srgb_rgb(self):
        schema = sample_schema()
        schema['attachments'][0]['format'] = 'RGBA8Unorm'
        schema['storage'][1].update(channels='g', bits={'offset': 0, 'width': 8})
        schema['codecs'][1]['range'] = [0, 255]
        self.validate(schema)
        schema['attachments'][0]['format'] = 'RGBA8UnormSrgb'
        with self.assertRaisesRegex(ValueError, 'sRGB'):
            self.validate(schema)

    def test_full_word_and_signed_bit_fields(self):
        schema = sample_schema()
        schema['storage'][1].update(channels='g', bits={'offset': 0, 'width': 32})
        schema['attachments'][0]['format'] = 'RG32Uint'
        schema['codecs'][1]['range'] = [0, 2**32-1]
        self.validate(schema)
        schema['fields'][1]['type'] = 'int'
        schema['codecs'][1].update(kind='sint', range=[-(2**31), 2**31-1])
        self.validate(schema)

    def test_custom_group_owns_multiple_fields_and_slots(self):
        schema = sample_schema()
        schema['codecs'][:2] = [{'kind': 'custom', 'name': 'joint', 'file': 'Joint.slangh',
                                'encode': 'encodeJoint', 'decode': 'decodeJoint',
                                'fields': ['roughness', 'materialID'], 'storage': ['roughnessCode', 'idCode']}]
        self.validate(schema)
        schema['codecs'][0]['fields'].append('roughness')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.validate(schema)


class NativeGenerationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('generate_native_gbuffer'),
                             'G4 native generator is not implemented')
        from generate_native_gbuffer import generate
        self.generate = generate
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'Schema.json'
        self.schema = sample_schema()
        self.source.write_text(json.dumps(self.schema), encoding='utf-8')

    def test_repeat_generation_is_deterministic(self):
        first = self.generate(self.source, self.root/'out')
        second = self.generate(self.source, self.root/'out')
        self.assertEqual(first.codec, second.codec)
        metadata = json.loads(first.metadata.read_text())
        self.assertEqual(metadata['schema']['fields'], self.schema['fields'])
        self.assertEqual(len(metadata['layout_hash']), 64)
        self.assertIsNone(first.definition)

    def test_rejected_update_preserves_published_manifest(self):
        first = self.generate(self.source, self.root/'out')
        published = first.manifest.read_bytes()
        self.schema['storage'][1]['bits']['offset'] = 0
        self.source.write_text(json.dumps(self.schema))
        with self.assertRaisesRegex(ValueError, 'overlap'):
            self.generate(self.source, self.root/'out')
        self.assertEqual(first.manifest.read_bytes(), published)

    def test_native_definition_uses_generated_attachment_order_and_producer(self):
        (self.root/'Producer.slangh').write_text('// Authored material producer\n')
        self.schema['producer'] = {'file': 'Producer.slangh', 'entry': 'evaluateGBuffer'}
        self.schema['depthFormat'] = 'D16Unorm'
        self.source.write_text(json.dumps(self.schema))
        result = self.generate(self.source, self.root/'out')
        definition = json.loads(result.definition.read_text())
        self.assertEqual(definition['attachments'], self.schema['attachments'])
        self.assertEqual(definition['depthFormat'], 'D16Unorm')
        self.assertTrue((result.definition.parent/definition['shader']).is_file())

    def test_missing_custom_source_does_not_publish(self):
        self.schema['codecs'][:2] = [{'kind': 'custom', 'name': 'joint', 'file': 'Missing.slangh',
                                    'encode': 'encodeJoint', 'decode': 'decodeJoint',
                                    'fields': ['roughness', 'materialID'], 'storage': ['roughnessCode', 'idCode']}]
        self.source.write_text(json.dumps(self.schema))
        with self.assertRaisesRegex(ValueError, 'source'):
            self.generate(self.source, self.root/'out')
        self.assertFalse((self.root/'out/manifest.json').exists())

    def test_changed_custom_implementation_changes_guarded_contract(self):
        self.schema['codecs'][:2] = [{'kind': 'custom', 'name': 'joint', 'file': 'Joint.slangh',
                                    'encode': 'encodeJoint', 'decode': 'decodeJoint',
                                    'fields': ['roughness', 'materialID'], 'storage': ['roughnessCode', 'idCode']}]
        self.source.write_text(json.dumps(self.schema))
        custom = self.root/'Joint.slangh'
        custom.write_text('// Implementation A\n')
        first = self.generate(self.source, self.root/'out')
        custom.write_text('// Incompatible implementation B\n')
        second = self.generate(self.source, self.root/'out')
        first_meta, second_meta = (json.loads(a.metadata.read_text()) for a in (first, second))
        self.assertNotEqual(first_meta['layout_hash'], second_meta['layout_hash'])

    def test_duplicate_json_keys_rejected(self):
        self.source.write_text('{"version": 1, "version": 2}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.generate(self.source, self.root/'out')


if __name__ == '__main__':
    unittest.main()
