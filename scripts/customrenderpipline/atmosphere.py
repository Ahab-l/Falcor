"""Source atmosphere setup and reusable declared LUT compute graph.

Physical units are km and km^-1, matching FAtmosphereSetup::Init. This
adapter currently supports the source sRGB working space and default two-ray
multi-scattering branch. It never consumes an exported/captured LUT.
"""
import math
import json
from pathlib import Path
import numpy as np

SHADER=Path(__file__).resolve().parents[2]/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/AtmosphereLuts.slang'
SRGB_TABLE_SOURCE=json.loads(SHADER.with_name('UESRGBToLinearTable.json').read_text(encoding='utf-8'))
if SRGB_TABLE_SOURCE.get('capture_inputs') is not False or len(SRGB_TABLE_SOURCE.get('literals',[]))!=256:
    raise ValueError('The original source FLinearColor sRGB table is required')
SRGB_TO_LINEAR=np.array([v.removesuffix('f') for v in SRGB_TABLE_SOURCE['literals']],dtype=np.float32)
SRGB_TO_LINEAR.setflags(write=False)
VECTOR_FIELDS={'GroundAlbedo','RayleighScattering','MieScattering','MieAbsorption','MieExtinction','AbsorptionExtinction'}
SCALAR_FIELDS={'BottomRadiusKm','TopRadiusKm','MultiScatteringFactor','RayleighDensityExpScale','MiePhaseG',
    'MieDensityExpScale','AbsorptionDensity0LayerWidth','AbsorptionDensity0LinearTerm','AbsorptionDensity0ConstantTerm',
    'AbsorptionDensity1LinearTerm','AbsorptionDensity1ConstantTerm'}


def finite(value, name):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(name+' must be finite numeric data')
    with np.errstate(over='ignore'):
        result=float(np.float32(value))
    if not math.isfinite(result):raise ValueError(name+' exceeds float32')
    return result


def component_parameters(component):
    c=component
    def scalar(name):
        if name not in c:raise ValueError('Missing source atmosphere property '+name)
        return finite(c[name],name)
    def rgb(name):
        v=c.get(name)
        if not isinstance(v,(list,tuple)) or len(v) not in (3,4):raise ValueError(name+' requires RGB')
        return np.array([finite(x,name) for x in v[:3]],dtype=np.float32)
    def coeff(name,scale):
        with np.errstate(over='ignore'):
            v=np.clip(rgb(name)*np.float32(scalar(scale)),np.float32(0),np.float32(1e38))
        if not np.isfinite(v).all():raise ValueError(name+' coefficient overflow')
        return v.tolist()
    bottom=scalar('bottom_radius')
    if bottom<=0:raise ValueError('bottom_radius must be positive')
    top=float(np.float32(bottom)+np.float32(max(.1,scalar('atmosphere_height'))))
    if not math.isfinite(top) or top<=bottom:raise ValueError('Atmosphere radii are not distinct finite float32 values')
    ground=rgb('ground_albedo')
    if np.any(ground<0) or np.any(ground>255) or np.any(ground!=np.floor(ground)):
        raise ValueError('ground_albedo must contain source FColor bytes')
    # FLinearColor(FColor) indexes these original float literals. Recomputing
    # the analytic transfer differs by one ULP for some bytes (including 196).
    ground=SRGB_TO_LINEAR[ground.astype(np.uint8)]
    p={'BottomRadiusKm':bottom,'TopRadiusKm':top,'GroundAlbedo':ground.tolist(),
       'MultiScatteringFactor':min(100.,max(0.,scalar('multi_scattering_factor'))),
       'RayleighScattering':coeff('rayleigh_scattering','rayleigh_scattering_scale'),
       'MieScattering':coeff('mie_scattering','mie_scattering_scale'),
       'MieAbsorption':coeff('mie_absorption','mie_absorption_scale'),
       'AbsorptionExtinction':coeff('other_absorption','other_absorption_scale'),
       'MiePhaseG':scalar('mie_anisotropy')}
    if not 0<=p['MiePhaseG']<1:raise ValueError('mie_anisotropy must be in [0,1)')
    for target,key in [('RayleighDensityExpScale','rayleigh_exponential_distribution'),
                       ('MieDensityExpScale','mie_exponential_distribution')]:
        height=scalar(key)
        if height<=0:raise ValueError(key+' must be positive')
        p[target]=finite(-1./height,key)
    p['MieExtinction']=(np.array(p['MieScattering'],dtype=np.float32)+np.array(p['MieAbsorption'],dtype=np.float32)).tolist()
    tent=c.get('other_tent_distribution',{})
    try:alt,value,width=(np.float32(finite(tent[k],k)) for k in ('tip_altitude','tip_value','width'))
    except KeyError as e:raise ValueError('Missing source ozone tent property') from e
    slope=np.float32(value/width) if width>0 and value>0 else np.float32(0)
    enabled=width>0 and value>0
    p.update(AbsorptionDensity0LayerWidth=float(alt) if enabled else 0.,
             AbsorptionDensity0LinearTerm=float(slope),AbsorptionDensity1LinearTerm=float(-slope),
             AbsorptionDensity0ConstantTerm=float(value-alt*slope) if enabled else 0.,
             AbsorptionDensity1ConstantTerm=float(value+alt*slope) if enabled else 0.)
    return p


