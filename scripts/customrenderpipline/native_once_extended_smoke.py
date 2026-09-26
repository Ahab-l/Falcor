"""Q1 native once replacement/default-execution and retained GF GPU acceptance.

Run with Mogwai --script, or use --cpu-check with ordinary Python (no Falcor).
Each invocation owns a fresh evidence directory and never edits retained shaders.
"""
import copy
import ctypes
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts/customrenderpipline'
GF_SOURCE = ROOT / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/SkyLight'
sys.path.insert(0, str(SCRIPTS))
if 'm' in globals():
    # This directory contains Mogwai's CPython 3.10 NumPy, not ordinary
    # system-Python extension modules (the CPU-only runner may use Python 3.13).
    sys.path.insert(1, str(ROOT / 'build/m0-evidence/python'))

REPLACEMENT_GENERATOR = '''RWTexture2D<uint> result;
cbuffer Params { uint value; };
[numthreads(4,4,1)] void main(uint3 p:SV_DispatchThreadID) {
    if (p.x < 8 && p.y < 8) result[p.xy] = value + 1000 + p.x + 8*p.y;
}
[numthreads(4,4,1)] void alternate(uint3 p:SV_DispatchThreadID) {
    if (p.x < 8 && p.y < 8) result[p.xy] = value + 2000 + p.x + 8*p.y;
}
'''

GF_CONSUMER = '''RWTexture2D<float2> sharedGF;
RWTexture2D<float2> sharedAB;
RWTexture2D<float2> observedGF;
RWTexture2D<float2> observedAB;
[numthreads(8,8,1)] void main(uint3 p:SV_DispatchThreadID) {
    if (p.x >= 128 || p.y >= 32) return;
    observedGF[p.xy] = sharedGF[p.xy];
    observedAB[p.xy] = sharedAB[p.xy];
    sharedGF[p.xy] = float2(1.0, 0.0);
    sharedAB[p.xy] = float2(-123.0, 456.0);
}
'''


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require_count(observed, expected, label):
    if observed != expected:
        raise AssertionError(f'{label}: dispatch count {observed}, expected {expected}')


def require_bytes(observed, expected, label):
    if observed != expected:
        raise AssertionError(f'{label}: raw bytes differ: {digest(observed)} != {digest(expected)}')


def cpu_reference(out, report):
    """Unmodified independent FP32 oracle; never upload its values to the GPU."""
    from sky_light_brdf_reference import integrate_reference, unorm16_codes

    reference = integrate_reference()
    codes = unorm16_codes(reference)
    if reference.shape != (32, 128, 2) or reference.dtype != np.float32:
        raise AssertionError('CPU reference must be FP32 128 x 32 RG')
    if not np.isfinite(reference).all() or not (reference >= 0).all():
        raise AssertionError('CPU reference is nonfinite or negative')
    np.testing.assert_array_equal(
        unorm16_codes(np.array([-1, 0, .5, 1, 2], np.float32)), [0, 0, 32768, 65535, 65535])
    if not (codes[0, -1, 0] > 65000 and codes[0, -1, 1] < 2 and codes[0, 0, 1] > 50000):
        raise AssertionError('Independent GF endpoint invariants failed')
    # Do not substitute FP64 for the CPU's FP32 contract at grazing roughness.
    double_reference = integrate_reference(dtype=np.float64)
    difference = np.abs(reference - double_reference)
    if tuple(np.unravel_index(difference.argmax(), difference.shape)) != (0, 0, 1):
        raise AssertionError('Unexpected FP32 vs FP64 reference discrepancy location')
    if difference[0, 0, 1] <= 1e-3:
        raise AssertionError('Reference lost source FP32 cancellation behavior')
    native_cosine = {'status': 'not_exercised', 'reason': 'UCRT check requires Windows'}
    if sys.platform == 'win32':
        native = ctypes.CDLL('ucrtbase')
        native.cosf.argtypes = [ctypes.c_float]
        native.cosf.restype = ctypes.c_float
        for index in range(128):
            phase = (np.float32(2) * np.float32(math.pi)) * (np.float32(index) / np.float32(128))
            require_bytes(np.float32(math.cos(float(phase))).tobytes(),
                          np.float32(native.cosf(float(phase))).tobytes(), f'UCRT phase {index}')
        native_cosine = {'status': 'passed', 'phases': 128}
    original = GF_SOURCE / 'PreintegratedGFCPUOriginal.inl'
    manifest = json.loads((GF_SOURCE / 'PreintegratedGFSource.json').read_text(encoding='utf-8'))
    expected_digest = next(item['sha256'] for item in manifest['outputs'] if item['path'] == original.name)
    if digest(original.read_bytes()) != expected_digest:
        raise AssertionError('Retained unchanged CPU excerpt differs from its provenance manifest')
    (out / 'cpu-reference.rg16unorm.bin').write_bytes(codes.astype('<u2').tobytes())
    (out / 'cpu-reference.rg32float.bin').write_bytes(reference.astype('<f4').tobytes())
    report['cpu_reference'] = {
        'status': 'passed', 'shape': list(reference.shape), 'dtype': str(reference.dtype),
        'codes_sha256': digest(codes.tobytes()), 'ab_sha256': digest(reference.tobytes()),
        'fp32_vs_fp64_max_abs': float(difference.max()), 'ucrt_cosine': native_cosine,
        'source_files': {str(path): digest(path.read_bytes()) for path in (
            GF_SOURCE / 'PreintegratedGF.slang', GF_SOURCE / 'PreintegratedGFSourceMath.slangh',
            GF_SOURCE / 'PreintegratedGFSource.json', original, SCRIPTS / 'sky_light_brdf_reference.py')},
    }
    return reference, codes


