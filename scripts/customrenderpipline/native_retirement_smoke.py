"""The active plugin exposes native services, not retired UE transactions."""
import json
from pathlib import Path
import sys
import tempfile
import traceback
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/customrenderpipline'))
import falcor
OUT=Path(tempfile.mkdtemp(prefix='retirement-',dir=ROOT/'build/resource-history-migration'))
print('NATIVE_RETIREMENT_EVIDENCE '+str(OUT),flush=True)
try:
    retired=('customRenderPiplineSceneIdentity','customRenderPiplineBindGraphContract',
             'customRenderPiplineSealGraph','customRenderPiplinePrepareGraph','customRenderPiplineRenderHistoryFrame')
    assert not any(hasattr(falcor,name) for name in retired), 'Retired runtime entry remains exported'
    for name in ('customRenderPiplineOutputCatalog','customRenderPiplineRenderAtlas','customRenderPiplineReadDepthStencil',
                 'customRenderPiplineBindHistory','customRenderPiplineResetHistory','ueReferenceSourceSun'):
        assert hasattr(falcor,name), 'Lost retained service '+name
    for name in ('CustomRenderPiplineInitPass','CustomRenderPiplinePrePass','CustomRenderPiplineDecodePass',
                 'CustomRenderPiplineGBufferAdapterPass','UEReferenceGBufferPass','UEReferenceLightingPass',
                 'UEReferenceShadowSetupPass','UEReferenceSkyViewSetupPass'):
        try:falcor.createPass(name,{})
        except RuntimeError as error:
            assert 'sceneDefinition' not in str(error) and 'schemaPath' not in str(error),str(error)
        else:raise AssertionError('Retired pass remains registered: '+name)
    result={'status':'passed','retired_exports_absent':list(retired),'native_services_retained':True}
except Exception as error:
    traceback.print_exc();result={'status':'failed','error':str(error)}
(OUT/'result.json').write_text(json.dumps(result,indent=2))
print('NATIVE_RETIREMENT_'+result['status'].upper(),flush=True)
exit()
