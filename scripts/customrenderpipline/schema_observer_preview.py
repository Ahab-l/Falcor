"""On-demand GPU-only Schema snapshots using the verified V4 generated decoder.

The returned RGBA32Float texture is borrowed: another successful render of the
same size updates it in place. No implicit render, readback, colorspace conversion
or vector normalization is performed. All methods belong to the observer thread.

Display bounds are rounded to float32. Nonzero subnormal bounds and subnormal
spans are rejected because shader arithmetic may flush them to zero. Finite
samples are clamped *before* a two-step power-of-two scaling and subtraction;
this keeps normalization intermediates finite even near FLT_MAX. RGB ignores
alpha for display, but any nonfinite lane of the observed value is diagnostic
magenta. Signed display is exactly v * 0.5 + 0.5 (not length normalization).
"""
from collections import OrderedDict
from dataclasses import dataclass
import math
import struct

from gbuffer_codegen import packed_type
from gbuffer_schema import FLOAT32_MAX, TYPES
from schema_observer_codegen import MAX_BYTES

FLOAT32_MIN_NORMAL = float.fromhex('0x1p-126')
MAX_PROGRAMS = 8
MAX_TEXTURE_DIMENSION = 16384


@dataclass(frozen=True)
class PreviewSpec:
    """Pure validated shader request; range uniforms are not in the program key."""
    shader: str
    cache_key: tuple
    bindings: tuple
    low: float
    high: float
    span: float
    scale: tuple  # First factor, second factor, scaled low, scaled span.


def _float32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


def _range(low, high):
    for value in (low, high):
        if type(value) not in (int, float) or not -FLOAT32_MAX <= value <= FLOAT32_MAX:
            raise ValueError('preview range requires finite float32 numbers')
        if value != 0 and abs(value) < FLOAT32_MIN_NORMAL:
            raise ValueError('preview range rejects nonzero subnormal float32 bounds (GPU flush-to-zero)')
    low, high = _float32(low), _float32(high)
    if not low < high:
        raise ValueError('preview range must satisfy low < high after float32 conversion')
    if not FLOAT32_MIN_NORMAL <= high-low <= FLOAT32_MAX:
        raise ValueError('preview range span is subnormal or overflows float32')
    span = _float32(high-low)
    # Neither multiplier is subnormal, infinite, or zero. Scaling to unit
    # magnitude also avoids overflowing the reciprocal of a tiny interval.
    exponent = math.frexp(max(abs(low), abs(high)))[1]
    first_exponent = -exponent // 2
    first = math.ldexp(1., first_exponent)
    second = math.ldexp(1., -exponent-first_exponent)
    scaled_low = _float32(_float32(low*first)*second)
    scaled_high = _float32(_float32(high*first)*second)
    scaled_span = _float32(scaled_high-scaled_low)
    if not FLOAT32_MIN_NORMAL <= scaled_span <= FLOAT32_MAX:
        raise ValueError('preview range cannot be normalized reliably in float32')
    return low, high, span, (first, second, scaled_low, scaled_span)


def validate_preview_dimensions(dimensions):
    """Bound 2D dispatch and RGBA32Float allocation before touching the device."""
    if (not isinstance(dimensions, (tuple, list)) or len(dimensions) != 2
            or any(type(value) is not int or not 1 <= value <= MAX_TEXTURE_DIMENSION for value in dimensions)):
        raise ValueError('preview dimensions must be positive integers within the 2D texture limit')
    width, height = dimensions
    if width*height*16 > MAX_BYTES:
        raise ValueError('preview output exceeds GPU texture byte limit')
    return width, height


