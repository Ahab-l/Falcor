"""Shared Python/CLI operations, called only at a rendered-frame boundary."""
from pathlib import Path
import copy
import threading
import uuid
import weakref
import numpy as np
from observer_transport import LocalMailbox, DeferredResponse
from observer_async import owner_pool, MappedReadback, completed

INLINE_COMPONENTS = 4096


class _ResponseTicket:
    """Keep service protocol identity even if the native task/decoder fails."""
    def __init__(self, ticket, format_error):
        self.ticket, self.format_error = ticket, format_error

    @property
    def ready(self): return self.ticket.ready

    @property
    def status(self): return self.ticket.status

    @property
    def metadata(self): return self.ticket.metadata

    def cancel(self): self.ticket.cancel()

    def result(self):
        # This also checks ownership; misuse/pending collection must still throw.
        if not self.ticket.ready:
            raise RuntimeError('Readback is not ready')
        try:
            return self.ticket.result()
        except Exception as error:
            result = self.format_error(self.ticket.metadata, error)
            if self.ticket.status == 'cancelled': result['error']['code'] = 'cancelled'
            return result


class ObservationService:
    def __init__(self, observer, session_dir):
        self.observer = observer
        self.owner = threading.get_ident()
        self.mailbox = LocalMailbox(session_dir)
        self.exports = self.mailbox.session_dir/'exports'
        self.exports.mkdir()
        self.frame = 0
        self.active_graph = None
        self.closed = False
        self._frame_listeners = {}
        self._close_listeners = {}
        self.listener_errors = {}
        self.pool = owner_pool()
        self._tickets = weakref.WeakSet()

    def add_frame_listener(self, callback, *, on_close=None):
        """Register bounded frame work and optional owner-thread teardown.

        Call close() between native UI frames, just like resource teardown.
        """
        self._thread()
        if self.closed:
            raise RuntimeError('Observation service is closed')
        if not callable(callback) or (on_close is not None and not callable(on_close)) or len(self._frame_listeners) >= 16:
            raise ValueError('Expected a callable; at most 16 frame listeners are supported')
        token = uuid.uuid4().hex
        self._frame_listeners[token] = callback
        if on_close is not None:
            self._close_listeners[token] = on_close
        return token

    def remove_frame_listener(self, token):
        self._thread()
        self._frame_listeners.pop(token, None)
        self._close_listeners.pop(token, None)
        self.listener_errors.pop(token, None)

    def _thread(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Observation service must run on its owning render thread')

    def after_frame(self, active_graph=None):
        """Call after rendering; frame numbers are local to this service instance."""
        self._thread()
        if self.closed:
            raise RuntimeError('Observation service is closed')
        self.frame += 1
        self.active_graph = self.observer.graph.name if active_graph is None else active_graph
        # Expire/cancel mailbox deliveries before mapping newly ready staging.
        count = self.mailbox.pump(self._mailbox_submit)
        self.pool.poll()
        for token, callback in tuple(self._frame_listeners.items()):
            if token not in self._frame_listeners:
                continue
            try:
                callback()
                self.listener_errors.pop(token, None)
            except Exception as error:
                self.listener_errors[token] = str(error)
        return count

    def close(self):
        self._thread()
        if self.closed:
            return
        self.mailbox.close()
        for ticket in tuple(self._tickets):
            ticket.cancel()
        self._tickets.clear()
        self.closed = True
        for token, callback in tuple(self._close_listeners.items()):
            if token not in self._close_listeners:
                continue
            try:
                callback()
            except Exception as error:
                self.listener_errors[token] = str(error)
        self._frame_listeners.clear()
        self._close_listeners.clear()

    def _arrays(self, sample, export):
        groups = {group: sample[group] for group in ('fields', 'attachments', 'storage')}
        arrays = {group+'.'+name: a for group, values in groups.items() for name, a in values.items()}
        if any(a.dtype.kind == 'f' and not np.isfinite(a).all() for a in arrays.values()):
            raise ValueError('Observation contains nonfinite values; use raw read for byte diagnostics')
        file = None
        if export or sum(a.size for a in arrays.values()) > INLINE_COMPONENTS:
            file = self.exports/(uuid.uuid4().hex+'.npz')
            temporary = file.with_suffix('.tmp')
            with temporary.open('wb') as stream:
                np.savez(stream, **arrays)
            temporary.replace(file)
        result = {'region': sample['region'], 'attachment_values': 'Texture.Load values; use read for exact bytes'}
        for group, values in groups.items():
            result[group] = {}
            for name, array in values.items():
                descriptor = {'dtype': str(array.dtype), 'shape': list(array.shape)}
                descriptor.update({'path': str(file.resolve()), 'key': group+'.'+name} if file else {'values': array.tolist()})
                result[group][name] = descriptor
        return result

    def _read(self, args):
        from observer import PipelineObserver
        output = args.get('output')
        if not isinstance(output, str) or not output:
            raise ValueError('read requires an output name')
        options = {key: args[key] for key in ('mip', 'slice') if key in args}
        sample = PipelineObserver(self.observer.graph).read(output, **options)
        return self._raw_files(sample)

    def _raw_files(self, sample):
        result = {}
        for name, value in sample.items():
            if isinstance(value, bytes):
                file = self.exports/(uuid.uuid4().hex+'.bin')
                temporary = file.with_suffix('.tmp')
                temporary.write_bytes(value)
                temporary.replace(file)
                result[name] = {'path': str(file.resolve()), 'dtype': 'uint8', 'shape': [len(value)], 'bytes': len(value)}
            else:
                result[name] = value
        return result

    def handle(self, request):
        """Explicitly synchronous compatibility API; never used by frame pumps."""
        return self._handle(request, asynchronous=False)

    def submit(self, request):
        """Submit on the render thread and return a nonblocking, cancellable ticket."""
        self._thread()
        result = self._handle(copy.deepcopy(request), asynchronous=True)
        ticket = completed(result) if isinstance(result, dict) else _ResponseTicket(result, self._error)
        self._tickets.add(ticket)
        return ticket

    def _mailbox_submit(self, request):
        ticket = self.submit(request)
        return ticket.result() if ticket.ready else DeferredResponse(ticket)

    @staticmethod
    def _error(envelope, error):
        code = ('invalid_request' if isinstance(error, (ValueError, KeyError, TypeError)) else
                'file_error' if isinstance(error, OSError) else 'execution_error')
        return {**envelope, 'status':'error', 'error':{'code':code, 'message':str(error)}}

    def _stage(self, factory, finish, envelope):
        def convert(sample):
            try:
                result, status = finish(sample)
                return {**envelope, 'status':status, 'result':result}
            except Exception as error:
                return self._error(envelope, error)
        # The envelope is frozen before submitting; collection never reads the
        # new frame/graph/layout identity. Native byte snapshots outlive sources.
        return self.pool.submit(lambda cap: MappedReadback(factory(cap), convert), metadata=envelope)

    def _handle(self, request, *, asynchronous):
        self._thread()
        request_id = request.get('request_id', str(uuid.uuid4())) if isinstance(request, dict) else str(uuid.uuid4())
        request_graph = request.get('graph') if isinstance(request, dict) else None
        envelope = {'version': 1, 'request_id': request_id, 'instance': self.mailbox.instance,
                    'graph': request_graph, 'frame': self.frame, 'layout_hash': self.observer.layout_hash}
        try:
            if self.closed:
                return {**envelope, 'status': 'error', 'error': {'code': 'closed', 'message': 'Observation service is closed'}}
            if not isinstance(request, dict) or request.get('graph') != self.observer.graph.name:
                raise ValueError('Request graph does not match this registered observer')
            if self.frame < 1 or self.active_graph != self.observer.graph.name:
                return {**envelope, 'status': 'error', 'error': {'code': 'inactive_graph', 'message': 'Registered graph has not rendered in the current frame'}}
            operation = request.get('operation')
            args = request.get('arguments', {})
            allowed = {'list': set(), 'inspect': {'region', 'fields', 'export'},
                       'compare': {'region', 'fields', 'reference', 'rules', 'mask'}, 'read': {'output', 'mip', 'slice'}}
            if not isinstance(operation, str) or operation not in allowed:
                raise ValueError('Unknown operation')
            if not isinstance(args, dict) or args.keys()-allowed[operation]:
                raise ValueError('Unknown operation arguments')
            if operation == 'list':
                result = self.observer.describe()
            elif operation == 'read':
                if asynchronous:
                    from observer import PipelineObserver
                    output = args.get('output')
                    if not isinstance(output, str) or not output:
                        raise ValueError('read requires an output name')
                    raw = PipelineObserver(self.observer.graph)
                    options = {key: args[key] for key in ('mip', 'slice') if key in args}
                    return self._stage(lambda cap: raw.read_async(output, max_bytes=cap, **options),
                                       lambda sample: (self._raw_files(sample), 'ok'), envelope)
                result = self._read(args)
            else:
                fields = args.get('fields')
                if operation == 'compare':
                    rules = args.get('rules')
                    if not isinstance(rules, dict) or not rules:
                        raise ValueError('compare requires nonempty per-field rules')
                    fields = list(rules) if fields is None else fields
                if operation == 'inspect':
                    export = args.get('export', False)
                    if type(export) is not bool:
                        raise ValueError('export must be boolean')
                    if asynchronous:
                        return self._stage(lambda cap: self.observer.read_async(args.get('region'), fields=fields, max_bytes=cap),
                                           lambda sample: (self._arrays(sample, export), 'ok'), envelope)
                    sample = self.observer.inspect(args.get('region'), fields=fields)
                    result = self._arrays(sample, export)
                else:
                    path = args.get('reference')
                    if not isinstance(path, str) or not Path(path).is_absolute() or Path(path).suffix.lower() != '.npz':
                        raise ValueError('reference must be an absolute numeric NPZ path')
                    with np.load(path, allow_pickle=False) as archive:
                        # Accept ordinary field keys or archives exported by inspect.
                        if not isinstance(fields, list) or not fields or any(not isinstance(f,str) for f in fields):
                            raise ValueError('fields must be a nonempty list of Schema field names')
                        reference = {f: archive[f if f in archive.files else 'fields.'+f] for f in fields}
                        mask_key = args.get('mask')
                        if mask_key is not None and not isinstance(mask_key, str):
                            raise ValueError('mask must name a boolean array in the reference archive')
                        mask = archive[mask_key] if mask_key is not None else None
                        if asynchronous:
                            from schema_observer_compare import compare_fields
                            def compare(sample):
                                result = compare_fields(sample['fields'], reference, rules, mask=mask)
                                return result, 'ok' if result['passed'] else 'comparison_failed'
                            return self._stage(lambda cap: self.observer.read_async(args.get('region'), fields=fields, max_bytes=cap, strict=False),
                                               compare, envelope)
                        result = self.observer.compare(args.get('region'), reference, rules, mask=mask, fields=fields)
                    return {**envelope, 'status': 'ok' if result['passed'] else 'comparison_failed', 'result': result}
            return {**envelope, 'status': 'ok', 'result': result}
        except (ValueError, KeyError, TypeError) as error:
            return {**envelope, 'status': 'error', 'error': {'code': 'invalid_request', 'message': str(error)}}
        except OSError as error:
            return {**envelope, 'status': 'error', 'error': {'code': 'file_error', 'message': str(error)}}
        except Exception as error:
            return {**envelope, 'status': 'error', 'error': {'code': 'execution_error', 'message': str(error)}}
