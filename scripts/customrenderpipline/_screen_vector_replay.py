"""Read a bounded frozen set of initial E2655 pixel-shader inputs.

Compatible with qrenderdoc Python 3.6. DebugPixel performs instrumented replay;
the returned initial inputs are read immediately and the interpreter is never
continued. This does not independently prove uninstrumented interpolation bits.
"""
import hashlib
import json
import math
import os
import struct
import time
import traceback

CAPTURE_HASH = '822d41ea6ecb12633f42b18ed5ae1a3e7cea02653c9a72724f6e55e127d85fc9'
MAX_POINTS = 128
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
TIME_LIMIT_SECONDS = 840


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest_file(path):
    result = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write(out, name, value):
    payload = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8')
    require(len(payload) <= MAX_OUTPUT_BYTES, 'Input evidence exceeds bounded output size')
    with open(os.path.join(out, name), 'wb') as stream:
        stream.write(payload)


def initial_inputs(variables, xy):
    found = {}
    visited = [0]
    counts = {'TEXCOORD0': 2, 'TEXCOORD1': 3, 'SV_Position': 4}
    def visit(values, depth=0):
        require(depth <= 16, 'Unexpected shader input nesting')
        for value in values:
            visited[0] += 1
            require(visited[0] <= 512, 'Unexpected shader input variable count')
            name = str(value.name)
            if name in counts:
                count = counts[name]
                require(name not in found and int(value.columns) == count and int(value.rows) == 1, 'Unexpected or duplicate PS semantic shape')
                floats = [float(v) for v in value.value.f32v][:count]
                bits = [int(v) for v in value.value.u32v][:count]
                require(len(floats) == len(bits) == count and all(math.isfinite(v) for v in floats), 'Invalid initial float32 input')
                actual_bits = list(struct.unpack('<' + 'I' * count, struct.pack('<' + 'f' * count, *floats)))
                require(actual_bits == bits, 'Initial input float32 union bits disagree')
                found[name] = {'float32': floats, 'float32_bits': bits}
            visit(value.members, depth + 1)
    visit(variables)
    require(set(found) == set(counts), 'Missing initial PS input semantics')
    require(found['SV_Position']['float32'][:2] == [xy[0] + 0.5, xy[1] + 0.5], 'Initial SV_Position disagrees with requested pixel')
    return {'xy': list(xy), 'inputs': found,
        'method': 'DebugPixel initial trace.inputs; no interpreted states', 'algorithm_input': False}


def validate_points(plan):
    selected, cached, points = (plan[key] for key in ('selected_pixels_xy', 'cached_pixels_xy', 'replay_pixels_xy'))
    require(plan['extent'] == [1424, 1040], 'Unexpected render extent')
    for values in (selected, cached, points):
        require(isinstance(values, list) and len(values) <= MAX_POINTS, 'Unbounded input selection')
        require(all(isinstance(p, list) and len(p) == 2 and all(type(v) is int for v in p)
            and 0 <= p[0] < 1424 and 0 <= p[1] < 1040 for p in values), 'Invalid selected input pixel')
        require(len(set(tuple(p) for p in values)) == len(values), 'Duplicate input pixels')
    require(0 < len(selected) == plan['selected_count'] <= MAX_POINTS and points, 'Empty or inconsistent selection')
    require(set(tuple(p) for p in cached).issubset(set(tuple(p) for p in selected)), 'Cached input lies outside frozen selection')
    require(points == [p for p in selected if p not in cached], 'Replay must extract only missing frozen inputs')
    return points


