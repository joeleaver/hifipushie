"""The atlas: the head's UVs, the atlas itself, interpolation at texels, the image, blur. Part of the skin projection (skin_project.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_project

def _faces(tpl: dict) -> list:
    L, S = np.asarray(tpl["L"]), np.asarray(tpl["S"]) if "S" in tpl else None
    if S is None:
        return [L[i:i + 4] for i in range(0, len(L), 4)]
    out, o = [], 0
    for n in S:
        out.append(L[o:o + int(n)])
        o += int(n)
    return out


def vertex_uv(tpl: dict) -> tuple:
    """(candidates per template vertex: list of (k, 2) arrays, asset vertex index per template vertex or -1): the one
    mesh's atlas coordinates of a built template's vertices. A vertex on the atlas' cut has more than one."""
    from . import onemesh
    a = onemesh.asset()
    nraw = int(a["n_raw_v"])
    fid = np.asarray(tpl["fid"], int)
    skin = np.asarray(a["part"]) == 0
    cand: dict = {}
    for f, q in zip(np.asarray(a["faces"])[skin], np.asarray(a["uv"], float)[skin]):
        for v, t in zip(f, q):
            c = cand.setdefault(int(v), [])
            if not any(abs(t[0] - x[0]) + abs(t[1] - x[1]) < 1e-6 for x in c):
                c.append(t)
    out = [np.asarray(cand[int(i)], float) if int(i) in cand else None for i in fid]
    new = np.flatnonzero(fid >= nraw)
    if len(new):  # the lids' extra edge loops (onemesh_head._with_loops): each new vertex is the mean of its parents
        from . import gnmloops
        par = np.asarray(gnmloops.plan()["parents"], int)
        gid = np.asarray(a["gnm_id"], int)
        row = np.full(gnmloops.N_RAW + len(par), -1)
        old = np.flatnonzero((fid < nraw) & (fid >= 0))
        g = gid[fid[old]]
        row[g[g >= 0]] = old[g >= 0]
        row[gnmloops.N_RAW + (fid[new] - nraw)] = new
        for k in np.argsort(fid[new]):
            i = new[k]
            p = row[par[fid[i] - nraw]]
            if (p >= 0).all() and all(out[j] is not None for j in p):
                out[i] = np.mean([out[j][0] for j in p], 0)[None]
    return out, fid


def mesh_uv(base: dict) -> dict:
    """The head's mesh in the atlas, no raster: {"V" (template vertices at rest), "T" (the head's triangles), "uvT"
    (their atlas coordinates), "other" (the template's remaining triangles: body, mouth sock), "gid", "fid", "fade",
    "head", "is_new", "state"}."""
    from . import humanfit, onemesh
    key = hashlib.sha1(json.dumps([base, skin_project.VERSION, "lookup3"], sort_keys=True, default=str).encode()).hexdigest()
    if skin_project._MESH.get("key") == key:
        return skin_project._MESH["m"]
    st = humanfit.state(base)
    tpl = st["tpl"]
    a = onemesh.asset()
    V = np.asarray(tpl["P"], float)
    cand, fid = vertex_uv(tpl)
    nraw = int(a["n_raw_v"])
    gid = np.where((fid >= 0) & (fid < nraw), np.asarray(a["gnm_id"], int)[np.clip(fid, 0, nraw - 1)], -1)
    fade = np.where((fid >= 0) & (fid < nraw), np.asarray(a["fade"], float)[np.clip(fid, 0, nraw - 1)], 1.0)
    is_new = fid >= nraw
    headv = (gid >= 0) | is_new
    T, uvT, other = [], [], []
    for f in _faces(tpl):
        f = np.asarray(f, int)
        tri = [(f[0], f[j], f[j + 1]) for j in range(1, len(f) - 1)]
        if not headv[f].all() or any(cand[i] is None for i in f):
            other += tri
            continue
        one = [cand[i][0] for i in f if len(cand[i]) == 1]
        ref = np.mean(one, 0) if one else np.mean([c.mean(0) for c in (cand[i] for i in f)], 0)
        uv = np.array([cand[i][np.argmin(np.abs(cand[i] - ref).sum(1))] for i in f])
        if np.ptp(uv, 0).max() > 0.05:   # a face across the cut with no single-valued corner: not drawn
            other += tri
            continue
        for j in range(1, len(f) - 1):
            T.append((f[0], f[j], f[j + 1]))
            uvT.append((uv[0], uv[j], uv[j + 1]))
    m = {"V": V, "T": np.asarray(T, int), "uvT": np.asarray(uvT, float), "other": np.asarray(other, int).reshape(-1, 3), "gid": gid, "fid": fid,
         "fade": fade, "head": headv, "is_new": is_new, "state": st, "nraw": nraw}
    skin_project._MESH.clear()
    skin_project._MESH.update(key=key, m=m)
    return m


