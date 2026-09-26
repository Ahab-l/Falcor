#include "CustomRenderPiplineNativeGBuffer.h"
#include "CustomRenderPiplineShaderPass.h"
#include "CustomRenderPiplineMeshDrawPass.h"
#include "CustomRenderPiplineAssetPass.h"
#include "CustomRenderPiplineHistoryPass.h"
#include "CustomRenderPiplineObserver.h"
#include "CustomRenderPiplineReadback.h"
#include "CustomRenderPiplineRTVProbe.h"
#include "Extensions/UEReference/Atmosphere/UESunSetup.h"
#include "Utils/Scripting/ScriptBindings.h"
#include "Utils/Timing/Clock.h"
#include <nlohmann/json.hpp>

namespace
{
pybind11::dict depthStencilReadbackToPython(const Falcor::CustomRenderPipline::DepthStencilReadback& result)
{
    pybind11::dict value;
    value["width"] = result.dimensions.x;
    value["height"] = result.dimensions.y;
    for (uint32_t plane = 0; plane < 2; ++plane)
    {
        const auto name = plane == 0 ? std::string("depth") : std::string("stencil");
        value[name.c_str()] = pybind11::bytes(reinterpret_cast<const char*>(result.planes[plane].data()), result.planes[plane].size());
        value[(name + "_row_bytes").c_str()] = result.rowBytes[plane];
        value[(name + "_native_format").c_str()] = result.nativeFormats[plane];
    }
    return value;
}
}

// Only native framework nodes are registered. Retired reference source and
// algorithms remain archived/unbuilt; they are not a runtime compatibility API.
extern "C" FALCOR_API_EXPORT void registerPlugin(Falcor::PluginRegistry& registry)
{
    registry.registerClass<Falcor::RenderPass, Falcor::CustomRenderPiplineGBufferPass>();
    registry.registerClass<Falcor::RenderPass, Falcor::CustomRenderPiplineComputePass>();
    registry.registerClass<Falcor::RenderPass, Falcor::CustomRenderPiplineFullscreenPass>();
    registry.registerClass<Falcor::RenderPass, Falcor::CustomRenderPiplineMeshDrawPass>();
    registry.registerClass<Falcor::RenderPass, Falcor::CustomRenderPiplineAssetPass>();
    registry.registerClass<Falcor::RenderPass, Falcor::CustomRenderPiplineHistoryReadPass>();
    registry.registerClass<Falcor::RenderPass, Falcor::CustomRenderPiplineHistoryWritePass>();
    Falcor::ScriptBindings::registerBinding([](pybind11::module& m)
    {
        m.def("customRenderPiplineHistoryInfo", [](Falcor::RenderGraph& graph) { return Falcor::historyGraphInfo(graph).dump(); });
        m.def("customRenderPiplineBindHistory", &Falcor::bindHistoryGraph, pybind11::arg("graph"));
        m.def("customRenderPiplineResetHistory", &Falcor::resetHistoryGraph, pybind11::arg("graph"), pybind11::arg("key") = "");
        m.def("customRenderPiplineClockTime", [](const Falcor::Clock& clock) { return clock.getTime(); });
        m.def("customRenderPiplineComputeDispatchCount", [](const Falcor::RenderGraph& graph, const std::string& name) {
            const auto* pass = dynamic_cast<const Falcor::CustomRenderPiplineComputePass*>(graph.getPass(name).get());
            FALCOR_CHECK(pass, "Compute dispatch count requires a CustomRenderPiplineComputePass node");
            return pass->getDispatchCount();
        }, pybind11::arg("graph"), pybind11::arg("name"));
        m.def("customRenderPiplineOutputCatalog", [](Falcor::RenderGraph& graph) { return Falcor::CustomRenderPipline::outputCatalog(graph).dump(); });
        m.def("customRenderPiplineRenderAtlas", &Falcor::CustomRenderPipline::renderAtlas);
        m.def("customRenderPiplineProbeRTV", [](const Falcor::ref<Falcor::RenderGraph>& graph, const std::vector<float>& values)
        {
            FALCOR_CHECK(graph, "RTV probe requires a graph device");
            const auto result = Falcor::CustomRenderPipline::probeRTV(graph->getDevice(), values);
            pybind11::dict output;
            output["count"] = values.size();
            const std::array<const char*, 5> names = {"rgb10a2", "bgra8", "float32", "srgb_decode", "srgb_codes"};
            for (uint32_t index = 0; index < names.size(); ++index)
                output[names[index]] = pybind11::bytes(reinterpret_cast<const char*>(result[index].data()), result[index].size());
            return output;
        });
        using DepthReadTask = Falcor::CustomRenderPipline::DepthStencilReadbackTask;
        pybind11::class_<DepthReadTask, DepthReadTask::SharedPtr>(m, "DepthStencilReadbackTask")
            .def_property_readonly("ready", &DepthReadTask::isReady)
            .def_property_readonly("staging_bytes", &DepthReadTask::getStagingSize)
            .def_property_readonly("byte_size", &DepthReadTask::getDataSize)
            .def("result", [](const DepthReadTask& task)
            {
                return depthStencilReadbackToPython(task.getDataNonBlocking());
            }, "Return exact compact native depth/stencil plane bytes only when ready; never waits for the GPU.");
        m.def("customRenderPiplineReadDepthStencilAsync",
            [](const Falcor::ref<Falcor::Texture>& texture, uint32_t mip, uint32_t slice, uint64_t maxBytes)
            {
                FALCOR_CHECK(texture, "CustomRenderPipline depth/stencil readback requires a texture");
                return Falcor::CustomRenderPipline::readDepthStencilAsync(
                    texture->getDevice()->getRenderContext(), texture.get(), mip, slice, maxBytes
                );
            },
            pybind11::arg("texture"), pybind11::arg("mip") = 0, pybind11::arg("slice") = 0,
            pybind11::arg("max_bytes") = uint64_t(64 * 1024 * 1024));
        m.def("customRenderPiplineReadDepthStencil", [](const Falcor::ref<Falcor::Texture>& texture, uint32_t mip, uint32_t slice)
        {
            FALCOR_CHECK(texture, "CustomRenderPipline depth/stencil readback requires a texture");
            const auto result = Falcor::CustomRenderPipline::readDepthStencil(texture->getDevice()->getRenderContext(), texture.get(), mip, slice);
            return depthStencilReadbackToPython(result);
        }, pybind11::arg("texture"), pybind11::arg("mip") = 0, pybind11::arg("slice") = 0);
        // Independent Sun math is retained, not the old UE render graph.
        m.def("ueReferenceSourceSun", [](const std::string& settings) {
            return Falcor::CustomRenderPipline::SunSetup::evaluate(nlohmann::json::parse(settings)).dump();
        });
    });
}
