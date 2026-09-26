"""Extract unchanged UE shadow functions; source files are read-only."""
import hashlib
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]
ENGINE=Path('E:/ue/engine/UnrealEngine/Engine/Shaders/Private')
DEST=ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Shadows'

def function(data,signature):
    start=data.index(signature.encode())
    opening=data.index(b'{',start);depth=1;end=opening+1
    while depth:
        if data[end]==123:depth+=1
        elif data[end]==125:depth-=1
        end+=1
    if signature.startswith('struct '):end+=1
    return data[start:end]

def export():
    DEST.mkdir(exist_ok=True)
    manifest={'capture_inputs':False,'engine':'53c568c6b4e0318ef75fd81cdcf6edd5dd51a9b0','excerpts':[]}
    def emit(name,parts):
        chunks=[b'// Copyright Epic Games, Inc. All Rights Reserved.\n// Unchanged source excerpts; see UECSMSource.json.\n']
        for source,signature in parts:
            path=ENGINE/source;data=path.read_bytes();chunk=function(data,signature)
            chunks.append(chunk)
            manifest['excerpts'].append({'output':name,'source':str(path),'signature':signature,
                'source_sha256':hashlib.sha256(data).hexdigest(),'excerpt_sha256':hashlib.sha256(chunk).hexdigest(),
                'line':data[:data.index(chunk)].count(b'\n')+1})
        (DEST/name).write_bytes(b'\n\n'.join(chunks)+b'\n')
    emit('UECSMFiltering.ush',[("ShadowFilteringCommon.ush",s) for s in (
        'struct FPCFSamplerSettings','float2 HorizontalPCF5x2(',
        'float4 CalculateShadowVisibilityTransmittanceFactor(','float Manual5x5PCF(')])
    emit('UECSMDepth.ush',[("ShadowDepthVertexShader.usf",s) for s in (
        'float ComputeDepthBiasDirectionalSpot(','float4 TransformShadowDirectional(')])
    emit('UECSMEncode.ush',[("ShadowProjectionPixelShader.usf",'float ApplyPCFOverBlurCorrection('),
        ('Common.ush','MaterialFloat EncodeLightAttenuation(')])
    (DEST/'UECSMSource.json').write_text(json.dumps(manifest,indent=2))
if __name__=='__main__':export()
