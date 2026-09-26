#include "UESunSetup.h"
#include "UESunSetupCompat.h"
#include "UESunSetupOriginal.inl"
#include <nlohmann/json.hpp>
#include <set>
#include <stdexcept>
#include <string>

namespace Falcor::CustomRenderPipline::SunSetup
{
namespace
{
using Json=nlohmann::json;
using namespace Compat;
void require(bool condition,const std::string& label)
{ if(!condition) throw std::invalid_argument("UE source sun: "+label); }
void keys(const Json& value,const std::set<std::string>& expected)
{
    require(value.is_object() && value.size()==expected.size(),"settings must contain the complete source contract");
    for(const auto& [key,item]:value.items()) require(expected.count(key)!=0,"unsupported field "+key);
}
float scalar(const Json& value)
{
    require(value.is_number(),"finite numeric value required");
    float result=value.get<float>(); require(std::isfinite(result),"finite float32 value required");return result;
}
bool boolean(const Json& value) { require(value.is_boolean(),"boolean required");return value.get<bool>(); }
FLinearColor color(const Json& value)
{
    require(value.is_array() && value.size()==3,"RGB requires three components");
    FLinearColor result(scalar(value[0]),scalar(value[1]),scalar(value[2]));
    require(result.R>=0 && result.G>=0 && result.B>=0,"negative RGB"); return result;
}
Json rgb(FLinearColor v)
{
    require(std::isfinite(v.R)&&std::isfinite(v.G)&&std::isfinite(v.B),"derived RGB overflow");
    return {v.R,v.G,v.B};
}
}
Json evaluate(const Json& settings)
{
    using namespace Compat;
    keys(settings,{"working_color_space","color_srgb","intensity","use_temperature","temperature_kelvin",
        "atmosphere_sun","per_pixel_transmittance","direction_ue","source_angle_degrees","disk_color_scale",
        "transmittance_min_elevation_degrees","atmosphere"});
    require(settings.at("working_color_space")=="sRGB","working color space requires exported sRGB settings");
    bool atmosphereSun=boolean(settings.at("atmosphere_sun"));
    bool perPixel=boolean(settings.at("per_pixel_transmittance"));
    require(!perPixel,"per-pixel atmospheric transmittance consumer is not implemented");
    const auto& bytes=settings.at("color_srgb");
    require(bytes.is_array()&&bytes.size()==3,"source FColor RGB required");
    for(const auto& v:bytes) require(v.is_number_integer() && v>=0 && v<=255,"source FColor byte required");
    float intensity=scalar(settings.at("intensity")); require(intensity>=0,"negative intensity");
    // ULightComponent::GetColoredLightBrightness, no IES branch: the source
    // FLinearColor(FColor) lookup, then brightness, then optional temperature.
    FLinearColor energy(sRGBToLinearTable[bytes[0].get<unsigned>()],sRGBToLinearTable[bytes[1].get<unsigned>()],
        sRGBToLinearTable[bytes[2].get<unsigned>()]);
    energy=energy*intensity;
    float temperature=scalar(settings.at("temperature_kelvin"));
    if(boolean(settings.at("use_temperature"))) energy=energy*FColorSpace().MakeFromColorTemperature(temperature);
    const auto& direction=settings.at("direction_ue");
    require(direction.is_array()&&direction.size()==3,"direction requires three components");
    for(const auto& v:direction) require(v.is_number()&&std::isfinite(v.get<double>()),"finite direction required");
    FVector sun(direction[0].get<double>(),direction[1].get<double>(),direction[2].get<double>());
    require(std::abs(FVector::DotProduct(sun,sun)-1.0)<=1e-4,"unit sun direction required");
    const auto& p=settings.at("atmosphere");
    keys(p,{"BottomRadiusKm","TopRadiusKm","MieDensityExpScale","RayleighDensityExpScale","MieExtinction",
        "RayleighScattering","AbsorptionExtinction","AbsorptionDensity0LayerWidth","AbsorptionDensity0LinearTerm",
        "AbsorptionDensity0ConstantTerm","AbsorptionDensity1LinearTerm","AbsorptionDensity1ConstantTerm"});
    FAtmosphereSetup a;
#define SCALAR(name) a.name=scalar(p.at(#name))
    SCALAR(BottomRadiusKm);SCALAR(TopRadiusKm);SCALAR(MieDensityExpScale);SCALAR(RayleighDensityExpScale);
    SCALAR(AbsorptionDensity0LayerWidth);SCALAR(AbsorptionDensity0LinearTerm);SCALAR(AbsorptionDensity0ConstantTerm);
    SCALAR(AbsorptionDensity1LinearTerm);SCALAR(AbsorptionDensity1ConstantTerm);
#undef SCALAR
    a.MieExtinction=color(p.at("MieExtinction"));a.RayleighScattering=color(p.at("RayleighScattering"));
    a.AbsorptionExtinction=color(p.at("AbsorptionExtinction"));
    require(a.BottomRadiusKm>0&&a.TopRadiusKm>a.BottomRadiusKm&&a.TopRadiusKm<=1e8,"ordered positive atmosphere radii required");
    require(a.MieDensityExpScale<=0&&a.RayleighDensityExpScale<=0,"density must not grow with altitude");
    a.TransmittanceMinLightElevationAngle=scalar(settings.at("transmittance_min_elevation_degrees"));
    require(std::abs(a.TransmittanceMinLightElevationAngle)<=90,"minimum sun elevation outside [-90,90]");
    FLinearColor transmittance=a.GetTransmittanceAtGroundLevel(sun);
    FLinearColor direct=atmosphereSun?energy*transmittance:energy;
    float angle=scalar(settings.at("source_angle_degrees")); require(angle>0&&angle<180,"sun disk angle outside (0,180)");
    // FDirectionalLightSceneProxy::GetSunLightHalfApexAngleRadian and GetLightDiskLuminance.
    const float halfApex=0.5f*angle*3.1415926535897932f/180.f;
    const float solidAngle=2.0f*3.1415926535897932f*(1.0f-FMath::Cos(halfApex));
    require(solidAngle>0,"sun disk angle underflows float solid angle");
    FLinearColor disk=color(settings.at("disk_color_scale"))*energy;
    disk={disk.R/solidAngle,disk.G/solidAngle,disk.B/solidAngle};
    return {{"outer_space_illuminance",rgb(energy)},{"ground_transmittance",rgb(transmittance)},
        {"direct_illuminance",rgb(direct)},{"disk_outer_space_luminance",rgb(disk)},
        {"half_apex_radians",halfApex},{"source_radius",FMath::Sin(0.5f*FMath::DegreesToRadians(angle))}};
}
}
