TextureCube<float> gCube;
TextureCubeArray<float> gCubeArray;
SamplerState gPoint;
uint gSampleMip;
RWStructuredBuffer<float> gResult;
RWTexture2DArray<float> gArrayWrite;
Texture2DArray<float> gDepth;

// Native cube face order on both backends. Face-center point samples never
// cross an edge and each uploaded face/mip holds a different exact integer.
static const float3 kDirections[6] = {
    float3(1, 0, 0), float3(-1, 0, 0), float3(0, 1, 0),
    float3(0, -1, 0), float3(0, 0, 1), float3(0, 0, -1)
};

[numthreads(1, 1, 1)]
void sampleCube(uint3 tid : SV_DispatchThreadID)
{
    gResult[tid.x] = gCube.SampleLevel(gPoint, kDirections[tid.x], float(gSampleMip));
}

[numthreads(1, 1, 1)]
void sampleCubeArray(uint3 tid : SV_DispatchThreadID)
{
    gResult[tid.x] = gCubeArray.SampleLevel(gPoint, float4(kDirections[tid.x % 6], float(tid.x / 6)), float(gSampleMip));
}

[numthreads(1, 1, 1)]
void writeArrayFace(uint3 tid : SV_DispatchThreadID)
{
    gArrayWrite[tid] = 777.0;
    gResult[tid.y * 4 + tid.x] = 777.0;
}

[numthreads(1, 1, 1)]
void loadDepth(uint3 tid : SV_DispatchThreadID)
{
    gResult[tid.y * 4 + tid.x] = gDepth.Load(int4(tid.xy, 0, 0));
}
