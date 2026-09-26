"""Reconstruct selected native diffuse from observed GPU material/NoL values."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def record(path):
    path=Path(path).resolve()
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def main(path):
    path=Path(path).resolve(); evidence=read(path)
    assert evidence['status']=='prefixes_observed' and evidence['execution_inputs_unchanged']
    images={}
    for run in evidence['runs']:
        r=run['output']; assert record(r['path'])['sha256']==r['sha256']
        assert len(run['unchanged_outputs'])==12 and all(v['raw_equal'] for v in run['unchanged_outputs'].values())
        with np.load(r['path'],allow_pickle=False) as data:
            images[run['name']]={k:data[k].copy() for k in data.files if k!='context_json'}
    selection=read(evidence['selection']['path'])
    assert record(evidence['selection']['path'])['sha256']==evidence['selection']['sha256']
    scene_path=evidence['runs'][0]['context']['pipeline_properties']['sceneDefinition']
    scene=read(scene_path);light=scene['lighting']['lights'][0]
    assert light['type']=='Directional' and light['diffuse_scale']==light['specular_scale']==1
    color=np.array(light['color'],dtype=np.float32)
    rows=[]
    for x,y in selection['selected_pixels_xy']:
        c,metallic,roughness,nol=images['material']['directTransmission'][y,x]
        raw=images['baseline']['gBufferC'][y,x,:3]
        assert np.all(raw==raw[0]),'This scalar-color check only covers the selected gray materials'
        # Fixed captured operation order, with every float32 boundary explicit.
        diffuse=np.float32(c-np.float32(c*metallic))
        diffuse=np.float32(diffuse*np.float32(1/np.pi))
        diffuse=np.float32(diffuse*nol)
        shadow=images['baseline']['directDiffuse'][y,x,3]
        assert shadow in (0,1),'This selection only covers exact identity/zero shadow factors'
        predicted=np.float32(diffuse*np.float32(color*shadow))
        actual=images['baseline']['directDiffuse'][y,x,:3]
        same=np.array_equal(predicted.view(np.uint32),actual.view(np.uint32))
        rows.append({'xy':[x,y],'capture_hdr_residual':[x,y] in selection['mismatch_pixels_xy'],
            'material_nol':images['material']['directTransmission'][y,x].tolist(),
            'normal_and_raw_dot':images['normal']['directTransmission'][y,x].tolist(),
            'view_and_raw_dot':images['view']['directTransmission'][y,x].tolist(),
            'surface_shadow':float(shadow),'predicted_diffuse':predicted.tolist(),'actual_diffuse':actual.tolist(),
            'bitwise_equal':bool(same)})
    result={'status':'native_diffuse_reconstructed' if all(r['bitwise_equal'] for r in rows) else 'native_diffuse_differences',
        'native_observation':record(path),'analysis_script':record(__file__),'scene':record(scene_path),
        'selected_pixels':len(rows),'bitwise_equal_pixels':sum(r['bitwise_equal'] for r in rows),
        'residual_pixels':sum(r['capture_hdr_residual'] for r in rows),'rows':rows,
        'scope':__doc__,'ue_intermediates_observed':False,'capture_equivalence':False,'full_goal_complete':False}
    target=path.parent/'native-diffuse-prefix-analysis.json'
    assert not target.exists()
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'report':record(target),'status':result['status'],'exact':result['bitwise_equal_pixels'],'selected':len(rows)}))
    assert result['status']=='native_diffuse_reconstructed'

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('report',type=Path)
    main(parser.parse_args().report)
