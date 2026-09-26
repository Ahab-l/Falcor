#include "Testing/UnitTest.h"
#include "Core/Plugin.h"
#include "RenderGraph/RenderGraph.h"
#include "Utils/Scripting/Scripting.h"
#include <pybind11/pybind11.h>

namespace Falcor
{
GPU_TEST(CustomRenderPiplineMeshRouteBinding, Device::Type::D3D12)
{
    ASSERT_TRUE(Scripting::isRunning());
    pybind11::gil_scoped_acquire gil;
    PluginManager::instance().loadPluginByName("customrenderpipline");
    const auto module = pybind11::module_::import("falcor.falcor_ext");
    ASSERT_TRUE(pybind11::hasattr(module, "customRenderPiplineAddMeshPasses"));
    auto graph = RenderGraph::create(ctx.getDevice(), "MeshRoutes");
    auto addRoutes = module.attr("customRenderPiplineAddMeshPasses");
    EXPECT_THROW(([&]() { addRoutes(pybind11::cast(graph), pybind11::none(), pybind11::list()); })());
}
}

