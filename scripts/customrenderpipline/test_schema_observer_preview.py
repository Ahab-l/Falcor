"""CPU preview policy and shader emission tests; GPU acceptance runs separately."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

from generate_native_gbuffer import generate
from gbuffer_schema import FLOAT32_MAX, TYPES
from schema_observer_codegen import load_contract
from test_native_gbuffer_schema import sample_schema


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('schema_observer_preview'),
                             'GPU Schema preview is not implemented')
        import schema_observer_preview
        self.preview = schema_observer_preview
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contract = self.generate(sample_schema(), 'sample')

    def generate(self, schema, name):
        path = self.root/(name+'.json')
        path.write_text(json.dumps(schema), encoding='utf-8')
        return load_contract(generate(path, self.root/name))

    def typed_contract(self, field_type):
        base, count = TYPES[field_type]
        fmt = ('R', 'RG', 'RGB', 'RGBA')[count-1]+'32'+{'float': 'Float', 'int': 'Int', 'uint': 'Uint', 'bool': 'Uint'}[base]
        slot = {'name': 'stored', 'attachment': 'data', 'channels': 'rgba'[:count]}
        codec = {'kind': 'direct', 'field': 'value', 'storage': 'stored', 'range': [0, 1], 'overflow': 'clamp'}
        if base == 'bool':
            slot['bits'] = {'offset': 0, 'width': 1}
            codec = {'kind': 'bool', 'field': 'value', 'storage': 'stored'}
        return self.generate({'version': 1, 'name': 'TypedPreview',
            'attachments': [{'name': 'data', 'format': fmt}],
            'fields': [{'name': 'value', 'type': field_type}],
            'storage': [slot], 'codecs': [codec]}, field_type)

    def test_field_uses_generated_decoder_not_custom_reimplementation(self):
        spec = self.preview.emit_preview(self.contract, 'field:roughness')
        self.assertIn('#include "'+self.contract['artifacts'].codec.resolve().as_posix()+'"', spec.shader)
        self.assertIn('TestLayoutDecode(packed)', spec.shader)
        self.assertIn('value.roughness', spec.shader)
        self.assertIn('Texture2D<uint> gAttachment0;', spec.shader)
        self.assertIn('Texture2D<float4> gAttachment1;', spec.shader)
        self.assertEqual(spec.bindings, (('gAttachment0', 'packed'), ('gAttachment1', 'color')))
        self.assertIn('RWTexture2D<float4> gPreview;', spec.shader)
        self.assertIn('[numthreads(8,8,1)]', spec.shader)

    def test_attachment_uses_actual_typed_load_without_decode(self):
        for source, mode, typename, name in [('attachment:packed', 'id', 'uint', 'packed'),
                                              ('attachment:color', 'rgb', 'float4', 'color')]:
            with self.subTest(source=source):
                spec = self.preview.emit_preview(self.contract, source, mode)
                self.assertIn('Texture2D<'+typename+'> gAttachment0;', spec.shader)
                self.assertIn('gAttachment0.Load(int3(pixel, 0))', spec.shader)
                self.assertNotIn('TestLayoutDecode(', spec.shader)
                self.assertEqual(spec.bindings, (('gAttachment0', name),))

    def test_source_and_mode_are_explicit_exact_selections(self):
        for source in ('roughness', 'storage:roughnessCode', 'field:', 'field:missing',
                       'field:roughness:extra', ' attachment:color', '', None, [], 1):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'source|Source'):
                self.preview.emit_preview(self.contract, source)
        for mode in ('auto', 'Gray', '', None, []):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'mode'):
                self.preview.emit_preview(self.contract, 'field:roughness', mode)

    def test_component_is_integer_and_within_source_lanes(self):
        for component in (True, False, 1., '1', None, -1, 3):
            with self.subTest(component=component), self.assertRaisesRegex(ValueError, 'component'):
                self.preview.emit_preview(self.contract, 'field:baseColor', component=component)
        self.assertIn('sampleValue.z', self.preview.emit_preview(self.contract, 'field:baseColor', component=2).shader)
        for mode in ('rgb', 'signed'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'component'):
                self.preview.emit_preview(self.contract, 'field:baseColor', mode, component=1)

    def test_type_mode_matrix(self):
        for field_type, (base, count) in TYPES.items():
            contract = self.typed_contract(field_type)
            for mode in ('gray', 'rgb', 'signed', 'id'):
                valid = {'gray': base != 'bool', 'rgb': base == 'float' and count in (3, 4),
                         'signed': base == 'float' and count == 3, 'id': base in ('bool', 'int', 'uint')}[mode]
                with self.subTest(field_type=field_type, mode=mode):
                    if valid:
                        self.preview.emit_preview(contract, 'field:value', mode)
                    else:
                        with self.assertRaisesRegex(ValueError, 'mode|requires'):
                            self.preview.emit_preview(contract, 'field:value', mode)

    def test_id_hashes_full_integer_bits_before_palette_float_conversion(self):
        for field_type, cast in (('uint', 'sampleValue'), ('uint4', 'sampleValue.w'),
                                 ('int', 'asuint(sampleValue)'), ('bool', '(sampleValue ? 1u : 0u)')):
            with self.subTest(field_type=field_type):
                contract = self.typed_contract(field_type)
                spec = self.preview.emit_preview(contract, 'field:value', 'id', component=3 if field_type == 'uint4' else 0)
                self.assertIn('previewHash('+cast+')', spec.shader)
                self.assertIn('uint previewHash(uint value)', spec.shader)
                self.assertIn('0x7feb352du', spec.shader)
                self.assertIn('0x846ca68bu', spec.shader)
                self.assertNotIn('float(sampleValue', spec.shader)

    def test_signed_is_only_explicit_mapping_and_float_invalid_is_magenta(self):
        spec = self.preview.emit_preview(self.contract, 'field:baseColor', 'signed')
        self.assertIn('sampleValue * 0.5f + 0.5f', spec.shader)
        self.assertNotIn('normalize(', spec.shader)
        self.assertIn('all(isfinite(sampleValue))', spec.shader)
        self.assertIn('float4(1.0f, 0.0f, 1.0f, 1.0f)', spec.shader)

    def test_range_rejects_nonfinite_overflow_collapsed_or_ftz_values(self):
        invalid = [(float('nan'), 1), (0, float('inf')), (-float('inf'), 1),
                   (0, FLOAT32_MAX*2), (-FLOAT32_MAX, FLOAT32_MAX),
                   (1, 1), (2, 1), (1, 1+2**-25), (True, 1), ('0', 1),
                   (1e-40, 1), (0, 1e-40), (0, 1e-50),
                   (float.fromhex('0x1p-126'), float.fromhex('0x1.000002p-126'))]
        for low, high in invalid:
            with self.subTest(low=low, high=high), self.assertRaisesRegex(ValueError, 'range|float32'):
                self.preview.emit_preview(self.contract, 'field:roughness', low=low, high=high)

    def test_range_uniforms_do_not_change_shader_or_cache_key(self):
        first = self.preview.emit_preview(self.contract, 'field:roughness', low=0, high=1)
        second = self.preview.emit_preview(self.contract, 'field:roughness', low=-10, high=10)
        self.assertEqual(first.shader, second.shader)
        self.assertEqual(first.cache_key, ('field:roughness', 'gray', 0))
        self.assertEqual(first.cache_key, second.cache_key)
        self.assertNotEqual(first.scale, second.scale)
        self.assertEqual((second.low, second.high, second.span), (-10., 10., 20.))
        self.assertIn('clamp(value, gBounds.x, gBounds.y)', first.shader)

    def test_scaled_normalization_stays_finite_for_extreme_valid_ranges(self):
        f32 = lambda value: struct.unpack('f', struct.pack('f', value))[0]
        for low, high in [(0, FLOAT32_MAX), (-FLOAT32_MAX, 0), (1e-37, 2e-37),
                          (-1, 1), (1., 1.+2**-23), (-1e30, 1e30)]:
            with self.subTest(low=low, high=high):
                spec = self.preview.emit_preview(self.contract, 'field:roughness', low=low, high=high)
                first, second, scaled_low, scaled_span = spec.scale
                normalized = lambda value: f32(f32(f32(f32(value*first)*second)-scaled_low)/scaled_span)
                self.assertEqual(normalized(spec.low), 0.)
                self.assertEqual(normalized(spec.high), 1.)
                self.assertGreaterEqual(scaled_span, float.fromhex('0x1p-126'))

    def test_lru_cache_is_bounded_and_ranges_cannot_grow_it(self):
        cache = self.preview._ProgramCache()
        for index in range(32):
            cache.put(('field:f'+str(index), 'gray', 0), index)
            self.assertLessEqual(len(cache), 8)
        self.assertIsNone(cache.get(('field:f0', 'gray', 0)))
        self.assertEqual(cache.get(('field:f24', 'gray', 0)), 24)
        cache.put(('field:new', 'gray', 0), 42)
        self.assertEqual(cache.get(('field:f24', 'gray', 0)), 24)
        self.assertIsNone(cache.get(('field:f25', 'gray', 0)))
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_dimensions_reject_empty_invalid_and_excess_allocation(self):
        self.assertEqual(self.preview.validate_preview_dimensions((128, 72)), (128, 72))
        for dims in ((0, 1), (1, -1), (True, 1), (1., 1), (1,), (16384, 16384), (65536, 1)):
            with self.subTest(dims=dims), self.assertRaisesRegex(ValueError, 'dimension|byte|limit'):
                self.preview.validate_preview_dimensions(dims)

    def test_closed_state_and_invalid_arguments_do_not_touch_gpu(self):
        class UnreachableObserver:
            contract = self.contract
            def _thread(self):
                pass
            def _resources(self):
                raise AssertionError('GPU validation must not run for an invalid request')
        preview = self.preview.SchemaFieldPreview(UnreachableObserver())
        with self.assertRaises(ValueError):
            preview.render('field:missing')
        self.assertEqual(preview.dispatch_count, 0)
        preview.close()
        preview.close()
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            preview.render('field:roughness')

    def test_resource_validation_failure_propagates_before_dispatch(self):
        class InvalidObserver:
            contract = self.contract
            def _thread(self):
                pass
            def _resources(self):
                raise ValueError('Schema changed; rebind observer')
        preview = self.preview.SchemaFieldPreview(InvalidObserver())
        with self.assertRaisesRegex(ValueError, 'rebind'):
            preview.render('field:roughness')
        self.assertEqual(preview.dispatch_count, 0)


if __name__ == '__main__':
    unittest.main()
