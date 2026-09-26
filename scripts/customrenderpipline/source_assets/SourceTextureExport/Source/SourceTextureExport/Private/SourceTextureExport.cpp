#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"
#include "Engine/Texture2D.h"
#include "TextureCompiler.h"
#include "AssetCompilingManager.h"
#include "ShaderCompiler.h"
#include "Misc/CoreDelegates.h"
#include "TextureResource.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

// Source-side diagnostic module, never part of Falcor or the original project.
// Loaded at commandlet PostEngineInit (before Main); performs one bounded export.
class FSourceTextureExportModule : public IModuleInterface
{
    FDelegateHandle DrainHandle;
    static bool Export(const FString& Out, const TSharedRef<FJsonObject>& Result, FString& Error)
    {
        const TCHAR* Object = TEXT("/Engine/OpenWorldTemplate/LandscapeMaterial/T_GridChecker_A.T_GridChecker_A");
        Result->SetStringField(TEXT("source_object"), Object);
        Result->SetBoolField(TEXT("capture_inputs"), false);
        UTexture2D* Texture = LoadObject<UTexture2D>(nullptr, Object);
        if (!Texture) { Error = TEXT("LoadObject failed"); return false; }
        UTexture* Textures[] = { Texture };
        FTextureCompilingManager::Get().FinishCompilation(MakeArrayView(Textures));
        FTexturePlatformData* Platform = Texture->GetPlatformData();
        if (!Platform) { Error = TEXT("No platform data after source compilation"); return false; }
        Result->SetNumberField(TEXT("width"), Platform->SizeX);
        Result->SetNumberField(TEXT("height"), Platform->SizeY);
        Result->SetNumberField(TEXT("pixel_format_enum"), int32(Platform->PixelFormat));
        Result->SetBoolField(TEXT("srgb"), Texture->SRGB != 0);
        Result->SetStringField(TEXT("encoder"), Platform->ResultMetadata.Encoder.ToString());
        Result->SetBoolField(TEXT("encoder_metadata_valid"), Platform->ResultMetadata.bIsValid);
        Result->SetNumberField(TEXT("encode_speed"), Platform->ResultMetadata.EncodeSpeed);
        Result->SetNumberField(TEXT("oodle_rdo"), Platform->ResultMetadata.OodleRDO);
        if (Platform->SizeX != 512 || Platform->SizeY != 512 || Platform->PixelFormat != PF_DXT1 ||
            Platform->Mips.Num() != 10 || !Texture->SRGB)
        { Error = TEXT("Source-built platform texture is not expected 512x512 BC1 sRGB 10 mips"); return false; }
        TArray<void*> Data;
        TArray<int64> Sizes;
        Data.SetNumZeroed(10); Sizes.SetNumZeroed(10);
        // Virtual public API dispatches into Engine and returns allocation sizes.
        // It uses PlatformData.TryLoadMipsWithSizes, not Texture.Source.
        const bool Loaded = Texture->GetInitialMipData(0, MakeArrayView(Data), MakeArrayView(Sizes));
        ON_SCOPE_EXIT { for (void* Pointer : Data) FMemory::Free(Pointer); };
        if (!Loaded) { Error = TEXT("GetInitialMipData failed"); return false; }
        TArray64<uint8> Payload;
        TArray<TSharedPtr<FJsonValue>> Mips;
        for (int32 Index = 0; Index < 10; ++Index)
        {
            const int32 Side = FMath::Max(1, 512 >> Index);
            const int64 Expected = int64(FMath::Max(1, (Side + 3) / 4)) * FMath::Max(1, (Side + 3) / 4) * 8;
            if (!Data[Index] || Sizes[Index] != Expected || Platform->Mips[Index].SizeX != Side || Platform->Mips[Index].SizeY != Side)
            { Error = TEXT("Source mip allocation does not match BC1 geometry"); return false; }
            TSharedRef<FJsonObject> Mip = MakeShared<FJsonObject>();
            Mip->SetNumberField(TEXT("level"), Index);
            Mip->SetNumberField(TEXT("width"), Side); Mip->SetNumberField(TEXT("height"), Side);
            Mip->SetNumberField(TEXT("offset"), Payload.Num()); Mip->SetNumberField(TEXT("bytes"), Sizes[Index]);
            Mips.Add(MakeShared<FJsonValueObject>(Mip));
            Payload.Append(static_cast<const uint8*>(Data[Index]), Sizes[Index]);
        }
        if (Payload.Num() != 174776) { Error = TEXT("Unexpected full-chain length"); return false; }
        if (!FFileHelper::SaveArrayToFile(Payload, *(Out / TEXT("platform-mips.bin")), &IFileManager::Get(), FILEWRITE_NoReplaceExisting))
        { Error = TEXT("Cannot exclusively write mip payload"); return false; }
        Result->SetStringField(TEXT("payload"), TEXT("platform-mips.bin"));
        Result->SetStringField(TEXT("format"), TEXT("BC1UnormSrgb"));
        Result->SetArrayField(TEXT("mips"), Mips);
        return true;
    }

public:
    virtual void StartupModule() override
    {
        FString Out;
        if (!FParse::Value(FCommandLine::Get(), TEXT("SourceTextureOut="), Out)) return;
        Out = FPaths::ConvertRelativePathToFull(Out);
        // Parent is root-launcher-owned and new; never create outside directories.
        if (!IsRunningCommandlet() || !IFileManager::Get().DirectoryExists(*Out) ||
            IFileManager::Get().FileExists(*(Out / TEXT("result.json"))) ||
            IFileManager::Get().FileExists(*(Out / TEXT("platform-mips.bin"))))
        { UE_LOG(LogTemp, Error, TEXT("SOURCE_TEXTURE_EXPORT rejected output/commandlet context")); return; }
        // This source engine's pending shader cancellation crashes during the
        // Python shutdown GC. Finish owned source work before that phase; do not
        // bypass shutdown or patch the original engine/cache implementation.
        DrainHandle = FCoreDelegates::OnCommandletPostMain.AddLambda([]()
        {
            FAssetCompilingManager::Get().FinishAllCompilation();
            if (GShaderCompilingManager) GShaderCompilingManager->FinishAllCompilation();
            const int32 Remaining = FAssetCompilingManager::Get().GetNumRemainingAssets();
            UE_LOG(LogTemp, Display, TEXT("SOURCE_TEXTURE_COMPILE_DRAIN remaining=%d"), Remaining);
        });
        TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
        FString Error;
        const bool Passed = Export(Out, Result, Error);
        Result->SetStringField(TEXT("status"), Passed ? TEXT("passed") : TEXT("failed"));
        Result->SetStringField(TEXT("error"), Error);
        Result->SetBoolField(TEXT("packages_saved"), false);
        FString Text;
        TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
        FJsonSerializer::Serialize(Result, Writer);
        const bool Saved = FFileHelper::SaveStringToFile(Text, *(Out / TEXT("result.json")),
            FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_NoReplaceExisting);
        UE_LOG(LogTemp, Display, TEXT("SOURCE_TEXTURE_EXPORT %s saved=%d %s"), Passed ? TEXT("PASSED") : TEXT("FAILED"), int(Saved), *Error);
    }
    virtual void ShutdownModule() override
    {
        FCoreDelegates::OnCommandletPostMain.Remove(DrainHandle);
    }
};

IMPLEMENT_MODULE(FSourceTextureExportModule, SourceTextureExport)
