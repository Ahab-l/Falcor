# Stable Render-Target Cache Design

## Goal

Remove repeated steady-state FBO construction and attachment validation from the custom Mesh and fullscreen shader passes while preserving resource alias checks, graph replacement behavior, shader reload behavior, and identical pixels.

## Scope

The change is limited to `CustomRenderPiplineMeshDrawPass` and `CustomRenderPiplineShaderPass`. Compute dispatches keep their current resource binding behavior. No RenderGraph interface, shader ABI, attachment schema, or clear/load semantics change.

## Design

Each graphics pass owns one cached FBO plus a binding signature. The signature contains the resource identity and subresource selection for every color/depth attachment, the declared format, slot, and the resolved extent. On execute, the pass computes the signature before mutating state. If it matches the cached signature, the existing FBO and validated attachment state are reused. If it differs, the pass clears the cached FBO, validates all attachments and aliases, attaches the new views, and publishes the new signature only after all checks succeed.

Mesh inputs and draw-list selection keep their current validation. A successful input signature is cached separately so unchanged resources skip repeated size/format/alias checks. Scene update flags, `compile()`, `setScene()`, program rebuild, and shader hot reload clear all signatures. A failed validation leaves the previous cache untouched and does not clear or draw into outputs.

Fullscreen shader passes use the same FBO signature for MRT outputs. SRV/UAV binding remains per execute because resource state and parameter-block writes are command-list state; only FBO attachment construction and immutable declaration checks are cached. A changed graph allocation pointer or subresource automatically invalidates the cache.

The existing PSO probe cache remains independent and keyed by the FBO description. It is reset whenever the FBO signature changes or the program is rebuilt.

## Safety and behavior

The first execute after any invalidation follows the current full validation path. Subsequent executes with identical graph allocations reuse the FBO. FBO ownership keeps attached textures alive. Resource replacement, resize, alias changes, mip/slice changes, and format changes all force a rebuild. Clear operations still run every execute according to `load` and `hasClear`; only attachment setup and declaration validation are skipped.

## Verification

Add source-level regression tests for signature fields, invalidation calls, and the no-mutation-on-validation-failure ordering. Run the existing Python source tests, build the plugin, run the native Mesh/Shader smoke tests, and repeat the targetmap performance run. Require identical output hashes and no D3D12 validation errors; report the warm CPU/GPU delta separately from readback time.