def atlas(base: dict, size: int = skin_project.SIZE) -> dict:
    """The head's texture space: the one mesh's atlas over the head's faces (GNM's skin layout), `size` texels across.
    {"shape": (H, W), "box": [u0, v0, u1, v1] (atlas units the image covers), "ii", "jj" (the valid texels' rows /
    columns), "tri" (their triangle), "bary", "T" (triangles: template vertex indices), "uvT" (triangles' atlas
    coordinates), "V" (template vertices at rest), "head" (vertex is the head's), "gid" (GNM vertex or -1), "fade",
    "mm" (mm per texel, median), per-vertex "groups" {name: weight}}. Image row 0 is the top (v = v1)."""
    from . import onemesh
    from . import likeness_render
    from . import likeness
    from . import base_identity
    key = hashlib.sha1(json.dumps([base, size, skin_project.VERSION], sort_keys=True, default=str).encode()).hexdigest()
    if skin_project._ATLAS.get("key") == key:
        return skin_project._ATLAS["at"]
    mu = mesh_uv(base)
    a = onemesh.asset()
    st, V, T, uvT, gid, fid, fade, headv, is_new, nraw = (mu[k] for k in ("state", "V", "T", "uvT", "gid", "fid", "fade", "head", "is_new", "nraw"))
    fade = fade.copy()
    lo, hi = uvT.reshape(-1, 2).min(0) - skin_project.PAD, uvT.reshape(-1, 2).max(0) + skin_project.PAD
    W = int(size)
    H = int(round(size * (hi[1] - lo[1]) / (hi[0] - lo[0])))
    sx = ((uvT[..., 0] - lo[0]) / (hi[0] - lo[0]) * W).ravel()
    sy = ((hi[1] - uvT[..., 1]) / (hi[1] - lo[1]) * H).ravel()
    if not likeness._RUN:
        likeness._RUN.append(likeness_render._raster())
    F = np.arange(3 * len(T)).reshape(-1, 3)
    bary = np.zeros((H, W, 3))
    zb = np.full((H, W), np.inf)
    likeness._RUN[0](sx, sy, np.zeros(len(sx)), np.ascontiguousarray(F), np.tile(np.eye(3), (len(T), 1)), W, H, bary, zb)
    tid = np.zeros((H, W, 3))
    zb2 = np.full((H, W), np.inf)
    likeness._RUN[0](sx, sy, np.zeros(len(sx)), np.ascontiguousarray(F), np.repeat(np.arange(len(T), dtype=float), 3)[:, None] * np.ones(3), W, H, tid, zb2)
    ii, jj = np.nonzero(np.isfinite(zb))
    b = bary[ii, jj]
    b /= b.sum(1, keepdims=True)
    tri = np.round(tid[ii, jj, 0]).astype(int)
    G = base_identity._gnm_data()["groups"]
    groups = {}
    for k, g in G.items():
        g = np.asarray(g, float)
        groups[k] = np.where(gid >= 0, g[np.clip(gid, 0, len(g) - 1)], 0.0)
    for k in list(groups):   # the lids' new loop vertices take their neighbours' groups
        if is_new.any():
            pass
    e3 = np.linalg.norm(V[T[:, 1]] - V[T[:, 0]], axis=1)
    e2 = np.linalg.norm((uvT[:, 1] - uvT[:, 0]) / (hi - lo) * [W, H], axis=1)
    at = {"shape": (H, W), "box": [float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])], "ii": ii, "jj": jj, "tri": tri,
          "bary": b, "T": T, "uvT": uvT, "V": V, "head": headv, "gid": gid, "fid": fid, "fade": fade, "groups": groups,
          "mm": float(np.median(1000 * e3 / np.maximum(e2, 1e-9))), "state": st, "key": key[:12],
          "neutral": np.asarray(a["neutral"], float)[np.clip(fid, 0, nraw - 1)] if True else None, "is_new": is_new}
    if is_new.any():   # new loop vertices: neutral position and groups from the nearest old head vertex at rest
        from scipy.spatial import cKDTree
        old = np.flatnonzero(headv & ~is_new)
        nn = old[cKDTree(V[old]).query(V[is_new])[1]]
        at["neutral"][is_new] = at["neutral"][nn] + (V[is_new] - V[nn])
        for k in groups:
            groups[k][is_new] = groups[k][nn]
        at["fade"][is_new] = fade[nn]
    skin_project._ATLAS.clear()
    skin_project._ATLAS.update(key=key, at=at)
    return at


def interp(at: dict, A: np.ndarray) -> np.ndarray:
    """A per-vertex array at the valid texels."""
    A = np.asarray(A, float)
    t, b = at["T"][at["tri"]], at["bary"]
    if A.ndim == 1:
        return (A[t] * b).sum(1)
    return (A[t] * b[:, :, None]).sum(1)


def image(at: dict, vals: np.ndarray, fill=0.0) -> np.ndarray:
    """Valid-texel values as an (H, W[, c]) image."""
    vals = np.asarray(vals)
    out = np.full(at["shape"] + vals.shape[1:], fill, vals.dtype if vals.dtype != bool else bool)
    out[at["ii"], at["jj"]] = vals
    return out


def _blur(at: dict, vals: np.ndarray, w: np.ndarray | None, mm: float) -> np.ndarray:
    """A masked Gaussian of valid-texel values across the atlas (sigma in mm; weights w, default 1): the weighted
    local mean, at the valid texels. Where no weight is within reach the value stays."""
    from scipy import ndimage
    sg = mm / at["mm"]
    w = np.ones(len(vals)) if w is None else np.asarray(w, float)
    Wm = image(at, w.astype(np.float32))
    den = ndimage.gaussian_filter(Wm, sg)[at["ii"], at["jj"]]
    if vals.ndim == 1:
        num = ndimage.gaussian_filter(image(at, (vals * w).astype(np.float32)), sg)[at["ii"], at["jj"]]
        return np.where(den > 1e-4, num / np.maximum(den, 1e-4), vals)
    out = np.empty_like(vals, dtype=float)
    for c in range(vals.shape[1]):
        num = ndimage.gaussian_filter(image(at, (vals[:, c] * w).astype(np.float32)), sg)[at["ii"], at["jj"]]
        out[:, c] = np.where(den > 1e-4, num / np.maximum(den, 1e-4), vals[:, c])
    return out


def _normals(at: dict, V: np.ndarray) -> np.ndarray:
    from . import likeness_render
    return likeness_render._vertex_normals(V, at["_Fall"]) if "_Fall" in at else likeness_render._vertex_normals(V, at["T"])
