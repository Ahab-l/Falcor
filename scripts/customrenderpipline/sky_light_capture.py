"""Bounded source sky-material capture, followed by original Cube filtering.

The source component supplies the capture position, Cube width, and consumer
intensity/color. Cloud and height-fog composition remain pending. The cached
capture exposure defaults to the source CVar EV 4; this is not a runtime read.
"""
import copy
import math
from pathlib import Path
import re

import numpy as np
from atmosphere import finite, SRGB_TO_LINEAR
from sky_light_filter import SHADER_DIRECTORY

CAPTURE_SHADER = SHADER_DIRECTORY.parents[1] / 'Materials/SourceSkyCapture.3d.slang'


def _position(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('Capture position requires three UE centimeter coordinates')
    if any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e15 for x in value):
        raise ValueError('Capture position requires finite bounded UE centimeters')
    return [float(x) for x in value]


def source_sky_light_settings(scene, *, cached_lighting_pre_exposure_ev=4.):
    """Read saved source settings; capture intensity belongs to the consumer.

    EV 4 is the source default in PostProcessEyeAdaptation.cpp:201-207. An
    explicit caller override remains authored source input, not runtime proof.
    """
    components = [c for actor in scene['source_environment']['actors'] for c in actor.get('lights', [])
                  if c.get('class') == 'SkyLightComponent']
    if len(components) != 1:
        raise ValueError('Capture requires exactly one source SkyLightComponent')
    component = components[0]
    if (component.get('real_time_capture') is not True or component.get('cubemap') is not None or
            component.get('source_type') != '<SkyLightSourceType.SLS_CAPTURED_SCENE: 0>'):
        raise ValueError('Only realtime captured-scene SkyLight source is supported')
    width = component.get('cubemap_resolution')
    if type(width) is not int or not 16 <= width <= 16384 or width & (width-1):
        raise ValueError('Source Cube width must be a power of two in 16..16384')
    intensity = finite(component['intensity'], 'SkyLight intensity')
    if intensity < 0:
        raise ValueError('Source SkyLight intensity must be nonnegative')
    color = component.get('light_color')
    if not isinstance(color, list) or len(color) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in color):
        raise ValueError('Source SkyLight color requires four FColor bytes')
    lower = component.get('lower_hemisphere_is_black')
    if type(lower) is not bool:
        raise ValueError('Source lower-hemisphere setting must be explicit')
    ev = min(16., max(-16., finite(cached_lighting_pre_exposure_ev, 'Cached capture exposure EV')))
    pending = [c['class'] for a in scene['source_environment']['actors'] for c in a.get('environment', [])
               if c.get('class') in ('VolumetricCloudComponent', 'ExponentialHeightFogComponent')]
    return {'position_cm': _position(component['world_location_cm']), 'width': width, 'intensity': intensity,
            'light_color_linear': SRGB_TO_LINEAR[np.array(color[:3])].astype(float).tolist(),
            'lower_hemisphere_enabled': lower, 'lower_hemisphere_color': copy.deepcopy(component['lower_hemisphere_color']),
            'cached_lighting_pre_exposure_ev': ev, 'capture_pre_exposure': 2.**(-ev),
            'runtime_exposure_verified': False, 'pending_source_components': pending}


def capture_view_projections(position_cm, *, near_cm=5.):
    """Source 90-degree Cube views, reversed infinite Z, Falcor world meters.

    CalcCubeFaceViewRotationMatrix derives right = up cross direction. Shader
    column-vector multiplication requires these basis vectors as matrix rows.
    """
    position = np.asarray(_position(position_cm), dtype=float)/100.
    near = finite(near_cm, 'Capture near plane')/100.
    if near <= 0:
        raise ValueError('Capture near plane must be positive')
    world_to_ue = np.array([[0, 0, -1], [1, 0, 0], [0, 1, 0]], dtype=float)
    result = []
    for direction, up in [([1, 0, 0], [0, 1, 0]), ([-1, 0, 0], [0, 1, 0]),
                          ([0, 1, 0], [0, 0, -1]), ([0, -1, 0], [0, 0, 1]),
                          ([0, 0, 1], [0, 1, 0]), ([0, 0, -1], [0, 1, 0])]:
        axes = np.array([np.cross(up, direction), up, direction], dtype=float)
        transformed = axes @ world_to_ue
        offset = -axes @ position
        result.append([[*transformed[0], offset[0]], [*transformed[1], offset[1]],
                       [0., 0., 0., near], [*transformed[2], offset[2]]])
    return result


