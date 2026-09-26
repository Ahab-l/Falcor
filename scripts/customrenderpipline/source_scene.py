"""Source-authored UE mesh geometry and instance transforms, independent of Falcor.

The input is StaticMeshExporterOBJ's triangulated ``*_Internal.obj`` (LOD 0,
UV channel 0). EditorExporters.cpp exports position/normal as (UE.X, UE.Z,
UE.Y), UV as (UE.U, 1-UE.V), and keeps the render index buffer's winding.
Positions remain centimeters. This module restores UE UVs and converts to
Falcor local meters (UE.Y, UE.Z, -UE.X)/100. Normals only change basis.

OBJ -> Falcor is (OBJ.Z, OBJ.Y, -OBJ.X), a proper rotation, so triangle order
is preserved. The instance transform carries any negative-scale winding
change separately. No instance transform is baked into the shared mesh.

The exporter does not include section/material IDs, other UV channels, or
tangents. Obtain those separately from original source assets when needed;
this module does not infer them or read external OBJ material files.
"""
from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np


def _readonly(values, dtype=np.float64):
    result = np.array(values, dtype=dtype, order="C", copy=True)
    result.flags.writeable = False
    return result


@dataclass(frozen=True, eq=False)
class SourceMesh:
    """Immutable unified vertices; ``source_indices`` are zero-based OBJ v/vt/vn.

    Each distinct source corner tuple becomes one vertex, preserving seams and
    hard normals. Triangles index these vertices in source face order. Only
    vertices used by faces are included; the source indices retain provenance.
    Normal lengths are preserved from the exporter, including its quantization.
    """
    positions: np.ndarray
    normals: np.ndarray
    texcoords: np.ndarray
    triangles: np.ndarray
    source_indices: np.ndarray


def _numbers(tokens, count, line):
    if len(tokens) != count:
        raise ValueError("line {}: expected {} numeric components".format(line, count))
    try:
        values = tuple(float(token) for token in tokens)
    except ValueError as error:
        raise ValueError("line {}: invalid numeric component".format(line)) from error
    if not np.all(np.isfinite(values)):
        raise ValueError("line {}: components must be finite".format(line))
    return values


def _index(token, count, kind, line):
    if not re.fullmatch(r"[+-]?[0-9]+", token):
        raise ValueError("line {}: invalid {} index {!r}".format(line, kind, token))
    index = int(token)
    resolved = index - 1 if index > 0 else count + index
    if index == 0 or not 0 <= resolved < count:
        raise ValueError("line {}: {} index {} outside {} preceding entries".format(line, kind, index, count))
    return resolved


def parse_ue_internal_obj(text):
    """Parse source OBJ text to a shared mesh in Falcor local coordinates.

    Faces must be triangles with explicit position/UV/normal indices. Both
    positive and negative indices refer to entries already declared at the
    face. Unsupported geometry is rejected instead of triangulated/repaired.
    Comments and the non-geometric o/g/s records are accepted.
    """
    if not isinstance(text, str):
        raise TypeError("OBJ input must be text")
    positions, texcoords, normals = [], [], []
    unique, corners, triangles = {}, [], []
    for line, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        tokens = raw.partition("#")[0].split()
        if not tokens:
            continue
        kind, values = tokens[0], tokens[1:]
        if kind == "v":
            positions.append(_numbers(values, 3, line))
        elif kind == "vt":
            texcoords.append(_numbers(values, 2, line))
        elif kind == "vn":
            normal = _numbers(values, 3, line)
            if not any(normal):
                raise ValueError("line {}: normal must be nonzero".format(line))
            normals.append(normal)
        elif kind == "f":
            if len(values) != 3:
                raise ValueError("line {}: expected a triangle".format(line))
            triangle = []
            for value in values:
                fields = value.split("/")
                if len(fields) != 3:
                    raise ValueError("line {}: expected position/UV/normal corner".format(line))
                corner = tuple(_index(token, count, name, line) for token, count, name in
                               zip(fields, (len(positions), len(texcoords), len(normals)), ("position", "UV", "normal")))
                if corner not in unique:
                    unique[corner] = len(corners)
                    corners.append(corner)
                triangle.append(unique[corner])
            triangles.append(triangle)
        elif kind not in ("o", "g", "s"):
            raise ValueError("line {}: unsupported OBJ record {!r}".format(line, kind))
    if not triangles:
        raise ValueError("OBJ contains no triangles")
    source_indices = np.asarray(corners, dtype=np.int64)
    local_positions = np.asarray(positions, dtype=np.float64)[source_indices[:, 0]][:, [2, 1, 0]].copy()
    local_positions[:, 2] *= -1
    local_positions /= 100
    local_normals = np.asarray(normals, dtype=np.float64)[source_indices[:, 2]][:, [2, 1, 0]].copy()
    local_normals[:, 2] *= -1
    source_uvs = np.asarray(texcoords, dtype=np.float64)[source_indices[:, 1]].copy()
    source_uvs[:, 1] = 1 - source_uvs[:, 1]
    return SourceMesh(_readonly(local_positions), _readonly(local_normals), _readonly(source_uvs),
                      _readonly(triangles, np.uint32), _readonly(source_indices, np.int64))


