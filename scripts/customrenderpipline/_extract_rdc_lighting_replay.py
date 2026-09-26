"""Bounded, read-only RenderDoc worker for extract_rdc_lighting.py (Python 3.6)."""
import gzip
import hashlib
import json
import os
import sys
import traceback

import renderdoc as rd

OUT = os.environ['UE_RDC_LIGHTING_OUT']
CAPTURE = os.environ['UE_RDC_LIGHTING_CAPTURE']
EID = 2655
MAX_RAW_BYTES = 256 * 1024 * 1024
raw_bytes = 0


def simple(obj, depth=0):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, rd.ResourceId):
        return str(obj)
    if depth > 8:
        return str(obj)
    if hasattr(obj, '__iter__') or (hasattr(obj, '__len__') and hasattr(obj, '__getitem__')):
        return [simple(x, depth + 1) for x in obj]
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


def fmt(value):
    result = simple(value)
    try:
        result['name'] = value.Name()
    except Exception:
        pass
    return result


def raw_file(name, data, compress=False):
    global raw_bytes
    data = bytes(data)
    raw_bytes += len(data)
    if raw_bytes > MAX_RAW_BYTES:
        raise RuntimeError('Lighting export exceeded 256 MiB raw-data bound')
    if compress:
        name += '.gz'
        with gzip.open(os.path.join(OUT, name), 'wb') as stream:
            stream.write(data)
    else:
        with open(os.path.join(OUT, name), 'wb') as stream:
            stream.write(data)
    return {'file': name, 'byteSize': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'compression': 'gzip' if compress else 'none'}


