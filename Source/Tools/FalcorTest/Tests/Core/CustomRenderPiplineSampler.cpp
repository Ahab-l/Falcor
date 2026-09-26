// Descriptor parsing only: these CPU tests create no Device, shader, or GPU sampler.
#include "Testing/UnitTest.h"
#include "../../../../RenderPasses/customrenderpipline/CustomRenderPiplineShaderBindings.h"
#include <limits>

namespace Falcor
{
using CustomRenderPipline::ShaderBindings::Json;
using CustomRenderPipline::ShaderBindings::samplerDesc;

CPU_TEST(CustomRenderPiplineSamplerDefaults)
{
    const auto clamp = TextureAddressingMode::Clamp;
    const auto legacy = Sampler::Desc().setAddressingMode(clamp, clamp, clamp);
    EXPECT_TRUE(samplerDesc(Json::object()) == legacy);
    EXPECT_TRUE(samplerDesc(Json{{"max_anisotropy", 1}}) == legacy);
    EXPECT_TRUE(samplerDesc(Json{{"filter", "Linear"}, {"address", "Clamp"}}) == legacy);
    const auto point = TextureFilteringMode::Point;
    const auto wrap = TextureAddressingMode::Wrap;
    const auto oldPointWrap = Sampler::Desc().setFilterMode(point, point, point).setAddressingMode(wrap, wrap, wrap);
    EXPECT_TRUE(samplerDesc(Json{{"filter", "Point"}, {"address", "Wrap"}}) == oldPointWrap);
}

CPU_TEST(CustomRenderPiplineSamplerIntegerRange)
{
    for (uint32_t value = 1; value <= 16; ++value)
    {
        const auto clamp = TextureAddressingMode::Clamp;
        const auto expected = Sampler::Desc().setAddressingMode(clamp, clamp, clamp).setMaxAnisotropy(value);
        EXPECT_TRUE(samplerDesc(Json{{"max_anisotropy", value}}) == expected) << value;
        EXPECT_TRUE(samplerDesc(Json::parse("{\"max_anisotropy\":" + std::to_string(value) + "}")) == expected) << value;
    }
    // Native semantics permit Point + anisotropy: anisotropy > 1 overrides filtering.
    const auto point = TextureFilteringMode::Point;
    const auto wrap = TextureAddressingMode::Wrap;
    const auto expected = Sampler::Desc().setFilterMode(point, point, point).setAddressingMode(wrap, wrap, wrap).setMaxAnisotropy(8);
    EXPECT_TRUE(samplerDesc(Json{{"filter", "Point"}, {"address", "Wrap"}, {"max_anisotropy", 8}}) == expected);
}

CPU_TEST(CustomRenderPiplineSamplerStrictIntegerType)
{
    const std::vector<Json> invalid = {
        true, false, 1.0, 8.0, 8.5, 16.0, -1, 0, 17,
        std::numeric_limits<int64_t>::min(), std::numeric_limits<uint64_t>::max(),
        nullptr, "8", Json::array({8}), Json::object(),
    };
    for (const auto& value : invalid)
        EXPECT_THROW(samplerDesc(Json{{"max_anisotropy", value}}));
    for (const char* text : {"1.0", "8.0", "16.0", "8e0", "null", "true", "false"})
        EXPECT_THROW(samplerDesc(Json::parse(std::string("{\"max_anisotropy\":") + text + "}")));
}

CPU_TEST(CustomRenderPiplineSamplerClosedSchema)
{
    for (const char* alias : {"maxAnisotropy", "anisotropy", "lod_bias", "min_lod", "max_lod", "unknown"})
        EXPECT_THROW(samplerDesc(Json{{alias, 8}}));
    for (const auto& invalid : std::vector<Json>{nullptr, true, 8, "Linear", Json::array()})
        EXPECT_THROW(samplerDesc(invalid));
    EXPECT_THROW(samplerDesc(Json{{"filter", "Anisotropic"}}));
    EXPECT_THROW(samplerDesc(Json{{"address", "Invalid"}}));
    EXPECT_THROW(samplerDesc(Json{{"filter", nullptr}}));
    EXPECT_THROW(samplerDesc(Json{{"address", false}}));
}
} // namespace Falcor
