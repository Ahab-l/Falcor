"""Pure CPU selection and Atlas layout for already-observed render outputs.

Only metadata and display intent enter this module. Native rendering supplies
the resources and performs all sampling, buffer interpretation, and display.
"""
from dataclasses import dataclass
import math


# Falcor ResourceFormat spellings. Normalized and compressed formats sample as
# floats; signed integer ResourceFormat names use "Int", while display uses
# "sint". Depth/stencil formats expose only their depth lane here.
_FORMATS = {}
for _channels, _names in {
    1: 'R8Unorm R8Snorm R16Unorm R16Snorm R16Float R32Float BC4Unorm BC4Snorm',
    2: 'RG8Unorm RG8Snorm RG16Unorm RG16Snorm RG16Float RG32Float BC5Unorm BC5Snorm',
    3: 'RGB32Float R11G11B10Float RGB9E5Float R5G6B5Unorm BC6HS16 BC6HU16',
    4: ('RGB5A1Unorm RGBA8Unorm RGBA8Snorm RGB10A2Unorm RGBA16Unorm RGBA16Snorm '
        'RGBA8UnormSrgb RGBA16Float RGBA32Float BGRA4Unorm BGRA8Unorm BGRA8UnormSrgb '
        'BGRX8Unorm BGRX8UnormSrgb BC1Unorm BC1UnormSrgb BC2Unorm BC2UnormSrgb '
        'BC3Unorm BC3UnormSrgb BC7Unorm BC7UnormSrgb'),
}.items():
    _FORMATS.update({name: ('float', _channels) for name in _names.split()})
for _prefix, _channels in (('R', 1), ('RG', 2), ('RGB', 3), ('RGBA', 4)):
    for _bits in ((32,) if _prefix == 'RGB' else (8, 16, 32)):
        _FORMATS[_prefix + str(_bits) + 'Uint'] = ('uint', _channels)
        _FORMATS[_prefix + str(_bits) + 'Int'] = ('sint', _channels)
_FORMATS['RGB10A2Uint'] = ('uint', 4)
_FORMATS.update({name: ('depth', 1) for name in ('D16Unorm', 'D32Float', 'D32FloatS8Uint')})
_RAW_MODES = frozenset(('bytes', 'uint32', 'sint32', 'float32'))


