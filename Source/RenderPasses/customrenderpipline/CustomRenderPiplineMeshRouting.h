#pragma once

#include "RenderGraph/RenderGraph.h"
#include "Scene/Scene.h"
#include <nlohmann/json.hpp>

namespace Falcor::CustomRenderPipline
{
/** Create one ordinary CustomRenderPiplineMeshDrawPass for every route.
    The route selectors are resolved against the supplied scene at call time.
    The returned JSON is a deterministic receipt containing each pass name and
    its resolved triangle instance IDs.
*/
nlohmann::ordered_json addMeshPasses(RenderGraph& graph, const ref<Scene>& scene, const nlohmann::ordered_json& routes);
}
