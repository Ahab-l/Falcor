#pragma once
#include "Falcor.h"
#include "Core/Pass/FullScreenPass.h"
#include <array>
#include <cmath>

namespace Falcor::CustomRenderPipline
{
// Independent hardware conversion reference for numerical diagnostics. This
// shader deliberately has no material, Scene, Schema, or Codec dependencies.
inline std::array<std::vector<uint8_t>, 5> probeRTV(const ref<Device>& device, const std::vector<float>& values)
{
    FALCOR_CHECK(device && !values.empty() && values.size() <= 16384, "RTV probe needs 1..16384 values");
    for (const float value : values)
        FALCOR_CHECK(std::isfinite(value), "RTV probe requires finite float32 values");
    const uint32_t width = uint32_t(values.size());
    const char shader[] = R"(
StructuredBuffer<float> gProbeValues;
struct ProbeOutput
{
    float4 rgb10a2 : SV_Target0;
    float4 bgra8 : SV_Target1;
    float4 float32 : SV_Target2;
};
ProbeOutput probe(float2 texC : TEXCOORD, float4 position : SV_Position)
{
    const float value = gProbeValues[uint(position.x)];
    ProbeOutput output;
    output.rgb10a2 = float4(value);
    output.bgra8 = float4(value);
    output.float32 = float4(value);
    return output;
}
)";
    ProgramDesc desc;
    desc.addShaderModule().addString(shader, "CustomRenderPiplineIndependentRTVProbe.slang");
    desc.psEntry("probe").setShaderModel(ShaderModel::SM6_6);
    const auto pass = FullScreenPass::create(device, desc);
    pass->getRootVar()["gProbeValues"] = device->createStructuredBuffer(
        sizeof(float), width, ResourceBindFlags::ShaderResource, MemoryType::DeviceLocal, values.data(), false);
    std::vector<ref<Texture>> colors;
    for (const auto format : {ResourceFormat::RGB10A2Unorm, ResourceFormat::BGRA8Unorm, ResourceFormat::RGBA32Float})
        colors.push_back(device->createTexture2D(width, 1, format, 1, 1, nullptr, ResourceBindFlags::RenderTarget));
    auto context = device->getRenderContext();
    pass->execute(context, Fbo::create(device, colors));
    std::array<std::vector<uint8_t>, 5> result;
    for (uint32_t index = 0; index < 3; ++index)
        result[index] = context->readTextureSubresource(colors[index].get(), 0);
    // A raw byte ramp makes SRV sRGB conversion independently observable. Its
    // format conversion is hardware-defined within the D3D precision bounds.
    std::array<uint8_t, 256 * 4> ramp;
    for (uint32_t code = 0; code < 256; ++code)
    {
        for (uint32_t channel = 0; channel < 3; ++channel) ramp[code * 4 + channel] = uint8_t(code);
        ramp[code * 4 + 3] = 255;
    }
    const auto srgb = device->createTexture2D(256, 1, ResourceFormat::BGRA8UnormSrgb, 1, 1, ramp.data(), ResourceBindFlags::ShaderResource);
    const auto decoded = device->createTexture2D(256, 1, ResourceFormat::RGBA32Float, 1, 1, nullptr, ResourceBindFlags::RenderTarget);
    const char srgbShader[] = R"(
Texture2D<float4> gProbeSrgb;
float4 probeSrgb(float2 texC : TEXCOORD, float4 position : SV_Position) : SV_Target0
{
    return gProbeSrgb.Load(int3(uint(position.x), 0, 0));
}
)";
    ProgramDesc srgbDesc;
    srgbDesc.addShaderModule().addString(srgbShader, "CustomRenderPiplineIndependentSrgbProbe.slang");
    srgbDesc.psEntry("probeSrgb").setShaderModel(ShaderModel::SM6_6);
    const auto srgbPass = FullScreenPass::create(device, srgbDesc);
    srgbPass->getRootVar()["gProbeSrgb"] = srgb;
    srgbPass->execute(context, Fbo::create(device, {decoded}));
    result[3] = context->readTextureSubresource(decoded.get(), 0);
    result[4] = context->readTextureSubresource(srgb.get(), 0);
    return result;
}
} // namespace Falcor::CustomRenderPipline
