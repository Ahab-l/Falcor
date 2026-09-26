// GPU-only observation converts a selected Cube mip into six horizontal faces.
#include "CubeDirections.slangh"
TextureCube<float4> SourceCubemapTexture;
SamplerState SourceCubemapSampler;
RWTexture2D<float4> Atlas;
cbuffer ReadbackParameters { uint Width; };
[numthreads(8,8,1)]
void main(uint3 p : SV_DispatchThreadID)
{
    if (p.x >= Width*6 || p.y >= Width) return;
    uint face = p.x/Width;
    float2 uv = (float2(p.x%Width,p.y)+0.5f)*2.0f/Width-1.0f;
    Atlas[p.xy] = SourceCubemapTexture.SampleLevel(SourceCubemapSampler, GetCubemapVector(uv,int(face)), 0);
}
