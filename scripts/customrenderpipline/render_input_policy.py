"""Keep captured stage outputs and baked renderer state out of live UE graphs.

Raw capture readers remain available to offline comparison/research tools.
There is no runtime opt-out for the rejected legacy replay interfaces.
"""

MESSAGE = 'RDC intermediate inputs are comparison-only; compute this state from the native scene'


def validate_render_inputs(scene, properties):
    for key in ('captured_view', 'csm_projection', 'csm_depth'):
        if key in scene:
            raise ValueError(MESSAGE + ': ' + key)
    for key in ('source_geometry', 'primitive_flags'):
        if scene.get(key):
            raise ValueError(MESSAGE + ': baked ' + key)
    for key in ('projectionDefinitionPath', 'projectionValidationBranch', 'depthDefinitionPath', 'depthValidationBranch'):
        if key in properties:
            raise ValueError(MESSAGE + ': ' + key)
    lighting = scene.get('lighting', {})
    if not isinstance(lighting, dict):
        raise ValueError('Lighting declaration must be an object')
    if lighting.get('input_mode', 'native') != 'native':
        raise ValueError(MESSAGE + ': lighting.input_mode')
    resources = lighting.get('resources', {})
    if not isinstance(resources, dict):
        raise ValueError('Lighting resource references must be an object')
    for name in ('scene_color_before', 'shadow_mask', 'scene_ao'):
        if name in resources:
            raise ValueError(MESSAGE + ': lighting.resources.' + name)
    view = lighting.get('view', {})
    for name in ('screen_to_translated_world_row_major', 'translated_camera_origin_ue', 'inv_device_z_to_world_z'):
        if name in view:
            raise ValueError(MESSAGE + ': lighting.view.' + name)
    if lighting.get('coordinate_space', 'absolute_ue_cm') != 'absolute_ue_cm':
        raise ValueError(MESSAGE + ': captured translated lighting coordinates')
