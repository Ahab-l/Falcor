"""Real GPU snapshots, bounded admission, lifecycle and measured async callback cost."""
import ctypes
from ctypes import wintypes
import gc
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts/customrenderpipline'), str(ROOT/'build/m0-evidence/python')]
import falcor
import numpy as np
from native_schema_observer import start
from observer import PipelineObserver
from observer_async import ReadbackPool
from schema_observer_service import ObservationService
from observer_mogwai import MogwaiObservation

OUT = Path(tempfile.mkdtemp(prefix='async-lifecycle-', dir=ROOT/'build/native-framework-completion'))
print('ASYNC_LIFECYCLE_EVIDENCE '+str(OUT), flush=True)


def private_bytes():
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
            'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    fn = ctypes.windll.psapi.GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    assert fn(get_process(), ctypes.byref(counters), counters.cb)
    return counters.PrivateUsage


def run():
    graph, artifacts, observer, service, attachment = start(m, session_dir=OUT/'session', output_dir=OUT/'generated')
    m.resizeFrameBuffer(128,72)
    m.clock.pause()
    m.ui = False
    m.renderFrame()
    reference = observer.inspect([0,0,128,72])
    sync_seconds = []
    for _ in range(12):
        begin = time.perf_counter(); observer.inspect([0,0,8,8], fields=['baseColor'])
        sync_seconds.append(time.perf_counter()-begin)
    raw_reference = PipelineObserver(graph).read('GBuffer.materialBits')
    def forbidden(*args, **kwargs):
        raise AssertionError('Rendering callback used a synchronous compatibility API')
    observer.inspect = observer.compare = observer._decode = forbidden
    PipelineObserver.read = forbidden
    service.handle = forbidden
    submit_seconds, pump_seconds, private_samples = [], [], []
    shared = service.pool
    max_count = max_bytes = 0

    def submit(region, fields=None, **arguments):
        nonlocal max_count, max_bytes
        before = time.perf_counter()
        ticket = service.submit({'graph':graph.name,'operation':'inspect',
                                 'arguments':{'region':region,'fields':fields or ['baseColor'],**arguments}})
        submit_seconds.append(time.perf_counter()-before)
        max_count = max(max_count, service.pool.pending_count)
        max_bytes = max(max_bytes, service.pool.staging_bytes)
        return ticket

    def drain(tickets):
        deadline = time.perf_counter()+15
        for _ in range(240):
            if all(ticket.ready for ticket in tickets): break
            assert time.perf_counter() < deadline, 'Async observation timed out'
            begin = time.perf_counter(); m.renderFrame(); pump_seconds.append(time.perf_counter()-begin)
        assert all(ticket.ready for ticket in tickets)
        replies = [ticket.result() for ticket in tickets]
        assert all(reply['status']=='ok' for reply in replies), replies
        assert not service.listener_errors, service.listener_errors
        return replies

    # Eight different regions reuse the SAME decoder scratch buffer before any
    # collection. Saturated count rejects a ninth without an extra dispatch.
    regions = [[i*13,12,8,8] for i in range(8)]
    submitted_frame = service.frame
    tickets = [submit(region) for region in regions]
    assert shared.pending_count == 8 and all(not ticket.ready for ticket in tickets)
    copies = observer.readback_count
    rejected = submit([0,0,8,8])
    assert rejected.ready and rejected.result()['status']=='error'
    assert observer.readback_count == copies and shared.pending_count == 8
    m.resizeFrameBuffer(160,90)
    replies = drain(tickets)
    for region, reply in zip(regions, replies):
        x,y,w,h = region
        assert reply['frame']==submitted_frame and reply['layout_hash']==observer.layout_hash
        assert reply['result']['region']==region
        np.testing.assert_array_equal(np.asarray(reply['result']['fields']['baseColor']['values'],dtype=np.float32),
                                      reference['fields']['baseColor'][y:y+h,x:x+w])

    # Per-pool aggregate bytes are validated BEFORE decoder allocation/dispatch.
    service.pool = ReadbackPool(max_bytes=observer.stride*64*4-1)
    copies = observer.readback_count
    rejected = submit([0,0,8,8])
    assert rejected.ready and rejected.result()['status']=='error'
    assert observer.readback_count==copies and service.pool.pending_count==0
    service.pool = shared
    m.resizeFrameBuffer(128,72); m.renderFrame()

    # Both raw and Schema requests survive output removal with submitted data.
    submitted_frame = service.frame
    raw = service.submit({'graph':graph.name,'operation':'read','arguments':{'output':'GBuffer.materialBits'}})
    staged = submit([0,0,8,8])
    graph.unmarkOutput('GBuffer.materialBits')
    invalid = submit([0,0,8,8])
    assert invalid.ready and invalid.result()['status']=='error'
    raw_reply, sample_reply = drain([raw, staged])
    assert raw_reply['frame']==sample_reply['frame']==submitted_frame
    assert Path(raw_reply['result']['data']['path']).read_bytes()==raw_reference['data']
    graph.markOutput('GBuffer.materialBits'); m.renderFrame()

    # Reference files and rule/mask values are captured at submission, not read
    # again when GPU completion is collected.
    np.savez(OUT/'reference.npz', baseColor=reference['fields']['baseColor'][:8,:8])
    compare = service.submit({'graph':graph.name,'operation':'compare','arguments':{
        'region':[0,0,8,8], 'reference':str(OUT/'reference.npz'),
        'rules':{'baseColor':{'kind':'numeric','atol':0.0,'rtol':0.0}}}})
    np.savez(OUT/'reference.npz', baseColor=np.ones((8,8,3),dtype=np.float32)*7)
    assert drain([compare])[0]['result']['passed']

    # Closing detaches delivery, not GPU work. Charges cannot disappear until a
    # pool poll observes the native fence; reopen must use the SAME shared pool.
    cancelled = [submit([0,0,8,8], export=True) for _ in range(8)]
    charged = shared.staging_bytes
    exported_before = set(service.exports.iterdir())
    service.close()
    assert shared.pending_count==8 and shared.staging_bytes==charged
    assert all(ticket.ready and ticket.result()['error']['code']=='cancelled' for ticket in cancelled)
    attachment.close()
    service = ObservationService(observer, OUT/'reopened')
    assert service.pool is shared
    attachment = MogwaiObservation(m,service)
    service.handle = forbidden
    m.renderFrame()
    assert shared.pending_count==0 and shared.staging_bytes==0
    assert set((OUT/'session'/'exports').iterdir())==exported_before

    # Warm then repeatedly saturate/reap real GPU tasks. Memory samples include
    # the entire renderer; a generous cap catches growth, not allocator noise.
    stress_batches = 64
    for batch in range(stress_batches+4):
        tickets = [submit([i*13,12,8,8]) for i in range(8)]
        assert shared.pending_count==8 and shared.staging_bytes<=shared.max_bytes
        drain(tickets)
        tickets.clear()
        for _ in range(2): m.renderFrame()
        gc.collect()
        assert shared.pending_count==0 and shared.staging_bytes==0
        if batch>=4: private_samples.append(private_bytes())
    assert max(private_samples)-min(private_samples) < 128*1024*1024, private_samples
    counts = observer.dispatch_count, observer.readback_count
    for _ in range(16): m.renderFrame()
    assert counts==(observer.dispatch_count,observer.readback_count), 'Idle observation issued GPU work'
    attachment.close()
    return {'status':'passed','same_scratch_snapshots':8,'resize_and_removed_output_snapshots':True,
            'frozen_reference_compare':True,'cancel_close_reopen_shared_pool':True,
            'synchronous_compatibility_methods_forbidden':True,'count_and_byte_admission_before_dispatch':True,
            'stress_batches':stress_batches,'stress_tasks':stress_batches*8,'maximum_pending_count':max_count,
            'maximum_staging_bytes':max_bytes,'private_bytes_samples':private_samples,'idle_frames_without_observation_work':16,
            'sync_8x8_seconds':sync_seconds,'async_submit_seconds':submit_seconds,'render_frame_during_collection_seconds':pump_seconds,
            'timing_scope':'Diagnostic CPU wall time only; no whole-renderer FPS claim or hardware performance guarantee'}


try:
    result = run()
except Exception as error:
    traceback.print_exc()
    result = {'status':'failed','error':str(error)}
(OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('NATIVE_ASYNC_LIFECYCLE_'+result['status'].upper(),flush=True)
exit()
