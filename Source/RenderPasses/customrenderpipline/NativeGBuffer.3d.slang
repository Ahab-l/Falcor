#include "Scene/VertexAttrib.slangh"
#include "NativeGBufferCodec.slangh"
import Scene.Raster;
import Rendering.Materials.TexLODHelpers;

struct Output
{
#if PACKED_LAYOUT
    uint materialBits : SV_Target0;
    float4 color : SV_Target1;
    float4 normal : SV_Target2;
#else
    float4 colorRoughness : SV_Target0;
    float4 normal : SV_Target1;
#endif
};

VSOut vsMain(VSIn input) { return defaultVS(input); }

Output psMain(VSOut input, uint triangleIndex : SV_PrimitiveID)
{
    float3 faceNormal = gScene.getFaceNormalW(input.instanceID, triangleIndex);
    VertexData vertex = prepareVertexData(input, faceNormal);
    let lod = ImplicitLodTextureSampler();
    if (gScene.materials.alphaTest(vertex, input.materialID, lod)) discard;
    float3 view = normalize(gScene.camera.getPosition() - vertex.posW);
    ShadingData sd = gScene.materials.prepareShadingData(vertex, input.materialID, view);
    let material = gScene.materials.getMaterialInstance(sd, lod, uint(MaterialInstanceHints::AdjustShadingNormal));
    let properties = material.getProperties(sd);
    Output result;
#if PACKED_LAYOUT
    result.materialBits = packNativeMaterial(properties.roughness, input.materialID, any(properties.emission > 0));
    result.color = float4(properties.diffuseReflectionAlbedo, 1);
#else
    result.colorRoughness = float4(properties.diffuseReflectionAlbedo, properties.roughness);
#endif
    result.normal = float4(properties.guideNormal, 1);
    return result;
}
