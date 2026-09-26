# FY1 hair in the native deferred framework

User objective: reproduce the hair from the referenced task 了解 RenderDoc CLI 和 MCP
in our Falcor framework using deferred rendering, through the matching Shading
stage; postprocessing is excluded. This is the full objective, not just an asset
import or isolated BRDF unit test.

Authoritative target: E:/rdc/fy/fy1.rdc, hair BasePass EID7861,
53676 indices/13828 vertices, followed by independent light contribution EID14389
(SceneColor14389 minus14372), not final postprocessed SceneColor. Reference
analysis/assets: D:/BaiduNetdiskDownload/RenderDocPro_1.44.0-pro.4_64/analysis/hair_fy1.
The attached image identifies the earlier task rather than containing a hair image.

Use current Falcor-m0 worktree and preserve its uncommitted framework work.
No UE/RDC/source-analysis writes, commits or merges. Current posed geometry and
the original bound material textures/parameters may be imported as case assets.
Do not feed captured GBuffer, depth, coverage, shadow-mask or Shading images into
production rendering. Readback reference data is for comparisons only. The old
Web3D capture preset used such intermediates and is not proof of native parity.

Pipeline: immutable file assets -> depth-only scene occluders and alpha-tested
hair -> Hair GBuffer -> independent native deferred Hair lighting -> raw HDR.
Prefer existing declared MeshDraw/Compute/Fullscreen and Schema interfaces.
Add a generic immutable asset source executor if needed for original texture/
buffer uploads, rather than embedding case paths in C++.
Reconstruct necessary light-volume, depth-bounds and visibility/shadow terms from
geometry so capture-camera matching uses generated frame resources. Imported
pose is not a claim of recovered T-pose, rig or animation.

Acceptance: verified model/UV/tangent-frame identity and same capture projection;
native alpha/depth coverage and GBuffer comparisons at native sampling; Hair
lobes/probes agree with original shader evidence; final Shading compares across
the full hair region including union coverage, with quantitative errors and
visual side-by-side inspection. Preserve original Shader precision/texture formats.
Any unresolved error stays unfinished. Validate changed inputs or camera cause
recomputed deferred outputs. Provide runnable native viewer/graph and document
pass/material definitions. No postprocessing matching.

Alternative considered: capture-fed WebGL preview is useful reference but cannot
satisfy the native deferred requirement. A standalone monolithic hair renderer
would bypass the framework. Reuse declared passes and keep material/lighting
logic in case Shaders and graph declarations.
