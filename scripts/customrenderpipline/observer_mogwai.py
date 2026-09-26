"""Attach observation to Mogwai's existing once-per-frame graph callback."""
import weakref

_owners = weakref.WeakValueDictionary()


class MogwaiObservation:
    def __init__(self, renderer, service):
        self.renderer = renderer
        self.service = service
        previous_owner = _owners.get(id(renderer))
        self.previous_owner = (previous_owner if previous_owner is not None and
                               previous_owner.revision == renderer.graphExecutionCallbackRevision else None)
        self.previous = renderer.graphExecutionCallback
        self.callback = self._execute
        self.closed = False
        renderer.graphExecutionCallback = self.callback
        self.revision = renderer.graphExecutionCallbackRevision
        _owners[id(renderer)] = self

    def _execute(self, graph, clock_time):
        handled = self.previous(graph, clock_time) if self.previous is not None else False
        if not handled:
            graph.execute()
        if not self.closed:
            self.service.after_frame(graph.name)
        return True

    def close(self):
        if not self.closed:
            # Preserve a newer callback installed by the application.
            if self.renderer.graphExecutionCallbackRevision == self.revision:
                previous, owner = self.previous, self.previous_owner
                while owner is not None and owner.closed:
                    previous, owner = owner.previous, owner.previous_owner
                self.renderer.graphExecutionCallback = previous
                if owner is not None:
                    owner.revision = self.renderer.graphExecutionCallbackRevision
                    _owners[id(self.renderer)] = owner
            if _owners.get(id(self.renderer)) is self:
                del _owners[id(self.renderer)]
            self.service.close()
            self.closed = True
