"""Create the isolated content-only UE project used by build_ue_reference.py."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/m0-evidence/ue-reference"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "Config").mkdir(exist_ok=True)
project = {"FileVersion": 3, "EngineAssociation": "", "Description": "Generated M0 paired reference",
           "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True},
                       {"Name": "EditorScriptingUtilities", "Enabled": True}]}
(OUT / "M0Reference.uproject").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
(OUT / "Config/DefaultEngine.ini").write_text("""[/Script/EngineSettings.GameMapsSettings]
EditorStartupMap=/Game/M0/Reference
GameDefaultMap=/Game/M0/Reference

[/Script/Engine.Engine]
NearClipPlane=10.0

[/Script/Engine.RendererSettings]
r.DynamicGlobalIlluminationMethod=0
r.ReflectionMethod=0
r.Shadow.Virtual.Enable=0
r.Nanite.ProjectEnabled=False
r.Substrate=False
r.DefaultFeature.AutoExposure=True
r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange=True
r.AntiAliasingMethod=0
r.DefaultFeature.MotionBlur=False
r.DefaultFeature.Bloom=False
r.AllowStaticLighting=False
r.GenerateMeshDistanceFields=False

[/Script/WindowsTargetPlatform.WindowsTargetSettings]
DefaultGraphicsRHI=DefaultGraphicsRHI_DX12
-D3D12TargetedShaderFormats=PCD3D_SM5
+D3D12TargetedShaderFormats=PCD3D_SM6

[SystemSettings]
r.ScreenPercentage=100
r.EyeAdaptationQuality=2
r.SSR.Quality=0
r.SSGI.Quality=0
""", encoding="utf-8")
print(OUT / "M0Reference.uproject")
