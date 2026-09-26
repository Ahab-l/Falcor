#include "Testing/UnitTest.h"
#include "Utils/Algorithm/ParallelReduction.h"
#include <algorithm>
#include <array>
#include <cstring>
#include <initializer_list>
#include <iostream>
#include <limits>
#include <type_traits>
#include <vector>

namespace Falcor
{
namespace
{
template<typename T>
void checkReductionTypeStage(
    GPUUnitTestContext& ctx,
    ParallelReduction& reduction,
    const char* label,
    uint32_t width,
    uint32_t height,
    std::initializer_list<ParallelReduction::Type> operations = {ParallelReduction::Type::Sum, ParallelReduction::Type::MinMax})
{
    using Scalar = typename T::value_type;
    static_assert(sizeof(T) == 16);
    constexpr bool isUnsigned = std::is_unsigned_v<Scalar>;
    constexpr bool isFloat = std::is_floating_point_v<Scalar>;
    const auto device = ctx.getDevice();
    std::vector<T> input(size_t(width) * height);
    std::array<int64_t, 4> sums = {};
    std::array<int32_t, 4> minima, maxima;
    minima.fill(std::numeric_limits<int32_t>::max());
    maxima.fill(std::numeric_limits<int32_t>::lowest());
    for (uint32_t y = 0; y < height; ++y)
    {
        for (uint32_t x = 0; x < width; ++x)
        {
            for (uint32_t channel = 0; channel < 4; ++channel)
            {
                const int32_t value = int32_t((3 * x + 5 * y + 7 * channel) % 17) - (isUnsigned ? 0 : 8);
                // Float inputs are exact multiples of 1/4. The largest stage's
                // absolute partial sums stay exactly representable in FP32;
                // CPU expectation uses integer units, independent of GPU order.
                input[size_t(y) * width + x][channel] = isFloat ? Scalar(value) * Scalar(.25) : Scalar(value);
                sums[channel] += value;
                minima[channel] = std::min(minima[channel], value);
                maxima[channel] = std::max(maxima[channel], value);
            }
        }
    }
    const auto texture = device->createTexture2D(
        width, height, detail::FormatForElementType<T>::kFormat, 1, 1, input.data(), ResourceBindFlags::ShaderResource);
    for (const auto operation : operations)
    {
        const bool sum = operation == ParallelReduction::Type::Sum;
        const size_t resultCount = sum ? 1 : 2;
        T expected[2] = {};
        for (uint32_t channel = 0; channel < 4; ++channel)
        {
            expected[0][channel] = Scalar(sum ? sums[channel] : minima[channel]);
            expected[1][channel] = Scalar(maxima[channel]);
            if constexpr (isFloat)
            {
                expected[0][channel] *= .25f;
                expected[1][channel] *= .25f;
            }
        }
        std::array<uint8_t, 80> initial;
        initial.fill(0xa5);
        // This is only a raw copy destination, not a typed shader binding.
        // Prefix/suffix sentinels also retain the public resultOffset contract.
        auto output = device->createBuffer(initial.size(), ResourceBindFlags::None, MemoryType::DeviceLocal, initial.data());
        T result[2] = {};
        reduction.execute<T>(ctx.getRenderContext(), texture, operation, result, output, 16);
        for (size_t value = 0; value < resultCount; ++value)
            for (uint32_t channel = 0; channel < 4; ++channel)
                ASSERT_EQ(result[value][channel], expected[value][channel]) << label << (sum ? " Sum" : " MinMax");
        std::array<uint8_t, 80> actual;
        output->getBlob(actual.data(), 0, actual.size());
        auto expectedBytes = initial;
        std::memcpy(expectedBytes.data() + 16, expected, resultCount * sizeof(T));
        ASSERT_EQ(std::memcmp(actual.data(), expectedBytes.data(), actual.size()), 0) << label;
        std::cout << "PARALLEL_REDUCTION_TYPE_TRANSITIONS_CASE " << label << " " << width << "x" << height
                  << " " << (sum ? "Sum" : "MinMax") << " PASS" << std::endl;
    }
}
}

// Numerical PASS is necessary but not sufficient: the runner must also inspect
// the actual FalcorTest Logger file for Vulkan validation errors. Pre-fix UINT
// intermediates can produce correct bytes while violating FLOAT/SINT view types.
GPU_TEST(ParallelReductionTypedIntermediateTransitions)
{
    ParallelReduction reduction(ctx.getDevice());
    checkReductionTypeStage<float4>(ctx, reduction, "fixed_float_1", 33, 33);
    checkReductionTypeStage<uint4>(ctx, reduction, "fixed_uint", 33, 33);
    checkReductionTypeStage<int4>(ctx, reduction, "fixed_sint", 33, 33);
    checkReductionTypeStage<float4>(ctx, reduction, "fixed_float_2", 33, 33);
    // 33 x 33 tiles, not pixels: this grows both ping-pong capacities and
    // requires two final-pass dispatches before returning to a smaller type.
    checkReductionTypeStage<float4>(ctx, reduction, "grown_float", 1025, 1025);
    checkReductionTypeStage<uint4>(ctx, reduction, "shrunk_uint", 33, 33);
    checkReductionTypeStage<int4>(ctx, reduction, "shrunk_sint", 33, 33);
    checkReductionTypeStage<float4>(ctx, reduction, "shrunk_float", 33, 33);
    std::cout << "PARALLEL_REDUCTION_TYPE_TRANSITIONS_PASS stages=8 reductions=16" << std::endl;
}

GPU_TEST(ParallelReductionSecondaryCapacityGrowth)
{
    ParallelReduction reduction(ctx.getDevice());
    // 32 x 32 tiles with Sum seed capacities [1024, 1]. Do not run MinMax
    // here: that would pre-grow buffer 1 and hide its independent resize path.
    checkReductionTypeStage<float4>(ctx, reduction, "secondary_seed_sum", 1024, 1024, {ParallelReduction::Type::Sum});
    ASSERT_EQ(reduction.getMemoryUsageInBytes(), uint64_t(1024 + 1) * sizeof(float4)) << "seed capacities [1024, 1]";

    // Two tiles with MinMax need [4, 2]. Buffer 0 must retain its sufficient
    // capacity while buffer 1 grows, with no format change to force recreation.
    checkReductionTypeStage<float4>(ctx, reduction, "secondary_growth_minmax", 64, 32, {ParallelReduction::Type::MinMax});
    ASSERT_EQ(reduction.getMemoryUsageInBytes(), uint64_t(1024 + 2) * sizeof(float4)) << "grown capacities [1024, 2]";
    std::cout << "PARALLEL_REDUCTION_SECONDARY_CAPACITY_GROWTH_PASS stages=2 reductions=2" << std::endl;
}
}
