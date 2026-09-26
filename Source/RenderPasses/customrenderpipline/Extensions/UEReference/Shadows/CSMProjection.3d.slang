#include "CSMParameters.slangh"
Texture2D<float4> gShadowDepth;
Texture2D<float4> gPosition;
Texture2D<float4> gNormal;
Texture2D<uint> gCoverage;
SamplerState gShadowSampler;
cbuffer CSMProjection { uint cascadeIndex; };
#define FLATTEN [flatten]
// FastMath.ush:12 and TransmissionCommon.ush:69. The opaque caller always
// sets bSubsurface=false; keeping the original function body requires these.
float4 FastExp(float4 x) { return exp2(1.442695f*x); }
float4 GetSubSurfaceTransmission(float4 d,float density) { return saturate(FastExp(-d*density)); }
#include "UECSMFiltering.ush"
#define MaterialFloat float
float ueCSMSquare(float x) { return x*x; }
#define Square ueCSMSquare
#include "UECSMEncode.ush"
#undef Square
#undef MaterialFloat
float4 main(float4 sv:SV_Position):SV_Target0
{
    uint2 pixel=uint2(sv.xy);
    if(gCoverage.Load(int3(pixel,0))==0)discard;
    float3 position=gPosition.Load(int3(pixel,0)).xyz;
    float4 splits=ueCSMData(cascadeIndex,4);
    float viewDepth=dot(position-ueCSMHeader(0).xyz,ueCSMHeader(1).xyz);
    if(viewDepth<splits.x || viewDepth>splits.y)discard;
    float4 clip=mul(ueCSMMatrix(cascadeIndex),float4(position,1));
    float3 shadow=clip.xyz/clip.w;
    if(any(abs(shadow.xy)>1))discard;
    float4 info=ueCSMHeader(2);
    float2 uv=(float2(shadow.x,-shadow.y)*.5+.5)*(info.x-2*info.y)/info.x+info.y/info.x;
    float3 normalUE=gNormal.Load(int3(pixel,0)).xyz;
    float3 normalW=float3(normalUE.y,normalUE.z,-normalUE.x);
    float4 light=ueCSMData(cascadeIndex,6);
    FPCFSamplerSettings settings;
    settings.ShadowDepthTexture=gShadowDepth;
    settings.ShadowDepthTextureSampler=gShadowSampler;
    settings.ShadowBufferSize=float4(info.xx,rcp(info.xx));
    settings.SceneDepth=min(1-shadow.z,0.99999);
    settings.TransitionScale=ueCSMData(cascadeIndex,5).w*lerp(1-light.w,1,saturate(dot(normalW,light.xyz)));
    settings.bSubsurface=false;
    settings.bTreatMaxDepthUnshadowed=false;
    settings.DensityMulConstant=0;
    settings.ProjectionDepthBiasParameters=0;
    float shadowFactor=Manual5x5PCF(uv,settings);
    shadowFactor=saturate((shadowFactor-.5)*(1+7*info.z)+.5);
    shadowFactor=ApplyPCFOverBlurCorrection(shadowFactor);
    float encoded=EncodeLightAttenuation(shadowFactor);
    float alpha=1-saturate((viewDepth-splits.z)*splits.w);
    // CSM hardware blending writes RG only; BA retain their clear value 1.
    return float4(encoded,1,encoded,alpha);
}
