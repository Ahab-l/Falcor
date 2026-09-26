#include "Testing/UnitTest.h"
#include "NativeGpuWorkload.h"
#include <array>
#include <chrono>

namespace Falcor
{
GPU_TEST(NativeAsyncReadbackPendingDoesNotWait)
{
    auto context = ctx.getRenderContext();
    auto device = ctx.getDevice();
    const std::array<uint32_t, 8> words = {0, 1, 0xffffffff, 0x80000000, 3, 7, 13, 17};
    auto buffer = device->createBuffer(sizeof(words), ResourceBindFlags::ShaderResource, MemoryType::DeviceLocal, words.data());
    auto texture = device->createTexture2D(2, 1, ResourceFormat::RGBA32Uint, 1, 1, words.data());
    CopyContext::ReadBufferTask::SharedPtr b;
    CopyContext::ReadTextureTask::SharedPtr t;
    // The cleanup guard precedes task destruction. A real bounded workload
    // replaces the invalid future-host-signal timeline/binary queue gate.
    testing::NativeGpuWorkload workload(context);
    workload.enqueue();
    b = context->asyncReadBuffer(buffer.get(), 4, 16);
    t = context->asyncReadTextureSubresource(texture.get(), 0);
    const auto start = std::chrono::steady_clock::now();
    const bool markerBefore = workload.markerPending();
    const bool bufferPending = !b->isReady();
    const bool texturePending = !t->isReady();
    bool bufferRejected = false, textureRejected = false;
    try { b->getDataNonBlocking(); } catch (const std::exception&) { bufferRejected = true; }
    try { t->getDataNonBlocking(); } catch (const std::exception&) { textureRejected = true; }
    const auto pollDuration = std::chrono::steady_clock::now() - start;
    const bool markerAfter = workload.markerPending();
    workload.finish();
    logInfo("NATIVE_ASYNC_PENDING iterations={}, marker_before={}, marker_after={}, buffer_pending={}, texture_pending={}, poll_us={}",
        workload.iterations(), markerBefore, markerAfter, bufferPending, texturePending,
        std::chrono::duration_cast<std::chrono::microseconds>(pollDuration).count());
    EXPECT_TRUE(markerBefore && markerAfter) << "The prerequisite must remain pending during observation; no automatic retry";
    EXPECT_TRUE(bufferPending && texturePending);
    EXPECT_TRUE(bufferRejected && textureRejected);
    EXPECT_TRUE(pollDuration < std::chrono::seconds(1));
    buffer = nullptr;
    texture = nullptr;
    ASSERT_TRUE(b->isReady() && t->isReady());
    const auto bytes = reinterpret_cast<const uint8_t*>(words.data());
    EXPECT_TRUE(b->getDataNonBlocking() == std::vector<uint8_t>(bytes + 4, bytes + 20));
    EXPECT_TRUE(t->getDataNonBlocking() == std::vector<uint8_t>(bytes, bytes + sizeof(words)));
}

GPU_TEST(NativeAsyncReadbackRejectsBeforeAllocation)
{
    auto context = ctx.getRenderContext();
    auto buffer = ctx.getDevice()->createBuffer(16);
    auto texture = ctx.getDevice()->createTexture2D(3, 2, ResourceFormat::RGBA32Uint, 1, 1);
    EXPECT_THROW(context->asyncReadBuffer(nullptr));
    EXPECT_THROW(context->asyncReadBuffer(buffer.get(), 16));
    EXPECT_THROW(context->asyncReadBuffer(buffer.get(), 12, 8));
    EXPECT_THROW(context->asyncReadBuffer(buffer.get(), 0, 16, 15));
    EXPECT_THROW(context->asyncReadTextureSubresource(nullptr, 0));
    EXPECT_THROW(context->asyncReadTextureSubresource(texture.get(), 1));
    EXPECT_THROW(context->asyncReadTextureSubresource(texture.get(), 0, 1));
}
}
