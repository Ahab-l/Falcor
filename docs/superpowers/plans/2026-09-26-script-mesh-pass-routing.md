# Script MeshPass Routing Implementation Plan

> **For agentic workers:** Execute this plan task-by-task in the existing `E:/Project/falcor/Falcor-m0` worktree. Keep the core branch free of scene-specific pipelines.

**Goal:** Add a script binding that resolves material or explicit instance selectors into independent `CustomRenderPiplineMeshDrawPass` nodes with per-route properties.

**Architecture:** A small helper in the customrenderpipline plugin parses a Python list of route dictionaries, resolves a snapshot of triangle instance IDs from the supplied Scene, rejects invalid or overlapping routes, injects the IDs into ordinary MeshPass properties, and calls `RenderGraph::createPass()`. It returns a JSON receipt through Python. No graph edges are created automatically.

**Tech Stack:** C++17, nlohmann::json, Falcor `RenderGraph`/`Scene` APIs, pybind11 ScriptBindings, FalcorTest CPU/GPU test macros, CMake.

---

### Task 1: Add a failing route-helper test

**Files:**
- Create: `Source/Tools/FalcorTest/Tests/Core/CustomRenderPiplineMeshRouting.cpp`
- Modify: `Source/Tools/FalcorTest/CMakeLists.txt`

- [ ] **Step 1: Write the failing binding test.**

Load the plugin, import `falcor.falcor_ext`, assert that `customRenderPiplineAddMeshPasses` exists, and call it with a null scene and empty routes. The expected failure should come from the missing Scene validation rather than an unknown Python symbol:

```cpp
GPU_TEST(CustomRenderPiplineMeshRouteBinding, Device::Type::D3D12)
{
    ASSERT_TRUE(Scripting::isRunning());
    pybind11::gil_scoped_acquire gil;
    PluginManager::instance().loadPluginByName("customrenderpipline");
    auto module = pybind11::module_::import("falcor.falcor_ext");
    ASSERT_TRUE(pybind11::hasattr(module, "customRenderPiplineAddMeshPasses"));
    auto graph = RenderGraph::create(ctx.getDevice(), "MeshRoutes");
    auto addRoutes = module.attr("customRenderPiplineAddMeshPasses");
    EXPECT_THROW(addRoutes(pybind11::cast(graph), pybind11::none(), pybind11::list()), std::exception);
}
```

- [ ] **Step 2: Add the source to `FalcorTest`** immediately after `CustomRenderPiplineSampler.cpp` in `Source/Tools/FalcorTest/CMakeLists.txt`.

- [ ] **Step 3: Build/run the focused test** with the existing FalcorTest command used by the build tree. It must fail because the binding is not defined yet.

- [ ] **Step 4: Commit the red test** with `git add Source/Tools/FalcorTest && git commit -m "test: add script mesh route binding coverage"`.

### Task 2: Implement route parsing and graph creation

**Files:**
- Create: `Source/RenderPasses/customrenderpipline/CustomRenderPiplineMeshRouting.h`
- Create: `Source/RenderPasses/customrenderpipline/CustomRenderPiplineMeshRouting.cpp`
- Modify: `Source/RenderPasses/customrenderpipline/CustomRenderPiplinePlugin.cpp`
- Modify: `Source/RenderPasses/customrenderpipline/CMakeLists.txt`

- [ ] **Step 1: Define the narrow helper interface.**

Use a C++ function returning `nlohmann::ordered_json`:

```cpp
namespace Falcor::CustomRenderPipline
{
ordered_json addMeshPasses(RenderGraph& graph, const ref<Scene>& scene, const ordered_json& routes);
}
```

- [ ] **Step 2: Parse one route at a time.**

Require object keys `name`, `properties`, and exactly one of `materials` or `instanceIDs`. Reject unknown route keys. Validate non-empty names, object properties, array selectors, and that `graph.getScene() == scene` (both must be non-null). Reject names already in the graph before mutating it.

