"""Mogwai entry: native Schema GBuffer with an on-demand Python/CLI observer."""
import atexit
import os
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import falcor
from generate_native_gbuffer import generate
from observer import PipelineObserver
from schema_observer_service import ObservationService
from observer_mogwai import MogwaiObservation


def start(renderer, *, schema_path=None, session_dir=None, output_dir=None, scene_path=None):
    artifacts = generate(schema_path or HERE/'examples/schema_gbuffer/Schema.json',
                         output_dir or ROOT/'build/native-schema-observer/generated')
    graph = falcor.RenderGraph('SchemaGBuffer')
    graph.addPass(falcor.createPass('CustomRenderPiplineGBufferPass', {'definition': str(artifacts.definition)}), 'GBuffer')
    graph.addPass(falcor.createPass('BlitPass', {'outputFormat': 'RGBA32Float'}), 'Preview')
    graph.addEdge('GBuffer.color', 'Preview.src')
    graph.markOutput('Preview.dst')
    graph.markOutput('GBuffer.depth')
    observer = PipelineObserver(graph).schema(artifacts)
    session_dir = session_dir or ROOT/'build/native-schema-observer/sessions'/uuid.uuid4().hex
    service = ObservationService(observer, session_dir)
    renderer.addGraph(graph)
    renderer.setActiveGraph(graph)
    renderer.loadScene(str(scene_path or HERE/'examples/schema_gbuffer/Scene.pyscene'))
    attachment = MogwaiObservation(renderer, service)
    atexit.register(attachment.close)
    return graph, artifacts, observer, service, attachment


if 'm' in globals():
    graph, artifacts, observer, service, attachment = start(m, session_dir=os.environ.get('CRP_OBSERVER_SESSION'))
    print('V4_SESSION '+str(service.mailbox.session_dir), flush=True)