def run():
    import renderdoc as rd
    plan_path = os.environ['UE_SCREEN_VECTOR_PLAN']
    out = os.environ['UE_SCREEN_VECTOR_RUN']
    plan_hash = os.environ['UE_SCREEN_VECTOR_PLAN_SHA256']
    cap, controller, capture, before = None, None, None, None
    started = time.monotonic()
    exit_code = 1
    try:
        require(os.path.isdir(out) and not any(os.path.exists(os.path.join(out, p)) for p in ('inputs.json', 'done.json', 'error.json')), 'Launcher must create a fresh output directory')
        require(digest_file(plan_path) == plan_hash, 'Frozen selection plan checksum mismatch')
        with open(plan_path, 'r', encoding='utf-8') as stream:
            plan = json.load(stream)
        require(plan['version'] == 1 and plan['event'] == 2655 and plan['production_residual_pixels'] == 29, 'Unexpected input evidence plan')
        require(plan['capture']['sha256'] == CAPTURE_HASH, 'Unexpected capture identity')
        points = validate_points(plan)
        capture = plan['capture']['path']
        require(os.path.isabs(capture) and os.path.isfile(capture), 'Capture must be an existing absolute file')
        before = digest_file(capture)
        require(before == CAPTURE_HASH, 'Capture checksum mismatch before replay')
        cap = rd.OpenCaptureFile()
        status = cap.OpenFile(capture, '', None)
        require(status == rd.ResultCode.Succeeded, 'OpenFile failed: ' + str(status))
        status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
        require(controller is not None, 'OpenCapture failed: ' + str(status))
        controller.SetFrameEvent(2655, True)
        resource = controller.GetD3D12PipelineState().outputMerger.renderTargets[0].resource
        require(str(resource) == plan['resource'], 'Unexpected E2655 color attachment')
        texture = next(t for t in controller.GetTextures() if t.resourceId == resource)
        require(texture.width == 1424 and texture.height == 1040 and texture.msSamp == 1, 'Unexpected E2655 attachment shape')
        write(out, 'api.json', {'DebugPixel': controller.DebugPixel.__doc__, 'FreeTrace': controller.FreeTrace.__doc__,
            'resource': str(resource), 'event': 2655, 'instrumented_initial_inputs': True,
            'interpreter_executed': False, 'unmodified_interpolation_bits_proven': False,
            'renderdoc_version': str(rd.GetVersionString()) if hasattr(rd, 'GetVersionString') else None})
        output = []
        for x, y in points:
            require(time.monotonic() - started < TIME_LIMIT_SECONDS, 'Initial-input extraction exceeded time budget')
            controller.SetFrameEvent(2655, True)
            trace = controller.DebugPixel(x, y, rd.DebugPixelInputs())
            try:
                require(trace is not None, 'DebugPixel returned no initial trace')
                output.append(initial_inputs(trace.inputs, (x, y)))
            finally:
                if trace is not None:
                    controller.FreeTrace(trace)
            write(out, 'inputs.json', output)
        after = digest_file(capture)
        require(before == after == CAPTURE_HASH, 'Capture changed during initial-input replay')
        require(digest_file(plan_path) == plan_hash, 'Selection plan changed during input replay')
        write(out, 'done.json', {'plan_sha256': plan_hash, 'capture_unchanged': True,
            'capture_sha256_before': before, 'capture_sha256_after': after,
            'inputs_sha256': digest_file(os.path.join(out, 'inputs.json')),
            'point_count': len(output), 'elapsed_seconds': time.monotonic() - started,
            'method': 'DebugPixel initial inputs, no interpreter execution',
            'unmodified_interpolation_bits_proven': False, 'algorithm_input': False})
        exit_code = 0
    except Exception:
        failure = {'error': traceback.format_exc(), 'elapsed_seconds': time.monotonic() - started}
        if capture is not None and before is not None:
            failure.update(capture_sha256_before=before, capture_sha256_after=digest_file(capture))
            failure['capture_unchanged'] = failure['capture_sha256_after'] == before
        write(out, 'error.json', failure)
    finally:
        if controller is not None:
            controller.Shutdown()
        if cap is not None:
            cap.Shutdown()
    return exit_code


if 'UE_SCREEN_VECTOR_PLAN' in os.environ:
    os._exit(run())
