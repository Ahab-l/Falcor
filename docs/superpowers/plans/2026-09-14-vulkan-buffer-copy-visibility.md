# Vulkan buffer-copy visibility repair

Continuation of the approved native nonblocking readback implementation, not a new framework or ABI.

**Goal:** Preserve exact initialized Buffer bytes when an initialized Texture upload occurs before the first buffer copy/readback, without CPU waits, extra queue submissions, or loss of Vulkan coverage.

**Evidence:** A standalone Vulkan 1.2 executable reproduces the same zero snapshot on RTX 4090 / driver 616.56, without Falcor, GFX, a shader or task. Full RenderDoc replay also reproduces, whereas partial-event replay synchronizes away the defect. The spec-valid TRANSFER_WRITE→TRANSFER_READ dependency passes synchronization validation but gives zero bytes. ALL_COMMANDS alone and widening only source writes do not fix it; broadening destination memory reads does. Artifacts are under `build/native-framework-completion/raw-access-scope-zpxik_hl` and `vk-repair-staging-capture-layer-vkt3nu8x`.

**Architecture:** For Vulkan DeviceLocal buffer CopyDest→CopySource barriers, use GFX General as the destination access scope while preserving Falcor's logical CopySource tracking. Vulkan buffers have no native image layout to change. This is conservative driver compatibility, not a claim that the original transfer barrier is spec-invalid. All other states/backends remain unchanged.

Alternatives: CPU-drain is rejected because it violates nonblocking submission. GPU semaphore/submit split was proved correct by the standalone test but rejected in favor of one broader buffer dependency with no extra submission. Global access/stage expansion is unnecessary; keep the workaround local to transfer RAW buffers.

- [ ] Add formal mixed-upload async/sync/region-copy tests, including multiple sizes and exact sentinels; verify expected RED before changing production.
- [ ] Back up the exact current production/test bytes and change only the Vulkan copy barrier destination scope.
- [ ] Build with pinned CMake; strict native Logger + bytes tests on both backends; repeat old lifetime cases unchanged.
- [ ] Independent bounded source review. Check backend isolation, logical state tracking, no extra wait/submit, regression coverage and limitations.
- [ ] Archive and remove temporary lifetime diagnostic switches / RenderDoc integration, retaining the pure Vulkan reproduction and immutable RED/GREEN evidence.
- [ ] Continue legal pending fixtures, strict R4/Q1 matrix, real V5 UI and performance. This repair is not the complete goal.

No commits, merges, device-driver updates, or global Vulkan layer configuration changes.
