"""Read the saved target map in a scratch UE project; never save packages."""
import hashlib,json,os,re
from pathlib import Path
import unreal

out=Path(os.environ['UE_TARGETMAP_INVENTORY_OUT'])
scratch=Path(unreal.Paths.project_dir()).resolve()
if scratch!= (out/'Scratch').resolve():
    raise RuntimeError('Target map inventory must run in its isolated project')
subsystem=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
# Export the package's serialized editor view before an editor viewport can
# overlay per-user settings. GETALL reads reflected text without changing it.
saved_world=unreal.load_object(None,'/Game/targetmap.targetmap')
if not saved_world:raise RuntimeError('Could not read saved /Game/targetmap')
unreal.log('TARGETMAP_SAVED_EDITOR_VIEWS_BEGIN')
unreal.SystemLibrary.execute_console_command(saved_world,'getall World EditorViews NAME=targetmap OUTER=/Game/targetmap')
unreal.log('TARGETMAP_SAVED_EDITOR_VIEWS_END')
world=unreal.EditorLoadingAndSavingUtils.load_map(str(scratch/'Content/targetmap.umap'))
if not world:raise RuntimeError('Could not load /Game/targetmap')
result={'source':'saved UE source packages in an isolated project','map':'/Game/targetmap',
        'capture_inputs':False,'actors':[],'world':world.get_path_name()}

def value(v):
    if v is None or isinstance(v,(str,bool,int,float)):return v
    if isinstance(v,unreal.Object):return v.get_path_name()
    if isinstance(v,unreal.Vector):return [v.x,v.y,v.z]
    if isinstance(v,unreal.Rotator):return [v.pitch,v.yaw,v.roll]
    if isinstance(v,unreal.Color):return [v.r,v.g,v.b,v.a]
    if isinstance(v,unreal.LinearColor):return [v.r,v.g,v.b,v.a]
    return str(v)

def properties(obj,keys):
    answer={}
    for key in keys:
        try:answer[key]=value(obj.get_editor_property(key))
        except Exception:pass
    return answer

