"""Build and run source sky view CPU tests in a fresh evidence directory."""
import json
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
def run():
    parent=ROOT/'build/sky-view-setup';parent.mkdir(exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    command=out/'build.cmd'
    command.write_text('@echo off\ncall "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat" >nul\nif errorlevel 1 exit /b 1\n'
        'cl /nologo /std:c++17 /EHsc /O2 /fp:precise /W3 '
        '"'+str(ROOT/'Source/Tools/FalcorTest/Standalone/UESkyViewSetupSmoke.cpp')+'" '
        '"'+str(ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/UESkyViewSetup.cpp')+'" '
        '/Fe:"'+str(out/'sky-view-setup.exe')+'"\n',encoding='utf-8')
    build=subprocess.run(['cmd','/c',str(command)],cwd=out,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (out/'build.log').write_text(build.stdout+build.stderr,encoding='utf-8');print(str(out),flush=True)
    if build.returncode:print(build.stdout+build.stderr);return build.returncode
    test=subprocess.run([str(out/'sky-view-setup.exe')],capture_output=True,text=True)
    (out/'test.log').write_text(test.stdout+test.stderr)
    passed=test.returncode==0 and 'SKY_VIEW_SETUP_PASS' in test.stdout
    (out/'result.json').write_text(json.dumps({'build_exit_code':build.returncode,'test_exit_code':test.returncode,'status':'passed' if passed else 'failed'},indent=2))
    print(test.stdout+test.stderr,flush=True);return 0 if passed else 1
if __name__=='__main__':raise SystemExit(run())
