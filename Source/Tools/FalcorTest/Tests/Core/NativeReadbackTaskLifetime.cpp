#include "Testing/UnitTest.h"
#include "NativeGpuWorkload.h"
#include <array>
#include <chrono>
#include <cstring>
#include <vector>

namespace Falcor
{
namespace
{
const std::array<uint32_t, 8> kWords = {0x10203040u, 0u, 0xffffffffu, 0x80000000u, 3u, 7u, 13u, 0xa5a55a5au};
constexpr auto kNonblockingLimit = std::chrono::milliseconds(500);

std::vector<uint8_t> knownBytes()
{
    std::vector<uint8_t> bytes(sizeof(kWords));
    std::memcpy(bytes.data(), kWords.data(), bytes.size());
    return bytes;
}

void expectRecovery(GPUUnitTestContext& ctx)
{
    auto context = ctx.getRenderContext();
    const auto expected = knownBytes();
    const auto buffer = ctx.getDevice()->createBuffer(expected.size(), ResourceBindFlags::ShaderResource,
        MemoryType::DeviceLocal, expected.data());
    const auto texture = ctx.getDevice()->createTexture2D(2, 1, ResourceFormat::RGBA32Uint, 1, 1, expected.data());
    const auto bufferTask = context->asyncReadBuffer(buffer.get());
    const auto textureTask = context->asyncReadTextureSubresource(texture.get(), 0);
    context->submit(true);
    ASSERT_TRUE(bufferTask->isReady());
    ASSERT_TRUE(textureTask->isReady());
    EXPECT_TRUE(bufferTask->getDataNonBlocking() == expected);
    EXPECT_TRUE(textureTask->getDataNonBlocking() == expected);
}
} // namespace

// Run this alone FIRST. Both real task fences are retained through completion.
// Every pending assertion is mandatory: fast completion is not a PASS/retry.
GPU_TEST(NativeReadbackWorkloadPilot)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    const auto sourceBuffer = device->createBuffer(sizeof(kWords), ResourceBindFlags::ShaderResource,
        MemoryType::DeviceLocal, kWords.data());
    const auto sourceTexture = device->createTexture2D(2, 1, ResourceFormat::RGBA32Uint, 1, 1, kWords.data());
    CopyContext::ReadBufferTask::SharedPtr bufferTask;
    CopyContext::ReadTextureTask::SharedPtr textureTask;
    testing::NativeGpuWorkload workload(context);
    workload.enqueue();
    bufferTask = context->asyncReadBuffer(sourceBuffer.get());
    textureTask = context->asyncReadTextureSubresource(sourceTexture.get(), 0);
    const auto start = std::chrono::steady_clock::now();
    const bool markerBefore = workload.markerPending();
    const bool bufferPending = !bufferTask->isReady();
    const bool texturePending = !textureTask->isReady();
    const auto readyEnd = std::chrono::steady_clock::now();
    bool bufferRejected = false, textureRejected = false;
    try { bufferTask->getDataNonBlocking(); } catch (const std::exception&) { bufferRejected = true; }
    const auto bufferEnd = std::chrono::steady_clock::now();
    const bool markerAfterBuffer = workload.markerPending();
    try { textureTask->getDataNonBlocking(); } catch (const std::exception&) { textureRejected = true; }
    const auto textureEnd = std::chrono::steady_clock::now();
    const bool markerAfter = workload.markerPending();
    const auto pollTime = std::chrono::steady_clock::now() - start;
    workload.finish();
    logInfo("NATIVE_WORKLOAD_POLL_PHASES ready_us={}, buffer_us={}, texture_us={}, marker_after_buffer={}",
        std::chrono::duration_cast<std::chrono::microseconds>(readyEnd - start).count(),
        std::chrono::duration_cast<std::chrono::microseconds>(bufferEnd - readyEnd).count(),
        std::chrono::duration_cast<std::chrono::microseconds>(textureEnd - bufferEnd).count(), markerAfterBuffer);
    logInfo("NATIVE_WORKLOAD_PILOT iterations={}, marker_before={}, marker_after={}, buffer_pending={}, texture_pending={}, poll_us={}",
        workload.iterations(), markerBefore, markerAfter, bufferPending, texturePending,
        std::chrono::duration_cast<std::chrono::microseconds>(pollTime).count());
    EXPECT_TRUE(markerBefore && markerAfter) << "Workload completed too early; fail, do not silently retry";
    EXPECT_TRUE(bufferPending && texturePending);
    EXPECT_TRUE(bufferRejected && textureRejected);
    EXPECT_TRUE(pollTime < kNonblockingLimit);
    ASSERT_TRUE(bufferTask->isReady() && textureTask->isReady());
    EXPECT_TRUE(bufferTask->getDataNonBlocking() == knownBytes());
    EXPECT_TRUE(textureTask->getDataNonBlocking() == knownBytes());
}

