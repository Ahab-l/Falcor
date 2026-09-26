/***************************************************************************
 # Copyright (c) 2015-23, NVIDIA CORPORATION. All rights reserved.
 #
 # Redistribution and use in source and binary forms, with or without
 # modification, are permitted provided that the following conditions
 # are met:
 #  * Redistributions of source code must retain the above copyright
 #    notice, this list of conditions and the following disclaimer.
 #  * Redistributions in binary form must reproduce the above copyright
 #    notice, this list of conditions and the following disclaimer in the
 #    documentation and/or other materials provided with the distribution.
 #  * Neither the name of NVIDIA CORPORATION nor the names of its
 #    contributors may be used to endorse or promote products derived
 #    from this software without specific prior written permission.
 #
 # THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS" AND ANY
 # EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 # IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 # PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 # CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 # EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 # PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 # PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
 # OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 # (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 # OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 **************************************************************************/
#include "CopyContext.h"
#include "Device.h"
#include "Texture.h"
#include "Buffer.h"
#include "Fence.h"
#include "GFXAPI.h"
#include "GFXHelpers.h"
#include "NativeHandleTraits.h"
#include "Aftermath.h"
#if FALCOR_HAS_D3D12
#include "Shared/D3D12DescriptorPool.h"
#include "Shared/D3D12DescriptorData.h"
#endif
#include "Core/Error.h"
#include "Utils/Logger.h"
#include "Utils/Math/Common.h"

#if FALCOR_HAS_CUDA
#include "Utils/CudaUtils.h"
#endif

