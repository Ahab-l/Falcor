"""Original sky material byte provenance and bounded perspective specialization."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'
MANIFEST = DEST / 'UESkyMaterialSource.json'


class SkyMaterialSourceTests(unittest.TestCase):
    def manifest(self):
        self.assertTrue(MANIFEST.is_file(), 'Original sky material source has not been extracted')
        return json.loads(MANIFEST.read_text())

    def test_source_bytes_and_output_hashes(self):
        manifest = self.manifest()
        self.assertIs(manifest['capture_inputs'], False)
        for entry in manifest['excerpts']:
            original = Path(entry['source']).read_bytes()
            start = entry['byte_offset']
            excerpt = original[start:start + entry['bytes']]
            self.assertEqual(hashlib.sha256(original).hexdigest(), entry['source_sha256'])
            self.assertEqual(hashlib.sha256(excerpt).hexdigest(), entry['excerpt_sha256'])
            self.assertEqual(original[:start].count(b'\n') + 1, entry['line'])
            self.assertIn(excerpt, (DEST / entry['output']).read_bytes())
        for output in manifest['outputs']:
            self.assertEqual(hashlib.sha256((DEST / output['path']).read_bytes()).hexdigest(), output['sha256'])

    def test_original_algorithms_and_licenses_are_retained(self):
        manifest = self.manifest()
        signatures = {entry['signature'] for entry in manifest['excerpts']}
        for signature in (
            'float3 MaterialExpressionSkyAtmosphereLightDiskLuminance(',
            'float3 MaterialExpressionSkyAtmosphereViewLuminance(',
            'void SkyViewLutParamsToUv(', 'float3 GetAtmosphereTransmittance(',
            'float3 GetLightDiskLuminance(', 'float2 RayIntersectSphere(',
            'float atan2Fast(', 'float acosFast4(',
            'float3 QuantizeFloatColor(in float3 Color, in float3 QuantizationError, in float E)',
            'float3 QuantizeFloatColor(in float3 Color, in float3 QuantizationError, in float2 Pos2D,',
            'float InterleavedGradientNoise(',
            'FVector3f ComputePixelFormatQuantizationError(',
        ):
            self.assertIn(signature, signatures)
        notice = (DEST / 'UESkyMaterialThirdPartyNotice.txt').read_text()
        self.assertIn('The MIT License', notice)
        self.assertIn('Copyright', notice)

    def test_perspective_specialization_only_omits_orthographic_blocks(self):
        manifest = self.manifest()
        specialization = manifest['specialization']
        self.assertEqual(specialization['supported_projection'], 'perspective')
        self.assertEqual(specialization['unsupported_branches'], ['orthographic', 'reflection_capture', 'primitive_alpha_holdout'])
        original = (DEST / specialization['original']).read_bytes()
        removed = specialization['removed_ranges']
        self.assertEqual(len(removed), 2)
        reconstructed = original
        for entry in sorted(removed, key=lambda item: item['byte_offset'], reverse=True):
            start = entry['byte_offset']
            end = start + entry['bytes']
            chunk = original[start:end]
            self.assertIn(b'IsOrthoProjection()', chunk)
            self.assertEqual(hashlib.sha256(chunk).hexdigest(), entry['sha256'])
            reconstructed = reconstructed[:start] + reconstructed[end:]
        self.assertEqual(reconstructed, (DEST / specialization['output']).read_bytes())
        self.assertNotIn(b'IsOrthoProjection()', reconstructed)
        self.assertNotIn(b'GetTranslatedWorldCameraPosFromView(', reconstructed)

    def test_exporter_reproduces_checked_in_bytes(self):
        manifest = self.manifest()
        path = ROOT / 'scripts/customrenderpipline/export_sky_material_source.py'
        self.assertTrue(path.is_file(), 'Sky material exporter is missing')
        spec = importlib.util.spec_from_file_location('export_sky_material_source', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='ue-sky-material-source-') as directory:
            generated = Path(directory)
            module.export(dest=generated)
            for entry in manifest['outputs']:
                self.assertEqual((DEST / entry['path']).read_bytes(), (generated / entry['path']).read_bytes())
            self.assertEqual(manifest, json.loads((generated / MANIFEST.name).read_text()))

    def test_archived_wrapper_preserves_original_material_integration_reference(self):
        self.manifest()
        path = ROOT / 'docs/research/archive/ue-legacy-wrappers/SourceSky.3d.slang.reference'
        self.assertTrue(path.is_file(), 'Archived source sky material integration reference is missing')
        wrapper = path.read_text()
        for declaration in (
            'ByteAddressBuffer gSkyViewParameters;', 'Texture2D<float4> gSkyViewLut;',
            'Texture2D<float4> gSkyTransmittanceLut;', 'Texture2D<float> gSkyPreExposure;',
            'Texture2D<uint4> gSkyFrameStatus;', 'cbuffer SkyMaterialParams',
            'SamplerState gSkyViewSampler;', 'SamplerState gSkyTransmittanceSampler;',
            'gSkyViewParameters.Load4(144)', 'gSkyFrameStatus.Load(int3(0,0,0)).z & 7u',
            '1.0f / gSkyPreExposure.Load(int3(0,0,0))',
            'float3(-input.posW.z, input.posW.x, input.posW.y) * 100.0f',
            '#include "../Atmosphere/UESkyMaterialPerspective.ush"',
            '#include "../../../CustomRenderPiplineRaster.3d.slang"',
        ):
            self.assertIn(declaration, wrapper)
        self.assertIn('MaterialExpressionSkyAtmosphereViewLuminance(parameters, -parameters.CameraVector)', wrapper)
        self.assertIn('MaterialExpressionSkyAtmosphereLightDiskLuminance(parameters, 0u, -1.0f)', wrapper)
        self.assertNotIn('surface.emissive *=', wrapper)
        self.assertIn('UESurface sky = (UESurface)0;', wrapper)
        self.assertIn('sky.modelID = surface.modelID;', wrapper)
        self.assertIn('return sky;', wrapper)
        self.assertNotIn('surface.modelID =', wrapper, 'The immutable schema owns the Unlit material ID')


if __name__ == '__main__':
    unittest.main()
