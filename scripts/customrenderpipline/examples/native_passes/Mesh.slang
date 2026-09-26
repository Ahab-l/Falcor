#include "Scene/VertexAttrib.slangh"
import Scene.Raster;

VSOut vsMain(VSIn v) { return defaultVS(v); }
float4 psMain(VSOut v) : SV_Target0
{
    // Native Scene data is available; no material name table or UEMeshPass ABI.
    return float4(1.0, 0.5, float(v.instanceID.index) * 0.1, 1.0);
}
