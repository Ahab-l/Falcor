"""Native GPU regression for generic resource shapes, views, sizing and dispatch."""
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
from pipeline import make_graph

PARENT = ROOT / 'build/native-generic-migration'
PARENT.mkdir(exist_ok=True)
OUT = Path(tempfile.mkdtemp(prefix='resources-', dir=PARENT))
print('NATIVE_RESOURCE_SHAPES_EVIDENCE ' + str(OUT), flush=True)


def shader(name, source):
    (OUT / name).write_text(source)


def run(*, observe=False):
    shader('CubeWrite.slang', '''RWTexture2DArray<float4> target;
cbuffer Params { uint mipIndex; uint2 extent; };
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
 if(all(p.xy<extent) && p.z<6) target[p]=float4(p.z+1,mipIndex+1,p.x+p.y*extent.x,1); }
''')
    shader('CubeRead.slang', '''TextureCube<float4> source; SamplerState pointSampler; RWTexture2D<float4> result;
cbuffer Params { uint rows; };
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
 if(p.x>=6 || p.y>=rows)return;
 float3 d[6]={float3(1,0,0),float3(-1,0,0),float3(0,1,0),float3(0,-1,0),float3(0,0,1),float3(0,0,-1)};
 result[p.xy]=source.SampleLevel(pointSampler,d[p.x],float(p.y)); }
''')
    shader('BufferWrite.slang', '''RWStructuredBuffer<float4> values;
[numthreads(8,1,1)] void main(uint3 p:SV_DispatchThreadID){if(p.x<8)values[p.x]=float4(p.x+1,3*p.x+2,17-p.x,.5*p.x);}
''')
    shader('BufferRead.slang', '''StructuredBuffer<float4> values; RWTexture2D<float4> result;
[numthreads(8,1,1)] void main(uint3 p:SV_DispatchThreadID){if(p.x<8)result[p.xy]=values[p.x]*float4(2,3,4,8)+float4(11,13,17,19);}
''')
    shader('Dynamic.slang', '''RWTexture2D<uint> counts; cbuffer Params { uint2 extent; };
[numthreads(4,2,1)] void main(uint3 g:SV_GroupID){if(g.x<extent.y&&g.y<extent.x&&g.z<2)InterlockedAdd(counts[g.yx],1);}
''')
    shader('Relative.slang', '''Texture2D<uint> source; RWTexture2D<float4> target; cbuffer Params { uint2 extent; };
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID){if(any(p.xy>=extent))return;uint w,h;source.GetDimensions(w,h);target[p.xy]=float4(w,h,extent);}
''')
    shader('Mask.slang', 'float4 main(float4 p:SV_Position):SV_Target0{return float4(0,.5,0,.25);}')

    cube = {'name':'cube','binding':'target','kind':'textureCube','format':'RGBA32Float','size':[16,16],'mip_count':4}
    nodes, edges = [], []
    for mip in range(4):
        port = dict(cube, direction='output' if mip == 0 else 'inputOutput', view={'mip':mip})
        nodes.append({'name':f'Write{mip}','type':'CustomRenderPiplineComputePass','properties':{
            'shader':{'file':'CubeWrite.slang'},'resources':[port],
            'uniforms':{'Params.mipIndex':{'type':'uint','value':mip},'Params.extent':{'type':'uint2','source':'extent'}},
            'dispatch':{'extent':'cube'}}})
        if mip: edges.append([f'Write{mip-1}.cube',f'Write{mip}.cube'])
    nodes.append({'name':'ReadCube','type':'CustomRenderPiplineComputePass','properties':{
        'shader':{'file':'CubeRead.slang'},'resources':[dict(cube,binding='source',direction='input'),
        {'name':'result','binding':'result','direction':'output','format':'RGBA32Float','size':[6,4]}],
        'samplers':{'pointSampler':{'filter':'Point','address':'Clamp'}},
        'uniforms':{'Params.rows':{'type':'uint','value':4}},'dispatch':{'extent':'result'}}})
    edges.append(['Write3.cube','ReadCube.cube'])
    buf = lambda name,binding,direction: {'name':name,'binding':binding,'direction':direction,'kind':'structured_buffer','stride':16,'count':8}
    nodes += [
      {'name':'BufferWrite','type':'CustomRenderPiplineComputePass','properties':{'shader':{'file':'BufferWrite.slang'},'resources':[buf('values','values','output')],'dispatch':{'threads':[8,1,1]}}},
      {'name':'BufferRead','type':'CustomRenderPiplineComputePass','properties':{'shader':{'file':'BufferRead.slang'},'resources':[buf('values','values','input'),{'name':'result','binding':'result','direction':'output','format':'RGBA32Float','size':[8,1]}],'dispatch':{'threads':[8,1,1]}}},
      {'name':'Groups','type':'CustomRenderPiplineComputePass','properties':{'shader':{'file':'Dynamic.slang'},'resources':[{'name':'counts','binding':'counts','direction':'output','format':'R32Uint','clear':[0,0,0,0],'max_size':[32,16]}],'uniforms':{'Params.extent':{'type':'uint2','source':'extent'}},'dispatch':{'groups':{'extent':'counts','axes':['height','width',2]}}}},
      {'name':'Half','type':'CustomRenderPiplineComputePass','properties':{'shader':{'file':'Relative.slang'},'resources':[{'name':'source','binding':'source','direction':'input','format':'R32Uint'},{'name':'target','binding':'target','direction':'output','format':'RGBA32Float','size':{'relative_to':'source','divisor':[2,2]}}],'uniforms':{'Params.extent':{'type':'uint2','source':'extent'}},'dispatch':{'extent':'target'}}},
      {'name':'Mask','type':'CustomRenderPiplineFullscreenPass','properties':{'shader':{'file':'Mask.slang'},'resources':[{'name':'mask','direction':'output','format':'BGRA8Unorm','slot':0,'size':[7,5],'clear':[1,1,1,1],'writeMask':[True,True,False,False]}],'state':{'blend':'alpha'}}}]
    edges += [['BufferWrite.values','BufferRead.values'],['Groups.counts','Half.source']]
    # Mogwai previews the first marked output with stock Blit: use a 2D image,
    # not the raw Cube that remains available for explicit observer reads.
    outputs = ['ReadCube.result','BufferWrite.values','BufferRead.result','Groups.counts','Half.target','Mask.mask','Write3.cube']
    definition = {'version':1,'nodes':nodes,'edges':edges,'outputs':outputs}
    path=OUT/'Graph.json';path.write_text(json.dumps(definition,indent=2))
    graph=make_graph('NativeResourceShapes',path)
    m.ui=False;m.addGraph(graph);m.setActiveGraph(graph)
    frames=[]
    for w,h in ((17,9),(29,7)):
        m.resizeFrameBuffer(w,h);m.renderFrame()
        counts=np.asarray(graph.getOutput('Groups.counts').to_numpy())
        np.testing.assert_array_equal(counts,np.full((h,w),16,np.uint32))
        half=np.asarray(graph.getOutput('Half.target').to_numpy())
        expected_size=((w+1)//2,(h+1)//2)
        assert (graph.getOutput('Half.target').width,graph.getOutput('Half.target').height)==expected_size
        np.testing.assert_array_equal(half,np.broadcast_to(np.array([w,h,*expected_size],np.float32),half.shape))
        frames.append([w,h])
    expected_buffer=np.array([[i+1,3*i+2,17-i,.5*i] for i in range(8)],np.float32)
    actual_buffer=np.frombuffer(graph.getOutput('BufferWrite.values').to_numpy().tobytes(),np.float32).reshape(8,4)
    np.testing.assert_array_equal(actual_buffer,expected_buffer)
    np.testing.assert_array_equal(np.asarray(graph.getOutput('BufferRead.result').to_numpy()).reshape(8,4),expected_buffer*np.array([2,3,4,8])+np.array([11,13,17,19]))
    cube_values=np.asarray(graph.getOutput('ReadCube.result').to_numpy())
    expected_cube=np.empty((4,6,4),np.float32)
    for mip in range(4):
        width=16>>mip
        for face in range(6): expected_cube[mip,face]=[face+1,mip+1,width//2*(1+width),1]
    np.testing.assert_array_equal(cube_values,expected_cube)
    mask=np.asarray(graph.getOutput('Mask.mask').to_numpy()).reshape(5,7,4)
    np.testing.assert_array_equal(mask,np.broadcast_to(np.array([255,223,191,255],np.uint8),mask.shape))

    if observe:
        from observer import PipelineObserver
        observer = PipelineObserver(graph)
        record = observer.catalog().select(['Write3.cube'])[0]
        assert record.kind == 'textureCube' and record.mip_count == 4
        views = []
        for mip in range(4):
            width = 16 >> mip
            for face in range(6):
                raw = observer.read('Write3.cube', mip=mip, slice=face)
                actual = np.frombuffer(raw['data'], np.float32).reshape(width, width, 4)
                expected = np.empty_like(actual)
                expected[..., 0] = face+1; expected[..., 1] = mip+1
                expected[..., 2] = np.arange(width*width).reshape(width,width); expected[..., 3] = 1
                np.testing.assert_array_equal(actual, expected)
                views.append({'name':'Write3.cube','mip':mip,'slice':face})
        atlas, layout = observer.atlas_views(views, tile_extent=(16,16), columns=6)
        pixels = np.asarray(atlas.to_numpy())
        for mip in range(4):
            width = 16 >> mip
            index = np.arange(16)*width//16
            for face in range(6):
                tile = pixels[mip*16:(mip+1)*16, face*16:(face+1)*16]
                np.testing.assert_array_equal(tile[...,0], face+1)
                np.testing.assert_array_equal(tile[...,1], mip+1)
                np.testing.assert_array_equal(tile[...,2], index[:,None]*width+index[None,:])
        for view in ({'mip':4}, {'slice':6}, {'mip':-1}):
            try: observer.read('Write3.cube', **view)
            except (ValueError, RuntimeError, falcor.RuntimeError): pass
            else: raise AssertionError('Accepted invalid observer view')
        np.testing.assert_array_equal(graph.getOutput('ReadCube.result').to_numpy(), expected_cube)

    rejections=[]
    for label, mutate in (
      ('structured_stride',lambda d:d['nodes'][5]['properties']['resources'][0].update(stride=32)),
      ('relative_divisor',lambda d:d['nodes'][8]['properties']['resources'][1].update(size={'relative_to':'source','divisor':[0,2]})),
      ('group_axis',lambda d:d['nodes'][7]['properties']['dispatch'].update(groups={'extent':'counts','axes':['depth',1,1]})),
      ('partial_cube_view',lambda d:d['nodes'][4]['properties']['resources'][0].update(view={'mip':4})),
    ):
        bad=copy.deepcopy(definition);mutate(bad)
        try:make_graph('Rejected'+label,bad,base_directory=OUT)
        except (RuntimeError, falcor.RuntimeError, ValueError) as error:rejections.append({'case':label,'message':str(error)})
        else:raise AssertionError('Accepted invalid '+label)
    return {'status':'passed','ordinary_make_graph':True,'frames':frames,'structured_uav_srv_exact':True,
            'cube_faces_and_mips_exact':True,'relative_size_exact':True,'mapped_group_dispatch_exact':True,
            'fullscreen_mask_exact':True,'observer_faces_and_mips':24 if observe else 0,'gpu_atlas_exact':observe,'rejections':rejections}


if not globals().get('_CRP_EMBEDDED'):
    try:
        result=run()
    except Exception as error:
        traceback.print_exc();result={'status':'failed','error':str(error)}
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('NATIVE_RESOURCE_SHAPES_'+result['status'].upper(),flush=True)
    exit()
