# Relative resources and UE metering downsample

Continue the authorized framework-first plan. Root owns edits, serial builds/GPU/UE executions. UE and capture stay read-only; no capture data enters the renderer.

Design: generic texture output `size` accepts `{relative_to: inputPort|$viewport, divisor: [x,y]}`. Resolve ceil division through Falcor connected reflection, retry compilation until reflection agrees, and validate actual execution dimensions. References must be read-only textures, preventing local cycles. Output omission explicitly means viewport; input omission accepts upstream; inputOutput and loaded Mesh attachments inherit upstream. Fixed input size asserts compatibility. Reuse Falcor allocation and scheduling.

Reuse exact UE `SampleInput`, `DownsampleCommon` and `MainPS`, with a thin full-viewport Compute wrapper and bilinear clamp sampler. Default is Raster (PreferCompute=0), half-resolution R11G11B10Float (UE PF_FloatRGB on D3D12), low quality. Also support Compute/high quality. Exposure meters the reduced input and applies exposure to full-resolution SceneColor. Inset views, upscaler branches and local exposure remain separate work.

- [x] RED native fixture: chained ceil dimensions, odd/even/single-pixel/resize and invalid descriptors.
- [x] Native reflection/compile/execute dimension contract and verification, including generic inputOutput and loaded Mesh propagation. Independent review closed.
- [x] Original source byte/hash verification, reusable fragment, independent bilinear/packed oracle.
- [x] GPU downsample and full histogram/adaptation with native half-resolution input; both execution/quality permutations and odd dimensions.
- [x] Affected regression, evidence and limitations. Scene exposure, History, generic Shader and auxiliary Mesh final regressions passed on the final binary; details in the report. This closes the functional slice, not the stability investigation or original renderer goal.

Evidence: `docs/research/ue-legacy-metering-downsample.md`. Functional checks have passed, but the intermittent Windows AV recurred at viewport resize. CDB140-rejection and eight test-recorder runs did not reproduce it. Stability investigation remains open; do not represent these repetitions as a fix.
