// Copyright Epic Games, Inc. All Rights Reserved.
// Exact source excerpts; see UESkyLightSource.json and UESkyLightSourceNotice.txt.
// Source evidence only; runtime integration is not established.

	void ModifyShaderCompilerInput(FShaderCompilerInput& Input) const final
	{
		checkf(IsValidD3DShaderFormat(Input.ShaderFormat), TEXT("Unknown D3D shader format %s"), *Input.ShaderFormat.ToString());
		const ED3DShaderModel ShaderModel = DetermineShaderModel(Input);

		// Our compilers only support HLSL
		Input.Environment.SetDefine(TEXT("COMPILER_HLSL"), true);

		// Assume min. spec HW supports with DX12/SM5
		Input.Environment.SetDefine(TEXT("PLATFORM_SUPPORTS_ROV"), true);

		const bool bSM6Features = RequiresSM6Features(Input);
		const bool bDXC         = DoesShaderModelRequireDXC(ShaderModel);

		// Compiler specific defines
		Input.Environment.SetDefine(TEXT("COMPILER_FXC"), !bDXC);
		Input.Environment.SetDefine(TEXT("COMPILER_DXC"),  bDXC);

		// Do we need SM6.0+ features enabled? This is intentionally disconnected from the ED3DShaderModel to allow SM6.0 to be used without new language features.
		Input.Environment.SetDefine(TEXT("PLATFORM_SUPPORTS_CONSTANTBUFFER_OBJECT"), bSM6Features);
		Input.Environment.SetDefine(TEXT("PLATFORM_SUPPORTS_SM6_0_WAVE_OPERATIONS"), bSM6Features);
		Input.Environment.SetDefine(TEXT("PLATFORM_SUPPORTS_DIAGNOSTIC_BUFFER"),     bSM6Features);

		const bool bSM6Profile = ShaderModel >= ED3DShaderModel::SM6_6;
		const bool bSM5Profile = Input.ShaderFormat == NAME_PCD3D_SM5;

		// "profiles" are almost analogous to ERHIFeatureLevel but RT shaders are forcing themselves to SM6
		Input.Environment.SetDefine(TEXT("SM6_PROFILE"), bSM6Profile);
		Input.Environment.SetDefine(TEXT("SM5_PROFILE"), bSM5Profile);
		Input.Environment.SetDefine(TEXT("ES3_1_PROFILE"), (Input.ShaderFormat == NAME_PCD3D_ES3_1));

		if (!bSM6Profile && !bSM5Profile)
		{
			Input.Environment.SetDefine(TEXT("COMPILER_SUPPORTS_ATTRIBUTES"), true);
			Input.Environment.SetDefine(TEXT("PLATFORM_PREFER_SRGB_BRANCH"), true);
		}

		// Add SM6.6+ specific defines. None of these are intended to be enabled in lower SM's
		if (ShaderModel >= ED3DShaderModel::SM6_6)
		{
			Input.Environment.SetDefine(TEXT("PLATFORM_SUPPORTS_REAL_TYPES"),         Input.Environment.CompilerFlags.Contains(CFLAG_AllowRealTypes));
			Input.Environment.SetDefine(TEXT("PLATFORM_SUPPORTS_INLINE_RAY_TRACING"), Input.Environment.CompilerFlags.Contains(CFLAG_InlineRayTracing));

			Input.Environment.SetDefine(TEXT("PLATFORM_SUPPORTS_STATIC_SAMPLERS"),  true);
			Input.Environment.SetDefine(TEXT("PLATFORM_SUPPORTS_CALLABLE_SHADERS"), true);
			Input.Environment.SetDefine(TEXT("COMPILER_SUPPORTS_NOINLINE"),         true);
		}

		// Add defines for our specific shader model (5.0, 6.0, 6.6)
		switch (ShaderModel)
		{
		case ED3DShaderModel::SM5_0:
			AddShaderTargetDefines(Input, 5, 0);
			break;
		case ED3DShaderModel::SM6_0:
			AddShaderTargetDefines(Input, 6, 0);
			break;
		case ED3DShaderModel::SM6_6:
			AddShaderTargetDefines(Input, 6, 6);
			break;
		case ED3DShaderModel::SM6_8:
			AddShaderTargetDefines(Input, 6, 8);
			break;
		}

		// For mobile emulation
		if (Input.Environment.FullPrecisionInPS || (Input.SharedEnvironment.IsValid() && Input.SharedEnvironment->FullPrecisionInPS))
		{
			Input.Environment.SetDefine(TEXT("FORCE_FLOATS"), (uint32)1);
		}
	}
