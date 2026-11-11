"""Map seams: the tiles' baked maps compared along shared borders. Part of the terrain mesh (terrain_mesh.py has
the overview)."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from .terrain_gltf import _from_gltf, read_glb
from .terrain_tile_finish import _unit_rows
from .terrain_tile_mesh import _boundary_edges

def read_glb_images(path, n=None):
    """The images embedded in a GLB, decoded (float arrays 0..1, rows top first), in texture order (the first `n`)."""
    import io
    from PIL import Image
    b = Path(path).read_bytes()
    jl = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jl])
    binb = b[28 + jl:]
    out = []
    for im in doc.get("images", [])[:n]:
        if "bufferView" not in im:  # (a file beside the GLB: the detail swatches)
            out.append(None)
            continue
        v = doc["bufferViews"][im["bufferView"]]
        a = np.asarray(Image.open(io.BytesIO(binb[v["byteOffset"]:v["byteOffset"] + v["byteLength"]])), float)
        out.append(a / 255.0)
    return out


def _bilinear(img, uv):
    H, W = img.shape[:2]
    x = np.clip(uv[:, 0] * W - 0.5, 0, W - 1.001)
    y = np.clip(uv[:, 1] * H - 0.5, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy
            + img[y0 + 1, x0 + 1] * fx * fy)


def _map_side(out, L, ax, lim):
    """Along a tile's border plane: points on its border edges (a quarter, half, three quarters along each) with what
    its maps say there: the normal decoded to world axes (through the tile's NORMAL/TANGENT: MikkTSpace-style, as
    engines recompute them), base colour, occlusion, roughness, the height map in metres and the layer weights.
    Returns (points (n, 3), {channel: (n, k)})."""
    return _map_sides(out, L, [(ax, lim)])[ax, lim]


def _map_files(L):
    mp = L.get("maps") or {}
    return [L["file"]] + ([mp["height"]] if mp.get("height") else []) + list(mp.get("weights", []))


def _map_sides(out, L, planes):
    """`_map_side` on several border planes of one tile LOD, its maps decoded once: {(ax, lim): (points, channels)}."""
    from PIL import Image
    path = out / L["file"]
    tr, prims = read_glb(path)
    p = prims[0]
    none = {pl: (np.zeros((0, 3)), {}) for pl in planes}
    if "TEXCOORD_0" not in p:
        return none
    imgs = read_glb_images(path, 3)
    if len(imgs) < 3:
        return none
    mp = L.get("maps") or {}
    hi = np.asarray(Image.open(out / mp["height"]), float) / 65535.0 if mp.get("height") else None
    wimgs = [np.asarray(Image.open(out / fn), float) / 255.0 for fn in mp.get("weights", [])]
    return {(ax, lim): _map_plane(p, tr, imgs, hi, wimgs, mp, ax, lim) for ax, lim in planes}


def _map_plane(p, tr, imgs, hi, wimgs, mp, ax, lim):
    origin = _from_gltf(tr[None])[0]
    P = _from_gltf(p["POSITION"].astype(np.float64)) + origin
    N = _from_gltf(p["NORMAL"].astype(np.float64))
    T = _from_gltf(p["TANGENT"][:, :3].astype(np.float64))
    w = p["TANGENT"][:, 3].astype(np.float64)
    uv = p["TEXCOORD_0"].astype(np.float64)
    be = _boundary_edges(p["indices"])
    be = be[(P[be[:, 0], ax] == lim) & (P[be[:, 1], ax] == lim)]
    if not len(be):
        return np.zeros((0, 3)), {}
    # (each edge's ends in a canonical order, so both tiles sample the same points)
    swap = np.array([tuple(P[a]) > tuple(P[b]) for a, b in be])
    a_, b_ = np.where(swap, be[:, 1], be[:, 0]), np.where(swap, be[:, 0], be[:, 1])
    t = np.repeat(np.array([[0.25, 0.5, 0.75]]), len(be), 0).ravel()[:, None]
    a_, b_ = np.repeat(a_, 3), np.repeat(b_, 3)
    lerp = lambda A: A[a_] * (1 - t) + A[b_] * t
    X = lerp(P)
    Nl = _unit_rows(lerp(N))
    Tl = lerp(T)
    Tl = _unit_rows(Tl - Nl * (Tl * Nl).sum(1, keepdims=True))
    Bl = np.cross(Nl, Tl) * np.sign(w[a_])[:, None]
    q = lerp(uv)
    tn = _bilinear(imgs[2], q)[:, :3] * 2 - 1
    ch = {"normal": _unit_rows(tn[:, :1] * Tl + tn[:, 1:2] * Bl + tn[:, 2:3] * Nl),
          "colour": _bilinear(imgs[0], q)[:, :3], "orm": _bilinear(imgs[1], q)[:, :2]}
    if hi is not None:
        ch["height_m"] = ((_bilinear(hi[..., None], q)[:, 0] - 0.5) * 2 * mp["height_range_m"])[:, None]
    for g, w in enumerate(wimgs):
        ch[f"weights{g}"] = _bilinear(w, q)
    return X, ch


def _job_sides(a):
    out, L, planes = a
    return _map_sides(out, L, planes)


def _side_pool(todo):
    """`_map_sides` of each (key, files key, args) across a fork pool (decoding the maps was 80% of the checks)."""
    from . import resources
    if len(todo) <= 2:
        return [_job_sides(t[2]) for t in todo]
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    ex = ProcessPoolExecutor(max_workers=resources.workers(1.0, cap=16, jobs=len(todo)),
                             mp_context=multiprocessing.get_context("fork"), initializer=resources._worker_init)
    with resources.guarded(ex, "map seams") as ex:
        return list(ex.map(_job_sides, [t[2] for t in todo], chunksize=2))


def map_seams(out, tiles, lods, kind="tiles", memo=None):
    """Baked maps across shared tile borders: every channel decoded from both tiles at the same border points (same
    LOD) and, for mixed LODs (0 against the coarsest), at the nearest point of the other tile's border within 0.6 m.
    Per pair: normals (deg), colour, occlusion, roughness, weights (0..1) and height (m) differences, p50/p95.
    Each tile LOD's maps are decoded once for all its borders, across a pool; `memo` (terrain_incremental.Memo)
    keeps each side's samples by its files' content, so an incremental export decodes only the tiles it rewrote."""
    from scipy.spatial import cKDTree
    from . import terrain_incremental as inc
    res = {}
    by = {(e["i"], e["j"]): e for e in tiles}
    pairs = [(k, k) for k in range(lods)] + ([(0, lods - 1)] if lods > 1 else [])
    need = {}
    for ka, kb in pairs:
        for (i, j), e in by.items():
            for di, dj, ax in ((1, 0, 0), (0, 1, 1)):
                o = by.get((i + di, j + dj))
                if o is None or not e["lods"][ka] or not o["lods"][kb]:
                    continue
                lim = e["max"][ax]
                need.setdefault((i, j, ka), set()).add((ax, lim))
                need.setdefault((i + di, j + dj, kb), set()).add((ax, lim))
    cache, todo = {}, []
    for (i, j, k), planes in need.items():
        L = by[i, j]["lods"][k]
        fk = inc.files_key(out, _map_files(L)) if memo is not None else None
        miss = []
        for pl in sorted(planes):
            got = memo.get(inc._h("map side", fk, pl)) if memo is not None else None
            if got is None:
                miss.append(pl)
            else:
                cache[(i, j, k) + pl] = got
        if miss:
            todo.append(((i, j, k), fk, (out, L, miss)))
    if todo:
        got_all = _side_pool(todo)
        for ((i, j, k), fk, _), got in zip(todo, got_all):
            for pl, v in got.items():
                cache[(i, j, k) + pl] = v
                if memo is not None:
                    memo.put(inc._h("map side", fk, pl), v)

    def side(e, k, ax, lim):
        return cache[e["i"], e["j"], k, ax, lim]

    for ka, kb in pairs:
        diffs, per = {}, {}
        for (i, j), e in by.items():
            for di, dj, ax in ((1, 0, 0), (0, 1, 1)):
                o = by.get((i + di, j + dj))
                if o is None or not e["lods"][ka] or not o["lods"][kb]:
                    continue
                lim = e["max"][ax]
                XA, A = side(e, ka, ax, lim)
                XB, B = side(o, kb, ax, lim)
                if not len(XA) or not len(XB):
                    continue
                d, nb = cKDTree(XB).query(XA)
                m = d < (1e-6 if ka == kb else 0.6)
                if not m.any():
                    continue
                for c in sorted(A.keys() & B.keys()):  # (sorted: a set of names iterates in hash order, run to run)
                    va, vb = A[c][m], B[c][nb[m]]
                    if c == "normal":
                        v = np.degrees(np.arccos(np.clip((va * vb).sum(1), -1, 1)))
                    else:
                        v = np.abs(va - vb).max(1)
                    diffs.setdefault(c, []).append(v)
                    if len(v) >= 20:  # (which border: a failure names its tiles)
                        per.setdefault(c, []).append((round(float(np.percentile(v, 95)), 3), [i, j], [i + di, j + dj]))
        if not diffs:
            continue
        name = f"lod{ka}" if ka == kb else f"lod{ka}_vs_lod{kb}"
        lim = MAP_SEAM[min(max(ka, kb), len(MAP_SEAM) - 1)]
        r = {"points": int(sum(len(v) for v in diffs["normal"]))}
        for c, vs in diffs.items():
            v = np.concatenate(vs)
            r[c] = [round(float(np.percentile(v, 50)), 3), round(float(np.percentile(v, 95)), 3)]
        bad = []
        if r["normal"][0] > lim["normal"][0] or r["normal"][1] > lim["normal"][1]:
            bad.append("normal")
        # (mixed LODs: height is measured from each LOD's own low poly, so it differs by design; occlusion is
        # interpolated over triangles of different sizes and gets a looser limit)
        for c in ("colour", "orm") + (("height_m",) if ka == kb else ()) + tuple(c for c in r if c.startswith("weights")):
            if c in r and r[c][1] > lim[c if c in lim else "weights"] * (1.0 if ka == kb or c != "orm" else 1.4):
                bad.append(c)
        r["ok"] = not bad
        r["bad"] = bad
        if bad:  # the borders it is worst on, per failing channel: [p95, tile, tile]
            r["worst"] = {c: [list(w) for w in sorted(per.get(c, []), reverse=True)[:WORST_BORDERS]] for c in bad}
        res[name] = r
    return res


WORST_BORDERS = 4  # borders listed per failing map channel


# the same border point decoded from both tiles' maps (each samples its own texels, 8-bit, bilinear): normals p50 and
# p95 (deg) and colour p95 (0..1) allowed, per LOD. A seam would shift the median; a few aliased texels at sharp
# detail don't. LOD 2 (0.4 m texels on a mesh 0.5 m off the rock) is looser: where its triangles stray far from the
# rock's normal the map can't bend past its surface (z >= 0.02) and the two sides clamp differently
MAP_SEAM = [
    {"normal": (3.0, 15.0), "colour": 0.08, "orm": 0.08, "height_m": 0.03, "weights": 0.1},
    {"normal": (3.0, 15.0), "colour": 0.12, "orm": 0.1, "height_m": 0.06, "weights": 0.15},
    {"normal": (6.0, 50.0), "colour": 0.2, "orm": 0.15, "height_m": 0.15, "weights": 0.25},
]
