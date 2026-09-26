"""Exercise the delivered generator-to-Mogwai entry and stock Blit connection."""
from pathlib import Path
import json
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'build/m0-evidence/python'))
import numpy as np

entry = runpy.run_path(str(ROOT/'scripts/customrenderpipline/native_schema_gbuffer.py'))
graph = entry['graph']
m.addGraph(graph)
m.setActiveGraph(graph)
m.loadScene(str(ROOT/'scripts/customrenderpipline/examples/schema_gbuffer/Scene.pyscene'))
m.resizeFrameBuffer(128, 72)
m.clock.pause()
m.ui = False
m.renderFrame()
preview = np.asarray(graph.getOutput('Preview.dst').to_numpy())
mask = preview[..., 3] > 0
assert mask.sum() > 100
assert np.isfinite(preview).all()
assert graph.getOutput('GBuffer.depth') is not None
(ROOT/'build/native-gbuffer-schema/example-result.json').write_text(json.dumps({
    'status': 'passed', 'visible_pixels': int(mask.sum()), 'native_blit': True,
    'schema_entry': 'scripts/customrenderpipline/native_schema_gbuffer.py'}, indent=2))
print('NATIVE_SCHEMA_EXAMPLE_PASS', flush=True)
exit()
