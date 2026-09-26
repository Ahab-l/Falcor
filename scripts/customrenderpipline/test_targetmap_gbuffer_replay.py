"""CPU-only contract tests; never load RenderDoc or launch a GPU process."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


MODULE = Path(__file__).with_name('_targetmap_gbuffer_replay.py')
EXPECTED = (
    ('ResourceId::955', 'SceneColor', 'R16G16B16A16_FLOAT', 'R16G16B16A16_FLOAT', 8),
    ('ResourceId::40947', 'GBufferA', 'R10G10B10A2_UNORM', 'R10G10B10A2_UNORM', 4),
    ('ResourceId::256513', 'GBufferB', 'B8G8R8A8_TYPELESS', 'B8G8R8A8_UNORM', 4),
    ('ResourceId::256515', 'GBufferC', 'B8G8R8A8_TYPELESS', 'B8G8R8A8_SRGB', 4),
    ('ResourceId::256540', 'GBufferD', 'B8G8R8A8_TYPELESS', 'B8G8R8A8_UNORM', 4),
    ('ResourceId::945', 'SceneDepthZ', 'D32S8_TYPELESS', 'D32S8', 8),
)


class CollectorContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'A1 read-only GBuffer collector is not implemented')
        spec = importlib.util.spec_from_file_location('targetmap_gbuffer_worker', MODULE)
        self.worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.worker)
        self.textures, self.targets = {}, []
        for rid, name, resource_format, view_format, bpp in EXPECTED:
            self.textures[rid] = dict(resource=rid, name=name, format=resource_format,
                width=1424, height=1040, depth=1, arraysize=1, mips=1, dimension=2, samples=1)
            self.targets.append(dict(resource=rid, format=view_format, firstMip=0,
                firstSlice=0, numMips=1, numSlices=1, elementByteSize=bpp))
        self.viewports = [dict(x=0.0, y=0.0, width=1421.0, height=1035.0,
            minDepth=0.0, maxDepth=1.0, enabled=True)]
        self.scissors = [dict(x=0, y=0, width=1421, height=1035, enabled=True)]

    def plan(self, event=1452):
        return self.worker.plan_snapshots(event, self.textures, self.targets[:5],
            self.targets[5], self.viewports, self.scissors)

    def test_all_five_nonnull_rtvs_and_actual_dsv_are_planned(self):
        plans = self.plan()
        self.assertEqual([p['resource'] for p in plans], [r[0] for r in EXPECTED])
        self.assertEqual([p['binding'] for p in plans], ['RTV'] * 5 + ['DSV'])
        self.assertEqual(sum(p['planned_byte_size'] for p in plans), 47390720)
        for plan, row in zip(plans, EXPECTED):
            self.assertEqual(plan['format'], row[3])
            self.assertEqual(plan['resource_format'], row[2])
            self.assertEqual(plan['subresource'], dict(mip=0, slice=0, sample=0))
            self.assertEqual(plan['view_rect'], [0, 0, 1421, 1035])
            self.assertEqual(plan['role'], 'offline_reference_only')
            self.assertFalse(plan['full_renderer_parity'])
        self.assertFalse(plans[-1]['plane_parity_verified'])
        self.assertEqual(plans[-1]['raw_readback_encoding'], 'unverified')

    def test_unapproved_event_is_rejected(self):
        for event in (1426, 1437, 1853, True):
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.plan(event)

    def test_missing_extra_or_reordered_nonnull_binding_is_rejected(self):
        original = copy.deepcopy(self.targets)
        mutations = [original[:4] + [original[-1]],
            original[:5] + [original[0], original[-1]],
            [original[1], original[0]] + original[2:]]
        for targets in mutations:
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                self.worker.plan_snapshots(1452, self.textures, targets[:-1],
                    targets[-1], self.viewports, self.scissors)

    def test_null_trailing_slots_do_not_silently_drop_bound_rtvs(self):
        targets = self.targets[:5] + [dict(resource='ResourceId::0')]
        self.assertEqual(len(self.worker.plan_snapshots(1452, self.textures,
            targets, self.targets[-1], self.viewports, self.scissors)), 6)
        targets[2] = dict(resource='ResourceId::0')
        with self.assertRaises(ValueError):
            self.worker.plan_snapshots(1452, self.textures, targets,
                self.targets[-1], self.viewports, self.scissors)

    def test_identity_format_shape_subresource_and_msaa_are_exact(self):
        for kind, key, bad in [('target', 'resource', 'ResourceId::967'),
            ('target', 'format', 'R8G8B8A8_UNORM'), ('target', 'firstMip', 1),
            ('target', 'numSlices', 2), ('target', 'elementByteSize', 16),
            ('texture', 'format', 'B8G8R8A8_UNORM'), ('texture', 'width', 1421),
            ('texture', 'samples', 4), ('texture', 'arraysize', 2),
            ('texture', 'name', 'NotGBufferB')]:
            data = self.targets[2] if kind == 'target' else self.textures[EXPECTED[2][0]]
            old = data[key]
            data[key] = bad
            with self.subTest(kind=kind, key=key), self.assertRaises(ValueError): self.plan()
            data[key] = old

    def test_viewport_scissor_and_depth_range_are_exact(self):
        for data, key, bad in [(self.viewports[0], 'x', 0.5),
            (self.viewports[0], 'width', float('nan')),
            (self.viewports[0], 'maxDepth', 0.5),
            (self.scissors[0], 'enabled', False), (self.scissors[0], 'width', 1424)]:
            old = data[key]
            data[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): self.plan()
            data[key] = old
        self.viewports.append(copy.deepcopy(self.viewports[0]))
        with self.assertRaises(ValueError): self.plan()

    def test_payload_verification_preserves_exact_bytes_without_decoding(self):
        plan = self.plan()[-1]
        payload = b'\x81\x7f\x00\xff' * (plan['planned_byte_size'] // 4)
        with tempfile.TemporaryDirectory() as temp:
            artifacts = self.worker.Artifacts(Path(temp) / 'reference')
            record = self.worker.save_snapshot(artifacts, plan, payload)
            self.assertEqual((artifacts.directory / record['file']).read_bytes(), payload)
            self.assertEqual(record['sha256'], hashlib.sha256(payload).hexdigest())
            self.assertTrue(record['readback_length_verified'])
            self.assertFalse(record['plane_parity_verified'])
            self.assertEqual(record['raw_readback_encoding'], 'unverified')

    def test_short_and_long_payloads_are_not_published(self):
        plan = self.plan()[1]
        with tempfile.TemporaryDirectory() as temp:
            artifacts = self.worker.Artifacts(Path(temp) / 'reference')
            for offset in (-1, 1):
                with self.assertRaises(ValueError):
                    self.worker.save_snapshot(artifacts, plan,
                        b'\0' * (plan['planned_byte_size'] + offset))
            self.assertEqual(artifacts.files, [])

    def test_total_budget_and_filename_and_fresh_directory_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'reference'
            artifacts = self.worker.Artifacts(target)
            with self.assertRaises(FileExistsError): self.worker.Artifacts(target)
            for name in ('../bad.bin', 'dir/bad.bin', 'dir\\bad.bin'):
                with self.assertRaises(ValueError): artifacts.raw(name, b'bad')
            artifacts.used = self.worker.MAX_BYTES - self.worker.RESULT_RESERVE
            with self.assertRaises(ValueError): artifacts.raw('too-much.bin', b'x')
            self.assertEqual(list(target.iterdir()), [])

    def test_embedded_startup_can_resolve_without_dunder_file(self):
        del self.worker.__file__
        with patch.dict('os.environ', {'CRP_TARGETMAP_GBUFFER_SCRIPT': str(MODULE)}):
            self.assertEqual(self.worker.worker_path(), MODULE.resolve())
            helpers = self.worker.load_helpers(self.worker.worker_path())
            self.assertTrue(callable(helpers.simple))

    def test_output_must_be_fresh_owned_child(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / 'build/targetmap-shading-a1'
            for out in (root, base, root / 'build/targetmap-shading-a10/run'):
                with self.assertRaises(ValueError): self.worker.prepare_output(root, out)
            out = base / 'run'
            self.assertEqual(self.worker.prepare_output(root, out), out.resolve())
            (out / 'sentinel').write_text('do not overwrite')
            with self.assertRaises(FileExistsError): self.worker.prepare_output(root, out)
            self.assertEqual((out / 'sentinel').read_text(), 'do not overwrite')

    def test_pipeline_revalidation_rejects_live_binding_drift(self):
        prior = dict(event=1452, pipeline='ResourceId::40847', ancestry=['BasePass', 'floor'],
            output_merger={'renderTargets': self.targets}, rasterizer={'viewports': self.viewports})
        self.worker.validate_pipeline(copy.deepcopy(prior), prior)
        for field in ('pipeline', 'ancestry', 'output_merger', 'rasterizer'):
            live = copy.deepcopy(prior)
            live[field] = None
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.worker.validate_pipeline(live, prior)

    def test_startup_failure_is_caught_and_capture_rehashed(self):
        with patch.object(self.worker, 'worker_path', side_effect=RuntimeError('startup-failed')), \
            patch.object(self.worker, 'sha_file', return_value=self.worker.CAPTURE_SHA256) as digest, \
            patch('sys.stderr', new_callable=__import__('io').StringIO) as stderr:
            self.assertEqual(self.worker.main(), 1)
        digest.assert_called_with(self.worker.CAPTURE)
        self.assertIn('startup-failed', stderr.getvalue())
        self.assertIn('sha256_after', stderr.getvalue())

    def test_read_only_surface_and_python36_syntax(self):
        source = MODULE.read_text(encoding='utf-8')
        tree = ast.parse(source, feature_version=(3, 6))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertFalse(attrs & {'ReplaceResource', 'RemoveReplacement', 'BuildTargetShader',
            'BuildCustomShader', 'ReplayLog', 'DebugPixel', 'GetPostVSData', 'GetBufferData',
            'ExecuteAndInject', 'CreateTargetControl', 'SaveTexture', 'GetTextureSave'})
        self.assertIn('_exit', attrs)
        self.assertNotIn('numpy', source)

    def make_a0(self, directory, disassembly=False):
        reference = directory / 'reference'
        reference.mkdir(parents=True)
        files, events = [], {}

        def write(name, payload):
            (reference / name).write_bytes(payload)
            record = dict(file=name, byte_size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
            files.append(record)
            return record

        for event in (1426, 1437, 1452):
            cb = write('E{}-Pixel-cb0.bin'.format(event), bytes([event % 256]) * 8)
            evidence = dict(event=event, stages={'Pixel': {'constant_buffers': [dict(raw=cb)]}})
            if disassembly and event == 1452:
                evidence['stages']['Pixel']['disassembly'] = write('E1452-Pixel.dxil.txt', b'; offline audit')
            events[event] = evidence
            write('E{}-pipeline.json'.format(event), json.dumps(evidence).encode('utf-8'))
        manifest = dict(role='offline_reference_only', full_renderer_parity=False,
            capture=dict(path=self.worker.CAPTURE, sha256=self.worker.CAPTURE_SHA256), files=files)
        payload = json.dumps(manifest).encode('utf-8')
        (reference / 'manifest.json').write_bytes(payload)
        result = dict(status='passed', capture=self.worker.CAPTURE,
            sha256_before=self.worker.CAPTURE_SHA256, sha256_after=self.worker.CAPTURE_SHA256,
            capture_unchanged=True, manifest='reference/manifest.json',
            manifest_sha256=hashlib.sha256(payload).hexdigest())
        (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        return events

    def test_a0_reuse_copies_only_verified_event_metadata_and_cbuffers(self):
        self.assertTrue(hasattr(self.worker, 'load_a0_evidence'), 'verified A0 reuse is missing')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            expected_events = self.make_a0(root / 'a0')
            artifacts = self.worker.Artifacts(root / 'reference')
            audit = self.worker.load_a0_evidence(root / 'a0', artifacts)
            self.assertEqual(audit['events'], expected_events)
            self.assertEqual(len(audit['reused_files']), 6)
            for record in audit['reused_files']:
                original = root / 'a0/reference' / record['file']
                self.assertEqual((artifacts.directory / record['file']).read_bytes(), original.read_bytes())

    def test_a0_reuse_accepts_actual_dot_separated_disassembly_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_a0(root / 'a0', disassembly=True)
            artifacts = self.worker.Artifacts(root / 'reference')
            try:
                audit = self.worker.load_a0_evidence(root / 'a0', artifacts)
            except ValueError as error:
                self.fail('Actual A0 disassembly filename rejected: {}'.format(error))
            self.assertEqual(len(audit['reused_files']), 7)
            self.assertEqual((artifacts.directory / 'E1452-Pixel.dxil.txt').read_bytes(), b'; offline audit')

    def test_a0_modified_manifest_or_cbuffer_fails_before_copy(self):
        self.assertTrue(hasattr(self.worker, 'load_a0_evidence'), 'verified A0 reuse is missing')
        for filename in ('manifest.json', 'E1437-Pixel-cb0.bin', 'E1452-pipeline.json'):
            with self.subTest(file=filename), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.make_a0(root / 'a0')
                path = root / 'a0/reference' / filename
                path.write_bytes(path.read_bytes() + b'changed')
                artifacts = self.worker.Artifacts(root / 'reference')
                with self.assertRaises(ValueError): self.worker.load_a0_evidence(root / 'a0', artifacts)
                self.assertEqual(artifacts.files, [])

    def fake_replay(self):
        """Small RenderDoc API boundary fake; all validation/writes remain real."""
        helper = self.worker.load_helpers(MODULE)

        class Format:
            def __init__(self, name): self.name = name
            def Name(self): return self.name

        def native_target(row):
            result = dict(row)
            result['format'] = Format(row['format'])
            return types.SimpleNamespace(**result)

        om = types.SimpleNamespace(renderTargets=[native_target(t) for t in self.targets[:5]],
            depthTarget=native_target(self.targets[5]))
        rasterizer = types.SimpleNamespace(viewports=self.viewports, scissors=self.scissors)
        d3d = types.SimpleNamespace(outputMerger=om, rasterizer=rasterizer,
            pipelineResourceId='ResourceId::40847')
        action = types.SimpleNamespace(eventId=1452, flags=1, children=[],
            GetName=lambda structured: 'MI_ProcGrid SM_Template_Map_Floor (1 instances)')
        textures = [types.SimpleNamespace(resourceId=t['resource'], format=Format(t['format']),
            width=t['width'], height=t['height'], depth=t['depth'], arraysize=t['arraysize'],
            mips=t['mips'], dimension=t['dimension'], msSamp=t['samples']) for t in self.textures.values()]
        resources = [types.SimpleNamespace(resourceId=t['resource'], name=t['name']) for t in self.textures.values()]
        prior = dict(event=1452, pipeline='ResourceId::40847',
            ancestry=[action.GetName(None)], output_merger=helper.simple(om), rasterizer=helper.simple(rasterizer))
        reads, frame_events, shutdown = [], [], []

        def read(rid, sub):
            reads.append((rid, sub.mip, sub.slice, sub.sample))
            row = next(row for row in EXPECTED if row[0] == rid)
            return b'\x81' * (1424 * 1040 * row[-1])

        controller = types.SimpleNamespace(GetTextures=lambda: textures, GetResources=lambda: resources,
            GetRootActions=lambda: [action], GetStructuredFile=lambda: None,
            SetFrameEvent=lambda eid, force: frame_events.append((eid, force)),
            GetD3D12PipelineState=lambda: d3d, GetTextureData=read,
            GetUsage=lambda rid: [types.SimpleNamespace(eventId=1452, usage='ColorTarget')],
            GetAPIProperties=lambda: types.SimpleNamespace(pipelineType='D3D12'),
            Shutdown=lambda: shutdown.append('controller'))
        capture = types.SimpleNamespace(OpenFile=lambda *args: 0,
            OpenCapture=lambda *args: (0, controller), Shutdown=lambda: shutdown.append('capture'))
        rd = types.SimpleNamespace(ResourceId=types.SimpleNamespace(Null=lambda: 'ResourceId::0'),
            ActionFlags=types.SimpleNamespace(Drawcall=1), Subresource=types.SimpleNamespace,
            OpenCaptureFile=lambda: capture, ResultCode=types.SimpleNamespace(Succeeded=0),
            ReplayOptions=types.SimpleNamespace)
        return rd, controller, prior, helper, reads, frame_events, shutdown

    def test_collect_reads_each_exact_output_once_and_preserves_named_usage(self):
        self.assertTrue(hasattr(self.worker, 'collect'), 'read-only collection flow is missing')
        rd, controller, prior, helper, reads, frames, shutdown = self.fake_replay()
        with tempfile.TemporaryDirectory() as temp:
            artifacts = self.worker.Artifacts(Path(temp) / 'reference')
            manifest = self.worker.collect(rd, controller, artifacts, prior, helper)
            self.assertEqual(frames, [(1452, True)])
            self.assertEqual(reads, [(row[0], 0, 0, 0) for row in EXPECTED])
            self.assertEqual(len(manifest['snapshots']), 6)
            for row, snapshot in zip(EXPECTED, manifest['snapshots']):
                self.assertEqual(snapshot['name'], row[1])
                self.assertEqual(snapshot['usages'][0]['ancestry'], prior['ancestry'])
                self.assertEqual(snapshot['usages'][0]['event'], 1452)
                self.assertFalse(snapshot['plane_parity_verified'])

    def test_collect_checks_whole_budget_and_pipeline_before_any_readback(self):
        self.assertTrue(hasattr(self.worker, 'collect'), 'read-only collection flow is missing')
        for failure in ('budget', 'pipeline', 'shape'):
            rd, controller, prior, helper, reads, frames, shutdown = self.fake_replay()
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                artifacts = self.worker.Artifacts(Path(temp) / 'reference')
                if failure == 'budget': artifacts.used = 30 * 1024 * 1024
                elif failure == 'pipeline': prior['pipeline'] = 'wrong'
                else: controller.GetTextures()[0].width = 2048
                with self.assertRaises(ValueError):
                    self.worker.collect(rd, controller, artifacts, prior, helper)
                self.assertEqual(reads, [])

    def test_main_success_and_failure_always_shutdown_rehash_and_never_false_pass(self):
        for failure in (None, 'readback', 'shutdown', 'rehash', 'openfile'):
            rd, controller, prior, helper, reads, frames, shutdown = self.fake_replay()
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                script = root / 'scripts/customrenderpipline' / MODULE.name
                out = root / 'build/targetmap-shading-a1/run'
                if failure == 'readback':
                    controller.GetTextureData = lambda *args: b'short'
                elif failure == 'shutdown':
                    def fail_shutdown():
                        shutdown.append('controller')
                        raise RuntimeError('shutdown failure')
                    controller.Shutdown = fail_shutdown
                elif failure == 'openfile': rd.OpenCaptureFile().OpenFile = lambda *args: 1
                capture_hashes = [self.worker.CAPTURE_SHA256,
                    '0' * 64 if failure == 'rehash' else self.worker.CAPTURE_SHA256]

                def digest(path):
                    return capture_hashes.pop(0) if str(path) == self.worker.CAPTURE else 'a' * 64

                with patch.object(self.worker, 'worker_path', return_value=script), \
                    patch.object(self.worker, 'load_helpers', return_value=helper), \
                    patch.object(self.worker, 'load_a0_evidence', create=True,
                        return_value={'events': {1452: prior}, 'reused_files': []}), \
                    patch.object(self.worker, 'sha_file', side_effect=digest), \
                    patch.dict('sys.modules', {'renderdoc': rd}), \
                    patch.dict('os.environ', {'CRP_TARGETMAP_GBUFFER_OUT': str(out)}):
                    code = self.worker.main()
                result = json.loads((out / 'result.json').read_text())
                self.assertEqual(capture_hashes, [])
                self.assertEqual(shutdown, ['capture'] if failure == 'openfile' else ['controller', 'capture'])
                self.assertEqual(result['status'], 'failed' if failure else 'passed')
                self.assertEqual(code, 1 if failure else 0)
                self.assertEqual((out / 'reference/manifest.json').exists(), not bool(failure))
                if not failure:
                    self.assertEqual(len(result['raw_identities']), 6)
                    total = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
                    self.assertLessEqual(total, self.worker.MAX_BYTES)


if __name__ == '__main__':
    unittest.main()
