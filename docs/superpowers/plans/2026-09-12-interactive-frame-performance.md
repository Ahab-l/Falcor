# Interactive source-frame performance repair

> Execute in the existing worktree with subagent-driven-development for the independent immutable Compute cache. Root owns all native builds and GPU execution. No commits or merges.

**Goal:** repair the slow visible targetmap preview without reducing source resolution, shading precision, automatic exposure, or using captured/readback data as input.

**Architecture:** give Mogwai an optional graph execution callback after normal scene updates, replacing (not preceding) the default graph execution. The source preview uses its existing temporal executor once per display frame. Preserve the default execution path when no callback is installed. Cache explicitly input-free immutable Compute generators in private GPU resources and restore outputs from those resources, preventing transient aliasing or downstream writes from corrupting the cache. Only PreintegratedGF opts in initially.

**Original evidence:** the retired build/targetmap-live/launch.py called pipeline.render_frame in sceneUpdateCallback; Mogwai then executed the graph again. It also slept for a 15 FPS cap and recomputed GF with 128 samples per texel. PID37040 exited. That scratch entry now forwards to the repaired source viewer.

- [x] Root: reproduce unavailable graph-execution callback with the installed binary; add generic optional callback to Mogwai after scene update notification, preserving default path and avoiding stale graph references across callback changes.
- [x] Cache subtask: add opt-in immutable input-free Compute execution cache, CPU/native rejection, unchanged GPU outputs over repeats/resize/replacement, and dispatch counts. Preserve exact GF shader arithmetic; use only GPU-produced cache resources.
- [x] Root: replace live launch callback, remove artificial cap, disable verbose draw logging. Add bounded benchmark mode and native profiler receipts.
- [x] Root: serial build, callback/default-path test, cache and history regressions, full source same-view timing and pixel comparisons. Attribute residual synchronous readbacks and stage costs before additional changes.
- [x] Root: update documentation, report measured results and remaining limitations, and reopen the repaired preview only after validation.

The current synchronous history API retires heaps and waits before publishing. Avoid changing temporal publication semantics merely to optimize before measurements. GPU pre-exposure readbacks also remain measurable candidates, not assumed eliminated. SkyLight capture/filter remains dynamic until source dependencies and invalidation are proven.

Verified repair: same-view mean83.82ms→59.35ms(single execution)→20.15ms(cachedGF+per-execution identity snapshot), final49.63FPS. Five raw outputs (combined/exposed color, pre-exposure/exposure,GF) byte exact versus single uncached baseline.455Python,15nativeidentity,hostcallback,cache/history/Shader GPU pass. Report docs/research/ue-legacy-interactive-performance.md; comparison build/targetmap-live/comparison.json. Visible repaired PID173992 ran1200frames; recent intervals34.90 and36.48FPS. It had exited by final process inspection; stderr empty. Do not equate the headless49.63FPS measurement to live presentation FPS. This repair is verified; residual sync costs and fullRDC alignment remain open.
