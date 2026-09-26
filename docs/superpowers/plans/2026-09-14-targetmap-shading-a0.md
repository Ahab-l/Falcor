# Targetmap shading A0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Root exclusively owns replay/GPU; the independent offline verifier can be delegated. No commits/merges/resets.

**Goal:** Establish immutable, independently reproducible RGBA16F references for the approved E2793/E2962 checkpoints and document actual input/viewport provenance.

**Architecture:** A bounded read-only RenderDoc worker exports two raw textures and explicit per-event pipeline evidence into new run directories. A NumPy offline verifier checks identity, file containment/size/hash/format, actual view rectangle, and compares independent runs without any display transform. Neither module imports Falcor production pipeline code or uploads captured data.

**Tech Stack:** Python standard library (worker compatible with embedded RenderDoc), NumPy (offline verifier), installed qrenderdoc.exe, D3D12 replay.

## File structure

All paths below are under E:/Project/falcor/Falcor-m0:
- scripts/customrenderpipline/_targetmap_shading_replay.py — read-only pinned collector, bounded outputs and cleanup.
- scripts/customrenderpipline/test_targetmap_shading_replay.py — collector guards and read-only surface tests.
- scripts/customrenderpipline/targetmap_shading_reference.py — pure offline identity/size/hash validation and raw HDR metrics.
- scripts/customrenderpipline/test_targetmap_shading_reference.py — positive/negative synthetic contracts and numeric edge cases.
- build/targetmap-shading-a0/<unique-run>/ — original raw outputs/evidence/logs, never production inputs.
- docs/research/customrenderpipline-targetmap-shading-zh.md — current evidence, limitations, next action.

## Manifest contract

```json
{"schema":"crp-rdc-shading-reference-v1","role":"offline_reference_only","capture":{"path":"E:/rdc/ue/2.rdc","sha256":"059eef7978d1c32039ad4bd21b5b0c59574c393996fb842b37f3a9e4a87edb2f"},"full_renderer_parity":false,"checkpoints":[{"event":2793,"resource":"ResourceId::955","format":"R16G16B16A16_FLOAT","width":1424,"height":1040,"view_rect":[0,0,1421,1035],"subresource":{"mip":0,"slice":0,"sample":0},"file":"E2793-SceneColor.rgba16f","byte_size":11847680,"sha256":"64-hex-sha256"}]}
```

Actual manifest must contain exactly events 2793 and 2962; collect actual viewport/subresource then require expected capture contract. The sample above illustrates one entry only, not an acceptable complete manifest. No tolerance is introduced at A0; repeated-reference comparison is exact visible-region bits. Padding differences are reported separately, never silently ignored or counted as visible pixels.

## Task 1: Offline validation and comparison

- [x] Write failing tests before implementation. Test import/function absence as missing capability, then positive tiny RGBA16F fixtures with the manifest contract.
- [x] Test wrong capture/role/event/format/hash/byte_size, duplicate/missing checkpoint, path traversal, nonfinite visible values, different view/subresource, signed zero and one half ULP.
- [x] Implement `validate_reference(path)` and `compare_references(left,right)`, returning JSON-safe RGB/alpha metrics for visible region and padding separately. Include exact scalar/pixel counts, MAE/RMSE/max_abs/max_ulp and nonfinite counts. Do not label renderer parity.
- [x] Run `python -m unittest discover -s scripts/customrenderpipline -p test_targetmap_shading_reference.py -v` and preserve RED/GREEN logs.

## Task 2: Read-only collector

- [x] Write guard tests for pinned capture/hash, events, raw length, view/scissor bounds and forbidden replay mutators.
- [x] Implement guarded main: hash capture; OpenCaptureFile/OpenCapture; sequential event snapshots; read only SceneColor raw bytes at 2793/2962; record D3D12 pipeline, resource descriptors, shader reflection/constant buffers and samplers at selected relevant events. No DebugPixel or shader replacement.
- [x] Fixed bounded metadata events: Base 1426/1437/1452, historical consumers 1978/2058/2680/2701/2761, direct 2227, primary 2793/2962. Export cbuffer bytes only as audit evidence, never render inputs; do not export arbitrary textures/IA/postVS/history payloads.
- [x] Store shader disassembly at Base1452/lighting2793 only for actual-layout validation. Cap each cbuffer at 128 KiB and all raw exports at 64 MiB; no arbitrary native object recursive cycles.
- [x] On any failure preserve error JSON; always shutdown controller/capture and rehash; publish success manifest only after all checks and shutdown succeed. Fresh output directory required.
- [x] Run collector guard tests; launch one hidden owned process at a time with 120-second bound, logs and script hash pinned. Reject stale/missing completion artifacts.

## Task 3: Independent replay evidence and checkpoint

- [x] Launch first fresh worker, run offline validation; inspect actual view/scissor/cbuffer/descriptor evidence.
- [x] Launch second fresh worker after first exits, compare raw outputs; require exact visible bits, report padding and any replay instability without broadening tolerances.
- [x] Verify source map/capture/script identities and owned process exit; preserve detailed manifest/metrics and read-only pipeline findings.
- [x] Independently review specification then code/negative tests; fix findings before claiming A0 complete.
- [x] Update local scoped plan/progress/findings and main TODO F1; preserve blocked V5 goal as separate. Report A0 result and earliest remaining uncertain input rather than claim full shading parity.

## Review commands

```powershell
python -m unittest discover -s scripts/customrenderpipline -p test_targetmap_shading_reference.py -v
python -m unittest discover -s scripts/customrenderpipline -p test_targetmap_shading_replay.py -v
```

Expected GREEN for CPU guards/contracts. GPU evidence requires new replay results and exact visible-region comparison, not test mocks. Prior metadata-only audit is not a raw baseline. Broader rendering modifications follow A1 and are not hidden inside A0.

## Completion checkpoint
A0 only:43CPU tests, two independent metadata+raw replays,58artifacts per run, all visible/padding bits exact. Scope and quality reviews closed. No renderer parity claim. Evidence: build/targetmap-shading-a0/final-repeatability.json, input-identity-audit.json, review.md. Next A1 source native GBuffer; the full user shading objective remains unfinished.

