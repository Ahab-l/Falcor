"""Read/select native outputs and request GPU visualization without graph mutation."""
import json
from output_catalog import OutputCatalog,output_view


def compare_arrays(actual, reference, *, atol=0.0, rtol=0.0):
    """Compare finite numeric samples in the same encoding and units.

    Tolerance is abs(actual-reference) <= atol + rtol*abs(reference).
    This explicit CPU operation does not run in the live rendering loop.
    """
    import math
    import numpy as np
    for value in (atol, rtol):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Comparison tolerances must be finite and nonnegative')
    actual, reference = np.asarray(actual), np.asarray(reference)
    if actual.shape != reference.shape or actual.size == 0:
        raise ValueError('Comparison requires equal, nonempty shapes')
    if actual.dtype.kind not in 'biuf' or reference.dtype.kind not in 'biuf':
        raise ValueError('Comparison requires real numeric arrays')
    # float64 preserves all texture-sized integer formats and prevents uint
    # subtraction wrapping. Larger integer IDs must use exact integer tools.
    if any(a.dtype.kind in 'iu' and a.size and (np.any(a > 2**53) or (a.dtype.kind == 'i' and np.any(a < -(2**53))))
           for a in (actual, reference)):
        raise ValueError('Integer samples exceed exact float64 comparison range')
    actual, reference = actual.astype(np.float64), reference.astype(np.float64)
    if not np.isfinite(actual).all() or not np.isfinite(reference).all():
        raise ValueError('Comparison requires finite samples')
    with np.errstate(over='ignore', invalid='ignore'):
        error = np.abs(actual-reference)
        threshold = atol + rtol*np.abs(reference)
    if not np.isfinite(error).all() or not np.isfinite(threshold).all():
        raise ValueError('Comparison arithmetic exceeds float64 range')
    maximum = float(error.max())
    failed = int(np.count_nonzero(error > threshold))
    # Scale before squaring to avoid unnecessary overflow in RMSE.
    rmse = maximum * float(np.sqrt(np.mean((error/maximum)**2))) if maximum else 0.0
    return {'passed': failed == 0, 'sample_count': int(error.size), 'failed_samples': failed,
            'max_abs': maximum, 'mae': float(np.mean(error/maximum))*maximum if maximum else 0.0,
            'rmse': rmse, 'worst_index': [int(i) for i in np.unravel_index(int(error.argmax()), error.shape)],
            'atol': float(atol), 'rtol': float(rtol)}

class PipelineObserver:
    def __init__(self, graph):
        self.graph = graph

    def schema(self, artifacts, bindings=None, **options):
        """Register a generated Schema observer before rendering its marked outputs."""
        from schema_observer import SchemaObserver
        return SchemaObserver(self.graph, artifacts, bindings, **options)

    def catalog(self):
        import falcor
        return OutputCatalog(json.loads(falcor.customRenderPiplineOutputCatalog(self.graph)))

    def _selection(self, name, *, mip=None, slice=None):
        import falcor
        records = json.loads(falcor.customRenderPiplineOutputCatalog(self.graph))
        record = OutputCatalog(records).select([name])[0]
        options={key:value for key,value in (('mip',mip),('slice',slice)) if value is not None}
        view = output_view(record, options)
        result = next(value for value in records if value['name'] == name)
        resource = self.graph.getOutput(name)
        if record.kind.startswith('texture'):
            if record.mip_count > 1 or record.array_size > 1 or record.kind == 'textureCube':
                result['view'] = view
            result.update(width=max(1, record.width >> view['mip']), height=max(1, record.height >> view['mip']))
        return record, view, result, resource

    def read(self, name, *, mip=None, slice=None):
        import falcor
        record, view, result, resource = self._selection(name, mip=mip, slice=slice)
        if record.kind.startswith('texture'):
            if record.format == 'D32FloatS8Uint':
                result.update(falcor.customRenderPiplineReadDepthStencil(resource, view['mip'], view['slice']))
            else:
                result['data'] = resource.to_numpy(mip_level=view['mip'], array_slice=view['slice']).tobytes()
        else:
            result['data'] = resource.to_numpy().tobytes()
        return result

    def read_async(self, name, *, mip=None, slice=None, max_bytes=64*1024*1024):
        """Native raw snapshot; frozen view metadata and no synchronous fallback."""
        import falcor
        from observer_async import MappedReadback
        record, view, result, resource = self._selection(name, mip=mip, slice=slice)
        if record.kind.startswith('texture'):
            if record.format == 'D32FloatS8Uint':
                native = falcor.customRenderPiplineReadDepthStencilAsync(resource, view['mip'], view['slice'], max_bytes)
                return MappedReadback(native, lambda planes: {**result, **planes})
            native = resource.read_async(mip_level=view['mip'], array_slice=view['slice'], max_bytes=max_bytes)
        else:
            native = resource.read_async(max_bytes=max_bytes)
        return MappedReadback(native, lambda data: {**result, 'data': data})

    def compare(self, name, reference, *, dtype, shape=None, blob='data', atol=0.0, rtol=0.0, mip=None, slice=None):
        """Explicit raw readback and numeric comparison; caller selects encoding.

        Packed formats and padded depth planes require caller decoding via read()
        and compare_arrays(). No implicit sRGB, channel or normal conversion.
        """
        import numpy as np
        result = self.read(name, mip=mip, slice=slice)
        if blob not in result:
            raise ValueError('Output has no requested byte plane: ' + blob)
        actual = np.frombuffer(result[blob], dtype=dtype)
        actual = actual.reshape(np.asarray(reference).shape if shape is None else shape)
        return compare_arrays(actual, reference, atol=atol, rtol=rtol)

    def atlas(self, names, *, tile_extent=(256, 256), columns=4, displays=None, views=None):
        import falcor
        layout = self.catalog().atlas_layout(names, tile_extent=tile_extent, columns=columns, displays=displays, views=views)
        if not layout['tiles']:
            raise ValueError('Atlas requires at least one selected output')
        return falcor.customRenderPiplineRenderAtlas(self.graph, json.dumps(layout)), layout

    def atlas_views(self, selections, *, tile_extent=(256,256), columns=4):
        import falcor
        layout=self.catalog().atlas_views_layout(selections,tile_extent=tile_extent,columns=columns)
        if not layout['tiles']:raise ValueError('Atlas requires at least one selected view')
        return falcor.customRenderPiplineRenderAtlas(self.graph,json.dumps(layout)),layout
