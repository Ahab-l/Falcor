"""Bounded RenderDoc PixelHistory worker. Compatible with qrenderdoc Python 3.6.

Only extract E2655 history for a hashed, preselected list of at most 128 pixels.
No shader replacement, resource writes, capture saves, or algorithm inputs.
"""
import hashlib
import json
import math
import os
import struct
import time
import traceback

import renderdoc as rd

CAPTURE_HASH = '822d41ea6ecb12633f42b18ed5ae1a3e7cea02653c9a72724f6e55e127d85fc9'
MAX_POINTS = 128
MAX_HISTORY_EVENTS = 4096
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
TIME_LIMIT_SECONDS = 900
PLAN = os.environ['UE_RDC_PIXEL_HISTORY_PLAN']
OUT = os.environ['UE_RDC_PIXEL_HISTORY_OUT']
PLAN_HASH = os.environ['UE_RDC_PIXEL_HISTORY_PLAN_SHA256']


def digest_file(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write(name, obj):
    payload = (json.dumps(obj, indent=2, allow_nan=False) + '\n').encode('utf-8')
    require(len(payload) <= MAX_OUTPUT_BYTES, 'PixelHistory output exceeded bounded size')
    with open(os.path.join(OUT, name), 'wb') as stream:
        stream.write(payload)


def pixel_value(value):
    floats = [float(v) for v in value.col.floatValue]
    require(len(floats) == 4 and all(math.isfinite(v) for v in floats), 'Expected finite RGBA pixel history')
    return {'col': {'floatValue': floats, 'uintValue': [int(v) for v in value.col.uintValue],
                    'intValue': [int(v) for v in value.col.intValue]},
            'depth': float(value.depth), 'stencil': int(value.stencil)}


def modification(entry):
    result = {'eventId': int(entry.eventId), 'fragIndex': int(entry.fragIndex), 'primitiveID': int(entry.primitiveID),
              'preMod': pixel_value(entry.preMod), 'shaderOut': pixel_value(entry.shaderOut), 'postMod': pixel_value(entry.postMod)}
    for name in ('backfaceCulled', 'depthBoundsFailed', 'depthClipped', 'depthTestFailed', 'directShaderWrite',
                 'predicationSkipped', 'sampleMasked', 'scissorClipped', 'shaderDiscarded',
                 'stencilTestFailed', 'unboundPS', 'viewClipped'):
        result[name] = bool(getattr(entry, name))
    return result


def extract_fullscreen_triangle(controller):
    """Read the actual indexed IA draw and PostVS records, at most 1 KiB total."""
    actions = []
    def visit(nodes):
        for action in nodes:
            actions.append(action)
            require(len(actions) <= 100000, 'Unexpected action tree size')
            visit(action.children)
    visit(controller.GetRootActions())
    action = next(a for a in actions if a.eventId == 2655)
    require(action.numIndices == 3 and action.numInstances == 1, 'Expected one indexed three-vertex fullscreen draw')
    controller.SetFrameEvent(2655, True)
    ia = controller.GetD3D12PipelineState().inputAssembly
    total = [0]
    files = []
    def read(name, resource, offset, size):
        require(type(size) is int and 0 < size <= 1024 and total[0] + size <= 1024, 'Fullscreen geometry read exceeds 1 KiB total')
        require(offset >= 0, 'Negative geometry buffer offset')
        payload = bytes(controller.GetBufferData(resource, offset, size))
        require(len(payload) == size, 'Incomplete fullscreen geometry buffer read')
        with open(os.path.join(OUT, name), 'wb') as stream:
            stream.write(payload)
        total[0] += len(payload)
        files.append({'file': name, 'resource': str(resource), 'byteOffset': offset,
                      'byteSize': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
        return payload
    def binding(value):
        return {'resourceId': str(value.resourceId), 'byteOffset': int(value.byteOffset),
                'byteStride': int(value.byteStride), 'byteSize': int(value.byteSize)}
    def index_values(payload, offset, count, stride):
        require(stride in (2, 4) and offset + count * stride <= len(payload), 'Invalid indexed draw range')
        return list(struct.unpack_from('<' + ('H' if stride == 2 else 'I') * count, payload, offset))
    def words(payload):
        require(len(payload) % 4 == 0, 'Expected float32-aligned vertex stride')
        return {'float32': [v if math.isfinite(v) else str(v) for v in struct.unpack('<' + 'f' * (len(payload) // 4), payload)],
                'uint32': list(struct.unpack('<' + 'I' * (len(payload) // 4), payload))}
    ib = ia.indexBuffer
    require(str(ib.resourceId) == 'ResourceId::339' and ib.byteOffset == 256 and ib.byteStride == 2 and ib.byteSize == 32,
            'Captured fullscreen index binding changed')
    raw_indices = read('2655-ia-indices.bin', ib.resourceId, int(ib.byteOffset), int(ib.byteSize))
    indices = index_values(raw_indices, int(action.indexOffset * ib.byteStride), 3, int(ib.byteStride))
    require(len(ia.vertexBuffers) == 1, 'Unexpected fullscreen vertex buffer count')
    vb = ia.vertexBuffers[0]
    require(str(vb.resourceId) == 'ResourceId::339' and vb.byteOffset == 0 and vb.byteStride == 32 and vb.byteSize == 192,
            'Captured fullscreen vertex binding changed')
    raw_vertices = read('2655-ia-vertices.bin', vb.resourceId, int(vb.byteOffset), int(vb.byteSize))
    vertices = []
    for index in indices:
        vertex = int(index + action.vertexOffset)
        start = vertex * int(vb.byteStride)
        require(vertex >= 0 and start + vb.byteStride <= len(raw_vertices), 'Fullscreen vertex index outside bound VB')
        vertices.append({'index': index, 'index_plus_base_vertex': vertex,
            'absolute_byte_offset': int(vb.byteOffset) + start, 'record_words': words(raw_vertices[start:start + int(vb.byteStride)])})
    layouts = [{'semanticName': l.semanticName, 'semanticIndex': int(l.semanticIndex), 'inputSlot': int(l.inputSlot),
        'byteOffset': int(l.byteOffset), 'perInstance': bool(l.perInstance),
        'format': {'compCount': int(l.format.compCount), 'compByteWidth': int(l.format.compByteWidth), 'compType': str(l.format.compType)}} for l in ia.layouts]
    post = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
    require(post.numIndices == 3 and 0 < post.vertexByteStride <= 256, 'Unexpected fullscreen PostVS layout')
    post_indices = [0, 1, 2]
    if post.indexResourceId != rd.ResourceId.Null():
        raw_post_indices = read('2655-postvs-indices.bin', post.indexResourceId, int(post.indexByteOffset), int(post.numIndices * post.indexByteStride))
        post_indices = index_values(raw_post_indices, 0, 3, int(post.indexByteStride))
    post_vertices = []
    for ordinal, index in enumerate(post_indices):
        vertex = int(index + post.baseVertex)
        relative = vertex * int(post.vertexByteStride)
        require(vertex >= 0 and relative + post.vertexByteStride <= post.vertexByteSize, 'PostVS index outside vertex range')
        offset = int(post.vertexByteOffset) + relative
        record = read('2655-postvs-vertex-{}.bin'.format(ordinal), post.vertexResourceId, offset, int(post.vertexByteStride))
        post_vertices.append({'draw_vertex_ordinal': ordinal, 'index': index, 'index_plus_base_vertex': vertex,
                              'absolute_byte_offset': offset, 'record_words': words(record)})
    return {'event': 2655, 'source': 'actual D3D12 IA bindings/action offsets and RenderDoc GetPostVSData, not source-code inference',
        'action': {n: int(getattr(action, n)) for n in ('numIndices', 'numInstances', 'indexOffset', 'vertexOffset', 'instanceOffset')},
        'topology': str(ia.topology), 'index_binding': binding(ib), 'vertex_binding': binding(vb), 'layouts': layouts,
        'first_draw_index_absolute_byte_offset': int(ib.byteOffset + action.indexOffset * ib.byteStride),
        'draw_indices': indices, 'draw_ia_vertices': vertices,
        'postvs': {'vertexResourceId': str(post.vertexResourceId), 'vertexByteOffset': int(post.vertexByteOffset),
            'vertexByteStride': int(post.vertexByteStride), 'vertexByteSize': int(post.vertexByteSize),
            'indexResourceId': str(post.indexResourceId), 'indexByteOffset': int(post.indexByteOffset),
            'indexByteStride': int(post.indexByteStride), 'baseVertex': int(post.baseVertex),
            'position_format': {'compCount': int(post.format.compCount), 'compByteWidth': int(post.format.compByteWidth), 'compType': str(post.format.compType)},
            'draw_indices': post_indices, 'draw_vertices': post_vertices},
        'files': files, 'total_raw_bytes': total[0], 'hard_max_raw_bytes': 1024, 'algorithm_input': False}


cap, controller = None, None
exit_code = 1
capture = None
before = None
started = time.monotonic()
try:
    require(digest_file(PLAN) == PLAN_HASH, 'Selection plan checksum mismatch')
    with open(PLAN, 'r', encoding='utf-8') as stream:
        plan = json.load(stream)
    require(plan['version'] == 1 and plan['event'] == 2655, 'Unsupported history selection plan')
    require(plan['capture']['sha256'] == CAPTURE_HASH, 'Unexpected capture identity')
    capture = plan['capture']['path']
    require(os.path.isabs(capture) and os.path.isfile(capture), 'Capture must be an existing absolute path')
    points = plan['selected_pixels_xy']
    width, height = plan['extent']
    require([width, height] == [1424, 1040], 'Unexpected SceneColor allocation')
    require(isinstance(points, list) and 0 < len(points) <= MAX_POINTS, 'PixelHistory point count is out of bounds')
    require(all(isinstance(p, list) and len(p) == 2 and all(type(v) is int for v in p)
                and 0 <= p[0] < width and 0 <= p[1] < height for p in points), 'Invalid pixel coordinates')
    require(len(set(tuple(p) for p in points)) == len(points), 'Duplicate history pixels')
    require(os.path.isdir(OUT), 'Launcher must create the output directory')
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
    require(texture.width == width and texture.height == height and texture.msSamp == 1, 'Unsupported SceneColor dimensions/sample count')
    write('fullscreen-triangle.json', extract_fullscreen_triangle(controller))
    write('api.json', {'PixelHistory': controller.PixelHistory.__doc__, 'GetPostVSData': controller.GetPostVSData.__doc__, 'resource': str(resource),
        'extent': [width, height], 'subresource': {'mip': 0, 'slice': 0, 'sample': 0},
        'typeCast': 'CompType.Float', 'renderdoc_version': str(rd.GetVersionString()) if hasattr(rd, 'GetVersionString') else None})
    output = []
    for x, y in points:
        require(time.monotonic() - started < TIME_LIMIT_SECONDS, 'PixelHistory exceeded time budget')
        controller.SetFrameEvent(2655, True)
        # RenderDoc may replay earlier events internally. Only E2655 is retained.
        history = controller.PixelHistory(resource, x, y, rd.Subresource(), rd.CompType.Float)
        require(len(history) <= MAX_HISTORY_EVENTS, 'Unexpectedly large per-pixel history')
        entries = [entry for entry in history if entry.eventId == 2655]
        require(len(entries) == 1, 'Expected one E2655 fullscreen fragment at {},{}; got {}'.format(x, y, len(entries)))
        output.append({'xy': [x, y], 'all_history_event_count': len(history), 'history': [modification(entries[0])]})
        write('history.json', output)  # Retain completed samples if a later replay fails.
    after = digest_file(capture)
    require(after == before, 'Capture changed during PixelHistory replay')
    require(digest_file(PLAN) == PLAN_HASH, 'Selection plan changed during replay')
    write('replay-done.json', {'ok': True, 'capture_sha256_before': before, 'capture_sha256_after': after,
        'capture_unchanged': True, 'plan_sha256': PLAN_HASH, 'point_count': len(output),
        'history_sha256': digest_file(os.path.join(OUT, 'history.json')),
        'api_sha256': digest_file(os.path.join(OUT, 'api.json')),
        'fullscreen_triangle_sha256': digest_file(os.path.join(OUT, 'fullscreen-triangle.json')),
        'elapsed_seconds': time.monotonic() - started,
        'method': 'GPU replay PixelHistory; no DebugPixel shader interpreter',
        'algorithm_input': False})
    exit_code = 0
except Exception:
    failure = {'error': traceback.format_exc(), 'elapsed_seconds': time.monotonic() - started}
    if capture is not None and before is not None:
        failure.update(capture_sha256_before=before, capture_sha256_after=digest_file(capture))
        failure['capture_unchanged'] = failure['capture_sha256_after'] == before
    write('replay-error.json', failure)
finally:
    if controller is not None:
        controller.Shutdown()
    if cap is not None:
        cap.Shutdown()
os._exit(exit_code)
