"""Pinned, read-only targetmap RDC oracle collector; never a renderer input loader.

Run using qrenderdoc --python with CRP_TARGETMAP_REFERENCE_OUT set to a fresh
directory under this worktree's build/targetmap-shading-a0. Embedded Python 3.6.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback

CAPTURE = 'E:/rdc/ue/2.rdc'
CAPTURE_SHA256 = '059eef7978d1c32039ad4bd21b5b0c59574c393996fb842b37f3a9e4a87edb2f'
CHECKPOINTS = (2793, 2962)
AUDIT_EVENTS = (1426, 1437, 1452, 1978, 2058, 2227, 2680, 2701, 2761)
MAX_BYTES = 64 * 1024 * 1024
MAX_CBUFFER = 128 * 1024


def sha_file(path):
    h = hashlib.sha256()
    with open(str(path), 'rb') as stream:
        for part in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def worker_path():
    # qrenderdoc --python executes source without populating __file__.
    path = Path(globals().get('__file__') or os.environ['CRP_TARGETMAP_REFERENCE_SCRIPT']).resolve()
    if path.name != '_targetmap_shading_replay.py' or not path.is_file():
        raise ValueError('Invalid reference worker script identity')
    return path


def validate_capture(path, digest):
    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.realpath(CAPTURE)):
        raise ValueError('Only the approved targetmap capture is allowed')
    if digest != CAPTURE_SHA256:
        raise ValueError('Capture SHA256 differs from the approved reference')


def validate_budget(used, count):
    if type(used) is not int or type(count) is not int or min(used, count) < 0 or used + count > MAX_BYTES:
        raise ValueError('Reference artifacts exceed the 64 MiB export budget')


def validate_snapshot(event, texture, target, viewport, scissor, byte_size):
    if type(event) is not int or event not in CHECKPOINTS:
        raise ValueError('Not an approved shading checkpoint')
    wanted = dict(resource='ResourceId::955', format='R16G16B16A16_FLOAT', width=1424,
                  height=1040, depth=1, arraysize=1, mips=1, dimension=2, samples=1)
    if any(texture.get(key) != value for key, value in wanted.items()):
        raise ValueError('Unexpected SceneColor identity, format or shape')
    view = dict(resource='ResourceId::955', firstMip=0, firstSlice=0, numMips=1,
                numSlices=1, format='R16G16B16A16_FLOAT')
    if any(target.get(key) != value for key, value in view.items()):
        raise ValueError('Unexpected SceneColor RTV or subresource')
    rect = [viewport.get(key) for key in ('x', 'y', 'width', 'height')]
    clip = [scissor.get(key) for key in ('x', 'y', 'width', 'height')]
    if rect != [0, 0, 1421, 1035] or clip != rect:
        raise ValueError('Actual viewport/scissor differs from the approved view rectangle')
    if viewport.get('minDepth') != 0 or viewport.get('maxDepth') != 1:
        raise ValueError('Unexpected viewport depth range')
    if not viewport.get('enabled') or not scissor.get('enabled'):
        raise ValueError('Viewport/scissor must be enabled')
    if type(byte_size) is not int or byte_size != 1424 * 1040 * 8:
        raise ValueError('Raw RGBA16F payload length mismatch')
    return dict(event=event, resource='ResourceId::955', format=wanted['format'],
                width=1424, height=1040, view_rect=[0, 0, 1421, 1035],
                subresource=dict(mip=0, slice=0, sample=0), byte_size=byte_size)


def simple(obj, depth=0):
    """Bound native metadata traversal; do not serialize arbitrary shader bytes."""
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else str(obj)
    if type(obj).__name__ == 'ResourceId':
        return str(obj)
    if depth > 8:
        raise ValueError('Native metadata traversal exceeded depth bound')
    if isinstance(obj, dict):
        return {str(k): simple(v, depth + 1) for k, v in obj.items()}
    if hasattr(obj, '__iter__') or (hasattr(obj, '__len__') and hasattr(obj, '__getitem__')):
        if len(obj) > 100000:
            raise ValueError('Native metadata sequence exceeded length bound')
        return [simple(v, depth + 1) for v in obj]
    result = {}
    for name in dir(obj):
        if name.startswith('_') or name in ('this', 'thisown'):
            continue
        value = getattr(obj, name)
        if not callable(value):
            result[name] = simple(value, depth + 1)
    return result if result else str(obj)


class Artifacts:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(exist_ok=False)
        self.used = 0
        self.files = []

    def raw(self, name, payload):
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Artifact name must be a filename')
        payload = bytes(payload)
        validate_budget(self.used, len(payload))
        with (self.directory / name).open('xb') as stream:
            stream.write(payload)
        self.used += len(payload)
        record = dict(file=name, byte_size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        self.files.append(record)
        return record

    def json(self, name, data):
        return self.raw(name, (json.dumps(data, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def collect(rd, controller, artifacts):
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    names = {str(r.resourceId): r.name for r in controller.GetResources()}
    actions, ancestry = {}, {}
    structured = controller.GetStructuredFile()

    def walk(sequence, parents):
        for action in sequence:
            name = action.GetName(structured)
            actions[action.eventId] = action
            ancestry[action.eventId] = parents + [name]
            walk(action.children, parents + [name])
    walk(controller.GetRootActions(), [])
    usage = {}

    def resource_info(rid):
        key = str(rid)
        if key not in usage and rid != rd.ResourceId.Null():
            usage[key] = [dict(event=int(u.eventId), usage=str(u.usage)) for u in controller.GetUsage(rid)]
        info = dict(resource=key, name=names.get(key, ''), usages=usage.get(key, []))
        if key in textures:
            t = textures[key]
            info['texture'] = dict(width=t.width, height=t.height, depth=t.depth,
                                   arraysize=t.arraysize, mips=t.mips, format=t.format.Name(),
                                   samples=t.msSamp, dimension=t.dimension)
        return info

    def event_evidence(event):
        action = actions[event]
        controller.SetFrameEvent(event, True)
        pipe = controller.GetPipelineState()
        d3d = controller.GetD3D12PipelineState()
        stages = (rd.ShaderStage.Compute,) if action.flags & rd.ActionFlags.Dispatch else (
            rd.ShaderStage.Vertex, rd.ShaderStage.Pixel)
        evidence = dict(event=event, ancestry=ancestry[event], flags=str(action.flags),
                        pipeline=str(d3d.pipelineResourceId), rasterizer=simple(d3d.rasterizer),
                        output_merger=simple(d3d.outputMerger), stages={})
        for stage in stages:
            reflection = pipe.GetShaderReflection(stage)
            if reflection is None:
                raise ValueError('Missing shader reflection at event {}'.format(event))
            label = str(stage).split('.')[-1]
            data = dict(shader=str(reflection.resourceId), entry_point=reflection.entryPoint,
                        constant_buffers=[], read_only=[], read_write=[], samplers=simple(pipe.GetSamplers(stage)))
            for i, block in enumerate(reflection.constantBlocks):
                bound = pipe.GetConstantBlock(stage, i, 0)
                desc = bound.descriptor
                item = dict(index=i, reflection=simple(block), descriptor=simple(desc), access=simple(bound.access))
                if block.byteSize < 0 or block.byteSize > MAX_CBUFFER:
                    raise ValueError('Constant buffer exceeds 128 KiB audit limit')
                if block.bufferBacked and desc.resource != rd.ResourceId.Null() and block.byteSize:
                    validate_budget(artifacts.used, int(block.byteSize))
                    payload = bytes(controller.GetBufferData(desc.resource, desc.byteOffset, block.byteSize))
                    if len(payload) != block.byteSize:
                        raise ValueError('Short constant-buffer audit read')
                    item['raw'] = artifacts.raw('E{}-{}-cb{}.bin'.format(event, label, i), payload)
                else:
                    item['not_exported'] = 'No nonempty buffer-backed binding; no guessed offset/value'
                data['constant_buffers'].append(item)
            for method, field in ((pipe.GetReadOnlyResources, 'read_only'), (pipe.GetReadWriteResources, 'read_write')):
                for used in method(stage):
                    desc = used.descriptor
                    data[field].append(dict(access=simple(used.access), descriptor=simple(desc),
                                            view_format=desc.format.Name(), identity=resource_info(desc.resource)))
            if event in (1452, 2793):
                code = controller.DisassembleShader(d3d.pipelineResourceId, reflection, '')
                if not code or len(code) > 8 * 1024 * 1024:
                    raise ValueError('Unexpected shader disassembly size')
                data['disassembly'] = artifacts.raw('E{}-{}.dxil.txt'.format(event, label), code.encode('utf-8'))
            evidence['stages'][label] = data
        return pipe, d3d, evidence

    snapshots, event_files = [], []
    # Snapshot approved outputs first; subsequent audit events never feed them.
    for event in CHECKPOINTS + AUDIT_EVENTS:
        if event not in actions:
            raise ValueError('Expected event absent from pinned capture')
        pipe, d3d, evidence = event_evidence(event)
        if event in CHECKPOINTS:
            if not actions[event].flags & rd.ActionFlags.Drawcall:
                raise ValueError('Checkpoint is not an actual draw')
            target = d3d.outputMerger.renderTargets[0]
            texture = textures[str(target.resource)]
            t = dict(resource=str(texture.resourceId), format=texture.format.Name(), width=texture.width,
                     height=texture.height, depth=texture.depth, arraysize=texture.arraysize,
                     mips=texture.mips, dimension=texture.dimension, samples=texture.msSamp)
            rt = {key: getattr(target, key) for key in ('firstMip', 'firstSlice', 'numMips', 'numSlices')}
            rt.update(resource=str(target.resource), format=target.format.Name())
            viewports = simple(d3d.rasterizer.viewports)
            scissors = simple(d3d.rasterizer.scissors)
            if len(viewports) != 1 or len(scissors) != 1:
                raise ValueError('Expected exactly one viewport and scissor')
            expected_size = 1424 * 1040 * 8
            snapshot = validate_snapshot(event, t, rt, viewports[0], scissors[0], expected_size)
            validate_budget(artifacts.used, expected_size)
            sub = rd.Subresource()
            sub.mip, sub.slice, sub.sample = 0, 0, 0
            payload = bytes(controller.GetTextureData(target.resource, sub))
            validate_snapshot(event, t, rt, viewports[0], scissors[0], len(payload))
            snapshot.update(artifacts.raw('E{}-SceneColor.rgba16f'.format(event), payload))
            snapshot['pipeline_file'] = 'E{}-pipeline.json'.format(event)
            snapshots.append(snapshot)
            del payload
        event_files.append(artifacts.json('E{}-pipeline.json'.format(event), evidence))
    return dict(schema='crp-rdc-shading-reference-v1', role='offline_reference_only',
                capture=dict(path=CAPTURE, sha256=CAPTURE_SHA256), full_renderer_parity=False,
                checkpoints=snapshots, audit_events=list(AUDIT_EVENTS), pipeline_files=event_files,
                files=list(artifacts.files), api=simple(controller.GetAPIProperties()),
                export_scope='SceneColor checkpoint oracle + cbuffer audit only; no IA/postVS/history/other texture payloads')


def main():
    script = worker_path()
    root = script.parents[2]
    base = (root / 'build/targetmap-shading-a0').resolve()
    out = Path(os.environ['CRP_TARGETMAP_REFERENCE_OUT']).resolve()
    if out == base or os.path.commonpath([str(base), str(out)]) != str(base):
        raise ValueError('Output must be a fresh child of build/targetmap-shading-a0')
    if (out / 'result.json').exists() or (out / 'reference').exists():
        raise ValueError('Refusing to reuse an existing replay result directory')
    out.mkdir(parents=True, exist_ok=True)
    result = dict(status='failed', role='offline_reference_only', full_renderer_parity=False,
                  capture=CAPTURE, pid=os.getpid(), errors=[], script_sha256=sha_file(script))
    cap, controller, manifest, artifacts = None, None, None, None
    try:
        result['sha256_before'] = sha_file(CAPTURE)
        validate_capture(CAPTURE, result['sha256_before'])
        import renderdoc as rd
        artifacts = Artifacts(out / 'reference')
        cap = rd.OpenCaptureFile()
        status = cap.OpenFile(CAPTURE, '', None)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError('OpenFile: {}'.format(status))
        status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
        if status != rd.ResultCode.Succeeded or controller is None:
            raise RuntimeError('OpenCapture: {}'.format(status))
        manifest = collect(rd, controller, artifacts)
    except BaseException:
        result['errors'].append(traceback.format_exc())
    finally:
        for name, obj in (('controller', controller), ('capture', cap)):
            if obj is not None:
                try:
                    obj.Shutdown()
                    result[name + '_shutdown'] = True
                except BaseException:
                    result['errors'].append(traceback.format_exc())
        try:
            result['sha256_after'] = sha_file(CAPTURE)
            result['capture_unchanged'] = result.get('sha256_before') == result['sha256_after'] == CAPTURE_SHA256
            if not result['capture_unchanged']:
                raise ValueError('Capture identity changed')
        except BaseException:
            result['errors'].append(traceback.format_exc())
    if not result['errors'] and manifest is not None:
        try:
            published = artifacts.json('manifest.json', manifest)
            result.update(status='passed', manifest='reference/manifest.json',
                          manifest_sha256=published['sha256'], exported_bytes=artifacts.used)
        except BaseException:
            result['errors'].append(traceback.format_exc())
    with (out / 'result.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    try:
        code = main()
    except BaseException:
        traceback.print_exc()
        sys.stderr.flush()
        code = 1
    os._exit(code)
