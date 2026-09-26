#include "Scene/VertexAttrib.slangh"
import Scene.Raster;

#ifndef CRP_CODEC_HEADER
#error CRP_CODEC_HEADER must name the generated source-owned Schema codec.
#endif
#include CRP_CODEC_HEADER
#include "Material.slangh"

struct TransformParams
{
    float4x4 projection;
};
ConstantBuffer<TransformParams> Transform;

VSOut vsMain(VSIn input)
{
    VSOut output = defaultVS(input);
    output.posH = mul(Transform.projection, float4(output.posW, 1.0f));
    return output;
}

TargetMapSurfacePacked psMain(VSOut input)
{
    TargetMapSurfaceFields fields = evaluateSourceMaterial(input);
    TargetMapSurfacePacked output;
    if (!TargetMapSurfaceEncode(fields, output)) discard;
    return output;
}