def emit_preview(contract, source, mode='gray', low=0., high=1., component=0):
    """Emit from a V4 verified contract without importing Falcor or using a GPU.

    Sources are exactly ``field:NAME`` or ``attachment:NAME``. Gray accepts a
    numeric component; id accepts an integer component or bool; rgb accepts
    float3/float4; signed accepts float3. Vector modes require component=0.
    Bounds are validated for every mode, but used only by gray/rgb.
    """
    if not isinstance(source, str) or source.count(':') != 1:
        raise ValueError('preview source must be field:NAME or attachment:NAME')
    group, selected = source.split(':')
    if group not in ('field', 'attachment'):
        raise ValueError('preview source must be field:NAME or attachment:NAME')
    schema = contract['schema']
    available = schema['fields' if group == 'field' else 'attachments']
    item = next((item for item in available if item['name'] == selected), None)
    if item is None:
        raise ValueError('Unknown preview source: '+source)
    typename = item['type'] if group == 'field' else packed_type(item)
    base, count = TYPES[typename]
    if not isinstance(mode, str) or mode not in ('gray', 'rgb', 'signed', 'id'):
        raise ValueError('Unknown preview mode')
    if type(component) is not int or not 0 <= component < count:
        raise ValueError('preview component must be an integer within the source channel count')
    if mode in ('rgb', 'signed') and component != 0:
        raise ValueError('vector preview modes require component=0')
    if mode == 'gray' and base == 'bool':
        raise ValueError('gray mode requires a numeric source; use id for bool')
    if mode == 'rgb' and not (base == 'float' and count in (3, 4)):
        raise ValueError('rgb mode requires float3 or float4')
    if mode == 'signed' and not (base == 'float' and count == 3):
        raise ValueError('signed mode requires float3')
    if mode == 'id' and base not in ('uint', 'int', 'bool'):
        raise ValueError('id mode requires an integer component or bool')
    low, high, span, scale = _range(low, high)

    lines = []
    attachments = schema['attachments'] if group == 'field' else [item]
    if group == 'field':
        lines.append('#include "'+contract['artifacts'].codec.resolve().as_posix()+'"')
    bindings = tuple(('gAttachment'+str(index), attachment['name']) for index, attachment in enumerate(attachments))
    for (binding, _), attachment in zip(bindings, attachments):
        lines.append(f'Texture2D<{packed_type(attachment)}> {binding};')
    lines += ['RWTexture2D<float4> gPreview;', 'uint2 gDimensions;']
    if mode in ('gray', 'rgb'):
        lines += ['float2 gBounds;', 'float4 gScale;',
                  'float previewRange(float value)', '{',
                  '    precise float bounded = clamp(value, gBounds.x, gBounds.y);',
                  '    precise float scaled = (bounded * gScale.x) * gScale.y;',
                  '    precise float normalized = (scaled - gScale.z) / gScale.w;',
                  '    return saturate(normalized);', '}']
    if mode == 'id':
        lines += ['uint previewHash(uint value)', '{',
                  '    value ^= value >> 16;', '    value *= 0x7feb352du;',
                  '    value ^= value >> 15;', '    value *= 0x846ca68bu;',
                  '    value ^= value >> 16;', '    return value;', '}']
    lines += ['[numthreads(8,8,1)] void main(uint3 tid: SV_DispatchThreadID)', '{',
              '    uint2 pixel = tid.xy;', '    if (any(pixel >= gDimensions)) return;']
    if group == 'field':
        name = schema['name']
        lines.append(f'    {name}Packed packed;')
        for binding, attachment in bindings:
            lines.append(f'    packed.{attachment} = {binding}.Load(int3(pixel, 0));')
        lines += [f'    {name}Fields value = {name}Decode(packed);',
                  f'    {typename} sampleValue = value.{selected};']
    else:
        lines.append(f'    {typename} sampleValue = gAttachment0.Load(int3(pixel, 0));')
    if base == 'float':
        lines += ['    if (!all(isfinite(sampleValue)))', '    {',
                  '        gPreview[pixel] = float4(1.0f, 0.0f, 1.0f, 1.0f);', '        return;', '    }']
    scalar = 'sampleValue'+('.'+'xyzw'[component] if count > 1 else '')
    if mode == 'gray':
        lines += [f'    float gray = previewRange(float({scalar}));', '    float3 color = float3(gray, gray, gray);']
    elif mode == 'rgb':
        lines.append('    float3 color = float3(previewRange(sampleValue.x), previewRange(sampleValue.y), previewRange(sampleValue.z));')
    elif mode == 'signed':
        lines.append('    float3 color = sampleValue * 0.5f + 0.5f;')
    else:
        value = f'({scalar} ? 1u : 0u)' if base == 'bool' else f'asuint({scalar})' if base == 'int' else scalar
        lines += [f'    uint hashed = previewHash({value});',
                  '    uint3 palette = uint3(hashed & 255u, (hashed >> 8) & 255u, (hashed >> 16) & 255u);',
                  '    float3 color = float3(palette) / 255.0f;']
    lines += ['    gPreview[pixel] = float4(color, 1.0f);', '}', '']
    return PreviewSpec('\n'.join(lines), (source, mode, component), bindings, low, high, span, scale)


