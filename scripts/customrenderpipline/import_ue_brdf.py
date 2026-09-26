"""Check or extract pinned, unmodified UE BRDF source ranges for the PC Codec.

Example: python import_ue_brdf.py --engine-root E:/ue/engine/UnrealEngine
Use --extract to refresh the two imported source files from that pinned engine.
The adapter and algorithm bodies are never rewritten by this tool.
"""
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'Source/RenderPasses/customrenderpipline/Codecs/Lighting'
SOURCES = (
    ('BRDF.ush', '0de81cc25c9b035a77aeb0e2f1be3e730c0f117f9250fe365104f30119b5e906',
     0, 4506, 'UEBRDF.prefix.ush', '7ddeb1bc1a0c143f754ef7019c11ba5af0250f6ad8b7161e34ee0f9e294510f7'),
    ('Common.ush', '11184bf6e39a0065e66acd174e2b8407c89791a184a2ad9552a1f1d83669c84b',
     33108, 33148, 'UEPow2.scalar.ush', '1fecb8d3b05f05cb732464d87fadcd672ffc5f6adc483e86bb710f6366f1e996'),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-root', type=Path, help='Optional check against the original pinned UE files')
    parser.add_argument('--extract', action='store_true', help='Write exact source byte ranges; requires --engine-root')
    args = parser.parse_args()
    if args.extract and args.engine_root is None:
        parser.error('--extract requires --engine-root')
    extracted = []
    for source, full_hash, begin, end, output, span_hash in SOURCES:
        target = DEST / output
        if args.engine_root is not None:
            original = (args.engine_root / 'Engine/Shaders/Private' / source).read_bytes()
            if digest(original) != full_hash:
                raise ValueError('UE source baseline changed: ' + source)
            content = original[begin:end]
            if digest(content) != span_hash:
                raise ValueError('Source byte span changed: ' + source)
            extracted.append((target, content))
        if not args.extract and digest(target.read_bytes()) != span_hash:
            raise ValueError('Imported source changed: ' + output)
    # Validate every source before writing any output.
    if args.extract:
        for target, content in extracted:
            target.write_bytes(content)
    print('UE_BRDF_ORIGINAL_SOURCE_VERIFIED: 2 exact byte ranges')


if __name__ == '__main__':
    main()
