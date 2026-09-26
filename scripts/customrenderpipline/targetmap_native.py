"""Source-authored camera math for the targetmap example; no capture imports."""
import math
import hashlib
import json

import numpy as np

from source_scene import ue_instance_transform


def read_source_json(path):
    """Parse and fingerprint one identical read, not a second filesystem state."""
    path = path.resolve()
    data = path.read_bytes()
    return json.loads(data), {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def source_camera(camera):
    """Column-vector, RH Falcor meters, reverse-Z infinite projection.

    Projection aspect uses the unscaled frame rectangle when explicitly given;
    raster size can be a rounded screen-percentage reduction. Neither uses the
    padded allocation. Without an unscaled frame size, use the visible extent.
    Source positions/Rotator come from the saved map. No captured matrix,
    jitter, previous-frame transform or exposure is accepted by this helper.
    """
    near, fov = camera['near_cm'], camera['horizontal_fov_degrees']
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (near, fov)):
        raise ValueError('near and FOV must be finite numbers')
    if near <= 0 or not 0 < fov < 180:
        raise ValueError('near must be positive and FOV in (0,180)')
    size = camera['resolution']
    if len(size) != 2 or any(type(v) is not int or not 0 < v <= 16384 for v in size):
        raise ValueError('resolution must contain two bounded positive integers')
    projection_size = camera.get('projection_resolution', size)
    if len(projection_size) != 2 or any(type(v) is not int or not 0 < v <= 16384 for v in projection_size):
        raise ValueError('projection_resolution must contain two bounded positive integers')
    transform = ue_instance_transform(camera['position_cm'], camera['rotation_pitch_yaw_roll']).matrix
    rotation, origin = transform[:3, :3], transform[:3, 3]
    view = np.eye(4)
    view[:3, :3] = rotation.T
    view[:3, 3] = -rotation.T @ origin
    # EditorViewportClient supplies float MatrixFOV and axis multipliers to the
    # double-precision reversed-Z matrix. Preserve those scalar rounding points.
    half_fov = float(np.float32(max(np.float32(.001), np.float32(fov))*np.float32(math.pi))/np.float32(360))
    aspect = float(np.float32(projection_size[0] / projection_size[1]))
    xscale = 1 / math.tan(half_fov)
    projection = np.array([[xscale, 0, 0, 0], [0, aspect / math.tan(half_fov), 0, 0],
                           [0, 0, 0, near / 100], [0, 0, -1, 0]], dtype='f8')
    return {'origin_m': origin.tolist(), 'view': view.tolist(), 'projection': projection.tolist(),
            'view_projection': (projection @ view).tolist(), 'view_rect': [0, 0, *size]}
