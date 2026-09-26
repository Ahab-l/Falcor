#define NOMINMAX
#include <windows.h>
#include <imagehlp.h>
#include <psapi.h>
#include <string>
#include <cstdio>
#include <cstring>

static std::string mode;
static unsigned moduleLoads = 0;
static bool lineSizeValid = false;

// The sink retains the native NUL-terminated PCSTR contract, using ASan-visible
// string reads. The module/name construction under test is the real dependency.
static DWORD64 WINAPI checkedSymLoadModule64(HANDLE,HANDLE,PCSTR image,PCSTR module,DWORD64 base,DWORD)
{
    const std::string imageCopy(image), moduleCopy(module);
    if (imageCopy.empty() || moduleCopy.empty()) std::abort();
    ++moduleLoads;
    return base;
}
static BOOL WINAPI checkedModuleInformation(HANDLE process, HMODULE module, LPMODULEINFO info, DWORD size)
{
    if (mode == "module-failure" || mode == "resolver-module-failure") return FALSE;
    return GetModuleInformation(process,module,info,size);
}
static DWORD WINAPI checkedModulePath(HANDLE process, HMODULE module, LPSTR buffer, DWORD size)
{
    if (mode == "path-failure") { std::memset(buffer,'X',size); return 0; }
    return GetModuleFileNameExA(process,module,buffer,size);
}
static DWORD WINAPI checkedModuleName(HANDLE process, HMODULE module, LPSTR buffer, DWORD size)
{
    if (mode == "name-failure") { std::memset(buffer,'X',size); return 0; }
    return GetModuleBaseNameA(process,module,buffer,size);
}
static DWORD WINAPI checkedUndecorate(PCSTR input,PSTR output,DWORD size,DWORD flags)
{
    if (mode == "symbol-failure") { std::memset(output,'X',size); return 0; }
    return UnDecorateSymbolName(input,output,size,flags);
}
static BOOL WINAPI checkedSymbol(HANDLE process,DWORD64 address,PDWORD64 displacement,PSYMBOL_INFO symbol)
{
    if (mode == "symbol-failure")
    {
        std::strcpy(symbol->Name,"known");symbol->NameLen=5;*displacement=0;return TRUE;
    }
    return SymFromAddr(process,address,displacement,symbol);
}
static BOOL WINAPI checkedLine(HANDLE,DWORD64,PDWORD,PIMAGEHLP_LINE64 line)
{
    lineSizeValid = line->SizeOfStruct == sizeof(*line);
    return FALSE;
}
#define SymLoadModule64 checkedSymLoadModule64
#undef GetModuleInformation
#undef GetModuleFileNameExA
#undef GetModuleBaseNameA
#define GetModuleInformation checkedModuleInformation
#define GetModuleFileNameExA checkedModulePath
#define GetModuleBaseNameA checkedModuleName
#define UnDecorateSymbolName checkedUndecorate
#define SymFromAddr checkedSymbol
#define SymGetLineFromAddr64 checkedLine
#include <backward/backward.hpp>
#undef SymGetLineFromAddr64
#undef UnDecorateSymbolName
#undef SymFromAddr
#undef GetModuleBaseNameA
#undef GetModuleFileNameExA
#undef GetModuleInformation
#undef SymLoadModule64

int main(int argc,char** argv)
{
    mode = argc > 1 ? argv[1] : "strings";
    if (mode == "resolver-module-failure")
    {
        backward::TraceResolver resolver;
        if (resolver.machine_type() != IMAGE_FILE_MACHINE_AMD64 || moduleLoads != 0) return 6;
    }
    else if (mode == "symbol-failure" || mode == "line-size")
    {
        backward::TraceResolver resolver;
        backward::Trace input(reinterpret_cast<void*>(1),0);
        const auto result = resolver.resolve(input);
        if (mode == "symbol-failure" && result.source.function != "known") return 3;
        if (mode == "line-size" && !lineSizeValid) return 4;
    }
    else
    {
        backward::get_mod_info inspect(GetCurrentProcess());
        const auto result=inspect(GetModuleHandleW(nullptr));
        if (mode == "strings")
        {
            if (result.image_name.empty() || result.module_name.empty() || moduleLoads != 1) return 2;
        }
        else if (moduleLoads != 0) return 5;
    }
    std::printf("BACKWARD_MODULE_STRINGS_PASS %s\n",mode.c_str());
}
