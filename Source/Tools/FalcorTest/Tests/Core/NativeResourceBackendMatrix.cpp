// Finite native resource/backend contracts. These tests deliberately do not use
// the D3D12-only description-based Shader/Mesh wrappers.
#include "Testing/UnitTest.h"
#include "Core/API/GFXAPI.h"
#include "../../../../RenderPasses/customrenderpipline/CustomRenderPiplineReadback.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

namespace Falcor
{
namespace
{
const char kShader[] = "Tests/Core/NativeResourceBackendMatrix.slang";
constexpr uint32_t kFaces = 6;
constexpr uint32_t kCubeWidth = 8;
constexpr uint32_t kCubeMips = 4;
const auto kReadWrite = ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess;

void expectBytes(GPUUnitTestContext& ctx, const std::vector<uint8_t>& actual, const std::vector<uint8_t>& expected,
    const std::string& label)
{
    ASSERT_EQ(actual.size(), expected.size()) << label;
    for (size_t byte = 0; byte < expected.size(); ++byte)
        EXPECT_EQ(uint32_t(actual[byte]), uint32_t(expected[byte])) << label << ", byte " << byte;
}

template<typename Task>
bool awaitReady(const Task& task)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (!task->isReady() && std::chrono::steady_clock::now() < deadline)
        std::this_thread::sleep_for(std::chrono::milliseconds(1)); // Bounded, test-only host polling.
    return task->isReady();
}

template<typename Function>
void expectRejected(GPUUnitTestContext& ctx, Function operation, const char* reason)
{
    // Do not accept an unrelated allocation/format error as the tested boundary.
    std::string message;
    EXPECT_THROW(([&]()
    {
        try { operation(); }
        catch (const std::exception& error) { message = error.what(); throw; }
    })());
    EXPECT_TRUE(message.find(reason) != std::string::npos) << "Expected '" << reason << "', got '" << message << "'";
}

std::vector<uint8_t> knownBytes(size_t size, uint32_t seed)
{
    std::vector<uint8_t> bytes(size);
    // Every subresource has a different seed; nonuniform rows/blocks expose
    // row-padding, mip-offset, array-layer and compressed-tail mistakes.
    for (size_t i = 0; i < size; ++i)
        bytes[i] = uint8_t((seed * 53u + uint32_t(i) * 37u + uint32_t(i / 7) * 11u) & 0xffu);
    return bytes;
}

void expectTextureBytes(GPUUnitTestContext& ctx, const ref<Texture>& texture, uint32_t subresource,
    const std::vector<uint8_t>& expected, const std::string& label)
{
    auto context = ctx.getRenderContext();
    expectBytes(ctx, context->readTextureSubresource(texture.get(), subresource), expected, label + " sync");
    const auto task = context->asyncReadTextureSubresource(texture.get(), subresource);
    EXPECT_EQ(task->getDataSize(), expected.size()) << label;
    EXPECT_GE(task->getStagingSize(), task->getDataSize()) << label;
    ASSERT_TRUE(awaitReady(task)) << label;
    expectBytes(ctx, task->getDataNonBlocking(), expected, label + " async");
    expectBytes(ctx, task->getDataNonBlocking(), expected, label + " repeated async");
}

void expectColorRecovery(GPUUnitTestContext& ctx, uint32_t seed)
{
    const auto expected = knownBytes(5 * 3 * 4, seed);
    const auto valid = ctx.getDevice()->createTexture2D(5, 3, ResourceFormat::RGBA8Unorm, 1, 1, expected.data());
    expectTextureBytes(ctx, valid, 0, expected, "valid color after rejection");
}

struct FormatCase
{
    const char* name;
    ResourceFormat format;
    uint32_t blockWidth;
    uint32_t blockHeight;
    uint32_t blockBytes;
};

void testTextureBytes(GPUUnitTestContext& ctx, const FormatCase& format, uint32_t width, uint32_t height, uint32_t layers)
{
    constexpr uint32_t mips = 4;
    std::vector<std::vector<uint8_t>> expected;
    std::vector<uint8_t> initial;
    for (uint32_t layer = 0; layer < layers; ++layer)
        for (uint32_t mip = 0; mip < mips; ++mip)
        {
            const uint32_t w = std::max(1u, width >> mip);
            const uint32_t h = std::max(1u, height >> mip);
            // The test table supplies independent physical block dimensions,
            // rather than using the production footprint to predict itself.
            const size_t size = size_t((w + format.blockWidth - 1) / format.blockWidth) *
                ((h + format.blockHeight - 1) / format.blockHeight) * format.blockBytes;
            expected.push_back(knownBytes(size, 1 + layer * mips + mip));
            initial.insert(initial.end(), expected.back().begin(), expected.back().end());
        }

    auto context = ctx.getRenderContext();
    const auto texture = ctx.getDevice()->createTexture2D(width, height, format.format, layers, mips, initial.data());
    ASSERT_EQ(texture->getSubresourceCount(), layers * mips);
    EXPECT_EQ(texture->getArrayLayerCount(), layers);
    context->resourceBarrier(texture.get(), Resource::State::ShaderResource);
    const auto tailView = texture->getSRV(mips - 1, 1, layers - 1, 1);
    context->resourceBarrier(texture.get(), Resource::State::CopySource, &tailView->getViewInfo());
    ASSERT_FALSE(texture->isStateGlobal());
    const uint32_t tail = texture->getSubresourceIndex(layers - 1, mips - 1);
    // Vulkan can stage the R8 1x1 tail in exactly one byte, so budget=1 is
    // valid there. Mip 2 is at least 3 raw bytes for the color table (13>>2)
    // and one 8/16-byte block for BC, independently of backend row alignment.
    const uint32_t budgetSubresource = texture->getSubresourceIndex(layers - 1, mips - 2);
    ASSERT_GT(expected[budgetSubresource].size(), size_t(1));
    expectRejected(ctx, [&] { context->asyncReadTextureSubresource(texture.get(), budgetSubresource, 1); }, "staging byte budget");
    EXPECT_FALSE(texture->isStateGlobal()) << "Rejected budget must not collapse the mixed state tracker";
    for (uint32_t layer = 0; layer < layers; ++layer)
        for (uint32_t mip = 0; mip < mips; ++mip)
            EXPECT_EQ(uint32_t(texture->getSubresourceState(layer, mip)), uint32_t(
                layer == layers - 1 && mip == mips - 1 ? Resource::State::CopySource : Resource::State::ShaderResource));

    for (uint32_t layer = 0; layer < layers; ++layer)
        for (uint32_t mip = 0; mip < mips; ++mip)
        {
            const uint32_t subresource = layer * mips + mip;
            const std::string label = std::string(format.name) + " layer " + std::to_string(layer) + " mip " + std::to_string(mip);
            EXPECT_EQ(texture->getWidth(mip), std::max(1u, width >> mip)) << label;
            EXPECT_EQ(texture->getHeight(mip), std::max(1u, height >> mip)) << label;
            EXPECT_EQ(texture->getSubresourceIndex(layer, mip), subresource) << label;
            EXPECT_EQ(texture->getSubresourceArraySlice(subresource), layer) << label;
            EXPECT_EQ(texture->getSubresourceMipLevel(subresource), mip) << label;
            expectTextureBytes(ctx, texture, subresource, expected[subresource], label);
        }
    EXPECT_TRUE(texture->isStateGlobal());
    EXPECT_EQ(uint32_t(texture->getGlobalState()), uint32_t(Resource::State::CopySource));

    // Snapshot before overwriting the smallest physical mip. A new upload and
    // subsequent reads must preserve every neighboring layer/mip.
    const auto snapshot = context->asyncReadTextureSubresource(texture.get(), tail);
    const auto previous = expected[tail];
    expected[tail] = knownBytes(previous.size(), 201);
    texture->setSubresourceBlob(tail, expected[tail].data(), expected[tail].size());
    context->submit(true);
    ASSERT_TRUE(snapshot->isReady());
    expectBytes(ctx, snapshot->getDataNonBlocking(), previous, std::string(format.name) + " pre-overwrite snapshot");
    for (uint32_t subresource = 0; subresource < texture->getSubresourceCount(); ++subresource)
        expectBytes(ctx, context->readTextureSubresource(texture.get(), subresource), expected[subresource],
            std::string(format.name) + " after tail update, subresource " + std::to_string(subresource));
}

float cubeValue(uint32_t physicalFace, uint32_t mip)
{
    return float(1000 + physicalFace * 32 + mip * 3);
}

std::vector<float> cubeInitialData(uint32_t cubes)
{
    std::vector<float> data;
    for (uint32_t face = 0; face < cubes * kFaces; ++face)
        for (uint32_t mip = 0; mip < kCubeMips; ++mip)
            data.insert(data.end(), (kCubeWidth >> mip) * (kCubeWidth >> mip), cubeValue(face, mip));
    return data;
}

void expectCubeSamples(GPUUnitTestContext& ctx, const ref<Texture>& texture)
{
    const uint32_t cubes = texture->getArraySize();
    ctx.createProgram(kShader, cubes == 1 ? "sampleCube" : "sampleCubeArray");
    ctx.allocateStructuredBuffer("gResult", cubes * kFaces);
    ctx["gPoint"] = ctx.getDevice()->createSampler(Sampler::Desc().setFilterMode(
        TextureFilteringMode::Point, TextureFilteringMode::Point, TextureFilteringMode::Point));
    const char* input = cubes == 1 ? "gCube" : "gCubeArray";
    for (uint32_t mip = 0; mip < kCubeMips; ++mip)
        for (bool rebased : {false, true})
        {
            const auto view = rebased ? texture->getSRV(mip, 1, 0, cubes * kFaces) : texture->getSRV();
            EXPECT_EQ(view->getViewInfo().arraySize, cubes * kFaces);
            EXPECT_EQ(view->getGfxResourceView()->getViewDesc()->subresourceRange.layerCount, cubes * kFaces);
            EXPECT_EQ(view->getViewInfo().mostDetailedMip, rebased ? mip : 0u);
            EXPECT_EQ(view->getViewInfo().mipCount, rebased ? 1u : kCubeMips);
            ctx[input].setSrv(view);
            ctx["gSampleMip"] = rebased ? 0u : mip;
            ctx.runProgram(cubes * kFaces);
            const auto values = ctx.readBuffer<float>("gResult");
            ASSERT_EQ(values.size(), size_t(cubes * kFaces));
            for (uint32_t face = 0; face < cubes * kFaces; ++face)
                EXPECT_EQ(values[face], cubeValue(face, mip))
                    << "physical face " << face << ", mip " << mip << ", rebased " << rebased;
        }
    if (cubes == 2)
    {
        // A complete cube beginning at physical face six is a valid slice of
        // the array. The shader-visible array index is rebased to zero.
        ctx.allocateStructuredBuffer("gResult", kFaces);
        for (uint32_t mip = 0; mip < kCubeMips; ++mip)
        {
            const auto view = texture->getSRV(mip, 1, kFaces, kFaces);
            EXPECT_EQ(view->getViewInfo().firstArraySlice, kFaces);
            EXPECT_EQ(view->getGfxResourceView()->getViewDesc()->subresourceRange.baseArrayLayer, kFaces);
            ctx["gCubeArray"].setSrv(view);
            ctx["gSampleMip"] = 0u;
            ctx.runProgram(kFaces);
            const auto values = ctx.readBuffer<float>("gResult");
            ASSERT_EQ(values.size(), size_t(kFaces));
            for (uint32_t face = 0; face < kFaces; ++face)
                EXPECT_EQ(values[face], cubeValue(kFaces + face, mip)) << "second-cube view, face " << face << ", mip " << mip;
        }
    }
}
} // namespace

