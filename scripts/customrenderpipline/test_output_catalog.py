"""CPU tests for observed output metadata, display intent, and Atlas rectangles."""
from dataclasses import FrozenInstanceError
import importlib
import json
import unittest


class OutputCatalogTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('output_catalog')
        self.records = [
            {'name': 'Lit.color', 'kind': 'texture2D', 'format': 'RGBA32Float', 'width': 640, 'height': 360},
            {'name': 'Depth.depth', 'kind': 'texture2D', 'format': 'D32Float', 'width': 640, 'height': 360},
            {'name': 'IDs.mesh', 'kind': 'texture2D', 'format': 'R32Uint', 'width': 320, 'height': 180},
            {'name': 'Motion.x', 'kind': 'texture2D', 'format': 'RG16Int', 'width': 320, 'height': 180},
            {'name': 'Decode.roughness', 'kind': 'texture2D', 'format': 'R32Float', 'width': 640, 'height': 360},
            {'name': 'Stats.raw', 'kind': 'raw_buffer', 'format': 'Unknown', 'bytes': 256},
        ]
        self.catalog = self.module.OutputCatalog(self.records)

    def test_catalog_owns_immutable_metadata_and_preserves_observed_order(self):
        self.records[0]['name'] = 'mutated'
        self.assertIsInstance(self.catalog.outputs, tuple)
        self.assertEqual([record.name for record in self.catalog.outputs], [
            'Lit.color', 'Depth.depth', 'IDs.mesh', 'Motion.x', 'Decode.roughness', 'Stats.raw'])
        with self.assertRaises(FrozenInstanceError):
            self.catalog.outputs[0].width = 1

    def test_selection_preserves_requested_order_and_rejects_unknown_or_duplicate_names(self):
        self.assertEqual([record.name for record in self.catalog.select(['IDs.mesh', 'Lit.color'])],
                         ['IDs.mesh', 'Lit.color'])
        for names in (['missing'], ['Lit.color', 'Lit.color'], 'Lit.color', [None], {'Lit.color'}):
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.catalog.select(names)
        self.assertEqual(self.catalog.select([]), ())

    def test_duplicate_observed_names_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '[Dd]uplicate'):
            self.module.OutputCatalog([self.records[0], self.records[0]])

    def test_records_require_exact_resource_shape_and_supported_metadata(self):
        texture, raw = self.records[0], self.records[-1]
        invalid = [None, {}, {**texture, 'kind': 'texture3D'}, {**texture, 'width': True},
                   {**texture, 'height': 0}, {**texture, 'width': 1.5}, {**texture, 'name': ' '},
                   {**texture, 'format': 'Unknown'}, {**texture, 'format': 'InventedFloat'},
                   {**texture, 'bytes': 4}, {**raw, 'bytes': -1}, {**raw, 'bytes': False},
                   {**raw, 'width': 2}, {**raw, 'format': None}, {**texture, 'filename': 'unused'}]
        for record in invalid:
            with self.subTest(record=record), self.assertRaises(ValueError):
                self.module.OutputCatalog([record])
        with self.assertRaises(ValueError):
            self.module.OutputCatalog({'output': texture})

    def test_raw_buffer_metadata_rejects_texture_formats(self):
        raw = self.records[-1]
        for resource_format in ('RGBA32Float', 'R32Uint', 'RG16Int', 'D32Float'):
            with self.subTest(format=resource_format), self.assertRaises(ValueError):
                self.module.OutputCatalog([{**raw, 'format': resource_format}])

    def test_atlas_uses_requested_order_and_exact_row_major_rectangles(self):
        names = ['IDs.mesh', 'Lit.color', 'Depth.depth', 'Motion.x', 'Decode.roughness']
        layout = self.catalog.atlas_layout(names, tile_extent=(100, 60), columns=3)
        self.assertEqual((layout['width'], layout['height']), (300, 120))
        self.assertEqual([(tile['name'], tile['x'], tile['y'], tile['width'], tile['height'])
                          for tile in layout['tiles']], [
            ('IDs.mesh', 0, 0, 100, 60), ('Lit.color', 100, 0, 100, 60),
            ('Depth.depth', 200, 0, 100, 60), ('Motion.x', 0, 60, 100, 60),
            ('Decode.roughness', 100, 60, 100, 60)])
        self.assertEqual(json.loads(json.dumps(layout)), layout)

    def test_tiles_do_not_overlap_and_stay_inside_total_extent(self):
        layout = self.catalog.atlas_layout([record.name for record in self.catalog.outputs[:-1]],
                                            tile_extent=(17, 11), columns=2)
        for index, tile in enumerate(layout['tiles']):
            self.assertLessEqual(tile['x'] + tile['width'], layout['width'])
            self.assertLessEqual(tile['y'] + tile['height'], layout['height'])
            for other in layout['tiles'][index + 1:]:
                self.assertTrue(tile['x'] + tile['width'] <= other['x'] or
                                other['x'] + other['width'] <= tile['x'] or
                                tile['y'] + tile['height'] <= other['y'] or
                                other['y'] + other['height'] <= tile['y'])

    def test_single_row_is_tightly_sized_and_empty_selection_has_empty_layout(self):
        layout = self.catalog.atlas_layout(['Lit.color'], tile_extent=(100, 60), columns=8)
        self.assertEqual((layout['width'], layout['height']), (100, 60))
        self.assertEqual(self.catalog.atlas_layout([], tile_extent=(100, 60), columns=8),
                         {'width': 0, 'height': 0, 'tiles': []})
        self.assertEqual(self.module.OutputCatalog([]).outputs, ())

    def test_invalid_atlas_dimensions_are_rejected(self):
        for extent in ((0, 1), (1, -1), (True, 1), (1.5, 1), (1,), (1, 2, 3), None, '100x60'):
            with self.subTest(extent=extent), self.assertRaises(ValueError):
                self.catalog.atlas_layout(['Lit.color'], tile_extent=extent)
        for columns in (0, -1, True, 1.0, '2', None):
            with self.subTest(columns=columns), self.assertRaises(ValueError):
                self.catalog.atlas_layout(['Lit.color'], columns=columns)

    def test_texture_defaults_distinguish_color_depth_uint_sint_and_scalar_float(self):
        layout = self.catalog.atlas_layout([record.name for record in self.catalog.outputs[:-1]])
        self.assertEqual([tile['display']['mode'] for tile in layout['tiles']],
                         ['color', 'depth', 'uint', 'sint', 'float'])
        self.assertNotIn('channel', layout['tiles'][0]['display'])
        self.assertEqual(layout['tiles'][1]['display'],
                         {'mode': 'depth', 'channel': 0, 'scale': 1.0, 'bias': 0.0, 'minmax': None})

    def test_display_overrides_are_owned_and_preserve_numeric_intent(self):
        spec = {'mode': 'float', 'channel': 2, 'scale': 2, 'bias': -1, 'minmax': [-3, 5]}
        first = self.catalog.atlas_layout(['Lit.color'], displays={'Lit.color': spec})
        normalized = first['tiles'][0]['display']
        self.assertEqual(normalized, {'mode': 'float', 'channel': 2, 'scale': 2.0,
                                     'bias': -1.0, 'minmax': [-3.0, 5.0]})
        spec['minmax'][0] = 0
        self.assertEqual(normalized['minmax'], [-3.0, 5.0])
        normalized['minmax'][0] = 100
        second = self.catalog.atlas_layout(['Lit.color'])
        self.assertEqual(second['tiles'][0]['display']['mode'], 'color')

    def test_modes_must_match_observed_numeric_resource_type(self):
        invalid = [('Lit.color', 'depth'), ('Lit.color', 'uint'), ('Depth.depth', 'color'),
                   ('IDs.mesh', 'float'), ('Motion.x', 'uint'), ('Decode.roughness', 'bytes'),
                   ('Stats.raw', 'color'), ('Stats.raw', 'float'), ('Lit.color', 'made_up')]
        for name, mode in invalid:
            with self.subTest(name=name, mode=mode), self.assertRaises(ValueError):
                self.catalog.atlas_layout([name], displays={name: {'mode': mode}})

    def test_channels_are_integer_existing_scalar_lanes_and_not_ignored_color_options(self):
        for channel in (-1, 4, True, 1.0, None):
            with self.subTest(channel=channel), self.assertRaises(ValueError):
                self.catalog.atlas_layout(['Lit.color'], displays={'Lit.color': {'mode': 'float', 'channel': channel}})
        for name, spec in [('IDs.mesh', {'channel': 1}), ('Depth.depth', {'channel': 1}),
                           ('Lit.color', {'mode': 'color', 'channel': 0}),
                           ('Stats.raw', {'mode': 'bytes', 'channel': 1})]:
            with self.subTest(name=name, spec=spec), self.assertRaises(ValueError):
                self.catalog.atlas_layout([name], displays={name: spec})

    def test_nonfinite_or_malformed_display_values_are_rejected(self):
        invalid = [{'scale': True}, {'bias': float('nan')}, {'scale': float('inf')},
                   {'minmax': [2, 2]}, {'minmax': [3, 2]}, {'minmax': [0, float('inf')]},
                   {'minmax': [0]}, {'minmax': [False, 1]}, {'minmax': '0,1'},
                   {'unknown': 1}, {'mode': None}]
        for spec in invalid:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                self.catalog.atlas_layout(['Lit.color'], displays={'Lit.color': spec})
        for displays in ([], {'missing': {}}, {'IDs.mesh': {}}, {'Lit.color': None}):
            with self.subTest(displays=displays), self.assertRaises(ValueError):
                self.catalog.atlas_layout(['Lit.color'], displays=displays)

    def test_raw_buffers_require_explicit_byte_or_scalar_grid_modes(self):
        self.assertEqual(self.catalog.select(['Stats.raw'])[0].bytes, 256)
        with self.assertRaisesRegex(ValueError, '[Ee]xplicit'):
            self.catalog.atlas_layout(['Stats.raw'])
        for mode in ('bytes', 'uint32', 'sint32', 'float32'):
            with self.subTest(mode=mode):
                layout = self.catalog.atlas_layout(['Stats.raw'], displays={'Stats.raw': {'mode': mode}})
                self.assertEqual(layout['tiles'][0]['display']['mode'], mode)
                self.assertEqual(layout['tiles'][0]['display']['channel'], 0)

    def test_raw_scalar_grid_requires_complete_32_bit_elements(self):
        catalog = self.module.OutputCatalog([{'name': 'Raw.data', 'kind': 'raw_buffer', 'format': 'Unknown', 'bytes': 7}])
        catalog.atlas_layout(['Raw.data'], displays={'Raw.data': {'mode': 'bytes'}})
        for mode in ('uint32', 'sint32', 'float32'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, '4|32'):
                catalog.atlas_layout(['Raw.data'], displays={'Raw.data': {'mode': mode}})


if __name__ == '__main__':
    unittest.main()
