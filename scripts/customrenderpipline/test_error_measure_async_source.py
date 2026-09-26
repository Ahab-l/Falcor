"""Structural guardrails only; native_error_measure_async_smoke.py validates GPU behavior."""
from pathlib import Path
import ast
import json
import re
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
CPP = (ROOT / 'Source/RenderPasses/ErrorMeasurePass/ErrorMeasurePass.cpp').read_text()
HEADER = (ROOT / 'Source/RenderPasses/ErrorMeasurePass/ErrorMeasurePass.h').read_text()


class ErrorMeasureAsyncSourceTests(unittest.TestCase):
    def test_reduction_never_requests_a_cpu_result(self):
        self.assertNotRegex(CPP, r'ParallelReduction::Type::Sum\s*,\s*&')
        self.assertRegex(CPP, r'execute<float4>\([\s\S]*?ParallelReduction::Type::Sum,\s*nullptr,\s*mpReductionResult')

    def test_collection_is_nonblocking_and_admission_precedes_dispatch(self):
        body = CPP.split('void ErrorMeasurePass::runReductionPasses(', 1)[1].split('\nvoid ', 1)[0]
        self.assertIn('mPendingMeasurements.size() >= kMaxPendingMeasurements', body)
        self.assertLess(body.index('mPendingMeasurements.size() >= kMaxPendingMeasurements'), body.index('mpParallelReduction->execute'))
        self.assertIn('asyncReadBuffer', body)
        self.assertIn('getDataNonBlocking()', CPP)
        self.assertIn('isReady()', CPP)
        self.assertNotRegex(CPP, r'\b(?:wait|waitForGpu|flush|map|getData)\s*\(')
        self.assertRegex(HEADER, r'kMaxPendingMeasurements\s*=\s*4\s*;')

    def test_sample_captures_submission_identity_and_normalizes_frozen_extent(self):
        for field in ('submittedFrame', 'submittedTime', 'width', 'height', 'generation', 'squaredDifference', 'computeAverage', 'ignoreBackground', 'runningErrorSigma'):
            self.assertIn(field, HEADER)
        self.assertIn('sample.width', CPP)
        self.assertIn('sample.height', CPP)
        self.assertIn('sample.submittedFrame', CPP)
        self.assertIn('sample.submittedTime', CPP)

    def test_invalidation_keeps_pending_budget_charged_and_scene_hook_exists(self):
        self.assertIn('void ErrorMeasurePass::invalidateMeasurements()', CPP)
        body = CPP.split('void ErrorMeasurePass::invalidateMeasurements()', 1)[1].split('\nvoid ', 1)[0]
        self.assertIn('++mMeasurementGeneration', body)
        self.assertNotIn('mPendingMeasurements.clear()', body)
        self.assertIn('sample.generation != mMeasurementGeneration', CPP)
        self.assertIn('ErrorMeasurePass::setScene', CPP)

    def test_ordinary_scene_updates_do_not_cancel_all_pending_statistics(self):
        if 'void ErrorMeasurePass::onSceneUpdates(' in CPP:
            body = CPP.split('void ErrorMeasurePass::onSceneUpdates(', 1)[1].split('\nvoid ', 1)[0]
            self.assertNotIn('invalidateMeasurements()', body)

    def test_upstream_refresh_does_not_cancel_frozen_samples(self):
        body = CPP.split('void ErrorMeasurePass::execute(', 1)[1].split('\nvoid ', 1)[0]
        self.assertNotIn('kRenderPassRefreshFlags', body)

    def test_csv_is_written_only_for_new_completion_and_diagnostics_are_readonly(self):
        execute = CPP.split('void ErrorMeasurePass::execute(', 1)[1].split('\nvoid ', 1)[0]
        self.assertNotIn('saveMeasurementsToFile()', execute)
        self.assertIn('saveMeasurementsToFile()', CPP.split('void ErrorMeasurePass::collectMeasurements()', 1)[1].split('\nvoid ', 1)[0])
        self.assertIn('schema_version', CPP)
        self.assertIn('skipped_samples', CPP)
        self.assertIn('def_property_readonly("statistics"', CPP)

    def test_mogwai_smoke_failure_requests_nonzero_shutdown(self):
        for name in ('native_error_measure_async_smoke.py', 'native_async_pool_budget_smoke.py'):
            with self.subTest(script=name), tempfile.TemporaryDirectory() as directory:
                source = ROOT / 'scripts/customrenderpipline' / name
                tree = ast.parse(source.read_text(encoding='utf-8'))
                start = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.Try))
                tail = ast.Module(body=tree.body[start:], type_ignores=[])
                calls = []

                def fail():
                    raise ValueError('injected acceptance failure')

                scope = {'run': fail, 'm': object(), 'OUT': Path(directory), 'json': json,
                         'traceback': SimpleNamespace(print_exc=lambda: None),
                         'print': lambda *args, **kwargs: None, 'exit': lambda code=0: calls.append(code)}
                exec(compile(tail, str(source), 'exec'), scope)
                self.assertEqual(calls, [1])
                self.assertEqual(json.loads((Path(directory) / 'result.json').read_text())['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
