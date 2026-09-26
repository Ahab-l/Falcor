"""D3D12 exact D32S8 async plane readback; run with Mogwai --headless --script."""
import gc
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/customrenderpipline"), str(ROOT / "build/m0-evidence/python")]
import falcor
import numpy as np


OUT = Path(tempfile.mkdtemp(prefix="async-depth-", dir=ROOT / "build/native-framework-completion"))
print("ASYNC_DEPTH_EVIDENCE " + str(OUT), flush=True)


def same_planes(actual, expected):
    keys = (
        "width",
        "height",
        "depth",
        "stencil",
        "depth_row_bytes",
        "stencil_row_bytes",
        "depth_native_format",
        "stencil_native_format",
    )
    return all(actual[key] == expected[key] for key in keys)


def run():
    from observer import PipelineObserver
    assert hasattr(falcor, "customRenderPiplineReadDepthStencilAsync")
    shader = OUT / "DepthFixture.slang"
    shader.write_text('''#include "Scene/VertexAttrib.slangh"
import Scene.Raster;
VSOut vsMain(VSIn v) { return defaultVS(v); }
float4 psMain(VSOut v):SV_Target0 { return float4(v.posW,1); }
''', encoding="utf-8")
    # Native MeshDraw clearDsv initializes known depth + nonzero stencil. Never
    # infer packed D32S8 upload semantics from its compact readback plane sizes.
    graph = falcor.RenderGraph("AsyncDepthFixture")
    views = []
    for kind, size, layers in (("texture2DArray", [37,19], 2), ("textureCube", [32,32], 6)):
        for layer in range(layers):
            for mip in range(3):
                name = f"Depth{kind}{layer}M{mip}"
                width, height = size[0] >> mip, size[1] >> mip
                depth, stencil = .125 + (layer*3+mip)/32, 17+(layer*3+mip)*7
                props = {
                    "shader": {"file": str(shader), "vertex": "vsMain", "pixel": "psMain"},
                    "instanceIDs": [],
                    "colorTargets": [{"name":"color", "format":"RGBA32Float", "slot":0, "size":[width,height]}],
                    "depthTarget": {"name":"depth", "format":"D32FloatS8Uint", "size":size,
                                    "kind":kind, "array_size":2 if kind=="texture2DArray" else 1,
                                    "mip_count":3, "view":{"mip":mip,"first_slice":layer,"slice_count":1},
                                    "clear":depth, "stencilClear":stencil},
                }
                graph.addPass(falcor.createPass("CustomRenderPiplineMeshDrawPass", props), name)
                if not views: graph.markOutput(name+".color")  # Stock display is a 2D color view.
                graph.markOutput(name+".depth")
                views.append((name+".depth", mip, layer, width, height, depth, stencil))
    m.loadScene(str(ROOT/"scripts/customrenderpipline/reference_scene.pyscene"))
    m.resizeFrameBuffer(80,60)
    m.clock.pause()
    m.ui = False
    m.addGraph(graph)
    m.setActiveGraph(graph)
    m.renderFrame()
    raw = PipelineObserver(graph)
    jobs, rejections = [], []
    for name, mip, layer, width, height, depth, stencil in views:
        texture = graph.getOutput(name)
        reference = raw.read(name, mip=mip, slice=layer)
        np.testing.assert_array_equal(np.frombuffer(reference["depth"], dtype=np.float32),
                                      np.full(width*height, depth, dtype=np.float32))
        assert reference["stencil"] == bytes([stencil]) * (width*height)
        native = falcor.customRenderPiplineReadDepthStencilAsync(texture, mip, layer)
        mapped = raw.read_async(name, mip=mip, slice=layer)
        assert native.byte_size == width*height*5
        assert native.staging_bytes >= native.byte_size
        assert mapped.staging_bytes == native.staging_bytes
        jobs.append((native, reference, False))
        jobs.append((mapped, reference, True))
        if len(jobs) == 2:
            for label, operation in (
                ("implicit_plane", lambda: texture.read_async()),
                ("mip", lambda: falcor.customRenderPiplineReadDepthStencilAsync(texture, 3, layer)),
                ("layer", lambda: falcor.customRenderPiplineReadDepthStencilAsync(texture, mip, 2)),
                ("aggregate_budget", lambda: raw.read_async(name,mip=mip,slice=layer,max_bytes=native.staging_bytes-1)),
            ):
                try: operation()
                except Exception as error: rejections.append({"case":label,"message":str(error)})
                else: raise AssertionError("Accepted invalid depth readback " + label)
    # The graph/output catalog is no longer consulted when collecting snapshots.
    m.removeGraph(graph)
    del texture, graph, raw
    gc.collect()
    collection_seconds = []
    for task, reference, mapped in jobs:
        deadline = time.perf_counter() + 10
        while not task.ready:
            if time.perf_counter() >= deadline: raise AssertionError("Depth task timed out")
            time.sleep(.001)  # Explicit test harness only; not a render callback.
        begin = time.perf_counter()
        actual = task.result()
        collection_seconds.append(time.perf_counter()-begin)
        assert same_planes(actual, reference), "async/sync exact mismatch"
        if mapped:
            assert actual["view"] == reference["view"]
            assert actual["name"] == reference["name"]
        assert same_planes(task.result(), reference)
    return {"status":"passed", "backend":"D3D12", "mip_layer_snapshots":len(views),
            "native_and_raw_tasks":len(jobs), "graph_removed_before_collection":True,
            "known_depth_and_nonzero_stencil":True, "exact_sync_reference":True,
            "pending_gate_evidence":"NativeAsyncDepthReadbackPendingLifetime native test",
            "rejections":rejections, "collection_seconds":collection_seconds}


try:
    result = run()
except Exception as error:
    traceback.print_exc()
    result = {"status": "failed", "error": str(error)}
(OUT / "result.json").write_text(json.dumps(result, indent=2))
print("NATIVE_ASYNC_DEPTH_" + result["status"].upper(), flush=True)
exit()
