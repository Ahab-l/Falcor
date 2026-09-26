// Copyright Epic Games, Inc. All Rights Reserved.
// Exact source excerpts; see UESkyLightSource.json and UESkyLightSourceNotice.txt.
// Source evidence only; runtime integration is not established.

class FDownsampleCubeFaceCS : public FGlobalShader
{
	DECLARE_GLOBAL_SHADER(FDownsampleCubeFaceCS);
	SHADER_USE_PARAMETER_STRUCT(FDownsampleCubeFaceCS, FGlobalShader);

	static const uint32 ThreadGroupSize = 8;

	using FPermutationDomain = TShaderPermutationDomain<>;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, MipIndex)
		SHADER_PARAMETER(uint32, NumMips)
		SHADER_PARAMETER(int32, CubeFace)
		SHADER_PARAMETER(int32, FaceThreadGroupSize)
		SHADER_PARAMETER(FIntPoint, ValidDispatchCoord)
		SHADER_PARAMETER_RDG_TEXTURE_SRV(TextureCube, SourceCubemapTexture)
		SHADER_PARAMETER_SAMPLER(SamplerState, SourceCubemapSampler)
		SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D, OutTextureMipColor)
	END_SHADER_PARAMETER_STRUCT()

public:
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters) { return !IsMobilePlatform(Parameters.Platform); }
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
	{
		FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
		OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
		OutEnvironment.SetDefine(TEXT("USE_COMPUTE"), 1);
	}
};
IMPLEMENT_GLOBAL_SHADER(FDownsampleCubeFaceCS, "/Engine/Private/ReflectionEnvironmentShaders.usf", "DownsampleCS", SF_Compute);


class FConvolveSpecularFaceCS : public FGlobalShader
{
	DECLARE_GLOBAL_SHADER(FConvolveSpecularFaceCS);
	SHADER_USE_PARAMETER_STRUCT(FConvolveSpecularFaceCS, FGlobalShader);

	static const uint32 ThreadGroupSize = 8;

	using FPermutationDomain = TShaderPermutationDomain<>;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, MipIndex)
		SHADER_PARAMETER(uint32, NumMips)
		SHADER_PARAMETER(int32, CubeFaceOffset)
		SHADER_PARAMETER(int32, CubeFace)
		SHADER_PARAMETER(int32, FaceThreadGroupSize)
		SHADER_PARAMETER(FIntPoint, ValidDispatchCoord)
		SHADER_PARAMETER_RDG_TEXTURE_SRV(TextureCube, SourceCubemapTexture)
		SHADER_PARAMETER_SAMPLER(SamplerState, SourceCubemapSampler)
		SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D, OutTextureMipColor)
	END_SHADER_PARAMETER_STRUCT()

public:
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters) { return GetMaxSupportedFeatureLevel(Parameters.Platform) >= ERHIFeatureLevel::ES3_1; }
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
	{
		FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
		OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
		OutEnvironment.SetDefine(TEXT("USE_COMPUTE"), 1);
	}
};
IMPLEMENT_GLOBAL_SHADER(FConvolveSpecularFaceCS, "/Engine/Private/ReflectionEnvironmentShaders.usf", "FilterCS", SF_Compute);


class FComputeSkyEnvMapDiffuseIrradianceCS : public FGlobalShader
{
	DECLARE_GLOBAL_SHADER(FComputeSkyEnvMapDiffuseIrradianceCS);
	SHADER_USE_PARAMETER_STRUCT(FComputeSkyEnvMapDiffuseIrradianceCS, FGlobalShader);

	// 8*8=64 threads in a group.
	// Each thread uses 4*7*RGB sh float => 84 bytes shared group memory. 
	// 64 * 84 = 5376 bytes which fits dx11 16KB shared memory limitation. 6144 with vector alignement in shared memory and it still fits
	// Low occupancy on a single CU.
	static const uint32 ThreadGroupSizeX = 8;
	static const uint32 ThreadGroupSizeY = 8;

	using FPermutationDomain = TShaderPermutationDomain<>;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_RDG_TEXTURE_SRV(TextureCube, SourceCubemapTexture)
		SHADER_PARAMETER_SAMPLER(SamplerState, SourceCubemapSampler)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer, OutIrradianceEnvMapSH)
		SHADER_PARAMETER(float, UniformSampleSolidAngle)
		SHADER_PARAMETER(uint32, MipIndex)
	END_SHADER_PARAMETER_STRUCT()

