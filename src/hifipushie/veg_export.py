"""A plant as a GLB (first export: one LOD; LODs, wind data and season variants are stage 4).

Two meshes: `wood` (branch tubes; bark base colour = the bark's colour x its tiling albedo, normal and roughness maps,
REPEAT sampling on the branch uv) and `foliage` (every twig's card, realised into one mesh; the twig atlas as base
colour with alpha MASK, double sided; COLOR_0 = a per-twig tint). glTF axes (Y up: x, z, -y), uv v flipped. Textures
are embedded. extras carry the plant's name, stats and counts.
"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

import numpy as np

from . import veg_bark, veg_leaf, veg_mesh, vegetation


def _normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    ln = np.linalg.norm(N, axis=1, keepdims=True)
    return np.where(ln > 1e-12, N / np.maximum(ln, 1e-12), [0, 0, 1.0])


def _png(a) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(np.clip(np.asarray(a) * 255 + 0.5, 0, 255).astype(np.uint8)).save(b, "PNG")
    return b.getvalue()


def _yup(v):
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1)


def foliage_mesh(tree: dict, at: dict) -> dict:
    """Every twig's card placed on the tree, as one mesh: V, F, uv, tint (per vertex)."""
    tw = veg_leaf.place(tree)
    if not len(tw["pos"]):
        return {"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "uv": np.zeros((0, 2)), "tint": np.zeros(0)}
    nv = len(at["cards"])
    var = (vegetation._child(tw["key"], 11) % np.uint64(nv)).astype(int)
    tint = 0.75 + 0.5 * vegetation._u(tw["key"], 77)
    Vs, Fs, Us, Ts = [], [], [], []
    base = 0
    for i, c in enumerate(at["cards"]):
        sel = np.flatnonzero(var == i)
        if not len(sel):
            continue
        k = len(c["V"])
        V = np.einsum("nij,kj->nki", tw["frame"][sel], c["V"]) * tw["scale"][sel][:, None, None] + tw["pos"][sel][:, None, :]
        Vs.append(V.reshape(-1, 3))
        Fs.append((c["F"][None] + (base + np.arange(len(sel)) * k)[:, None, None]).reshape(-1, 3))
        Us.append(np.tile(c["uv"], (len(sel), 1)))
        Ts.append(np.repeat(tint[sel], k))
        base += len(sel) * k
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "uv": np.vstack(Us), "tint": np.concatenate(Ts)}


