"""The GLB, read our way: the container, accessors, triangles, images, texels, UV probes, merged and double-sided faces. Part of the judge (judge.py has the overview)."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from . import judge

# ------------------------------------------------------------------ the GLB, read our way
def read_glb(path) -> tuple[dict, bytes]:
    b = Path(path).read_bytes()
    magic, _, _ = struct.unpack_from("<III", b, 0)
    if magic != 0x46546C67:
        raise ValueError(f"{path}: not a GLB")
    off, js, binc = 12, None, b""
    while off < len(b):
        n, kind = struct.unpack_from("<II", b, off)
        chunk = b[off + 8: off + 8 + n]
        if kind == 0x4E4F534A:
            js = json.loads(chunk)
        elif kind == 0x004E4942:
            binc = chunk
        off += 8 + n
    return js, binc


def accessor(js, binc, i) -> np.ndarray:
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    dt = np.dtype(judge._CT[a["componentType"]])
    nc = judge._NC[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0) or dt.itemsize * nc
    raw = np.frombuffer(binc, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * nc, offset=start)
    out = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * nc), (stride, 1)).copy()
    out = out.view(dt).reshape(a["count"], nc)
    if a.get("normalized") and dt != np.float32:
        out = out.astype(np.float32) / np.iinfo(dt).max
    return out if nc > 1 else out[:, 0]


def glb_triangles(js) -> dict:
    """Triangles per mesh name, counted once per node that draws the mesh (mode 4; indexed or not)."""
    per = {}
    for nd in js.get("nodes", []):
        if "mesh" not in nd:
            continue
        m = js["meshes"][nd["mesh"]]
        n = 0
        for p in m["primitives"]:
            if p.get("mode", 4) != 4:
                continue
            cnt = js["accessors"][p["indices"]]["count"] if "indices" in p else js["accessors"][p["attributes"]["POSITION"]]["count"]
            n += cnt // 3
        per[m.get("name", f"mesh{nd['mesh']}")] = per.get(m.get("name", f"mesh{nd['mesh']}"), 0) + n
    return per


def glb_image(js, binc, glb_path, ti):
    from PIL import Image
    import io
    img = js["images"][js["textures"][ti]["source"]]
    if "bufferView" in img:
        bv = js["bufferViews"][img["bufferView"]]
        data = binc[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        im = Image.open(io.BytesIO(data))
    else:
        im = Image.open(Path(glb_path).parent / img["uri"])
    return im, img.get("name") or Path(img.get("uri", "")).stem


def texel_at(arr: np.ndarray, uv) -> np.ndarray:
    """THE uv reader (bilinear, texel centres at half pixels). glTF texcoords: origin at the image's TOP-left, v down,
    so row = v * H. (trimesh flips them to v-up on load: never `1 - v` on trimesh's uvs; r70's mis-read.)"""
    H, W = arr.shape[:2]
    fx, fy = uv[:, 0] * W - 0.5, uv[:, 1] * H - 0.5
    i0, j0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = (fx - i0)[:, None], (fy - j0)[:, None]
    def g(i, j):
        return arr[np.clip(j, 0, H - 1), np.clip(i, 0, W - 1)]
    return ((1 - tx) * (1 - ty) * g(i0, j0) + tx * (1 - ty) * g(i0 + 1, j0) + (1 - tx) * ty * g(i0, j0 + 1)
            + tx * ty * g(i0 + 1, j0 + 1))


def _engine_sides(glb) -> dict:
    """Per mesh, per primitive: drawn two-sided? (doubleSided, or explicit back faces Blender will drop)."""
    js, binc = read_glb(glb)
    mf = glb_merged_faces(js, binc)
    return {k: [bool(x) or mf.get(k, {}).get("back", 0) > 0 for x in v] for k, v in glb_double_sided(js).items()}


def uv_probes(glb, n=40, seed=0, min_tris=500, skip=()) -> tuple[list, dict]:
    """Points on every textured mesh (>= min_tris): triangle centroids (glTF-local positions) on textured spots, the
    base colour read there OUR way (texel_at on the raw glTF uv), and the same read with v flipped (to prove the probe
    tells the two apart). Blender reads the same points its own way (blender_game's audit)."""
    js, binc = read_glb(glb)
    rng = np.random.default_rng(seed)
    probes, ours, flips, meshes, images = [], [], [], [], {}
    for m in js["meshes"]:
        for p in m["primitives"][:1]:
            mat = js["materials"][p["material"]] if "material" in p else {}
            bt = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
            if bt is None or "TEXCOORD_0" not in p["attributes"] or bt.get("texCoord", 0) != 0 or "indices" not in p:
                continue
            F = accessor(js, binc, p["indices"]).reshape(-1, 3)
            if len(F) < min_tris or m.get("name") in skip:
                continue
            X = accessor(js, binc, p["attributes"]["POSITION"]).astype(float)
            U = accessor(js, binc, p["attributes"]["TEXCOORD_0"]).astype(float)
            ti = bt["index"]
            si = js["textures"][ti]["source"]
            if si not in images:
                im, iname = glb_image(js, binc, glb, ti)
                images[si] = (np.asarray(im.convert("RGB"), np.float32) / 255.0, iname or f"Image_{si}")
            arr, iname = images[si]
            pick = rng.choice(len(F), size=min(len(F), 40 * n), replace=False)
            c, uv = X[F[pick]].mean(1), U[F[pick]].mean(1)
            var = np.abs(texel_at(arr, U[F[pick, 0]]) - texel_at(arr, U[F[pick, 1]])).sum(1)
            area = np.linalg.norm(np.cross(X[F[pick, 1]] - X[F[pick, 0]], X[F[pick, 2]] - X[F[pick, 0]]), axis=1)
            order = np.argsort(-(var * (area > np.percentile(area, 30))))[:n]
            ours += texel_at(arr, uv[order]).tolist()
            flips += texel_at(arr, np.c_[uv[order, 0], 1.0 - uv[order, 1]]).tolist()
            probes += [{"mesh": m.get("name"), "image": iname, "local": c[k].tolist()} for k in order]
            meshes.append(m.get("name"))
    if not probes:
        return [], {"error": "no textured mesh", "ours": [], "flipped": []}
    return probes, {"ours": ours, "flipped": flips, "mesh": ",".join(meshes), "image": "base colour"}


def glb_merged_faces(js, binc) -> dict:
    """mesh name -> {"back": triangles that repeat another's corners (an explicit back face: same vertices, reversed),
    "degenerate": triangles with a repeated corner}. Blender can't hold either (one face per vertex set), so its
    import drops them: the drawn count is the GLB's minus these, and a mesh with explicit back faces must then be drawn
    two-sided, or a judge render shows the cards half-sided."""
    out = {}
    for m in js["meshes"]:
        b = d = 0
        for p in m["primitives"]:
            if "indices" not in p or p.get("mode", 4) != 4:
                continue
            F = accessor(js, binc, p["indices"]).reshape(-1, 3).astype(np.int64)
            deg = (F[:, 0] == F[:, 1]) | (F[:, 1] == F[:, 2]) | (F[:, 0] == F[:, 2])
            S = np.sort(F[~deg], 1)
            _, cnt = np.unique(S, axis=0, return_counts=True)
            b += int((cnt - 1).sum())
            d += int(deg.sum())
        out[m.get("name")] = {"back": b, "degenerate": d}
    return out


def glb_double_sided(js) -> dict:
    """mesh name -> [doubleSided per primitive's material] (what an engine culls)."""
    out = {}
    for m in js["meshes"]:
        out[m.get("name")] = [bool(js["materials"][p["material"]].get("doubleSided", False)) if "material" in p else False
                              for p in m["primitives"]]
    return out
