"""UI policy tests without Falcor or desktop automation."""
import unittest
from types import SimpleNamespace
from observer_async import completed, ReadbackTicket
try:
    from schema_observer_ui_model import InspectorModel, format_values, make_rule
except ImportError:
    InspectorModel=None


class Service:
    frame=1
    active_graph='Graph'
    closed=False
    observer=SimpleNamespace(graph=SimpleNamespace(name='Graph'),layout_hash='abc')
    def __init__(self): self.calls=[]
    def submit(self, request): return completed(self.handle(request))
    def handle(self,request):
        self.calls.append(request)
        if request['operation']=='list': result={'dimensions':[8,4]}
        else: result={'fields':{'id':{'dtype':'uint32','shape':[1,1],'values':[[4294967295]]}}}
        return {'status':'ok','frame':self.frame,'layout_hash':'abc','result':result}


class Preview:
    def __init__(self): self.calls=[]; self.closed=False
    def render(self,*args,**kwargs): self.calls.append((args,kwargs)); return SimpleNamespace(width=8,height=4)
    def close(self): self.closed=True


class ModelTests(unittest.TestCase):
    def test_pending_action_does_not_resubmit_and_completion_keeps_submitted_frame(self):
        native_submit=self.service.submit
        ticket=ReadbackTicket({'frame':1})
        calls=[]
        def submit(request):
            if request['operation']=='list': return native_submit(request)
            calls.append(request)
            return ticket
        self.service.submit=submit
        self.model.enqueue('inspect',self.state);self.model.pump()
        self.assertIn('pending',self.model.status.lower())
        self.assertIsNone(self.model.last_reply)
        for _ in range(3):self.model.pump()
        self.assertEqual(len(calls),1)
        self.service.frame=9
        ticket._value={'status':'ok','frame':1,'result':{'fields':{}}};ticket.status='ready'
        self.model.pump()
        self.assertEqual(self.model.last_reply['frame'],1)
        self.assertEqual(self.model.preview_frame,1)

    def test_close_cancels_pending_readback_delivery(self):
        native_submit=self.service.submit;ticket=ReadbackTicket()
        self.service.submit=lambda request:native_submit(request) if request['operation']=='list' else ticket
        self.model.enqueue('export',self.state);self.model.pump();self.model.close()
        self.assertEqual(ticket.status,'cancelled')

    def setUp(self):
        self.assertIsNotNone(InspectorModel,'Native UI model not implemented')
        self.service=Service();self.preview=Preview()
        self.model=InspectorModel(self.service,self.preview)
        self.state={'source':'field:id','mode':'id','component':0,'low':0.,'high':1.,'region':[0,0,1,1],
                    'field':'id','field_type':'uint','rule_kind':'exact','atol':.001,'rtol':0.,'angle':.1,
                    'reference':'','rules_path':'','mask':'','raw_output':'GBuffer.bits'}

    def test_idle_does_not_call_service_or_gpu(self):
        self.model.pump()
        self.assertFalse(self.service.calls or self.preview.calls)

    def test_ui_action_is_deferred_and_snapshotted(self):
        self.model.enqueue('inspect',self.state)
        self.state['region'][0]=5
        self.assertFalse(self.service.calls)
        self.model.pump()
        self.assertEqual(self.model.last_reply['status'],'ok')
        self.assertEqual(self.service.calls[-1]['arguments']['region'],[0,0,1,1])
        self.assertEqual(self.model.preview_frame,1)

    def test_pick_checks_display_dimensions(self):
        state={**self.state,'display_dims':[7,4]}
        self.model.enqueue('pick',state);self.model.pump()
        self.assertIn('resize',self.model.status.lower())
        self.assertFalse(self.preview.calls)

    def test_fail_keeps_old_preview(self):
        self.model.enqueue('refresh',self.state);self.model.pump()
        old=self.model.texture
        self.service.active_graph='Other'
        self.model.enqueue('refresh',self.state);self.model.pump()
        self.assertIs(self.model.texture,old)
        self.assertTrue(self.model.stale)

    def test_bounded_queue_and_close(self):
        for _ in range(8):self.model.enqueue('export',self.state)
        with self.assertRaises(ValueError):self.model.enqueue('export',self.state)
        self.model.close()
        self.model.pump()
        self.assertFalse(self.service.calls)
        self.assertTrue(self.preview.closed)

    def test_integer_formatting_keeps_precision(self):
        text=format_values({'id':{'dtype':'uint32','shape':[1,1],'values':[[4294967295]]}})
        self.assertIn('4294967295',text)
        self.assertNotIn('4.29497',text)

    def test_rule_restrictions(self):
        self.assertEqual(make_rule('uint','exact',.01,0,.1),{'kind':'exact'})
        self.assertEqual(make_rule('float3','angle',.01,0,.1)['max_degrees'],.1)
        for dtype,kind in [('uint','angle'),('float','exact'),('float2','angle')]:
            with self.assertRaises(ValueError):make_rule(dtype,kind,.1,0,.1)

if __name__=='__main__': unittest.main()
