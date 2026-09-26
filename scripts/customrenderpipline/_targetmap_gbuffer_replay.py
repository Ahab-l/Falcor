"""Pinned read-only E1452 MRT/DSV collector for offline reference, not renderer input.

Embedded Python 3.6: qrenderdoc --python does not set __file__. Supply
CRP_TARGETMAP_GBUFFER_SCRIPT and a fresh CRP_TARGETMAP_GBUFFER_OUT child of
build/targetmap-shading-a1. The optional CRP_TARGETMAP_GBUFFER_A0 selects an
already verified A0 run; its metadata/cbuffers are reused, never replayed here.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import traceback


CAPTURE = 'E:/rdc/ue/2.rdc'
CAPTURE_SHA256 = '059eef7978d1c32039ad4bd21b5b0c59574c393996fb842b37f3a9e4a87edb2f'
EVENT = 1452
MAX_BYTES = 64 * 1024 * 1024
RESULT_RESERVE = 64 * 1024
ROLE = 'offline_reference_only'
# Actual A0 E1452 output merger: five NONNULL RTVs, not four.
# Names and resource formats confirmed by A0 E2227 resource/usage metadata.
TARGETS = (
    ('ResourceId::955', 'SceneColor', 'R16G16B16A16_FLOAT', 'R16G16B16A16_FLOAT', 8),
    ('ResourceId::40947', 'GBufferA', 'R10G10B10A2_UNORM', 'R10G10B10A2_UNORM', 4),
    ('ResourceId::256513', 'GBufferB', 'B8G8R8A8_TYPELESS', 'B8G8R8A8_UNORM', 4),
    ('ResourceId::256515', 'GBufferC', 'B8G8R8A8_TYPELESS', 'B8G8R8A8_SRGB', 4),
    ('ResourceId::256540', 'GBufferD', 'B8G8R8A8_TYPELESS', 'B8G8R8A8_UNORM', 4),
    ('ResourceId::945', 'SceneDepthZ', 'D32S8_TYPELESS', 'D32S8', 8),
)


def sha_file(path):
    digest = hashlib.sha256()
    with open(str(path), 'rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def worker_path():
    path = Path(globals().get('__file__') or os.environ['CRP_TARGETMAP_GBUFFER_SCRIPT']).resolve()
    if path.name != '_targetmap_gbuffer_replay.py' or not path.is_file():
        raise ValueError('Invalid GBuffer worker script identity')
    return path


def load_helpers(script):
    # No reliance on qrenderdoc cwd, implicit sys.path, or A0's worker_path().
    directory = str(script.parent.resolve())
    if directory not in sys.path:
        sys.path.insert(0, directory)
    helper = importlib.import_module('_targetmap_shading_replay')
    if Path(helper.__file__).resolve() != (script.parent / '_targetmap_shading_replay.py').resolve():
        raise ValueError('Unexpected A0 helper import path')
    return helper


def prepare_output(root, out):
    base = (root / 'build/targetmap-shading-a1').resolve()
    out = Path(out).resolve()
    if out == base or os.path.commonpath([str(base), str(out)]) != str(base):
        raise ValueError('Output must be a fresh child of build/targetmap-shading-a1')
    out.mkdir(parents=True, exist_ok=False)
    return out


def validate_budget(used, count):
    if type(used) is not int or type(count) is not int or min(used, count) < 0:
        raise ValueError('Invalid artifact byte budget')
    if used + count > MAX_BYTES - RESULT_RESERVE:
        raise ValueError('Reference artifacts exceed 64 MiB including result reservation')


class Artifacts:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(exist_ok=False)
        self.used, self.files = 0, []

    def raw(self, name, payload):
        if not name or name in ('.', '..') or '/' in name or '\\' in name or ':' in name:
            raise ValueError('Artifact name must be a filename')
        payload = bytes(payload)
        validate_budget(self.used, len(payload))
        with (self.directory / name).open('xb') as stream:
            stream.write(payload)
        record = dict(file=name, byte_size=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                      role=ROLE, full_renderer_parity=False)
        self.used += len(payload)
        self.files.append(record)
        return record

    def json(self, name, value):
        return self.raw(name, (json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def plan_snapshots(event, textures, render_targets, depth_target, viewports, scissors):
    """Fail closed before GetTextureData; every non-NULL bound output is included."""
    if type(event) is not int or event != EVENT:
        raise ValueError('Not the pinned E1452 floor/base draw')
    bound = [(slot, t) for slot, t in enumerate(render_targets) if t.get('resource') != 'ResourceId::0']
    if [slot for slot, _ in bound] != list(range(5)):
        raise ValueError('Expected all five NONNULL E1452 RTV bindings, in their actual slots')
    if len(viewports) != 1 or len(scissors) != 1:
        raise ValueError('Expected exactly one viewport/scissor')
    viewport, scissor = viewports[0], scissors[0]
    for rect in (viewport, scissor):
        if [rect.get(k) for k in ('x', 'y', 'width', 'height')] != [0, 0, 1421, 1035]:
            raise ValueError('Viewport/scissor differs from the actual view rectangle')
        if rect.get('enabled') is not True:
            raise ValueError('Viewport/scissor is disabled')
    if viewport.get('minDepth') != 0 or viewport.get('maxDepth') != 1:
        raise ValueError('Unexpected viewport depth range')
    plans = []
    for index, (target, expected) in enumerate(zip([t for _, t in bound] + [depth_target], TARGETS)):
        rid, name, resource_format, view_format, bpp = expected
        wanted_target = dict(resource=rid, format=view_format, firstMip=0, firstSlice=0,
                             numMips=1, numSlices=1, elementByteSize=bpp)
        if any(target.get(k) != v for k, v in wanted_target.items()):
            raise ValueError('Unexpected {} bound identity, format, or subresource'.format(name))
        texture = textures.get(rid, {})
        wanted_texture = dict(resource=rid, name=name, format=resource_format, width=1424,
                              height=1040, depth=1, arraysize=1, mips=1, dimension=2, samples=1)
        if any(texture.get(k) != v for k, v in wanted_texture.items()):
            raise ValueError('Unexpected {} resource identity, format, name, or shape'.format(name))
        plan = dict(event=EVENT, binding='RTV' if index < 5 else 'DSV',
                    slot=index if index < 5 else None, resource=rid, name=name,
                    format=view_format, resource_format=resource_format, texture=dict(texture),
                    target=dict(target), width=1424, height=1040, viewport=dict(viewport),
                    scissor=dict(scissor), view_rect=[0, 0, 1421, 1035],
                    subresource=dict(mip=0, slice=0, sample=0),
                    planned_byte_size=1424 * 1040 * bpp, planned_bytes_per_pixel=bpp,
                    role=ROLE, full_renderer_parity=False,
                    raw_readback_encoding='unverified', plane_parity_verified=False)
        if index == 5:
            plan['encoding_constraint'] = ('D32S8 8-byte readback length is planned from the bound '
                'element size and earlier readback evidence; this run must verify it. '
                'No unpacking, depth/stencil plane offsets, or plane parity are asserted.')
        plans.append(plan)
    validate_budget(0, sum(p['planned_byte_size'] for p in plans))
    return plans


def save_snapshot(artifacts, plan, payload):
    if len(payload) != plan['planned_byte_size']:
        raise ValueError('{} raw readback length differs from preflight plan: {} != {}'.format(
            plan['name'], len(payload), plan['planned_byte_size']))
    name = 'E{}-{}-{}.raw'.format(EVENT, plan['binding'], plan['name'])
    result = dict(plan)
    result.update(artifacts.raw(name, payload))
    result['readback_length_verified'] = True
    return result


def validate_pipeline(live, prior):
    for field in ('event', 'pipeline', 'ancestry', 'output_merger', 'rasterizer'):
        if live.get(field) != prior.get(field):
            raise ValueError('Live E1452 {} differs from verified A0 evidence'.format(field))
    if live.get('event') != EVENT or live.get('pipeline') != 'ResourceId::40847':
        raise ValueError('Wrong pinned floor/base pipeline')


def read_bounded(path, limit):
    if path.stat().st_size > limit:
        raise ValueError('Audit file exceeds its bounded read size: {}'.format(path.name))
    with path.open('rb') as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError('Audit file grew beyond its bounded read size')
    return payload


def load_a0_evidence(source, artifacts):
    """Hash-verify ALL selected prior files before copying any; no new cbuffer reads."""
    source = Path(source).resolve()
    result_payload = read_bounded(source / 'result.json', RESULT_RESERVE)
    result = json.loads(result_payload.decode('utf-8'))
    if (result.get('status') != 'passed' or result.get('capture') != CAPTURE or
            result.get('sha256_before') != CAPTURE_SHA256 or result.get('sha256_after') != CAPTURE_SHA256 or
            result.get('capture_unchanged') is not True or result.get('manifest') != 'reference/manifest.json'):
        raise ValueError('A0 evidence is not a passed unchanged run of the pinned capture')
    reference = source / 'reference'
    manifest_payload = read_bounded(reference / 'manifest.json', 4 * 1024 * 1024)
    manifest_sha = hashlib.sha256(manifest_payload).hexdigest()
    if manifest_sha != result.get('manifest_sha256'):
        raise ValueError('A0 manifest SHA256 mismatch')
    manifest = json.loads(manifest_payload.decode('utf-8'))
    if (manifest.get('capture') != dict(path=CAPTURE, sha256=CAPTURE_SHA256) or
            manifest.get('role') != ROLE or manifest.get('full_renderer_parity') is not False):
        raise ValueError('A0 manifest provenance/scope mismatch')
    records = {}
    for record in manifest['files']:
        name = record['file']
        if name in records:
            raise ValueError('Duplicate file in A0 manifest')
        records[name] = record
    pending, events = {}, {}

    def verified(name):
        if not re.match(r'^E(1426|1437|1452)-(pipeline\.json|(Vertex|Pixel)(-cb[0-9]+\.bin|\.dxil\.txt))$', name):
            raise ValueError('A0 file is not an approved metadata/cbuffer/disassembly audit filename')
        if name in pending:
            return pending[name]
        record = records.get(name, {})
        size = record.get('byte_size')
        limit = 128 * 1024 if name.endswith('.bin') else 4 * 1024 * 1024
        if type(size) is not int or size < 0 or size > limit:
            raise ValueError('A0 file has invalid planned audit size')
        validate_budget(artifacts.used + sum(len(p) for p in pending.values()), size)
        path = reference / name
        if path.resolve().parent != reference.resolve():
            raise ValueError('A0 audit file escapes its reference directory')
        payload = read_bounded(path, size)
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != record.get('sha256'):
            raise ValueError('A0 file length/SHA256 mismatch: {}'.format(name))
        pending[name] = payload
        return payload

    for event in (1426, 1437, EVENT):
        evidence = json.loads(verified('E{}-pipeline.json'.format(event)).decode('utf-8'))
        if type(evidence.get('event')) is not int or evidence['event'] != event:
            raise ValueError('Wrong event in A0 pipeline file')
        for stage in evidence['stages'].values():
            for cb in stage['constant_buffers']:
                if 'raw' in cb:
                    payload = verified(cb['raw']['file'])
                    if (len(payload) != cb['raw']['byte_size'] or
                            hashlib.sha256(payload).hexdigest() != cb['raw']['sha256']):
                        raise ValueError('Cbuffer identity differs between A0 manifest and pipeline')
            if 'disassembly' in stage:
                verified(stage['disassembly']['file'])
        events[event] = evidence
    reused = []
    for name in sorted(pending):
        record = artifacts.raw(name, pending[name])
        record = dict(record, source_path=str(reference / name))
        reused.append(record)
    return dict(events=events, reused_files=reused, role=ROLE, full_renderer_parity=False,
                source_result=dict(path=str(source / 'result.json'),
                    sha256=hashlib.sha256(result_payload).hexdigest()),
                source_manifest=dict(path=str(reference / 'manifest.json'), sha256=manifest_sha),
                replayed_audit_events=[], audit_events=[1426, 1437, EVENT])


def collect(rd, controller, artifacts, prior, helpers):
    actions, ancestry = {}, {}
    structured = controller.GetStructuredFile()

    def walk(sequence, parents):
        if len(parents) > 64:
            raise ValueError('Action ancestry exceeds bound')
        for action in sequence:
            if len(actions) >= 100000:
                raise ValueError('Action metadata count exceeds bound')
            actions[action.eventId] = action
            ancestry[action.eventId] = parents + [action.GetName(structured)]
            walk(action.children, ancestry[action.eventId])

    walk(controller.GetRootActions(), [])
    if EVENT not in actions or not actions[EVENT].flags & rd.ActionFlags.Drawcall:
        raise ValueError('Pinned E1452 is absent or not an actual draw')
    names = {str(r.resourceId): r.name for r in controller.GetResources()}
    native_textures = {str(t.resourceId): t for t in controller.GetTextures()}
    textures = {}
    for rid, native in native_textures.items():
        textures[rid] = dict(resource=rid, name=names.get(rid, ''), format=native.format.Name(),
            width=native.width, height=native.height, depth=native.depth, arraysize=native.arraysize,
            mips=native.mips, dimension=native.dimension, samples=native.msSamp)
    controller.SetFrameEvent(EVENT, True)
    d3d = controller.GetD3D12PipelineState()
    live = dict(event=EVENT, ancestry=ancestry[EVENT], flags=str(actions[EVENT].flags),
                pipeline=str(d3d.pipelineResourceId), output_merger=helpers.simple(d3d.outputMerger),
                rasterizer=helpers.simple(d3d.rasterizer), role=ROLE, full_renderer_parity=False)
    validate_pipeline(live, prior)

    def target_info(target):
        if target.resource == rd.ResourceId.Null():
            return dict(resource=str(target.resource))
        info = {k: getattr(target, k) for k in ('firstMip', 'firstSlice', 'numMips', 'numSlices', 'elementByteSize')}
        info.update(resource=str(target.resource), format=target.format.Name())
        return info

    targets = [target_info(target) for target in d3d.outputMerger.renderTargets]
    depth = target_info(d3d.outputMerger.depthTarget)
    plans = plan_snapshots(EVENT, textures, targets, depth,
        helpers.simple(d3d.rasterizer.viewports), helpers.simple(d3d.rasterizer.scissors))
    validate_budget(artifacts.used, sum(p['planned_byte_size'] for p in plans))
    for plan in plans:
        usages = controller.GetUsage(native_textures[plan['resource']].resourceId)
        if len(usages) > 100000:
            raise ValueError('Resource usage metadata exceeds bound')
        plan['usages'] = [dict(event=int(u.eventId), usage=str(u.usage),
            ancestry=ancestry.get(int(u.eventId), []),
            action_name=ancestry.get(int(u.eventId), [None])[-1],
            at_or_before_snapshot=int(u.eventId) <= EVENT) for u in usages]
    pipeline_file = artifacts.json('E1452-live-pipeline.json', live)
    plan_file = artifacts.json('E1452-readback-plan.json', dict(event=EVENT, snapshots=plans,
        planned_raw_bytes=sum(p['planned_byte_size'] for p in plans),
        role=ROLE, full_renderer_parity=False))
    validate_budget(artifacts.used, sum(p['planned_byte_size'] for p in plans))
    snapshots = []
    for plan in plans:
        validate_budget(artifacts.used, plan['planned_byte_size'])
        sub = rd.Subresource()
        sub.mip, sub.slice, sub.sample = 0, 0, 0
        payload = controller.GetTextureData(native_textures[plan['resource']].resourceId, sub)
        snapshot = save_snapshot(artifacts, plan, payload)
        snapshots.append(snapshot)
        del payload
    return dict(schema='crp-rdc-gbuffer-reference-v1', role=ROLE, full_renderer_parity=False,
        capture=dict(path=CAPTURE, sha256=CAPTURE_SHA256), event=EVENT,
        state_semantics='Full resource contents after E1452; cumulative frame state, not isolated floor pixels.',
        export_scope='All five bound color RTVs and actual DSV raw; no geometry, history, or renderer inputs.',
        plane_parity_verified=False, raw_readback_encoding='unverified', snapshots=snapshots,
        pipeline_file=pipeline_file, readback_plan_file=plan_file, api=helpers.simple(controller.GetAPIProperties()))


def main():
    result = dict(status='failed', role=ROLE, full_renderer_parity=False, capture=CAPTURE,
                  pid=os.getpid(), errors=[])
    out, artifacts, cap, controller, manifest = None, None, None, None, None
    try:
        script = worker_path()
        out = prepare_output(script.parents[2], os.environ['CRP_TARGETMAP_GBUFFER_OUT'])
        result['script_sha256'] = sha_file(script)
        result['sha256_before'] = sha_file(CAPTURE)
        if result['sha256_before'] != CAPTURE_SHA256:
            raise ValueError('Capture SHA256 differs from the approved reference')
        helpers = load_helpers(script)
        result['helper_script_sha256'] = sha_file(Path(helpers.__file__))
        helpers.validate_capture(CAPTURE, result['sha256_before'])
        artifacts = Artifacts(out / 'reference')
        a0_base = (script.parents[2] / 'build/targetmap-shading-a0').resolve()
        source = Path(os.environ.get('CRP_TARGETMAP_GBUFFER_A0',
            str(a0_base / 'reference-a-0e5c7221'))).resolve()
        if source == a0_base or os.path.commonpath([str(a0_base), str(source)]) != str(a0_base):
            raise ValueError('A0 evidence must be a child of this worktree build/targetmap-shading-a0')
        audit = load_a0_evidence(source, artifacts)
        import renderdoc as rd
        cap = rd.OpenCaptureFile()
        status = cap.OpenFile(CAPTURE, '', None)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError('OpenFile: {}'.format(status))
        status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
        if status != rd.ResultCode.Succeeded or controller is None:
            raise RuntimeError('OpenCapture: {}'.format(status))
        manifest = collect(rd, controller, artifacts, audit['events'][EVENT], helpers)
        manifest['a0_audit'] = {k: v for k, v in audit.items() if k != 'events'}
        manifest['files'] = list(artifacts.files)
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
                raise ValueError('Capture identity not verified unchanged')
        except BaseException:
            result['errors'].append(traceback.format_exc())
    if not result['errors'] and manifest is not None:
        try:
            published = artifacts.json('manifest.json', manifest)
            raw_identities = [{k: snapshot[k] for k in ('event', 'resource', 'name', 'binding', 'slot',
                'format', 'resource_format', 'file', 'byte_size', 'sha256', 'role', 'full_renderer_parity')}
                for snapshot in manifest['snapshots']]
            result.update(status='passed', manifest='reference/manifest.json',
                manifest_sha256=published['sha256'], exported_bytes=artifacts.used,
                raw_identities=raw_identities, plane_parity_verified=False,
                raw_readback_encoding='unverified')
        except BaseException:
            result['errors'].append(traceback.format_exc())
    try:
        payload = (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8')
        if len(payload) > RESULT_RESERVE:
            raise ValueError('Result exceeds reserved byte budget')
        if out is not None:
            with (out / 'result.json').open('xb') as stream:
                stream.write(payload)
        else:
            sys.stderr.write(payload.decode('utf-8'))
    except BaseException:
        traceback.print_exc()
        return 1
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    try:
        code = main()
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
