// Copyright Epic Games, Inc. All Rights Reserved.
// Exact source bodies; see UESkyViewSetupSource.json.
namespace Falcor::CustomRenderPipline::SkyViewSetup::Compat
{
const float FAtmosphereSetup::CmToSkyUnit = 0.00001f;

const float FAtmosphereSetup::SkyUnitToCm = 1.0f / 0.00001f;

void FAtmosphereSetup::UpdateTransform(const FTransform& ComponentTransform, uint8 TranformMode)
{
	switch (ESkyAtmosphereTransformMode(TranformMode))
	{
	case ESkyAtmosphereTransformMode::PlanetTopAtAbsoluteWorldOrigin:
		PlanetCenterKm = FVector(0.0f, 0.0f, -BottomRadiusKm);
		break;
	case ESkyAtmosphereTransformMode::PlanetTopAtComponentTransform:
		PlanetCenterKm = FVector(0.0f, 0.0f, -BottomRadiusKm) + ComponentTransform.GetTranslation() * double(FAtmosphereSetup::CmToSkyUnit);
		break;
	case ESkyAtmosphereTransformMode::PlanetCenterAtComponentTransform:
		PlanetCenterKm = ComponentTransform.GetTranslation() * double(FAtmosphereSetup::CmToSkyUnit);
		break;
	default:
		check(false);
	}
}

void FAtmosphereSetup::ComputeViewData(
	const FVector& WorldCameraOrigin, const FVector& PreViewTranslation, const FVector3f& ViewForward, const FVector3f& ViewRight,
	FVector3f& SkyCameraTranslatedWorldOriginTranslatedWorld, FVector4f& SkyPlanetTranslatedWorldCenterAndViewHeight, FMatrix44f& SkyViewLutReferential) const
{
	// The constants below should match the one in SkyAtmosphereCommon.ush
	// Always force to be 5 meters above the ground/sea level (to always see the sky and not be under the virtual planet occluding ray tracing) and lower for small planet radius
	const float PlanetRadiusOffset = 0.005f;		

	const float Offset = PlanetRadiusOffset * SkyUnitToCm;
	const float BottomRadiusWorld = BottomRadiusKm * SkyUnitToCm;
	const FVector PlanetCenterWorld = PlanetCenterKm * SkyUnitToCm;
	const FVector PlanetCenterTranslatedWorld = PlanetCenterWorld + PreViewTranslation;
	const FVector WorldCameraOriginTranslatedWorld = WorldCameraOrigin + PreViewTranslation;
	const FVector PlanetCenterToCameraTranslatedWorld = WorldCameraOriginTranslatedWorld - PlanetCenterTranslatedWorld;
	const float DistanceToPlanetCenterTranslatedWorld = PlanetCenterToCameraTranslatedWorld.Size();

	// If the camera is below the planet surface, we snap it back onto the surface.
	// This is to make sure the sky is always visible even if the camera is inside the virtual planet.
	SkyCameraTranslatedWorldOriginTranslatedWorld = FVector3f(
						DistanceToPlanetCenterTranslatedWorld < (BottomRadiusWorld + Offset) ?
						PlanetCenterTranslatedWorld + (BottomRadiusWorld + Offset) * (PlanetCenterToCameraTranslatedWorld / DistanceToPlanetCenterTranslatedWorld) :
						WorldCameraOriginTranslatedWorld);
	SkyPlanetTranslatedWorldCenterAndViewHeight = FVector4f((FVector3f)PlanetCenterTranslatedWorld, ((FVector)SkyCameraTranslatedWorldOriginTranslatedWorld - PlanetCenterTranslatedWorld).Size());

	// Now compute the referential for the SkyView LUT
	FVector PlanetCenterToWorldCameraPos = ((FVector)SkyCameraTranslatedWorldOriginTranslatedWorld - PlanetCenterTranslatedWorld) * CmToSkyUnit;
	FVector3f Up = (FVector3f)PlanetCenterToWorldCameraPos;
	Up.Normalize();
	FVector3f Forward = ViewForward;		// This can make texel visible when the camera is rotating. Use constant world direction instead?
	//FVector3f	Left = normalize(cross(Forward, Up)); 
	FVector3f	Left;
	Left = FVector3f::CrossProduct(Forward, Up);
	Left.Normalize();
	const float DotMainDir = FMath::Abs(FVector3f::DotProduct(Up, Forward));
	if (DotMainDir > 0.999f)
	{
		// When it becomes hard to generate a referential, generate it procedurally.
		// [ Duff et al. 2017, "Building an Orthonormal Basis, Revisited" ]
		const float Sign = Up.Z >= 0.0f ? 1.0f : -1.0f;
		const float a = -1.0f / (Sign + Up.Z);
		const float b = Up.X * Up.Y * a;
		Forward = FVector3f( 1 + Sign * a * FMath::Pow(Up.X, 2.0f), Sign * b, -Sign * Up.X );
		Left = FVector3f(b,  Sign + a * FMath::Pow(Up.Y, 2.0f), -Up.Y );

		SkyViewLutReferential.SetColumn(0, Forward);
		SkyViewLutReferential.SetColumn(1, Left);
		SkyViewLutReferential.SetColumn(2, Up);
		SkyViewLutReferential = SkyViewLutReferential.GetTransposed();
	}
	else
	{
		// This is better as it should be more stable with respect to camera forward.
		Forward = FVector3f::CrossProduct(Up, Left);
		Forward.Normalize();
		SkyViewLutReferential.SetColumn(0, Forward);
		SkyViewLutReferential.SetColumn(1, Left);
		SkyViewLutReferential.SetColumn(2, Up);
		SkyViewLutReferential = SkyViewLutReferential.GetTransposed();
	}
}
}
