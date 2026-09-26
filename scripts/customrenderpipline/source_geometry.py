"""Preserve original UE vertex inputs alongside Falcor's Scene vertex packing."""
import hashlib
from pathlib import Path
import numpy as np


def prepare_rdc_sources(assets, manifest, output):
    assets, output = Path(assets), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    bindings = {}
    for instance, obj in enumerate(manifest["objects"]):
        asset = assets / obj["asset"]
        if hashlib.sha256(asset.read_bytes()).hexdigest() != obj["asset_sha256"]:
            raise ValueError("Original vertex asset checksum mismatch")
        with np.load(asset) as data:
            vertices = np.concatenate([data["positions_local_ue_cm"], data["normals_local"],
                                       data["unused_uv_placeholder"]], axis=1).astype("<f4")
            scene_positions = data["positions_falcor_m"].astype("<f4").tobytes()
            scene_normals = data["normals_falcor"].astype("<f4").tobytes()
        contents = vertices.tobytes()
        def publish(kind, payload):
            digest = hashlib.sha1(payload).hexdigest()
            path = output / (str(obj["eid"]) + "-" + digest + "-" + kind + ".bin")
            if path.exists():
                if path.read_bytes() != payload:
                    raise ValueError("Immutable source geometry contents changed")
            else:
                path.write_bytes(payload)
            return str(path.resolve()), digest
        path, digest = publish("vertices", contents)
        positions_path, positions_digest = publish("scene-positions", scene_positions)
        normals_path, normals_digest = publish("scene-normals", scene_normals)
        linear = np.array(obj["local_to_world_row_major"], dtype=np.float64)[:3, :3]
        normal = linear / np.linalg.norm(linear, axis=1)[:, None]
        bindings[str(instance)] = {"vertices": path, "vertex_count": len(vertices),
            "vertices_sha1": digest, "source_index": "texcoord_x",
            "scene_positions": positions_path, "scene_positions_sha1": positions_digest,
            "scene_normals": normals_path, "scene_normals_sha1": normals_digest,
            "linear_rows": linear.tolist(), "normal_rows": normal.tolist(),
            "primitive_high_cm": obj["primitive_position_high_cm"],
            "relative_translation_cm": obj["instance_relative_translation_cm"]}
    # The captured shaders do not read UVs. The Scene vertex now transports the
    # source index through texcoord.x so SceneBuilder remapping cannot corrupt it.
    # The source buffer restores the actual material UV (explicit unused zero).
    source = (assets / "captured_scene.pyscene").read_text()
    old_loop = 'for p, n in zip(arrays["positions_falcor_m"], arrays["normals_falcor"]):'
    old_uv = 'float2(0,0))'
    if source.count(old_loop) != 1 or source.count(old_uv) != 1:
        raise ValueError("Unexpected generated scene source-index insertion point")
    source = source.replace(old_loop, 'for source_id, (p, n) in enumerate(zip(arrays["positions_falcor_m"], arrays["normals_falcor"])):')
    source = source.replace(old_uv, 'float2(float(source_id),0))')
    scene_path = output / "captured_source_scene.pyscene"
    scene_path.write_text(source)
    return bindings, scene_path
