// Authored native adapter and DefaultLit specialization of the exact UE helpers.
// Source bodies and scope are recorded in LightingSource.json.
#include "Platform.slangh"
Texture2D<float4> gSkySceneColor;
Texture2D<float4> gSkyPosition;
ByteAddressBuffer gSkyMainView;
Texture2D<float> gSkyPreExposure;
StructuredBuffer<float4> gSkyDiffuseSH;
Texture2D<float2> gSkyPreIntegratedGF;
SamplerState gSkyPreIntegratedGFSampler;
TextureCube<float4> gSkyReflectionCube;
SamplerState gSkyReflectionSampler;
#if UE_SKY_SCREEN_AO
Texture2D<float> gSkyScreenAO;
#endif
RWTexture2D<float4> gSkyLightingColor;
RWTexture2D<float4> gSkyDiffuse;
RWTexture2D<float4> gSkySpecular;
cbuffer SkyConsumer
{
    float3 SkyLightColor;
    uint DefaultLitModel;
    float4 SkyLightParameters;
};
struct UESkyReflectionParameters
{
    float4 SkyLightParameters;
};
UESkyReflectionParameters UESkyLoadReflectionParameters()
{
    UESkyReflectionParameters parameters;
    parameters.SkyLightParameters = SkyLightParameters;
    return parameters;
}
struct UESkyConsumerView
{
    float3 SkyLightColor;
    float PreExposure;
};
UESkyConsumerView UESkyLoadConsumerView()
{
    UESkyConsumerView v;
    v.SkyLightColor = SkyLightColor;
    v.PreExposure = gSkyPreExposure.Load(int3(0,0,0));
    return v;
}
// Keep every uniform in an explicit cbuffer and every resource at top level.
// The single source Cube sample is redirected at the intrinsic boundary;
// its original symbolic texture argument is not a separate shader resource.
// This avoids Slang/GFX's implicit global block for a mixed resource struct.
#define View UESkyLoadConsumerView()
#define ReflectionStruct UESkyLoadReflectionParameters()
#define SharedSkyLightCubemapSampler gSkyReflectionSampler
#undef TextureCubeSampleLevel
#define TextureCubeSampleLevel(Texture, Sampler, Coordinates, Level) gSkyReflectionCube.SampleLevel(Sampler, Coordinates, Level)
#define SkyIrradianceEnvironmentMap gSkyDiffuseSH
#define PreIntegratedGF gSkyPreIntegratedGF
#define PreIntegratedGFSampler gSkyPreIntegratedGFSampler
#define Texture2DSampleLevel(Texture, Sampler, Coordinates, Level) Texture.SampleLevel(Sampler, Coordinates, Level)
#define MaterialFloat float
#define MaterialFloat3 float3
#define WORKING_COLOR_SPACE_IS_SRGB 1
#define UE_LEGACY_LUMINANCE_FACTORS 0
#define APPLY_SKY_SHADOWING 0
#define FEATURE_LEVEL 5
#define FEATURE_LEVEL_ES3_1 3
#define REFLECTION_CAPTURE_ROUGHEST_MIP 1
#define REFLECTION_CAPTURE_ROUGHNESS_MIP_SCALE 1.2
#define OcclusionCombineMode 0
#define OcclusionTintAndMinOcclusion float4(0,0,0,0)
// Isolate every source helper from Schema lighting helpers in the same module.
#define LuminanceFactors UESkyConsumerLuminanceFactors
#define Luminance UESkyConsumerLuminance
#define DielectricSpecularToF0 UESkyConsumerDielectricSpecularToF0
#define ComputeF0 UESkyConsumerComputeF0
#define ComputeDiffuseAlbedo UESkyConsumerComputeDiffuseAlbedo
#define GetSkyLightCubemapBrightness UESkyConsumerGetSkyLightCubemapBrightness
#define ComputeReflectionCaptureMipFromRoughness UESkyConsumerComputeReflectionCaptureMipFromRoughness
#define GetSkyLightReflection UESkyConsumerGetSkyLightReflection
#define GetSkySHDiffuse UESkyConsumerGetSkySHDiffuse
#define GetOffSpecularPeakReflectionDir UESkyConsumerGetOffSpecularPeakReflectionDir
#define GetSpecularOcclusion UESkyConsumerGetSpecularOcclusion
#define EnvBRDF UESkyConsumerEnvBRDF
#define FSkyLightVisibilityData UESkyConsumerVisibilityData
#define GetSkyLightVisibilityData UESkyConsumerGetSkyLightVisibilityData
#include "LightingHelpersOriginal.slangh"

float3 UESkyDefaultLitDiffuse(float3 N, float GBufferAO, float ScreenAO, float3 DiffuseColor)
{
    float3 Lighting = 0;
    FSkyLightVisibilityData SkyVisData = GetSkyLightVisibilityData(N, N, GBufferAO, ScreenAO, N);
    float3 DiffuseWeight = 1.0f; // Source USE_ENERGY_CONSERVATION=0 specialization.
#include "LightingDiffuseSelected.ush"
}

[numthreads(8,8,1)]
void main(uint3 pixel : SV_DispatchThreadID)
{
    uint width, height;
    gSkyLightingColor.GetDimensions(width,height);
    if (pixel.x >= width || pixel.y >= height) return;
    const float4 initial = gSkySceneColor.Load(int3(pixel.xy,0));
    gSkyLightingColor[pixel.xy] = initial;
    gSkyDiffuse[pixel.xy] = 0;
    gSkySpecular[pixel.xy] = 0;
    const float4 position = gSkyPosition.Load(int3(pixel.xy,0));
    if (position.w <= 0) return;
    const UESurface surface = decodeGBuffer(ueLoadRaw(pixel.xy), View.PreExposure);
    if (surface.modelID != DefaultLitModel) return;
    const float3 N = normalize(surface.normalUE);
    const float3 positionUE = float3(-position.z,position.x,position.y)*100;
    const float3 cameraUE = asfloat(gSkyMainView.Load4(144)).xyz;
    const float3 V = normalize(cameraUE-positionUE);
    float ScreenAO = 1.0f; // Explicit AO-disabled route; no SSAO producer is claimed.
#if UE_SKY_SCREEN_AO
    ScreenAO = gSkyScreenAO.Load(int3(pixel.xy,0));
#endif
    const float3 diffuse = UESkyDefaultLitDiffuse(N,surface.ao,ScreenAO,
        ComputeDiffuseAlbedo(surface.baseColor,surface.metallic));
    // ReflectionEnvironmentPixelShader + dynamic-sky-only GatherRadiance.
    float3 R = 2 * dot(V,N) * N - V;
    float NoV = saturate(dot(N,V));
    R = GetOffSpecularPeakReflectionDir(N,R,surface.roughness);
    float AO = surface.ao * ScreenAO;
    float SpecularOcclusion = GetSpecularOcclusion(NoV,surface.roughness*surface.roughness,AO);
    float SkyAverageBrightness;
    float3 SkyLighting = GetSkyLightReflection(R,surface.roughness,SkyAverageBrightness);
    float3 ExtraIndirectSpecular = SkyLighting * (1.0f * 1.0f);
    float3 specular = View.PreExposure * (SpecularOcclusion * ExtraIndirectSpecular);
    specular *= EnvBRDF(ComputeF0(surface.specular,surface.baseColor,surface.metallic),surface.roughness,NoV);
    specular = -min(-specular,0);
    gSkyDiffuse[pixel.xy] = float4(diffuse,0);
    gSkySpecular[pixel.xy] = float4(specular,0);
    gSkyLightingColor[pixel.xy] = float4(initial.rgb+diffuse+specular,initial.a);
}
