"""Native nonblocking readback snapshots; run with Mogwai --headless --script."""
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts/customrenderpipline'), str(ROOT/'build/m0-evidence/python')]
import falcor
import numpy as np

OUT = Path(tempfile.mkdtemp(prefix='async-native-', dir=ROOT/'build/native-framework-completion'))
print('ASYNC_READBACK_EVIDENCE '+str(OUT), flush=True)


def run():
    assert hasattr(falcor.Buffer, 'read_async'), 'Native buffer asynchronous readback missing'
    assert hasattr(falcor.Texture, 'read_async'), 'Native texture asynchronous readback missing'
    backend = getattr(falcor.DeviceType, os.environ.get('CRP_ASYNC_BACKEND', 'D3D12'))
    testbed = falcor.Testbed(create_window=False, width=8, height=8,
                             device_type=backend, enable_debug_layers=True)
    device = testbed.device
    timings = []

    def collect(task, expected):
        begin = time.perf_counter()
        # Test harness yields CPU time. Production frame pumps only poll once.
        while not task.ready:
            if time.perf_counter()-begin > 10:
                raise AssertionError('GPU readback did not finish')
            time.sleep(.001)
        before = time.perf_counter()
        actual = task.result()
        timings.append(time.perf_counter()-before)
        assert isinstance(actual, bytes) and actual == expected
        assert task.byte_size == len(expected)
        assert task.staging_bytes >= task.byte_size
        assert task.result() == expected

    flags = falcor.ResourceBindFlags.UnorderedAccess | falcor.ResourceBindFlags.ShaderResource
    buffer = device.create_structured_buffer(4, 8, flags)
    words = np.array([0, 1, 0xffffffff, 0x80000000, 7, 9, 0x7fc00000, 11], np.uint32)
    buffer.from_numpy(words)
    whole = buffer.read_async()
    part = buffer.read_async(offset=8, size=16)
    buffer.from_numpy(np.zeros_like(words))
    del buffer
    gc.collect()
    collect(whole, words.tobytes())
    collect(part, words.tobytes()[8:24])

    texture = device.create_texture(width=5, height=3, format=falcor.ResourceFormat.RGBA32Uint,
                                    array_size=2, mip_levels=3, bind_flags=flags)
    jobs = []
    for layer in range(2):
        for mip in range(3):
            w, h = max(1, 5 >> mip), max(1, 3 >> mip)
            image = np.arange(w*h*4, dtype=np.uint32).reshape(h,w,4)+np.uint32(0x80000000+layer*100+mip*10)
            texture.from_numpy(image, mip_level=mip, array_slice=layer)
            task = texture.read_async(mip_level=mip, array_slice=layer)
            texture.from_numpy(np.zeros_like(image), mip_level=mip, array_slice=layer)
            jobs.append((task, image.tobytes()))
    rejects = []
    for label, kwargs in [('mip', {'mip_level':3}), ('layer', {'array_slice':2}), ('budget', {'max_bytes':1})]:
        try: texture.read_async(**kwargs)
        except Exception as error: rejects.append({'case':label, 'message':str(error)})
        else: raise AssertionError('Accepted invalid '+label)
    del texture
    gc.collect()
    for task, expected in jobs: collect(task, expected)
    buffer = device.create_buffer(16)
    for kwargs in ({'offset':17}, {'offset':12,'size':8}, {'max_bytes':15}, {'size':2**32}):
        try: buffer.read_async(**kwargs)
        except Exception: pass
        else: raise AssertionError('Accepted out-of-range buffer read')
    return {'status':'passed', 'backend':os.environ.get('CRP_ASYNC_BACKEND','D3D12'),
            'buffer_snapshot_and_slice':True, 'texture_layers_and_mips':6,
            'source_destroyed_before_collect':True, 'rejections':rejects,
            'collection_seconds':timings}


try:
    result = run()
except Exception as error:
    traceback.print_exc()
    result = {'status':'failed','error':str(error)}
(OUT/'result.json').write_text(json.dumps(result,indent=2))
print('NATIVE_ASYNC_READBACK_'+result['status'].upper(), flush=True)
exit()
