"""Real GPU ErrorMeasurePass regression. Run with Mogwai --headless --script.

The description-based generator is D3D12-only. Vulkan coverage uses the native
ErrorMeasureAsyncTests.cpp fixture, not a unsupported generator substitution.
The synchronous output reads below are test oracles, never pass implementation.
Frame identity is explicitly pass-local execute ordinal, NOT the host clock.
"""
import copy
import csv
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts/customrenderpipline'), str(ROOT / 'build/m0-evidence/python')]
import falcor
import numpy as np

PARENT = ROOT / 'build/native-framework-completion'
PARENT.mkdir(parents=True, exist_ok=True)
OUT = Path(tempfile.mkdtemp(prefix='error-measure-async-', dir=PARENT))
print('ERROR_MEASURE_ASYNC_EVIDENCE ' + str(OUT), flush=True)


def run():
    backend = os.environ.get('CRP_ASYNC_BACKEND', 'D3D12')
    if backend != 'D3D12':
        raise ValueError('This fixture requires D3D12; use ErrorMeasureAsyncTests for native Vulkan coverage')
    testbed = falcor.Testbed(create_window=False, width=17, height=9,
        device_type=getattr(falcor.DeviceType, backend), enable_debug_layers=True)
    testbed.show_ui = False
    source_path = OUT / 'ErrorMeasureInput.slang'
    source_path.write_text('''RWTexture2D<float4> source;
RWTexture2D<float4> reference;
RWTexture2D<float4> worldPosition;
cbuffer Params { uint2 extent; float bias; uint work; };
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
    if (any(p.xy >= extent)) return;
    float3 r = float3(.25, .5, .75);
    float3 d = float3(bias + float(p.x % 4)*.125, -.5, 1.);
    // Dynamic work is preserved in alpha, which ErrorMeasure deliberately ignores.
    uint state = p.x + p.y*extent.x;
    for (uint i=0; i<work; ++i) state = (state * 1664525u + 1013904223u) ^ (state >> 11);
    source[p.xy] = float4(r+d, float(state & 65535u));
    reference[p.xy] = float4(r, 1.);
    worldPosition[p.xy] = float4(0.,0.,0., (p.x+p.y)%3 != 0 ? 1. : 0.);
}
''', encoding='utf-8')
    source_props = {
        'shader': {'file': str(source_path)},
        'resources': [{'name': name, 'binding': name, 'direction': 'output', 'format': 'RGBA32Float'}
                      for name in ('source', 'reference', 'worldPosition')],
        'uniforms': {'Params.extent': {'type': 'uint2', 'source': 'extent'},
                     'Params.bias': {'type': 'float', 'value': .25},
                     'Params.work': {'type': 'uint', 'value': 0}},
        'dispatch': {'extent': 'source'},
    }
    csv_path = OUT / 'measurements-mse.csv'
    options = {'IgnoreBackground': True, 'ComputeSquaredDifference': True,
               'ComputeAverage': False, 'ReportRunningError': False,
               'SelectedOutputId': 'Difference', 'MeasurementsFilePath': str(csv_path)}
    graph = testbed.create_render_graph('NativeErrorMeasureAsync')
    graph.create_pass('Generate', 'CustomRenderPiplineComputePass', source_props)
    graph.create_pass('Error', 'ErrorMeasurePass', options)
    graph.add_edge('Generate.source', 'Error.Source')
    graph.add_edge('Generate.reference', 'Error.Reference')
    graph.add_edge('Generate.worldPosition', 'Error.WorldPosition')
    graph.mark_output('Error.Output')
    testbed.render_graph = graph
    error_pass = graph.get_pass('Error')
    timings, snapshots = [], []

    def rows(path=None):
        with (path or csv_path).open(newline='', encoding='utf-8') as stream:
            return list(csv.DictReader(stream))

    def stats():
        value = dict(error_pass.statistics)
        for name in ('error', 'running_error'):
            if name in value:
                value[name] = [float(value[name][i]) for i in range(3)]
        return value

    def step():
        begin = time.perf_counter()
        graph.execute()
        timings.append(time.perf_counter() - begin)
        s = stats()
        assert 0 <= s['pending_samples'] <= s['max_pending_samples'] == 4, s
        assert s['staging_bytes'] == s['pending_samples'] * 16 <= s['max_staging_bytes'] == 64, s
        assert s['submitted_samples'] == s['completed_samples'] + s['discarded_samples'] + s['pending_samples'], s
        assert s['schema_version'] == 2 and s['frame_domain'] == 'pass_execute_ordinal', s
        assert s['time_domain'] == 'monotonic_seconds_since_pass_construction', s
        if s['backpressured']:
            assert s['status'] == 'backpressure' and s['skipped_samples'] > 0, s
        if s['valid']:
            assert s['submitted_frame'] < s['collected_frame'] <= s['execute_frame'], s
            assert s['sample_generation'] == s['generation'], s
        snapshots.append(s)
        return s

    def await_sample():
        deadline = time.perf_counter() + 15
        while time.perf_counter() < deadline:
            s = step()
            if s['valid']:
                return s
            time.sleep(.001)  # Harness only; pass execute/poll never sleeps.
        raise AssertionError('No completed sample before timeout')

    def oracle(w, h, *, bias=.25, squared=True, average=False, ignore=True):
        yy, xx = np.indices((h, w))
        diff = np.empty((h, w, 4), np.float32)
        diff[..., 0] = bias + (xx % 4) * .125
        diff[..., 1] = .5
        diff[..., 2] = 1.
        diff[..., 3] = 0.
        if ignore:
            diff[(xx + yy) % 3 == 0, :3] = 0.
        if squared:
            diff[..., :3] *= diff[..., :3]
        if average:
            diff[..., :3] = np.mean(diff[..., :3], axis=2, keepdims=True)
        return diff

    def check_sample(s, expected):
        h, w = expected.shape[:2]
        assert (s['width'], s['height']) == (w, h), s
        expected_rgb = expected[..., :3].astype(np.float64).mean(axis=(0, 1))
        actual = graph.get_output('Error.Output').to_numpy()
        np.savez(OUT / 'last-oracle.npz', actual=actual, expected=expected,
                 statistic=np.asarray(s['error']), expected_statistic=expected_rgb)
        np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=2e-6)
        np.testing.assert_allclose(s['error'], expected_rgb, atol=2e-6, rtol=2e-6)
        np.testing.assert_allclose(s['avg_error'], expected_rgb.mean(), atol=2e-6, rtol=2e-6)

    # The first execute must only submit, not publish or write a synchronous sample.
    first = step()
    assert not first['valid'] and first['pending_samples'] == first['submitted_samples'] == 1, first
    assert rows() == [], 'First submission was incorrectly written as an already completed sample'
    check_sample(await_sample(), oracle(17, 9))
    before_resize = step()
    assert before_resize['pending_samples'] >= 1
    old_row_count = len(rows())
    testbed.resize_frame_buffer(23, 11)
    resized = step()
    assert resized['generation'] > before_resize['generation'] and not resized['valid'], resized
    assert len(rows()) == old_row_count, 'An old-generation sample leaked through resize'
    new = await_sample()
    check_sample(new, oracle(23, 11))
    assert new['discarded_samples'] > before_resize['discarded_samples'], new
    mse_rows = rows()
    assert len(mse_rows) == new['completed_samples'], 'CSV dropped or repeated a completion'
    ids = [int(row['submitted_frame']) for row in mse_rows]
    assert ids == sorted(set(ids)), ids
    submitted_times = [float(row['submitted_time']) for row in mse_rows]
    assert submitted_times == sorted(submitted_times)
    for row in mse_rows:
        assert row['schema_version'] == '2' and row['status'] == 'completed'
        assert row['error_metric'] == 'MSE' and int(row['submitted_frame']) < int(row['collected_frame'])
        expected = oracle(int(row['width']), int(row['height']))[..., :3].astype(np.float64).mean(axis=(0, 1))
        np.testing.assert_allclose([float(row[k]) for k in list(row)[:4]], [expected.mean(), *expected], atol=2e-6, rtol=2e-6)

    # A native property update recreates the pass. Pending old tasks must neither
    # block destruction nor populate the new instance's CSV/statistics.
    csv_path = OUT / 'measurements-l1.csv'
    options.update(ComputeSquaredDifference=False, ComputeAverage=True, IgnoreBackground=False,
                   MeasurementsFilePath=str(csv_path))
    old_pass = error_pass
    graph.update_pass('Error', options)
    error_pass = graph.get_pass('Error')
    del old_pass
    gc.collect()
    assert not stats()['valid'] and stats()['submitted_samples'] == 0
    initial_l1 = step()
    assert not initial_l1['valid'] and rows() == []
    l1 = await_sample()
    assert not l1['squared_difference'] and l1['compute_average'] and not l1['ignore_background'], l1
    check_sample(l1, oracle(23, 11, squared=False, average=True, ignore=False))

    # Reference disappearance invalidates pending samples. Repeated executions
    # and diagnostic reads must not rewrite the previous completed value to CSV.
    graph.remove_edge('Generate.reference', 'Error.Reference')
    before_missing_rows = len(rows())
    for _ in range(12):
        no_reference = step()
        assert not no_reference['valid'] and no_reference['status'] == 'no_reference'
        assert len(rows()) == before_missing_rows
        time.sleep(.001)
    assert no_reference['pending_samples'] == 0, no_reference
    counters = (no_reference['submitted_samples'], no_reference['completed_samples'])
    for _ in range(10):
        observed = stats()
        assert (observed['submitted_samples'], observed['completed_samples']) == counters
        assert len(rows()) == before_missing_rows

    # Apply bounded real GPU pressure. This affects only fixture alpha, ignored by
    # ErrorMeasure. Record if this device actually reaches backpressure; do not
    # misreport branch coverage on a device fast enough to finish every task.
    graph.add_edge('Generate.reference', 'Error.Reference')
    heavy = copy.deepcopy(source_props)
    heavy['uniforms']['Params.work']['value'] = int(os.environ.get('CRP_ERROR_MEASURE_WORK', '16384'))
    graph.update_pass('Generate', heavy)
    testbed.resize_frame_buffer(256, 128)
    pressure = [step() for _ in range(48)]
    after_pressure = await_sample()
    check_sample(after_pressure, oracle(256, 128, squared=False, average=True, ignore=False))
    assert pressure[-1]['pending_samples'] <= 4
    maximum_pending = max(s['pending_samples'] for s in snapshots)
    observed_backpressure = any(s['backpressured'] for s in pressure)

    # Detach graph while there is a submitted, as-yet uncollected task. Any device
    # shutdown wait belongs to Testbed, not ErrorMeasurePass's destructor.
    step()
    pending_at_close = stats()['pending_samples']
    testbed.render_graph = None
    del error_pass, graph
    gc.collect()
    (OUT / 'snapshots.json').write_text(json.dumps(snapshots, indent=2), encoding='utf-8')
    return {'status': 'passed', 'backend': backend,
        'first_submission_does_not_publish': True, 'cpu_oracle_mse_and_l1_rgb_average': True,
        'resolutions': [[17, 9], [23, 11], [256, 128]], 'resize_discards_old_generation': True,
        'config_replacement_does_not_deliver_old_tasks': True, 'missing_reference_no_duplicate_csv': True,
        'csv_submission_identity_and_values': True, 'max_pending_samples': maximum_pending,
        'max_staging_bytes': max(s['staging_bytes'] for s in snapshots),
        'backpressure_observed': observed_backpressure, 'skipped_samples': after_pressure['skipped_samples'],
        'pending_at_graph_close': pending_at_close, 'graph_execute_seconds': timings,
        'constraints': ([] if observed_backpressure else ['Actual queue-full branch not observed on this device; increase CRP_ERROR_MEASURE_WORK.']) +
            ['CPU wall timings include fixture GPU submission/compilation; they are not an FPS claim.',
             'Same-instance UI option mutation requires real UI coverage; this smoke uses native update_pass replacement.',
             'Vulkan and continuous scene/refresh/queue-full cases are covered by the separate native fixture.']}


try:
    result = run()
except Exception as error:
    traceback.print_exc()
    result = {'status': 'failed', 'error': str(error)}
(OUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print('NATIVE_ERROR_MEASURE_ASYNC_' + result['status'].upper(), flush=True)
if 'm' in globals():
    exit(0 if result['status'] == 'passed' else 1)
elif result['status'] != 'passed':
    raise SystemExit(1)
