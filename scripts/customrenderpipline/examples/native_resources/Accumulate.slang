ByteAddressBuffer increment;
Texture2D<float4> previous;
RWTexture2D<float4> current;
cbuffer Params { uint2 extent; };

[numthreads(8,8,1)]
void main(uint3 p : SV_DispatchThreadID)
{
    if (any(p.xy >= extent)) return;
    // The native History reader clears invalid/first-frame history to zero.
    current[p.xy] = previous[p.xy] + asfloat(increment.Load4(0));
}
