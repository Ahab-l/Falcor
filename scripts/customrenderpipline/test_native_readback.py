"""Use Falcor's standard resource readback while preserving observer metadata."""
import json
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np
from observer import PipelineObserver


class NativeReadbackTests(unittest.TestCase):
    def observer(self, record, array):
        self.calls = []
        def to_numpy(**kwargs):
            self.calls.append(kwargs)
            return array
        graph = types.SimpleNamespace(getOutput=lambda name: types.SimpleNamespace(to_numpy=to_numpy))
        native = types.SimpleNamespace(customRenderPiplineOutputCatalog=lambda g: json.dumps([record]))
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, falcor=native).start()
        return PipelineObserver(graph), native

    def test_color_mip_and_face_use_native_texture_to_numpy(self):
        expected = np.arange(16, dtype=np.uint32).reshape(2, 2, 4)
        observer, _ = self.observer({'name': 'Image.color', 'kind': 'textureCube', 'format': 'RGBA32Uint',
                                     'width': 8, 'height': 8, 'mip_count': 4, 'array_size': 1}, expected)
        result = observer.read('Image.color', mip=2, slice=5)
        self.assertEqual(self.calls, [{'mip_level': 2, 'array_slice': 5}])
        self.assertEqual(result['data'], expected.tobytes())
        self.assertEqual((result['width'], result['height']), (2, 2))
        self.assertEqual(result['view'], {'mip': 2, 'slice': 5})

    def test_structured_buffer_uses_native_byte_readback(self):
        expected = np.arange(32, dtype=np.uint8)
        observer, _ = self.observer({'name': 'Data.values', 'kind': 'structured_buffer', 'format': 'Unknown',
                                     'bytes': 32, 'stride': 16, 'count': 2}, expected)
        result = observer.read('Data.values')
        self.assertEqual(self.calls, [{}])
        self.assertEqual(result['data'], expected.tobytes())
        self.assertEqual((result['stride'], result['count']), (16, 2))
        with self.assertRaises(ValueError):
            observer.read('Data.values', mip=0)

    def test_d32s8_uses_only_the_plane_extension(self):
        observer, native = self.observer({'name': 'Depth.value', 'kind': 'texture2DArray', 'format': 'D32FloatS8Uint',
                                          'width': 8, 'height': 4, 'array_size': 2}, None)
        def planes(texture, mip, slice):
            self.calls.append((mip, slice))
            return {'width': 8, 'height': 4, 'depth': b'depth', 'stencil': b'stencil',
                    'depth_row_bytes': 32, 'stencil_row_bytes': 4}
        native.customRenderPiplineReadDepthStencil = planes
        result = observer.read('Depth.value', slice=1)
        self.assertEqual(self.calls, [(0, 1)])
        self.assertEqual(result['stencil'], b'stencil')


if __name__ == '__main__':
    unittest.main()
