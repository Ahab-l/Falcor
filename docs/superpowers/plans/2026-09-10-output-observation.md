# Output observation foundation

Sixth framework gate. Observation reads actual marked Falcor graph outputs; no uploads or renderer input mutation. Pure CPU OutputCatalog validates names, formats, display interpretation and tile layout. Native code enumerates live texture/buffer metadata, reads raw bytes on explicit request, and produces a GPU RGBA32Float atlas. Python control selects outputs and normalized display settings. Additional graph outputs require staging a declaration with those outputs; sealed graph topology is never changed in place.

Depth/stencil readback preserves separate raw planes. GPU depth visualization copies the native depth plane into a device-local byte buffer and samples it in compute; no CPU download/reupload. Raw buffer interpretation is explicit bytes/uint32/sint32/float32. Texture modes preserve float/int/uint semantics, optional scalar channel, scale/bias and minmax. Visualization conversions do not replace raw output comparisons.

- [x] RED authored color/integer/raw/depth atlas fixture with independent array oracle.
- [x] Native metadata/readback/compute atlas implementation and Python controller.
- [x] Verify multiple simultaneous outputs, exact raw bytes, depth visualization, parameter validation and source-output preservation.
- [x] Review selection/lifecycle behavior and update complete framework status.

Latest evidence: `build/observer-gpu/run-vune1430/result.json` (launch `build/ue-lighting-closure-cache/run-36asso5b`). Four simultaneous native outputs match exact NumPy arrays. Native raw readback and separate depth/stencil plane metadata preserve original data. A second 2 MiB raw-byte fixture exposed uint32 coordinate overflow (6144 mismatched lanes); uint64 coordinate/index/address computation now passes. CPU OutputCatalog has 16 tests and rejects typed texture formats for raw buffers. `PipelineObserver` returns the actual GPU atlas plus layout metadata, with no CPU-upload dependency. The raw-only graph executes through `SchemaPipeline.render_frame()` without invoking Mogwai's texture-only presenter.

WebRTC transport and the later Web UI consume this native surface. They are subsequent feature work, not prerequisites for the native framework gate.
