#include "CustomRenderPiplineMeshDrawPass.h"
#include "CustomRenderPiplinePassDescription.h"
#include "CustomRenderPiplineShaderBindings.h"
#include "CustomRenderPiplineTextureSubresources.h"

namespace Falcor
{
namespace
{
using Json = nlohmann::json;
// Native raster states indexed by double-sided material and winding order.
using MeshRasterizers = std::array<std::array<ref<RasterizerState>, 2>, 2>;
using namespace CustomRenderPipline::ShaderBindings;
uint8_t byte(const Json& j, const char* name, uint8_t fallback)
{
    if (!j.contains(name)) return fallback;
    const auto& v = j.at(name);
    FALCOR_CHECK(v.is_number_integer() && v >= 0 && v <= 255, "{} must be uint8", name);
    return v.get<uint8_t>();
}
DepthStencilState::StencilOp stencilOp(const std::string& name)
{
    using Op = DepthStencilState::StencilOp;
    const std::map<std::string, Op> ops = {{"Keep",Op::Keep},{"Zero",Op::Zero},{"Replace",Op::Replace},
        {"Invert",Op::Invert},{"Increase",Op::Increase},{"Decrease",Op::Decrease},
        {"IncreaseSaturate",Op::IncreaseSaturate},{"DecreaseSaturate",Op::DecreaseSaturate}};
    FALCOR_CHECK(ops.count(name), "Invalid stencil operation '{}'", name);
    return ops.at(name);
}
}
struct CustomRenderPiplineMeshDrawPass::Impl
{
    CustomRenderPipline::PassDescription description;
    std::optional<std::vector<uint32_t>> instanceIDs;
    std::array<ref<Scene::RasterDrawList>,2> drawLists;
    std::string viewProjectionBinding;
    bool materialCull = true;
    DefineList resourceDefines;
    Json shader, uniforms, filter;
    struct Target
    {
        std::string name;
        ResourceFormat format;
        uint32_t slot = 0;
        bool depth = false, load = false;
        float4 clear = float4(0);
        uint8_t stencil = 0;
        uint2 reflectedSize = uint2(0);
        uint2 size = uint2(0);
        CustomRenderPipline::TextureSubresources subresources;
    };
    std::vector<Target> targets;
    struct Input
    {
        std::string name,binding;
        ResourceFormat format = ResourceFormat::Unknown;
        uint2 size = uint2(0);
        uint32_t bytes = 0, mipCount = 1;
        bool raw = false,optional = false;
    };
    std::vector<Input> inputs;
    std::map<std::string,ref<Sampler>> samplers;
    uint4 viewport = uint4(0);
    std::optional<float4x4> viewProjection;
    ref<Scene> scene;
    IScene::UpdateFlags updateFlags = IScene::UpdateFlags::None;
    sigs::Connection updateFlagsConnection;
    ref<Program> program;
    ref<ProgramVars> vars;
    ref<GraphicsState> state;
    MeshRasterizers rasterizers;
    struct AttachmentKey
    {
        const Texture* texture = nullptr;
        ResourceFormat format = ResourceFormat::Unknown;
        uint32_t slot = 0;
        uint32_t firstMip = 0;
        uint32_t firstSlice = 0;
        uint32_t sliceCount = 1;
        uint2 extent = uint2(0);
        bool depth = false;

        bool operator==(const AttachmentKey& other) const
        {
            return texture == other.texture && format == other.format && slot == other.slot &&
                firstMip == other.firstMip && firstSlice == other.firstSlice && sliceCount == other.sliceCount &&
                all(extent == other.extent) && depth == other.depth;
        }
    };
    struct InputKey
    {
        const Resource* resource = nullptr;
        const Texture* texture = nullptr;
        const Buffer* buffer = nullptr;
        ResourceFormat format = ResourceFormat::Unknown;
        uint2 extent = uint2(0);
        uint32_t bytes = 0;
        uint32_t structSize = 0;
        uint32_t elementCount = 0;
        uint32_t mipCount = 1;
        uint32_t arraySize = 1;
        uint32_t sampleCount = 1;
        bool raw = false;

