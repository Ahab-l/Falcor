"""Version-1 local observer mailbox; this module never imports Falcor.

Only ``pump()`` invokes the handler on its caller's thread. A handler may return
a DeferredResponse: later pumps test readiness once and publish only completed
work. Expiry/close cancel delivery, not GPU execution or in-flight staging.

The directory belongs to one local user, not a security boundary against that
user. Cooperating clients share an OS file lock for bounded queue admission.
JSON files are published by atomic rename and replies use UUID filenames only.
"""
from contextlib import contextmanager
import itertools
import json
import math
import os
from pathlib import Path
import time
import uuid

VERSION = 1
MAX_TIMEOUT = 300.0
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_QUEUE_SIZE = 64
MAX_PUMP_REQUESTS = 64
POLL_INTERVAL = 0.01
OPERATIONS = frozenset(("list", "inspect", "compare", "read"))


class DeferredResponse:
    """An owner-thread ticket exposing nonblocking ready/result/cancel."""
    def __init__(self, ticket):
        self.ticket = ticket


class _ProtocolError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def error_response(code, message, *, request_id=None, instance=None, graph=None):
    """Create the same JSON envelope for CLI, client and server errors."""
    return dict(version=VERSION, request_id=request_id, instance=instance,
                status="error", graph=graph, frame=None, layout_hash=None,
                error=dict(code=code, message=str(message)))


def _uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _reject_constant(value):
    raise ValueError("Nonfinite JSON number: " + value)


def _read_json(path, limit, size_code="invalid_json"):
    if path.is_symlink():
        raise _ProtocolError("invalid_path", "Mailbox files cannot be symbolic links")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise _ProtocolError(size_code, "JSON exceeds the mailbox size limit")
    try:
        value = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise _ProtocolError("invalid_json", str(exc)) from exc
    if not isinstance(value, dict):
        raise _ProtocolError("invalid_json", "JSON must contain an object")
    return value


