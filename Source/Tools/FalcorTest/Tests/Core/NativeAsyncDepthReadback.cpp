#include "Testing/UnitTest.h"
#include "Core/API/Fence.h"
#include "Core/API/GFXAPI.h"
#include "NativeGpuWorkload.h"
#include "../../../../RenderPasses/customrenderpipline/CustomRenderPiplineReadback.h"
#include <chrono>
#include <cstring>
#include <thread>
#if FALCOR_HAS_D3D12
#include <d3d12sdklayers.h>
#endif

namespace Falcor
{
namespace
{
using namespace CustomRenderPipline;
void expectPlanes(GPUUnitTestContext& ctx, const DepthStencilReadback& data, uint32_t width, uint32_t height, float depth, uint8_t stencil)
{
    EXPECT_EQ(data.dimensions.x, width);
    EXPECT_EQ(data.dimensions.y, height);
    EXPECT_EQ(data.rowBytes[0], uint64_t(width) * 4);
    EXPECT_EQ(data.rowBytes[1], uint64_t(width));
    ASSERT_EQ(data.planes[0].size(), size_t(width) * height * 4);
    ASSERT_EQ(data.planes[1].size(), size_t(width) * height);
    for (size_t pixel = 0; pixel < size_t(width) * height; ++pixel)
    {
        float actual;
        std::memcpy(&actual, data.planes[0].data() + pixel * 4, 4);
        EXPECT_EQ(actual, depth) << "depth at pixel " << pixel;
        EXPECT_EQ(uint32_t(data.planes[1][pixel]), uint32_t(stencil)) << "stencil at pixel " << pixel;
    }
}
void clearView(RenderContext* context, const ref<Texture>& texture, uint32_t mip, uint32_t slice, float depth, uint8_t stencil)
{
    const auto view = texture->getDSV(mip, slice, 1);
    context->resourceBarrier(texture.get(), Resource::State::DepthStencil, &view->getViewInfo());
    context->clearDsv(view.get(), depth, stencil, true, true);
}
bool awaitReady(const DepthStencilReadbackTask::SharedPtr& task)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (!task->isReady() && std::chrono::steady_clock::now() < deadline)
        std::this_thread::sleep_for(std::chrono::milliseconds(1)); // Test-only bounded host wait.
    return task->isReady();
}
}

GPU_TEST(NativeAsyncDepthReadbackPendingLifetime, Device::Type::D3D12)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    auto source = device->createTexture2D(37, 19, ResourceFormat::D32FloatS8Uint, 1, 1, nullptr, ResourceBindFlags::DepthStencil);
    clearView(context, source, 0, 0, 0.25f, 173);
    auto gate = device->createFence();
    struct ReleaseGate { ref<Fence> fence; ~ReleaseGate() { fence->signal(1); } } release{gate};
    context->submit(false);
    context->wait(gate.get(), 1);
    auto task = readDepthStencilAsync(context, source.get());
    const auto start = std::chrono::steady_clock::now();
    const bool pending = !task->isReady();
    bool rejected = false;
    try { task->getDataNonBlocking(); } catch (const std::exception&) { rejected = true; }
    const auto elapsed = std::chrono::steady_clock::now() - start;
    clearView(context, source, 0, 0, 0.875f, 13);
    context->submit(false);
    source = nullptr;
    gate->signal(1);
    EXPECT_TRUE(pending && rejected);
    EXPECT_TRUE(elapsed < std::chrono::seconds(1));
    EXPECT_EQ(task->getDataSize(), uint64_t(37 * 19 * 5));
    EXPECT_GE(task->getStagingSize(), task->getDataSize());
    ASSERT_TRUE(awaitReady(task));
    const auto data = task->getDataNonBlocking();
    expectPlanes(ctx, data, 37, 19, 0.25f, 173);
    EXPECT_TRUE(data.planes == task->getDataNonBlocking().planes);
}

