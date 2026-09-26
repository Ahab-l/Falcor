"""Export and inspect E2655 directional-light inputs without modifying the capture.

Use --replay for one hidden RenderDoc process. Offline analysis uses only the raw
exports; SceneColor deltas are comparison evidence, not an algorithm substitute.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT.parent / 'Falcor/docs/research/captures/2026-09-09-1'


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(16 * 1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_dds(path, record, payload, dxgi_format, bytes_per_pixel):
    """Preserve a single native 2D payload behind a standard DDS/DX10 header."""
    width, height = record['width'], record['height']
    if len(payload) != width * height * bytes_per_pixel:
        raise ValueError('DDS input is not the expected tightly packed native subresource')
    header = [124, 0x100F, height, width, width * bytes_per_pixel, 0, 1] + [0] * 11
    header += [32, 4, struct.unpack('<I', b'DX10')[0], 0, 0, 0, 0, 0]
    header += [0x1000, 0, 0, 0, 0]
    assert len(header) == 31
    prefix = b'DDS ' + struct.pack('<31I', *header) + struct.pack('<5I', dxgi_format, 3, 0, 1, 0)
    assert len(prefix) == 148
    path.write_bytes(prefix + payload)
    written_payload = path.read_bytes()[148:]
    if written_payload != payload:
        raise RuntimeError('DDS payload changed during export')
    return {'path': str(path.resolve()), 'dxgiFormat': dxgi_format, 'width': width, 'height': height,
            'payloadOffset': 148, 'payloadBytes': len(payload), 'sourceRawFile': record['file'],
            'sourceRawSha256': record['sha256'], 'ddsPayloadSha256': hashlib.sha256(written_payload).hexdigest(),
            'ddsSha256': sha(path), 'payloadUnchanged': True}


def analyze(out, capture, before_hash, evidence):
    raw = out / 'raw'
    if (raw / 'replay-error.json').exists():
        raise RuntimeError((raw / 'replay-error.json').read_text())
    done = json.loads((raw / 'replay-done.json').read_text())
    facts = json.loads((raw / 'replay-lighting.json').read_text())
    verified = []
    arrays = {}
    for record in facts['textureExports'] + facts['sceneColor']:
        data = gzip.decompress((raw / record['file']).read_bytes())
        assert len(data) == record['byteSize'] and hashlib.sha256(data).hexdigest() == record['sha256']
        verified.append(record['file'])
        if 'event' in record:
            arrays[record['event']] = np.frombuffer(data, dtype='<f2').reshape(record['height'], record['width'], 4).astype(np.float32)
    for stage in facts['stages'].values():
        for record in stage['constantBuffers']:
            data = (raw / record['file']).read_bytes()
            assert len(data) == record['byteSize'] and hashlib.sha256(data).hexdigest() == record['sha256']
            verified.append(record['file'])
    post, pre = arrays[2655], arrays[facts['previousDrawEvent']]
    delta = post - pre
    # Half-float attachment subtraction measures the blended result, not the unrounded PS return.
    np.save(out / 'direct-light-delta.npy', delta)
    ps = facts['stages']['Pixel']
    cb1 = (raw / next(c['file'] for c in ps['constantBuffers'] if c['index'] == 1)).read_bytes()
    layout = [('ShadowMapChannelMask', 0, '4f'), ('DistanceFadeMAD', 16, '2f'),
              ('ContactShadowLength', 24, 'f'), ('ContactShadowCastingIntensity', 28, 'f'),
              ('ContactShadowNonCastingIntensity', 32, 'f'), ('VolumetricScatteringIntensity', 36, 'f'),
              ('ShadowedBits', 40, 'I'), ('LightingChannelMask', 44, 'I'),
              ('TranslatedWorldPosition', 48, '3f'), ('InvRadius', 60, 'f'), ('Color', 64, '3f'),
              ('FalloffExponent', 76, 'f'), ('Direction', 80, '3f'), ('SpecularScale', 92, 'f'),
              ('DiffuseScale', 96, 'f'), ('Tangent', 112, '3f'), ('SourceRadius', 124, 'f'),
              ('SpotAngles', 128, '2f'), ('SoftSourceRadius', 136, 'f'), ('SourceLength', 140, 'f'),
              ('RectLightBarnCosAngle', 144, 'f'), ('RectLightBarnLength', 148, 'f'),
              ('RectLightAtlasUVOffset', 152, '2f'), ('RectLightAtlasUVScale', 160, '2f'),
              ('RectLightAtlasMaxLevel', 168, 'f'), ('IESAtlasIndex', 172, 'f'),
              ('LightFunctionAtlasLightIndex', 176, 'I'), ('bAffectsTranslucentLighting', 180, 'I')]
    uniforms = {name: {'byteOffset': offset, 'value': list(struct.unpack_from('<' + kind, cb1, offset))}
                for name, offset, kind in layout}
    write(out / 'light-uniforms.json', uniforms)
    view_layout = json.loads((evidence / 'view-layout-evidence.json').read_text())
    view_raw = (raw / next(c['file'] for c in ps['constantBuffers'] if c['index'] == 0)).read_bytes()
    view = {}
    for field in view_layout['fields']:
        if field['offset'] + field['bytes'] <= len(view_raw):
            dtype = '<u4' if field['type'].startswith('uint') else '<f4'
            view[field['name']] = {'byteOffset': field['offset'], 'type': field['type'],
                                  'value': np.frombuffer(view_raw, dtype=dtype, count=field['bytes'] // 4,
                                                         offset=field['offset']).tolist()}
    write(out / 'view-uniforms.json', view)
    samples = []
    for name, x, y in [('sphere', 280, 475), ('plane', 600, 550), ('cube', 975, 550),
                       ('floor', 650, 950), ('shadow', 291, 668), ('sky', 650, 150)]:
        samples.append({'name': name, 'xy': [x, y], 'before': pre[y, x].tolist(),
                        'after': post[y, x].tolist(), 'delta': delta[y, x].tolist()})
    dds_dir = out / 'dds'
    dds_dir.mkdir(exist_ok=True)
    before_record = next(r for r in facts['sceneColor'] if r['event'] == facts['previousDrawEvent'])
    by_name = {r['name']: r for r in facts['textureExports']}
    dds_inputs = {}
    for name, record, dxgi, bpp, format_name, role in [
            ('SceneColorBefore', before_record, 10, 8, 'R16G16B16A16_FLOAT', 'Reference fixture destination before direct lighting; contains prior SSGI.'),
            ('ShadowMaskTexture', by_name['ShadowMaskTexture'], 87, 4, 'B8G8R8A8_UNORM', 'Reference shadow-stage input; shader squares sampled RGBA.'),
            ('PreintegratedSkinBRDF', by_name['PreintegratedSkinBRDF'], 91, 4, 'B8G8R8A8_UNORM_SRGB', 'Algorithm LUT, native BGRA8 payload with captured sRGB SRV interpretation.'),
            ('ScreenSpaceAO', by_name['FWhiteTexture'], 28, 4, 'R8G8B8A8_UNORM', 'Reference scene-AO binding; this capture uses a constant white fallback.')]:
        payload = gzip.decompress((raw / record['file']).read_bytes())
        dds_inputs[name] = write_dds(dds_dir / (name + '.dds'), record, payload, dxgi, bpp)
        dds_inputs[name]['formatName'] = format_name
        dds_inputs[name]['role'] = role
    write(out / 'dds-inputs.json', dds_inputs)
    debug_summary = []
    for point in done['debugPixels']:
        x, y = point['pixel']
        states = json.loads((raw / point['stateFile']).read_text())
        variables, shader_output = {}, None
        for state in states:
            for change in state['changes']:
                after = change['after']
                if after['name']:
                    variables[after['name']] = after
                if after['name'] == '_OUT':
                    for member in after['members']:
                        if member['name'] == 'SV_Target':
                            shader_output = member['value']['f32v'][:4]
        if shader_output is None:
            raise RuntimeError('No SV_Target value in completed debug trace')
        predicted = (pre[y, x] + np.asarray(shader_output, dtype=np.float32)).astype('<f2').astype(np.float32)
        debug_summary.append({'pixel': point['pixel'], 'states': len(states), 'shaderOutput': shader_output,
                              'predictedPostAfterHalfRounding': predicted.tolist(), 'actualPost': post[y, x].tolist(),
                              'predictionMinusActual': (predicted - post[y, x]).tolist(),
                              'selectedDXILValues': {name: variables[name]['value']['f32v'][:4]
                                 for name in ('_198', '_212', '_216', '_219', '_224', '_381', '_481') if name in variables},
                              'warning': 'RenderDoc shader interpreter trace is not a GPU numerical oracle.'})
    write(out / 'debug-pixel-summary.json', debug_summary)
    after_hash = sha(capture)
    if before_hash != after_hash:
        raise RuntimeError('Capture content changed during export')
    summary = {'capture': str(capture), 'captureSha256Before': before_hash, 'captureSha256After': after_hash,
               'captureUnchanged': True, 'lightEvent': 2655, 'previousDrawEvent': facts['previousDrawEvent'],
               'ssgiCompositeDraw': 2520, 'ssgiAndPreLightSceneColorByteIdentical':
                   next(r['sha256'] for r in facts['sceneColor'] if r['event'] == 2520) == before_record['sha256'],
               'verifiedRawFiles': verified, 'colorChangedPixels': int(np.any(delta[:, :, :3] != 0, axis=2).sum()),
               'alphaChangedPixels': int(np.count_nonzero(delta[:, :, 3])),
               'deltaRGBMin': delta[:, :, :3].min(axis=(0, 1)).tolist(),
               'deltaRGBMax': delta[:, :, :3].max(axis=(0, 1)).tolist(),
               'samples': samples, 'debugPixels': done['debugPixels'],
               'ddsInputs': dds_inputs, 'debugNumericalCaveats': debug_summary,
               'sceneColorComparisonCaveat': 'RGBA16F blended result: subtraction includes destination rounding; not raw PS output.',
               'viewLayoutEvidence': {'file': str(evidence / 'view-layout-evidence.json'),
                                      'sha256': sha(evidence / 'view-layout-evidence.json')},
               'scriptSha256': {'launcher': sha(Path(__file__)),
                                 'worker': sha(Path(__file__).with_name('_extract_rdc_lighting_replay.py'))}}
    write(out / 'lighting-summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('captureUnchanged', 'previousDrawEvent',
          'ssgiAndPreLightSceneColorByteIdentical', 'colorChangedPixels', 'alphaChangedPixels', 'samples')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=Path(r'E:\rdc\ue\1.rdc'))
    parser.add_argument('--out', type=Path, default=ROOT / 'build/rdc-lighting')
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    parser.add_argument('--renderdoc', type=Path, default=Path(r'C:\Program Files\RenderDoc\qrenderdoc.exe'))
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--debug-pixels', default='[[280,475],[650,950]]')
    args = parser.parse_args()
    capture, out = args.capture.resolve(), args.out.resolve()
    if not out.is_relative_to(ROOT / 'build'):
        raise ValueError('Lighting evidence output must stay within this worktree build directory')
    raw = out / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    before_hash = sha(capture)
    if args.replay:
        for marker in ('replay-error.json', 'replay-done.json'):
            (raw / marker).unlink(missing_ok=True)
        environment = dict(os.environ, UE_RDC_LIGHTING_OUT=str(raw), UE_RDC_LIGHTING_CAPTURE=str(capture),
                           UE_RDC_LIGHTING_POINTS=args.debug_pixels)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        with (out / 'replay-process.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(args.renderdoc), '--python', str(Path(__file__).with_name('_extract_rdc_lighting_replay.py'))],
                           env=environment, startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=420)
    analyze(out, capture, before_hash, args.evidence.resolve())


if __name__ == '__main__':
    main()
