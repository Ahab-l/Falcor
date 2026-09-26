"""Independent NumPy/GPU acceptance for UE ordinary capsule/area DefaultLit.

Normal Python: --oracle-only (default), no falcor import, device, or output files.
Mogwai embedded: run a separate D3D12 Device probe and save raw/source evidence.
Outputs include area geometry, SphereMaxNoH with and without Newton, energy,
DefaultLit lobes, and an independently supplied sqrtFast bit-pattern probe.

This is a bounded float32-versus-float64 test, not a bitwise BRDF claim. Geometric
outputs use rtol=3e-5/atol=2e-6; nonlinear context uses 2e-5 absolute; energy uses
1e-4 relative/2e-7 absolute; lobes use 1e-3 relative/2e-6 absolute. These are
predeclared engineering budgets for float32 dot/rsqrt/FMA/pow chains compared
with double precision, not tolerances fitted to a GPU run. 256 float operations
alone have gamma_n about 1.53e-5; Newton and the GGX denominator amplify error.
To bound that amplification, non-saturated NoH cases with GGX d<0.01 are excluded
and recorded. NoH=1 highlight cases use binary-exact roughness >=1/8. Near-singular
line/Newton inputs are excluded by fixture validation, never repaired with an
epsilon. sqrtFast of the uploaded probe is required to match uint32 bits exactly.
Failures must be investigated per stage rather than loosening these budgets.

Scope excludes rect/anisotropy, optional energy LUTs/rough diffuse, light masks,
shadows, exposure, GBuffer quantization, and LightingPass/capture equivalence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

EMBEDDED = "m" in globals()
ROOT = Path.cwd().resolve() if EMBEDDED else Path(__file__).resolve().parents[2]
BIN = ROOT / "build/windows-vs2022/bin/Release"
if EMBEDDED:
    sys.path.insert(0, str(BIN / "python"))
    sys.path.insert(0, str(ROOT / "build/m0-evidence/python"))
import numpy as np

SEED = 26550063
INPUT_ROWS, OUTPUT_ROWS = 6, 10
TOLERANCES = {"area": (3e-5, 2e-6), "context": (0.0, 2e-5),
              "energy": (1e-4, 2e-7), "lobes": (1e-3, 2e-6)}
MIN_CONDITIONED_D = 0.01

KERNEL = r"""
StructuredBuffer<float4> gInput;
RWStructuredBuffer<float4> gResult;
[numthreads(1,1,1)] void main(uint3 tid : SV_DispatchThreadID)
{
    const uint i = tid.x;
    const float4 nr = gInput[i * 6];
    const float4 vm = gInput[i * 6 + 1];
    const float4 lr = gInput[i * 6 + 2];
    const float4 tl = gInput[i * 6 + 3];
    const float4 cs = gInput[i * 6 + 4];
    const float4 extra = gInput[i * 6 + 5];
    const UEAreaLight area = ueMakeCapsuleAreaLight(nr.w, nr.xyz, vm.xyz,
        lr.xyz, tl.xyz, tl.w, lr.w, extra.x, extra.y != 0.0);
    const UEBxDFContext initial = ueInitBxDF(nr.xyz, vm.xyz, area.specularL);
    UEBxDFContext withNewton = initial;
    UEBxDFContext withoutNewton = initial;
    ueSphereMaxNoH(withNewton, area.sphereSinAlpha, true);
    ueSphereMaxNoH(withoutNewton, area.sphereSinAlpha, false);
    float a2 = uePow4(nr.w);
    const float energy = ueEnergyNormalization(a2, withNewton.VoH, area);
    UESurface surface = (UESurface)0;
    surface.normalUE = nr.xyz;
    surface.roughness = nr.w;
    surface.metallic = vm.w;
    surface.baseColor = cs.xyz;
    surface.specular = cs.w;
    surface.modelID = 1u;
    UEDirectLightingContext context = (UEDirectLightingContext)0;
    context.N = nr.xyz;
    context.V = vm.xyz;
    context.area = area;
    const UEModelLighting lighting = ueShadeDefaultLit(surface, context);
    gResult[i * 10] = float4(area.sphereSinAlpha, area.sphereSinAlphaSoft, area.lineCosSubtended, area.NoL);
    gResult[i * 10 + 1] = float4(area.diffuseL, area.falloff);
    gResult[i * 10 + 2] = float4(area.specularL, 0.0);
    gResult[i * 10 + 3] = float4(withNewton.NoL, withNewton.NoV, withNewton.VoL, withNewton.NoH);
    gResult[i * 10 + 4] = float4(withNewton.VoH, withoutNewton.NoH, withoutNewton.VoH, ueSqrtFast(extra.z));
    gResult[i * 10 + 5] = float4(a2, energy, initial.NoH, initial.VoH);
    gResult[i * 10 + 6] = float4(lighting.diffuse, 0.0);
    gResult[i * 10 + 7] = float4(lighting.specular, 0.0);
    gResult[i * 10 + 8] = float4(lighting.transmission, 0.0);
    gResult[i * 10 + 9] = float4(area.falloffColor, 0.0);
}
"""


def positive(value, label):
    if not np.isfinite(value) or value <= 0:
        raise ValueError(label + " must be positive; degenerate input is not repaired")
    return value


def unit(vector):
    v = np.asarray(vector, dtype=np.float64)
    return v / np.sqrt(positive(np.dot(v, v), "vector length squared"))


def sat(value):
    return np.clip(value, 0.0, 1.0)


def sqrt_fast(value):
    """UE FastMathThirdParty.ush:52, exact positive-float bit transform."""
    x = np.asarray(value, dtype=np.float32)
    if not np.isfinite(x).all() or (x < 0).any():
        raise ValueError("sqrtFast probe requires finite nonnegative float32")
    bits = x.view(np.int32).astype(np.int64)
    return np.asarray(0x1FBD1DF5 + (bits >> 1), dtype=np.int32).view(np.float32)


def case(name, **overrides):
    c = dict(name=name, N=[0, 0, 1], V=[0, 0, 1], to_light=[0, 0, 8], tangent=[1, 0, 0],
             roughness=0.5, metallic=0.5, base_color=[0.125, 0.5, 0.75], specular=0.5,
             radius=0.0, soft_radius=0.0, length=0.0, inverse_squared=False, sqrt_probe=0.0625)
    c.update(overrides)
    return c


def pack(c):
    return np.asarray([list(c["N"]) + [c["roughness"]], list(c["V"]) + [c["metallic"]],
                       list(c["to_light"]) + [c["radius"]], list(c["tangent"]) + [c["length"]],
                       list(c["base_color"]) + [c["specular"]],
                       [c["soft_radius"], c["inverse_squared"], c["sqrt_probe"], 0]], dtype=np.float32)


def validate_input(p):
    if p.shape != (INPUT_ROWS, 4) or not np.isfinite(p).all():
        raise ValueError("nonfinite or malformed capsule input")
    for row, name in ((0, "N"), (1, "V"), (3, "tangent")):
        norm = np.linalg.norm(p[row, :3].astype(np.float64))
        if abs(norm - 1) > 2e-6:
            raise ValueError(name + " must already be a unit vector")
    if not float(np.float32(0.02)) <= p[0, 3] <= 1:
        raise ValueError("roughness must already have the View floor and lie in [0.02,1]")
    if min(p[2, 3], p[3, 3], p[5, 0], p[5, 2]) < 0:
        raise ValueError("radius, length, soft radius and sqrt probe must be nonnegative")
    if not (0 <= p[1, 3] <= 1 and (p[4] >= 0).all() and (p[4] <= 1).all()):
        raise ValueError("material fixture values must lie in [0,1]")


def area_oracle(p):
    N, V, to_light, tangent = p[0, :3], p[1, :3], p[2, :3], p[3, :3]
    roughness, radius, length, soft = p[0, 3], p[2, 3], p[3, 3], p[5, 0]
    P0, P1 = to_light - 0.5 * length * tangent, to_light + 0.5 * length * tangent
    d0 = positive(np.dot(P0, P0), "capsule endpoint P0 distance squared")
    line_cos = 1.0
    if length > 0:
        d1 = positive(np.dot(P1, P1), "capsule endpoint P1 distance squared")
        q0, q1 = 1 / np.sqrt(d0), 1 / np.sqrt(d1)
        line_cos = np.dot(P0, P1) * q0 * q1
        falloff = q0 * q1 / positive(0.5 * line_cos + 0.5 + q0 * q1, "line irradiance denominator")
        vector_irradiance = 0.5 * (P0 * q0 + P1 * q1)
        NoL = np.dot(N, vector_irradiance)
        diffuseL = unit(vector_irradiance)
    else:
        falloff = 1 / (d0 + 1)
        diffuseL = P0 / np.sqrt(d0)
        NoL = np.dot(N, diffuseL)
    wrapped = False
    if radius > 0:
        sin_alpha = np.sqrt(sat(radius * radius * falloff))
        if NoL < sin_alpha:
            positive(sin_alpha, "horizon-wrap denominator")
            NoL = (sin_alpha + max(NoL, -sin_alpha)) ** 2 / (4 * sin_alpha)
            wrapped = True
    NoL = sat(NoL)
    if p[5, 1] == 0:
        falloff = 1.0
    to_specular = P0
    line_denominator_ratio = 1.0
    if length > 0:
        reflection = -V + 2 * np.dot(V, N) * N
        segment = P1 - P0
        B = np.dot(reflection, segment)
        denominator = positive(length * length - B * B, "line/reflection parallel denominator")
        line_denominator_ratio = denominator / (length * length)
        t = sat(np.dot(P0, B * reflection - segment) / denominator)
        to_specular = P0 + t * segment
    inverse_distance = 1 / np.sqrt(positive(np.dot(to_specular, to_specular), "specular direction distance squared"))
    return dict(sphere=float(sat(radius * inverse_distance * (1 - roughness * roughness))),
                soft=float(sat(soft * inverse_distance)), line=float(line_cos),
                diffuseL=diffuseL, specularL=to_specular * inverse_distance, NoL=float(NoL),
                falloff=float(falloff), wrapped=wrapped, line_denominator_ratio=float(line_denominator_ratio))


def initial_context(N, V, L):
    NoL, NoV, VoL = np.dot(N, L), np.dot(N, V), np.dot(V, L)
    inv_half = 1 / np.sqrt(positive(2 + 2 * VoL, "antiparallel half-vector denominator"))
    return dict(NoL=NoL, NoV=NoV, VoL=VoL,
                NoH=float(sat((NoL + NoV) * inv_half)), VoH=float(sat(inv_half + inv_half * VoL)))


def sphere_context(original, sin_alpha, newton):
    c = dict(original)
    branch = "inactive"
    if sin_alpha > 0:
        cos_alpha = np.sqrt(1 - sin_alpha * sin_alpha)
        RoL = 2 * c["NoL"] * c["NoV"] - c["VoL"]
        if RoL >= cos_alpha:
            c["NoH"], c["VoH"] = 1.0, abs(c["NoV"])
            branch = "reflection_inside"
        else:
            branch = "newton" if newton else "without_newton"
            r_inverse_T = sin_alpha / np.sqrt(positive(1 - RoL * RoL, "sphere tangent denominator"))
            NoTr = r_inverse_T * (c["NoV"] - RoL * c["NoL"])
            VoTr = r_inverse_T * (2 * c["NoV"] * c["NoV"] - 1 - RoL * c["VoL"])
            if newton:
                NxLoV = np.sqrt(sat(1 - c["NoL"] ** 2 - c["NoV"] ** 2 - c["VoL"] ** 2
                                      + 2 * c["NoL"] * c["NoV"] * c["VoL"]))
                NoBr, VoBr = r_inverse_T * NxLoV, r_inverse_T * NxLoV * 2 * c["NoV"]
                NoLVTr = c["NoL"] * cos_alpha + c["NoV"] + NoTr
                VoLVTr = c["VoL"] * cos_alpha + 1 + VoTr
                P, Q, S = NoBr * VoLVTr, NoLVTr * VoLVTr, VoBr * NoLVTr
                x_num = Q * (-0.5 * P + 0.25 * VoBr * NoLVTr)
                x_den = P * P + S * (S - 2 * P) + NoLVTr * (
                    (c["NoL"] * cos_alpha + c["NoV"]) * VoLVTr ** 2
                    + Q * (-0.5 * (VoLVTr + c["VoL"] * cos_alpha) - 0.5))
                two_x = 2 * x_num / positive(x_den * x_den + x_num * x_num, "Newton denominator")
                sin_theta, cos_theta = two_x * x_den, 1 - two_x * x_num
                NoTr, VoTr = cos_theta * NoTr + sin_theta * NoBr, cos_theta * VoTr + sin_theta * VoBr
            c["NoL"] = c["NoL"] * cos_alpha + NoTr
            c["VoL"] = c["VoL"] * cos_alpha + VoTr
            inv_half = 1 / np.sqrt(positive(2 + 2 * c["VoL"], "morphed half-vector denominator"))
            c["NoH"] = float(sat((c["NoL"] + c["NoV"]) * inv_half))
            c["VoH"] = float(sat(inv_half + inv_half * c["VoL"]))
    return c, branch


def energy_oracle(roughness, VoH, area, exact_sqrt=False):
    a2 = roughness ** 4
    if area["soft"] > 0:
        a2 = float(sat(a2 + area["soft"] ** 2 / (VoH * 3.6 + 0.4)))

    def new_a2(value, angle):
        root = np.sqrt(value) if exact_sqrt else float(sqrt_fast(value))
        return value + 0.25 * angle * (3 * root + angle) / (VoH + 0.001)

    sphere_a2, energy = a2, 1.0
    if area["sphere"] > 0:
        sphere_a2 = new_a2(a2, area["sphere"])
        energy = a2 / positive(sphere_a2, "sphere energy denominator")
    if area["line"] < 1:
        line_tan = np.sqrt((1.0001 - area["line"]) / positive(1 + area["line"], "line angle denominator"))
        line_a2 = new_a2(sphere_a2, line_tan)
        # 1e-5 is the actual UE source term, not a new fixture epsilon.
        energy *= np.sqrt(sphere_a2 / max(line_a2, 1e-5))
    return a2, energy


def oracle(packed):
    validate_input(packed)
    p = packed.astype(np.float64)
    a = area_oracle(p)
    initial = initial_context(p[0, :3], p[1, :3], a["specularL"])
    c, branch = sphere_context(initial, a["sphere"], True)
    no_newton, _ = sphere_context(initial, a["sphere"], False)
    a2, energy = energy_oracle(p[0, 3], c["VoH"], a)
    d = (c["NoH"] * a2 - c["NoH"]) * c["NoH"] + 1
    diffuse, specular = np.zeros(3), np.zeros(3)
    if a["NoL"] > 0:
        dielectric = 0.08 * p[4, 3]
        F0 = dielectric + p[1, 3] * (p[4, :3] - dielectric)
        NoV = float(sat(abs(c["NoV"]) + 1e-5))
        alpha = np.sqrt(a2)
        visibility = 0.5 / positive(a["NoL"] * (NoV * (1 - alpha) + alpha)
                                   + NoV * (a["NoL"] * (1 - alpha) + alpha), "Smith visibility denominator")
        D = a2 / (np.pi * positive(d, "GGX denominator") ** 2) * energy
        Fc = (1 - c["VoH"]) ** 5
        fresnel = sat(50 * F0[1]) * Fc + (1 - Fc) * F0
        geometric = a["falloff"] * a["NoL"]
        diffuse = (p[4, :3] - p[4, :3] * p[1, 3]) / np.pi * geometric
        specular = geometric * D * visibility * fresnel
    output = np.asarray([[a["sphere"], a["soft"], a["line"], a["NoL"]], [*a["diffuseL"], a["falloff"]],
                         [*a["specularL"], 0], [c["NoL"], c["NoV"], c["VoL"], c["NoH"]],
                         [c["VoH"], no_newton["NoH"], no_newton["VoH"], float(sqrt_fast(packed[5, 2]))],
                         [a2, energy, initial["NoH"], initial["VoH"]], [*diffuse, 0], [*specular, 0],
                         [0, 0, 0, 0], [1, 1, 1, 0]], dtype=np.float64)
    if not np.isfinite(output).all():
        raise ValueError("nonfinite oracle result")
    info = dict(sphere_branch=branch, horizon_wrapped=a["wrapped"], line=bool(p[3, 3] > 0),
                soft=bool(p[5, 0] > 0), NoL=a["NoL"], ggx_d=float(d),
                line_denominator_ratio=a["line_denominator_ratio"],
                newton_delta=float(abs(c["NoH"] - no_newton["NoH"])),
                exact_sqrt_energy_delta=float(abs(energy - energy_oracle(p[0, 3], c["VoH"], a, True)[1])))
    return output, info


def candidates():
    frames = [dict(name="normal"),
              dict(name="skew", N=unit([0.15, -0.1, 1]).tolist(), V=unit([0.45, 0.25, 1]).tolist(),
                   to_light=[3, -2, 8], tangent=unit([1, 0.3, 0.1]).tolist()),
              dict(name="grazing", V=unit([1, 0.4, 0.1]).tolist(), to_light=[3, 1, 4], tangent=unit([0, 1, 0.2]).tolist()),
              dict(name="horizon", V=unit([0.4, 0.5, 1]).tolist(), to_light=[8, 2, -0.25], tangent=unit([1, 0, 0.1]).tolist())]
    shapes = [("point", 0, 0, 0), ("sphere", 0.8, 0, 0), ("soft", 0, 0.9, 0),
              ("sphere_soft", 0.8, 0.4, 0), ("line", 0, 0, 3), ("capsule", 0.6, 0.3, 3), ("broad", 4, 0, 0)]
    result = []
    for frame in frames:
        frame = dict(frame)
        name = frame.pop("name")
        for shape, radius, soft, length in shapes:
            for index, (rough, metal) in enumerate(((0.125, 0), (0.25, 0.5), (0.5, 1), (0.75, 0), (1, 0.5))):
                result.append(case(f"{name}_{shape}_r{rough}_m{metal}", **frame, radius=radius, soft_radius=soft,
                                   length=length, roughness=rough, metallic=metal, inverse_squared=bool(index % 2)))
    direction = [-0.6387413144111633, 0.11617802828550339, 0.7605998516082764]
    for rough in (0.02, 0.125, 0.5):
        result.append(case(f"captured_direction_radius_r{rough}", to_light=direction,
                           radius=0.006420149467885494, roughness=rough))
    result.append(case("low_F0_grazing", V=unit([1, 0.2, 0.15]).tolist(), to_light=[-4, 2, 3],
                       radius=0.7, soft_radius=0.2, specular=0.05, metallic=0, roughness=0.25))
    result.append(case("zero_specular", radius=1, specular=0, metallic=0))
    result.append(case("black_metal", radius=1, base_color=[0, 0, 0], metallic=1))
    probe_bits = [0, 0x00800000, 0x1E3CE508, 0x342BCC77, 0x3D800000, 0x3E800000,
                  0x3F000000, 0x3F800000, 0x40000000, 0x40800000, 0x41800000, 0x7F7FFFFF]
    for bits in probe_bits:
        value = float(np.asarray(bits, dtype=np.uint32).view(np.float32))
        result.append(case(f"sqrt_probe_{bits:08x}", radius=0.8, sqrt_probe=value, base_color=[0.2, 0.6, 0.9]))
    rng = np.random.default_rng(SEED)
    for i in range(32):
        result.append(case(f"random_{SEED}_{i}", N=unit([*rng.uniform(-0.3, 0.3, 2), 1]).tolist(),
                           V=unit([*rng.uniform(-0.8, 0.8, 2), 1]).tolist(), to_light=rng.uniform([1, -3, 4], [5, 3, 12]).tolist(),
                           tangent=unit([1, *rng.uniform(-0.3, 0.3, 2)]).tolist(), radius=float(rng.uniform(0.05, 1.5)),
                           soft_radius=float(rng.uniform(0, 0.6)), length=float(rng.uniform(0.5, 4)),
                           roughness=float(rng.choice([0.25, 0.5, 0.75])), metallic=float(rng.uniform(0, 1)),
                           specular=float(rng.uniform(0, 1)), inverse_squared=bool(i % 2)))
    return result


def rejection_self_check():
    invalid = [case("zero_N", N=[0, 0, 0]), case("zero_V", V=[0, 0, 0]),
               case("zero_tangent", tangent=[0, 0, 0]), case("nonunit_N", N=[0, 0, 2]),
               case("zero_distance", to_light=[0, 0, 0]), case("endpoint_zero", to_light=[1, 0, 0], length=2),
               case("line_cross_origin", to_light=[0, 0, 0], length=2),
               case("parallel_reflection", tangent=[0, 0, 1], length=2),
               case("antiparallel_half", to_light=[0, 0, -8]),
               case("sphere_tangent_singular", V=[1, 0, 0], to_light=[5, 0, 0], radius=1),
               case("roughness_without_floor", roughness=0), case("negative_radius", radius=-1),
               case("negative_length", length=-1), case("negative_soft", soft_radius=-1),
               case("negative_sqrt_probe", sqrt_probe=-1), case("nonfinite", V=[float("nan"), 0, 1])]
    rejected = []
    for c in invalid:
        try:
            oracle(pack(c))
        except ValueError as error:
            rejected.append({"name": c["name"], "reason": str(error)})
        else:
            raise AssertionError("degenerate fixture was accepted: " + c["name"])
    return rejected


def prepare():
    cases, inputs, expected, details, excluded = [], [], [], [], []
    for c in candidates():
        packed = pack(c)
        try:
            output, info = oracle(packed)
            if output[3, 3] < 1 and info["ggx_d"] < MIN_CONDITIONED_D:
                raise ValueError("outside bounded precision profile: nonsaturated GGX d < 0.01")
            if info["line_denominator_ratio"] < 0.03:
                raise ValueError("outside bounded precision profile: nearly parallel line/reflection")
        except ValueError as error:
            excluded.append({"name": c["name"], "reason": str(error)})
            continue
        cases.append(c)
        inputs.append(packed)
        expected.append(output)
        details.append(info)
    inputs, expected = np.asarray(inputs, dtype=np.float32), np.asarray(expected, dtype=np.float64)
    assert len(cases) >= 80
    assert len({c["name"] for c in cases}) == len(cases)
    assert len({p.tobytes() for p in inputs}) == len(cases)
    assert {d["sphere_branch"] for d in details} == {"inactive", "reflection_inside", "newton"}
    assert any(d["horizon_wrapped"] for d in details) and any(d["NoL"] == 0 for d in details)
    assert max(d["newton_delta"] for d in details) > 1e-5
    assert max(d["exact_sqrt_energy_delta"] for d in details) > 1e-4
    by_name = {c["name"]: expected[i] for i, c in enumerate(cases)}
    np.testing.assert_array_equal(by_name["zero_specular"][7, :3], 0)
    np.testing.assert_array_equal(by_name["black_metal"][6:9, :3], 0)
    point = by_name["normal_point_r0.5_m1"]
    np.testing.assert_array_equal(point[0], [0, 0, 1, 1])
    np.testing.assert_array_equal(point[1], [0, 0, 1, 1])
    np.testing.assert_allclose(point[7, :3], np.array([0.125, 0.5, 0.75]) / (4 * np.pi * 0.5 ** 4), rtol=0, atol=1e-15)
    probe_input = inputs[:, 5, 2].view(np.uint32)
    probe_output = expected[:, 4, 3].astype(np.float32).view(np.uint32)
    np.testing.assert_array_equal(probe_output, np.uint32(0x1FBD1DF5) + (probe_input >> np.uint32(1)))
    rejected = rejection_self_check()
    coverage = {name: sum(d["sphere_branch"] == name for d in details)
                for name in ("inactive", "reflection_inside", "newton")}
    coverage.update(line=sum(bool(d["line"]) for d in details), soft=sum(bool(d["soft"]) for d in details),
                    horizon_wrap=sum(bool(d["horizon_wrapped"]) for d in details),
                    zero_NoL=sum(d["NoL"] == 0 for d in details))
    return cases, inputs, expected, details, dict(samples=len(cases), seed=SEED, coverage=coverage,
        excluded_candidates=excluded, degenerate_rejections=rejected, offline_self_check="passed")


def shader_snapshot():
    root = (ROOT / "Source/RenderPasses/customrenderpipline/Codecs").resolve()
    active, emitted, hashes = set(), set(), {}
    include = re.compile(r'^\s*#\s*include\s+"([^"\r\n]+)"[ \t]*$', re.MULTILINE)

    def visit(path):
        path = path.resolve()
        if not path.is_relative_to(root) or path in active:
            raise ValueError("include cycle or path escaping codec root")
        if path in emitted:
            return ""
        active.add(path)
        data = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
        text = include.sub(lambda match: visit(path.parent / match[1]), data.decode("utf-8"))
        if re.search(r'^\s*(?:#\s*include\b|import\b)', text, re.MULTILINE):
            raise ValueError("unresolved shader include or import")
        active.remove(path)
        emitted.add(path)
        return f"// Source: {path.relative_to(ROOT).as_posix()}\n{text}\n"

    return visit(root / "Lighting/DefaultLit.slangh") + KERNEL, hashes


def comparison(actual, expected, cases):
    groups = {"area": [(row, col) for row in (0, 1, 2, 9) for col in range(4)],
              "context": [(3, col) for col in range(4)] + [(4, col) for col in range(3)] + [(5, 2), (5, 3)],
              "energy": [(5, 0), (5, 1)], "lobes": [(row, col) for row in (6, 7, 8) for col in range(4)]}
    flags, metrics = {}, {}
    flags["finite"] = np.isfinite(actual).all(axis=(1, 2))
    for name, indices in groups.items():
        a = np.stack([actual[:, row, col] for row, col in indices], axis=1)
        e = np.stack([expected[:, row, col] for row, col in indices], axis=1)
        rtol, atol = TOLERANCES[name]
        flags[name] = np.isclose(a, e, rtol=rtol, atol=atol).all(axis=1)
        metrics[name] = {"rtol": rtol, "atol": atol,
                         "max_absolute_error": float(np.abs(a - e).max()) if np.isfinite(a).all() else None}
    flags["sqrtFast_bits"] = actual[:, 4, 3].view(np.uint32) == expected[:, 4, 3].astype(np.float32).view(np.uint32)
    flags["zero_transmission"] = (actual[:, 8] == 0).all(axis=1)
    passed = np.logical_and.reduce(list(flags.values()))
    return dict(passed=bool(passed.all()), groups=metrics, cases=[dict(index=i, name=c["name"], passed=bool(passed[i]),
                failed_checks=[name for name, values in flags.items() if not values[i]]) for i, c in enumerate(cases)])


def run_gpu(cases, inputs, expected, details, self_check, out):
    import falcor

    out.mkdir(parents=True, exist_ok=True)
    shader, hashes = shader_snapshot()
    (out / "kernel.cs.slang").write_text(shader, encoding="utf-8")
    ue_root = Path(os.environ.get("UE_SOURCE_ROOT", "E:/ue/engine/UnrealEngine")) / "Engine/Shaders/Private"
    ue_sources = [ue_root / name for name in ("CapsuleLight.ush", "CapsuleLightIntegrate.ush", "AreaLightCommon.ush",
                                            "BRDF.ush", "ShadingModels.ush", "FastMathThirdParty.ush")]
    result = dict(status="running", scope="ordinary capsule geometry, sphere Newton, energy and DefaultLit component probe",
                  capture_equivalence=False, native_lighting_pass_complete=False, **self_check,
                  source_hashes=hashes, kernel_sha256=hashlib.sha256(shader.encode()).hexdigest(),
                  script_sha256=hashlib.sha256((ROOT / "scripts/customrenderpipline/capsule_lighting_smoke.py").read_bytes()).hexdigest(),
                  ue_source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in ue_sources},
                  numpy_version=np.__version__, case_inputs=cases, oracle_details=details,
                  tolerance_basis=__doc__, input_rows=INPUT_ROWS, output_rows=OUTPUT_ROWS,
                  output_layout=["sphere,soft,lineCos,NoL", "diffuseL.xyz,falloff", "specularL.xyz,0",
                                 "Newton NoL,NoV,VoL,NoH", "Newton VoH,noNewton NoH,VoH,sqrtProbe",
                                 "modifiedA2,energy,initial NoH,VoH", "diffuse.xyz,0", "specular.xyz,0",
                                 "transmission.xyz,0", "falloffColor.xyz,0"])
    actual, failure = None, None
    try:
        device = falcor.Device(type=falcor.DeviceType.D3D12, gpu=0, enable_debug_layer=True)
        src = device.create_structured_buffer(16, len(cases) * INPUT_ROWS, falcor.ResourceBindFlags.ShaderResource)
        dst = device.create_structured_buffer(16, len(cases) * OUTPUT_ROWS, falcor.ResourceBindFlags.UnorderedAccess)
        src.from_numpy(inputs.reshape(-1, 4))
        compute = falcor.ComputePass(device, string=shader, cs_entry="main", shader_model=falcor.ShaderModel.SM6_6)
        compute.globals["gInput"], compute.globals["gResult"] = src, dst
        compute.execute(threads_x=len(cases))
        actual = np.frombuffer(dst.to_numpy().tobytes(), dtype=np.float32).reshape(expected.shape).copy()
        result["comparison"] = comparison(actual, expected, cases)
        if not result["comparison"]["passed"]:
            raise AssertionError("capsule lighting comparison failed; inspect per-stage/case evidence")
        result["status"] = "passed"
    except Exception as error:
        failure = error
        result.update(status="failed", error_type=type(error).__name__, error=str(error))
    finally:
        arrays = dict(inputs=inputs, expected=expected, names=np.asarray([c["name"] for c in cases]),
                      sqrt_probe_input_bits=inputs[:, 5, 2].view(np.uint32),
                      sqrt_probe_expected_bits=expected[:, 4, 3].astype(np.float32).view(np.uint32))
        if actual is not None:
            arrays.update(actual=actual, actual_bits=actual.view(np.uint32))
        raw = out / "raw.npz"
        np.savez_compressed(raw, **arrays)
        result.update(raw_npz=str(raw), raw_npz_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
        dll = BIN / "Falcor.dll"
        result["falcor_dll_sha256"] = hashlib.sha256(dll.read_bytes()).hexdigest() if dll.is_file() else None
        (out / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("CAPSULE_LIGHTING_GPU_" + result["status"].upper() + " " + json.dumps({"samples": len(cases), "result": str(out / "result.json")}))
    if failure is not None:
        raise failure
    return result


def main(gpu=False, out=None):
    cases, inputs, expected, details, self_check = prepare()
    # Validate evidence metadata before any device execution can produce results.
    json.dumps(dict(case_inputs=cases, oracle_details=details, **self_check), allow_nan=False)
    assert comparison(expected.astype(np.float32), expected, cases)["passed"]
    mutation = expected.astype(np.float32)
    mutation[0, 4, 3] = np.sqrt(inputs[0, 5, 2])
    assert not comparison(mutation, expected, cases)["passed"], "sqrt replacement must fail"
    shader, hashes = shader_snapshot()
    if not gpu:
        print("CAPSULE_LIGHTING_ORACLE_PASSED " + json.dumps({**self_check, "gpu_executed": False,
              "source_hashes": hashes, "kernel_sha256": hashlib.sha256(shader.encode()).hexdigest()}))
        return self_check
    return run_gpu(cases, inputs, expected, details, self_check, out or ROOT / "build/capsule-lighting-evidence")


if __name__ == "__main__" or EMBEDDED:
    if EMBEDDED:
        main(gpu=True)
        exit()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--oracle-only", action="store_true", help="offline only (default), without device or output files")
        mode.add_argument("--gpu", action="store_true", help="explicit GPU execution; Mogwai selects this automatically")
        parser.add_argument("--output", type=Path)
        args = parser.parse_args()
        main(gpu=args.gpu, out=args.output)
