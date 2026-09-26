"""Validate the paired scene's stock raster against independent CPU ray/triangle hits."""
import hashlib
import json
from pathlib import Path
import sys

root = Path.cwd()
sys.path.insert(0, str(root / "build/m0-evidence/python"))
import numpy as np
from falcor import *

definition = root / "scripts/customrenderpipline/reference_scene.json"
source = json.loads(definition.read_text(encoding="utf-8"))
out = root / "build/m0-evidence/reference-pair"
out.mkdir(parents=True, exist_ok=True)
g = RenderGraph("M0PairedStockRaster")
g.addPass(createPass("GBufferRaster"), "Raster")
for name in ("posW", "normW", "diffuseOpacity"):
    g.markOutput("Raster." + name)
m.addGraph(g)
m.loadScene(str(root / "scripts/customrenderpipline/reference_scene.pyscene"))
width, height = source["camera"]["resolution"]
m.resizeFrameBuffer(width, height)
m.ui = False
m.clock.pause()
m.clock.time = 0
for _ in range(3):
    m.renderFrame()
outputs = {name: np.array(g.getOutput("Raster."+name).to_numpy(), copy=True)
           for name in ("posW", "normW", "diffuseOpacity")}
for name, array in outputs.items():
    if array.shape != (height, width, 4) or not np.isfinite(array).all():
        raise RuntimeError("Invalid raster output: " + name)
    np.save(out / (name+".npy"), array)

def convert(v):
    return np.asarray([v[1], v[2], -v[0]], dtype=np.float64) / 100
def normalize(v):
    return v / np.linalg.norm(v)

triangles = []
for instance in source["instances"]:
    mesh = source["meshes"][instance["mesh"]]
    positions = [convert(np.asarray(v["position"])+instance["translation_cm"]) for v in mesh["vertices"]]
    for ids in mesh["triangles"]:
        triangles.append(np.asarray([positions[i] for i in ids]))
triangles = np.asarray(triangles)
eye = convert(source["camera"]["position_cm"])
forward = normalize(convert(source["camera"]["target_cm"])-eye)
right = normalize(np.cross(forward, convert(source["camera"]["up"])))
up = np.cross(right, forward)
tan_h = np.tan(np.deg2rad(source["camera"]["horizontal_fov_degrees"])/2)
errors = []
normal_errors = []
misses = 0
for y in range(8, height, 16):
    for x in range(8, width, 16):
        ray = normalize(forward + right*((2*(x+0.5)/width-1)*tan_h)
                        + up*((1-2*(y+0.5)/height)*tan_h*height/width))
        hits = []
        for a,b,c in triangles:
            e1,e2 = b-a,c-a
            p = np.cross(ray,e2)
            determinant = np.dot(e1,p)
            if determinant < 1e-9:
                continue
            tv = eye-a
            u = np.dot(tv,p)/determinant
            q = np.cross(tv,e1)
            v = np.dot(ray,q)/determinant
            t = np.dot(e2,q)/determinant
            if u >= 0 and v >= 0 and u+v <= 1 and t > 0:
                hits.append((t,min(u,v,1-u-v),normalize(np.cross(e1,e2))))
        actual = outputs["posW"][y,x]
        if not hits:
            if actual[3] != 0:
                raise RuntimeError("GPU covers CPU miss at " + str((x,y)))
            misses += 1
            continue
        distance,edge,normal = min(hits,key=lambda h:h[0])
        if edge < 0.01:
            continue
        if actual[3] == 0:
            raise RuntimeError("GPU missed expected surface at " + str((x,y)))
        errors.append(float(np.linalg.norm(actual[:3]-(eye+ray*distance))))
        normal_errors.append(float(np.linalg.norm(outputs["normW"][y,x,:3]-normal)))
if len(errors) < 100 or max(errors) > 0.0003 or max(normal_errors) > 0.002:
    raise RuntimeError("Ray/triangle comparison failed: " + str((len(errors), max(errors,default=-1), max(normal_errors,default=-1))))
covered = outputs["posW"][...,3] > 0
preview = np.zeros((height,width,3),dtype=np.uint8)
preview[covered] = np.rint(np.clip(outputs["normW"][covered,:3]*0.5+0.5,0,1)*255).astype(np.uint8)
with (out / "normals.ppm").open("wb") as stream:
    stream.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
    stream.write(preview.tobytes())
report = {"status":"passed", "source_sha256":hashlib.sha256(definition.read_bytes()).hexdigest(),
          "scope":"stock geometry/camera/normals; no UE material/light equivalence claim",
          "sampled_hits":len(errors), "sampled_misses":misses, "covered_pixels":int(covered.sum()),
          "max_position_error_m":max(errors), "max_normal_error":max(normal_errors)}
(out / "falcor-raster-result.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print("M0_REFERENCE_RASTER_PASSED " + json.dumps(report))
exit()
