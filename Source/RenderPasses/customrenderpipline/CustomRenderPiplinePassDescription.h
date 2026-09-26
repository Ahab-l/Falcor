#pragma once
#include "Falcor.h"
#include "Utils/Properties.h"
#include <nlohmann/json.hpp>

namespace Falcor::CustomRenderPipline
{
class PassDescription
{
public:
    PassDescription(const Properties& props, const std::string& type, const std::set<std::string>& allowed);
    Properties properties() const { return mProperties; }
    const nlohmann::json& options() const { return mOptions; }
    void addShader(ProgramDesc& desc, const std::string& path, const std::string& extra = {}) const;
    nlohmann::json expandResources(const nlohmann::json& resources, bool directions, DefineList& defines) const;
    void validateUniform(const nlohmann::json& definition) const;
    float exposure() const { return 1.f; }
private:
    Properties mProperties;
    nlohmann::json mOptions;
};
}
