// Native cube face/mip contracts required by the UE SkyLight compute passes.
#include "Testing/UnitTest.h"
#include "Core/API/FBO.h"
#include "Core/API/GFXAPI.h"
#include "Core/API/NativeHandleTraits.h"

#if FALCOR_HAS_D3D12
#include <d3d12sdklayers.h>
#endif

#include <vector>

namespace Falcor
{
namespace
{
const char kShader[] = "Tests/Core/CustomRenderPiplineCubeSubresources.slang";
constexpr uint32_t kWidth = 8;
constexpr uint32_t kMips = 3;
constexpr uint32_t kFaces = 6;
const auto kFlags = ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess;

ref<Texture> createTexture(GPUUnitTestContext& ctx, bool cube)
{
    return cube ? ctx.getDevice()->createTextureCube(kWidth, kWidth, ResourceFormat::R32Float, 1, kMips, nullptr, kFlags)
                : ctx.getDevice()->createTexture2D(kWidth, kWidth, ResourceFormat::R32Float, kFaces, kMips, nullptr, kFlags);
}

float initialValue(uint32_t face, uint32_t mip)
{
    return float(100 * face + 10 * mip + 1);
}

void initializeSubresources(GPUUnitTestContext& ctx, const ref<Texture>& texture)
{
    // Assert before addressing face 5: the broken tracker allocates only one face.
    ASSERT_EQ(texture->getSubresourceCount(), kFaces * kMips);
    for (uint32_t face = 0; face < kFaces; ++face)
    {
        for (uint32_t mip = 0; mip < kMips; ++mip)
        {
            const uint32_t subresource = face * kMips + mip;
            EXPECT_EQ(texture->getSubresourceIndex(face, mip), subresource);
            EXPECT_EQ(texture->getSubresourceArraySlice(subresource), face);
            EXPECT_EQ(texture->getSubresourceMipLevel(subresource), mip);
            const uint32_t width = kWidth >> mip;
            std::vector<float> pixels(width * width, initialValue(face, mip));
            texture->setSubresourceBlob(subresource, pixels.data(), pixels.size() * sizeof(float));
        }
    }
}

void expectSubresource(GPUUnitTestContext& ctx, const ref<Texture>& texture, uint32_t face, uint32_t mip, float expected)
{
    const uint32_t width = kWidth >> mip;
    std::vector<float> pixels(width * width);
    texture->getSubresourceBlob(face * kMips + mip, pixels.data(), pixels.size() * sizeof(float));
    for (size_t i = 0; i < pixels.size(); ++i)
        EXPECT_EQ(pixels[i], expected) << "face " << face << ", mip " << mip << ", pixel " << i;
}

void testFaceViewAndTracker(GPUUnitTestContext& ctx, bool cube)
{
    const auto texture = createTexture(ctx, cube);
    initializeSubresources(ctx, texture);
    const auto srv = texture->getSRV();
    EXPECT_EQ(srv->getViewInfo().arraySize, kFaces);
    EXPECT_EQ(srv->getGfxResourceView()->getViewDesc()->subresourceRange.layerCount, kFaces);
    EXPECT_EQ(srv->getViewInfo().mipCount, kMips);

    const auto uav = texture->getUAV(1, 5, 1);
    ASSERT_EQ(uav->getViewInfo().firstArraySlice, 5u) << "face 5 must not be clamped to face 0";
    EXPECT_EQ(uav->getViewInfo().arraySize, 1u);
    EXPECT_EQ(uav->getGfxResourceView()->getViewDesc()->subresourceRange.baseArrayLayer, 5u);
    EXPECT_EQ(uav->getGfxResourceView()->getViewDesc()->subresourceRange.layerCount, 1u);
    EXPECT_EQ(uav->getGfxResourceView()->getViewDesc()->subresourceRange.mipLevel, 1u);
    EXPECT_TRUE(uav != texture->getUAV(1, 0, 1)) << "distinct face views must not share a cache entry";

    auto context = ctx.getRenderContext();
    context->resourceBarrier(texture.get(), Resource::State::ShaderResource);
    context->resourceBarrier(texture.get(), Resource::State::UnorderedAccess, &uav->getViewInfo());
    EXPECT_FALSE(texture->isStateGlobal());
    for (uint32_t face = 0; face < kFaces; ++face)
    {
        for (uint32_t mip = 0; mip < kMips; ++mip)
        {
            const auto expected = face == 5 && mip == 1 ? Resource::State::UnorderedAccess : Resource::State::ShaderResource;
            EXPECT_EQ(uint32_t(texture->getSubresourceState(face, mip)), uint32_t(expected)) << "face " << face << ", mip " << mip;
        }
    }
    // A full transition after mixed states must include all six faces.
    context->resourceBarrier(texture.get(), Resource::State::CopySource);
    EXPECT_TRUE(texture->isStateGlobal());
    for (uint32_t face = 0; face < kFaces; ++face)
        for (uint32_t mip = 0; mip < kMips; ++mip)
            EXPECT_EQ(uint32_t(texture->getSubresourceState(face, mip)), uint32_t(Resource::State::CopySource));

    ctx.createProgram(kShader, "writeFace");
    ctx["gWrite"].setUav(uav);
    ctx.runProgram(kWidth >> 1, kWidth >> 1);
    for (uint32_t face = 0; face < kFaces; ++face)
    {
        for (uint32_t mip = 0; mip < kMips; ++mip)
            expectSubresource(ctx, texture, face, mip, face == 5 && mip == 1 ? 777.f : initialValue(face, mip));
    }
}
} // namespace

GPU_TEST(CustomRenderPiplineCubeNativeAllocation, Device::Type::D3D12)
{
#if FALCOR_HAS_D3D12
    for (uint32_t cubes : {1u, 2u})
    {
        const auto texture = ctx.getDevice()->createTextureCube(kWidth, kWidth, ResourceFormat::R32Float, cubes, kMips, nullptr, kFlags);
        const auto native = texture->getNativeHandle().as<ID3D12Resource*>()->GetDesc();
        EXPECT_EQ(uint32_t(native.Dimension), uint32_t(D3D12_RESOURCE_DIMENSION_TEXTURE2D));
        EXPECT_EQ(uint32_t(native.DepthOrArraySize), cubes * kFaces) << "one cube has exactly six native face layers";
        EXPECT_EQ(uint32_t(native.MipLevels), kMips);
        EXPECT_EQ(texture->getGfxTextureResource()->getDesc()->arraySize, cubes) << "GFX allocation counts cubes, not faces";
        EXPECT_EQ(texture->getArraySize(), cubes);
        EXPECT_EQ(texture->getArrayLayerCount(), cubes * kFaces);
        EXPECT_EQ(texture->getSubresourceCount(), cubes * kFaces * kMips);
        EXPECT_EQ(texture->getTexelCount(), uint64_t(cubes * kFaces * (64 + 16 + 4)));
    }
#endif
}

GPU_TEST(CustomRenderPiplineCubeInvalidSrvRanges, Device::Type::D3D12)
{
    const auto texture = createTexture(ctx, true);
    EXPECT_THROW(texture->getSRV(0, 1, 0, 1));
    EXPECT_THROW(texture->getSRV(0, 1, 1, 5));
    EXPECT_THROW(texture->getSRV(0, 1, 6, kFaces));
    EXPECT_THROW(texture->getSRV(0, 1, 0, 0));
    EXPECT_THROW(texture->getSRV(0, 1, 0, 12));
    EXPECT_THROW(ShaderResourceView::create(ctx.getDevice().get(), texture.get(), 0, 1, 0, 1));
    EXPECT_THROW(texture->generateMips(ctx.getRenderContext()));
    for (uint32_t width : {1u, kWidth})
    {
        std::vector<float> baseData(kFaces * width * width, 1.f);
        EXPECT_THROW(ctx.getDevice()->createTextureCube(
            width, width, ResourceFormat::R32Float, 1, Texture::kMaxPossible, baseData.data(), kFlags
        ));
        const auto singleMip = ctx.getDevice()->createTextureCube(width, width, ResourceFormat::R32Float, 1, 1, nullptr, kFlags);
        EXPECT_THROW(singleMip->generateMips(ctx.getRenderContext()));
    }
}

GPU_TEST(CustomRenderPiplineCubeInitialDataAndWrappedTexture, Device::Type::D3D12)
{
    std::vector<float> initialData;
    for (uint32_t face = 0; face < kFaces; ++face)
        for (uint32_t mip = 0; mip < kMips; ++mip)
            initialData.insert(initialData.end(), (kWidth >> mip) * (kWidth >> mip), initialValue(face, mip));
    const auto texture = ctx.getDevice()->createTextureCube(
        kWidth, kWidth, ResourceFormat::R32Float, 1, kMips, initialData.data(), kFlags
    );
    ASSERT_EQ(texture->getSubresourceCount(), kFaces * kMips);
    for (uint32_t face = 0; face < kFaces; ++face)
        for (uint32_t mip = 0; mip < kMips; ++mip)
            expectSubresource(ctx, texture, face, mip, initialValue(face, mip));

    // Wrapping delegates to the same constructor and must allocate a state entry for every face/mip.
    // Use only the wrapper after this point; independently used wrappers cannot share state tracking.
    const auto wrapped = ctx.getDevice()->createTextureFromResource(
        texture->getGfxTextureResource(), Texture::Type::TextureCube, ResourceFormat::R32Float,
        kWidth, kWidth, 1, 1, kMips, 1, kFlags, Resource::State::CopySource
    );
    EXPECT_EQ(wrapped->getArraySize(), 1u);
    EXPECT_EQ(wrapped->getArrayLayerCount(), kFaces);
    ASSERT_EQ(wrapped->getSubresourceCount(), kFaces * kMips);
    const auto srv = wrapped->getSRV(2, 1);
    ctx.getRenderContext()->resourceBarrier(wrapped.get(), Resource::State::ShaderResource, &srv->getViewInfo());
    EXPECT_EQ(uint32_t(wrapped->getSubresourceState(5, 2)), uint32_t(Resource::State::ShaderResource));
    EXPECT_EQ(uint32_t(wrapped->getSubresourceState(5, 1)), uint32_t(Resource::State::CopySource));
}

GPU_TEST(CustomRenderPiplineCubeFaceFramebufferClear, Device::Type::D3D12)
{
    const auto texture = ctx.getDevice()->createTextureCube(
        kWidth, kWidth, ResourceFormat::R32Float, 1, kMips, nullptr, kFlags | ResourceBindFlags::RenderTarget
    );
    initializeSubresources(ctx, texture);
    const auto fbo = Fbo::create(ctx.getDevice());
    fbo->attachColorTarget(texture, 0, 1, 5, 1);
    const auto rtv = fbo->getRenderTargetView(0);
    ASSERT_EQ(rtv->getViewInfo().firstArraySlice, 5u);
    ASSERT_EQ(rtv->getGfxResourceView()->getViewDesc()->subresourceRange.layerCount, 1u);
    ctx.getRenderContext()->clearRtv(rtv.get(), float4(888.f));
    for (uint32_t face = 0; face < kFaces; ++face)
        for (uint32_t mip = 0; mip < kMips; ++mip)
            expectSubresource(ctx, texture, face, mip, face == 5 && mip == 1 ? 888.f : initialValue(face, mip));
}

GPU_TEST(CustomRenderPiplineCubeFaceViewsAndTracker, Device::Type::D3D12)
{
    testFaceViewAndTracker(ctx, true);
}

GPU_TEST(CustomRenderPiplineCubeTexture2DArrayControl, Device::Type::D3D12)
{
    testFaceViewAndTracker(ctx, false);
}

GPU_TEST(CustomRenderPiplineCubeSampleMipView, Device::Type::D3D12)
{
    const auto texture = createTexture(ctx, true);
    initializeSubresources(ctx, texture);
    ctx.createProgram(kShader, "sampleFaces");
    ctx.allocateStructuredBuffer("gResult", kFaces);
    ctx["gPoint"] = ctx.getDevice()->createSampler(Sampler::Desc().setFilterMode(
        TextureFilteringMode::Point, TextureFilteringMode::Point, TextureFilteringMode::Point
    ));
    // Both a full cube SRV and a rebased one-mip SRV must sample all six directions.
    for (uint32_t firstMip : {0u, 2u})
    {
        const auto srv = firstMip == 0 ? texture->getSRV() : texture->getSRV(firstMip, 1, 0, kFaces);
        ASSERT_EQ(srv->getViewInfo().arraySize, kFaces);
        EXPECT_EQ(srv->getGfxResourceView()->getViewDesc()->subresourceRange.mipLevel, firstMip);
        ctx["gCube"].setSrv(srv);
        ctx.runProgram(kFaces);
        const auto values = ctx.readBuffer<float>("gResult");
        ASSERT_EQ(values.size(), size_t(kFaces));
        for (uint32_t face = 0; face < kFaces; ++face)
            EXPECT_EQ(values[face], initialValue(face, firstMip)) << "face " << face << ", view mip " << firstMip;
    }
}

namespace
{
void testNonOverlappingMipBindings(GPUUnitTestContext& ctx, bool cube)
{
#if FALCOR_HAS_D3D12
    const auto device = ctx.getDevice();
    if (!device->getDesc().enableDebugLayer)
        ctx.skip("Texture mip alias acceptance requires --enable-debug-layer.");
    auto context = ctx.getRenderContext();
    context->submit(true);
    Slang::ComPtr<ID3D12InfoQueue> infoQueue;
    FALCOR_D3D_CALL(device->getNativeHandle().as<ID3D12Device*>()->QueryInterface(IID_PPV_ARGS(infoQueue.writeRef())));
    const uint64_t firstMessage = infoQueue->GetNumStoredMessagesAllowedByRetrievalFilter();
    const uint64_t firstDiscarded = infoQueue->GetNumMessagesDiscardedByMessageCountLimit();

    const auto texture = createTexture(ctx, cube);
    initializeSubresources(ctx, texture);
    ctx.createProgram(kShader, cube ? "copyMip" : "copyArrayMip");
    ctx[cube ? "gCube" : "gArrayRead"].setSrv(texture->getSRV(0, 1, 0, kFaces));
    ctx["gWrite"].setUav(texture->getUAV(1, 0, kFaces));
    if (cube)
    {
        ctx["gPoint"] = device->createSampler(Sampler::Desc().setFilterMode(
            TextureFilteringMode::Point, TextureFilteringMode::Point, TextureFilteringMode::Point
        ));
    }
    ctx.getVars()->prepareDescriptorSets(context);
    // Check before dispatch to expose whole-resource barriers without issuing an invalid GPU access.
    for (uint32_t face = 0; face < kFaces; ++face)
    {
        ASSERT_EQ(uint32_t(texture->getSubresourceState(face, 0)), uint32_t(Resource::State::ShaderResource)) << "SRV face " << face;
        ASSERT_EQ(uint32_t(texture->getSubresourceState(face, 1)), uint32_t(Resource::State::UnorderedAccess)) << "UAV face " << face;
        ASSERT_EQ(uint32_t(texture->getSubresourceState(face, 2)), uint32_t(Resource::State::CopyDest)) << "untouched mip, face " << face;
    }
    ctx.runProgram(kWidth >> 1, kWidth >> 1, kFaces);
    // Repeat without a submit to exercise the UAV ordering path with mixed subresource states.
    ctx.runProgram(kWidth >> 1, kWidth >> 1, kFaces);
    for (uint32_t face = 0; face < kFaces; ++face)
    {
        expectSubresource(ctx, texture, face, 0, initialValue(face, 0));
        expectSubresource(ctx, texture, face, 1, initialValue(face, 0) + 1000.f);
        expectSubresource(ctx, texture, face, 2, initialValue(face, 2));
    }
    context->submit(true);
    device->wait();
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
} // namespace

GPU_TEST(CustomRenderPiplineCubeNonOverlappingMipBindings, Device::Type::D3D12)
{
    testNonOverlappingMipBindings(ctx, true);
}

GPU_TEST(CustomRenderPiplineCubeTexture2DArrayMipBindings, Device::Type::D3D12)
{
    testNonOverlappingMipBindings(ctx, false);
}

GPU_TEST(CustomRenderPiplineDepthStencilMipTransitions, Device::Type::D3D12)
{
#if FALCOR_HAS_D3D12
    const auto device=ctx.getDevice();
    if (!device->getDesc().enableDebugLayer)ctx.skip("Requires D3D12 validation");
    auto context=ctx.getRenderContext();context->submit(true);
    Slang::ComPtr<ID3D12InfoQueue> queue;
    FALCOR_D3D_CALL(device->getNativeHandle().as<ID3D12Device*>()->QueryInterface(IID_PPV_ARGS(queue.writeRef())));
    const auto start=queue->GetNumStoredMessagesAllowedByRetrievalFilter();
    const auto depth=device->createTexture2D(16,16,ResourceFormat::D32FloatS8Uint,2,3,nullptr,
        ResourceBindFlags::DepthStencil | ResourceBindFlags::ShaderResource);
    context->resourceBarrier(depth.get(),Resource::State::CopySource);
    const auto view=depth->getDSV(1,1,1);
    context->resourceBarrier(depth.get(),Resource::State::DepthStencil,&view->getViewInfo());
    context->clearDsv(view.get(),.75f,23,true,true);
    context->resourceBarrier(depth.get(),Resource::State::CopySource);
    context->submit(true);device->wait();
    for (uint64_t i=start;i<queue->GetNumStoredMessagesAllowedByRetrievalFilter();++i)
    {
        SIZE_T bytes=0;FALCOR_D3D_CALL(queue->GetMessage(i,nullptr,&bytes));
        std::vector<uint8_t> storage(bytes);auto message=reinterpret_cast<D3D12_MESSAGE*>(storage.data());
        FALCOR_D3D_CALL(queue->GetMessage(i,message,&bytes));
        EXPECT_TRUE(message->Severity>D3D12_MESSAGE_SEVERITY_ERROR) << message->pDescription;
    }
#endif
}
} // namespace Falcor