def write_glb(tree: dict, path: str, name: str = "plant") -> dict:
    """Write the plant to `path` (.glb). Returns counts: triangles per mesh, texture sizes, bytes."""
    s = tree["spec"]
    bark = s.get("bark") or {}
    bm = veg_bark.bark_maps(bark.get("kind", "furrowed"), 256, seed=int(s.get("seed", 1)))
    W = veg_mesh.tubes(tree, tile=bm["tile"])
    has_leaves = len(veg_leaf.place(tree)["pos"]) > 0
    at = veg_leaf.atlas(s["leaves"], bark.get("twig_color") or [0.45, 0.4, 0.35]) if has_leaves else None
    L = foliage_mesh(tree, at) if at else None
    buf = bytearray()
    views, accessors, images, textures, materials, meshes, nodes = [], [], [], [], [], [], []

    def view(data: bytes, target=None):
        while len(buf) % 4:
            buf.append(0)
        v = {"buffer": 0, "byteOffset": len(buf), "byteLength": len(data)}
        if target:
            v["target"] = target
        buf.extend(data)
        views.append(v)
        return len(views) - 1

    def acc(a, kind, comp, target, minmax=False, normalized=False):
        a = np.ascontiguousarray(a)
        d = {"bufferView": view(a.tobytes(), target), "componentType": comp, "count": int(len(a)), "type": kind}
        if minmax:
            d["min"], d["max"] = a.min(0).astype(float).tolist(), a.max(0).astype(float).tolist()
        if normalized:
            d["normalized"] = True
        accessors.append(d)
        return len(accessors) - 1

    def tex(png: bytes, repeat: bool):
        images.append({"bufferView": view(png), "mimeType": "image/png"})
        textures.append({"source": len(images) - 1, "sampler": 0 if repeat else 1})
        return len(textures) - 1

    def prim(V, F, uv, material, colour=None):
        N = _normals(V, F)
        at_ = {"POSITION": acc(_yup(V).astype(np.float32), "VEC3", 5126, 34962, minmax=True),
               "NORMAL": acc(_yup(N).astype(np.float32), "VEC3", 5126, 34962),
               "TEXCOORD_0": acc(np.c_[uv[:, 0], 1 - uv[:, 1]].astype(np.float32), "VEC2", 5126, 34962)}
        if colour is not None:
            c = np.clip(colour, 0, 1)
            at_["COLOR_0"] = acc(np.c_[c, c, c, np.ones(len(c))].astype(np.float32), "VEC4", 5126, 34962)
        return {"attributes": at_, "indices": acc(F.astype(np.uint32).ravel(), "SCALAR", 5125, 34963), "material": material}

    col = np.asarray(bark.get("color", [0.5, 0.45, 0.4]), float)
    base = np.clip(bm["albedo"][..., None] * col[None, None], 0, 1)  # (sRGB colour x a multiplier: near enough)
    orm = np.stack([np.ones_like(bm["rough"]), bm["rough"], np.zeros_like(bm["rough"])], -1)
    materials.append({"name": "bark", "pbrMetallicRoughness": {
        "baseColorTexture": {"index": tex(_png(base), True)},
        "metallicRoughnessTexture": {"index": tex(_png(orm), True)}},
        "normalTexture": {"index": tex(_png(bm["normal"]), True)}})
    meshes.append({"name": "wood", "primitives": [prim(W["V"], W["F"], W["uv"], 0)]})
    nodes.append({"name": "wood", "mesh": 0})
    counts = {"wood_triangles": int(len(W["F"])), "foliage_triangles": 0}
    if L is not None and len(L["F"]):
        m = at["mask"]
        orm = np.stack([np.ones_like(m[..., 1]), m[..., 1], np.zeros_like(m[..., 1])], -1)
        materials.append({"name": "foliage", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex(_png(at["color"]), False)},
            "metallicRoughnessTexture": {"index": tex(_png(orm), False)}},
            "normalTexture": {"index": tex(_png(at["normal"]), False)},
            "alphaMode": "MASK", "alphaCutoff": 0.4, "doubleSided": True,
            "extras": {"mask_texture": "R = light comes through (leaf), G = roughness, B = shade",
                       "card_fill": round(at["fill"], 3)}})
        mask_tex = tex(_png(at["mask"]), False)
        materials[-1]["extras"]["mask_texture_index"] = mask_tex
        meshes.append({"name": "foliage", "primitives": [prim(L["V"], L["F"], L["uv"], 1, L["tint"])]})
        nodes.append({"name": "foliage", "mesh": 1})
        counts["foliage_triangles"] = int(len(L["F"]))
        counts["atlas_px"] = int(at["color"].shape[0])
    while len(buf) % 4:
        buf.append(0)
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation"},
            "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
            "materials": materials, "textures": textures, "images": images,
            "samplers": [{"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987},
                         {"wrapS": 33071, "wrapT": 33071, "magFilter": 9729, "minFilter": 9987}],
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(buf)}],
            "extras": {"hifipushie_plant": {"name": name, "species": s.get("species"), "age": s.get("age"),
                                            "height_m": round(tree["height"], 2), "stats": tree["stats"], **counts,
                                            "bark_tile_m": bm["tile"], "lods": 1, "wind": None}}}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(buf)))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(buf), b"BIN\0"))
        f.write(bytes(buf))
    counts["bytes"] = out.stat().st_size
    counts["path"] = str(out)
    return counts
