#include "CustomRenderPiplineMeshRouting.h"
#include "Utils/Properties.h"

#include <algorithm>
#include <map>
#include <set>
#include <string>

namespace Falcor::CustomRenderPipline
{
namespace
{
using Json = nlohmann::ordered_json;

void validateKeys(const Json& object, const std::set<std::string>& allowed, const std::string& context)
{
    FALCOR_CHECK(object.is_object(), "{} must be an object", context);
    for (const auto& [key, value] : object.items())
        FALCOR_CHECK(allowed.count(key), "Unknown {} key '{}'", context, key);
}

std::vector<uint32_t> parseInstanceIDs(const Json& value, const std::string& context)
{
    FALCOR_CHECK(value.is_array(), "{} must be an array", context);
    std::vector<uint32_t> ids;
    ids.reserve(value.size());
    for (const auto& item : value)
    {
        FALCOR_CHECK(item.is_number_integer() && item >= 0 && item <= UINT32_MAX,
            "{} must contain uint32 instance IDs", context);
        ids.push_back(item.get<uint32_t>());
    }
    std::sort(ids.begin(), ids.end());
    ids.erase(std::unique(ids.begin(), ids.end()), ids.end());
    return ids;
}

std::vector<std::string> parseMaterials(const Json& value)
{
    FALCOR_CHECK(value.is_array(), "Mesh route materials must be an array");
    std::vector<std::string> materials;
    materials.reserve(value.size());
    for (const auto& item : value)
    {
        FALCOR_CHECK(item.is_string() && !item.get<std::string>().empty(),
            "Mesh route materials must contain non-empty strings");
        materials.push_back(item.get<std::string>());
    }
    return materials;
}

struct PreparedRoute
{
    std::string name;
    std::vector<uint32_t> instanceIDs;
    Json properties;
};
}

nlohmann::ordered_json addMeshPasses(RenderGraph& graph, const ref<Scene>& scene, const Json& routes)
{
    FALCOR_CHECK(scene, "Mesh route helper requires a Scene");
    FALCOR_CHECK(graph.getScene(), "Mesh route helper requires the graph to have a Scene");
    FALCOR_CHECK(graph.getScene().get() == scene.get(), "Mesh route helper graph and Scene must match");
    FALCOR_CHECK(routes.is_array(), "Mesh routes must be an array");

    std::vector<PreparedRoute> prepared;
    prepared.reserve(routes.size());
    std::set<std::string> names;
    std::map<uint32_t, std::string> owners;

    for (const auto& route : routes)
    {
        validateKeys(route, {"name", "materials", "instanceIDs", "properties"}, "Mesh route");
        FALCOR_CHECK(route.contains("name") && route.at("name").is_string() && !route.at("name").get<std::string>().empty(),
            "Mesh route requires a non-empty name");
        const auto name = route.at("name").get<std::string>();
        FALCOR_CHECK(names.insert(name).second, "Duplicate Mesh route name '{}'", name);
        FALCOR_CHECK(!graph.doesPassExist(name), "Mesh route pass '{}' already exists", name);
        FALCOR_CHECK(route.contains("properties") && route.at("properties").is_object(),
            "Mesh route '{}' requires an object 'properties'", name);
        const bool hasMaterials = route.contains("materials");
        const bool hasIDs = route.contains("instanceIDs");
        FALCOR_CHECK(hasMaterials != hasIDs, "Mesh route '{}' requires exactly one of materials or instanceIDs", name);

        std::vector<uint32_t> ids;
        if (hasMaterials)
        {
            ids = scene->getRasterInstanceIDs(parseMaterials(route.at("materials")));
        }
        else
        {
            ids = parseInstanceIDs(route.at("instanceIDs"), "Mesh route instanceIDs");
        }
        // This validates range and triangle-only semantics before any graph mutation.
        scene->createRasterDrawList(ids);
        for (const uint32_t id : ids)
        {
            const auto [it, inserted] = owners.emplace(id, name);
            FALCOR_CHECK(inserted, "Mesh instance {} belongs to both routes '{}' and '{}'", id, it->second, name);
        }

        Json properties = route.at("properties");
        FALCOR_CHECK(!properties.contains("instanceIDs"),
            "Mesh route '{}' must not put instanceIDs inside properties; use the route selector", name);
        properties["instanceIDs"] = ids;
        prepared.push_back({name, std::move(ids), std::move(properties)});
    }

    std::vector<std::string> created;
    try
    {
        for (const auto& route : prepared)
        {
            const auto properties = nlohmann::json::parse(route.properties.dump());
            auto pass = graph.createPass(route.name, "CustomRenderPiplineMeshDrawPass", Properties(properties));
            FALCOR_CHECK(pass, "Failed to create Mesh route pass '{}'", route.name);
            created.push_back(route.name);
        }
    }
    catch (...)
    {
        for (auto it = created.rbegin(); it != created.rend(); ++it)
            graph.removePass(*it);
        throw;
    }

    Json receipt = Json::array();
    for (const auto& route : prepared)
        receipt.push_back({{"name", route.name}, {"instanceCount", route.instanceIDs.size()}, {"instanceIDs", route.instanceIDs}});
    return receipt;
}
}
