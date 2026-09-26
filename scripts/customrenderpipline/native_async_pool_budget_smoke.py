"""Exercise the real 64 MiB staging budget; native fence tests cover pending timing.

Run with Mogwai --headless --enable-debug-layer --script, optionally setting
CRP_ASYNC_BACKEND=D3D12|Vulkan. Sleeps occur only in this acceptance harness.
"""
import gc
import hashlib
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
from observer_async import ReadbackPool

OUT = Path(tempfile.mkdtemp(prefix='async-full-budget-', dir=ROOT / 'build/native-framework-completion'))
print('ASYNC_FULL_BUDGET_EVIDENCE ' + str(OUT), flush=True)


def run():
    backend = os.environ.get('CRP_ASYNC_BACKEND', 'D3D12')
    testbed = falcor.Testbed(create_window=False, width=16, height=16,
        device_type=getattr(falcor.DeviceType, backend), enable_debug_layers=True)
    size, cap = 8 * 1024 * 1024, 64 * 1024 * 1024
    data = np.arange(size // 4, dtype=np.uint32) * np.uint32(17) ^ np.uint32(0xa538ef91)
    expected = hashlib.sha256(data.tobytes()).hexdigest()
    records = []
    for max_tasks in (8, 16, 8):
        pool = ReadbackPool(max_tasks=max_tasks)
        source = testbed.device.create_buffer(size, bind_flags=falcor.ResourceBindFlags.ShaderResource)
        source.from_numpy(data)
        tickets = []
        for index in range(8):
            tickets.append(pool.submit(lambda budget: source.read_async(max_bytes=budget), metadata={'index': index}))
        assert pool.pending_count == 8 and pool.staging_bytes == cap
        calls = []

        def forbidden_factory(budget):
            calls.append(budget)
            return source.read_async(max_bytes=budget)

        for ticket in tickets[:4]:
            ticket.cancel()
        assert pool.pending_count == 8 and pool.staging_bytes == cap
        try:
            pool.submit(forbidden_factory)
            raise AssertionError('Full staging pool admitted a ninth task')
        except ValueError as error:
            assert 'queue is full' in str(error), error
        assert not calls, 'Admission must reject before allocation/copy'

        # All eight staged snapshots precede the overwrite and source release.
        source.from_numpy(np.zeros_like(data))
        del source
        gc.collect()
        deadline = time.perf_counter() + 15
        while pool.pending_count and time.perf_counter() < deadline:
            pool.poll()
            if pool.pending_count:
                time.sleep(.001)
        assert pool.pending_count == pool.staging_bytes == 0
        for index, ticket in enumerate(tickets):
            if index < 4:
                assert ticket.status == 'cancelled'
            else:
                value = ticket.result()
                assert len(value) == size and hashlib.sha256(value).hexdigest() == expected
                assert ticket.metadata['index'] == index
                del value
        records.append({'max_tasks': max_tasks, 'peak_tasks': 8, 'peak_staging_bytes': cap,
                        'cancelled': 4, 'exact_results': 4, 'final_staging_bytes': pool.staging_bytes})
        del ticket, tickets, pool
        gc.collect()

    # At one byte below a native allocation size, failure leaves no pool charge.
    source = testbed.device.create_buffer(size)
    pool = ReadbackPool(max_bytes=size - 1)
    try:
        pool.submit(lambda budget: source.read_async(max_bytes=budget))
        raise AssertionError('Native allocation bypassed the remaining byte budget')
    except falcor.RuntimeError as error:
        assert 'staging byte budget' in str(error), error
    assert pool.pending_count == pool.staging_bytes == 0
    return {'status': 'passed', 'backend': backend, 'batches': records,
            'staged_bytes_total': 3 * cap, 'exact_snapshot_sha256': expected,
            'native_over_budget_no_pool_charge': True,
            'constraints': ['64 MiB refers to native staging, not process/private memory or retained result bytes.',
                           'Tasks may already be GPU-ready before cancellation; deterministic pending fences have separate native tests.',
                           'No desktop FPS or whole-framework backend claim.']}


try:
    result = run()
except Exception as error:
    traceback.print_exc()
    result = {'status': 'failed', 'error': str(error)}
(OUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print('NATIVE_ASYNC_FULL_BUDGET_' + result['status'].upper(), flush=True)
exit(0 if result['status'] == 'passed' else 1)
