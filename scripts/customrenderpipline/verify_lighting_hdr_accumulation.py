"""Bound native HDR accumulation using saved, unexposed per-light RGB lobes.

This is a Mesh HDR accumulation check conditioned on independently rendered
single-light GPU debug lobes, not a whole-image BRDF oracle. It covers the
non-dual-normal front/back/two graphs only, not Adapter or dual-normal HDR.
Each float32 radiance is bracketed by adjacent representable half values
to cover the source-format conversion; each subsequent half-target addition is
bracketed again. Bounds therefore cover retained float32 or half source precision
without selecting a device-specific blend rounding formula. They are fixed by
the target format and never fitted to measured errors. The strict Capture gate
remains bitwise and separate. Missing-light/transmission mutants must be rejected.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def record(path):
    path = Path(path).resolve()
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def half_bracket(lower, upper):
    """Outward neighboring half values also enclose unrounded finite inputs."""
    lo = np.nextafter(np.asarray(lower, dtype=np.float16), np.float16(-np.inf)).astype(np.float64)
    hi = np.nextafter(np.asarray(upper, dtype=np.float16), np.float16(np.inf)).astype(np.float64)
    if not np.isfinite(lo).all() or not np.isfinite(hi).all():
        raise ValueError('This acceptance does not cover half overflow')
    assert np.all(lo <= lower) and np.all(hi >= upper)
    return lo, hi


def radiance(arrays, exposure, transmission=True):
    assert np.isfinite(exposure) and exposure > 0
    for name in ('directDiffuse', 'directSpecular', 'directTransmission'):
        source = arrays['Lighting.' + name]
        assert source.dtype == np.float32 and source.ndim == 3 and source.shape[-1] == 4
        assert np.isfinite(source).all() and np.all(source[..., :3] >= 0)
    diffuse = arrays['Lighting.directDiffuse'][..., :3].astype(np.float64)
    specular = arrays['Lighting.directSpecular'][..., :3].astype(np.float64)
    transmitted = arrays['Lighting.directTransmission'][..., :3].astype(np.float64) if transmission else 0.
    # Double arithmetic avoids copying a guessed GPU f32 instruction ordering.
    value = (specular + (diffuse + transmitted)) * exposure
    # Three rounded positive-domain operations in the production expression.
    # Use four float32 ulps conservatively before conversion; not a fitted budget.
    magnitude = np.abs(specular) + np.abs(diffuse) + np.abs(transmitted)
    error = 4*np.spacing(np.asarray(magnitude*exposure, dtype=np.float32)).astype(np.float64)
    assert np.isfinite(value).all() and np.all(error >= 0)
    return half_bracket(value-error, value+error)


def accumulation_bounds(base, lights, exposure, transmission=True):
    lower = upper = base[..., :3].astype(np.float64)
    for light in lights:
        source_lo, source_hi = radiance(light, exposure, transmission)
        lower, upper = half_bracket(lower+source_lo, upper+source_hi)
    return lower, upper


def outside(value, lower, upper):
    rgb = value[..., :3].astype(np.float64)
    return np.any((rgb < lower) | (rgb > upper) | ~np.isfinite(rgb), axis=-1)


def main(path, output=None):
    path = Path(path).resolve()
    evidence = json.loads(path.read_text(encoding='utf-8'))
    assert evidence['status'] == 'passed'
    selected = {run['name']: run for run in evidence['runs'] if run['kind'] == 'mesh'
                and run['name'] in ('zero', 'front', 'back', 'two')}
    assert set(selected) == {'zero', 'front', 'back', 'two'}
    images, records = {}, []
    for name, run in selected.items():
        item = run['output']
        actual = record(item['path'])
        assert actual['sha256'] == item['sha256'] and actual['bytes'] == item['bytes']
        records.append(actual)
        with np.load(item['path'], allow_pickle=False) as arrays:
            images[name] = {key: arrays[key].copy() for key in arrays.files}
    base = images['zero']['sceneColor']
    assert base.dtype == np.float16
    for image in images.values():
        assert np.array_equal(image['sceneColor'].view(np.uint16), base.view(np.uint16))
    exposure = float(selected['two']['observed']['actualPipeline']['Lighting']['preExposure'])
    assert np.isfinite(exposure) and exposure > 0
    for name, image in images.items():
        assert float(selected[name]['observed']['actualPipeline']['Lighting']['preExposure']) == exposure
        actual = image['Lighting.lightingColor']
        assert actual.dtype == np.float16 and actual.shape == base.shape and np.isfinite(actual).all()
        for lobe in ('directDiffuse', 'directSpecular', 'directTransmission'):
            assert image['Lighting.' + lobe].shape == base.shape
    checks = []
    for name, light_names in (('front', ['front']), ('back', ['back']), ('two', ['front', 'back'])):
        inputs = [images[light] for light in light_names]
        lower, upper = accumulation_bounds(base, inputs, exposure)
        actual = images[name]['Lighting.lightingColor']
        bad = outside(actual, lower, upper)
        assert not np.any(bad), (name, int(np.count_nonzero(bad)), np.argwhere(bad)[:12].tolist())
        assert actual[..., 3].tobytes() == base[..., 3].tobytes()
        background = images[name]['coverage'] == 0
        assert actual[background].tobytes() == base[background].tobytes()
        # A replacement computed with the transmission omitted is rejected even
        # allowing the same full conversion/rounding interval on the mutant.
        mutant_lo, mutant_hi = accumulation_bounds(base, inputs, exposure, transmission=False)
        mutant_disjoint = np.any((mutant_hi < lower) | (mutant_lo > upper), axis=-1)
        checks.append({'name': name, 'full_buffer_pixels': int(bad.size), 'outside_bound_pixels': 0,
                       'alpha_background_exact': True,
                       'maximum_interval_width': float(np.max(upper-lower)),
                       'missing_transmission_disjoint_interval_pixels': int(np.count_nonzero(mutant_disjoint))})
        if name == 'two':
            missing_light = outside(images['front']['Lighting.lightingColor'], lower, upper)
            assert np.count_nonzero(missing_light) > 1000, 'Second-light mutant is not distinguishable'
            assert np.count_nonzero(mutant_disjoint) > 1000, 'Transmission mutant is not distinguishable'
            checks[-1]['missing_second_light_rejected_pixels'] = int(np.count_nonzero(missing_light))
    result = {'status': 'bounded-hdr-accumulation-passed', 'scope': __doc__,
              'input_report': record(path), 'inputs': records, 'script': record(__file__),
              'pre_exposure': exposure, 'checks': checks, 'capture_equivalence': False,
              'half_bits_exact_proven': False, 'full_image_brdf_oracle_proven': False,
              'full_goal_complete': False}
    target = Path(output).resolve() if output else path.parent/'hdr-accumulation-bounds.json'
    assert not target.exists(), 'Do not overwrite earlier evidence'
    target.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'report':str(target),'sha256':record(target)['sha256'],'checks':checks}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.report, args.output)
