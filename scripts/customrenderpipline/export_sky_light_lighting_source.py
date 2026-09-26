"""Export exact consumer helper bodies with byte provenance, no source edits."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path('E:/ue/engine/UnrealEngine/Engine/Shaders/Private')
DEST = ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/SkyLight'


def export():
    manifest = {'capture_inputs':False, 'full_rendering_parity':False, 'excerpts':[],
        'specialization':['DefaultLit and Unlit only; USE_ENERGY_CONSERVATION=0, anisotropy disabled.',
            'Dynamic sky contribution only; SSR, SSGI, DFAO, local captures and cloud AO remain unimplemented.',
            'ScreenAO omitted selects explicit disabled branch; AO tint zero, pending component tint export.',
            'Helper bodies unchanged; adapter macros isolate names and native resource bindings.',
            'One source Cube sample redirects its symbolic texture argument to a top-level TextureCube; parameters live in an explicit cbuffer, avoiding a mixed implicit global block.',
            'SkyLightDiffuse keeps exact selected accumulation lines, with DefaultLit normal and DiffuseWeight=1.',
            'Reflection specialization retains offspecular direction, multiplicative AO, dynamic gather, exposure, EnvBRDF and nonnegative sanitization.',
            'Main camera comes from live main-view row9 UE cm; position comes from native Decode world meters.']}
    outputs = {}
    def retain(file,begin,end=None,output='LightingHelpersOriginal.slangh'):
        data = (SOURCE/file).read_bytes()
        first = data.index(begin.encode())
        if end is None:
            opening = data.index(b'{',first); level = 1; last = opening+1
            while level:
                level += (data[last:last+1] == b'{')-(data[last:last+1] == b'}')
                last += 1
        else:
            last = data.index(end.encode(),first)
        chunk = data[first:last]
        target = outputs.setdefault(output,bytearray(b'// Copyright Epic Games, Inc. All Rights Reserved.\n// Exact source excerpts; see LightingSource.json.\n'))
        target.extend(b'\n')
        manifest['excerpts'].append({'source':str(SOURCE/file),'byte_offset':first,'bytes':len(chunk),
            'line':data[:first].count(b'\n')+1,'source_sha256':hashlib.sha256(data).hexdigest(),
            'excerpt_sha256':hashlib.sha256(chunk).hexdigest(),'output':output,'output_byte_offset':len(target)})
        target.extend(chunk); target.extend(b'\n')
    for begin in ('float3 LuminanceFactors()', 'MaterialFloat Luminance( MaterialFloat3 LinearColor )'):
        retain('Common.ush',begin)
    for begin in ('half DielectricSpecularToF0(', 'half3 ComputeF0(', 'float3 ComputeDiffuseAlbedo('):
        retain('ShadingCommon.ush',begin)
    for begin in ('float GetSkyLightCubemapBrightness()', 'half ComputeReflectionCaptureMipFromRoughness(',
                  'float3 GetSkyLightReflection(', 'float3 GetSkySHDiffuse(',
                  'half3 GetOffSpecularPeakReflectionDir(', 'half GetSpecularOcclusion('):
        retain('ReflectionEnvironmentShared.ush',begin)
    retain('BRDF.ush','half3 EnvBRDF( half3 SpecularColor, half Roughness, half NoV )')
    retain('SkyLightingDiffuseShared.ush','struct FSkyLightVisibilityData','float3 SkyLightDiffuse(')
    retain('SkyLightingDiffuseShared.ush','\t// Compute the preconvolved incoming lighting', '\n}',
           'LightingDiffuseSelected.ush')
    for name,data in outputs.items():
        (DEST/name).write_bytes(data)
    (DEST/'LightingSource.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    export()
