# V4 Schema Observer Implementation Plan

> Use subagent-driven-development for independent transport/comparison modules, with spec and code review before acceptance. Preserve the existing worktree; no commits or merges.

**Goal:** Observe and compare Schema fields through Python and CMD against a live native Falcor instance.

**Architecture:** Generated Slang consumer invoked through native ComputePass; render-thread service processes an atomic local JSON mailbox after a frame. CLI and Python share the service; Mogwai uses thin native RenderGraph device/execute bindings.

**Tech Stack:** Python, NumPy, Slang, Falcor D3D12, existing Mogwai callback.

- [x] Snapshot files to be modified and write failing CPU tests before implementations.
- [x] `schema_observer_compare.py` plus tests: compare_fields(actual, reference, rules, mask=None); exact integer precision, numeric tolerances, normal angle, strict type/shape/finite/rule validation. Run `python -m unittest discover -s scripts/customrenderpipline -p test_schema_observer_compare.py`.
- [x] `observer_transport.py`, `inspect_cli.py` plus tests: versioned atomic local requests, deadlines, bounded frame pump and response envelopes; standalone subprocess CLI JSON and exit codes. No Falcor import in client. Run `python -m unittest discover -s scripts/customrenderpipline -p test_observer_transport.py`.
- [x] `schema_observer.py`, `schema_observer_codegen.py` plus tests: verified artifact loading, typed shader emission, complete attachment mapping, region validation, exact uint word transport and GPU decoding. Existing decoder stays sole algorithm source.
- [x] `schema_observer_service.py`: list/inspect/compare/export handler with frame/layout identity; native resource catalog; NPZ numeric references, explicit masks, no unsafe pickle; bounded inline response.
- [x] Native RenderGraph scripting: expose device and execute() using its existing render context. Add `observer_mogwai.py` attach/detach using existing callback; preserve pre-existing callback and ordinary once-per-frame behavior.
- [x] `native_schema_observer.py` demo and `native_schema_observer_smoke.py`: external CLI launched from an independent process while real Mogwai frames continue. Test core decoder + integer/signed precision, custom quantization/normal, region/exports/errors, idle behavior and callback restoration.
- [x] Review spec conformance and code quality; resolve important findings with targeted regression tests.
- [x] Run full Python suite, build changed native binding, serial D3D12 GPU acceptance and required regressions; collect exit codes/logs/source hashes under build/native-schema-observer.
- [x] Chinese guide with actual runnable commands, update Todo V4 and persistent progress, verify docs/links and report evidence and remaining scope.

Completed evidence: build/native-schema-observer/verification.json. Final CPU suite: 575 passing. Two new GPU/CLI format variants plus four existing native/observer/Mogwai suites pass. Review findings resolved with targeted regressions, including artifact redirection, callback ownership/lifecycle, mailbox fairness, envelope parity and masked nonfinite samples. No commits or merges.
