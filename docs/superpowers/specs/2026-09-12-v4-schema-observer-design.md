# V4 Schema observation and external program access

User approved implementation on 2026-09-12 after requiring both a generic observer and CMD/program access. Work only in Falcor-m0; preserve all prior modifications; no commits/merges. UI V5, asynchronous GPU readback R4, arbitrary depth codecs and UE migration remain separate.

## Contract

`SchemaObserver(graph, artifacts, bindings=None, pass_name='GBuffer')` validates generated artifacts, maps every Schema attachment to a marked native output and creates a cached native ComputePass. `inspect(region=[x,y,width,height], fields=None)` returns decoded typed arrays, texture-load values and extracted storage slots from the same dispatch. UINT/INT results use uint32 transport words and bit reinterpretation, never float ID conversion. Raw texture bytes remain available through existing PipelineObserver.read; texture-load values are explicitly distinct from raw bytes (hardware normalization/sRGB applies).

Schema attachment observation initially accepts single-sample 2D mip-0 textures of the declared formats. Reject unsupported resource shapes explicitly. Metadata and generated files are checked against the generator, including direct source content. Configurable native producers must still refer to the bound generated definition. Independent custom producers require explicit matching contract registration; do not claim arbitrary cross-Pass semantic proof. Invalid layouts/outputs/coordinates, nonfinite decoded fields and stale direct sources produce structured errors.

Comparison takes typed reference arrays and explicit per-field rules: exact (integers/bool), abs/relative numeric (existing compare_arrays), or normal angle in degrees (float3). Optional explicit boolean coverage mask. No inferred color space, semantic field-name rules, or implicit NaN acceptance. Independent reference tests are necessary for custom codec correctness.

## External access

Local file mailbox, atomic JSON publication in a unique session directory. CLI writes version-1 request with UUID, instance, graph, operation, arguments and deadline; render-thread `pump(handler)` handles a bounded batch after graph execution and publishes one JSON reply. No network listener, arbitrary code execution command, or background GPU operations. Timeouts cancel pending requests; no commands are processed without frame-boundary pump. Idle polling does no GPU readback.

Responses include version/request_id/status/instance/graph/frame/layout_hash and result or structured error. stdout is JSON; stderr is diagnostics; exit 0 success, 1 comparison_failed, 2 execution/validation error, 3 timeout. `list`, `inspect`, `compare` and export through `inspect --export` share the same service handler as Python callers. Large arrays export to an instance-owned NPZ path; JSON lists dtype/shape/archive key. Inline results are bounded. Reference NPZ loads forbid pickle.

Mogwai attach wraps its existing graphExecutionCallback, executes the ordinary graph only when the previous callback did not handle it, then pumps requests for that active graph. Add native RenderGraph Python device/execute bindings because Mogwai presently exposes neither. Testbed users can call service.after_frame() after testbed.frame(). Frame IDs are service-local rendered-frame counters. Detach restores the previous callback only when still installed; inactive graph requests are explicit errors.

## Acceptance

Pure Python tests for contract generation, extraction, comparison rules, validation, independent-process mailbox round trips, timeouts and JSON/exit codes. D3D12 debug-layer acceptance for generated decoder on real native MRT outputs, nonlinear custom codec, independent reference values, full uint32/int32, region selection, layout mismatch, typed exports, service/API equality and external CLI on a live Mogwai process. Verify ordinary preview idle frames do not issue decode/readback and callbacks execute each frame once. Run existing Python and relevant native Schema/observer GPU regressions serially. Publish runnable demo and Chinese CLI/API guide.