def source_atmosphere(inventory):
    """Require a complete saved-source inventory, without runtime-capture claims."""
    if inventory.get('capture_inputs') is not False:raise ValueError('Source inventory provenance is required')
    renderer=inventory.get('renderer_source_settings',{})
    if not isinstance(renderer,dict) or not renderer.get('provenance'):
        raise ValueError('Effective source renderer settings and provenance are required')
    choice=renderer.get('working_color_space_choice')
    if isinstance(choice,bool) or not isinstance(choice,int) or choice!=1:
        raise ValueError('This source adapter requires the exported sRGB working_color_space_choice')
    expected={'red':[.64,.33],'green':[.30,.60],'blue':[.15,.06],'white':[.3127,.329]}
    if renderer.get('working_color_space_chromaticities')!=expected:
        raise ValueError('This source adapter requires verified sRGB working-space chromaticities')
    if any(finite(renderer.get(key),key)!=0 for key in ('propagate_alpha','mobile_propagate_alpha')):
        raise ValueError('Alpha-output atmosphere LUT formats are not supported by this source adapter')
    formats=renderer.get('targeted_shader_formats')
    if (not isinstance(formats,list) or not formats or any(v not in ('PCD3D_SM5','PCD3D_SM6','SF_VULKAN_SM5','SF_VULKAN_SM6') for v in formats)
        or renderer.get('lut_feature_level_branch')!='desktop' or renderer.get('lut_format_branch')!='desktop_rgb'
        or renderer.get('lut_pixel_format')!='PF_FloatRGB'):
        raise ValueError('This source adapter requires a verified desktop PF_FloatRGB LUT branch; mobile/unknown formats are unsupported')
    components=[e for a in inventory['actors'] for e in a.get('environment',[]) if e['class']=='SkyAtmosphereComponent']
    if len(components)!=1:raise ValueError('Exactly one source SkyAtmosphere is required')
    cvars=inventory['atmosphere_source_defaults']
    def cvar(key):return finite(cvars['r.SkyAtmosphere.'+key],key)
    if cvar('TransmittanceLUT')<=0 or cvar('TransmittanceLUT.UseSmallFormat')>0 or cvar('MultiScatteringLUT.HighQuality')>0:
        raise ValueError('This source adapter requires enabled full-format transmittance and default two-ray multi scattering')
    def size(key):return tuple(max(4,int(cvar(key+'.'+axis))) for axis in ('Width','Height'))
    return component_parameters(components[0]),dict(transmittance_size=size('TransmittanceLUT'),multi_size=size('MultiScatteringLUT'),
        transmittance_samples=max(1.,cvar('TransmittanceLUT.SampleCount')),multi_samples=max(1.,cvar('MultiScatteringLUT.SampleCount')))


