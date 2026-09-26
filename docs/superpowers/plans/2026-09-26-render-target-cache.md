# Stable Render-Target Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache stable FBO attachments and declaration validation in the custom Mesh and fullscreen shader passes without changing rendered output.

**Architecture:** Add small per-pass cache records containing resource identities and subresource metadata. Build a cache candidate after validating the current graph resources, then commit it only after all validation and attachment operations succeed. Invalidation is explicit at compile, scene/program replacement, and shader reload boundaries.

**Tech Stack:** C++17, Falcor FBO/Texture APIs, nlohmann::json, Python pytest source checks, MSBuild, D3D12 headless targetmap runner.

---

### Task 1: Add failing cache-contract regression checks

**Files:**
- Create: `scripts/customrenderpipline/test_render_target_cache.py`
- Test: `Source/RenderPasses/customrenderpipline/CustomRenderPiplineMeshDrawPass.cpp`, `CustomRenderPiplineShaderPass.cpp`

- [ ] **Step 1: Write tests that require cached FBO members, resource-identity signatures, explicit invalidation, and publish-after-validation ordering.**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MESH = (ROOT / "Source/RenderPasses/customrenderpipline/CustomRenderPiplineMeshDrawPass.cpp").read_text()
SHADER = (ROOT / "Source/RenderPasses/customrenderpipline/CustomRenderPiplineShaderPass.cpp").read_text()

def test_mesh_cache_tracks_resource_identity_and_invalidates():
    assert "ref<Fbo> cachedFbo" in MESH
    assert "Texture*" in MESH
    assert "invalidateAttachmentCache" in MESH
    assert "p.cachedFbo = candidate" in MESH

def test_shader_cache_tracks_resource_identity_and_invalidates():
    assert "ref<Fbo> cachedFbo" in SHADER
    assert "Texture*" in SHADER
    assert "invalidateFboCache" in SHADER
    assert "p.cachedFbo = candidate" in SHADER

def test_cache_is_published_after_validation():
    for source in (MESH, SHADER):
        assert source.index("p.cachedFbo = candidate") > source.index("validate")
```

- [ ] **Step 2: Run the new test and confirm it fails because the cache contract is absent.**

Run: `python -m pytest -q scripts/customrenderpipline/test_render_target_cache.py`

Expected: FAIL with missing `cachedFbo` or invalidation symbols.

### Task 2: Implement Mesh FBO and attachment cache

**Files:**
- Modify: `Source/RenderPasses/customrenderpipline/CustomRenderPiplineMeshDrawPass.cpp`

- [ ] **Step 1: Add cache records for FBO attachment identity and validated input identity.**

The attachment key stores each target's `Texture*`, format, slot, depth flag, first mip, first slice, array size, and resolved extent. The input key stores each input's `Resource*`, format, raw/structured contract, and texture subresource shape. Keep `ref<Fbo> cachedFbo` and `std::optional<...> cachedKey` in `Impl`.

- [ ] **Step 2: Add `invalidateAttachmentCache()` and call it from `compile()`, `setScene()`, and program rebuild.**

The helper clears the cached FBO, attachment key, input key, and probe descriptor. It does not alter scene selection or output data.

- [ ] **Step 3: Move current attachment/input validation into a candidate-build block.**

Construct a temporary FBO and temporary keys. Validate every target, alias, input, and binding exactly as today. Attach views to the temporary FBO. Only after all checks pass assign `p.cachedFbo`, keys, and `p.probedFboDesc` state. Reuse the cache only when all keys match.

- [ ] **Step 4: Keep clear and draw operations outside the cache.**

Each execute still clears `load: clear` attachments, sets the current viewport, binds the cached FBO, and rasterizes the selected lists. No clear is issued before candidate validation succeeds.

- [ ] **Step 5: Run the focused source tests.**

Run: `python -m pytest -q scripts/customrenderpipline/test_render_target_cache.py scripts/customrenderpipline/test_native_completion_cleanup.py scripts/customrenderpipline/test_native_pipeline.py`

Expected: PASS.

### Task 3: Implement fullscreen ShaderPass FBO cache

**Files:**
- Modify: `Source/RenderPasses/customrenderpipline/CustomRenderPiplineShaderPass.cpp`

- [ ] **Step 1: Add an output attachment signature and cached FBO to `Impl`.**

The signature includes output resource pointers, MRT slots, first mip, first slice, slice count, formats, and extent. Add `invalidateFboCache()` and call it from `invalidateCache()`, `compile()`, and program hot-reload handling.

- [ ] **Step 2: Cache only graphics output attachment setup.**

For fullscreen passes, validate output contracts and build a temporary FBO when the signature changes. Reuse the cached FBO when the signature matches. Continue binding SRVs/UAVs, setting uniforms, dispatching, and clearing declared resources every execute.

- [ ] **Step 3: Preserve compute and once-only paths.**

Compute passes continue using no FBO. Once-only cached-output copies remain unchanged; replacing a destination invalidates the graphics FBO cache as part of the shared cache invalidation.

- [ ] **Step 4: Run focused tests and build the plugin.**

Run: `python -m pytest -q scripts/customrenderpipline/test_render_target_cache.py scripts/customrenderpipline/test_native_completion_cleanup.py scripts/customrenderpipline/test_native_pipeline.py`

Build: `cmake --build build/windows-vs2022 --config Release --target customrenderpipline -j 4`

Expected: test PASS and build exit code 0.

### Task 4: Verify output and performance

**Files:**
- Modify: `build/targetmap-shading-a6/customrenderpipline-fbo-cache-performance.md` (generated report)
- Create: `build/targetmap-shading-a6/customrenderpipline-fbo-cache-performance.json` (generated data)

- [ ] **Step 1: Run the native smoke scripts.**

Run the existing native MeshDraw, resource composition, sampler, and schema observer smoke scripts with the rebuilt plugin. Expected: exit code 0 and no D3D12 validation errors.

- [ ] **Step 2: Run the targetmap warm-frame benchmark twice.**

Use the existing headless runner with the same scene, temporal manifest, output set, and debug-layer setting as the prior comparison. Capture full graph and `SSRLighting.color` runs.

- [ ] **Step 3: Compare output hashes.**

Require all 81 full-graph output hashes and the single-output hash to match the cached-probe baseline. Any mismatch stops the performance claim.

- [ ] **Step 4: Record CPU/GPU timings and readback separately.**

Report warm CPU/GPU, RenderGraph GPU, pass count, output count, readback bytes/time, and D3D12 validation status. Do not include setup, shader compilation, or readback in steady-state frame timing.

- [ ] **Step 5: Run the full relevant Python test subset.**

Run: `python -m pytest -q scripts/customrenderpipline`

Expected: no failures. If the full suite contains environment-only tests, list their exact failures instead of treating them as a pass.
