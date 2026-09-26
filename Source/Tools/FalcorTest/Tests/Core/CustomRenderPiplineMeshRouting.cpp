#include "Testing/UnitTest.h"
#include "Core/Plugin.h"
#include "RenderGraph/RenderGraph.h"
#include "Scene/SceneBuilder.h"
#include "Scene/Material/StandardMaterial.h"
#include "Utils/Scripting/Scripting.h"
#include <pybind11/pybind11.h>
#include <array>
#include <algorithm>
#include <cstring>
#include <nlohmann/json.hpp>

namespace Falcor
{
namespace
{
ref<Scene> makeRouteScene(const ref<Device>& device)
{
    SceneBuilder builder(device, Settings(), SceneBuilder::Flags::DontMergeMaterials | SceneBuilder::Flags::DontOptimizeMaterials);
    const std::array<uint32_t, 3> indices = {0, 1, 2};
    const std::array<float3, 3> vertices = {float3(-0.8f, -0.5f, 0), float3(-0.1f, -0.5f, 0), float3(-0.45f, 0.4f, 0)};
    const float3 normal(0, 0, 1);
    const float4 tangent(1, 0, 0, 1);
    const std::array<float2, 3> uv = {float2(0, 0), float2(1, 0), float2(0.5f, 1)};
    using Frequency = SceneBuilder::Mesh::AttributeFrequency;
    for (uint32_t i = 0; i < 2; ++i)
    {
        SceneBuilder::Mesh mesh;
        mesh.name = "route-triangle-" + std::to_string(i);
        mesh.faceCount = 1;
        mesh.vertexCount = mesh.indexCount = 3;
        mesh.pIndices = indices.data();
        mesh.topology = Vao::Topology::TriangleList;
        mesh.pMaterial = StandardMaterial::create(device, "route-material-" + std::to_string(i));
        mesh.positions = {vertices.data(), Frequency::Vertex};
        mesh.normals = {&normal, Frequency::Constant};
        mesh.tangents = {&tangent, Frequency::Constant};
        mesh.texCrds = {uv.data(), Frequency::Vertex};
        mesh.useOriginalTangentSpace = true;
        const auto meshID = builder.addMesh(mesh);
        SceneBuilder::Node node;
        node.name = mesh.name;
        node.transform = node.meshBind = node.localToBindPose = float4x4::identity();
        builder.addMeshInstance(builder.addNode(node), meshID);
    }
    auto camera = Camera::create("route-camera");
    camera->setPosition(float3(0, 0, 2));
    camera->setTarget(float3(0));
    camera->setUpVector(float3(0, 1, 0));
    builder.addCamera(camera);
    builder.setSelectedCamera(camera);
    return builder.getScene();
}

pybind11::object routeList(const char* json)
{
    return pybind11::module_::import("json").attr("loads")(json);
}

const char kMeshProperties[] = R"({
        "shader": {"file": "Tests/Scene/SceneRasterDrawList.3d.slang", "vertex": "vsMain", "pixel": "psMain"},
        "colorTargets": [{"name": "color", "format": "RGBA16Float", "slot": 0, "size": [64, 32]}],
        "depthTarget": {"name": "depth", "format": "D32Float", "size": [64, 32]}
})";
}

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

GPU_TEST(CustomRenderPiplineMeshRouteCreation, Device::Type::D3D12)
{
    ASSERT_TRUE(Scripting::isRunning());
    pybind11::gil_scoped_acquire gil;
    PluginManager::instance().loadPluginByName("customrenderpipline");
    const auto module = pybind11::module_::import("falcor.falcor_ext");
    const auto addRoutes = module.attr("customRenderPiplineAddMeshPasses");
    const auto scene = makeRouteScene(ctx.getDevice());
    scene->update(ctx.getRenderContext(), 0.0);
    const auto ids = scene->getRasterInstanceIDs();
    ASSERT_EQ(ids.size(), size_t(2));

    auto graph = RenderGraph::create(ctx.getDevice(), "MeshRouteCreation");
    graph->setScene(scene);
    const auto routeProperties = std::string("\"properties\":") + kMeshProperties;
    const auto routes = routeList((std::string("[") +
        R"({"name":"materialRoute","materials":["route-material-0"],)" + routeProperties + "}," +
        R"({"name":"explicitRoute","instanceIDs":[)" + std::to_string(ids[1]) + "]," + routeProperties + "}]").c_str());
    const auto receipt = addRoutes(pybind11::cast(graph), pybind11::cast(scene), routes).cast<pybind11::list>();
    ASSERT_EQ(receipt.size(), size_t(2));
    EXPECT_EQ(receipt[0]["name"].cast<std::string>(), "materialRoute");
    EXPECT_EQ(receipt[0]["instanceIDs"].cast<pybind11::list>()[0].cast<uint32_t>(), ids[0]);
    EXPECT_EQ(receipt[1]["name"].cast<std::string>(), "explicitRoute");
    EXPECT_EQ(receipt[1]["instanceIDs"].cast<pybind11::list>()[0].cast<uint32_t>(), ids[1]);
    ASSERT_TRUE(graph->doesPassExist("materialRoute"));
    ASSERT_TRUE(graph->doesPassExist("explicitRoute"));
    const auto materialProperties = graph->getPass("materialRoute")->getProperties().toJson();
    const auto explicitProperties = graph->getPass("explicitRoute")->getProperties().toJson();
    EXPECT_EQ(materialProperties.at("instanceIDs").dump(), nlohmann::json::array({ids[0]}).dump());
    EXPECT_EQ(explicitProperties.at("instanceIDs").dump(), nlohmann::json::array({ids[1]}).dump());
}