class _ProgramCache:
    """Small LRU whose production policy can be tested without fake GPU objects."""
    def __init__(self):
        self._entries = OrderedDict()

    def __len__(self):
        return len(self._entries)

    def get(self, key):
        if key not in self._entries:
            return None
        self._entries.move_to_end(key)
        return self._entries[key]

    def put(self, key, program):
        self._entries[key] = program
        self._entries.move_to_end(key)
        while len(self._entries) > MAX_PROGRAMS:
            self._entries.popitem(last=False)

    def clear(self):
        self._entries.clear()


class SchemaFieldPreview:
    """A bounded on-demand snapshot renderer for one existing SchemaObserver."""
    def __init__(self, observer):
        observer._thread()
        self.observer = observer
        self._programs = _ProgramCache()
        self._texture = None
        self._dimensions = None
        self._closed = False
        self.dispatch_count = 0

    def render(self, source, mode='gray', low=0., high=1., component=0):
        """Validate V4 resources, dispatch once, return a same-size GPU texture."""
        if self._closed:
            raise RuntimeError('Schema preview is closed')
        self.observer._thread()
        spec = emit_preview(self.observer.contract, source, mode, low, high, component)
        # This authoritative V4 check catches changed source files/layout,
        # producer definition, marked outputs, formats, samples and dimensions.
        textures, dimensions, _ = self.observer._resources()
        dimensions = validate_preview_dimensions(dimensions)
        import falcor
        device = self.observer.graph.device
        program = self._programs.get(spec.cache_key)
        if program is None:
            program = falcor.ComputePass(device, string=spec.shader, cs_entry='main', shader_model=falcor.ShaderModel.SM6_6)
        for binding, attachment in spec.bindings:
            program.globals[binding] = textures[attachment]
        program.globals['gDimensions'] = falcor.uint2(*dimensions)
        if mode in ('gray', 'rgb'):
            program.globals['gBounds'] = falcor.float2(spec.low, spec.high)
            program.globals['gScale'] = falcor.float4(*spec.scale)
        texture = self._texture
        resized = self._dimensions != dimensions
        if texture is None or resized:
            texture = device.create_texture(width=dimensions[0], height=dimensions[1],
                format=falcor.ResourceFormat.RGBA32Float, mip_levels=1,
                bind_flags=falcor.ResourceBindFlags.UnorderedAccess | falcor.ResourceBindFlags.ShaderResource)
        program.globals['gPreview'] = texture
        program.execute(threads_x=dimensions[0], threads_y=dimensions[1])
        self.dispatch_count += 1
        if resized:
            # Programs keep bound resources alive; drop old-sized bindings.
            self._programs.clear()
        self._programs.put(spec.cache_key, program)
        self._texture, self._dimensions = texture, dimensions
        return texture

    def close(self):
        """Release owned programs/textures; already-returned textures are borrowed."""
        if self._closed:
            return
        self.observer._thread()
        self._programs.clear()
        self._texture = None
        self._dimensions = None
        self._closed = True