GPU_TEST(NativeResourceBackendColorArrayMipBytes)
{
    const std::array<FormatCase, 5> formats = {{
        {"R8Unorm", ResourceFormat::R8Unorm, 1, 1, 1},
        {"RGBA8Unorm", ResourceFormat::RGBA8Unorm, 1, 1, 4},
        {"R32Uint", ResourceFormat::R32Uint, 1, 1, 4},
        {"RG16Float", ResourceFormat::RG16Float, 1, 1, 4},
        {"RGBA32Uint", ResourceFormat::RGBA32Uint, 1, 1, 16},
    }};
    for (const auto& format : formats)
        for (uint32_t layers : {1u, 3u})
            testTextureBytes(ctx, format, 13, 7, layers);
}

GPU_TEST(NativeResourceBackendBCTailMipBytes)
{
    const std::array<FormatCase, 4> formats = {{
        {"BC1Unorm", ResourceFormat::BC1Unorm, 4, 4, 8},
        {"BC3Unorm", ResourceFormat::BC3Unorm, 4, 4, 16},
        {"BC4Unorm", ResourceFormat::BC4Unorm, 4, 4, 8},
        {"BC5Unorm", ResourceFormat::BC5Unorm, 4, 4, 16},
    }};
    // 8x8, 4x4, 2x2, 1x1: both tails still occupy a complete physical block.
    for (const auto& format : formats)
        testTextureBytes(ctx, format, 8, 8, 2);
}

