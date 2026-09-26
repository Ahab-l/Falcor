#include "Testing/UnitTest.h"
#include "RenderGraph/RenderPassReflection.h"
#include "RenderGraph/RenderGraph.h"
#include "RenderGraph/ResourceCache.h"

namespace Falcor
{
CPU_TEST(RenderGraphStructuredBufferReflection)
{
    using Field = RenderPassReflection::Field;
    Field field("values", "", Field::Visibility::Output);
    field.structuredBuffer(16, 8);
    EXPECT_EQ(uint32_t(field.getType()), uint32_t(Field::Type::StructuredBuffer));
    EXPECT_EQ(field.getWidth(), 128u);
    EXPECT_EQ(field.getStructSize(), 16u);
    EXPECT_TRUE(field.isValid());

    auto same = field;
    same.visibility(Field::Visibility::Input);
    field.merge(same);
    auto differentStride = same;
    differentStride.structuredBuffer(8, 16);
    EXPECT_TRUE(field != differentStride);
    EXPECT_THROW(field.merge(differentStride));
    auto differentCount = same;
    differentCount.structuredBuffer(16, 7);
    EXPECT_THROW(field.merge(differentCount));
    auto raw = same;
    raw.rawBuffer(128);
    EXPECT_EQ(raw.getStructSize(), 0u);
    EXPECT_THROW(field.merge(raw));
    EXPECT_THROW(raw.merge(field));
    auto texture = same;
    texture.texture2D(8, 1);
    EXPECT_EQ(texture.getStructSize(), 0u);
    auto generic = same;
    generic.resourceType(Field::Type::StructuredBuffer, 128, 0, 0, 0, 0, 0, 16);
    EXPECT_EQ(generic.getStructSize(), 16u);
    EXPECT_EQ(generic.getWidth(), 128u);
}

CPU_TEST(RenderGraphStructuredBufferInvalidShape)
{
    RenderPassReflection::Field field("values", "", RenderPassReflection::Field::Visibility::Output);
    EXPECT_THROW(field.structuredBuffer(0, 8));
    EXPECT_THROW(field.structuredBuffer(14, 8));
    EXPECT_THROW(field.structuredBuffer(16, 0));
    EXPECT_THROW(field.structuredBuffer(16, 0x10000000u));
    EXPECT_THROW(field.structuredBuffer(0xfffffffcu, 2));
    EXPECT_THROW(field.resourceType(RenderPassReflection::Field::Type::StructuredBuffer, 127, 0, 0, 0, 0, 0, 16));
    EXPECT_THROW(field.resourceType(RenderPassReflection::Field::Type::StructuredBuffer, 128, 0, 0, 0, 0, 0));
}

GPU_TEST(RenderGraphStructuredBufferAllocation, Device::Type::D3D12)
{
    using Field = RenderPassReflection::Field;
    Field structured("values", "", Field::Visibility::Output);
    structured.structuredBuffer(16, 8);
    Field raw("raw", "", Field::Visibility::Output);
    raw.rawBuffer(128);
    ResourceCache cache;
    cache.registerField("Write.values", structured, 0);
    cache.registerField("Read.values", structured, 1, "Write.values");
    cache.registerField("Write.raw", raw, 0);
    ResourceCache::DefaultProperties defaults;
    defaults.dims = uint2(1);
    cache.allocateResources(ctx.getDevice(), defaults);
    const auto buffer = cache.getResource("Write.values")->asBuffer();
    ASSERT_TRUE(buffer);
    EXPECT_TRUE(buffer->isStructured());
    EXPECT_EQ(buffer->getStructSize(), 16u);
    EXPECT_EQ(buffer->getElementCount(), 8u);
    EXPECT_EQ(buffer->getSize(), size_t(128));
    EXPECT_TRUE(cache.getResource("Read.values").get() == buffer.get());
    EXPECT_TRUE(is_set(buffer->getBindFlags(), ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess));
    EXPECT_FALSE(cache.getResource("Write.raw")->asBuffer()->isStructured());
}

namespace
{
class ExternalBufferFixture : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(ExternalBufferFixture, "ExternalBufferFixture", "External buffer reflection fixture");
    ExternalBufferFixture(ref<Device> device, bool structured) : RenderPass(device), mStructured(structured) {}
    RenderPassReflection reflect(const CompileData&) override
    {
        RenderPassReflection result;
        auto& input = result.addInput("values", "External buffer").bindFlags(ResourceBindFlags::ShaderResource);
        if (mStructured) input.structuredBuffer(16, 8);
        else input.rawBuffer(128);
        result.addOutput("result", "Keeps the fixture live").rawBuffer(4);
        return result;
    }
    void execute(RenderContext*, const RenderData&) override {}
private:
    bool mStructured;
};
}

GPU_TEST(RenderGraphStructuredBufferExternalReflection, Device::Type::D3D12)
{
    const auto device = ctx.getDevice();
    const auto srv = ResourceBindFlags::ShaderResource;
    const auto uav = ResourceBindFlags::UnorderedAccess;
    const auto check = [&](const ref<Buffer>& buffer, bool structured, bool valid, const char* error)
    {
        auto graph = RenderGraph::create(device, "ExternalBufferReflection");
        graph->addPass(make_ref<ExternalBufferFixture>(device, structured), "Read");
        graph->markOutput("Read.result");
        graph->setInput("Read.values", buffer);
        std::string log;
        EXPECT_EQ(graph->compile(ctx.getRenderContext(), log), valid) << log;
        if (!valid) EXPECT_TRUE(log.find(error) != std::string::npos) << log;
    };
    check(device->createStructuredBuffer(16, 8, srv), true, true, "");
    check(device->createBuffer(128, srv), false, true, "");
    check(device->createStructuredBuffer(8, 16, srv), true, false, "mismatching");
    check(device->createStructuredBuffer(16, 7, srv), true, false, "mismatching");
    check(device->createBuffer(128, srv), true, false, "mismatching types");
    check(device->createStructuredBuffer(16, 8, srv), false, false, "mismatching types");
    check(device->createStructuredBuffer(16, 8, uav), true, false, "bind flags mismatch");
}
} // namespace Falcor