for actor in subsystem.get_all_level_actors():
    item={'name':actor.get_name(),'label':actor.get_actor_label(),'class':actor.get_class().get_name(),
        'location_cm':value(actor.get_actor_location()),'rotation_pitch_yaw_roll':value(actor.get_actor_rotation()),
        'scale':value(actor.get_actor_scale3d()),'meshes':[],'lights':[],'cameras':[]}
    for comp in actor.get_components_by_class(unreal.StaticMeshComponent):
        mesh=comp.get_editor_property('static_mesh')
        entry={'component':comp.get_name(),'asset':value(mesh),
            'world_location_cm':value(comp.get_world_location()),'world_rotation':value(comp.get_world_rotation()),
            'world_scale':value(comp.get_world_scale()),
            'materials':[value(m) for m in comp.get_materials()]}
        entry.update(properties(comp,['cast_shadow','visible','mobility','reverse_culling','cast_dynamic_shadow',
                                      'cast_hidden_shadow','cast_shadow_as_two_sided']))
        item['meshes'].append(entry)
    for comp in actor.get_components_by_class(unreal.LightComponentBase):
        item['lights'].append({'class':comp.get_class().get_name(),
            'world_location_cm':value(comp.get_world_location()),'world_rotation':value(comp.get_world_rotation()),
            **properties(comp,[
            'intensity','light_color','cast_shadows','mobility','indirect_lighting_intensity',
            'volumetric_scattering_intensity','source_type','cubemap','source_cubemap_angle',
            'real_time_capture','attenuation_radius','intensity_units','use_inverse_squared_falloff',
            'source_radius','soft_source_radius','source_length','inner_cone_angle','outer_cone_angle',
            'dynamic_shadow_distance_movable_light','dynamic_shadow_cascades','cascade_distribution_exponent',
            'cascade_transition_fraction','shadow_distance_fadeout_fraction','shadow_bias','shadow_slope_bias',
            'shadow_filter_sharpen','shadow_resolution_scale','shadow_cascade_bias_distribution',
            'use_ray_traced_distance_field_shadows','distance_field_shadow_distance','far_shadow_cascade_count',
            'far_shadow_distance','light_source_angle','light_source_soft_angle','trace_distance','contact_shadow_length',
            'cast_contact_shadow','cast_dynamic_shadows','cast_static_shadows','shadow_sharpen',
            'cast_shadows_on_clouds','cast_shadows_on_atmosphere','atmosphere_sun_light','atmosphere_sun_light_index',
            'atmosphere_sun_disk_color_scale','per_pixel_atmosphere_transmittance','use_temperature','temperature',
            'lower_hemisphere_is_black','lower_hemisphere_color','cubemap_resolution','sky_distance_threshold'])})
    # Export actual serialized/reflected component values, including constructor
    # defaults. These are source inputs, never capture constants or LUT exports.
    environment_types={
        'SkyAtmosphereComponent':[
            'transform_mode','bottom_radius','atmosphere_height','ground_albedo','multi_scattering_factor',
            'trace_sample_count_scale','rayleigh_scattering_scale','rayleigh_scattering','rayleigh_exponential_distribution',
            'mie_scattering_scale','mie_scattering','mie_absorption_scale','mie_absorption','mie_anisotropy',
            'mie_exponential_distribution','other_absorption_scale','other_absorption','other_tent_distribution',
            'sky_luminance_factor','sky_and_aerial_perspective_luminance_factor','aerial_pespective_view_distance_scale',
            'height_fog_contribution','transmittance_min_light_elevation_angle','aerial_perspective_start_depth'],
        'ExponentialHeightFogComponent':[
            'fog_density','fog_height_falloff','second_fog_data','fog_inscattering_luminance','fog_max_opacity',
            'start_distance','fog_cutoff_distance','directional_inscattering_exponent','directional_inscattering_start_distance',
            'directional_inscattering_luminance','volumetric_fog','volumetric_fog_scattering_distribution',
            'volumetric_fog_albedo','volumetric_fog_emissive','volumetric_fog_extinction_scale','volumetric_fog_distance',
            'override_light_colors_with_fog_inscattering_colors','inscattering_color_cubemap'],
        'VolumetricCloudComponent':[
            'layer_bottom_altitude','layer_height','tracing_start_max_distance','tracing_max_distance','planet_radius',
            'ground_albedo','material','view_sample_count_scale','reflection_view_sample_count_scale',
            'shadow_view_sample_count_scale','shadow_reflection_view_sample_count_scale','shadow_tracing_distance',
            'stop_tracing_transmittance_threshold','use_per_sample_atmospheric_light_transmittance']}
    item['environment']=[]
    for class_name,keys in environment_types.items():
        for comp in actor.get_components_by_class(getattr(unreal,class_name)):
            entry={'class':class_name,'component':comp.get_name(),
                'world_location_cm':value(comp.get_world_location()),'world_rotation':value(comp.get_world_rotation()),
                'world_scale':value(comp.get_world_scale()),**properties(comp,keys)}
            if class_name=='SkyAtmosphereComponent':
                entry['light_direction_overrides']=[
                    {'enabled':comp.is_atmosphere_light_direction_overriden(index),
                     'direction':value(comp.get_overriden_atmosphere_light_direction(index))} for index in range(2)]
            for key,fields in (('other_tent_distribution',['tip_altitude','tip_value','width']),
                               ('second_fog_data',['fog_density','fog_height_falloff','fog_height_offset'])):
                if key in entry:entry[key]=properties(comp.get_editor_property(key),fields)
            item['environment'].append(entry)
    for comp in actor.get_components_by_class(unreal.CameraComponent):
        item['cameras'].append(properties(comp,['field_of_view','aspect_ratio','projection_mode','ortho_width']))
    if isinstance(actor,unreal.PostProcessVolume):
        item['postprocess_volume']=properties(actor,['enabled','unbound','blend_weight','priority'])
        settings=actor.get_editor_property('settings')
        item['postprocess']=properties(settings,[
            'auto_exposure_method','auto_exposure_bias','auto_exposure_min_brightness','auto_exposure_max_brightness',
            'auto_exposure_speed_up','auto_exposure_speed_down','auto_exposure_low_percent','auto_exposure_high_percent',
            'dynamic_global_illumination_method','reflection_method','screen_space_reflection_intensity',
            'screen_space_reflection_quality','bloom_intensity','motion_blur_amount','vignette_intensity'])
    result['actors'].append(item)
