"""Offline generic GBuffer generator; output plugs into the native JSON/Slang Pass."""
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile

from gbuffer_schema import validate_layout, slot_info
from gbuffer_codegen import emit_codec, emit_raster

GENERATOR_VERSION = 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: '+key)
        result[key] = value
    return result


@dataclass(frozen=True)
class Artifacts:
    codec: Path
    metadata: Path
    definition: Path | None
    manifest: Path


def atomic_write(path, data):
    """Publish one generated file only after its complete contents are written."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.generate-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def generate(schema_path, output_dir):
    schema_path, output_dir = Path(schema_path).resolve(), Path(output_dir).resolve()
    schema = validate_layout(json.loads(schema_path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_keys))
    sources = {}
    for entry in ([c for c in schema['codecs'] if c['kind'] == 'custom'] +
                  ([schema['producer']] if 'producer' in schema else [])):
        source = (schema_path.parent/entry['file']).resolve()
        if not source.is_file():
            raise ValueError('missing Shader source: '+str(source))
        if any(c in str(source) for c in '\r\n"'):
            raise ValueError('Shader source path contains a quote or newline')
        sources[entry['file']] = source
    source_info = {key: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                   for key, path in sources.items()}
    codec_hashes = {c['file']: source_info[c['file']]['sha256'] for c in schema['codecs'] if c['kind'] == 'custom'}
    layout_hash = hashlib.sha256(canonical({'generator_version': GENERATOR_VERSION, 'schema': schema,
                                           'custom_sources': codec_hashes}).encode()).hexdigest()
    metadata = {'generator_version': GENERATOR_VERSION, 'layout_hash': layout_hash, 'schema': schema,
                'storage_info': {s['name']: slot_info(schema, s) for s in schema['storage']},
                'sources': source_info}
    files = {'Codec.slangh': emit_codec(schema, layout_hash, sources), 'Metadata.json': canonical(metadata)+'\n'}
    if 'producer' in schema:
        files['GBuffer.3d.slang'] = emit_raster(schema, sources[schema['producer']['file']])
        files['Layout.json'] = canonical({'shader': 'GBuffer.3d.slang', 'attachments': schema['attachments'],
                                         'depthFormat': schema.get('depthFormat', 'D32Float')})+'\n'
    content_hash = hashlib.sha256(canonical(files).encode()).hexdigest()
    directory = output_dir/content_hash[:24]
    # Validation and source reads happen before touching any published output.
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        path, data = directory/name, text.encode('utf-8')
        if path.exists() and path.read_bytes() != data:
            raise ValueError('generated artifact was modified: '+str(path))
        if not path.exists():
            atomic_write(path, data)
    result = Artifacts(directory/'Codec.slangh', directory/'Metadata.json',
                       directory/'Layout.json' if 'producer' in schema else None, output_dir/'manifest.json')
    manifest = {'layout_hash': layout_hash, 'content_hash': content_hash,
                'codec': str(result.codec), 'metadata': str(result.metadata),
                'definition': str(result.definition) if result.definition else None}
    atomic_write(result.manifest, (canonical(manifest)+'\n').encode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('schema', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.schema, args.output)
    print(result.manifest.read_text().strip())


if __name__ == '__main__':
    main()
