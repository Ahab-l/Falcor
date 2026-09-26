"""Offline raw native-vs-reference diagnostics; never imported by the renderer."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def unpack_depth_stencil(raw, width, height):
    """RenderDoc v1.45 D3D12 D32S8 canonical readback layout, not GPU layout.

    d3d12_replay.cpp's D32S8 merge writes depth uint32 + zero-extended uint8
    stencil per pixel. Audit the installed version separately; exact plane
    parity is a separate claim from interpreting this API's output.
    """
    if len(raw) != width*height*8:
        raise ValueError('D32S8 readback byte count differs')
    data = np.frombuffer(raw, dtype='<u4').reshape(height, width, 2)
    if np.any(data[..., 1] > 255):
        raise ValueError('Stencil word is not zero-extended uint8')
    return data[..., 0].copy().view('<f4'), data[..., 1].astype('u1')


def unpack_normal(raw):
    return np.stack([(raw >> shift) & mask for shift, mask in ((0, 1023), (10, 1023), (20, 1023), (30, 3))], axis=-1)


def metrics(a, b):
    delta = a.astype('f8') - b.astype('f8')
    return dict(values=int(delta.size), different_values=int(np.count_nonzero(delta)),
                max_abs=float(np.max(np.abs(delta))) if delta.size else None,
                mae=float(np.mean(np.abs(delta))) if delta.size else None,
                rmse=float(np.sqrt(np.mean(delta*delta))) if delta.size else None)


def compare_arrays(reference, native, view_rect):
    if set(reference) != set(native) or 'depth' not in reference:
        raise ValueError('Outputs must share the same names and include depth')
    shape = reference['depth'].shape
    if len(shape) != 2:
        raise ValueError('Depth must have shape H,W')
    for name in reference:
        a, b = reference[name], native[name]
        if a.shape != b.shape or a.shape[:2] != shape or not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError('Nonfinite data or mismatched shape: '+name)
    if len(view_rect) != 4 or any(type(x) is not int for x in view_rect):
        raise ValueError('View rectangle must contain four integers')
    x, y, width, height = view_rect
    if min(x, y) < 0 or min(width, height) <= 0 or x+width > shape[1] or y+height > shape[0]:
        raise ValueError('View rectangle outside data')
    visible = np.zeros(shape, dtype=bool)
    visible[y:y+height, x:x+width] = True
    refmask, native_mask = reference['depth'] > 0, native['depth'] > 0
    common = visible & refmask & native_mask
    result = {'coverage': {'reference': int(np.count_nonzero(visible & refmask)),
                           'native': int(np.count_nonzero(visible & native_mask)),
                           'intersection': int(np.count_nonzero(common)),
                           'reference_only': int(np.count_nonzero(visible & refmask & ~native_mask)),
                           'native_only': int(np.count_nonzero(visible & native_mask & ~refmask))},
              'view_rect': view_rect, 'full_renderer_parity': False}
    for label, mask in [('visible', visible), ('padding', ~visible), ('opaque_intersection', common)]:
        result[label] = {name: metrics(reference[name][mask], native[name][mask]) for name in reference}
    result['all_visible_values_equal'] = all(value['different_values'] == 0 for value in result['visible'].values())
    return result


def _checked(path, size, digest):
    data = path.read_bytes()
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Changed artifact: '+str(path))
    return data


def validate_native_output(entry):
    formats = {'sceneColor': 'RGBA16Float', 'gbufferA': 'RGB10A2Unorm', 'gbufferB': 'BGRA8Unorm',
               'gbufferC': 'BGRA8UnormSrgb', 'gbufferD': 'BGRA8Unorm', 'depth': 'float32', 'stencil': 'uint8'}
    name = entry['name']
    if name not in formats or entry.get('format') != formats[name]:
        raise ValueError('Native output format differs: '+name)
    if name not in ('depth', 'stencil'):
        dtype, shape = ('float16', [1040, 1424, 4]) if name == 'sceneColor' else ('uint8', [5923840])
        if entry.get('dtype') != dtype or entry.get('shape') != shape:
            raise ValueError('Native raw storage dtype/shape differs: '+name)


def load_pair(reference_path, native_path):
    """Read independently emitted manifests; pin expected output names/formats."""
    reference_path, native_path = Path(reference_path).resolve(), Path(native_path).resolve()
    reference, native = json.loads(reference_path.read_text()), json.loads(native_path.read_text())
    if reference.get('schema') != 'crp-rdc-gbuffer-reference-v1' or reference.get('role') != 'offline_reference_only' or reference.get('event') != 1452:
        raise ValueError('Not the E1452 reference contract')
    if reference.get('capture', {}).get('sha256') != '059eef7978d1c32039ad4bd21b5b0c59574c393996fb842b37f3a9e4a87edb2f':
        raise ValueError('Wrong targetmap capture identity')
    if native.get('status') != 'rendered_not_parity' or native.get('capture_inputs') is not False or native.get('allocation') != [1424, 1040]:
        raise ValueError('Not a successful independent native run')
    expected = {'SceneColor': ('sceneColor', 'R16G16B16A16_FLOAT', '<f2', 4),
                'GBufferA': ('gbufferA', 'R10G10B10A2_UNORM', '<u4', 1),
                'GBufferB': ('gbufferB', 'B8G8R8A8_UNORM', 'u1', 4),
                'GBufferC': ('gbufferC', 'B8G8R8A8_SRGB', 'u1', 4),
                'GBufferD': ('gbufferD', 'B8G8R8A8_UNORM', 'u1', 4)}
    arrays = {}
    if len(reference['snapshots']) != 6 or len({s['name'] for s in reference['snapshots']}) != 6:
        raise ValueError('Expected six unique reference resources')
    for entry in reference['snapshots']:
        if [entry['width'], entry['height']] != [1424, 1040] or entry['view_rect'] != native['view_rect']:
            raise ValueError('Mismatched view/extent')
        file = (reference_path.parent/entry['file']).resolve()
        if file.parent != reference_path.parent:
            raise ValueError('Reference path escaped its directory')
        raw = _checked(file, entry['byte_size'], entry['sha256'])
        if entry['name'] == 'SceneDepthZ':
            if entry['format'] != 'D32S8':
                raise ValueError('Wrong depth format')
            arrays['depth'], arrays['stencil'] = unpack_depth_stencil(raw, 1424, 1040)
            continue
        name, fmt, dtype, channels = expected[entry['name']]
        if fmt != entry['format']:
            raise ValueError('Wrong reference format')
        arrays[name] = np.frombuffer(raw, dtype=dtype).reshape((1040, 1424, channels) if channels > 1 else (1040, 1424))
    actual = {}
    for entry in native['outputs']:
        validate_native_output(entry)
        name = entry['name']
        if name not in arrays or name in actual:
            raise ValueError('Unexpected or duplicated native output')
        file = Path(entry['path']).resolve()
        if file.parent != native_path.parent:
            raise ValueError('Native path escaped its directory')
        raw = _checked(file, entry['bytes'], entry['sha256'])
        actual[name] = np.frombuffer(raw, dtype=arrays[name].dtype).reshape(arrays[name].shape)
    if set(actual) != set(arrays):
        raise ValueError('Missing native output')
    arrays['gbufferA'], actual['gbufferA'] = unpack_normal(arrays['gbufferA']), unpack_normal(actual['gbufferA'])
    return arrays, actual, native['view_rect']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('native', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.out:
        output = args.out.resolve()
        for path in (args.reference, args.native):
            if output.is_relative_to(path.resolve().parent):
                raise ValueError('Comparison output may not modify an input run')
    reference, native, rect = load_pair(args.reference, args.native)
    result = compare_arrays(reference, native, rect)
    result.update(reference=str(args.reference.resolve()), native=str(args.native.resolve()),
                  reference_sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),
                  native_sha256=hashlib.sha256(args.native.read_bytes()).hexdigest(),
                  depth_encoding='RenderDoc-v1.45-D3D12-D32S8-canonical', plane_parity_verified=False)
    text = json.dumps(result, indent=2, allow_nan=False)+'\n'
    if args.out:
        with args.out.open('x', encoding='utf-8') as stream:
            stream.write(text)
    print(text)


if __name__ == '__main__':
    main()
