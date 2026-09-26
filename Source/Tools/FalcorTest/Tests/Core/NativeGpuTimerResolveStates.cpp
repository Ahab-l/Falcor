#include "Testing/UnitTest.h"
#include "Core/API/GpuTimer.h"
#include "Core/API/GFXAPI.h"
#include "Core/API/NativeHandleTraits.h"
#include <cmath>
#if FALCOR_HAS_D3D12
#include <d3d12sdklayers.h>
#endif

namespace Falcor
{
GPU_TEST(NativeGpuTimerResolveFirstAndReuse)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    if (!device->getDesc().enableDebugLayer) ctx.skip("Requires --enable-debug-layer.");
    context->submit(true);
#if FALCOR_HAS_D3D12
    Slang::ComPtr<ID3D12InfoQueue> info;
    uint64_t first = 0, discarded = 0;
    if (device->getType() == Device::Type::D3D12)
    {
        FALCOR_D3D_CALL(device->getNativeHandle().as<ID3D12Device*>()->QueryInterface(IID_PPV_ARGS(info.writeRef())));
        first = info->GetNumStoredMessagesAllowedByRetrievalFilter();
        discarded = info->GetNumMessagesDiscardedByMessageCountLimit();
    }
#endif
    // No shader, custom depth task, workload fixture or async readback API.
    // First resolve and reuse must agree with the tracked destination state.
    const auto timer = GpuTimer::create(device);
    for (uint32_t cycle = 0; cycle < 3; ++cycle)
    {
        timer->begin();
        timer->end();
        timer->resolve();
        context->submit(true);
        const auto elapsed = timer->getElapsedTime();
        EXPECT_TRUE(std::isfinite(elapsed) && elapsed >= 0.0);
        EXPECT_EQ(timer->getElapsedTime(), elapsed);
    }
#if FALCOR_HAS_D3D12
    if (info)
    {
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
    }
#endif
}
}
