"""Q1 native graph sizing, Mesh attachment inheritance and alias boundaries.

Run with Mogwai --headless --enable-debug-layer --script. Every invocation owns
its shaders/reports; no production source, retained UE ABI or snapshot is used.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts/customrenderpipline'), str(ROOT / 'build/m0-evidence/python')]
import falcor
import numpy as np
from pipeline import make_graph
from native_pipeline import load_graph_definition

PARENT = ROOT / 'build/native-framework-completion'
PARENT.mkdir(exist_ok=True)
OUT = Path(tempfile.mkdtemp(prefix='resource-composition-', dir=PARENT))
CASES = []
print('NATIVE_RESOURCE_COMPOSITION_EVIDENCE ' + str(OUT), flush=True)


def shader(name, text):
    path = OUT / name
    path.write_text(text, encoding='utf-8')
    return str(path)


def texture(name, direction='output', **kw):
    return dict(name=name, binding=name, direction=direction, format='RGBA32Float', **kw)


def node(name, file, ports, dispatch=None, **kw):
    return dict(name=name, type='CustomRenderPiplineComputePass', properties=dict(
        shader={'file': file}, resources=ports, dispatch=dispatch or {'extent': ports[-1]['name']}, **kw))


def graph(name, nodes, edges=(), outputs=None):
    definition = dict(version=1, nodes=nodes, edges=list(edges),
                      outputs=outputs or [nodes[-1]['name'] + '.' + nodes[-1]['properties']['resources'][-1]['name']])
    (OUT / (name + '.json')).write_text(json.dumps(definition, indent=2), encoding='utf-8')
    result = make_graph(name, definition, base_directory=OUT)
    m.addGraph(result)
    m.setActiveGraph(result)
    return result


def exact(value, expected):
    actual = np.asarray(value.to_numpy())
    np.testing.assert_array_equal(actual, np.broadcast_to(np.asarray(expected, dtype=actual.dtype), actual.shape))
    return hashlib.sha256(actual.tobytes()).hexdigest()


def reject(label, callback, message):
    try:
        callback()
    except (ValueError, RuntimeError, falcor.RuntimeError) as error:
        assert message.lower() in str(error).lower(), (label, str(error))
        return str(error).split('\n', 1)[0]
    raise AssertionError('Accepted invalid ' + label)


def sizing():
    generate = shader('Generate.slang', '''RWTexture2D<float4> result;
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
 uint w,h; result.GetDimensions(w,h); if(p.x<w&&p.y<h) result[p.xy]=float4(w,h,3,1); }
''')
    relative = shader('Relative.slang', '''Texture2D<float4> source; RWTexture2D<float4> result;
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
 uint w,h,sw,sh; result.GetDimensions(w,h); source.GetDimensions(sw,sh);
 if(p.x<w&&p.y<h) result[p.xy]=float4(sw,sh,w,h); }
''')
    mutate = shader('Mutate.slang', '''RWTexture2D<float4> shared;
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
 uint w,h; shared.GetDimensions(w,h); if(p.x<w&&p.y<h) shared[p.xy]+=float4(100,200,300,400); }
''')
    mesh_file = shader('Mesh.slang', '''#include "Scene/VertexAttrib.slangh"
import Scene.Raster;
VSOut vsMain(VSIn v) { return defaultVS(v); }
float4 psMain(VSOut v):SV_Target0 { return float4(101,202,303,1); }
''')
    nodes = [node('Viewport', generate, [texture('result')]),
             node('Fixed', generate, [texture('result', size=[53,37])])]
    edges, outputs = [], ['Viewport.result']
    for source, prefix in [('Viewport', 'View'), ('Fixed', 'Fix')]:
        last = source + '.result'
        for index, divisor in enumerate(([2,3], [3,2], [2,2])):
            name = prefix + str(index)
            nodes.append(node(name, relative, [texture('source', 'input'), texture('result',
                size={'relative_to': 'source', 'divisor': divisor})]))
            edges.append([last, name + '.source'])
            last = name + '.result'
            outputs.append(last)
        nodes.append(node(prefix + 'IO', mutate, [texture('shared', 'inputOutput')]))
        edges.append([last, prefix + 'IO.shared'])
        outputs.append(prefix + 'IO.shared')
    # Mesh targets use native connected reflection, not another size language.
    for label, target in [('LoadedMesh', {'load':'load'}), ('FixedMesh', {'size':[19,13]})]:
        nodes.append(dict(name=label, type='CustomRenderPiplineMeshDrawPass', properties={
            'shader': {'file':mesh_file, 'vertex':'vsMain', 'pixel':'psMain'},
            'colorTargets':[dict(name='color', format='RGBA32Float', slot=0, **target)],
            'state':{'cull_mode':'None'}}))
        outputs.append(label + '.color')
    # Use first half-size level (49x21+) so the fixture has both mesh and background pixels.
    edges.append(['View0.result', 'LoadedMesh.color'])
    m.loadScene(str(ROOT / 'scripts/customrenderpipline/reference_scene.pyscene'))
    g = graph('CompositionSizes', nodes, edges, outputs)
    frames = []
    for width, height in [(97,61), (113,79)]:
        m.resizeFrameBuffer(width, height)
        g.execute()
        rows = {}
        for initial, prefix in [((width,height), 'View'), ((53,37), 'Fix')]:
            sw, sh = initial
            for index, (dx,dy) in enumerate(((2,3),(3,2),(2,2))):
                w,h = (sw+dx-1)//dx, (sh+dy-1)//dy
                output = g.getOutput(prefix + str(index) + '.result')
                assert (output.width, output.height) == (w,h)
                expected = np.array([sw,sh,w,h], np.float32)
                if index == 2:
                    expected += [100,200,300,400]  # InputOutput is the same allocation.
                    exact(g.getOutput(prefix + 'IO.shared'), expected)
                if index != 0 or prefix != 'View':
                    exact(output, expected)
                rows[prefix + str(index)] = [w,h]
                sw,sh = w,h
        half_w,half_h = (width+1)//2,(height+2)//3
        loaded = np.asarray(g.getOutput('LoadedMesh.color').to_numpy())
        assert loaded.shape == (half_h,half_w,4)
        drawn = np.all(loaded == np.array([101,202,303,1], np.float32), axis=-1)
        assert drawn.any() and (~drawn).any(), 'Fixture must distinguish rendered Mesh and preserved background'
        np.testing.assert_array_equal(loaded[~drawn], np.broadcast_to(
            np.array([width,height,half_w,half_h],np.float32), loaded[~drawn].shape))
        fixed = np.asarray(g.getOutput('FixedMesh.color').to_numpy())
        assert fixed.shape == (13,19,4) and np.any(fixed[...,3] == 1)
        frames.append(dict(viewport=[width,height], extents=rows,
                           loaded_mesh_pixels=int(drawn.sum()), fixed_mesh_pixels=int(np.count_nonzero(fixed[...,3]))))
    m.removeGraph(g)
    CASES.append(dict(case='multihop_fixed_inputOutput_mesh_sizes', status='passed', frames=frames))


def buffer_alias(kind, mode):
    structured = kind == 'structured_buffer'
    def port(name, direction):
        return dict(name=name, binding=name, direction=direction, kind=kind,
                    **({'stride':16,'count':8} if structured else {'bytes':128}))
    def declaration(name, write):
        return ('RW' if write else '') + ('StructuredBuffer<uint4> ' if structured else 'ByteAddressBuffer ') + name + ';'
    def value(name):
        return name + '[p.x].x' if structured else name + '.Load(p.x*16)'
    def put(name):
        return name + '[p.x]=uint4(p.x+7,11,13,17);' if structured else name + '.Store4(p.x*16,uint4(p.x+7,11,13,17));'
    generate = shader(kind + 'Generate.slang', declaration('values', True) +
        '\n[numthreads(8,1,1)] void main(uint3 p:SV_DispatchThreadID){if(p.x<8){' + put('values') + '}}')
    left_write, right_write = mode == 'two_writers', mode != 'readonly'
    def props(write_left, write_right):
        file = shader(kind + str(write_left) + str(write_right) + '.slang',
            declaration('left',write_left) + declaration('right',write_right) + '''RWTexture2D<uint> proof;
[numthreads(8,1,1)] void main(uint3 p:SV_DispatchThreadID){if(p.x<8){proof[p.xy]=''' +
            value('left') + '+' + value('right') + ';' + (put('left') if write_left else '') +
            (put('right') if write_right else '') + '}}')
        return node('Alias', file, [port('left','inputOutput' if write_left else 'input'),
                    port('right','inputOutput' if write_right else 'input'),
                    dict(name='proof',binding='proof',direction='output',format='R32Uint',size=[8,1],clear=[0,0,0,0])],
                    {'threads':[8,1,1]})['properties']
    properties = props(left_write,right_write)
    g = graph(kind + '_' + mode, [node('Produce',generate,[port('values','output')],{'threads':[8,1,1]}),
        dict(name='Alias',type='CustomRenderPiplineComputePass',properties=properties)],
        [['Produce.values','Alias.left'],['Produce.values','Alias.right']], ['Alias.proof'])
    row = dict(case=kind + '_' + mode)
    if mode != 'readonly':
        row['error'] = reject(mode,g.execute,'alias creates conflicting access')
        proof = g.getOutput('Alias.proof')
        sentinel = np.full((1,8),0x1234abcd,np.uint32)
        proof.from_numpy(sentinel)
        reject(mode + '_before_clear',g.execute,'alias creates conflicting access')
        # Falcor removes unit dimensions from native ndarray views.
        np.testing.assert_array_equal(np.asarray(proof.to_numpy()).reshape(1,8),sentinel)
        row['rejected_before_clear'] = True
        g.updatePass('Alias',props(False,False))
    g.execute()
    expected = 2 * (np.arange(8,dtype=np.uint32) + 7)
    np.testing.assert_array_equal(np.asarray(g.getOutput('Alias.proof').to_numpy()).reshape(8),expected)
    row.update(status='passed', recovery_bytes_exact=True)
    CASES.append(row)
    m.removeGraph(g)


def limits_and_loader():
    file = shader('Limits.slang', '''RWTexture2D<uint> proof;
[numthreads(2,1,1)] void main(uint3 p:SV_DispatchThreadID) { InterlockedAdd(proof[uint2(0,0)],1); }
''')
    props = node('Limits',file,[dict(name='proof',binding='proof',direction='output',format='R32Uint',
        clear=[0,0,0,0],max_size=[10,10])],{'groups':{'extent':'proof','axes':[2,3,2]}})['properties']
    errors = []
    for axis in ['depth',0,65536]:
        bad = copy.deepcopy(props);bad['dispatch']['groups']['axes'][0] = axis
        errors.append(reject('invalid_group_'+str(axis), lambda:falcor.createPass('CustomRenderPiplineComputePass',bad),'Group axis requires'))
    bad = copy.deepcopy(props);bad['dispatch']={'threads':[4294967295,1,1]}
    errors.append(reject('thread_rounding', lambda:falcor.createPass('CustomRenderPiplineComputePass',bad),'group limit or uint32'))
    g = graph('LimitsAndRecovery',[dict(name='Limits',type='CustomRenderPiplineComputePass',properties=props)])
    m.resizeFrameBuffer(17,9)
    errors.append(reject('max_size',g.execute,'max_size contract'))
    output = g.getOutput('Limits.proof')
    sentinel = np.full((9,17),0x543210ab,np.uint32)
    output.from_numpy(sentinel)
    reject('max_size_before_clear',g.execute,'max_size contract')
    np.testing.assert_array_equal(output.to_numpy(),sentinel)
    m.resizeFrameBuffer(9,7)
    g.execute()
    expected = np.zeros((7,9),np.uint32);expected[0,0]=24
    np.testing.assert_array_equal(g.getOutput('Limits.proof').to_numpy(),expected)
    m.removeGraph(g)
    # Loader rejects ambiguous ownership without constructing a GPU graph.
    definition = dict(version=1,nodes=[{'name':n,'type':'BlitPass'} for n in ['A','B','C']],
                      edges=[['A.dst','C.src'],['B.dst','C.src']],outputs=['C.dst'])
    message = reject('duplicate_destination',lambda:load_graph_definition(definition),'duplicate destination')
    definition['edges'].pop()
    assert load_graph_definition(definition)['edges'] == [['A.dst','C.src']]
    CASES.append(dict(case='group_max_size_duplicate_destination',status='passed',errors=errors,
        max_size_rejected_before_clear=True, valid_group_count=24, recovery_bytes_exact=True,loader_error=message))


try:
    m.ui = False
    m.clock.pause()
    m.clock.time = 0
    sizing()
    for resource_kind in ['raw_buffer','structured_buffer']:
        for access_mode in ['readonly','srv_uav','two_writers']:
            buffer_alias(resource_kind,access_mode)
    limits_and_loader()
    result = dict(status='passed',backend='D3D12',cases=CASES,
                  scope='finite graph combinations; not whole-backend or all-format certification')
except Exception as error:
    traceback.print_exc()
    result = dict(status='failed',error=str(error),cases=CASES)
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print('NATIVE_RESOURCE_COMPOSITION_'+result['status'].upper(),flush=True)
exit(0 if result['status']=='passed' else 1)
