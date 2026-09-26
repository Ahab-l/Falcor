// Copyright Epic Games, Inc. All Rights Reserved.
// Unchanged original CPU source evidence; not compiled as shader code.

	// The PreintegratedGF maybe used on forward shading including mobile platform, initialize it anyway.
	{
		// for testing, with 128x128 R8G8 we are very close to the reference (if lower res is needed we might have to add an offset to counter the 0.5f texel shift)
		const bool bReference = false;

		EPixelFormat Format = PF_R8G8;
		// for low roughness we would get banding with PF_R8G8 but for low spec it could be used, for now we don't do this optimization
		if (GPixelFormats[PF_G16R16].Supported && UE::PixelFormat::HasCapabilities(PF_G16R16, EPixelFormatCapabilities::TextureFilterable))
		{
			Format = PF_G16R16;
		}

		FIntPoint Extent(128, 32);

		if (bReference)
		{
			Extent.X = 128;
			Extent.Y = 128;
		}

		const FRHITextureCreateDesc Desc =
			FRHITextureCreateDesc::Create2D(TEXT("PreintegratedGF"), Extent, Format)
			.SetFlags(ETextureCreateFlags::ShaderResource)
			.SetClassName(SystemTexturesName)
			.SetInitActionInitializer();

		FRHITextureInitializer Initializer = RHICmdList.CreateTextureInitializer(Desc);

		// Write the contents of the texture.
		FRHITextureSubresourceInitializer Subresource = Initializer.GetTexture2DSubresource(0);

		uint8* DestBuffer = reinterpret_cast<uint8*>(Subresource.Data);

		// x is NoV, y is roughness
		for (int32 y = 0; y < Extent.Y; y++)
		{
			float Roughness = (float)(y + 0.5f) / Extent.Y;
			float m = Roughness * Roughness;
			float m2 = m * m;

			for (int32 x = 0; x < Extent.X; x++)
			{
				float NoV = (float)(x + 0.5f) / Extent.X;

				FVector3f V;
				V.X = FMath::Sqrt(1.0f - NoV * NoV);	// sin
				V.Y = 0.0f;
				V.Z = NoV;								// cos

				float A = 0.0f;
				float B = 0.0f;
				float C = 0.0f;

				const uint32 NumSamples = 128;
				for (uint32 i = 0; i < NumSamples; i++)
				{
					float E1 = (float)i / NumSamples;
					float E2 = (double)ReverseBits(i) / (double)0x100000000LL;

					{
						float Phi = 2.0f * PI * E1;
						float CosPhi = FMath::Cos(Phi);
						float SinPhi = FMath::Sin(Phi);
						float CosTheta = FMath::Sqrt((1.0f - E2) / (1.0f + (m2 - 1.0f) * E2));
						float SinTheta = FMath::Sqrt(1.0f - CosTheta * CosTheta);

						FVector3f H(SinTheta * FMath::Cos(Phi), SinTheta * FMath::Sin(Phi), CosTheta);
						FVector3f L = 2.0f * (V | H) * H - V;

						float NoL = FMath::Max(L.Z, 0.0f);
						float NoH = FMath::Max(H.Z, 0.0f);
						float VoH = FMath::Max(V | H, 0.0f);

						if (NoL > 0.0f)
						{
							float Vis_SmithV = NoL * (NoV * (1 - m) + m);
							float Vis_SmithL = NoV * (NoL * (1 - m) + m);
							float Vis = 0.5f / (Vis_SmithV + Vis_SmithL);

							float NoL_Vis_PDF = NoL * Vis * (4.0f * VoH / NoH);
							float Fc = 1.0f - VoH;
							Fc *= FMath::Square(Fc*Fc);
							A += NoL_Vis_PDF * (1.0f - Fc);
							B += NoL_Vis_PDF * Fc;
						}
					}

					{
						float Phi = 2.0f * PI * E1;
						float CosPhi = FMath::Cos(Phi);
						float SinPhi = FMath::Sin(Phi);
						float CosTheta = FMath::Sqrt(E2);
						float SinTheta = FMath::Sqrt(1.0f - CosTheta * CosTheta);

						FVector3f L(SinTheta * FMath::Cos(Phi), SinTheta * FMath::Sin(Phi), CosTheta);
						FVector3f H = (V + L).GetUnsafeNormal();

						float NoL = FMath::Max(L.Z, 0.0f);
						float NoH = FMath::Max(H.Z, 0.0f);
						float VoH = FMath::Max(V | H, 0.0f);

						float FD90 = 0.5f + 2.0f * VoH * VoH * Roughness;
						float FdV = 1.0f + (FD90 - 1.0f) * pow(1.0f - NoV, 5);
						float FdL = 1.0f + (FD90 - 1.0f) * pow(1.0f - NoL, 5);
						C += FdV * FdL;// * ( 1.0f - 0.3333f * Roughness );
					}
				}
				A /= NumSamples;
				B /= NumSamples;
				C /= NumSamples;

				if (Format == PF_A16B16G16R16)
				{
					uint16* Dest = (uint16*)(DestBuffer + x * 8 + y * Subresource.Stride);
					Dest[0] = (int32)(FMath::Clamp(A, 0.0f, 1.0f) * 65535.0f + 0.5f);
					Dest[1] = (int32)(FMath::Clamp(B, 0.0f, 1.0f) * 65535.0f + 0.5f);
					Dest[2] = (int32)(FMath::Clamp(C, 0.0f, 1.0f) * 65535.0f + 0.5f);
				}
				else if (Format == PF_G16R16)
				{
					uint16* Dest = (uint16*)(DestBuffer + x * 4 + y * Subresource.Stride);
					Dest[0] = (int32)(FMath::Clamp(A, 0.0f, 1.0f) * 65535.0f + 0.5f);
					Dest[1] = (int32)(FMath::Clamp(B, 0.0f, 1.0f) * 65535.0f + 0.5f);
				}
				else
				{
					check(Format == PF_R8G8);

					uint8* Dest = (uint8*)(DestBuffer + x * 2 + y * Subresource.Stride);
					Dest[0] = (int32)(FMath::Clamp(A, 0.0f, 1.0f) * 255.f + 0.5f);
					Dest[1] = (int32)(FMath::Clamp(B, 0.0f, 1.0f) * 255.f + 0.5f);
				}
			}
		}

		FTextureRHIRef Texture = Initializer.Finalize();
		PreintegratedGF = CreateRenderTarget(Texture, Desc.DebugName);
	}

	OutParameters.PreIntegratedGF = GSystemTextures.PreintegratedGF->GetRHI();
	OutParameters.PreIntegratedGFSampler = TStaticSamplerState<SF_Bilinear, AM_Clamp, AM_Clamp, AM_Clamp>::GetRHI();
