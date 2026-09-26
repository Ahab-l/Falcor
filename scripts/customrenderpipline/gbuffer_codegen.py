"""Slang emission for a validated generic storage layout."""
from gbuffer_schema import FORMATS, TYPES, slot_info


def literal(value, base):
    if base == 'float':
        text = format(float(value), '.17g')
        return text + ('.0' if '.' not in text and 'e' not in text else '') + 'f'
    if base == 'uint':
        return str(value)+'u'
    return '(-2147483647 - 1)' if value == -(2**31) else str(value)


def emit_struct(name, members):
    return ['struct '+name, '{'] + ['    '+line+';' for line in members] + ['};', '']


def packed_type(attachment):
    sizes, base, _ = FORMATS[attachment['format']]
    base = base if base in ('uint', 'int') else 'float'
    return base+(str(len(sizes)) if len(sizes) > 1 else '')


def member(schema, slot, variable='packed'):
    a = next(a for a in schema['attachments'] if a['name'] == slot['attachment'])
    return variable+'.'+a['name']+('.'+slot['channels'] if len(FORMATS[a['format']][0]) > 1 else '')


def storage_checks(schema, slots, variable):
    lines = []
    for s in slots:
        info = slot_info(schema, s)
        value = variable+'.'+s['name']
        if info['base'] == 'float':
            lines.append(f'    if (!all(isfinite({value}))) return false;')
        low, high = (literal(v, info['base']) for v in info['limits'])
        lines.append(f'    if (any({value} < {low}) || any({value} > {high})) return false;')
    return lines


