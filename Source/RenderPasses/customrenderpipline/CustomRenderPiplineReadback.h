#pragma once
#include "Falcor.h"
#include "Core/API/NativeHandleTraits.h"
#include <array>
#include <cstring>
#include <limits>
#include <memory>

namespace Falcor::CustomRenderPipline
{
struct DepthStencilReadback
{
    uint2 dimensions;
    std::array<uint32_t, 2> nativeFormats;
    std::array<uint64_t, 2> rowBytes;
    std::array<std::vector<uint8_t>, 2> planes;
};

// Exact native D32S8 plane readback. The task owns all staging resources until
// GPU completion; it deliberately does not retain the source texture.
class DepthStencilReadbackTask
{
public:
    using SharedPtr = std::shared_ptr<DepthStencilReadbackTask>;

    static SharedPtr create(
        RenderContext* context,
        const Texture* texture,
        uint32_t mip,
        uint32_t slice,
        uint64_t maxStagingBytes
    )
    {
        FALCOR_CHECK(context && texture && context->getDevice() == texture->getDevice(),
            "CustomRenderPipline readback requires a same-device texture");
        FALCOR_CHECK((texture->getType() == Resource::Type::Texture2D || texture->getType() == Resource::Type::TextureCube) &&
            texture->getFormat() == ResourceFormat::D32FloatS8Uint && texture->getSampleCount() == 1 &&
            mip < texture->getMipCount() && slice < texture->getArrayLayerCount(),
            "CustomRenderPipline depth/stencil readback requires a bounded single-sample D32S8 texture view");
#if FALCOR_HAS_D3D12
        const auto device = context->getDevice();
        FALCOR_CHECK(device->getType() == Device::Type::D3D12,
            "CustomRenderPipline depth/stencil readback requires D3D12");
        auto nativeDevice = device->getNativeHandle().as<ID3D12Device*>();
        auto nativeTexture = texture->getNativeHandle().as<ID3D12Resource*>();
        const auto desc = nativeTexture->GetDesc();
        auto task = SharedPtr(new DepthStencilReadbackTask);
        task->mDimensions = uint2(texture->getWidth(mip), texture->getHeight(mip));
        const uint32_t baseSubresource = texture->getSubresourceIndex(slice, mip);
        const uint32_t planeStride = texture->getMipCount() * texture->getArrayLayerCount();

        // Query and validate both planes before allocating either staging buffer.
        // This guarantees a rejected aggregate budget cannot partially issue work.
        for (uint32_t plane = 0; plane < 2; ++plane)
        {
            nativeDevice->GetCopyableFootprints(
                &desc,
                baseSubresource + plane * planeStride,
                1,
                0,
                &task->mFootprints[plane],
                &task->mRowCounts[plane],
                &task->mRowBytes[plane],
                &task->mStagingSizes[plane]
            );
            FALCOR_CHECK(task->mRowCounts[plane] == task->mDimensions.y && task->mFootprints[plane].Footprint.Depth == 1 &&
                    task->mStagingSizes[plane] != UINT64_MAX && task->mStagingSizes[plane] > 0 &&
                    task->mRowBytes[plane] > 0 && task->mRowBytes[plane] <= task->mFootprints[plane].Footprint.RowPitch &&
                    task->mRowBytes[plane] <= std::numeric_limits<size_t>::max() / task->mRowCounts[plane],
                "CustomRenderPipline invalid native plane footprint");
            task->mNativeFormats[plane] = uint32_t(task->mFootprints[plane].Footprint.Format);
            task->mDataSize += task->mRowBytes[plane] * task->mRowCounts[plane];
        }
        FALCOR_CHECK(task->mStagingSizes[0] <= maxStagingBytes &&
                task->mStagingSizes[1] <= maxStagingBytes - task->mStagingSizes[0],
            "CustomRenderPipline depth/stencil readback exceeds staging byte budget");
        for (uint32_t plane = 0; plane < 2; ++plane)
            task->mBuffers[plane] = device->createBuffer(
                task->mStagingSizes[plane], ResourceBindFlags::None, MemoryType::ReadBack, nullptr
            );
        task->mStagingSize = task->mBuffers[0]->getSize() + task->mBuffers[1]->getSize();

        context->resourceBarrier(texture, Resource::State::CopySource);
        // Close any active render encoder before issuing native copy commands.
        context->getLowLevelData()->getResourceCommandEncoder();
        auto commandList = context->getLowLevelData()->getCommandBufferNativeHandle().as<ID3D12GraphicsCommandList*>();
        for (uint32_t plane = 0; plane < 2; ++plane)
        {
            D3D12_TEXTURE_COPY_LOCATION source = {};
            source.pResource = nativeTexture;
            source.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
            source.SubresourceIndex = baseSubresource + plane * planeStride;
            D3D12_TEXTURE_COPY_LOCATION destination = {};
            destination.pResource = task->mBuffers[plane]->getNativeHandle().as<ID3D12Resource*>();
            destination.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
            destination.PlacedFootprint = task->mFootprints[plane];
            commandList->CopyTextureRegion(&destination, 0, 0, 0, &source, nullptr);
        }
        // Submit now so the source may be overwritten or released immediately.
        context->setPendingCommands(true);
        task->mpFence = device->createFence();
        task->mpFence->breakStrongReferenceToDevice();
        context->submit(false);
        context->signal(task->mpFence.get());
        return task;
#else
        FALCOR_THROW("CustomRenderPipline depth/stencil readback requires D3D12");
#endif
    }

