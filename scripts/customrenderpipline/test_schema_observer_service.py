"""Service boundary tests using real arrays and filesystem publication."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from observer_async import ReadbackPool
try:
    from schema_observer_service import ObservationService
except ImportError:
    ObservationService = None


class SampleObserver:
    """CPU producer substituting only the GPU boundary."""
    layout_hash = 'a'*64
    class Graph:
        name = 'Graph'
    graph = Graph()
    def describe(self):
        return {'fields': [{'name': 'id', 'type': 'uint'}]}
    def inspect(self, region, fields=None):
        return {'region': region, 'layout_hash': self.layout_hash,
                'fields': {'id': np.array([[4294967295]], dtype=np.uint32)},
                'attachments': {}, 'storage': {}}
    def compare(self, region, reference, rules, mask=None, fields=None):
        from schema_observer_compare import compare_fields
        return compare_fields(self.inspect(region,fields)['fields'],reference,rules,mask)


class ServiceTests(unittest.TestCase):
    def test_async_native_result_failure_preserves_service_error_envelope(self):
        from types import SimpleNamespace
        self.assertTrue(hasattr(self.service,'submit'))
        def fail(): raise ValueError('Decoder produced nonfinite field')
        native=SimpleNamespace(ready=False,staging_bytes=4,result=fail)
        self.service.observer.read_async=lambda *a,**k:native
        ticket=self.service.submit({'graph':'Graph','operation':'inspect','arguments':{'region':[0,0,1,1]}})
        native.ready=True;self.service.after_frame('Graph')
        reply=ticket.result()
        self.assertEqual(reply['frame'],1)
        self.assertEqual(reply['layout_hash'],self.service.observer.layout_hash)
        self.assertEqual(reply['error']['code'],'invalid_request')

    def test_submit_is_nonblocking_freezes_frame_and_uses_no_sync_observer(self):
        self.assertTrue(hasattr(self.service, 'submit'), 'Async service submit missing')
        from types import SimpleNamespace
        captured=self.service.observer.inspect([0,0,1,1])
        native=SimpleNamespace(ready=False, staging_bytes=4, result=lambda:captured)
        self.service.observer.read_async=lambda *a,**k:native
        self.service.observer.inspect=lambda *a,**k:self.fail('Synchronous inspect on frame thread')
        request={'graph':'Graph','operation':'inspect','arguments':{'region':[0,0,1,1]}}
        ticket=self.service.submit(request)
        request['arguments']['region'][0]=99
        self.assertFalse(ticket.ready)
        self.service.after_frame('Graph')
        self.assertFalse(ticket.ready)
        native.ready=True;self.service.after_frame('Other')
        self.assertEqual(ticket.result()['frame'],1)
        self.assertEqual(ticket.result()['result']['region'],[0,0,1,1])
        self.assertEqual(ticket.result()['status'],'ok')

    def test_async_close_cancels_delivery_but_keeps_pending_staging_charged(self):
        self.assertTrue(hasattr(self.service, 'submit'), 'Async service submit missing')
        from types import SimpleNamespace
        self.service.pool=ReadbackPool(max_tasks=1,max_bytes=4)
        native=SimpleNamespace(ready=False,staging_bytes=4,result=lambda:self.fail('Cancelled collect'))
        self.service.observer.read_async=lambda *a,**k:native
        ticket=self.service.submit({'graph':'Graph','operation':'inspect','arguments':{'region':[0,0,1,1]}})
        self.service.close()
        self.assertEqual(ticket.status,'cancelled')
        self.assertEqual(self.service.pool.staging_bytes,4)
        native.ready=True;self.service.pool.poll()
        self.assertEqual(self.service.pool.staging_bytes,0)

    def test_mailbox_frame_handler_is_async_not_handle(self):
        self.assertTrue(hasattr(self.service, 'submit'), 'Async service submit missing')
        import json,time,uuid
        from types import SimpleNamespace
        self.service.observer.read_async=lambda *a,**k:SimpleNamespace(ready=False,staging_bytes=4,result=lambda:self.fail('Not ready'))
        self.service.handle=lambda *a,**k:self.fail('Mailbox used explicit sync handle')
        request={'version':1,'request_id':str(uuid.uuid4()),'instance':self.service.mailbox.instance,'graph':'Graph',
                 'operation':'inspect','arguments':{'region':[0,0,1,1]},'deadline':time.time()+10}
        path=self.service.mailbox.session_dir/'requests'/(request['request_id']+'.json')
        path.write_text(json.dumps(request))
        self.service.after_frame('Graph')
        self.assertTrue(path.with_suffix('.processing').exists())
        self.assertFalse(list((self.service.mailbox.session_dir/'responses').glob('*.json')))

    def setUp(self):
        self.assertIsNotNone(ObservationService, 'Observation service not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = ObservationService(SampleObserver(), self.root/'session')
        self.service.pool=ReadbackPool()
        self.addCleanup(self.service.close)
        self.service.after_frame('Graph')

    def call(self, operation, **arguments):
        return self.service.handle({'operation': operation, 'graph': 'Graph', 'arguments': arguments})

    def test_inline_typed_integer(self):
        value = self.call('inspect', region=[0,0,1,1])
        self.assertEqual(value['status'], 'ok')
        self.assertEqual(value['frame'], 1)
        self.assertEqual(value['result']['fields']['id']['values'], [[4294967295]])
        self.assertEqual(value['result']['fields']['id']['dtype'], 'uint32')

    def test_python_response_has_same_protocol_identity(self):
        value = self.call('list')
        self.assertEqual(value['version'], 1)
        self.assertEqual(value['instance'], self.service.mailbox.instance)
        self.assertTrue(value['request_id'])

    def test_closed_service_rejects_direct_calls(self):
        self.service.close()
        self.assertEqual(self.call('inspect',region=[0,0,1,1])['error']['code'], 'closed')

    def test_export_preserves_types(self):
        value = self.call('inspect', region=[0,0,1,1], export=True)
        descriptor = value['result']['fields']['id']
        with np.load(descriptor['path'], allow_pickle=False) as archive:
            array = archive[descriptor['key']]
            self.assertEqual(array.dtype, np.dtype('uint32'))
            self.assertEqual(int(array[0,0]), 4294967295)

    def test_compare_has_distinct_failure_status(self):
        reference = self.root/'reference.npz'
        np.savez(reference, id=np.array([[4294967294]], dtype=np.uint32))
        result = self.call('compare', region=[0,0,1,1], reference=str(reference), rules={'id': {'kind':'exact'}})
        self.assertEqual(result['status'], 'comparison_failed')
        self.assertFalse(result['result']['passed'])

    def test_reject_wrong_graph_or_operation_or_options(self):
        self.assertEqual(self.service.handle({'graph':'Other','operation':'list','arguments':{}})['status'], 'error')
        self.assertEqual(self.call('eval', code='bad')['status'], 'error')
        self.assertEqual(self.call('list', unknown=True)['status'], 'error')

    def test_wrong_graph_error_preserves_request_graph(self):
        result = self.service.handle({'graph':'Other','operation':'list','arguments':{}})
        self.assertEqual(result['graph'],'Other')

    def test_inactive_graph_is_explicit_error(self):
        self.service.after_frame('Other')
        self.assertEqual(self.call('list')['error']['code'], 'inactive_graph')

    def test_frame_listeners_run_after_state_update_and_unregister(self):
        self.assertTrue(hasattr(self.service,'add_frame_listener'), 'UI needs a frame-boundary listener')
        frames=[]
        token=self.service.add_frame_listener(lambda: frames.append((self.service.frame,self.service.active_graph)))
        self.service.after_frame('Graph')
        self.service.remove_frame_listener(token)
        self.service.after_frame('Graph')
        self.assertEqual(frames,[(2,'Graph')])

    def test_listener_can_remove_next_listener(self):
        self.assertTrue(hasattr(self.service,'add_frame_listener'))
        calls=[]
        self.service.add_frame_listener(lambda: self.service.remove_frame_listener(second))
        second=self.service.add_frame_listener(lambda: calls.append('bad'))
        self.service.after_frame('Graph')
        self.assertFalse(calls)

    def test_listener_error_does_not_break_rendering_or_cli(self):
        self.assertTrue(hasattr(self.service,'add_frame_listener'))
        def bad(): raise ValueError('UI failure')
        token=self.service.add_frame_listener(bad)
        self.service.after_frame('Graph')
        self.assertIn('UI failure',self.service.listener_errors[token])
        self.assertEqual(self.call('list')['status'],'ok')
        self.service.close()
        with self.assertRaises(RuntimeError): self.service.add_frame_listener(lambda:None)

    def test_close_notifies_owned_listeners_once_and_allows_detach(self):
        calls=[]
        def close_panel():
            calls.append(self.service.closed)
            self.service.remove_frame_listener(token)
        token=self.service.add_frame_listener(lambda:None, on_close=close_panel)
        self.service.close()
        self.service.close()
        self.assertEqual(calls,[True])
        self.assertFalse(self.service._frame_listeners)


if __name__ == '__main__':
    unittest.main()
