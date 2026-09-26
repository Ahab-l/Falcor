"""Mogwai entry: V4 native Schema demo plus on-demand native inspector."""
import atexit
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from native_schema_observer import start as start_observer
from schema_observer_ui import SchemaInspectorPanel


def start(renderer, **kwargs):
    graph, artifacts, observer, service, attachment = start_observer(renderer, **kwargs)
    panel = SchemaInspectorPanel(renderer, service)
    atexit.register(panel.close)
    return graph, artifacts, observer, service, attachment, panel


if 'm' in globals():
    graph, artifacts, observer, service, attachment, panel = start(m, session_dir=os.environ.get('CRP_OBSERVER_SESSION'))
    m.resizeFrameBuffer(1280, 800)
    m.ui = True
    panel._submit('refresh')
    print('V5_SESSION '+str(service.mailbox.session_dir), flush=True)
