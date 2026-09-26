"""UE commandlet: export four original Engine meshes into an isolated run.

Invoked by build/source-assets/launch_export.py. Never saves a UE package and
never reads a capture. FBX preserves the authored render LOD0 geometry; UE's
own indexed *_Internal.obj is a separately countable geometry/normal export.

Source API references beneath Engine/Source in this engine checkout:
  Runtime/Engine/Classes/Engine/StaticMesh.h:2146-2208 (LOD/count/bounds)
  Runtime/Engine/Public/AssetExportTask.h and Classes/Exporters/Exporter.h:254
  Editor/UnrealEd/Private/EditorExporters.cpp:2070,2259,2378 (native OBJ/FBX)
  Editor/UnrealEd/Classes/Exporters/FbxExportOption.h:64-127 (export options)
"""
import hashlib
import json
import os
from pathlib import Path

import unreal


ASSETS = (
    "/Engine/BasicShapes/Sphere",
    "/Engine/BasicShapes/Cube",
    "/Engine/EngineSky/SM_SkySphere",
    "/Engine/MapTemplates/SM_Template_Map_Floor",
)


def fingerprint(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def vector(value):
    return [float(value.x), float(value.y), float(value.z)]


def obj_counts(path):
    data = path.read_bytes()
    text = data.decode("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig")
    counts = {"vertices": 0, "uvs": 0, "normals": 0, "triangles": 0}
    faces = []
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] in ("v", "vt", "vn"):
            counts[{"v": "vertices", "vt": "uvs", "vn": "normals"}[fields[0]]] += 1
        elif fields[0] == "f":
            if len(fields) != 4:
                raise RuntimeError("Native OBJ export contains a non-triangle face")
            counts["triangles"] += 1
            faces.append(fields[1:])
    for face in faces:
        for vertex in face:
            for component, name in zip(vertex.split("/"), ("vertices", "uvs", "normals")):
                if component and not 1 <= int(component) <= counts[name]:
                    raise RuntimeError("Native OBJ contains an invalid {} index".format(name))
    return counts


def export(mesh, filename, exporter, options=None):
    task = unreal.AssetExportTask()
    for name, value in {
        "object": mesh, "exporter": exporter, "filename": str(filename),
        "selected": False, "replace_identical": False, "prompt": False,
        "automated": True, "use_file_archive": False, "write_empty_files": False,
    }.items():
        task.set_editor_property(name, value)
    if options is not None:
        task.set_editor_property("options", options)
    success = unreal.Exporter.run_asset_export_task(task)
    errors = list(task.get_editor_property("errors"))
    if not success or errors or not filename.is_file() or filename.stat().st_size == 0:
        raise RuntimeError("Export failed for {}: {}".format(filename, errors))


