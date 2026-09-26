"""Read-only E1452 Pixel t5 BC1 block oracle, NEVER a native renderer input.

qrenderdoc embeds Python 3.6 without __file__: supply CRP_TARGETMAP_TEXTURE_SCRIPT
and a fresh CRP_TARGETMAP_TEXTURE_OUT child of build/targetmap-shading-a1.
CRP_TARGETMAP_TEXTURE_A0 optionally selects a verified A0 run in this worktree.
Only ResourceId::3905's ten raw mips are exported, plus bounded audit metadata.
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
RESOURCE = 'ResourceId::3905'
ROLE = 'offline_reference_only'
MAX_BYTES = 1024 * 1024
RESULT_RESERVE = 64 * 1024
RAW_BYTES = 174776
ENCODING = 'BC1_4x4_blocks_8_bytes_tightly_packed'
# A0 E1452-pipeline.json SHA f6806ad9f79b3901528438a60abd6199b1db0b3be397abcc6355832ad39e7202:
# Pixel read_only access.index=5, shader ResourceId::40849, SRV BC1_SRGB.
# A0 Pixel DXIL line 39 register(t5,space0), line 53 handle index=5, line 291 Sample.


def sha_file(path):
    digest = hashlib.sha256()
    with open(str(path), 'rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def worker_path():
    path = Path(globals().get('__file__') or os.environ['CRP_TARGETMAP_TEXTURE_SCRIPT']).resolve()
    if path.name != '_targetmap_texture_replay.py' or not path.is_file():
        raise ValueError('Invalid texture worker script identity')
    return path


def load_helpers(script):
    directory = str(script.parent.resolve())
    if directory not in sys.path:
        sys.path.insert(0, directory)
    helper = importlib.import_module('_targetmap_shading_replay')
    if Path(helper.__file__).resolve() != (script.parent / '_targetmap_shading_replay.py').resolve():
        raise ValueError('Unexpected A0 helper import path')
    return helper


def require_child(base, path):
    base, path = Path(base).resolve(), Path(path).resolve()
    if path == base or os.path.commonpath([str(base), str(path)]) != str(base):
        raise ValueError('Path must remain a child of {}'.format(base))
    return path


def prepare_output(root, out):
    out = require_child(root / 'build/targetmap-shading-a1', out)
    out.mkdir(parents=True, exist_ok=False)
    return out


def validate_budget(used, count):
    if type(used) is not int or type(count) is not int or min(used, count) < 0:
        raise ValueError('Invalid artifact byte budget')
    if used + count > MAX_BYTES - RESULT_RESERVE:
        raise ValueError('Texture reference exceeds 1 MiB including result reservation')


def read_bounded(path, limit):
    if path.stat().st_size > limit:
        raise ValueError('File exceeds bounded read: {}'.format(path))
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('File grew beyond bounded read')
    return data


class Artifacts:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(exist_ok=False)
        self.used, self.files = 0, []

    def raw(self, name, payload):
        if not name or name in ('.', '..') or any(c in name for c in '/\\:'):
            raise ValueError('Artifact name must be a filename')
        validate_budget(self.used, len(payload))
        payload = bytes(payload)
        with (self.directory / name).open('xb') as stream:
            stream.write(payload)
        result = dict(file=name, byte_size=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                      role=ROLE, full_renderer_parity=False)
        self.used += len(payload)
        self.files.append(result)
        return result

    def json(self, name, value):
        return self.raw(name, (json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def _fields(actual, expected, label):
    for key, value in expected.items():
        observed = actual.get(key)
        if observed != value or (type(value) in (bool, int) and type(observed) is not type(value)):
            raise ValueError('Unexpected {} {}'.format(label, key))


def select_binding(pipeline):
    _fields(pipeline, dict(event=EVENT, pipeline='ResourceId::40847'), 'E1452 pipeline')
    pixel = pipeline.get('stages', {}).get('Pixel', {})
    _fields(pixel, dict(shader='ResourceId::40849', entry_point='MainPS'), 'Pixel shader')
    matches = [b for b in pixel.get('read_only', []) if b.get('access', {}).get('index') == 5]
    if len(matches) != 1:
        raise ValueError('Expected exactly one actual Pixel t5 resource binding')
    binding = matches[0]
    _fields(binding.get('access', {}), dict(index=5, stage=4, arrayElement=0, staticallyUnused=False), 't5 access')
    _fields(binding.get('descriptor', {}), dict(resource=RESOURCE, firstMip=0, numMips=10,
        firstSlice=0, numSlices=1, elementByteSize=8, minLODClamp=0.0), 't5 descriptor')
    _fields(binding, dict(view_format='BC1_SRGB'), 't5 SRV')
    identity = binding.get('identity', {})
    _fields(identity, dict(resource=RESOURCE, name='2D Texture 3905'), 't5 resource')
    _fields(identity.get('texture', {}), dict(width=512, height=512, depth=1, arraysize=1,
        mips=10, format='BC1_TYPELESS', samples=1, dimension=2), 't5 texture')
    return binding


def mip_layout():
    result, offset = [], 0
    for mip in range(10):
        width = max(1, 512 >> mip)
        blocks = max(1, (width + 3) // 4)
        size = blocks * blocks * 8
        result.append(dict(mip=mip, width=width, height=width, blocks_x=blocks, blocks_y=blocks,
            row_pitch=blocks * 8, byte_size=size, offset=offset, slice=0, sample=0))
        offset += size
    if offset != RAW_BYTES:
        raise ValueError('Pinned BC1 block geometry changed')
    return result


def save_mip(artifacts, plan, payload):
    if len(payload) != plan['byte_size']:
        raise ValueError('BC1 mip {} raw block length mismatch: {} != {}; no decoding/padding fallback'.format(
            plan['mip'], len(payload), plan['byte_size']))
    result = dict(plan)
    result.update(artifacts.raw('E1452-t5-3905-mip{:02d}.bc1.raw'.format(plan['mip']), payload))
    result.update(readback_length_verified=True, raw_readback_encoding=ENCODING)
    return result


def load_a0_evidence(source, artifacts):
    source = Path(source).resolve()
    result_raw = read_bounded(source / 'result.json', RESULT_RESERVE)
    result = json.loads(result_raw.decode('utf-8'))
    if (result.get('status') != 'passed' or result.get('capture') != CAPTURE or
        result.get('sha256_before') != CAPTURE_SHA256 or result.get('sha256_after') != CAPTURE_SHA256 or
        result.get('capture_unchanged') is not True or result.get('manifest') != 'reference/manifest.json'):
        raise ValueError('A0 is not a passed unchanged run of the pinned capture')
    reference = source / 'reference'
    manifest_raw = read_bounded(reference / 'manifest.json', MAX_BYTES)
    if hashlib.sha256(manifest_raw).hexdigest() != result.get('manifest_sha256'):
        raise ValueError('A0 manifest SHA256 mismatch')
    manifest = json.loads(manifest_raw.decode('utf-8'))
    if (manifest.get('capture') != dict(path=CAPTURE, sha256=CAPTURE_SHA256) or
        manifest.get('role') != ROLE or manifest.get('full_renderer_parity') is not False):
        raise ValueError('A0 manifest provenance mismatch')
    records = {}
    for record in manifest.get('files', []):
        if record['file'] in records:
            raise ValueError('Duplicate A0 artifact filename')
        records[record['file']] = record
    pending = []
    for name in ('E1452-pipeline.json', 'E1452-Pixel.dxil.txt'):
        record = records.get(name, {})
        size = record.get('byte_size')
        if type(size) is not int or not 0 < size <= 512 * 1024:
            raise ValueError('Invalid A0 audit file size')
        path = reference / name
        if path.resolve().parent != reference.resolve():
            raise ValueError('A0 audit file escaped reference directory')
        raw = read_bounded(path, size)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != record.get('sha256'):
            raise ValueError('A0 audit file identity mismatch: {}'.format(name))
        pending.append((name, raw))
    pipeline = json.loads(pending[0][1].decode('utf-8'))
    select_binding(pipeline)
    if not re.search(r'Texture2D<float4>\s+Texture2D5\s*:\s*register\(t5,\s*space0\)', pending[1][1].decode('utf-8')):
        raise ValueError('A0 shader audit does not confirm actual t5/space0 binding')
    validate_budget(artifacts.used, RAW_BYTES + sum(len(raw) for _, raw in pending))
    # All selected prior identities are validated before copying any audit bytes.
    copied = [artifacts.raw(name, raw) for name, raw in pending]
    return dict(pipeline=pipeline, copied_files=copied,
        source_result=dict(path=str(source / 'result.json'), sha256=hashlib.sha256(result_raw).hexdigest()),
        source_manifest=dict(path=str(reference / 'manifest.json'), sha256=hashlib.sha256(manifest_raw).hexdigest()))


def collect(rd, controller, artifacts, prior, helpers):
    prior_binding = select_binding(prior)
    validate_budget(artifacts.used, RAW_BYTES)
    api = controller.GetAPIProperties()
    if api.pipelineType != rd.GraphicsAPI.D3D12:
        raise ValueError('Raw BC1 collector requires the observed D3D12 backend')
    actions, ancestry = {}, {}
    structured = controller.GetStructuredFile()
    def walk(sequence, parents):
        if len(parents) > 64:
            raise ValueError('Action ancestry exceeds bound')
        for action in sequence:
            if len(actions) >= 100000:
                raise ValueError('Action count exceeds bound')
            actions[action.eventId] = action
            ancestry[action.eventId] = parents + [action.GetName(structured)]
            walk(action.children, ancestry[action.eventId])
    walk(controller.GetRootActions(), [])
    if EVENT not in actions or not actions[EVENT].flags & rd.ActionFlags.Drawcall:
        raise ValueError('Pinned E1452 is absent or not a draw')
    controller.SetFrameEvent(EVENT, True)
    pipe, d3d = controller.GetPipelineState(), controller.GetD3D12PipelineState()
    for field, live in [('pipeline', str(d3d.pipelineResourceId)), ('ancestry', ancestry[EVENT]),
                        ('rasterizer', helpers.simple(d3d.rasterizer)), ('output_merger', helpers.simple(d3d.outputMerger))]:
        if live != prior.get(field):
            raise ValueError('Live E1452 {} differs from A0'.format(field))
    reflection = pipe.GetShaderReflection(rd.ShaderStage.Pixel)
    if reflection is None or str(reflection.resourceId) != 'ResourceId::40849' or reflection.entryPoint != 'MainPS':
        raise ValueError('Live Pixel shader differs from A0')
    used = [b for b in pipe.GetReadOnlyResources(rd.ShaderStage.Pixel) if b.access.index == 5]
    if len(used) != 1:
        raise ValueError('Expected one live Pixel t5 binding')
    used = used[0]
    stage = used.access.stage
    if isinstance(stage, bool) or not isinstance(stage, int) or stage != rd.ShaderStage.Pixel:
        raise ValueError('Live t5 access is not the actual Pixel shader stage')
    names = {str(r.resourceId): r.name for r in controller.GetResources()}
    textures = {str(t.resourceId): t for t in controller.GetTextures()}
    resource = str(used.descriptor.resource)
    if resource not in textures:
        raise ValueError('Live t5 is not a texture')
    texture = textures[resource]
    binding = dict(access=helpers.simple(used.access), descriptor=helpers.simple(used.descriptor),
        view_format=used.descriptor.format.Name(), identity=dict(resource=resource, name=names.get(resource, ''),
        texture=dict(width=texture.width, height=texture.height, depth=texture.depth, arraysize=texture.arraysize,
            mips=texture.mips, format=texture.format.Name(), samples=texture.msSamp, dimension=texture.dimension)))
    # simple() preserves native int-enums, while A0's JSON round trip produces
    # built-in ints. Normalize only the stage already verified as native Pixel.
    binding['access']['stage'] = int(stage)
    live = dict(event=EVENT, pipeline=str(d3d.pipelineResourceId), stages={'Pixel': dict(
        shader=str(reflection.resourceId), entry_point=reflection.entryPoint, read_only=[binding])})
    select_binding(live)
    for field in ('access', 'descriptor'):
        a, b = dict(binding[field]), dict(prior_binding[field])
        # Format's Name() is compared explicitly; do not infer type casting from JSON internals.
        if field == 'descriptor':
            a.pop('format', None); b.pop('format', None)
        if a != b:
            raise ValueError('Live t5 {} differs from A0'.format(field))
    binding_file = artifacts.json('E1452-live-t5.json', dict(binding=binding, role=ROLE, full_renderer_parity=False))
    plans = mip_layout()
    validate_budget(artifacts.used, RAW_BYTES)
    mips = []
    for plan in plans:
        validate_budget(artifacts.used, plan['byte_size'])
        sub = rd.Subresource()
        sub.mip, sub.slice, sub.sample = plan['mip'], 0, 0
        payload = controller.GetTextureData(texture.resourceId, sub)
        mips.append(save_mip(artifacts, plan, payload))
        del payload
    # API no-remap + BC1 identity + exact block lengths: no decode, row-padding,
    # sRGB conversion, DDS synthesis, or attempts to repair an unexpected payload.
    # v1.45 replay_controller.cpp:582 passes default GetTextureDataParams;
    # replay_driver.h:94-97 defaults standardLayout=false, resolve=false, NoRemap.
    # D3D12 backend:3859 remaps only if requested; 4143-4192 copies this subresource;
    # 4218 allocates GetByteSize(copyDesc.Format); 4291-4303 strips row pitch via memcpy.
    return dict(schema='crp-rdc-texture-reference-v1', role=ROLE, full_renderer_parity=False,
        capture=dict(path=CAPTURE, sha256=CAPTURE_SHA256), event=EVENT, resource=RESOURCE,
        binding=dict(stage='Pixel', index=5, register='t5', space=0), resource_format='BC1_TYPELESS',
        view_format='BC1_SRGB', texture=dict(binding['identity']['texture']), mips=mips, raw_bytes=RAW_BYTES,
        raw_readback_encoding=ENCODING, readback_length_verified=True, source_binary_identity_verified=False,
        readback_api='GetTextureData(resource, Subresource(mip,0,0)); default NoRemap',
        state_semantics='Resource contents after E1452, used through its Pixel t5 SRV; read-only offline oracle.',
        export_scope='Only ten pinned BC1 raw mip payloads and E1452 audit metadata; no renderer inputs.',
        live_binding_file=binding_file, api=helpers.simple(api))


def main():
    result = dict(status='failed', role=ROLE, full_renderer_parity=False, capture=CAPTURE, pid=os.getpid(), errors=[])
    out, artifacts, cap, controller, manifest = None, None, None, None, None
    try:
        script = worker_path()
        out = prepare_output(script.parents[2], os.environ['CRP_TARGETMAP_TEXTURE_OUT'])
        result['script_sha256'] = sha_file(script)
        result['sha256_before'] = sha_file(CAPTURE)
        if result['sha256_before'] != CAPTURE_SHA256:
            raise ValueError('Capture SHA256 differs from approved reference')
        helpers = load_helpers(script)
        result['helper_script_sha256'] = sha_file(Path(helpers.__file__))
        artifacts = Artifacts(out / 'reference')
        a0_base = (script.parents[2] / 'build/targetmap-shading-a0').resolve()
        source = require_child(a0_base, os.environ.get('CRP_TARGETMAP_TEXTURE_A0', str(a0_base / 'reference-a-0e5c7221')))
        audit = load_a0_evidence(source, artifacts)
        import renderdoc as rd
        cap = rd.OpenCaptureFile()
        status = cap.OpenFile(CAPTURE, '', None)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError('OpenFile: {}'.format(status))
        status, controller = cap.OpenCapture(rd.ReplayOptions(), None)
        if status != rd.ResultCode.Succeeded or controller is None:
            raise RuntimeError('OpenCapture: {}'.format(status))
        manifest = collect(rd, controller, artifacts, audit['pipeline'], helpers)
        manifest['a0_audit'] = {k: v for k, v in audit.items() if k != 'pipeline'}
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
            result.update(status='passed', manifest='reference/manifest.json', manifest_sha256=published['sha256'],
                          exported_bytes=artifacts.used, raw_bytes=RAW_BYTES, mip_count=10, resource=RESOURCE,
                          raw_readback_encoding=ENCODING, readback_length_verified=True)
        except BaseException:
            result['errors'].append(traceback.format_exc())
    try:
        payload = (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8')
        if len(payload) > RESULT_RESERVE:
            raise ValueError('Result exceeds reserved byte budget')
        if out is None:
            sys.stderr.write(payload.decode('utf-8'))
        else:
            with (out / 'result.json').open('xb') as stream:
                stream.write(payload)
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
