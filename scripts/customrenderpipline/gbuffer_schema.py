"""Generic GBuffer storage contracts, independent of Falcor and material models."""
import copy
import math
import re
import struct

FLOAT32_MAX = float.fromhex('0x1.fffffep+127')
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z', re.ASCII)
RESERVED = set('struct class interface return float float2 float3 float4 uint uint2 uint3 uint4 '
               'int int2 int3 int4 bool void if else for while switch case default in out inout '
               'const static true false namespace import export typedef enum vector matrix '
               'sampler SamplerState Texture2D RWTexture2D discard this sizeof '
               'break continue do let var func generic extension associatedtype property '
               'half half2 half3 half4 double double2 double3 double4 register packoffset '
               'cbuffer tbuffer groupshared shared uniform extern inline volatile precise '
               'row_major column_major nointerpolation noperspective centroid sample '
               'snorm unorm signed unsigned using operator public private protected '
               'new delete try catch throw typealias typename namespace interface '
               'Buffer RWBuffer ByteAddressBuffer RWByteAddressBuffer StructuredBuffer '
               'RWStructuredBuffer AppendStructuredBuffer ConsumeStructuredBuffer '
               'Texture1D Texture3D TextureCube Texture1DArray Texture2DArray TextureCubeArray '
               'RWTexture1D RWTexture3D RWTexture1DArray RWTexture2DArray SamplerComparisonState '
               'InputPatch OutputPatch PointStream LineStream TriangleStream '
               'triangle triangleadj line lineadj point inlinable differentiable __init'.split())
TYPES = {base + (str(n) if n > 1 else ''): (base, n)
         for base in ('float', 'uint', 'int') for n in range(1, 5)}
TYPES['bool'] = ('bool', 1)

# Physical channel sizes; shaders use logical RGBA, even for BGRA formats.
FORMATS = {}
for channels in ('R', 'RG', 'RGBA'):
    for bits in (8, 16, 32):
        for suffix, base in (('Uint', 'uint'), ('Int', 'int')):
            FORMATS[f'{channels}{bits}{suffix}'] = (tuple([bits]*len(channels)), base, False)
    for bits in (16, 32):
        FORMATS[f'{channels}{bits}Float'] = (tuple([bits]*len(channels)), 'float', False)
    for bits in (8, 16):
        FORMATS[f'{channels}{bits}Unorm'] = (tuple([bits]*len(channels)), 'unorm', False)
        FORMATS[f'{channels}{bits}Snorm'] = (tuple([bits]*len(channels)), 'snorm', False)
FORMATS.update({'RGB10A2Unorm': ((10, 10, 10, 2), 'unorm', False),
                'RGBA8UnormSrgb': ((8, 8, 8, 8), 'unorm', True),
                'BGRA8Unorm': ((8, 8, 8, 8), 'unorm', False),
                'BGRA8UnormSrgb': ((8, 8, 8, 8), 'unorm', True),
                'RGB32Float': ((32, 32, 32), 'float', False),
                'RGB32Uint': ((32, 32, 32), 'uint', False),
                'RGB32Int': ((32, 32, 32), 'int', False)})


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_keys(value, required, optional=(), label='schema'):
    require(isinstance(value, dict), f'{label}: expected object')
    require(not (set(value)-set(required)-set(optional)), f'{label}: unknown keys')
    require(set(required) <= set(value), f'{label}: missing required keys')


def identifier(value, label):
    require(isinstance(value, str) and IDENTIFIER.fullmatch(value) and value not in RESERVED
            and not value.startswith('__crp'), f'{label}: invalid identifier/name')


def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high, f'{label}: integer outside [{low}, {high}]')


def named_items(items, label):
    require(isinstance(items, list) and items, f'{label}: expected nonempty array')
    result = {}
    for item in items:
        require(isinstance(item, dict) and 'name' in item, f'{label}: missing name')
        identifier(item['name'], label)
        require(item['name'] not in result, f'{label}: duplicate name {item["name"]}')
        result[item['name']] = item
    return result


def source_path(value):
    require(isinstance(value, str) and value and not any(c in value for c in '\x00\r\n"'),
            'source: expected nonempty path without newline or quote')


