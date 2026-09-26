"""Extract original SkyView shader bodies, with exact byte provenance."""
import hashlib,json,subprocess
from pathlib import Path
from export_shadow_source import function
ROOT=Path(__file__).resolve().parents[2]
ENGINE=Path('E:/ue/engine/UnrealEngine')
DEST=ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'

def export():
    manifest={'capture_inputs':False,'engine':subprocess.check_output(['git','-C',str(ENGINE),'rev-parse','HEAD'],text=True).strip(),
        'excerpts':[],'outputs':[]}
    def emit(name,items):
        chunks=[b'// Original source bodies; see UESkyViewLutSource.json.\n// Copyright and third-party notices are retained alongside this file.']
        for file,signature,ordinary in items:
            path=ENGINE/'Engine/Shaders/Private'/file;data=path.read_bytes()
            search=data
            if ordinary:
                start=data.index(b'#else // PERMUTATION_REALTIME_REFLECTION_LUT')
                search=data[start:]
            chunk=function(search,signature);start=data.index(chunk)
            chunks.append(chunk)
            manifest['excerpts'].append({'output':name,'source':str(path),'signature':signature,'byte_offset':start,'bytes':len(chunk),
                'source_sha256':hashlib.sha256(data).hexdigest(),'excerpt_sha256':hashlib.sha256(chunk).hexdigest(),
                'line':data[:start].count(b'\n')+1})
        output=DEST/name;output.write_bytes(b'\n\n'.join(chunks)+b'\n')
        manifest['outputs'].append({'path':name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()})
    emit('UESkyViewHelpers.ush',[
        ('FastMathThirdParty.ush','float acosFast4(',False),
        *[('SkyAtmosphereCommon.ush',s,False) for s in ('float2 FromSubUvsToUnit(', 'float3x3 GetSkyViewLutReferential(')],
        *[('SkyAtmosphere.usf',s,True) for s in ('float3x3 GetSkyViewLutReferentialParameter(',
            'float3 GetSkyPlanetTranslatedWorldCenterAndViewHeightParameter(', 'float3 GetSkyCameraTranslatedWorldOriginParameter(')],
        *[('SkyAtmosphere.usf',s,False) for s in ('float3 GetCameraTranslatedWorldPos(', 'float3 GetTranslatedCameraPlanetPos(',
            'bool MoveToTopAtmosphere(', 'void UvToSkyViewLutParams(', 'float3 GetMultipleScattering(')]])
    emit('UESkyViewLut.ush',[('SkyAtmosphere.usf','void RenderSkyViewLutCS(',False)])
    # Preserve the source license preamble, including FastMath's MIT notice.
    thirdparty=(ENGINE/'Engine/Shaders/Private/FastMathThirdParty.ush').read_bytes()
    (DEST/'UESkyViewThirdPartyNotice.txt').write_bytes(thirdparty[:thirdparty.index(b'// Normalized range')])
    (DEST/'UESkyViewLutSource.json').write_text(json.dumps(manifest,indent=2))
if __name__=='__main__':export()
