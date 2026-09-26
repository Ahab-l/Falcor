"""Preserved source SkyView settings; retired runtime graph builder is archived."""
import re
import numpy as np
from atmosphere import finite,source_atmosphere


def source_sky_view_settings(scene):
    env=scene['source_environment']
    # Revalidate physical parameters/formats against the exported source inputs.
    physical,luts=source_atmosphere({'capture_inputs':False,'actors':env['actors'],
        'renderer_source_settings':env['renderer_source_settings'],'atmosphere_source_defaults':env['source_defaults']})
    if physical!=env['atmosphere_parameters']:
        raise ValueError('SkyView physical parameters differ from source component')
    components=[c for a in env['actors'] for c in a.get('environment',[]) if c['class']=='SkyAtmosphereComponent']
    c=components[0];v=env['source_defaults']
    def value(name):return finite(v['r.SkyAtmosphere.FastSkyLUT'+name],name)
    if value('')<=0:raise ValueError('SkyView source requires enabled FastSkyLUT')
    modes={'<SkyAtmosphereTransformMode.PLANET_TOP_AT_ABSOLUTE_WORLD_ORIGIN: 0>':0,
        '<SkyAtmosphereTransformMode.PLANET_TOP_AT_COMPONENT_TRANSFORM: 1>':1,
        '<SkyAtmosphereTransformMode.PLANET_CENTER_AT_COMPONENT_TRANSFORM: 2>':2}
    if c['transform_mode'] not in modes:raise ValueError('Unknown source sky transform mode')
    lights=[light for light in scene['lighting']['lights'] if 'source_sun' in light]
    if len(lights)!=1:raise ValueError('SkyView currently requires one original source sun')
    light=lights[0]
    setup={'bottom_radius_km':physical['BottomRadiusKm'],'transform_mode':modes[c['transform_mode']],
        'component_translation_cm':list(c['world_location_cm']),
        'sun':dict(light['source_sun'],direction_ue=light['direction_ue'])}
    minimum=max(1.,value('.SampleCountMin'))
    maximum=max(minimum,min(float(np.float32(32)*np.float32(finite(c['trace_sample_count_scale'],'trace scale'))),value('.SampleCountMax')))
    return setup,{'size':[max(4,int(value('.'+axis))) for axis in ('Width','Height')],
        'min_samples':minimum,'max_samples':maximum,
        'distance_to_max_inv':float(np.float32(1)/np.float32(max(1e-4,value('.DistanceToSampleCountMax')))),
        'luminance_factor':[finite(x,'luminance factor') for x in c['sky_and_aerial_perspective_luminance_factor'][:3]]}


