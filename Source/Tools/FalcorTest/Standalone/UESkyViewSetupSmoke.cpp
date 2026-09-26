#include "../../../RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/UESkyViewSetup.h"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace Falcor::CustomRenderPipline::SkyViewSetup;
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
void close(double actual,double expected,double tolerance,const char* label)
{ require(std::abs(actual-expected)<=tolerance,label); }
double determinant(const Result& r)
{
    const auto& a=r.referential;
    return a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])-a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])+a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0]);
}
void orthonormal(const Result& r)
{
    for(int i=0;i<3;++i) for(int j=0;j<3;++j)
    {
        double dot=0;for(int k=0;k<3;++k)dot+=double(r.referential[i][k])*r.referential[j][k];
        close(dot,i==j?1:0,3e-6,"orthonormal sky basis");
    }
}
int main()
{
    Input input{};
    input.bottomRadiusKm=10; input.transformMode=0; input.cameraUECm={0,0,1000};
    input.viewForwardUE={1,0,0}; input.viewRightUE={0,1,0};
    auto above=evaluate(input);
    close(above.skyCameraTranslatedCm[2],1000,0,"above-surface camera remains unchanged");
    close(above.planetTranslatedCmAndHeight[3],1001000,0,"radial view height in cm");
    orthonormal(above);close(determinant(above),-1,1e-6,"ordinary UE left basis is reflected");
    input.cameraUECm={0,0,-100};auto below=evaluate(input);
    close(below.skyCameraTranslatedCm[2],500,1e-3,"camera snaps 5m above sea level");
    input.preViewTranslationCm={4096,-8192,16384};auto translated=evaluate(input);
    for(int i=0;i<3;++i)close(translated.skyCameraTranslatedCm[i]-input.preViewTranslationCm[i],below.skyCameraTranslatedCm[i],.002,"translated camera");
    for(int i=0;i<4;++i)for(int j=0;j<4;++j)close(translated.referential[i][j],below.referential[i][j],1e-6,"translation invariant referential");
    input.preViewTranslationCm={0,0,0};input.cameraUECm={0,0,1000};input.viewForwardUE={0,0,1};
    auto pole=evaluate(input);orthonormal(pole);close(determinant(pole),1,1e-6,"UE Duff pole branch orientation");
    input.transformMode=2;input.componentTranslationCm={0,0,0};input.cameraUECm={0,0,-1001000};
    auto south=evaluate(input);orthonormal(south);close(south.referential[2][2],-1,1e-6,"south pole");
    input.cameraUECm={300000,400000,1000000};input.viewForwardUE={1,0,0};auto tilted=evaluate(input);orthonormal(tilted);
    double length=std::sqrt(1.25e12);
    for(int i=0;i<3;++i)close(tilted.referential[2][i],input.cameraUECm[i]/length,2e-7,"arbitrary spherical up");
    input.transformMode=1;input.componentTranslationCm={0,0,-6000};input.cameraUECm={0,0,1000};
    auto offset=evaluate(input);close(offset.planetCenterKm[2],-10.06,2e-9,"component transform retains UE float cm-to-km constant");
    for(int kind=0;kind<4;++kind)
    {
        auto bad=input;
        if(kind==0)bad.bottomRadiusKm=0;
        if(kind==1)bad.viewForwardUE={0,0,0};
        if(kind==2)bad.cameraUECm[0]=std::numeric_limits<double>::infinity();
        if(kind==3) { bad.transformMode=2;bad.componentTranslationCm={0,0,0};bad.cameraUECm={0,0,0}; }
        bool rejected=false;try {evaluate(bad);}catch(const std::exception&){rejected=true;}
        require(rejected,"invalid sky view accepted");
    }
    std::cout<<"SKY_VIEW_SETUP_PASS\n";
}
