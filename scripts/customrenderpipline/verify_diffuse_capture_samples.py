"""Strict regression for the 43 observed UE diffuseColor/diffuse samples.

This reads the complete accepted alpha-only UE replay and a native local-export
NPZ only after rendering. It tests observed values, not a proposed formula.
It does not certify unrelated native buffers or full-image HDR equivalence.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
UE_RUN = ROOT / 'build/lighting-dxil-prefix-generations/replay-oweg0_0j'
UE_PLAN = ROOT / 'build/lighting-dxil-prefix-generations/run-himx4c4v/plan.json'
CHECKER = ROOT / 'build/compare-lighting-dxil-prefix-v2.py'


def record(path):
    path = Path(path).resolve()
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def compare(path):
    spec = importlib.util.spec_from_file_location('accepted_ue_replay', CHECKER)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    reader = checker.Reader()
    plan, _, selection, raw = checker.load_replay(UE_RUN, UE_PLAN, reader)
    points = selection['selected_pixels_xy']
    with np.load(path, allow_pickle=False) as source:
        diffuse = source['directDiffuse'].copy()
        local = source['directTransmission'].copy()
    if diffuse.dtype != np.float32 or local.dtype != np.float32 or diffuse.shape != local.shape:
        raise ValueError('Expected equal-shape float32 native local and diffuse images')
    if local.ndim != 3 or local.shape[2] != 4 or not all(x < local.shape[1] and y < local.shape[0] for x, y in points):
        raise ValueError('Invalid image shape or sample extent')
    stages = []
    for name, image, channel in [('diffuseColor_r', local, 0)] + [
        ('directDiffuse_' + component, diffuse, index) for index, component in enumerate('rgb')]:
        rows = []
        for (x, y), ue in zip(points, raw[name]):
            actual = image[y, x, channel]
            if not np.isfinite(actual):
                raise ValueError('Nonfinite native observation')
            native_bits = int(actual.view(np.uint32))
            expected_bits = ue['shaderOut']['uint32'][3]
            rows.append({'xy': [x, y], 'native_bits': native_bits, 'ue_bits': expected_bits,
                         'bitwise_equal': native_bits == expected_bits})
        stages.append({'name': name, 'compared': len(rows),
                       'equal': sum(p['bitwise_equal'] for p in rows), 'points': rows})
    total = sum(s['compared'] for s in stages)
    same = sum(s['equal'] for s in stages)
    if total != 172:
        raise ValueError('Incomplete fixed regression')
    return {'status': 'passed' if same == total else 'differences',
            'native_npz': record(path), 'ue_plan': record(UE_PLAN),
            'ue_report': record(UE_RUN / 'result.json'), 'checker': record(CHECKER),
            'test': record(__file__), 'total_compared': total, 'total_equal': same,
            'stages': stages, 'capture_equivalence': False, 'full_goal_complete': False,
            'scope': __doc__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_npz', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Refusing to overwrite a regression record')
    result = compare(args.native_npz)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'report': record(args.output), 'status': result['status'],
                      'total_equal': result['total_equal'], 'total_compared': result['total_compared'],
                      'stages': [{k: v for k, v in stage.items() if k != 'points'} for stage in result['stages']]}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
