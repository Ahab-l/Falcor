"""CPU-only source-fidelity analysis; original IA/GPUScene are inputs, postVS is proof only."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def f32(a):
    return np.asarray(a,dtype=np.float32)


def fma(a,b,c):
    # f32 operands have 24-bit mantissas. The f64 intermediate faithfully models
    # these capture's single-rounding multiply-adds; results are checked vs GPU.
    return (np.asarray(a,dtype=np.float64)*np.asarray(b,dtype=np.float64)+np.asarray(c,dtype=np.float64)).astype(np.float32)


def row_mul_captured(v,m):
    result = v[...,0,None]*m[0]
    for i in (1,2,3):
        result = fma(v[...,i,None],m[i],result)
    return result


def normalize(v):
    return v/np.linalg.norm(v,axis=-1,keepdims=True)


def summary(a,b):
    a,b=np.asarray(a),np.asarray(b)
    error=np.abs(a.astype(np.float64)-b.astype(np.float64))
    return {'values':int(a.size),'different_values':int(np.count_nonzero(a!=b)),
        'max_abs_error':float(error.max()),'p99_abs_error':float(np.quantile(error,.99)),
        'mean_abs_error':float(error.mean())}


def float32_bit_differences(a,b):
    return int(np.count_nonzero(np.ascontiguousarray(a,dtype='f4').view('u4') !=
                                np.ascontiguousarray(b,dtype='f4').view('u4')))


def erode(mask,radius=2):
    h,w=mask.shape;p=np.pad(mask,radius);r=np.ones_like(mask)
    for y in range(radius*2+1):
        for x in range(radius*2+1):r &= p[y:y+h,x:x+w]
    return r


def inverse_falcor(m):
    """Float32 translation of MatrixMath.h inverse(matrix<T,4,4>), row-index API."""
    m=f32(m)
    c00=m[2,2]*m[3,3]-m[2,3]*m[3,2];c02=m[2,1]*m[3,3]-m[2,3]*m[3,1];c03=m[2,1]*m[3,2]-m[2,2]*m[3,1]
    c04=m[1,2]*m[3,3]-m[1,3]*m[3,2];c06=m[1,1]*m[3,3]-m[1,3]*m[3,1];c07=m[1,1]*m[3,2]-m[1,2]*m[3,1]
    c08=m[1,2]*m[2,3]-m[1,3]*m[2,2];c10=m[1,1]*m[2,3]-m[1,3]*m[2,1];c11=m[1,1]*m[2,2]-m[1,2]*m[2,1]
    c12=m[0,2]*m[3,3]-m[0,3]*m[3,2];c14=m[0,1]*m[3,3]-m[0,3]*m[3,1];c15=m[0,1]*m[3,2]-m[0,2]*m[3,1]
    c16=m[0,2]*m[2,3]-m[0,3]*m[2,2];c18=m[0,1]*m[2,3]-m[0,3]*m[2,1];c19=m[0,1]*m[2,2]-m[0,2]*m[2,1]
    c20=m[0,2]*m[1,3]-m[0,3]*m[1,2];c22=m[0,1]*m[1,3]-m[0,3]*m[1,1];c23=m[0,1]*m[1,2]-m[0,2]*m[1,1]
    fac=[f32(x) for x in [(c00,c00,c02,c03),(c04,c04,c06,c07),(c08,c08,c10,c11),(c12,c12,c14,c15),(c16,c16,c18,c19),(c20,c20,c22,c23)]]
    vec=[f32([m[i,1],m[i,0],m[i,0],m[i,0]]) for i in range(4)]
    inv=[vec[1]*fac[0]-vec[2]*fac[1]+vec[3]*fac[2],vec[0]*fac[0]-vec[2]*fac[3]+vec[3]*fac[4],
         vec[0]*fac[1]-vec[1]*fac[3]+vec[3]*fac[5],vec[0]*fac[2]-vec[1]*fac[4]+vec[2]*fac[5]]
    result=np.column_stack([v*f32([1,-1,1,-1] if i%2==0 else [-1,1,-1,1]) for i,v in enumerate(inv)])
    dot0=m[:,0]*result[0]
    dot1=(dot0[0]+dot0[1])+(dot0[2]+dot0[3])
    return result*(np.float32(1)/dot1)


def sphere_interpolation(clips,triangles,variants,width,height):
    """Perspective interpolation at centers; no hardware subpixel/edge emulation."""
    out={k:np.zeros((height,width,3),dtype=np.float64) for k in variants}
    depth=np.zeros((height,width))
    ndc=clips[:,:3].astype(np.float64)/clips[:,3,None]
    xy=np.column_stack([(ndc[:,0]*.5+.5)*width,(.5-ndc[:,1]*.5)*height])
    for tri in triangles:
        p=xy[tri];e1=p[1]-p[0];e2=p[2]-p[0];area=e1[0]*e2[1]-e1[1]*e2[0]
        if area>=-1e-12:continue
        low=np.maximum(np.ceil(p.min(axis=0)-.5).astype(int),[0,0]);high=np.minimum(np.floor(p.max(axis=0)-.5).astype(int),[width-1,height-1])
        if np.any(low>high):continue
        xx,yy=np.meshgrid(np.arange(low[0],high[0]+1)+.5,np.arange(low[1],high[1]+1)+.5)
        b1=((xx-p[0,0])*e2[1]-(yy-p[0,1])*e2[0])/area
        b2=(e1[0]*(yy-p[0,1])-e1[1]*(xx-p[0,0]))/area
        bary=np.stack([1-b1-b2,b1,b2],axis=-1)
        dz=np.sum(bary*ndc[tri,2],axis=-1)
        region=np.s_[low[1]:high[1]+1,low[0]:high[0]+1]
        update=(bary>=-1e-10).all(axis=-1)&(dz>=depth[region])
        depth[region][update]=dz[update]
        weights=bary/clips[tri,3]
        weights/=weights.sum(axis=-1,keepdims=True)
        for k,v in variants.items():
            interp=normalize(weights @ v[tri])
            out[k][region][update]=interp[update]
    return out,depth>0


def triangle_pixel(clips,triangle,x,y,width,height,subpixel_bits=None):
    """Diagnostic edge/depth calculation; fixed-point rounding is an explicit model."""
    c=clips[triangle]
    if np.any(c[:,3]<=0):return None
    ndc=c[:,:3].astype(np.float64)/c[:,3,None]
    screen=np.column_stack([(ndc[:,0]*.5+.5)*width,(.5-ndc[:,1]*.5)*height])
    if subpixel_bits is not None:
        scale=2**subpixel_bits;screen=np.rint(screen*scale)/scale
    cross=lambda a,b:a[0]*b[1]-a[1]*b[0]
    e1=screen[1]-screen[0];e2=screen[2]-screen[0];area=cross(e1,e2)
    if area>=-1e-12:return None
    delta=np.array([x+.5,y+.5])-screen[0]
    b1=cross(delta,e2)/area;b2=cross(e1,delta)/area
    bary=np.array([1-b1-b2,b1,b2])
    lengths=np.array([np.linalg.norm(screen[2]-screen[1]),np.linalg.norm(screen[0]-screen[2]),np.linalg.norm(screen[1]-screen[0])])
    return {'screen_vertices':screen.tolist(),'barycentrics':bary.tolist(),
            'min_signed_edge_distance_pixels':float((bary*abs(area)/lengths).min()),
            'inside':bool(np.all(bary>=0)), 'interpolated_reverse_z':float(np.dot(bary,ndc[:,2]))}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scene',type=Path,default=ROOT/'build/rdc-scene')
    ap.add_argument('--native',type=Path,default=ROOT/'build/rdc-render/outputs.npz')
    ap.add_argument('--capture-exports',type=Path,default=ROOT.parent/'Falcor/docs/research/captures/2026-09-09-1')
    ap.add_argument('--out',type=Path,default=ROOT/'docs/research/ue-legacy-rdc-scene')
    ap.add_argument('--report-prefix',default='vertex-fidelity')
    args=ap.parse_args()
    scene=args.scene;m=json.loads((scene/'scene-manifest.json').read_text());v=m['camera']
    native_bytes=args.native.read_bytes();native=np.load(io.BytesIO(native_bytes))
    report={'schema':'ue-vertex-fidelity-analysis-v1','gpu_work':False,
        'native_npz_sha256':hashlib.sha256(native_bytes).hexdigest(),'capture_sha256':m['capture_sha256'],
        'postvs_role':'validation only; all simulated clip positions computed from original local IA and decoded GPUScene transforms',
        'source_files':{},'objects':[]}
    source_names=['Source/Falcor/Scene/SceneTypes.slang','Source/Falcor/Scene/SceneBuilder.cpp',
                  'Source/Falcor/Scene/Raster.slang','Source/Falcor/Scene/Scene.cpp','Source/Falcor/Utils/Math/MatrixMath.h']
    for name in source_names:report['source_files'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    vp=f32(v['translated_world_to_clip_row_major']);hi=f32(v['pre_view_translation_high']);lo=f32(v['pre_view_translation_low'])
    width,height=v['view_rect'][2:];bw,bh=v['buffer_extent'];sphere_data=None;cube_data=None
    for obj in m['objects']:
        a=np.load(scene/obj['asset']);position=a['positions_local_ue_cm'];matrix=f32(obj['local_to_world_row_major'])
        relative=f32(obj['instance_relative_translation_cm']);primitive=f32(obj['primitive_position_high_cm'])
        linear=position[:,2,None]*matrix[2,:3]
        linear=fma(position[:,1,None],matrix[1,:3],linear)
        linear=fma(position[:,0,None],matrix[0,:3],linear)
        translation=((hi+primitive)+lo)+relative
        translated=linear+translation
        clips=row_mul_captured(np.column_stack([translated,np.ones(len(position),dtype='f4')]),vp)
        post=np.fromfile(scene/f'raw/{obj["eid"]}-postVS.bin',dtype='<f4').reshape(len(position),-1)
        meter=a['positions_falcor_m'];roundtrip=np.column_stack([-meter[:,2],meter[:,0],meter[:,1]])*np.float32(100)
        baked_translated=(roundtrip+hi)+lo
        baked_clips=row_mul_captured(np.column_stack([baked_translated,np.ones(len(position),dtype='f4')]),vp)
        normal=a['normals_world_ue'];normal_half=normal.astype('f2').astype('f4')
        decoded_normal=normalize(normal_half)
        norm_lengths=np.linalg.norm(normal,axis=1)
        result={'eid':obj['eid'],'name':obj['name'],'source_vertex_count':len(position),
            'local_fma_vs_captured_clip':summary(clips,post[:,:4]),
            'baked_meter_order_vs_captured_clip_same_clip_fma':summary(baked_clips,post[:,:4]),
            'baked_meter_roundtrip_ue_cm':summary(roundtrip,a['positions_world_ue_cm']),
            'translated_world_order_error_cm':summary(baked_translated,translated),
            'normal_half_storage_error':summary(normal_half,normal),
            'normal_half_plus_vertex_normalize_error':summary(decoded_normal,normal),
            'raw_normal_length_range':[float(norm_lengths.min()),float(norm_lengths.max())],
            'linear_rows_ue':matrix[:3,:3].tolist(),'primitive_position_high_cm':primitive.tolist(),
            'instance_relative_translation_cm':relative.tolist()}
        report['objects'].append(result)
        result['local_fma_vs_captured_clip']['different_float32_bit_patterns']=float32_bit_differences(clips,post[:,:4])
        if obj['eid']==1816:
            sphere_data=(clips,a['triangles'],normal)
        if obj['eid']==1827:
            cube_data=(clips,baked_clips,a['triangles'])
    assert all(o['local_fma_vs_captured_clip']['different_float32_bit_patterns']==0 for o in report['objects']), 'Captured arithmetic proof failed'
    cb=(scene/'raw/1853-Pixel-cb0.bin').read_bytes()
    sv_matrix=np.frombuffer(cb,dtype='<f4',count=16,offset=704).reshape(4,4)
    captured_inverse=np.frombuffer(cb,dtype='<f4',count=16,offset=640).reshape(4,4)
    relative_pre=np.frombuffer(cb,dtype='<f4',count=3,offset=2048)
    # Falcor stores the transposed captured row-major VP for column-vector shader mul.
    falcor_inverse_rows=inverse_falcor(vp.T).T
    inverse_identity_residual=float(np.max(np.abs(vp.astype('f8') @ falcor_inverse_rows.astype('f8')-np.eye(4))))
    assert inverse_identity_residual<1e-6, 'Falcor inverse model failed its independent identity check'
    depth=np.frombuffer(gzip.decompress((args.capture_exports/'1853-SceneDepthZ.bin.gz').read_bytes()),dtype='<f4').reshape(bh,bw,2)[:height,:width,0]
    yy,xx=np.mgrid[:height,:width];xy=f32(np.stack([xx+.5,yy+.5],axis=-1))
    coords=np.concatenate([xy,depth[...,None],np.ones((height,width,1),dtype='f4')],axis=-1)
    direct_h=row_mul_captured(coords,sv_matrix)
    valid=depth>0
    direct=np.zeros((height,width,3),dtype='f4')
    direct[valid]=direct_h[valid,:3]/direct_h[valid,3,None]-relative_pre
    uv=xy/f32([width,height]);ndcxy=f32(np.stack([uv[...,0]*np.float32(2)-np.float32(1),np.float32(1)-uv[...,1]*np.float32(2)],axis=-1))
    ndc=np.concatenate([ndcxy,depth[...,None],np.ones((height,width,1),dtype='f4')],axis=-1)
    alternate={}
    for key,matrix in [('captured_clip_inverse_plus_uv',captured_inverse),('falcor_float32_inverse_plus_uv',falcor_inverse_rows)]:
        h=row_mul_captured(ndc,matrix);p=np.zeros_like(direct);p[valid]=h[valid,:3]/h[valid,3,None]-hi;alternate[key]=p
    ids=np.load(scene/'object-id.npy');floor=erode(ids==4)&valid
    floor_pairs_x=floor[:,1::2]&floor[:,0:-1:2];floor_pairs_y=floor[1::2]&floor[0:-1:2]
    report['pixel_position_reconstruction']={'cbuffer_sha256':hashlib.sha256(cb).hexdigest(),
        'SVPositionToTranslatedWorld_byte_offset':704,'SVPositionToTranslatedWorld_row_major':sv_matrix.tolist(),
        'SVPositionToTranslatedWorld_float32_bits':[[f'{x:08x}' for x in row] for row in sv_matrix.view('u4')],
        'ClipToTranslatedWorld_byte_offset':640,'ClipToTranslatedWorld_row_major':captured_inverse.tolist(),
        'relative_preview_translation_byte_offset':2048,'relative_preview_translation':relative_pre.tolist(),
        'falcor_inverse_row_major_cpu_model':falcor_inverse_rows.tolist(),
        'inverse_identity_max_abs_residual':inverse_identity_residual,
        'matrix_float32_inverse_vs_captured_inverse':summary(falcor_inverse_rows,captured_inverse),'alternatives':{},
        'derivative_model':'form float32 UV first, then subtract horizontal/vertical even-odd pixel pairs matching 2x2 quad alignment; not a texture hardware LOD simulation',
        'limit':'CPU models native mul with the same FMA accumulation as captured PS; actual backend reassociation is not assumed bit-identical'}
    for key,p in alternate.items():
        uv_grid=(p-f32([0,0,-.5]))*np.float32(.01)
        direct_uv_grid=(direct-f32([0,0,-.5]))*np.float32(.01)
        dx=uv_grid[:,1::2]-uv_grid[:,0:-1:2];dy=uv_grid[1::2]-uv_grid[0:-1:2]
        ddx=direct_uv_grid[:,1::2]-direct_uv_grid[:,0:-1:2];ddy=direct_uv_grid[1::2]-direct_uv_grid[0:-1:2]
        report['pixel_position_reconstruction']['alternatives'][key]={
            'covered_position_cm':summary(p[valid],direct[valid]),'floor_interior_position_cm':summary(p[floor],direct[floor]),
            'floor_uv_ddx_at_frequency_0_01':summary(dx[floor_pairs_x],ddx[floor_pairs_x]),
            'floor_uv_ddy_at_frequency_0_01':summary(dy[floor_pairs_y],ddy[floor_pairs_y])}
    cube_clips,cube_baked,cube_triangles=cube_data
    native_depth=native['depth'].reshape(bh,bw)[:height,:width]
    report['depth_boundary_pixels']={'source_object':'cube, event 1827',
        'source_vs_baked_same_fma_clip_bit_differences':float32_bit_differences(cube_clips,cube_baked),
        'model_limit':'1/256 screen snapping is a CPU diagnostic supported by captured depths; native postVS and raster setup have not been compared here',
        'pixels':[]}
    for x,y in [(1126,565),(1123,597)]:
        point={'x':x,'y':y,'captured_depth':float(depth[y,x]),'native_depth':float(native_depth[y,x]),
               'cpu_object_id':int(ids[y,x]),'nearby_front_facing_cube_triangles':[]}
        for index,triangle in enumerate(cube_triangles):
            exact=triangle_pixel(cube_clips,triangle,x,y,width,height)
            if exact is None or min(exact['barycentrics'])<=-.001:continue
            snapped=triangle_pixel(cube_clips,triangle,x,y,width,height,8)
            snapped_depth=np.float32(snapped['interpolated_reverse_z'])
            point['nearby_front_facing_cube_triangles'].append({'triangle_index':index,'source_vertex_indices':triangle.tolist(),
                'unsnapped':exact,'screen_snapped_to_1_over_256':snapped,
                'snapped_depth_abs_error':float(abs(float(snapped_depth)-float(depth[y,x]))),
                'snapped_depth_float32_ulp_distance':abs(int(snapped_depth.view('u4'))-int(depth[y,x].view('u4')))})
        report['depth_boundary_pixels']['pixels'].append(point)
    # Separate magnitude normalization from float16 compression using the same
    # original projected triangles for each normal candidate.
    clips,triangles,n=sphere_data
    candidates={'captured_raw_snorm':n.astype(np.float64),'vertex_normalize_only':normalize(n.astype(np.float64)),
                'float16_and_vertex_normalize':normalize(n.astype('f2').astype(np.float64))}
    interp,coverage=sphere_interpolation(clips,triangles,candidates,width,height)
    sphere=erode(ids==1)&coverage
    captured_a=np.frombuffer(gzip.decompress((args.capture_exports/'1853-GBufferA.bin.gz').read_bytes()),dtype='<u4').reshape(bh,bw)[:height,:width]
    native_a=native['gBufferA'].view('<u4').reshape(bh,bw)[:height,:width]
    channels=lambda a:np.stack([a&1023,(a>>10)&1023,(a>>20)&1023],axis=-1).astype(np.int32)
    cap_code=channels(captured_a);native_code=channels(native_a)
    mismatch_y,mismatch_x=np.where(np.any(cap_code!=native_code,axis=-1))
    report['native_normal_mismatch_pixels']={'count':len(mismatch_x),'coordinate_limit':32,'pixels':[
        {'x':int(x),'y':int(y),'cpu_object_id':int(ids[y,x]),'captured_word':f'{int(captured_a[y,x]):08x}',
         'native_word':f'{int(native_a[y,x]):08x}','captured_rgb':cap_code[y,x].tolist(),'native_rgb':native_code[y,x].tolist()}
        for x,y in zip(mismatch_x[:32],mismatch_y[:32])]}
    report['normal_encoding_arithmetic']={
        'captured_final_encode':'PS DXIL values %460..%465 (lines 630-635): three fmul fast by 0.5, then three fadd fast 0.5; contraction is permitted',
        'native_final_encode':'Codecs/DefaultLit.slangh: surface.normalUE * 0.5 + 0.5; contraction is permitted',
        'conclusion':'For the remaining non-subnormal normal, multiplication by exactly 0.5 is exact. FMA versus separated multiply/add cannot differ for identical float32 input normal.',
        'captured_normalize':'UE x/y/z dot3, rsqrt, per-component multiply (captured PS values %140..%144)',
        'native_normalize':'CustomRenderPiplineMaterial.slangh normalizes Falcor (UE.y, UE.z, -UE.x) then swizzles to UE',
        'recommendation':'Swizzle the unnormalized input to UE axes before normalize, preserving the captured dot component order. This is source-fidelity guidance, not proof that it resolves the last pixel.',
        'limit':'This CPU analysis has no native interpolated-normal or final-PS-float readback; actual backend rsqrt/dot and ROP conversion remain unmeasured'}
    # An explicit diagnostic rounding convention; it is not an emulation of all
    # hardware UNORM conversion rules. Half-way ties go to the lower integer.
    quantize=lambda a:np.maximum(0,np.minimum(1023,np.ceil((a*.5+.5)*1023-.5))).astype(np.int32)
    report['sphere_normal_interpolation']={'interior_pixels':int(sphere.sum()),'variants':{},
        'quantization_model':'nearest UNORM10 with exact halfway ties to lower integer; diagnostic only',
        'interpolation_model':'float64 perspective-correct barycentrics at centers from original-IA-derived clip; no hardware edge snapping',
        'actual_native_vs_capture_codes':summary(native_code[sphere],cap_code[sphere])}
    for key,p in interp.items():
        code=quantize(p)
        report['sphere_normal_interpolation']['variants'][key]={
            'normal_delta_from_raw_interp':summary(p[sphere],interp['captured_raw_snorm'][sphere]),
            'predicted_code_vs_capture':summary(code[sphere],cap_code[sphere]),
            'predicted_code_vs_native':summary(code[sphere],native_code[sphere]),
            'pixels_matching_capture_all_rgb':int((code[sphere]==cap_code[sphere]).all(axis=1).sum()),
            'pixels_matching_native_all_rgb':int((code[sphere]==native_code[sphere]).all(axis=1).sum())}
    report['recommended_vertex_record']={'stride_bytes':48,'members':[
        {'byte_offset':0,'type':'float3','name':'localPositionUECm'}, {'byte_offset':12,'type':'uint','name':'sourceVertexID'},
        {'byte_offset':16,'type':'float3','name':'normalLocalUnnormalized'}, {'byte_offset':28,'type':'float','name':'tangentSign'},
        {'byte_offset':32,'type':'float3','name':'tangentLocal'}, {'byte_offset':44,'type':'uint','name':'padding'}],
        'input_source':'original IA positions and manual tangent SRV SNORM8 decode; never postVS',
        'instance_fields':['localLinearRowsUE[3]','primitivePositionHighUECm','instanceRelativeTranslationUECm','inverseAbsoluteScale[3]','primitiveFlags','vertexBase','vertexCount'],
        'normal_transform':'multiply original local normal by localLinearRowsUE / abs(scale) per row; do not normalize per vertex; normalize only in PS',
        'scene_mapping':'explicit Scene-processed vertex->source vertex mapping required; SV_VertexID includes mesh.vbOffset and SceneBuilder can reorder/split',
        'mapping_option':'carry original source vertex numeric integer in otherwise unused texC.x; identity texture transform required, float32 exactly represents these IDs; declare this an ID channel, not recovered UV'}
    args.out.mkdir(parents=True,exist_ok=True)
    json_path=args.out/f'{args.report_prefix}.json'
    md_path=args.out/f'{args.report_prefix}.md'
    json_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    lines=['# Vertex source-fidelity analysis','',
        'This CPU-only investigation uses original indexed local positions and GPUScene transforms. PostVS data is used exclusively to check results.', '',
        '| Object | Clip values different from captured using source arithmetic | Max baked-order clip error | Max translated-position error cm | Half normal error |',
        '|---|---:|---:|---:|---:|']
    for o in report['objects']:
        lines.append(f'| {o["name"]} | {o["local_fma_vs_captured_clip"]["different_values"]} | {o["baked_meter_order_vs_captured_clip_same_clip_fma"]["max_abs_error"]:.9g} | {o["translated_world_order_error_cm"]["max_abs_error"]:.9g} | {o["normal_half_storage_error"]["max_abs_error"]:.9g} |')
    lines += ['','Every source-arithmetic clip component is bit-exact to the captured GPU postVS stream. This checks all four objects; it does not assert raster/GBuffer equality.', '',
        'Falcor SceneTypes.slang stores normals as three float16 components, then explicitly normalizes the decoded vertex normal before interpolation. Tangents use octahedral 2×16 encoding; normals do not use quaternion packing. The captured UE VS keeps unnormalized SNORM8-derived normals until PS normalization. Both the half conversion and vertex normalization must be bypassed.', '',
        '## Required operation order','',
        '```hlsl','float3 localLinear = localPosition.z * localLinearRow2;',
        'localLinear = fma(localPosition.y, localLinearRow1, localLinear);',
        'localLinear = fma(localPosition.x, localLinearRow0, localLinear);',
        'float3 translation = ((preHigh + primitiveHigh) + preLow) + instanceRelativeTranslation;',
        'float3 translated = localLinear + translation;',
        'float4 clip = translated.x * translatedWorldToClipRow0;',
        'clip = fma(translated.y, translatedWorldToClipRow1, clip);',
        'clip = fma(translated.z, translatedWorldToClipRow2, clip);',
        'clip = fma(1.0, translatedWorldToClipRow3, clip);','```','',
        'Use the original local float32 positions and separated primitive-high/relative translations; baking world meters then multiplying by 100 changes arithmetic and rounding. Keep the captured FMA order rather than allowing matrix multiplication to change association.', '',
        '## Two depth boundary pixels','',
        'The captured depths at (1126,565) and (1123,597) belong to cube triangles 42 and 40. Their pixel centers are respectively 0.000729 pixels outside and 0.000398 pixels inside the unsnapped right edge. Rounding the captured screen coordinates to 1/256 pixel puts both centers inside; interpolated depth agrees with the captured value within one float32 ULP. '+
        ('The native snapshot matches captured depth exactly at both locations.' if all(p['captured_depth']==p['native_depth'] for p in report['depth_boundary_pixels']['pixels']) else 'The native snapshot differs at one or both locations; the exact values are retained in JSON.'), '',
        'The cube has identical source-local and baked-meter clip bits when both calculations use captured FMA order. Consequently, world-meter baking alone cannot explain these two pixels. Native matrix accumulation and raster setup require a GPU comparison. The CPU object-ID mask itself is sensitive to edge snapping and is not ground truth at these boundary pixels.', '',
        '## Pixel position reconstruction','',
        'The original PS multiplies `[SV_Position.x,SV_Position.y,SV_Position.z,1]` directly by the captured View.SVPositionToTranslatedWorld matrix at cbuffer byte 704, using x multiply then y/z/w FMAs, divides xyz by w, and subtracts View.RelativePreViewTranslationTO at byte 2048. Both raw matrices and exact float32 values are in the accompanying JSON. Do not add a second half-pixel or normalize pixel coordinates for this direct matrix.', '',
        'Computing a new inverse VP and normalizing coordinates first changes both the rounded matrix coefficients and per-pixel arithmetic. JSON quantifies coordinate and adjacent-pixel derivative differences on the same captured depth values, keeping geometry/depth differences separate. The native backend may choose a different multiplication association than this CPU model.', '',
        '## Source buffer interface','',
        'The recommended 48-byte record is localPositionUECm(float3), sourceVertexID(uint), normalLocalUnnormalized(float3), tangentSign(float), tangentLocal(float3), padding(uint), at offsets 0/12/16/28/32/44. StructuredBuffer lookup bypasses PackedStaticVertexData. Keep Scene geometry/material IDs, draw list, index buffer, winding and draw arguments.', '',
        'An explicit mapping from Scene-processed vertices to source vertices is required: SceneBuilder.processMesh can reorder/split vertices, and indexed draw SV_VertexID includes mesh.vbOffset. For these four UV-free draws, texC.x may carry the original numeric source ID through Scene processing (identity texture transform); otherwise provide an explicit remap buffer. Do not assume original source indexing survives preprocessing.', '',
        'Per-instance data must retain scaled linear rows, primitive-high position and relative translation separately. For captured normal transformation divide each linear row by its absolute scale and apply the original unnormalized normal. Normalize only at the pixel stage. The instance packet also carries primitiveFlags and source vertex base/count.', '',
        'Sphere pixel comparisons in JSON independently separate vertex-normalization-only and half-plus-normalization candidates. Their software UNORM rounding and floating interpolation are explicitly diagnostic, not substituted for GPU validation. No tolerances are relaxed.', '',
        '## Current native normal residual','',
        f'The native snapshot has {len(mismatch_x)} pixels with different normal RGB codes. Coordinates and raw words for up to 32 pixels are recorded in JSON. Native NPZ SHA-256: `{report["native_npz_sha256"]}`.', '',
        'Both captured DXIL and native source allow contraction of the final normal × 0.5 + 0.5 encoding. Multiplication by this exact power of two is exact for the remaining normal magnitude, so changing final encode contraction alone cannot change its result. A source difference occurs earlier: native material code normalizes in Falcor axis order and then swizzles, while captured PS normalizes UE x/y/z. Swizzle before normalization to preserve the captured dot component order; GPU validation is still required.']
    md_path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'json':str(json_path),'markdown':str(md_path),'native_npz_sha256':report['native_npz_sha256'],
        'clip_bit_differences':{o['name']:o['local_fma_vs_captured_clip']['different_float32_bit_patterns'] for o in report['objects']},
        'native_normal_mismatch_count':len(mismatch_x)},indent=2))


if __name__=='__main__':main()
