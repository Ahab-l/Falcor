#include "CustomRenderPiplinePassDescription.h"
#include "CustomRenderPiplineShaderBindings.h"

namespace Falcor::CustomRenderPipline
{
PassDescription::PassDescription(const Properties& props, const std::string&, const std::set<std::string>& allowed)
    : mProperties(props), mOptions(props.toJson())
{
    ShaderBindings::keys(mOptions, allowed, "pass");
}
void PassDescription::addShader(ProgramDesc& desc, const std::string& path, const std::string& extra) const
{
    FALCOR_CHECK(!path.empty(), "Pass shader file must not be empty");
    auto& module = desc.addShaderModule();
    module.addFile(path);
    if (!extra.empty()) module.addString(extra, "CustomRenderPiplineFullscreenVertex.slang");
}
nlohmann::json PassDescription::expandResources(const nlohmann::json& resources, bool, DefineList&) const
{
    FALCOR_CHECK(resources.is_array(), "Pass resources must be an array");
    for (const auto& resource : resources)
        FALCOR_CHECK(resource.is_object() && !resource.contains("schema") && !resource.contains("schema_expanded"),
            "Native resources must be explicit; schema macros and schema_expanded are not native pass inputs");
    return resources;
}
void PassDescription::validateUniform(const nlohmann::json& definition) const
{
    if (definition.is_object() && definition.contains("source"))
        FALCOR_CHECK(definition.at("source") == "extent",
            "Native uniform source must be extent; provide effect parameters explicitly as values or resources");
}
}