def main():
    request_path = Path(os.environ["UE_SOURCE_ASSETS_REQUEST"]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    run = Path(request["run_directory"]).resolve()
    workspace = Path(request["workspace"]).resolve()
    base = workspace / "build/source-assets"
    if run == base or not run.is_relative_to(base) or request_path.parent != run:
        raise RuntimeError("Export output must be a dedicated workspace source-assets run")
    actual_project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
    actual_engine = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir())).resolve()
    if actual_project != run / "Scratch" or actual_engine != Path(request["engine_root"]).resolve() / "Engine":
        raise RuntimeError("This export must run in its isolated project with the declared engine")
    if tuple(entry["asset"] for entry in request["assets"]) != ASSETS:
        raise RuntimeError("Only the four declared original Engine meshes are supported")
    for entry in request["assets"]:
        expected_package = actual_engine / "Content" / (entry["asset"][len("/Engine/"):] + ".uasset")
        if Path(entry["source_files"][0]["path"]).resolve() != expected_package:
            raise RuntimeError("Source package identity does not match the Engine asset")

    manifest = {
        "version": 1, "status": "running", "capture_inputs": False,
        "source": "Original UE Engine assets; locally built render LOD data",
        "source_packages_saved": False, "exported_lods": [0], "assets": [],
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "fbx": {"exporter": "StaticMeshExporterFBX", "units": "centimeters",
                "axis_system": "UE FBX metadata: right-handed Z-up, default -Y front",
                "position": "(UE.X, -UE.Y, UE.Z); importer must honor FBX axis/unit metadata",
                "normal_and_tangent": "Native exporter flips Y and normalizes vectors",
                "export_source_mesh": False, "level_of_detail": False,
                "collision": False, "bake_material_inputs": "Disabled"},
        "obj": {"exporter": "StaticMeshExporterOBJ", "position_and_normal": "(UE.X, UE.Z, UE.Y)",
                "uv": "(UE.U, 1-UE.V)", "units": "centimeters", "decimal_places": 6,
                "primary_file": "expanded triangle vertices, UV0, no normals",
                "internal_file": "indexed render LOD0 vertices, UV0 and normals",
                "tangents": "not represented by OBJ; use FBX for the preferred import"},
    }
    manifest_path = run / "assets.json"

    def publish():
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    publish()
    source_files = [item for entry in request["assets"] for item in entry["source_files"]]
    try:
        for original in source_files:
            if fingerprint(original["path"]) != original:
                raise RuntimeError("Source package changed before export: " + original["path"])
        for entry in request["assets"]:
            asset_path = entry["asset"]
            unreal.log("SOURCE_ASSET_BEGIN " + asset_path)
            # Scratch projects may not have asynchronously indexed this Engine
            # directory. Load the known package object directly, not via AssetRegistry.
            mesh = unreal.load_object(None, asset_path + '.' + asset_path.rsplit('/', 1)[-1])
            if not isinstance(mesh, unreal.StaticMesh):
                raise RuntimeError("Asset is not a StaticMesh: " + asset_path)
            lod_count = int(mesh.get_num_lods())
            if lod_count < 1:
                raise RuntimeError("StaticMesh has no render LODs: " + asset_path)
            lods = [{"lod": lod, "vertices": int(mesh.get_num_vertices(lod)),
                     "triangles": int(mesh.get_num_triangles(lod)),
                     "sections": int(mesh.get_num_sections(lod)),
                     "uv_channels": int(mesh.get_num_tex_coords(lod))}
                    for lod in range(lod_count)]
            if min(lods[0]["vertices"], lods[0]["triangles"], lods[0]["uv_channels"]) <= 0:
                raise RuntimeError("StaticMesh LOD0 is not exportable: " + asset_path)
            bounds = mesh.get_bounds()
            record = {"asset": asset_path, "object": mesh.get_path_name(), "source_files": entry["source_files"],
                      "lod_count": lod_count, "lods": lods,
                      "bounds_ue_cm": {"origin": vector(bounds.origin), "extent": vector(bounds.box_extent),
                                       "sphere_radius": float(bounds.sphere_radius)}, "exports": []}
            manifest["assets"].append(record)
            name = asset_path.rsplit("/", 1)[-1]
            destination = run / "Meshes" / name
            destination.mkdir(parents=True)
            options = unreal.FbxExportOption()
            for option, value in {"ascii": False, "force_front_x_axis": False,
                                  "export_source_mesh": False, "level_of_detail": False,
                                  "collision": False, "vertex_color": True,
                                  "bake_material_inputs": unreal.FbxMaterialBakeMode.DISABLED}.items():
                options.set_editor_property(option, value)
            fbx = destination / (name + ".fbx")
            export(mesh, fbx, unreal.StaticMeshExporterFBX(), options)
            export(mesh, destination / (name + ".obj"), unreal.StaticMeshExporterOBJ())
            internal = destination / (name + "_Internal.obj")
            if not internal.is_file():
                raise RuntimeError("UE OBJ exporter did not produce its indexed Internal file")
            counts = obj_counts(internal)
            expected = {"vertices": lods[0]["vertices"], "uvs": lods[0]["vertices"],
                        "normals": lods[0]["vertices"], "triangles": lods[0]["triangles"]}
            if counts != expected:
                raise RuntimeError("Indexed OBJ counts differ from native LOD0: {} != {}".format(counts, expected))
            for path in sorted(destination.rglob("*")):
                if not path.is_file():
                    continue
                output = fingerprint(path)
                output["relative_path"] = str(path.relative_to(run)).replace("\\", "/")
                if path.suffix.lower() == ".obj":
                    output["counts"] = obj_counts(path)
                record["exports"].append(output)
            record["preferred_geometry"] = str(fbx.relative_to(run)).replace("\\", "/")
            record["indexed_obj"] = str(internal.relative_to(run)).replace("\\", "/")
            publish()
            unreal.log("SOURCE_ASSET_END " + asset_path)
        manifest["status"] = "passed"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        raise
    finally:
        changed = []
        for original in source_files:
            try:
                if fingerprint(original["path"]) == original:
                    continue
            except OSError:
                pass
            changed.append(original["path"])
        manifest["source_files_changed"] = changed
        if changed:
            manifest["status"] = "failed"
        publish()
    if manifest["source_files_changed"]:
        raise RuntimeError("Source packages changed during export")
    unreal.log("SOURCE_ASSETS_PASS " + str(manifest_path))


if __name__ == "__main__":
    main()
