"""Run from the checkout root using Mogwai --headless --script <this path>."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd() / "build/m0-evidence/python"))
import numpy as np
from falcor import *

root = Path.cwd()
out = root / "build/m0-evidence/raster-smoke"
out.mkdir(parents=True, exist_ok=True)
g = RenderGraph("M0StockRaster")
g.addPass(createPass("GBufferRaster"), "GBufferRaster")
for channel in ("posW", "normW", "diffuseOpacity"):
    g.markOutput("GBufferRaster." + channel)
m.addGraph(g)
m.loadScene(str(root / "scripts/customrenderpipline/raster_smoke.pyscene"))
m.resizeFrameBuffer(640, 360)
m.ui = False
m.clock.pause()
m.clock.time = 0
for _ in range(3):
    m.renderFrame()

arrays = {}
stats = {}
for channel in ("posW", "normW", "diffuseOpacity"):
    data = np.array(g.getOutput("GBufferRaster." + channel).to_numpy(), copy=True)
    if data.shape != (360, 640, 4) or not np.isfinite(data).all():
        raise RuntimeError("Invalid GPU output for " + channel + ": " + str(data.shape))
    arrays[channel] = data
    np.save(out / (channel + ".npy"), data)
    stats[channel] = {"shape": list(data.shape), "dtype": str(data.dtype),
                      "sha256": hashlib.sha256(data.tobytes()).hexdigest()}

covered = arrays["posW"][..., 3] > 0
coverage = int(covered.sum())
if not 1000 < coverage < 640 * 360 // 2:
    raise RuntimeError("Unexpected cube raster coverage: " + str(coverage))
lengths = np.linalg.norm(arrays["normW"][covered, :3], axis=1)
if not np.allclose(lengths, 1.0, atol=0.002):
    raise RuntimeError("Raster normals are not unit length")
if not np.any(arrays["diffuseOpacity"][covered, :3] > 0):
    raise RuntimeError("Raster material output is empty")

# PPM is intentionally dependency-free and gives a inspectable view of actual GPU normals.
preview = np.zeros((360, 640, 3), dtype=np.uint8)
preview[covered] = np.rint(np.clip(arrays["normW"][covered, :3] * 0.5 + 0.5, 0, 1) * 255).astype(np.uint8)
with (out / "normals.ppm").open("wb") as stream:
    stream.write(b"P6\n640 360\n255\n")
    stream.write(preview.tobytes())
report = {"status": "passed", "scope": "stock GBufferRaster, not UE GBuffer ABI",
          "resolution": [640, 360], "frames": 3, "covered_pixels": coverage, "outputs": stats}
(out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("M0_RASTER_SMOKE_PASSED " + json.dumps(report))
exit()
