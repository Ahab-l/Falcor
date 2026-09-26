"""Mogwai/D3D12 GPU preview acceptance; readbacks occur only in this test.

Run with Mogwai's --script option. The fixture uses the ordinary V4 native scene
and generated Codec, augmented with adjacent full-width UINT/SINT values. JSON,
NPZ evidence and failure tracebacks are written below build/native-schema-observer-ui.
"""
import builtins
import json
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT/'scripts/customrenderpipline'
sys.path[:0] = [str(HERE), str(ROOT/'build/m0-evidence/python')]
OUT = ROOT/'build/native-schema-observer-ui'
OUT.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix='gpu-preview-', dir=OUT))
print('V5_PREVIEW_EVIDENCE '+str(out), flush=True)

result = {'status': 'running', 'cases': [], 'evidence': str(out)}
preview = attachment = None
arrays = {}


def palette_reference(value):
    """Independent unsigned arithmetic oracle; never round IDs through float."""
    if value.dtype == np.dtype('int32'):
        bits = value.view(np.uint32)
    elif value.dtype == np.dtype('bool'):
        bits = value.astype(np.uint32)
    else:
        assert value.dtype == np.dtype('uint32'), value.dtype
        bits = value
    word = bits.astype(np.uint64)
    word ^= word >> 16
    word = (word * np.uint64(0x7feb352d)) & np.uint64(0xffffffff)
    word ^= word >> 15
    word = (word * np.uint64(0x846ca68b)) & np.uint64(0xffffffff)
    word ^= word >> 16
    return np.stack((word & 255, (word >> 8) & 255, (word >> 16) & 255), axis=-1).astype(np.float32)/np.float32(255)


def expected_preview(value, mode, low, high, component):
    """Map authoritative V4 arrays, without importing preview implementation math."""
    if mode in ('gray', 'id'):
        selected = value if value.ndim == 2 else value[..., component]
    if mode == 'id':
        color = palette_reference(selected)
    elif mode == 'gray':
        normalized = np.clip((selected.astype(np.float64)-float(np.float32(low))) /
                             (float(np.float32(high))-float(np.float32(low))), 0., 1.).astype(np.float32)
        color = np.repeat(normalized[..., None], 3, axis=-1)
    elif mode == 'rgb':
        color = np.clip((value[..., :3].astype(np.float64)-float(np.float32(low))) /
                        (float(np.float32(high))-float(np.float32(low))), 0., 1.).astype(np.float32)
    else:
        assert mode == 'signed'
        color = value.astype(np.float32)*np.float32(.5)+np.float32(.5)
    rgba = np.concatenate((color, np.ones((*color.shape[:2], 1), np.float32)), axis=-1)
    if value.dtype.kind == 'f':
        valid = np.isfinite(value)
        if valid.ndim == 3:
            valid = valid.all(axis=-1)
        rgba[~valid] = [1., 0., 1., 1.]
    return rgba