namespace Falcor
{
#if FALCOR_HAS_D3D12
namespace
{
Resource::State getD3D12BufferReadState(const Buffer* pBuffer, Resource::State state)
{
    const auto flags = pBuffer->getBindFlags();
    if (!is_set(flags, ResourceBindFlags::ShaderResource) ||
        (!is_set(flags, ResourceBindFlags::Vertex) && !is_set(flags, ResourceBindFlags::Index)))
        return state;

    // Scene geometry is read through IA and shader views in the same draw. Include only compatible read bits,
    // even when the buffer also permits UAV writes; the next write must leave this read union explicitly.
    switch (state)
    {
    case Resource::State::VertexBuffer:
    case Resource::State::ConstantBuffer:
    case Resource::State::IndexBuffer:
    case Resource::State::ShaderResource:
    case Resource::State::PixelShader:
    case Resource::State::NonPixelShader:
    case Resource::State::IndirectArg:
    case Resource::State::CopySource:
        return Resource::State::GenericRead;
    default:
        return state;
    }
}

D3D12_RESOURCE_STATES getD3D12ResourceState(Resource::State state, bool buffer)
{
    // gfx maps Falcor GenericRead to General, which is native COMMON, not GENERIC_READ. Native transitions
    // must therefore handle both entry into this state and outgoing transitions, preserving the tracked state.
    if (buffer && state == Resource::State::GenericRead)
        return D3D12_RESOURCE_STATE_GENERIC_READ;

    // Match the existing gfx D3D12 mapping for the other states, including legacy General aliases.
    switch (getGFXResourceState(state))
    {
    case gfx::ResourceState::VertexBuffer:
    case gfx::ResourceState::ConstantBuffer:
        return D3D12_RESOURCE_STATE_VERTEX_AND_CONSTANT_BUFFER;
    case gfx::ResourceState::IndexBuffer:
        return D3D12_RESOURCE_STATE_INDEX_BUFFER;
    case gfx::ResourceState::StreamOutput:
        return D3D12_RESOURCE_STATE_STREAM_OUT;
    case gfx::ResourceState::ShaderResource:
        return D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE | D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
    case gfx::ResourceState::PixelShaderResource:
        return D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
    case gfx::ResourceState::NonPixelShaderResource:
        return D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
    case gfx::ResourceState::UnorderedAccess:
        return D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
    case gfx::ResourceState::RenderTarget:
        return D3D12_RESOURCE_STATE_RENDER_TARGET;
    case gfx::ResourceState::DepthWrite:
        return D3D12_RESOURCE_STATE_DEPTH_WRITE;
    case gfx::ResourceState::IndirectArgument:
        return D3D12_RESOURCE_STATE_INDIRECT_ARGUMENT;
    case gfx::ResourceState::CopySource:
        return D3D12_RESOURCE_STATE_COPY_SOURCE;
    case gfx::ResourceState::CopyDestination:
        return D3D12_RESOURCE_STATE_COPY_DEST;
    case gfx::ResourceState::ResolveSource:
        return D3D12_RESOURCE_STATE_RESOLVE_SOURCE;
    case gfx::ResourceState::ResolveDestination:
        return D3D12_RESOURCE_STATE_RESOLVE_DEST;
    case gfx::ResourceState::AccelerationStructure:
        return D3D12_RESOURCE_STATE_RAYTRACING_ACCELERATION_STRUCTURE;
    default:
        return D3D12_RESOURCE_STATE_COMMON;
    }
}
} // namespace
#endif

CopyContext::CopyContext(Device* pDevice, gfx::ICommandQueue* pQueue) : mpDevice(pDevice)
{
    FALCOR_ASSERT(mpDevice);
    FALCOR_ASSERT(pQueue);
    mpLowLevelData = std::make_unique<LowLevelContextData>(mpDevice, pQueue);
}

CopyContext::~CopyContext() = default;

ref<Device> CopyContext::getDevice() const
{
    return ref<Device>(mpDevice);
}

Profiler* CopyContext::getProfiler() const
{
    return mpDevice->getProfiler();
}

void CopyContext::submit(bool wait)
{
    if (mCommandsPending)
    {
        mpLowLevelData->submitCommandBuffer();
        mCommandsPending = false;
    }
    else
    {
        // We need to signal even if there are no commands to execute. We need this because some resources may have been released since the
        // last flush(), and unless we signal they will not be released
        signal(mpLowLevelData->getFence().get());
    }

    bindDescriptorHeaps();

    if (wait)
    {
        mpLowLevelData->getFence()->wait();
    }
}

uint64_t CopyContext::signal(Fence* pFence, uint64_t value)
{
    FALCOR_CHECK(pFence, "'fence' must not be null");
    uint64_t signalValue = pFence->updateSignaledValue(value);
    mpLowLevelData->getGfxCommandQueue()->executeCommandBuffers(0, nullptr, pFence->getGfxFence(), signalValue);
    return signalValue;
}

void CopyContext::wait(Fence* pFence, uint64_t value)
{
    FALCOR_CHECK(pFence, "'fence' must not be null");
    uint64_t waitValue = value == Fence::kAuto ? pFence->getSignaledValue() : value;
    gfx::IFence* fences[] = {pFence->getGfxFence()};
    uint64_t waitValues[] = {waitValue};
    FALCOR_GFX_CALL(mpLowLevelData->getGfxCommandQueue()->waitForFenceValuesOnDevice(1, fences, waitValues));
}

#if FALCOR_HAS_CUDA
void CopyContext::waitForCuda(cudaStream_t stream)
{
    if (mpDevice->getType() == Device::Type::D3D12)
    {
        mpLowLevelData->getCudaSemaphore()->waitForCuda(this, stream);
    }
    else
    {
        // In the past, we used to wait for all CUDA work to be done.
        // Since GFX with Vulkan doesn't support shared fences yet, we do the same here.
        cuda_utils::deviceSynchronize();
    }
}

void CopyContext::waitForFalcor(cudaStream_t stream)
{
    if (mpDevice->getType() == Device::Type::D3D12)
    {
        mpLowLevelData->submitCommandBuffer();
        mpLowLevelData->getCudaSemaphore()->waitForFalcor(this, stream);
    }
    else
    {
        // In the past, we used to wait for all work on the command queue to be done.
        // Since GFX with Vulkan doesn't support shared fences yet, we do the same here.
        submit(true);
    }
}
#endif

CopyContext::ReadTextureTask::SharedPtr CopyContext::asyncReadTextureSubresource(
    const Texture* pTexture, uint32_t subresourceIndex, uint64_t maxStagingBytes)
{
    return CopyContext::ReadTextureTask::create(this, pTexture, subresourceIndex, maxStagingBytes);
}

CopyContext::ReadBufferTask::SharedPtr CopyContext::asyncReadBuffer(
    const Buffer* pBuffer, size_t offset, size_t size, uint64_t maxStagingBytes)
{
    return ReadBufferTask::create(this, pBuffer, offset, size, maxStagingBytes);
}

std::vector<uint8_t> CopyContext::readTextureSubresource(const Texture* pTexture, uint32_t subresourceIndex)
{
    CopyContext::ReadTextureTask::SharedPtr pTask = asyncReadTextureSubresource(pTexture, subresourceIndex);
    return pTask->getData();
}

bool CopyContext::resourceBarrier(const Resource* pResource, Resource::State newState, const ResourceViewInfo* pViewInfo)
{
    const Texture* pTexture = dynamic_cast<const Texture*>(pResource);
    if (pTexture)
    {
        bool globalBarrier = pTexture->isStateGlobal();
        if (pViewInfo)
        {
            globalBarrier = globalBarrier && pViewInfo->firstArraySlice == 0;
            globalBarrier = globalBarrier && pViewInfo->mostDetailedMip == 0;
            globalBarrier = globalBarrier && pViewInfo->mipCount == pTexture->getMipCount();
            globalBarrier = globalBarrier && pViewInfo->arraySize == pTexture->getArrayLayerCount();
        }

        if (globalBarrier)
        {
            return textureBarrier(pTexture, newState);
        }
        else
        {
            return subresourceBarriers(pTexture, newState, pViewInfo);
        }
    }
    else
    {
        const Buffer* pBuffer = dynamic_cast<const Buffer*>(pResource);
        return bufferBarrier(pBuffer, newState);
    }
}

bool CopyContext::subresourceBarriers(const Texture* pTexture, Resource::State newState, const ResourceViewInfo* pViewInfo)
{
    ResourceViewInfo fullResource;
    bool setGlobal = false;
    if (pViewInfo == nullptr)
    {
        fullResource.arraySize = pTexture->getArrayLayerCount();
        fullResource.firstArraySlice = 0;
        fullResource.mipCount = pTexture->getMipCount();
        fullResource.mostDetailedMip = 0;
        setGlobal = true;
        pViewInfo = &fullResource;
    }

    bool entireViewTransitioned = true;

    for (uint32_t a = pViewInfo->firstArraySlice; a < pViewInfo->firstArraySlice + pViewInfo->arraySize; a++)
    {
        for (uint32_t m = pViewInfo->mostDetailedMip; m < pViewInfo->mipCount + pViewInfo->mostDetailedMip; m++)
        {
            Resource::State oldState = pTexture->getSubresourceState(a, m);
            if (oldState != newState)
            {
                apiSubresourceBarrier(pTexture, newState, oldState, a, m);
                if (setGlobal == false)
                    pTexture->setSubresourceState(a, m, newState);
                mCommandsPending = true;
            }
            else
                entireViewTransitioned = false;
        }
    }
    if (setGlobal)
        pTexture->setGlobalState(newState);
    return entireViewTransitioned;
}

void CopyContext::updateTextureData(const Texture* pTexture, const void* pData)
{
    mCommandsPending = true;
    updateTextureSubresources(pTexture, 0, pTexture->getSubresourceCount(), pData);
}

void CopyContext::updateSubresourceData(
    const Texture* pDst,
    uint32_t subresource,
    const void* pData,
    const uint3& offset,
    const uint3& size
)
{
    mCommandsPending = true;
    updateTextureSubresources(pDst, subresource, 1, pData, offset, size);
}

void CopyContext::bindDescriptorHeaps() {}

void CopyContext::bindCustomGPUDescriptorPool()
{
#if FALCOR_HAS_D3D12
    mpDevice->requireD3D12();

    const D3D12DescriptorPool* pGpuPool = mpDevice->getD3D12GpuDescriptorPool().get();
    const D3D12DescriptorPool::ApiData* pData = pGpuPool->getApiData();
    ID3D12DescriptorHeap* pHeaps[D3D12DescriptorPool::ApiData::kHeapCount];
    uint32_t heapCount = 0;
    for (uint32_t i = 0; i < std::size(pData->pHeaps); i++)
    {
        if (pData->pHeaps[i])
        {
            pHeaps[heapCount] = pData->pHeaps[i]->getApiHandle();
            heapCount++;
        }
    }
    mpLowLevelData->getCommandBufferNativeHandle().as<ID3D12GraphicsCommandList*>()->SetDescriptorHeaps(heapCount, pHeaps);
#endif
}

void CopyContext::unbindCustomGPUDescriptorPool()
{
#if FALCOR_HAS_D3D12
    mpDevice->requireD3D12();

    Slang::ComPtr<gfx::ICommandBufferD3D12> d3d12CommandBuffer;
    mpLowLevelData->getGfxCommandBuffer()->queryInterface(
        SlangUUID SLANG_UUID_ICommandBufferD3D12, reinterpret_cast<void**>(d3d12CommandBuffer.writeRef())
    );
    d3d12CommandBuffer->invalidateDescriptorHeapBinding();
#endif
}

void CopyContext::updateTextureSubresources(
    const Texture* pTexture,
    uint32_t firstSubresource,
    uint32_t subresourceCount,
    const void* pData,
    const uint3& offset,
    const uint3& size
)
{
    resourceBarrier(pTexture, Resource::State::CopyDest);

    bool copyRegion = any(offset != uint3(0)) || any(size != uint3(-1));
    FALCOR_ASSERT(subresourceCount == 1 || (copyRegion == false));
    uint8_t* dataPtr = (uint8_t*)pData;
    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();
    gfx::ITextureResource::Offset3D gfxOffset = {
        static_cast<gfx::GfxIndex>(offset.x), static_cast<gfx::GfxIndex>(offset.y), static_cast<gfx::GfxIndex>(offset.z)};
    gfx::ITextureResource::Extents gfxSize = {
        static_cast<gfx::GfxCount>(size.x), static_cast<gfx::GfxCount>(size.y), static_cast<gfx::GfxCount>(size.z)};
    gfx::FormatInfo formatInfo = {};
    gfx::gfxGetFormatInfo(getGFXFormat(pTexture->getFormat()), &formatInfo);
    for (uint32_t index = firstSubresource; index < firstSubresource + subresourceCount; index++)
    {
        gfx::SubresourceRange subresourceRange = {};
        subresourceRange.baseArrayLayer = static_cast<gfx::GfxIndex>(pTexture->getSubresourceArraySlice(index));
        subresourceRange.mipLevel = static_cast<gfx::GfxIndex>(pTexture->getSubresourceMipLevel(index));
        subresourceRange.layerCount = 1;
        subresourceRange.mipLevelCount = 1;
        if (!copyRegion)
        {
            gfxSize.width = align_to(formatInfo.blockWidth, static_cast<gfx::GfxCount>(pTexture->getWidth(subresourceRange.mipLevel)));
            gfxSize.height = align_to(formatInfo.blockHeight, static_cast<gfx::GfxCount>(pTexture->getHeight(subresourceRange.mipLevel)));
            gfxSize.depth = static_cast<gfx::GfxCount>(pTexture->getDepth(subresourceRange.mipLevel));
        }
        gfx::ITextureResource::SubresourceData data = {};
        data.data = dataPtr;
        data.strideY = static_cast<int64_t>(gfxSize.width) / formatInfo.blockWidth * formatInfo.blockSizeInBytes;
        data.strideZ = data.strideY * (gfxSize.height / formatInfo.blockHeight);
        dataPtr += data.strideZ * gfxSize.depth;
        resourceEncoder->uploadTextureData(pTexture->getGfxTextureResource(), subresourceRange, gfxOffset, gfxSize, &data, 1);
    }
}

CopyContext::ReadTextureTask::SharedPtr CopyContext::ReadTextureTask::create(
    CopyContext* pCtx,
    const Texture* pTexture,
    uint32_t subresourceIndex,
    uint64_t maxStagingBytes
)
{
    FALCOR_CHECK(pCtx && pTexture && pCtx->getDevice() == pTexture->getDevice(),
        "Asynchronous readback requires a same-device texture");
    FALCOR_CHECK(pTexture->getSampleCount() == 1 && subresourceIndex < pTexture->getSubresourceCount(),
        "Asynchronous readback requires a valid single-sample subresource");
    SharedPtr pThis = SharedPtr(new ReadTextureTask);
    pThis->mpContext = pCtx;
    // Get footprint
    gfx::ITextureResource* srcTexture = pTexture->getGfxTextureResource();
    gfx::FormatInfo formatInfo;
    gfx::gfxGetFormatInfo(srcTexture->getDesc()->format, &formatInfo);

#if FALCOR_HAS_D3D12
    // The gfx copy encoder does not preserve a complete block footprint for
    // compressed mip tails smaller than a block. Use the native footprint and
    // copy the full subresource, including its padded physical block extent.
    if (pCtx->getDevice()->getType() == Device::Type::D3D12 && formatInfo.blockWidth > 1)
    {
        auto nativeDevice = pCtx->getDevice()->getNativeHandle().as<ID3D12Device*>();
        auto nativeTexture = pTexture->getNativeHandle().as<ID3D12Resource*>();
        const auto nativeDesc = nativeTexture->GetDesc();
        D3D12_PLACED_SUBRESOURCE_FOOTPRINT footprint = {};
        UINT rows = 0;
        UINT64 rowBytes = 0, totalBytes = 0;
        nativeDevice->GetCopyableFootprints(&nativeDesc, subresourceIndex, 1, 0, &footprint, &rows, &rowBytes, &totalBytes);
        FALCOR_CHECK(totalBytes != UINT64_MAX && rowBytes && rowBytes <= UINT32_MAX && footprint.Offset == 0,
            "Invalid native compressed texture readback footprint");
        pThis->mActualRowSize = uint32_t(rowBytes);
        pThis->mRowSize = footprint.Footprint.RowPitch;
        pThis->mRowCount = rows;
        pThis->mDepth = footprint.Footprint.Depth;
        FALCOR_CHECK(totalBytes <= maxStagingBytes, "Readback exceeds staging byte budget");
        pThis->mpBuffer = pCtx->getDevice()->createBuffer(totalBytes, ResourceBindFlags::None, MemoryType::ReadBack, nullptr);
        pCtx->resourceBarrier(pTexture, Resource::State::CopySource);
        pCtx->getLowLevelData()->getResourceCommandEncoder();
        auto commandList = pCtx->getLowLevelData()->getCommandBufferNativeHandle().as<ID3D12GraphicsCommandList*>();
        D3D12_TEXTURE_COPY_LOCATION source = {};
        source.pResource = nativeTexture;
        source.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
        source.SubresourceIndex = subresourceIndex;
        D3D12_TEXTURE_COPY_LOCATION destination = {};
        destination.pResource = pThis->mpBuffer->getNativeHandle().as<ID3D12Resource*>();
        destination.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
        destination.PlacedFootprint = footprint;
        commandList->CopyTextureRegion(&destination, 0, 0, 0, &source, nullptr);
        pCtx->setPendingCommands(true);
        pThis->mpFence = pCtx->getDevice()->createFence();
        pThis->mpFence->breakStrongReferenceToDevice();
        pCtx->submit(false);
        pCtx->signal(pThis->mpFence.get());
        return pThis;
    }
#endif

    auto mipLevel = pTexture->getSubresourceMipLevel(subresourceIndex);
    pThis->mActualRowSize =
        uint32_t((pTexture->getWidth(mipLevel) + formatInfo.blockWidth - 1) / formatInfo.blockWidth * formatInfo.blockSizeInBytes);
    size_t rowAlignment = 1;
    pCtx->mpDevice->getGfxDevice()->getTextureRowAlignment(&rowAlignment);
    pThis->mRowSize = align_to(static_cast<uint32_t>(rowAlignment), pThis->mActualRowSize);
    uint64_t rowCount = (pTexture->getHeight(mipLevel) + formatInfo.blockHeight - 1) / formatInfo.blockHeight;
    uint64_t size = pTexture->getDepth(mipLevel) * rowCount * pThis->mRowSize;
    FALCOR_CHECK(size && size <= maxStagingBytes, "Readback exceeds staging byte budget");

    // Create buffer
    pThis->mpBuffer = pCtx->getDevice()->createBuffer(size, ResourceBindFlags::None, MemoryType::ReadBack, nullptr);

    // Copy from texture to buffer
    pCtx->resourceBarrier(pTexture, Resource::State::CopySource);
    auto encoder = pCtx->getLowLevelData()->getResourceCommandEncoder();
    gfx::SubresourceRange srcSubresource = {};
    srcSubresource.baseArrayLayer = pTexture->getSubresourceArraySlice(subresourceIndex);
    srcSubresource.mipLevel = mipLevel;
    srcSubresource.layerCount = 1;
    srcSubresource.mipLevelCount = 1;
    encoder->copyTextureToBuffer(
        pThis->mpBuffer->getGfxBufferResource(),
        0,
        size,
        pThis->mRowSize,
        srcTexture,
        gfx::ResourceState::CopySource,
        srcSubresource,
        gfx::ITextureResource::Offset3D(0, 0, 0),
        gfx::ITextureResource::Extents{
            static_cast<gfx::GfxIndex>(pTexture->getWidth(mipLevel)),
            static_cast<gfx::GfxIndex>(pTexture->getHeight(mipLevel)),
            static_cast<gfx::GfxIndex>(pTexture->getDepth(mipLevel))}
    );
    pCtx->setPendingCommands(true);

    // Create a fence and signal
    pThis->mpFence = pCtx->getDevice()->createFence();
    pThis->mpFence->breakStrongReferenceToDevice();
    pCtx->submit(false);
    pCtx->signal(pThis->mpFence.get());
    pThis->mRowCount = (uint32_t)rowCount;
    pThis->mDepth = pTexture->getDepth(mipLevel);
    return pThis;
}

CopyContext::ReadTextureTask::~ReadTextureTask()
{
    // A caller may abandon the task while its queue signal is pending. Keep
    // the native fence until normal deferred resource retirement. Do this
    // while the staging buffer still owns Device; Fence has a weak Device
    // reference and the buffer member is destroyed before the fence member.
    // The null guards also cover partially constructed tasks.
    if (mpBuffer && mpFence)
        mpBuffer->getDevice()->releaseResource(mpFence->getGfxFence());
}

void CopyContext::ReadTextureTask::getData(void* pData, size_t size) const
{
    mpFence->wait();
    copyData(pData, size);
}

bool CopyContext::ReadTextureTask::isReady() const
{
    return mpFence->getCurrentValue() >= mpFence->getSignaledValue();
}

std::vector<uint8_t> CopyContext::ReadTextureTask::getDataNonBlocking() const
{
    FALCOR_CHECK(isReady(), "Readback is not ready");
    std::vector<uint8_t> result(getDataSize());
    copyData(result.data(), result.size());
    return result;
}

void CopyContext::ReadTextureTask::copyData(void* pData, size_t size) const
{
    FALCOR_CHECK(size == getDataSize() && pData, "Readback destination size mismatch");

    uint8_t* pDst = reinterpret_cast<uint8_t*>(pData);
    const uint8_t* pSrc = reinterpret_cast<const uint8_t*>(mpBuffer->map());

    for (uint32_t z = 0; z < mDepth; z++)
    {
        const uint8_t* pSrcZ = pSrc + z * (size_t)mRowSize * mRowCount;
        uint8_t* pDstZ = pDst + z * (size_t)mActualRowSize * mRowCount;
        for (uint32_t y = 0; y < mRowCount; y++)
        {
            const uint8_t* pSrcY = pSrcZ + y * (size_t)mRowSize;
            uint8_t* pDstY = pDstZ + y * (size_t)mActualRowSize;
            std::memcpy(pDstY, pSrcY, mActualRowSize);
        }
    }

    mpBuffer->unmap();
}

std::vector<uint8_t> CopyContext::ReadTextureTask::getData() const
{
    std::vector<uint8_t> result(size_t(mRowCount) * mActualRowSize * mDepth);
    getData(result.data(), result.size());
    return result;
}

CopyContext::ReadBufferTask::SharedPtr CopyContext::ReadBufferTask::create(
    CopyContext* context, const Buffer* buffer, size_t offset, size_t size, uint64_t maxStagingBytes)
{
    FALCOR_CHECK(context && buffer && context->getDevice() == buffer->getDevice(),
        "Asynchronous readback requires a same-device buffer");
    FALCOR_CHECK(offset < buffer->getSize(), "Readback buffer offset is out of range");
    if (size == 0) size = buffer->getSize() - offset;
    FALCOR_CHECK(size <= buffer->getSize() - offset, "Readback buffer size is out of range");
    FALCOR_CHECK(size <= maxStagingBytes, "Readback exceeds staging byte budget");
    auto task = SharedPtr(new ReadBufferTask);
    task->mpBuffer = context->getDevice()->createBuffer(size, ResourceBindFlags::None, MemoryType::ReadBack);
    context->copyBufferRegion(task->mpBuffer.get(), 0, buffer, offset, size);
    task->mpFence = context->getDevice()->createFence();
    task->mpFence->breakStrongReferenceToDevice();
    context->submit(false);
    context->signal(task->mpFence.get());
    return task;
}

CopyContext::ReadBufferTask::~ReadBufferTask()
{
    // Match texture tasks, including the last staging-buffer owner of Device.
    // No task wait/poll/map/submit, and no reference cycle back to the task.
    if (mpBuffer && mpFence)
        mpBuffer->getDevice()->releaseResource(mpFence->getGfxFence());
}

bool CopyContext::ReadBufferTask::isReady() const
{
    return mpFence->getCurrentValue() >= mpFence->getSignaledValue();
}

std::vector<uint8_t> CopyContext::ReadBufferTask::getDataNonBlocking() const
{
    FALCOR_CHECK(isReady(), "Readback is not ready");
    std::vector<uint8_t> result(getDataSize());
    std::memcpy(result.data(), mpBuffer->map(), result.size());
    mpBuffer->unmap();
    return result;
}

bool CopyContext::textureBarrier(const Texture* pTexture, Resource::State newState)
{
    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();
    bool recorded = false;
    if (pTexture->getGlobalState() != newState)
    {
        gfx::ITextureResource* textureResource = pTexture->getGfxTextureResource();
        resourceEncoder->textureBarrier(
            1, &textureResource, getGFXResourceState(pTexture->getGlobalState()), getGFXResourceState(newState)
        );
        mCommandsPending = true;
        recorded = true;
    }
    pTexture->setGlobalState(newState);
    return recorded;
}

bool CopyContext::bufferBarrier(const Buffer* pBuffer, Resource::State newState)
{
    FALCOR_ASSERT(pBuffer);
    if (pBuffer->getMemoryType() != MemoryType::DeviceLocal)
        return false;
#if FALCOR_HAS_D3D12
    if (mpDevice->getType() == Device::Type::D3D12)
        newState = getD3D12BufferReadState(pBuffer, newState);
#endif
    bool recorded = false;
    const auto oldState = pBuffer->getGlobalState();
    if (oldState != newState)
    {
        // End any active render encoder before recording a transition on its native command list.
        auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();
#if FALCOR_HAS_D3D12
        if (mpDevice->getType() == Device::Type::D3D12 &&
            (oldState == Resource::State::GenericRead || newState == Resource::State::GenericRead))
        {
            D3D12_RESOURCE_BARRIER barrier = {};
            barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
            barrier.Transition.pResource = pBuffer->getNativeHandle().as<ID3D12Resource*>();
            barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
            barrier.Transition.StateBefore = getD3D12ResourceState(oldState, true);
            barrier.Transition.StateAfter = getD3D12ResourceState(newState, true);
            getLowLevelData()->getCommandBufferNativeHandle().as<ID3D12GraphicsCommandList*>()->ResourceBarrier(1, &barrier);
        }
        else
#endif
        {
            gfx::IBufferResource* bufferResource = pBuffer->getGfxBufferResource();
            auto destinationScope = getGFXResourceState(newState);
            if (mpDevice->getType() == Device::Type::Vulkan &&
                oldState == Resource::State::CopyDest && newState == Resource::State::CopySource)
            {
                // Some Vulkan drivers lose transfer-read visibility when a
                // buffer upload and its first readback straddle an image copy.
                // Widen only this RAW destination stage/access scope via native GFX;
                // no extra submit/wait, and no image layout/state change.
                // Keep logical CopySource below for subsequent real accesses.
                destinationScope = gfx::ResourceState::General;
            }
            resourceEncoder->bufferBarrier(1, &bufferResource, getGFXResourceState(oldState), destinationScope);
        }
        pBuffer->setGlobalState(newState);
        mCommandsPending = true;
        recorded = true;
    }
    return recorded;
}

void CopyContext::apiSubresourceBarrier(
    const Texture* pTexture,
    Resource::State newState,
    Resource::State oldState,
    uint32_t arraySlice,
    uint32_t mipLevel
)
{
    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();
    auto subresourceState = pTexture->getSubresourceState(arraySlice, mipLevel);
    if (subresourceState != newState)
    {
#if FALCOR_HAS_D3D12
        if (mpDevice->getType() == Device::Type::D3D12 && pTexture->getType() == Resource::Type::TextureCube &&
            isStencilFormat(pTexture->getFormat()))
        {
            // GFX's D3D12 Cube subresource barrier uses the cube count for the
            // plane stride, not the physical face count. Transition the depth
            // and stencil of this one face/mip using native subresource indices.
            D3D12_RESOURCE_BARRIER barriers[2] = {};
            const uint32_t base = pTexture->getSubresourceIndex(arraySlice, mipLevel);
            const uint32_t planeStride = pTexture->getMipCount() * pTexture->getArrayLayerCount();
            for (uint32_t plane = 0; plane < 2; ++plane)
            {
                auto& barrier = barriers[plane];
                barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
                barrier.Transition.pResource = pTexture->getNativeHandle().as<ID3D12Resource*>();
                barrier.Transition.Subresource = base + plane * planeStride;
                barrier.Transition.StateBefore = getD3D12ResourceState(subresourceState, false);
                barrier.Transition.StateAfter = getD3D12ResourceState(newState, false);
            }
            getLowLevelData()->getCommandBufferNativeHandle().as<ID3D12GraphicsCommandList*>()->ResourceBarrier(2, barriers);
            mCommandsPending = true;
            return;
        }
#endif
        gfx::ITextureResource* textureResource = pTexture->getGfxTextureResource();
        gfx::SubresourceRange subresourceRange = {};
        if (isStencilFormat(pTexture->getFormat())) subresourceRange.aspectMask = gfx::TextureAspect::DepthStencil;
        else if (isDepthStencilFormat(pTexture->getFormat())) subresourceRange.aspectMask = gfx::TextureAspect::Depth;
        subresourceRange.baseArrayLayer = arraySlice;
        subresourceRange.mipLevel = mipLevel;
        subresourceRange.layerCount = 1;
        subresourceRange.mipLevelCount = 1;
        resourceEncoder->textureSubresourceBarrier(
            textureResource, subresourceRange, getGFXResourceState(subresourceState), getGFXResourceState(newState)
        );
        mCommandsPending = true;
    }
}

void CopyContext::uavBarrier(const Resource* pResource)
{
    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();

    if (pResource->getType() == Resource::Type::Buffer)
    {
        gfx::IBufferResource* bufferResource = static_cast<gfx::IBufferResource*>(pResource->getGfxResource());
        resourceEncoder->bufferBarrier(1, &bufferResource, gfx::ResourceState::UnorderedAccess, gfx::ResourceState::UnorderedAccess);
    }
    else
    {
        gfx::ITextureResource* textureResource = static_cast<gfx::ITextureResource*>(pResource->getGfxResource());
        const auto pTexture = static_cast<const Texture*>(pResource);
        if (mpDevice->getType() == Device::Type::Vulkan && !pTexture->isStateGlobal())
        {
            // A whole-image GENERAL barrier would also change the layouts of read-only mips.
            // D3D12 UAV barriers below are resource-wide memory barriers with no layout transition.
            for (uint32_t layer = 0; layer < pTexture->getArrayLayerCount(); ++layer)
            {
                for (uint32_t mip = 0; mip < pTexture->getMipCount(); ++mip)
                {
                    if (pTexture->getSubresourceState(layer, mip) != Resource::State::UnorderedAccess)
                        continue;
                    gfx::SubresourceRange range = {};
                    range.baseArrayLayer = layer;
                    range.layerCount = 1;
                    range.mipLevel = mip;
                    range.mipLevelCount = 1;
                    resourceEncoder->textureSubresourceBarrier(
                        textureResource, range, gfx::ResourceState::UnorderedAccess, gfx::ResourceState::UnorderedAccess
                    );
                }
            }
        }
        else
            resourceEncoder->textureBarrier(1, &textureResource, gfx::ResourceState::UnorderedAccess, gfx::ResourceState::UnorderedAccess);
    }
    mCommandsPending = true;
}

void CopyContext::copyResource(const Resource* pDst, const Resource* pSrc)
{
    // Copy from texture to texture or from buffer to buffer.
    FALCOR_ASSERT(pDst->getType() == pSrc->getType());

    resourceBarrier(pDst, Resource::State::CopyDest);
    resourceBarrier(pSrc, Resource::State::CopySource);

    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();

    if (pDst->getType() == Resource::Type::Buffer)
    {
        const Buffer* pSrcBuffer = static_cast<const Buffer*>(pSrc);
        const Buffer* pDstBuffer = static_cast<const Buffer*>(pDst);

        FALCOR_ASSERT(pSrcBuffer->getSize() <= pDstBuffer->getSize());

        resourceEncoder->copyBuffer(pDstBuffer->getGfxBufferResource(), 0, pSrcBuffer->getGfxBufferResource(), 0, pSrcBuffer->getSize());
    }
    else
    {
        const Texture* pSrcTexture = static_cast<const Texture*>(pSrc);
        const Texture* pDstTexture = static_cast<const Texture*>(pDst);
        gfx::SubresourceRange subresourceRange = {};
        resourceEncoder->copyTexture(
            pDstTexture->getGfxTextureResource(),
            gfx::ResourceState::CopyDestination,
            subresourceRange,
            gfx::ITextureResource::Offset3D(0, 0, 0),
            pSrcTexture->getGfxTextureResource(),
            gfx::ResourceState::CopySource,
            subresourceRange,
            gfx::ITextureResource::Offset3D(0, 0, 0),
            gfx::ITextureResource::Extents{0, 0, 0}
        );
    }
    mCommandsPending = true;
}

void CopyContext::copySubresource(const Texture* pDst, uint32_t dstSubresourceIdx, const Texture* pSrc, uint32_t srcSubresourceIdx)
{
    copySubresourceRegion(pDst, dstSubresourceIdx, pSrc, srcSubresourceIdx, uint3(0), uint3(0), uint3(-1));
}

void CopyContext::updateBuffer(const Buffer* pBuffer, const void* pData, size_t offset, size_t numBytes)
{
    if (numBytes == 0)
    {
        numBytes = pBuffer->getSize() - offset;
    }

    if (pBuffer->adjustSizeOffsetParams(numBytes, offset) == false)
    {
        logWarning("CopyContext::updateBuffer() - size and offset are invalid. Nothing to update.");
        return;
    }

    bufferBarrier(pBuffer, Resource::State::CopyDest);
    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();
    resourceEncoder->uploadBufferData(pBuffer->getGfxBufferResource(), offset, numBytes, (void*)pData);

    mCommandsPending = true;
}

void CopyContext::readBuffer(const Buffer* pBuffer, void* pData, size_t offset, size_t numBytes)
{
    if (numBytes == 0)
        numBytes = pBuffer->getSize() - offset;

    if (pBuffer->adjustSizeOffsetParams(numBytes, offset) == false)
    {
        logWarning("CopyContext::readBuffer() - size and offset are invalid. Nothing to read.");
        return;
    }

    const auto& pReadBackHeap = mpDevice->getReadBackHeap();

    auto allocation = pReadBackHeap->allocate(numBytes);

    bufferBarrier(pBuffer, Resource::State::CopySource);

    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();
    resourceEncoder->copyBuffer(allocation.gfxBufferResource, allocation.offset, pBuffer->getGfxBufferResource(), offset, numBytes);
    mCommandsPending = true;
    submit(true);

    std::memcpy(pData, allocation.pData, numBytes);

    pReadBackHeap->release(allocation);
}

void CopyContext::copyBufferRegion(const Buffer* pDst, uint64_t dstOffset, const Buffer* pSrc, uint64_t srcOffset, uint64_t numBytes)
{
    resourceBarrier(pDst, Resource::State::CopyDest);
    resourceBarrier(pSrc, Resource::State::CopySource);

    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();
    resourceEncoder->copyBuffer(pDst->getGfxBufferResource(), dstOffset, pSrc->getGfxBufferResource(), srcOffset, numBytes);
    mCommandsPending = true;
}

void CopyContext::copySubresourceRegion(
    const Texture* pDst,
    uint32_t dstSubresourceIdx,
    const Texture* pSrc,
    uint32_t srcSubresourceIdx,
    const uint3& dstOffset,
    const uint3& srcOffset,
    const uint3& size
)
{
    resourceBarrier(pDst, Resource::State::CopyDest);
    resourceBarrier(pSrc, Resource::State::CopySource);

    gfx::SubresourceRange dstSubresource = {};
    dstSubresource.baseArrayLayer = pDst->getSubresourceArraySlice(dstSubresourceIdx);
    dstSubresource.layerCount = 1;
    dstSubresource.mipLevel = pDst->getSubresourceMipLevel(dstSubresourceIdx);
    dstSubresource.mipLevelCount = 1;

    gfx::SubresourceRange srcSubresource = {};
    srcSubresource.baseArrayLayer = pSrc->getSubresourceArraySlice(srcSubresourceIdx);
    srcSubresource.layerCount = 1;
    srcSubresource.mipLevel = pSrc->getSubresourceMipLevel(srcSubresourceIdx);
    srcSubresource.mipLevelCount = 1;

    gfx::ITextureResource::Extents copySize = {(int)size.x, (int)size.y, (int)size.z};

    if (size.x == uint(-1))
    {
        copySize.width = pSrc->getWidth(srcSubresource.mipLevel) - srcOffset.x;
        copySize.height = pSrc->getHeight(srcSubresource.mipLevel) - srcOffset.y;
        copySize.depth = pSrc->getDepth(srcSubresource.mipLevel) - srcOffset.z;
    }

    auto resourceEncoder = getLowLevelData()->getResourceCommandEncoder();
    resourceEncoder->copyTexture(
        pDst->getGfxTextureResource(),
        gfx::ResourceState::CopyDestination,
        dstSubresource,
        gfx::ITextureResource::Offset3D(dstOffset.x, dstOffset.y, dstOffset.z),
        pSrc->getGfxTextureResource(),
        gfx::ResourceState::CopySource,
        srcSubresource,
        gfx::ITextureResource::Offset3D(srcOffset.x, srcOffset.y, srcOffset.z),
        copySize
    );
    mCommandsPending = true;
}

void CopyContext::addAftermathMarker(std::string_view name)
{
#if FALCOR_HAS_AFTERMATH
    if (AftermathContext* pAftermathContext = mpDevice->getAftermathContext())
        pAftermathContext->addMarker(mpLowLevelData.get(), name);
#endif
};

} // namespace Falcor
