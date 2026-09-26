// Diagnostic only: expose source-port operations for the first (grazing) x texel.
#include "PreintegratedGFSourceMath.slangh"
RWTexture2D<float4> gDistribution;
RWTexture2D<float4> gHemisphere;
RWTexture2D<float4> gWeights;
[numthreads(8, 8, 1)]
void main(uint3 threadId : SV_DispatchThreadID)
{
    if (threadId.x >= 128 || threadId.y >= 32) return;
    uint i = threadId.x;
    precise float Roughness = (float(threadId.y) + 0.5f) / 32.0f;
    precise float m = Roughness * Roughness;
    precise float m2 = m * m;
    precise float NoV = 0.5f / 128.0f;
    precise float3 V = float3(SourceCPUFloatSqrt(1.0f - NoV * NoV), 0.0f, NoV);
    precise float E1 = float(i) / 128.0f;
    precise float E2 = float(reversebits(i)) / 4294967296.0f;
    precise float Phi = 2.0f * 3.1415926535897932f * E1;
    precise float Denominator = 1.0f + (m2 - 1.0f) * E2;
    precise float Ratio = SourceCPUFloatDivide(1.0f - E2, Denominator);
    precise float CosTheta = SourceCPUFloatSqrt(Ratio);
    precise float SinTheta = SourceCPUFloatSqrt(1.0f - CosTheta * CosTheta);
    precise float CosPhi = SourceCPUFloatCos(Phi);
    precise float3 H = float3(SinTheta * CosPhi, SinTheta * sin(Phi), CosTheta);
    precise float VDotH = (V.x * H.x + V.y * H.y) + V.z * H.z;
    precise float3 L = (2.0f * VDotH) * H - V;
    precise float NoL = max(L.z, 0.0f);
    precise float NoH = max(H.z, 0.0f);
    precise float VoH = max(VDotH, 0.0f);
    precise float Vis_SmithV = NoL * (NoV * (1.0f - m) + m);
    precise float Vis_SmithL = NoV * (NoL * (1.0f - m) + m);
    precise float Vis = SourceCPUFloatDivide(0.5f, Vis_SmithV + Vis_SmithL);
    precise float Weight = NoL * Vis * SourceCPUFloatDivide(4.0f * VoH, NoH);
    precise float Fc = 1.0f - VoH;
    precise float Fc2 = Fc * Fc;
    Fc *= Fc2 * Fc2;
    gDistribution[threadId.xy] = float4(E2, m2, Denominator, Ratio);
    gHemisphere[threadId.xy] = float4(Phi, CosPhi, CosTheta, SinTheta);
    gWeights[threadId.xy] = float4(VDotH, NoL, Weight, Fc);
}
