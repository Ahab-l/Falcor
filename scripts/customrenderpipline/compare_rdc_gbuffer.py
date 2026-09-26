"""Independently compare native UE Legacy outputs against captured EID 1853 raw bytes.

All errors are reported, including outside ViewRect. Object interiors only exclude
explicit CPU object-ID boundaries; they do not replace the full-frame comparison.
This performs no GPU operations and asserts no final image equivalence.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def erode(mask, radius):
    h, w = mask.shape
    padded = np.pad(mask, radius)
    result = np.ones_like(mask)
    for dy in range(2*radius+1):
        for dx in range(2*radius+1):
            result &= padded[dy:dy+h, dx:dx+w]
    return result


def stats(native, captured, mask, names):
    if native.ndim == 2:
        native, captured = native[...,None], captured[...,None]
    n, c = native[mask], captured[mask]
    if not len(n):
        return {'pixels':0}
    finite = np.isfinite(n) & np.isfinite(c)
    error = np.abs(n.astype(np.float64)-c.astype(np.float64))
    exact = n == c
    channels = {}
    for i, name in enumerate(names):
        values = error[:,i][finite[:,i]]
        delta = n[:,i].astype(np.float64)-c[:,i].astype(np.float64)
        entry = {'exact_values':int(exact[:,i].sum()), 'nonfinite_values':int((~finite[:,i]).sum()),
            'max_abs_error':float(values.max()) if len(values) else None,
            'mean_abs_error':float(values.mean()) if len(values) else None,
            'p99_abs_error':float(np.quantile(values,.99)) if len(values) else None,
            'p999_abs_error':float(np.quantile(values,.999)) if len(values) else None,
            'signed_mean_error':float(delta[finite[:,i]].mean()) if len(values) else None}
        if np.issubdtype(n.dtype,np.integer):
            entry['over_1_lsb'] = int((values>1).sum())
            entry['over_2_lsb'] = int((values>2).sum())
            unique, count = np.unique(delta.astype(np.int64),return_counts=True)
            order = np.argsort(count)[::-1][:12]
            entry['top_signed_integer_deltas_native_minus_capture'] = [
                {'delta':int(unique[j]),'count':int(count[j])} for j in order]
        channels[name] = entry
    return {'pixels':len(n), 'exact_pixels_all_channels':int(exact.all(axis=1).sum()),
            'different_pixels_any_channel':int((~exact.all(axis=1)).sum()),'channels':channels}


def srgb_to_linear(value):
    return np.where(value<=.04045,value/12.92,((value+.055)/1.055)**2.4)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native',type=Path,default=ROOT/'build/rdc-render/outputs.npz')
    ap.add_argument('--capture-exports',type=Path,default=ROOT.parent/'Falcor/docs/research/captures/2026-09-09-1')
    ap.add_argument('--scene',type=Path,default=ROOT/'build/rdc-scene')
    ap.add_argument('--out',type=Path,default=ROOT/'docs/research/ue-legacy-rdc-scene')
    ap.add_argument('--label',default='grid-initial')
    ap.add_argument('--interior-radius',type=int,default=2)
    args = ap.parse_args()
    assert args.interior_radius >= 0
    assert args.label.replace('-','').replace('_','').isalnum()
    # Snapshot bytes once: a later GPU run can replace outputs.npz without changing this comparison.
    native_bytes = args.native.read_bytes()
    native_npz = np.load(io.BytesIO(native_bytes))
    manifest = json.loads((args.scene/'scene-manifest.json').read_text())
    ex = json.loads((args.capture_exports/'exports-1853.json').read_text())
    width,height = manifest['camera']['buffer_extent']
    x,y,vw,vh = manifest['camera']['view_rect']
    captured, native, evidence = {}, {}, {}
    keys = {'GBufferA':'gBufferA','GBufferB':'gBufferB','GBufferC':'gBufferC','GBufferD':'gBufferD',
            'SceneColor':'sceneColor','SceneDepthZ':'depth'}
    for entry in ex:
        name = entry['texture']['name']
        raw = gzip.decompress((args.capture_exports/entry['rawFile']).read_bytes())
        assert len(raw)==entry['rawBytes'] and digest(raw)==entry['sha256'], name+' capture hash mismatch'
        data = native_npz[keys[name]]
        if name == 'GBufferA':
            captured[name] = np.frombuffer(raw,dtype='<u4').reshape(height,width)
            assert data.nbytes == height*width*4
            native[name] = data.view('<u4').reshape(height,width)
        elif name == 'SceneColor':
            captured[name] = np.frombuffer(raw,dtype='<f2').reshape(height,width,4)
            assert data.dtype == np.float16
            native[name] = data.reshape(height,width,4)
        elif name == 'SceneDepthZ':
            captured[name] = np.frombuffer(raw,dtype='<f4').reshape(height,width,2)[...,0]
            captured['Stencil'] = (np.frombuffer(raw,dtype='<u4').reshape(height,width,2)[...,1]&255).astype(np.uint8)
            native[name] = data.reshape(height,width)
        else:
            captured[name] = np.frombuffer(raw,dtype=np.uint8).reshape(height,width,4)
            assert data.nbytes==height*width*4
            native[name] = data.view(np.uint8).reshape(height,width,4)
        evidence[name] = {'path':str((args.capture_exports/entry['rawFile']).resolve()),
            'uncompressed_sha256':digest(raw),'format':entry['texture']['viewFormat'],
            'native_key':keys[name],'native_original_shape':list(data.shape),'native_original_dtype':str(data.dtype)}
    if 'stencil' in native_npz:
        stencil = native_npz['stencil']
        assert stencil.dtype == np.uint8 and stencil.shape == (height, width), 'native stencil must be raw uint8 HxW'
        native['Stencil'] = stencil
    if 'nativeDepth' in native_npz:
        native_depth = native_npz['nativeDepth']
        assert native_depth.dtype == np.float32 and native_depth.shape == (height, width), 'native depth must be raw float32 HxW'
        native['NativeDepthPlane'] = native_depth
    active = np.zeros((height,width),dtype=bool)
    active[y:y+vh,x:x+vw] = True
    ccov, ncov = captured['SceneDepthZ']>0,native['SceneDepthZ']>0
    overlap = ccov & ncov
    ids = np.zeros((height,width),dtype=np.uint8)
    ids[y:y+vh,x:x+vw] = np.load(args.scene/'object-id.npy')
    scopes = {'full_extent':np.ones((height,width),dtype=bool),'view_rect':active,
              'outside_view_rect':~active,'covered_overlap':overlap,'background_both':~ccov & ~ncov}
    for i,obj in enumerate(manifest['objects'],1):
        mask = ids==i
        scopes[obj['name']+'_full_cpu_id'] = mask
        scopes[obj['name']+'_interior'] = erode(mask,args.interior_radius)&overlap
    report = {'schema':'ue-rdc-native-gbuffer-comparison-v1','label':args.label,
        'native_npz':str(args.native.resolve()),'native_npz_sha256':digest(native_bytes),
        'extent':[width,height],'view_rect':[x,y,vw,vh],'capture_sources':evidence,
        'native_array_format':'A flat uint8 reinterpreted as little-endian R10G10B10A2 uint32; B/C/D raw BGRA uint8; SceneColor RGBA float16; depth float32',
        'interior_definition':f'CPU object-id mask eroded by square radius {args.interior_radius} pixels, intersected with both coverages',
        'scope_definition':'All full-frame errors retained. Interior excludes only declared boundaries; CPU IDs do not prove native material identity.',
        'final_image_equivalence':False,'scopes':{}}
    decoded = {}
    for source,arrays in [('captured',captured),('native',native)]:
        a = arrays['GBufferA']
        ac = np.stack([a&1023,(a>>10)&1023,(a>>20)&1023,(a>>30)&3],axis=-1).astype(np.uint16)
        decoded[source] = {'A':ac,'normal':ac[...,:3].astype(np.float64)*(2/1023)-1,
            'model':arrays['GBufferB'][...,3]&31,'flags':arrays['GBufferB'][...,3]&224,
            'C_linear':srgb_to_linear(arrays['GBufferC'][...,[2,1,0]].astype(np.float64)/255)}
    for scope,mask in scopes.items():
        rows = {}
        rows['GBufferA_packed_uint32'] = stats(native['GBufferA'],captured['GBufferA'],mask,['packed_word'])
        rows['GBufferA_components_integer'] = stats(decoded['native']['A'],decoded['captured']['A'],mask,['normal_x_10','normal_y_10','normal_z_10','per_object_2'])
        rows['GBufferB_raw_BGRA'] = stats(native['GBufferB'],captured['GBufferB'],mask,['roughness_B','specular_G','metallic_R','model_and_flags_A'])
        rows['GBufferC_raw_BGRA'] = stats(native['GBufferC'],captured['GBufferC'],mask,['baseColor_sRGB_B','baseColor_sRGB_G','baseColor_sRGB_R','AO_A'])
        rows['GBufferD_raw_BGRA'] = stats(native['GBufferD'],captured['GBufferD'],mask,['B','G','R','A'])
        rows['SceneColor_half_values'] = stats(native['SceneColor'],captured['SceneColor'],mask,['R','G','B','A'])
        rows['SceneColor_half_bits'] = stats(native['SceneColor'].view('<u2'),captured['SceneColor'].view('<u2'),mask,['R_bits','G_bits','B_bits','A_bits'])
        rows['normal_components_UE'] = stats(decoded['native']['normal'],decoded['captured']['normal'],mask,['X','Y','Z'])
        nerr = np.abs(decoded['native']['normal'][mask]-decoded['captured']['normal'][mask])
        rows['normal_component_quantization'] = {'one_10bit_lsb_in_normal_space':2/1023,
            'pixels_over_one_lsb':int((nerr>2/1023+1e-12).any(axis=1).sum()),
            'pixels_over_two_lsb':int((nerr>4/1023+1e-12).any(axis=1).sum())}
        rows['baseColor_decoded_linear'] = stats(decoded['native']['C_linear'],decoded['captured']['C_linear'],mask,['R','G','B'])
        rows['shading_model_low5_bits'] = stats(decoded['native']['model'],decoded['captured']['model'],mask,['modelID'])
        rows['selective_output_high3_bits'] = stats(decoded['native']['flags'],decoded['captured']['flags'],mask,['flags'])
        rows['depth'] = stats(native['SceneDepthZ'],captured['SceneDepthZ'],mask,['reverse_z'])
        if 'Stencil' in native:
            rows['stencil_raw_uint8'] = stats(native['Stencil'], captured['Stencil'], mask, ['stencil'])
        if 'NativeDepthPlane' in native:
            rows['native_depth_plane_bits'] = stats(native['NativeDepthPlane'].view('<u4'), captured['SceneDepthZ'].view('<u4'), mask, ['depth_bits'])
        report['scopes'][scope] = rows
    de = np.abs(native['SceneDepthZ'].astype(np.float64)-captured['SceneDepthZ'])
    bad = overlap & (de>1e-6)
    report['depth_summary'] = {'captured_covered':int(ccov.sum()),'native_covered':int(ncov.sum()),
        'coverage_mismatch':int((ccov!=ncov).sum()),'outlier_threshold':1e-6,
        'outliers':[{'x':int(xx),'y':int(yy),'captured':float(captured['SceneDepthZ'][yy,xx]),
            'native':float(native['SceneDepthZ'][yy,xx]),'abs_error':float(de[yy,xx]),'cpu_object_id':int(ids[yy,xx])}
            for yy,xx in np.argwhere(bad)],
        'coverage_mismatch_locations':[{'x':int(xx),'y':int(yy)} for yy,xx in np.argwhere(ccov!=ncov)],
        'stencil':'capture stencil retained in source; native outputs contain no stencil plane, so stencil equivalence is untested'}
    if 'Stencil' in native:
        stencil_bad = native['Stencil'] != captured['Stencil']
        report['depth_summary']['stencil'] = {'compared': True, 'mismatch_pixels': int(stencil_bad.sum()),
            'captured_values': {str(int(v)): int(n) for v, n in zip(*np.unique(captured['Stencil'], return_counts=True))},
            'native_values': {str(int(v)): int(n) for v, n in zip(*np.unique(native['Stencil'], return_counts=True))},
            'mismatches': [{'x': int(xx), 'y': int(yy), 'captured': int(captured['Stencil'][yy, xx]),
                'native': int(native['Stencil'][yy, xx])} for yy, xx in np.argwhere(stencil_bad)]}
    if 'NativeDepthPlane' in native:
        report['depth_summary']['native_depth_plane_bits_exact'] = bool(np.array_equal(
            native['NativeDepthPlane'].view('<u4'), captured['SceneDepthZ'].view('<u4')))
        report['depth_summary']['native_depth_vs_copy_bits_exact'] = bool(np.array_equal(
            native['NativeDepthPlane'].view('<u4'), native['SceneDepthZ'].view('<u4')))
    aerr = np.abs(decoded['native']['A'].astype(np.int32)-decoded['captured']['A'].astype(np.int32))
    report['summary'] = {'normal_rgb_exact_pixels':int((aerr[...,:3]==0).all(axis=-1)[overlap].sum()),
        'per_object_alpha_exact_pixels':int((aerr[...,3]==0)[overlap].sum()),
        'model_bits_exact_pixels':int((decoded['native']['model']==decoded['captured']['model'])[overlap].sum()),
        'gbufferB_exact_pixels':int((native['GBufferB']==captured['GBufferB']).all(axis=-1)[overlap].sum()),
        'gbufferC_exact_pixels':int((native['GBufferC']==captured['GBufferC']).all(axis=-1)[overlap].sum()),
        'gbufferD_exact_full_extent':bool(np.array_equal(native['GBufferD'],captured['GBufferD'])),
        'sceneColor_half_bits_exact_full_extent':bool(np.array_equal(native['SceneColor'].view('<u2'),captured['SceneColor'].view('<u2')))}
    args.out.mkdir(parents=True,exist_ok=True)
    prefix = args.out/f'native-{args.label}'
    prefix.with_suffix('.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    pictures = args.scene/f'native-{args.label}'
    pictures.mkdir(parents=True,exist_ok=True)
    for name in ['GBufferB','GBufferC']:
        diff = np.max(np.abs(native[name].astype(np.int16)-captured[name].astype(np.int16))[...,:3],axis=-1)
        im = np.zeros((height,width,3),dtype=np.uint8)
        im[diff==1]=[100,180,255]
        im[diff>1]=[255,140,0]
        im[diff>10]=[255,0,100]
        Image.fromarray(im).save(pictures/(name+'-integer-difference.png'))
    for kind,arrays in [('capture',captured),('native',native)]:
        Image.fromarray(arrays['GBufferC'][...,[2,1,0]][y:y+vh,x:x+vw]).save(pictures/(kind+'-baseColor-sRGB.png'))
    lines = [f'# Native GBuffer comparison: {args.label}', '',
        f'Native NPZ SHA-256: `{report["native_npz_sha256"]}`. All capture files passed their recorded uncompressed byte/hash checks.', '',
        'This report compares captured EID 1853 physical attachments. It does not assert final shaded-image equality.', '',
        f'Extent {width}×{height}; ViewRect {vw}×{vh}. Coverage mismatch: **{int((ccov!=ncov).sum())}** pixels. Depth outliers above 1e-6: **{int(bad.sum())}**. Exact coordinates are retained in the JSON.', '',
        '| Scope | Pixels | A normal RGB exact | A alpha exact | B exact | C exact | Model bits exact |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for scope in ['full_extent','covered_overlap']+[o['name']+'_interior' for o in manifest['objects']]:
        mask=scopes[scope];r=report['scopes'][scope]
        lines.append(f'| {scope} | {int(mask.sum())} | {int((aerr[...,:3]==0).all(axis=-1)[mask].sum())} | {int((aerr[...,3]==0)[mask].sum())} | {r["GBufferB_raw_BGRA"]["exact_pixels_all_channels"]} | {r["GBufferC_raw_BGRA"]["exact_pixels_all_channels"]} | {r["shading_model_low5_bits"]["exact_pixels_all_channels"]} |')
    lines += ['',f'Object interiors exclude a {args.interior_radius}-pixel square radius around the independently reconstructed CPU object-ID boundaries. Full extent, ViewRect, background, full object-ID regions and interiors are all reported separately.', '',
        'The JSON includes signed integer error histograms, mean/p99/p999/max component errors, one/two-LSB exceedance counts, RGBA half values and raw half-bit comparisons, decoded sRGB linear errors, low-five shading-model bits (mask31) and high-three selective-output flags (mask224), matching this customized UE Schema. Normal comparisons use 2/1023 per stored 10-bit step; no tolerance is silently treated as equality.', '',
        f'GBufferD exact over full extent: **{report["summary"]["gbufferD_exact_full_extent"]}**. SceneColor half bits exact over full extent: **{report["summary"]["sceneColor_half_bits_exact_full_extent"]}**.', '',
        f'Difference images and capture/native baseColor previews: `{pictures}`.', '',
        (f'Native stencil is compared over the whole allocation: **{int((native["Stencil"] != captured["Stencil"]).sum())}** mismatched pixels.'
         if 'Stencil' in native else 'Native stencil is absent from the NPZ and is not compared.'),
        (f'Native depth-plane bits match capture over the whole allocation: **{report["depth_summary"]["native_depth_plane_bits_exact"]}**.'
         if 'NativeDepthPlane' in native else 'Native depth-plane readback is absent; depthCopy alone is compared.'),
        'A small raw packed-word difference is not a normal tolerance; A is also compared component-by-component.']
    prefix.with_suffix('.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(prefix.with_suffix('.json')),'summary':report['summary'],'depth':report['depth_summary']},indent=2))


if __name__=='__main__':
    main()
