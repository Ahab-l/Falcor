#pragma once
#include "UESunSetupCompat.h"
#include <cstdint>
#include <stdexcept>

namespace Falcor::CustomRenderPipline::SkyViewSetup::Compat
{
using SunSetup::Compat::FVector;
using SunSetup::Compat::FVector3f;
using uint8=uint8_t;
struct FVector4f
{
    float X{},Y{},Z{},W{};
    FVector4f()=default;
    FVector4f(FVector3f v,float w):X(v.X),Y(v.Y),Z(v.Z),W(w){}
};
struct FMatrix44f
{
    float M[4][4]{};
    FMatrix44f() { for(int i=0;i<4;++i)M[i][i]=1.f; }
    void SetColumn(int column,FVector3f v) { M[0][column]=v.X;M[1][column]=v.Y;M[2][column]=v.Z; }
    FMatrix44f GetTransposed() const
    { FMatrix44f r;for(int i=0;i<4;++i)for(int j=0;j<4;++j)r.M[i][j]=M[j][i];return r; }
};
struct FTransform
{
    FVector translation;
    FVector GetTranslation() const { return translation; }
};
enum class ESkyAtmosphereTransformMode: uint8
{ PlanetTopAtAbsoluteWorldOrigin=0,PlanetTopAtComponentTransform=1,PlanetCenterAtComponentTransform=2 };
inline void check(bool value) { if(!value)throw std::invalid_argument("Invalid atmosphere transform mode"); }
struct FMath: SunSetup::Compat::FMath
{
    static float Abs(float v) { return std::abs(v); }
    static float Pow(float a,float b) { return std::pow(a,b); }
};
struct FAtmosphereSetup
{
    static const float CmToSkyUnit,SkyUnitToCm;
    float BottomRadiusKm{};
    FVector PlanetCenterKm;
    void UpdateTransform(const FTransform&,uint8);
    void ComputeViewData(const FVector&,const FVector&,const FVector3f&,const FVector3f&,
                         FVector3f&,FVector4f&,FMatrix44f&) const;
};
}
