#include "Core/Plugin.h"
#include "../Core/NativeGpuWorkload.h"
#include "Testing/UnitTest.h"
#include "RenderGraph/RenderGraph.h"
#include "RenderGraph/RenderPassStandardFlags.h"
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <sstream>

namespace Falcor
{
namespace
{
std::vector<std::vector<std::string>> readRows(const std::filesystem::path& path)
{
    std::ifstream stream(path);
    std::string line;
    std::getline(stream, line); // Header.
    std::vector<std::vector<std::string>> rows;
    while (std::getline(stream, line))
    {
        std::istringstream row(line);
        std::vector<std::string> fields;
        while (std::getline(row, line, ',')) fields.push_back(line);
        rows.push_back(std::move(fields));
    }
    return rows;
}

// Exercise the actual native graph/pass behind bounded real GPU work.
// Pending markers are mandatory: early completion is a failure, not a retry.
void checkDynamicMeasurements(GPUUnitTestContext& ctx, bool sceneUpdates, bool refresh, bool replaceScene)
{
    PluginManager::instance().loadPluginByName("ErrorMeasurePass");
    const auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto path = std::filesystem::temp_directory_path() / ("falcor-error-async-" + std::to_string(stamp) + ".csv");
    Properties props;
    props["IgnoreBackground"] = false;
    props["ReportRunningError"] = false;
    props["SelectedOutputId"] = std::string("Difference");
    props["MeasurementsFilePath"] = path;
    auto pass = RenderPass::create("ErrorMeasurePass", device, props);
    auto graph = RenderGraph::create(device, "AsyncErrorMeasureTest");
    graph->addPass(pass, "Error");
    const auto flags = ResourceBindFlags::ShaderResource | ResourceBindFlags::RenderTarget;
    auto source = device->createTexture2D(2, 2, ResourceFormat::RGBA32Float, 1, 1, nullptr, flags);
    auto reference = device->createTexture2D(2, 2, ResourceFormat::RGBA32Float, 1, 1, nullptr, flags);
    graph->setInput("Error.Source", source);
    graph->setInput("Error.Reference", reference);
    graph->setInput("Error.WorldPosition", reference);
    graph->markOutput("Error.Output");
    auto fbo = Fbo::create2D(device, 2, 2, ResourceFormat::RGBA32Float);
    graph->onResize(fbo.get());
    context->clearRtv(source->getRTV().get(), float4(1.f));
    context->clearRtv(reference->getRTV().get(), float4(0.f));
    graph->execute(context); // Compile/warm without blocking the device queue.
    context->submit(true);
    graph->execute(context);
    context->submit(true);

    testing::NativeGpuWorkload workload(context);
    workload.enqueue();
    const bool markerBefore = workload.markerPending();
    const auto update = [&]
    {
        if (sceneUpdates)
            graph->onSceneUpdates(context, IScene::UpdateFlags::CameraMoved | IScene::UpdateFlags::GeometryMoved);
        graph->getPassesDictionary()[kRenderPassRefreshFlags] =
            refresh ? RenderPassRefreshFlags::LightingChanged : RenderPassRefreshFlags::None;
    };
    for (uint32_t i = 1; i <= 8; ++i)
    {
        context->clearRtv(source->getRTV().get(), float4(float(i), 2.f, 3.f, 1.f));
        update();
        graph->execute(context);
    }
    const auto before = readRows(path).size();
    const bool markerAfter = workload.markerPending();
    workload.finish();
    logInfo("ERROR_MEASURE_PENDING iterations={}, marker_before={}, marker_after={}, executions=8, rows_before_collect={}",
        workload.iterations(), markerBefore, markerAfter, before);
    ASSERT_TRUE(markerBefore && markerAfter) << "Statistics must remain pending through all eight executions; no retry";
    // This completion and pixel read are test oracles, not render-pass implementation.
    const auto bytes = context->readTextureSubresource(graph->getOutput("Error.Output")->asTexture().get(), 0);
    ASSERT_EQ(bytes.size(), size_t(4 * sizeof(float4)));
    float4 pixels[4];
    std::memcpy(pixels, bytes.data(), bytes.size());
    for (const auto& pixel : pixels)
    {
        EXPECT_EQ(pixel.x, 64.f); // Queue full must not suppress Difference.
        EXPECT_EQ(pixel.y, 4.f);
        EXPECT_EQ(pixel.z, 9.f);
        EXPECT_EQ(pixel.w, 0.f);
    }
    if (replaceScene) pass->setScene(context, nullptr);
    update();
    graph->execute(context);
    const auto rows = readRows(path);
    ASSERT_EQ(rows.size(), before + (replaceScene ? 0u : 4u));
    if (!replaceScene)
    {
        // Four staged generations of scratch, not four copies of the last one.
        for (size_t i = 0; i < 4; ++i)
        {
            const auto& row = rows[before + i];
            ASSERT_EQ(row.size(), size_t(22));
            EXPECT_EQ(std::stof(row[1]), float((i + 1) * (i + 1)));
            EXPECT_EQ(std::stof(row[2]), 4.f);
            EXPECT_EQ(std::stof(row[3]), 9.f);
            EXPECT_EQ(std::stoull(row[6]), uint64_t(i + 3));
            EXPECT_TRUE(std::stoull(row[18]) > std::stoull(row[6]));
            EXPECT_EQ(std::stoull(row[19]), uint64_t(4));
        }
    }
    context->submit(true);
    graph = nullptr;
    pass = nullptr;
    std::filesystem::remove(path);
}
}

GPU_TEST(ErrorMeasureAsyncSceneUpdatesDoNotStarve)
{
    checkDynamicMeasurements(ctx, true, false, false);
}

GPU_TEST(ErrorMeasureAsyncRefreshDoesNotStarve)
{
    checkDynamicMeasurements(ctx, false, true, false);
}

GPU_TEST(ErrorMeasureAsyncSceneReplacementDiscardsPending)
{
    checkDynamicMeasurements(ctx, false, false, true);
}

GPU_TEST(ErrorMeasureAsyncValuesAndResize)
{
    PluginManager::instance().loadPluginByName("ErrorMeasurePass");
    const auto device = ctx.getDevice();
    auto context = ctx.getRenderContext();
    const bool cases[][3] = {{true, false, true}, {false, true, false}, {false, false, true}, {true, true, false}};
    for (const auto& options : cases)
    {
        const bool squared = options[0], average = options[1], ignore = options[2];
        const auto path = std::filesystem::temp_directory_path() /
            ("falcor-error-values-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".csv");
        Properties props;
        props["IgnoreBackground"] = ignore;
        props["ComputeSquaredDifference"] = squared;
        props["ComputeAverage"] = average;
        props["ReportRunningError"] = false;
        props["SelectedOutputId"] = std::string("Difference");
        props["MeasurementsFilePath"] = path;
        auto pass = RenderPass::create("ErrorMeasurePass", device, props);
        auto graph = RenderGraph::create(device, "ErrorValuesResize");
        graph->addPass(pass, "Error");
        graph->markOutput("Error.Output");
        for (uint32_t variant = 0; variant < 2; ++variant)
        {
            const uint32_t w = variant == 0 ? 17 : 23, h = variant == 0 ? 9 : 11;
            std::vector<float4> source(w * h), reference(w * h, float4(.25f, .5f, .75f, 1.f)), world(w * h), expected(w * h);
            double sums[3] = {};
            for (uint32_t y = 0; y < h; ++y)
                for (uint32_t x = 0; x < w; ++x)
                {
                    const auto i = y * w + x;
                    const bool foreground = (x + y) % 3 != 0;
                    const float3 delta(.25f + float(x % 4) * .125f, -.5f, 1.f);
                    source[i] = reference[i] + float4(delta, 7.f);
                    world[i] = float4(0.f, 0.f, 0.f, foreground ? 1.f : 0.f);
                    float3 error = ignore && !foreground ? float3(0.f) : abs(delta);
                    if (squared) error *= error;
                    if (average) error = float3((error.x + error.y + error.z) / 3.f);
                    expected[i] = float4(error, 0.f);
                    for (uint32_t c = 0; c < 3; ++c) sums[c] += error[c];
                }
            const auto texture = [&](const std::vector<float4>& data)
            {
                return device->createTexture2D(w, h, ResourceFormat::RGBA32Float, 1, 1, data.data(), ResourceBindFlags::ShaderResource);
            };
            graph->setInput("Error.Source", texture(source));
            graph->setInput("Error.Reference", texture(reference));
            graph->setInput("Error.WorldPosition", texture(world));
            const auto fbo = Fbo::create2D(device, w, h, ResourceFormat::RGBA32Float);
            graph->onResize(fbo.get());
            graph->execute(context);
            // First submission, and the resize with an old pending task, must
            // not publish a row. The native wait belongs solely to this test.
            EXPECT_EQ(readRows(path).size(), size_t(variant));
            context->submit(true);
            graph->execute(context);
            const auto rows = readRows(path);
            ASSERT_EQ(rows.size(), size_t(variant + 1));
            const auto& row = rows.back();
            ASSERT_EQ(row.size(), size_t(22));
            EXPECT_EQ(std::stoul(row[8]), w);
            EXPECT_EQ(std::stoul(row[9]), h);
            EXPECT_EQ(std::stoull(row[6]), uint64_t(variant * 2 + 1));
            EXPECT_EQ(row[11], squared ? std::string("MSE") : std::string("L1"));
            for (uint32_t c = 0; c < 3; ++c)
                EXPECT_LE(std::abs(std::stod(row[c + 1]) - sums[c] / (w * h)), 2e-6);
            const auto bytes = context->readTextureSubresource(graph->getOutput("Error.Output")->asTexture().get(), 0);
            ASSERT_EQ(bytes.size(), expected.size() * sizeof(float4));
            std::vector<float4> actual(expected.size());
            std::memcpy(actual.data(), bytes.data(), bytes.size());
            for (size_t i = 0; i < actual.size(); ++i)
                for (uint32_t c = 0; c < 4; ++c)
                    EXPECT_LE(std::abs(actual[i][c] - expected[i][c]), 2e-6f);
        }
        context->submit(true);
        graph = nullptr;
        pass = nullptr;
        std::filesystem::remove(path);
    }
}
}
