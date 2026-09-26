#include "CustomRenderPiplineShaderPass.h"
#include <cstdlib>
#include "CustomRenderPiplinePassDescription.h"
#include "CustomRenderPiplineShaderBindings.h"
#include "CustomRenderPiplineTextureSubresources.h"
#include "Core/Pass/ComputePass.h"
#include "Core/Pass/FullScreenPass.h"
#include <nlohmann/json.hpp>
#include <regex>

namespace Falcor
{
namespace
{
using Json = nlohmann::json;
using CustomRenderPipline::ShaderBindings::keys;
using CustomRenderPipline::ShaderBindings::member;
using CustomRenderPipline::ShaderBindings::uniform;

bool immutableExecution(const Json& options)
{
    FALCOR_CHECK(!options.contains("execution") || options.at("execution").is_string(),
        "Compute execution must be once or every_frame");
    const auto mode = options.value("execution", std::string("every_frame"));
    FALCOR_CHECK(mode == "once" || mode == "every_frame", "Compute execution must be once or every_frame");
    if (mode != "once") return false;
    const auto& resources = options.at("resources");
    FALCOR_CHECK(resources.is_array() && !resources.empty(), "Compute execution once requires outputs");
    for (const auto& port : resources)
    {
        FALCOR_CHECK(port.is_object() && port.value("direction", std::string()) == "output" && !port.contains("schema"),
            "Compute execution once requires input-free output resources");
        FALCOR_CHECK(port.value("kind", std::string("texture2D")) == "texture2D" &&
            port.value("array_size", Json(1)) == Json(1) && port.value("mip_count", Json(1)) == Json(1) &&
            !port.contains("view") && port.contains("size") && port.at("size").is_array() && port.at("size").size() == 2,
            "Compute execution once requires fixed-size whole single-mip texture2D outputs");
        for (const auto& size : port.at("size"))
            FALCOR_CHECK(size.is_number_integer() && size > 0 && size <= 16384,
                "Compute execution once requires fixed-size whole single-mip texture2D outputs");
    }
    const auto uniforms = options.value("uniforms", Json::object());
    FALCOR_CHECK(uniforms.is_object(), "Compute execution once requires literal uniforms");
    for (const auto& [name, value] : uniforms.items())
        FALCOR_CHECK(value.is_object() && value.contains("value") && !value.contains("source"),
            "Compute execution once requires literal uniforms without dynamic sources");
    return true;
}

uint32_t positive(const Json& value, const char* label)
{
    FALCOR_CHECK(value.is_number_integer() && value > 0 && value <= 0xffffffffull, "{} must be a positive uint32", label);
    return value.get<uint32_t>();
}


void validateDispatch(uint3 threads, uint3 group)
{
    for (size_t i = 0; i < 3; ++i)
        FALCOR_CHECK(group[i] > 0 && threads[i] > 0 &&
            (uint64_t(threads[i]) + group[i] - 1) / group[i] <= 65535 &&
            uint64_t(threads[i]) + group[i] - 1 <= UINT32_MAX,
            "Compute dispatch exceeds the D3D12 group limit or uint32 rounding range");
}


}

struct CustomRenderPiplineShaderPass::Impl
{
    CustomRenderPipline::PassDescription description;
    bool compute;
    bool once = false, cacheValid = false;
    uint64_t dispatchCount = 0;
    // Never expose these GPU allocations through RenderGraph. Outputs may be
    // transient aliases or written by downstream inputOutput passes every frame.
    std::vector<ref<Texture>> cachedOutputs;
    std::vector<ref<Resource>> cachedDestinations;
    ref<const ProgramVersion> cachedProgram;
    struct ResourceKey
    {
        const Resource* resource = nullptr;
        const Texture* texture = nullptr;
        const Buffer* buffer = nullptr;
        ResourceFormat format = ResourceFormat::Unknown;
        uint2 extent = uint2(0);
        uint32_t bytes = 0;
        uint32_t structSize = 0;
        uint32_t elementCount = 0;
        uint32_t arraySize = 1;
        uint32_t mipCount = 1;
        uint32_t sampleCount = 1;

        bool operator==(const ResourceKey& other) const
        {
            return resource == other.resource && texture == other.texture && buffer == other.buffer &&
                format == other.format && all(extent == other.extent) && bytes == other.bytes &&
                structSize == other.structSize && elementCount == other.elementCount &&
                arraySize == other.arraySize && mipCount == other.mipCount && sampleCount == other.sampleCount;
        }
    };
    struct FboAttachmentKey
    {
        ResourceKey resource;
        uint32_t slot = 0;
        uint32_t firstMip = 0;
        uint32_t firstSlice = 0;
        uint32_t sliceCount = 1;