        bool operator==(const InputKey& other) const
        {
            return resource == other.resource && texture == other.texture && buffer == other.buffer &&
                format == other.format && all(extent == other.extent) && bytes == other.bytes &&
                structSize == other.structSize && elementCount == other.elementCount && mipCount == other.mipCount &&
                arraySize == other.arraySize && sampleCount == other.sampleCount && raw == other.raw;
        }
    };
    ref<Fbo> cachedFbo;
    std::vector<AttachmentKey> cachedAttachmentKeys;
    std::vector<InputKey> cachedInputKeys;
    // The zero-index draws below only force lazy PSO validation. The GSO cache
    // is keyed by the program, FBO description, VAO layout and fixed states,
    // so repeating the probe for every frame only adds command-list work.
    std::optional<Fbo::Desc> probedFboDesc;
    uint32_t drawCount = 0;
    uint32_t programBuildCount = 0;
    std::string diagnostics = "[]";
    explicit Impl(const Properties& p) : description(p, "CustomRenderPiplineMeshDrawPass",
        {"shader","filter","instanceIDs","colorTargets","depthTarget","state","uniforms","resources","samplers","viewport","view_projection","view_projection_binding"})
    {}
    bool reserved(const std::string& name) const
    {
        return name == "gScene" || name.rfind("gScene.",0) == 0;
    }
    void invalidateAttachmentCache(bool resetProbe)
    {
        cachedFbo = nullptr;
        cachedAttachmentKeys.clear();
        cachedInputKeys.clear();
        if (resetProbe) probedFboDesc.reset();
    }
    void prepareNativeDrawLists()
    {
        const auto selected = instanceIDs ? *instanceIDs : scene->getRasterInstanceIDs();
        std::array<std::vector<uint32_t>,2> groups;
        for (uint32_t id : selected)
        {
            FALCOR_CHECK(id < scene->getGeometryInstanceCount(), "Mesh instance ID {} is out of range", id);
            const auto& instance = scene->getGeometryInstance(id);
            FALCOR_CHECK(instance.getType() == GeometryType::TriangleMesh, "Mesh instance {} is not raster triangle geometry", id);
            const auto material = scene->getMaterial(MaterialID::fromSlang(instance.materialID));
            groups[materialCull && material->isDoubleSided() ? 1 : 0].push_back(id);
        }
        for (size_t i = 0; i < groups.size(); ++i)
        {
            std::sort(groups[i].begin(), groups[i].end());
            groups[i].erase(std::unique(groups[i].begin(), groups[i].end()), groups[i].end());
            if (!drawLists[i] || drawLists[i]->getInstanceIDs() != groups[i]) drawLists[i] = scene->createRasterDrawList(groups[i]);
        }
    }
    static uint2 targetSize(const Target& target, const CompileData& data)
    {
        if (target.size.x) return target.size;
        if (!target.load) return data.defaultTexDims;
        const auto* field = data.connectedResources.getField(target.name);
        return field ? uint2(field->getWidth(),field->getHeight()) : uint2(0);
    }
};
CustomRenderPiplineMeshDrawPass::CustomRenderPiplineMeshDrawPass(ref<Device> device, const Properties& props)
    : RenderPass(device), mpImpl(std::make_unique<Impl>(props))
{
    auto& p = *mpImpl;
    FALCOR_CHECK(device->getType() == Device::Type::D3D12 && device->isShaderModelSupported(ShaderModel::SM6_6), "Mesh executor requires D3D12 SM6.6");
    const auto& o = p.description.options();
    {
        FALCOR_CHECK(!o.contains("filter") || (o.at("filter").is_object() && o.at("filter").empty()),
            "Native Mesh selection uses instanceIDs; material/model/tag filters belong to the reference extension");
        FALCOR_CHECK(o.contains("view_projection") == o.contains("view_projection_binding"),
            "Native view_projection requires an explicit view_projection_binding and vice versa");
        if (o.contains("view_projection_binding"))
        {
            p.viewProjectionBinding = o.at("view_projection_binding").get<std::string>();
            FALCOR_CHECK(!p.viewProjectionBinding.empty() && !p.reserved(p.viewProjectionBinding), "Invalid native view projection binding");
        }
        if (o.contains("instanceIDs"))
        {
            const auto& ids = o.at("instanceIDs");
            FALCOR_CHECK(ids.is_array(), "instanceIDs must be a uint32 array");
            p.instanceIDs.emplace();
            for (const auto& id : ids)
            {
                FALCOR_CHECK(id.is_number_integer() && id >= 0 && id <= UINT32_MAX, "instanceIDs requires uint32 values");
                p.instanceIDs->push_back(id.get<uint32_t>());
            }
        }
    }
    if (o.contains("view_projection"))
    {
        const auto& rows = o.at("view_projection");
        FALCOR_CHECK(rows.is_array() && rows.size() == 4, "Mesh view_projection requires four rows");
        float4x4 matrix;
        for (uint32_t row = 0; row < 4; ++row)
        {
            FALCOR_CHECK(rows[row].is_array() && rows[row].size() == 4, "Mesh view_projection requires four values per row");
            for (uint32_t col = 0; col < 4; ++col)
            {
                FALCOR_CHECK(rows[row][col].is_number() && std::isfinite(rows[row][col].get<float>()),
                    "Mesh view_projection requires finite numeric values");
                matrix[row][col] = rows[row][col].get<float>();
            }
        }
        p.viewProjection = matrix;
    }
    if (o.contains("viewport"))
    {
        const auto& v = o.at("viewport");
        FALCOR_CHECK(v.is_array() && v.size() == 4, "Mesh viewport requires x, y, width, height");
        for (uint32_t i = 0; i < 4; ++i)
        {
            FALCOR_CHECK(v[i].is_number_integer() && v[i] >= (i < 2 ? 0 : 1) && v[i] <= 16384, "Mesh viewport must use bounded integer pixels");
            p.viewport[i] = v[i].get<uint32_t>();
        }
    }
    p.shader = o.at("shader");
    keys(p.shader, {"file","vertex","pixel","defines"}, "Mesh shader");
    FALCOR_CHECK(!p.shader.at("file").get<std::string>().empty(), "Mesh shader file must not be empty");
    p.filter = o.value("filter", Json::object());

    p.uniforms = o.value("uniforms", Json::object());
    FALCOR_CHECK(p.uniforms.is_object(), "Mesh uniforms must be an object");
    for (const auto& [name, value] : p.uniforms.items())
        FALCOR_CHECK(!p.reserved(name),
            "Mesh builtins cannot be overridden by uniform '{}'", name);
    std::set<std::string> names;
    std::set<uint32_t> slots;
    BlendState::Desc blend;
    blend.setIndependentBlend(true);
    const auto colors = o.value("colorTargets", Json::array());
    FALCOR_CHECK(colors.is_array(), "colorTargets must be an array");
    auto parseTarget = [&](const Json& t, bool depth)
    {
        keys(t, depth ? std::set<std::string>{"name","format","load","clear","stencilClear","size","kind","array_size","mip_count","view"} :
            std::set<std::string>{"name","format","slot","load","clear","blend","writeMask","size","kind","array_size","mip_count","view"}, "Mesh attachment");
        Impl::Target target;
        target.subresources = CustomRenderPipline::TextureSubresources(t, false);
        FALCOR_CHECK(target.subresources.sliceCount == 1, "Mesh attachments select exactly one face or layer");
        if (t.contains("size"))
        {
            const auto& size = t.at("size");
            FALCOR_CHECK(size.is_array() && size.size() == 2, "Mesh attachment size requires width and height");
            for (uint32_t i = 0; i < 2; ++i)
            {
                FALCOR_CHECK(size[i].is_number_integer() && size[i] > 0 && size[i] <= 16384, "Mesh attachment size out of D3D12 range");
                target.size[i] = size[i].get<uint32_t>();
            }
        }
        target.subresources.validateSize(target.size);
        target.name = t.at("name").get<std::string>();
        FALCOR_CHECK(std::regex_match(target.name,std::regex("[A-Za-z_][A-Za-z0-9_]*")) && names.insert(target.name).second, "Duplicate or invalid Mesh attachment");
        target.format = stringToEnum<ResourceFormat>(t.at("format").get<std::string>());
        target.depth = depth;
        const auto load = t.value("load",std::string("clear"));
        FALCOR_CHECK(load == "clear" || load == "load", "Mesh attachment load must be clear or load");
        target.load = load == "load";
        FALCOR_CHECK(!target.load || (!t.contains("clear") && !t.contains("stencilClear")), "Loaded Mesh attachment cannot specify clear");
        const auto flags = (depth ? ResourceBindFlags::DepthStencil : ResourceBindFlags::RenderTarget) | ResourceBindFlags::ShaderResource;
        FALCOR_CHECK(target.format != ResourceFormat::Unknown && isDepthStencilFormat(target.format) == depth &&
            (device->getFormatBindFlags(target.format) & flags) == flags, "Unsupported Mesh attachment format");
        if (depth)
        {
            const auto clear = t.value("clear", Json(1.0));
            FALCOR_CHECK(clear.is_number() && std::isfinite(clear.get<float>()) && clear >= 0 && clear <= 1, "Depth clear must be in [0,1]");
            target.clear.x = clear.get<float>();
            target.stencil = byte(t,"stencilClear",0);
            FALCOR_CHECK(!t.contains("stencilClear") || isStencilFormat(target.format), "stencilClear requires a stencil attachment");
        }
        else
        {
            const auto& slot = t.at("slot");
            FALCOR_CHECK(slot.is_number_integer() && slot >= 0 && slot < 8, "Mesh MRT slot must be in [0,7]");
            target.slot = slot.get<uint32_t>();
            FALCOR_CHECK(slots.insert(target.slot).second, "Duplicate Mesh MRT slot");
            const auto clear = t.value("clear",Json::array({0,0,0,0}));
            FALCOR_CHECK(clear.is_array() && clear.size() == 4, "Mesh color clear requires four floats");
            for (size_t i = 0; i < 4; ++i)
            {
                FALCOR_CHECK(clear[i].is_number() && std::isfinite(clear[i].get<float>()), "Mesh color clear requires finite floats");
                target.clear[i] = clear[i].get<float>();
            }
            FALCOR_CHECK(target.load || (!isIntegerFormat(target.format)), "Integer RTV clear requires an explicit shader producer");
            const auto mask = t.value("writeMask",Json::array({true,true,true,true}));
            FALCOR_CHECK(mask.is_array() && mask.size() == 4 && std::all_of(mask.begin(),mask.end(),[](const auto& v){return v.is_boolean();}), "Mesh writeMask requires four booleans");
            blend.setRenderTargetWriteMask(target.slot,mask[0].get<bool>(),mask[1].get<bool>(),mask[2].get<bool>(),mask[3].get<bool>());
            const auto mode = t.value("blend",std::string("disabled"));
            FALCOR_CHECK(mode == "disabled" || mode == "additive" || mode == "alpha", "Invalid Mesh blend mode");
            FALCOR_CHECK(mode == "disabled" || !isIntegerFormat(target.format), "Integer MRTs cannot blend");
            if (mode != "disabled")
            {
                using Op = BlendState::BlendOp; using Func = BlendState::BlendFunc;
                blend.setRtBlend(target.slot,true).setRtParams(target.slot,Op::Add,Op::Add,
                    mode == "alpha" ? Func::SrcAlpha : Func::One, mode == "alpha" ? Func::OneMinusSrcAlpha : Func::One,
                    Func::One,mode == "alpha" ? Func::OneMinusSrcAlpha : Func::One);
            }
        }
        p.targets.push_back(target);
    };
    for (const auto& t : colors) parseTarget(t,false);
    FALCOR_CHECK(slots.empty() || *slots.rbegin() == slots.size()-1, "Mesh MRT slots must be contiguous from zero");
    const bool hasDepth = o.contains("depthTarget");
    if (hasDepth) parseTarget(o.at("depthTarget"),true);
    std::set<std::string> bindings;
    auto claimBinding = [&](const std::string& name)
    {
        FALCOR_CHECK(!p.reserved(name),
            "Mesh builtins cannot be overridden by binding '{}'",name);
        FALCOR_CHECK(bindings.insert(name).second,"Duplicate Mesh shader binding '{}'",name);
    };
    if (!p.viewProjectionBinding.empty()) claimBinding(p.viewProjectionBinding);
    for (const auto& [name,value] : p.uniforms.items()) { p.description.validateUniform(value); claimBinding(name); }
    const auto resources = o.value("resources",Json::array());
    FALCOR_CHECK(resources.is_array(),"Mesh resources must be an array");
    std::vector<std::pair<Json,bool>> expanded;
    for (auto r : p.description.expandResources(resources, true, p.resourceDefines))
    {
        const bool optional = r.value("schema_expanded", false);
        r.erase("schema_expanded");
        expanded.emplace_back(std::move(r), optional);
    }
    for (const auto& [r,optional] : expanded)
    {
        keys(r,{"name","binding","direction","format","size","kind","bytes","mip_count"},"Mesh input");
        Impl::Input input;input.optional = optional;
        input.name = r.at("name").get<std::string>();input.binding = r.at("binding").get<std::string>();
        FALCOR_CHECK(std::regex_match(input.name,std::regex("[A-Za-z_][A-Za-z0-9_]*")) && names.insert(input.name).second,"Duplicate or invalid Mesh resource name");
        FALCOR_CHECK(r.value("direction",std::string("input")) == "input","Mesh resources are read-only inputs; writes belong to attachments");
        claimBinding(input.binding);
        const auto kind = r.value("kind",std::string("texture2D"));
        FALCOR_CHECK(kind == "texture2D" || kind == "raw_buffer","Unsupported Mesh input kind");input.raw = kind == "raw_buffer";
        if (input.raw)
        {
            FALCOR_CHECK(!r.contains("format") && !r.contains("size") && !r.contains("mip_count"),"Raw Mesh input uses bytes, not texture shape/mips");
            const auto& bytes = r.at("bytes");
            FALCOR_CHECK(bytes.is_number_integer() && bytes > 0 && bytes <= UINT32_MAX,"Raw Mesh input bytes must be uint32");
            input.bytes = bytes.get<uint32_t>();FALCOR_CHECK(input.bytes%4 == 0,"Raw Mesh input needs whole 32-bit elements");
        }
        else
        {
            FALCOR_CHECK(!r.contains("bytes"),"Texture Mesh input cannot specify bytes");
            input.format = stringToEnum<ResourceFormat>(r.at("format").get<std::string>());
            FALCOR_CHECK(input.format != ResourceFormat::Unknown && !isDepthStencilFormat(input.format) &&
                is_set(device->getFormatBindFlags(input.format),ResourceBindFlags::ShaderResource),"Mesh texture input needs a sampled color/float depth representation");
            if (r.contains("size"))
            {
                const auto& size = r.at("size");FALCOR_CHECK(size.is_array() && size.size() == 2,"Mesh input size requires width/height");
                for (uint32_t i = 0; i < 2; ++i)
                {
                    FALCOR_CHECK(size[i].is_number_integer() && size[i] > 0 && size[i] <= 16384,"Mesh input size out of D3D12 range");
                    input.size[i] = size[i].get<uint32_t>();
                }
            }
            input.mipCount = CustomRenderPipline::TextureSubresources::integer(r.value("mip_count",Json(1)),"mip_count",15);
            CustomRenderPipline::TextureSubresources shape(Json{{"kind","texture2D"},{"mip_count",input.mipCount}},true);
            shape.validateSize(input.size);
        }
        p.inputs.push_back(input);
    }
    const auto samplers = o.value("samplers",Json::object());FALCOR_CHECK(samplers.is_object(),"Mesh samplers must be an object");
    for (const auto& [name,value] : samplers.items())
    {
        claimBinding(name);
        p.samplers[name] = device->createSampler(CustomRenderPipline::ShaderBindings::samplerDesc(value));
    }
    FALCOR_CHECK(!p.targets.empty() && (slots.empty() || p.shader.contains("pixel")), "Mesh pass needs attachments and a pixel entry for color outputs");
    const auto s = o.value("state",Json::object());
    keys(s,{"depth_enabled","depth_func","depth_write","stencil_enabled","stencil_func","stencil_reference","stencil_read_mask",
        "stencil_write_mask","stencil_fail","stencil_depth_fail","stencil_pass","cull_mode"},"Mesh state");
    for (const char* key : {"depth_enabled","depth_write","stencil_enabled"})
        FALCOR_CHECK(!s.contains(key) || s.at(key).is_boolean(), "Mesh {} must be boolean",key);
    const bool depthEnabled = s.value("depth_enabled",hasDepth), depthWrite = s.value("depth_write",hasDepth), stencilEnabled = s.value("stencil_enabled",false);
    FALCOR_CHECK(hasDepth || !(depthEnabled || depthWrite || stencilEnabled), "Mesh depth/stencil state requires depthTarget");
    FALCOR_CHECK(!depthWrite || depthEnabled, "Depth writes require depth testing enabled");
    if (stencilEnabled) FALCOR_CHECK(isStencilFormat(p.targets.back().format), "Stencil requires a stencil attachment");
    auto ds = DepthStencilState::Desc().setDepthEnabled(depthEnabled).setDepthWriteMask(depthWrite)
        .setDepthFunc(stringToEnum<ComparisonFunc>(s.value("depth_func",std::string("LessEqual"))))
        .setStencilEnabled(stencilEnabled).setStencilReadMask(byte(s,"stencil_read_mask",255)).setStencilWriteMask(byte(s,"stencil_write_mask",255));
    ds.setStencilFunc(DepthStencilState::Face::FrontAndBack,stringToEnum<ComparisonFunc>(s.value("stencil_func",std::string("Always"))))
        .setStencilOp(DepthStencilState::Face::FrontAndBack,stencilOp(s.value("stencil_fail",std::string("Keep"))),
            stencilOp(s.value("stencil_depth_fail",std::string("Keep"))),stencilOp(s.value("stencil_pass",std::string("Keep"))));
    p.state = GraphicsState::create(device);
    p.state->setDepthStencilState(DepthStencilState::create(ds));
    p.state->setStencilRef(byte(s,"stencil_reference",0));
    p.state->setBlendState(BlendState::create(blend));
    const auto cull = s.value("cull_mode",std::string("Material"));
    p.materialCull = cull == "Material";
    FALCOR_CHECK(cull == "Material" || cull == "None" || cull == "Front" || cull == "Back", "Invalid Mesh cull mode");
    for (uint32_t sided = 0; sided < 2; ++sided) for (uint32_t ccw = 0; ccw < 2; ++ccw)
        p.rasterizers[sided][ccw] = RasterizerState::create(RasterizerState::Desc().setFrontCounterCW(ccw != 0)
            .setCullMode(cull == "Material" ? (sided ? RasterizerState::CullMode::None : RasterizerState::CullMode::Back) : stringToEnum<RasterizerState::CullMode>(cull)));
}
CustomRenderPiplineMeshDrawPass::~CustomRenderPiplineMeshDrawPass()
{
    if (mpImpl->updateFlagsConnection) mpImpl->updateFlagsConnection->disconnect();
}
Properties CustomRenderPiplineMeshDrawPass::getProperties() const
{
    auto props = mpImpl->description.properties();
    return props;
}
RenderPassReflection CustomRenderPiplineMeshDrawPass::reflect(const CompileData& data)
{
    RenderPassReflection r;
    for (auto& t : mpImpl->targets)
    {
        auto& f = t.load ? r.addInputOutput(t.name,"Loaded Mesh attachment") : r.addOutput(t.name,"Cleared Mesh attachment");
        t.reflectedSize = Impl::targetSize(t,data);
        const auto& s = t.subresources;
        s.validateSize(t.reflectedSize);
        if (s.type == Resource::Type::TextureCube) f.textureCube(t.reflectedSize.x,t.reflectedSize.y,s.mipCount,1);
        else f.texture2D(t.reflectedSize.x,t.reflectedSize.y,1,s.mipCount,s.arraySize);
        f.format(t.format).bindFlags((t.depth ? ResourceBindFlags::DepthStencil : ResourceBindFlags::RenderTarget) | ResourceBindFlags::ShaderResource);
    }
    for (const auto& input : mpImpl->inputs)
    {
        auto& field = r.addInput(input.name,"Declared Mesh shader input").bindFlags(ResourceBindFlags::ShaderResource);
        if (input.raw) field.rawBuffer(input.bytes);else field.texture2D(input.size.x,input.size.y,1,input.mipCount,1).format(input.format);
    }
    return r;
}
void CustomRenderPiplineMeshDrawPass::compile(RenderContext*, const CompileData& data)
{
    mpImpl->invalidateAttachmentCache(true);
    for (const auto& target : mpImpl->targets)
        FALCOR_CHECK(all(target.reflectedSize == Impl::targetSize(target,data)),
            "Mesh attachment '{}' is awaiting consistent connected reflection",target.name);
}
void CustomRenderPiplineMeshDrawPass::setScene(RenderContext*, const ref<Scene>& scene)
{
    auto& p = *mpImpl;
    if (p.updateFlagsConnection) p.updateFlagsConnection->disconnect();
    p.updateFlagsConnection = {};
    p.updateFlags = IScene::UpdateFlags::None;
    p.drawLists = {};
    p.scene = scene; p.program = nullptr; p.vars = nullptr; p.invalidateAttachmentCache(true); p.drawCount = 0; p.diagnostics = "[]";
    if (p.scene)
        p.updateFlagsConnection = p.scene->getUpdateFlagsSignal().connect(
            [this](IScene::UpdateFlags flags) { mpImpl->updateFlags |= flags; });
}
void CustomRenderPiplineMeshDrawPass::execute(RenderContext* context, const RenderData& data)
{
    auto& p = *mpImpl;
    FALCOR_CHECK(p.scene, "Mesh executor requires Scene");

    if (!p.program || is_set(p.updateFlags,IScene::UpdateFlags::RecompileNeeded))
    {
        ProgramDesc desc;
        desc.addShaderModules(p.scene->getShaderModules());
        const auto file = p.shader.at("file").get<std::string>();
        p.description.addShader(desc, file);
        desc.vsEntry(p.shader.at("vertex").get<std::string>());
        if (p.shader.contains("pixel")) desc.psEntry(p.shader.at("pixel").get<std::string>());
        desc.addTypeConformances(p.scene->getTypeConformances()).setShaderModel(ShaderModel::SM6_6);
        auto defines = p.scene->getSceneDefines();
        defines.add(p.resourceDefines);
        const auto values = p.shader.value("defines",Json::object());
        FALCOR_CHECK(values.is_object(), "Mesh defines must be an object");
        for (const auto& [name,value] : values.items()) defines.add(name,value.get<std::string>());
        p.program = Program::create(mpDevice,desc,defines);
        p.vars = ProgramVars::create(mpDevice,p.program.get());
        p.state->setProgram(p.program);
        p.invalidateAttachmentCache(true);
        ++p.programBuildCount;
    }
    p.updateFlags = IScene::UpdateFlags::None;
    auto root = p.vars->getRootVar();
    auto sceneVar = root.findMember("gScene");
    // Scene::rasterize() binds this block even for an empty draw list. Reject a
    // missing native Scene ABI before clearing any attachment, not during draw.
    FALCOR_CHECK(sceneVar.isValid(),
        "Native Mesh shader requires the gScene parameter block; import Scene.Raster or Scene.Scene");
    if (sceneVar.isValid()) p.scene->bindShaderData(sceneVar);
    const auto first = data.getTexture(p.targets.front().name);
    FALCOR_CHECK(first, "Mesh attachment missing");
    const auto firstMip = p.targets.front().subresources.firstMip;
    const uint2 extent(first->getWidth(firstMip),first->getHeight(firstMip));
    const auto vp = p.viewport.z ? p.viewport : uint4(0,0,extent.x,extent.y);
    FALCOR_CHECK(vp.x + vp.z <= extent.x && vp.y + vp.w <= extent.y, "Mesh viewport exceeds attachment extent");
    std::vector<Impl::AttachmentKey> attachmentKeys;
    attachmentKeys.reserve(p.targets.size());
    for (const auto& t : p.targets)
    {
        const auto texture = data.getTexture(t.name);
        const auto& s = t.subresources;
        FALCOR_CHECK(texture, "Mesh attachment missing");
        attachmentKeys.push_back({texture.get(), t.format, t.slot, s.firstMip, s.firstSlice, 1,
            uint2(texture->getWidth(s.firstMip), texture->getHeight(s.firstMip)), t.depth});
    }
    std::vector<Impl::InputKey> inputKeys;
    inputKeys.reserve(p.inputs.size());
    for (const auto& input : p.inputs)
    {
        const auto resource = data[input.name];
        FALCOR_CHECK(resource, "Missing Mesh input '{}'", input.name);
        Impl::InputKey key;
        key.resource = resource.get();
        key.raw = input.raw;
        if (const auto texture = resource->asTexture())
        {
            key.texture = texture.get();
            key.format = texture->getFormat();
            key.extent = uint2(texture->getWidth(), texture->getHeight());
            key.mipCount = texture->getMipCount();
            key.arraySize = texture->getArraySize();
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
        inputKeys.push_back(key);
    }
    const bool cacheHit = p.cachedFbo && p.cachedAttachmentKeys == attachmentKeys && p.cachedInputKeys == inputKeys;
    if (!cacheHit)
    {
        auto candidate = Fbo::create(mpDevice);
        std::map<const Texture*,std::vector<const CustomRenderPipline::TextureSubresources*>> aliases;
        for (size_t i = 0; i < p.targets.size(); ++i)
        {
            const auto& t = p.targets[i];
            const auto texture = data.getTexture(t.name);
            const auto& s = t.subresources;
            s.validate(texture,t.format);
            FALCOR_CHECK(all(uint2(texture->getWidth(),texture->getHeight()) == t.reflectedSize), "Mesh attachment allocation extent mismatch");
            FALCOR_CHECK(texture->getWidth(s.firstMip) == extent.x && texture->getHeight(s.firstMip) == extent.y, "Mesh attachment extents must match");
            for (const auto* other : aliases[texture.get()])
                FALCOR_CHECK(!s.overlaps(*other), "Mesh attachment alias creates conflicting writes");
            aliases[texture.get()].push_back(&s);
            if (t.depth) candidate->attachDepthStencilTarget(texture,s.firstMip,s.firstSlice,1);
            else candidate->attachColorTarget(texture,t.slot,s.firstMip,s.firstSlice,1);
        }
        for (size_t i = 0; i < p.inputs.size(); ++i)
        {
            const auto& input = p.inputs[i];
            const auto resource = data[input.name];
            FALCOR_CHECK(!resource->asTexture() || !aliases.count(resource->asTexture().get()),"Mesh input/attachment alias creates conflicting access");
            if (input.raw)
            {
                const auto buffer=resource->asBuffer();
                FALCOR_CHECK(buffer && buffer->getSize()==input.bytes && buffer->getFormat()==ResourceFormat::Unknown && buffer->getStructSize()==0,
                    "Mesh raw input allocation mismatch: {}",input.name);
            }
            else
            {
                const auto texture=resource->asTexture();
                FALCOR_CHECK(texture && texture->getType()==Resource::Type::Texture2D && texture->getFormat()==input.format &&
                    texture->getArraySize()==1 && texture->getMipCount()==input.mipCount && texture->getSampleCount()==1 &&
                    (!input.size.x || all(uint2(texture->getWidth(),texture->getHeight())==input.size)),
                    "Mesh texture input allocation mismatch: {}",input.name);
            }
        }
        // Publish only after validation and attachment succeed.
        p.cachedFbo = candidate;
        p.cachedAttachmentKeys = std::move(attachmentKeys);
        p.cachedInputKeys = std::move(inputKeys);
    }
    for (const auto& input : p.inputs)
    {
        const auto resource = data[input.name];
        if (input.optional && !root.findMember(input.binding).isValid()) continue;
        const auto var = member(root,input.binding);resourceType(var,input.binding,input.raw,input.format,true);
        if (input.raw) var.setBuffer(resource->asBuffer());else var.setTexture(resource->asTexture());
    }
    for (const auto& [name,value] : p.samplers) sampler(root,name,value);
    {
        if (!p.viewProjectionBinding.empty())
        {
            const auto var = member(root,p.viewProjectionBinding);
            const auto basic = var.getType()->asBasicType();
            FALCOR_CHECK(basic && basic->getType() == ReflectionBasicType::Type::Float4x4,
                "Native view projection binding must have float4x4 type");
            var = *p.viewProjection;
        }
        p.prepareNativeDrawLists();
    }
    for (const auto& [name,value] : p.uniforms.items()) uniform(root,name,value,extent,p.description.exposure());
    p.state->setFbo(p.cachedFbo);
    p.state->setViewport(0,GraphicsState::Viewport(float(vp.x),float(vp.y),float(vp.z),float(vp.w),0.f,1.f));
    // Validate linked GPU state once for each PSO-compatible FBO description.
    // The probe emits no fragments, but submitting the same eight zero-index
    // draws on every frame needlessly increases CPU command recording and GPU
    // queue work. A changed graph layout or shader rebuild resets this cache.
    const bool needProbe = !p.probedFboDesc || !(*p.probedFboDesc == p.cachedFbo->getDesc());
    if (needProbe)
    {
        for (const auto& vao : {p.scene->getMeshVao16(),p.scene->getMeshVao()}) if (vao)
        {
            p.state->setVao(vao);
            for (const auto& sided : p.rasterizers) for (const auto& rasterizer : sided)
            {
                p.state->setRasterizerState(rasterizer);
                context->drawIndexedInstanced(p.state.get(),p.vars.get(),0,1,0,0,0);
            }
        }
        p.probedFboDesc = p.cachedFbo->getDesc();
    }
    FALCOR_CHECK(p.scene->getMeshVao16() || p.scene->getMeshVao(), "Mesh executor requires a Scene triangle VAO");
    for (const auto& t : p.targets) if (!t.load)
    {
        const auto texture = data.getTexture(t.name);
        const auto& s = t.subresources;
        if (t.depth) context->clearDsv(texture->getDSV(s.firstMip,s.firstSlice,1).get(),t.clear.x,t.stencil,true,isStencilFormat(t.format));
        else context->clearRtv(texture->getRTV(s.firstMip,s.firstSlice,1).get(),t.clear);
    }
    p.state->setFbo(p.cachedFbo);
    p.state->setViewport(0,GraphicsState::Viewport(float(vp.x),float(vp.y),float(vp.z),float(vp.w),0.f,1.f));
    p.drawCount = 0;
    for (size_t i = 0; i < p.drawLists.size(); ++i)
    {
        p.scene->rasterize(context,p.state.get(),p.vars.get(),p.drawLists[i],p.rasterizers[i][0],p.rasterizers[i][1]);
        p.drawCount += p.drawLists[i]->getDrawCount();
    }
}
}
