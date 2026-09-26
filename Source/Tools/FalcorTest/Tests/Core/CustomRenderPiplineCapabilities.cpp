// GPU capability probes for the UE legacy deferred BasePass attachment contract.
#include "Testing/UnitTest.h"
#include "Core/API/BlendState.h"
#include "Core/API/FBO.h"
#include "Core/API/GFXAPI.h"
#include "Core/API/NativeHandleTraits.h"
#include "Core/Pass/FullScreenPass.h"
#include "Core/State/GraphicsState.h"
#include "../../../../RenderPasses/customrenderpipline/CustomRenderPiplineReadback.h"

#if FALCOR_HAS_D3D12
#include <d3d12sdklayers.h>
#endif

#include <array>
#include <cmath>
#include <cstring>

namespace Falcor
{
namespace
{
const char kShader[] = "Tests/Core/CustomRenderPiplineCapabilities.slang";
constexpr uint32_t kWidth = 32;
constexpr uint32_t kHeight = 16;
const float4 kWhole(0.f, 0.f, float(kWidth), float(kHeight));
const float4 kRegionA(2.f, 2.f, 12.f, 14.f);
const float4 kRegionB(14.f, 2.f, 24.f, 14.f);
const std::array<uint2, 3> kPixels = {uint2(6, 6), uint2(18, 6), uint2(28, 6)};
const std::array<ResourceFormat, 5> kFormats = {
    ResourceFormat::RGBA16Float,
    ResourceFormat::RGB10A2Unorm,
    ResourceFormat::BGRA8Unorm,
    ResourceFormat::BGRA8UnormSrgb,
    ResourceFormat::BGRA8Unorm,
};
// Independent view-format oracle; do not derive expected values through Falcor's mapping helper.
const std::array<gfx::Format, 5> kExpectedGfxFormats = {
    gfx::Format::R16G16B16A16_FLOAT,
    gfx::Format::R10G10B10A2_UNORM,
    gfx::Format::B8G8R8A8_UNORM,
    gfx::Format::B8G8R8A8_UNORM_SRGB,
    gfx::Format::B8G8R8A8_UNORM,
};

struct Colors
{
    float4 scene;
    std::array<uint16_t, 4> sceneHalfBits;
    uint4 packed;
    uint4 bgra;
    float4 srgb;
};

// Integer UNORM codes are centered in quantization bins; half values are exactly representable.
const Colors kColorsA = {
    float4(-0.5f, 1.5f, 4.f, 0.375f),
    {0xb800, 0x3e00, 0x4400, 0x3600},
    uint4(123, 456, 789, 2),
    uint4(17, 93, 201, 61),
    float4(0.002f, 0.18f, 0.72f, 73.f / 255.f),
};
const Colors kColorsB = {
    float4(0.125f, 2.25f, -1.f, 0.75f),
    {0x3000, 0x4080, 0xbc00, 0x3a00},
    uint4(900, 211, 37, 1),
    uint4(231, 47, 109, 173),
    float4(0.6f, 0.04f, 0.35f, 181.f / 255.f),
};

using ColorReadback = std::array<std::vector<uint8_t>, 4>;

double encodeSrgb(double linear)
{
    return linear <= 0.0031308 ? 12.92 * linear : 1.055 * std::pow(linear, 1.0 / 2.4) - 0.055;
}

// Assert the independently specified byte contract, before considering SRV conversion.
void expectColorPixel(GPUUnitTestContext& ctx, const ColorReadback& data, const uint2& pixel, const Colors* expected)
{
    const size_t index = pixel.y * kWidth + pixel.x;
    for (uint32_t rt = 0; rt < data.size(); ++rt)
        ASSERT_EQ(data[rt].size(), size_t(kWidth * kHeight) * (rt == 0 ? 8 : 4));

    if (!expected)
    {
        for (uint32_t rt = 0; rt < data.size(); ++rt)
        {
            const size_t pixelSize = rt == 0 ? 8 : 4;
            for (size_t byte = 0; byte < pixelSize; ++byte)
                EXPECT_EQ(uint32_t(data[rt][index * pixelSize + byte]), 0u) << "untouched clear, RT " << rt;
        }
        return;
    }

    std::array<uint16_t, 4> halfBits;
    std::memcpy(halfBits.data(), data[0].data() + index * 8, 8);
    for (uint32_t channel = 0; channel < 4; ++channel)
        EXPECT_EQ(halfBits[channel], expected->sceneHalfBits[channel]) << "SceneColor half channel " << channel;

    uint32_t packed;
    std::memcpy(&packed, data[1].data() + index * 4, 4);
    const uint32_t expectedPacked =
        expected->packed.x | (expected->packed.y << 10) | (expected->packed.z << 20) | (expected->packed.w << 30);
    EXPECT_EQ(packed, expectedPacked) << "RGB10A2 exact packed word";

    const uint32_t memoryToRgba[] = {2, 1, 0, 3};
    for (uint32_t byte = 0; byte < 4; ++byte)
    {
        const uint32_t channel = memoryToRgba[byte];
        EXPECT_EQ(uint32_t(data[2][index * 4 + byte]), expected->bgra[channel]) << "BGRA8 memory byte " << byte;
        const double encoded = channel == 3 ? expected->srgb[channel] : encodeSrgb(expected->srgb[channel]);
        const int expectedByte = int(std::lround(encoded * 255.0));
        const int error = std::abs(int(data[3][index * 4 + byte]) - expectedByte);
        EXPECT_LE(error, channel == 3 ? 0 : 1) << "BGRA8 sRGB memory byte " << byte << "; alpha must remain linear";
    }
}

void requireCapabilities(GPUUnitTestContext& ctx)
{
    if (!ctx.getDevice()->isShaderModelSupported(ShaderModel::SM6_6))
        ctx.skip("CAPABILITY GAP: shader model 6.6 is unavailable.");
    const auto colorFlags = ResourceBindFlags::RenderTarget | ResourceBindFlags::ShaderResource;
    for (const auto format : kFormats)
    {
        if ((ctx.getDevice()->getFormatBindFlags(format) & colorFlags) != colorFlags)
            ctx.skip(fmt::format("CAPABILITY GAP: {} lacks render-target/SRV support.", to_string(format)).c_str());
    }
    if (!is_set(ctx.getDevice()->getFormatBindFlags(ResourceFormat::D32FloatS8Uint), ResourceBindFlags::DepthStencil))
        ctx.skip("CAPABILITY GAP: D32FloatS8Uint lacks depth/stencil attachment support.");
}

ref<Texture> createDepth(const ref<Device>& device)
{
    // D32S8 SRV conversion/plane selection is unavailable in Falcor. Views are lazy; never request its SRV.
    return device->createTexture2D(kWidth, kHeight, ResourceFormat::D32FloatS8Uint, 1, 1, nullptr, ResourceBindFlags::DepthStencil);
}

ref<FullScreenPass> createPass(const ref<Device>& device, const char* entry)
{
    ProgramDesc desc;
    desc.addShaderLibrary(kShader).psEntry(entry).setShaderModel(ShaderModel::SM6_6);
    auto pass = FullScreenPass::create(device, desc);
    pass->getState()->setRasterizerState(RasterizerState::create(RasterizerState::Desc().setCullMode(RasterizerState::CullMode::None)));
    return pass;
}

void setRegionAndDepth(const ref<FullScreenPass>& pass, const float4& region, float depth)
{
    auto var = pass->getRootVar()["DrawCB"];
    var["gRegion"] = region;
    var["gDepth"] = depth;
}

void runPrepass(GPUUnitTestContext& ctx, const ref<Texture>& depth)
{
    auto fbo = Fbo::create(ctx.getDevice(), {}, depth);
    auto pass = createPass(ctx.getDevice(), "prepass");
    pass->getState()->setDepthStencilState(DepthStencilState::create(
        DepthStencilState::Desc().setDepthEnabled(true).setDepthFunc(ComparisonFunc::GreaterEqual).setDepthWriteMask(true)
    ));
    ctx.getRenderContext()->clearDsv(depth->getDSV().get(), 0.f, 0x09, true, true);
    setRegionAndDepth(pass, kWhole, 0.75f);
    pass->execute(ctx.getRenderContext(), fbo);
    setRegionAndDepth(pass, kWhole, 0.25f);
    pass->execute(ctx.getRenderContext(), fbo); // The farther primitive must not replace reverse-Z depth.
}

DepthStencilState::Desc baseDepthStencilDesc()
{
    using Face = DepthStencilState::Face;
    using Op = DepthStencilState::StencilOp;
    return DepthStencilState::Desc()
        .setDepthEnabled(true)
        .setDepthFunc(ComparisonFunc::GreaterEqual)
        .setDepthWriteMask(false)
        .setStencilEnabled(true)
        .setStencilFunc(Face::FrontAndBack, ComparisonFunc::Always)
        .setStencilOp(Face::FrontAndBack, Op::Keep, Op::Keep, Op::Replace)
        .setStencilRef(0x86)
        .setStencilReadMask(0xFF)
        .setStencilWriteMask(0xF6);
}

void drawBase(
    GPUUnitTestContext& ctx,
    const ref<FullScreenPass>& pass,
    const ref<Fbo>& fbo,
    const float4& region,
    float depth,
    const Colors& colors,
    bool reverseFacing = false
)
{
    setRegionAndDepth(pass, region, depth);
    auto var = pass->getRootVar()["DrawCB"];
    var["gSceneColor"] = colors.scene;
    var["gPackedColor"] = float4(colors.packed) / float4(1023.f, 1023.f, 1023.f, 3.f);
    var["gBgraColor"] = float4(colors.bgra) / 255.f;
    var["gSrgbColor"] = colors.srgb;
    pass->getState()->setRasterizerState(
        RasterizerState::create(RasterizerState::Desc().setCullMode(RasterizerState::CullMode::None).setFrontCounterCW(reverseFacing))
    );
    pass->execute(ctx.getRenderContext(), fbo);
}

ref<FullScreenPass> createBasePass(const ref<Device>& device)
{
    auto pass = createPass(device, "basepass");
    pass->getState()->setDepthStencilState(DepthStencilState::create(baseDepthStencilDesc()));
    pass->getState()->setStencilRef(0x86);
    BlendState::Desc blend;
    blend.setIndependentBlend(true).setRenderTargetWriteMask(4, false, false, false, false);
    pass->getState()->setBlendState(BlendState::create(blend));
    return pass;
}

ColorReadback readColors(GPUUnitTestContext& ctx, const ref<Fbo>& fbo)
{
    ColorReadback result;
    for (uint32_t rt = 0; rt < result.size(); ++rt)
        result[rt] = ctx.getRenderContext()->readTextureSubresource(fbo->getColorTexture(rt).get(), 0);
    return result;
}

void inspectNativeResource(GPUUnitTestContext& ctx, const ref<Texture>& texture, const char* label)
{
#if FALCOR_HAS_D3D12
    DXGI_FORMAT typed = DXGI_FORMAT_UNKNOWN;
    DXGI_FORMAT typeless = DXGI_FORMAT_UNKNOWN;
    switch (texture->getFormat())
    {
    case ResourceFormat::RGBA16Float:
        typed = DXGI_FORMAT_R16G16B16A16_FLOAT;
        typeless = DXGI_FORMAT_R16G16B16A16_TYPELESS;
        break;
    case ResourceFormat::RGB10A2Unorm:
        typed = DXGI_FORMAT_R10G10B10A2_UNORM;
        typeless = DXGI_FORMAT_R10G10B10A2_TYPELESS;
        break;
    case ResourceFormat::BGRA8Unorm:
        typed = DXGI_FORMAT_B8G8R8A8_UNORM;
        typeless = DXGI_FORMAT_B8G8R8A8_TYPELESS;
        break;
    case ResourceFormat::BGRA8UnormSrgb:
        typed = DXGI_FORMAT_B8G8R8A8_UNORM_SRGB;
        typeless = DXGI_FORMAT_B8G8R8A8_TYPELESS;
        break;
    case ResourceFormat::D32FloatS8Uint:
        typed = DXGI_FORMAT_D32_FLOAT_S8X24_UINT;
        typeless = DXGI_FORMAT_R32G8X24_TYPELESS;
        break;
    default:
        FALCOR_UNREACHABLE();
    }
    const auto nativeDesc = texture->getNativeHandle().as<ID3D12Resource*>()->GetDesc();
    logInfo(
        "CustomRenderPipline {}: Falcor {}, native DXGI format {} (typed {}, typeless {}), resource kind {}.",
        label,
        to_string(texture->getFormat()),
        uint32_t(nativeDesc.Format),
        uint32_t(typed),
        uint32_t(typeless),
        nativeDesc.Format == typed      ? "typed"
        : nativeDesc.Format == typeless ? "typeless"
                                        : "unexpected"
    );
    EXPECT_TRUE(nativeDesc.Format == typed || nativeDesc.Format == typeless) << label << ": native format family";
    EXPECT_EQ(nativeDesc.Width, uint64_t(kWidth));
    EXPECT_EQ(nativeDesc.Height, kHeight);
    EXPECT_EQ(nativeDesc.SampleDesc.Count, 1u);
#endif
}

void expectDepthStencil(
    GPUUnitTestContext& ctx,
    const ref<FullScreenPass>& predicate,
    const ref<Fbo>& fbo,
    float expectedDepth,
    uint8_t expectedStencil,
    const std::array<bool, 3>& expectedPixels
)
{
    using Face = DepthStencilState::Face;
    using Op = DepthStencilState::StencilOp;
    auto desc = DepthStencilState::Desc()
                    .setDepthEnabled(true)
                    .setDepthFunc(ComparisonFunc::Equal)
                    .setDepthWriteMask(false)
                    .setStencilEnabled(true)
                    .setStencilFunc(Face::FrontAndBack, ComparisonFunc::Equal)
                    .setStencilReadMask(0xFF)
                    .setStencilWriteMask(0)
                    .setStencilRef(expectedStencil)
                    .setStencilOp(Face::FrontAndBack, Op::Keep, Op::Keep, Op::Keep);
    predicate->getState()->setDepthStencilState(DepthStencilState::create(desc));
    predicate->getState()->setStencilRef(expectedStencil);
    setRegionAndDepth(predicate, kWhole, expectedDepth);
    ctx.getRenderContext()->clearRtv(fbo->getRenderTargetView(0).get(), float4(0.f));
    predicate->execute(ctx.getRenderContext(), fbo);
    auto bytes = ctx.getRenderContext()->readTextureSubresource(fbo->getColorTexture(0).get(), 0);
    ASSERT_EQ(bytes.size(), size_t(kWidth * kHeight * 4));
    for (uint32_t i = 0; i < kPixels.size(); ++i)
    {
        const size_t offset = (kPixels[i].y * kWidth + kPixels[i].x) * 4;
        EXPECT_EQ(uint32_t(bytes[offset]), expectedPixels[i] ? 255u : 0u)
            << "predicate pixel " << i << ", depth " << expectedDepth << ", stencil " << uint32_t(expectedStencil);
    }
}
} // namespace

GPU_TEST(CustomRenderPiplineMRTFormatsAndPreservation, Device::Type::D3D12)
{
    requireCapabilities(ctx);
    auto device = ctx.getDevice();
    auto depth = createDepth(device);
    std::vector<ref<Texture>> colors;
    for (uint32_t rt = 0; rt < kFormats.size(); ++rt)
    {
        auto texture = device->createTexture2D(
            kWidth, kHeight, kFormats[rt], 1, 1, nullptr, ResourceBindFlags::RenderTarget | ResourceBindFlags::ShaderResource
        );
        const auto rtvFormat = texture->getRTV()->getGfxResourceView()->getViewDesc()->format;
        const auto srvFormat = texture->getSRV()->getGfxResourceView()->getViewDesc()->format;
        logInfo(
            "CustomRenderPipline MRT{}: gfx RTV format {}, SRV format {}, expected {} ({}).",
            rt,
            uint32_t(rtvFormat),
            uint32_t(srvFormat),
            uint32_t(kExpectedGfxFormats[rt]),
            to_string(kFormats[rt])
        );
        EXPECT_EQ(uint32_t(rtvFormat), uint32_t(kExpectedGfxFormats[rt]));
        EXPECT_EQ(uint32_t(srvFormat), uint32_t(kExpectedGfxFormats[rt]));
        inspectNativeResource(ctx, texture, fmt::format("MRT{}", rt).c_str());
        colors.push_back(texture);
    }
    inspectNativeResource(ctx, depth, "depth/stencil");
    const auto dsvFormat = depth->getDSV()->getGfxResourceView()->getViewDesc()->format;
    logInfo(
        "CustomRenderPipline depth/stencil: gfx DSV format {}, expected {} (D32_FLOAT_S8_UINT).",
        uint32_t(dsvFormat),
        uint32_t(gfx::Format::D32_FLOAT_S8_UINT)
    );
    EXPECT_EQ(uint32_t(dsvFormat), uint32_t(gfx::Format::D32_FLOAT_S8_UINT));
    auto fbo = Fbo::create(device, colors, depth);
    ctx.getRenderContext()->clearFbo(fbo.get(), float4(0.f), 0.f, 0, FboAttachmentType::Color);
    runPrepass(ctx, depth);
    auto base = createBasePass(device);
    drawBase(ctx, base, fbo, kRegionA, 0.75f, kColorsA);
    auto first = readColors(ctx, fbo); // Submit and read back before the second render pass, testing Load preservation.
    expectColorPixel(ctx, first, kPixels[0], &kColorsA);
    expectColorPixel(ctx, first, kPixels[1], nullptr);
    expectColorPixel(ctx, first, kPixels[2], nullptr);
    drawBase(ctx, base, fbo, kRegionB, 0.875f, kColorsB, true);
    auto second = readColors(ctx, fbo);
    expectColorPixel(ctx, second, kPixels[0], &kColorsA);
    expectColorPixel(ctx, second, kPixels[1], &kColorsB);
    expectColorPixel(ctx, second, kPixels[2], nullptr);
    drawBase(ctx, base, fbo, kWhole, 0.5f, kColorsB);
    auto rejected = readColors(ctx, fbo);
    for (uint32_t rt = 0; rt < second.size(); ++rt)
        EXPECT_TRUE(rejected[rt] == second[rt]) << "farther draw must leave every byte of MRT " << rt << " unchanged";

    ctx.createProgram(kShader, "readSrgb", {}, SlangCompilerFlags::None, ShaderModel::SM6_6);
    ctx.allocateStructuredBuffer("result", kWidth * kHeight);
    ctx["gSrgbTexture"] = colors[3];
    ctx["ReadbackCB"]["gDimensions"] = uint2(kWidth, kHeight);
    ctx.runProgram(kWidth, kHeight);
    auto decoded = ctx.readBuffer<float4>("result");
    ASSERT_EQ(decoded.size(), size_t(kWidth * kHeight));
    const uint32_t rgbaToMemory[] = {2, 1, 0, 3};
    for (const auto pixel : kPixels)
    {
        const size_t index = pixel.y * kWidth + pixel.x;
        for (uint32_t channel = 0; channel < 4; ++channel)
        {
            const double encoded = second[3][index * 4 + rgbaToMemory[channel]] / 255.0;
            const double actual = double(decoded[index][channel]);
            if (channel == 3)
                EXPECT_LE(std::abs(actual - encoded), 1e-7) << "SRV alpha must remain linear";
            else if (encoded == 0.0 || encoded == 1.0)
                EXPECT_EQ(actual, encoded) << "SRV sRGB endpoints must be exact";
            else
            {
                // Direct3D functional spec 3.2.3.7: 0.5 ULP on the 8-bit sRGB side, measured by ideal re-encoding.
                // https://microsoft.github.io/DirectX-Specs/d3d/archive/D3D11_3_FunctionalSpec.htm#SRGBtoFLOAT
                const double errorInSrgbCodes = std::abs(encodeSrgb(actual) - encoded) * 255.0;
                EXPECT_LE(errorInSrgbCodes, 0.5) << "SRV sRGB decode channel " << channel;
            }
        }
    }
    logInfo("CustomRenderPipline MRT output checks cover slots 0-3. Slot 4 (GBuffer D) is bound but excluded from output validity.");
}

GPU_TEST(CustomRenderPiplineDepthStencilSemantics, Device::Type::D3D12)
{
    requireCapabilities(ctx);
    auto device = ctx.getDevice();
    auto depth = createDepth(device);
    runPrepass(ctx, depth);
    auto marker = device->createTexture2D(kWidth, kHeight, ResourceFormat::RGBA8Unorm, 1, 1, nullptr, ResourceBindFlags::RenderTarget);
    auto fbo = Fbo::create(device, {marker}, depth);
    auto predicate = createPass(device, "predicate");
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0x09, {true, true, true});
    expectDepthStencil(ctx, predicate, fbo, 0.25f, 0x09, {false, false, false});

