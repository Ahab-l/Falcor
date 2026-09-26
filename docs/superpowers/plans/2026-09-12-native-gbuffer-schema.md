# G4/G5 native GBuffer Schema implementation

**Goal:** Generate storage codecs from a shared generic layout and validate that layout before connecting it to the native GBuffer entry.

**Authorization:** The user said “G4/G5 现在开干吧” after reviewing the proposed scope. Continue inline in the existing Falcor-m0 worktree, preserve unrelated changes and avoid commits/merges.

**Architecture:** Pure Python layout validator, independent Slang code generator, a thin file/CLI publication layer, and native Scene producer examples. No imports of old generate_schema, SchemaPipeline, UE model ABI or depth constants. The design is recorded in ../specs/2026-09-12-native-gbuffer-schema-design.md.

**Tech stack:** Python 3.10-compatible stdlib, Slang SM6.6, existing native Falcor GBuffer Pass and Python ComputePass, D3D12 acceptance.

- [x] Back up affected entry/docs and record baseline source hashes.
- [x] Add test_native_gbuffer_schema.py with bad-layout, impossible-range, routing, generation/publication and custom-codec tests. Run with Anaconda unittest and record expected RED before implementation.
- [x] Implement gbuffer_schema.py validation of attachment formats/channels, named field/storage layouts and codec ownership/ranges. Re-run the CPU acceptance.
- [x] Implement gbuffer_codegen.py and generate_native_gbuffer.py to emit shared Slang structs, encode/decode, checked overflow, custom blocks, native raster wrapper and metadata. Verify deterministic artifacts and rejected updates.
- [x] Add a generic schema/material producer/custom-codec example and native_schema_gbuffer.py. Add a GPU acceptance with independently calculated encoded values, independently supplied decode inputs, non-finite/overflow rejection and mixed-header compilation rejection.
- [x] Run the new GPU acceptance against the native GBuffer and a real downstream decoder. Resolve failures in code or test setup without weakening numeric expectations. Run the existing native_gbuffer_smoke.py and native_mesh_selection_smoke.py serially.
- [x] Run the complete Python suite once the final implementation is stable; perform scoped diff/whitespace and source-dependency review. C++ builds only if source changes require them.
- [x] Deliver Chinese usage, validation evidence and accurate limits. Update Todo G4/G5, project progress and findings; keep A1/V4/R4 and deferred rollback separate.

Completion: 495 Python tests (26 new), 4 D3D12 GPU suites, verified backup/unchanged native entry and independent review close-out. No C++ changes; generated Slang compiled and executed. Evidence: build/native-gbuffer-schema/verification.json.

CPU command: `E:/IDE/Anaconda/python.exe -X utf8 -m unittest discover -s scripts/customrenderpipline -p test_native_gbuffer_schema.py -v` (workspace TEMP, no embedded Python 3.10 numpy override).

GPU command: `build/windows-vs2022/bin/Release/Mogwai.exe --headless --enable-debug-layer --verbosity 2 --script scripts/customrenderpipline/native_gbuffer_schema_smoke.py`; each run exits after storing results under build/native-gbuffer-schema. Existing GPU regression commands use the same options and run serially.
