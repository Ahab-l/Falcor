"""Offline source-triangle oracle for native CSM depth; never a render input."""
import json
from pathlib import Path
import numpy as np
from source_scene import load_ue_internal_obj,ue_instance_transform
from build_targetmap_scene import verify

def validate(scene,parameters,depths):
    triangles=[];normals=[];labels=[]
    for instance in scene['instances']:
        f=instance['shadow_flags']
        if not f['cast_shadow'] or not f['cast_dynamic_shadow'] or not (f['visible'] or f['cast_hidden_shadow']):continue
        if f['cast_shadow_as_two_sided'] or f['reverse_culling']:raise ValueError('This source oracle fixture expects one-sided ordinary winding')
        mesh=load_ue_internal_obj(verify(scene['source_meshes'][instance['mesh']]['file']))
        xf=ue_instance_transform(instance['translation_cm'],instance['rotation_pitch_yaw_roll'],instance['scale'])
        world=xf.transform_positions(mesh.positions)
        rotation=xf.matrix[:3,:3]/np.linalg.norm(xf.matrix[:3,:3],axis=0)
        # SceneTypes.slang PackedStaticVertexData stores normal components as
        # f16. Account for that declared vertex format before evaluating bias.
        normal=mesh.normals.astype(np.float16).astype(np.float64)@rotation.T
        triangles.extend(world[mesh.triangles]);normals.extend(normal[mesh.triangles]);labels.extend([instance['id']]*len(mesh.triangles))
    triangles=np.array(triangles);normals=np.array(normals);labels=np.array(labels)
    geometric=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    reports=[]
    for cascade,depth in enumerate(depths):
        c=parameters[4+cascade*8:12+cascade*8].astype(float)
        points=np.concatenate([triangles,np.ones((*triangles.shape[:2],1))],axis=2)@c[:4].T
        # Independent orthographic raster barycentrics over original source
        # triangles; full outer projection includes the four-texel border.
        size=parameters[2,0];border=parameters[2,1]
        xy=points[:,:,:2]/points[:,:,3,None]*(size-2*border)/size
        xy=(xy*[1,-1]+1)*size*.5
        z=points[:,:,2].copy();z[z>1]=.999999
        nol=np.abs(normals@c[6,:3]);slope=np.sqrt(np.clip(1-nol*nol,0,1))/np.maximum(nol,1e-30)
        z=1-z+c[5,0]+c[5,1]*np.clip(slope,0,c[5,2])
        a=xy[:,0];u=xy[:,1]-a;v=xy[:,2]-a
        determinant=u[:,0]*v[:,1]-u[:,1]*v[:,0]
        with np.errstate(divide='ignore',invalid='ignore'):
            gradient_x=((z[:,1]-z[:,0])*v[:,1]-(z[:,2]-z[:,0])*u[:,1])/determinant
            gradient_y=(u[:,0]*(z[:,2]-z[:,0])-v[:,0]*(z[:,1]-z[:,0]))/determinant
        facing=geometric@c[6,:3]>1e-10
        maxima=0.;tested=0;hits={};clear=0
        for y in range(17,int(size),61):
            for x in range(19,int(size),59):
                d=np.array([x+.5,y+.5])-a
                with np.errstate(divide='ignore',invalid='ignore'):
                    bu=(d[:,0]*v[:,1]-d[:,1]*v[:,0])/determinant
                    bv=(u[:,0]*d[:,1]-u[:,1]*d[:,0])/determinant
                inside=facing&(bu>=0)&(bv>=0)&(bu+bv<=1)
                weights=np.stack([1-bu-bv,bu,bv],axis=1)
                pixel_z=(weights*z).sum(axis=1)
                valid=inside&(pixel_z>=0)&(pixel_z<=1)
                if not valid.any():
                    assert depth[y,x]==1,(cascade,x,y,'Expected clear',depth[y,x]);clear+=1;continue
                nearest=np.argmin(np.where(valid,pixel_z,np.inf))
                if weights[nearest].min()<.002:continue
                error=abs(float(depth[y,x])-pixel_z[nearest])
                # D3D raster XY has eight fractional bits. A one-subpixel
                # perturbation in each axis bounds slope-dependent depth error;
                # retain a small float32 arithmetic floor, not a scene-wide
                # tolerance scaled from the observed residual.
                budget=5e-7+(abs(gradient_x[nearest])+abs(gradient_y[nearest]))/256
                assert error<budget,(cascade,x,y,error,budget,labels[nearest],float(depth[y,x]),pixel_z[nearest])
                maxima=max(maxima,error);tested+=1;label=labels[nearest];hits[label]=hits.get(label,0)+1
        assert tested>0
        reports.append(dict(cascade=cascade,samples=tested,clear_samples=clear,max_depth_error=maxima,hits=hits))
    return reports

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('evidence',type=Path)
    args=parser.parse_args();arrays=np.load(args.evidence/'raw.npz')
    result=validate(json.loads((args.evidence/'Scene.json').read_text()),arrays['parameters'],[arrays[f'depth{i}'] for i in range(4)])
    (args.evidence/'depth-oracle.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