GPU_TEST(NativeReadbackWorkloadDropPendingTexture)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    const auto source = device->createTexture2D(2, 1, ResourceFormat::RGBA32Uint, 1, 1, kWords.data());
    CopyContext::ReadTextureTask::SharedPtr task; // Workload cleanup drains before exceptional task destruction.
    testing::NativeGpuWorkload workload(context);
    workload.enqueue();
    task = context->asyncReadTextureSubresource(source.get(), 0);
    ASSERT_FALSE(task->isReady());
    EXPECT_THROW(task->getDataNonBlocking());
    const bool markerBefore = workload.markerPending();
    ASSERT_TRUE(markerBefore) << "Workload completed before texture reset; fail without retry";
    const auto start = std::chrono::steady_clock::now();
    task.reset();
    const auto dropTime = std::chrono::steady_clock::now() - start;
    const bool markerAfter = workload.markerPending();
    workload.finish();
    logInfo("NATIVE_WORKLOAD_DROP texture iterations={}, marker_before={}, marker_after={}, drop_us={}",
        workload.iterations(), markerBefore, markerAfter,
        std::chrono::duration_cast<std::chrono::microseconds>(dropTime).count());
    EXPECT_TRUE(markerAfter) << "A blocking destructor cannot pass: its prerequisite marker must still be pending after reset";
    EXPECT_TRUE(dropTime < kNonblockingLimit);
    expectRecovery(ctx);
}

GPU_TEST(NativeReadbackWorkloadDropPendingBuffer)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    const auto source = device->createBuffer(sizeof(kWords), ResourceBindFlags::ShaderResource,
        MemoryType::DeviceLocal, kWords.data());
    CopyContext::ReadBufferTask::SharedPtr task;
    testing::NativeGpuWorkload workload(context);
    workload.enqueue();
    task = context->asyncReadBuffer(source.get(), 4, 16);
    ASSERT_FALSE(task->isReady());
    EXPECT_THROW(task->getDataNonBlocking());
    const bool markerBefore = workload.markerPending();
    ASSERT_TRUE(markerBefore) << "Workload completed before buffer reset; fail without retry";
    const auto start = std::chrono::steady_clock::now();
    task.reset();
    const auto dropTime = std::chrono::steady_clock::now() - start;
    const bool markerAfter = workload.markerPending();
    workload.finish();
    logInfo("NATIVE_WORKLOAD_DROP buffer iterations={}, marker_before={}, marker_after={}, drop_us={}",
        workload.iterations(), markerBefore, markerAfter,
        std::chrono::duration_cast<std::chrono::microseconds>(dropTime).count());
    EXPECT_TRUE(markerAfter) << "A blocking destructor cannot pass: its prerequisite marker must still be pending after reset";
    EXPECT_TRUE(dropTime < kNonblockingLimit);
    expectRecovery(ctx);
}

GPU_TEST(NativeReadbackWorkloadRetainedSnapshotAfterSourceRelease)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    auto buffer = device->createBuffer(sizeof(kWords), ResourceBindFlags::ShaderResource, MemoryType::DeviceLocal, kWords.data());
    auto texture = device->createTexture2D(2, 1, ResourceFormat::RGBA32Uint, 1, 1, kWords.data());
    CopyContext::ReadBufferTask::SharedPtr bufferTask;
    CopyContext::ReadTextureTask::SharedPtr textureTask;
    testing::NativeGpuWorkload workload(context);
    workload.enqueue();
    bufferTask = context->asyncReadBuffer(buffer.get());
    textureTask = context->asyncReadTextureSubresource(texture.get(), 0);
    ASSERT_FALSE(bufferTask->isReady());
    ASSERT_FALSE(textureTask->isReady());
    EXPECT_THROW(bufferTask->getDataNonBlocking());
    EXPECT_THROW(textureTask->getDataNonBlocking());
    ASSERT_TRUE(workload.markerPending()) << "Workload completed before source mutation; fail without retry";
    const std::array<uint32_t, 8> replacement = {9, 8, 7, 6, 5, 4, 3, 2};
    buffer->setBlob(replacement.data(), 0, sizeof(replacement));
    texture->setSubresourceBlob(0, replacement.data(), sizeof(replacement));
    context->submit(false);
    ASSERT_TRUE(workload.markerPending()) << "Workload completed before source release; fail without retry";
    buffer = nullptr;
    texture = nullptr;
    const bool markerAfterRelease = workload.markerPending();
    workload.finish();
    EXPECT_TRUE(markerAfterRelease) << "Sources must actually be released while both readback snapshots remain pending";
    ASSERT_TRUE(bufferTask->isReady() && textureTask->isReady());
    EXPECT_TRUE(bufferTask->getDataNonBlocking() == knownBytes());
    EXPECT_TRUE(textureTask->getDataNonBlocking() == knownBytes());
    EXPECT_TRUE(bufferTask->getDataNonBlocking() == knownBytes());
    EXPECT_TRUE(textureTask->getDataNonBlocking() == knownBytes());
    logInfo("NATIVE_WORKLOAD_SNAPSHOT iterations={}, marker_after_source_release={}, bytes={}",
        workload.iterations(), markerAfterRelease, sizeof(kWords));
    expectRecovery(ctx);
}
} // namespace Falcor
