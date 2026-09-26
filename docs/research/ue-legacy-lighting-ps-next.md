# Current PS residual: next observation

No new production math change is justified by this read-only inspection. The useful next step is a fixed GPU material-prefix observation; the existing sphere/Newton/GGX association table already covers the visible CLI differences.

The 31 residuals have 20 floor normals `[511,511,1023]`, 9 wall normals `[0,511,511]`, and 2 sphere normals. All have gray BaseColor and a white raw shadow texel; 8 have nonzero metallic. Raw A/B/C bytes at all 31 match captured resources. NPZ B/C are physical BGRA:

| Pixel | Metallic byte | Roughness byte | Native−UE RGB ULP | Native specular share |
|---|---:|---:|---|---:|
| (966,1015) |218|86|+4,+4,+5|14.43%|
| (880,701) |106|119|−3,−3,−3|6.34%|

Both share the floor normal. Across 31, CPU64 ideal NoL is 0.638–0.986 and the smallest `cosAlpha−RoL` margin is 0.310. Those calculations classify a robust path; they are not observed GPU intermediates.

`normalize(N)` and `normalize(V)` have matching dot3→rsqrt→component-multiply skeletons, then V is negated. Capture text 191–195 and349–353/400–402 correspond to precise CLI 442–446 and304–311, current outer 139/157. Equal ScreenVector does not establish normalized V bits. Captured material reads 86/90/93 use SampleLevel; CLI 238–244 uses textureLoad. Matching packed bytes and SRV formats do not directly prove equal sampled float32 values. No sampled-value difference has been demonstrated.

The diffuse chain is `base-base*metallic` in capture 250–255 and CLI 969–974. The largest point has relative input sensitivity 6.89 from `1/(1-metallic)`. This motivates observing material floats before assigning its correlated RGB residual to specular/Newton; it does not identify the cause. The previous GGX/NoL/SphereSinAlpha/Newton associations remain hypotheses, and half residual counts must not select variants.

[Evidence JSON](../../build/lighting-ps-next-evidence.json) contains 43 rows, hashes, exact anchors and executable preparation code in `next_experiment.preparation_python`. That code derives a new observer in build with the sole debug write:

```slang
result.transmission = float4(surface.baseColor.r, surface.metallic,
    surface.roughness, shading.area.NoL);
```

After preparation, the next GPU task can run:

```powershell
& .\build\windows-vs2022\bin\Release\Mogwai.exe --headless --script build/lighting-ps-prefix-next.py
```

It preserves the paired observer's source/pipeline and all 12 unchanged-output gates. Preparation and generated observer were syntax-checked in memory only; no GPU/build/replay ran and no observer script was created. Reconstruct native diffuse from actual output `(c,m,r,n)` with float32 rounding at each captured operation, then compare `directDiffuse` bits. A match accounts for native diffuse only; definitive UE prefix comparison still requires actual GPU instrumentation. Saved interpreter states cannot substitute. The JSON specifies fixed N/V follow-ups and decision limits.