    // The depth/stencil-only BasePass entry exercises identical PSO state without writing MRT payloads.
    auto base = createPass(device, "prepass");
    base->getState()->setDepthStencilState(DepthStencilState::create(baseDepthStencilDesc()));
    base->getState()->setStencilRef(0x86);
    auto depthFbo = Fbo::create(device, {}, depth);
    setRegionAndDepth(base, kRegionA, 0.75f);
    base->execute(ctx.getRenderContext(), depthFbo);
    base->getState()->setRasterizerState(
        RasterizerState::create(RasterizerState::Desc().setCullMode(RasterizerState::CullMode::None).setFrontCounterCW(true))
    );
    setRegionAndDepth(base, kRegionB, 0.875f);
    base->execute(ctx.getRenderContext(), depthFbo);
    // (0x09 & ~0xF6) | (0x86 & 0xF6) == 0x8F. Both unmasked sentinel bits must survive.
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0x8F, {true, true, false});
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0x09, {false, false, true});
    expectDepthStencil(ctx, predicate, fbo, 0.875f, 0x8F, {false, false, false}); // Wrong depth negative control.
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0x86, {false, false, false});  // Wrong stencil negative control.

    ctx.getRenderContext()->clearDsv(depth->getDSV().get(), 0.125f, 0, false, true);
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0, {true, true, true});
    expectDepthStencil(ctx, predicate, fbo, 0.125f, 0, {false, false, false});
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0x8F, {false, false, false});

    // Capture-style transition: the same BasePass stencil state replaces zero with exactly 0x86.
    setRegionAndDepth(base, kRegionA, 0.75f);
    base->execute(ctx.getRenderContext(), depthFbo);
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0x86, {true, false, false});
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0, {false, true, true});
    expectDepthStencil(ctx, predicate, fbo, 0.75f, 0x8F, {false, false, false});
    logInfo(
        "CustomRenderPipline depth preservation uses a writable DSV with depth writes disabled in the PSO. "
        "Native depth-read-only/stencil-writable DSV fidelity is an untested API capability gap."
    );
}

