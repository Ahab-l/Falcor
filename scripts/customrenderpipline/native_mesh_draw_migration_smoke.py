"""Native MeshDraw selection/attachments without a legacy material or view ABI."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts/customrenderpipline'),str(ROOT/'build/m0-evidence/python')]
import falcor
import numpy as np
OUT=Path(tempfile.mkdtemp(prefix='mesh-',dir=ROOT/'build/native-pass-migration'))
print('NATIVE_MESH_DRAW_EVIDENCE '+str(OUT),flush=True)


def run():
    shader=OUT/'Mesh.slang'
    shader.write_text('''#include "Scene/VertexAttrib.slangh"
import Scene.Raster;
cbuffer Transform { float4x4 projection; };
VSOut vsMain(VSIn v) {
    VSOut o=defaultVS(v);
#ifdef EXPLICIT_VIEW
    o.posH=mul(projection,o.posH);
#endif
#ifdef FLIP_FACING
    o.posH.x=-o.posH.x;
#endif
    return o;
}
float4 psMain(VSOut v):SV_Target0 { return float4(float(v.instanceID.index),v.posW.xy,1); }
''')
    props={'shader':{'file':str(shader),'vertex':'vsMain','pixel':'psMain'},
           'colorTargets':[{'name':'color','format':'RGBA32Float','slot':0}],
           'depthTarget':{'name':'depth','format':'D32Float'},
           'state':{'cull_mode':'Back'}}
    # RED should fail solely on the old mandatory Config, before loading a scene.
    falcor.createPass('CustomRenderPiplineMeshDrawPass',props)
    flags = falcor.SceneBuilderFlags.NonIndexedVertices if os.environ.get('CRP_NATIVE_NONINDEXED') else falcor.SceneBuilderFlags.Default
    m.loadScene(str(ROOT/'scripts/customrenderpipline/reference_scene.pyscene'),flags)
    m.resizeFrameBuffer(128,72);m.clock.pause();m.clock.time=0;m.ui=False;m.renderFrame()
    all_ids=list(m.scene.get_raster_instance_ids())
    blue=list(m.scene.get_raster_instance_ids(['blue']))
    assert blue and set(blue)<set(all_ids)
    graph=falcor.RenderGraph('NativeMeshDraw')
    for label,ids in [('All',None),('Blue',blue),('Empty',[])]:
        p=copy.deepcopy(props)
        if ids is not None:p['instanceIDs']=ids
        graph.addPass(falcor.createPass('CustomRenderPiplineMeshDrawPass',p),label)
        graph.addPass(falcor.createPass('CustomRenderPiplineGBufferPass',{} if ids is None else {'instanceIDs':ids}),label+'Reference')
        for port in ('color','depth'):graph.markOutput(label+'.'+port)
        for port in ('normal','depth'):graph.markOutput(label+'Reference.'+port)
    load=copy.deepcopy(props)
    load['instanceIDs']=[]
    load['colorTargets'][0]['load']='load'
    load['depthTarget']['load']='load'
    graph.addPass(falcor.createPass('CustomRenderPiplineMeshDrawPass',load),'Preserve')
    graph.addEdge('All.color','Preserve.color');graph.addEdge('All.depth','Preserve.depth')
    graph.markOutput('Preserve.color')
    m.addGraph(graph);m.setActiveGraph(graph);m.renderFrame()
    arrays={}
    for label in ('All','Blue','Empty'):
        color=np.array(graph.getOutput(label+'.color').to_numpy(),copy=True)
        mask=color[...,3]>0
        reference=graph.getOutput(label+'Reference.normal').to_numpy()[...,3]>0
        np.testing.assert_array_equal(mask,reference)
        np.testing.assert_allclose(graph.getOutput(label+'.depth').to_numpy(),graph.getOutput(label+'Reference.depth').to_numpy(),atol=1e-7,rtol=0)
        arrays[label]=color
    np.testing.assert_array_equal(graph.getOutput('Preserve.color').to_numpy(),arrays['All'])
    assert np.any(arrays['Blue'][...,3]) and not np.any(arrays['Empty'])
    assert set(np.unique(arrays['Blue'][...,0][arrays['Blue'][...,3]>0]).astype(int))<=set(blue)
    update=copy.deepcopy(props);update['instanceIDs']=blue
    graph.updatePass('Empty',update);m.renderFrame()
    np.testing.assert_array_equal(graph.getOutput('Empty.color').to_numpy(),arrays['Blue'])
    # Native material names are not keys into any second material table.
    material=m.scene.get_material(name='blue'); material.name='NativeOnlyRenamed'
    m.renderFrame()
    np.testing.assert_array_equal(graph.getOutput('Blue.color').to_numpy(),arrays['Blue'])
    sided_props=copy.deepcopy(props)
    sided_props['instanceIDs']=blue
    sided_props['shader']['defines']={'FLIP_FACING':'1'}
    sided_graph=falcor.RenderGraph('NativeMaterialCulling')
    for label,cull in [('Material','Material'),('Back','Back'),('None','None')]:
        p=copy.deepcopy(sided_props);p['state']['cull_mode']=cull
        sided_graph.addPass(falcor.createPass('CustomRenderPiplineMeshDrawPass',p),label)
        sided_graph.markOutput(label+'.color')
    m.addGraph(sided_graph);m.setActiveGraph(sided_graph)
    material.doubleSided=False;m.renderFrame()
    back=np.array(sided_graph.getOutput('Back.color').to_numpy(),copy=True)
    unculled=np.array(sided_graph.getOutput('None.color').to_numpy(),copy=True)
    assert np.any(back!=unculled), 'Fixture must distinguish material culling'
    np.testing.assert_array_equal(sided_graph.getOutput('Material.color').to_numpy(),back)
    material.doubleSided=True;m.renderFrame()
    np.testing.assert_array_equal(sided_graph.getOutput('Material.color').to_numpy(),unculled)
    material.doubleSided=False;m.renderFrame()
    np.testing.assert_array_equal(sided_graph.getOutput('Material.color').to_numpy(),back)
    m.setActiveGraph(graph);m.removeGraph(sided_graph)
    m.loadScene(str(ROOT/'scripts/customrenderpipline/reference_scene.pyscene'),flags);m.renderFrame()
    np.testing.assert_array_equal(graph.getOutput('All.color').to_numpy(),arrays['All'])
    explicit=copy.deepcopy(props)
    explicit['shader']['defines']={'EXPLICIT_VIEW':'1'}
    explicit['instanceIDs']=blue
    explicit['view_projection']=[[1,0,0,0],[0,1,0,0],[0,0,0,0.25],[0,0,0,1]]
    explicit['view_projection_binding']='Transform.projection'
    explicit['viewport']=[8,4,96,56]
    explicit['depthTarget']['clear']=0.75
    explicit['state'].update(depth_func='Always',depth_write=True)
    override=falcor.RenderGraph('ExplicitNativeState')
    override.addPass(falcor.createPass('CustomRenderPiplineMeshDrawPass',explicit),'Mesh')
    override.markOutput('Mesh.color');override.markOutput('Mesh.depth')
    m.addGraph(override);m.setActiveGraph(override);m.renderFrame()
    color=np.asarray(override.getOutput('Mesh.color').to_numpy())
    depth=np.asarray(override.getOutput('Mesh.depth').to_numpy()).reshape(72,128)
    mask=color[...,3]>0
    assert mask.any() and not mask[:4].any() and not mask[60:].any() and not mask[:,:8].any() and not mask[:,104:].any()
    np.testing.assert_allclose(depth[mask],0.25,atol=1e-7,rtol=0)
    np.testing.assert_array_equal(depth[~mask],np.full_like(depth[~mask],0.75))
    # Scene ID validity is checked before this executor clears its attachments.
    invalid=copy.deepcopy(props);invalid['instanceIDs']=[2**31]
    invalid_graph=falcor.RenderGraph('OutOfSceneRange')
    invalid_graph.addPass(falcor.createPass('CustomRenderPiplineMeshDrawPass',invalid),'Mesh')
    invalid_graph.markOutput('Mesh.color')
    m.addGraph(invalid_graph);m.setActiveGraph(invalid_graph)
    try:m.renderFrame()
    except RuntimeError as error:assert 'out of range' in str(error)
    else:raise AssertionError('Accepted out-of-Scene instance ID')
    # Allocation already exists after the first failed execution. Seed it and
    # execute again to prove validation does not clear or draw into that output.
    output=invalid_graph.getOutput('Mesh.color')
    sentinel=np.full((72,128,4),0.375,dtype=np.float32)
    output.from_numpy(sentinel)
    try:invalid_graph.execute()
    except RuntimeError as error:assert 'out of range' in str(error)
    else:raise AssertionError('Accepted out-of-Scene instance ID on re-execution')
    np.testing.assert_array_equal(output.to_numpy(),sentinel)
    m.setActiveGraph(graph);m.removeGraph(invalid_graph)
    # Scene::rasterize requires the native Scene parameter block, even for an
    # empty draw list. A shader without it must reject before clearing outputs.
    bare_shader=OUT/'MissingScene.slang'
    bare_shader.write_text('''float4 vsMain(float3 p:POSITION):SV_Position { return float4(p,1); }
float4 psMain():SV_Target0 { return float4(1,0,0,1); }
''')
    bare=copy.deepcopy(props);bare['shader']['file']=str(bare_shader);bare['instanceIDs']=[]
    bare_graph=falcor.RenderGraph('MissingNativeSceneBlock')
    bare_graph.addPass(falcor.createPass('CustomRenderPiplineMeshDrawPass',bare),'Mesh')
    bare_graph.markOutput('Mesh.color')
    m.addGraph(bare_graph);m.setActiveGraph(bare_graph)
    try:m.renderFrame()
    except RuntimeError as error:assert 'gScene' in str(error)
    else:raise AssertionError('Accepted missing native Scene block')
    output=bare_graph.getOutput('Mesh.color');output.from_numpy(sentinel)
    try:bare_graph.execute()
    except RuntimeError as error:assert 'gScene' in str(error)
    else:raise AssertionError('Accepted missing native Scene block on re-execution')
    np.testing.assert_array_equal(output.to_numpy(),sentinel)
    m.setActiveGraph(graph);m.removeGraph(bare_graph)
    for invalid in (None,'blue',[-1],[2**32],[True],[0.5]):
        bad=copy.deepcopy(props);bad['instanceIDs']=invalid
        try:falcor.createPass('CustomRenderPiplineMeshDrawPass',bad)
        except RuntimeError:pass
        else:raise AssertionError('Accepted invalid instanceIDs '+repr(invalid))
    for label,change in [('legacy_filter',{'filter':{'model_ids':[1]}}),('implicit_matrix',{'view_projection':np.eye(4).tolist()})]:
        bad=copy.deepcopy(props);bad.update(change)
        try:falcor.createPass('CustomRenderPiplineMeshDrawPass',bad)
        except RuntimeError:pass
        else:raise AssertionError('Accepted '+label)
    return {'status':'passed','all_ids':all_ids,'blue':blue,'native_mask_and_depth_match':True,
            'no_material_table':True,'no_ue_shader_builtin':True,'empty_and_load_preservation':True,'property_update':True,
            'material_rename':True,'material_culling_update':True,'scene_replacement':True,'explicit_view_depth_viewport':True,
            'scene_id_rejection':True,'rejected_before_clear':True,'missing_scene_block_before_clear':True,
            'nonindexed':bool(os.environ.get('CRP_NATIVE_NONINDEXED'))}


try:result=run()
except Exception as error:
    traceback.print_exc();result={'status':'failed','error':str(error)}
(OUT/'result.json').write_text(json.dumps(result,indent=2))
print('NATIVE_MESH_DRAW_'+result['status'].upper(),flush=True)
exit()
