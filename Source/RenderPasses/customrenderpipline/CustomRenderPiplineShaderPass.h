#pragma once
#include "RenderGraph/RenderPass.h"
#include <memory>

namespace Falcor
{
class CustomRenderPiplineShaderPass : public RenderPass
{
public:
    ~CustomRenderPiplineShaderPass();
    Properties getProperties() const override;
    RenderPassReflection reflect(const CompileData&) override;
    void compile(RenderContext*, const CompileData&) override;
    void execute(RenderContext*, const RenderData&) override;
    void onHotReload(HotReloadFlags) override;
    /// Actual Compute dispatches submitted over this pass instance's lifetime.
    uint64_t getDispatchCount() const;
protected:
    CustomRenderPiplineShaderPass(ref<Device>, const Properties&, bool compute);
private:
    struct Impl;
    std::unique_ptr<Impl> mpImpl;
};

class CustomRenderPiplineComputePass : public CustomRenderPiplineShaderPass
{
public:
    FALCOR_PLUGIN_CLASS(CustomRenderPiplineComputePass, "CustomRenderPiplineComputePass", "Declared compute shader, resources, uniforms and dispatch.");
    static ref<CustomRenderPiplineComputePass> create(ref<Device> device, const Properties& props) { return make_ref<CustomRenderPiplineComputePass>(device, props); }
    CustomRenderPiplineComputePass(ref<Device> device, const Properties& props) : CustomRenderPiplineShaderPass(device, props, true) {}
};

class CustomRenderPiplineFullscreenPass : public CustomRenderPiplineShaderPass
{
public:
    FALCOR_PLUGIN_CLASS(CustomRenderPiplineFullscreenPass, "CustomRenderPiplineFullscreenPass", "Declared fullscreen shader, bindings and independent MRTs.");
    static ref<CustomRenderPiplineFullscreenPass> create(ref<Device> device, const Properties& props) { return make_ref<CustomRenderPiplineFullscreenPass>(device, props); }
    CustomRenderPiplineFullscreenPass(ref<Device> device, const Properties& props) : CustomRenderPiplineShaderPass(device, props, false) {}
};
}
