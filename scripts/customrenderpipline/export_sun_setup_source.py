"""Extract original UE CPU sun math used by the native compatibility layer."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from export_shadow_source import function

ROOT = Path(__file__).resolve().parents[2]
ENGINE = Path('E:/ue/engine/UnrealEngine')
DEST = ROOT / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'


def export():
    parts = []
    manifest = {'capture_inputs': False, 'native_integration_pending': False,
                'integration': 'UESunSetup.cpp via UEReferenceLightingConfig and ueReferenceSourceSun',
                'compatibility': 'FVector/FVector2D and color matrices are double; medium, color and integration are float. Matrix inverse is a double cofactor adapter, not UE SIMD instruction emulation. RGB channels are implemented; alpha is unused.',
                'engine': subprocess.check_output(['git', '-C', str(ENGINE), 'rev-parse', 'HEAD'], text=True).strip(),
                'excerpts': []}

    def add(relative, signature, array=False):
        path = ENGINE / relative
        data = path.read_bytes()
        if array:
            match = re.search(rb'static constexpr float sRGBToLinearTable\[\]\s*=\s*\{.*?\};', data, re.S)
            if not match:
                raise ValueError('Original sRGB literal table was not found')
            excerpt = match.group()
        else:
            excerpt = function(data, signature)
        parts.append(excerpt)
        manifest['excerpts'].append({'source': str(path), 'signature': signature,
            'source_sha256': hashlib.sha256(data).hexdigest(), 'excerpt_sha256': hashlib.sha256(excerpt).hexdigest(),
            'byte_offset': data.index(excerpt), 'bytes': len(excerpt),
            'line': data[:data.index(excerpt)].count(b'\n') + 1})

    add('Engine/Source/Runtime/Core/Public/Math/Color.h', 'FLinearColor::sRGBToLinearTable', array=True)
    color = 'Engine/Source/Runtime/Core/Private/ColorManagement/ColorSpace.cpp'
    add(color, 'FMatrix44d FColorSpace::CalcRgbToXYZ() const')
    add(color, 'FLinearColor FColorSpace::MakeFromColorTemperature(float Temp) const')
    add('Engine/Source/Runtime/Core/Private/Math/UnrealMath.cpp', 'FVector2D FMath::GetAzimuthAndElevation')
    add('Engine/Source/Runtime/Engine/Public/Rendering/SkyAtmosphereCommonData.cpp',
        'FLinearColor FAtmosphereSetup::GetTransmittanceAtGroundLevel(const FVector& SunDirection) const')
    target = DEST / 'UESunSetupOriginal.inl'
    target.write_bytes(b'// Copyright Epic Games, Inc. All Rights Reserved.\n'
        b'// Exact original excerpts; see UESunSetupSource.json.\n'
        b'namespace Falcor::CustomRenderPipline::SunSetup::Compat\n{\n' + b'\n\n'.join(parts) + b'\n}\n')
    manifest['output'] = {'path': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    (DEST / 'UESunSetupSource.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    export()
