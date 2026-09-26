# customrenderpipline core

This plugin contains the reusable framework for custom material/G-buffer
layouts, composable RenderGraph passes, resource/history inputs, mesh draw
selection, output observation, and asynchronous readback.

The plugin deliberately does not contain a concrete lighting, atmosphere,
targetmap, or UE compatibility pipeline. Those are consumers of this API and
can be kept in a separate application repository.

Registered pass types:

- `CustomRenderPiplineGBufferPass`
- `CustomRenderPiplineComputePass`
- `CustomRenderPiplineFullscreenPass`
- `CustomRenderPiplineMeshDrawPass`
- `CustomRenderPiplineAssetPass`
- `CustomRenderPiplineHistoryReadPass`
- `CustomRenderPiplineHistoryWritePass`

The plugin also exposes Python bindings for graph history, output catalogs,
RTV probes, and depth/stencil readback. Layout and codec code is supplied by a
consumer shader, so this core plugin has no fixed UE material or depth ABI.
