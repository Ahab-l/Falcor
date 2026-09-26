#include "CustomRenderPiplineHistoryPass.h"
#include "CustomRenderPiplineShaderBindings.h"

namespace Falcor
{
namespace
{
using Json = nlohmann::json;
const auto kFlags = ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess;
struct HistoryStorage
{
    std::map<std::string, std::array<ref<Texture>, 2>> textures;
    uint2 extent = uint2(0);
    uint64_t updates = 0;
    uint32_t publishedSlot = 0;
    bool valid = false;
    void reset() { valid = false; updates = 0; publishedSlot = 0; }
};
std::string nodeOf(const std::string& port) { return port.substr(0, port.find('.')); }
}

struct CustomRenderPiplineHistoryPass::Impl
{
    Properties properties;
    bool read;
    std::string key;
    struct Resource
    {
        std::string name;
        ResourceFormat format;
        uint2 size = uint2(0);
        uint2 resolve(uint2 viewport) const { return size.x ? size : viewport; }
        bool operator==(const Resource& other) const
        { return name == other.name && format == other.format && all(size == other.size); }
    };
    std::vector<Resource> resources;
    uint2 extent = uint2(0);
    std::shared_ptr<HistoryStorage> storage;
    Impl(const Properties& p, bool r) : properties(p), read(r) {}
};

CustomRenderPiplineHistoryPass::CustomRenderPiplineHistoryPass(ref<Device> device, const Properties& props, bool read)
    : RenderPass(device), mpImpl(std::make_unique<Impl>(props, read))
{
    using CustomRenderPipline::ShaderBindings::keys;
    auto& p = *mpImpl;
    const auto o = props.toJson();
    keys(o, {"key", "resources"}, "history");
    p.key = o.at("key").get<std::string>();
    FALCOR_CHECK(std::regex_match(p.key, std::regex("[A-Za-z_][A-Za-z0-9_]*")), "Invalid history key");
    const auto& resources = o.at("resources");
    FALCOR_CHECK(resources.is_array() && !resources.empty(), "History resources must be a nonempty array");
    std::set<std::string> names;
    for (const auto& r : resources)
    {
        keys(r, {"name", "format", "size"}, "history resource");
        const auto name = r.at("name").get<std::string>();
        const auto format = stringToEnum<ResourceFormat>(r.at("format").get<std::string>());
        FALCOR_CHECK(name != "status" && std::regex_match(name, std::regex("[A-Za-z_][A-Za-z0-9_]*")) && names.insert(name).second,
            "Invalid/duplicate history resource name");
        FALCOR_CHECK(format != ResourceFormat::Unknown && !isDepthStencilFormat(format) && !isCompressedFormat(format) &&
            (device->getFormatBindFlags(format) & kFlags) == kFlags, "History requires a sampled/UAV texture format");
        uint2 size(0);
        if (r.contains("size"))
        {
            const auto& value = r.at("size");
            FALCOR_CHECK(value.is_array() && value.size() == 2, "History size requires two integer dimensions");
            for (uint32_t i = 0; i < 2; ++i)
            {
                FALCOR_CHECK(value[i].is_number_integer() && value[i] > 0 && value[i] <= 16384,
                    "History dimensions must be in [1,16384]");
                size[i] = value[i].get<uint32_t>();
            }
        }
        p.resources.push_back({name, format, size});
    }
}
CustomRenderPiplineHistoryPass::~CustomRenderPiplineHistoryPass() = default;
Properties CustomRenderPiplineHistoryPass::getProperties() const { return mpImpl->properties; }

RenderPassReflection CustomRenderPiplineHistoryPass::reflect(const CompileData&)
{
    RenderPassReflection r;
    for (const auto& resource : mpImpl->resources)
    {
        auto& field = mpImpl->read ? r.addOutput(resource.name, "Previous writer execution") : r.addInput(resource.name, "Current history value");
        field.texture2D(resource.size.x, resource.size.y).format(resource.format).bindFlags(kFlags);
    }
    r.addOutput("status", "uint4(valid, updates low32, reserved=0, read=0/write=1)")
        .texture2D(1, 1).format(ResourceFormat::RGBA32Uint).bindFlags(kFlags);
    return r;
}
void CustomRenderPiplineHistoryPass::compile(RenderContext*, const CompileData& data) { mpImpl->extent = data.defaultTexDims; }
void CustomRenderPiplineHistoryPass::setScene(RenderContext*, const ref<Scene>&)
{
    if (mpImpl->storage) mpImpl->storage->reset();
}

void CustomRenderPiplineHistoryPass::execute(RenderContext* context, const RenderData& data)
{
    auto& p = *mpImpl;
    FALCOR_CHECK(p.storage, "History pair is not bound; call customRenderPiplineBindHistory after graph edits");
    auto& s = *p.storage;
    // Validate every resource before allocation, clear, copy or publication.
    for (const auto& resource : p.resources)
    {
        const auto texture = data.getTexture(resource.name);
        const auto extent = resource.resolve(p.extent);
        FALCOR_CHECK(extent.x > 0 && extent.y > 0 && extent.x <= 16384 && extent.y <= 16384, "History extent out of range");
        FALCOR_CHECK(texture && texture->getType() == Resource::Type::Texture2D && texture->getFormat() == resource.format &&
            texture->getWidth() == extent.x && texture->getHeight() == extent.y && texture->getArraySize() == 1 &&
            texture->getMipCount() == 1 && texture->getSampleCount() == 1, "History resource extent/type mismatch");
    }
    const auto status = data.getTexture("status");
    FALCOR_CHECK(status && status->getFormat() == ResourceFormat::RGBA32Uint && status->getWidth() == 1 && status->getHeight() == 1,
        "History status allocation mismatch");
    if (any(s.extent != p.extent))
    {
        s.textures.clear();
        s.extent = p.extent;
        s.reset();
    }
    // Allocate all destinations before publishing any value. These resources
    // never enter the graph pool, so downstream writes cannot corrupt history.
    for (const auto& resource : p.resources)
    {
        auto& pair = s.textures[resource.name];
        const auto extent = resource.resolve(p.extent);
        for (auto& texture : pair)
            if (!texture) texture = mpDevice->createTexture2D(extent.x, extent.y, resource.format, 1, 1, nullptr, kFlags);
    }
    const uint32_t writeSlot = 1 - s.publishedSlot;
    for (const auto& resource : p.resources)
    {
        const auto texture = data.getTexture(resource.name);
        const auto& pair = s.textures.at(resource.name);
        if (p.read)
        {
            if (s.valid) context->copyResource(texture.get(), pair[s.publishedSlot].get());
            else if (isIntegerFormat(resource.format)) context->clearUAV(texture->getUAV().get(), uint4(0));
            else context->clearUAV(texture->getUAV().get(), float4(0));
        }
        else context->copyResource(pair[writeSlot].get(), texture.get());
    }
    if (!p.read)
    {
        // Ordinary graph semantics: a later pass failure does not undo this
        // writer. GPU ordering handles copies; no wait/readback/frame scheduler.
        s.publishedSlot = writeSlot;
        ++s.updates;
        s.valid = true;
    }
    context->clearUAV(status->getUAV().get(), uint4(s.valid ? 1u : 0u, uint32_t(s.updates), 0u, p.read ? 0u : 1u));
}

void bindHistoryGraph(RenderGraph& graph)
{
    struct Pair { CustomRenderPiplineHistoryPass* reader = nullptr; CustomRenderPiplineHistoryPass* writer = nullptr; };
    std::map<std::string, Pair> pairs;
    const auto topology = graph.getTopology();
    for (const auto& [name, type] : topology.nodes)
    {
        auto* pass = dynamic_cast<CustomRenderPiplineHistoryPass*>(graph.getPass(name).get());
        if (!pass) continue;
        auto& pair = pairs[pass->mpImpl->key];
        auto& slot = pass->mpImpl->read ? pair.reader : pair.writer;
        FALCOR_CHECK(!slot, "History key requires exactly one reader and writer");
        slot = pass;
    }
    // A malformed pair must not invalidate other pairs already in use.
    for (const auto& [key, pair] : pairs)
    {
        FALCOR_CHECK(pair.reader && pair.writer, "Missing history reader/writer for '{}'", key);
        FALCOR_CHECK(pair.reader->mpImpl->resources == pair.writer->mpImpl->resources, "History pair resource contract mismatch");
        std::set<std::string> reached{pair.reader->getName()};
        bool changed = true;
        while (changed)
        {
            changed = false;
            for (const auto& [src, dst] : topology.edges)
                if (reached.count(nodeOf(src))) changed |= reached.insert(nodeOf(dst)).second;
        }
        FALCOR_CHECK(reached.count(pair.writer->getName()), "History reader must precede writer through graph dependencies");
        const auto status = pair.writer->getName() + ".status";
        FALCOR_CHECK(std::find(topology.outputs.begin(), topology.outputs.end(), status) != topology.outputs.end(),
            "History writer status must be a graph output to retain the writer");
    }
    for (const auto& [key, pair] : pairs)
        pair.reader->mpImpl->storage = pair.writer->mpImpl->storage = std::make_shared<HistoryStorage>();
}

void resetHistoryGraph(RenderGraph& graph, const std::string& key)
{
    std::vector<std::shared_ptr<HistoryStorage>> storages;
    for (const auto& [name, type] : graph.getTopology().nodes)
    {
        auto* pass = dynamic_cast<CustomRenderPiplineHistoryPass*>(graph.getPass(name).get());
        if (!pass || !pass->mpImpl->read || (!key.empty() && pass->mpImpl->key != key)) continue;
        FALCOR_CHECK(pass->mpImpl->storage, "History pair is not bound");
        storages.push_back(pass->mpImpl->storage);
    }
    FALCOR_CHECK(key.empty() || !storages.empty(), "Unknown history reset key '{}'", key);
    for (const auto& storage : storages) storage->reset();
}

Json historyGraphInfo(RenderGraph& graph)
{
    Json result = Json::object();
    for (const auto& [name, type] : graph.getTopology().nodes)
    {
        auto* pass = dynamic_cast<CustomRenderPiplineHistoryPass*>(graph.getPass(name).get());
        if (!pass || !pass->mpImpl->read) continue;
        const auto& p = *pass->mpImpl;
        FALCOR_CHECK(p.storage, "History pair is not bound");
        result[p.key] = {{"valid", p.storage->valid}, {"updates", p.storage->updates},
            {"extent", {p.storage->extent.x, p.storage->extent.y}}};
    }
    return result;
}
}