public:
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters) { return GetMaxSupportedFeatureLevel(Parameters.Platform) >= ERHIFeatureLevel::ES3_1; }
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
	{
		FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
		OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE_X"), ThreadGroupSizeX);
		OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE_Y"), ThreadGroupSizeY);
		OutEnvironment.SetDefine(TEXT("SHADER_DIFFUSE_TO_SH"), 1);
	}
};
IMPLEMENT_GLOBAL_SHADER(FComputeSkyEnvMapDiffuseIrradianceCS, "/Engine/Private/ReflectionEnvironmentShaders.usf", "ComputeSkyEnvMapDiffuseIrradianceCS", SF_Compute);

	auto RenderCubeFaces_GenCubeMips = [&](uint32 CubeMipStart, uint32 CubeMipEnd, TRefCountPtr<IPooledRenderTarget>& SkyRenderTarget)
	{
		// on mobile platforms use the pixel shader implementation as compute shaders might not be optimal
		const bool bIsMobilePlatform = IsMobilePlatform(MainView.GetShaderPlatform());
		if (bIsMobilePlatform)
		{
			FRDGTextureRef SkyCubeTexture = GraphBuilder.RegisterExternalTexture(SkyRenderTarget, TEXT("SkyRenderTarget"));
			CreateCubeMips(GraphBuilder, GetGlobalShaderMap(FeatureLevel), SkyCubeTexture);
		}
		else
		{
			check(CubeMipStart > 0);	// Never write to mip0 as it has just been redered into

			FRDGTextureRef SkyCubeTexture = GraphBuilder.RegisterExternalTexture(SkyRenderTarget, TEXT("SkyRenderTarget"));

			FDownsampleCubeFaceCS::FPermutationDomain PermutationVector;
			TShaderMapRef<FDownsampleCubeFaceCS> ComputeShader(GetGlobalShaderMap(FeatureLevel), PermutationVector);

			for (uint32 MipIndex = CubeMipStart; MipIndex <= CubeMipEnd; MipIndex++)
			{
				const uint32 MipResolution = 1 << (CubeMipCount - MipIndex - 1);
				FRDGTextureSRVRef SkyCubeTextureSRV = GraphBuilder.CreateSRV(FRDGTextureSRVDesc::CreateForMipLevel(SkyCubeTexture, MipIndex - 1)); // slice/face selection is useless so remove from CreateForMipLevel

				FDownsampleCubeFaceCS::FParameters* PassParameters = GraphBuilder.AllocParameters<FDownsampleCubeFaceCS::FParameters>();
				PassParameters->MipIndex = MipIndex;
				PassParameters->NumMips = CubeMipCount;
				PassParameters->CubeFace = 0; // unused
				PassParameters->ValidDispatchCoord = FIntPoint(MipResolution, MipResolution);
				PassParameters->SourceCubemapSampler = TStaticSamplerState<SF_Point>::GetRHI();

				PassParameters->SourceCubemapTexture = SkyCubeTextureSRV;
				FRDGTextureUAVDesc OutTextureMipColorDesc(SkyCubeTexture, MipIndex);
				OutTextureMipColorDesc.DimensionOverride = ETextureDimension::Texture2DArray;
				PassParameters->OutTextureMipColor = GraphBuilder.CreateUAV(OutTextureMipColorDesc);

				FIntVector NumGroups = FIntVector::DivideAndRoundUp(FIntVector(MipResolution, MipResolution, 1), FIntVector(FDownsampleCubeFaceCS::ThreadGroupSize, FDownsampleCubeFaceCS::ThreadGroupSize, 1));

				// The groupd size per face with padding
				PassParameters->FaceThreadGroupSize = NumGroups.X * FDownsampleCubeFaceCS::ThreadGroupSize;

				// We are going to dispatch once for all faces 
				NumGroups.X *= 6;

				// Dispatch with GenerateMips: reading from a slice through SRV and writing into lower mip through UAV.
				ClearUnusedGraphResources(ComputeShader, PassParameters);
				GraphBuilder.AddPass(
					Forward<FRDGEventName>(RDG_EVENT_NAME("MipGen")),
					PassParameters,
					ERDGPassFlags::Compute,
				[PassParameters, ComputeShader, NumGroups](FRDGAsyncTask, FRHICommandList& RHICmdList)
				{
					FComputeShaderUtils::Dispatch(RHICmdList, ComputeShader, *PassParameters, NumGroups);
				});
			}
		}
		
	};

	auto RenderCubeFaces_SpecularConvolution = [&](uint32 CubeMipStart, uint32 CubeMipEnd, uint32 FaceStart, uint32 FaceCount, TRefCountPtr<IPooledRenderTarget>& DstRenderTarget, TRefCountPtr<IPooledRenderTarget>& SrcRenderTarget)
	{
		check((FaceStart + FaceCount) <= 6);
		FRDGTextureRef RDGSrcRenderTarget = GraphBuilder.RegisterExternalTexture(SrcRenderTarget);
		FRDGTextureRef RDGDstRenderTarget = GraphBuilder.RegisterExternalTexture(DstRenderTarget);

		// on mobile platforms use the pixel shader convolution as compute shaders might not be optimal
		const bool bIsMobilePlatform = IsMobilePlatform(MainView.GetShaderPlatform());
		if (bIsMobilePlatform)
		{
			ConvolveCubeMap(GraphBuilder, GetGlobalShaderMap(FeatureLevel), CubeMipStart, CubeMipEnd, FaceStart, FaceCount, RDGSrcRenderTarget, RDGDstRenderTarget);
		}
		else
		{
			FRDGTextureSRVRef RDGSrcRenderTargetSRV = GraphBuilder.CreateSRV(FRDGTextureSRVDesc::Create(RDGSrcRenderTarget));

			FDownsampleCubeFaceCS::FPermutationDomain PermutationVector;
			TShaderMapRef<FConvolveSpecularFaceCS> ComputeShader(GetGlobalShaderMap(FeatureLevel), PermutationVector);
			for (uint32 MipIndex = CubeMipStart; MipIndex <= CubeMipEnd; MipIndex++)
			{
				const uint32 MipResolution = 1 << (CubeMipCount - MipIndex - 1);
		
				FConvolveSpecularFaceCS::FParameters* PassParameters = GraphBuilder.AllocParameters<FConvolveSpecularFaceCS::FParameters>();
				PassParameters->MipIndex = MipIndex;
				PassParameters->NumMips = CubeMipCount;
				PassParameters->CubeFace = 0; // unused
				PassParameters->CubeFaceOffset = int(FaceStart);
				PassParameters->ValidDispatchCoord = FIntPoint(MipResolution, MipResolution);
				PassParameters->SourceCubemapSampler = TStaticSamplerState<SF_Point>::GetRHI();
		
				PassParameters->SourceCubemapTexture = RDGSrcRenderTargetSRV;
				FRDGTextureUAVDesc OutTextureMipColorDesc(RDGDstRenderTarget, MipIndex);
				OutTextureMipColorDesc.DimensionOverride = ETextureDimension::Texture2DArray;
				PassParameters->OutTextureMipColor = GraphBuilder.CreateUAV(OutTextureMipColorDesc);
		
				FIntVector NumGroups = FIntVector::DivideAndRoundUp(FIntVector(MipResolution, MipResolution, 1), FIntVector(FConvolveSpecularFaceCS::ThreadGroupSize, FConvolveSpecularFaceCS::ThreadGroupSize, 1));
		
				// The groupd size per face with padding
				PassParameters->FaceThreadGroupSize = NumGroups.X * FConvolveSpecularFaceCS::ThreadGroupSize;
		
				// We are going to dispatch once for all faces 
				NumGroups.X *= FaceCount;
		
				FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("Convolve"), ComputeShader, PassParameters, NumGroups);
			}
		}
	};

	auto RenderCubeFaces_DiffuseIrradiance = [&](TRefCountPtr<IPooledRenderTarget>& SourceCubemap)
	{
		FRDGTextureRef SourceCubemapTexture = GraphBuilder.RegisterExternalTexture(SourceCubemap);
		FRDGTextureSRVRef SourceCubemapTextureSRV = GraphBuilder.CreateSRV(FRDGTextureSRVDesc::Create(SourceCubemapTexture));
		
		// ForceImmediateFirstBarrier is required because the RHI resource is used as an SRV outside of RDG prior to this UAV pass. Without
		// the flag, RDG will split the transition to UAV to the start of the graph, which results in a validation error. With the flag, RDG
		// will transition to UAV at the start of the pass instead.
		FRDGBuffer* SkyIrradianceEnvironmentMapRDG = GraphBuilder.RegisterExternalBuffer(SkyIrradianceEnvironmentMap, ERDGBufferFlags::ForceImmediateFirstBarrier); // TODO SkyIrradianceEnvironmentMap is nullptr
		GraphBuilder.UseInternalAccessMode(SkyIrradianceEnvironmentMapRDG);

		TShaderMapRef<FComputeSkyEnvMapDiffuseIrradianceCS> ComputeShader(GetGlobalShaderMap(FeatureLevel));

		const float SampleCount = FComputeSkyEnvMapDiffuseIrradianceCS::ThreadGroupSizeX * FComputeSkyEnvMapDiffuseIrradianceCS::ThreadGroupSizeY;
		const float UniformSampleSolidAngle = 4.0f * PI / SampleCount; // uniform distribution

		FComputeSkyEnvMapDiffuseIrradianceCS::FParameters* PassParameters = GraphBuilder.AllocParameters<FComputeSkyEnvMapDiffuseIrradianceCS::FParameters>();
		PassParameters->SourceCubemapSampler = TStaticSamplerState<SF_Point>::GetRHI();
		PassParameters->SourceCubemapTexture = SourceCubemapTextureSRV;
		PassParameters->OutIrradianceEnvMapSH = GraphBuilder.CreateUAV(SkyIrradianceEnvironmentMapRDG);
		PassParameters->UniformSampleSolidAngle = UniformSampleSolidAngle;

		// For 64 uniform samples on the unit sphere, we roughly have 10 samples per face.
		// Considering mip generation and bilinear sampling, we can assume 10 samples is enough to integrate 10*4=40 texels.
		// With that, we target integration of 16*16 face.
		const uint32 Log2_16 = 4; // FMath::Log2(16.0f)
		PassParameters->MipIndex = uint32(FMath::Log2(float(CapturedSkyRenderTarget->GetDesc().GetSize().X))) - Log2_16;

		const FIntVector NumGroups = FIntVector(1, 1, 1);
		FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("ComputeSkyEnvMapDiffuseIrradianceCS"), ComputeShader, PassParameters, NumGroups);

		const bool bIsMobilePlatform = IsMobilePlatform(MainView.GetShaderPlatform());
		if (bIsMobilePlatform)
		{
			TSharedPtr<FRHIGPUBufferReadback> NewReadBack = MakeShared<FRHIGPUBufferReadback>(TEXT("MobileSkyLightRealTimeCaptureIrradianceReadBack"));
			AddEnqueueCopyPass(GraphBuilder, NewReadBack.Get(), SkyIrradianceEnvironmentMapRDG, SkyIrradianceEnvironmentMapRDG->GetSize());

			FScene* Scene = MainView.Family->Scene->GetRenderScene();
			Scene->MobileSkyLightRealTimeCaptureIrradianceReadBackQueries.Enqueue(NewReadBack);
		}

		ExternalAccessQueue.Add(SkyIrradianceEnvironmentMapRDG, ERHIAccess::SRVMask, ERHIPipeline::All);
	};

		RenderCubeFaces_SkyCloud(true, true, CapturedSkyRenderTarget, 0, CubeFace_MAX);

		// 0.05ms
		RenderCubeFaces_GenCubeMips(1, LastMipLevel, CapturedSkyRenderTarget);

		// 0.80ms total (0.30ms for mip0, 0.20ms for mip1+2, 0.30ms for remaining mips)
		RenderCubeFaces_SpecularConvolution(0, LastMipLevel, 0, 6, ConvolvedSkyRenderTarget[ConvolvedSkyRenderTargetReadyIndex], CapturedSkyRenderTarget);

		// 0.015ms
		RenderCubeFaces_DiffuseIrradiance(ConvolvedSkyRenderTarget[ConvolvedSkyRenderTargetReadyIndex]);