def load_ue_internal_obj(path):
    """Read one original-source OBJ; never resolve referenced files."""
    return parse_ue_internal_obj(Path(path).read_text(encoding="utf-8-sig"))


def _vector(value, name):
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3,) or not np.all(np.isfinite(result)):
        raise ValueError("{} must contain three finite numbers".format(name))
    return result


def _vectors(value, name):
    result = np.asarray(value, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 3 or not np.all(np.isfinite(result)):
        raise ValueError("{} must have shape (N, 3) and finite values".format(name))
    return result


@dataclass(frozen=True, eq=False)
class InstanceTransform:
    """Instance matrices use column vectors: world = matrix @ [local, 1].

    ``normal_matrix`` is inverse-transpose of the linear 3x3 transform.
    ``reverses_winding`` requires the renderer to invert its front-face rule
    for that instance (or reverse indices when explicitly baking geometry).
    Matrices are immutable; methods return new arrays without changing mesh.
    """
    matrix: np.ndarray
    normal_matrix: np.ndarray
    reverses_winding: bool

    def transform_positions(self, positions):
        positions = _vectors(positions, "positions")
        return positions @ self.matrix[:3, :3].T + self.matrix[:3, 3]

    def transform_normals(self, normals):
        normals = _vectors(normals, "normals")
        transformed = normals @ self.normal_matrix.T
        lengths = np.linalg.norm(transformed, axis=1)
        if np.any(lengths == 0) or not np.all(np.isfinite(lengths)):
            raise ValueError("transformed normals must have finite nonzero length")
        return transformed / lengths[:, None]


def ue_instance_transform(translation_cm=(0, 0, 0), rotation_deg=(0, 0, 0), scale=(1, 1, 1)):
    """Convert one UE instance's scale -> Rotator -> translation to Falcor.

    rotation_deg is (pitch, yaw, roll), following UE RotationTranslationMatrix:
    yaw rotates +X toward +Y, pitch +X toward +Z, roll +Y toward -Z.
    The returned matrix acts on already converted Falcor local meters.
    Zero scale is rejected because no inverse-transpose normal map exists.
    """
    translation = _vector(translation_cm, "translation_cm")
    angles = np.deg2rad(_vector(rotation_deg, "rotation_deg"))
    scaling = _vector(scale, "scale")
    if np.any(scaling == 0):
        raise ValueError("scale must be nonzero on every axis")
    sp, sy, sr = np.sin(angles)
    cp, cy, cr = np.cos(angles)
    # Columns are UE's rotated X/Y/Z axes; UE's source matrix uses row vectors.
    rotation = np.array([[cp * cy, sr * sp * cy - cr * sy, -(cr * sp * cy + sr * sy)],
                         [cp * sy, sr * sp * sy + cr * cy, cy * sr - cr * sp * sy],
                         [sp, -sr * cp, cr * cp]], dtype=np.float64)
    basis = np.array([[0, 1, 0], [0, 0, 1], [-1, 0, 0]], dtype=np.float64)
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = basis @ (rotation * scaling[None, :]) @ basis.T
    matrix[:3, 3] = basis @ translation / 100
    # inverse-transpose(B R S B^-1) = B R S^-1 B^-1 for orthogonal B and R.
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        normal_matrix = basis @ (rotation / scaling[None, :]) @ basis.T
    if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(normal_matrix)):
        raise ValueError("instance transform must have finite matrices")
    return InstanceTransform(_readonly(matrix), _readonly(normal_matrix), bool(np.count_nonzero(scaling < 0) % 2))