def scalar_limits(base, bits):
    if base == 'uint':
        return 0, (1 << bits)-1
    if base == 'int':
        return -(1 << (bits-1)), (1 << (bits-1))-1
    if base == 'unorm':
        return 0.0, 1.0
    if base == 'snorm':
        return -1.0, 1.0
    maximum = 65504.0 if bits == 16 else FLOAT32_MAX
    return -maximum, maximum


def slot_info(schema, slot):
    attachment = next(a for a in schema['attachments'] if a['name'] == slot['attachment'])
    sizes, base, srgb = FORMATS[attachment['format']]
    widths = [sizes['rgba'.index(c)] for c in slot['channels']]
    if 'bits' in slot:
        return {'type': 'uint', 'base': 'uint', 'count': 1, 'width': slot['bits']['width'],
                'limits': (0, (1 << slot['bits']['width'])-1), 'format_base': base}
    limits = [scalar_limits(base, width) for width in widths]
    shader_base = base if base in ('uint', 'int') else 'float'
    count = len(widths)
    return {'type': shader_base+(str(count) if count > 1 else ''), 'base': shader_base,
            'count': count, 'width': min(widths), 'format_base': base,
            'limits': (max(r[0] for r in limits), min(r[1] for r in limits))}


def float_range(bounds, label, quantized=False):
    require(isinstance(bounds, list) and len(bounds) == 2, f'{label}: range needs two numbers')
    require(all(type(v) in (float, int) and math.isfinite(v) and abs(v) <= FLOAT32_MAX for v in bounds),
            f'{label}: range must contain finite float32 numbers')
    low, high = (struct.unpack('f', struct.pack('f', v))[0] for v in bounds)
    require(low < high, f'{label}: range collapses in float32')
    if quantized:
        require(float.fromhex('0x1p-126') <= high-low <= FLOAT32_MAX,
                f'{label}: quantization range span is denormal or overflows float32')


