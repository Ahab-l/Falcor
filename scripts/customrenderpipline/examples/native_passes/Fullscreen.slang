Texture2D<float4> source;
cbuffer Params { float gain; };
float4 main(float4 p : SV_Position) : SV_Target0
{
    float4 value = source.Load(int3(p.xy, 0));
    return float4(value.rgb * gain, value.a);
}
