# C2 native source cleanup design

User authorization: remove the leftover obsolete source/dependencies described by C2, while retaining generic capabilities and useful algorithms/reference data.

Keep native GBuffer/Schema, ShaderPass/PassDescription's neutral resource parsing, MeshDraw/Scene draw lists, native History/Asset, observer/RTV/readback and independent Sun/Sky mathematics. First archive exact bytes/hashes. Remove uncompiled Config/SceneIdentity/FrameReadback/Geometry/Routing/Adapter/old Passes and UE compatibility/setup wrapper C++ and their exclusively obsolete headers/tests. Keep actual UE shader algorithm excerpts/provenance under Extensions/UEReference as reference assets; move legacy ABI-only codecs/material glue/JSON to a clearly documented archive rather than presenting it as supported runtime. A caller trace, not the filename, decides removals.

Remove PassCompatibility factory/delegation and MeshPassCompatibility policy branches now that no registered factory exists. Remove RenderGraph's old ExecutionValidator/hasExternalInputs sealing policy and observer's empty validator invocation; preserve topology/device/execute, resource compatibility, native external inputs and all core graphics fixes. The generic MeshRasterizers alias stays local to the native implementation if still used.

Acceptance: clean include/build source graph, no live deleted-path references or old export, pinned Release Mogwai/FalcorTest build, complete retained CPU tests and native GPU regression. Archive inventory explains each removed path and preserved algorithm counterpart. No whole-graph rollback or UE effect translation.
