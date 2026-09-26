"""Deterministic fake-fence tests of the production bounded ticket lifecycle."""
import threading
import weakref
import gc
import unittest
try:
    from observer_async import ReadbackPool, completed, MappedReadback
except ImportError:
    ReadbackPool = None


class NativeTask:
    def __init__(self, size=4, value=b'data'):
        self.ready = False
        self.staging_bytes = size
        self.value = value
        self.collections = 0
    def result(self):
        assert self.ready, 'Never map pending staging memory'
        self.collections += 1
        return self.value


class AsyncPoolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ReadbackPool, 'Bounded readback pool missing')
        self.pool = ReadbackPool(max_tasks=2, max_bytes=8)

    def test_pending_has_no_collection_and_keeps_admission_charge(self):
        task = NativeTask()
        ticket = self.pool.submit(lambda cap: task, metadata={'frame': 3})
        for _ in range(10): self.pool.poll()
        self.assertEqual(ticket.status, 'pending')
        self.assertEqual((self.pool.pending_count, self.pool.staging_bytes), (1, 4))
        self.assertEqual(task.collections, 0)
        with self.assertRaises(RuntimeError): ticket.result()
        task.ready = True
        self.pool.poll()
        self.assertEqual(ticket.result(), b'data')
        self.assertEqual(ticket.metadata, {'frame': 3})
        self.assertEqual((self.pool.pending_count, self.pool.staging_bytes), (0, 0))

    def test_count_rejects_before_factory_and_byte_cap_is_remaining(self):
        capacities = []
        def factory(cap):
            capacities.append(cap)
            return NativeTask()
        self.pool.submit(factory)
        self.pool.submit(factory)
        with self.assertRaises(ValueError): self.pool.submit(factory)
        self.assertEqual(capacities, [8, 4])

    def test_cancel_does_not_release_pending_native_task_or_reuse_bytes(self):
        task = NativeTask(8)
        ticket = self.pool.submit(lambda cap: task)
        ticket.cancel()
        self.assertEqual(ticket.status, 'cancelled')
        with self.assertRaises(ValueError): self.pool.submit(lambda cap: self.fail('Allocation after cancel'))
        self.pool.poll()
        self.assertEqual(self.pool.staging_bytes, 8)
        task.ready = True
        self.pool.poll()
        self.assertEqual(task.collections, 0)
        self.assertEqual(self.pool.staging_bytes, 0)

    def test_metadata_is_frozen_and_results_survive_later_pool_use(self):
        metadata = {'frame': 7, 'region': [1,2,1,1]}
        task = NativeTask()
        ticket = self.pool.submit(lambda cap: task, metadata=metadata)
        metadata['region'][0] = 99
        ticket.metadata['region'][0] = 88
        task.ready = True; self.pool.poll()
        self.assertEqual(ticket.metadata['region'][0], 1)
        self.assertEqual(ticket.result(), b'data')

    def test_factory_failure_does_not_leak_slot_or_bytes(self):
        def fail(cap): raise ValueError('budget before dispatch')
        with self.assertRaisesRegex(ValueError, 'budget'): self.pool.submit(fail)
        self.assertEqual((self.pool.pending_count, self.pool.staging_bytes), (0,0))

    def test_collection_error_releases_ready_task_and_allows_recovery(self):
        native = NativeTask(); native.ready = True
        def fail(data): raise ValueError('decode failed')
        ticket = self.pool.submit(lambda cap: MappedReadback(native, fail))
        self.pool.poll()
        with self.assertRaisesRegex(ValueError, 'decode failed'): ticket.result()
        self.assertEqual(ticket.status, 'error')
        self.assertEqual(self.pool.pending_count, 0)
        self.assertEqual(completed({'ok': True}).result(), {'ok': True})

    def test_retained_error_tickets_do_not_retain_native_staging_via_traceback(self):
        pool=ReadbackPool(max_tasks=1,max_bytes=4)
        tickets=[]; references=[]
        def fail(raw): raise ValueError('Invalid decoded value')
        for _ in range(20):
            native=NativeTask(); native.ready=True; references.append(weakref.ref(native))
            tickets.append(pool.submit(lambda cap: MappedReadback(native,fail)))
            pool.poll();del native
        gc.collect()
        self.assertEqual(pool.staging_bytes,0)
        self.assertFalse(any(reference() is not None for reference in references))
        for ticket in tickets:
            with self.assertRaisesRegex(ValueError,'Invalid decoded value'):ticket.result()

    def test_wrong_thread_cannot_submit_poll_cancel_or_collect(self):
        native = NativeTask()
        ticket = self.pool.submit(lambda cap: native)
        errors=[]
        def worker():
            for call in (lambda: self.pool.submit(lambda cap: native), self.pool.poll, ticket.cancel, ticket.result):
                try: call()
                except RuntimeError: errors.append(True)
        thread=threading.Thread(target=worker);thread.start();thread.join()
        self.assertEqual(len(errors),4)


if __name__ == '__main__': unittest.main()
