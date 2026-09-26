#include "../../../RenderPasses/customrenderpipline/Extensions/UEReference/Atmosphere/UESunSetup.h"
#include <nlohmann/json.hpp>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>

using Json = nlohmann::json;
using Falcor::CustomRenderPipline::SunSetup::evaluate;
void require(bool value, const char* label) { if (!value) throw std::runtime_error(label); }
void close(double a, double b, double tolerance, const char* label) { require(std::abs(a-b)<=tolerance, label); }
template<typename F> void rejects(F f) { bool caught=false; try { f(); } catch (const std::exception&) { caught=true; } require(caught,"invalid input accepted"); }
Json fixture()
{
    return {{"working_color_space", "sRGB"}, {"color_srgb", {255,255,255}}, {"intensity", 6.0},
        {"use_temperature", false}, {"temperature_kelvin", 6500.0}, {"atmosphere_sun", true},
        {"per_pixel_transmittance", false}, {"direction_ue", {0,0,1}}, {"source_angle_degrees", 0.7357},
        {"disk_color_scale", {1,1,1}}, {"transmittance_min_elevation_degrees", -90},
        {"atmosphere", {{"BottomRadiusKm", 10}, {"TopRadiusKm", 12},
        {"MieExtinction", {0,0,0}}, {"RayleighScattering", {0,0,0}}, {"AbsorptionExtinction", {0,0,0}},
        {"MieDensityExpScale", 0}, {"RayleighDensityExpScale", 0}, {"AbsorptionDensity0LayerWidth", 0},
        {"AbsorptionDensity0LinearTerm", 0}, {"AbsorptionDensity0ConstantTerm", 0},
        {"AbsorptionDensity1LinearTerm", 0}, {"AbsorptionDensity1ConstantTerm", 0}}}};
}
int main(int argc, char** argv)
{
    if (argc==2)
    {
        std::ifstream f(argv[1]); Json inputs; f>>inputs;
        Json outputs=Json::array(); for (const auto& input:inputs) outputs.push_back(evaluate(input));
        std::cout<<outputs.dump(2)<<'\n'; return 0;
    }
    auto input=fixture(); auto output=evaluate(input);
    require(output["ground_transmittance"]==Json({1,1,1}),"vacuum");
    require(output["direct_illuminance"]==Json({6,6,6}),"temperature disabled");
    input["color_srgb"]={128,64,196}; output=evaluate(input);
    for (int i=0;i<3;++i)
    {
        double code=input["color_srgb"][i].get<double>()/255;
        close(output["outer_space_illuminance"][i],6*std::pow((code+.055)/1.055,2.4),3e-7,"sRGB decoding");
    }
    input=fixture(); input["atmosphere"]["MieExtinction"]={.1,.2,.3}; output=evaluate(input);
    for (int i=0;i<3;++i) close(output["ground_transmittance"][i],std::exp(-.1*(i+1)*1.5),2e-7,"constant medium Beer law");
    input["direction_ue"]={1,0,0}; input["transmittance_min_elevation_degrees"]=30;
    auto clamped=evaluate(input); input["direction_ue"]={std::sqrt(.75),0,.5}; input["transmittance_min_elevation_degrees"]=-90;
    for(int i=0;i<3;++i) close(evaluate(input)["ground_transmittance"][i],clamped["ground_transmittance"][i],2e-7,"elevation clamp");
    input=fixture(); input["use_temperature"]=true; output=evaluate(input);
    // Independent sRGB XYZ matrix inversion and Planckian rational, evaluated offline in float64.
    const double white6500[]={1.04415519, .98326854, 1.03569215};
    for(int i=0;i<3;++i) close(output["outer_space_illuminance"][i],6*white6500[i],1e-5,"working-space 6500 K");
    input["temperature_kelvin"]=500; auto low=evaluate(input); input["temperature_kelvin"]=1000;
    require(evaluate(input)==low,"temperature clamp");
    input=fixture(); input["atmosphere_sun"]=false; input["atmosphere"]["MieExtinction"]={1,1,1};
    require(evaluate(input)["direct_illuminance"]==Json({6,6,6}),"non-atmosphere directional light");
    input=fixture(); input["per_pixel_transmittance"]=true; rejects([&]{evaluate(input);});
    for (auto bad: {Json(true),Json(-1),Json(1e100)}) { input=fixture();input["intensity"]=bad;rejects([&]{evaluate(input);}); }
    input=fixture();input["direction_ue"]={0,0,0};rejects([&]{evaluate(input);});
    input=fixture();input["working_color_space"]="ACEScg";rejects([&]{evaluate(input);});
    input=fixture();input["ground_transmittance"]={1,1,1};rejects([&]{evaluate(input);});
    std::cout<<"SUN_SETUP_PASS\n";
}
