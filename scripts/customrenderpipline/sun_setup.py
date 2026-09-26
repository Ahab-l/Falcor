"""Project source sun contract; all derived light values are computed natively."""
ATMOSPHERE_FIELDS={'BottomRadiusKm','TopRadiusKm','MieExtinction','RayleighScattering','AbsorptionExtinction',
    'MieDensityExpScale','RayleighDensityExpScale','AbsorptionDensity0LayerWidth','AbsorptionDensity0LinearTerm',
    'AbsorptionDensity0ConstantTerm','AbsorptionDensity1LinearTerm','AbsorptionDensity1ConstantTerm'}

def source_sun_settings(light,environment):
    if light['per_pixel_atmosphere_transmittance'] or light['atmosphere_sun_light_index']!=0:
        raise ValueError('Source sun adapter requires atmosphere index 0 without per-pixel transmittance')
    if light['light_source_soft_angle']!=0:
        raise ValueError('Source sun soft-angle setup is not yet supported')
    components=[e for a in environment['actors'] for e in a.get('environment',[]) if e['class']=='SkyAtmosphereComponent']
    if len(components)!=1:raise ValueError('Exactly one source atmosphere is required')
    if any(entry['enabled'] for entry in components[0]['light_direction_overrides']):
        raise ValueError('Source atmosphere direction overrides are not yet supported')
    return {'working_color_space':environment['working_color_space']['name'],
        'color_srgb':light['light_color'][:3],'intensity':light['intensity'],
        'use_temperature':light['use_temperature'],'temperature_kelvin':light['temperature'],
        'atmosphere_sun':light['atmosphere_sun_light'],'per_pixel_transmittance':light['per_pixel_atmosphere_transmittance'],
        'source_angle_degrees':light['light_source_angle'],'disk_color_scale':light['atmosphere_sun_disk_color_scale'][:3],
        'transmittance_min_elevation_degrees':components[0]['transmittance_min_light_elevation_angle'],
        'atmosphere':{k:environment['atmosphere_parameters'][k] for k in sorted(ATMOSPHERE_FIELDS)}}