GPU_TEST(NativeResourceBackendBufferBytesAndRecovery)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    const auto expected = knownBytes(96, 47);
    const std::array<ref<Buffer>, 4> buffers = {{
        device->createBuffer(expected.size(), kReadWrite, MemoryType::DeviceLocal, expected.data()),
        device->createTypedBuffer(ResourceFormat::R32Uint, 24, kReadWrite, MemoryType::DeviceLocal, expected.data()),
        device->createTypedBuffer(ResourceFormat::RGBA32Uint, 6, kReadWrite, MemoryType::DeviceLocal, expected.data()),
        device->createStructuredBuffer(12, 8, kReadWrite, MemoryType::DeviceLocal, expected.data()),
    }};
    for (size_t kind = 0; kind < buffers.size(); ++kind)
    {
        const auto& buffer = buffers[kind];
        std::vector<uint8_t> actual(expected.size());
        buffer->getBlob(actual.data(), 0, actual.size());
        expectBytes(ctx, actual, expected, "buffer initial bytes " + std::to_string(kind));
        context->resourceBarrier(buffer.get(), Resource::State::ShaderResource);
        expectRejected(ctx, [&] { context->asyncReadBuffer(buffer.get(), 4, 20, 19); }, "staging byte budget");
        EXPECT_EQ(uint32_t(buffer->getGlobalState()), uint32_t(Resource::State::ShaderResource));
        const auto task = context->asyncReadBuffer(buffer.get(), 4, 20, 20);
        EXPECT_EQ(task->getDataSize(), size_t(20));
        const auto replacement = knownBytes(expected.size(), 91);
        buffer->setBlob(replacement.data(), 0, replacement.size());
        context->submit(true);
        ASSERT_TRUE(task->isReady());
        expectBytes(ctx, task->getDataNonBlocking(), std::vector<uint8_t>(expected.begin() + 4, expected.begin() + 24),
            "buffer pre-overwrite snapshot " + std::to_string(kind));
        const auto valid = context->asyncReadBuffer(buffer.get(), 0, replacement.size());
        ASSERT_TRUE(awaitReady(valid));
        expectBytes(ctx, valid->getDataNonBlocking(), replacement, "valid buffer after rejection and update " + std::to_string(kind));
        buffer->getBlob(actual.data(), 0, actual.size());
        expectBytes(ctx, actual, replacement, "buffer updated sync bytes " + std::to_string(kind));
    }
}

