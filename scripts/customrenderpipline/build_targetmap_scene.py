"""Assemble a native scene only from independently exported original UE sources."""
import argparse,hashlib,json,re,shutil,struct
from pathlib import Path
import numpy as np
from source_scene import load_ue_internal_obj,ue_instance_transform
ROOT=Path(__file__).resolve().parents[2]

def identity(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}

def verify(entry):
    actual=identity(entry['path'])
    if any(actual[key]!=entry[key] for key in ('sha256','bytes')):raise ValueError('Changed source export: '+entry['path'])
    return Path(entry['path'])

def assemble(inventory_dir,mesh_dir,output):
    inventory_dir,mesh_dir,output=map(Path,(inventory_dir,mesh_dir,output))
    inventory=json.loads((inventory_dir/'inventory.json').read_text())
    materials=json.loads((inventory_dir/'materials.json').read_text())
    assets=json.loads((mesh_dir/'assets.json').read_text())
    for directory in (inventory_dir,mesh_dir):
        result=json.loads((directory/'result.json').read_text())
        if result['status']!='passed' or result['source_files_changed']:raise ValueError('Source export did not pass')
    if materials['status']!='passed' or materials['capture_inputs'] or assets['capture_inputs']:raise ValueError('Invalid original asset provenance')
    output.mkdir(parents=True,exist_ok=True)
    copied={}
    for asset in assets['assets']:
        record=next(e for e in asset['exports'] if e['relative_path']==asset['indexed_obj'])
        source=verify(record);target=output/'Meshes'/source.name;target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source,target)
        mesh=load_ue_internal_obj(target)
        if len(mesh.triangles)!=asset['lods'][0]['triangles']:raise ValueError('Source LOD0 triangle count mismatch')
        copied[asset['object']]={'file':identity(target),'source_asset':asset['object'],'source_files':asset['source_files'],
            'vertices':len(mesh.positions),'triangles':len(mesh.triangles),'role':'sky' if 'SkySphere' in asset['object'] else 'opaque'}
    table={entry['object']:entry for entry in materials['materials']}
    basic=table['/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial']
    defaults={e['parameter_name']:e['default_value'] for e in basic['expressions'] if 'parameter_name' in e}
    floor=table['/Engine/OpenWorldTemplate/LandscapeMaterial/M_ProcGrid.M_ProcGrid']
    params={e['parameter_name']:e['default_value'] for e in floor['expressions'] if 'parameter_name' in e}
    instance=table['/Engine/OpenWorldTemplate/LandscapeMaterial/MI_ProcGrid.MI_ProcGrid']
    instance_text=verify(instance['text']).read_text(encoding='utf-8-sig')
    switches={name:value=='True' for value,name in re.findall(r'(?:Value=(True|False),)?ParameterInfo=\(Name="([^"]+)"\),bOverride=True',instance_text)}
    if switches!={'ObjectAligned':True,'Tri-Planar (Or Uni-Planar)':True,'Enable Side Tint':False,'Water Level Tint':False}:
        raise ValueError('Source ProcGrid shader requires the exported targetmap static-switch branch')
    colors={}
    for name,r,g,b in re.findall(r'Name="(Checker Colour [12])".*?ParameterValue=\(R=([^,]+),G=([^,]+),B=([^,]+),',instance_text):
        colors[name]=[float(np.float32(v)) for v in (r,g,b)]
    if len(colors)!=2:raise ValueError('Missing original material instance color overrides')
    texture=next(e for e in materials['textures'] if e['object'].endswith('/T_GridChecker_A.T_GridChecker_A'))
    payload=verify(texture['source_image']).read_bytes()
    # UE exported original source pixels as a DX10 BGRA8 sRGB DDS, one mip.
    # Convert just its container so Falcor can construct its native mip chain.
    if payload[:4]!=b'DDS ' or payload[84:88]!=b'DX10' or struct.unpack_from('<5I',payload,128)!=(91,3,0,1,0):
        raise ValueError('Expected the original single-slice BGRA8 sRGB source DDS')
    h,w=struct.unpack_from('<2I',payload,12)
    if len(payload)!=148+w*h*4:raise ValueError('Unexpected source-image mip/byte layout')
    texfile=output/'T_GridChecker_A.tga'
    texfile.write_bytes(struct.pack('<BBBHHBHHHHBB',0,0,2,0,0,0,0,0,w,h,32,0x28)+payload[148:])
    log=(inventory_dir/'unreal.log').read_text(encoding='utf-8-sig')
    saved=log.split('TARGETMAP_SAVED_EDITOR_VIEWS_BEGIN',1)[1].split('TARGETMAP_SAVED_EDITOR_VIEWS_END',1)[0]
    match=re.search(r'3: \(CamPosition=\(X=([^,]+),Y=([^,]+),Z=([^\)]+)\),CamRotation=\(Pitch=([^,]+),Yaw=([^,]+),Roll=([^\)]+)\)',saved)
    if not match:raise ValueError('Map did not export its saved perspective view')
    view=list(map(float,match.groups()))
    camera={'position_cm':view[:3],'rotation_pitch_yaw_roll':view[3:],'horizontal_fov_degrees':90.0,'near_cm':10.0,
        'resolution':[1421,1035],'falcor_far_m':20000.0,
        'provenance':'Saved targetmap.World.EditorViews[3]; FOV from saved viewport config, Near from Engine BaseEngine.ini; resolution is authored validation extent',
        'capture_camera_verified':False}
    def surface(color,roughness,program='constant',model='DefaultLit',tags=None):
        return {'shading_model':model,'material_program':program,'base_color_linear':color,'roughness':roughness,
            'metallic':0,'specular':0.5,'emissive_linear':[0,0,0],'render_tags':tags or ['Opaque']}
    scene={'version':1,'id':'targetmap-source-v1','capture_inputs':False,'camera':camera,'source_meshes':copied,
        'materials':{'BasicShape':surface(defaults['Color'][:3],defaults['Roughness']),
                     'ProcGrid':surface(colors['Checker Colour 1'],params['Checker Rough 1'],'shader'),
                     'SkyDomePending':surface([0,0,0],1,model='Unlit',tags=['Sky','Pending'])},'instances':[]}
    mapping={'/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial':'BasicShape',
        '/Engine/OpenWorldTemplate/LandscapeMaterial/MI_ProcGrid.MI_ProcGrid':'ProcGrid',
        '/Engine/EngineSky/M_SimpleSkyDome.M_SimpleSkyDome':'SkyDomePending'}
    for actor in inventory['actors']:
        for mesh in actor['meshes']:
            if len(mesh['materials'])!=1:raise ValueError('Source importer currently requires one material section')
            if actor['location_cm']!=mesh['world_location_cm']:raise ValueError('Actor-relative material origin needs explicit component offset support')
            scene['instances'].append({'id':actor['label'],'mesh':mesh['asset'],'material':mapping[mesh['materials'][0]],
                'translation_cm':mesh['world_location_cm'],'rotation_pitch_yaw_roll':mesh['world_rotation'],'scale':mesh['world_scale'],
                'casts_shadow':mesh['cast_shadow'],'source_material':mesh['materials'][0]})
            scene['instances'][-1]['shadow_flags']={key:mesh[key] for key in (
                'cast_shadow','cast_dynamic_shadow','cast_hidden_shadow','cast_shadow_as_two_sided','visible','reverse_culling') if key in mesh}
    sun=next(a for a in inventory['actors'] if a['class']=='DirectionalLight')
    forward=ue_instance_transform(rotation_deg=sun['rotation_pitch_yaw_roll']).matrix[:3,:3]@np.array([0,0,-1])
    ray=[-forward[2],forward[0],forward[1]]
    light=sun['lights'][0]
    scene['lighting']={'lights':[{'type':'Directional','direction_ue':[-float(v) for v in ray]}]}
    scene['source_directional_light']={'actor':sun,'ray_direction_ue':ray,'shadows_pending':True}
    if 'shadow_source_defaults' in inventory:
        scene['source_directional_light'].update(source_defaults=inventory['shadow_source_defaults'],
            defaults_provenance=inventory['shadow_source_defaults_provenance'])
    if 'atmosphere_source_defaults' in inventory:
        from atmosphere import source_atmosphere
        physical,lut_settings=source_atmosphere(inventory)
        scene['source_environment']={'actors':[a for a in inventory['actors'] if a.get('environment') or a['class']=='SkyLight'],
            'source_defaults':inventory['atmosphere_source_defaults'],
            'defaults_provenance':inventory['atmosphere_source_defaults_provenance'],
            'atmosphere_parameters':physical,'atmosphere_lut_settings':lut_settings,
            'renderer_source_settings':inventory['renderer_source_settings'],
            'working_color_space':{'choice':inventory['renderer_source_settings']['working_color_space_choice'],
                'name':inventory['renderer_source_settings']['working_color_space_choice_name'],
                'chromaticities':inventory['renderer_source_settings']['working_color_space_chromaticities'],
                'provenance':inventory['renderer_source_settings']['provenance']}}
    from sun_setup import source_sun_settings
    if 'source_environment' not in scene:raise ValueError('Source sun requires an inventory with verified atmosphere/renderer settings')
    scene['lighting']['lights'][0]['source_sun']=source_sun_settings(light,scene['source_environment'])
    scene['procgrid_parameters']={'tileSize':params['Tile Scale'],'checkerColor1':colors['Checker Colour 1'],
        'checkerColor2':colors['Checker Colour 2'],'lineColor':params['Line Colour'][:3],
        'checkerRoughness1':params['Checker Rough 1'],'checkerRoughness2':params['Checker Rough 2'],'lineRoughness':float(np.float32(0.3))}
    scene['source_texture']={'file':identity(texfile),'original_export':texture,'native_mips':'Falcor sRGB linear-filter mip generation; UE platform compression/build not yet reproduced'}
    scene['provenance']={'inventory':identity(inventory_dir/'inventory.json'),'materials':identity(inventory_dir/'materials.json'),
        'mesh_exports':identity(mesh_dir/'assets.json'),'map_source':next(e for e in json.loads((inventory_dir/'result.json').read_text())['sources'] if e['path'].endswith('targetmap.umap')),
        'export_precision':'Original Engine render LOD0 OBJ positions/UV0/normals at six decimals; Falcor packs normals and regenerates tangents',
        'pending':['Sky/atmosphere/cloud/fog','source directional shadow generation','UE texture build/compression/mips','GI/reflections/postprocess/full-image validation']}
    path=output/'Scene.json';path.write_text(json.dumps(scene,indent=2),encoding='utf-8')
    return path

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path,required=True);parser.add_argument('--meshes',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'build/source-targetmap')
    a=parser.parse_args();print(assemble(a.inventory,a.meshes,a.output))
