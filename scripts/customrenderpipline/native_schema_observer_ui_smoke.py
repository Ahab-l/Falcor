"""Serial real D3D12 panel integration. Mouse acceptance is a separate live run."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import traceback
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts/customrenderpipline'), str(ROOT/'build/m0-evidence/python')]
import falcor
import numpy as np
from native_schema_observer_ui import start
from native_schema_observer_ui_live import LiveInspectorControls

OUT = ROOT/'build/native-schema-observer-ui'
OUT.mkdir(exist_ok=True, parents=True)
run_dir = Path(tempfile.mkdtemp(prefix='panel-', dir=OUT))


def save_frame(path):
    pixels = np.asarray(m.framebuffer.to_numpy())
    assert pixels.dtype == np.uint8 and pixels.size == 800*1280*4, (pixels.dtype,pixels.shape)
    pixels = pixels.reshape(800,1280,4)
    def chunk(name, data):
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    data = b''.join(b'\0'+row.tobytes() for row in pixels)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',1280,800,8,6,0,0,0))+
                     chunk(b'IDAT',zlib.compress(data))+chunk(b'IEND',b''))


def run():
    graph, artifacts, observer, service, attachment, panel = start(
        m, session_dir=run_dir/'session', output_dir=run_dir/'generated')
    live_controls = LiveInspectorControls(m, service, panel)
    m.resizeFrameBuffer(1280,800)
    m.ui = True
    m.clock.pause()
    m.renderFrame()
    for _ in range(3): m.renderFrame()
    assert observer.dispatch_count == observer.readback_count == panel.model.preview.dispatch_count == 0

    async_actions = []

    def collect_pending():
        deadline = time.perf_counter() + 15
        for _ in range(240):
            if panel.model.pending is None and not panel.model.actions:
                break
            assert time.perf_counter() < deadline, 'Panel async request timed out'
            m.renderFrame()
        assert panel.model.pending is None and not panel.model.actions, 'Panel never completed its request'
        assert not service.listener_errors, service.listener_errors
        assert not panel.model.status.startswith('ERROR'), panel.model.status

    def action(name):
        panel.buttons[name].callback()
        m.renderFrame()
        submitted_frame = service.frame
        if name in ('inspect','export','compare','raw'):
            assert panel.model.pending is not None, 'UI requests must stage, not collect synchronously'
        collect_pending()
        assert not service.listener_errors, service.listener_errors
        assert not panel.model.status.startswith('ERROR'), panel.model.status
        if name in ('inspect','export','compare','raw'):
            assert panel.model.last_reply['frame'] == submitted_frame
            assert service.frame > submitted_frame
            async_actions.append({'action':name,'submitted':submitted_frame,'collected':service.frame})

    action('refresh')
    assert panel.model.texture is panel.image.texture
    assert observer.readback_count == 0
    sample = observer.inspect([640,400,1,1])
    def forbidden_sync(*args, **kwargs):
        raise AssertionError('Panel used an explicitly synchronous compatibility API')
    # Take one oracle above; any later frame callback must use the async path.
    observer.inspect = observer.compare = observer._decode = forbidden_sync
    service.handle = forbidden_sync
    from observer import PipelineObserver
    PipelineObserver.read = forbidden_sync
    panel.region.value = falcor.int4(640,400,1,1)
    action('inspect')
    assert panel.model.last_reply['frame'] == panel.model.preview_frame
    for field, expected in sample['fields'].items():
        np.testing.assert_allclose(panel.model.last_reply['result']['fields'][field]['values'], expected)
    assert 'STORAGE' in panel.results.text and 'ATTACHMENTS' in panel.results.text
    counts = (observer.dispatch_count,observer.readback_count,panel.model.preview.dispatch_count)
    for _ in range(4): m.renderFrame()
    assert counts == (observer.dispatch_count,observer.readback_count,panel.model.preview.dispatch_count)
    action('export')
    reference = Path(panel.model.last_reply['result']['fields']['roughness']['path'])
    assert reference.is_file()
    panel.reference.value = str(reference)
    action('compare')
    assert panel.model.last_reply['result']['passed']
    with np.load(reference) as archive: arrays = {key: archive[key].copy() for key in archive.files}
    arrays['fields.roughness'] += .5
    np.savez(run_dir/'bad.npz', **arrays)
    panel.reference.value = str(run_dir/'bad.npz')
    action('compare')
    assert panel.model.last_reply['status'] == 'comparison_failed'
    panel.reference.value = str(reference)
    action('raw')
    assert Path(panel.model.last_reply['result']['data']['path']).is_file()

    panel.source.value = panel.source.items.index('field:baseColor')
    panel.mode.value = panel.mode.items.index('rgb')
    action('refresh')
    panel.image.click_callback(falcor.uint2(640,400))  # Wiring test only, not actual mouse.
    m.renderFrame()
    assert panel.model.pending is not None
    collect_pending()
    assert panel.model.last_reply['result']['region'] == [640,400,1,1]
    assert panel.model.last_reply['frame'] == panel.model.preview_frame
    m.renderFrame()
    save_frame(run_dir/'panel-headless.png')
    rect = panel.image.rect
    assert rect.z > 0 and rect.w > 0
    old = panel.image.texture
    panel.source.value = panel.source.items.index('field:materialID')  # rgb invalid for uint
    panel.buttons['refresh'].callback(); m.renderFrame()
    assert panel.model.stale and panel.image.texture is old
    panel.mode.value = panel.mode.items.index('id')
    action('refresh')

    m.resizeFrameBuffer(960,600)
    panel.image.click_callback(falcor.uint2(100,100)); m.renderFrame()
    assert panel.model.stale and 'resize' in panel.model.status.lower()
    action('refresh')
    m.resizeFrameBuffer(1280,800)
    action('refresh')
    old = panel.image.texture
    original = artifacts.codec.read_bytes()
    try:
        artifacts.codec.write_bytes(original+b'\n// smoke contract mutation\n')
        panel.buttons['refresh'].callback(); m.renderFrame()
        assert panel.model.stale and panel.image.texture is old
    finally:
        artifacts.codec.write_bytes(original)
    action('refresh')

    panel.controls.close()
    panel.buttons['inspect'].callback(); m.renderFrame()
    assert not panel.model.actions and not panel.viewer.visible
    panel.show()
    callback_revision = m.graphExecutionCallbackRevision
    panel.buttons['close'].callback(); m.renderFrame()
    assert panel.model.closed and not service.closed
    assert not service._frame_listeners
    assert m.graphExecutionCallbackRevision == callback_revision
    live_controls.tick()
    assert live_controls.window.visible
    old_panel = panel
    live_controls.button.callback()  # Same native control as live; still not real mouse acceptance.
    assert live_controls.panel is old_panel, 'Reopen must defer native tree mutation'
    live_controls.tick()
    panel = live_controls.panel
    assert panel is not old_panel and live_controls.generation == 1
    assert panel.service is service and not service.closed
    assert len(service._frame_listeners) == 1
    assert m.graphExecutionCallbackRevision == callback_revision
    assert not live_controls.window.visible and panel.model.preview.dispatch_count == 0
    counts = (observer.dispatch_count, observer.readback_count)
    for _ in range(3):
        live_controls.tick()
        m.renderFrame()
    assert counts == (observer.dispatch_count, observer.readback_count)
    assert panel.model.preview.dispatch_count == 0
    action('refresh')
    attachment.close()
    assert panel.model.closed and panel.controls.parent is None, 'Service close must detach native panel'
    live_controls.close()
    assert live_controls.window.parent is None and live_controls.button.callback is None
    return {'status':'passed','evidence':str(run_dir),'screenshot':str(run_dir/'panel-headless.png'),
            'native_image_rect':[rect.x,rect.y,rect.z,rect.w],
            'async_actions':async_actions, 'synchronous_compatibility_methods_forbidden':True,
            'live_reopen_control_generation':live_controls.generation,
            'checks':['on-demand preview','submission-frame pixel','compare pass/fail','typed/raw export',
                      'idle no GPU work','source/resize/layout stale','hide/show','close/reopen CLI preserved'],
            'mouse_driven_acceptance':False}


try:
    result = run()
    print('V5_PANEL_PASS',flush=True)
except Exception:
    result = {'status':'failed','evidence':str(run_dir),'error':traceback.format_exc()}
    print(result['error'],flush=True)
finally:
    (run_dir/'panel-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    exit()