GPU_TEST(NativeResourceBackendCubeSrvFacesMips)
{
    for (uint32_t cubes : {1u, 2u})
    {
        const auto initial = cubeInitialData(cubes);
        const auto texture = ctx.getDevice()->createTextureCube(
            kCubeWidth, kCubeWidth, ResourceFormat::R32Float, cubes, kCubeMips, initial.data(), ResourceBindFlags::ShaderResource);
        EXPECT_EQ(texture->getArraySize(), cubes);
        EXPECT_EQ(texture->getArrayLayerCount(), cubes * kFaces);
        ASSERT_EQ(texture->getSubresourceCount(), cubes * kFaces * kCubeMips);
        for (uint32_t face = 0; face < cubes * kFaces; ++face)
            for (uint32_t mip = 0; mip < kCubeMips; ++mip)
            {
                const uint32_t width = kCubeWidth >> mip;
                const std::vector<float> values(width * width, cubeValue(face, mip));
                std::vector<uint8_t> bytes(values.size() * sizeof(float));
                std::memcpy(bytes.data(), values.data(), bytes.size());
                EXPECT_EQ(texture->getSubresourceIndex(face, mip), face * kCubeMips + mip);
                expectTextureBytes(ctx, texture, face * kCubeMips + mip, bytes,
                    "initialized cube face " + std::to_string(face) + " mip " + std::to_string(mip));
            }
        expectRejected(ctx, [&] { texture->getSRV(0, 1, 1, 6); }, "Cube SRVs must start");
        expectRejected(ctx, [&] { texture->getSRV(0, 1, 0, 5); }, "complete groups of six faces");
        expectRejected(ctx, [&] { ShaderResourceView::create(ctx.getDevice().get(), texture.get(), 0, 1, 0, 5); },
            "aligned, complete groups of six faces");
        // The next valid binding must still work after all rejected cached and direct views.
        expectCubeSamples(ctx, texture);
    }
}

