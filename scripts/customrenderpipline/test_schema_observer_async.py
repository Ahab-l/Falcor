import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from schema_observer import SchemaObserver


class Buffer:
    def __init__(self, words): self.data = np.zeros(words, np.uint32)
    def to_numpy(self): raise AssertionError('Async observer used synchronous readback')
    def read_async(self, *, max_bytes):
        data=self.data.tobytes()
        assert len(data)<=max_bytes
        return SimpleNamespace(ready=False, staging_bytes=len(data), result=lambda: data)


class SchemaAsyncTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(SchemaObserver, 'read_async'), 'Schema async dispatch missing')
        self.o=object.__new__(SchemaObserver)
        self.o._resources=lambda: ({},(2,1),[])
        self.o.contract={'schema':{'attachments':[]}}
        self.o.columns={'fields':{'id':{'offset':0,'channels':1,'dtype':'uint32'}},'storage':{},'attachments':{}}
        self.o.stride=1; self.o.layout_hash='layout'
        self.o._buffer=None; self.o._capacity=0
        self.o.dispatch_count=self.o.readback_count=0
        self.allocations=[]
        def allocate(stride, words, flags):
            b=Buffer(words);self.allocations.append(b);return b
        self.o.graph=SimpleNamespace(device=SimpleNamespace(create_structured_buffer=allocate))
        def execute(**kwargs): self.o._buffer.data[:]=np.uint32(0xffffffff)
        self.o._program=SimpleNamespace(globals={}, execute=execute)
        self.native=SimpleNamespace(ResourceBindFlags=SimpleNamespace(UnorderedAccess=1), uint4=lambda *v:v)

    def test_snapshot_is_staged_before_reuse_and_unpack_is_deferred(self):
        with patch.dict(sys.modules, falcor=self.native): task=self.o.read_async([0,0,2,1],fields=['id'])
        self.assertFalse(task.ready)
        self.o._buffer.data[:]=0
        task.native.ready=True
        np.testing.assert_array_equal(task.result()['fields']['id'],[[0xffffffff,0xffffffff]])
        self.assertEqual((self.o.dispatch_count,self.o.readback_count),(1,1))

    def test_cap_rejects_before_buffer_allocation_and_dispatch(self):
        with patch.dict(sys.modules, falcor=self.native), self.assertRaisesRegex(ValueError,'limit|budget'):
            self.o.read_async([0,0,2,1],max_bytes=4)
        self.assertFalse(self.allocations)
        self.assertEqual(self.o.dispatch_count,0)


if __name__=='__main__':unittest.main()
