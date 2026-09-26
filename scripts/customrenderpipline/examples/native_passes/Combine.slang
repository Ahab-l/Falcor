Texture2D<float4> surface;
Texture2D<float4> selection;
RWTexture2D<float4> result;
cbuffer Params { uint2 extent; };

[numthreads(8, 8, 1)]
void main(uint3 p : SV_DispatchThreadID)
{
    if (any(p.xy >= extent)) return;
    float4 base = surface.Load(int3(p.xy, 0));
    float4 selected = selection.Load(int3(p.xy, 0));
    result[p.xy] = float4(lerp(base.rgb, selected.rgb, selected.a * 0.5), base.a);
}
