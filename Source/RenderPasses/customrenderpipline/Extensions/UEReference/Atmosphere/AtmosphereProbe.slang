// Diagnostic observations only. No output from this pass feeds the renderer.
// Original atmosphere functions and resources are shared with the native LUTs.
#define main unusedLutEntry
#include "AtmosphereLuts.slang"
#undef main

RWTexture2D<float4> probePosition;
RWTexture2D<float4> probePath;
RWTexture2D<float4> probeMedium;
RWTexture2D<float4> probeLight;

[numthreads(8,8,1)]
void main(uint3 pixel : SV_DispatchThreadID)
{
#if TRANSMITTANCE_PASS
    uint2 extent = uint2(SkyAtmosphere.TransmittanceLutSizeAndInvSize.xy);
    float count = SkyAtmosphere.TransmittanceSampleCount;
    uint steps = uint(ceil(count));
    if (pixel.x >= extent.x || pixel.y >= extent.y * steps) return;
    uint row = pixel.y % extent.y;
    uint step = pixel.y / extent.y;
    float2 uv = (float2(pixel.x, row) + 0.5f) * SkyAtmosphere.TransmittanceLutSizeAndInvSize.zw;
    float height, mu;
    UvToLutTransmittanceParams(height, mu, uv);
    float3 origin = float3(0, 0, height);
    float3 direction = float3(0, sqrt(1.0f - mu * mu), mu);
#else
    uint2 extent = uint2(SkyAtmosphere.MultiScatteredLuminanceLutSizeAndInvSize.xy);
    float count = SkyAtmosphere.MultiScatteringSampleCount;
    uint steps = uint(ceil(count)) + 1; // final slot observes ground bounce
    if (pixel.x >= extent.x || pixel.y >= 2 * extent.y * steps) return;
    uint row = pixel.y % extent.y;
    uint step = (pixel.y / extent.y) % steps;
    float sign = pixel.y < extent.y * steps ? 1.0f : -1.0f;
    float2 uv = (float2(pixel.x, row) + 0.5f) * SkyAtmosphere.MultiScatteredLuminanceLutSizeAndInvSize.zw;
    float mu = uv.x * 2.0f - 1.0f;
    float height = Atmosphere.BottomRadiusKm + uv.y * (Atmosphere.TopRadiusKm - Atmosphere.BottomRadiusKm);
    float3 origin = float3(0, 0, height);
    float3 direction = float3(0, 0, sign);
#endif
    float2 bottom = RayIntersectSphere(origin, direction, float4(0, 0, 0, Atmosphere.BottomRadiusKm));
    float2 top = RayIntersectSphere(origin, direction, float4(0, 0, 0, Atmosphere.TopRadiusKm));
    bool hitsGround = !all(bottom < 0.0f);
    float end = hitsGround ? max(0.0f, min(bottom.x, bottom.y)) : max(top.x, top.y);
    end = min(end, 9000000.0f);
    float distance = end * (float(step) + DEFAULT_SAMPLE_OFFSET) / count;
#if !TRANSMITTANCE_PASS
    if (step == steps - 1) distance = end;
#endif
    float3 position = origin + distance * direction;
    float radius = length(position);
    MediumSampleRGB medium = SampleAtmosphereMediumRGB(position);
    probePosition[pixel.xy] = float4(position, radius);
    probePath[pixel.xy] = float4(end, distance, count, hitsGround ? 1.0f : 0.0f);
    probeMedium[pixel.xy] = float4(medium.Extinction, 1);
#if TRANSMITTANCE_PASS
    probeLight[pixel.xy] = float4(1, 1, 1, mu);
#else
    float3 light = float3(0, sqrt(saturate(1.0f - mu * mu)), mu);
    float lightCosine = dot(light, position / radius);
    probeLight[pixel.xy] = float4(GetTransmittance(lightCosine, radius), lightCosine);
#endif
}
