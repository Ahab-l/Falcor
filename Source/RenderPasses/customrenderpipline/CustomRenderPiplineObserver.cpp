#include "CustomRenderPiplineObserver.h"
#include "CustomRenderPiplineReadback.h"
#include "CustomRenderPiplineShaderBindings.h"
#include "Core/Pass/ComputePass.h"
#include <limits>
namespace Falcor::CustomRenderPipline
{
namespace
{
using Json = nlohmann::json;
ref<Resource> observed(RenderGraph& graph,const std::string& name)
{
    const auto outputs = graph.getTopology().outputs;
    FALCOR_CHECK(std::find(outputs.begin(),outputs.end(),name) != outputs.end(), "Output '{}' is not marked in this graph; stage a declaration with the required output",name);
    const auto resource = graph.getOutput(name);
    FALCOR_CHECK(resource, "Observed output has no allocated resource");
    return resource;
}
Json metadata(const std::string& name,const ref<Resource>& resource)
{
    if (const auto texture = resource->asTexture())
    {
        FALCOR_CHECK((texture->getType() == Resource::Type::Texture2D || texture->getType() == Resource::Type::TextureCube) &&
            texture->getSampleCount() == 1 && (texture->getType() != Resource::Type::TextureCube || texture->getArraySize() == 1),
            "Observation requires single-sample Texture2D/array or one Cube");
        const auto kind = texture->getType() == Resource::Type::TextureCube ? "textureCube" : texture->getArraySize() > 1 ? "texture2DArray" : "texture2D";
        Json result={{"name",name},{"kind",kind},{"format",to_string(texture->getFormat())},{"width",texture->getWidth()},{"height",texture->getHeight()}};
        if (texture->getMipCount() > 1 || texture->getArrayLayerCount() > 1)
        { result["mip_count"]=texture->getMipCount();result["array_size"]=texture->getArraySize(); }
        return result;
    }
    const auto buffer = resource->asBuffer();
    FALCOR_CHECK(buffer && buffer->getFormat() == ResourceFormat::Unknown, "Observation requires a raw/structured buffer or texture");
    Json result={{"name",name},{"kind",buffer->getStructSize() ? "structured_buffer" : "raw_buffer"},{"format","Unknown"},{"bytes",buffer->getSize()}};
    if (buffer->getStructSize()) {result["stride"]=buffer->getStructSize();result["count"]=buffer->getElementCount();}
    return result;
}
uint32_t bounded(const Json& value,uint32_t limit,const char* name,bool zero=false)
{
    FALCOR_CHECK(value.is_number_integer() && value >= (zero ? 0 : 1) && value <= limit,"Atlas {} is out of range",name);
    return value.get<uint32_t>();
}
float finite(const Json& v)
{
    FALCOR_CHECK(v.is_number() && std::isfinite(v.get<float>()), "Atlas display numbers must be finite float32");return v.get<float>();
}
uint2 selectedView(const ref<Resource>& resource,const Json& view)
{
    ShaderBindings::keys(view,{"mip","slice"},"observed view");
    const auto texture=resource->asTexture();
    if (!texture) {FALCOR_CHECK(view.empty(),"Buffer does not have texture views");return uint2(0);}
    return uint2(bounded(view.value("mip",Json(0)),texture->getMipCount()-1,"mip",true),
        bounded(view.value("slice",Json(0)),texture->getArrayLayerCount()-1,"slice",true));
}
// A selected Cube face cannot be rebound as a Texture2D SRV. Copy that exact
// subresource to a transient GPU texture for the generic display/depth helpers.
// No readback is uploaded and the source resource is never written.
ref<Texture> displayTexture(RenderContext* context,const ref<Texture>& source,uint2 view)
{
    if (source->getType()==Resource::Type::Texture2D && source->getMipCount()==1 && source->getArraySize()==1) return source;
    const auto flags=ResourceBindFlags::ShaderResource | (isDepthStencilFormat(source->getFormat()) ? ResourceBindFlags::DepthStencil : ResourceBindFlags::None);
    auto selected=source->getDevice()->createTexture2D(source->getWidth(view.x),source->getHeight(view.x),source->getFormat(),1,1,nullptr,flags);
    context->copySubresource(selected.get(),0,source.get(),source->getSubresourceIndex(view.y,view.x));
    return selected;
}
struct DepthPlane { ref<Buffer> buffer;uint32_t pitch,stride; };
DepthPlane copyDepthPlane(RenderContext* context,const ref<Texture>& texture)
{
#if FALCOR_HAS_D3D12
    const auto device = texture->getDevice();
    FALCOR_CHECK(device->getType() == Device::Type::D3D12,"GPU depth observation requires D3D12");
    auto nativeDevice = device->getNativeHandle().as<ID3D12Device*>();
    auto nativeTexture = texture->getNativeHandle().as<ID3D12Resource*>();
    const auto desc = nativeTexture->GetDesc();
    D3D12_PLACED_SUBRESOURCE_FOOTPRINT footprint{};UINT rows;UINT64 rowBytes,total;
    nativeDevice->GetCopyableFootprints(&desc,0,1,0,&footprint,&rows,&rowBytes,&total);
    FALCOR_CHECK(rows == texture->getHeight() && rowBytes % texture->getWidth() == 0 && total <= UINT32_MAX,"Unsupported depth plane footprint");
    const uint32_t stride = uint32_t(rowBytes/texture->getWidth());
    FALCOR_CHECK(stride == 2 || stride == 4 || stride == 8,"Unsupported depth plane stride");
    auto buffer = device->createBuffer((total+3)&~uint64_t(3),ResourceBindFlags::ShaderResource,MemoryType::DeviceLocal);
    context->resourceBarrier(texture.get(),Resource::State::CopySource);
    context->resourceBarrier(buffer.get(),Resource::State::CopyDest);
    context->getLowLevelData()->getResourceCommandEncoder();
    auto commands = context->getLowLevelData()->getCommandBufferNativeHandle().as<ID3D12GraphicsCommandList*>();
    D3D12_TEXTURE_COPY_LOCATION src{},dst{};
    src.pResource = nativeTexture;src.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;src.SubresourceIndex = 0;
    dst.pResource = buffer->getNativeHandle().as<ID3D12Resource*>();dst.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;dst.PlacedFootprint = footprint;
    commands->CopyTextureRegion(&dst,0,0,0,&src,nullptr);
    context->setPendingCommands(true);
    return {buffer,footprint.Footprint.RowPitch,stride};
#else
    FALCOR_THROW("GPU depth observation requires D3D12");
#endif
}
const char* kAtlasShader = R"(
#if ATLAS_KIND == 0
Texture2D<float4> gTexture;
#elif ATLAS_KIND == 1
Texture2D<uint4> gTexture;
#elif ATLAS_KIND == 2
Texture2D<int4> gTexture;
#else
ByteAddressBuffer gRaw;
#endif
RWTexture2D<float4> gAtlas;
cbuffer Params {
 uint2 tileOffset;uint2 tileSize;uint2 sourceExtent;
 uint rawMode;uint byteCount;uint rowPitch;uint pixelStride;
 uint channel;uint colorMode;uint normalizeRange;
 float scale;float bias;float2 limits;
};
[numthreads(8,8,1)] void main(uint3 tid:SV_DispatchThreadID) {
 if(any(tid.xy>=tileSize))return;
 uint2 p=min(uint2(uint(uint64_t(tid.x)*sourceExtent.x/tileSize.x),
                   uint(uint64_t(tid.y)*sourceExtent.y/tileSize.y)),sourceExtent-1);
 float4 value;
#if ATLAS_KIND < 3
 value=float4(gTexture.Load(int3(p,0)));
#elif ATLAS_KIND == 4
 uint offset=p.y*rowPitch+p.x*pixelStride;
 uint bits=gRaw.Load(offset & ~3u);
 float depth=rawMode==4 ? float((bits>>((offset&3)*8))&65535u)/65535.0 : asfloat(bits);
 value=depth.xxxx;
#else
 uint64_t index=uint64_t(p.y)*sourceExtent.x+p.x;
 uint64_t address=index*(rawMode==0 ? 1u : 4u);
 float scalar=0;
 if(address<byteCount) {
  uint offset=uint(address);
  uint bits=gRaw.Load(offset & ~3u);
  scalar=rawMode==0 ? float((bits>>((offset&3)*8))&255u) : rawMode==1 ? float(bits) : rawMode==2 ? float(asint(bits)) : asfloat(bits);
 }
 value=scalar.xxxx;
#endif
 float3 rgb=colorMode!=0 ? value.xyz : value[channel].xxx;
 rgb=rgb*scale+bias;
 if(normalizeRange!=0)rgb=saturate((rgb-limits.x)/(limits.y-limits.x));
 gAtlas[tid.xy+tileOffset]=float4(rgb,colorMode!=0 ? value.w : 1.0);
}
)";
}
Json outputCatalog(RenderGraph& graph)
{
Json result = Json::array();
    for (const auto& name : graph.getTopology().outputs) result.push_back(metadata(name,observed(graph,name)));
    return result;
}
ref<Texture> renderAtlas(RenderGraph& graph,const std::string& serialized)
{
const auto layout = Json::parse(serialized);
    ShaderBindings::keys(layout,{"width","height","tiles"},"atlas layout");
    const uint32_t width = bounded(layout.at("width"),16384,"width"),height = bounded(layout.at("height"),16384,"height");
    FALCOR_CHECK(uint64_t(width)*height <= 16*1024*1024,"Atlas exceeds 16 million pixels");
    const auto& tiles = layout.at("tiles");FALCOR_CHECK(tiles.is_array() && !tiles.empty(),"Atlas needs tiles");
    const auto device = graph.getDevice();auto context = device->getRenderContext();
    auto atlas = device->createTexture2D(width,height,ResourceFormat::RGBA32Float,1,1,nullptr,ResourceBindFlags::ShaderResource | ResourceBindFlags::UnorderedAccess);
    context->clearUAV(atlas->getUAV().get(),float4(0));
    std::set<std::string> names;std::vector<uint4> rectangles;
    std::map<uint32_t,ref<ComputePass>> programs;
    for (const auto& tile : tiles)
    {
        ShaderBindings::keys(tile,{"name","x","y","width","height","display","view"},"atlas tile");
        const auto name = tile.at("name").get<std::string>();
        const auto source = observed(graph,name);metadata(name,source);
        const auto view=selectedView(source,tile.value("view",Json::object()));
        FALCOR_CHECK(names.insert(name+":"+std::to_string(view.x)+":"+std::to_string(view.y)).second,"Duplicate Atlas output view");
        const uint2 offset(bounded(tile.at("x"),width,"x",true),bounded(tile.at("y"),height,"y",true));
        const uint2 size(bounded(tile.at("width"),width,"tile width"),bounded(tile.at("height"),height,"tile height"));
        FALCOR_CHECK(uint64_t(offset.x)+size.x <= width && uint64_t(offset.y)+size.y <= height,"Atlas tile outside bounds");
        for (const auto& r : rectangles) FALCOR_CHECK(offset.x+size.x <= r.x || r.x+r.z <= offset.x || offset.y+size.y <= r.y || r.y+r.w <= offset.y,"Overlapping Atlas tiles");
        rectangles.push_back(uint4(offset,size));
        const auto& display = tile.at("display");ShaderBindings::keys(display,{"mode","channel","scale","bias","minmax"},"atlas display");
        const auto mode = display.at("mode").get<std::string>();
        const uint32_t channel = display.contains("channel") ? bounded(display.at("channel"),3,"channel",true) : 0;
        const float scale = finite(display.at("scale")),bias = finite(display.at("bias"));
        float2 limits(0,1);const bool normalize = display.contains("minmax") && !display.at("minmax").is_null();
        if (normalize)
        {
            const auto& range = display.at("minmax");FALCOR_CHECK(range.is_array() && range.size() == 2,"Invalid Atlas minmax");
            limits = float2(finite(range[0]),finite(range[1]));FALCOR_CHECK(limits.x < limits.y && std::isfinite(limits.y-limits.x),"Atlas minmax must increase within float32 range");
        }
        uint32_t kind = 0,rawMode = 0,byteCount = 0,rowPitch = 0,pixelStride = 0;
        uint2 sourceExtent;
        ref<Buffer> raw;
        ref<Texture> texture = source->asTexture();
        if (texture)
        {
            texture=displayTexture(context,texture,view);
            sourceExtent = uint2(texture->getWidth(),texture->getHeight());const auto format = texture->getFormat();
            if (isDepthStencilFormat(format))
            {
                FALCOR_CHECK(mode == "depth" && channel == 0,"Depth output requires depth display mode");
                const auto plane = copyDepthPlane(context,texture);raw = plane.buffer;rowPitch = plane.pitch;pixelStride = plane.stride;
                kind = 4;rawMode = format == ResourceFormat::D16Unorm ? 4 : 5;
            }
            else
            {
                const auto type = getFormatType(format);kind = type == FormatType::Uint ? 1 : type == FormatType::Sint ? 2 : 0;
                FALCOR_CHECK((kind == 0 && (mode == "color" || mode == "float")) || (kind == 1 && mode == "uint") || (kind == 2 && mode == "sint"),"Atlas texture display type mismatch");
                FALCOR_CHECK(channel < getFormatChannelCount(format) && !(mode == "color" && display.contains("channel")),"Invalid Atlas texture channel");
                FALCOR_CHECK(is_set(texture->getBindFlags(),ResourceBindFlags::ShaderResource),"Observed color texture lacks SRV capability");
            }
        }
        else
        {
            kind = 3;raw = source->asBuffer();FALCOR_CHECK(raw->getSize() <= UINT32_MAX,"Atlas raw buffer exceeds uint32 addressing");
            byteCount = uint32_t(raw->getSize());
            const std::map<std::string,uint32_t> modes = {{"bytes",0},{"uint32",1},{"sint32",2},{"float32",3}};
            FALCOR_CHECK(modes.count(mode) && channel == 0,"Raw display requires an explicit scalar/byte mode");rawMode = modes.at(mode);
            FALCOR_CHECK(rawMode == 0 || byteCount%4 == 0,"Raw scalar buffer needs whole 32-bit elements");
            const uint32_t elements = rawMode == 0 ? byteCount : byteCount/4;
            sourceExtent = uint2(size.x,uint32_t((uint64_t(elements)+size.x-1)/size.x));
            if (raw->getStructSize() || byteCount%4 || !is_set(raw->getBindFlags(),ResourceBindFlags::ShaderResource))
            {
                auto padded = device->createBuffer((uint64_t(byteCount)+3)&~uint64_t(3),ResourceBindFlags::ShaderResource,MemoryType::DeviceLocal);
                context->copyBufferRegion(padded.get(),0,raw.get(),0,byteCount);raw = padded;
            }
        }
        auto& pass = programs[kind];
        if (!pass)
        {
            ProgramDesc desc;desc.addShaderModule().addString(kAtlasShader,"CustomRenderPiplineObserver.slang");desc.csEntry("main").setShaderModel(ShaderModel::SM6_6);
            pass = ComputePass::create(device,desc,DefineList{{"ATLAS_KIND",std::to_string(kind)}});
        }
        auto root = pass->getRootVar();root["gAtlas"] = atlas;
        if (kind < 3) root["gTexture"] = texture;else root["gRaw"] = raw;
        auto params = root["Params"];params["tileOffset"] = offset;params["tileSize"] = size;params["sourceExtent"] = sourceExtent;
        params["channel"] = channel;params["colorMode"] = mode == "color" ? 1u : 0u;params["scale"] = scale;params["bias"] = bias;
        params["normalizeRange"] = normalize ? 1u : 0u;params["limits"] = limits;
        // These members can be removed entirely by specialization for texture views.
        for (const auto& [key,value] : std::map<std::string,uint32_t>{{"rawMode",rawMode},{"byteCount",byteCount},{"rowPitch",rowPitch},{"pixelStride",pixelStride}})
            if (auto var = params.findMember(key);var.isValid()) var = value;
        pass->execute(context,uint3(size,1));
    }
    device->wait();return atlas;
}
}
