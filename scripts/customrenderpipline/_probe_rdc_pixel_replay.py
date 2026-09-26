"""Read-only, bounded RenderDoc pixel traces; defaults to the original floor probe."""
import json
import os
import sys
import traceback
import renderdoc as rd

OUT = os.environ['UE_RDC_PIXEL_OUT']
os.makedirs(OUT, exist_ok=True)


def simple(obj, depth=0):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, rd.ResourceId):
        return str(obj)
    if depth > 9:
        return str(obj)
    if hasattr(obj, '__iter__') or (hasattr(obj, '__len__') and hasattr(obj, '__getitem__')):
        return [simple(v, depth + 1) for v in obj]
    result = {}
    for key in dir(obj):
        if key.startswith('_') or key in ('this', 'thisown'):
            continue
        try:
            value = getattr(obj, key)
            if not callable(value):
                result[key] = simple(value, depth + 1)
        except Exception:
            pass
    return result if result else str(obj)


def write(name, value):
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


cap, controller, trace = None, None, None
try:
    cap = rd.OpenCaptureFile()
    status = cap.OpenFile(os.environ['UE_RDC_PIXEL_CAPTURE'], '', None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if controller is None:
        raise RuntimeError(str(status))
    write('api.json', {name: getattr(controller, name).__doc__ for name in ('DebugPixel', 'ContinueDebug', 'FreeTrace')})
    points = json.loads(os.environ.get('UE_RDC_PIXEL_POINTS', '[[1853,948,1017]]'))
    if not isinstance(points, list) or not 1 <= len(points) <= 8:
        raise ValueError('Expected one to eight [event,x,y] points')
    batch_out = OUT
    results = []
    for event, x, y in points:
        if any(type(v) is not int or v < 0 for v in (event, x, y)):
            raise ValueError('Expected nonnegative integer event and pixel coordinates')
        if len(points) > 1:
            OUT = os.path.join(batch_out, str(event) + '-' + str(x) + '-' + str(y))
            os.makedirs(OUT, exist_ok=True)
        inputs = rd.DebugPixelInputs()
        write('debug-input-defaults.json', simple(inputs))
        controller.SetFrameEvent(event, True)
        trace = controller.DebugPixel(x, y, inputs)
        write('trace.json', simple(trace))
        states = []
        for batch in range(100):
            chunk = controller.ContinueDebug(trace.debugger)
            if not chunk:
                break
            states.extend(simple(chunk))
        else:
            raise RuntimeError('Pixel debug trace exceeded bounded 100 batches')
        if not states:
            raise RuntimeError('Pixel debug returned no states')
        write('states.json', states)
        result = {'status': 'traced', 'event': event, 'pixel': [x, y], 'states': len(states)}
        write('result.json', result)
        results.append(result)
        controller.FreeTrace(trace)
        trace = None
    OUT = batch_out
    if len(points) > 1:
        write('result.json', {'status': 'traced', 'points': results})
except Exception:
    write('error.json', {'error': traceback.format_exc()})
finally:
    if trace is not None and trace.debugger is not None:
        controller.FreeTrace(trace)
    if controller is not None:
        controller.Shutdown()
    if cap is not None:
        cap.Shutdown()
sys.exit(0)
