"""Mogwai GPU smoke for JSON sampler max_anisotropy and native sampling parity.

Run with Mogwai --script. CRP_NATIVE_SAMPLER_OUT may name a NONEXISTENT
child of build/targetmap-shading-a1; otherwise a fresh sampler-gpu-* child
is created. Inspect result.json, not Mogwai's exit code, for acceptance.
Importing this file does not import Falcor/NumPy, create files, or run GPU work.
The diagnostic DDS and scene are authored here, never loaded from a capture.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[2]
WIDTH, HEIGHT = 32, 16
KINDS = ("Compute", "Fullscreen", "Mesh")
VARIANTS = (("default", {}), ("one", {"max_anisotropy": 1}),
            ("eight", {"max_anisotropy": 8}), ("sixteen", {"max_anisotropy": 16}))
SAMPLE_SOURCE = """Texture2D<float4> sourceTexture;
SamplerState sourceSampler;
float4 sampleValue()
{
    return sourceTexture.SampleGrad(sourceSampler, float2(0.5, 0.5),
        float2(32.0 / 256.0, 0.0), float2(0.0, 1.0 / 256.0));
}
"""


def create_output(parent, requested=None):
    parent = Path(parent).resolve()
    if requested is not None:
        output = Path(requested).resolve()
        if output == parent or not output.is_relative_to(parent):
            raise ValueError("Sampler output must be a fresh child of the owned parent")
        output.mkdir(parents=True, exist_ok=False)
        return output
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="sampler-gpu-", dir=parent))


def write_fixtures(output):
    output = Path(output)
    # DX10 DDS: DXGI_FORMAT_R32G32B32A32_FLOAT (2), 2D (3), one layer.
    # Each mip is spatially constant but different from every other mip.
    # Explicit 32:1 gradients make LOD/filtering differences measurable.
    header = [124, 0x2100F, 256, 256, 256 * 16, 0, 9] + [0] * 11
    header += [32, 4, int.from_bytes(b"DX10", "little"), 0, 0, 0, 0, 0]
    header += [0x401008, 0, 0, 0, 0]
    payload = b"".join(struct.pack("<4f", mip / 8, (8 - mip) / 8, mip % 2, 1)
                       * ((256 >> mip) ** 2) for mip in range(9))
    texture = output / "AuthoredMips.dds"
    with texture.open("xb") as stream:
        stream.write(b"DDS " + struct.pack("<31I", *header) + struct.pack("<5I", 2, 3, 0, 1, 0) + payload)
    sources = {
        "Compute": SAMPLE_SOURCE + """RWTexture2D<float4> target;
[numthreads(8,8,1)] void main(uint3 p : SV_DispatchThreadID)
{ if (p.x < 32 && p.y < 16) target[p.xy] = sampleValue(); }
""",
        "Fullscreen": SAMPLE_SOURCE + "float4 main(float4 p : SV_Position) : SV_Target0 { return sampleValue(); }\n",
        "Mesh": """#include "Scene/VertexAttrib.slangh"
