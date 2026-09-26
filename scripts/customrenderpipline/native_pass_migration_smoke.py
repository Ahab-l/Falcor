"""GPU acceptance for described executors with no legacy Schema/Scene/transaction."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts/customrenderpipline'), str(ROOT/'build/m0-evidence/python')]
import falcor
import numpy as np

OUT = Path(tempfile.mkdtemp(prefix='executors-', dir=ROOT/'build/native-pass-migration'))
print('NATIVE_PASS_EVIDENCE '+str(OUT), flush=True)


def run():
    cs = OUT/'Generate.slang'
    cs.write_text('''RWTexture2D<float4> gOutput;
RWStructuredBuffer<uint> gValues;
cbuffer Params { uint2 dimensions; float bias; };
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
    if(any(p.xy>=dimensions)) return;
    gOutput[p.xy]=float4(p.x,p.y,p.x+p.y,1)+bias;
    if(p.y==0 && p.x<4) gValues[p.x]=p.x+10;
}
''')
    ps = OUT/'Transform.slang'
    ps.write_text('''Texture2D<float4> source;
StructuredBuffer<uint> values;
float4 main(float4 p:SV_Position):SV_Target0 { return source.Load(int3(p.xy,0))*2+values[0]; }
''')
    compute = {'shader': {'file': str(cs)}, 'resources': [
        {'name': 'color', 'direction': 'output', 'binding': 'gOutput', 'format': 'RGBA32Float', 'size': [17,9]},
        {'name': 'values', 'direction': 'output', 'binding': 'gValues', 'kind': 'structured_buffer', 'stride': 4, 'count': 4}],
        'uniforms': {'Params.dimensions': {'type': 'uint2', 'source': 'extent'},
                     'Params.bias': {'type': 'float', 'value': 0.25}}, 'dispatch': {'extent': 'color'}}
    fullscreen = {'shader': {'file': str(ps)}, 'resources': [
        {'name': 'source', 'direction': 'input', 'binding': 'source', 'format': 'RGBA32Float'},
        {'name': 'values', 'direction': 'input', 'binding': 'values', 'kind': 'structured_buffer', 'stride': 4, 'count': 4},
        {'name': 'color', 'direction': 'output', 'format': 'RGBA32Float', 'size': [17,9], 'slot': 0}]}
    # RED must reach the old mandatory Config constructor on an otherwise valid pass.
    first = falcor.createPass('CustomRenderPiplineComputePass', compute)
    from pipeline import make_graph
    authored_compute = copy.deepcopy(compute); authored_compute['shader']['file'] = cs.name
    authored_fullscreen = copy.deepcopy(fullscreen); authored_fullscreen['shader']['file'] = ps.name
    (OUT/'Fullscreen.json').write_text(json.dumps({'type':'CustomRenderPiplineFullscreenPass','properties':authored_fullscreen}))
    definition = {'version':1,'nodes':[
        {'name':'Generate','type':'CustomRenderPiplineComputePass','properties':authored_compute},
        {'name':'Transform','description':'Fullscreen.json'},
        {'name':'Blit','type':'BlitPass','properties':{'outputFormat':'RGBA32Float'}}],
        'edges':[['Generate.color','Transform.source'],['Generate.values','Transform.values'],['Transform.color','Blit.src']],
        'outputs':['Generate.color','Generate.values','Transform.color','Blit.dst']}
    (OUT/'Graph.json').write_text(json.dumps(definition))
    graph = make_graph('NeutralExecutors', OUT/'Graph.json')
    assert 'generate_schema' not in sys.modules and 'pipeline_snapshot' not in sys.modules
    assert 'extensions.ue_reference.transaction' not in sys.modules
    m.resizeFrameBuffer(17,9)
    m.ui = False
    m.addGraph(graph)
    m.setActiveGraph(graph)
    m.renderFrame()
    yy, xx = np.indices((9,17), dtype=np.float32)
    expected = np.stack((xx,yy,xx+yy,np.ones_like(xx)), axis=-1)+0.25
    np.testing.assert_array_equal(graph.getOutput('Generate.color').to_numpy(), expected)
    np.testing.assert_array_equal(np.asarray(graph.getOutput('Generate.values').to_numpy()).view(np.uint32).reshape(-1), np.arange(10,14,dtype=np.uint32))
    np.testing.assert_array_equal(graph.getOutput('Transform.color').to_numpy(), expected*2+10)
    np.testing.assert_array_equal(graph.getOutput('Blit.dst').to_numpy(), expected*2+10)
    props = dict(first.getDictionary())
    assert not (set(props) & {'schemaPath','sceneDefinition','pipelinePath','pipelineNode'})
    replacement = copy.deepcopy(compute)
    replacement['uniforms']['Params.bias']['value'] = 1.0
    graph.updatePass('Generate', replacement)
    graph.markOutput('Transform.color')
    m.renderFrame()
    np.testing.assert_array_equal(graph.getOutput('Transform.color').to_numpy(), (expected+0.75)*2+10)
    rejections = []
    for label, mutate in (
        ('wrong_binding', lambda p: p['resources'][0].update(binding='missing')),
        ('stride_mismatch', lambda p: p['resources'][1].update(stride=8)),
        ('bad_dispatch', lambda p: p.update(dispatch={'threads':[0,1,1]})),
        ('unknown_option', lambda p: p.update(unrelated=True)),
        ('implicit_exposure', lambda p: p['uniforms']['Params.bias'].update(source='preExposure')),
        ('legacy_macro', lambda p: p['resources'].append({'schema':'$packed','direction':'input'})),
    ):
        bad = copy.deepcopy(compute); mutate(bad)
        try:
            falcor.createPass('CustomRenderPiplineComputePass',bad)
        except RuntimeError as error:
            rejections.append({'case':label,'message':str(error)})
        else:
            raise AssertionError('Accepted '+label)
    bad = copy.deepcopy(fullscreen); bad['state'] = {'blend':'not-a-blend-mode'}
    try: falcor.createPass('CustomRenderPiplineFullscreenPass',bad)
    except RuntimeError as error: rejections.append({'case':'fullscreen_state','message':str(error)})
    else: raise AssertionError('Accepted invalid fullscreen state')
    return {'status':'passed','no_scene':True,'no_legacy_properties':True,'json_to_gpu':True,'compute_fullscreen_blit':True,
            'structured_buffer':True,'property_update':True,'rejections':rejections}


try:
    result = run()
except Exception as error:
    traceback.print_exc()
    result = {'status':'failed','error':str(error)}
(OUT/'result.json').write_text(json.dumps(result,indent=2))
print('NATIVE_PASS_'+result['status'].upper(), flush=True)
exit()
