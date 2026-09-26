# Windows exception stack trace memory defects

The intermittent candidate-rejection/resize crashes led to symbol-location evidence: KERNELBASE+0x1e0a0 resolves to `MultiByteToWideChar+0x380`, scanning for a terminating zero. This is consistent with, but does not conclusively attribute every historical crash to, the defects below.

Bundled `external/include/backward/backward.hpp` passed vectors constructed from string begin/end to `SymLoadModule64` without terminating NULs. Adjacent failure paths used unchecked module-name buffers, undefined demangling output and uninitialized line metadata. The resolver could also dereference a null PE header after module-information failure.

The fix uses `c_str()`, checks Win32 return values/lengths, retains the resolved symbol name if demangling fails, initializes `IMAGEHLP_LINE::SizeOfStruct`, and falls back to the compiled architecture when no valid module header exists. It changes no rendering mathematics.

`Source/Tools/FalcorTest/Standalone/BackwardModuleStrings` exercises the actual header with Win32 failure interception and MSVC ASan. RED logs include `build/backward-string-repro/red-symbols.log`, `build/backward-symbol-red.log`, `build/backward-resolver-red.log`. All seven tests pass in `build/backward-tests-final.log`.

Fresh ordinary native runs after the fix, without debugger or fault recorder:

- Downsample/resize twice: `build/downsample-gpu/run-xtli60g4/result.json`, `run-xrjku2hx/result.json`; launches `run-p08nvicp`, `run-ntw1ykgd`.
- Relative sizes/rejections: `build/relative-size-gpu/run-1eylrxgg/result.json`; launch `run-mis74_x1`.
- Mesh/Adapter exposure/native rejections: `build/scene-exposure-gpu/run-jb8byb3i/result.json`; launch `run-p_ef_vf_`.
- After removing cancelled HZB work: `build/observer-gpu/run-4xqhlziw/result.json`, `build/downsample-gpu/run-2ei_c0mc/result.json`; launches `run-9gmiatpb`, `run-sckkhkv6`.

All launch receipts in `build/ue-lighting-closure-cache` report exit0. The deterministic ASan defects are fixed; finite passing runs do not prove every possible intermittent fault eliminated. No speculative global DbgHelp lock was added.

To run the standalone tests, prepend the installed MSVC ASan DLL directory to PATH, then use pinned CMake/CTest:

```powershell
cmake -S Source/Tools/FalcorTest/Standalone/BackwardModuleStrings -B build/backward-module-tests -G "Visual Studio 17 2022" -A x64
cmake --build build/backward-module-tests --config Release
ctest --test-dir build/backward-module-tests -C Release --output-on-failure
```
