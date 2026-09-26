using UnrealBuildTool;

public class SourceTextureExport : ModuleRules
{
    public SourceTextureExport(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "Json", "RenderCore", "RHI" });
    }
}
