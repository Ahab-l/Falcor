#pragma once
#include "RenderGraph/RenderPass.h"
#include <memory>

namespace Falcor
{
class CustomRenderPiplineAssetPass : public RenderPass
{
public:
    FALCOR_PLUGIN_CLASS(CustomRenderPiplineAssetPass, "CustomRenderPiplineAssetPass", "Immutable file textures and raw buffers as declared graph outputs.");
    static ref<CustomRenderPiplineAssetPass> create(ref<Device> device, const Properties& props) { return make_ref<CustomRenderPiplineAssetPass>(device, props); }
    CustomRenderPiplineAssetPass(ref<Device>, const Properties&);
    ~CustomRenderPiplineAssetPass();
    Properties getProperties() const override;
    RenderPassReflection reflect(const CompileData&) override;
    void execute(RenderContext*, const RenderData&) override;
private:
    struct Impl;
    std::unique_ptr<Impl> mpImpl;
};
}
