#pragma once
#include "RenderGraph/RenderGraph.h"
#include <nlohmann/json.hpp>
namespace Falcor::CustomRenderPipline
{
nlohmann::json outputCatalog(RenderGraph&);
ref<Texture> renderAtlas(RenderGraph&,const std::string& layout);
}