import Scene.Raster;
""" + SAMPLE_SOURCE + """VSOut vsMain(VSIn v) { return defaultVS(v); }
float4 psMain(VSOut v) : SV_Target0 { return sampleValue(); }
""",
    }
    files = {"texture": texture}
    for kind, source in sources.items():
        files[kind] = output / (kind + ".slang")
        with files[kind].open("x", encoding="utf-8") as stream:
            stream.write(source)
    files["scene"] = output / "AuthoredCube.pyscene"
    with files["scene"].open("x", encoding="utf-8") as stream:
        stream.write('''from falcor import *
material = StandardMaterial("Sampler fixture")
mesh = TriangleMesh.createCube(float3(1.5))
node = sceneBuilder.addNode("Sampler cube", Transform())
sceneBuilder.addMeshInstance(node, sceneBuilder.addTriangleMesh(mesh, material))
camera = Camera("Sampler camera")
camera.position = float3(3, 2, 4)
camera.target = float3(0, 0, 0)
camera.up = float3(0, 1, 0)
camera.nearPlane = 0.1
camera.farPlane = 100.0
camera.focalLength = 35.0
camera.aspectRatio = 2.0
sceneBuilder.addCamera(camera)
''')
    return files


def pass_properties(kind, shader, sampler):
    source = {"name": "source", "binding": "sourceTexture", "direction": "input",
              "format": "RGBA32Float", "size": [256, 256], "mip_count": 9}
    properties = {"shader": {"file": str(shader)}, "resources": [source],
                  "samplers": {"sourceSampler": copy.deepcopy(sampler)}}
    target = {"name": "color", "format": "RGBA32Float", "size": [WIDTH, HEIGHT]}
    if kind == "Mesh":
        properties["shader"].update(vertex="vsMain", pixel="psMain")
        properties["colorTargets"] = [dict(target, slot=0)]
        properties["state"] = {"cull_mode": "None", "depth_enabled": False, "depth_write": False}
    elif kind == "Compute":
        properties["resources"].append(dict(target, direction="output", binding="target"))
        properties["dispatch"] = {"threads": [WIDTH, HEIGHT, 1]}
    elif kind == "Fullscreen":
        properties["resources"].append(dict(target, direction="output", slot=0))
    else:
        raise ValueError("Unknown sampler fixture executor")
    return properties


def invalid_samplers():
    values = (("bool_true", True), ("bool_false", False), ("float_integral", 8.0),
              ("float_fractional", 8.5), ("zero", 0), ("seventeen", 17), ("negative", -1),
              ("null", None), ("string", "8"), ("array", [8]), ("object", {}))
    return [(label, {"max_anisotropy": value}) for label, value in values] + [
        ("unknown", {"max_anisotropy": 8, "unexpected": True})]


def _record_file(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def run(host, output):
    import sys
    sys.path.insert(0, str(ROOT / "build/m0-evidence/python"))
    import falcor
    import numpy as np

    files = write_fixtures(output)
    graph = falcor.RenderGraph("NativeSamplerDescriptor")
    graph.addPass(falcor.createPass("CustomRenderPiplineAssetPass", {"assets": {"source": {
        "kind": "texture2D", "file": str(files["texture"]), "format": "RGBA32Float",
        "size": [256, 256], "mip_count": 9}}}), "Asset")
    types = {"Compute": "CustomRenderPiplineComputePass", "Fullscreen": "CustomRenderPiplineFullscreenPass",
             "Mesh": "CustomRenderPiplineMeshDrawPass"}
    declarations = {}
    for kind in KINDS:
        for label, sampler in VARIANTS:
            name = kind + "_" + label
            declarations[name] = pass_properties(kind, files[kind], sampler)
            graph.addPass(falcor.createPass(types[kind], declarations[name]), name)
            graph.addEdge("Asset.source", name + ".source")
            graph.markOutput(name + ".color")
    graph.markOutput("Asset.source")
    (output / "pass-properties.json").write_text(json.dumps(declarations, indent=2) + "\n", encoding="utf-8")
    host.loadScene(str(files["scene"]))
    host.resizeFrameBuffer(WIDTH, HEIGHT)
    host.clock.pause()
    host.clock.time = 0
    host.ui = False
    host.addGraph(graph)
    host.setActiveGraph(graph)
    host.renderFrame()
    source = graph.getOutput("Asset.source")
    # Confirm the authoritative GPU texture carries the authored mip bytes.
    for mip in range(9):
        actual = np.asarray(source.to_numpy(mip_level=mip), dtype=np.float32)
        expected = np.array([mip / 8, (8 - mip) / 8, mip % 2, 1], dtype=np.float32)
        np.testing.assert_array_equal(actual, np.broadcast_to(expected, actual.shape))

    device = graph.device
    reference = falcor.ComputePass(device, file=str(files["Compute"]), cs_entry="main",
                                  shader_model=falcor.ShaderModel.SM6_6)
    target = device.create_texture(width=WIDTH, height=HEIGHT, format=falcor.ResourceFormat.RGBA32Float,
                                  mip_levels=1, bind_flags=falcor.ResourceBindFlags.UnorderedAccess
                                  | falcor.ResourceBindFlags.ShaderResource)
    reference.root_var["sourceTexture"] = source
    reference.root_var["target"] = target
    native = {}
    address = falcor.TextureAddressingMode.Clamp
    for anisotropy in (1, 8, 16):
        sampler = device.create_sampler(max_anisotropy=anisotropy, address_mode_u=address,
                                        address_mode_v=address, address_mode_w=address)
        assert sampler.max_anisotropy == anisotropy
        reference.root_var["sourceSampler"] = sampler
        reference.execute(threads_x=WIDTH, threads_y=HEIGHT)
        native[anisotropy] = np.array(target.to_numpy(), dtype=np.float32, copy=True).reshape(HEIGHT, WIDTH, 4)
        native[anisotropy].tofile(output / f"native-anisotropy-{anisotropy}.rgba32f")
    difference = float(np.max(np.abs(native[1] - native[8])))
    assert difference > 0.01, "Diagnostic must distinguish actual GPU anisotropy 1 from 8"

    comparisons, pixels = [], {}
    for kind in KINDS:
        for label, descriptor in VARIANTS:
            name = kind + "_" + label
            anisotropy = descriptor.get("max_anisotropy", 1)
            actual = np.array(graph.getOutput(name + ".color").to_numpy(), dtype=np.float32, copy=True).reshape(HEIGHT, WIDTH, 4)
            pixels[name] = actual
            actual.tofile(output / (name + ".rgba32f"))
            mask = actual[..., 3] > 0.5 if kind == "Mesh" else np.ones((HEIGHT, WIDTH), dtype=bool)
            assert mask.any(), name + " must write diagnostic pixels"
            if kind == "Mesh":
                assert not mask.all(), "Scene diagnostic must retain an uncovered background"
                np.testing.assert_array_equal(actual[~mask], np.zeros_like(actual[~mask]))
            np.testing.assert_allclose(actual[mask], native[anisotropy][mask], atol=1e-6, rtol=0)
            comparisons.append({"executor": kind, "variant": label, "max_anisotropy": anisotropy,
                                "compared_pixels": int(mask.sum()), "native_rgba": native[anisotropy][0, 0].tolist(),
                                "max_abs_error": float(np.max(np.abs(actual[mask] - native[anisotropy][mask])))})
        np.testing.assert_array_equal(pixels[kind + "_default"], pixels[kind + "_one"])
        assert float(np.max(np.abs(pixels[kind + "_one"] - pixels[kind + "_eight"]))) > 0.01

    # Reject through the actual three public pass constructors. A different
    # shader/scene failure cannot satisfy these cases: require sampler diagnostics.
    rejections = []
    for kind in KINDS:
        for label, sampler in invalid_samplers():
            properties = pass_properties(kind, files[kind], sampler)
            expected = "Unknown sampler property" if label == "unknown" else "max_anisotropy must be an integer"
            try:
                falcor.createPass(types[kind], properties)
            except Exception as error:
                assert expected in str(error), (kind, label, str(error))
                rejections.append({"executor": kind, "case": label, "message": str(error)[:2048]})
            else:
                raise AssertionError("Accepted invalid sampler " + kind + "/" + label)
    return {"status": "passed", "full_renderer_parity": False, "capture_inputs_used": False,
            "authored_mips_gpu_exact": True, "native_sampler_api": "device.create_sampler(max_anisotropy=N)",
            "anisotropy_1_vs_8_max_abs_difference": difference, "omitted_equals_one_all_executors": True,
            "comparisons": comparisons, "rejections": rejections,
            "files": [_record_file(path) for path in sorted(output.iterdir()) if path.is_file()]}


def main(host):
    output = create_output(ROOT / "build/targetmap-shading-a1", os.environ.get("CRP_NATIVE_SAMPLER_OUT"))
    print("NATIVE_SAMPLER_EVIDENCE " + str(output), flush=True)
    try:
        result = run(host, output)
    except Exception as error:
        traceback.print_exc()
        result = {"status": "failed", "error": str(error), "full_renderer_parity": False, "capture_inputs_used": False}
    result["output"] = str(output)
    total = sum(path.stat().st_size for path in output.iterdir() if path.is_file())
    if total > 8 * 1024 * 1024:
        result.update(status="failed", error="Sampler evidence exceeded 8 MiB budget")
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("NATIVE_SAMPLER_" + result["status"].upper(), flush=True)
    return result


if "m" in globals():
    main(m)
    exit()
elif __name__ == "__main__":
    raise SystemExit("Run with Mogwai --script; CPU tests import this module without a GPU")
