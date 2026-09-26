"""Retain unchanged original CPU LUT generation and record the authored GPU port."""
import hashlib
import json
from pathlib import Path
import subprocess

from export_sky_light_source import select_lines

ROOT = Path(__file__).resolve().parents[2]
ENGINE = Path('E:/ue/engine/UnrealEngine')
DEST = ROOT / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/SkyLight'


def export(dest=DEST):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {
        'engine': subprocess.check_output(['git', '-C', str(ENGINE), 'rev-parse', 'HEAD'], text=True).strip(),
        'implementation': 'GPU port of the original CPU algorithm',
        'capture_inputs': False,
        'contract': {'extent': [128, 32], 'format': 'RG16Unorm', 'sample_count': 128,
                     'coordinates': ['pixel-center NoV along x', 'pixel-center Roughness along y'],
                     'sampler': 'bilinear clamp', 'rounding': 'floor(clamp(AB,0,1)*65535+0.5)',
                     'source_format_selection': 'PF_G16R16 when supported and filterable, otherwise PF_R8G8'},
        'port_changes': [
            'CPU nested texel loops become independent GPU threads; dimensions remain128x32.',
            'FVector3f operations retain precise FP32 association; declaration explicitly selects floating_point_mode=precise.',
            'SourceCPUFloatDivide/Sqrt correct hardware seeds through exact FP64 midpoint comparisons, then return one FP32 result per original source operation.',
            'SourceCPUFloatCos uses range reduction and degree28 factorial Taylor coefficients in FP64, then returns FP32. All128 original phases match native UCRT cosf; broad mathematical accuracy is tested independently. It is not a general bit-identical replacement for UCRT at every argument.',
            'ReverseBits double fraction maps to an exact FP32 fraction for all128 source samples.',
            'Unused C integration and unused local CosPhi/SinPhi variables are omitted; neither affects A/B.',
            'Source integer UNORM16 rounding is explicit; GPU UAV storage receives normalized exact codes.',
            'Additional RG32Float diagnostic exposes prequantized A/B; it is not consumed by EnvBRDF.',
            'GPU transcendentals are not presumed bit-identical to FMath; smoke records every quantized mismatch.',
        ],
        'not_substituted': ['AmbientCubemapComposite.usf::IntegrateBRDF (64 randomized samples)',
                            'BRDF.ush::EnvBRDFApprox', 'PreintegratedSkin LUT'],
        'excerpts': [], 'outputs': [],
    }
    chunks = [
        ('Engine/Source/Runtime/Renderer/Private/SystemTextures.cpp', 534, 671,
         '// The PreintegratedGF maybe used on forward shading including mobile platform, initialize it anyway.', '}'),
        ('Engine/Source/Runtime/Renderer/Private/IndirectLightRendering.cpp', 756, 757,
         'OutParameters.PreIntegratedGF = GSystemTextures.PreintegratedGF->GetRHI();',
         'OutParameters.PreIntegratedGFSampler = TStaticSamplerState<SF_Bilinear, AM_Clamp, AM_Clamp, AM_Clamp>::GetRHI();'),
    ]
    output = bytearray(b'// Copyright Epic Games, Inc. All Rights Reserved.\n'
                       b'// Unchanged original CPU source evidence; not compiled as shader code.\n')
    name = 'PreintegratedGFCPUOriginal.inl'
    for relative, first, last, beginning, ending in chunks:
        path = ENGINE / relative
        source = path.read_bytes()
        offset, chunk = select_lines(source, first, last, beginning, ending)
        output.extend(b'\n')
        manifest['excerpts'].append({'source': str(path), 'line': first, 'end_line': last,
            'source_sha256': hashlib.sha256(source).hexdigest(), 'excerpt_sha256': hashlib.sha256(chunk).hexdigest(),
            'byte_offset': offset, 'bytes': len(chunk), 'output': name, 'output_byte_offset': len(output)})
        output.extend(chunk)
    (dest / name).write_bytes(output)
    manifest['outputs'].append({'path': name, 'sha256': hashlib.sha256(output).hexdigest()})
    shader = DEST / 'PreintegratedGF.slang'
    manifest['port_sha256'] = hashlib.sha256(shader.read_bytes()).hexdigest()
    manifest['math_adapter_sha256'] = hashlib.sha256((DEST / 'PreintegratedGFSourceMath.slangh').read_bytes()).hexdigest()
    (dest / 'PreintegratedGFSource.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (dest / 'PreintegratedGFSourceNotice.txt').write_text(
        'Original source copyright Epic Games, Inc. All Rights Reserved.\n'
        'The CPU excerpt is unchanged source evidence from the configured local engine.\n'
        'PreintegratedGF.slang is an authored GPU port of its A/B algorithm, not a verbatim UE shader.\n'
        'This metadata is provenance, not a license grant or a rendering-parity claim.\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    export()