    bool isReady() const
    {
        return mpFence->getCurrentValue() >= mpFence->getSignaledValue();
    }

    uint64_t getDataSize() const { return mDataSize; }
    uint64_t getStagingSize() const { return mStagingSize; }

    DepthStencilReadback getDataNonBlocking() const
    {
        FALCOR_CHECK(isReady(), "CustomRenderPipline depth/stencil readback is not ready");
        return copyData();
    }

private:
    friend DepthStencilReadback readDepthStencil(RenderContext*, const Texture*, uint32_t, uint32_t);

    DepthStencilReadbackTask() = default;

    DepthStencilReadback getDataBlocking() const
    {
        mpFence->wait();
        return copyData();
    }

    DepthStencilReadback copyData() const
    {
        DepthStencilReadback result;
        result.dimensions = mDimensions;
        result.nativeFormats = mNativeFormats;
        result.rowBytes = mRowBytes;
#if FALCOR_HAS_D3D12
        for (uint32_t plane = 0; plane < 2; ++plane)
        {
            result.planes[plane].resize(size_t(mRowBytes[plane]) * mRowCounts[plane]);
            const auto* source = static_cast<const uint8_t*>(mBuffers[plane]->map());
            for (uint32_t row = 0; row < mRowCounts[plane]; ++row)
                std::memcpy(
                    result.planes[plane].data() + row * size_t(mRowBytes[plane]),
                    source + mFootprints[plane].Offset + row * size_t(mFootprints[plane].Footprint.RowPitch),
                    size_t(mRowBytes[plane])
                );
            mBuffers[plane]->unmap();
        }
#endif
        return result;
    }

    ref<Fence> mpFence;
    uint2 mDimensions = {};
    std::array<uint32_t, 2> mNativeFormats = {};
    std::array<uint64_t, 2> mRowBytes = {};
    uint64_t mDataSize = 0;
    uint64_t mStagingSize = 0;
#if FALCOR_HAS_D3D12
    std::array<D3D12_PLACED_SUBRESOURCE_FOOTPRINT, 2> mFootprints = {};
    std::array<UINT, 2> mRowCounts = {};
    std::array<UINT64, 2> mStagingSizes = {};
    std::array<ref<Buffer>, 2> mBuffers;
#endif
};

inline DepthStencilReadbackTask::SharedPtr readDepthStencilAsync(
    RenderContext* context,
    const Texture* texture,
    uint32_t mip = 0,
    uint32_t slice = 0,
    uint64_t maxStagingBytes = uint64_t(64) * 1024 * 1024
)
{
    return DepthStencilReadbackTask::create(context, texture, mip, slice, maxStagingBytes);
}

// Diagnostic readback, not a sampled view or a replacement for the packed contract.
// This compatibility wrapper is the only blocking path and shares the async copy implementation.
inline DepthStencilReadback readDepthStencil(RenderContext* context, const Texture* texture, uint32_t mip = 0, uint32_t slice = 0)
{
    return readDepthStencilAsync(context, texture, mip, slice, std::numeric_limits<uint64_t>::max())->getDataBlocking();
}
}