GPU_TEST(CustomRenderPiplineNativeDepthStencilReadback, Device::Type::D3D12)
{
#if FALCOR_HAS_D3D12
    const auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    if (!device->getDesc().enableDebugLayer)
        ctx.skip("Native plane readback acceptance requires --enable-debug-layer.");
    context->submit(true);
    Slang::ComPtr<ID3D12InfoQueue> infoQueue;
    FALCOR_D3D_CALL(device->getNativeHandle().as<ID3D12Device*>()->QueryInterface(IID_PPV_ARGS(infoQueue.writeRef())));
    const uint64_t firstMessage = infoQueue->GetNumStoredMessagesAllowedByRetrievalFilter();
    const uint64_t firstDiscarded = infoQueue->GetNumMessagesDiscardedByMessageCountLimit();
    constexpr uint32_t width = 37, height = 19;
    auto wrongFormat = device->createTexture2D(width, height, ResourceFormat::R32Float, 1, 1, nullptr, ResourceBindFlags::ShaderResource);
    auto arrayDepth = device->createTexture2D(width, height, ResourceFormat::D32FloatS8Uint, 2, 1, nullptr, ResourceBindFlags::DepthStencil);
    auto mipDepth = device->createTexture2D(width, height, ResourceFormat::D32FloatS8Uint, 1, 2, nullptr, ResourceBindFlags::DepthStencil);
    EXPECT_THROW(CustomRenderPipline::readDepthStencil(context, nullptr));
    EXPECT_THROW(CustomRenderPipline::readDepthStencil(nullptr, wrongFormat.get()));
    EXPECT_THROW(CustomRenderPipline::readDepthStencil(context, wrongFormat.get()));
    // Mips/layers are supported; only out-of-bounds views must reject.
    EXPECT_THROW(CustomRenderPipline::readDepthStencil(context, arrayDepth.get(), 0, 2));
    EXPECT_THROW(CustomRenderPipline::readDepthStencil(context, mipDepth.get(), 2, 0));
    context->clearDsv(arrayDepth->getDSV(0, 1, 1).get(), 0.5f, 37, true, true);
    context->clearDsv(mipDepth->getDSV(1, 0, 1).get(), 0.75f, 113, true, true);
    const auto arrayPlane = CustomRenderPipline::readDepthStencil(context, arrayDepth.get(), 0, 1);
    const auto mipPlane = CustomRenderPipline::readDepthStencil(context, mipDepth.get(), 1, 0);
    EXPECT_EQ(arrayPlane.planes[1].size(), size_t(width * height));
    EXPECT_EQ(mipPlane.planes[1].size(), size_t((width >> 1) * (height >> 1)));
    for (auto value : arrayPlane.planes[1]) EXPECT_EQ(uint32_t(value), 37u);
    for (auto value : mipPlane.planes[1]) EXPECT_EQ(uint32_t(value), 113u);
    auto depth = device->createTexture2D(width, height, ResourceFormat::D32FloatS8Uint, 1, 1, nullptr, ResourceBindFlags::DepthStencil);
    auto fbo = Fbo::create(device, {}, depth);
    auto pass = createPass(device, "prepass");
    using Face = DepthStencilState::Face;
    using Op = DepthStencilState::StencilOp;
    auto state = DepthStencilState::Desc().setDepthEnabled(true).setDepthFunc(ComparisonFunc::GreaterEqual)
        .setDepthWriteMask(true).setStencilEnabled(true).setStencilFunc(Face::FrontAndBack, ComparisonFunc::Always)
        .setStencilOp(Face::FrontAndBack, Op::Keep, Op::Keep, Op::Replace).setStencilReadMask(255);
    context->clearDsv(depth->getDSV().get(), 0.25f, 0x59, true, true);
    pass->getState()->setDepthStencilState(DepthStencilState::create(state.setStencilWriteMask(0xF6)));
    pass->getState()->setStencilRef(0xA6);
    setRegionAndDepth(pass, float4(1, 2, 18, 17), 0.5f);
    pass->execute(context, fbo);
    pass->getState()->setDepthStencilState(DepthStencilState::create(state.setStencilWriteMask(0x0F)));
    pass->getState()->setStencilRef(0x3C);
    setRegionAndDepth(pass, float4(19, 1, 36, 18), 0.75f);
    pass->execute(context, fbo);
    pass->getState()->setStencilRef(0xE1);
    setRegionAndDepth(pass, float4(0, 0, width, height), 0.125f);
    pass->execute(context, fbo); // Rejected depth must preserve both native planes.

    const auto initial = CustomRenderPipline::readDepthStencil(context, depth.get());
    logInfo("Native depth/stencil footprints: formats {}/{}, row bytes {}/{}.",
        initial.nativeFormats[0], initial.nativeFormats[1], initial.rowBytes[0], initial.rowBytes[1]);
    ASSERT_EQ(initial.rowBytes[0], uint64_t(width * 4));
    ASSERT_EQ(initial.rowBytes[1], uint64_t(width));
    EXPECT_EQ(initial.nativeFormats[0], uint32_t(DXGI_FORMAT_R32_TYPELESS));
    EXPECT_EQ(initial.nativeFormats[1], uint32_t(DXGI_FORMAT_R8_TYPELESS));
    ASSERT_EQ(initial.planes[0].size(), size_t(width * height * 4));
    ASSERT_EQ(initial.planes[1].size(), size_t(width * height));
    for (uint32_t y = 0; y < height; ++y)
        for (uint32_t x = 0; x < width; ++x)
        {
            const bool a = x >= 1 && x < 18 && y >= 2 && y < 17;
            const bool b = x >= 19 && x < 36 && y >= 1 && y < 18;
            float actualDepth;
            std::memcpy(&actualDepth, initial.planes[0].data() + (y * width + x) * 4, 4);
            EXPECT_EQ(actualDepth, a ? 0.5f : b ? 0.75f : 0.25f) << "native depth at " << x << "," << y;
            EXPECT_EQ(uint32_t(initial.planes[1][y * width + x]), a ? 0xAFu : b ? 0x5Cu : 0x59u) << "native stencil at " << x << "," << y;
        }
    const auto repeated = CustomRenderPipline::readDepthStencil(context, depth.get());
    EXPECT_TRUE(initial.planes == repeated.planes) << "CopySource to CopySource consecutive read must still submit";
    context->clearDsv(depth->getDSV().get(), 0, 0xD2, false, true);
    const auto cleared = CustomRenderPipline::readDepthStencil(context, depth.get());
    EXPECT_TRUE(initial.planes[0] == cleared.planes[0]) << "stencil-only clear changed depth";
    for (auto value : cleared.planes[1]) EXPECT_EQ(uint32_t(value), 0xD2u);
    pass->getState()->setDepthStencilState(DepthStencilState::create(state.setStencilWriteMask(255)));
    pass->getState()->setStencilRef(0x17);
    setRegionAndDepth(pass, float4(0, 0, width, height), 1.f);
    pass->execute(context, fbo);
    const auto rewritten = CustomRenderPipline::readDepthStencil(context, depth.get());
    for (size_t pixel = 0; pixel < width * height; ++pixel)
    {
        float actualDepth;
        std::memcpy(&actualDepth, rewritten.planes[0].data() + pixel * 4, 4);
        EXPECT_EQ(actualDepth, 1.f);
        EXPECT_EQ(uint32_t(rewritten.planes[1][pixel]), 0x17u);
    }
    context->submit(true);
    EXPECT_EQ(infoQueue->GetNumMessagesDiscardedByMessageCountLimit(), firstDiscarded);
    const uint64_t messageCount = infoQueue->GetNumStoredMessagesAllowedByRetrievalFilter();
    EXPECT_GE(messageCount, firstMessage);
    for (uint64_t index = firstMessage; index < messageCount; ++index)
    {
        SIZE_T size = 0;
        FALCOR_D3D_CALL(infoQueue->GetMessage(index, nullptr, &size));
        std::vector<uint8_t> storage(size);
        auto message = reinterpret_cast<D3D12_MESSAGE*>(storage.data());
        FALCOR_D3D_CALL(infoQueue->GetMessage(index, message, &size));
        EXPECT_TRUE(message->Severity > D3D12_MESSAGE_SEVERITY_ERROR)
            << "D3D12 message " << uint32_t(message->ID) << ": " << message->pDescription;
    }
#endif
}

