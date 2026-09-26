"""Observe native Cube subresources; no retired GPU fixture or runtime entry."""
import json
from pathlib import Path
import runpy
import traceback

scope = runpy.run_path(str(Path(__file__).with_name('native_resource_shapes_migration_smoke.py')),
                      init_globals={'m':m, '_CRP_EMBEDDED':True})
try:
    result = scope['run'](observe=True)
except Exception as error:
    traceback.print_exc()
    result = {'status':'failed','error':str(error)}
(scope['OUT']/'result.json').write_text(json.dumps(result, indent=2))
print('NATIVE_OBSERVER_VIEWS_'+result['status'].upper(), flush=True)
exit()
