"""Create/build/run an isolated original-asset platform texture export.

Does not launch or save the original UE project. All GPU/build execution is
explicit (--build/--run) and owned by the root task. --existing resumes only a
prepared worktree-owned run; no timeout-driven automatic restart.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path('E:/ue/engine/UnrealEngine')
BASE = ROOT/'build/source-platform-texture'
sys.path.insert(0, str(ROOT/'scripts/customrenderpipline'))
from source_platform_texture import make_dds


def identity(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return identity_bytes(path, data)


def identity_bytes(path, data):
    path = Path(path).resolve()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def prepare_loader(run, engine_manifest):
    """Package the freshly built isolated module; -Module omits UBT metadata.

    This creates only the scratch plugin manifest. It never edits or relabels
    an existing engine/plugin binary or replaces an existing manifest.
    """
    record_path = run/'loader-prepared.json'
    if record_path.exists():
        record = json.loads(record_path.read_text())
        for entry in record.values():
            if identity(entry['path']) != entry:
                raise ValueError('Prepared loader identity changed: '+entry['path'])
        return record
    receipts = [json.loads(p.read_text()) for p in run.glob('build-*.result.json')]
    if not any(r.get('exit_code') == 0 for r in receipts):
        raise ValueError('Loader packaging requires a successful owned module build')
    data = Path(engine_manifest).read_bytes()
    engine = json.loads(data)
    if not isinstance(engine.get('BuildId'), str) or not engine['BuildId'] or engine.get('Modules', {}).get('Engine') != 'UnrealEditor-Engine-Win64-Debug.dll':
        raise ValueError('Expected current Debug engine module manifest')
    binary = run/'Scratch/Plugins/SourceTextureExport/Binaries/Win64'
    dll = binary/'UnrealEditor-SourceTextureExport-Win64-Debug.dll'
    dll_identity = identity(dll)
    manifest = binary/'UnrealEditor-Win64-Debug.modules'
    write(manifest, {'BuildId': engine['BuildId'], 'Modules': {'SourceTextureExport': dll.name}})
    engine_identity = identity(engine_manifest)
    if engine_identity['sha256'] != hashlib.sha256(data).hexdigest():
        raise ValueError('Engine manifest changed during loader packaging')
    record = dict(engine=engine_identity, dll=dll_identity, manifest=identity(manifest))
    write(record_path, record)
    return record


def execute(command, run, stage, env, timeout):
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    prefix = run/(stage+'-'+str(time.time_ns()))
    receipt = dict(command=command, timeout_seconds=timeout, started_ns=time.time_ns())
    with prefix.with_suffix('.stdout.log').open('xb') as stdout, prefix.with_suffix('.stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command, cwd=run/'Scratch', env=env, startupinfo=startup,
                                   stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        receipt['pid'] = process.pid
        write(prefix.with_suffix('.launch.json'), receipt)
        print(json.dumps(dict(stage=stage, pid=process.pid, stdout=str(prefix.with_suffix('.stdout.log')))), flush=True)
        try:
            receipt['exit_code'] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Parent-only termination is not enough for a build: report the live
            # handle and let root inspect/stop owned build children explicitly.
            receipt['timeout'] = True
            write(prefix.with_suffix('.observation.json'), receipt)
            raise RuntimeError('Owned process remains live after observation timeout: '+str(process.pid))
    receipt['elapsed_seconds'] = (time.time_ns()-receipt['started_ns'])/1e9
    write(prefix.with_suffix('.result.json'), receipt)
    print(json.dumps(receipt, indent=2), flush=True)
    if receipt['exit_code'] != 0:
        raise RuntimeError(stage+' failed; inspect '+str(prefix))
    return receipt


def prepare():
    BASE.mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='export-', dir=BASE)).resolve()
    scratch = run/'Scratch'
    for sub in ('Config', 'Content', 'Plugins'):
        (scratch/sub).mkdir(parents=True, exist_ok=True)
    for name in ('User', 'DDC', 'Export'):
        (run/name).mkdir()
    plugin = Path(__file__).parent/'SourceTextureExport'
    shutil.copytree(plugin, scratch/'Plugins/SourceTextureExport')
    project = scratch/'SourceTextureScratch.uproject'
    write(project, {'FileVersion': 3, 'DisableEnginePluginsByDefault': True, 'Plugins': [
        {'Name': 'SourceTextureExport', 'Enabled': True}, {'Name': 'PythonScriptPlugin', 'Enabled': True},
        {'Name': 'TextureFormatOodle', 'Enabled': True}]})
    (scratch/'Config/DefaultEngine.ini').write_text(
        '[DerivedDataCacheGraphs]\nSourceTextureExport=(Local=SourceTextureLocal)\n'
        '[DerivedDataCacheStores]\nSourceTextureLocal=(Type=FileSystem,ReadOnly=false,DeleteUnused=false,Path="'+(run/'DDC').as_posix()+'")\n', encoding='utf-8')
    sentinel = run/'verify_export_in_engine.py'
    sentinel.write_text('import json,os\nfrom pathlib import Path\np=Path(os.environ["CRP_SOURCE_EXPORT_DIR"])/"result.json"\n'
        'assert p.is_file(), "PostEngineInit exporter did not execute"\n'
        'data=json.loads(p.read_text())\nassert data["status"]=="passed", data\nprint("SOURCE_TEXTURE_SENTINEL_PASSED")\n', encoding='utf-8')
    protected = [ENGINE/'Engine/Content/OpenWorldTemplate/LandscapeMaterial/T_GridChecker_A.uasset',
                 ENGINE/'Engine/Binaries/Win64/UnrealEditor-Win64-Debug-Cmd.exe',
                 ENGINE/'Engine/Binaries/Win64/UnrealEditor-Engine-Win64-Debug.dll',
                 ENGINE/'Engine/Binaries/Win64/UnrealEditor-Win64-Debug.modules',
                 ENGINE/'Engine/Config/BaseEngine.ini']
    plan = dict(project=str(project), source_plugin=[identity(p) for p in plugin.rglob('*') if p.is_file()],
                executed_plugin=[identity(p) for p in (scratch/'Plugins').rglob('*') if p.is_file()],
                protected=[identity(p) for p in protected], original_project_launched=False, capture_inputs=False)
    write(run/'prepared.json', plan)
    print('SOURCE_PLATFORM_PREPARED '+str(run), flush=True)
    return run, plan


def export_command(run, plan):
    # NullRHI suppresses Texture2D::PostLoad's platform cache entirely. Rendering
    # permission is required to build the source texture, but no scene is drawn.
    return [str(ENGINE/'Engine/Binaries/Win64/UnrealEditor-Win64-Debug-Cmd.exe'), plan['project'],
            '-run=pythonscript', '-script='+str(run/'verify_export_in_engine.py'),
            '-AllowCommandletRendering', '-RenderOffscreen', '-d3d12',
            # Editor material layout initialization asserts when shader compiling
            # is forbidden. CoreLimit=4 limits the native compiler to 3 workers.
            '-unattended', '-nosplash', '-nosound', '-corelimit=4', '-NoRemoteShaderCompile', '-NoAssetRegistryCache', '-nop4',
            '-DDC=SourceTextureExport', '-UserDir='+str(run/'User'),
            '-abslog='+str(run/('unreal-'+str(time.time_ns())+'.log')), '-SourceTextureOut='+str(run/'Export')]


def seed_source_ddc(run, previous):
    previous = Path(previous).resolve()
    if previous.parent != BASE.resolve() or run.resolve().parent != BASE.resolve() or previous == run.resolve():
        raise ValueError('DDC seed must be a distinct owned source-export run')
    destination = run/'DDC'
    if any(destination.iterdir()):
        raise ValueError('DDC seed requires an empty destination cache')
    source = previous/'DDC'
    entries = []
    for path in sorted(source.rglob('*')):
        if path.is_file():
            if not path.resolve().is_relative_to(source.resolve()):
                raise ValueError('DDC source link escaped its cache')
            data = path.read_bytes()
            entry = identity_bytes(path, data)
            output = destination/path.relative_to(source)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('xb') as stream:
                stream.write(data)
            if identity(path) != entry or identity(output)['sha256'] != entry['sha256']:
                raise ValueError('DDC source changed while seeding')
            entries.append(entry)
    if not entries:
        raise ValueError('DDC source contains no cached data')
    write(run/'source-ddc-seed.json', dict(source=str(previous), capture_inputs=False, files=entries,
                                         bytes=sum(p['bytes'] for p in entries)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing', type=Path)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--seed-ddc-from', type=Path)
    args = parser.parse_args()
    if args.existing:
        run = args.existing.resolve()
        if run.parent != BASE.resolve():
            raise ValueError('Existing run must be a direct child of the workspace export directory')
        plan = json.loads((run/'prepared.json').read_text())
    else:
        run, plan = prepare()
    if args.run:
        for name in ('result.json', 'platform-mips.bin', 'T_GridChecker_A.bc1.srgb.dds'):
            if (run/'Export'/name).exists():
                raise ValueError('Existing export evidence requires a fresh run: '+name)
        if (run/'source-platform-result.json').exists():
            raise ValueError('Existing source platform result requires a fresh run')
    for entry in plan['protected']+plan['executed_plugin']:
        if identity(entry['path']) != entry:
            raise ValueError('Prepared source/binary changed: '+entry['path'])
    if getattr(args, 'seed_ddc_from', None):
        seed_source_ddc(run, args.seed_ddc_from)
    env = os.environ.copy()
    env.pop('PYTHONHOME', None); env.pop('PYTHONPATH', None)
    env.update({'UE-LocalDataCachePath': str(run/'DDC'), 'UE-SharedDataCachePath': 'None', 'CRP_SOURCE_EXPORT_DIR': str(run/'Export')})
    receipts = []
    pending_result = None
    launcher_sources = [identity(Path(__file__)), identity(ROOT/'scripts/customrenderpipline/source_platform_texture.py')]
    try:
        if args.build:
            command = [str(ENGINE/'Engine/Build/BatchFiles/Build.bat'), 'UnrealEditor', 'Win64', 'Debug',
                       '-Project='+plan['project'], '-Module=SourceTextureExport', '-NoEngineChanges',
                       '-NoHotReloadFromIDE', '-MaxParallelActions=4', '-NoUBA']
            receipts.append(execute(command, run, 'build', env, 600))
        if args.run:
            prepare_loader(run, ENGINE/'Engine/Binaries/Win64/UnrealEditor-Win64-Debug.modules')
            command = export_command(run, plan)
            receipts.append(execute(command, run, 'export', env, 900))
            metadata_path, payload_path = run/'Export/result.json', run/'Export/platform-mips.bin'
            metadata_bytes, payload_bytes = metadata_path.read_bytes(), payload_path.read_bytes()
            metadata = json.loads(metadata_bytes)
            metadata_id, payload_id = identity_bytes(metadata_path, metadata_bytes), identity_bytes(payload_path, payload_bytes)
            dds = make_dds(metadata, payload_bytes)
            output = run/'Export/T_GridChecker_A.bc1.srgb.dds'
            with output.open('xb') as stream:
                stream.write(dds)
            expected = [metadata_id, payload_id, identity_bytes(output, dds)]
            if expected != [identity(p['path']) for p in expected]:
                raise ValueError('Export bytes changed after consumption')
            pending_result = dict(status='passed', capture_inputs=False,
                original_project_launched=False, texture=expected[2], metadata=metadata_id,
                payload=payload_id, receipts=receipts, launcher_sources=launcher_sources)
    finally:
        after = [identity(p['path']) for p in plan['protected']]
        protection_path = run/('protected-after-'+str(time.time_ns())+'.json')
        write(protection_path, {'unchanged': after == plan['protected'], 'files': after})
        if after != plan['protected']:
            raise RuntimeError('Original source/engine identity changed')
    if pending_result is not None:
        if launcher_sources != [identity(p['path']) for p in launcher_sources]:
            raise ValueError('Launcher source changed during execution')
        for entry in (pending_result['metadata'], pending_result['payload'], pending_result['texture']):
            if identity(entry['path']) != entry:
                raise ValueError('Export changed before publication')
        pending_result.update(protected_unchanged=True, protected=after, protection_report=str(protection_path))
        write(run/'source-platform-result.json', pending_result)
        print('SOURCE_PLATFORM_TEXTURE '+str(output), flush=True)


if __name__ == '__main__':
    main()
