#include "Testing/UnitTest.h"
#include "Scene/SceneBuilder.h"
#include "Scene/Material/StandardMaterial.h"
#include <algorithm>
#include <array>
#include <cstring>

namespace Falcor
{
namespace
{
ref<Scene> makeRasterScene(const ref<Device>& device, SceneBuilder::Flags extraFlags)
{
    SceneBuilder builder(device, Settings(), extraFlags | SceneBuilder::Flags::DontMergeMaterials | SceneBuilder::Flags::DontOptimizeMaterials);
    const float3 normal(0, 0, 1);
    const float4 tangent(1, 0, 0, 1);
    const std::array<uint32_t, 3> indices = {0, 1, 2};
    const std::array<float2, 3> uv = {float2(0, 0), float2(1, 0), float2(0.5f, 1)};
    for (uint32_t i = 0; i < 2; ++i)
    {
        const float x = i == 0 ? -0.5f : 0.5f;
        const std::array<float3, 3> vertices = {float3(x-0.3f, -0.4f, 0), float3(x+0.3f, -0.4f, 0), float3(x, 0.4f, 0)};
        SceneBuilder::Mesh mesh;
        mesh.name = "triangle-" + std::to_string(i);
        mesh.faceCount = 1;
        mesh.vertexCount = mesh.indexCount = 3;
        mesh.pIndices = indices.data();
        mesh.topology = Vao::Topology::TriangleList;
        mesh.pMaterial = StandardMaterial::create(device, "material-" + std::to_string(i));
        using Frequency = SceneBuilder::Mesh::AttributeFrequency;
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
    auto camera = Camera::create("raster-camera");
    camera->setPosition(float3(0, 0, 2));
    camera->setTarget(float3(0));
    camera->setUpVector(float3(0, 1, 0));
    camera->setAspectRatio(2.f);
    builder.addCamera(camera);
    builder.setSelectedCamera(camera);
    return builder.getScene();
}

void verifyRasterSelection(GPUUnitTestContext& ctx, SceneBuilder::Flags flags)
{
    auto device = ctx.getDevice();
    auto context = device->getRenderContext();
    auto scene = makeRasterScene(device, flags);
    scene->update(context, 0.0);
    const auto ids = scene->getRasterInstanceIDs();
    ASSERT_EQ(ids.size(), size_t(2));
    auto selected = scene->createRasterDrawList({ids[1], ids[1]});
    EXPECT_EQ(selected->getInstanceIDs().size(), size_t(1));
    EXPECT_EQ(selected->getInstanceIDs()[0], ids[1]);
    EXPECT_EQ(selected->getDrawCount(), 1u);
    EXPECT_EQ(selected->getBatchCount(), 1u);
    auto all = scene->createRasterDrawList(ids);
    auto empty = scene->createRasterDrawList({});
    EXPECT_EQ(empty->getBatchCount(), 0u);
    EXPECT_THROW(scene->createRasterDrawList({uint32_t(-1)}));
    EXPECT_THROW(scene->getRasterInstanceIDs(std::vector<std::string>{"missing"}));
    EXPECT_EQ(scene->getRasterInstanceIDs(std::vector<std::string>{}).size(), size_t(0));
    EXPECT_EQ(scene->getRasterInstanceIDs(std::vector<std::string>{"material-0"}).size(), size_t(1));

    auto color = device->createTexture2D(64, 32, ResourceFormat::R32Uint, 1, 1, nullptr, ResourceBindFlags::RenderTarget);
    auto depth = device->createTexture2D(64, 32, ResourceFormat::D32Float, 1, 1, nullptr, ResourceBindFlags::DepthStencil);
    auto fbo = Fbo::create(device);
    fbo->attachColorTarget(color, 0);
    fbo->attachDepthStencilTarget(depth);
    ProgramDesc desc;
    desc.addShaderModules(scene->getShaderModules());
    desc.addShaderLibrary("Tests/Scene/SceneRasterDrawList.3d.slang").vsEntry("vsMain").psEntry("psMain");
    desc.addTypeConformances(scene->getTypeConformances());
    auto program = Program::create(device, desc, scene->getSceneDefines());
    auto vars = ProgramVars::create(device, program.get());
    auto state = GraphicsState::create(device);
    state->setProgram(program);
    state->setFbo(fbo);
    auto render = [&](const ref<Scene::RasterDrawList>& list)
    {
        context->clearFbo(fbo.get(), float4(0), 1.f, 0, FboAttachmentType::All);
        scene->rasterize(context, state.get(), vars.get(), list);
        const auto bytes = context->readTextureSubresource(color.get(), 0);
        std::vector<uint32_t> pixels(bytes.size()/sizeof(uint32_t));
        std::memcpy(pixels.data(), bytes.data(), bytes.size());
        return pixels;
    };
    const auto full = render(nullptr);
    EXPECT_TRUE(full == render(all));
    auto subset = render(selected);
    EXPECT_GT(std::count(full.begin(), full.end(), ids[0]+1), 0);
    EXPECT_GT(std::count(full.begin(), full.end(), ids[1]+1), 0);
    EXPECT_GT(std::count(subset.begin(), subset.end(), ids[1]+1), 0);
    EXPECT_EQ(std::count(subset.begin(), subset.end(), ids[0]+1), 0);
    const auto blank = render(empty);
    EXPECT_TRUE(std::all_of(blank.begin(), blank.end(), [](uint32_t p) { return p == 0; }));
    EXPECT_TRUE(subset == render(selected));
    EXPECT_EQ(selected->getBuildCount(), uint64_t(1));
    EXPECT_TRUE(full == render(nullptr));
    auto otherScene = makeRasterScene(device, flags);
    EXPECT_THROW(otherScene->rasterize(context, state.get(), vars.get(), selected));

    // A transform with a negative determinant changes the native winding batch.
    auto flip = float4x4::identity();
    flip[0][0] = -1.f;
    scene->updateNodeTransform(scene->getGeometryInstance(ids[1]).globalMatrixID, flip);
    scene->update(context, 1.0);
    auto moved = render(selected);
    EXPECT_GT(std::count(moved.begin(), moved.end(), ids[1]+1), 0);
    EXPECT_EQ(selected->getBuildCount(), uint64_t(2));
    EXPECT_TRUE(render(nullptr) == render(all));
    EXPECT_TRUE(moved == render(selected));
    EXPECT_EQ(selected->getBuildCount(), uint64_t(2));
}
}

GPU_TEST(SceneRasterDrawList16Bit, Device::Type::D3D12) { verifyRasterSelection(ctx, SceneBuilder::Flags::Default); }
GPU_TEST(SceneRasterDrawList32Bit, Device::Type::D3D12) { verifyRasterSelection(ctx, SceneBuilder::Flags::Force32BitIndices); }
GPU_TEST(SceneRasterDrawListNonIndexed, Device::Type::D3D12) { verifyRasterSelection(ctx, SceneBuilder::Flags::NonIndexedVertices); }
}
