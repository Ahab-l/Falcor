#include "UESkyViewSetup.h"
#include "UESkyViewSetupCompat.h"
#include "UESkyViewSetupOriginal.inl"
#include <cmath>
#include <stdexcept>

namespace Falcor::CustomRenderPipline::SkyViewSetup
{
namespace
{
void require(bool condition,const char* label) { if(!condition)throw std::invalid_argument(label); }
template<typename T> bool finite(const std::array<T,3>& v)
{ for(auto x:v)if(!std::isfinite(x))return false;return true; }
template<typename T> double square(const std::array<T,3>& v)
{ return double(v[0])*v[0]+double(v[1])*v[1]+double(v[2])*v[2]; }
}
Result evaluate(const Input& input)
{
    using namespace Compat;
    require(std::isfinite(input.bottomRadiusKm)&&input.bottomRadiusKm>0&&input.bottomRadiusKm<=1e8,"Invalid sky planet radius");
    require(input.transformMode<=2,"Invalid sky planet transform mode");
    require(finite(input.cameraUECm)&&finite(input.preViewTranslationCm)&&finite(input.componentTranslationCm),"Nonfinite sky position");
    require(finite(input.viewForwardUE)&&finite(input.viewRightUE)&&std::abs(square(input.viewForwardUE)-1)<1e-4&&
        std::abs(square(input.viewRightUE)-1)<1e-4,"Sky view directions must be unit vectors");
    FAtmosphereSetup atmosphere;
    atmosphere.BottomRadiusKm=input.bottomRadiusKm;
    const auto& t=input.componentTranslationCm;
    atmosphere.UpdateTransform(FTransform{{t[0],t[1],t[2]}},input.transformMode);
    const auto& c=input.cameraUECm;const auto& p=input.preViewTranslationCm;
    const auto& f=input.viewForwardUE;const auto& r=input.viewRightUE;
    FVector camera(c[0],c[1],c[2]);
    auto delta=camera-atmosphere.PlanetCenterKm*FAtmosphereSetup::SkyUnitToCm;
    require(std::isfinite(delta.Size())&&delta.Size()>1e-6,"Sky camera at planet center is undefined");
    FVector3f skyCamera;FVector4f planet;FMatrix44f basis;
    atmosphere.ComputeViewData(camera,FVector(p[0],p[1],p[2]),FVector3f(f[0],f[1],f[2]),FVector3f(r[0],r[1],r[2]),skyCamera,planet,basis);
    Result result;
    result.planetCenterKm={atmosphere.PlanetCenterKm.X,atmosphere.PlanetCenterKm.Y,atmosphere.PlanetCenterKm.Z};
    result.skyCameraTranslatedCm={skyCamera.X,skyCamera.Y,skyCamera.Z};
    result.planetTranslatedCmAndHeight={planet.X,planet.Y,planet.Z,planet.W};
    require(finite(result.skyCameraTranslatedCm),"Sky translated camera overflow");
    for(int i=0;i<4;++i)
    {
        require(std::isfinite(result.planetTranslatedCmAndHeight[i]),"Sky planet data overflow");
        for(int j=0;j<4;++j)
        {
            require(std::isfinite(basis.M[i][j]),"Sky basis overflow");result.referential[i][j]=basis.M[i][j];
        }
    }
    return result;
}
}
