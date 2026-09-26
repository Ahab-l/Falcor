"""Compare verified source-built BC1 mips to offline E1452 t5 raw block oracle.

No decoding, output textures, capture-based material inputs, or renderer state.
Exit 0: byte-equal; exit 2: verified inputs differ; exit 1: invalid evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import _targetmap_texture_replay as reference
from source_platform_texture import load_verified_export


ROOT = Path(__file__).resolve().parents[2]


def compare_payloads(source, oracle):
    if len(source) != reference.RAW_BYTES or len(oracle) != reference.RAW_BYTES:
        raise ValueError('Both BC1 mip chains must contain exactly 174776 raw bytes')
    mips, total = [], 0
    for plan in reference.mip_layout():
        begin, size = plan['offset'], plan['byte_size']
        a, b = source[begin:begin + size], oracle[begin:begin + size]
        count, first = 0, None
        for offset, (x, y) in enumerate(zip(a, b)):
            if x == y:
                continue
            count += 1
            if first is None:
                block = offset // 8
                first = dict(mip_offset=offset, payload_offset=begin + offset, block_index=block,
                    block_x=block % plan['blocks_x'], block_y=block // plan['blocks_x'], byte_in_block=offset % 8,
                    source_byte=x, reference_byte=y)
        mips.append(dict(plan, byte_equal=count == 0, differing_bytes=count, first_difference=first,
            source_sha256=hashlib.sha256(a).hexdigest(), reference_sha256=hashlib.sha256(b).hexdigest()))
        total += count
    return dict(status='equal' if total == 0 else 'different', all_mips_equal=total == 0,
        differing_bytes=total, mips=mips, raw_bytes=reference.RAW_BYTES, full_renderer_parity=False,
        role='offline_comparison_only', scope='Exact source-built BC1 block bytes vs read-only capture oracle; not shading parity.')


def load_source(run):
    asset, identities = load_verified_export(run)
    path = Path(run).resolve() / 'Export/platform-mips.bin'
    expected = [entry for entry in identities if Path(entry['path']).resolve() == path]
    if len(expected) != 1 or asset.get('capture_inputs') is not False:
        raise ValueError('Source receipt does not identify one non-capture platform payload')
    raw = reference.read_bounded(path, reference.RAW_BYTES)
    actual = dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if actual != expected[0]:
        raise ValueError('Source platform payload changed after receipt verification')
    return raw, identities


def load_reference(run):
    run = Path(run).resolve()
    result_raw = reference.read_bounded(run / 'result.json', reference.RESULT_RESERVE)
    result = json.loads(result_raw.decode('utf-8'))
    if (result.get('status') != 'passed' or result.get('role') != reference.ROLE or
        result.get('full_renderer_parity') is not False or result.get('errors') != [] or result.get('capture') != reference.CAPTURE or
        result.get('sha256_before') != reference.CAPTURE_SHA256 or result.get('sha256_after') != reference.CAPTURE_SHA256 or
        result.get('capture_unchanged') is not True or result.get('controller_shutdown') is not True or
        result.get('capture_shutdown') is not True or result.get('manifest') != 'reference/manifest.json' or
        result.get('raw_bytes') != reference.RAW_BYTES or result.get('mip_count') != 10 or result.get('resource') != reference.RESOURCE):
        raise ValueError('Not a successful closed read-only texture reference receipt')
    directory = run / 'reference'
    manifest_raw = reference.read_bounded(directory / 'manifest.json', reference.MAX_BYTES)
    if hashlib.sha256(manifest_raw).hexdigest() != result.get('manifest_sha256'):
        raise ValueError('Reference manifest SHA256 mismatch')
    manifest = json.loads(manifest_raw.decode('utf-8'))
    expected = dict(schema='crp-rdc-texture-reference-v1', role=reference.ROLE, full_renderer_parity=False,
        capture=dict(path=reference.CAPTURE, sha256=reference.CAPTURE_SHA256), event=1452, resource=reference.RESOURCE,
        binding=dict(stage='Pixel', index=5, register='t5', space=0), resource_format='BC1_TYPELESS', view_format='BC1_SRGB',
        raw_bytes=reference.RAW_BYTES, raw_readback_encoding=reference.ENCODING, readback_length_verified=True)
    reference._fields(manifest, expected, 'reference manifest')
    reference._fields(manifest.get('texture', {}), dict(width=512, height=512, depth=1, arraysize=1,
        mips=10, format='BC1_TYPELESS', samples=1, dimension=2), 'reference texture')
    records, payloads, total = {}, {}, len(result_raw) + len(manifest_raw)
    for record in manifest.get('files', []):
        name = record['file']
        if not name or name in records or any(c in name for c in '/\\:') or name in ('.', '..'):
            raise ValueError('Duplicate or unsafe reference artifact filename')
        count = record.get('byte_size')
        if type(count) is not int or count < 0 or total + count > reference.MAX_BYTES:
            raise ValueError('Reference evidence exceeds bounded size')
        path = directory / name
        if path.resolve().parent != directory.resolve():
            raise ValueError('Reference artifact escaped its directory')
        raw = reference.read_bounded(path, count)
        if len(raw) != count or hashlib.sha256(raw).hexdigest() != record.get('sha256'):
            raise ValueError('Reference artifact length/SHA256 mismatch: ' + name)
        if record.get('role') != reference.ROLE or record.get('full_renderer_parity') is not False:
            raise ValueError('Reference artifact is not offline-only')
        records[name], payloads[name] = record, raw
        total += count
    plans = reference.mip_layout()
    if len(manifest.get('mips', [])) != len(plans):
        raise ValueError('Reference must contain all ten raw mips')
    selected = []
    for plan, mip in zip(plans, manifest['mips']):
        reference._fields(mip, plan, 'reference mip')
        name = 'E1452-t5-3905-mip{:02d}.bc1.raw'.format(plan['mip'])
        if mip.get('file') != name or name not in records:
            raise ValueError('Reference mip filename mismatch')
        for key in ('file', 'byte_size', 'sha256', 'role', 'full_renderer_parity'):
            if mip.get(key) != records[name].get(key):
                raise ValueError('Reference mip and file manifest disagree')
        if mip.get('readback_length_verified') is not True or mip.get('raw_readback_encoding') != reference.ENCODING:
            raise ValueError('Reference mip BC1 encoding not verified')
        selected.append(payloads[name])
    identities = [dict(path=str(run / 'result.json'), bytes=len(result_raw), sha256=hashlib.sha256(result_raw).hexdigest()),
                  dict(path=str(directory / 'manifest.json'), bytes=len(manifest_raw), sha256=hashlib.sha256(manifest_raw).hexdigest())]
    identities.extend(dict(path=str(directory / name), bytes=record['byte_size'], sha256=record['sha256'])
                      for name, record in records.items())
    return b''.join(selected), identities


def compare_runs(root, source_run, reference_run):
    root = Path(root).resolve()
    source_run = Path(source_run).resolve()
    if source_run.parent != (root / 'build/source-platform-texture').resolve():
        raise ValueError('Source must be a direct child of build/source-platform-texture, never a capture reference')
    reference_run = reference.require_child(root / 'build/targetmap-shading-a1', reference_run)
    source, source_files = load_source(source_run)
    oracle, reference_files = load_reference(reference_run)
    result = compare_payloads(source, oracle)
    result.update(source_run=str(source_run), reference_run=str(reference_run), source_capture_inputs=False,
                  source_identities=source_files, reference_identities=reference_files)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, required=True)
    parser.add_argument('--reference-run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    # A fresh JSON-only audit report cannot overwrite any input or appear inside
    # either input run. The tool never emits texture bytes or native asset options.
    out = reference.require_child(ROOT / 'build/targetmap-shading-a1', args.out)
    for run in (args.source_run.resolve(), args.reference_run.resolve()):
        if out == run or run in out.parents:
            raise ValueError('Comparison report must stay outside both input runs')
    if out.suffix.lower() != '.json' or out.exists():
        raise ValueError('Comparison output must be a fresh JSON file')
    try:
        result = compare_runs(ROOT, args.source_run, args.reference_run)
        code = 0 if result['all_mips_equal'] else 2
    except Exception as error:
        result = dict(status='failed', error=str(error), role='offline_comparison_only', full_renderer_parity=False)
        code = 1
    payload = (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(payload) > reference.RESULT_RESERVE:
        raise ValueError('Comparison report exceeds 64 KiB bound')
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as stream:
        stream.write(payload)
    print(json.dumps(dict(status=result['status'], output=str(out))))
    return code


if __name__ == '__main__':
    sys.exit(main())