def cpu_negative_controls(report):
    """Ensure a skipped dispatch, any changed storage bit, and a code error fail."""
    from sky_light_brdf_reference import parity_report
    caught = []
    for label, invoke in (
        ('skipped_default_dispatch', lambda: require_count(1, 2, 'negative control')),
        ('raw_float_bit_changed', lambda: require_bytes(b'\x00\x00\x80\x3f', b'\x01\x00\x80\x3f', 'negative control')),
    ):
        try:
            invoke()
        except AssertionError:
            caught.append(label)
        else:
            raise AssertionError('Negative control did not fail: ' + label)
    expected = np.array([[[10, 20], [30, 40]]], dtype=np.uint16)
    observed = expected.copy()
    observed[0, 1, 0] += 1
    mismatch = parity_report(observed, expected)
    if mismatch['exact'] or mismatch['mismatched_channels'] != 1 or mismatch['max_code_difference'] != 1:
        raise AssertionError('Independent code oracle did not detect one-LSB corruption')
    caught.append('one_lsb_cpu_parity')
    report['cpu_negative_controls'] = {'status': 'passed', 'detected': caught}


def activate(host, graph):
    host.addGraph(graph)
    host.setActiveGraph(graph)


def integer_cases(host, out, report):
    import falcor
    from immutable_compute_cache_fixture import GENERATOR, CONSUMER, declaration
    from pipeline import make_graph

    generator, replacement, consumer = out / 'Generate.slang', out / 'Replacement.slang', out / 'Consume.slang'
    generator.write_text(GENERATOR, encoding='utf-8')
    replacement.write_text(REPLACEMENT_GENERATOR, encoding='utf-8')
    consumer.write_text(CONSUMER, encoding='utf-8')
    authored = declaration(str(generator), str(consumer))
    write_json(out / 'OnceGraph.json', authored)
    graph = make_graph('NativeOnceExtended', out / 'OnceGraph.json')
    activate(host, graph)
    phases = report['integer_cases'] = []
    count = lambda name: int(falcor.customRenderPiplineComputeDispatchCount(graph, name))
    total_frames = 0

    def observe(label, base, expected_generate_count=1):
        nonlocal total_frames
        host.renderFrame()
        total_frames += 1
        entry = {'case': label, 'generator_count': count('Generate'), 'consumer_count': count('Consume')}
        phases.append(entry)
        observed = np.asarray(graph.getOutput('Consume.observed').to_numpy())
        shared = np.asarray(graph.getOutput('Consume.shared').to_numpy())
        (out / (label + '.observed.r32uint.bin')).write_bytes(observed.tobytes())
        (out / (label + '.overwritten.r32uint.bin')).write_bytes(shared.tobytes())
        expected = (np.arange(64, dtype=np.uint32) + base).reshape(8, 8)
        np.testing.assert_array_equal(observed, expected)
        np.testing.assert_array_equal(shared, np.full((8, 8), 999999, dtype=np.uint32))
        require_bytes(observed.tobytes(), expected.tobytes(), label)
        require_count(count('Generate'), expected_generate_count, label)
        require_count(count('Consume'), total_frames, label + ' default consumer')
        entry.update(status='passed', width=8, height=8, restored_before_overwrite=True,
                     observed_sha256=digest(observed.tobytes()))

    require_count(count('Generate'), 0, 'fresh once pass')
    for frame in range(3):
        observe(f'once_initial_{frame}', 17)

    properties = copy.deepcopy(authored['nodes'][0]['properties'])
    for label, mutate, expected in (
        ('uniform_replacement', lambda p: p['uniforms']['Params.value'].update(value=91), 91),
        ('shader_file_replacement', lambda p: p['shader'].update(file=str(replacement)), 1091),
        ('program_entry_replacement', lambda p: p['shader'].update(compute='alternate'), 2091),
    ):
        mutate(properties)  # One property changes at each transition.
        write_json(out / (label + '.properties.json'), properties)
        graph.updatePass('Generate', properties)
        require_count(count('Generate'), 0, label + ' recreated instance')
        for frame in range(3):
            observe(f'{label}_{frame}', expected)

    host.resizeFrameBuffer(23, 19)
    observe('fixed_size_recompile', 2091, expected_generate_count=2)
    observe('fixed_size_recompile_cache_hit', 2091, expected_generate_count=2)
    host.removeGraph(graph)

    # No execution key at all is the default-every-frame contract, not a once
    # declaration updated to explicit every_frame.
    authored = declaration(str(generator), str(consumer), execution=None)
    if 'execution' in authored['nodes'][0]['properties']:
        raise AssertionError('Default mode fixture accidentally specifies execution')
    write_json(out / 'DefaultGraph.json', authored)
    graph = make_graph('NativeDefaultEveryFrame', out / 'DefaultGraph.json')
    activate(host, graph)
    total_frames = 0
    for frame in range(1, 5):
        observe(f'default_every_frame_{frame}', 17, expected_generate_count=frame)
    host.removeGraph(graph)
    report['native_hot_reload'] = {
        'status': 'not_exercised',
        'reason': 'Current Device/ProgramManager/Renderer Python bindings expose no native shader-reload entry point.',
        'covered_instead': ['shader.file replacement via updatePass', 'shader.compute replacement via updatePass'],
        'not_equivalent_to_native_hot_reload': True,
    }


