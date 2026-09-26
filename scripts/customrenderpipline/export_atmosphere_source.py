"""Extract unchanged UE atmosphere functions; source tree remains read-only."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from export_shadow_source import function

ROOT=Path(__file__).resolve().parents[2]
ENGINE=Path('E:/ue/engine/UnrealEngine/Engine/Shaders/Private')
DEST=ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'
ENGINE_ROOT=ENGINE.parents[2]


def export_srgb_table():
    path=ENGINE_ROOT/'Engine/Source/Runtime/Core/Public/Math/Color.h'
    data=path.read_bytes()
    match=re.search(rb'static constexpr float sRGBToLinearTable\[\]\s*=\s*\{.*?\};',data,re.S)
    if not match:raise ValueError('Original FLinearColor::sRGBToLinearTable declaration was not found')
    literals=[v.decode('ascii') for v in re.findall(rb'\d+\.\d+(?:[eE][+-]?\d+)?f',match.group())]
    if len(literals)!=256:raise ValueError('Original sRGB table must contain exactly 256 float literals')
    table={'capture_inputs':False,'engine':subprocess.check_output(['git','-C',str(ENGINE_ROOT),'rev-parse','HEAD'],text=True).strip(),
        'source':str(path),'signature':'FLinearColor::sRGBToLinearTable','source_sha256':hashlib.sha256(data).hexdigest(),
        'excerpt_sha256':hashlib.sha256(match.group()).hexdigest(),'line':data[:match.start()].count(b'\n')+1,
        'line_end':data[:match.end()].count(b'\n')+1,'literals':literals}
    DEST.mkdir(parents=True,exist_ok=True)
    (DEST/'UESRGBToLinearTable.json').write_text(json.dumps(table,indent=2)+'\n',encoding='utf-8')
    return table


def export():
    DEST.mkdir(exist_ok=True)
    table=export_srgb_table()
    manifest={'capture_inputs':False,'engine':table['engine'],'excerpts':[],'srgb_table':'UESRGBToLinearTable.json'}
    def emit(name,parts):
        chunks=[b'// Copyright Epic Games, Inc. All Rights Reserved.\n// Unchanged source bodies; see UEAtmosphereSource.json.\n']
        for source,signature in parts:
            path=ENGINE/source;data=path.read_bytes();chunk=function(data,signature)
            chunks.append(chunk)
            manifest['excerpts'].append({'output':name,'source':str(path),'signature':signature,
                'source_sha256':hashlib.sha256(data).hexdigest(),'excerpt_sha256':hashlib.sha256(chunk).hexdigest(),
                'line':data[:data.index(chunk)].count(b'\n')+1})
        (DEST/name).write_bytes(b'\n\n'.join(chunks)+b'\n')
    emit('UEAtmosphereCommon.ush',[
        ('Common.ush','float2 RayIntersectSphere('),
        *[('ParticipatingMediaCommon.ush',s) for s in ('float HenyeyGreensteinPhase(','float RayleighPhase(')],
        *[('SkyAtmosphereCommon.ush',s) for s in ('void fromTransmittanceLutUVs(','void getTransmittanceLutUvs(',
            'float3 EncodeTransmittance(','float3 DecodeTransmittance(','float3 GetAlbedo(',
            'struct MediumSampleRGB','MediumSampleRGB SampleAtmosphereMediumRGB(')]])
    emit('UEAtmosphereIntegration.ush',[('SkyAtmosphere.usf',s) for s in (
        'float RaySphereIntersectNearest(','void UvToLutTransmittanceParams(','void LutTransmittanceParamsToUv(',
        'float3 GetTransmittance(','float SkyAtmosphereNoise(', 'struct SingleScatteringResult','struct SamplingSetup',
        'SingleScatteringResult IntegrateSingleScatteredLuminance(')])
    emit('UETransmittance.ush',[('SkyAtmosphere.usf','void RenderTransmittanceLutCS(')])
    emit('UEMultiScattering.ush',[('SkyAtmosphere.usf','void RenderMultiScatteredLuminanceLutCS(')])
    (DEST/'UEAtmosphereSource.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':export()
