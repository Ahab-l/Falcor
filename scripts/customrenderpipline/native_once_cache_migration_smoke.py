"""Native regression for immutable compute execution, without the retired pipeline."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts/customrenderpipline'), str(ROOT / 'build/m0-evidence/python')]
import falcor
import numpy as np
from immutable_compute_cache_fixture import GENERATOR, CONSUMER, declaration, invalid_declarations
from pipeline import make_graph

PARENT = ROOT / 'build/native-generic-migration'
PARENT.mkdir(exist_ok=True)
OUT = Path(tempfile.mkdtemp(prefix='once-', dir=PARENT))
print('NATIVE_ONCE_CACHE_EVIDENCE ' + str(OUT), flush=True)


def run():
    generator, consumer = OUT / 'Generate.slang', OUT / 'Consume.slang'
    generator.write_text(GENERATOR)
    consumer.write_text(CONSUMER)
    authored = declaration('Generate.slang', 'Consume.slang')
    path = OUT / 'Graph.json'
    path.write_text(json.dumps(authored, indent=2))
    graph = make_graph('NativeOnceCache', path)
    m.resizeFrameBuffer(16, 16)
    m.ui = False
    m.addGraph(graph)
    m.setActiveGraph(graph)
    m.renderFrame()
    count = lambda: falcor.customRenderPiplineComputeDispatchCount(graph, 'Generate')
    expected = (np.arange(64, dtype=np.uint32) + 17).reshape(8, 8)
    assert count() == 1
    np.testing.assert_array_equal(graph.getOutput('Consume.observed').to_numpy(), expected)
    for _ in range(3):
        m.renderFrame()
        np.testing.assert_array_equal(graph.getOutput('Consume.observed').to_numpy(), expected)
        np.testing.assert_array_equal(graph.getOutput('Consume.shared').to_numpy(), np.full((8, 8), 999999, np.uint32))
        assert count() == 1
    m.resizeFrameBuffer(23, 19)
    m.renderFrame()
    np.testing.assert_array_equal(graph.getOutput('Consume.observed').to_numpy(), expected)
    assert count() == 2

    # Keep native parser coverage for the restrictions that make a cached
    # output immutable and independent of viewport/graph state.
    rejected = []
    selected = {'mode_\'sometimes\'', 'mode_True', 'input', 'inputOutput',
                'extent', 'preExposure', 'viewport', 'relative', 'partial_view',
                'structured_buffer', 'fullscreen'}
    valid = declaration(str(generator), str(consumer))
    for label, bad in invalid_declarations(valid).items():
        if label not in selected:
            continue
        node = bad['nodes'][0]
        try:
            falcor.createPass(node['type'], node['properties'])
        except RuntimeError as error:
            rejected.append({'case': label, 'message': str(error)})
        else:
            raise AssertionError('Accepted invalid once declaration: ' + label)
    return {'status': 'passed', 'dispatch_count_after_resize': count(),
            'downstream_overwrite_restored_exact': True,
            'ordinary_make_graph': True, 'rejections': rejected}


try:
    result = run()
except Exception as error:
    traceback.print_exc()
    result = {'status': 'failed', 'error': str(error)}
(OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print('NATIVE_ONCE_CACHE_' + result['status'].upper(), flush=True)
exit()
