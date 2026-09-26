"""CPU acceptance for artifact identity and typed observation transport."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from generate_native_gbuffer import generate
from test_native_gbuffer_schema import sample_schema
from schema_observer import SchemaObserver

try:
    from schema_observer_codegen import load_contract, emit_observer, unpack_words, validate_region
except ImportError:
    load_contract = None


class SchemaObserverTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(load_contract, 'Schema observer contract/typed transport is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        schema = sample_schema()
        self.path = self.root/'Schema.json'
        self.path.write_text(json.dumps(schema))
        self.artifacts = generate(self.path, self.root/'generated')

    def test_load_verified_generated_contract(self):
        contract = load_contract(self.artifacts)
        self.assertEqual(contract['schema']['name'], sample_schema()['name'])
        self.assertEqual(load_contract(self.artifacts.manifest)['layout_hash'], contract['layout_hash'])

    def test_reject_modified_codec(self):
        self.artifacts.codec.write_text('// changed')
        with self.assertRaisesRegex(ValueError, 'modified|mismatch'):
            load_contract(self.artifacts)

    def test_reject_manifest_redirect_to_unchecked_shader(self):
        other = self.artifacts.codec.parent/'Unchecked.slangh'
        other.write_text('// different implementation')
        manifest = json.loads(self.artifacts.manifest.read_text())
        manifest['codec'] = str(other)
        self.artifacts.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Codec|codec'):
            load_contract(self.artifacts.manifest)

    def test_reject_unexpected_producer_definition(self):
        manifest = json.loads(self.artifacts.manifest.read_text())
        path = self.artifacts.codec.parent/'Layout.json'
        path.write_text('{}')
        manifest['definition'] = str(path)
        self.artifacts.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'producer|definition'):
            load_contract(self.artifacts.manifest)

    def test_reject_modified_metadata(self):
        value = json.loads(self.artifacts.metadata.read_text())
        value['storage_info'] = {}
        self.artifacts.metadata.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'metadata|Metadata|mismatch'):
            load_contract(self.artifacts)

    def test_reject_changed_custom_source(self):
        source = Path(__file__).parent/'examples/schema_gbuffer'
        for p in source.iterdir():
            if p.is_file(): (self.root/p.name).write_bytes(p.read_bytes())
        generated = generate(self.root/'Schema.json', self.root/'custom')
        (self.root/'SurfaceCodec.slangh').write_text('// changed')
        with self.assertRaisesRegex(ValueError, 'source|Source'):
            load_contract(generated)

    def test_word_unpack_preserves_full_integer_bits_and_types(self):
        columns = {'fields': {'id': {'offset': 0, 'channels': 1, 'dtype': 'uint32'},
                              'signed': {'offset': 1, 'channels': 1, 'dtype': 'int32'},
                              'normal': {'offset': 2, 'channels': 3, 'dtype': 'float32'},
                              'flag': {'offset': 5, 'channels': 1, 'dtype': 'bool'}}}
        words = np.array([0xffffffff, 0x80000000, 0x3f800000, 0, 0, 1], np.uint32).reshape(1, 1, 6)
        fields = unpack_words(words, columns)['fields']
        self.assertEqual(fields['id'].dtype, np.dtype('uint32'))
        self.assertEqual(int(fields['id'][0, 0]), 2**32-1)
        self.assertEqual(int(fields['signed'][0, 0]), -(2**31))
        np.testing.assert_array_equal(fields['normal'], [[[1., 0., 0.]]])
        self.assertEqual(fields['flag'].dtype, np.dtype(bool))

    def test_region_bounds_and_resource_budget(self):
        self.assertEqual(validate_region([3, 2, 4, 5], 8, 8), (3, 2, 4, 5))
        for region in ([True,0,1,1], [0,0,0,1], [-1,0,1,1], [7,0,2,1], [0,0,1], [0.,0,1,1], [0,0,100000,100000]):
            with self.subTest(region=region), self.assertRaises(ValueError):
                validate_region(region, 100000 if region[-1] == 100000 else 8, 100000 if region[-1] == 100000 else 8)

    def test_emission_exposes_fields_storage_and_load_values(self):
        contract = load_contract(self.artifacts)
        source, columns, stride = emit_observer(contract)
        self.assertEqual(set(columns), {'fields', 'storage', 'attachments'})
        self.assertEqual(set(columns['fields']), {f['name'] for f in contract['schema']['fields']})
        self.assertIn(contract['schema']['name']+'Decode(packed)', source)
        self.assertGreater(stride, 0)

    def test_comparison_masks_before_finite_validation(self):
        observer = object.__new__(SchemaObserver)
        observer._decode = lambda region, fields=None: {'fields':{'roughness':np.array([[.5,np.nan]],np.float32)}}
        self.assertTrue(hasattr(observer, 'compare'), 'Schema comparison must apply mask before finite checks')
        result = observer.compare([0,0,2,1], {'roughness':np.array([[.5,np.nan]],np.float32)},
                                  {'roughness':{'kind':'numeric','atol':0.,'rtol':0.}}, mask=np.array([[True,False]]))
        self.assertTrue(result['passed'])


if __name__ == '__main__':
    unittest.main()
