# Neutral described passes and native MeshDraw

The user approved the preceding concrete migration design: JSON directly assembles native RenderGraph; Compute/Fullscreen stop requiring old schemaPath/sceneDefinition or injecting UE shader source; MeshDraw selects native instanceIDs and submits through Scene::RasterDrawList, without old material tables or required UEMeshPass/reverse-Z. This document records that approved scope rather than reopening the architecture discussion.

## Boundaries

Keep the current worktree and uncommitted work. No commits/merges, whole-graph rollback work, UE algorithm migration, Asset/History migration, V5 work or wholesale old-code deletion. Preserve existing explicit UE/reference cases while removing their prerequisites from the new default path. Backend support remains the existing D3D12/SM6.6 scope. New Schema/codec and resource/view correctness remain intact.

## Architecture

- Main Python graph assembly accepts a neutral version-1 node/edge/output description, resolves pass-file origins, validates structural errors and calls native APIs. Old transaction behavior is isolated under extensions/ue_reference, lazily available only for explicit legacy calls.
- Existing Compute/Fullscreen and Mesh executors retain their resource reflection, clear/load/alias validation, typed bindings and graphics state. Their shared description context contains only options, source loading and optional compatibility data; it never constructs the old Config on the native path. An explicit UEReference bridge supplies frozen sources, expanded resources and legacy behavior for old callers, avoiding duplicate generic executors.
- Native source loading uses Falcor's file-based ProgramDesc for reload behavior, not old immutable snapshot ingestion. No inferred UE encoding or exposure. Optional dynamic preExposure only exists through an explicit legacy extension; native users provide literal or resource parameters.
- Native Mesh selection is instanceIDs (omitted=all raster instances, empty=none), validates IDs before clears, uses existing Scene draw lists, and honors native scene geometry/material identity. Shader uses native Scene data, with optional explicitly named view-projection binding rather than a mandatory engine-specific constant buffer. Depth defaults to conventional clear=1/LessEqual; explicit depth/stencil/cull/blend/viewport attachments remain supported.
- Existing old per-material builtin writes and routing stay in a compatibility policy implemented within UEReference, not as required inputs of the native executor. This is a transitional bridge for existing references, not a second graph scheduler or a second native renderer.

## Acceptance

1. CPU RED/GREEN for neutral graph parsing, file origins, unknown keys, bad node/edge/output structure, no legacy imports on the native path.
2. GPU RED on direct Compute/Fullscreen/Mesh creation without legacy properties; GREEN after migration.
3. Native JSON graph produces known compute pixels, composes fullscreen and stock Blit, binds structured resources, allows output updates and rejects bad typed/state/dispatch input.
4. Mesh tests compare selected/all/empty sets to existing native raster output, verify load-preservation and different pass selections, pass recreation, native scene/material changes, explicit view/depth state, and ensure no UEMeshPass or material-name table is required.
5. Build Release Mogwai using pinned CMake 3.24.1; full Python suite and representative legacy executor/Mesh regressions plus native Schema/observer regression run serially without opening a visible UI. Record actual evidence and remaining limits.
6. Independent spec then quality review; update usage/Todo only for implemented and verified scope. Backup source bytes/hashes are under build/native-pass-migration.
