"""CPU-only tests for pinned raw BC1 reference collection and byte comparison."""
import ast
import copy
from enum import IntEnum
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SIZES = [131072, 32768, 8192, 2048, 512, 128, 32, 8, 8, 8]


def module(name):
    path = HERE / (name + '.py')
    if not path.is_file():
        raise AssertionError('Missing implementation: ' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def pipeline_fixture():
    binding = dict(access=dict(index=5, stage=4, arrayElement=0, staticallyUnused=False,
        byteOffset=330645, byteSize=1, descriptorStore='ResourceId::309', type=4),
        descriptor=dict(resource='ResourceId::3905', firstMip=0, numMips=10, firstSlice=0,
            numSlices=1, elementByteSize=8, minLODClamp=0.0), view_format='BC1_SRGB',
        identity=dict(resource='ResourceId::3905', name='2D Texture 3905', texture=dict(
            width=512, height=512, depth=1, arraysize=1, mips=10, format='BC1_TYPELESS', samples=1, dimension=2)))
    return dict(event=1452, pipeline='ResourceId::40847', ancestry=['BasePass',
        'MI_ProcGrid SM_Template_Map_Floor (1 instances)', 'DrawIndexedInstanced'],
        rasterizer={}, output_merger={}, stages={'Pixel': dict(shader='ResourceId::40849',
            entry_point='MainPS', read_only=[binding])})


class TextureReferenceTests(unittest.TestCase):
    def setUp(self):
        self.worker = module('_targetmap_texture_replay')

    def test_identity_comes_from_actual_pixel_t5_not_array_position(self):
        prior = pipeline_fixture()
        prior['stages']['Pixel']['read_only'].insert(0, dict(access=dict(index=1)))
        binding = self.worker.select_binding(prior)
        self.assertEqual(binding['identity']['resource'], 'ResourceId::3905')
        self.assertEqual(binding['view_format'], 'BC1_SRGB')

    def test_binding_identity_shape_and_subresource_drift_fail_closed(self):
        for section, key, bad in [('access', 'index', 4), ('access', 'arrayElement', 1),
            ('access', 'staticallyUnused', True), ('access', 'stage', 0),
            ('descriptor', 'resource', 'ResourceId::3906'), ('descriptor', 'firstMip', 1),
            ('descriptor', 'numMips', 9), ('descriptor', 'numSlices', 2),
            ('descriptor', 'elementByteSize', 4), ('descriptor', 'minLODClamp', 1),
            ('identity', 'name', 'GuessedTexture')]:
            prior = pipeline_fixture()
            prior['stages']['Pixel']['read_only'][0][section][key] = bad
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                self.worker.select_binding(prior)
        for key, bad in [('format', 'BC1_UNORM'), ('width', 256), ('height', 256),
                         ('depth', 2), ('arraysize', 2), ('mips', 9), ('samples', 4), ('dimension', 3)]:
            prior = pipeline_fixture()
            prior['stages']['Pixel']['read_only'][0]['identity']['texture'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.worker.select_binding(prior)
        for field, bad in [('event', True), ('event', 1437), ('pipeline', 'ResourceId::1')]:
            prior = pipeline_fixture(); prior[field] = bad
            with self.assertRaises(ValueError): self.worker.select_binding(prior)
        prior = pipeline_fixture(); prior['stages']['Pixel']['read_only'] *= 2
        with self.assertRaises(ValueError): self.worker.select_binding(prior)

    def test_block_layout_has_ten_mips_including_sub_4x4_block_minimum(self):
        plans = self.worker.mip_layout()
        self.assertEqual([p['byte_size'] for p in plans], SIZES)
        self.assertEqual(sum(SIZES), 174776)
        self.assertEqual([p['width'] for p in plans], [512,256,128,64,32,16,8,4,2,1])
        self.assertEqual([p['row_pitch'] for p in plans][-4:], [16,8,8,8])
        self.assertEqual(plans[-1]['offset'], 174768)
        self.assertEqual([p['mip'] for p in plans], list(range(10)))

    def test_payload_is_exact_unchanged_bc1_bytes_without_padding_or_decode(self):
        with tempfile.TemporaryDirectory() as temp:
            artifacts = self.worker.Artifacts(Path(temp) / 'reference')
            plan = self.worker.mip_layout()[-1]
            raw = b'\x00\xf8\xe0\x07\x55\xaa\xff\x00'
            record = self.worker.save_mip(artifacts, plan, raw)
            self.assertEqual((artifacts.directory / record['file']).read_bytes(), raw)
            self.assertEqual(record['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertTrue(record['readback_length_verified'])
            self.assertEqual(record['role'], 'offline_reference_only')
            self.assertFalse(record['full_renderer_parity'])
        for length in (0, 4, 7, 9, 16, 256):
            with self.subTest(length=length), tempfile.TemporaryDirectory() as temp:
                artifacts = self.worker.Artifacts(Path(temp) / 'reference')
                with self.assertRaises(ValueError):
                    self.worker.save_mip(artifacts, plan, bytes(length))
                self.assertEqual(artifacts.files, [])

    def test_budget_fresh_output_and_no_file_embedded_bootstrap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / 'build/targetmap-shading-a1'
            for bad in (root, base, root / 'build/targetmap-shading-a10/run'):
                with self.assertRaises(ValueError): self.worker.prepare_output(root, bad)
            out = self.worker.prepare_output(root, base / 'fresh')
            with self.assertRaises(FileExistsError): self.worker.prepare_output(root, out)
            artifacts = self.worker.Artifacts(out / 'reference')
            for name in ('../bad', 'x/y', 'x\\y', 'x:y'):
                with self.assertRaises(ValueError): artifacts.raw(name, b'bad')
            artifacts.used = self.worker.MAX_BYTES - self.worker.RESULT_RESERVE
            with self.assertRaises(ValueError): artifacts.raw('too-large', b'x')
            self.assertEqual(list(artifacts.directory.iterdir()), [])
        del self.worker.__file__
        with patch.dict(os.environ, {'CRP_TARGETMAP_TEXTURE_SCRIPT': str(HERE / '_targetmap_texture_replay.py')}):
            self.assertEqual(self.worker.worker_path(), (HERE / '_targetmap_texture_replay.py').resolve())
            self.assertTrue(callable(self.worker.load_helpers(self.worker.worker_path()).simple))

    def test_read_only_surface_and_python36_syntax(self):
        source = (HERE / '_targetmap_texture_replay.py').read_text(encoding='utf-8')
        tree = ast.parse(source, feature_version=(3, 6))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertFalse(attrs & {'ReplaceResource', 'RemoveReplacement', 'BuildTargetShader',
            'BuildCustomShader', 'GetBufferData', 'GetPostVSData', 'DebugPixel', 'SaveTexture', 'ReplayLog'})
        self.assertIn('GetTextureData', attrs)
        self.assertIn('_exit', attrs)
        self.assertNotIn('numpy', source)
        self.assertNotIn('make_dds', source)

    def make_a0(self, directory):
        reference = directory / 'reference'; reference.mkdir(parents=True)
        prior = pipeline_fixture()
        code = b'Texture2D<float4> Texture2D5 : register(t5, space0);\n'
        files = []
        for name, raw in [('E1452-pipeline.json', json.dumps(prior).encode()), ('E1452-Pixel.dxil.txt', code)]:
            (reference / name).write_bytes(raw)
            files.append(dict(file=name, byte_size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        manifest = dict(capture=dict(path=self.worker.CAPTURE, sha256=self.worker.CAPTURE_SHA256),
                        role='offline_reference_only', full_renderer_parity=False, files=files)
        raw = json.dumps(manifest).encode(); (reference / 'manifest.json').write_bytes(raw)
        result = dict(status='passed', capture=self.worker.CAPTURE, capture_unchanged=True,
                      sha256_before=self.worker.CAPTURE_SHA256, sha256_after=self.worker.CAPTURE_SHA256,
                      manifest='reference/manifest.json', manifest_sha256=hashlib.sha256(raw).hexdigest())
        (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        return prior

    def test_a0_reads_only_verified_pipeline_and_t5_shader_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); prior = self.make_a0(root / 'a0')
            artifacts = self.worker.Artifacts(root / 'reference')
            audit = self.worker.load_a0_evidence(root / 'a0', artifacts)
            self.assertEqual(audit['pipeline'], prior)
            self.assertEqual([f['file'] for f in artifacts.files], ['E1452-pipeline.json', 'E1452-Pixel.dxil.txt'])
        for filename in ('manifest.json', 'E1452-pipeline.json', 'E1452-Pixel.dxil.txt'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self.make_a0(root / 'a0')
                path = root / 'a0/reference' / filename; path.write_bytes(path.read_bytes() + b'tamper')
                artifacts = self.worker.Artifacts(root / 'reference')
                with self.assertRaises(ValueError): self.worker.load_a0_evidence(root / 'a0', artifacts)
                self.assertEqual(artifacts.files, [])

    def fake_replay(self):
        prior = pipeline_fixture(); helper = self.worker.load_helpers(HERE / '_targetmap_texture_replay.py')
        binding = prior['stages']['Pixel']['read_only'][0]
        class Format:
            def __init__(self, name): self.name = name
            def Name(self): return self.name
        descriptor = types.SimpleNamespace(**dict(binding['descriptor'], format=Format('BC1_SRGB')))
        used = types.SimpleNamespace(access=types.SimpleNamespace(**binding['access']), descriptor=descriptor)
        texture = types.SimpleNamespace(resourceId='ResourceId::3905', width=512, height=512, depth=1,
            arraysize=1, mips=10, dimension=2, msSamp=1, format=Format('BC1_TYPELESS'))
        pipeline = types.SimpleNamespace(GetReadOnlyResources=lambda stage: [used],
            GetShaderReflection=lambda stage: types.SimpleNamespace(resourceId='ResourceId::40849', entryPoint='MainPS'))
        names = prior['ancestry']
        action = None
        for index in reversed(range(len(names))):
            action = types.SimpleNamespace(eventId=1452 if index == len(names)-1 else index+1,
                flags=1, children=[] if action is None else [action], GetName=lambda _, name=names[index]: name)
        reads, frames, shutdown = [], [], []
        def read(resource, sub):
            reads.append((resource, sub.mip, sub.slice, sub.sample))
            return bytes([sub.mip]) * SIZES[sub.mip]
        controller = types.SimpleNamespace(GetTextures=lambda: [texture],
            GetResources=lambda: [types.SimpleNamespace(resourceId='ResourceId::3905', name='2D Texture 3905')],
            GetRootActions=lambda: [action], GetStructuredFile=lambda: None,
            SetFrameEvent=lambda event, force: frames.append((event, force)),
            GetPipelineState=lambda: pipeline,
            GetD3D12PipelineState=lambda: types.SimpleNamespace(pipelineResourceId='ResourceId::40847', rasterizer={}, outputMerger={}),
            GetTextureData=read, GetAPIProperties=lambda: types.SimpleNamespace(pipelineType=3),
            Shutdown=lambda: shutdown.append('controller'))
        capture = types.SimpleNamespace(OpenFile=lambda *args: 0, OpenCapture=lambda *args: (0, controller),
                                        Shutdown=lambda: shutdown.append('capture'))
        rd = types.SimpleNamespace(ActionFlags=types.SimpleNamespace(Drawcall=1),
            ShaderStage=types.SimpleNamespace(Pixel=4), GraphicsAPI=types.SimpleNamespace(D3D12=3),
            Subresource=types.SimpleNamespace, ReplayOptions=types.SimpleNamespace,
            OpenCaptureFile=lambda: capture, ResultCode=types.SimpleNamespace(Succeeded=0))
        return rd, controller, prior, helper, reads, frames, shutdown

    def test_collect_reads_only_pinned_t5_ten_times_and_counts_exact_bytes(self):
        rd, controller, prior, helper, reads, frames, shutdown = self.fake_replay()
        with tempfile.TemporaryDirectory() as temp:
            artifacts = self.worker.Artifacts(Path(temp) / 'reference')
            manifest = self.worker.collect(rd, controller, artifacts, prior, helper)
            self.assertEqual(reads, [('ResourceId::3905', mip, 0, 0) for mip in range(10)])
            self.assertEqual(frames, [(1452, True)])
            self.assertEqual(manifest['raw_bytes'], 174776)
            self.assertEqual(len(manifest['mips']), 10)
            self.assertFalse(manifest['full_renderer_parity'])
            self.assertFalse(manifest['source_binary_identity_verified'])

    def test_live_pixel_enum_survives_helper_but_is_normalized_at_native_boundary(self):
        # The real failure shape: helper.simple returns an int-subclass unchanged,
        # whereas persisted A0 JSON deserializes to an ordinary built-in int.
        class ShaderStage(IntEnum):
            Vertex = 0
            Pixel = 4
        rd, controller, prior, helper, reads, frames, shutdown = self.fake_replay()
        rd.ShaderStage = ShaderStage
        access = controller.GetPipelineState().GetReadOnlyResources(ShaderStage.Pixel)[0].access
        access.stage = ShaderStage.Pixel
        self.assertIs(type(helper.simple(access)['stage']), ShaderStage)
        self.assertIs(type(prior['stages']['Pixel']['read_only'][0]['access']['stage']), int)
        with tempfile.TemporaryDirectory() as temp:
            artifacts = self.worker.Artifacts(Path(temp) / 'reference')
            try:
                manifest = self.worker.collect(rd, controller, artifacts, prior, helper)
            except ValueError as error:
                self.fail('Actual Pixel int-enum must be accepted at the live boundary: ' + str(error))
            self.assertEqual(manifest['raw_bytes'], 174776)
            self.assertEqual(len(reads), 10)
            live = json.loads((artifacts.directory / 'E1452-live-t5.json').read_text())
            self.assertIs(type(live['binding']['access']['stage']), int)
            self.assertEqual(live['binding']['access']['stage'], 4)

    def test_live_stage_normalization_never_accepts_nonpixel_or_coerces_bad_types(self):
        class ShaderStage(IntEnum):
            Vertex = 0
            Pixel = 4
            Compute = 5
        for wrong in (ShaderStage.Vertex, ShaderStage.Compute, '4', 4.0, True, None):
            rd, controller, prior, helper, reads, frames, shutdown = self.fake_replay()
            rd.ShaderStage = ShaderStage
            controller.GetPipelineState().GetReadOnlyResources(ShaderStage.Pixel)[0].access.stage = wrong
            with self.subTest(stage=repr(wrong)), tempfile.TemporaryDirectory() as temp:
                artifacts = self.worker.Artifacts(Path(temp) / 'reference')
                with self.assertRaises(ValueError):
                    self.worker.collect(rd, controller, artifacts, prior, helper)
                self.assertEqual(reads, [])

    def test_collect_rejects_live_drift_and_budget_before_any_readback(self):
        for failure in ('pipeline', 'shape', 'view', 'budget', 'shader', 'api'):
            rd, controller, prior, helper, reads, frames, shutdown = self.fake_replay()
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                artifacts = self.worker.Artifacts(Path(temp) / 'reference')
                if failure == 'pipeline': prior['pipeline'] = 'wrong'
                elif failure == 'shape': controller.GetTextures()[0].width = 1024
                elif failure == 'view': controller.GetPipelineState().GetReadOnlyResources(4)[0].descriptor.numMips = 9
                elif failure == 'budget': artifacts.used = self.worker.MAX_BYTES - self.worker.RESULT_RESERVE
                elif failure == 'shader': prior['stages']['Pixel']['shader'] = 'wrong'
                else: controller.GetAPIProperties = lambda: types.SimpleNamespace(pipelineType=2)
                with self.assertRaises(ValueError): self.worker.collect(rd, controller, artifacts, prior, helper)
                self.assertEqual(reads, [])

    def test_main_shutdown_rehash_and_exit_status_are_fail_closed(self):
        for failure in (None, 'readback', 'shutdown', 'rehash', 'openfile'):
            rd, controller, prior, helper, reads, frames, shutdown = self.fake_replay()
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); script = root / 'scripts/customrenderpipline/_targetmap_texture_replay.py'
                out = root / 'build/targetmap-shading-a1/fresh'
                if failure == 'readback': controller.GetTextureData = lambda *args: b'short'
                elif failure == 'shutdown':
                    def bad_shutdown():
                        shutdown.append('controller'); raise RuntimeError('shutdown failed')
                    controller.Shutdown = bad_shutdown
                elif failure == 'openfile': rd.OpenCaptureFile().OpenFile = lambda *args: 1
                hashes = [self.worker.CAPTURE_SHA256, '0'*64 if failure == 'rehash' else self.worker.CAPTURE_SHA256]
                def digest(path):
                    return hashes.pop(0) if str(path) == self.worker.CAPTURE else 'a'*64
                with patch.object(self.worker, 'worker_path', return_value=script), \
                     patch.object(self.worker, 'load_helpers', return_value=helper), \
                     patch.object(self.worker, 'load_a0_evidence', return_value={'pipeline':prior}), \
                     patch.object(self.worker, 'sha_file', side_effect=digest), \
                     patch.dict(sys.modules, {'renderdoc': rd}), \
                     patch.dict(os.environ, {'CRP_TARGETMAP_TEXTURE_OUT': str(out)}):
                    code = self.worker.main()
                result = json.loads((out / 'result.json').read_text())
                self.assertEqual(hashes, [])
                self.assertEqual(shutdown, ['capture'] if failure == 'openfile' else ['controller', 'capture'])
                self.assertEqual(code, 1 if failure else 0)
                self.assertEqual(result['status'], 'failed' if failure else 'passed')
                self.assertEqual((out / 'reference/manifest.json').exists(), failure is None)

    def test_startup_error_is_caught_and_capture_rehashed(self):
        with patch.object(self.worker, 'worker_path', side_effect=RuntimeError('bootstrap failed')), \
             patch.object(self.worker, 'sha_file', return_value=self.worker.CAPTURE_SHA256) as digest, \
             patch('sys.stderr', new_callable=io.StringIO) as stderr:
            self.assertEqual(self.worker.main(), 1)
        digest.assert_called_with(self.worker.CAPTURE)
        self.assertIn('bootstrap failed', stderr.getvalue())


class TextureComparatorTests(unittest.TestCase):
    def setUp(self):
        self.compare = module('targetmap_texture_compare')

    def test_exact_block_comparison_and_mip_boundaries(self):
        raw = bytes(i % 251 for i in range(174776))
        result = self.compare.compare_payloads(raw, raw)
        self.assertTrue(result['all_mips_equal'])
        self.assertEqual(len(result['mips']), 10)
        self.assertEqual(result['differing_bytes'], 0)
        self.assertFalse(result['full_renderer_parity'])
        changed = bytearray(raw); changed[131072] ^= 3; changed[-1] ^= 1
        result = self.compare.compare_payloads(raw, changed)
        self.assertFalse(result['all_mips_equal'])
        self.assertEqual(result['differing_bytes'], 2)
        self.assertEqual(result['mips'][1]['first_difference'], dict(mip_offset=0, payload_offset=131072,
            block_index=0, block_x=0, block_y=0, byte_in_block=0, source_byte=raw[131072], reference_byte=changed[131072]))
        self.assertEqual(result['mips'][9]['first_difference']['byte_in_block'], 7)
        self.assertEqual(result['mips'][0]['differing_bytes'], 0)
        for malformed in (raw[:-1], raw+b'x', bytes(512*512*4)):
            with self.assertRaises(ValueError): self.compare.compare_payloads(raw, malformed)

    def test_no_dds_or_decoder_or_renderer_output_is_produced(self):
        source = (HERE / 'targetmap_texture_compare.py').read_text(encoding='utf-8')
        ast.parse(source)
        for banned in ('import renderdoc', 'import falcor', 'import numpy', '.createPass(', '.make_dds('):
            self.assertNotIn(banned, source)
        self.assertIn('load_verified_export', source)

    def make_source(self, root, raw):
        platform = module('source_platform_texture')
        worker = self.compare.reference
        run = root / 'build/source-platform-texture/source-fixture'
        out = run / 'Export'; out.mkdir(parents=True)
        metadata = dict(status='passed', capture_inputs=False, source_object=platform.OBJECT,
            format='BC1UnormSrgb', srgb=True, width=512, height=512, payload='platform-mips.bin',
            mips=[dict(level=p['mip'], width=p['width'], height=p['height'], bytes=p['byte_size'], offset=p['offset'])
                  for p in worker.mip_layout()])
        def identity(path):
            data = path.read_bytes()
            return dict(path=str(path.resolve()), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        for name, payload in [('result.json', json.dumps(metadata).encode()), ('platform-mips.bin', raw),
                              ('T_GridChecker_A.bc1.srgb.dds', platform.make_dds(metadata, raw))]:
            (out / name).write_bytes(payload)
        original = run / 'original.fixture'; original.write_bytes(b'Independent source fixture, no capture inputs')
        protected = [identity(original)]
        (run / 'prepared.json').write_text(json.dumps(dict(protected=protected, capture_inputs=False, original_project_launched=False)))
        protection = run / 'protected-after.json'
        protection.write_text(json.dumps(dict(unchanged=True, files=protected)))
        record = dict(status='passed', capture_inputs=False, original_project_launched=False,
            protected_unchanged=True, protected=protected, protection_report=str(protection.resolve()),
            metadata=identity(out / 'result.json'), payload=identity(out / 'platform-mips.bin'),
            texture=identity(out / 'T_GridChecker_A.bc1.srgb.dds'), receipts=[dict(exit_code=0)])
        (run / 'source-platform-result.json').write_text(json.dumps(record))
        return run

    def make_reference(self, root):
        context = TextureReferenceTests(); context.worker = self.compare.reference
        worker = context.worker
        rd, controller, prior, helper, reads, frames, shutdown = context.fake_replay()
        run = root / 'build/targetmap-shading-a1/texture-fixture'; run.mkdir(parents=True)
        artifacts = worker.Artifacts(run / 'reference')
        artifacts.json('E1452-pipeline.json', prior)
        artifacts.raw('E1452-Pixel.dxil.txt', b'Texture2D<float4> Texture2D5 : register(t5, space0);\n')
        manifest = worker.collect(rd, controller, artifacts, prior, helper)
        manifest['files'] = list(artifacts.files)
        record = artifacts.json('manifest.json', manifest)
        result = dict(status='passed', role=worker.ROLE, full_renderer_parity=False, errors=[],
            capture=worker.CAPTURE, sha256_before=worker.CAPTURE_SHA256, sha256_after=worker.CAPTURE_SHA256,
            capture_unchanged=True, controller_shutdown=True, capture_shutdown=True,
            manifest='reference/manifest.json', manifest_sha256=record['sha256'], raw_bytes=174776,
            resource=worker.RESOURCE, mip_count=10)
        (run / 'result.json').write_text(json.dumps(result))
        return run

    def test_verified_source_and_reference_end_to_end_do_not_change_any_inputs(self):
        raw = b''.join(bytes([mip]) * size for mip, size in enumerate(SIZES))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_source(root, raw); oracle = self.make_reference(root)
            before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            result = self.compare.compare_runs(root, source, oracle)
            self.assertTrue(result['all_mips_equal'])
            self.assertFalse(result['source_capture_inputs'])
            self.assertTrue(result['source_identities'])
            self.assertTrue(result['reference_identities'])
            after = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            with self.assertRaises(ValueError): self.compare.compare_runs(root, oracle, source)

    def test_verified_different_source_is_reported_not_normalized(self):
        raw = bytearray(b''.join(bytes([mip]) * size for mip, size in enumerate(SIZES))); raw[-1] ^= 1
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self.compare.compare_runs(root, self.make_source(root, raw), self.make_reference(root))
            self.assertEqual(result['status'], 'different')
            self.assertEqual(result['differing_bytes'], 1)
            self.assertEqual(result['mips'][9]['first_difference']['payload_offset'], 174775)

    def test_missing_tampered_or_decoded_payloads_are_rejected(self):
        raw = b''.join(bytes([mip]) * size for mip, size in enumerate(SIZES))
        for surface, name in [('source', 'Export/platform-mips.bin'), ('source', 'Export/T_GridChecker_A.bc1.srgb.dds'),
            ('reference', 'reference/E1452-t5-3905-mip09.bc1.raw'), ('reference', 'reference/manifest.json')]:
            with self.subTest(surface=surface, name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); source = self.make_source(root, raw); oracle = self.make_reference(root)
                path = (source if surface == 'source' else oracle) / name
                path.write_bytes(path.read_bytes() + b'tampered')
                with self.assertRaises(ValueError): self.compare.compare_runs(root, source, oracle)

    def test_coherently_rehashed_wrong_texture_shape_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); oracle = self.make_reference(root)
            path = oracle / 'reference/manifest.json'
            manifest = json.loads(path.read_text()); manifest['texture']['width'] = 1024
            payload = json.dumps(manifest).encode(); path.write_bytes(payload)
            result_path = oracle / 'result.json'; result = json.loads(result_path.read_text())
            result['manifest_sha256'] = hashlib.sha256(payload).hexdigest(); result_path.write_text(json.dumps(result))
            with self.assertRaises(ValueError): self.compare.load_reference(oracle)

    def test_receipt_with_recorded_errors_cannot_be_a_passed_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            oracle = self.make_reference(Path(temp)); path = oracle / 'result.json'
            result = json.loads(path.read_text()); result['errors'] = ['shutdown failed']
            path.write_text(json.dumps(result))
            with self.assertRaises(ValueError): self.compare.load_reference(oracle)

    def test_cli_emits_json_only_and_exit_codes_distinguish_difference_from_invalid(self):
        raw = b''.join(bytes([mip]) * size for mip, size in enumerate(SIZES))
        for state, expected in [('equal', 0), ('different', 2), ('invalid', 1)]:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); source = self.make_source(root, raw if state != 'different' else raw[:-1]+b'!')
                oracle = self.make_reference(root)
                if state == 'invalid': (source / 'Export/platform-mips.bin').write_bytes(b'invalid')
                out = root / 'build/targetmap-shading-a1/comparison.json'
                arguments = ['--source-run', str(source), '--reference-run', str(oracle), '--out', str(out)]
                with patch.object(self.compare, 'ROOT', root), patch('sys.stdout', new_callable=io.StringIO):
                    self.assertEqual(self.compare.main(arguments), expected)
                    with self.assertRaises(ValueError): self.compare.main(arguments)
                self.assertEqual(json.loads(out.read_text())['status'], state if state != 'invalid' else 'failed')


if __name__ == '__main__':
    unittest.main()
