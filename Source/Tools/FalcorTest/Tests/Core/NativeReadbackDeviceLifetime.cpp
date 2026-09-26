#include "Testing/UnitTest.h"
#include <array>
#include <vector>

namespace Falcor
{
namespace
{
const std::array<uint32_t, 8> kLifetimeWords = {1u, 3u, 0xabcdef01u, 0xffffffffu, 0u, 17u, 257u, 65537u};

void checkLastDeviceOwner(GPUUnitTestContext& ctx, bool textureInput)
{
    // Separate from the framework-owned test Device: retain only the task's
    // staging Buffer ownership before exercising result access and teardown.
    auto device = make_ref<Device>(ctx.getDevice()->getDesc());
    auto context = device->getRenderContext();
    auto buffer = device->createBuffer(sizeof(kLifetimeWords), ResourceBindFlags::ShaderResource,
        MemoryType::DeviceLocal, kLifetimeWords.data());
    auto texture = device->createTexture2D(2, 1, ResourceFormat::RGBA32Uint, 1, 1, kLifetimeWords.data());
    auto bufferTask = textureInput ? nullptr : context->asyncReadBuffer(buffer.get());
    auto textureTask = textureInput ? context->asyncReadTextureSubresource(texture.get(), 0) : nullptr;
    context->submit(true);
    const auto beforeRelease = textureInput ? textureTask->getDataNonBlocking() : bufferTask->getDataNonBlocking();
    buffer = nullptr;
    texture = nullptr;
    Device* rawDevice = device.get();
    device = nullptr;
    // rawDevice is still valid only because the task's staging buffer owns it.
    // This also detects unintended new task/fence reference cycles.
    ASSERT_EQ(rawDevice->refCount(), 1);
    const auto first = reinterpret_cast<const uint8_t*>(kLifetimeWords.data());
    const std::vector<uint8_t> expected(first, first + sizeof(kLifetimeWords));
    ASSERT_TRUE(beforeRelease == expected) << "The copy must already be correct before ownership changes";
    if (textureInput)
    {
        ASSERT_TRUE(textureTask->isReady());
        EXPECT_TRUE(textureTask->getDataNonBlocking() == expected);
        EXPECT_TRUE(textureTask->getData() == expected);
    }
    else
    {
        ASSERT_TRUE(bufferTask->isReady());
        const auto actual = bufferTask->getDataNonBlocking();
        ASSERT_TRUE(actual == expected);
    }
    textureTask.reset();
    bufferTask.reset();
    // Do not access context/rawDevice after the final owner is released.
}
}

GPU_TEST(NativeReadbackLastDeviceOwnerBuffer)
{
    checkLastDeviceOwner(ctx, false);
}

GPU_TEST(NativeReadbackLastDeviceOwnerTexture)
{
    checkLastDeviceOwner(ctx, true);
}

}
