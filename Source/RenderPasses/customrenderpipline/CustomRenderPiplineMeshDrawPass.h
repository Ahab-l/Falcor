#pragma once
#include "RenderGraph/RenderPass.h"
#include <memory>
namespace Falcor
{
class CustomRenderPiplineMeshDrawPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(CustomRenderPiplineMeshDrawPass, "CustomRenderPiplineMeshDrawPass", "Filtered Scene indexed draws with independent attachments and state.");
    static ref<CustomRenderPiplineMeshDrawPass> create(ref<Device> d, const Properties& p) { return make_ref<CustomRenderPiplineMeshDrawPass>(d, p); }
    CustomRenderPiplineMeshDrawPass(ref<Device>, const Properties&);
    ~CustomRenderPiplineMeshDrawPass();
    Properties getProperties() const override;
    RenderPassReflection reflect(const CompileData&) override;
    void compile(RenderContext*, const CompileData&) override;
    void setScene(RenderContext*, const ref<Scene>&) override;
    void execute(RenderContext*, const RenderData&) override;
private:
    struct Impl;
    std::unique_ptr<Impl> mpImpl;
};
}
