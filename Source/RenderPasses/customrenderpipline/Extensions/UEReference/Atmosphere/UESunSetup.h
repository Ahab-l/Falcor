#pragma once
#include <nlohmann/json_fwd.hpp>

namespace Falcor::CustomRenderPipline::SunSetup
{
// Source component settings only; derived transmittance/color cannot be supplied.
// Independent source mathematics used by the observation binding; no GPU/readback dependencies.
nlohmann::json evaluate(const nlohmann::json& settings);
}
