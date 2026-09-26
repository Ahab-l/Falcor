# Native atmosphere LUT implementation plan

> For agentic workers: use subagent-driven-development and verification-before-completion. All UE/build/GPU executions belong to root and run serially. No staging or commits.

**Goal:** Generate UE transmittance and multi-scattering LUTs from saved targetmap atmosphere properties through the existing declared Compute executor, with source provenance and independent numerical checks.

**Architecture:** Source component → validated physical parameters → Transmittance Compute → MultiScattering Compute. Reuse unchanged UE function bodies, including the shared scattering integrator. Generic PassDefinition owns shader, uniforms, texture formats, samplers, dimensions and dependencies; no new one-off native pass is needed for these two 2D resources. This is the next slice of the already authorized renderer design; full sky, environment convolution, clouds/fog and final image agreement remain subsequent work.

**Tech Stack:** UE HLSL source, Slang, Falcor D3D12, Python/NumPy, SchemaPipeline.

- [x] Read exact active source branches and extend the read-only scratch exporter for atmosphere, cloud, fog and SkyLight settings. Verify original packages unchanged.
- [x] Add parameter conversion tests: sRGB ground color, coefficient scaling, density/tent clamps, float sample count and invalid settings. Implement `atmosphere.py` mapping UE component values to physical km units without capture data.
- [x] Extract original functions with SHA256/line manifest using `export_atmosphere_source.py`; use a thin Slang uniform/resource adapter and graph fragment. Retain sqrt transmittance encoding, default two-ray multi-scattering, sample offset 0.3, finite five-order scattering sum and native storage formats. Unsupported HQ/small-format requests must reject explicitly.
- [x] Independently implement `atmosphere_reference.py` for offline validation. Verify vacuum, pure absorption, positive scattering, encoding, ground reflection and parameter changes. CPU oracle outputs are observations and are never uploaded.
- [x] Run native declared graphs at source and authored dimensions. Compare raw GPU LUTs with the independent oracle, test repeatability and parameter restaging, and retain an atlas and process receipt. Validate storage conversion separately from integration/sampling. Source evidence `run-7ie9tom4`; source-radius precision is bounded conservatively, not asserted bit-exact.
- [ ] Preserve source environment inventory in `Scene.json` and expose optional LUT graph composition. Run CPU regression suite and native source-scene composition test; obtain independent source and code review and record evidence/limits.

Validation commands (worktree `E:/Project/falcor/Falcor-m0`):

```powershell
$env:PYTHONPATH='scripts/ue_legacy;build/m0-evidence/python'
& build/windows-vs2022/bin/Release/pythondist/python.exe -m unittest discover -s scripts/ue_legacy -p 'test_atmosphere*.py'
& build/windows-vs2022/bin/Release/pythondist/python.exe build/run_ue_closure_validation.py atmosphere scripts/ue_legacy/atmosphere_gpu_smoke.py
& build/windows-vs2022/bin/Release/pythondist/python.exe -m unittest discover -s scripts/ue_legacy -p 'test_*.py'
git diff --check
```

Acceptance of this slice is not acceptance of capture equality: source commandlet CVars are not proof of capture runtime overrides. The LUTs alone provide no camera sky background, aerial perspective or SkyLight irradiance yet. No captured texture/constant/depth/history is a rendering input.
