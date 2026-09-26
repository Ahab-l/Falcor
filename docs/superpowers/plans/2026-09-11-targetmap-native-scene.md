# Saved targetmap to native scene implementation plan

> For agentic workers: Continue the approved framework-first design with executing-plans and focused tests. Root owns source export, renderer changes, serial UE/build/GPU. Existing agent investigates source camera read-only. No commits, source-project edits, captured rendering inputs or HZB.

**Goal:** Render the saved targetmap geometry/materials through the existing Mesh / Packed / Decode framework using original assets and authored/source scene settings.

**Architecture:** Export original Engine mesh LOD0 through UE's asset exporters in a scratch project with source fingerprints. Convert source-coordinate meshes and saved instance transforms into native Falcor Scene geometry. Scene JSON and material-program source remain immutable graph inputs. Expose provenance and any source settings still uncertain. Reuse original UE material expressions/functions where available, without captured shader constants or exported geometry.

**Tech Stack:** UE Python commandlet, FBX/OBJ, Python/NumPy, Falcor SceneBuilder / PassDefinition / Slang.

- [x] Run and validate the existing scratch mesh exporter for Sphere, Cube, Floor and SkySphere; compare exported index/vertex counts with UE LOD0 and verify source files unchanged.
- [x] Read source camera from saved map/editor configuration; export original material graphs/parameters in scratch. Do not substitute capture View/constant buffers. If source camera cannot be established, author and label a working view while continuing geometry/material work.
- [x] Add a small reusable source-scene conversion module and focused tests for OBJ indexing/UV/handedness, saved transforms/normals and unit conversion. Tests exercise asymmetric nonuniform transforms and shared mesh instances.
- [x] Create targetmap scene input/provenance and a Falcor pyscene loader using original exports. Preserve two Cube instances, Sphere, Floor and separate sky role; schema/material routing remains in project layers.
- [x] Native validation: expected draw/instance selection, actual depth coverage, finite decoded normals/positions and source-material values, repeated-frame stability, resource/scene fingerprints. Use GPU Atlas for simultaneous raw-output inspection.
- [x] Once the scene is running, continue source-derived conventional directional shadows through the existing Mesh Pass framework; no captured cascade matrices/depth.
- [x] Record exact source/export/native evidence and remaining camera/material/whole-image discrepancies in research docs and the main task plan.

Evidence: `docs/research/ue-legacy-targetmap-native-scene.md` and `docs/research/ue-legacy-native-csm.md`. Native CSM final run `run-ydrkpj9_` passes source depth/PCF/Lighting and input-name collision checks; live setup camera/resize `run-_3jnw76b` passes. Current slice complete; remaining source sky/environment/GI/SSR/postprocessing and capture comparison are not claimed complete.

Source baseline and current image-affecting pass scope: `docs/research/ue-legacy-capture2-baseline.md`. This is a continuation of approved work, not a new approval gate. A valid native scene is required before claiming its full image matches 2.rdc.
