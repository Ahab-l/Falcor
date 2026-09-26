// Deterministic initial Cube mip zero before six source Mesh attachment writes.
RWTexture2DArray<float4> CaptureCube;
cbuffer CaptureInitParameters { uint Width; };
[numthreads(8,8,1)]
void main(uint3 p : SV_DispatchThreadID)
{
    if (any(p.xy >= Width) || p.z >= 6) return;
    CaptureCube[p] = 0.0f;
}
