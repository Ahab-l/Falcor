"""Host-independent execution policy; native callable ownership is tested on GPU."""
import unittest
from observer_mogwai import MogwaiObservation


class Renderer:
    def __init__(self):
        self.callback = None
        self.graphExecutionCallbackRevision = 0
    @property
    def graphExecutionCallback(self):
        # Model pybind11 returning a new wrapper, rather than the Python callback.
        saved = self.callback
        return (lambda *args: saved(*args)) if saved is not None else None
    @graphExecutionCallback.setter
    def graphExecutionCallback(self, value):
        self.callback = value
        self.graphExecutionCallbackRevision += 1


class Graph:
    name = 'Graph'
    def __init__(self): self.executions = 0
    def execute(self): self.executions += 1


class Service:
    def __init__(self): self.frames = 0; self.closed = False
    def after_frame(self, name):
        if self.closed: raise RuntimeError('Service closed')
        self.frames += 1
    def close(self): self.closed = True


class AdapterTests(unittest.TestCase):
    def test_ordinary_execution_once_then_observe(self):
        renderer, graph, service = Renderer(), Graph(), Service()
        attachment = MogwaiObservation(renderer, service)
        self.assertTrue(renderer.graphExecutionCallback(graph,0))
        self.assertEqual((graph.executions,service.frames),(1,1))
        attachment.close()
        self.assertIsNone(renderer.graphExecutionCallback)

    def test_previous_handled_and_fallback_execute_once(self):
        for handled in (False,True):
            renderer, graph, service = Renderer(), Graph(), Service()
            def previous(g, time):
                if handled: g.execute()
                return handled
            renderer.graphExecutionCallback = previous
            attachment = MogwaiObservation(renderer,service)
            renderer.graphExecutionCallback(graph,0)
            self.assertEqual((graph.executions,service.frames),(1,1))
            attachment.close()
            renderer.graphExecutionCallback(graph,0)
            self.assertEqual(graph.executions,2 if handled else 1)

    def test_newer_callback_survives_detach(self):
        renderer, service = Renderer(),Service()
        attachment = MogwaiObservation(renderer,service)
        renderer.graphExecutionCallback = lambda graph,time: 'newer'
        revision = renderer.graphExecutionCallbackRevision
        attachment.close(); attachment.close()
        self.assertEqual(renderer.graphExecutionCallbackRevision,revision)
        self.assertEqual(renderer.graphExecutionCallback(None,0),'newer')

    def test_newer_wrapper_can_call_closed_observer(self):
        renderer,graph,service = Renderer(),Graph(),Service()
        attachment = MogwaiObservation(renderer,service)
        previous = renderer.graphExecutionCallback
        renderer.graphExecutionCallback = lambda graph,time: previous(graph,time)
        attachment.close()
        renderer.graphExecutionCallback(graph,0)
        self.assertEqual((graph.executions,service.frames),(1,0))

    def test_nested_close_restores_managed_owner(self):
        renderer = Renderer()
        first = MogwaiObservation(renderer,Service())
        second = MogwaiObservation(renderer,Service())
        second.close(); first.close()
        self.assertIsNone(renderer.graphExecutionCallback)

    def test_nested_close_skips_already_closed_owner(self):
        renderer,graph = Renderer(),Graph()
        first = MogwaiObservation(renderer,Service())
        second = MogwaiObservation(renderer,Service())
        first.close()
        renderer.graphExecutionCallback(graph,0)
        self.assertEqual(graph.executions,1)
        second.close()
        self.assertIsNone(renderer.graphExecutionCallback)


if __name__ == '__main__': unittest.main()