def _encode(value, limit, size_code):
    try:
        data = json.dumps(value, ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise _ProtocolError("invalid_json", str(exc)) from exc
    if len(data) > limit:
        raise _ProtocolError(size_code, "JSON exceeds the mailbox size limit")
    return data


def _remove(path):
    try:
        path.unlink()
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        pass


def _publish(path, data, deadline=None):
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
        if deadline is not None:
            # Enables bounded expiry cleanup without reading large reply bodies.
            os.utime(temporary, (deadline, deadline))
        os.replace(temporary, path)
    finally:
        _remove(temporary)


def _metadata(session_dir):
    try:
        value = _read_json(session_dir / "session.json", MAX_REQUEST_BYTES)
    except OSError as exc:
        raise _ProtocolError("session_unavailable", str(exc)) from exc
    if type(value.get("version")) is not int or value["version"] != VERSION:
        raise _ProtocolError("unsupported_version", "Unsupported session protocol version")
    if not _uuid(value.get("instance")):
        raise _ProtocolError("invalid_instance", "Session instance must be a canonical UUID")
    if value.get("closed"):
        raise _ProtocolError("session_closed", "The observer session is closed")
    return value


@contextmanager
def _admission_lock(session_dir, stop, wait=True):
    # OS locks are released when a client exits, including abnormal termination.
    with (session_dir / ".admission.lock").open("r+b") as stream:
        if os.name == "nt":
            import msvcrt
            def acquire():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        while True:
            if wait and time.monotonic() >= stop:
                raise _ProtocolError("timeout", "Timed out waiting for mailbox admission")
            try:
                acquire()
                break
            except OSError as exc:
                if not wait:
                    raise _ProtocolError("mailbox_busy", "A client is publishing a request") from exc
                time.sleep(min(POLL_INTERVAL, max(0, stop - time.monotonic())))
        try:
            yield
        finally:
            release()


def _queue_full(session_dir):
    count = 0
    # Count unread replies too, so abandoned clients cannot grow storage forever.
    for name in ("requests", "responses"):
        with os.scandir(session_dir / name) as entries:
            for _ in itertools.islice(entries, MAX_QUEUE_SIZE):
                count += 1
                if count >= MAX_QUEUE_SIZE:
                    return True
    return False


def _validate_request(value, instance, request_id):
    if type(value.get("version")) is not int or value["version"] != VERSION:
        raise _ProtocolError("unsupported_version", "Unsupported request protocol version")
    if not _uuid(value.get("request_id")) or value["request_id"] != request_id:
        raise _ProtocolError("invalid_request_id", "Request UUID must match its filename")
    if value.get("instance") != instance:
        raise _ProtocolError("instance_mismatch", "Request belongs to a different observer instance")
    if not isinstance(value.get("graph"), str) or not value["graph"].strip():
        raise _ProtocolError("invalid_graph", "graph must be a nonempty string")
    if not isinstance(value.get("operation"), str) or value["operation"] not in OPERATIONS:
        raise _ProtocolError("invalid_operation", "operation must be list, inspect, compare or read")
    if not isinstance(value.get("arguments"), dict):
        raise _ProtocolError("invalid_arguments", "arguments must be an object")
    deadline = value.get("deadline")
    if not _finite_number(deadline) or deadline > time.time() + MAX_TIMEOUT + 1:
        raise _ProtocolError("invalid_deadline", "deadline must be finite and at most 300 seconds ahead")


def _validate_response(value, instance, request_id, graph):
    if type(value.get("version")) is not int or value["version"] != VERSION:
        raise _ProtocolError("unsupported_version", "Unsupported response protocol version")
    if value.get("request_id") != request_id or value.get("instance") != instance:
        raise _ProtocolError("response_mismatch", "Response UUID or instance does not match the request")
    if value.get("graph") != graph:
        raise _ProtocolError("response_mismatch", "Response graph does not match the request")
    if value.get("status") not in ("ok", "comparison_failed", "error"):
        raise _ProtocolError("invalid_response", "Invalid response status")
    if value["status"] == "error":
        error = value.get("error")
        if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
            raise _ProtocolError("invalid_response", "Error requires string code and message")
    elif "result" not in value:
        raise _ProtocolError("invalid_response", "Successful response requires result")


class LocalMailbox:
    """One non-reusable session. Call pump only from the render owner thread."""

    def __init__(self, session_dir, instance=None):
        self.instance = str(uuid.uuid4()) if instance is None else instance
        if not _uuid(self.instance):
            raise ValueError("instance must be a canonical UUID")
        self.session_dir = Path(session_dir).absolute()
        self.session_dir.mkdir(parents=True, exist_ok=False)
        (self.session_dir / "requests").mkdir()
        (self.session_dir / "responses").mkdir()
        (self.session_dir / ".admission.lock").write_bytes(b"0")
        self._closed = False
        self._scans = {}
        self._active_claims = set()
        self._deferred = {}
        _publish(self.session_dir / "session.json",
                 _encode(dict(version=VERSION, instance=self.instance), MAX_REQUEST_BYTES, "invalid_json"))

    def close(self):
        """Make shutdown visible to clients; keep the session for diagnostics."""
        if self._closed:
            return
        _publish(self.session_dir / "session.json",
                 _encode(dict(version=VERSION, instance=self.instance, closed=True), MAX_REQUEST_BYTES, "invalid_json"))
        self._closed = True
        for claimed, (_, _, future) in tuple(self._deferred.items()):
            future.ticket.cancel()
            self._active_claims.discard(claimed)
            _remove(claimed)
        self._deferred.clear()
        for entries in self._scans.values():
            entries.close()
        self._scans.clear()

    def _batch(self, directory, budget):
        """Continue a directory cursor across frames, with bounded entry visits.

        Retained temporary files, claims and live replies must not repeatedly
        occupy the first batch. A finished cursor is reopened on the next call;
        an old cursor already at EOF can restart once immediately for new work.
        """
        entries = self._scans.get(directory)
        restart = entries is not None
        if entries is None:
            entries = os.scandir(self.session_dir / directory)
            self._scans[directory] = entries
        paths = []
        while len(paths) < budget:
            try:
                paths.append(Path(next(entries).path))
            except StopIteration:
                entries.close()
                self._scans.pop(directory, None)
                if paths or not restart:
                    break
                restart = False
                entries = os.scandir(self.session_dir / directory)
                self._scans[directory] = entries
        return paths

    def _expire_temporary(self, path):
        # Only clean files matching _publish's private naming convention. Unknown
        # files are skipped fairly, never guessed to be another writer's scratch.
        parts = path.name.split(".")
        if not (len(parts) == 5 and parts[0] == "" and _uuid(parts[1]) and
                parts[2] == "json" and len(parts[3]) == 32 and
                all(char in "0123456789abcdef" for char in parts[3]) and parts[4] == "tmp"):
            return
        try:
            # A stopped or slow client can own an old file. The admission lock,
            # taken without waiting on the render thread, protects that writer.
            with _admission_lock(self.session_dir, 0, wait=False):
                if not path.is_symlink() and path.stat().st_mtime < time.time() - MAX_TIMEOUT - 1:
                    _remove(path)
        except (_ProtocolError, FileNotFoundError):
            pass

    def _expire_claim(self, path):
        if path in self._active_claims or not _uuid(path.stem):
            return
        try:
            value = _read_json(path, MAX_REQUEST_BYTES, "request_too_large")
            _validate_request(value, self.instance, path.stem)
            if value["deadline"] <= time.time():
                _remove(path)
        except _ProtocolError:
            # Malformed abandoned claims get the full maximum request lifetime.
            if not path.is_symlink() and path.stat().st_mtime < time.time() - MAX_TIMEOUT - 1:
                _remove(path)
        except FileNotFoundError:
            pass

    def _expire_replies(self, budget):
        for path in self._batch("responses", budget):
            try:
                if path.suffix == ".tmp":
                    self._expire_temporary(path)
                elif path.is_symlink() or path.stat().st_mtime <= time.time():
                    _remove(path)
            except FileNotFoundError:
                pass

    def _respond(self, request_id, graph, deadline, result):
        result = dict(result)
        result.update(version=VERSION, request_id=request_id, instance=self.instance)
        result.setdefault("graph", graph)
        result.setdefault("frame", None)
        result.setdefault("layout_hash", None)
        try:
            _validate_response(result, self.instance, request_id, graph)
            data = _encode(result, MAX_RESPONSE_BYTES, "response_too_large")
        except _ProtocolError as exc:
            data = _encode(error_response(exc.code, str(exc), request_id=request_id,
                                          instance=self.instance, graph=graph), MAX_RESPONSE_BYTES, "response_too_large")
        if time.time() < deadline and not self._closed:
            _publish(self.session_dir / "responses" / (request_id + ".json"), data, deadline)

    def pump(self, handler, max_requests=4):
        """Visit at most max_requests queue entries, counting malformed/expired ones.

        Also visit at most that many replies for expiry cleanup. Return the number
        of queue entries visited. No handler calls occur when the queue is empty.
        """
        if type(max_requests) is not int or not 1 <= max_requests <= MAX_PUMP_REQUESTS:
            raise ValueError("max_requests must be an integer between 1 and 64")
        if self._closed:
            return 0
        self._poll_deferred(max_requests)
        self._expire_replies(max_requests)
        processed = 0
        for path in self._batch("requests", max_requests):
            processed += 1
            regular_file = not path.is_symlink() and path.is_file()
            if regular_file and path.suffix == ".tmp":
                self._expire_temporary(path)
                continue
            if regular_file and path.suffix == ".processing":
                self._expire_claim(path)
                continue
            if path.suffix != ".json" or not regular_file or not _uuid(path.stem):
                if path.suffix not in (".processing", ".tmp"):
                    _remove(path)
                continue
            request_id = path.stem
            claimed = path.with_suffix(".processing")
            try:
                # The rename races safely with the client's pending cancellation.
                path.rename(claimed)
            except FileNotFoundError:
                continue
            self._active_claims.add(claimed)
            graph = None
            deadline = time.time() + MAX_TIMEOUT
            deferred = False
            try:
                value = _read_json(claimed, MAX_REQUEST_BYTES, "request_too_large")
                graph = value.get("graph") if isinstance(value.get("graph"), str) else None
                _validate_request(value, self.instance, request_id)
                deadline = value["deadline"]
                if time.time() >= deadline:
                    continue
                try:
                    result = handler(value)
                    if isinstance(result, DeferredResponse):
                        if self._closed:
                            result.ticket.cancel()
                        else:
                            self._deferred[claimed] = (graph, deadline, result)
                            deferred = True
                        continue
                    if not isinstance(result, dict):
                        raise ValueError("Handler must return a response object")
                except Exception as exc:
                    result = error_response("handler_error", str(exc))
                    result["graph"] = graph
                self._respond(request_id, graph, deadline, result)
            except _ProtocolError as exc:
                self._respond(request_id, graph, deadline,
                              error_response(exc.code, str(exc), graph=graph))
            except OSError as exc:
                self._respond(request_id, graph, deadline,
                              error_response("transport_error", str(exc), graph=graph))
            finally:
                if not deferred:
                    self._active_claims.discard(claimed)
                    _remove(claimed)
        return processed

    def _poll_deferred(self, budget):
        # Rotate pending entries so a slow fence cannot starve later completions.
        for claimed in tuple(self._deferred)[:budget]:
            graph, deadline, future = self._deferred.pop(claimed)
            keep = False
            try:
                if time.time() >= deadline:
                    future.ticket.cancel()
                elif not future.ticket.ready:
                    self._deferred[claimed] = (graph, deadline, future)
                    keep = True
                else:
                    self._respond(claimed.stem, graph, deadline, future.ticket.result())
            except Exception as error:
                self._respond(claimed.stem, graph, deadline, error_response('handler_error', str(error), graph=graph))
            finally:
                if not keep:
                    self._active_claims.discard(claimed)
                    _remove(claimed)


def request(session_dir, operation, graph, arguments=None, timeout=10):
    """Send one request and poll for JSON. Every ordinary failure returns an envelope."""
    request_id = str(uuid.uuid4())
    instance = None
    queued = reply = None
    try:
        if not _finite_number(timeout) or not 0 < timeout <= MAX_TIMEOUT:
            raise _ProtocolError("invalid_timeout", "timeout must be finite, positive and at most 300 seconds")
        stop = time.monotonic() + timeout
        session_dir = Path(session_dir).absolute()
        instance = _metadata(session_dir)["instance"]
        value = dict(version=VERSION, request_id=request_id, instance=instance,
                     operation=operation, graph=graph, arguments={} if arguments is None else arguments,
                     deadline=time.time() + timeout)
        _validate_request(value, instance, request_id)
        data = _encode(value, MAX_REQUEST_BYTES, "request_too_large")
        queued = session_dir / "requests" / (request_id + ".json")
        reply = session_dir / "responses" / (request_id + ".json")
        with _admission_lock(session_dir, stop):
            if _metadata(session_dir)["instance"] != instance:
                raise _ProtocolError("instance_mismatch", "Observer session instance changed")
            if _queue_full(session_dir):
                raise _ProtocolError("queue_full", "Observer mailbox is full; retry after pumping frames")
            _publish(queued, data)
        while time.monotonic() < stop:
            if _metadata(session_dir)["instance"] != instance:
                raise _ProtocolError("instance_mismatch", "Observer session instance changed")
            try:
                result = _read_json(reply, MAX_RESPONSE_BYTES, "response_too_large")
            except (FileNotFoundError, PermissionError):
                # A freshly published reply can be briefly sharing-locked on
                # Windows (Python open() exposes this as errno 13, no winerror).
                # Retry only this client-side read, under the original deadline;
                # never resubmit work or make the render-thread pump wait.
                time.sleep(min(POLL_INTERVAL, max(0, stop - time.monotonic())))
                continue
            _validate_response(result, instance, request_id, graph)
            return result
        raise _ProtocolError("timeout", "Timed out; queued request removed, already running work may finish")
    except _ProtocolError as exc:
        return error_response(exc.code, str(exc), request_id=request_id, instance=instance, graph=graph)
    except (OSError, TypeError, ValueError) as exc:
        return error_response("transport_error", str(exc), request_id=request_id, instance=instance, graph=graph)
    finally:
        if queued is not None:
            _remove(queued)
        if reply is not None:
            _remove(reply)
