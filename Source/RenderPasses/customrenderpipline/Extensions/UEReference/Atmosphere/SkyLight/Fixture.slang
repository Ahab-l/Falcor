// Authored GPU fixture only. No capture data or CPU-produced image is uploaded.
#include "CubeDirections.slangh"
RWTexture2DArray<float4> FixtureCube;
cbuffer FixtureParameters { uint Width; uint Pattern; float3 ConstantColor; float Scale; };
[numthreads(8,8,1)]
void main(uint3 p : SV_DispatchThreadID)
{
    if (any(p.xy >= Width) || p.z >= 6) return;
    float3 d = normalize(GetCubemapVector((float2(p.xy)+0.5f)*2.0f/Width-1.0f, int(p.z)));
    float3 color = ConstantColor;
    if (Pattern == 1)
        color = float3(1.0f+0.31f*d.x+0.17f*d.y+0.09f*d.z+0.08f*d.x*d.y,
                       2.0f-0.11f*d.x+0.23f*d.y+0.07f*d.z+0.06f*d.y*d.z,
                       3.0f+0.13f*d.x-0.05f*d.y+0.29f*d.z+0.04f*(d.x*d.x-d.y*d.y));
    FixtureCube[p] = float4(color*Scale, 1.0f);
}
