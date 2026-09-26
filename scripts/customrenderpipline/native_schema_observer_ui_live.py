"""Bounded live mouse-acceptance harness (not the normal user entry).

Saves state only after an action; write the printed run's stop file to exit.
The 30 ms sleep is test-only throttling, not part of the production panel.
"""
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import zlib

ROOT = Path(__file__).resolve().parents[2]


class LiveInspectorControls:
    """Acceptance-fixture controls, not a second production panel lifecycle API.

    tick() is called only between renderFrame calls. The native button queues a
    request; rebuilding/detaching widgets inside the draw callback is forbidden.
    """
    def __init__(self, renderer, service, panel):
        import falcor
        self.renderer, self.service, self.panel = renderer, service, panel
        self.generation = 0
        self._reopen_requested = self._closed = False
        self.window = falcor.ui.Window(renderer.screen, title='Live acceptance | Inspector closed',
                                      position=falcor.float2(10, 30), size=falcor.float2(475, 150))
        falcor.ui.Text(self.window, text='The graph and CLI service are still running.')
        self.status = falcor.ui.Text(self.window, text='Reopen creates a fresh panel on the same service.')
        self.button = falcor.ui.Button(self.window, label='Reopen Inspector', callback=self._request_reopen)
        self.window.close()

    def _request_reopen(self):
        self._reopen_requested = True

    def tick(self):
        if self._closed:
            return
        if self._reopen_requested:
            self._reopen_requested = False
            try:
                if self.service.closed:
                    raise RuntimeError('Observer service is closed; cannot reopen this session')
                if self.panel.model.closed:
                    from schema_observer_ui import SchemaInspectorPanel
                    self.panel = SchemaInspectorPanel(self.renderer, self.service)
                    self.generation += 1
                else:
                    self.panel.show()
                self.status.text = 'Inspector reopened on the existing service.'
            except Exception as error:
                self.status.text = 'ERROR: '+str(error)
        if self.panel.model.closed:
            self.window.show()
        else:
            self.window.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.button.callback = None
        self.panel.close()
        self.window.detach()


def save_frame(renderer, path):
    import numpy as np
    data = np.asarray(renderer.framebuffer.to_numpy()).reshape(800,1280,4)
    def chunk(name, payload):
        return struct.pack('>I',len(payload))+name+payload+struct.pack('>I',zlib.crc32(name+payload)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',1280,800,8,6,0,0,0))+
                     chunk(b'IDAT',zlib.compress(b''.join(b'\0'+row.tobytes() for row in data)))+chunk(b'IEND',b''))


def run(renderer):
    sys.path[:0] = [str(ROOT/'scripts/customrenderpipline'), str(ROOT/'build/m0-evidence/python')]
    from native_schema_observer_ui import start
    out = ROOT/'build/native-schema-observer-ui'
    out.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix='live-', dir=out))
    (out/'live-run.txt').write_text(str(run_dir), encoding='utf-8')
    graph, artifacts, observer, service, attachment, panel = start(
        renderer, session_dir=run_dir/'session', output_dir=run_dir/'generated')
    controls = None
    try:
        controls = LiveInspectorControls(renderer, service, panel)
        renderer.resizeFrameBuffer(1280,800)
        renderer.clock.pause()
        renderer.ui = True
        panel.source.value = panel.source.items.index('field:baseColor')
        panel.mode.value = panel.mode.items.index('rgb')
        panel._submit('refresh')
        print('V5_LIVE '+str(run_dir), flush=True)
        last_key, action_id = None, 0
        deadline = time.monotonic()+600
        while time.monotonic()<deadline and not (run_dir/'stop').exists():
            controls.tick()
            renderer.renderFrame()
            panel = controls.panel
            key = (controls.generation, panel.model.closed, panel.model.revision, controls.status.text, controls.window.visible)
            if key != last_key:
                last_key = key
                rect = panel.image.rect
                report = {'revision':panel.model.revision,'status':panel.model.status,'preview_frame':panel.model.preview_frame,
                          'source':panel.model.preview_source,'dimensions':panel.model.preview_dims,
                          'image_rect':[rect.x,rect.y,rect.z,rect.w], 'state':panel.model.last_state,
                          'reply':panel.model.last_reply,'listener_errors':service.listener_errors,
                          'panel_generation':controls.generation,'panel_closed':panel.model.closed,
                          'reopen_visible':controls.window.visible,
                          'service_closed':service.closed,'reopen_status':controls.status.text,
                          'listener_count':len(service._frame_listeners),
                          'graph_callback_revision':renderer.graphExecutionCallbackRevision}
                (run_dir/'state.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                # Panel revision restarts after reconstruction; never overwrite an earlier action.
                (run_dir/f'action-{action_id:04d}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                save_frame(renderer, run_dir/f'action-{action_id:04d}.png')
                action_id += 1
            time.sleep(.03)
    finally:
        if controls is not None:
            controls.close()
        else:
            panel.close()
        attachment.close()
        print('V5_LIVE_CLOSED',flush=True)


if 'm' in globals():
    try:
        run(m)
    finally:
        exit()
