"""CPU-only checks for exact SkyLight source and native dispatch provenance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'Source/RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere'
MANIFEST = DEST / 'UESkyLightSource.json'
ENGINE = Path('E:/ue/engine/UnrealEngine')
SHADER = ENGINE / 'Engine/Shaders/Private/ReflectionEnvironmentShaders.usf'


class SkyLightSourceTests(unittest.TestCase):
    def manifest(self):
        self.assertTrue(MANIFEST.is_file(), 'Exact SkyLight source has not been extracted')
        return json.loads(MANIFEST.read_text())

    def exporter(self):
        path = ROOT / 'scripts/customrenderpipline/export_sky_light_source.py'
        self.assertTrue(path.is_file(), 'SkyLight exporter is missing')
        spec = importlib.util.spec_from_file_location('export_sky_light_source', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_source_bytes_and_output_hashes(self):
        manifest = self.manifest()
        self.assertIs(manifest['capture_inputs'], False)
        self.assertIs(manifest['runtime_support_established'], False)
        self.assertRegex(manifest['engine'], r'^[0-9a-f]{40}$')
        for entry in manifest['excerpts']:
            with self.subTest(signature=entry['signature']):
                source = Path(entry['source']).read_bytes()
                start = entry['byte_offset']
                excerpt = source[start:start + entry['bytes']]
                output = (DEST / entry['output']).read_bytes()
                offset = entry['output_byte_offset']
                self.assertEqual(output[offset:offset + len(excerpt)], excerpt)
                self.assertEqual(hashlib.sha256(source).hexdigest(), entry['source_sha256'])
                self.assertEqual(hashlib.sha256(excerpt).hexdigest(), entry['excerpt_sha256'])
                self.assertEqual(source[:start].count(b'\n') + 1, entry['line'])
                self.assertEqual(entry['line'] + len(excerpt.splitlines()) - 1, entry['end_line'])
        for entry in manifest['outputs']:
            self.assertEqual(hashlib.sha256((DEST / entry['path']).read_bytes()).hexdigest(), entry['sha256'])

    def test_shader_regions_retain_alternate_braces_and_every_conditional(self):
        manifest = self.manifest()
        lines = SHADER.read_bytes().splitlines(keepends=True)
        for first, last, output in (
            (99, 130, 'UESkyLightCubeCommon.ush'),
            (188, 189, 'UESkyLightCubeCommon.ush'),
            (245, 267, 'UESkyLightCubeCommon.ush'),
            (269, 332, 'UESkyLightDownsample.ush'),
            (501, 651, 'UESkyLightFilter.ush'),
            (857, 1014, 'UESkyLightDiffuseSH.ush'),
        ):
            with self.subTest(first=first, last=last):
                expected = b''.join(lines[first - 1:last])
                entries = [entry for entry in manifest['excerpts'] if
                           Path(entry['source']) == SHADER and entry['line'] == first and entry['end_line'] == last]
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]['output'], output)
                self.assertIn(expected, (DEST / output).read_bytes())
                depth = 0
                for directive in re.findall(rb'^\s*#\s*(if|ifdef|ifndef|else|elif|endif)\b', expected, re.MULTILINE):
                    if directive in (b'if', b'ifdef', b'ifndef'):
                        depth += 1
                    elif directive == b'endif':
                        depth -= 1
                    else:
                        self.assertGreater(depth, 0)
                    self.assertGreaterEqual(depth, 0)
                self.assertEqual(depth, 0)
        downsample = (DEST / 'UESkyLightDownsample.ush').read_text()
        self.assertIn('void DownsamplePS(', downsample)
        self.assertIn('for( uint i = 0; i < 8; i++ )', downsample)
        filtered = (DEST / 'UESkyLightFilter.ush').read_text()
        self.assertIn('void FilterPS(', filtered)
        self.assertIn('const uint NumSamples = 1024;', filtered)
        self.assertIn('const uint NumSamples = Roughness < 0.1 ? 32 : 64;', filtered)
        self.assertIn('#define HammersleyDistribution Hammersley16', filtered)
        sh = (DEST / 'UESkyLightDiffuseSH.ush').read_text()
        self.assertIn('#include "SHCommon.ush"', sh)
        self.assertIn('RWStructuredBuffer<float4> OutIrradianceEnvMapSH;', sh)
        self.assertIn('const float SuperSampleAxisCount = 4.0f;', sh)
        self.assertIn('#error That is the only reduction supported today', sh)
        self.assertIn('OutIrradianceEnvMapSH[7].w = SkyAverageIrradiance;', sh)

    def test_math_dependencies_padding_and_attribution_are_retained(self):
        manifest = self.manifest()
        signatures = {entry['signature'] for entry in manifest['excerpts']}
        for signature in (
            'const static MaterialFloat PI = 3.1415926535897932f;',
            'float Pow2( float x )', 'float Pow4( float x )',
            'float3x3 GetTangentBasis( float3 TangentZ )',
            'float2 Hammersley( uint Index, uint NumSamples, uint2 Random )',
            'float4 UniformSampleSphere( float2 E )',
            'float4 CosineSampleHemisphere( float2 E )',
            'float4 ImportanceSampleGGX( float2 E, float a2 )',
            'float D_GGX( float a2, float NoH )',
            '#define REFLECTION_CAPTURE_ROUGHEST_MIP 1',
            'float ComputeReflectionCaptureRoughnessFromMip(float Mip, half CubemapMaxMip)',
            'struct FThreeBandSHVector',
            'FThreeBandSHVector MulSH3(FThreeBandSHVector A, half Scalar)',
            'FThreeBandSHVector AddSH3(FThreeBandSHVector A, FThreeBandSHVector B)',
            'FThreeBandSHVectorRGB AddSH3(FThreeBandSHVectorRGB A, FThreeBandSHVectorRGB B)',
            'FThreeBandSHVector SHBasisFunction3(half3 InputVector)',
        ):
            self.assertIn(signature, signatures)
        helpers = (DEST / 'UESkyLightHelpers.ush').read_text()
        for original in ('half4 V0;', 'half3 Pad;', 'NEED_SH_VECTOR_PADDING==1',
                         'struct FThreeBandSHVectorRGB', 'REFLECTION_CAPTURE_ROUGHNESS_MIP_SCALE 1.2',
                         '[ Duff et al. 2017, "Building an Orthonormal Basis, Revisited" ]',
                         '[Walter et al. 2007, "Microfacet models for refraction through rough surfaces"]'):
            self.assertIn(original, helpers)
        notice = (DEST / 'UESkyLightSourceNotice.txt').read_text()
        self.assertIn('Copyright Epic Games, Inc. All Rights Reserved.', notice)
        self.assertIn('Unreal Engine', notice)

    def test_native_dispatch_and_sampler_provenance(self):
        manifest = self.manifest()
        native = (DEST / 'UESkyLightNativeSetupOriginal.inl').read_text()
        for required in (
            'class FDownsampleCubeFaceCS : public FGlobalShader',
            'class FConvolveSpecularFaceCS : public FGlobalShader',
            'class FComputeSkyEnvMapDiffuseIrradianceCS : public FGlobalShader',
            'CreateForMipLevel(SkyCubeTexture, MipIndex - 1)',
            'FRDGTextureSRVDesc::Create(RDGSrcRenderTarget)',
            'FRDGTextureUAVDesc OutTextureMipColorDesc(RDGDstRenderTarget, MipIndex)',
            'const uint32 Log2_16 = 4;',
            'const FIntVector NumGroups = FIntVector(1, 1, 1);',
            'const float UniformSampleSolidAngle = 4.0f * PI / SampleCount;',
            'RenderCubeFaces_DiffuseIrradiance(ConvolvedSkyRenderTarget[ConvolvedSkyRenderTargetReadyIndex]);',
            'ExternalAccessQueue.Add(SkyIrradianceEnvironmentMapRDG, ERHIAccess::SRVMask, ERHIPipeline::All);',
        ):
            self.assertIn(required, native)
        self.assertEqual(native.count('PassParameters->SourceCubemapSampler = TStaticSamplerState<SF_Point>::GetRHI();'), 3)
        self.assertNotIn('CFLAG_AllowRealTypes', native)
        contract = manifest['native_contract']
        self.assertEqual(contract['sampler'], 'SF_Point')
        self.assertEqual(contract['mipgen']['shader_lod'], 0)
        self.assertEqual(contract['mipgen']['source_view_mip'], 'MipIndex - 1')
        self.assertEqual(contract['mipgen']['tap_count'], 9)
        self.assertEqual(contract['filter']['sample_counts'], [32, 64])
        self.assertEqual(contract['diffuse_sh']['source'], 'convolved cubemap')
        self.assertEqual(contract['diffuse_sh']['mip'], 'log2(capture_width) - 4')
        self.assertEqual(contract['diffuse_sh']['thread_group_size'], [8, 8, 1])
        self.assertEqual(contract['diffuse_sh']['dispatch_groups'], [1, 1, 1])
        self.assertEqual(contract['diffuse_sh']['sample_count'], 64)
        self.assertEqual(contract['diffuse_sh']['output_float4_count'], 8)
        self.assertEqual(contract['diffuse_sh']['brightness_index'], 7)
        self.assertIn('RWStructuredBuffer<float4>', ' '.join(manifest['integration_gaps']))

    def test_pc_precision_route_is_source_evidence_without_half_rewrite(self):
        manifest = self.manifest()
        platform = (DEST / 'UESkyLightPlatformOriginal.ush').read_text()
        compiler = (DEST / 'UESkyLightCompilerOriginal.inl').read_text()
        self.assertIn('#define PLATFORM_SUPPORTS_REAL_TYPES 0', platform)
        self.assertIn('#define PLATFORM_SUPPORTS_RELAXED_PRECISION 0', platform)
        self.assertIn('#elif FORCE_FLOATS || !PLATFORM_SUPPORTS_REAL_TYPES', platform)
        self.assertIn('#define half float', platform)
        self.assertIn('#define half3 float3', platform)
        self.assertIn('Input.Environment.CompilerFlags.Contains(CFLAG_AllowRealTypes)', compiler)
        self.assertEqual(manifest['native_contract']['precision']['half_alias'], 'float')
        self.assertIs(manifest['native_contract']['precision']['excerpt_tokens_rewritten'], False)

    def test_exporter_reproduces_checked_in_bytes(self):
        manifest = self.manifest()
        module = self.exporter()
        with tempfile.TemporaryDirectory(prefix='ue-sky-light-source-') as directory:
            generated = Path(directory)
            module.export(dest=generated)
            for entry in manifest['outputs']:
                self.assertEqual((DEST / entry['path']).read_bytes(), (generated / entry['path']).read_bytes())
            self.assertEqual(manifest, json.loads((generated / MANIFEST.name).read_text()))

    def test_bounded_extraction_rejects_shifted_and_incomplete_regions(self):
        module = self.exporter()
        data = b'header\r\n#ifdef TEST\r\nbody\r\n#endif\r\nfooter\r\n'
        start, chunk = module.select_lines(data, 2, 4, '#ifdef TEST', '#endif')
        self.assertEqual(start, len(b'header\r\n'))
        self.assertEqual(chunk, b'#ifdef TEST\r\nbody\r\n#endif\r\n')
        for first, last, beginning, ending in (
            (1, 3, '#ifdef TEST', '#endif'),
            (2, 3, '#ifdef TEST', 'body'),
            (2, 8, '#ifdef TEST', '#endif'),
        ):
            with self.subTest(first=first, last=last):
                with self.assertRaises(ValueError):
                    module.select_lines(data, first, last, beginning, ending)


if __name__ == '__main__':
    unittest.main()
