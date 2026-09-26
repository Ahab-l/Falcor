# V5 native Schema observation UI

User approved the preceding design: expose V4 in Mogwai, with pixel selection, decoded field/attachment values, field visualization, reference comparison and exports. Implement in Falcor-m0 without commits/merges or legacy UE dependencies. Reuse native PythonUI, V4 Schema decoding/service and Falcor ComputePass. Do not build a second render graph editor or desktop/web viewer.

## Native surface

Expose the already-existing python_ui::Screen on Mogwai as m.screen and render it inside the existing onGuiRender. Add generic PythonUI Image (float-compatible 2D texture, aspect-fit, native left-click texel selection, crosshair, bounds metadata), TextInput (string value/change callback) and open_file_dialog helper. Native UI owns no GBuffer semantics. Add a readonly target framebuffer accessor only for programmatic capture of the existing rendered UI.

## Python components

SchemaFieldPreview compiles a small native compute shader including the same generated Codec.slangh. It displays either a decoded Schema field or registered attachment through explicit grayscale range, RGB range, signed-vector mapping or integer-ID colors. It writes a float texture entirely on GPU, never reads back for preview. UINT identifiers remain integer through hashing. Validate source bindings/layout via V4 before dispatch. Compile/cache by selected source/mode, bound cache size; resources released on close. Preview is a requested snapshot, not an automatic per-frame cost.

SchemaInspectorPanel binds one existing ObservationService. Two native windows provide graph/source selection, region/pixel coordinates, display mapping, reference/rules NPZ+JSON selectors, numeric/angle rule controls, optional reference-mask key, inspect/refresh/compare/export buttons, status/frame/layout labels, and decoded/storage/attachment results. Default comparisons are explicit visible controls; optional rules JSON supports multiple fields. No inferred colorspace conversion or material semantics. Raw output export uses V4 read; decoded region export uses V4 inspect(export=True).

UI callbacks enqueue bounded actions; the service invokes registered frame listeners after rendering and mailbox pumping. UI GPU work therefore occurs at the same correct frame boundary as CLI, not during ImGui draw-list construction. Image clicks refer to the displayed preview snapshot; keep its selected-pixel result honest by refreshing preview and pixel together on a new frame, labeling frame/time. On graph switch/layout failure/resize, keep old picture and label it stale/error instead of interpreting incompatible new data. No live service state access from an external UI thread.

## Lifetime and tests

Close/unregister listeners; remove owned native widgets through a safe detach operation rather than leaving callbacks referencing dead controllers. Reopen is documented. Preserve V4 CLI and native graph callback ownership semantics. CPU tests cover model selections/formatting/rules/queue/closed state and preview code generation. Real D3D12 tests exercise native widgets, GPU preview versus V4 arrays, pixel click mapping, comparison/export, stale layout/graph errors, no idle readback, and CLI regression. Capture the native UI framebuffer and inspect the result visually; do not claim mouse-driven acceptance from callback-only tests. V4 format limits, synchronous on-demand numeric readback, Vulkan and final RDC remain separate.
