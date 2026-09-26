# V5 completion design addendum

This closes the previously authored native Inspector, not a new UI framework. Use Falcor PythonUI and the existing Schema observer/model/service.

Fix Windows file picker path encoding using a Unicode-safe native/path binding conversion, preserving exact non-ASCII text and cancellation. Catch picker exceptions inside the panel and publish visible error state, keeping the panel and future actions usable. Preserve weak callbacks, listener removal and texture reference release on close/reopen. Normal preview remains GPU-only and idle performs no decoding/readback.

Acceptance: test-first Unicode/error/cancel/lifecycle regressions; native GPU UI and panel tests; real mouse click on preview, pixel selection, source/mapping, file picker (Unicode file), comparison/export, cancel/error and close/reopen using official Computer Use. Callback invocation alone never counts as actual UI acceptance. If the user interrupts Computer Use stop inputs and retain goal unfinished until acceptance can resume. Final Chinese guide, screenshots and review accompany verified results.