result['actor_count']=len(result['actors'])
shadow_cvars=('r.ShadowQuality','r.Shadow.MaxCSMResolution','r.Shadow.CSM.MaxCascades','r.Shadow.DistanceScale',
    'r.Shadow.CSM.TransitionScale','r.Shadow.CSMDepthBias','r.Shadow.CSMSlopeScaleDepthBias',
    'r.Shadow.ShadowMaxSlopeScaleDepthBias','r.Shadow.CSMReceiverBias','r.Shadow.CSMShadowDistanceFadeoutMultiplier',
    'r.Shadow.FilterMethod','r.Shadow.CSMCaching','r.DistanceFieldShadowing','r.HeightFieldShadowing','r.DFDistanceScale',
    'r.Shadow.FarShadowDistanceOverride','r.Shadow.MaxNumFarShadowCascades','r.SkyAtmosphere.SampleLightShadowmap')
result['shadow_source_defaults']={key:unreal.SystemLibrary.get_console_variable_float_value(key) for key in shadow_cvars}
result['shadow_source_defaults_provenance']='Effective CVars in this isolated source commandlet; original interactive editor/capture runtime overrides are not known'
atmosphere_cvars=('r.SkyAtmosphere.TransmittanceLUT','r.SkyAtmosphere.TransmittanceLUT.SampleCount',
    'r.SkyAtmosphere.TransmittanceLUT.UseSmallFormat','r.SkyAtmosphere.TransmittanceLUT.Width','r.SkyAtmosphere.TransmittanceLUT.Height',
    'r.SkyAtmosphere.MultiScatteringLUT.SampleCount','r.SkyAtmosphere.MultiScatteringLUT.HighQuality',
    'r.SkyAtmosphere.MultiScatteringLUT.Width','r.SkyAtmosphere.MultiScatteringLUT.Height','r.SkyAtmosphere.LUT32',
    'r.SkyAtmosphere.FastSkyLUT','r.SkyAtmosphere.FastSkyLUT.Width','r.SkyAtmosphere.FastSkyLUT.Height',
    'r.SkyAtmosphere.FastSkyLUT.SampleCountMin','r.SkyAtmosphere.FastSkyLUT.SampleCountMax',
    'r.SkyAtmosphere.FastSkyLUT.DistanceToSampleCountMax','r.SkyAtmosphere.AerialPerspectiveLUT.Width',
    'r.SkyAtmosphere.AerialPerspectiveLUT.DepthResolution','r.SkyAtmosphere.AerialPerspectiveLUT.Depth',
    'r.SkyAtmosphere.AerialPerspectiveLUT.SampleCountMaxPerSlice')
result['atmosphere_source_defaults']={key:unreal.SystemLibrary.get_console_variable_float_value(key) for key in atmosphere_cvars}
result['atmosphere_source_defaults_provenance']=result['shadow_source_defaults_provenance']