GPU_TEST(CustomRenderPiplineSharedIABufferReadStates, Device::Type::D3D12)
{
#if FALCOR_HAS_D3D12
    auto device = ctx.getDevice();
    auto renderContext = ctx.getRenderContext();
    if (!device->getDesc().enableDebugLayer)
        ctx.skip("This acceptance test requires --enable-debug-layer to inspect D3D12 resource-state errors.");
    if (!device->isShaderModelSupported(ShaderModel::SM6_6))
        ctx.skip("CAPABILITY GAP: shader model 6.6 is unavailable.");

    renderContext->submit(true);
    Slang::ComPtr<ID3D12InfoQueue> infoQueue;
    FALCOR_D3D_CALL(device->getNativeHandle().as<ID3D12Device*>()->QueryInterface(IID_PPV_ARGS(infoQueue.writeRef())));
    const uint64_t firstMessage = infoQueue->GetNumStoredMessagesAllowedByRetrievalFilter();
    const uint64_t firstDiscarded = infoQueue->GetNumMessagesDiscardedByMessageCountLimit();

    struct Vertex
    {
        float x, y;
        uint32_t value;
    };
    static_assert(sizeof(Vertex) == 12);
    auto bufferLayout = VertexBufferLayout::create();
    bufferLayout->addElement("POSITION", 0, ResourceFormat::RG32Float, 1, 0);
    bufferLayout->addElement("TEXCOORD", 8, ResourceFormat::R32Uint, 1, 1);
    auto layout = VertexLayout::create();
    layout->addBufferLayout(0, bufferLayout);
    auto target = device->createTexture2D(
        kWidth, kHeight, ResourceFormat::RGBA32Uint, 1, 1, nullptr, ResourceBindFlags::RenderTarget
    );
    auto fbo = Fbo::create(device, {target});
    const auto shaderFlags = ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess;
    ctx.createProgram(kShader, "writeReadUnionBuffers", {}, SlangCompilerFlags::None, ShaderModel::SM6_6);

    // The IA-only variant proves resource checks also run when no SRV requests the transition after a write.
    for (const bool sharedReads : {true, false})
    {
        ProgramDesc desc;
        desc.addShaderLibrary(kShader).vsEntry("readUnionVS").psEntry("readUnionPS").setShaderModel(ShaderModel::SM6_6);
        auto program = Program::create(device, desc, {{"READ_UNION_WITH_SRV", sharedReads ? "1" : "0"}});
        auto vars = ProgramVars::create(device, program.get());
        auto state = GraphicsState::create(device);
        state->setProgram(program).setFbo(fbo);
        state->setRasterizerState(RasterizerState::create(RasterizerState::Desc().setCullMode(RasterizerState::CullMode::None)));
        state->setDepthStencilState(DepthStencilState::create(DepthStencilState::Desc().setDepthEnabled(false)));

        for (const bool index16 : {false, true})
        {
            std::array<Vertex, 3> vertices = {{{-1.f, -1.f, 17}, {-1.f, 3.f, 17}, {3.f, -1.f, 17}}};
            const std::array<uint32_t, 3> indices32 = {0, 1, 2};
            const std::array<uint16_t, 4> indices16 = {0, 1, 2, 0}; // Pad raw SRV/UAV access to four bytes.
            const void* indexData = index16 ? static_cast<const void*>(indices16.data()) : indices32.data();
            const size_t indexBytes = index16 ? sizeof(indices16) : sizeof(indices32);
            auto vertexBuffer = device->createBuffer(
                sizeof(vertices), shaderFlags | ResourceBindFlags::Vertex, MemoryType::DeviceLocal, vertices.data()
            );
            auto indexBuffer = device->createBuffer(
                indexBytes, shaderFlags | ResourceBindFlags::Index, MemoryType::DeviceLocal, indexData
            );
            state->setVao(Vao::create(
                Vao::Topology::TriangleList, layout, {vertexBuffer}, indexBuffer,
                index16 ? ResourceFormat::R16Uint : ResourceFormat::R32Uint
            ));
            auto root = vars->getRootVar();
            if (sharedReads)
            {
                root["gReadUnionVertices"] = vertexBuffer;
                root["gReadUnionIndices"] = indexBuffer;
            }
            root["ReadUnionCB"]["gReadUnionIndex16"] = uint32_t(index16);
            ctx["gWriteUnionVertices"] = vertexBuffer;
            ctx["gWriteUnionIndices"] = indexBuffer;
            ctx["ReadUnionCB"]["gReadUnionIndex16"] = uint32_t(index16);

            const auto gso = state->getGSO(vars.get());
            auto drawAndCheck = [&](uint32_t expectedValue, bool rotated, const char* phase)
            {
                root["ReadUnionCB"]["gReadUnionRotated"] = uint32_t(rotated);
                renderContext->clearRtv(target->getRTV().get(), float4(0.f));
                for (uint32_t draw = 1; draw <= 2; ++draw)
                {
                    root["ReadUnionCB"]["gReadUnionDrawId"] = draw;
                    EXPECT_TRUE(state->getGSO(vars.get()) == gso) << "The test must reuse the GSO";
                    renderContext->drawIndexed(state.get(), vars.get(), 3, 0, 0);
                }
                // This submits between phases; the next draw must restore both IA and shader reads.
                auto bytes = renderContext->readTextureSubresource(target.get(), 0);
                ASSERT_EQ(bytes.size(), size_t(kWidth * kHeight * sizeof(uint4)));
                uint4 pixel;
                std::memcpy(&pixel, bytes.data() + ((kHeight / 2) * kWidth + kWidth / 2) * sizeof(pixel), sizeof(pixel));
                EXPECT_EQ(pixel.x, expectedValue) << phase << ", SRV " << sharedReads << ", index16 " << index16;
                EXPECT_EQ(pixel.y, 1u) << phase << ": index SRV contents and vertex IA/SRV agreement";
                EXPECT_EQ(pixel.z, 2u) << phase << ": the repeated draw must execute";
                EXPECT_EQ(pixel.w, 1u) << phase << ": indexed geometry must cover the sample";
            };

            drawAndCheck(17, false, "initial upload");
            ctx["ReadUnionCB"]["gReadUnionValue"] = 29u;
            ctx["ReadUnionCB"]["gReadUnionRotated"] = 1u;
            ctx.runProgram(1); // Actually write both shared buffers as UAVs between uses of the same GSO.
            drawAndCheck(29, true, "UAV write");

            // Also exercise the full read -> write -> read sequence inside one command list.
            renderContext->drawIndexed(state.get(), vars.get(), 3, 0, 0);
            ctx["ReadUnionCB"]["gReadUnionValue"] = 37u;
            ctx.runProgram(1);
            drawAndCheck(37, true, "same-command-list UAV write");
            renderContext->submit(true);
            drawAndCheck(37, true, "submit boundary");

            for (auto& vertex : vertices)
                vertex.value = 41;
            renderContext->updateBuffer(vertexBuffer.get(), vertices.data(), 0, sizeof(vertices));
            renderContext->updateBuffer(indexBuffer.get(), indexData, 0, indexBytes);
            drawAndCheck(41, false, "CopyDest write");
        }
    }

    renderContext->submit(true);
    device->wait();
    EXPECT_EQ(infoQueue->GetNumMessagesDiscardedByMessageCountLimit(), firstDiscarded) << "D3D12 diagnostic storage overflow";
    const uint64_t messageCount = infoQueue->GetNumStoredMessagesAllowedByRetrievalFilter();
    EXPECT_GE(messageCount, firstMessage) << "D3D12 diagnostic storage was unexpectedly cleared";
    for (uint64_t index = firstMessage; index < messageCount; ++index)
    {
        SIZE_T size = 0;
        FALCOR_D3D_CALL(infoQueue->GetMessage(index, nullptr, &size));
        std::vector<uint8_t> storage(size);
        auto message = reinterpret_cast<D3D12_MESSAGE*>(storage.data());
        FALCOR_D3D_CALL(infoQueue->GetMessage(index, message, &size));
        EXPECT_TRUE(message->Severity > D3D12_MESSAGE_SEVERITY_ERROR)
            << "D3D12 message " << uint32_t(message->ID) << ": " << message->pDescription;
    }
#endif
}
} // namespace Falcor
