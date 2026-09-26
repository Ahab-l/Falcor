"""Native Asset -> accumulation -> History + stock Blit, without a Scene.

CRP_RESOURCE_EXAMPLE_TEST=1 checks three executions and reset, then exits.
Interactive console: reset_history(); graph.updatePass('Assets', new_properties).
"""
import json
import os
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT/'build/m0-evidence/python')]
from pipeline import make_graph
import falcor


def start(renderer, output_dir=None):
    output = Path(output_dir or ROOT/'build/resource-history-migration/example')
    output.mkdir(parents=True, exist_ok=True)
    asset = output/'increment.bin'
    # Only example setup writes this file. AssetPass performs no per-frame I/O.
    asset.write_bytes(struct.pack('<4f', 0.125, 0.25, 0.5, 1.0))
    definition = json.loads((HERE/'examples/native_resources/Graph.json').read_text())
    definition['nodes'][0]['properties']['assets']['increment']['file'] = str(asset.resolve())
    graph = make_graph('NativeResourceHistory', definition, base_directory=HERE/'examples/native_resources')
    renderer.addGraph(graph)
    renderer.setActiveGraph(graph)
    return graph, output


if 'm' in globals():
    graph, output = start(m)

    def reset_history():
        falcor.customRenderPiplineResetHistory(graph, 'accumulation')

    if os.environ.get('CRP_RESOURCE_EXAMPLE_TEST') == '1':
        import numpy as np
        m.resizeFrameBuffer(16, 8)
        m.clock.pause()
        m.ui = False
        increment = np.array([0.125, 0.25, 0.5, 1.0], dtype=np.float32)
        for n in (1, 2, 3):
            m.renderFrame()
            actual = np.asarray(graph.getOutput('Add.current').to_numpy()).reshape(8, 16, 4)
            np.testing.assert_array_equal(actual, np.broadcast_to(increment*n, actual.shape))
            np.testing.assert_array_equal(graph.getOutput('Blit.dst').to_numpy(), actual)
        assert json.loads(falcor.customRenderPiplineHistoryInfo(graph))['accumulation']['updates'] == 3
        reset_history()
        m.renderFrame()
        actual = np.asarray(graph.getOutput('Add.current').to_numpy()).reshape(8, 16, 4)
        np.testing.assert_array_equal(actual, np.broadcast_to(increment, actual.shape))
        assert not any(name in sys.modules for name in ('pipeline_snapshot', 'generate_schema', 'scene_package'))
        (output/'result.json').write_text(json.dumps({'status':'passed', 'sequence':[1,2,3,1],
            'asset_history_blit':True, 'scene_required':False}, indent=2))
        print('NATIVE_RESOURCE_EXAMPLE_PASSED '+str(output/'result.json'), flush=True)
        exit()
