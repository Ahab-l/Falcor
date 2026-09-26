// Companion shaders for CustomRenderPiplineCapabilities.cpp. All raster programs compile as SM 6.6.
cbuffer DrawCB
{
    float4 gRegion;
    float gDepth;
    float4 gSceneColor;
    float4 gPackedColor;
    float4 gBgraColor;
    float4 gSrgbColor;
}

void restrictRegion(float4 position)
{
    if (any(position.xy < gRegion.xy) || any(position.xy >= gRegion.zw))
        discard;
}

// Match FullScreenPass.vs.slang's TEXCOORD-before-SV_POSITION signature register order.
float prepass(float2 texC : TEXCOORD, float4 position : SV_Position) : SV_Depth
{
    restrictRegion(position);
    return gDepth;
}

struct BasePassOutput
{
    float4 sceneColor : SV_Target0;
    float4 packedColor : SV_Target1;
    float4 bgraColor : SV_Target2;
    float4 srgbColor : SV_Target3;
    // GBuffer D is bound at slot 4 but is deliberately outside output validity.
    float depth : SV_Depth;
};

BasePassOutput basepass(float2 texC : TEXCOORD, float4 position : SV_Position)
{
    restrictRegion(position);
    BasePassOutput output;
    output.sceneColor = gSceneColor;
    output.packedColor = gPackedColor;
    output.bgraColor = gBgraColor;
    output.srgbColor = gSrgbColor;
    output.depth = gDepth;
    return output;
}

struct PredicateOutput
{
    float4 marker : SV_Target0;
    float depth : SV_Depth;
};

PredicateOutput predicate(float2 texC : TEXCOORD, float4 position : SV_Position)
{
    restrictRegion(position);
    PredicateOutput output;
    output.marker = float4(1, 0, 0, 1);
    output.depth = gDepth;
    return output;
}

Texture2D<float4> gSrgbTexture;
RWStructuredBuffer<float4> result;

cbuffer ReadbackCB
{
    uint2 gDimensions;
}

[numthreads(8, 8, 1)] void readSrgb(uint3 tid
                                    : SV_DispatchThreadID)
{
    if (any(tid.xy >= gDimensions))
        return;
    result[tid.y * gDimensions.x + tid.x] = gSrgbTexture.Load(int3(tid.xy, 0));
}

cbuffer ReadUnionCB
{
    uint gReadUnionIndex16;
    uint gReadUnionRotated;
    uint gReadUnionValue;
    uint gReadUnionDrawId;
}

ByteAddressBuffer gReadUnionVertices;
ByteAddressBuffer gReadUnionIndices;
RWByteAddressBuffer gWriteUnionVertices;
RWByteAddressBuffer gWriteUnionIndices;

struct ReadUnionVertexOutput
{
    nointerpolation uint value : TEXCOORD0;
    nointerpolation uint valid : TEXCOORD1;
    float4 position : SV_Position;
};

ReadUnionVertexOutput readUnionVS(float2 position : POSITION, uint value : TEXCOORD, uint vertexId : SV_VertexID)
{
    ReadUnionVertexOutput output;
    output.position = float4(position, 0, 1);
    output.value = value;
    output.valid = 1;
#if READ_UNION_WITH_SRV
    uint3 rawVertex = gReadUnionVertices.Load3(vertexId * 12);
    output.valid = all(asfloat(rawVertex.xy) == position) && rawVertex.z == value ? 1 : 0;
#endif
    return output;
}

uint4 readUnionPS(ReadUnionVertexOutput input) : SV_Target0
{
    uint valid = input.valid;
#if READ_UNION_WITH_SRV
    uint3 indices;
    if (gReadUnionIndex16 != 0)
    {
        uint2 words = gReadUnionIndices.Load2(0);
        indices = uint3(words.x & 0xffff, words.x >> 16, words.y & 0xffff);
    }
    else
        indices = gReadUnionIndices.Load3(0);
    uint3 expected = gReadUnionRotated != 0 ? uint3(2, 0, 1) : uint3(0, 1, 2);
    valid &= all(indices == expected) ? 1 : 0;
#endif
    return uint4(input.value, valid, gReadUnionDrawId, 1);
}

[numthreads(1, 1, 1)]
void writeReadUnionBuffers()
{
    for (uint vertex = 0; vertex < 3; ++vertex)
        gWriteUnionVertices.Store(vertex * 12 + 8, gReadUnionValue);
    uint3 indices = gReadUnionRotated != 0 ? uint3(2, 0, 1) : uint3(0, 1, 2);
    if (gReadUnionIndex16 != 0)
        gWriteUnionIndices.Store2(0, uint2(indices.x | (indices.y << 16), indices.z));
    else
        gWriteUnionIndices.Store3(0, indices);
}
