// Resource and permutation adapter for unchanged UE SkyAtmosphere functions.
// No View, exposure, depth, shadow or capture resources participate in these LUTs.
#define VIEWDATA_AVAILABLE 0
#define PER_PIXEL_NOISE 0
#define SECOND_ATMOSPHERE_LIGHT_ENABLED 0
#define MULTISCATTERING_APPROX_SAMPLING_ENABLED 0
#define HIGHQUALITY_MULTISCATTERING_APPROX_ENABLED 0
#define SKYVIEWLUT_PASS 0
#define SAMPLE_OPAQUE_SHADOW 0
#define SAMPLE_CLOUD_SHADOW 0
#define SAMPLE_CLOUD_SKYAO 0
#define SHADING_PATH_MOBILE 0
#define DEFAULT_SAMPLE_OFFSET 0.3f
#define PLANET_RADIUS_OFFSET 0.001f
#define OutputPreExposure 1.0f
#define FarDepthValue 0.0f
#define FLATTEN [flatten]
#ifndef PI
#define PI 3.14159265358979323846f
#endif

#include "AtmosphereParameters.slang"

#if TRANSMITTANCE_PASS
#define WHITE_TRANSMITTANCE 1
struct UESkyLutParameters { float4 TransmittanceLutSizeAndInvSize; float TransmittanceSampleCount; };
RWTexture2D<float3> TransmittanceLutUAV;
#else
struct UESkyLutParameters { float4 MultiScatteredLuminanceLutSizeAndInvSize; float MultiScatteringSampleCount; };
Texture2D<float4> TransmittanceLutTexture;
SamplerState TransmittanceLutTextureSampler;
RWTexture2D<float3> MultiScatteredLuminanceLutUAV;
#endif
ConstantBuffer<UESkyLutParameters> SkyAtmosphere;

#include "UEAtmosphereCommon.ush"
#include "UEAtmosphereIntegration.ush"
#if TRANSMITTANCE_PASS
#include "UETransmittance.ush"
#else
#include "UEMultiScattering.ush"
#endif

[numthreads(8,8,1)]
void main(uint3 pixel : SV_DispatchThreadID)
{
    // UE dispatches ceil(extent/8); protect arbitrary declared odd extents.
#if TRANSMITTANCE_PASS
    if (any(pixel.xy >= uint2(SkyAtmosphere.TransmittanceLutSizeAndInvSize.xy))) return;
    RenderTransmittanceLutCS(pixel);
#else
    if (any(pixel.xy >= uint2(SkyAtmosphere.MultiScatteredLuminanceLutSizeAndInvSize.xy))) return;
    RenderMultiScatteredLuminanceLutCS(pixel);
#endif
}
