# Q1/R5/S4 wider validation design

Close the documented finite gaps rather than asserting every possible GPU configuration. Q1 includes resource-relative multihop/fixed/inputOutput/Mesh sizes, group axis/max_size failures and recovery, raw/structured alias and writer-conflict rejection, once shader/uniform replacement/default-every-frame, explicit base-mip Cube SRV, and the retained GF-style fixed-table compute cache comparison.

R5/S4 cover actual supported texture/buffer/Cube/array/mip formats, depth/stencil planes and backend branches touched by our patches. Execute D3D12 matrix and available Vulkan core/observer combinations. Existing explicit unsupported Cube RTV/DSV/UAV/generateMips or MSAA/raw readback boundaries must have rejection tests and clear documentation; tests of explicit rejection do not mean those operations are supported. Reachable implementation defects found in supported combinations must be fixed and regression-tested. Backend initialization or tooling failures leave corresponding acceptance incomplete, not silently green.

Run tests serially with debug layer and fresh result JSON/marker checks; verify authoritative bytes, extents, final output, counter and state recovery, not just construction or exit code. Preserve useful historical inputs in archives. Record all matrix entries, supported/rejected/failed/untested states, exact commands and limitations.
