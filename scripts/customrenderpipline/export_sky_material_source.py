"""Extract UE's original sky material without writing to the engine or using captures.

The two orthographic-only material blocks are omitted from a separate perspective
specialization. The original bodies, exact removal ranges, and all shared helper
bytes are retained, so the supported path is reproducible without an algorithm port.
"""
import hashlib
import json
from pathlib import Path
import subprocess

from export_shadow_source import function


ROOT = Path(__file__).resolve().parents[2]
ENGINE = Path('E:/ue/engine/UnrealEngine')
DEST = ROOT / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'
SHADERS = Path('Engine/Shaders/Private')


def export(dest=DEST):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {
        'capture_inputs': False,
        'engine': subprocess.check_output(['git', '-C', str(ENGINE), 'rev-parse', 'HEAD'], text=True).strip(),
        'material': '/Engine/EngineSky/M_SimpleSkyDome',
        'expression': 'SkyAtmosphereViewLuminance + SkyAtmosphereLightDiskLuminance',
        'excerpts': [],
        'outputs': [],
    }

    def output(name, data):
        (dest / name).write_bytes(data)
        manifest['outputs'].append({'path': name, 'sha256': hashlib.sha256(data).hexdigest()})

    def emit(name, entries):
        parts = [b'// Copyright Epic Games, Inc. All Rights Reserved.\n'
                 b'// Exact source excerpts; see UESkyMaterialSource.json and UESkyMaterialThirdPartyNotice.txt.']
        for source, signature, mode in entries:
            path = ENGINE / source
            data = path.read_bytes()
            if mode == 'line':
                start = data.index(signature.encode())
                chunk = data[start:data.index(b'\n', start)].rstrip(b'\r')
            else:
                chunk = function(data, signature)
                start = data.index(chunk)
            parts.append(chunk)
            manifest['excerpts'].append({
                'output': name, 'source': str(path), 'signature': signature,
                'byte_offset': start, 'bytes': len(chunk), 'line': data[:start].count(b'\n') + 1,
                'source_sha256': hashlib.sha256(data).hexdigest(),
                'excerpt_sha256': hashlib.sha256(chunk).hexdigest(),
            })
        data = b'\n\n'.join(parts) + b'\n'
        output(name, data)
        return data

    def shader(file, *signatures):
        return [(SHADERS / file, signature, 'function') for signature in signatures]

    emit('UESkyMaterialHelpers.ush', [
        *shader('FastMathThirdParty.ush', 'float acosFast4(', 'float atan2Fast('),
        *shader('Common.ush', 'float2 RayIntersectSphere('),
        *shader('SkyAtmosphereCommon.ush', 'float2 FromUnitToSubUvs(',
                'void getTransmittanceLutUvs(', 'void SkyViewLutParamsToUv(',
                'float3x3 GetSkyViewLutReferential(', 'float3 DecodeTransmittance(',
                'float3 GetAtmosphereTransmittance(', 'float3 GetLightDiskLuminance('),
        *shader('RandomPCG.ush', 'uint3 Rand3DPCG16(', 'float Rand16ToFloat(uint Rand16Bits)'),
        *shader('RandomInterleavedGradientNoise.ush', 'float InterleavedGradientNoise('),
        *[(SHADERS / 'Quantization.ush', signature, 'line') for signature in (
            '#define QUANTIZE_NOISE_TYPE', '#define QUANTIZE_NOISE_HAMMERSLEY',
            '#define QUANTIZE_NOISE_INTERLEAVEDGRADIENT')],
        *shader('Quantization.ush',
                'float3 QuantizeFloatColor(in float3 Color, in float3 QuantizationError, in float E)',
                'float3 QuantizeFloatColor(in float3 Color, in float3 QuantizationError, in float2 Pos2D,'),
        *[(Path('Engine/Shaders/Shared/EnvironmentComponentsFlags.h'), signature, 'line') for signature in (
            '#define ENVCOMP_FLAG_SKYATMOSPHERE_RENDERINMAIN', '#define IsSkyAtmosphereRenderedInMain(')],
    ])

    original_name = 'UESkyMaterialOriginal.ush'
    original = emit(original_name, shader('MaterialTemplate.ush',
        'float3 MaterialExpressionSkyAtmosphereLightDiskLuminance(',
        'float3 MaterialExpressionSkyAtmosphereViewLuminance('))
    removals = []
    for marker in (b'if (IsOrthoProjection())', b'if(IsOrthoProjection())'):
        if original.count(marker) != 1:
            raise ValueError('Original sky material orthographic branch changed')
        chunk = function(original, marker.decode())
        start = original.index(chunk)
        removals.append({'byte_offset': start, 'bytes': len(chunk), 'sha256': hashlib.sha256(chunk).hexdigest()})
    perspective = original
    for entry in sorted(removals, key=lambda item: item['byte_offset'], reverse=True):
        start = entry['byte_offset']
        perspective = perspective[:start] + perspective[start + entry['bytes']:]
    perspective_name = 'UESkyMaterialPerspective.ush'
    output(perspective_name, perspective)
    manifest['specialization'] = {
        'original': original_name, 'output': perspective_name,
        'supported_projection': 'perspective',
        'unsupported_branches': ['orthographic', 'reflection_capture', 'primitive_alpha_holdout'],
        'removed_ranges': removals,
        'defines': {'MATERIAL_SKY_ATMOSPHERE': 1, 'PROJECT_SUPPORT_SKY_ATMOSPHERE': 1,
                    'SUPPORT_PRIMITIVE_ALPHA_HOLDOUT': 0},
        'view_contract': {'RenderingReflectionCaptureMask': 0, 'RealTimeReflectionCapture': 0,
                          'EnvironmentComponentsFlags': [8, 0, 0, 0]},
    }

    emit('UESkyMaterialQuantizationOriginal.inl', [(
        Path('Engine/Source/Runtime/Renderer/Private/Quantization.cpp'),
        'FVector3f ComputePixelFormatQuantizationError(', 'function')])
    thirdparty = (ENGINE / SHADERS / 'FastMathThirdParty.ush').read_bytes()
    output('UESkyMaterialThirdPartyNotice.txt', thirdparty[:thirdparty.index(b'// Normalized range')])
    (dest / 'UESkyMaterialSource.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    export()