GPU_TEST(NativeResourceBackendMSAARawReadbackRejected)
{
    const auto texture = ctx.getDevice()->createTexture2DMS(
        8, 8, ResourceFormat::RGBA8Unorm, 4, 1, ResourceBindFlags::RenderTarget);
    ASSERT_EQ(texture->getSampleCount(), 4u);
    auto context = ctx.getRenderContext();
    context->clearRtv(texture->getRTV().get(), float4(0.25f, 0.5f, 0.75f, 1.f));
    const auto state = texture->getGlobalState();
    expectRejected(ctx, [&] { context->readTextureSubresource(texture.get(), 0); }, "valid single-sample subresource");
    EXPECT_EQ(uint32_t(texture->getGlobalState()), uint32_t(state));
    expectColorRecovery(ctx, 17);
    expectRejected(ctx, [&] { context->asyncReadTextureSubresource(texture.get(), 0); }, "valid single-sample subresource");
    EXPECT_EQ(uint32_t(texture->getGlobalState()), uint32_t(state));
    expectColorRecovery(ctx, 18);
}

GPU_TEST(NativeResourceBackendVulkanCubeViewsRejected, Device::Type::Vulkan)
{
    const auto initial = cubeInitialData(1);
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    const auto cube = device->createTextureCube(kCubeWidth, kCubeWidth, ResourceFormat::R32Float, 1, kCubeMips,
        initial.data(), kReadWrite | ResourceBindFlags::RenderTarget);
    const auto depthCube = device->createTextureCube(
        kCubeWidth, kCubeWidth, ResourceFormat::D32Float, 1, 1, nullptr, ResourceBindFlags::DepthStencil);
    expectRejected(ctx, [&] { cube->getRTV(1, 5, 1); }, "Cube RTVs are unsupported");
    expectColorRecovery(ctx, 101);
    expectRejected(ctx, [&] { cube->getUAV(1, 5, 1); }, "Cube UAVs require a Texture2DArray view");
    expectColorRecovery(ctx, 102);
    expectRejected(ctx, [&] { depthCube->getDSV(0, 5, 1); }, "Cube DSVs are unsupported");
    expectColorRecovery(ctx, 103);
    expectRejected(ctx, [&] { cube->generateMips(context); }, "generateMips() does not support cube textures");
    expectColorRecovery(ctx, 104);
    expectRejected(ctx, [&] { device->createTextureCube(kCubeWidth, kCubeWidth, ResourceFormat::R32Float,
        1, Texture::kMaxPossible, initial.data(), ResourceBindFlags::ShaderResource); }, "Automatic cube mip generation is unsupported");
    expectCubeSamples(ctx, cube);

    // The corresponding native 2D-array UAV/RTV operations are supported, not
    // reclassified as unsupported along with cube views. Verify the final pixels.
    const auto array = device->createTexture2D(kCubeWidth, kCubeWidth, ResourceFormat::R32Float, kFaces, kCubeMips,
        initial.data(), kReadWrite | ResourceBindFlags::RenderTarget);
    ctx.createProgram(kShader, "writeArrayFace");
    ctx.allocateStructuredBuffer("gResult", 16);
    ctx["gArrayWrite"].setUav(array->getUAV(1, 5, 1));
    ctx.runProgram(4, 4);
    ASSERT_FALSE(array->isStateGlobal());
    // Repeated dispatch before a submit reaches the Vulkan mixed-state UAV
    // ordering barrier; unrelated mips must retain their copy-destination layout.
    ctx.runProgram(4, 4);
    for (uint32_t face = 0; face < kFaces; ++face)
        for (uint32_t mip = 0; mip < kCubeMips; ++mip)
            EXPECT_EQ(uint32_t(array->getSubresourceState(face, mip)), uint32_t(
                face == 5 && mip == 1 ? Resource::State::UnorderedAccess : Resource::State::CopyDest));
    std::vector<float> values(16, 777.f);
    std::vector<uint8_t> bytes(values.size() * sizeof(float));
    std::memcpy(bytes.data(), values.data(), bytes.size());
    expectTextureBytes(ctx, array, array->getSubresourceIndex(5, 1), bytes, "2D-array UAV after cube rejection");
    context->clearRtv(array->getRTV(1, 5, 1).get(), float4(888.f));
    std::fill(values.begin(), values.end(), 888.f);
    std::memcpy(bytes.data(), values.data(), bytes.size());
    expectTextureBytes(ctx, array, array->getSubresourceIndex(5, 1), bytes, "2D-array RTV after cube rejection");
    for (uint32_t face = 0; face < kFaces; ++face)
        for (uint32_t mip = 0; mip < kCubeMips; ++mip)
        {
            const uint32_t width = kCubeWidth >> mip;
            values.assign(width * width, face == 5 && mip == 1 ? 888.f : cubeValue(face, mip));
            bytes.resize(values.size() * sizeof(float));
            std::memcpy(bytes.data(), values.data(), bytes.size());
            expectBytes(ctx, context->readTextureSubresource(array.get(), array->getSubresourceIndex(face, mip)), bytes,
                "array neighbors after UAV/RTV, face " + std::to_string(face) + " mip " + std::to_string(mip));
        }
}

