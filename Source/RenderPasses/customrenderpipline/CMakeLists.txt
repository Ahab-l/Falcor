# The plugin contains only the reusable customrenderpipline framework. UE
# reference shaders, codecs, schemas and scene-specific pipelines live outside
# this core branch and are not part of the published plugin.
add_plugin(customrenderpipline)
if(WIN32)
    target_link_libraries(customrenderpipline PRIVATE bcrypt)
endif()

target_sources(customrenderpipline PRIVATE
    CustomRenderPiplinePlugin.cpp
    CustomRenderPiplineNativeGBuffer.h
    CustomRenderPiplineNativeGBuffer.cpp
    NativeGBuffer.3d.slang
    NativeGBufferCodec.slangh
    CustomRenderPiplineContentHash.h
    CustomRenderPiplineShaderPass.h
    CustomRenderPiplinePassDescription.h
    CustomRenderPiplinePassDescription.cpp
    CustomRenderPiplineShaderPass.cpp
    CustomRenderPiplineShaderBindings.h
    CustomRenderPiplineTextureSubresources.h
    CustomRenderPiplineMeshDrawPass.h
    CustomRenderPiplineMeshDrawPass.cpp
    CustomRenderPiplineAssetPass.h
    CustomRenderPiplineAssetPass.cpp
    CustomRenderPiplineHistoryPass.h
    CustomRenderPiplineHistoryPass.cpp
    CustomRenderPiplineObserver.h
    CustomRenderPiplineObserver.cpp
    CustomRenderPiplineReadback.h
    CustomRenderPiplineRTVProbe.h
)
# This setting is scoped to the CustomRenderPipline directory.
set(SHADER_EXTENSION_REGEX "\\.(slang|slangh|hlsli|hlsl|ush)$")
target_copy_shaders(customrenderpipline RenderPasses/customrenderpipline)
target_source_group(customrenderpipline "RenderPasses")
