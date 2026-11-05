"""Proof sheet: a posed look (facepose.pose) beside the exported GLB set to the same face-shape weights.

uv run python examples/face_pose_match.py <model> <glb> <out.png> '<weights json>'

Both are drawn by the same clay renderer from the same cameras (the face's mouth, front / three-quarter / side), the
GLB's morph targets applied in numpy (base + sum of weight x target, Blender axes). Numbers: for every GLB vertex near
the mouth, its distance to the nearest posed-look vertex, posed and at the neutral (the neutral's is the export's
decimation alone: the floor a match can reach). Also prints the GLB's default weights (mesh.weights: the rest)."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from hifipushie import asset, facepose, faceshapes, render, store

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NK = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def glb_meshes(path: Path) -> dict:
    """{mesh name: {"V" (Blender axes), "F", "names", "weights", "targets" (Blender axes)}}."""
    raw = path.read_bytes()
    jl = struct.unpack("<I", raw[12:16])[0]
    doc = json.loads(raw[20:20 + jl])
    binp = raw[20 + jl + 8:]
    sparse = faceshapes.read_glb(path)

    def acc(i):
        a = doc["accessors"][i]
        bv = doc["bufferViews"][a["bufferView"]]
        k = NK[a["type"]]
        o = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(binp, CT[a["componentType"]], a["count"] * k, o).reshape(a["count"], k)
    out = {}
    for m in doc["meshes"]:
        pr = m["primitives"][0]
        V = acc(pr["attributes"]["POSITION"]).astype(np.float64) @ asset._Z_TO_Y
        F = acc(pr["indices"]).reshape(-1, 3).astype(np.int64)
        s = sparse[m["name"]]
        out[m["name"]] = {"V": V, "F": F, "names": s["names"], "weights": s["weights"],
                          "targets": [t["POSITION"].astype(np.float64) @ asset._Z_TO_Y for t in s["targets"]]}
    return out


def glb_posed(ms: dict, w: dict) -> dict:
    return {n: m["V"] + sum((w.get(k, 0.0) * t for k, t in zip(m["names"], m["targets"])), 0.0) for n, m in ms.items()}


def main(model: str, glb: str, out: str, weights: dict):
    spec = store.load(model)
    face = faceshapes.face_of(spec)
    ms = glb_meshes(Path(glb))
    w = facepose.weights(weights)
    sheet_rows, numbers = [], {}
    for tag, wt in (("posed", w), ("neutral", {})):
        path, info = facepose.pose(model, wt)
        with np.load(path) as z:
            X, F, P, pn = z["verts"].astype(np.float64), z["faces"], z["part"], [str(n) for n in z["part_names"]]
        G = glb_posed(ms, faceshapes.playback(wt) if wt else {})
        rows = []
        for i, name in enumerate(pn):
            if name not in G:
                continue
            g = G[name]
            near = np.linalg.norm(g - face.M, axis=1) < 1.5 * face.width
            if not near.any():
                continue
            d, _ = cKDTree(X[P == i]).query(g[near])
            rows.append((name, int(near.sum()), float(np.median(d) * 1000), float(np.percentile(d, 95) * 1000),
                         float(d.max() * 1000)))
        numbers[tag] = rows
        if tag != "posed":
            continue
        # the GLB posed, as a mesh the clay renderer draws (part colours as the look's)
        Vs, Fs, Ps = [], [], []
        for i, name in enumerate(pn):
            if name in G:
                Fs.append(ms[name]["F"] + sum(len(v) for v in Vs))
                Vs.append(G[name])
                Ps.append(np.full(len(G[name]), i, np.int16))
        GV, GF, GP = np.concatenate(Vs), np.concatenate(Fs), np.concatenate(Ps)
        defs = spec.get("parts") or {}
        gp = Path(path).with_name("glb_posed.npz")
        np.savez(gp, verts=GV.astype(np.float32), faces=GF, normals=faceshapes.vertex_normals(GV, GF).astype(np.float32),
                 part=GP, part_names=np.array(pn),
                 part_colors=np.concatenate([np.tile(store.part_colour(n, defs, i), ((GP == i).sum(), 1))
                                             for i, n in enumerate(pn)]))
        views = ["front", "three_quarter", "side"]
        frames = render.view_frames(store.extent(model), views, face.M.tolist(), 4.0)
        a = render.render_views(path, frames, 420, "clay_studio.exr")
        b = render.render_views(gp, frames, 420, "clay_studio.exr")
        sheet_rows = list(zip(a, b))
    W, H = 420, 420
    img = Image.new("RGB", (2 * W + 30, len(sheet_rows) * (H + 24) + 210), (28, 30, 34))
    dr = ImageDraw.Draw(img)
    dr.text((10, 4), "posed look (no export)", fill=(230, 230, 230))
    dr.text((W + 30, 4), "exported GLB, same weights", fill=(230, 230, 230))
    for r, (pa, pb) in enumerate(sheet_rows):
        img.paste(pa.convert("RGB").resize((W, H)), (0, 20 + r * (H + 24)))
        img.paste(pb.convert("RGB").resize((W, H)), (W + 30, 20 + r * (H + 24)))
    y = 20 + len(sheet_rows) * (H + 24)
    dr.text((10, y), "weights: " + ", ".join(f"{k} {v:.2f}" for k, v in w.items()), fill=(230, 230, 230))
    y += 18
    for tag, rows in numbers.items():
        for name, n, med, p95, mx in rows:
            dr.text((10, y), f"{tag:8s} {name:7s} {n:6d} GLB verts by the mouth -> posed look: median {med:.2f} mm, "
                    f"p95 {p95:.2f}, max {mx:.2f}", fill=(230, 230, 230))
            y += 16
    rest = {n: dict(zip(m["names"], m["weights"])) for n, m in ms.items() if m["names"]}
    dr.text((10, y), "GLB default weights (rest): " + "; ".join(
        f"{n}: " + ", ".join(f"{k} {v:.2f}" for k, v in r.items() if v) for n, r in rest.items()), fill=(230, 230, 230))
    img.save(out)
    print(json.dumps({"numbers": numbers, "rest": rest}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