GPU_TEST(NativeAsyncDepthReadbackArrayCubeMipPlanes, Device::Type::D3D12)
{
#if FALCOR_HAS_D3D12
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    if (!device->getDesc().enableDebugLayer) ctx.skip("Requires --enable-debug-layer.");
    context->submit(true);
    Slang::ComPtr<ID3D12InfoQueue> info;
    FALCOR_D3D_CALL(device->getNativeHandle().as<ID3D12Device*>()->QueryInterface(IID_PPV_ARGS(info.writeRef())));
    const auto first = info->GetNumStoredMessagesAllowedByRetrievalFilter();
    const auto discarded = info->GetNumMessagesDiscardedByMessageCountLimit();
    for (bool cube : {false, true})
    {
        auto source = cube
            ? device->createTextureCube(32, 32, ResourceFormat::D32FloatS8Uint, 1, 3, nullptr, ResourceBindFlags::DepthStencil)
            : device->createTexture2D(37, 19, ResourceFormat::D32FloatS8Uint, 2, 3, nullptr, ResourceBindFlags::DepthStencil);
        // Texture GenericRead maps through gfx General (COMMON), not the
        // buffer-only GENERIC_READ union. Exercise global -> partial mapping.
        if (cube) context->resourceBarrier(source.get(), Resource::State::GenericRead);
        struct Job
        {
            DepthStencilReadbackTask::SharedPtr task;
            DepthStencilReadback reference;
            uint32_t width, height;
            float depth;
            uint8_t stencil;
        };
        std::vector<Job> jobs;
        for (uint32_t slice = 0; slice < source->getArrayLayerCount(); ++slice)
            for (uint32_t mip = 0; mip < source->getMipCount(); ++mip)
            {
                const float depth = 0.125f + float(slice * 3 + mip) / 32.f;
                const uint8_t stencil = uint8_t(17 + (slice * 3 + mip) * 7);
                clearView(context, source, mip, slice, depth, stencil);
                const auto reference = readDepthStencil(context, source.get(), mip, slice);
                const auto task = readDepthStencilAsync(context, source.get(), mip, slice);
                EXPECT_EQ(task->getDataSize(), uint64_t(source->getWidth(mip)) * source->getHeight(mip) * 5);
                jobs.push_back({task, reference, source->getWidth(mip), source->getHeight(mip), depth, stencil});
                if (cube)
                {
                    const auto view = source->getDSV(mip, slice, 1);
                    context->resourceBarrier(source.get(), Resource::State::GenericRead, &view->getViewInfo());
                    context->resourceBarrier(source.get(), Resource::State::GenericRead);
                }
                clearView(context, source, mip, slice, 0.f, 0);
            }
        context->submit(false);
        source = nullptr;
        for (const auto& job : jobs)
        {
            ASSERT_TRUE(awaitReady(job.task));
            const auto data = job.task->getDataNonBlocking();
            expectPlanes(ctx, data, job.width, job.height, job.depth, job.stencil);
            EXPECT_TRUE(data.planes == job.reference.planes);
            EXPECT_EQ(data.nativeFormats[0], uint32_t(DXGI_FORMAT_R32_TYPELESS));
            EXPECT_EQ(data.nativeFormats[1], uint32_t(DXGI_FORMAT_R8_TYPELESS));
        }
    }
    context->submit(true);
    EXPECT_EQ(info->GetNumMessagesDiscardedByMessageCountLimit(), discarded);
    for (uint64_t index = first; index < info->GetNumStoredMessagesAllowedByRetrievalFilter(); ++index)
    {
        SIZE_T size = 0;
        FALCOR_D3D_CALL(info->GetMessage(index, nullptr, &size));
        std::vector<uint8_t> bytes(size);
        auto message = reinterpret_cast<D3D12_MESSAGE*>(bytes.data());
        FALCOR_D3D_CALL(info->GetMessage(index, message, &size));
        EXPECT_TRUE(message->Severity > D3D12_MESSAGE_SEVERITY_ERROR) << message->pDescription;
    }
#endif
}

GPU_TEST(NativeAsyncDepthReadbackBoundaries, Device::Type::D3D12)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    auto source = device->createTexture2D(37, 19, ResourceFormat::D32FloatS8Uint, 2, 3, nullptr, ResourceBindFlags::DepthStencil);
    auto wrong = device->createTexture2D(4, 4, ResourceFormat::R32Float);
    clearView(context, source, 1, 1, 0.5f, 219);
    auto task = readDepthStencilAsync(context, source.get(), 1, 1);
    const uint64_t budget = task->getStagingSize();
    EXPECT_THROW(readDepthStencilAsync(nullptr, source.get()));
    EXPECT_THROW(readDepthStencilAsync(context, nullptr));
    EXPECT_THROW(readDepthStencilAsync(context, wrong.get()));
    EXPECT_THROW(readDepthStencilAsync(context, source.get(), 3, 0));
    EXPECT_THROW(readDepthStencilAsync(context, source.get(), 0, 2));
    EXPECT_THROW(readDepthStencilAsync(context, source.get(), 1, 1, 0));
    EXPECT_THROW(readDepthStencilAsync(context, source.get(), 1, 1, budget - 1));
    const auto exact = readDepthStencilAsync(context, source.get(), 1, 1, budget);
    EXPECT_EQ(exact->getStagingSize(), budget);
    ASSERT_TRUE(awaitReady(exact));
    expectPlanes(ctx, exact->getDataNonBlocking(), 18, 9, 0.5f, 219);
}

