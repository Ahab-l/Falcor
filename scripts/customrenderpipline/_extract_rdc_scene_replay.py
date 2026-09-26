"""RenderDoc embedded-Python worker, called by extract_rdc_scene.py (Python 3.6 compatible)."""
import gzip
import hashlib
import json
import os
import struct
import sys
import traceback
import renderdoc as rd

OUT = os.environ['UE_RDC_SCENE_OUT']
CAPTURE = os.environ['UE_RDC_SCENE_CAPTURE']
EIDS = (1816, 1827, 1838, 1853)


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


def write(name, obj):
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)


cap = None
controller = None
try:
    cap = rd.OpenCaptureFile()
    status = cap.OpenFile(CAPTURE, '', None)
    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(str(status))
    status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if controller is None:
        raise RuntimeError(str(status))
    write('replay-api.json', {n: getattr(controller, n).__doc__ for n in
          ('GetPostVSData', 'GetDescriptors', 'GetDescriptorLocations', 'GetBuffers')})
    write('descriptor-range-api.json', simple(rd.DescriptorRange()))
    buffers = {str(b.resourceId): b for b in controller.GetBuffers()}
    write('buffers.json', simple(controller.GetBuffers()))
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    if hasattr(controller, 'GetDescriptorStores'):
        write('descriptor-stores.json', simple(controller.GetDescriptorStores()))
    all_actions = {}

    def collect(actions):
        for action in actions:
            all_actions[action.eventId] = action
            collect(action.children)
    collect(controller.GetRootActions())

    def raw_buffer(name, resource, offset, length):
        raw = bytes(controller.GetBufferData(resource, offset, length))
        filename = name + '.bin'
        with open(os.path.join(OUT, filename), 'wb') as f:
            f.write(raw)
        return {'file': filename, 'resource': str(resource), 'byteOffset': offset,
                'byteSize': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    facts = []
    for eid in EIDS:
        controller.SetFrameEvent(eid, True)
        pipe = controller.GetPipelineState()
        d3d = controller.GetD3D12PipelineState()
        action = all_actions[eid]
        fact = {'eid': eid, 'action': {n: getattr(action, n) for n in
                ('numIndices', 'numInstances', 'indexOffset', 'vertexOffset', 'instanceOffset')},
                'inputAssembly': simple(d3d.inputAssembly), 'rasterizer': simple(d3d.rasterizer),
                'buffers': {}, 'cbuffers': {}, 'readOnly': {}}
        ia = d3d.inputAssembly
        fact['buffers']['indices'] = raw_buffer(str(eid) + '-indices', ia.indexBuffer.resourceId,
                ia.indexBuffer.byteOffset, ia.indexBuffer.byteSize)
        for i, vb in enumerate(ia.vertexBuffers):
            if vb.resourceId != rd.ResourceId.Null():
                size = vb.byteSize if i == 0 else min(vb.byteSize, 64)
                fact['buffers']['vb' + str(i)] = raw_buffer(str(eid) + '-vb' + str(i),
                        vb.resourceId, vb.byteOffset, size)
        for stage in (rd.ShaderStage.Vertex, rd.ShaderStage.Pixel):
            label = str(stage).split('.')[-1]
            ref = pipe.GetShaderReflection(stage)
            fact[label + 'Shader'] = {'resource': str(ref.resourceId), 'inputSignature': simple(ref.inputSignature),
                                     'outputSignature': simple(ref.outputSignature)}
            fact['cbuffers'][label] = []
            for i, block in enumerate(ref.constantBlocks):
                desc = pipe.GetConstantBlock(stage, i, 0).descriptor
                fact['cbuffers'][label].append(raw_buffer('{}-{}-cb{}'.format(eid, label, i),
                            desc.resource, desc.byteOffset, block.byteSize))
            fact['readOnly'][label] = []
            fact[label + 'Samplers'] = simple(pipe.GetSamplers(stage))
            for used in pipe.GetReadOnlyResources(stage):
                desc = used.descriptor
                entry = {'index': used.access.index, 'descriptor': simple(desc)}
                if str(desc.resource) in buffers:
                    size = min(desc.byteSize, buffers[str(desc.resource)].length - desc.byteOffset, 1024 * 1024)
                    entry.update(raw_buffer('{}-{}-srv{}'.format(eid, label, used.access.index),
                                           desc.resource, desc.byteOffset, size))
                elif eid == 1853 and label == 'Pixel' and used.access.index == 5:
                    tex = textures[str(desc.resource)]
                    entry['texture'] = simple(tex)
                    entry['mips'] = []
                    for mip in range(tex.mips):
                        sub = rd.Subresource()
                        sub.mip = mip
                        raw = bytes(controller.GetTextureData(desc.resource, sub))
                        filename = '1853-grid-mip{}.bin'.format(mip)
                        with open(os.path.join(OUT, filename), 'wb') as f:
                            f.write(raw)
                        entry['mips'].append({'file': filename, 'byteSize': len(raw),
                            'sha256': hashlib.sha256(raw).hexdigest()})
                    save = rd.TextureSave()
                    save.resourceId = desc.resource
                    save.destType = rd.FileType.DDS
                    save.mip = -1
                    controller.SaveTexture(save, os.path.join(OUT, '1853-grid.dds'))
                    save.destType = rd.FileType.PNG
                    save.mip = 0
                    controller.SaveTexture(save, os.path.join(OUT, '1853-grid.png'))
                fact['readOnly'][label].append(entry)
        # Retain raw IA mesh neighbourhood to recover unused UV streams only where independently proven.
        vb = ia.vertexBuffers[0]
        neighbourhood_start = max(0, vb.byteOffset - 65536)
        fact['meshNeighbourhood'] = raw_buffer(str(eid) + '-mesh-neighbourhood', vb.resourceId,
                neighbourhood_start, min(131072, buffers[str(vb.resourceId)].length - neighbourhood_start))
        try:
            post = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
            fact['postVS'] = simple(post)
            fact['postVS']['vertices'] = raw_buffer(str(eid) + '-postVS', post.vertexResourceId,
                    post.vertexByteOffset, post.vertexByteSize)
            if post.indexResourceId != rd.ResourceId.Null():
                fact['postVS']['indices'] = raw_buffer(str(eid) + '-postVS-indices', post.indexResourceId,
                        post.indexByteOffset, post.numIndices * post.indexByteStride)
        except Exception:
            fact['postVSError'] = traceback.format_exc()
        facts.append(fact)
        write('replay-draws.json', facts)
    depth = d3d.outputMerger.depthTarget.resource
    raw = bytes(controller.GetTextureData(depth, rd.Subresource()))
    with gzip.open(os.path.join(OUT, 'capture-depth.bin.gz'), 'wb') as f:
        f.write(raw)
    write('replay-done.json', {'ok': True, 'api': simple(controller.GetAPIProperties()),
                              'depth': {'resource': str(depth), 'bytes': len(raw),
                                        'sha256': hashlib.sha256(raw).hexdigest()}})
except Exception:
    write('replay-error.json', {'error': traceback.format_exc()})
finally:
    if controller is not None:
        controller.Shutdown()
    if cap is not None:
        cap.Shutdown()
sys.exit(0)
