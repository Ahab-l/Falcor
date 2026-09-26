"""Editable native JSON graph: Schema GBuffer, selected Mesh and custom shaders.

Run with Mogwai --script this_file.py. CRP_NATIVE_EXAMPLE_TEST=1 runs a single
headless verification and exits. CRP_OBSERVER_SESSION optionally enables the
existing V4 command-line mailbox; there is no polling/readback when it is idle.
"""
import atexit
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
# Same optional dependency directory used by the existing V4 entry/tests.
sys.path.append(str(ROOT/'build/m0-evidence/python'))
from pipeline import make_graph
from generate_native_gbuffer import generate
from observer import PipelineObserver


def start(renderer, *, output_dir=None, session_dir=None):
    output_dir = Path(output_dir or ROOT/'build/native-pass-migration/example')
    artifacts = generate(HERE/'examples/schema_gbuffer/Schema.json', output_dir/'generated')
    definition = json.loads((HERE/'examples/native_passes/Graph.json').read_text())
    definition['nodes'][0]['properties'] = {'definition': str(artifacts.definition)}
    renderer.loadScene(str(HERE/'examples/schema_gbuffer/Scene.pyscene'))
    # Choose by a native material query, or supply application-owned instance IDs.
    # MeshDraw itself never looks up material names or another material registry.
    selected = list(renderer.scene.get_raster_instance_ids(['schema_material_1']))
    definition['nodes'][1]['properties'] = {'instanceIDs': selected}
    graph = make_graph('NativeDescribedPasses', definition, base_directory=HERE/'examples/native_passes')
    observer = PipelineObserver(graph).schema(artifacts)
    renderer.addGraph(graph)
    renderer.setActiveGraph(graph)
    attachment = None
    if session_dir is not None:
        from schema_observer_service import ObservationService
        from observer_mogwai import MogwaiObservation
        attachment = MogwaiObservation(renderer, ObservationService(observer, session_dir))
        atexit.register(attachment.close)
        print('V4_SESSION '+str(session_dir), flush=True)
    return graph, observer, attachment


if 'm' in globals():
    graph, observer, attachment = start(m, session_dir=os.environ.get('CRP_OBSERVER_SESSION'))
    if os.environ.get('CRP_NATIVE_EXAMPLE_TEST') == '1':
        import numpy as np
        from observer import compare_arrays
        m.resizeFrameBuffer(128, 72)
        m.clock.pause()
        m.ui = False
        m.renderFrame()
        # A real generated decoder, not the old UE Schema/Config path.
        decoded = observer.inspect([0, 0, 128, 72], fields=['baseColor', 'coverage'])
        selected = np.asarray(graph.getOutput('Selected.color').to_numpy())
        # UNORM to_numpy() returns raw bytes in this Falcor version.
        surface = np.asarray(graph.getOutput('GBuffer.color').to_numpy()).reshape(72, 128, 4).astype(np.float32)/255.0
        expected = surface.copy()
        expected[..., :3] += (selected[..., :3]-surface[..., :3])*selected[..., 3:4]*0.5
        assert selected[..., 3].any() and (selected[..., 3] == 0).any()
        comparisons = {}
        for name in ('Combine.color', 'Display.color', 'Blit.dst'):
            comparisons[name] = compare_arrays(graph.getOutput(name).to_numpy(), expected, atol=1e-6)
            assert comparisons[name]['passed'], comparisons[name]
        assert 'generate_schema' not in sys.modules and 'pipeline_snapshot' not in sys.modules
        output = ROOT/'build/native-pass-migration/example/result.json'
        output.write_text(json.dumps({'status': 'passed', 'schema_decode': bool(decoded),
                                     'comparisons': comparisons}, indent=2))
        print('NATIVE_DESCRIBED_EXAMPLE_PASSED '+str(output), flush=True)
        if attachment is not None:
            attachment.close()
        exit()
