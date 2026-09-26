#pragma once
#include "Falcor.h"
#include <nlohmann/json.hpp>
#include <regex>

namespace Falcor::CustomRenderPipline::ShaderBindings
{
using Json = nlohmann::json;
inline void keys(const Json& object, const std::set<std::string>& allowed, const char* label)
{
    FALCOR_CHECK(object.is_object(), "{} must be an object", label);
    for (const auto& [key, value] : object.items()) FALCOR_CHECK(allowed.count(key), "Unknown {} property '{}'", label, key);
}

inline Sampler::Desc samplerDesc(const Json& value)
{
    keys(value, {"filter", "address", "max_anisotropy"}, "sampler");
    const auto anisotropy = value.value("max_anisotropy", Json(1));
    FALCOR_CHECK(anisotropy.is_number_integer() && anisotropy >= 1 && anisotropy <= 16,
        "Sampler max_anisotropy must be an integer in [1,16]");
    const auto filter = stringToEnum<TextureFilteringMode>(value.value("filter", std::string("Linear")));
    const auto address = stringToEnum<TextureAddressingMode>(value.value("address", std::string("Clamp")));
    return Sampler::Desc().setFilterMode(filter, filter, filter).setAddressingMode(address, address, address)
        .setMaxAnisotropy(anisotropy.get<uint32_t>());
}

inline ShaderVar member(ShaderVar var, const std::string& path)
{
    FALCOR_CHECK(std::regex_match(path, std::regex("[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*)*")), "Invalid shader binding '{}'", path);
    size_t start = 0;
    while (start < path.size())
    {
        const auto end = path.find('.', start);
        var = var.findMember(path.substr(start, end == std::string::npos ? end : end - start));
        FALCOR_CHECK(var.isValid(), "Missing shader binding '{}'", path);
        if (end == std::string::npos) break;
        start = end + 1;
    }
    return var;
}

inline void uniform(ShaderVar root, const std::string& name, const Json& definition, uint2 extent, float exposure)
{
    keys(definition, {"type", "value", "source"}, "uniform");
    FALCOR_CHECK(definition.contains("value") != definition.contains("source"), "Uniform needs exactly one value or source");
    auto value = definition.value("value", Json());
    if (definition.contains("source"))
    {
        const auto source = definition.at("source").get<std::string>();
        FALCOR_CHECK(source == "extent" || source == "preExposure", "Unsupported uniform source '{}'", source);
        value = source == "extent" ? Json::array({extent.x, extent.y}) : Json(exposure);
    }
    const auto type = definition.at("type").get<std::string>();
    const std::map<std::string, ReflectionBasicType::Type> types = {
        {"float", ReflectionBasicType::Type::Float}, {"float2", ReflectionBasicType::Type::Float2},
        {"float3", ReflectionBasicType::Type::Float3}, {"float4", ReflectionBasicType::Type::Float4},
        {"uint", ReflectionBasicType::Type::Uint}, {"uint2", ReflectionBasicType::Type::Uint2},
        {"uint3", ReflectionBasicType::Type::Uint3}, {"uint4", ReflectionBasicType::Type::Uint4},
        {"int", ReflectionBasicType::Type::Int}, {"int2", ReflectionBasicType::Type::Int2},
        {"int3", ReflectionBasicType::Type::Int3}, {"int4", ReflectionBasicType::Type::Int4}, {"bool", ReflectionBasicType::Type::Bool},
    };
    FALCOR_CHECK(types.count(type), "Unsupported uniform type '{}'", type);
    const auto var = member(root, name);
    const auto* basic = var.getType()->asBasicType();
    FALCOR_CHECK(basic && basic->getType() == types.at(type), "Uniform type mismatch at '{}'", name);
    const size_t count = type.back() >= '2' && type.back() <= '4' ? type.back() - '0' : 1;
    if (count == 1) value = Json::array({value});
    FALCOR_CHECK(value.is_array() && value.size() == count, "Uniform component count mismatch at '{}'", name);
    std::array<float, 4> floats = {};
    std::array<uint32_t, 4> uints = {};
    std::array<int32_t, 4> ints = {};
    for (size_t i = 0; i < count; ++i)
    {
        if (type.rfind("float", 0) == 0)
        {
            FALCOR_CHECK(value[i].is_number() && std::isfinite(value[i].get<float>()), "Uniform requires finite float32");
            floats[i] = value[i].get<float>();
        }
        else if (type.rfind("uint", 0) == 0)
        {
            FALCOR_CHECK(value[i].is_number_integer() && value[i] >= 0 && value[i] <= 0xffffffffull, "Uniform requires uint32");
            uints[i] = value[i].get<uint32_t>();
        }
        else if (type.rfind("int", 0) == 0)
        {
            const bool inRange = value[i].is_number_unsigned() ? value[i].get<uint64_t>() <= uint64_t(INT32_MAX) :
                value[i].is_number_integer() && value[i].get<int64_t>() >= INT32_MIN && value[i].get<int64_t>() <= INT32_MAX;
            FALCOR_CHECK(inRange, "Uniform requires int32");
            ints[i] = value[i].get<int32_t>();
        }
        else
        {
            FALCOR_CHECK(value[i].is_boolean(), "Uniform requires bool");
            uints[i] = value[i].get<bool>() ? 1 : 0;
        }
    }
    if (type.rfind("float", 0) == 0) var.setBlob(floats.data(), count * sizeof(float));
    else if (type.rfind("int", 0) == 0) var.setBlob(ints.data(), count * sizeof(int32_t));
    else var.setBlob(uints.data(), count * sizeof(uint32_t));
}
inline void resourceType(ShaderVar variable,const std::string& name,bool raw,ResourceFormat format,bool readOnly,
    ReflectionResourceType::Dimensions dimensions = ReflectionResourceType::Dimensions::Texture2D, uint32_t structSize = 0)
{
    const auto* reflected = variable.getType()->asResourceType();
    using R = ReflectionResourceType;
    const auto resourceKind = structSize ? R::Type::StructuredBuffer : raw ? R::Type::RawBuffer : R::Type::Texture;
    FALCOR_CHECK(reflected && reflected->getType() == resourceKind &&
        (raw || structSize || reflected->getDimensions() == dimensions), "Shader resource kind/dimension mismatch at '{}'",name);
    FALCOR_CHECK(reflected->getShaderAccess() == (readOnly ? R::ShaderAccess::Read : R::ShaderAccess::ReadWrite), "Shader resource access mismatch at '{}'",name);
    if (structSize)
    {
        // Slang labels an ordinary RWStructuredBuffer as Counter even when no
        // counter is used. Append/consume resources have a different contract.
        FALCOR_CHECK(reflected->getStructuredBufferType() == (readOnly ? R::StructuredType::Default : R::StructuredType::Counter),
            "Shader structured buffer requires ordinary StructuredBuffer or RWStructuredBuffer at '{}'", name);
        const auto* element = reflected->getStructType();
        FALCOR_CHECK(element && element->getSlangTypeLayout()->getStride() == structSize,
            "Shader structured buffer stride mismatch at '{}'", name);
    }
    else if (!raw)
    {
        const auto type = getFormatType(format);
        const auto expected = type == FormatType::Uint ? R::ReturnType::Uint : type == FormatType::Sint ? R::ReturnType::Int : R::ReturnType::Float;
        FALCOR_CHECK(reflected->getReturnType() == expected,"Shader resource format type mismatch at '{}'",name);
    }
}
inline void sampler(ShaderVar root,const std::string& name,const ref<Sampler>& value)
{
    const auto var = member(root,name);
    const auto type = var.getType()->asResourceType();
    FALCOR_CHECK(type && type->getType() == ReflectionResourceType::Type::Sampler,
        "Shader sampler '{}' must be a single sampler, without arrays",name);
    var.setSampler(value);
}
}
