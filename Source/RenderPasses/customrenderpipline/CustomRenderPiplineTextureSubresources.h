#pragma once
#include "CustomRenderPiplineShaderBindings.h"

namespace Falcor::CustomRenderPipline
{
// Allocation shape and shader view are distinct parts of an immutable resource
// declaration. Slice indices are physical 2D layers, including six Cube faces.
struct TextureSubresources
{
    Resource::Type type = Resource::Type::Texture2D;
    uint32_t arraySize = 1, mipCount = 1;
    uint32_t firstMip = 0, viewMipCount = 1, firstSlice = 0, sliceCount = 1;
    bool layered = false;

    static uint32_t integer(const nlohmann::json& value, const char* label, uint32_t maximum, bool zero = false)
    {
        FALCOR_CHECK(value.is_number_integer() && value >= (zero ? 0 : 1) && value <= maximum,
            "Texture {} is out of range", label);
        return value.get<uint32_t>();
    }
    TextureSubresources() = default;
    TextureSubresources(const nlohmann::json& resource, bool readOnly)
    {
        using Json = nlohmann::json;
        const auto kind = resource.value("kind", std::string("texture2D"));
        FALCOR_CHECK(kind == "texture2D" || kind == "texture2DArray" || kind == "textureCube", "Unsupported texture kind");
        type = kind == "textureCube" ? Resource::Type::TextureCube : Resource::Type::Texture2D;
        layered = kind != "texture2D";
        arraySize = integer(resource.value("array_size", Json(1)), "array_size", 2048);
        FALCOR_CHECK(kind == "texture2DArray" ? arraySize >= 2 : arraySize == 1,
            "texture2DArray requires at least two layers; texture2D and textureCube require array_size 1");
        mipCount = integer(resource.value("mip_count", Json(1)), "mip_count", 15);
        const auto view = resource.value("view", Json::object());
        ShaderBindings::keys(view, {"mip", "mip_count", "first_slice", "slice_count"}, "texture view");
        firstMip = integer(view.value("mip", Json(0)), "view mip", mipCount - 1, true);
        viewMipCount = integer(view.value("mip_count", Json(readOnly ? mipCount - firstMip : 1)), "view mip_count", mipCount - firstMip);
        FALCOR_CHECK(readOnly || viewMipCount == 1, "Writable texture views select exactly one mip");
        const uint32_t layers = type == Resource::Type::TextureCube ? 6 : arraySize;
        firstSlice = integer(view.value("first_slice", Json(0)), "view first_slice", layers - 1, true);
        sliceCount = integer(view.value("slice_count", Json(layers - firstSlice)), "view slice_count", layers - firstSlice);
        FALCOR_CHECK(!readOnly || type != Resource::Type::TextureCube || (firstSlice == 0 && sliceCount == 6),
            "Cube SRV requires all six faces");
    }
    ReflectionResourceType::Dimensions dimensions(bool readOnly) const
    {
        using D = ReflectionResourceType::Dimensions;
        return type == Resource::Type::TextureCube && readOnly ? D::TextureCube : layered ? D::Texture2DArray : D::Texture2D;
    }
    void validateSize(uint2 size) const
    {
        if (!size.x || !size.y) return; // The graph may still be resolving input reflection.
        FALCOR_CHECK(size.x <= 16384 && size.y <= 16384, "Texture dimensions exceed the D3D12 limit");
        FALCOR_CHECK(type != Resource::Type::TextureCube || size.x == size.y, "Cube texture dimensions must be square");
        uint32_t levels = 1;
        for (uint32_t n = std::max(size.x, size.y); n > 1; n >>= 1) ++levels;
        FALCOR_CHECK(mipCount <= levels, "Texture mip_count exceeds its dimensions");
    }
    void validate(const ref<Texture>& texture, ResourceFormat format) const
    {
        FALCOR_CHECK(texture && texture->getType() == type && texture->getFormat() == format &&
            texture->getArraySize() == arraySize && texture->getMipCount() == mipCount && texture->getSampleCount() == 1,
            "Texture allocation does not match declared kind/format/layers/mips");
        validateSize(uint2(texture->getWidth(), texture->getHeight()));
    }
    bool overlaps(const TextureSubresources& other) const
    {
        return firstMip < other.firstMip + other.viewMipCount && other.firstMip < firstMip + viewMipCount &&
            firstSlice < other.firstSlice + other.sliceCount && other.firstSlice < firstSlice + sliceCount;
    }
};
}