GPU_TEST(NativeAsyncDepthReadbackDropPending, Device::Type::D3D12)
{
#if FALCOR_HAS_D3D12
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    if (!device->getDesc().enableDebugLayer) ctx.skip("Requires --enable-debug-layer.");
    context->submit(true);
    Slang::ComPtr<ID3D12InfoQueue> info;
    FALCOR_D3D_CALL(device->getNativeHandle().as<ID3D12Device*>()->QueryInterface(IID_PPV_ARGS(info.writeRef())));
    const auto first = info->GetNumStoredMessagesAllowedByRetrievalFilter();
    const auto discarded = info->GetNumMessagesDiscardedByMessageCountLimit();
    auto source = device->createTexture2D(37, 19, ResourceFormat::D32FloatS8Uint, 1, 1, nullptr, ResourceBindFlags::DepthStencil);
    clearView(context, source, 0, 0, 0.25f, 173);
    DepthStencilReadbackTask::SharedPtr task; // Exceptional cleanup drains before releasing a retained task.
    testing::NativeGpuWorkload workload(context);
    workload.enqueue();
    task = readDepthStencilAsync(context, source.get());
    const bool taskPending = !task->isReady();
    const bool markerBefore = workload.markerPending();
    ASSERT_TRUE(taskPending && markerBefore) << "Workload completed before depth reset; fail without retry";
    const auto start = std::chrono::steady_clock::now();
    task.reset();
    const auto dropTime = std::chrono::steady_clock::now() - start;
    const bool markerAfter = workload.markerPending();
    source = nullptr;
    const bool markerAfterSource = workload.markerPending();
    workload.finish();
    logInfo("NATIVE_DEPTH_DROP marker_before={}, marker_after={}, marker_after_source={}, drop_us={}",
        markerBefore, markerAfter, markerAfterSource,
        std::chrono::duration_cast<std::chrono::microseconds>(dropTime).count());
    EXPECT_TRUE(markerAfter && markerAfterSource) << "Reset/source release must finish while the task prerequisite is pending";
    EXPECT_TRUE(dropTime < std::chrono::milliseconds(500));

    // Reuse the same context after abandonment; both planes must still copy correctly.
    source = device->createTexture2D(37, 19, ResourceFormat::D32FloatS8Uint, 1, 1, nullptr, ResourceBindFlags::DepthStencil);
    clearView(context, source, 0, 0, 0.875f, 13);
    const auto recovery = readDepthStencilAsync(context, source.get());
    context->submit(true);
    ASSERT_TRUE(recovery->isReady());
    expectPlanes(ctx, recovery->getDataNonBlocking(), 37, 19, 0.875f, 13);
    EXPECT_EQ(info->GetNumMessagesDiscardedByMessageCountLimit(), discarded);
    for (uint64_t index = first; index < info->GetNumStoredMessagesAllowedByRetrievalFilter(); ++index)
    {
        SIZE_T size = 0;
        FALCOR_D3D_CALL(info->GetMessage(index, nullptr, &size));
        std::vector<uint8_t> bytes(size);
        auto message = reinterpret_cast<D3D12_MESSAGE*>(bytes.data());
        FALCOR_D3D_CALL(info->GetMessage(index, message, &size));
        EXPECT_TRUE(message->Severity > D3D12_MESSAGE_SEVERITY_ERROR) << message->pDescription;
    }
#endif
}

GPU_TEST(NativeAsyncDepthReadbackLastDeviceOwner, Device::Type::D3D12)
{
    // A separate Device, without a retained native debug interface that could
    // mask native teardown. Only the task's two staging buffers retain Device.
    auto device = make_ref<Device>(ctx.getDevice()->getDesc());
    auto context = device->getRenderContext();
    auto source = device->createTexture2D(37, 19, ResourceFormat::D32FloatS8Uint, 1, 1, nullptr, ResourceBindFlags::DepthStencil);
    clearView(context, source, 0, 0, 0.375f, 219);
    auto task = readDepthStencilAsync(context, source.get());
    context->submit(true);
    ASSERT_TRUE(task->isReady());
    const auto before = task->getDataNonBlocking();
    expectPlanes(ctx, before, 37, 19, 0.375f, 219);
    source = nullptr;
    Device* rawDevice = device.get();
    device = nullptr;
    ASSERT_EQ(rawDevice->refCount(), 2);
    ASSERT_TRUE(task->isReady());
    const auto after = task->getDataNonBlocking();
    expectPlanes(ctx, after, 37, 19, 0.375f, 219);
    EXPECT_TRUE(before.planes == after.planes);
    task.reset();
    // No access to rawDevice/context after final ownership release. Final
    // Device teardown may drain; it is not the pending task-reset latency test.
}
}
