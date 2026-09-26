// FAtmosphereUniformShaderParameters resource layout used by original bodies.
struct UEAtmosphereParameters
{
    float BottomRadiusKm;
    float TopRadiusKm;
    float3 GroundAlbedo;
    float MultiScatteringFactor;
    float3 RayleighScattering;
    float RayleighDensityExpScale;
    float3 MieScattering;
    float3 MieAbsorption;
    float3 MieExtinction;
    float MiePhaseG;
    float MieDensityExpScale;
    float3 AbsorptionExtinction;
    float AbsorptionDensity0LayerWidth;
    float AbsorptionDensity0LinearTerm;
    float AbsorptionDensity0ConstantTerm;
    float AbsorptionDensity1LinearTerm;
    float AbsorptionDensity1ConstantTerm;
};
ConstantBuffer<UEAtmosphereParameters> Atmosphere;