GPU_TEST(CustomRenderPiplineMeshRouteValidation, Device::Type::D3D12)
{
    ASSERT_TRUE(Scripting::isRunning());
    pybind11::gil_scoped_acquire gil;
    PluginManager::instance().loadPluginByName("customrenderpipline");
    const auto module = pybind11::module_::import("falcor.falcor_ext");
    const auto addRoutes = module.attr("customRenderPiplineAddMeshPasses");
    const auto scene = makeRouteScene(ctx.getDevice());
    scene->update(ctx.getRenderContext(), 0.0);
    const auto ids = scene->getRasterInstanceIDs();
    auto graph = RenderGraph::create(ctx.getDevice(), "MeshRouteValidation");
    graph->setScene(scene);

    const auto expectRejected = [&](const std::string& json)
    {
        const auto routes = routeList(json.c_str());
        EXPECT_THROW(([&]() { addRoutes(pybind11::cast(graph), pybind11::cast(scene), routes); })());
    };
    expectRejected(R"([{"name":"missingSelector","properties":{}}])");
    expectRejected(R"([{"name":"bothSelectors","materials":["route-material-0"],"instanceIDs":[0],"properties":{}}])");
    expectRejected(R"([{"name":"unknownMaterial","materials":["missing"],"properties":{}}])");
    expectRejected((std::string("[") + R"({"name":"overlapA","instanceIDs":[)" + std::to_string(ids[0]) + R"(],"properties":{}},)" +
        R"({"name":"overlapB","instanceIDs":[)" + std::to_string(ids[0]) + R"(],"properties":{}}])").c_str());
    EXPECT_FALSE(graph->doesPassExist("overlapA"));
    EXPECT_FALSE(graph->doesPassExist("overlapB"));
}

GPU_TEST(CustomRenderPiplineMeshRouteExecution, Device::Type::D3D12)
{
    ASSERT_TRUE(Scripting::isRunning());
    pybind11::gil_scoped_acquire gil;
    PluginManager::instance().loadPluginByName("customrenderpipline");
    const auto module = pybind11::module_::import("falcor.falcor_ext");
    const auto addRoutes = module.attr("customRenderPiplineAddMeshPasses");
    const auto scene = makeRouteScene(ctx.getDevice());
    scene->update(ctx.getRenderContext(), 0.0);
    const auto ids = scene->getRasterInstanceIDs();
    ASSERT_EQ(ids.size(), size_t(2));

    auto graph = RenderGraph::create(ctx.getDevice(), "MeshRouteExecution");
    graph->setScene(scene);
    const auto routeJson = std::string("[{\"name\":\"selected\",\"instanceIDs\":[") + std::to_string(ids[1]) +
        "],\"properties\":{\"shader\":{\"file\":\"Tests/Scene/SceneRasterDrawList.3d.slang\",\"vertex\":\"vsMain\",\"pixel\":\"psMain\"},"
        "\"colorTargets\":[{\"name\":\"color\",\"format\":\"R32Uint\",\"slot\":0,\"load\":\"load\",\"size\":[64,32]}],"
        "\"depthTarget\":{\"name\":\"depth\",\"format\":\"D32Float\",\"size\":[64,32]}}}]";
    const auto route = routeList(routeJson.c_str());
    addRoutes(pybind11::cast(graph), pybind11::cast(scene), route);

    const auto color = ctx.getDevice()->createTexture2D(64, 32, ResourceFormat::R32Uint, 1, 1, nullptr,
        ResourceBindFlags::RenderTarget | ResourceBindFlags::ShaderResource);
    graph->setInput("selected.color", color);
    graph->markOutput("selected.color");
    graph->execute(ctx.getRenderContext());

    const auto bytes = ctx.getRenderContext()->readTextureSubresource(color.get(), 0);
    std::vector<uint32_t> pixels(bytes.size() / sizeof(uint32_t));
    std::memcpy(pixels.data(), bytes.data(), bytes.size());
    EXPECT_GT(std::count(pixels.begin(), pixels.end(), ids[1] + 1), 0);
    EXPECT_EQ(std::count(pixels.begin(), pixels.end(), ids[0] + 1), 0);
}
}