def gf_cases(host, out, report, reference, reference_codes):
    import falcor
    from pipeline import make_graph
    from sky_light_brdf import sky_light_brdf_fragment
    from sky_light_brdf_reference import parity_report

    writer = out / 'GFConsumeAndOverwrite.slang'
    writer.write_text(GF_CONSUMER, encoding='utf-8')
    authored = {'version': 1, 'nodes': [], 'edges': [], 'outputs': []}
    for name, execution in (('OnceGF', 'once'), ('EveryGF', 'every_frame')):
        fragment = sky_light_brdf_fragment(prefix=name)
        node, = fragment['nodes']
        node['properties']['execution'] = execution
        authored['nodes'].append(node)
        ports = []
        for field, fmt in (('GF', 'RG16Unorm'), ('AB', 'RG32Float')):
            for prefix, direction in (('shared', 'inputOutput'), ('observed', 'output')):
                ports.append({'name': prefix + field, 'binding': prefix + field, 'direction': direction,
                              'kind': 'texture2D', 'format': fmt, 'size': [128, 32]})
        consumer = name + 'Consume'
        authored['nodes'].append({'name': consumer, 'type': 'CustomRenderPiplineComputePass',
                                 'properties': {'shader': {'file': str(writer)}, 'resources': ports,
                                                'dispatch': {'threads': [128, 32, 1]}}})
        authored['edges'] += [[name + '.preIntegratedGF', consumer + '.sharedGF'],
                              [name + '.integratedAB', consumer + '.sharedAB']]
        authored['outputs'] += [consumer + '.' + field for field in ('observedGF', 'observedAB', 'sharedGF', 'sharedAB')]
    write_json(out / 'GFGraph.json', authored)
    graph = make_graph('NativeGFOnceVersusEveryFrame', out / 'GFGraph.json')
    activate(host, graph)
    report['gf_cases'] = []
    baseline = {}
    for frame in range(1, 6):
        if frame == 5:
            host.resizeFrameBuffer(31, 21)
        host.renderFrame()
        frame_result = {'frame': frame, 'viewport_recompiled': frame == 5, 'passes': {}}
        report['gf_cases'].append(frame_result)
        current = {}
        for name in ('OnceGF', 'EveryGF'):
            consumer = name + 'Consume'
            count = int(falcor.customRenderPiplineComputeDispatchCount(graph, name))
            result = frame_result['passes'][name] = {'dispatch_count': count}
            require_count(count, (2 if frame == 5 else 1) if name == 'OnceGF' else frame, name)
            require_count(int(falcor.customRenderPiplineComputeDispatchCount(graph, consumer)), frame, consumer)
            # Unorm has no ndarray dtype mapping: to_numpy returns unchanged
            # packed uint8 storage, not normalized values. Decode explicitly.
            texture = graph.getOutput(consumer + '.observedGF')
            if (texture.width, texture.height, texture.format) != (128, 32, falcor.ResourceFormat.RG16Unorm):
                raise AssertionError(name + ': wrong GF texture descriptor')
            gf_bytes = np.asarray(texture.to_numpy()).tobytes()
            ab_bytes = np.asarray(graph.getOutput(consumer + '.observedAB').to_numpy()).tobytes()
            (out / f'gf-{frame}-{name}.rg16unorm.bin').write_bytes(gf_bytes)
            (out / f'gf-{frame}-{name}.rg32float.bin').write_bytes(ab_bytes)
            if len(gf_bytes) != 128 * 32 * 4 or len(ab_bytes) != 128 * 32 * 8:
                raise AssertionError(name + ': unexpected tightly packed storage length')
            codes = np.frombuffer(gf_bytes, '<u2').reshape(32, 128, 2)
            ab = np.frombuffer(ab_bytes, '<f4').reshape(32, 128, 2)
            parity = parity_report(codes, reference_codes)
            write_json(out / f'gf-{frame}-{name}.cpu-code-parity.json', parity)
            result.update(cpu_code_parity=parity, cpu_ab_max_abs=float(np.max(np.abs(ab - reference))),
                          gf_sha256=digest(gf_bytes), ab_sha256=digest(ab_bytes))
            if not parity['exact']:
                raise AssertionError(f'{name}: {parity["mismatched_channels"]} CPU UNORM16 code mismatches')
            # Exact storage-code parity is mandatory; prequantized FP32 diagnostics
            # have a fixed 2e-6 absolute tolerance, selected before GPU execution.
            np.testing.assert_allclose(ab, reference, rtol=0, atol=2e-6)
            poison_gf = np.empty((32, 128, 2), dtype='<u2')
            poison_gf[:] = [65535, 0]
            poison_ab = np.empty((32, 128, 2), dtype='<f4')
            poison_ab[:] = [-123, 456]
            require_bytes(np.asarray(graph.getOutput(consumer + '.sharedGF').to_numpy()).tobytes(),
                          poison_gf.tobytes(), name + ' downstream GF overwrite')
            require_bytes(np.asarray(graph.getOutput(consumer + '.sharedAB').to_numpy()).tobytes(),
                          poison_ab.tobytes(), name + ' downstream AB overwrite')
            current[name] = (gf_bytes, ab_bytes)
            if frame == 1:
                baseline[name] = current[name]
            for index, field in enumerate(('GF', 'AB')):
                require_bytes(current[name][index], baseline[name][index], name + ' immutable ' + field)
            result.update(status='passed', downstream_overwrite_restored_exact=True)
        for index, field in enumerate(('GF', 'AB')):
            require_bytes(current['OnceGF'][index], current['EveryGF'][index], 'once/every_frame ' + field)
        frame_result.update(status='passed', once_every_frame_raw_bytes_exact=True)
    host.removeGraph(graph)


