"""CPU-only protocol tests, including an independent client process."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


class TransportTests(unittest.TestCase):
    def test_deferred_reply_keeps_claim_and_never_collects_pending(self):
        self.assertTrue(hasattr(self.transport, 'DeferredResponse'), 'Deferred mailbox response missing')
        value=self.envelope(); self.queue(value); calls=[]
        future=SimpleNamespace(ready=False, result=lambda: calls.append('collect') or {'status':'ok','result':{'frame':7}}, cancel=lambda: calls.append('cancel'))
        self.mailbox.pump(lambda request: self.transport.DeferredResponse(future))
        self.assertTrue((self.session/'requests'/(value['request_id']+'.processing')).exists())
        for _ in range(3): self.mailbox.pump(lambda request: self.fail('Resubmitted request'))
        self.assertFalse(calls)
        future.ready=True
        self.mailbox.pump(lambda request: self.fail('Resubmitted request'))
        self.assertEqual(self.reply(value)['result'],{'frame':7})
        self.assertEqual(calls,['collect'])
        self.assertFalse(self.mailbox._active_claims)

    def test_deferred_expiry_and_close_cancel_without_late_delivery(self):
        self.assertTrue(hasattr(self.transport, 'DeferredResponse'), 'Deferred mailbox response missing')
        calls=[]
        def defer(request):
            return self.transport.DeferredResponse(SimpleNamespace(ready=False,
                result=lambda: self.fail('Collected cancelled work'), cancel=lambda: calls.append('cancel')))
        first=self.envelope();self.queue(first);self.mailbox.pump(defer)
        with patch('observer_transport.time.time',return_value=first['deadline']+1): self.mailbox.pump(defer)
        self.assertEqual(calls,['cancel'])
        self.assertFalse(self.mailbox._active_claims)
        second=self.envelope();self.queue(second);self.mailbox.pump(defer);self.mailbox.close()
        self.assertEqual(calls,['cancel','cancel'])
        self.assertFalse(list((self.session/'responses').glob('*.json')))

    def setUp(self):
        spec = importlib.util.find_spec("observer_transport")
        self.assertIsNotNone(spec, "the local mailbox implementation is missing")
        import observer_transport
        self.transport = observer_transport
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.session = Path(self.temporary.name) / "session"
        self.mailbox = observer_transport.LocalMailbox(self.session)
        self.addCleanup(self.mailbox.close)

    def envelope(self, **overrides):
        value = dict(version=1, request_id=str(uuid.uuid4()),
                     instance=self.mailbox.instance, graph="Scene", operation="list",
                     arguments={}, deadline=time.time() + 10)
        value.update(overrides)
        return value

    def queue(self, value, filename=None):
        path = self.session / "requests" / (filename or value["request_id"] + ".json")
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def reply(self, value):
        return json.loads((self.session / "responses" /
                           (value["request_id"] + ".json")).read_text(encoding="utf-8"))

    def cli(self, *arguments):
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "inspect_cli.py"), "--session", str(self.session),
             *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        return process

    def complete(self, process, handler):
        deadline = time.monotonic() + 5
        while process.poll() is None and time.monotonic() < deadline:
            self.mailbox.pump(handler)
            time.sleep(0.01)
        stdout, stderr = process.communicate(timeout=3)
        return process.returncode, json.loads(stdout), stderr

    def test_session_is_new_versioned_and_close_is_visible(self):
        metadata = json.loads((self.session / "session.json").read_text())
        self.assertEqual(metadata, {"version": 1, "instance": self.mailbox.instance})
        self.assertEqual(str(uuid.UUID(metadata["instance"])), metadata["instance"])
        with self.assertRaises(FileExistsError):
            self.transport.LocalMailbox(self.session)
        self.mailbox.close()
        value = self.transport.request(self.session, "list", "Scene", timeout=0.1)
        self.assertEqual(value["error"]["code"], "session_closed")
        self.assertEqual(value["version"], 1)

    def test_constructor_rejects_invalid_instance_without_creating_session(self):
        other = self.session.parent / "other"
        with self.assertRaises(ValueError):
            self.transport.LocalMailbox(other, instance="../../outside")
        self.assertFalse(other.exists())

    def test_cli_round_trip_runs_handler_on_pumping_thread(self):
        calls = []
        owner = threading.get_ident()
        def handler(value):
            calls.append(value)
            self.assertEqual(threading.get_ident(), owner)
            return dict(status="ok", graph=value["graph"], frame=7,
                        layout_hash="abc", result={"fields": ["normal"]})
        process = self.cli("list", "--graph", "Scene")
        code, value, stderr = self.complete(process, handler)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(value["result"], {"fields": ["normal"]})
        self.assertEqual(value["frame"], 7)
        self.assertEqual(value["instance"], self.mailbox.instance)
        self.assertEqual(value["request_id"], calls[0]["request_id"])
        self.assertEqual(value["version"], 1)
        self.assertEqual(len(calls), 1)
        self.assertFalse(list((self.session / "requests").glob("*.json")))
        self.assertFalse(list((self.session / "responses").glob("*.json")))

    def test_cli_inspect_forwards_region_fields_and_export(self):
        calls = []
        def handler(value):
            calls.append(value)
            return {"status": "ok", "result": {}}
        process = self.cli("inspect", "--graph", "Scene", "--region", "2", "3", "4", "5",
                           "--fields", "normal", "id", "--export")
        code, _, stderr = self.complete(process, handler)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(calls[0]["operation"], "inspect")
        self.assertEqual(calls[0]["arguments"],
                         {"region": [2, 3, 4, 5], "fields": ["normal", "id"], "export": True})

    def test_cli_read_forwards_raw_output_mip_and_slice(self):
        calls = []
        def handler(value):
            calls.append(value)
            return {"status": "ok", "result": {"files": []}}
        process = self.cli("read", "--graph", "Scene", "--output", "GBuffer.depth",
                           "--mip", "2", "--slice", "3")
        code, _, stderr = self.complete(process, handler)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(calls[0]["operation"], "read")
        self.assertEqual(calls[0]["arguments"], {"output": "GBuffer.depth", "mip": 2, "slice": 3})

    def test_cli_help_keeps_stdout_json(self):
        process = self.cli("--help")
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0)
        self.assertTrue(stdout.startswith("{"), "help must keep stdout a JSON envelope")
        self.assertEqual(json.loads(stdout)["status"], "ok")
        self.assertIn("--session", stderr)

    def test_cli_compare_parses_rules_and_absolute_paths(self):
        rules = self.session.parent / "rules.json"
        rules.write_text('{"normal": {"mode": "normal_angle", "degrees": 1}}')
        reference = self.session.parent / "reference.npz"
        reference.write_bytes(b"reference owned by service")
        calls = []
        def handler(value):
            calls.append(value)
            return {"status": "comparison_failed", "result": {"passed": False}}
        process = self.cli("compare", "--graph", "Scene", "--region", "0", "0", "1", "1",
                           "--reference", str(reference), "--rules", str(rules), "--mask", "coverage",
                           "--fields", "normal")
        code, value, stderr = self.complete(process, handler)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(value["status"], "comparison_failed")
        args = calls[0]["arguments"]
        self.assertEqual(args["reference"], str(reference.resolve()))
        self.assertEqual(args["rules"], {"normal": {"mode": "normal_angle", "degrees": 1}})
        self.assertEqual(args["mask"], "coverage")

    def test_cli_validation_error_is_json_and_exit_two(self):
        process = self.cli("inspect", "--graph", "Scene")
        stdout, _ = process.communicate(timeout=5)
        value = json.loads(stdout)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(value["status"], "error")
        self.assertEqual(value["version"], 1)

    def test_cli_handler_exception_is_structured_error(self):
        def handler(value):
            raise ValueError("unsupported output")
        code, value, _ = self.complete(self.cli("list", "--graph", "Scene"), handler)
        self.assertEqual(code, 2)
        self.assertEqual(value["error"]["code"], "handler_error")
        self.assertIn("unsupported output", value["error"]["message"])

    def test_cli_timeout_removes_queued_work(self):
        process = self.cli("--timeout", "0.08", "list", "--graph", "Scene")
        stdout, _ = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 3)
        self.assertEqual(json.loads(stdout)["error"]["code"], "timeout")
        calls = []
        self.mailbox.pump(lambda value: calls.append(value))
        self.assertEqual(calls, [])
        self.assertEqual(list((self.session / "requests").iterdir()), [])

    def test_timeout_is_finite_positive_and_bounded(self):
        for timeout in [0, -1, float("inf"), float("nan"), True, 301, "1", 10 ** 1000]:
            with self.subTest(timeout=timeout):
                try:
                    value = self.transport.request(self.session, "list", "Scene", timeout=timeout)
                except OverflowError:
                    self.fail("oversized integer timeout must return a structured error")
                self.assertEqual(value["error"]["code"], "invalid_timeout")
        self.assertEqual(list((self.session / "requests").iterdir()), [])

    def test_malformed_session_is_versioned_error(self):
        metadata = self.session / "session.json"
        for content in ['{"version": 2, "instance": "bad"}', '[]', '{']:
            metadata.write_text(content)
            value = self.transport.request(self.session, "list", "Scene", timeout=0.1)
            self.assertEqual(value["status"], "error")
            self.assertEqual(value["version"], 1)

    def test_no_falcor_import_in_client(self):
        process = subprocess.run(
            [sys.executable, "-c", "import sys; import observer_transport; "
             "assert 'falcor' not in sys.modules"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_pump_budget_includes_invalid_files(self):
        for index in range(9):
            (self.session / "requests" / f"invalid-{index}.json").write_text("{")
        calls = []
        self.assertEqual(self.mailbox.pump(lambda value: calls.append(value), max_requests=3), 3)
        self.assertEqual(len(list((self.session / "requests").iterdir())), 6)
        self.assertEqual(calls, [])

    def test_pump_budget_includes_expired_requests(self):
        expired = self.envelope(deadline=time.time() - 1)
        path = self.queue(expired)
        self.assertEqual(self.mailbox.pump(lambda _: self.fail("expired request reached handler"),
                                          max_requests=1), 1)
        self.assertFalse(path.exists())

    def temporary_request(self, index, age=0):
        request_id = f"00000000-0000-0000-0000-{index:012d}"
        path = self.session / "requests" / (f".{request_id}.json." + "a" * 32 + ".tmp")
        path.write_text("{")
        modified = time.time() - age
        os.utime(path, (modified, modified))
        return path

    def test_fresh_temporary_files_do_not_starve_queued_request(self):
        temporary = [self.temporary_request(index) for index in range(4)]
        value = self.envelope(request_id="ffffffff-ffff-ffff-ffff-ffffffffffff")
        self.queue(value)
        calls = []
        for _ in range(4):
            visited = self.mailbox.pump(lambda request: calls.append(request) or
                                       {"status": "ok", "result": {}}, max_requests=2)
            self.assertLessEqual(visited, 2)
        self.assertEqual(len(calls), 1, "retained temporary files must not monopolize the pump")
        self.assertTrue(all(path.exists() for path in temporary), "fresh publication files must be preserved")

    def test_stale_temporary_files_are_reclaimed_in_bounded_batches(self):
        temporary = [self.temporary_request(index, age=400) for index in range(4)]
        self.assertEqual(self.mailbox.pump(lambda _: self.fail("temporary file reached handler"),
                                          max_requests=2), 2)
        self.assertEqual(sum(path.exists() for path in temporary), 2)
        for _ in range(3):
            self.mailbox.pump(lambda _: self.fail("temporary file reached handler"), max_requests=2)
        self.assertFalse(any(path.exists() for path in temporary))

    def test_stale_temporary_file_is_preserved_while_publisher_holds_lock(self):
        temporary = self.temporary_request(0, age=400)
        with self.transport._admission_lock(self.session, time.monotonic() + 1):
            self.mailbox.pump(lambda _: self.fail("temporary file reached handler"))
            self.assertTrue(temporary.exists(), "active publisher owns its temporary file")
        for _ in range(2):
            self.mailbox.pump(lambda _: self.fail("temporary file reached handler"))
        self.assertFalse(temporary.exists(), "abandoned temporary file should be reclaimed once unlocked")

    def test_expired_claims_are_reclaimed_without_replaying_handler(self):
        claims = []
        for index in range(4):
            value = self.envelope(request_id=f"00000000-0000-0000-0000-{index:012d}",
                                  deadline=time.time() - 1)
            claims.append(self.queue(value, value["request_id"] + ".processing"))
        value = self.envelope(request_id="ffffffff-ffff-ffff-ffff-ffffffffffff")
        self.queue(value)
        calls = []
        for _ in range(4):
            self.assertLessEqual(self.mailbox.pump(lambda request: calls.append(request) or
                                                  {"status": "ok", "result": {}}, max_requests=2), 2)
        self.assertEqual(len(calls), 1, "abandoned claims must not starve new requests")
        self.assertFalse(any(path.exists() for path in claims))

    def test_current_handler_claim_is_not_removed_even_after_expiry(self):
        value = self.envelope()
        self.queue(value)
        def handler(request):
            claimed = self.session / "requests" / (request["request_id"] + ".processing")
            expired = dict(request, deadline=time.time() - 1)
            claimed.write_text(json.dumps(expired))
            self.mailbox.pump(lambda _: self.fail("nested pump invoked another handler"))
            self.assertTrue(claimed.exists(), "a running handler retains its claimed request")
            return {"status": "ok", "result": {}}
        self.mailbox.pump(handler)
        self.assertEqual(self.reply(value)["status"], "ok")

    def test_unexpired_claim_and_unknown_scratch_are_preserved_without_starvation(self):
        value = self.envelope(request_id="00000000-0000-0000-0000-000000000001")
        claim = self.queue(value, value["request_id"] + ".processing")
        scratch = self.session / "requests" / ".unrelated.tmp"
        scratch.write_text("external scratch")
        for path in (claim, scratch):
            os.utime(path, (time.time() - 400, time.time() - 400))
        queued = self.envelope(request_id="ffffffff-ffff-ffff-ffff-ffffffffffff")
        self.queue(queued)
        calls = []
        for _ in range(5):
            self.mailbox.pump(lambda request: calls.append(request) or
                              {"status": "ok", "result": {}}, max_requests=1)
        self.assertEqual(len(calls), 1)
        self.assertTrue(claim.exists(), "an unexpired claim must be preserved regardless of file age")
        self.assertEqual(scratch.read_text(), "external scratch")

    def test_unexpired_replies_do_not_starve_expiry_cleanup(self):
        replies = self.session / "responses"
        for index in range(4):
            path = replies / (f"00000000-0000-0000-0000-{index:012d}.json")
            path.write_text("{}")
            os.utime(path, (time.time() + 300, time.time() + 300))
        expired = replies / "ffffffff-ffff-ffff-ffff-ffffffffffff.json"
        expired.write_text("{}")
        for _ in range(4):
            self.mailbox.pump(lambda _: self.fail("reply cleanup invoked handler"), max_requests=2)
        self.assertFalse(expired.exists(), "live replies must not monopolize expiry scans")

    def test_rejects_invalid_envelopes_without_calling_handler(self):
        cases = [dict(version=2), dict(instance=str(uuid.uuid4())),
                 dict(deadline=float("nan")), dict(deadline=time.time() + 10000),
                 dict(arguments=[]), dict(graph=""), dict(operation="exec")]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                value = self.envelope(**overrides)
                self.queue(value)
                self.mailbox.pump(lambda _: self.fail("invalid request reached handler"))
                reply = self.reply(value)
                self.assertEqual(reply["status"], "error")
                self.assertEqual(reply["version"], 1)
                self.assertEqual(reply["instance"], self.mailbox.instance)

    def test_request_uuid_and_response_destination_cannot_escape_session(self):
        value = self.envelope(request_id="../../escape", response_path=str(self.session.parent / "escape"))
        self.queue(value, "attacker.json")
        self.mailbox.pump(lambda _: self.fail("invalid UUID reached handler"))
        self.assertFalse((self.session.parent / "escape").exists())
        good = self.envelope(response_path=str(self.session.parent / "escape"))
        self.queue(good)
        self.mailbox.pump(lambda _: {"status": "ok", "result": 42})
        self.assertEqual(self.reply(good)["result"], 42)
        self.assertFalse((self.session.parent / "escape").exists())

    def test_size_and_queue_limits(self):
        value = self.transport.request(self.session, "inspect", "Scene",
                                       {"padding": "x" * 70000}, timeout=0.1)
        self.assertEqual(value["error"]["code"], "request_too_large")
        for _ in range(self.transport.MAX_QUEUE_SIZE):
            self.queue(self.envelope())
        value = self.transport.request(self.session, "list", "Scene", timeout=0.1)
        self.assertEqual(value["error"]["code"], "queue_full")

    def test_concurrent_processes_cannot_overfill_queue(self):
        for _ in range(self.transport.MAX_QUEUE_SIZE - 2):
            self.queue(self.envelope())
        processes = [self.cli("--timeout", "2", "list", "--graph", "Scene") for _ in range(4)]
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and sum(p.poll() is not None for p in processes) < 2:
            self.assertLessEqual(len(list((self.session / "requests").iterdir())), self.transport.MAX_QUEUE_SIZE + 1)
            time.sleep(0.01)
        self.assertEqual(len(list((self.session / "requests").glob("*.json"))), self.transport.MAX_QUEUE_SIZE)
        outcomes = [self.complete(p, lambda _: {"status": "ok", "result": {}}) for p in processes]
        self.assertEqual(sorted(item[0] for item in outcomes), [0, 0, 2, 2], outcomes)
        self.assertEqual(sorted(item[1].get('error', {}).get('code', 'ok') for item in outcomes),
                         ['ok', 'ok', 'queue_full', 'queue_full'], outcomes)

    def test_client_rejects_response_with_wrong_identity(self):
        process = self.cli("--timeout", "2", "list", "--graph", "Scene")
        deadline = time.monotonic() + 1
        queued = []
        while not queued and time.monotonic() < deadline:
            queued = list((self.session / "requests").glob("*.json"))
            time.sleep(0.005)
        self.assertEqual(len(queued), 1)
        request_id = queued[0].stem
        reply = {"version": 1, "request_id": request_id, "instance": str(uuid.uuid4()),
                 "graph": "Scene", "status": "ok", "result": {}}
        (self.session / "responses" / (request_id + ".json")).write_text(json.dumps(reply))
        stdout, _ = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(stdout)["error"]["code"], "response_mismatch")

    @unittest.skipUnless(os.name == 'nt', 'Uses the real Windows file-sharing boundary')
    def test_client_retries_a_real_transient_reply_sharing_conflict(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        original_read = self.transport._read_json
        conflicts, handled = [], []

        def read_with_one_real_conflict(path, *args, **kwargs):
            if path.parent == self.session / 'responses' and not conflicts:
                self.mailbox.pump(lambda request: handled.append(request) or {'status': 'ok', 'result': 17})
                self.assertTrue(path.is_file())
                # Permit deletion, but deny other readers until this first read
                # attempt unwinds. No timing race or permanent permission change.
                handle = kernel.CreateFileW(str(path), 0x80000000, 4, None, 3, 0x80, None)
                self.assertNotEqual(handle, ctypes.c_void_p(-1).value, ctypes.get_last_error())
                try:
                    try:
                        return original_read(path, *args, **kwargs)
                    except PermissionError as error:
                        conflicts.append((error.errno, getattr(error, 'winerror', None)))
                        raise
                finally:
                    kernel.CloseHandle(handle)
            return original_read(path, *args, **kwargs)

        with patch.object(self.transport, '_read_json', side_effect=read_with_one_real_conflict):
            reply = self.transport.request(self.session, 'list', 'Scene', timeout=1)
        self.assertEqual(len(conflicts), 1, 'Must observe the actual kernel sharing conflict')
        self.assertEqual(reply['status'], 'ok', (reply, conflicts))
        self.assertEqual(reply['result'], 17)
        self.assertEqual(len(handled), 1, 'A read retry must not resubmit the operation')
        self.assertFalse(list((self.session / 'requests').iterdir()))
        self.assertFalse(list((self.session / 'responses').iterdir()))

    def test_reply_permission_retry_is_bounded_by_client_deadline(self):
        original_read = self.transport._read_json
        attempts = []
        def denied_reply(path, *args, **kwargs):
            if path.parent == self.session / 'responses':
                attempts.append(path)
                raise PermissionError(13, 'reply remains occupied', str(path))
            return original_read(path, *args, **kwargs)
        start = time.monotonic()
        with patch.object(self.transport, '_read_json', side_effect=denied_reply):
            reply = self.transport.request(self.session, 'list', 'Scene', timeout=0.05)
        self.assertEqual(reply['error']['code'], 'timeout', reply)
        self.assertGreater(len(attempts), 1)
        self.assertLess(time.monotonic() - start, 2)
        self.assertFalse(list((self.session / 'requests').glob('*.json')))

    def test_metadata_permission_error_is_not_retried_as_a_reply(self):
        with patch.object(self.transport, '_read_json', side_effect=PermissionError(13, 'metadata denied')) as read:
            reply = self.transport.request(self.session, 'list', 'Scene', timeout=1)
        self.assertEqual(reply['error']['code'], 'session_unavailable', reply)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(list((self.session / "requests").iterdir()), [])

    def test_expired_unread_replies_are_reclaimed(self):
        value = self.envelope(deadline=time.time() + 0.04)
        self.queue(value)
        self.mailbox.pump(lambda _: {"status": "ok", "result": {}})
        self.assertEqual(len(list((self.session / "responses").iterdir())), 1)
        time.sleep(0.05)
        self.assertEqual(self.mailbox.pump(lambda _: self.fail("idle pump called handler")), 0)
        self.assertEqual(list((self.session / "responses").iterdir()), [])

    def test_server_rejects_oversized_request(self):
        value = self.envelope()
        self.queue(value).write_text('{"padding":"' + "x" * 70000 + '"}')
        self.mailbox.pump(lambda _: self.fail("oversized request reached handler"))
        self.assertEqual(self.reply(value)["error"]["code"], "request_too_large")

    def test_server_bounds_and_validates_handler_result(self):
        for result in [{"status": "surprise"}, {"status": "ok", "result": float("nan")},
                       {"status": "ok", "result": "x" * (9 * 1024 * 1024)}]:
            value = self.envelope()
            self.queue(value)
            self.mailbox.pump(lambda _: result)
            self.assertEqual(self.reply(value)["status"], "error")

    def test_handler_cannot_spoof_response_identity(self):
        value = self.envelope()
        self.queue(value)
        self.mailbox.pump(lambda _: {"version": 9, "instance": "wrong", "request_id": "wrong",
                                    "status": "ok", "result": {}})
        reply = self.reply(value)
        self.assertEqual(reply["version"], 1)
        self.assertEqual(reply["instance"], self.mailbox.instance)
        self.assertEqual(reply["request_id"], value["request_id"])

    def test_in_flight_timeout_does_not_claim_to_cancel_handler(self):
        process = self.cli("--timeout", "0.08", "list", "--graph", "Scene")
        deadline = time.monotonic() + 3
        while not list((self.session / "requests").glob("*.json")) and time.monotonic() < deadline:
            time.sleep(0.005)
        calls = []
        def handler(value):
            calls.append(value)
            time.sleep(0.15)
            return {"status": "ok", "result": {}}
        self.mailbox.pump(handler)
        stdout, _ = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 3)
        self.assertEqual(json.loads(stdout)["error"]["code"], "timeout")
        self.assertEqual(len(calls), 1)
        self.assertEqual(list((self.session / "responses").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
