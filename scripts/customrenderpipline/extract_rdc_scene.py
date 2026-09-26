"""Reconstruct the four opaque GPU draws in UE capture 1.rdc; never modifies the RDC.

Run from the worktree with Python + numpy + Pillow. --replay invokes the existing
RenderDoc installation with its embedded Python; otherwise decode saved raw data.
The postVS stream is used exclusively as an independent projection/tangent check.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EIDS = (1816, 1827, 1838, 1853)
LABELS = ('sphere', 'cube', 'standing_plane', 'grid_floor')


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(16 * 1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def decode_transform(packed, translation):
    """SceneData.ush DecodeTransform, also matched to the captured VS DXIL."""
    r0, r1, r2, r3 = [int(x) for x in packed]
    octz = (np.array([r0 & 65535, r0 >> 16], dtype=np.float64) - 32768) / 32767
    z = np.array([octz[0] + octz[1], octz[0] - octz[1],
                  2 - abs(octz[0] + octz[1]) - abs(octz[0] - octz[1])])
    z /= np.linalg.norm(z)
    a = 1 / (1 + z[2])
    b = -z[0] * z[1] * a
    bx = np.array([1 - z[0] * z[0] * a, b, -z[0]])
    by = np.array([b, 1 - z[1] * z[1] * a, -z[1]])
    spin0 = ((r1 & 32767) - 16384) * (0.70710678 / 16383)
    spin1 = math.sqrt(1 - spin0 * spin0)
    x, y = (spin0, spin1) if r1 & 32768 else (spin1, spin0)
    axis0 = bx * x + by * y
    rotation = np.array([axis0, np.cross(z, axis0), z])
    exp_scale = struct.unpack('<f', struct.pack('<I', ((r3 >> 16) - 15) << 23))[0]
    scale = (np.array([r2 & 65535, r2 >> 16, r3 & 65535], dtype=np.float64) - 32768) * exp_scale
    matrix = np.eye(4)
    matrix[:3, :3] = rotation * scale[:, None]
    matrix[3, :3] = translation
    return matrix, rotation, scale


def falcor_vector(a, position=False):
    a = np.asarray(a)
    result = np.stack([a[..., 1], a[..., 2], -a[..., 0]], axis=-1)
    return result / 100 if position else result


def rasterize(clips, triangles, width, height, depth, ids, object_id):
    """Independent CPU depth/coverage check, clipped in homogeneous D3D space.

    Pixel centers are tested with floating edge equations, without the hardware
    subpixel snapping/top-left rule. Boundary mismatches are measured and reported.
    """
    planes = (lambda v: v[0]+v[3], lambda v: v[3]-v[0], lambda v: v[1]+v[3],
              lambda v: v[3]-v[1], lambda v: v[2], lambda v: v[3]-v[2])
    for tri in triangles:
        polygon = list(clips[tri])
        for plane in planes:
            result = []
            if not polygon:
                break
            prev = polygon[-1]
            dp = plane(prev)
            for cur in polygon:
                dc = plane(cur)
                if (dp >= 0) != (dc >= 0):
                    result.append(prev + (cur - prev) * (dp / (dp - dc)))
                if dc >= 0:
                    result.append(cur)
                prev, dp = cur, dc
            polygon = result
        for i in range(1, len(polygon)-1):
            c = np.array([polygon[0], polygon[i], polygon[i+1]])
            ndc = c[:, :3] / c[:, 3, None]
            xy = np.column_stack([(ndc[:, 0]*.5+.5)*width, (.5-ndc[:, 1]*.5)*height])
            edge1, edge2 = xy[1]-xy[0], xy[2]-xy[0]
            area = edge1[0]*edge2[1]-edge1[1]*edge2[0]
            # Captured D3D12 frontCCW=True: CCW in target coordinates means negative area.
            if area >= -1e-12:
                continue
            lo = np.maximum(np.ceil(xy.min(axis=0)-.5).astype(int), [0, 0])
            hi = np.minimum(np.floor(xy.max(axis=0)-.5).astype(int), [width-1, height-1])
            if np.any(lo > hi):
                continue
            xx, yy = np.meshgrid(np.arange(lo[0], hi[0]+1)+.5, np.arange(lo[1], hi[1]+1)+.5)
            w1 = ((xx-xy[0, 0])*(xy[2, 1]-xy[0, 1])-(yy-xy[0, 1])*(xy[2, 0]-xy[0, 0]))/area
            w2 = ((xy[1, 0]-xy[0, 0])*(yy-xy[0, 1])-(xy[1, 1]-xy[0, 1])*(xx-xy[0, 0]))/area
            w0 = 1-w1-w2
            inside = (w0 >= -1e-10) & (w1 >= -1e-10) & (w2 >= -1e-10)
            dz = w0*ndc[0, 2]+w1*ndc[1, 2]+w2*ndc[2, 2]
            region = np.s_[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
            update = inside & (dz >= depth[region])
            depth[region][update] = dz[update]
            ids[region][update] = object_id


def material_facts(eid, raw):
    values = np.fromfile(raw / f'{eid}-Pixel-cb2.bin', dtype='<f4')
    if eid != 1853:
        return {'program': 'captured_basic_shape', 'base_color_linear': values[4:7].tolist(),
                'roughness': float(values[7]), 'metallic': 0.0, 'specular': .5,
                'emissive_linear': (values[1:4] * values[0]).tolist(),
                'shader_evidence': 'shader-1816-Pixel.txt: cbuffer2 byte16 RGB/A; metallic=0, specular=.5; no UV samples',
                'raw_material_f32_0_31': values[:8].tolist()}
    return {'program': 'captured_triplanar_grid',
            'emissive_linear': (values[1:4] * values[0]).tolist(),
            'position_frequency_per_cm': float(values[4]),
            'checker_color_1_linear': values[5:8].tolist(),
            'checker_color_0_linear': values[8:11].tolist(),
            'grid_color_linear': values[12:15].tolist(),
            'checker_roughness_1': float(values[15]), 'checker_roughness_0': float(values[16]),
            'line_roughness': .3, 'specular': .5,
            'metallic': 'saturate(triplanar texture red at full frequency)',
            'texture': 'raw/1853-grid.dds',
            'texture_coordinates': 'object-relative world position projected on normalized primitive axes; not mesh UV',
            'blend_weights': 'saturate(abs(local normal x,z)*3-1), sequential XZ/YZ then XY blends',
            'shader_evidence': 'shader-1853-Pixel.txt: _309.._420; green sampled at half frequency blends checker colors and roughness; red at full frequency controls grid color, roughness and metallic',
            'raw_parameter_bytes_exclude_padding': {'offset0': values[:4].tolist(), 'offset16': values[4:8].tolist(),
                'offset32': values[8:11].tolist(), 'offset48': values[12:16].tolist(), 'offset64': [float(values[16])]},
            'implementation_status': 'standalone Materials/RDCGrid.slangh evaluator compiled; stock scene material is a placeholder until runtime routes program 2'}


def generate_scene(out, manifest):
    # The runtime owns material routing. The scene creates a real mesh/material for each opaque draw.
    script = '''"""Captured real geometry/camera. Floor StandardMaterial is a placeholder; use manifest MaterialProgram inputs."""
import json, math
from pathlib import Path
import numpy as np
from falcor import *
root = Path(r"__OUTPUT__")
data = json.loads((root / "scene-manifest.json").read_text())
for obj in data["objects"]:
    arrays = np.load(root / obj["asset"])
    mat = StandardMaterial(obj["material_name"])
    source = obj["material"]
    mat.baseColor = float4(*(source.get("base_color_linear", source.get("checker_color_0_linear"))), 1)
    mat.roughness = source.get("roughness", source.get("checker_roughness_0"))
    mat.metallic = float(source.get("metallic", 0)) if isinstance(source.get("metallic"), (int, float)) else 0
    mat.indexOfRefraction = 1.5
    mesh = TriangleMesh()
    for p, n in zip(arrays["positions_falcor_m"], arrays["normals_falcor"]):
        mesh.addVertex(float3(*map(float,p)), float3(*map(float,n)), float2(0,0))
    for tri in arrays["triangles"]:
        mesh.addTriangle(*map(int,tri))
    mesh.frontFaceCW = False
    node = sceneBuilder.addNode(obj["name"], Transform())
    sceneBuilder.addMeshInstance(node, sceneBuilder.addTriangleMesh(mesh, mat))
c = data["camera"]
camera = Camera("CapturedRdcCamera")
camera.position = float3(*c["position_falcor_m"])
camera.target = float3(*c["target_falcor_m"])
camera.up = float3(*c["up_falcor"])
camera.nearPlane = c["near_cm"] / 100
camera.farPlane = 1000000
camera.aspectRatio = c["view_rect"][2] / c["view_rect"][3]
camera.frameHeight = 24
camera.focalLength = 12 * c["projection_row_major"][1][1]
sceneBuilder.addCamera(camera)
'''.replace('__OUTPUT__', str(out.resolve()))
    (out / 'captured_scene.pyscene').write_text(script, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture', type=Path, default=Path(r'E:\rdc\ue\1.rdc'))
    ap.add_argument('--out', type=Path, default=ROOT/'build/rdc-scene')
    ap.add_argument('--evidence', type=Path, default=ROOT.parent/'Falcor/docs/research/captures/2026-09-09-1')
    ap.add_argument('--renderdoc', type=Path, default=Path(r'C:\Program Files\RenderDoc\qrenderdoc.exe'))
    ap.add_argument('--replay', action='store_true')
    args = ap.parse_args()
    out = args.out.resolve()
    raw = out / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    if args.replay:
        for stale in ('replay-error.json', 'replay-done.json'):
            (raw/stale).unlink(missing_ok=True)
        env = dict(os.environ, UE_RDC_SCENE_OUT=str(raw), UE_RDC_SCENE_CAPTURE=str(args.capture.resolve()))
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        subprocess.run([str(args.renderdoc), '--python', str(Path(__file__).with_name('_extract_rdc_scene_replay.py'))],
                       env=env, startupinfo=startup, check=True, timeout=300)
    if (raw/'replay-error.json').exists():
        raise RuntimeError((raw/'replay-error.json').read_text())
    if not (raw/'replay-done.json').exists():
        raise RuntimeError('No replay data; run with --replay first')
    facts = json.loads((raw/'replay-draws.json').read_text())
    layout = json.loads((args.evidence/'view-layout-evidence.json').read_text())
    cb = (raw/'1816-Vertex-cb0.bin').read_bytes()
    view = {f['name']: np.frombuffer(cb, dtype='<u4' if f['type'].startswith('uint') else '<f4',
                   count=f['bytes']//4, offset=f['offset']).astype(np.float64) for f in layout['fields']}
    pre = view['View_PreViewTranslationHigh'] + view['View_PreViewTranslationLow']
    clip_matrix = view['View_TranslatedWorldToClip'].reshape(4,4)
    view_matrix = view['View_TranslatedWorldToView'].reshape(4,4)
    projection = view['View_ViewToClip'].reshape(4,4)
    camera_position = -pre
    view_rect = view['View_ViewRectMinAndSize'].astype(int).tolist()
    width, height = view_rect[2:]
    buffer_size = view['View_BufferSizeAndInvSize'][:2].astype(int).tolist()
    manifest = {'schema': 'ue-rdc-scene-v1', 'capture': str(args.capture.resolve()),
        'capture_sha256': sha(args.capture), 'capture_modified': False,
        'coordinate_convention': {'source': 'UE left-handed centimeters, +Z up',
            'matrix': 'row vector multiplied by row-major matrix',
            'falcor': '(UE.y, UE.z, -UE.x)/100; directions same axis mapping without /100'},
        'view_layout_provenance': {'source': layout['source'], 'source_sha256': layout['sourceSha256'],
            'captured_shader_source_identity_proven': False,
            'method': 'existing normalized View layout matched to captured DXIL; transforms independently tested against postVS'},
        'camera': {'position_ue_cm': camera_position.tolist(),
            'forward_ue': view['View_ViewForward'].tolist(), 'up_ue': view['View_ViewUp'].tolist(),
            'right_ue': view['View_ViewRight'].tolist(), 'view_rect': view_rect, 'buffer_extent': buffer_size,
            'near_cm': float(projection[3,2]), 'far': 'infinite reverse Z',
            'horizontal_fov_degrees': math.degrees(2*math.atan(1/projection[0,0])),
            'pre_view_translation_high': view['View_PreViewTranslationHigh'].tolist(),
            'pre_view_translation_low': view['View_PreViewTranslationLow'].tolist(),
            'translated_world_to_clip_row_major': clip_matrix.tolist(),
            'sv_position_to_translated_world_row_major': view['View_SVPositionToTranslatedWorld'].reshape(4,4).tolist(),
            'relative_pre_view_translation': view['View_RelativePreViewTranslationTO'].tolist(),
            'translated_world_to_view_row_major': view_matrix.tolist(),
            'projection_row_major': projection.tolist(), 'jitter': view['View_TemporalAAJitter'].tolist(),
            'pre_exposure': float(view['View_PreExposure'][0]),
            'position_falcor_m': falcor_vector(camera_position, True).tolist(),
            'target_falcor_m': falcor_vector(camera_position + view['View_ViewForward']*100, True).tolist(),
            'up_falcor': falcor_vector(view['View_ViewUp']).tolist(),
            'falcor_stock_camera_limit': 'finite far=1000000m and normal depth; exact reverse-Z matrix retained here for UE runtime'},
        'asset_paths_relative_to': str(out), 'objects': [], 'uncertainties': [
            'Original uasset/package identity is not established from stripped shaders.',
            'Mesh UV attributes are not read by any of these captured shaders and the UV SRV is not bound. Zero UV in the scene adapter is an explicit unused placeholder, not recovered UV.',
            'The floor needs the captured triplanar grid MaterialProgram, mip selection and sampler; StandardMaterial floor preview is not equivalent.',
            'No final shaded image or light equivalence is asserted.'], 'source_evidence': {}}
    depth = np.zeros((height,width), dtype=np.float64)
    ids = np.zeros((height,width), dtype=np.uint8)
    for obj_index, (eid,label,d) in enumerate(zip(EIDS,LABELS,facts), 1):
        action = d['action']
        assert action == {'numIndices': action['numIndices'], 'numInstances':1, 'indexOffset':0, 'vertexOffset':0, 'instanceOffset':0}, action
        ix = np.fromfile(raw/f'{eid}-indices.bin', dtype='<u2')[:action['numIndices']].astype(np.uint32)
        count = int(ix.max())+1
        positions = np.fromfile(raw/f'{eid}-vb0.bin',dtype='<f4')[:count*3].reshape(-1,3).astype(np.float64)
        scene_cb = np.fromfile(raw/f'{eid}-Vertex-cb1.bin',dtype='<u4')
        draw_instance = np.fromfile(raw/f'{eid}-vb5.bin',dtype='<u4')[0]
        instance_ids = np.fromfile(raw/f'{eid}-Vertex-srv0.bin',dtype='<u4')
        assert draw_instance < 0x80000000
        instance_id = int(instance_ids[draw_instance] & 0xffffff)
        instance = np.fromfile(raw/f'{eid}-Vertex-srv1.bin',dtype='<u4').reshape(-1,4)
        primitive = np.fromfile(raw/f'{eid}-Vertex-srv2.bin',dtype='<f4').reshape(-1,4)
        page_log2, page_mask, page_stride = map(int,scene_cb[:3])
        base = (instance_id >> page_log2)*page_stride + (instance_id & page_mask)
        prim_id = int(instance[base,0] & 0xfffff)
        flags = int(instance[base,0] >> 20)
        packed = instance[base+(1<<page_log2)]
        translation = instance[base+(2<<page_log2)].view('<f4')[:3].astype(np.float64)
        primitive_data = primitive[prim_id*44:(prim_id+1)*44]
        matrix, rotation, scale = decode_transform(packed, translation)
        matrix[3,:3] += primitive_data[1,:3]
        world = np.column_stack([positions,np.ones(count)]) @ matrix
        translated = world.copy()
        translated[:,:3] += pre
        clips = translated @ clip_matrix
        tangent_slot = 4 if eid == 1853 else 3
        tangent = np.fromfile(raw/f'{eid}-Vertex-srv{tangent_slot}.bin',dtype='i1')[:count*8].reshape(-1,2,4)
        tangent = np.maximum(tangent.astype(np.float64)/127,-1)
        local_normal = tangent[:,1,:3]
        world_normal = local_normal @ (rotation * np.sign(scale)[:,None])
        local_tangent = np.cross(np.cross(local_normal,tangent[:,0,:3])*tangent[:,1,3,None],local_normal)*tangent[:,1,3,None]
        world_tangent = local_tangent @ (rotation*np.sign(scale)[:,None])
        post = np.fromfile(raw/f'{eid}-postVS.bin',dtype='<f4').reshape(-1,d['postVS']['vertexByteStride']//4)
        post_ix = np.fromfile(raw/f'{eid}-postVS-indices.bin',dtype='<u2')
        assert np.array_equal(post_ix,ix), 'Unexpected postVS index remapping'
        assert len(post)==count
        delta_clip = np.abs(clips-post[:,:4])
        predicted_screen = np.column_stack([(clips[:,0]/clips[:,3]*.5+.5)*width,(.5-clips[:,1]/clips[:,3]*.5)*height])
        reference_screen = np.column_stack([(post[:,0]/post[:,3]*.5+.5)*width,(.5-post[:,1]/post[:,3]*.5)*height])
        front = clips[:,3] > 0
        check = {'vertex_count':count,'index_count':len(ix),'max_abs_clip_error':float(delta_clip.max()),
            'max_screen_error_pixels_in_front':float(np.abs(predicted_screen[front]-reference_screen[front]).max()),
            'max_world_normal_vs_postVS_error':float(np.abs(world_normal-post[:,8:11]).max()),
            'max_world_tangent_vs_postVS_error':float(np.abs(world_tangent-post[:,4:7]).max())}
        asset = f'mesh-{eid}-{label}.npz'
        np.savez_compressed(out/asset, positions_local_ue_cm=positions.astype('f4'),
            normals_local=local_normal.astype('f4'), tangents_local=local_tangent.astype('f4'),
            tangent_sign=tangent[:,1,3].astype('f4'), positions_world_ue_cm=world[:,:3].astype('f4'),
            normals_world_ue=world_normal.astype('f4'), positions_falcor_m=falcor_vector(world[:,:3],True).astype('f4'),
            normals_falcor=falcor_vector(world_normal).astype('f4'), triangles=ix.reshape(-1,3),
            local_to_world_row_major=matrix, clip_from_reconstructed_geometry=clips,
            unused_uv_placeholder=np.zeros((count,2),dtype='f4'))
        rasterize(clips,ix.reshape(-1,3),width,height,depth,ids,obj_index)
        manifest['objects'].append({'eid':eid,'prepass_eid':{1816:1023,1827:1032,1838:1041,1853:1014}[eid],
            'name':label,'material_name':f'rdc_{label}_{eid}','asset':asset,'asset_sha256':sha(out/asset),
            'vertex_count':count,'triangle_count':len(ix)//3,'instance_id':instance_id,'primitive_id':prim_id,
            'instance_flags':flags,'packed_rotation_scale_u32':packed.astype(np.uint64).tolist(),
            'signed_scale':scale.tolist(),'primitive_position_high_cm':primitive_data[1,:3].tolist(),
            'instance_relative_translation_cm':translation.tolist(),'local_to_world_row_major':matrix.tolist(),
            'world_bounds_ue_cm':[world[:,:3].min(axis=0).tolist(),world[:,:3].max(axis=0).tolist()],
            'material':material_facts(eid,raw),'projection_check':check,
            'uv_status':'not consumed or bound in this draw; unused placeholder explicitly marked',
            'raw_binding_evidence':{'IA':d['buffers'],'VS_buffers':d['readOnly']['Vertex'],
                                    'material_cbuffer':d['cbuffers']['Pixel'][2]}})
        print(eid,label,json.dumps(check))
    raw_depth = gzip.decompress((raw/'capture-depth.bin.gz').read_bytes())
    captured_depth = np.frombuffer(raw_depth,dtype='<f4').reshape(buffer_size[1],buffer_size[0],2)[:height,:width,0]
    overlap = (depth>0) & (captured_depth>0)
    errors = np.abs(depth-captured_depth)
    mismatch = (depth>0) != (captured_depth>0)
    summary = {'resolution':[width,height],'captured_covered_pixels':int((captured_depth>0).sum()),
        'reconstructed_covered_pixels':int((depth>0).sum()),'coverage_mismatch_pixels':int(mismatch.sum()),
        'coverage_iou':float(overlap.sum()/((depth>0)|(captured_depth>0)).sum()),
        'depth_overlap_abs_error_max':float(errors[overlap].max()),
        'depth_overlap_abs_error_p99':float(np.quantile(errors[overlap],.99)),
        'depth_overlap_abs_error_mean':float(errors[overlap].mean()),
        'method':'independent CPU homogeneous clipping + backface culling + pixel-center barycentric reverse depth',
        'limitation':'CPU edges lack hardware subpixel snapping and top-left tie rule; image differences retained, not silently ignored',
        'postvs_role':'verification only; renderable mesh positions derived from original IA+compressed GPUScene data'}
    outlier_yx = np.argwhere(overlap & (errors > 1e-6))
    summary['depth_outliers_above_1e_6'] = [
        {'x':int(x),'y':int(y),'captured':float(captured_depth[y,x]),
         'reconstructed':float(depth[y,x]),'abs_error':float(errors[y,x]),'reconstructed_object_id':int(ids[y,x])}
        for y,x in outlier_yx]
    summary['coverage_mismatch_locations'] = [{'x':int(x),'y':int(y),
        'captured_depth':float(captured_depth[y,x]),'reconstructed_depth':float(depth[y,x])}
        for y,x in np.argwhere(mismatch)]
    colors=np.array([[12,15,22],[85,159,217],[244,181,89],[126,203,163],[87,93,109]],dtype=np.uint8)
    Image.fromarray(colors[ids]).save(out/'reconstructed-coverage.png')
    error_image = np.zeros((height,width,3),dtype=np.uint8)
    error_image[overlap]=[20,50,25]
    error_image[mismatch]=[255,0,255]
    error_image[overlap & (errors>1e-6)]=[255,70,0]
    Image.fromarray(error_image).save(out/'depth-coverage-difference.png')
    np.save(out/'reconstructed-depth.npy',depth.astype('f4'))
    np.save(out/'object-id.npy',ids)
    manifest['projection_verification'] = summary
    manifest['grid_texture'] = next(r for r in facts[-1]['readOnly']['Pixel'] if r['index']==5)
    manifest['grid_texture']['dds_sha256'] = sha(raw/'1853-grid.dds')
    manifest['grid_texture']['captured_view_format'] = 'BC1_UNORM_SRGB'
    manifest['grid_texture']['exported_dds_format'] = 'DXGI_FORMAT_BC1_UNORM; importer must explicitly request sRGB view'
    manifest['grid_sampler'] = {'meaning':'wrap U/V/W, anisotropic8, mipBias0, LOD[0,FLT_MAX]',
        'raw':facts[-1]['PixelSamplers'][0]}
    sources = ('view-layout-evidence.json','shader-1816-Vertex.txt','shader-1853-Vertex.txt',
               'shader-1816-Pixel.txt','shader-1853-Pixel.txt')
    durable = ROOT/'docs/research/ue-legacy-rdc-scene'
    durable.mkdir(parents=True,exist_ok=True)
    for name in sources:
        path = args.evidence/name
        manifest['source_evidence'][name]={'path':str(path.resolve()),'sha256':sha(path)}
        shutil.copyfile(path,durable/name)
    source = Path(r'E:\ue\engine\UnrealEngine\Engine\Shaders\Private\SceneData.ush')
    manifest['source_evidence']['SceneData.ush']={'path':str(source),'sha256':sha(source),'function':'DecodeTransform; GetInstanceSceneDataInternal'}
    write(out/'scene-manifest.json',manifest)
    write(out/'projection-verification.json',summary)
    write(durable/'manifest.json',manifest)
    write(out/'view-uniforms.json',{name:value.tolist() for name,value in view.items()})
    write(durable/'view-uniforms.json',{name:value.tolist() for name,value in view.items()})
    generate_scene(out,manifest)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
