# Retired UE entrypoints/config/transactions are not compiled into this plugin.
# Retired wrappers are archived outside the published shader tree.
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
    Extensions/UEReference/Atmosphere/UESunSetup.cpp
    Extensions/UEReference/Atmosphere/UESunSetup.h
    Extensions/UEReference/Atmosphere/UESunSetupCompat.h
    Extensions/UEReference/Atmosphere/UESunSetupOriginal.inl
    Extensions/UEReference/Atmosphere/UESkyViewSetup.cpp
    Extensions/UEReference/Atmosphere/UESkyViewSetup.h
    Extensions/UEReference/Atmosphere/UESkyViewSetupCompat.h
    Extensions/UEReference/Atmosphere/UESkyViewSetupOriginal.inl
    Extensions/UEReference/Shadows/CSMParameters.slangh
    Extensions/UEReference/Shadows/CSMDepth.3d.slang
    Extensions/UEReference/Shadows/CSMProjection.3d.slang
    Extensions/UEReference/Shadows/UECSMDepth.ush
    Extensions/UEReference/Shadows/UECSMFiltering.ush
    Extensions/UEReference/Shadows/UECSMEncode.ush
    # Independent algorithm assets stay available; old UE graph wrappers are retired.
    CustomRenderPiplineReadback.h
    CustomRenderPiplineRTVProbe.h
    Extensions/UEReference/Materials/RDCGrid.slangh
    Extensions/UEReference/Materials/SourceSkyCapture.3d.slang
    Extensions/UEReference/Atmosphere/SkyLight/CaptureInit.slang
    Extensions/UEReference/Atmosphere/UESkyMaterialHelpers.ush
    Extensions/UEReference/Atmosphere/UESkyMaterialPerspective.ush
    Extensions/UEReference/Atmosphere/UESkyMaterialOriginal.ush
    Extensions/UEReference/Atmosphere/UESkyMaterialSource.json
    Extensions/UEReference/Atmosphere/UESkyMaterialThirdPartyNotice.txt
    Extensions/UEReference/Atmosphere/SkyLight/Platform.slangh
    Extensions/UEReference/Atmosphere/SkyLight/Helpers.slangh
    Extensions/UEReference/Atmosphere/SkyLight/CubeCommon.slangh
    Extensions/UEReference/Atmosphere/SkyLight/CubeDirections.slangh
    Extensions/UEReference/Atmosphere/SkyLight/Downsample.slang
    Extensions/UEReference/Atmosphere/SkyLight/Filter.slang
    Extensions/UEReference/Atmosphere/SkyLight/DiffuseSH.slang
    Extensions/UEReference/Atmosphere/SkyLight/DiffuseSHOriginal.slangh
    Extensions/UEReference/Atmosphere/SkyLight/Fixture.slang
    Extensions/UEReference/Atmosphere/SkyLight/Readback.slang
    Extensions/UEReference/Atmosphere/SkyLight/PreintegratedGF.slang
    Extensions/UEReference/Atmosphere/SkyLight/PreintegratedGFCPUOriginal.inl
    Extensions/UEReference/Atmosphere/SkyLight/PreintegratedGFSource.json
    Extensions/UEReference/Atmosphere/SkyLight/PreintegratedGFSourceNotice.txt
    Schemas/DefaultLit.json
    Schemas/OpaqueModels.json
    Extensions/UEReference/Cases/HairFY1/Lighting.slangh
)

# UE source excerpts retain their original .ush syntax and extension.
set_source_files_properties(
    Extensions/UEReference/Atmosphere/UESkyMaterialHelpers.ush
    Extensions/UEReference/Atmosphere/UESkyMaterialPerspective.ush
    Extensions/UEReference/Atmosphere/UESkyMaterialOriginal.ush
    Extensions/UEReference/Shadows/UECSMDepth.ush
    Extensions/UEReference/Shadows/UECSMFiltering.ush
    Extensions/UEReference/Shadows/UECSMEncode.ush
    PROPERTIES HEADER_FILE_ONLY TRUE
)
# This setting is scoped to the CustomRenderPipline directory.
set(SHADER_EXTENSION_REGEX "\\.(slang|slangh|hlsli|hlsl|ush)$")
target_copy_shaders(customrenderpipline RenderPasses/customrenderpipline)
target_source_group(customrenderpipline "RenderPasses")
