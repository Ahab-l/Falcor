#pragma once
#include "Falcor.h"
#include "RenderGraph/RenderPass.h"

namespace Falcor
{
/** Configurable MRT writer using the native Scene and material system. */
class CustomRenderPiplineGBufferPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(CustomRenderPiplineGBufferPass, "CustomRenderPiplineGBufferPass",
        "Native scene materials into configurable GBuffer attachments.");
    static ref<CustomRenderPiplineGBufferPass> create(ref<Device> device, const Properties& props)
    { return make_ref<CustomRenderPiplineGBufferPass>(device, props); }
    CustomRenderPiplineGBufferPass(ref<Device> device, const Properties& props);
    Properties getProperties() const override;
    RenderPassReflection reflect(const CompileData& data) override;
    void setScene(RenderContext* context, const ref<Scene>& scene) override;
    void execute(RenderContext* context, const RenderData& data) override;
    void renderUI(Gui::Widgets& widget) override;

private:
    void loadDefinition(const std::filesystem::path& path);
    struct Attachment { std::string name; ResourceFormat format; };
    std::vector<Attachment> mAttachments;
    std::filesystem::path mDefinition, mShader;
    std::string mVertexEntry = "vsMain", mPixelEntry = "psMain";
    DefineList mDefines;
    ResourceFormat mDepthFormat = ResourceFormat::D32Float;
    ref<Scene> mpScene;
    std::optional<std::vector<uint32_t>> mInstanceIDs;
    ref<Scene::RasterDrawList> mpRasterDrawList;
    ref<GraphicsState> mpState;
    ref<Program> mpProgram;
    ref<ProgramVars> mpVars;
    ref<Fbo> mpFbo;
};
}