GPU_TEST(NativeResourceBackendVulkanExactDepthPlanesRejected, Device::Type::Vulkan)
{
    auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    // A genuinely valid D32S8 allocation, mip and slice reach the backend guard;
    // wrong-format/null/out-of-range failures would not establish this boundary.
    const auto depthStencil = device->createTexture2D(
        8, 8, ResourceFormat::D32FloatS8Uint, 2, 2, nullptr, ResourceBindFlags::DepthStencil);
    const auto state = depthStencil->getGlobalState();
    expectRejected(ctx, [&] { CustomRenderPipline::readDepthStencil(context, depthStencil.get(), 1, 1); }, "requires D3D12");
    EXPECT_EQ(uint32_t(depthStencil->getGlobalState()), uint32_t(state));
    expectColorRecovery(ctx, 111);
    expectRejected(ctx, [&] { CustomRenderPipline::readDepthStencilAsync(context, depthStencil.get(), 1, 1); }, "requires D3D12");
    EXPECT_EQ(uint32_t(depthStencil->getGlobalState()), uint32_t(state));
    expectColorRecovery(ctx, 112);

    // Ordinary Vulkan DSV + depth SRV remains supported. This is NOT a claim of
    // D32S8 packed/plane readback support: a separate D32Float texture is sampled.
    const auto depth = device->createTexture2D(8, 8, ResourceFormat::D32Float, 2, 2, nullptr,
        ResourceBindFlags::DepthStencil | ResourceBindFlags::ShaderResource);
    context->clearDsv(depth->getDSV(1, 1, 1).get(), 0.625f, 0, true, false);
    ctx.createProgram(kShader, "loadDepth");
    ctx.allocateStructuredBuffer("gResult", 16);
    ctx["gDepth"].setSrv(depth->getSRV(1, 1, 1, 1));
    ctx.runProgram(4, 4);
    const auto values = ctx.readBuffer<float>("gResult");
    ASSERT_EQ(values.size(), size_t(16));
    for (const auto value : values)
        EXPECT_EQ(value, 0.625f);
}
} // namespace Falcor
