"""Verify or extract original UE Lighting source using pinned byte ranges.

Use --engine-root E:/ue/engine/UnrealEngine to authenticate original source.
Add --extract to copy all source excerpts after validating every input. The
compatibility headers are maintained separately; this tool never rewrites math.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'Source/RenderPasses/customrenderpipline/Codecs/Lighting'
CATALOG = Path(__file__).with_name('ue_lighting_sources.json')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collect_outputs(catalog, engine_root):
    """Authenticate the complete extraction before the caller writes any file."""
    engine_shaders = (Path(engine_root) / 'Engine/Shaders').resolve()
    sources, outputs = {}, {}
    for name, item in catalog['outputs'].items():
        if Path(name).name != name or not name.endswith('.ush'):
            raise ValueError('Invalid output filename: ' + name)
        spans = []
        offset = 0
        for segment in item['segments']:
            source = segment['source']
            path = (engine_shaders / source).resolve()
            if not path.is_relative_to(engine_shaders):
                raise ValueError('Source path escapes Engine/Shaders')
            if source not in sources:
                sources[source] = path.read_bytes()
            original = sources[source]
            if digest(original) != segment['source_sha256']:
                raise ValueError('UE source baseline changed: ' + source)
            begin, end = segment['input_start'], segment['input_end']
            if not 0 <= begin < end <= len(original):
                raise ValueError('Invalid source range: ' + source)
            data = original[begin:end]
            if (len(data) != segment['bytes'] or digest(data) != segment['sha256']
                    or segment['output_start'] != offset or segment['output_end'] != offset + len(data)):
                raise ValueError('Source segment or contiguous output range changed: ' + name)
            spans.append(data)
            offset += len(data)
        outputs[name] = b''.join(spans)
        if len(outputs[name]) != item['bytes'] or digest(outputs[name]) != item['sha256']:
            raise ValueError('Extracted output identity changed: ' + name)
    return outputs


def verify_installed(catalog, destination=DEST):
    for name, item in catalog['outputs'].items():
        data = (destination / name).read_bytes()
        if len(data) != item['bytes'] or digest(data) != item['sha256']:
            raise ValueError('Imported UE source changed: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-root', type=Path)
    parser.add_argument('--extract', action='store_true')
    args = parser.parse_args()
    if args.extract and args.engine_root is None:
        parser.error('--extract requires --engine-root')
    catalog = json.loads(CATALOG.read_bytes())
    if args.engine_root is not None:
        outputs = collect_outputs(catalog, args.engine_root)
        if args.extract:
            for name, data in outputs.items():
                (DEST / name).write_bytes(data)
    verify_installed(catalog)
    print('UE_LIGHTING_ORIGINAL_SOURCE_VERIFIED: {} files, {} exact source segments'.format(
        len(catalog['outputs']), sum(len(item['segments']) for item in catalog['outputs'].values())))


if __name__ == '__main__':
    main()