def emit_codec(schema, layout_hash, sources):
    name = schema['name']
    guard = 'CRP_'+name+'_LAYOUT'
    words = [layout_hash[i:i+8] for i in range(0, 64, 8)]
    lines = ['// Generated storage contract. Edit the Schema, not this file.',
             '// Layout SHA256: '+layout_hash, '#if defined('+guard+'_0)']
    expression = ' || '.join(f'{guard}_{i} != 0x{word}u' for i, word in enumerate(words))
    lines += ['#if '+expression, '#error Conflicting GBuffer layout headers for '+name, '#endif', '#else']
    lines += [f'#define {guard}_{i} 0x{word}u' for i, word in enumerate(words)]
    fields = {f['name']: f for f in schema['fields']}
    slots = {s['name']: s for s in schema['storage']}
    lines += emit_struct(name+'Fields', [f['type']+' '+f['name'] for f in fields.values()])
    lines += emit_struct(name+'Storage', [slot_info(schema, s)['type']+' '+s['name'] for s in slots.values()])
    lines += emit_struct(name+'Packed', [f'{packed_type(a)} {a["name"]} : SV_Target{i}'
                                         for i, a in enumerate(schema['attachments'])])
    customs = [c for c in schema['codecs'] if c['kind'] == 'custom']
    for c in customs:
        prefix = name+'_'+c['name']
        lines += emit_struct(prefix+'Input', [fields[f]['type']+' '+f for f in c['fields']])
        lines += emit_struct(prefix+'Storage', [slot_info(schema, slots[s])['type']+' '+s for s in c['storage']])
    lines += ['#include "'+sources[file].as_posix()+'"' for file in dict.fromkeys(c['file'] for c in customs)]
    lines += ['', f'bool {name}Encode({name}Fields value, out {name}Packed packed)', '{',
              f'    packed = ({name}Packed)0;', f'    {name}Storage storage = ({name}Storage)0;']
    for i, c in enumerate(schema['codecs']):
        kind = c['kind']
        if kind == 'custom':
            prefix = name+'_'+c['name']
            lines += [f'    {prefix}Input __crp_input{i};', f'    {prefix}Storage __crp_output{i};']
            lines += [f'    __crp_input{i}.{f} = value.{f};' for f in c['fields']]
            lines += [f'    if (!{c["encode"]}(__crp_input{i}, __crp_output{i})) return false;']
            lines += [f'    storage.{s} = __crp_output{i}.{s};' for s in c['storage']]
            continue
        f, s = fields[c['field']], slots[c['storage']]
        target, source = 'storage.'+s['name'], 'value.'+f['name']
        if kind == 'bool':
            lines.append(f'    {target} = {source} ? 1u : 0u;')
            continue
        base = TYPES[f['type']][0]
        lo, hi = [literal(v, base) for v in c['range']]
        if base == 'float':
            lines.append(f'    if (!all(isfinite({source}))) return false;')
            # Classify raw bits before arithmetic can flush subnormal inputs to zero.
            magnitude = f'(asuint({source}) & 0x7fffffffu)'
            lines.append(f'    if (any(({magnitude} != 0u) & ({magnitude} < 0x00800000u))) return false;')
        if c['overflow'] == 'reject':
            lines.append(f'    if (any({source} < {lo}) || any({source} > {hi})) return false;')
        local = f'__crp_value{i}'
        lines.append(f'    {f["type"]} {local} = clamp({source}, {lo}, {hi});')
        if kind == 'unorm':
            max_code = (1 << slot_info(schema, s)['width'])-1
            expression = f'uint(round(saturate(({local} - {lo}) / ({hi} - {lo})) * {literal(max_code, "float")}))'
        elif kind == 'sint':
            expression = f'(asuint({local}) & {literal((1 << slot_info(schema, s)["width"])-1, "uint")})'
        else:
            expression = local
        lines.append(f'    {target} = {expression};')
    lines += storage_checks(schema, list(slots.values()), 'storage')
    # All rejection paths run before writing packed, so invalid output stays zero.
    bit_channels = {}
    for s in slots.values():
        if 'bits' not in s:
            lines.append(f'    {member(schema, s)} = storage.{s["name"]};')
            continue
        key = (s['attachment'], s['channels'])
        bit_channels.setdefault(key, []).append(s)
    for (attachment, channel), group in bit_channels.items():
        variable = '__crp_word_'+attachment+'_'+channel
        expressions = [f'(storage.{s["name"]} << {s["bits"]["offset"]})' for s in group]
        lines.append(f'    uint {variable} = '+' | '.join(expressions)+';')
        a = next(a for a in schema['attachments'] if a['name'] == attachment)
        widths, base, _ = FORMATS[a['format']]
        expression = variable if base == 'uint' else f'float({variable}) / {literal((1 << widths["rgba".index(channel)])-1, "float")}'
        lines.append(f'    {member(schema, group[0])} = {expression};')
    lines += ['    return true;', '}', '', f'{name}Fields {name}Decode({name}Packed packed)', '{',
              f'    {name}Storage storage = ({name}Storage)0;', f'    {name}Fields value = ({name}Fields)0;']
    for s in slots.values():
        source = member(schema, s)
        if 'bits' in s:
            a = next(a for a in schema['attachments'] if a['name'] == s['attachment'])
            widths, base, _ = FORMATS[a['format']]
            if base == 'unorm':
                source = f'uint(round(saturate({source}) * {literal((1 << widths["rgba".index(s["channels"])])-1, "float")}))'
            source = f'(({source} >> {s["bits"]["offset"]}) & {literal((1 << s["bits"]["width"])-1, "uint")})'
        lines.append(f'    storage.{s["name"]} = {source};')
    for i, c in enumerate(schema['codecs']):
        if c['kind'] == 'custom':
            prefix = name+'_'+c['name']
            lines.append(f'    {prefix}Storage __crp_storage{i};')
            lines += [f'    __crp_storage{i}.{s} = storage.{s};' for s in c['storage']]
            lines.append(f'    {prefix}Input __crp_decoded{i} = {c["decode"]}(__crp_storage{i});')
            lines += [f'    value.{f} = __crp_decoded{i}.{f};' for f in c['fields']]
            continue
        source = 'storage.'+c['storage']
        if c['kind'] == 'unorm':
            lo, hi = [literal(v, 'float') for v in c['range']]
            max_code = (1 << slot_info(schema, slots[c['storage']])['width'])-1
            source = f'(float({source}) / {literal(max_code, "float")}) * ({hi} - {lo}) + {lo}'
        elif c['kind'] == 'sint':
            shift = 32-slot_info(schema, slots[c['storage']])['width']
            source = f'(asint({source} << {shift}) >> {shift})'
        elif c['kind'] == 'bool':
            source += ' != 0u'
        lines.append(f'    value.{c["field"]} = {source};')
    lines += ['    return value;', '}', '#endif', '']
    return '\n'.join(lines)


def emit_raster(schema, producer):
    name = schema['name']
    return f'''// Generated native Falcor raster wrapper; material evaluation is authored.
#include "Scene/VertexAttrib.slangh"
import Scene.Raster;
import Rendering.Materials.TexLODHelpers;
#include "Codec.slangh"
#include "{producer.as_posix()}"

VSOut vsMain(VSIn input) {{ return defaultVS(input); }}

{name}Packed psMain(VSOut input, uint triangleIndex : SV_PrimitiveID)
{{
    float3 faceNormal = gScene.getFaceNormalW(input.instanceID, triangleIndex);
    VertexData vertex = prepareVertexData(input, faceNormal);
    let lod = ImplicitLodTextureSampler();
    if (gScene.materials.alphaTest(vertex, input.materialID, lod)) discard;
    float3 view = normalize(gScene.camera.getPosition() - vertex.posW);
    ShadingData sd = gScene.materials.prepareShadingData(vertex, input.materialID, view);
    {name}Fields fields = {schema['producer']['entry']}(sd, input.materialID);
    {name}Packed packed;
    if (!{name}Encode(fields, packed)) discard;
    return packed;
}}
'''
