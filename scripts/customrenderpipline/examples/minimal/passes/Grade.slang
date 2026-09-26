Texture2D<float4> gSource;
RWTexture2D<float4> gColor;
cbuffer Settings { float gain; };
[numthreads(8, 8, 1)]
void main(uint3 p : SV_DispatchThreadID)
{
    if (p.x >= 64 || p.y >= 32) return;
    gColor[p.xy] = float4(gSource[p.xy].rgb * gain, 1.0);
}
