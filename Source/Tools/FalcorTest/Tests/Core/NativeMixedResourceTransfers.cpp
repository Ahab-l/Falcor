#include "Testing/UnitTest.h"
#include <algorithm>
#include <array>
#include <cstring>
#include <vector>

namespace Falcor
{
namespace
{
enum class ReadMode { Async, Sync, RegionCopy };

void checkMixedTransfers(GPUUnitTestContext& ctx, ReadMode mode)
{
    for (const size_t count : {8u, 257u, 16385u})
    {
        // Fresh device for each case, no warm-up/drain between buffer upload,
        // texture upload, and first buffer copy. Later synchronous rereads can
        // hide the original defect and must not replace this first snapshot.
        auto device = make_ref<Device>(ctx.getDevice()->getDesc());
        auto context = device->getRenderContext();
        std::vector<uint32_t> words(count);
        for (size_t i = 0; i < count; ++i) words[i] = 0x13579bdfu ^ (uint32_t(i) * 0x9e3779b9u);
        const size_t bytes = words.size() * sizeof(uint32_t);
        auto source = device->createBuffer(bytes, ResourceBindFlags::ShaderResource, MemoryType::DeviceLocal, words.data());
        auto texture = device->createTexture2D(2, 1, ResourceFormat::RGBA32Uint, 1, 1, words.data());
        std::vector<uint32_t> actual(count, 0u);
        if (mode == ReadMode::Async)
        {
            auto task = context->asyncReadBuffer(source.get());
            // Deliberately mutate the source only after snapshot submission.
            const std::vector<uint32_t> changed(count, 0xdeadbeefu);
            source->setBlob(changed.data(), 0, bytes);
            auto nextTask = context->asyncReadBuffer(source.get());
            context->submit(true);
            ASSERT_TRUE(task->isReady());
            auto result = task->getDataNonBlocking();
            ASSERT_EQ(result.size(), bytes);
            std::memcpy(actual.data(), result.data(), bytes);
            ASSERT_TRUE(nextTask->isReady());
            auto nextResult = nextTask->getDataNonBlocking();
            ASSERT_EQ(nextResult.size(), bytes);
            EXPECT_EQ(std::memcmp(nextResult.data(), changed.data(), bytes), 0);
        }
        else if (mode == ReadMode::Sync)
        {
            source->getBlob(actual.data(), 0, bytes);
        }
        else
        {
            const uint32_t sentinel = 0x2468ace0u;
            std::vector<uint32_t> initial(count + 2, sentinel);
            auto target = device->createBuffer(initial.size() * sizeof(uint32_t), ResourceBindFlags::ShaderResource,
                MemoryType::DeviceLocal, initial.data());
            std::vector<uint32_t> expectedTarget = initial;
            std::copy(words.begin() + 1, words.end() - 1, expectedTarget.begin() + 2);
            context->copyBufferRegion(target.get(), 2 * sizeof(uint32_t), source.get(), sizeof(uint32_t), bytes - 2 * sizeof(uint32_t));
            target->getBlob(initial.data(), 0, initial.size() * sizeof(uint32_t));
            EXPECT_TRUE(initial == expectedTarget) << "Both offsets and all untouched sentinels must remain exact; count=" << count;
            continue;
        }
        EXPECT_TRUE(actual == words) << "mode=" << int(mode) << " count=" << count;
    }
}
}

GPU_TEST(NativeMixedUploadAsyncSnapshot) { checkMixedTransfers(ctx, ReadMode::Async); }
GPU_TEST(NativeMixedUploadSyncSnapshot) { checkMixedTransfers(ctx, ReadMode::Sync); }
GPU_TEST(NativeMixedUploadBufferRegion) { checkMixedTransfers(ctx, ReadMode::RegionCopy); }
}
