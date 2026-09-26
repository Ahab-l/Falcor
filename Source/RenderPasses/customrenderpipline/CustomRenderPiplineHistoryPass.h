#pragma once
#include "RenderGraph/RenderPass.h"
#include "RenderGraph/RenderGraph.h"
#include <nlohmann/json.hpp>
namespace Falcor
{
class CustomRenderPiplineHistoryPass : public RenderPass
{
public:
    ~CustomRenderPiplineHistoryPass();
    Properties getProperties() const override;
    RenderPassReflection reflect(const CompileData&) override;
    void compile(RenderContext*, const CompileData&) override;
    void execute(RenderContext*, const RenderData&) override;
    void setScene(RenderContext*, const ref<Scene>&) override;
protected:
    CustomRenderPiplineHistoryPass(ref<Device>, const Properties&, bool read);
private:
    struct Impl;
    std::unique_ptr<Impl> mpImpl;
    friend void bindHistoryGraph(RenderGraph&);
    friend nlohmann::json historyGraphInfo(RenderGraph&);
    friend void resetHistoryGraph(RenderGraph&, const std::string&);
};
class CustomRenderPiplineHistoryReadPass : public CustomRenderPiplineHistoryPass
{
public:
    FALCOR_PLUGIN_CLASS(CustomRenderPiplineHistoryReadPass,"CustomRenderPiplineHistoryReadPass","Previous native history writer outputs.");
    static ref<CustomRenderPiplineHistoryReadPass> create(ref<Device> d,const Properties& p) { return make_ref<CustomRenderPiplineHistoryReadPass>(d,p); }
    CustomRenderPiplineHistoryReadPass(ref<Device> d,const Properties& p) : CustomRenderPiplineHistoryPass(d,p,true) {}
};
class CustomRenderPiplineHistoryWritePass : public CustomRenderPiplineHistoryPass
{
public:
    FALCOR_PLUGIN_CLASS(CustomRenderPiplineHistoryWritePass,"CustomRenderPiplineHistoryWritePass","Copy outputs to native history for the next execution.");
    static ref<CustomRenderPiplineHistoryWritePass> create(ref<Device> d,const Properties& p) { return make_ref<CustomRenderPiplineHistoryWritePass>(d,p); }
    CustomRenderPiplineHistoryWritePass(ref<Device> d,const Properties& p) : CustomRenderPiplineHistoryPass(d,p,false) {}
};
void bindHistoryGraph(RenderGraph&);
nlohmann::json historyGraphInfo(RenderGraph&);
void resetHistoryGraph(RenderGraph&, const std::string& key = {});
}
