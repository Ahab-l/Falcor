#include "Testing/UnitTest.h"
#include "Core/Program/ProgramVersion.h"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>

namespace Falcor
{
// Keep scalar layout enabled and exercise the actual Falcor compiler session.
// With bundled Slang's direct emitter this can return correct values while
// emitting invalid ArrayStride decorations on Workgroup storage. The serial
// runner must also inspect native Logger diagnostics and validate the SPIR-V.
GPU_TEST(NativeWorkgroupDefaultEmitter)
{
    ProgramDesc desc;
    desc.addShaderModule().addString(R"(
groupshared float4 sharedValues[32];
RWStructuredBuffer<float4> result;
[numthreads(32, 1, 1)]
void main(uint i : SV_GroupIndex)
{
    sharedValues[i] = float4(i + 1, i + 2, i + 3, i + 4);
    GroupMemoryBarrierWithGroupSync();
    result[i] = sharedValues[(i + 1) % 32];
}
)");
    desc.csEntry("main").setShaderModel(ShaderModel::SM6_6);
    ctx.createProgram(desc);
    ctx.allocateStructuredBuffer("result", 32);
    ctx.runProgram(32);
    const auto result = ctx.readBuffer<float4>("result");
    ASSERT_EQ(result.size(), 32u);
    for (uint32_t i = 0; i < 32; ++i)
        for (uint32_t c = 0; c < 4; ++c)
            ASSERT_EQ(result[i][c], float((i + 1) % 32 + c + 1));

    if (ctx.getDevice()->getType() == Device::Type::Vulkan)
    {
        const auto kernels = ctx.getProgram()->getActiveVersion()->getKernels(ctx.getDevice().get(), ctx.getVars());
        const auto blob = kernels->getKernel(ShaderType::Compute)->getBlobData();
        const auto path = std::filesystem::temp_directory_path() /
            ("falcor-native-workgroup-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".spv");
        std::ofstream stream(path, std::ios::binary);
        stream.write(static_cast<const char*>(blob.data), blob.size);
        stream.close();
        ASSERT_TRUE(stream.good());
        std::cout << "NATIVE_WORKGROUP_SPIRV " << path.string() << std::endl;
    }
    std::cout << "NATIVE_WORKGROUP_NUMERICAL_PASS pixels=32 channels=4" << std::endl;
}
}