try:
    import falcor
    import numpy as np
    from native_schema_observer import start
    from schema_observer_preview import SchemaFieldPreview

    fixture = HERE/'examples/schema_gbuffer'
    schema = json.loads((fixture/'Schema.json').read_text(encoding='utf-8'))
    schema['attachments'].append({'name': 'exact', 'format': 'RG32Uint'})
    for name, channel, kind, bounds in (
            ('fullID', 'r', 'uint', [0, 4294967295]),
            ('signedID', 'g', 'sint', [-2147483648, 2147483647])):
        schema['fields'].append({'name': name, 'type': 'uint' if kind == 'uint' else 'int'})
        schema['storage'].append({'name': name+'Code', 'attachment': 'exact', 'channels': channel,
                                  'bits': {'offset': 0, 'width': 32}})
        schema['codecs'].append({'kind': kind, 'field': name, 'storage': name+'Code',
                                'range': bounds, 'overflow': 'reject'})
    (out/'SurfaceCodec.slangh').write_bytes((fixture/'SurfaceCodec.slangh').read_bytes())
    material = (fixture/'Material.slangh').read_text(encoding='utf-8')
    assert material.count('return fields;') == 1
    material = material.replace('return fields;', '''
    // Explicit acceptance fixture: both bool values and adjacent wide integers.
    fields.fullID = 4294967295u - (materialID & 1u);
    fields.signedID = (-2147483647 - 1) + int(materialID & 1u);
    fields.emissive = (materialID & 1u) != 0u;
    return fields;''')
    (out/'Material.slangh').write_text(material, encoding='utf-8')
    (out/'Schema.json').write_text(json.dumps(schema, indent=2), encoding='utf-8')
    graph, artifacts, observer, service, attachment = start(
        m, schema_path=out/'Schema.json', session_dir=out/'session', output_dir=out/'generated')
    m.resizeFrameBuffer(128, 72)
    m.clock.pause()
    m.ui = False
    m.renderFrame()
    preview = SchemaFieldPreview(observer)
    counts = (observer.dispatch_count, observer.readback_count, preview.dispatch_count)
    for _ in range(3):
        m.renderFrame()
    assert counts == (0, 0, 0) == (observer.dispatch_count, observer.readback_count, preview.dispatch_count)

    snapshot = observer.inspect([0, 0, 128, 72])
    mask = snapshot['fields']['coverage'] > 0
    assert int(mask.sum()) > 100, 'Native fixture did not rasterize sufficient pixels'
    full = snapshot['fields']['fullID'][mask]
    signed = snapshot['fields']['signedID'][mask]
    assert full.dtype == np.dtype('uint32') and signed.dtype == np.dtype('int32')
    assert set(map(int, np.unique(full))) == {4294967294, 4294967295}, np.unique(full)
    assert set(map(int, np.unique(signed))) == {-2147483648, -2147483647}, np.unique(signed)
    assert set(map(bool, np.unique(snapshot['fields']['emissive'][mask]))) == {False, True}
    # Both pairs collapse in float32, so distinct matching palettes prove that
    # the actual GPU path preserves more than float32's 24 integer bits.
    assert np.float32(4294967294) == np.float32(4294967295)
    assert np.float32(-2147483648) == np.float32(-2147483647)
    assert not np.array_equal(palette_reference(np.array([[4294967294]], np.uint32)),
                              palette_reference(np.array([[4294967295]], np.uint32)))
    for group in ('fields', 'storage', 'attachments'):
        for name, value in snapshot[group].items():
            arrays['v4.'+group+'.'+name] = value
    result.update(covered_pixels=int(mask.sum()), layout_hash=observer.layout_hash,
                  dimensions=[128, 72], full_integer_values=list(map(int, np.unique(full))),
                  signed_integer_values=list(map(int, np.unique(signed))), explicit_bool_fixture=True)

    last_texture = None

    def check(source, mode='gray', low=0., high=1., component=0):
        global last_texture
        before = (observer.dispatch_count, observer.readback_count)
        before_dispatch = preview.dispatch_count
        texture = preview.render(source, mode, low, high, component)
        assert (observer.dispatch_count, observer.readback_count) == before, 'Preview invoked V4 readback/decode'
        assert preview.dispatch_count == before_dispatch+1
        group, name = source.split(':')
        value = snapshot['fields' if group == 'field' else 'attachments'][name]
        expected = expected_preview(value, mode, low, high, component)
        height, width = expected.shape[:2]
        assert (texture.width, texture.height) == (width, height)
        assert texture.format == falcor.ResourceFormat.RGBA32Float
        if last_texture is not None:
            assert texture is last_texture, 'Same-sized preview texture was not reused'
        last_texture = texture
        # Acceptance-only readback. schema_observer_preview.py never does this.
        actual = np.asarray(texture.to_numpy()).copy()
        assert actual.dtype == np.dtype('float32') and actual.shape == expected.shape, (actual.dtype, actual.shape)
        np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=0,
                                   err_msg=f'{source} {mode} component={component}, range=[{low}, {high}]')
        index = len(result['cases'])
        arrays[f'case{index:02d}.actual'] = actual
        arrays[f'case{index:02d}.expected'] = expected
        result['cases'].append({'source': source, 'mode': mode, 'component': component,
            'range': [low, high], 'dimensions': [width, height],
            'max_abs_error': float(np.max(np.abs(actual-expected))), 'cache_size': len(preview._programs)})
        assert len(preview._programs) <= 8
        return actual

    check('field:roughness')
    rough_program = preview._programs.get(('field:roughness', 'gray', 0))
    check('field:roughness', low=.15, high=.65)
    assert len(preview._programs) == 1
    assert preview._programs.get(('field:roughness', 'gray', 0)) is rough_program
    check('field:baseColor', 'rgb')
    check('field:baseColor', 'rgb', low=-.25, high=.75)
    check('field:baseColor', component=2)
    check('field:normalW', 'signed')
    check('field:materialID', 'id')
    check('field:emissive', 'id')
    check('field:fullID', 'id')
    check('field:signedID', 'id')
    check('attachment:materialBits', 'id')
    check('attachment:color', 'rgb')
    check('attachment:color', component=3)
    check('attachment:normal', component=0)
    check('attachment:normal', component=1)
    check('attachment:exact', 'id', component=0)
    retained = check('attachment:exact', 'id', component=1)
    assert len(preview._programs) == 8

    before = (observer.dispatch_count, observer.readback_count, preview.dispatch_count)
    for _ in range(3):
        m.renderFrame()
    assert (observer.dispatch_count, observer.readback_count, preview.dispatch_count) == before
    np.testing.assert_array_equal(last_texture.to_numpy(), retained)
    for args in ({'source': 'field:unknown'}, {'source': 'field:roughness', 'mode': 'id'},
                 {'source': 'attachment:normal', 'mode': 'signed'},
                 {'source': 'field:roughness', 'low': float('nan')},
                 {'source': 'field:baseColor', 'component': True}):
        try:
            preview.render(**args)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid preview request accepted: '+repr(args))
        assert (observer.dispatch_count, observer.readback_count, preview.dispatch_count) == before
    np.testing.assert_array_equal(last_texture.to_numpy(), retained)

    original_codec = artifacts.codec.read_bytes()
    try:
        artifacts.codec.write_bytes(original_codec+b'\n// temporary stale-contract rejection probe\n')
        try:
            preview.render('field:roughness')
        except ValueError as error:
            assert 'modified' in str(error) or 'mismatch' in str(error), str(error)
        else:
            raise AssertionError('Modified generated codec was accepted')
        assert (observer.dispatch_count, observer.readback_count, preview.dispatch_count) == before
        np.testing.assert_array_equal(last_texture.to_numpy(), retained)
    finally:
        artifacts.codec.write_bytes(original_codec)
    check('field:roughness')

    old_texture = last_texture
    m.resizeFrameBuffer(96, 54)
    m.renderFrame()
    snapshot = observer.inspect([0, 0, 96, 54])
    last_texture = None
    check('field:roughness')
    assert last_texture is not old_texture
    assert (old_texture.width, old_texture.height) == (128, 72)
    assert len(preview._programs) == 1, 'Resize retained old-sized program bindings'
    successful_dispatches = preview.dispatch_count
    preview.close()
    preview.close()
    assert len(preview._programs) == 0 and preview._texture is None
    try:
        preview.render('field:roughness')
    # Mogwai imports falcor.* into script globals, shadowing builtin RuntimeError.
    except builtins.RuntimeError as error:
        assert 'closed' in str(error)
    else:
        raise AssertionError('Closed preview accepted GPU work')
    assert preview.dispatch_count == successful_dispatches
    result.update(status='passed', preview_dispatches=successful_dispatches,
        observer_readbacks=observer.readback_count, gpu_full_integer_precision=True,
        preview_does_not_invoke_observer_readback=True, idle_no_preview_work=True,
        same_size_texture_reused=True, resized_texture_verified=True, bound_program_cache=True,
        uniform_range_reuses_program=True, invalid_request_preserves_picture=True,
        stale_contract_preserves_picture=True, closed_state_verified=True)
except Exception:
    result['status'] = 'failed'
    result['traceback'] = traceback.format_exc()
    (out/'traceback.txt').write_text(result['traceback'], encoding='utf-8')
    print(result['traceback'], flush=True)
finally:
    for owned in (preview, attachment):
        if owned is not None:
            try:
                owned.close()
            except Exception:
                result.setdefault('cleanup_errors', []).append(traceback.format_exc())
                result['status'] = 'failed'
    if arrays:
        try:
            np.savez_compressed(out/'arrays.npz', **arrays)
            result['arrays'] = str(out/'arrays.npz')
        except Exception:
            result['status'] = 'failed'
            result['evidence_error'] = traceback.format_exc()
    (out/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('NATIVE_SCHEMA_PREVIEW_'+result['status'].upper()+' '+str(out/'result.json'), flush=True)
exit()
