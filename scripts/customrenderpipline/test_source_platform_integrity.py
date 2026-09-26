"""Exercise the actual launcher main with memory-only files and no processes.

These are orchestration regressions, not a simulation of UE texture building.
The engine boundary is mocked because tests must never launch UE or write assets.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from source_assets import launch_platform_texture as launcher
import test_source_platform_texture as texture_fixtures


class MemoryRun:
    def __init__(self, *, changed=None, stale=None):
        self.run = (launcher.BASE / 'review-memory-only').resolve()
        self.protected = self.run / 'protected.fixture'
        self.metadata = self.run / 'Export/result.json'
        self.payload = self.run / 'Export/platform-mips.bin'
        self.dds = self.run / 'Export/T_GridChecker_A.bc1.srgb.dds'
        metadata, payload = texture_fixtures.PlatformTextureTests().fixture()
        self.export_bytes = {self.metadata: json.dumps(metadata).encode(), self.payload: payload}
        self.files = {self.protected: b'original protected bytes'}
        self.plan = {
            'project': str(self.run / 'Scratch/SourceTextureScratch.uproject'),
            'protected': [self.identity(self.protected, self.files[self.protected])],
            'executed_plugin': [], 'source_plugin': [],
            'original_project_launched': False, 'capture_inputs': False,
        }
        self.files[self.run / 'prepared.json'] = json.dumps(self.plan).encode()
        self.changed, self.reads = changed, {}
        self.records, self.execute_calls, self.output_sinks = [], [], {}
        if stale:
            path = self.run / 'Export' / stale
            self.files[path] = self.export_bytes.get(path, b'previous DDS')

    @staticmethod
    def identity(path, data):
        return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def read_bytes(self, path):
        path = path.resolve()
        if path in self.output_sinks:
            return self.output_sinks[path].getvalue()
        if path not in self.files:
            if path.is_relative_to(self.run):
                raise FileNotFoundError(path)
            return self.original_read_bytes(path)  # Read-only production source fingerprinting.
        data = self.files[path]
        self.reads[path] = self.reads.get(path, 0) + 1
        if self.execute_calls and self.reads[path] == 1:
            if self.changed == 'payload' and path == self.payload:
                self.files[path] = bytes([data[0] ^ 1]) + data[1:]
            if self.changed == 'metadata' and path == self.metadata:
                value = json.loads(data)
                value['encoder'] = 'changed after parsed byte read'
                self.files[path] = json.dumps(value).encode()
        return data

    def exists(self, path):
        path = path.resolve()
        if path.is_relative_to(self.run):
            return path in self.files or path in self.output_sinks or path in {
                self.run, self.run / 'Export', self.run / 'Scratch', self.run / 'User', self.run / 'DDC',
            }
        return self.original_exists(path)

    def open(self, path, mode='r', *args, **kwargs):
        path = path.resolve()
        if not path.is_relative_to(self.run) and mode == 'rb':
            return self.original_open(path, mode, *args, **kwargs)
        if path != self.dds or mode != 'xb':
            raise AssertionError('Unexpected filesystem open: ' + str((path, mode)))
        if self.exists(path):
            raise FileExistsError(path)

        class Sink(io.BytesIO):
            def close(self):
                pass  # Keep the memory-only written bytes available for identity().

        self.output_sinks[path] = Sink()
        return self.output_sinks[path]

    def execute(self, command, run, stage, env, timeout):
        self.execute_calls.append(stage)
        if self.changed == 'protected':
            self.files[self.protected] = b'changed protected bytes'
        # Existing exports are intentionally not replaced: UE's exporter refuses
        # them, while the old sentinel could still accept previous passed JSON.
        for path, data in self.export_bytes.items():
            self.files.setdefault(path, data)
        return {'exit_code': 0, 'pid': 999, 'command': ['memory-only engine boundary']}

    def invoke(self):
        self.original_read_bytes, self.original_exists = Path.read_bytes, Path.exists
        self.original_open = Path.open
        self.output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(launcher.argparse.ArgumentParser, 'parse_args', return_value=SimpleNamespace(
                existing=self.run, build=False, run=True)))
            stack.enter_context(patch.object(Path, 'read_bytes', lambda path: self.read_bytes(path)))
            stack.enter_context(patch.object(Path, 'read_text', lambda path, *a, **k: self.read_bytes(path).decode('utf-8-sig')))
            stack.enter_context(patch.object(Path, 'exists', lambda path: self.exists(path)))
            stack.enter_context(patch.object(Path, 'is_file', lambda path: path.resolve() in self.files))
            stack.enter_context(patch.object(Path, 'open', lambda path, *a, **k: self.open(path, *a, **k)))
            stack.enter_context(patch.object(launcher, 'prepare_loader', return_value={}))
            stack.enter_context(patch.object(launcher, 'execute', side_effect=self.execute))
            stack.enter_context(patch.object(launcher, 'write', side_effect=lambda path, value: self.records.append((path, value))))
            stack.enter_context(patch.object(launcher.subprocess, 'Popen', side_effect=AssertionError('No subprocess allowed')))
            stack.enter_context(contextlib.redirect_stdout(self.output))
            try:
                launcher.main()
            except Exception as error:
                return error
        return None

    def successes(self):
        return [value for path, value in self.records
                if path.name == 'source-platform-result.json' and value.get('status') == 'passed']


class SourcePlatformIntegrityTests(unittest.TestCase):
    def test_fresh_unchanged_export_can_publish_matching_dds(self):
        run = MemoryRun()
        self.assertIsNone(run.invoke())
        self.assertEqual(run.execute_calls, ['export'])
        success, = run.successes()
        self.assertIs(success['protected_unchanged'], True)
        self.assertEqual(success['protected'], run.plan['protected'])
        protection_records = [value for path, value in run.records if path.name.startswith('protected-after-')]
        self.assertEqual(protection_records, [{'unchanged': True, 'files': run.plan['protected']}])
        embedded = run.output_sinks[run.dds].getvalue()[148:]
        self.assertEqual(hashlib.sha256(embedded).hexdigest(), success['payload']['sha256'])

    def test_protected_change_cannot_leave_a_passed_manifest(self):
        run = MemoryRun(changed='protected')
        self.assertIsInstance(run.invoke(), (RuntimeError, ValueError))
        self.assertEqual(run.successes(), [], 'Protection failure was detected only after publishing passed')
        self.assertNotIn('SOURCE_PLATFORM_TEXTURE ', run.output.getvalue())

    def test_payload_change_after_consumption_cannot_publish(self):
        run = MemoryRun(changed='payload')
        error = run.invoke()
        self.assertEqual(run.successes(), [], 'DDS input bytes differ from the later recorded payload identity')
        self.assertIsInstance(error, (RuntimeError, ValueError))

    def test_metadata_change_after_parse_cannot_publish(self):
        run = MemoryRun(changed='metadata')
        error = run.invoke()
        self.assertEqual(run.successes(), [], 'Parsed metadata bytes differ from the later recorded metadata identity')
        self.assertIsInstance(error, (RuntimeError, ValueError))

    def test_existing_export_artifacts_are_rejected_before_any_process(self):
        for name in ('result.json', 'platform-mips.bin', 'T_GridChecker_A.bc1.srgb.dds'):
            with self.subTest(name=name):
                run = MemoryRun(stale=name)
                error = run.invoke()
                self.assertEqual(run.execute_calls, [], 'Existing evidence was not rejected before process launch')
                self.assertEqual(run.successes(), [])
                self.assertIsInstance(error, (RuntimeError, ValueError, FileExistsError))


if __name__ == '__main__':
    unittest.main()
