// Copyright Epic Games, Inc. All Rights Reserved.
// GPU source-algorithm port of SystemTextures.cpp567-617,641-642,652-656.
// This is authored adapter code, not an original UE shader entry point.
// See PreintegratedGFSource.json and the unchanged CPU excerpt.
#include "PreintegratedGFSourceMath.slangh"
RWTexture2D<float2> gPreintegratedGF;
RWTexture2D<float2> gIntegratedAB;

[numthreads(8, 8, 1)]
void main(uint3 threadId : SV_DispatchThreadID)
{
    if (threadId.x >= 128 || threadId.y >= 32) return;
    precise float Roughness = (float(threadId.y) + 0.5f) / 32.0f;
    precise float m = Roughness * Roughness;
    precise float m2 = m * m;
    precise float NoV = (float(threadId.x) + 0.5f) / 128.0f;
    precise float3 V = float3(SourceCPUFloatSqrt(1.0f - NoV * NoV), 0.0f, NoV);
    precise float A = 0.0f;
    precise float B = 0.0f;
    const uint NumSamples = 128;
    [loop]
    for (uint i = 0; i < NumSamples; i++)
    {
        precise float E1 = float(i) / float(NumSamples);
        // The source's double conversion is exact for this 128-sample sequence.
        precise float E2 = float(reversebits(i)) / 4294967296.0f;
        precise float Phi = 2.0f * 3.1415926535897932f * E1;
        precise float CosTheta = SourceCPUFloatSqrt(SourceCPUFloatDivide(1.0f - E2, 1.0f + (m2 - 1.0f) * E2));
        precise float SinTheta = SourceCPUFloatSqrt(1.0f - CosTheta * CosTheta);
        precise float3 H = float3(SinTheta * SourceCPUFloatCos(Phi), SinTheta * sin(Phi), CosTheta);
        // Explicit association matches FVector3f::operator|. precise prevents
        // contraction/reassociation; hardware transcendental parity is tested.
        precise float VDotH = (V.x * H.x + V.y * H.y) + V.z * H.z;
        precise float3 L = (2.0f * VDotH) * H - V;
        precise float NoL = max(L.z, 0.0f);
        precise float NoH = max(H.z, 0.0f);
        precise float VoH = max(VDotH, 0.0f);
        if (NoL > 0.0f)
        {
            precise float Vis_SmithV = NoL * (NoV * (1.0f - m) + m);
            precise float Vis_SmithL = NoV * (NoL * (1.0f - m) + m);
            precise float Vis = SourceCPUFloatDivide(0.5f, Vis_SmithV + Vis_SmithL);
            precise float NoL_Vis_PDF = NoL * Vis * SourceCPUFloatDivide(4.0f * VoH, NoH);
            precise float Fc = 1.0f - VoH;
            precise float Fc2 = Fc * Fc;
            Fc *= Fc2 * Fc2;
            A += NoL_Vis_PDF * (1.0f - Fc);
            B += NoL_Vis_PDF * Fc;
        }
    }
    A /= float(NumSamples);
    B /= float(NumSamples);
    // Source C integrates diffuse but is not stored in PF_G16R16; it has no
    // dependency on A/B and is intentionally excluded from this RG-only port.
    precise float2 integrated = float2(A, B);
    precise float2 codes = floor(clamp(integrated, 0.0f, 1.0f) * 65535.0f + 0.5f);
    gIntegratedAB[threadId.xy] = integrated;
    gPreintegratedGF[threadId.xy] = codes / 65535.0f;
}
