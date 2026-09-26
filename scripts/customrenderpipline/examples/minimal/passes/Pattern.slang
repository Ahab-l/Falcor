RWTexture2D<float4> gColor;
[numthreads(8, 8, 1)]
void main(uint3 p : SV_DispatchThreadID)
{
    if (p.x >= 64 || p.y >= 32) return;
    gColor[p.xy] = float4(p.x / 64.0, p.y / 32.0, 0.25, 1.0);
}
