"""Validate and wrap source-built targetmap BC1 mip bytes; no RenderDoc imports."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


OBJECT = '/Engine/OpenWorldTemplate/LandscapeMaterial/T_GridChecker_A.T_GridChecker_A'


def validate_export(metadata, payload):
    if (metadata.get('status') != 'passed' or metadata.get('capture_inputs') is not False or
        metadata.get('source_object') != OBJECT or metadata.get('format') != 'BC1UnormSrgb' or
        metadata.get('srgb') is not True or metadata.get('width') != 512 or metadata.get('height') != 512):
        raise ValueError('Not a successful source-built targetmap BC1 sRGB export')
    mips = metadata.get('mips', [])
    if len(mips) != 10:
        raise ValueError('Expected all 10 source platform mips')
    offset = 0
    for level, mip in enumerate(mips):
        size = max(1, 512 >> level)
        count = max(1, (size+3)//4)**2*8
        if any(type(mip.get(key)) is not int or mip[key] != value for key, value in
               dict(level=level, width=size, height=size, bytes=count, offset=offset).items()):
            raise ValueError('Invalid BC1 mip extent/offset/length')
        offset += count
    if len(payload) != offset:
        raise ValueError('Platform payload has missing or extra bytes')


def make_dds(metadata, payload):
    validate_export(metadata, payload)
    header = [124, 0xA1007, 512, 512, 131072, 0, 10] + [0]*11
    header += [32, 4, int.from_bytes(b'DX10', 'little'), 0, 0, 0, 0, 0]
    header += [0x401008, 0, 0, 0, 0]
    return b'DDS '+struct.pack('<31I', *header)+struct.pack('<5I', 72, 3, 0, 1, 0)+payload


def load_verified_export(run):
    """Load a source-export receipt, never a RenderDoc texture. Recheck all bytes."""
    run = Path(run).resolve()
    identities = []
    def read(path, expected=None):
        path = Path(path).resolve()
        data = path.read_bytes()
        entry = dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        if expected is not None and entry != expected:
            raise ValueError('Source export identity mismatch: '+str(path))
        identities.append(entry)
        return data
    result = json.loads(read(run/'source-platform-result.json'))
    plan = json.loads(read(run/'prepared.json'))
    if (result.get('status') != 'passed' or result.get('capture_inputs') is not False or
        result.get('original_project_launched') is not False or result.get('protected_unchanged') is not True or
        plan.get('capture_inputs') is not False or plan.get('original_project_launched') is not False or
        not result.get('protected') or result['protected'] != plan.get('protected') or
        not result.get('receipts') or any(r.get('exit_code') != 0 for r in result['receipts'])):
        raise ValueError('Expected verified successful source platform export')
    protection = Path(result['protection_report']).resolve()
    if protection.parent != run:
        raise ValueError('Protection report escaped source run')
    if json.loads(read(protection)) != {'unchanged':True, 'files':result['protected']}:
        raise ValueError('Source protection report disagrees')
    for entry in result['protected']:
        read(entry['path'], entry)
    blobs = {}
    for name, filename in [('metadata','result.json'), ('payload','platform-mips.bin'), ('texture','T_GridChecker_A.bc1.srgb.dds')]:
        path = run/'Export'/filename
        if Path(result[name]['path']).resolve() != path:
            raise ValueError('Export path escaped its owned source directory')
        blobs[name] = read(path, result[name])
    metadata = json.loads(blobs['metadata'])
    if make_dds(metadata, blobs['payload']) != blobs['texture']:
        raise ValueError('DDS does not preserve the source platform payload')
    return dict(capture_inputs=False, file=result['texture']['path'], format='BC1UnormSrgb',
                size=[512,512], mip_count=10, srgb=True), identities


def native_options(root, environ):
    text = environ.get('CRP_TARGETMAP_GRID_ANISOTROPY', '1')
    if text not in {str(i) for i in range(1, 17)}:
        raise ValueError('Grid anisotropy must be integer text 1..16')
    requested = environ.get('CRP_TARGETMAP_SOURCE_PLATFORM_RUN')
    if requested is None:
        return None, int(text), []
    run = Path(requested).resolve()
    if run.parent != (Path(root)/'build/source-platform-texture').resolve():
        raise ValueError('Source platform run must be a direct child of build/source-platform-texture')
    texture, identities = load_verified_export(run)
    return texture, int(text), identities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('metadata', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text(encoding='utf-8-sig'))
    path = (args.metadata.parent/metadata['payload']).resolve()
    if path.parent != args.metadata.resolve().parent:
        raise ValueError('Source payload must remain inside the exporter output')
    if args.out.resolve() in (args.metadata.resolve(), path):
        raise ValueError('DDS output must not overwrite source evidence')
    data = make_dds(metadata, path.read_bytes())
    with args.out.open('xb') as stream:
        stream.write(data)
    print(json.dumps(dict(path=str(args.out.resolve()), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), capture_inputs=False)))


if __name__ == '__main__':
    main()
