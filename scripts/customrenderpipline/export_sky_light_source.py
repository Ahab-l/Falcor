"""Extract reviewed, unchanged UE SkyLight regions from the read-only engine.

Downsample and Filter contain alternate compute/pixel opening braces followed by
one shared body. A brace-only function extractor truncates these algorithms.
Reviewed line bounds, boundary checks, balanced conditionals, and byte hashes
retain the complete regions, including inactive paths and attribution comments.
These files are source evidence; exporting them does not establish runtime support.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
ENGINE = Path('E:/ue/engine/UnrealEngine')
DEST = ROOT / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'
SHADERS = Path('Engine/Shaders/Private')
REFLECTION = SHADERS / 'ReflectionEnvironmentShaders.usf'
NATIVE = Path('Engine/Source/Runtime/Renderer/Private/ReflectionEnvironmentRealTimeCapture.cpp')
PLATFORM = Path('Engine/Shaders/Public/Platform.ush')
COMPILER = Path('Engine/Source/Developer/Windows/ShaderFormatD3D/Private/ShaderFormatD3D.cpp')


def select_lines(data, first, last, beginning, ending):
    """Select complete source lines without newline normalization or preprocessing."""
    lines = data.splitlines(keepends=True)
    if not 1 <= first <= last <= len(lines):
        raise ValueError(f'Source range {first}-{last} is outside the file')
    selected = lines[first - 1:last]
    if selected[0].strip() != beginning.encode() or selected[-1].strip() != ending.encode():
        raise ValueError(f'Reviewed source boundaries changed at lines {first}-{last}')
    chunk = b''.join(selected)
    depth = 0
    for directive in re.findall(rb'^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b', chunk, re.MULTILINE):
        if directive in (b'if', b'ifdef', b'ifndef'):
            depth += 1
        elif directive == b'endif':
            depth -= 1
        elif depth == 0:
            raise ValueError(f'Orphan conditional branch in source lines {first}-{last}')
        if depth < 0:
            raise ValueError(f'Orphan #endif in source lines {first}-{last}')
    if depth:
        raise ValueError(f'Incomplete conditional in source lines {first}-{last}')
    return sum(map(len, lines[:first - 1])), chunk


def export(dest=DEST):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {
        'capture_inputs': False,
        'runtime_support_established': False,
        'engine': subprocess.check_output(['git', '-C', str(ENGINE), 'rev-parse', 'HEAD'], text=True).strip(),
        'extraction': 'Verbatim reviewed line regions; no preprocessing, algorithm pruning, or token rewriting.',
        'native_contract': {
            'scope': 'PC compute path in ReflectionEnvironmentRealTimeCapture.cpp',
            'sampler': 'SF_Point',
            'mipgen': {'source_view_mip': 'MipIndex - 1', 'shader_lod': 0,
                       'destination_view': 'same cube, selected mip as Texture2DArray UAV', 'tap_count': 9},
            'filter': {'source_view': 'full source cubemap mip chain',
                       'destination_view': 'separate convolved cubemap, selected mip as Texture2DArray UAV',
                       'sample_counts': [32, 64], 'sharp_path': 'Roughness < 0.01 copies source LOD 0'},
            'diffuse_sh': {'source': 'convolved cubemap', 'mip': 'log2(capture_width) - 4',
                           'thread_group_size': [8, 8, 1], 'dispatch_groups': [1, 1, 1],
                           'sample_count': 64, 'uniform_sample_solid_angle': '4 * PI / 64',
                           'output_float4_count': 8, 'brightness_index': 7,
                           'output_binding': 'RWStructuredBuffer<float4> OutIrradianceEnvMapSH'},
            'precision': {'half_alias': 'float', 'material_float_alias': 'float',
                          'excerpt_tokens_rewritten': False,
                          'per_shader_allow_real_types': False,
                          'evidence': 'The three native shader classes do not enable CFLAG_AllowRealTypes. '
                                      'D3D gates real types on that flag; Platform.ush retains the exact '
                                      'half-to-float branch and relaxed-precision/real-type defaults. '
                                      'Common.ush retains the MaterialFloat compute alias.'},
        },
        'integration_gaps': [
            'RWStructuredBuffer<float4> UAV binding for OutIrradianceEnvMapSH needs runtime integration and validation.',
            'Original SHCommon.ush and MonteCarlo.ush include directives remain unchanged; a source include adapter is needed.',
            'A runtime wrapper must supply the evidenced PC precision aliases, shader macros, bindings, and dispatch state.',
            'These excerpts are unregistered source evidence; they have not been compiled or GPU-validated by this exporter.',
        ],
        'excerpts': [],
        'outputs': [],
    }
    sources = {}

    def region(source, first, last, signature, ending='}', beginning=None):
        return source, first, last, signature, beginning or signature, ending

    def emit(name, entries, purpose='shader source excerpts', preamble=None):
        result = bytearray(preamble or (
            b'// Copyright Epic Games, Inc. All Rights Reserved.\n'
            b'// Exact source excerpts; see UESkyLightSource.json and UESkyLightSourceNotice.txt.\n'
            b'// Source evidence only; runtime integration is not established.\n'))
        for source, first, last, signature, beginning, ending in entries:
            path = ENGINE / source
            if path not in sources:
                sources[path] = path.read_bytes()
            data = sources[path]
            try:
                start, chunk = select_lines(data, first, last, beginning, ending)
            except ValueError as error:
                raise ValueError(f'{path}: {error}') from error
            if signature.encode() not in chunk:
                raise ValueError(f'{path}:{first}-{last}: missing reviewed signature {signature}')
            result.extend(b'\n')
            output_offset = len(result)
            result.extend(chunk)
            manifest['excerpts'].append({
                'output': name, 'source': str(path), 'signature': signature,
                'byte_offset': start, 'bytes': len(chunk), 'line': first, 'end_line': last,
                'output_byte_offset': output_offset,
                'source_sha256': hashlib.sha256(data).hexdigest(),
                'excerpt_sha256': hashlib.sha256(chunk).hexdigest(),
            })
        (dest / name).write_bytes(result)
        manifest['outputs'].append({'path': name, 'purpose': purpose, 'sha256': hashlib.sha256(result).hexdigest()})

    emit('UESkyLightCubeCommon.ush', [
        region(REFLECTION, 11, 15,
               '#if defined(DXC_GROUPSHARED_ALIGNMENT_WORKAROUND) && DXC_GROUPSHARED_ALIGNMENT_WORKAROUND', '#endif'),
        region(REFLECTION, 99, 130, 'float3 GetCubemapVector(float2 ScaledUVs, int InCubeFace)'),
        region(REFLECTION, 188, 189, 'TextureCube SourceCubemapTexture;', 'SamplerState SourceCubemapSampler;'),
        region(REFLECTION, 245, 267, 'uint MipIndex;', '#endif'),
    ])
    emit('UESkyLightDownsample.ush', [
        region(REFLECTION, 269, 332, 'void DownsampleCS(uint3 ThreadId : SV_DispatchThreadID)', beginning='#ifdef USE_COMPUTE'),
    ])
    emit('UESkyLightFilter.ush', [
        region(REFLECTION, 501, 651, 'void FilterCS(uint3 ThreadId : SV_DispatchThreadID)', beginning='#if SHADING_PATH_MOBILE'),
    ])
    emit('UESkyLightDiffuseSH.ush', [
        region(REFLECTION, 857, 1014, '#ifdef SHADER_DIFFUSE_TO_SH', '#endif'),
    ])
    emit('UESkyLightHelpers.ush', [
        region(SHADERS / 'Common.ush', 133, 133, 'const static MaterialFloat PI = 3.1415926535897932f;',
               'const static MaterialFloat PI = 3.1415926535897932f;'),
        region(SHADERS / 'Common.ush', 1074, 1077, 'float Pow2( float x )'),
        region(SHADERS / 'Common.ush', 1114, 1118, 'float Pow4( float x )'),
        region(SHADERS / 'MonteCarlo.ush', 11, 23, 'float3x3 GetTangentBasis( float3 TangentZ )',
               beginning='// [ Duff et al. 2017, "Building an Orthonormal Basis, Revisited" ]'),
        region(SHADERS / 'MonteCarlo.ush', 58, 63, 'float2 Hammersley( uint Index, uint NumSamples, uint2 Random )'),
        region(SHADERS / 'MonteCarlo.ush', 213, 228, 'float4 UniformSampleSphere( float2 E )', beginning='// PDF = 1 / (4 * PI)'),
        region(SHADERS / 'MonteCarlo.ush', 247, 262, 'float4 CosineSampleHemisphere( float2 E )', beginning='// PDF = NoL / PI'),
        region(SHADERS / 'MonteCarlo.ush', 367, 384, 'float4 ImportanceSampleGGX( float2 E, float a2 )', beginning='// PDF = D * NoH / (4 * VoH)'),
        region(SHADERS / 'BRDF.ush', 309, 315, 'float D_GGX( float a2, float NoH )', beginning='// GGX / Trowbridge-Reitz'),
        region(SHADERS / 'ReflectionEnvironmentShared.ush', 16, 17, '#define REFLECTION_CAPTURE_ROUGHEST_MIP 1',
               '#define REFLECTION_CAPTURE_ROUGHNESS_MIP_SCALE 1.2'),
        region(SHADERS / 'ReflectionEnvironmentShared.ush', 35, 39,
               'float ComputeReflectionCaptureRoughnessFromMip(float Mip, half CubemapMaxMip)'),
        region(SHADERS / 'SHCommon.ush', 37, 54, 'struct FThreeBandSHVector', '};',
               '/** The SH coefficients for the projection of a function that maps directions to scalar values. */'),
        region(SHADERS / 'SHCommon.ush', 96, 103, 'FThreeBandSHVector MulSH3(FThreeBandSHVector A, half Scalar)'),
        region(SHADERS / 'SHCommon.ush', 121, 128, 'FThreeBandSHVector AddSH3(FThreeBandSHVector A, FThreeBandSHVector B)'),
        region(SHADERS / 'SHCommon.ush', 130, 137, 'FThreeBandSHVectorRGB AddSH3(FThreeBandSHVectorRGB A, FThreeBandSHVectorRGB B)'),
        region(SHADERS / 'SHCommon.ush', 232, 249, 'FThreeBandSHVector SHBasisFunction3(half3 InputVector)'),
    ])
    emit('UESkyLightNativeSetupOriginal.inl', [
        region(NATIVE, 82, 179, 'class FDownsampleCubeFaceCS : public FGlobalShader',
               'IMPLEMENT_GLOBAL_SHADER(FComputeSkyEnvMapDiffuseIrradianceCS, "/Engine/Private/ReflectionEnvironmentShaders.usf", "ComputeSkyEnvMapDiffuseIrradianceCS", SF_Compute);'),
        region(NATIVE, 1038, 1186,
               'auto RenderCubeFaces_GenCubeMips = [&](uint32 CubeMipStart, uint32 CubeMipEnd, TRefCountPtr<IPooledRenderTarget>& SkyRenderTarget)', '};'),
        region(NATIVE, 1274, 1283, 'RenderCubeFaces_SkyCloud(true, true, CapturedSkyRenderTarget, 0, CubeFace_MAX);',
               'RenderCubeFaces_DiffuseIrradiance(ConvolvedSkyRenderTarget[ConvolvedSkyRenderTargetReadyIndex]);'),
    ], 'read-only native shader classes, complete setup lambdas, and source/destination call statements')
    emit('UESkyLightPlatformOriginal.ush', [
        region(PLATFORM, 257, 263, '#ifndef PLATFORM_SUPPORTS_REAL_TYPES', '#endif'),
        region(PLATFORM, 338, 374, '// ---------------------------------------------------- Alternative floating point types', '#endif'),
        region(SHADERS / 'Common.ush', 13, 32,
               '// These types are used for material translator generated code, or any functions the translated code can call', '#endif'),
    ], 'read-only original precision alias conditionals')
    emit('UESkyLightCompilerOriginal.inl', [
        region(COMPILER, 204, 274, 'void ModifyShaderCompilerInput(FShaderCompilerInput& Input) const final'),
    ], 'read-only complete D3D compiler input method documenting real-type opt-in')

    copyright_line = '// Copyright Epic Games, Inc. All Rights Reserved.'
    notice_sources = sorted(sources, key=str)
    emit('UESkyLightSourceNotice.txt', [
        region(path.relative_to(ENGINE), 1, 1, copyright_line, copyright_line)
        for path in notice_sources
    ], 'exact source-header copyright notices', preamble=(
        b'Unreal Engine source notice\n\n'
        b'The excerpts retain their original Unreal Engine source notices and remain subject to the applicable Unreal Engine license.\n'
        b'No Falcor license is substituted for the extracted source. The byte ranges and source paths are recorded in UESkyLightSource.json.\n'
        b'Original attribution comments (including Duff et al., Walter et al., and Stupid Spherical Harmonics (SH) Tricks) remain in the excerpts.\n'
        b'Each original source-header copyright line follows, in source-path order as listed in the manifest.\n'))
    (dest / 'UESkyLightSource.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    export()
