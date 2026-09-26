"""Extract the exact native planet transform and view setup; UE remains read-only."""
import hashlib
import json
from pathlib import Path
import subprocess
from export_shadow_source import function
ROOT=Path(__file__).resolve().parents[2]
ENGINE=Path('E:/ue/engine/UnrealEngine')
DEST=ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'
def export():
    path=ENGINE/'Engine/Source/Runtime/Engine/Public/Rendering/SkyAtmosphereCommonData.cpp'
    data=path.read_bytes();parts=[]
    manifest={'capture_inputs':False,'native_graph_integration_pending':False,
        'engine':subprocess.check_output(['git','-C',str(ENGINE),'rev-parse','HEAD'],text=True).strip(),'excerpts':[]}
    for signature in ('const float FAtmosphereSetup::CmToSkyUnit','const float FAtmosphereSetup::SkyUnitToCm',
                      'void FAtmosphereSetup::UpdateTransform(', 'void FAtmosphereSetup::ComputeViewData('):
        if signature.startswith('const'):
            start=data.index(signature.encode());part=data[start:data.index(b';',start)+1]
        else:part=function(data,signature)
        parts.append(part);start=data.index(part)
        manifest['excerpts'].append({'source':str(path),'signature':signature,'byte_offset':start,'bytes':len(part),
            'source_sha256':hashlib.sha256(data).hexdigest(),'excerpt_sha256':hashlib.sha256(part).hexdigest(),
            'line':data[:start].count(b'\n')+1})
    target=DEST/'UESkyViewSetupOriginal.inl'
    target.write_bytes(b'// Copyright Epic Games, Inc. All Rights Reserved.\n// Exact source bodies; see UESkyViewSetupSource.json.\n'
        b'namespace Falcor::CustomRenderPipline::SkyViewSetup::Compat\n{\n'+b'\n\n'.join(parts)+b'\n}\n')
    manifest['output']={'path':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (DEST/'UESkyViewSetupSource.json').write_text(json.dumps(manifest,indent=2))
if __name__=='__main__':export()