def _positive_integer(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(label + ' must be a positive integer')
    return value


def _finite_number(value, label):
    if type(value) not in (int, float):
        raise ValueError(label + ' must be a finite number')
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(label + ' must be a finite number') from error
    if not math.isfinite(result):
        raise ValueError(label + ' must be a finite number')
    return result


@dataclass(frozen=True)
class OutputRecord:
    """Owned metadata returned by OutputCatalog after record validation."""

    name: str
    kind: str
    format: str
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    mip_count: int = 1
    array_size: int = 1
    stride: int | None = None
    count: int | None = None


def _record(value):
    if type(value) is not dict:
        raise ValueError('Output record must be an object')
    kind = value.get('kind')
    texture = kind in ('texture2D','texture2DArray','textureCube')
    if not texture and kind not in ('raw_buffer','structured_buffer'):
        raise ValueError('Unsupported observed output kind')
    required = {'name', 'kind', 'format'} | ({'width', 'height'} if texture else {'bytes'})
    if kind == 'structured_buffer':required |= {'stride','count'}
    optional = {'mip_count','array_size'} if texture else set()
    if not required <= value.keys() or value.keys() - required - optional:
        raise ValueError('Output record has missing or unsupported metadata keys')
    if type(value['name']) is not str or not value['name'].strip():
        raise ValueError('Output name must be a nonempty string')
    resource_format = value['format']
    allowed_formats = _FORMATS if texture else {'Unknown'}
    if type(resource_format) is not str or resource_format not in allowed_formats:
        raise ValueError('Unsupported observed output format')
    for dimension in ('width', 'height') if texture else ('bytes',):
        _positive_integer(value[dimension], 'Output ' + dimension)
    if texture:
        mips=_positive_integer(value.get('mip_count',1),'Output mip_count')
        arrays=_positive_integer(value.get('array_size',1),'Output array_size')
        if mips>max(value['width'],value['height']).bit_length():raise ValueError('Too many texture mips')
        if kind=='textureCube' and (value['width']!=value['height'] or arrays!=1):raise ValueError('Expected one square Cube')
        if (kind=='texture2D' and arrays!=1) or (kind=='texture2DArray' and arrays<2):raise ValueError('Texture array size mismatch')
    elif kind=='structured_buffer':
        stride=_positive_integer(value['stride'],'Output stride');count=_positive_integer(value['count'],'Output count')
        if stride%4 or stride*count!=value['bytes']:raise ValueError('Structured buffer shape mismatch')
    return OutputRecord(**value)


def _display(record, options):
    if type(options) is not dict or options.keys() - {'mode', 'channel', 'scale', 'bias', 'minmax'}:
        raise ValueError('Display options require an object with supported keys')
    if record.kind in ('raw_buffer','structured_buffer'):
        if 'mode' not in options:
            raise ValueError('Raw buffer display requires an explicit byte or scalar grid mode')
        mode, channels = options['mode'], 1
        if type(mode) is not str or mode not in _RAW_MODES:
            raise ValueError('Raw buffer mode must be bytes, uint32, sint32, or float32')
        if mode != 'bytes' and record.bytes % 4:
            raise ValueError('Raw scalar grid requires complete 32-bit elements (bytes divisible by 4)')
    else:
        category, channels = _FORMATS[record.format]
        default = 'color' if category == 'float' and channels >= 3 else category
        mode = options.get('mode', default)
        allowed = ('color', 'float') if category == 'float' else (category,)
        if type(mode) is not str or mode not in allowed:
            raise ValueError('Display mode is incompatible with observed output format')
    result = {'mode': mode}
    if mode == 'color':
        if 'channel' in options:
            raise ValueError('Color display does not accept a scalar channel option')
    else:
        channel = options.get('channel', 0)
        if type(channel) is not int or not 0 <= channel <= 3 or channel >= channels:
            raise ValueError('Display channel must be an existing integer lane in range 0..3')
        result['channel'] = channel
    result['scale'] = _finite_number(options.get('scale', 1.0), 'Display scale')
    result['bias'] = _finite_number(options.get('bias', 0.0), 'Display bias')
    limits = options.get('minmax')
    if limits is not None:
        if type(limits) not in (list, tuple) or len(limits) != 2:
            raise ValueError('Display minmax must contain two finite increasing values')
        limits = [_finite_number(value, 'Display minmax') for value in limits]
        if limits[0] >= limits[1]:
            raise ValueError('Display minmax must contain two finite increasing values')
    result['minmax'] = limits
    return result


def output_view(record, options):
    if type(options) is not dict or options.keys()-{'mip','slice'}:raise ValueError('Invalid output view')
    if not record.kind.startswith('texture'):
        if options:raise ValueError('Buffer does not have texture views')
        return {}
    result={'mip':options.get('mip',0),'slice':options.get('slice',0)}
    layers=6 if record.kind=='textureCube' else record.array_size
    for key,bound in (('mip',record.mip_count),('slice',layers)):
        if type(result[key]) is not int or not 0<=result[key]<bound:raise ValueError('Output '+key+' is out of range')
    return result


class OutputCatalog:
    """Validate observed records, preserve their order, and select exact outputs."""

    def __init__(self, records):
        if type(records) not in (list, tuple):
            raise ValueError('Output records must be an ordered list or tuple')
        outputs, by_name = [], {}
        for value in records:
            record = _record(value)
            if record.name in by_name:
                raise ValueError('Duplicate observed output name: ' + record.name)
            outputs.append(record)
            by_name[record.name] = record
        self._outputs, self._by_name = tuple(outputs), by_name

    @property
    def outputs(self):
        return self._outputs

    def select(self, names):
        """Return immutable records in request order; unknown/duplicate names fail."""
        if type(names) not in (list, tuple):
            raise ValueError('Output selection must be an ordered list or tuple of names')
        result, seen = [], set()
        for name in names:
            if type(name) is not str or name not in self._by_name:
                raise ValueError('Unknown output name in selection')
            if name in seen:
                raise ValueError('Duplicate output name in selection: ' + name)
            seen.add(name)
            result.append(self._by_name[name])
        return tuple(result)

    def atlas_layout(self, names, tile_extent=(256, 256), columns=4, displays=None, views=None):
        """Return JSON-safe {width, height, tiles} without reading render data.

        Tiles contain name, x/y/width/height, and normalized display options.
        They fill rows in selection order without padding, overlap, or aspect
        fitting; a partial first row has a tight width. Empty selection returns
        a 0x0 layout and no tiles. Native allocation limits belong to the caller.

        displays maps selected names to mode/channel/scale/bias/minmax options.
        Texture modes are color, float, depth, uint, and sint, constrained by
        observed format. Scalar modes use one existing lane (0..3). Raw buffers
        require explicit bytes/uint32/sint32/float32 grid mode; byte and scalar
        interpretation and grid sampling are native responsibilities.

        Display intent is value * scale + bias, then optional minmax remapping
        to [0,1]. minmax=None requests no extra remapping. This module validates
        parameters only; it does not transform or clamp any resource values.
        """
        selected = self.select(names)
        if type(tile_extent) not in (list, tuple) or len(tile_extent) != 2:
            raise ValueError('tile_extent must contain two positive integer dimensions')
        width, height = [_positive_integer(value, 'Tile extent') for value in tile_extent]
        columns = _positive_integer(columns, 'Atlas columns')
        displays = {} if displays is None else displays
        if type(displays) is not dict or displays.keys() - {record.name for record in selected}:
            raise ValueError('Display options may name only selected outputs')
        views={} if views is None else views
        if type(views) is not dict or views.keys()-{r.name for r in selected}:raise ValueError('Views may name only selected outputs')
        tiles = []
        for index, record in enumerate(selected):
            tiles.append({'name': record.name, 'x': index % columns * width, 'y': index // columns * height,
                          'width': width, 'height': height, 'display': _display(record, displays.get(record.name, {}))})
            if record.name in views:tiles[-1]['view']=output_view(record,views[record.name])
        return {'width': min(columns, len(tiles)) * width,
                'height': ((len(tiles) + columns - 1) // columns) * height, 'tiles': tiles}

    def atlas_views_layout(self, selections, *, tile_extent=(256,256), columns=4):
        """Display distinct views of the same resource together, with per-tile intent."""
        if type(selections) not in (list,tuple):raise ValueError('Output views must be an ordered list')
        columns=_positive_integer(columns,'Atlas columns')
        # Reuse the ordinary layout's extent validation, including an empty selection.
        self.atlas_layout([],tile_extent=tile_extent,columns=columns)
        width,height=tile_extent
        tiles=[];seen=set()
        for index,selection in enumerate(selections):
            if type(selection) is not dict or 'name' not in selection or selection.keys()-{'name','mip','slice','display'}:
                raise ValueError('Invalid Atlas view selection')
            name=selection['name'];record=self.select([name])[0]
            view=output_view(record,{k:selection[k] for k in ('mip','slice') if k in selection})
            identity=(name,view.get('mip',0),view.get('slice',0))
            if identity in seen:raise ValueError('Duplicate Atlas output view')
            seen.add(identity)
            tiles.append({'name':name,'view':view,'x':index%columns*width,'y':index//columns*height,
                'width':width,'height':height,'display':_display(record,selection.get('display',{}))})
        return {'width':min(columns,len(tiles))*width,'height':((len(tiles)+columns-1)//columns)*height,'tiles':tiles}
