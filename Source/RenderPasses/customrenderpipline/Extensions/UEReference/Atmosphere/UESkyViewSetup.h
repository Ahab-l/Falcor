#pragma once
#include <array>
#include <cstdint>

namespace Falcor::CustomRenderPipline::SkyViewSetup
{
struct Input
{
    float bottomRadiusKm=6360.f;
    uint8_t transformMode=0; // UE: absolute planet top, component planet top, component planet center.
    std::array<double,3> componentTranslationCm{};
    std::array<double,3> cameraUECm{};
    std::array<double,3> preViewTranslationCm{};
    std::array<float,3> viewForwardUE{1,0,0};
    std::array<float,3> viewRightUE{0,1,0};
};
struct Result
{
    std::array<double,3> planetCenterKm{};
    std::array<float,3> skyCameraTranslatedCm{};
    std::array<float,4> planetTranslatedCmAndHeight{};
    // Exact UE matrix rows. Do not impose a common handedness on the two UE basis branches.
    std::array<std::array<float,4>,4> referential{};
};
Result evaluate(const Input& input);
}