def main(host=None):
    parent = ROOT / 'build/native-framework-completion'
    parent.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='once-extended-' if host is not None else 'once-extended-cpu-', dir=parent))
    print('NATIVE_ONCE_EXTENDED_EVIDENCE ' + str(out), flush=True)
    report = {'status': 'running', 'mode': 'gpu' if host is not None else 'cpu_only',
              'gpu_executed': False, 'evidence_directory': str(out)}
    try:
        global np
        import numpy as np
        reference, codes = cpu_reference(out, report)
        cpu_negative_controls(report)
        if host is not None:
            host.ui = False
            host.resizeFrameBuffer(16, 16)
            report['gpu_executed'] = True
            integer_cases(host, out, report)
            gf_cases(host, out, report, reference, codes)
        report['status'] = 'passed'
    except Exception as error:
        traceback.print_exc()
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
    write_json(out / 'result.json', report)
    marker = 'NATIVE_ONCE_EXTENDED_' + ('PASS' if report['status'] == 'passed' else 'FAIL')
    if host is None:
        marker += '_CPU_ONLY'
    print(marker, flush=True)
    code = 0 if report['status'] == 'passed' else 1
    if host is not None:
        import falcor
        falcor.exit(code)  # SampleApp.shutdown(errorCode), not Python sys.exit().
    return code


if 'm' in globals():
    main(m)
elif __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-check', action='store_true', required=True, help='Validate only the CPU oracle and negative controls')
    parser.parse_args()
    raise SystemExit(main())
