#include "CustomRenderPiplineNativeGBuffer.h"
#include <fstream>
#include <regex>
#include <set>
#include <nlohmann/json.hpp>

namespace Falcor
{
CustomRenderPiplineGBufferPass::CustomRenderPiplineGBufferPass(ref<Device> device, const Properties& props)
    : RenderPass(device)
{
    for (const auto& [key, value] : props)
        FALCOR_CHECK(key == "definition" || key == "instanceIDs", "Unknown native GBuffer property '{}'", key);
    if (props.has("instanceIDs"))
    {
        const auto ids = props.toJson().at("instanceIDs");
        FALCOR_CHECK(ids.is_array(), "instanceIDs must be an array of uint32 IDs");
        for (const auto& id : ids)
            FALCOR_CHECK(id.is_number_integer() && id >= 0 && id <= UINT32_MAX, "instanceIDs must contain uint32 IDs");
        mInstanceIDs = ids.get<std::vector<uint32_t>>();
    }
    mpState = GraphicsState::create(device);
    mpState->setDepthStencilState(DepthStencilState::create(DepthStencilState::Desc()
        .setDepthEnabled(true).setDepthWriteMask(true).setDepthFunc(ComparisonFunc::LessEqual)));
    loadDefinition(props.get<std::string>("definition", ""));
}

void CustomRenderPiplineGBufferPass::loadDefinition(const std::filesystem::path& inputPath)
{
    using Json = nlohmann::json;
    Json definition = {
        {"shader", "RenderPasses/customrenderpipline/NativeGBuffer.3d.slang"},
        {"attachments", {{{"name", "colorRoughness"}, {"format", "RGBA32Float"}},
                         {{"name", "normal"}, {"format", "RGBA32Float"}}}}
    };
    const auto path = inputPath.empty() ? inputPath : std::filesystem::absolute(inputPath).lexically_normal();
    if (!path.empty())
    {
        std::ifstream stream(path);
        FALCOR_CHECK(stream.good(), "Cannot open GBuffer definition '{}'", path);
        definition = Json::parse(stream);
    }
    FALCOR_CHECK(definition.is_object(), "GBuffer definition must be an object");
    const std::set<std::string> keys = {"shader", "attachments", "defines", "vertexEntry", "pixelEntry", "depthFormat"};
    for (const auto& [key, value] : definition.items())
        FALCOR_CHECK(keys.count(key), "Unknown GBuffer definition field '{}'", key);
    const auto& attachments = definition.at("attachments");
    FALCOR_CHECK(attachments.is_array() && !attachments.empty() && attachments.size() <= 8,
        "GBuffer requires one to eight color attachments");
    std::vector<Attachment> parsed;
    std::set<std::string> names;
    const std::regex identifier("[A-Za-z_][A-Za-z0-9_]*");
    const auto flags = ResourceBindFlags::RenderTarget | ResourceBindFlags::ShaderResource;
    for (const auto& entry : attachments)
    {
        FALCOR_CHECK(entry.is_object() && entry.size() == 2 && entry.contains("name") && entry.contains("format"),
            "GBuffer attachment requires only name and format");
        Attachment attachment{entry.at("name").get<std::string>(), stringToEnum<ResourceFormat>(entry.at("format").get<std::string>())};
        FALCOR_CHECK(std::regex_match(attachment.name, identifier) && attachment.name != "depth" && names.insert(attachment.name).second,
            "GBuffer attachment names must be unique identifiers other than depth");
        FALCOR_CHECK(!isDepthStencilFormat(attachment.format) && (mpDevice->getFormatBindFlags(attachment.format) & flags) == flags,
            "Unsupported GBuffer color attachment format '{}'", to_string(attachment.format));
        parsed.push_back(std::move(attachment));
    }
    const auto depth = stringToEnum<ResourceFormat>(definition.value("depthFormat", std::string("D32Float")));
    FALCOR_CHECK(isDepthStencilFormat(depth) && is_set(mpDevice->getFormatBindFlags(depth), ResourceBindFlags::DepthStencil),
        "Unsupported GBuffer depth format");
    auto shader = std::filesystem::path(definition.at("shader").get<std::string>());
    FALCOR_CHECK(!shader.empty(), "GBuffer shader file must not be empty");
    if (!path.empty() && shader.is_relative()) shader = (path.parent_path() / shader).lexically_normal();
    const auto defines = definition.value("defines", Json::object());
    FALCOR_CHECK(defines.is_object(), "GBuffer defines must be an object");
    DefineList parsedDefines;
    for (const auto& [key, value] : defines.items())
    {
        FALCOR_CHECK(std::regex_match(key, identifier) && (value.is_string() || value.is_number_integer() || value.is_boolean()),
            "GBuffer defines require identifiers and string/integer/boolean values");
        parsedDefines.add(key, value.is_string() ? value.get<std::string>() : value.is_boolean() ? (value.get<bool>() ? "1" : "0") : value.dump());
    }
    const auto vertex = definition.value("vertexEntry", std::string("vsMain"));
    const auto pixel = definition.value("pixelEntry", std::string("psMain"));
    FALCOR_CHECK(std::regex_match(vertex, identifier) && std::regex_match(pixel, identifier), "Invalid GBuffer entry point");
    // Publish parsed settings only after all configuration checks have passed.
    mDefinition = path;
    mAttachments = std::move(parsed);
    mShader = std::move(shader);
    mDepthFormat = depth;
    mDefines = std::move(parsedDefines);
    mVertexEntry = vertex;
    mPixelEntry = pixel;
    mpProgram = nullptr;
    mpVars = nullptr;
    mpFbo = Fbo::create(mpDevice);
    requestRecompile();
}

Properties CustomRenderPiplineGBufferPass::getProperties() const
{
    Properties props;
    if (!mDefinition.empty()) props["definition"] = mDefinition.string();
    auto json = props.toJson();
    if (mInstanceIDs) json["instanceIDs"] = *mInstanceIDs;
    return Properties(json);
}

RenderPassReflection CustomRenderPiplineGBufferPass::reflect(const CompileData& data)
{
    RenderPassReflection result;
    for (const auto& attachment : mAttachments)
        result.addOutput(attachment.name, "Configured GBuffer color attachment").texture2D().format(attachment.format)
            .bindFlags(ResourceBindFlags::RenderTarget | ResourceBindFlags::ShaderResource);
    result.addOutput("depth", "Native scene depth").texture2D().format(mDepthFormat)
        .bindFlags(ResourceBindFlags::DepthStencil | ResourceBindFlags::ShaderResource);
    return result;
}

void CustomRenderPiplineGBufferPass::setScene(RenderContext*, const ref<Scene>& scene)
{
    mpScene = scene;
    mpRasterDrawList = scene && mInstanceIDs ? scene->createRasterDrawList(*mInstanceIDs) : nullptr;
    mpProgram = nullptr;
    mpVars = nullptr;
}

void CustomRenderPiplineGBufferPass::execute(RenderContext* context, const RenderData& data)
{
    for (uint32_t slot = 0; slot < mAttachments.size(); ++slot)
        mpFbo->attachColorTarget(data.getTexture(mAttachments[slot].name), slot);
    mpFbo->attachDepthStencilTarget(data.getTexture("depth"));
    context->clearFbo(mpFbo.get(), float4(0.f), 1.f, 0, FboAttachmentType::All);
    if (!mpScene) return;
    if (is_set(mpScene->getUpdates(), IScene::UpdateFlags::RecompileNeeded))
    {
        mpProgram = nullptr;
        mpVars = nullptr;
    }
    if (!mpProgram)
    {
        ProgramDesc desc;
        desc.addShaderModules(mpScene->getShaderModules());
        desc.addShaderLibrary(mShader).vsEntry(mVertexEntry).psEntry(mPixelEntry);
        desc.addTypeConformances(mpScene->getTypeConformances());
        desc.setShaderModel(ShaderModel::SM6_6);
        auto defines = mpScene->getSceneDefines();
        defines.add(mDefines);
        mpProgram = Program::create(mpDevice, desc, defines);
        mpState->setProgram(mpProgram);
        mpVars = ProgramVars::create(mpDevice, mpProgram.get());
    }
    mpState->setFbo(mpFbo);
    mpScene->rasterize(context, mpState.get(), mpVars.get(), mpRasterDrawList, RasterizerState::CullMode::Back);
}

void CustomRenderPiplineGBufferPass::renderUI(Gui::Widgets& widget)
{
    widget.text(mDefinition.empty() ? "Built-in native material layout" : mDefinition.string());
    auto path = mDefinition;
    bool load = widget.button("Load GBuffer definition") && openFileDialog({}, path);
    if (!mDefinition.empty()) load |= widget.button("Reload GBuffer definition");
    if (load)
    {
        try { loadDefinition(path); }
        catch (const std::exception& e) { logWarning("GBuffer definition rejected: {}", e.what()); }
    }
}
}
