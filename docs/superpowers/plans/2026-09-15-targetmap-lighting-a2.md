# Targetmap source lighting implementation plan

Goal: complete the previously approved source-only rendering chain through E2793 and E2962, without post-processing, captured renderer inputs, or retired Config/ABI infrastructure.

Architecture: retain the verified A1 GBuffer arithmetic; append native declared MeshDraw/Compute/Fullscreen/Asset/History passes. Read original source component settings and retained authenticated UE functions. Original RDC outputs and constants are offline validation data only. Continue inline in the existing worktree; GPU/replay/build remain serial. No commit/merge/reset.

## A2: direct light and cascaded shadows

- [x] Restore the 2,323-file material checkpoint and approved prepost-shading specification.
- [x] Inspect retained CSM equations, UE BRDF excerpts, source sun setup, and actual 2.rdc pass order.
- [ ] Export bounded E2196 shadow mask and E2210/E2227 pre/post direct HDR, PS/cbuffer/pipeline evidence to a fresh `build/targetmap-shading-a2/reference-*` directory; verify original capture identity and shutdown.
- [ ] Add source lighting settings and native graph tests in `build/targetmap-shading-a2/source-lighting/test_lighting_graph.py`. Reject captured input provenance, malformed source lights, invalid caster selection; require four independent depth targets, reverse cascade projection order, and an additive direct-light output.
- [ ] Create `lighting_graph.py`, `Decode.slang`, `ShadowDepth.slang`, `ShadowProjection.slang`, `Direct.slang`, and `SourceBRDF.slangh` in the same directory. Reuse the unchanged original PCF/depth/BRDF functions by explicit include; the wrapper owns neutral bindings and fields. Source setting calculations supply source-only CSM parameters and the existing native sun helper supplies light energy.
- [ ] Decode current Schema outputs and own depth to normal/material/position; produce four shadow maps from original Scene geometry; project and blend shadow visibility; evaluate source DefaultLit with nonzero directional source radius. Keep pre-exposure explicit until the independent exposure chain is connected.
- [ ] Run bounded native generation; save direct radiance, shadow mask, depth layers and unchanged seven A1 outputs. Compare full images and independent CPU source-triangle/BRDF samples. Record actual residuals, never relax a budget after observing them.

## A3: indirect light and owned history

- [ ] Inspect actual SSGI/DFAO/SSR reads and source renderer settings. Implement their active branches with owned history and reset, including depth/color reduction, tracing, filtering and composition in the captured order.
- [ ] Migrate retained source atmosphere/sky capture/filter/SH/BRDF functions to declared native passes; use original source cube configuration, not captured cubes.
- [ ] Connect the retained independent histogram exposure/history fragment so PreExposure comes from owned prior state. Audit reconstruction of the recorded Frame 4403 history separately; do not claim that a static reset automatically reproduces capture history.
- [ ] Validate E2793 raw RGBA16F including padding, RGB, alpha, exact/ULP/absolute metrics and reset repeatability.

## A4/A5: sky, fog, clouds, final validation

- [ ] Read original sky/cloud material graphs and source component parameters; implement sky atmosphere, exponential height fog, volumetric cloud view/reconstruction/composition as distinct native passes.
- [ ] Validate E2962 before Bloom/Tonemap/grading, with actual intermediate outputs and input provenance.
- [ ] Promote only verified source contracts and graph/shaders into `scripts/customrenderpipline/examples/targetmap_shading`; keep the frozen experiments intact. Repeat both HDR checkpoints from independent processes/reset; report any history or numeric limitation explicitly.

Validation commands are the existing `test_targetmap*.py` suite, candidate `test_lighting_graph.py`, source CSM/BRDF oracles, and offline raw comparisons. A2 passing does not complete A3/A4; final acceptance remains open until both HDR checkpoints meet the recorded criteria.
