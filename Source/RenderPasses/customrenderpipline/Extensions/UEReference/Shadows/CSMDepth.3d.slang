import Scene.Raster;
#include "CSMParameters.slangh"
cbuffer UEMeshPass { float4x4 viewProjection; float3 baseColor; uint modelID; uint instanceID; };
cbuffer CSMDraw { uint cascadeIndex; };
struct UEShadowDepthParameters { float4 ShadowParams; uint bClampToNearPlane; };
static UEShadowDepthParameters PassStruct;
#define PLATFORM_NEEDS_PRECISE_SHADOW_DEPTH 0
#include "UECSMDepth.ush"
float4 vertexMain(VSIn vertex):SV_Position
{
    VSOut v=defaultVS(vertex);
    float4 bias=ueCSMData(cascadeIndex,5);
    PassStruct.ShadowParams=float4(bias.xyz,1);
    PassStruct.bClampToNearPlane=1;
    float3 axis=ueCSMData(cascadeIndex,6).xyz;
    // The original VS uses row-vector matrices; its slope function only reads
    // the normalized shadow-view Z axis. Clip matrix includes unit conversion.
    float4x4 view=float4x4(1,0,axis.x,0, 0,1,axis.y,0, 0,0,axis.z,0, 0,0,0,1);
    // LocalVertexFactory.ush removes instance scale before rotating the packed
    // vertex normal. Falcor's inverse-transpose normal is a different quantity.
    GeometryInstanceID meshInstance={instanceID};
    float3x3 object=(float3x3)gScene.getWorldMatrix(meshInstance);
    // PackedStaticVertexData.unpack() additionally normalizes the decoded
    // vector. UE preserves the source TangentZ magnitude for this slope bias.
    uint2 packed=asuint(vertex.packedNormalTangentCurveRadius.xy);
    float3 local=float3(f16tof32(packed.x&0xffff),f16tof32(packed.x>>16),f16tof32(packed.y&0xffff));
    float3 normal=normalize(mul(object,float3(1,0,0)))*local.x+
                  normalize(mul(object,float3(0,1,0)))*local.y+
                  normalize(mul(object,float3(0,0,1)))*local.z;
    float4 position=TransformShadowDirectional(transpose(ueCSMMatrix(cascadeIndex)),view,float4(v.posW,1),normal);
    // ShadowSetup.cpp's outer clip projection renders the PCF border as well.
    // An inset viewport would align the inner samples but lose border casters.
    float4 info=ueCSMHeader(2);
    position.xy*=(info.x-2*info.y)/info.x;
    return position;
}