def atmosphere_lut_fragment(parameters,*,prefix='Atmosphere',transmittance_size=(256,64),multi_size=(32,32),
                            transmittance_samples=10.,multi_samples=15.,output_format='R11G11B10Float'):
    if output_format not in ('R11G11B10Float','RGBA32Float'):
        raise ValueError('Atmosphere LUTs use native R11G11B10Float or diagnostic RGBA32Float')
    def size(value):
        if len(value)!=2 or any(isinstance(v,bool) or not isinstance(v,int) or not 1<=v<=16384 for v in value):
            raise ValueError('LUT size must contain two bounded positive integers')
        return list(value)
    transmittance_size,multi_size=map(size,(transmittance_size,multi_size))
    transmittance_samples=max(1.,finite(transmittance_samples,'Transmittance samples'))
    multi_samples=max(1.,finite(multi_samples,'Multi-scattering samples'))
    if max(transmittance_samples,multi_samples)>4096:raise ValueError('LUT sample count exceeds the declared execution budget')
    if set(parameters)!=VECTOR_FIELDS|SCALAR_FIELDS:raise ValueError('Atmosphere physical parameter fields must match the declared contract')
    uniforms={};physical={}
    for name,value in parameters.items():
        vector=isinstance(value,(list,tuple))
        if vector!=(name in VECTOR_FIELDS) or (vector and len(value)!=3):raise ValueError('Atmosphere parameter shape mismatch: '+name)
        physical[name]=[finite(v,name) for v in value] if vector else finite(value,name)
        uniforms['Atmosphere.'+name]={'type':'float3' if vector else 'float',
            'value':physical[name]}
    if not 0<physical['BottomRadiusKm']<physical['TopRadiusKm']<=1e8:raise ValueError('Atmosphere radii must be ordered positive km values below 1e8')
    if any(physical[k]>0 for k in ('RayleighDensityExpScale','MieDensityExpScale')):raise ValueError('Atmosphere exponential density must not grow with altitude')
    if not 0<=physical['MiePhaseG']<1 or not 0<=physical['MultiScatteringFactor']<=100:raise ValueError('Atmosphere phase/factor outside source domain')
    for name in VECTOR_FIELDS:
        if any(v<0 or v>(1 if name=='GroundAlbedo' else 1e38) for v in physical[name]):raise ValueError('Atmosphere RGB outside source domain: '+name)
    extinction=(np.array(physical['MieScattering'],dtype=np.float32)+np.array(physical['MieAbsorption'],dtype=np.float32)).tolist()
    if physical['MieExtinction']!=extinction:raise ValueError('MieExtinction must equal float32 scattering plus absorption')
    t,m=prefix+'Transmittance',prefix+'MultiScattering'
    nodes=[]
    for trans,name,extent,samples in ((True,t,transmittance_size,transmittance_samples),(False,m,multi_size,multi_samples)):
        lut='Transmittance' if trans else 'MultiScatteredLuminance'
        u=dict(uniforms)
        u['SkyAtmosphere.'+lut+'LutSizeAndInvSize']={'type':'float4','value':extent+[1./extent[0],1./extent[1]]}
        u['SkyAtmosphere.'+('Transmittance' if trans else 'MultiScattering')+'SampleCount']={'type':'float','value':samples}
        props={'shader':{'file':str(SHADER),'defines':{'TRANSMITTANCE_PASS':str(int(trans))}},
            'resources':[{'name':'lut','direction':'output','binding':lut+'LutUAV','format':output_format,'size':extent}],
            'uniforms':u,'dispatch':{'extent':'lut'}}
        if not trans:
            props['resources'].append({'name':'transmittance','direction':'input','binding':'TransmittanceLutTexture',
                'format':output_format,'size':transmittance_size})
            props['samplers']={'TransmittanceLutTextureSampler':{'filter':'Linear','address':'Clamp'}}
        nodes.append({'name':name,'type':'CustomRenderPiplineComputePass','file_inputs':['shader.file'],'properties':props})
    return {'version':1,'nodes':nodes,'edges':[[t+'.lut',m+'.transmittance']],'outputs':[t+'.lut',m+'.lut']}
