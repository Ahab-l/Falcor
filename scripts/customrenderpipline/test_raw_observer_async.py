"""CPU boundary tests of the real raw observer; GPU bytes have separate smoke tests."""
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from observer import PipelineObserver
from observer_async import ReadbackPool


class NativeTask:
    def __init__(self, value=b'bytes', size=5):
        self.value, self.staging_bytes, self.ready = value, size, False
        self.collections = 0

    def result(self):
        if not self.ready:
            raise RuntimeError('Readback is not ready')
        self.collections += 1
        return self.value


class RawObserverAsyncTests(unittest.TestCase):
    def setUp(self):
        self.records = [{'name': 'A.data', 'kind': 'texture2DArray', 'format': 'RGBA32Uint',
                         'width': 8, 'height': 4, 'mip_count': 3, 'array_size': 3}]
        self.calls, self.tasks = [], []

        def submit(**options):
            self.calls.append(options)
            if options['max_bytes'] < 5:
                raise ValueError('Native staging byte budget exceeded')
            task = NativeTask()
            self.tasks.append(task)
            return task

        def sync_forbidden(*args, **kwargs):
            self.fail('Raw async used a synchronous fallback')

        self.resource = SimpleNamespace(read_async=submit, to_numpy=sync_forbidden)
        self.graph = SimpleNamespace(getOutput=lambda name: self.resource)
        self.observer = PipelineObserver(self.graph)
        self.falcor = SimpleNamespace(customRenderPiplineOutputCatalog=lambda graph: json.dumps(self.records),
                                      customRenderPiplineReadDepthStencil=sync_forbidden)
        self.patch = patch.dict(sys.modules, falcor=self.falcor)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_selected_view_and_metadata_survive_resize_and_resource_removal(self):
        task = self.observer.read_async('A.data', mip=1, slice=2, max_bytes=99)
        self.assertEqual(self.calls, [{'mip_level': 1, 'array_slice': 2, 'max_bytes': 99}])
        self.records[0]['width'] = 128
        self.graph.getOutput = lambda name: self.fail('Collection must not look up the graph again')
        self.tasks[0].ready = True
        result = task.result()
        self.assertEqual((result['width'], result['height']), (4, 2))
        self.assertEqual(result['view'], {'mip': 1, 'slice': 2})
        self.assertEqual(result['data'], b'bytes')

    def test_pending_collection_does_not_wait_or_fallback(self):
        task = self.observer.read_async('A.data')
        self.assertFalse(task.ready)
        self.assertEqual(task.staging_bytes, 5)
        with self.assertRaisesRegex(RuntimeError, 'not ready'):
            task.result()
        self.assertEqual(self.tasks[0].collections, 0)

    def test_buffers_preserve_raw_and_structured_metadata(self):
        for kind in ('raw_buffer', 'structured_buffer'):
            with self.subTest(kind=kind):
                self.records = [{'name': 'A.data', 'kind': kind, 'format': 'Unknown', 'bytes': 16}]
                if kind == 'structured_buffer':
                    self.records[0].update(stride=4, count=4)
                task = self.observer.read_async('A.data', max_bytes=16)
                self.assertEqual(self.calls[-1], {'max_bytes': 16})
                self.tasks[-1].ready = True
                result = task.result()
                self.assertEqual(result, {**self.records[0], 'data': b'bytes'})

    def test_depth_uses_async_plane_api_with_exact_view_and_budget(self):
        self.records[0]['format'] = 'D32FloatS8Uint'
        calls = []
        native = NativeTask({'depth': b'abcd', 'stencil': b'e'})
        self.falcor.customRenderPiplineReadDepthStencilAsync = lambda *args: calls.append(args) or native
        task = self.observer.read_async('A.data', mip=2, slice=1, max_bytes=7)
        self.assertEqual(calls, [(self.resource, 2, 1, 7)])
        self.assertEqual(self.calls, [])
        native.ready = True
        self.assertEqual(task.result()['depth'], b'abcd')
        self.assertEqual(task.result()['stencil'], b'e')
        self.assertEqual((task.result()['width'], task.result()['height']), (2, 1))

    def test_invalid_selection_rejects_before_native_copy(self):
        for options in ({'mip': 3}, {'slice': 3}, {'mip': -1}, {'slice': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.observer.read_async('A.data', **options)
        self.records = [{'name': 'A.data', 'kind': 'raw_buffer', 'format': 'Unknown', 'bytes': 16}]
        with self.assertRaises(ValueError):
            self.observer.read_async('A.data', mip=0)
        self.assertEqual(self.calls, [])

    def test_native_budget_error_leaves_pool_unmodified(self):
        pool = ReadbackPool(max_bytes=4)
        with self.assertRaisesRegex(ValueError, 'staging byte budget'):
            pool.submit(lambda cap: self.observer.read_async('A.data', max_bytes=cap))
        self.assertEqual(self.calls[0]['max_bytes'], 4)
        self.assertEqual((pool.pending_count, pool.staging_bytes), (0, 0))


if __name__ == '__main__':
    unittest.main()
