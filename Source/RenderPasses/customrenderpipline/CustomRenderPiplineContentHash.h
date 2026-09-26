#pragma once
#include "Falcor.h"
#if FALCOR_WINDOWS
#include <Windows.h>
#include <bcrypt.h>
#endif

namespace Falcor::CustomRenderPipline
{
inline std::string contentSHA256(const std::string& data)
{
#if FALCOR_WINDOWS
    FALCOR_CHECK(data.size()<=ULONG_MAX,"Pipeline identity input exceeds Windows hash API size");
    struct Provider
    {
        BCRYPT_ALG_HANDLE handle=nullptr;
        ~Provider() { if(handle) BCryptCloseAlgorithmProvider(handle,0); }
    } provider;
    FALCOR_CHECK(BCryptOpenAlgorithmProvider(&provider.handle,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,"Cannot open SHA256 provider");
    std::array<uint8_t,32> bytes={};
    FALCOR_CHECK(BCryptHash(provider.handle,nullptr,0,reinterpret_cast<PUCHAR>(const_cast<char*>(data.data())),ULONG(data.size()),
        bytes.data(),ULONG(bytes.size()))>=0,"Cannot compute Pipeline SHA256");
    std::string result;
    for(auto b:bytes) result+=fmt::format("{:02x}",b);
    return result;
#else
    FALCOR_THROW("Current UE D3D12 Pipeline SHA256 provider requires Windows");
#endif
}
}
