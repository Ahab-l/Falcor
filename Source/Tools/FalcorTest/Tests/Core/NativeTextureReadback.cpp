// Generic raw BC tail-mip regression extracted from retired SceneIdentity tests.
#include "Testing/UnitTest.h"
#include <array>

namespace Falcor
{
GPU_TEST(NativeBC4MipReadback, Device::Type::D3D12)
{
    // Each BC4 mip occupies one 8-byte block, including the 2x2 and 1x1 tails.
    const std::array<std::array<uint8_t, 8>, 3> blocks = {{
        {{241, 17, 0x88, 0xc6, 0xfa, 0x88, 0xc6, 0xfa}},
        {{193, 41, 0x13, 0x57, 0x9b, 0xdf, 0x24, 0x68}},
        {{127, 3, 0x55, 0xaa, 0x33, 0xcc, 0x0f, 0xf0}},
    }};
    const auto texture = ctx.getDevice()->createTexture2D(4, 4, ResourceFormat::BC4Unorm, 1, 3, blocks.data());
    for (uint32_t mip = 0; mip < blocks.size(); ++mip)
    {
        EXPECT_EQ(texture->getWidth(mip), 4u >> mip);
        const auto bytes = ctx.getRenderContext()->readTextureSubresource(texture.get(), mip);
        ASSERT_EQ(bytes.size(), size_t(8));
        for (size_t byte = 0; byte < bytes.size(); ++byte)
            EXPECT_EQ(bytes[byte], blocks[mip][byte]) << "BC4 mip " << mip << ", raw byte " << byte;
    }
}

}
