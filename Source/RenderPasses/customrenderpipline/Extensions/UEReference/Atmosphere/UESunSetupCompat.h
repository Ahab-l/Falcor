#pragma once
#include <algorithm>
#include <cmath>
#include <type_traits>

// Minimal type adapter for unchanged UE CPU functions. FVector and FVector2D
// are double in this engine revision, unlike FVector3f and FLinearColor.
// The color matrices use UE row-vector convention and double arithmetic.
namespace Falcor::CustomRenderPipline::SunSetup::Compat
{
enum EForceInit { ForceInitToZero };
template<typename T> struct Vector2
{
    T X{},Y{};
    Vector2(T x,T y):X(x),Y(y){}
    T operator[](unsigned i) const { return i==0?X:Y; }
};
template<typename T> struct Vector3
{
    using FReal=T;
    T X{},Y{},Z{};
    Vector3()=default;
    Vector3(EForceInit){}
    Vector3(T x,T y,T z):X(x),Y(y),Z(z){}
    template<typename U> explicit Vector3(const Vector3<U>& v):X(T(v.X)),Y(T(v.Y)),Z(T(v.Z)){}
    T operator[](unsigned i) const { return i==0?X:i==1?Y:Z; }
    Vector3 operator-(Vector3 b) const { return {X-b.X,Y-b.Y,Z-b.Z}; }
    Vector3 operator+(Vector3 b) const { return {X+b.X,Y+b.Y,Z+b.Z}; }
    Vector3 operator*(T b) const { return {X*b,Y*b,Z*b}; }
    Vector3 operator/(T b) const { return *this*(T(1)/b); }
    friend Vector3 operator*(T a,Vector3 b) { return b*a; }
    static T DotProduct(Vector3 a,Vector3 b) { return a.X*b.X+a.Y*b.Y+a.Z*b.Z; }
    T operator|(Vector3 b) const { return DotProduct(*this,b); }
    static T Distance(Vector3 a,Vector3 b) { auto d=a-b; return std::sqrt(DotProduct(d,d)); }
    T Size() const { return std::sqrt(X*X+Y*Y+Z*Z); }
    static Vector3 CrossProduct(Vector3 a,Vector3 b)
    { return {a.Y*b.Z-a.Z*b.Y,a.Z*b.X-a.X*b.Z,a.X*b.Y-a.Y*b.X}; }
    bool Normalize(T tolerance=T(1e-8f))
    {
        T square=X*X+Y*Y+Z*Z;
        if(square>tolerance) { T scale=T(1)/std::sqrt(square);X*=scale;Y*=scale;Z*=scale;return true; }
        return false;
    }
    Vector3 GetSafeNormal() const
    {
        T square=DotProduct(*this,*this);
        if(square==T(1)) return *this;
        if(square<T(1e-8f)) return {};
        return *this*(T(1)/std::sqrt(square));
    }
    static const Vector3 ForwardVector,LeftVector,UpVector;
};
template<typename T> inline const Vector3<T> Vector3<T>::ForwardVector{1,0,0};
template<typename T> inline const Vector3<T> Vector3<T>::LeftVector{0,-1,0};
template<typename T> inline const Vector3<T> Vector3<T>::UpVector{0,0,1};
using FVector3f=Vector3<float>;
using FVector3d=Vector3<double>;
using FVector=FVector3d;
using FVector2D=Vector2<double>;
using FVector2d=FVector2D;
struct FVector4d: FVector3d { using FVector3d::FVector3d; };
struct FLinearColor
{
    float R{},G{},B{},A{1};
    FLinearColor()=default;
    FLinearColor(EForceInit):A(0){}
    FLinearColor(float r,float g,float b):R(r),G(g),B(b){}
    FLinearColor operator+(FLinearColor v) const { return {R+v.R,G+v.G,B+v.B}; }
    FLinearColor& operator+=(FLinearColor v) { R+=v.R;G+=v.G;B+=v.B;return *this; }
    FLinearColor operator*(FLinearColor v) const { return {R*v.R,G*v.G,B*v.B}; }
    FLinearColor operator*(float v) const { return {R*v,G*v,B*v}; }
    friend FLinearColor operator*(float v,FLinearColor c) { return c*v; }
};
struct FMatrix44d
{
    double M[4][4]{};
    FMatrix44d() { M[3][3]=1; }
    FMatrix44d(FVector3d a,FVector3d b,FVector3d c,FVector3d d):FMatrix44d()
    { const FVector3d rows[]={a,b,c,d}; for(unsigned i=0;i<4;++i) for(unsigned j=0;j<3;++j) M[i][j]=rows[i][j]; }
    FVector4d TransformVector(FVector3d v) const
    { return {v.X*M[0][0]+v.Y*M[1][0]+v.Z*M[2][0],v.X*M[0][1]+v.Y*M[1][1]+v.Z*M[2][1],v.X*M[0][2]+v.Y*M[1][2]+v.Z*M[2][2]}; }
    FMatrix44d Inverse() const
    {
        // These color matrices have zero translation and an affine last row.
        // Cofactor inverse in double; no claim of matching UE SIMD instruction bits.
        FMatrix44d result;
        for(unsigned i=0;i<3;++i) for(unsigned j=0;j<3;++j)
            result.M[j][i]=M[(i+1)%3][(j+1)%3]*M[(i+2)%3][(j+2)%3]-M[(i+1)%3][(j+2)%3]*M[(i+2)%3][(j+1)%3];
        double det=M[0][0]*result.M[0][0]+M[0][1]*result.M[1][0]+M[0][2]*result.M[2][0];
        for(unsigned i=0;i<3;++i) for(unsigned j=0;j<3;++j) result.M[i][j]/=det;
        return result;
    }
};
struct FMath
{
    template<typename A,typename B> static auto Max(A a,B b) { using T=std::common_type_t<A,B>;return std::max(T(a),T(b)); }
    template<typename T> static T Min(T a,T b) { return std::min(a,b); }
    template<typename T> static T Clamp(T a,T lo,T hi) { return std::clamp(a,lo,hi); }
    static float Exp(float v) { return std::exp(v); }
    template<typename T> static T Sin(T v) { return std::sin(v); }
    template<typename T> static T Cos(T v) { return std::cos(v); }
    template<typename T> static T Acos(T v) { return std::acos(std::clamp(v,T(-1),T(1))); }
    template<typename T> static T Asin(T v) { return std::asin(std::clamp(v,T(-1),T(1))); }
    static float DegreesToRadians(float v) { return v*(3.1415926535897932f/180.f); }
    static FVector2D GetAzimuthAndElevation(const FVector&,const FVector&,const FVector&,const FVector&);
};
struct FColorSpace
{
    FVector2d Chromaticities[4]={{.64,.33},{.30,.60},{.15,.06},{.3127,.3290}};
    FMatrix44d XYZToRgb;
    FColorSpace():XYZToRgb(CalcRgbToXYZ().Inverse()){}
    FMatrix44d CalcRgbToXYZ() const;
    FLinearColor MakeFromColorTemperature(float Temp) const;
};
struct FAtmosphereSetup
{
    float BottomRadiusKm{},TopRadiusKm{},MieDensityExpScale{},RayleighDensityExpScale{};
    float AbsorptionDensity0LayerWidth{},AbsorptionDensity0LinearTerm{},AbsorptionDensity0ConstantTerm{};
    float AbsorptionDensity1LinearTerm{},AbsorptionDensity1ConstantTerm{},TransmittanceMinLightElevationAngle{};
    FLinearColor MieExtinction,RayleighScattering,AbsorptionExtinction;
    FLinearColor GetTransmittanceAtGroundLevel(const FVector& SunDirection) const;
};
}
