# Native temporal resources

Fifth framework gate. The CPU TemporalEpoch identity/continuity module is independently tested. Native history must contain only prior successful native render outputs.

Declare paired UELegacyHistoryReadPass/UELegacyHistoryWritePass nodes with the same key and texture resource contract. Read emits previous textures plus a small uint status texture. Write consumes current textures. An explicit DAG path orders Read before Write; the writer status output stays marked so Falcor executes it. Bind validates unique pairs and contracts. Two private textures per resource isolate prior reads from pending writes. Repeated execution of a frame preserves the same read slot and does not publish twice.

Use an explicit complete-frame native entry point to begin, execute, wait and publish. Failure anywhere in the graph does not publish pending history. Candidate preparation is preview-only; commit installs fresh invalid history. Generation/signature/input changes are new graph instances. Extent, camera-cut, reset and frame discontinuity invalidate. Shader algorithms consume the validity bit and own fallback mathematics.

- [x] RED authored accumulation fixture: frame0=1, frame1=2, repeated frame1=2, frame2=3; independent NumPy expected values.
- [x] Implement paired native history textures and declaration validation.
- [x] Integrate complete-frame execution with SchemaPipeline and CPU epoch state.
- [x] Verify failed candidate isolation, failed-frame nonpublication, resize/reset/cut/gap/backward invalidation and same-frame stability.
- [x] Document limitations and review before reproduction resumes.

Latest evidence: `build/history-resources-gpu/run-es0eec8k/result.json` (final integration rerun after ownership/external-binding checks, launch `build/ue-lighting-closure-cache/run-_8choptf`). Includes a material-name failure in a real Mesh pass ordered after the writer, restore/retry, missing/mismatched/pruned pairs and unbound entry rejection. CPU TemporalEpoch commits at actual graph commit, including a real no-history state via commit_without_history; no delayed or duplicate epoch counter. `test_pipeline_history.py` covers repeated commits without rendering, switch failures, identity checks and ordinary graph execution. Native prevalidates every history pair before changing any of their states. Preview cannot publish; complete graph failure cannot publish staged textures.

Initial storage contract supports single-layer single-mip sampled/UAV texture2D float/int/uint formats; depth history uses explicit float representation. No external history import. SSR/TSR algorithms remain later framework consumers.
