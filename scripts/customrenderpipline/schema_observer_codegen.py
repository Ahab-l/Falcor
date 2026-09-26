"""Verified generated contracts and typed GPU observation; no Falcor import."""
import hashlib
import json
from pathlib import Path
import numpy as np
from generate_native_gbuffer import Artifacts, GENERATOR_VERSION, canonical, unique_keys
from gbuffer_schema import validate_layout, slot_info, TYPES, FORMATS
from gbuffer_codegen import emit_codec, emit_raster, packed_type, member, literal

MAX_PIXELS = 1024 * 1024
MAX_BYTES = 128 * 1024 * 1024


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique_keys)


def load_contract(artifacts):
    """Reject stale/edited generated files and directly declared shader sources."""
    if not isinstance(artifacts, Artifacts):
        manifest_path = Path(artifacts).resolve()
        manifest = _json(manifest_path)
        artifacts = Artifacts(Path(manifest['codec']), Path(manifest['metadata']),
                              Path(manifest['definition']) if manifest['definition'] else None, manifest_path)
    manifest = _json(artifacts.manifest)
    for name in ('codec', 'metadata', 'definition'):
        supplied = getattr(artifacts, name)
        declared = manifest[name]
        if (supplied is None) != (declared is None) or (supplied is not None and supplied.resolve() != Path(declared).resolve()):
            raise ValueError('Generated manifest/contract mismatch: '+name)
    metadata = _json(artifacts.metadata)
    schema = validate_layout(metadata['schema'])
    if (artifacts.definition is not None) != ('producer' in schema):
        raise ValueError('Generated definition must exist exactly when Schema has a producer')
    if metadata['generator_version'] != GENERATOR_VERSION:
        raise ValueError('Unsupported metadata generator version')
    sources = {}
    entries = [c for c in schema['codecs'] if c['kind'] == 'custom']
    if 'producer' in schema:
        entries += [schema['producer']]
    if set(metadata['sources']) != {c['file'] for c in entries}:
        raise ValueError('Metadata source mismatch')
    for file, info in metadata['sources'].items():
        path = Path(info['path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError('Shader source changed; regenerate and rebind: '+str(path))
        sources[file] = path
    hashes = {c['file']: metadata['sources'][c['file']]['sha256'] for c in schema['codecs'] if c['kind'] == 'custom'}
    layout_hash = hashlib.sha256(canonical({'generator_version': GENERATOR_VERSION, 'schema': schema,
                                           'custom_sources': hashes}).encode()).hexdigest()
    if metadata['layout_hash'] != layout_hash or manifest['layout_hash'] != layout_hash:
        raise ValueError('Layout hash mismatch')
    if canonical(metadata['storage_info']) != canonical({s['name']: slot_info(schema, s) for s in schema['storage']}):
        raise ValueError('Metadata storage mismatch')
    files = {'Codec.slangh': emit_codec(schema, layout_hash, sources), 'Metadata.json': canonical(metadata)+'\n'}
    if 'producer' in schema:
        if artifacts.definition is None:
            raise ValueError('Missing native producer definition')
        files.update({'GBuffer.3d.slang': emit_raster(schema, sources[schema['producer']['file']]),
                      'Layout.json': canonical({'shader': 'GBuffer.3d.slang', 'attachments': schema['attachments'],
                                                'depthFormat': schema.get('depthFormat', 'D32Float')})+'\n'})
    directory = artifacts.codec.parent
    if artifacts.codec.resolve() != (directory/'Codec.slangh').resolve():
        raise ValueError('Codec path mismatch')
    for name, expected in files.items():
        path = directory/name
        if not path.is_file() or path.read_text(encoding='utf-8') != expected:
            raise ValueError('Generated file modified/mismatch: '+str(path))
    if artifacts.metadata.resolve() != (directory/'Metadata.json').resolve():
        raise ValueError('Metadata directory mismatch')
    if artifacts.definition and artifacts.definition.resolve() != (directory/'Layout.json').resolve():
        raise ValueError('Definition directory mismatch')
    if hashlib.sha256(canonical(files).encode()).hexdigest() != manifest['content_hash']:
        raise ValueError('Generated content hash mismatch')
    return {**metadata, 'artifacts': artifacts}


def validate_region(region, width, height):
    if not isinstance(region, (list, tuple)) or len(region) != 4 or any(type(v) is not int for v in region):
        raise ValueError('region must be four integers: x y width height')
    x, y, w, h = region
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
        raise ValueError('region lies outside the output or is empty')
    if w*h > MAX_PIXELS:
        raise ValueError('region exceeds observation pixel limit')
    return tuple(region)


def emit_observer(contract):
    schema, artifacts = contract['schema'], contract['artifacts']
    name = schema['name']
    columns = {group: {} for group in ('fields', 'storage', 'attachments')}
    stores = []
    stride = 0

    def add(group, key, base, count, expression):
        nonlocal stride
        dtype = {'float': 'float32', 'uint': 'uint32', 'int': 'int32', 'bool': 'bool'}[base]
        columns[group][key] = {'offset': stride, 'channels': count, 'dtype': dtype}
        for lane in range(count):
            value = expression+('.'+'xyzw'[lane] if count > 1 else '')
            encoded = f'({value} ? 1u : 0u)' if base == 'bool' else value if base == 'uint' else f'asuint({value})'
            stores.append(f'    gWords[i * STRIDE + {stride}u] = {encoded};')
            stride += 1

    lines = [f'#include "{artifacts.codec.resolve().as_posix()}"', 'RWStructuredBuffer<uint> gWords;', 'uint4 gRegion;']
    for i, a in enumerate(schema['attachments']):
        lines.append(f'Texture2D<{packed_type(a)}> gAttachment{i};')
    body = [f'    {name}Packed packed;']
    for i, a in enumerate(schema['attachments']):
        body.append(f'    packed.{a["name"]} = gAttachment{i}.Load(int3(pixel, 0));')
    body.append(f'    {name}Fields value = {name}Decode(packed);')
    for f in schema['fields']:
        base, count = TYPES[f['type']]
        add('fields', f['name'], base, count, 'value.'+f['name'])
    for a in schema['attachments']:
        sizes, base, _ = FORMATS[a['format']]
        add('attachments', a['name'], base if base in ('uint', 'int') else 'float', len(sizes), 'packed.'+a['name'])
    for index, slot in enumerate(schema['storage']):
        info = slot_info(schema, slot)
        expression = member(schema, slot)
        if 'bits' in slot:
            a = next(a for a in schema['attachments'] if a['name'] == slot['attachment'])
            sizes, base, _ = FORMATS[a['format']]
            if base == 'unorm':
                expression = f'uint(round(saturate({expression}) * {literal((1 << sizes["rgba".index(slot["channels"])])-1, "float")}))'
            expression = f'(({expression} >> {slot["bits"]["offset"]}) & {literal((1 << slot["bits"]["width"])-1, "uint")})'
        variable = f'slot{index}'
        body.append(f'    {info["type"]} {variable} = {expression};')
        base, count = TYPES[info['type']]
        add('storage', slot['name'], base, count, variable)
    lines += [f'static const uint STRIDE = {stride}u;', '[numthreads(64,1,1)] void main(uint3 tid: SV_DispatchThreadID)',
              '{', '    uint i = tid.x;', '    if (i >= gRegion.z * gRegion.w) return;',
              '    uint2 pixel = gRegion.xy + uint2(i % gRegion.z, i / gRegion.z);']
    return '\n'.join(lines+body+stores+['}', '']), columns, stride


def unpack_words(words, columns):
    result = {}
    for group, entries in columns.items():
        result[group] = {}
        for name, info in entries.items():
            array = np.ascontiguousarray(words[..., info['offset']:info['offset']+info['channels']])
            array = array.astype(bool) if info['dtype'] == 'bool' else array.view(info['dtype'])
            result[group][name] = array[..., 0] if info['channels'] == 1 else array
    return result