        bool operator==(const FboAttachmentKey& other) const
        {
            return resource == other.resource && slot == other.slot && firstMip == other.firstMip &&
                firstSlice == other.firstSlice && sliceCount == other.sliceCount;
        }
    };
    ref<Fbo> cachedFbo;
    std::vector<ResourceKey> cachedResourceKeys;
    std::vector<FboAttachmentKey> cachedFboKeys;
    void invalidateFboCache()
    {
        cachedFbo = nullptr;
        cachedResourceKeys.clear();
        cachedFboKeys.clear();
    }
    static ResourceKey makeResourceKey(const ref<Resource>& resource)
    {
        ResourceKey key;
        key.resource = resource.get();
        if (const auto texture = resource->asTexture())
        {
            key.texture = texture.get();
            key.format = texture->getFormat();
            key.extent = uint2(texture->getWidth(), texture->getHeight());
            key.arraySize = texture->getArraySize();
            key.mipCount = texture->getMipCount();
            key.sampleCount = texture->getSampleCount();
        }
        else if (const auto buffer = resource->asBuffer())
        {
            key.buffer = buffer.get();
            key.format = buffer->getFormat();
            key.bytes = buffer->getSize();
            key.structSize = buffer->getStructSize();
            key.elementCount = buffer->getElementCount();
        }
        return key;
    }
    void invalidateCache()
    {
        invalidateFboCache();
        cacheValid = false;
        cachedOutputs.clear();
        cachedDestinations.clear();
        cachedProgram = nullptr;
    }
    struct Port
    {
        std::string name, direction, binding;
        ResourceFormat format = ResourceFormat::Unknown;
        CustomRenderPipline::TextureSubresources texture;
        uint2 size = uint2(0);
        std::string relativeTo;
        uint2 divisor = uint2(1), reflectedSize = uint2(0);
        uint2 maxSize = uint2(UINT32_MAX);
        uint32_t bytes = 0, stride = 0, count = 0, slot = 0;
        bool raw = false, optionalBinding = false;
        bool isBuffer() const { return raw || stride != 0; }
        bool hasClear = false, integerClear = false;
        float4 clearFloat = float4(0);
        uint4 clearUint = uint4(0);
        std::array<bool,4> writeMask = {true,true,true,true};
        ResourceBindFlags flags = ResourceBindFlags::ShaderResource;
    };
    std::vector<Port> ports;
    Json uniforms;
    std::map<std::string, ref<Sampler>> samplers;
    std::string extentPort;
    uint3 threads = uint3(0);
    Json groupAxes;
    ref<ComputePass> cs;
    ref<FullScreenPass> fs;
    explicit Impl(const Properties& props, bool c) : description(props,
        c ? "CustomRenderPiplineComputePass" : "CustomRenderPiplineFullscreenPass",
        c ? std::set<std::string>{"shader", "resources", "uniforms", "samplers", "dispatch", "execution"} :
            std::set<std::string>{"shader", "resources", "uniforms", "samplers", "state"}), compute(c) {}
    ShaderVar root() const { return compute ? cs->getRootVar() : fs->getRootVar(); }
    static uint2 divideSize(uint2 size, uint2 divisor)
    {
        // Use uint64 so valid uint32 dimensions/divisors cannot overflow.
        return uint2(uint32_t((uint64_t(size.x) + divisor.x - 1) / divisor.x),
                     uint32_t((uint64_t(size.y) + divisor.y - 1) / divisor.y));
    }
    uint2 resolveSize(const Port& port, const CompileData& data) const
    {
        if (port.relativeTo.empty())
        {
            if (port.size.x && port.size.y) return port.size;
            // Producers own allocation size. Omitted output size means viewport,
            // while omitted inputs accept and inputOutputs inherit upstream size.
            // A consumer cannot silently resize a producer's viewport output.
            if (port.direction == "output") return data.defaultTexDims;
            const auto* field = data.connectedResources.getField(port.name);
            return field ? uint2(field->getWidth(), field->getHeight()) : uint2(0);
        }
        uint2 source = data.defaultTexDims;
        if (port.relativeTo != "$viewport")
        {
            const auto* field = data.connectedResources.getField(port.relativeTo);
            if (!field) return uint2(0); // Falcor's first reflect has no connected fields.
            source = uint2(field->getWidth() ? field->getWidth() : source.x,
                           field->getHeight() ? field->getHeight() : source.y);
        }
        return divideSize(source, port.divisor);
    }
};

CustomRenderPiplineShaderPass::CustomRenderPiplineShaderPass(ref<Device> device, const Properties& props, bool compute)
    : RenderPass(device), mpImpl(std::make_unique<Impl>(props, compute))
{
    auto& p = *mpImpl;
    FALCOR_CHECK(device->getType() == Device::Type::D3D12 && device->isShaderModelSupported(ShaderModel::SM6_6),
        "CustomRenderPipline Shader executors require D3D12 and SM6.6");
    const auto& options = p.description.options();
    if (compute) p.once = immutableExecution(options);
    const auto shader = options.at("shader");
    keys(shader, compute ? std::set<std::string>{"file", "compute", "defines", "floating_point_mode"} :
        std::set<std::string>{"file", "vertex", "pixel", "defines", "floating_point_mode"}, "shader");
    ProgramDesc program;
    FALCOR_CHECK(!shader.contains("floating_point_mode") || shader.at("floating_point_mode").is_string(),
        "Shader floating_point_mode must be a string");
    const auto floatingPointMode = shader.value("floating_point_mode", std::string("default"));
    FALCOR_CHECK(floatingPointMode == "default" || floatingPointMode == "precise",
        "Shader floating_point_mode must be default or precise");
    if (floatingPointMode == "precise") program.setCompilerFlags(SlangCompilerFlags::FloatingPointModePrecise);
    const auto path = shader.at("file").get<std::string>();
    // The default vertex ABI has only SV_Position. Shaders needing varyings
    // declare their own vertex entry and matching pixel input structure.
    const std::string vertex = !compute && !shader.contains("vertex") ?
        "\nfloat4 customRenderPiplineFullscreenVS(float2 position : POSITION) : SV_Position { return float4(position,0,1); }\n" : "";
    p.description.addShader(program, path, vertex);
    program.setShaderModel(ShaderModel::SM6_6);
    if (compute) program.csEntry(shader.value("compute", std::string("main")));
    else
    {
        program.psEntry(shader.value("pixel", std::string("main")));
        program.vsEntry(shader.value("vertex", std::string("customRenderPiplineFullscreenVS")));
    }
    DefineList defines;
    const auto shaderDefines = shader.value("defines", Json::object());
    FALCOR_CHECK(shaderDefines.is_object(), "Shader defines must be an object");
    for (const auto& [name, value] : shaderDefines.items()) defines.add(name, value.get<std::string>());
    const auto& resources = options.at("resources");
    FALCOR_CHECK(resources.is_array() && !resources.empty(), "Shader pass requires resources");
    const auto expanded = p.description.expandResources(resources, true, defines);
    if (compute) p.cs = ComputePass::create(device, program, defines);
    else p.fs = FullScreenPass::create(device, program, defines);
    std::set<std::string> names, bindings;
    std::set<uint32_t> slots;
    for (const auto& resource : expanded)
    {
        keys(resource, {"name", "direction", "binding", "format", "size", "max_size", "slot", "kind", "bytes", "stride", "count", "clear",
            "schema_expanded", "writeMask", "array_size", "mip_count", "view"}, "resource");
        Impl::Port port;
        port.name = resource.at("name").get<std::string>();
        FALCOR_CHECK(std::regex_match(port.name, std::regex("[A-Za-z_][A-Za-z0-9_]*")) && names.insert(port.name).second, "Duplicate or invalid resource name");
        port.direction = resource.at("direction").get<std::string>();
        FALCOR_CHECK(port.direction == "input" || port.direction == "output" || port.direction == "inputOutput", "Invalid resource direction");
        const auto kind = resource.value("kind", std::string("texture2D"));
        FALCOR_CHECK(kind == "texture2D" || kind == "texture2DArray" || kind == "textureCube" || kind == "raw_buffer" || kind == "structured_buffer",
            "Unsupported resource kind");
        port.raw = kind == "raw_buffer";
        if (kind == "structured_buffer")
        {
            FALCOR_CHECK(resource.contains("stride") && resource.contains("count"), "Structured buffer requires stride and count");
            port.stride = positive(resource.at("stride"), "Structured buffer stride");
            FALCOR_CHECK(port.stride % 4 == 0, "Structured buffer stride must be a multiple of four");
            port.count = positive(resource.at("count"), "Structured buffer count");
            const uint64_t byteSize = uint64_t(port.stride) * port.count;
            FALCOR_CHECK(byteSize <= UINT32_MAX, "Structured buffer byte size exceeds uint32");
            port.bytes = uint32_t(byteSize);
        }
        else FALCOR_CHECK(!resource.contains("stride") && !resource.contains("count"), "Only structured buffers may specify stride/count");
        if (resource.contains("max_size"))
        {
            const auto& limit = resource.at("max_size");
            FALCOR_CHECK(!port.isBuffer() && limit.is_array() && limit.size() == 2,"Texture max_size requires two positive uint32 dimensions");
            port.maxSize = uint2(positive(limit[0],"Texture max_size x"),positive(limit[1],"Texture max_size y"));
        }
        const bool mrt = !compute && port.direction != "input";
        if (resource.contains("writeMask"))
        {
            const auto& mask = resource.at("writeMask");
            FALCOR_CHECK(mrt && mask.is_array() && mask.size() == 4 &&
                std::all_of(mask.begin(),mask.end(),[](const auto& v){return v.is_boolean();}),
                "Fullscreen MRT writeMask requires four booleans");
            for (size_t i = 0; i < 4; ++i) port.writeMask[i] = mask[i].get<bool>();
        }
        if (port.isBuffer())
        {
            FALCOR_CHECK(!mrt && !resource.contains("format") && !resource.contains("size") && !resource.contains("clear") &&
                !resource.contains("array_size") && !resource.contains("mip_count") && !resource.contains("view"),
                "Buffers require compute writes, without texture properties");
            if (port.raw)
            {
                port.bytes = positive(resource.at("bytes"), "Raw buffer bytes");
                FALCOR_CHECK(port.bytes % 4 == 0, "Raw buffer byte size must be a multiple of four");
            }
            else FALCOR_CHECK(!resource.contains("bytes"), "Structured buffer uses stride and count, not bytes");
        }
        else
        {
            FALCOR_CHECK(!resource.contains("bytes"), "Texture resource cannot specify bytes");
            port.texture = CustomRenderPipline::TextureSubresources(resource, port.direction == "input");
            FALCOR_CHECK(!mrt || port.texture.sliceCount == 1, "Fullscreen color output must select one layer or Cube face");
            port.format = stringToEnum<ResourceFormat>(resource.at("format").get<std::string>());
            FALCOR_CHECK(port.format != ResourceFormat::Unknown, "Shader resource needs an explicit format");
            if (resource.contains("size"))
            {
                const auto& size = resource.at("size");
                if (size.is_object())
                {
                    keys(size, {"relative_to", "divisor"}, "relative texture size");
                    FALCOR_CHECK(port.direction == "output", "Relative texture size requires an output");
                    port.relativeTo = size.at("relative_to").get<std::string>();
                    FALCOR_CHECK(!port.relativeTo.empty(), "Relative size requires a source");
                    const auto& divisor = size.at("divisor");
                    FALCOR_CHECK(divisor.is_array() && divisor.size() == 2, "Relative size divisor requires two dimensions");
                    port.divisor = uint2(positive(divisor[0], "Size divisor x"), positive(divisor[1], "Size divisor y"));
                }
                else
                {
                    FALCOR_CHECK(size.is_array() && size.size() == 2, "Texture size requires width and height");
                    port.size = uint2(positive(size[0], "Texture width"), positive(size[1], "Texture height"));
                }
            }
            port.texture.validateSize(port.size);
        }
        if (port.direction != "input") port.flags |= mrt ? ResourceBindFlags::RenderTarget : ResourceBindFlags::UnorderedAccess;
        if (!port.isBuffer()) FALCOR_CHECK((device->getFormatBindFlags(port.format) & port.flags) == port.flags, "Unsupported shader resource format/bind flags");
        if (mrt)
        {
            const auto& slot = resource.at("slot");
            FALCOR_CHECK(slot.is_number_integer() && slot >= 0 && slot < 8, "MRT slot must be in [0,7]");
            port.slot = slot.get<uint32_t>();
            FALCOR_CHECK(slots.insert(port.slot).second && !resource.contains("binding"), "Duplicate MRT slot or feedback binding");
            if (port.slot == 0) p.extentPort = port.name;
        }
        else
        {
            FALCOR_CHECK(!resource.contains("slot"), "Only fullscreen color outputs have MRT slots");
            port.binding = resource.at("binding").get<std::string>();
            FALCOR_CHECK(bindings.insert(port.binding).second, "Duplicate shader resource binding");
            port.optionalBinding = resource.value("schema_expanded", false);
            if (!port.optionalBinding || p.root().findMember(port.binding).isValid())
            {
                const auto variable = member(p.root(), port.binding);
                CustomRenderPipline::ShaderBindings::resourceType(variable,port.binding,port.raw,port.format,port.direction == "input",
                    port.texture.dimensions(port.direction == "input"), port.stride);
            }
        }
        if (resource.contains("clear"))
        {
            const auto& clear = resource.at("clear");
            FALCOR_CHECK(port.direction != "input" && clear.is_array() && clear.size() == 4,
                "Clear requires a writable texture and four components");
            port.hasClear = true;
            port.integerClear = isIntegerFormat(port.format);
            FALCOR_CHECK(!port.integerClear || compute, "Integer render-target clear requires a dedicated shader; compute UAV clear is supported");
            for (size_t i = 0; i < 4; ++i)
            {
                if (port.integerClear)
                {
                    const bool signedValue = getFormatType(port.format) == FormatType::Sint;
                    FALCOR_CHECK(clear[i].is_number_integer() && clear[i] >= (signedValue ? Json(INT32_MIN) : Json(0)) &&
                        clear[i] <= (signedValue ? Json(INT32_MAX) : Json(UINT32_MAX)), "Integer clear component out of range");
                    port.clearUint[i] = signedValue ? uint32_t(clear[i].get<int32_t>()) : clear[i].get<uint32_t>();
                }
                else
                {
                    FALCOR_CHECK(clear[i].is_number() && std::isfinite(clear[i].get<float>()), "Clear requires finite numbers");
                    port.clearFloat[i] = clear[i].get<float>();
                }
            }
        }
        p.ports.push_back(std::move(port));
    }
    for (const auto& port : p.ports)
        if (!port.relativeTo.empty() && port.relativeTo != "$viewport")
            FALCOR_CHECK(std::any_of(p.ports.begin(), p.ports.end(), [&](const auto& source) {
                return source.name == port.relativeTo && source.direction == "input" && !source.isBuffer();
            }), "Relative size source '{}' must be a declared read-only texture", port.relativeTo);
    if (compute)
    {
        const auto& dispatch = options.at("dispatch");
        keys(dispatch, {"extent", "threads", "groups"}, "dispatch");
        FALCOR_CHECK(dispatch.size() == 1, "Compute dispatch requires extent, threads or groups");
        if (dispatch.contains("groups"))
        {
            const auto& groups = dispatch.at("groups");
            keys(groups,{"extent","axes"},"dispatch groups");
            p.extentPort = groups.at("extent").get<std::string>();
            p.groupAxes = groups.at("axes");
            FALCOR_CHECK(p.groupAxes.is_array() && p.groupAxes.size() == 3, "Dispatch groups requires three axes");
            for (const auto& axis : p.groupAxes)
                FALCOR_CHECK((axis.is_string() && (axis == "width" || axis == "height" || axis == "layers")) ||
                    (axis.is_number_integer() && axis > 0 && axis <= 65535), "Group axis requires width, height, layers or a count in 1..65535");
        }
        if (dispatch.contains("extent"))
            p.extentPort = dispatch.at("extent").get<std::string>();
        if (!p.extentPort.empty())
        {
            FALCOR_CHECK(std::any_of(p.ports.begin(), p.ports.end(), [&](const auto& port) { return port.name == p.extentPort && !port.isBuffer(); }),
                "Dispatch extent must name a declared texture");
        }
        else
        {
            const auto& threads = dispatch.at("threads");
            FALCOR_CHECK(threads.is_array() && threads.size() == 3, "Dispatch threads needs three components");
            p.threads = uint3(positive(threads[0], "Dispatch x"), positive(threads[1], "Dispatch y"), positive(threads[2], "Dispatch z"));
            validateDispatch(p.threads, p.cs->getThreadGroupSize());
        }
    }
    else
    {
        FALCOR_CHECK(!slots.empty() && *slots.rbegin() == slots.size() - 1, "Fullscreen MRT slots must be contiguous from zero");
        const auto state = options.value("state", Json::object());
        keys(state, {"blend"}, "fullscreen state");
        const auto mode = state.value("blend", std::string("disabled"));
        FALCOR_CHECK(mode == "disabled" || mode == "additive" || mode == "alpha", "Unsupported fullscreen blend");
        BlendState::Desc blend;
        blend.setIndependentBlend(true);
        for (const auto& port : p.ports) if (port.direction != "input")
            blend.setRenderTargetWriteMask(port.slot,port.writeMask[0],port.writeMask[1],port.writeMask[2],port.writeMask[3]);
        for (auto slot : slots)
        {
            if (mode == "disabled") continue;
            using Op = BlendState::BlendOp;
            using Func = BlendState::BlendFunc;
            blend.setRtBlend(slot, true).setRtParams(slot, Op::Add, Op::Add,
                mode == "alpha" ? Func::SrcAlpha : Func::One, mode == "alpha" ? Func::OneMinusSrcAlpha : Func::One,
                Func::One, mode == "alpha" ? Func::OneMinusSrcAlpha : Func::One);
        }
        p.fs->getState()->setBlendState(BlendState::create(blend));
    }
    p.uniforms = options.value("uniforms", Json::object());
    FALCOR_CHECK(p.uniforms.is_object(), "Uniforms must be an object");
    for (const auto& [name, value] : p.uniforms.items())
    {
        FALCOR_CHECK(bindings.insert(name).second, "Duplicate shader binding");
        p.description.validateUniform(value);
        uniform(p.root(), name, value, uint2(1), p.description.exposure());
    }
    const auto samplers = options.value("samplers", Json::object());
    FALCOR_CHECK(samplers.is_object(), "Samplers must be an object");
    for (const auto& [name, value] : samplers.items())
    {
        FALCOR_CHECK(bindings.insert(name).second, "Duplicate shader binding");
        p.samplers[name] = device->createSampler(CustomRenderPipline::ShaderBindings::samplerDesc(value));
        CustomRenderPipline::ShaderBindings::sampler(p.root(), name, p.samplers[name]);
    }
}

CustomRenderPiplineShaderPass::~CustomRenderPiplineShaderPass() = default;
Properties CustomRenderPiplineShaderPass::getProperties() const { return mpImpl->description.properties(); }
uint64_t CustomRenderPiplineShaderPass::getDispatchCount() const { return mpImpl->dispatchCount; }

void CustomRenderPiplineShaderPass::onHotReload(HotReloadFlags reloaded)
{
    if (is_set(reloaded, HotReloadFlags::Program)) mpImpl->invalidateCache();
}

RenderPassReflection CustomRenderPiplineShaderPass::reflect(const CompileData& data)
{
    RenderPassReflection result;
    for (auto& port : mpImpl->ports)
    {
        auto& field = port.direction == "input" ? result.addInput(port.name, "Declared shader input") :
            port.direction == "output" ? result.addOutput(port.name, "Declared shader output") : result.addInputOutput(port.name, "Declared shared resource");
        field.bindFlags(port.flags);
        if (port.raw) field.rawBuffer(port.bytes);
        else if (port.stride) field.structuredBuffer(port.stride, port.count);
        else
        {
            port.reflectedSize = mpImpl->resolveSize(port, data);
            port.texture.validateSize(port.reflectedSize);
            if (port.texture.type == Resource::Type::TextureCube)
                field.textureCube(port.reflectedSize.x, port.reflectedSize.y, port.texture.mipCount, port.texture.arraySize);
            else field.texture2D(port.reflectedSize.x, port.reflectedSize.y, 1, port.texture.mipCount, port.texture.arraySize);
            field.format(port.format);
        }
    }
    return result;
}

void CustomRenderPiplineShaderPass::compile(RenderContext*, const CompileData& data)
{
    // Compile includes viewport changes even for fixed-size generators. Property
    // changes create new instances; native shader edits use Falcor hot reload.
    mpImpl->invalidateCache();
    // Trigger Falcor's reflection retry before allocation. A chain may need more
    // than one retry as upstream resource dimensions become available.
    for (const auto& port : mpImpl->ports)
        if (!port.isBuffer())
        {
            const auto size = mpImpl->resolveSize(port, data);
            FALCOR_CHECK((port.relativeTo.empty() || (size.x && size.y)) && all(size == port.reflectedSize),
                "Resource size for '{}' is awaiting consistent connected reflection", port.name);
        }
}

void CustomRenderPiplineShaderPass::execute(RenderContext* context, const RenderData& data)
{
    auto& p = *mpImpl;
    std::vector<Impl::ResourceKey> resourceKeys;
    resourceKeys.reserve(p.ports.size());
    for (const auto& port : p.ports)
    {
        const auto resource = data[port.name];
        FALCOR_CHECK(resource, "Declared shader resource '{}' is missing", port.name);
        resourceKeys.push_back(Impl::makeResourceKey(resource));
    }
    if (p.once)
    {
        // Retaining destination refs also prevents pointer reuse from hiding a
        // graph allocation replacement. Inactive graphs may miss the host's
        // onHotReload notification.
        bool sameDestinations = p.cachedDestinations.size() == p.ports.size() &&
            p.cachedProgram == p.cs->getProgram()->getActiveVersion();
        for (size_t i = 0; sameDestinations && i < p.ports.size(); ++i)
            sameDestinations = p.cachedDestinations[i] == data[p.ports[i].name];
        if (!sameDestinations) p.invalidateCache();
        if (p.cacheValid)
        {
            for (size_t i = 0; i < p.ports.size(); ++i)
                context->copyResource(data[p.ports[i].name].get(), p.cachedOutputs[i].get());
            return;
        }
        if (p.cachedOutputs.empty())
        {
            // Allocate transactionally so an allocation failure is retryable.
            std::vector<ref<Texture>> outputs;
            std::vector<ref<Resource>> destinations;
            for (const auto& port : p.ports)
            {
                outputs.push_back(mpDevice->createTexture2D(port.size.x, port.size.y, port.format, 1, 1, nullptr, port.flags));
                destinations.push_back(data[port.name]);
            }
            p.cachedOutputs = std::move(outputs);
            p.cachedDestinations = std::move(destinations);
        }
    }
    const bool resourceCacheHit = p.cachedResourceKeys == resourceKeys;
    if (!resourceCacheHit)
    {
        // Graph fanout may alias differently named ports to the same allocation.
        // Validate before changing resource states, clearing or binding any view.
        std::map<const Resource*, std::vector<const Impl::Port*>> aliases;
        for (const auto& port : p.ports)
        {
            const auto resource = data[port.name];
        if (port.isBuffer())
        {
            const auto buffer = resource->asBuffer();
            FALCOR_CHECK(buffer && buffer->getSize() == port.bytes && buffer->getFormat() == ResourceFormat::Unknown &&
                buffer->getStructSize() == port.stride && (!port.stride || buffer->getElementCount() == port.count),
                "Declared shader buffer '{}' size/stride/kind mismatch", port.name);
            FALCOR_CHECK((buffer->getBindFlags() & port.flags) == port.flags,
                "Declared shader buffer '{}' bind flags mismatch", port.name);
        }
        else
        {
            const auto texture = resource->asTexture();
            port.texture.validate(texture, port.format);
            FALCOR_CHECK(texture && texture->getWidth() <= port.maxSize.x && texture->getHeight() <= port.maxSize.y,
                "Declared shader resource '{}' exceeds its max_size contract",port.name);
            if (p.once)
                FALCOR_CHECK(all(uint2(texture->getWidth(), texture->getHeight()) == port.size),
                    "Compute execution once output '{}' differs from its fixed size", port.name);
            if (!port.relativeTo.empty())
            {
                auto sourceSize = data.getDefaultTextureDims();
                if (port.relativeTo != "$viewport")
                {
                    const auto source = data.getTexture(port.relativeTo);
                    FALCOR_CHECK(source, "Relative size source texture is missing");
                    sourceSize = uint2(source->getWidth(), source->getHeight());
                }
                FALCOR_CHECK(all(uint2(texture->getWidth(), texture->getHeight()) == Impl::divideSize(sourceSize, port.divisor)),
                    "Resource '{}' violates its relative size contract", port.name);
            }
        }
        auto& previous = aliases[resource.get()];
        for (const auto* other : previous)
            FALCOR_CHECK((port.direction == "input" && other->direction == "input") ||
                (!port.isBuffer() && !other->isBuffer() && !port.texture.overlaps(other->texture)),
                "Declared shader resource alias creates conflicting access at '{}'", port.name);
        previous.push_back(&port);
        }
    }
    auto root = p.root();
    std::vector<Impl::FboAttachmentKey> fboKeys;
    if (!p.compute)
    {
        for (const auto& port : p.ports) if (port.direction != "input")
        {
            if (port.binding.empty())
            {
                const auto texture = data.getTexture(port.name);
                FALCOR_CHECK(texture, "Declared fullscreen output '{}' must be a texture", port.name);
                fboKeys.push_back({Impl::makeResourceKey(texture), port.slot, port.texture.firstMip,
                    port.texture.firstSlice, port.texture.sliceCount});
            }
        }
    }
    const bool fboCacheHit = p.compute || (p.cachedFbo && resourceCacheHit && p.cachedFboKeys == fboKeys);
    if (!p.compute && !fboCacheHit)
    {
        auto candidate = Fbo::create(mpDevice);
        for (const auto& port : p.ports) if (port.direction != "input" && port.binding.empty())
        {
            const auto texture = data.getTexture(port.name);
            candidate->attachColorTarget(texture, port.slot, port.texture.firstMip, port.texture.firstSlice, port.texture.sliceCount);
        }
        // Publish only after validation and attachment succeed.
        p.cachedFbo = candidate;
        p.cachedFboKeys = std::move(fboKeys);
    }
    if (!resourceCacheHit) p.cachedResourceKeys = std::move(resourceKeys);
    uint2 extent(p.threads.x, p.threads.y);
    uint32_t extentLayers = 1;
    if (!p.extentPort.empty())
    {
        const auto texture = data.getTexture(p.extentPort);
        FALCOR_CHECK(texture, "Shader dispatch/output extent texture is missing");
        const auto& port = *std::find_if(p.ports.begin(), p.ports.end(), [&](const auto& port) { return port.name == p.extentPort; });
        extent = uint2(texture->getWidth(port.texture.firstMip), texture->getHeight(port.texture.firstMip));
        extentLayers = port.texture.sliceCount;
    }
    // Resolve every dispatch/MRT constraint before any writable view is cleared.
    // Runtime dimensions can reject a candidate even when its declaration was valid.
    auto threads = p.extentPort.empty() ? p.threads : uint3(extent, extentLayers);
    if (p.compute)
    {
        if (!p.groupAxes.is_null())
        {
            const auto kernel = p.cs->getThreadGroupSize();
            for (uint32_t i = 0; i < 3; ++i)
            {
                const auto& axis = p.groupAxes[i];
                const uint64_t count = axis.is_string() ? (axis == "width" ? extent.x : axis == "height" ? extent.y : extentLayers) : axis.get<uint32_t>();
                FALCOR_CHECK(count > 0 && count <= 65535 && count * kernel[i] <= UINT32_MAX,
                    "Mapped dispatch exceeds group count or thread range");
                threads[i] = uint32_t(count * kernel[i]);
            }
        }
        validateDispatch(threads, p.cs->getThreadGroupSize());
    }
    else
    {
        for (const auto& port : p.ports) if (port.direction != "input")
        {
            const auto texture = data.getTexture(port.name);
            FALCOR_CHECK(texture->getWidth(port.texture.firstMip) == extent.x && texture->getHeight(port.texture.firstMip) == extent.y,
                "Fullscreen MRT extents must match");
        }
    }
    auto fbo = p.compute ? ref<Fbo>() : p.cachedFbo;
    for (size_t portIndex = 0; portIndex < p.ports.size(); ++portIndex)
    {
        const auto& port = p.ports[portIndex];
        if (port.isBuffer()) member(root, port.binding).setBuffer(data[port.name]->asBuffer());
        else
        {
            const auto texture = p.once ? p.cachedOutputs[portIndex] : data.getTexture(port.name);
            FALCOR_CHECK(texture, "Declared shader texture '{}' is missing", port.name);
            if (!port.binding.empty())
            {
                if (!port.optionalBinding || root.findMember(port.binding).isValid())
                {
                    const auto variable = member(root, port.binding);
                    const auto& view = port.texture;
                    if (port.direction == "input") variable.setSrv(texture->getSRV(view.firstMip, view.viewMipCount, view.firstSlice, view.sliceCount));
                    else variable.setUav(texture->getUAV(view.firstMip, view.firstSlice, view.sliceCount));
                }
            }
            if (port.hasClear)
            {
                const auto& view = port.texture;
                if (port.integerClear) context->clearUAV(texture->getUAV(view.firstMip, view.firstSlice, view.sliceCount).get(), port.clearUint);
                else if (p.compute) context->clearUAV(texture->getUAV(view.firstMip, view.firstSlice, view.sliceCount).get(), port.clearFloat);
                else context->clearRtv(texture->getRTV(view.firstMip, view.firstSlice, view.sliceCount).get(), port.clearFloat);
            }
        }
    }
    for (const auto& [name, value] : p.uniforms.items()) uniform(root, name, value, extent, p.description.exposure());
    if (p.compute)
    {
        if (std::getenv("UE_TRACE_DISPATCH")) logInfo("UE dispatch {}: threads {}, {}, {}",getName(),threads.x,threads.y,threads.z);
        p.cs->execute(context, threads);
        ++p.dispatchCount;
        if (p.once)
        {
            p.cacheValid = true;
            p.cachedProgram = p.cs->getProgram()->getActiveVersion();
            for (size_t i = 0; i < p.ports.size(); ++i)
                context->copyResource(data[p.ports[i].name].get(), p.cachedOutputs[i].get());
        }
    }
    else p.fs->execute(context, fbo);
}
}