def validate_layout(schema):
    """Return an owned validated description; never rewrite the caller's schema."""
    check_keys(schema, ('version', 'name', 'attachments', 'fields', 'storage', 'codecs'),
               ('producer', 'depthFormat'))
    require(type(schema['version']) is int and schema['version'] == 1, 'schema version must be 1')
    identifier(schema['name'], 'schema name')
    attachments = named_items(schema['attachments'], 'attachments')
    require(1 <= len(attachments) <= 8, 'attachments: require 1 through 8 MRTs')
    for a in attachments.values():
        check_keys(a, ('name', 'format'), label='attachment')
        require(a['name'] != 'depth', 'attachment name depth is reserved')
        require(isinstance(a['format'], str) and a['format'] in FORMATS, 'unsupported attachment format')
    fields = named_items(schema['fields'], 'fields')
    for f in fields.values():
        check_keys(f, ('name', 'type'), label='field')
        require(isinstance(f['type'], str) and f['type'] in TYPES, 'unsupported field type')
    slots = named_items(schema['storage'], 'storage')
    occupied = {}
    for s in slots.values():
        check_keys(s, ('name', 'attachment', 'channels'), ('bits',), 'storage')
        require(isinstance(s['attachment'], str) and s['attachment'] in attachments, 'unknown storage attachment')
        sizes, base, srgb = FORMATS[attachments[s['attachment']]['format']]
        channels = s['channels']
        require(isinstance(channels, str) and 1 <= len(channels) <= 4 and len(set(channels)) == len(channels)
                and all(c in 'rgba'[:len(sizes)] for c in channels), 'invalid storage channel selection')
        if 'bits' in s:
            require(len(channels) == 1, 'bit storage must be scalar')
            require(base in ('uint', 'unorm'), 'bit storage requires uint or linear UNORM')
            require(not srgb or channels == 'a', 'sRGB RGB channels cannot store bit fields')
            check_keys(s['bits'], ('offset', 'width'), label='bits')
            integer(s['bits']['offset'], 0, 31, 'bit offset')
            integer(s['bits']['width'], 1, 32, 'bit width')
            require(s['bits']['offset']+s['bits']['width'] <= sizes['rgba'.index(channels)],
                    'bit range exceeds channel capacity')
        for channel in channels:
            width = sizes['rgba'.index(channel)]
            mask = (((1 << s['bits']['width'])-1) << s['bits']['offset']) if 'bits' in s else (1 << width)-1
            key = (s['attachment'], channel)
            require(not (occupied.get(key, 0) & mask), f'storage overlap at {key[0]}.{key[1]}')
            occupied[key] = occupied.get(key, 0) | mask
    require(isinstance(schema['codecs'], list) and schema['codecs'], 'codecs: expected nonempty array')
    field_owners, slot_owners, custom_names, entries = set(), set(), set(), set()
    for codec in schema['codecs']:
        require(isinstance(codec, dict), 'codec: expected object')
        kind = codec.get('kind')
        require(kind in ('uint', 'sint', 'bool', 'unorm', 'direct', 'custom'), 'unknown codec kind')
        if kind == 'custom':
            check_keys(codec, ('kind', 'name', 'file', 'encode', 'decode', 'fields', 'storage'), label='custom codec')
            identifier(codec['name'], 'custom codec name')
            require(codec['name'] not in custom_names, 'duplicate custom codec name')
            custom_names.add(codec['name'])
            source_path(codec['file'])
            for key in ('encode', 'decode'):
                identifier(codec[key], f'custom {key}')
                require(codec[key] not in entries, 'duplicate custom codec entry')
                entries.add(codec[key])
            owned_fields, owned_slots = codec['fields'], codec['storage']
        else:
            check_keys(codec, ('kind', 'field', 'storage') if kind == 'bool' else
                       ('kind', 'field', 'storage', 'range', 'overflow'), label='codec')
            owned_fields, owned_slots = [codec['field']], [codec['storage']]
        for values, available, owners, label in ((owned_fields, fields, field_owners, 'fields'),
                                                (owned_slots, slots, slot_owners, 'storage')):
            require(isinstance(values, list) and values and all(isinstance(n, str) for n in values),
                    f'codec {label}: expected nonempty names')
            require(len(set(values)) == len(values), f'codec {label}: duplicate name')
            require(set(values) <= set(available), f'codec {label}: unknown name')
            require(not (owners & set(values)), f'codec {label}: already owned')
            owners.update(values)
        if kind == 'custom':
            continue
        field_type = fields[codec['field']]['type']
        info = slot_info(schema, slots[codec['storage']])
        if kind == 'direct':
            require(field_type == info['type'], 'direct codec type mismatch')
        else:
            expected = {'uint': 'uint', 'sint': 'int', 'bool': 'bool', 'unorm': 'float'}[kind]
            require(field_type == expected and info['type'] == 'uint', 'codec requires matching scalar type and uint storage')
        if kind == 'bool':
            continue
        require(codec['overflow'] in ('clamp', 'reject'), 'unknown overflow policy')
        bounds = codec['range']
        if TYPES[field_type][0] == 'float':
            float_range(bounds, 'codec', quantized=kind == 'unorm')
            if kind == 'unorm':
                require(info['width'] <= 24, 'UNORM quantization requires at most 24 bits for float32 precision')
                require((bounds[1]-bounds[0])/((1 << info['width'])-1) >= 2*float.fromhex('0x1p-126'),
                        'quantization half-step is outside the normal float32 range')
        else:
            low, high = scalar_limits('int' if kind == 'sint' else info['base'], info['width'])
            require(isinstance(bounds, list) and len(bounds) == 2 and all(type(v) is int for v in bounds)
                    and low <= bounds[0] <= bounds[1] <= high, 'codec integer range exceeds storage range')
        if kind == 'direct':
            low, high = info['limits']
            require(low <= bounds[0] <= bounds[1] <= high, 'direct range exceeds storage range')
    require(field_owners == set(fields) and slot_owners == set(slots), 'unassigned fields or storage slots')
    if 'depthFormat' in schema:
        require(schema['depthFormat'] in ('D16Unorm', 'D32Float', 'D32FloatS8Uint'), 'unsupported depth format')
    if 'producer' in schema:
        check_keys(schema['producer'], ('file', 'entry'), label='producer')
        source_path(schema['producer']['file'])
        identifier(schema['producer']['entry'], 'producer entry')
        require(schema['producer']['entry'] not in entries, 'producer entry conflicts with custom codec')
    return copy.deepcopy(schema)
