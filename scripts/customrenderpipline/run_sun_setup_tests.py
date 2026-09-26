"""Build and run the CPU-only source sun adapter, recording fresh evidence."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
def run():
    parent=ROOT/'build/sun-setup'; parent.mkdir(exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    vcvars=Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvars64.bat')
    command=out/'build.cmd'
    command.write_text('@echo off\ncall "'+str(vcvars)+'" >nul\nif errorlevel 1 exit /b 1\n'
        'cl /nologo /std:c++17 /EHsc /O2 /fp:precise /W3 /I"'+str(ROOT/'external/include')+'" '
        '"'+str(ROOT/'Source/Tools/FalcorTest/Standalone/UESunSetupCompatSmoke.cpp')+'" '
        '"'+str(ROOT/'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/UESunSetup.cpp')+'" '
        '/Fe:"'+str(out/'sun-setup.exe')+'"\n',encoding='utf-8')
    result=subprocess.run(['cmd','/c',str(command)],cwd=out,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (out/'build.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    print(str(out),flush=True)
    if result.returncode: print(result.stdout+result.stderr);return result.returncode
    test=subprocess.run([str(out/'sun-setup.exe')],capture_output=True,text=True)
    (out/'test.log').write_text(test.stdout+test.stderr)
    (out/'result.json').write_text(json.dumps({'build_exit_code':result.returncode,'test_exit_code':test.returncode,
        'status':'passed' if test.returncode==0 and 'SUN_SETUP_PASS' in test.stdout else 'failed'},indent=2))
    print(test.stdout+test.stderr,flush=True)
    return test.returncode
if __name__=='__main__':raise SystemExit(run())