def identity(path):
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def renderer_source_settings():
    # Unexported enum classes cannot be Pythonized in this engine build.
    # GETALL reads FProperty text directly; the launcher parses it after log
    # closure and validates enum names against the original declarations.
    launch=json.loads((out/'launch.json').read_text(encoding='utf-8'))
    configuration=launch['source_configuration']
    for record in configuration:
        for key in ('source','copied'):
            if identity(Path(record[key]['path']))!=record[key]:
                raise RuntimeError('Source renderer configuration identity changed')
    def reflected_default(class_path):
        cls=unreal.load_class(None,class_path)
        if not cls:raise RuntimeError('Required reflected settings class is unavailable: '+class_path)
        obj=unreal.get_default_object(cls)
        if not obj:raise RuntimeError('Required settings default is unavailable: '+class_path)
        return obj
    settings=reflected_default('/Script/Engine.RendererSettings')
    windows=reflected_default('/Script/WindowsTargetPlatformSettings.WindowsTargetSettings')
    for obj,keys in ((settings,('WorkingColorSpaceChoice','bEnableAlphaChannelInPostProcessing',
                               'bMobileEnableAlphaChannelInPostProcessing','RedChromaticityCoordinate',
                               'GreenChromaticityCoordinate','BlueChromaticityCoordinate','WhiteChromaticityCoordinate')),
                     (windows,('DefaultGraphicsRHI','D3D11TargetedShaderFormats',
                               'D3D12TargetedShaderFormats','VulkanTargetedShaderFormats'))):
        for key in keys:
            unreal.log('TARGETMAP_RENDERER_PROPERTY_BEGIN '+key)
            command='getall '+obj.get_class().get_name()+' '+key+' SHOWDEFAULTS NAME='+obj.get_name()
            unreal.SystemLibrary.execute_console_command(world,command)
            unreal.log('TARGETMAP_RENDERER_PROPERTY_END '+key)
    alpha=unreal.SystemLibrary.get_console_variable_int_value('r.PostProcessing.PropagateAlpha')
    mobile_alpha=unreal.SystemLibrary.get_console_variable_int_value('r.Mobile.PropagateAlpha')
    engine=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir()))
    def source_symbol(relative,signature):
        path=engine/relative;data=path.read_bytes();start=data.index(signature.encode())
        return {**identity(path),'signature':signature,'line':data[:start].count(b'\n')+1}
    return {'propagate_alpha':alpha,'mobile_propagate_alpha':mobile_alpha,'text_probe_pending':True,
        'provenance':{'settings_object':settings.get_path_name(),'platform_settings_object':windows.get_path_name(),
            'engine_revision':launch['engine_revision'],'configuration':configuration,'executed_script':identity(Path(__file__)),
            'working_color_space':source_symbol('Source/Runtime/Engine/Classes/Engine/RendererSettings.h','TEnumAsByte<EWorkingColorSpace::Type> WorkingColorSpaceChoice;'),
            'lut_format':source_symbol('Source/Runtime/Renderer/Private/SkyAtmosphereRendering.cpp','static EPixelFormat GetSkyLutTextureFormat('),
            'alpha_branch':source_symbol('Source/Runtime/Renderer/Private/PostProcess/PostProcessing.cpp','bool IsPostProcessingWithAlphaChannelSupported()'),
            'scope':'Reflected default objects and effective CVars from source-configured isolated commandlet. Selected source Windows shader targets determine the LUT feature branch. NullRHI does not establish interactive feature level or capture runtime overrides.'}}


result['renderer_source_settings']=renderer_source_settings()

# Keep original material expressions and function dependencies as source text,
# independent of cooked shader permutations or captured constant buffers.
material_dir=out/'Materials';material_dir.mkdir()
source_files={}
def package_identity(obj):
    package=obj.get_path_name().split('.')[0]
    if package.startswith('/Engine/'):
        base=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_content_dir()))
        filename=base/(package[len('/Engine/'):]+'.uasset')
    elif package.startswith('/Game/'):
        filename=scratch/'Content'/(package[len('/Game/'):]+'.uasset')
    else:raise RuntimeError('Unexpected material source package: '+package)
    for suffix in ('.uasset','.uexp','.ubulk','.uptnl'):
        path=filename.with_suffix(suffix)
        if path.is_file():source_files.setdefault(str(path),identity(path))

def export_text(obj,filename,exporter=None):
    task=unreal.AssetExportTask()
    for key,val in {'object':obj,'exporter':exporter or unreal.ObjectExporterT3D(),'filename':str(filename),
                    'selected':False,'replace_identical':False,'prompt':False,'automated':True,
                    'use_file_archive':False,'write_empty_files':False}.items():
        task.set_editor_property(key,val)
    if not unreal.Exporter.run_asset_export_task(task) or not filename.is_file():
        raise RuntimeError('Cannot export original material text: '+obj.get_path_name())

