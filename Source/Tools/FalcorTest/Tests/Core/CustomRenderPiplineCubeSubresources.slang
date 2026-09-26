TextureCube<float> gCube;
Texture2DArray<float> gArrayRead;
RWTexture2DArray<float> gWrite;
SamplerState gPoint;
RWStructuredBuffer<float> gResult;

// D3D cube face order: +X, -X, +Y, -Y, +Z, -Z. Face centers avoid filtering across edges.
static const float3 kFaceDirections[6] = {
    float3(1, 0, 0), float3(-1, 0, 0), float3(0, 1, 0),
    float3(0, -1, 0), float3(0, 0, 1), float3(0, 0, -1)
};

[numthreads(1, 1, 1)]
void writeFace(uint3 tid : SV_DispatchThreadID)
{
    // The view starts at physical face 5; shader layer zero must address that face.
    gWrite[tid] = 777.0;
}

[numthreads(1, 1, 1)]
void sampleFaces(uint3 tid : SV_DispatchThreadID)
{
    gResult[tid.x] = gCube.SampleLevel(gPoint, kFaceDirections[tid.x], 0.0);
}

[numthreads(1, 1, 1)]
void copyMip(uint3 tid : SV_DispatchThreadID)
{
    gWrite[tid] = gCube.SampleLevel(gPoint, kFaceDirections[tid.z], 0.0) + 1000.0;
}

[numthreads(1, 1, 1)]
void copyArrayMip(uint3 tid : SV_DispatchThreadID)
{
    gWrite[tid] = gArrayRead.Load(int4(tid.xy * 2, tid.z, 0)) + 1000.0;
}
