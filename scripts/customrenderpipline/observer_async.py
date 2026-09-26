"""Owner-thread, bounded native staging tickets; never waits for GPU completion.

The shared per-owner pool also retains cancelled tasks after a service closes.
They keep their admission charge until a later frame/submission observes the
fence. No new service can reuse those bytes early. At most 8 tasks / 64 MiB are
retained per render owner, including closed-service work. User-retained completed
results are ordinary caller-owned CPU data, not an unbounded service cache.
"""
import copy
import threading
import weakref


class ReadbackTicket:
    def __init__(self, metadata=None):
        self.owner = threading.get_ident()
        self._metadata = copy.deepcopy(metadata or {})
        self.status = 'pending'
        self._value = self._error = None

    def _thread(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Readback tickets belong to their render owner thread')

    @property
    def metadata(self):
        return copy.deepcopy(self._metadata)

    @property
    def ready(self):
        self._thread()
        return self.status != 'pending'

    def cancel(self):
        self._thread()
        if self.status == 'pending':
            self.status = 'cancelled'

    def result(self):
        self._thread()
        if self.status == 'pending':
            raise RuntimeError('Readback is not ready')
        if self.status == 'cancelled':
            raise RuntimeError('Readback was cancelled')
        if self._error is not None:
            # Never retain exception tracebacks: they keep task.result()/poll()
            # frames and native staging alive after its admission charge ends.
            error_type, message = self._error
            try:
                error = error_type(message)
            except Exception:
                error = RuntimeError(message)
            raise error
        return self._value


def completed(value, metadata=None):
    ticket = ReadbackTicket(metadata)
    ticket._value = value
    ticket.status = 'ready'
    return ticket


class MappedReadback:
    """Map a native task only after ready; metadata/arrays are captured at submit."""
    def __init__(self, native, convert):
        self.native, self.convert = native, convert

    @property
    def ready(self):
        return self.native.ready

    @property
    def staging_bytes(self):
        return self.native.staging_bytes

    def result(self):
        return self.convert(self.native.result())


class ReadbackPool:
    def __init__(self, *, max_tasks=8, max_bytes=64*1024*1024):
        if type(max_tasks) is not int or not 1 <= max_tasks <= 64 or type(max_bytes) is not int or max_bytes < 1:
            raise ValueError('Invalid readback pool limits')
        self.owner = threading.get_ident()
        self.max_tasks, self.max_bytes = max_tasks, max_bytes
        self._jobs = []
        self.staging_bytes = 0

    def _thread(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Readback pool belongs to its render owner thread')

    @property
    def pending_count(self):
        return len(self._jobs)

    def submit(self, factory, *, metadata=None):
        """factory(cap) MUST reject over-cap allocation before GPU dispatch/copy.

        Admission is synchronous on the owner: no other factory can race the
        remaining cap. Native read_async(max_bytes=cap) checks the real footprint
        before allocation; Schema checks its exact buffer bytes before dispatch.
        """
        self._thread()
        if self.pending_count >= self.max_tasks or self.staging_bytes >= self.max_bytes:
            raise ValueError('Readback queue is full; retry after later rendered frames')
        remaining = self.max_bytes - self.staging_bytes
        ticket = ReadbackTicket(metadata)
        task = factory(remaining)
        size = task.staging_bytes
        if type(size) is not int or not 0 < size <= remaining:
            raise ValueError('Native task violated the pre-allocation staging budget contract')
        # A forgotten caller is treated as cancelled, while staging is retained.
        self._jobs.append((weakref.ref(ticket), task, size))
        self.staging_bytes += size
        return ticket

    def poll(self):
        self._thread()
        retained = []
        for ticket_ref, task, size in self._jobs:
            ticket = ticket_ref()
            try:
                ready = task.ready
            except Exception as error:
                # Fail closed: a failed fence query is not completion evidence.
                if ticket is not None and ticket.status == 'pending':
                    ticket._error, ticket.status = (type(error), str(error)), 'error'
                ready = False
            if not ready:
                retained.append((ticket_ref, task, size))
                continue
            self.staging_bytes -= size
            if ticket is None or ticket.status != 'pending':
                continue
            try:
                ticket._value = task.result()
                ticket.status = 'ready'
            except Exception as error:
                ticket._error, ticket.status = (type(error), str(error)), 'error'
        self._jobs = retained


_pools = {}


def owner_pool():
    """Shared even across service close/reopen; reap only on the owning thread."""
    owner = threading.get_ident()
    if owner not in _pools:
        _pools[owner] = ReadbackPool()
    pool = _pools[owner]
    pool.poll()
    return pool