- [ ] **Step 3: Resolve and normalize selectors.**

For `materials`, call `scene->getRasterInstanceIDs(materialNames)`. For `instanceIDs`, require integer values in `[0, UINT32_MAX]`, sort and deduplicate, then call `scene->createRasterDrawList()` to validate range and triangle geometry before graph mutation. Reject overlap with an ordered map from instance ID to route name. Inject the normalized IDs into a copy of `properties`; reject a caller-provided `properties.instanceIDs` to avoid two sources of truth.

- [ ] **Step 4: Create ordinary MeshPass nodes.**

Call `graph.createPass(routeName, "CustomRenderPiplineMeshDrawPass", Properties(propertiesJson))` for each route. If any creation throws, remove all nodes created by this helper before rethrowing so the operation is atomic.

- [ ] **Step 5: Return a deterministic receipt.**

Return an array of objects `{ "name": routeName, "instanceCount": ids.size(), "instanceIDs": ids }` in input order. Register a Python binding in `CustomRenderPiplinePlugin.cpp` that accepts `RenderGraph`, `Scene`, and a Python object converted to `ordered_json`, then returns `receipt.dump()` so scripts receive a stable JSON string like the existing plugin catalog APIs.

- [ ] **Step 6: Add the new files to the plugin CMake source list and compile.**

- [ ] **Step 7: Re-run the Task 1 test** and verify it now reaches the intended null-scene validation rather than missing binding.

### Task 3: Expand tests for successful routes and rejection rules

**Files:**
- Modify: `Source/Tools/FalcorTest/Tests/Core/CustomRenderPiplineMeshRouting.cpp`

- [ ] **Step 1: Add a CPU-level parser test helper** for the route JSON normalization function if the helper exposes it internally; otherwise use a minimal GPU fixture with a generated scene containing two materials and two triangle instances.

- [ ] **Step 2: Add success coverage.**

Verify two material routes create two graph nodes, the receipt preserves input order, the resolved IDs are disjoint, and each node's `getProperties()` contains the injected `instanceIDs` while preserving distinct shader and target properties. Verify an explicit ID route produces the same IDs as the material route.

- [ ] **Step 3: Add rejection coverage.**

Assert failures for: null graph Scene, route list not an array, missing selector, both selectors, unknown route key, duplicate route name, existing graph pass name, unknown material, explicit out-of-range ID, non-triangle ID, overlapping routes, and caller-provided `properties.instanceIDs`.

- [ ] **Step 4: Run the focused tests and check the expected failure messages.**

### Task 4: Document script usage and finalize validation

**Files:**
- Modify: `Source/RenderPasses/customrenderpipline/README.md`
- Modify: `docs/superpowers/specs/2026-09-26-script-mesh-pass-routing-design.md` only if the final API name or return type changes.

- [ ] **Step 1: Add the complete route-table example** with opaque/hair routes, explicit `add_edge()`/`mark_output()`, material snapshot semantics, overlap behavior, and the distinction between raster MeshPass and hardware Mesh Shader.

- [ ] **Step 2: Run formatting/static checks** on the changed C++ files and inspect `git diff --check`.

- [ ] **Step 3: Run the focused native test, existing Scene raster draw-list tests, and the existing customrenderpipline capability tests.**

- [ ] **Step 4: Run the relevant build target and record exact command/output in `progress.md`.**

- [ ] **Step 5: Commit the implementation and documentation** with `git add` and `git commit -m "feat: add script mesh pass routing"`.

---

## Self-review

- The spec requirements map to Task 2 parsing, selector resolution, overlap validation, ordinary Pass creation, and Task 3 tests.
- No placeholders or unspecified validation steps remain.
- The public function name, JSON receipt shape, and `instanceIDs` property are consistent across all tasks.
- Graph edges remain caller-owned as required; no task accidentally introduces a dispatcher or scene-specific pipeline.