seen={}
textures={}
def inspect_material(obj):
    key=obj.get_path_name()
    if key in seen:return
    package_identity(obj)
    filename=material_dir/(key.split('.')[0].strip('/').replace('/','__')+'.t3d')
    export_text(obj,filename)
    item={'object':key,'class':obj.get_class().get_name(),'text':identity(filename)}
    seen[key]=item
    if isinstance(obj,unreal.MaterialInstanceConstant):
        parent=obj.get_editor_property('parent');item['parent']=value(parent)
        item['overrides']=properties(obj,['scalar_parameter_values','vector_parameter_values','texture_parameter_values','base_property_overrides'])
        if parent:inspect_material(parent)
    elif isinstance(obj,(unreal.Material,unreal.MaterialFunction)):
        expressions=(unreal.MaterialEditingLibrary.get_material_expressions(obj) if isinstance(obj,unreal.Material)
                     else unreal.MaterialEditingLibrary.get_material_function_expressions(obj))
        item['expressions']=[]
        for expr in expressions:
            entry={'object':expr.get_path_name(),'class':expr.get_class().get_name(),
                   **properties(expr,['parameter_name','default_value','r','g','b','a','constant','texture','material_function'])}
            item['expressions'].append(entry)
            texture=entry.get('texture')
            if texture and texture not in textures:
                tex=unreal.load_object(None,texture);package_identity(tex)
                path=material_dir/(texture.split('.')[0].strip('/').replace('/','__')+'.dds')
                export_text(tex,path,unreal.TextureExporterDDS())
                textures[texture]={'object':texture,'source_image':identity(path),
                    'export_semantics':'UE TextureExporterDDS exports original Texture.Source, not built platform compression/mips',
                    **properties(tex,['srgb','compression_settings','lod_group','mip_gen_settings','lod_bias','num_cinematic_mip_levels',
                                      'filter','address_x','address_y','never_stream','virtual_texture_streaming','compression_no_alpha'])}
            if isinstance(expr,unreal.MaterialExpressionMaterialFunctionCall):
                dependency=expr.get_editor_property('material_function')
                if dependency:inspect_material(dependency)
        if isinstance(obj,unreal.Material):
            item['outputs']={}
            for prop in ('MP_BASE_COLOR','MP_METALLIC','MP_SPECULAR','MP_ROUGHNESS','MP_NORMAL','MP_EMISSIVE_COLOR','MP_OPACITY','MP_AMBIENT_OCCLUSION'):
                node=unreal.MaterialEditingLibrary.get_material_property_input_node(obj,getattr(unreal.MaterialProperty,prop))
                item['outputs'][prop]=value(node)
            item['settings']=properties(obj,['blend_mode','shading_model','two_sided','use_material_attributes','is_sky'])

for actor in result['actors']:
    for mesh in actor['meshes']:
        for asset in mesh['materials']:
            if asset:
                material=unreal.load_object(None,asset)
                if not material:raise RuntimeError('Cannot load original material '+asset)
                inspect_material(material)
# Source configuration enables async asset builds. Drain registered compilers
# through UE's existing command before commandlet teardown, without changing
# rendering CVars or saving packages (AssetCompilingManager.cpp:46,674).
unreal.log('TARGETMAP_ASSET_COMPILATION_FINISH_BEGIN')
unreal.SystemLibrary.execute_console_command(world,'Editor.AsyncAssetCompilationFinishAll')
unreal.log('TARGETMAP_ASSET_COMPILATION_FINISH_END')
changed=[item['path'] for item in source_files.values() if identity(Path(item['path']))!=item]
materials={'status':'failed' if changed else 'passed','capture_inputs':False,'materials':list(seen.values()),'textures':list(textures.values()),
           'source_files':list(source_files.values()),'source_files_changed':changed}
(out/'materials.json').write_text(json.dumps(materials,indent=2),encoding='utf-8')
if changed:raise RuntimeError('Source material packages changed during read-only export')
(out/'inventory.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
unreal.log('TARGETMAP_INVENTORY_COMPLETE '+str(out/'inventory.json'))
