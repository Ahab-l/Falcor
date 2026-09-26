// Capture adapter for original M_SimpleSkyDome atmosphere expressions.
// Exact expression includes and main-view SourceSky wrapper remain unchanged.
// Captures use source reflection flags; clouds and height fog are external.
import Scene.Raster;

ByteAddressBuffer gSkyViewParameters;
Texture2D<float4> gSkyViewLut;
Texture2D<float4> gSkyTransmittanceLut;
Texture2D<float> gSkyPreExposure;
SamplerState gSkyViewSampler;
SamplerState gSkyTransmittanceSampler;
cbuffer SkyMaterialParams
{
    float skyBottomRadiusKm;
    float skyTopRadiusKm;
    float3 skyLuminanceFactor;
};

namespace UEOriginalSkyMaterial
{
struct FMaterialPixelParameters
{
    float3 CameraVector;
    float4 SvPosition;
};
struct UESkyMaterialResolvedView
{
    float3 SkyCameraTranslatedWorldOrigin;
    float4 SkyPlanetTranslatedWorldCenterAndViewHeight;
    float4x4 SkyViewLutReferential;
    float4 AtmosphereLightDirection[2];
    float4 AtmosphereLightDiscCosHalfApexAngle_PPTrans[2];
    float4 AtmosphereLightDiscLuminance[2];
    float SkyAtmosphereBottomRadiusKm;
    float SkyAtmosphereTopRadiusKm;
    float4 SkyViewLutSizeAndInvSize;
    float4 SkyAtmosphereSkyLuminanceFactor;
    float OneOverPreExposure;
    float3 SceneColorTextureFormatQuantizationError;
    float RenderingReflectionCaptureMask;
    float RealTimeReflectionCapture;
    uint4 EnvironmentComponentsFlags;
};
UESkyMaterialResolvedView LoadSkyMaterialResolvedView()
{
    UESkyMaterialResolvedView v = (UESkyMaterialResolvedView)0;
    v.SkyCameraTranslatedWorldOrigin = asfloat(gSkyViewParameters.Load4(0)).xyz;
    v.SkyPlanetTranslatedWorldCenterAndViewHeight = asfloat(gSkyViewParameters.Load4(16));
    v.SkyViewLutReferential = float4x4(asfloat(gSkyViewParameters.Load4(32)), asfloat(gSkyViewParameters.Load4(48)),
        asfloat(gSkyViewParameters.Load4(64)), asfloat(gSkyViewParameters.Load4(80)));
    v.AtmosphereLightDirection[0] = asfloat(gSkyViewParameters.Load4(96));
    const float4 disk = asfloat(gSkyViewParameters.Load4(128));
    v.AtmosphereLightDiscLuminance[0] = float4(disk.xyz, 0.0f);
    // The native setup stores the source half apex angle in radians.
    v.AtmosphereLightDiscCosHalfApexAngle_PPTrans[0] = float4(cos(disk.w), 0.0f, 0.0f, 0.0f);
    v.SkyAtmosphereBottomRadiusKm = skyBottomRadiusKm;
    v.SkyAtmosphereTopRadiusKm = skyTopRadiusKm;
    uint width, height;
    gSkyViewLut.GetDimensions(width, height);
    v.SkyViewLutSizeAndInvSize = float4(float(width), float(height), 1.0f / float(width), 1.0f / float(height));
    v.SkyAtmosphereSkyLuminanceFactor = float4(skyLuminanceFactor, 0.0f);
    v.OneOverPreExposure = 1.0f / gSkyPreExposure.Load(int3(0,0,0));
    v.SceneColorTextureFormatQuantizationError = 0.0f;
    v.RenderingReflectionCaptureMask = 1.0f;
    v.RealTimeReflectionCapture = 1.0f;
    v.EnvironmentComponentsFlags = uint4(8u, 0u, 0u, 0u);
    return v;
}
struct UESkyMaterialResourceView
{
    Texture2D<float4> SkyViewLutTexture;
    SamplerState SkyViewLutTextureSampler;
    Texture2D<float4> TransmittanceLutTexture;
    SamplerState TransmittanceLutTextureSampler;
    uint StateFrameIndexMod8;
};
UESkyMaterialResourceView LoadSkyMaterialResourceView()
{
    UESkyMaterialResourceView v;
    v.SkyViewLutTexture = gSkyViewLut;
    v.SkyViewLutTextureSampler = gSkyViewSampler;
    v.TransmittanceLutTexture = gSkyTransmittanceLut;
    v.TransmittanceLutTextureSampler = gSkyTransmittanceSampler;
    v.StateFrameIndexMod8 = 0u; // Capture disables source dithering.
    return v;
}

#define View LoadSkyMaterialResourceView()
#define ResolvedView LoadSkyMaterialResolvedView()
#define MATERIAL_SKY_ATMOSPHERE 1
#define PROJECT_SUPPORT_SKY_ATMOSPHERE 1
#define SUPPORT_PRIMITIVE_ALPHA_HOLDOUT 0
#define Texture2DSampleLevel(T,S,U,L) T.SampleLevel(S,U,L)
#define CM_TO_SKY_UNIT 0.00001f
#define FLATTEN [flatten]
#ifndef PI
#define PI 3.14159265358979323846f
#endif
#include "../Atmosphere/UESkyMaterialHelpers.ush"
#include "../Atmosphere/UESkyMaterialPerspective.ush"
#undef View
#undef ResolvedView
#undef MATERIAL_SKY_ATMOSPHERE
#undef PROJECT_SUPPORT_SKY_ATMOSPHERE
#undef SUPPORT_PRIMITIVE_ALPHA_HOLDOUT
#undef Texture2DSampleLevel
#undef CM_TO_SKY_UNIT
#undef FLATTEN
#undef QUANTIZE_NOISE_TYPE
#undef QUANTIZE_NOISE_HAMMERSLEY
#undef QUANTIZE_NOISE_INTERLEAVEDGRADIENT
#undef ENVCOMP_FLAG_SKYATMOSPHERE_RENDERINMAIN
#undef IsSkyAtmosphereRenderedInMain
}

cbuffer UEMeshPass { float4x4 viewProjection; };
cbuffer SkyCaptureParams { float capturePreExposure; };
VSOut vertexMain(VSIn input)
{
    VSOut output = defaultVS(input);
    output.posH = mul(viewProjection, float4(output.posW, 1.0f));
    return output;
}
float4 pixelMain(VSOut input) : SV_Target0
{
    UEOriginalSkyMaterial::FMaterialPixelParameters parameters;
    const float3 positionUECm = float3(-input.posW.z, input.posW.x, input.posW.y) * 100.0f;
    const float3 cameraUECm = asfloat(gSkyViewParameters.Load4(144)).xyz;
    parameters.CameraVector = normalize(cameraUECm - positionUECm);
    parameters.SvPosition = input.posH;
    float3 emissive = UEOriginalSkyMaterial::MaterialExpressionSkyAtmosphereViewLuminance(parameters, -parameters.CameraVector)
        + UEOriginalSkyMaterial::MaterialExpressionSkyAtmosphereLightDiskLuminance(parameters, 0u, -1.0f);
    // BasePassPixelShader.usf:2484-2499 selects cached capture pre-exposure;
    // line2556 clamps after exposure. Source PC float aliases remain FP32.
    emissive *= capturePreExposure;
    emissive = min(emissive, 64512.0f);
    return float4(emissive, 1.0f);
}
