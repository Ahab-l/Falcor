"""CPU guard tests for the read-only targetmap reference collector."""
import ast
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name('_targetmap_shading_replay.py')


class CollectorContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'read-only targetmap collector has not been implemented')
        spec = importlib.util.spec_from_file_location('targetmap_worker', MODULE)
        self.worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.worker)
        self.texture = dict(resource='ResourceId::955', format='R16G16B16A16_FLOAT',
                            width=1424, height=1040, depth=1, arraysize=1, mips=1,
                            dimension=2, samples=1)
        self.target = dict(resource='ResourceId::955', firstMip=0, firstSlice=0,
                           numMips=1, numSlices=1, format='R16G16B16A16_FLOAT')
        self.viewport = dict(x=0.0, y=0.0, width=1421.0, height=1035.0,
                             minDepth=0.0, maxDepth=1.0, enabled=True)
        self.scissor = dict(x=0, y=0, width=1421, height=1035, enabled=True)

    def check(self, event=2793, size=11847680):
        return self.worker.validate_snapshot(event, self.texture, self.target,
                                             self.viewport, self.scissor, size)

    def test_pinned_valid_snapshots(self):
        for event in (2793, 2962):
            self.assertEqual(self.check(event)['view_rect'], [0, 0, 1421, 1035])

    def test_unapproved_event_rejected(self):
        with self.assertRaises(ValueError): self.check(3125)

    def test_wrong_resource_rejected(self):
        self.target['resource'] = 'ResourceId::967'
        with self.assertRaises(ValueError): self.check()

    def test_approximate_format_rejected(self):
        self.texture['format'] = 'R11G11B10_FLOAT'
        with self.assertRaises(ValueError): self.check()

    def test_wrong_byte_size_rejected(self):
        for size in (11847679, 11847681):
            with self.assertRaises(ValueError): self.check(size=size)

    def test_subresource_and_msaa_rejected(self):
        for key in ('firstMip', 'firstSlice'):
            original = copy.deepcopy(self.target)
            self.target[key] = 1
            with self.assertRaises(ValueError): self.check()
            self.target = original
        self.texture['samples'] = 4
        with self.assertRaises(ValueError): self.check()

    def test_fractional_or_different_viewport_rejected(self):
        for x in (0.5, 1, float('nan')):
            self.viewport['x'] = x
            with self.assertRaises(ValueError): self.check()

    def test_wrong_scissor_or_depth_range_rejected(self):
        self.scissor['width'] = 1424
        with self.assertRaises(ValueError): self.check()
        self.scissor['width'] = 1421
        self.viewport['maxDepth'] = 0.5
        with self.assertRaises(ValueError): self.check()

    def test_capture_identity_pinned(self):
        self.worker.validate_capture('E:/rdc/ue/2.rdc', self.worker.CAPTURE_SHA256)
        for path, digest in [('E:/rdc/ue/1.rdc', self.worker.CAPTURE_SHA256),
                             ('E:/rdc/ue/2.rdc', '0' * 64)]:
            with self.assertRaises(ValueError): self.worker.validate_capture(path, digest)

    def test_artifact_budget_checked_before_write(self):
        self.worker.validate_budget(0, 11847680)
        for before, add in [(64 * 1024 * 1024, 1), (0, -1)]:
            with self.assertRaises(ValueError): self.worker.validate_budget(before, add)

    def test_embedded_runner_without_dunder_file(self):
        del self.worker.__file__
        with patch.dict('os.environ', {'CRP_TARGETMAP_REFERENCE_SCRIPT': str(MODULE)}):
            self.assertEqual(self.worker.worker_path(), MODULE.resolve())

    def test_no_shader_replacement_or_render_inputs_exported(self):
        tree = ast.parse(MODULE.read_text(encoding='utf-8'))
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        forbidden = {'ReplaceResource', 'RemoveReplacement', 'BuildTargetShader',
                     'BuildCustomShader', 'ReplayLog', 'DebugPixel', 'GetPostVSData',
                     'ExecuteAndInject', 'CreateTargetControl', 'SaveTexture'}
        self.assertFalse(attrs & forbidden)
        self.assertFalse(any(isinstance(n, (ast.Import, ast.ImportFrom)) and
                             'falcor' in ast.unparse(n).lower() for n in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
