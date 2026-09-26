"""Native History advances on ordinary graph execution, not old transactions."""
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
from pipeline import make_graph

OUT = Path(tempfile.mkdtemp(prefix='history-', dir=ROOT/'build/resource-history-migration'))
print('NATIVE_HISTORY_EVIDENCE '+str(OUT), flush=True)


def run():
    shader = OUT/'Increment.slang'
    shader.write_text('''Texture2D<float4> previous;
Texture2D<uint4> previousID;
Texture2D<uint4> status;
RWTexture2D<float4> current;
RWTexture2D<uint4> currentID;
cbuffer Params { uint2 extent; float increment; };
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
    if(any(p.xy>=extent)) return;
    current[p.xy]=(status[uint2(0)].x ? previous[p.xy] : float4(0))+increment;
    if(p.y==0 && p.x<2) currentID[p.xy]=status[uint2(0)].x ? previousID[p.xy]+1 : uint4(0xffffffff,0x80000000,123,7);
}
''')
    resources = [{'name':'color','format':'RGBA32Float'}, {'name':'ids','format':'RGBA32Uint','size':[2,1]}]
    history = {'key':'accumulation','resources':resources}
    # RED: old mandatory Config rejects this valid native resource declaration.
    falcor.createPass('CustomRenderPiplineHistoryReadPass', history)
    definition = {'version':1,'nodes':[
        {'name':'Previous','type':'CustomRenderPiplineHistoryReadPass','properties':copy.deepcopy(history)},
        {'name':'Add','type':'CustomRenderPiplineComputePass','properties':{
            'shader':{'file':shader.name},'resources':[
                {'name':'previous','direction':'input','binding':'previous','format':'RGBA32Float'},
                {'name':'previousID','direction':'input','binding':'previousID','format':'RGBA32Uint','size':[2,1]},
                {'name':'status','direction':'input','binding':'status','format':'RGBA32Uint','size':[1,1]},
                {'name':'current','direction':'output','binding':'current','format':'RGBA32Float'},
                {'name':'currentID','direction':'output','binding':'currentID','format':'RGBA32Uint','size':[2,1]}],
            'uniforms':{'Params.extent':{'type':'uint2','source':'extent'},'Params.increment':{'type':'float','value':1}},
            'dispatch':{'extent':'current'}}},
        {'name':'Save','type':'CustomRenderPiplineHistoryWritePass','properties':copy.deepcopy(history)}],
        'edges':[['Previous.color','Add.previous'],['Previous.ids','Add.previousID'],['Previous.status','Add.status'],
                 ['Add.current','Save.color'],['Add.currentID','Save.ids']],
        'outputs':['Previous.color','Previous.status','Add.current','Add.currentID','Save.status']}
    path = OUT/'Graph.json'; path.write_text(json.dumps(definition))
    m.resizeFrameBuffer(7,5); m.clock.pause(); m.ui=False
    graph = make_graph('NativeHistory', path)
    m.addGraph(graph); m.setActiveGraph(graph)
    def frame(g, expected):
        m.setActiveGraph(g);m.renderFrame()
        actual = np.asarray(g.getOutput('Add.current').to_numpy())
        np.testing.assert_array_equal(actual, np.full_like(actual, expected))
        previous = np.asarray(g.getOutput('Previous.color').to_numpy())
        np.testing.assert_array_equal(previous, np.full_like(previous, expected-1))
        status = np.asarray(g.getOutput('Previous.status').to_numpy()).reshape(-1)
        assert int(status[0]) == int(expected > 1)
        seed = np.array([0xffffffff,0x80000000,123,7],dtype=np.uint32)
        ids = np.asarray(g.getOutput('Add.currentID').to_numpy()).reshape(2,4)
        np.testing.assert_array_equal(ids, np.tile(seed+np.uint32(expected-1),(2,1)))
    frame(graph,1);frame(graph,2);frame(graph,3)
    # Paused wall clock does not freeze history; every writer execution counts.
    info = json.loads(falcor.customRenderPiplineHistoryInfo(graph))
    assert info['accumulation']['updates'] == 3
    second = make_graph('IndependentHistory', path)
    m.addGraph(second)
    frame(second,1);frame(graph,4);frame(second,2)
    falcor.customRenderPiplineResetHistory(graph)
    frame(graph,1);frame(graph,2)
    falcor.customRenderPiplineResetHistory(graph,'accumulation')
    frame(graph,1)
    try:falcor.customRenderPiplineResetHistory(graph,'missing')
    except RuntimeError:pass
    else:raise AssertionError('Accepted unknown history reset key')
    frame(graph,2)
    m.resizeFrameBuffer(11,3);frame(graph,1)
    assert graph.getOutput('Add.current').width == 11
    assert graph.getOutput('Add.currentID').width == 2
    falcor.customRenderPiplineBindHistory(graph)
    frame(graph,1)
    # Replacing a history node requires explicit rebind, not stale shared state.
    graph.updatePass('Save',copy.deepcopy(history))
    try:m.renderFrame()
    except RuntimeError as error:assert 'bound' in str(error)
    else:raise AssertionError('Unbound replacement writer executed')
    falcor.customRenderPiplineBindHistory(graph);frame(graph,1)
    # A Scene transition invalidates history without old scene identity hashing.
    m.loadScene(str(ROOT/'scripts/customrenderpipline/examples/schema_gbuffer/Scene.pyscene'))
    frame(graph,1);frame(graph,2)
    m.loadScene(str(ROOT/'scripts/customrenderpipline/examples/schema_gbuffer/Scene.pyscene'))
    frame(graph,1)
    rejections = []
    for label,change in [
        ('missing_pair',lambda d:d['nodes'][2]['properties'].update(key='other')),
        ('mismatched_format',lambda d:d['nodes'][2]['properties']['resources'][0].update(format='RGBA16Float')),
        ('mismatched_size',lambda d:d['nodes'][2]['properties']['resources'][1].update(size=[1,2])),
        ('pruned_writer',lambda d:d['outputs'].remove('Save.status')),
        ('bad_format',lambda d:d['nodes'][0]['properties']['resources'][0].update(format='D32Float')),
        ('bad_size',lambda d:d['nodes'][0]['properties']['resources'][0].update(size=[True,2])),
        ('unknown_option',lambda d:d['nodes'][0]['properties'].update(epoch=0)),
        ('duplicate_reader',lambda d:d['nodes'].append(dict(copy.deepcopy(d['nodes'][0]),name='Duplicate'))),
        ('unordered_reader',lambda d:d['edges'].__setitem__(slice(0,3),[])),
    ]:
        bad=copy.deepcopy(definition);change(bad)
        try:make_graph('InvalidHistory',bad,base_directory=OUT)
        except (RuntimeError,ValueError) as error:rejections.append({'case':label,'message':str(error)})
        else:raise AssertionError('Accepted '+label)
    # Two keys in one graph do not alias storage.
    both=copy.deepcopy(definition)
    extra=copy.deepcopy(definition)
    for node in extra['nodes']:
        node['name'] += 'B'
        if 'key' in node['properties']:node['properties']['key']='second'
    def remap(endpoint):
        node,_,port=endpoint.partition('.')
        return node+'B'+('.'+port if port else '')
    both['nodes']+=extra['nodes']
    both['edges'] += [[remap(a),remap(b)] for a,b in extra['edges']]
    both['outputs'] += [remap(o) for o in extra['outputs']]
    two=make_graph('TwoKeys',both,base_directory=OUT);m.addGraph(two);m.setActiveGraph(two)
    m.renderFrame();m.renderFrame()
    falcor.customRenderPiplineResetHistory(two,'second');m.renderFrame()
    assert np.all(two.getOutput('Add.current').to_numpy()==3)
    assert np.all(two.getOutput('AddB.current').to_numpy()==1)
    # Publication belongs to the writer, not the success of later passes.
    bad_shader=OUT/'LateFailure.slang'
    bad_shader.write_text('''float4 vsMain(float3 p:POSITION):SV_Position { return float4(p,1); }
float4 psMain():SV_Target0 { return 1; }
''')
    late=copy.deepcopy(definition)
    late['nodes'].append({'name':'LateFailure','type':'CustomRenderPiplineMeshDrawPass','properties':{
        'shader':{'file':str(bad_shader),'vertex':'vsMain','pixel':'psMain'},'instanceIDs':[],
        'colorTargets':[{'name':'color','format':'RGBA32Float','slot':0}]}})
    late['edges'].append(['Save','LateFailure']);late['outputs'].append('LateFailure.color')
    failed=make_graph('WriterBeforeFailure',late,base_directory=OUT);m.addGraph(failed);m.setActiveGraph(failed)
    for updates in (1,2):
        try:m.renderFrame()
        except RuntimeError as error:assert 'gScene' in str(error)
        else:raise AssertionError('Late pass unexpectedly succeeded')
        assert json.loads(falcor.customRenderPiplineHistoryInfo(failed))['accumulation']['updates']==updates
        assert np.all(failed.getOutput('Add.current').to_numpy()==updates)
    m.setActiveGraph(graph);m.removeGraph(failed)
    assert 'generate_schema' not in sys.modules and 'pipeline_snapshot' not in sys.modules
    assert 'extensions.ue_reference.transaction' not in sys.modules
    return {'status':'passed','ordinary_execution':True,'integer_bits':True,'paused_clock_counts_executions':True,
            'graph_and_key_isolation':True,'reset':True,'resize':True,'rebind':True,'scene_replacement':True,
            'no_legacy_imports':True,'writer_publication_not_transactional':True,'rejections':rejections}


try: result=run()
except Exception as error:
    traceback.print_exc();result={'status':'failed','error':str(error)}
(OUT/'result.json').write_text(json.dumps(result,indent=2))
print('NATIVE_HISTORY_'+result['status'].upper(),flush=True)
exit()
