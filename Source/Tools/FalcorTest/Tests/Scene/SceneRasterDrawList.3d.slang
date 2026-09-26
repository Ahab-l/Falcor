import Scene.Raster;
VSOut vsMain(VSIn input) { return defaultVS(input); }
uint psMain(VSOut input) : SV_Target0 { return input.instanceID.index + 1; }