cap, controller, trace = None, None, None
try:
    cap = rd.OpenCaptureFile()
    status = cap.OpenFile(CAPTURE, '', None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if controller is None:
        raise RuntimeError(str(status))
    write('api.json', {name: getattr(controller, name).__doc__ for name in
          ('SetFrameEvent', 'GetTextureData', 'GetUsage', 'DisassembleShader',
           'GetCBufferVariableContents', 'DebugPixel', 'ContinueDebug', 'FreeTrace')})
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    resources = {str(r.resourceId): r.name for r in controller.GetResources()}
    actions, ancestry = {}, {}
    structured = controller.GetStructuredFile()

    def collect(sequence, parents):
        for action in sequence:
            name = action.GetName(structured)
            actions[action.eventId] = action
            ancestry[action.eventId] = parents + [name]
            collect(action.children, parents + [name])

    collect(controller.GetRootActions(), [])
    previous = max(e for e, a in actions.items() if e < EID and a.flags & rd.ActionFlags.Drawcall)
    if previous != 2624:
        raise RuntimeError('Unexpected preceding draw {}, expected 2624'.format(previous))
    controller.SetFrameEvent(EID, True)
    pipe = controller.GetPipelineState()
    d3d = controller.GetD3D12PipelineState()
    scene = d3d.outputMerger.renderTargets[0].resource
    fact = {'event': EID, 'previousDrawEvent': previous, 'ancestry': ancestry[EID],
            'previousDrawAncestry': ancestry[previous], 'sceneColorResource': str(scene),
            'pipelineResource': str(d3d.pipelineResourceId), 'stages': {},
            'outputMerger': simple(d3d.outputMerger), 'rasterizer': simple(d3d.rasterizer),
            'inputAssembly': simple(d3d.inputAssembly), 'textureExports': [], 'sceneColor': []}
    blend = d3d.outputMerger.blendState.blends[0]
    depth = d3d.outputMerger.depthStencilState
    fact['stateNames'] = {
        'colorSource': str(blend.colorBlend.source), 'colorDestination': str(blend.colorBlend.destination),
        'colorOperation': str(blend.colorBlend.operation), 'alphaSource': str(blend.alphaBlend.source),
        'alphaDestination': str(blend.alphaBlend.destination), 'alphaOperation': str(blend.alphaBlend.operation),
        'depthFunction': str(depth.depthFunction), 'cullMode': str(d3d.rasterizer.state.cullMode)}
    fact['sceneColorUsage'] = simple(controller.GetUsage(scene))
    fact['nearbyActions'] = [{'event': e, 'flags': str(a.flags), 'ancestry': ancestry[e],
                              'numIndices': a.numIndices, 'numInstances': a.numInstances}
                             for e, a in sorted(actions.items()) if 2380 <= e <= EID]
    exported = {}
    for stage in (rd.ShaderStage.Vertex, rd.ShaderStage.Pixel):
        label = str(stage).split('.')[-1]
        ref = pipe.GetShaderReflection(stage)
        stage_data = {'shader': str(ref.resourceId), 'entryPoint': ref.entryPoint,
                      'reflection': simple(ref), 'samplers': simple(pipe.GetSamplers(stage)),
                      'constantBuffers': [], 'readOnly': [], 'readWrite': simple(pipe.GetReadWriteResources(stage))}
        shader_name = 'shader-{}-{}.txt'.format(EID, label)
        with open(os.path.join(OUT, shader_name), 'w', encoding='utf-8') as stream:
            stream.write(controller.DisassembleShader(d3d.pipelineResourceId, ref, ''))
        stage_data['disassemblyFile'] = shader_name
        for index, block in enumerate(ref.constantBlocks):
            desc = pipe.GetConstantBlock(stage, index, 0).descriptor
            data = raw_file('{}-{}-cb{}.bin'.format(EID, label, index),
                            controller.GetBufferData(desc.resource, desc.byteOffset, block.byteSize))
            data.update(index=index, reflection=simple(block), descriptor=simple(desc))
            stage_data['constantBuffers'].append(data)
        for used in pipe.GetReadOnlyResources(stage):
            desc = used.descriptor
            key = str(desc.resource)
            entry = {'access': simple(used.access), 'descriptor': simple(desc),
                     'viewFormat': fmt(desc.format), 'resourceName': resources.get(key, '')}
            stage_data['readOnly'].append(entry)
            if used.access.staticallyUnused or key not in textures:
                continue
            tex = textures[key]
            entry['texture'] = simple(tex)
            entry['resourceFormat'] = fmt(tex.format)
            if tex.dimension != 2:
                entry['notExportedReason'] = 'Not a 2D texture'
                continue
            count_mips = min(desc.numMips, tex.mips - desc.firstMip)
            count_slices = min(desc.numSlices, tex.arraysize - desc.firstSlice)
            if count_mips * count_slices > 32 or tex.msSamp > 1:
                raise RuntimeError('Unexpected large/multisample lighting texture view')
            entry['subresources'] = []
            for mip in range(desc.firstMip, desc.firstMip + count_mips):
                for layer in range(desc.firstSlice, desc.firstSlice + count_slices):
                    export_key = (key, mip, layer)
                    if export_key not in exported:
                        sub = rd.Subresource()
                        sub.mip, sub.slice = mip, layer
                        name = '{}-{}-t{}-mip{}-slice{}.bin'.format(EID, label, used.access.index, mip, layer)
                        data = raw_file(name, controller.GetTextureData(desc.resource, sub), True)
                        data.update(resource=key, name=resources.get(key, ''), mip=mip, slice=layer,
                                    width=max(1, tex.width >> mip), height=max(1, tex.height >> mip),
                                    resourceFormat=fmt(tex.format), usage=simple(controller.GetUsage(desc.resource)))
                        exported[export_key] = data
                        fact['textureExports'].append(data)
                    entry['subresources'].append(exported[export_key]['file'])
        fact['stages'][label] = stage_data
    # All snapshots refer to the same resource, regardless of which target the preceding draw bound.
    scene_tex = textures[str(scene)]
    for event in (2520, previous, EID):
        controller.SetFrameEvent(event, True)
        data = raw_file('{}-SceneColor.bin'.format(event), controller.GetTextureData(scene, rd.Subresource()), True)
        data.update(event=event, resource=str(scene), width=scene_tex.width, height=scene_tex.height,
                    resourceFormat=fmt(scene_tex.format), ancestry=ancestry[event])
        fact['sceneColor'].append(data)
    write('replay-lighting.json', fact)
    # Optional bounded traces are evidence of shader execution, never replayed as lighting output.
    points = json.loads(os.environ.get('UE_RDC_LIGHTING_POINTS', '[]'))
    if not isinstance(points, list) or len(points) > 4:
        raise RuntimeError('At most four debug pixels are allowed')
    debug_results = []
    controller.SetFrameEvent(EID, True)
    for point in points:
        x, y = point
        if any(type(v) is not int or v < 0 for v in point):
            raise RuntimeError('Debug pixel coordinates must be nonnegative integers')
        prefix = 'debug-{}-{}'.format(x, y)
        trace = controller.DebugPixel(x, y, rd.DebugPixelInputs())
        write(prefix + '-trace.json', simple(trace))
        states = []
        for batch in range(100):
            chunk = controller.ContinueDebug(trace.debugger)
            if not chunk:
                break
            states.extend(simple(chunk))
        else:
            raise RuntimeError('Pixel trace exceeded 100 batches')
        if not states:
            raise RuntimeError('Debug pixel produced no states')
        write(prefix + '-states.json', states)
        debug_results.append({'pixel': point, 'states': len(states), 'trace': prefix + '-trace.json',
                              'stateFile': prefix + '-states.json'})
        controller.FreeTrace(trace)
        trace = None
    write('replay-done.json', {'ok': True, 'rawBytesExported': raw_bytes,
                              'debugPixels': debug_results, 'api': simple(controller.GetAPIProperties())})
except Exception:
    write('replay-error.json', {'error': traceback.format_exc()})
finally:
    if trace is not None and trace.debugger is not None:
        controller.FreeTrace(trace)
    if controller is not None:
        controller.Shutdown()
    if cap is not None:
        cap.Shutdown()
sys.exit(0)
