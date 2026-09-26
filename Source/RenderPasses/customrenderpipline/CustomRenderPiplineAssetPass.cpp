#include "CustomRenderPiplineAssetPass.h"
#include "CustomRenderPiplineTextureSubresources.h"
#include <fstream>
#include <regex>

namespace Falcor
{
struct CustomRenderPiplineAssetPass::Impl
{
    Properties properties;
    struct Asset
    {
        std::string name;
        uint32_t bytes = 0;
        uint2 size = uint2(0);
        ResourceFormat format = ResourceFormat::Unknown;
        CustomRenderPipline::TextureSubresources texture;
        // This allocation never enters the graph's pool or escapes to a caller.
        // A graph consumer may overwrite its own copy without corrupting assets.
        ref<Resource> source;
    };
    std::vector<Asset> assets;
    explicit Impl(const Properties& props) : properties(props) {}
};

CustomRenderPiplineAssetPass::CustomRenderPiplineAssetPass(ref<Device> device, const Properties& props)
    : RenderPass(device), mpImpl(std::make_unique<Impl>(props))
{
    using CustomRenderPipline::ShaderBindings::keys;
    auto& p = *mpImpl;
    const auto options = props.toJson();
    keys(options, {"assets"}, "asset pass");
    FALCOR_CHECK(options.contains("assets"), "Asset source requires named assets");
    const auto& declarations = options.at("assets");
    FALCOR_CHECK(declarations.is_object() && !declarations.empty(), "Asset source requires named assets");
    for (const auto& [name, declaration] : declarations.items())
    {
        FALCOR_CHECK(std::regex_match(name, std::regex("[A-Za-z_][A-Za-z0-9_]*")), "Invalid asset name '{}': use an identifier", name);
        Impl::Asset asset;
        asset.name = name;
        FALCOR_CHECK(declaration.is_object() && declaration.contains("kind") && declaration.at("kind").is_string(),
            "Asset '{}' requires an explicit resource kind", name);
        const auto kind = declaration.at("kind").get<std::string>();
        const bool raw = kind == "raw_buffer";
        FALCOR_CHECK(raw || kind == "texture2D" || kind == "texture2DArray" || kind == "textureCube",
            "Unsupported asset kind '{}'", kind);
        keys(declaration, raw ? std::set<std::string>{"file", "kind", "bytes"} :
            std::set<std::string>{"file", "kind", "format", "size", "mip_count", "array_size", "srgb"}, "asset");
        FALCOR_CHECK(declaration.contains("file") && declaration.at("file").is_string() &&
            !declaration.at("file").get<std::string>().empty(), "Asset '{}' requires a nonempty file path", name);
        const std::filesystem::path path(declaration.at("file").get<std::string>());
        FALCOR_CHECK(std::filesystem::is_regular_file(path), "Asset file does not exist or is not a regular file: {}", path);
        if (raw)
        {
            const auto count = declaration.at("bytes");
            FALCOR_CHECK(count.is_number_integer() && count > 0 && count <= UINT32_MAX && count.get<uint32_t>() % 4 == 0,
                "Asset raw_buffer bytes must be a positive uint32 multiple of four");
            asset.bytes = count.get<uint32_t>();
            FALCOR_CHECK(std::filesystem::file_size(path) == asset.bytes, "Asset buffer file size does not match declared bytes: {}", name);
            std::vector<char> bytes(asset.bytes);
            std::ifstream stream(path, std::ios::binary);
            FALCOR_CHECK(stream.read(bytes.data(), bytes.size()), "Cannot read asset buffer: {}", path);
            asset.source = device->createBuffer(asset.bytes, ResourceBindFlags::ShaderResource, MemoryType::DeviceLocal, bytes.data());
        }
        else
        {
            asset.texture = CustomRenderPipline::TextureSubresources(declaration, true);
            const auto& size = declaration.at("size");
            FALCOR_CHECK(size.is_array() && size.size() == 2, "Asset texture requires a fixed size [width,height]");
            asset.size = uint2(CustomRenderPipline::TextureSubresources::integer(size[0], "width", 16384),
                CustomRenderPipline::TextureSubresources::integer(size[1], "height", 16384));
            asset.texture.validateSize(asset.size);
            asset.format = stringToEnum<ResourceFormat>(declaration.at("format").get<std::string>());
            FALCOR_CHECK(asset.format != ResourceFormat::Unknown, "Asset texture requires an explicit format");
            FALCOR_CHECK(!declaration.contains("srgb") || declaration.at("srgb").is_boolean(), "Asset srgb must be boolean");
            // Loading happens only at construction (including native updatePass).
            // DDS retains its original format and complete mip chain. Other
            // image formats are uploaded without synthesizing additional mips.
            auto texture = Texture::createFromFile(device, path, false, declaration.value("srgb", false));
            asset.texture.validate(texture, asset.format);
            FALCOR_CHECK(all(uint2(texture->getWidth(), texture->getHeight()) == asset.size),
                "Asset texture size does not match the declaration: {}", name);
            asset.source = texture;
        }
        p.assets.push_back(std::move(asset));
    }
}

CustomRenderPiplineAssetPass::~CustomRenderPiplineAssetPass() = default;

Properties CustomRenderPiplineAssetPass::getProperties() const
{
    return mpImpl->properties;
}

RenderPassReflection CustomRenderPiplineAssetPass::reflect(const CompileData&)
{
    RenderPassReflection result;
    for (const auto& asset : mpImpl->assets)
    {
        auto& field = result.addOutput(asset.name, "Copy of an immutable file asset").bindFlags(ResourceBindFlags::ShaderResource);
        if (asset.bytes) field.rawBuffer(asset.bytes);
        else
        {
            if (asset.texture.type == Resource::Type::TextureCube)
                field.textureCube(asset.size.x, asset.size.y, asset.texture.mipCount, asset.texture.arraySize);
            else field.texture2D(asset.size.x, asset.size.y, 1, asset.texture.mipCount, asset.texture.arraySize);
            field.format(asset.format);
        }
    }
    return result;
}

void CustomRenderPiplineAssetPass::execute(RenderContext* context, const RenderData& data)
{
    auto& p = *mpImpl;
    // Validate all destinations before recording any copy.
    for (const auto& asset : p.assets)
    {
        const auto destination = data[asset.name];
        FALCOR_CHECK(destination && destination != asset.source, "Missing or aliased asset output: {}", asset.name);
        if (asset.bytes)
        {
            const auto buffer = destination->asBuffer();
            FALCOR_CHECK(buffer && buffer->getSize() == asset.bytes && buffer->getFormat() == ResourceFormat::Unknown && buffer->getStructSize() == 0,
                "Asset buffer allocation mismatch: {}", asset.name);
        }
        else
        {
            const auto texture = destination->asTexture();
            asset.texture.validate(texture, asset.format);
            FALCOR_CHECK(all(uint2(texture->getWidth(), texture->getHeight()) == asset.size), "Asset texture allocation size mismatch: {}", asset.name);
        }
    }
    // GPU copies only. No per-frame file I/O, upload, or CPU/GPU wait.
    for (const auto& asset : p.assets) context->copyResource(data[asset.name].get(), asset.source.get());
}
}
