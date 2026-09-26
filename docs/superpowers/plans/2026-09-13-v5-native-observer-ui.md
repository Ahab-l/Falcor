# V5 Native Observer UI Implementation Plan

> Use subagent-driven-development for independent native UI and GPU preview tasks, followed by independent spec/code review. Worktree Falcor-m0, no commits or merges.

**Goal:** Operate V4 inspection, comparison and export from Mogwai native UI, including clickable GPU field previews.

**Architecture:** Native PythonUI Screen/widgets in Mogwai, a Python controller queued on V4 frame listeners, and a GPU-only preview using generated decoder. CLI and UI share ObservationService.

**Tech Stack:** Falcor PythonUI/ImGui, Python, NumPy, Slang/D3D12.

- [ ] Verify baseline/source instructions and backup all edited native/V4 files.
- [ ] Native surface: Source/Falcor/Utils/UI/PythonUI.{cpp,h}; Source/Mogwai/Mogwai.{cpp,h}, MogwaiScripting.cpp. Add screen, Image/TextInput/file dialog, safe detach and rendered framebuffer access. Establish failing native binding/widget test first, then build Mogwai.
- [ ] Preview: scripts/customrenderpipline/schema_observer_preview.py and test_schema_observer_preview.py. Generate field/attachment decode shaders with explicit modes, bounded program cache and no CPU readback; RED/GREEN pure tests before code and real GPU comparisons later.
- [ ] Frame integration: schema_observer_service.py frame listener add/remove API, bounded UI actions. Test idle/closed/mutation semantics; retain existing CLI operation behavior.
- [ ] Panel: schema_observer_ui_model.py and schema_observer_ui.py plus CPU tests. Static native controls, source/field selection, region, inspect/compare/export actions, results/status, preview click, error/stale state and lifecycle.
- [ ] Entry: native_schema_observer_ui.py; build on V4 start() and use the same session. Do not modify V4 default entry into an always-on UI dependency.
- [ ] D3D12 acceptance: native_schema_observer_ui_smoke.py. Verify actual GPU previews, native picking and screenshot render, comparison/export results, callback detachment, on-demand behavior and CLI parity. Run serially.
- [ ] Independent review; repair concrete defects with RED/GREEN regressions.
- [ ] Full Python suite and relevant V4/native UI GPU regressions; save hashes/exit codes/screenshots under build/native-schema-observer-ui.
- [ ] Chinese guide, Todo V5/progress/spec updates and doc/link checks. Report precise verified scope and remaining limits.
