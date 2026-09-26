// Original SkyView bodies with native camera, sun and graph exposure resources.
// RenderSkyViewLutCS always passes FarDepthValue. Specialize its unreachable
// scene-depth branch out of the shared integrator; no depth stub or input.
#define VIEWDATA_AVAILABLE 0
#define PER_PIXEL_NOISE 0
#define SECOND_ATMOSPHERE_LIGHT_ENABLED 0
#define MULTISCATTERING_APPROX_SAMPLING_ENABLED 1
#define HIGHQUALITY_MULTISCATTERING_APPROX_ENABLED 0
#define SKYVIEWLUT_PASS 1
#define SAMPLE_OPAQUE_SHADOW 0
#define SAMPLE_CLOUD_SHADOW 0
#define SAMPLE_CLOUD_SKYAO 0
#define SHADING_PATH_MOBILE 0
#define DEFAULT_SAMPLE_OFFSET 0.3f
#define PLANET_RADIUS_OFFSET 0.001f
#define CM_TO_SKY_UNIT 0.00001f
#define SKY_UNIT_TO_CM (1.0f / CM_TO_SKY_UNIT)
#define FarDepthValue 0.0f
#define FLATTEN [flatten]
#ifndef PI
#define PI 3.14159265358979323846f
#endif

#include "AtmosphereParameters.slang"
struct UESkyLutParameters
{
    float4 SkyViewLutSizeAndInvSize;
    float FastSkySampleCountMin;
    float FastSkySampleCountMax;
    float FastSkyDistanceToSampleCountMaxInv;
    float3 SkyAndAerialPerspectiveLuminanceFactor;
};
ConstantBuffer<UESkyLutParameters> SkyAtmosphere;
ByteAddressBuffer gSkyViewParameters;
Texture2D<float> gPreExposure;
#define OutputPreExposure gPreExposure.Load(int3(0,0,0))
Texture2D<float4> TransmittanceLutTexture;
Texture2D<float4> MultiScatteredLuminanceLutTexture;
SamplerState TransmittanceLutTextureSampler;
SamplerState MultiScatteredLuminanceLutTextureSampler;
RWTexture2D<float4> SkyViewLutUAV;

struct UESkyView
{
    float3 SkyCameraTranslatedWorldOrigin;
    float4 SkyPlanetTranslatedWorldCenterAndViewHeight;
    float4x4 SkyViewLutReferential;
    float4 AtmosphereLightDirection[2];
    float4 AtmosphereLightIlluminanceOuterSpace[2];
};
UESkyView LoadSkyView()
{
    UESkyView v=(UESkyView)0;
    v.SkyCameraTranslatedWorldOrigin=asfloat(gSkyViewParameters.Load4(0)).xyz;
    v.SkyPlanetTranslatedWorldCenterAndViewHeight=asfloat(gSkyViewParameters.Load4(16));
    v.SkyViewLutReferential=float4x4(asfloat(gSkyViewParameters.Load4(32)),asfloat(gSkyViewParameters.Load4(48)),
        asfloat(gSkyViewParameters.Load4(64)),asfloat(gSkyViewParameters.Load4(80)));
    v.AtmosphereLightDirection[0]=asfloat(gSkyViewParameters.Load4(96));
    v.AtmosphereLightIlluminanceOuterSpace[0]=asfloat(gSkyViewParameters.Load4(112));
    return v;
}
#define View LoadSkyView()
#include "UEAtmosphereCommon.ush"
#include "UESkyViewHelpers.ush"
#include "UEAtmosphereIntegration.ush"
#include "UESkyViewLut.ush"

[numthreads(8,8,1)]
void main(uint3 pixel:SV_DispatchThreadID)
{
    if(any(pixel.xy>=uint2(SkyAtmosphere.SkyViewLutSizeAndInvSize.xy)))return;
    RenderSkyViewLutCS(pixel);
}
