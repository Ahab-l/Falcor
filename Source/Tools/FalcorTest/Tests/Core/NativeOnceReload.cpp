#include "Testing/UnitTest.h"
#include "Core/HotReloadFlags.h"
#include "Core/Plugin.h"
#include "Core/Platform/OS.h"
#include "Core/Program/ProgramManager.h"
#include "RenderGraph/RenderGraph.h"
#include "Utils/Scripting/ScriptBindings.h"
#include "Utils/Scripting/Scripting.h"
#include <nlohmann/json.hpp>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>

namespace Falcor
{
namespace
{
using Json = nlohmann::ordered_json;

std::filesystem::path makeOnceReloadEvidenceDirectory()
{
    const auto parent = std::filesystem::temp_directory_path();
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    for (uint32_t attempt = 0; attempt < 16; ++attempt)
    {
        const auto path = parent / ("falcor-native-once-reload-" + std::to_string(stamp) + "-" + std::to_string(attempt));
        if (std::filesystem::create_directory(path)) return path;
    }
    FALCOR_THROW("Could not create a fresh native once-reload evidence directory");
}

std::string onceReloadShader(uint32_t value)
{
    return "RWTexture2D<uint> result;\n"
           "[numthreads(4,4,1)] void main(uint3 p:SV_DispatchThreadID) {\n"
           "    if (p.x < 8 && p.y < 8) result[p.xy] = " + std::to_string(value) + ";\n}\n";
}

void writeOnceReloadText(const std::filesystem::path& path, const std::string& contents)
{
    std::ofstream stream(path, std::ios::binary | std::ios::trunc);
    stream << contents;
    stream.close();
    FALCOR_CHECK(stream.good(), "Failed to write once-reload evidence '{}'", path);
}
}

// This uses the public C++ program manager API, not a test-only Python reload
// hook. Plugin loading mirrors ErrorMeasureAsyncTests.cpp. The same pass and
// destination allocation survive every shader edit and reload.
GPU_TEST(NativeOnceShaderFileHotReload, Device::Type::D3D12)
{
    const auto out = makeOnceReloadEvidenceDirectory();
    std::cout << "NATIVE_ONCE_RELOAD_EVIDENCE " << out.string() << std::endl;
    Json evidence = {{"status", "running"}, {"backend", "D3D12"}, {"steps", Json::array()},
                     {"dispatch_count_source", "falcor.falcor_ext.customRenderPiplineComputeDispatchCount"},
                     {"expected_dispatch_counts", {1, 1, 1, 2, 2, 3, 3}}};
    const auto saveResult = [&] { writeOnceReloadText(out / "result.json", evidence.dump(2) + "\n"); };
    try
    {
        // UnitTest.cpp::runTests owns interpreter startup/shutdown, as used by
        // SettingsTests.cpp. Keep the GIL until all local Python objects die;
        // plugin registration can immediately add bindings to the live module.
        ASSERT_TRUE(Scripting::isRunning());
        pybind11::gil_scoped_acquire gil;
        PluginManager::instance().loadPluginByName("customrenderpipline");
        // FalcorTest imports the package before loading this plugin. Its
        // __init__.py copies "from .falcor_ext import *" only once, whereas
        // ScriptBindings registers late plugin functions on the live native
        // falcor_ext module. Query that module, not the stale package exports.
        const auto falcorModule = pybind11::module_::import("falcor.falcor_ext");
        ASSERT_TRUE(pybind11::hasattr(falcorModule, "customRenderPiplineComputeDispatchCount"));
        const auto dispatchCount = falcorModule.attr("customRenderPiplineComputeDispatchCount");
        const auto device = ctx.getDevice();
        auto context = ctx.getRenderContext();
        const auto shader = out / "Program.slang";
        writeOnceReloadText(shader, onceReloadShader(1));
        writeOnceReloadText(out / "Program-v1.slang", onceReloadShader(1));
        Json properties = {
            {"execution", "once"},
            {"shader", {{"file", shader.string()}}},
            {"resources", Json::array({{{"name", "result"}, {"binding", "result"}, {"direction", "output"},
                                        {"kind", "texture2D"}, {"format", "R32Uint"}, {"size", {8, 8}}}})},
            {"dispatch", {{"threads", {8, 8, 1}}}},
        };
        writeOnceReloadText(out / "Properties.json", properties.dump(2) + "\n");
        auto pass = RenderPass::create("CustomRenderPiplineComputePass", device, Properties(properties));
        auto graph = RenderGraph::create(device, "NativeOnceShaderFileHotReload");
        graph->addPass(pass, "Once");
        graph->markOutput("Once.result");
        auto fbo = Fbo::create2D(device, 8, 8, ResourceFormat::RGBA32Float);
        graph->onResize(fbo.get());
        graph->execute(context);
        auto output = graph->getOutput("Once.result")->asTexture();
        ASSERT_TRUE(output);
        ASSERT_EQ(output->getWidth(), 8u);
        ASSERT_EQ(output->getHeight(), 8u);

        const auto readExpected = [&](const char* label, uint32_t expected, uint64_t expectedDispatchCount)
        {
            ASSERT_TRUE(graph->getPass("Once").get() == pass.get());
            ASSERT_TRUE(graph->getOutput("Once.result").get() == output.get());
            // Use the already-shipped plugin binding rather than directly
            // linking its non-exported CustomRenderPiplineShaderPass class.
            const auto actualDispatchCount = dispatchCount(pybind11::cast(graph), "Once").cast<uint64_t>();
            evidence["steps"].push_back({{"case", label}, {"expected_each_pixel", expected},
                                         {"pixels", 64}, {"same_pass_and_output", true},
                                         {"dispatch_count", actualDispatchCount}, {"expected_dispatch_count", expectedDispatchCount},
                                         {"status", "running"}});
            saveResult();
            const auto bytes = context->readTextureSubresource(output.get(), 0);
            const auto path = out / (std::string(label) + ".r32uint.bin");
            std::ofstream file(path, std::ios::binary);
            file.write(reinterpret_cast<const char*>(bytes.data()), bytes.size());
            file.close();
            ASSERT_TRUE(file.good());
            ASSERT_EQ(bytes.size(), size_t(8 * 8 * sizeof(uint32_t)));
            uint32_t pixels[64];
            std::memcpy(pixels, bytes.data(), bytes.size());
            for (uint32_t pixel : pixels) ASSERT_EQ(pixel, expected) << label;
            ASSERT_EQ(actualDispatchCount, expectedDispatchCount) << label;
            evidence["steps"].back()["status"] = "passed";
            saveResult();
        };
        const auto poisonThenExecute = [&]
        {
            context->clearUAV(output->getUAV().get(), uint4(777u));
            graph->execute(context);
        };
        const auto edit = [&](uint32_t value)
        {
            const auto oldNativeTime = getFileModifiedTime(shader);
            const auto oldTime = std::filesystem::last_write_time(shader);
            writeOnceReloadText(shader, onceReloadShader(value));
            writeOnceReloadText(out / ("Program-v" + std::to_string(value) + ".slang"), onceReloadShader(value));
            // Program::checkIfFilesChanged uses second-granularity stat(). Force
            // only this fresh fixture's mtime forward; never sleep or forceReload.
            std::filesystem::last_write_time(shader, oldTime + std::chrono::seconds(2));
            ASSERT_NE(getFileModifiedTime(shader), oldNativeTime);
        };

        readExpected("initial_program", 1, 1);
        poisonThenExecute();
        readExpected("initial_cache_restores_poison", 1, 1);
        edit(2);
        poisonThenExecute();
        readExpected("file_edit_without_reload_keeps_program_1", 1, 1);
        ASSERT_TRUE(device->getProgramManager()->reloadAllPrograms(false));
        graph->onHotReload(HotReloadFlags::Program);
        poisonThenExecute();
        readExpected("native_reload_and_notification_program_2", 2, 2);
        poisonThenExecute();
        readExpected("reloaded_cache_restores_program_2", 2, 2);

        // Inactive Mogwai graphs do not receive Renderer::onHotReload. The
        // cached ProgramVersion comparison must independently catch this case.
        edit(3);
        ASSERT_TRUE(device->getProgramManager()->reloadAllPrograms(false));
        poisonThenExecute();
        readExpected("native_reload_without_notification_program_3", 3, 3);
        poisonThenExecute();
        readExpected("inactive_graph_reloaded_cache_restores_program_3", 3, 3);
        context->submit(true);
        evidence["status"] = "passed";
        saveResult();
        std::cout << "NATIVE_ONCE_RELOAD_PASS" << std::endl;
    }
    catch (const std::exception& error)
    {
        evidence["status"] = "failed";
        evidence["error"] = error.what();
        saveResult();
        std::cout << "NATIVE_ONCE_RELOAD_FAIL" << std::endl;
        throw;
    }
    catch (...)
    {
        evidence["status"] = "failed";
        evidence["error"] = "Non-standard exception from native test assertion";
        saveResult();
        std::cout << "NATIVE_ONCE_RELOAD_FAIL" << std::endl;
        throw;
    }
}
}
