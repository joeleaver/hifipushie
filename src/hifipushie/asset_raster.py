"""Rasterizing and UV space: rasterize, UV islands, projection, corners, dilation, fills across seams, PNG. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import asset
from . import surface

def rasterize(parts: dict, size: int, atlas: int | None = None, ring: int = 0):
    """Which triangle covers each texel and where: (texel rows and columns, triangle id, barycentrics, part index
    of every triangle, inside, drawn). Triangle ids and part indices count over all parts in order; only the parts on
    `atlas` (None: all) are drawn. Texel (x, y) of the PNG (row 0 at the top) is uv ((x + .5) / size, 1 - (y + .5)
    / size). inside: the texel's centre lies in its triangle. ring > 0: texels whose centre lies outside (PIL's edge
    texels, plus every texel up to `ring` (+ the diagonal) texels past an island's edge, appended after the drawn ones, with their
    nearest drawn texel's triangle) get the triangle's barycentrics extrapolated: the surface carried on past the
    chart's edge, as the chart across the seam has it (a texel copied from its nearest neighbour put a sharp edge
    a fraction of a texel off on each side of a seam). Without ring they are clamped onto the triangle."""
    img = Image.new("I", (size, size), -1)
    d = ImageDraw.Draw(img)
    uvs, tpart, draw = [], [], []
    for pi, p in enumerate(parts.values()):
        uvs.append(p["uv"].reshape(-1, 3, 2))
        tpart.append(np.full(len(uvs[-1]), pi))
        draw.append(np.full(len(uvs[-1]), atlas is None or p.get("atlas", 0) == atlas))
    uv = np.concatenate(uvs).astype(np.float64)
    px = np.stack([uv[..., 0] * size, (1 - uv[..., 1]) * size], -1)
    for t in np.flatnonzero(np.concatenate(draw)):
        d.polygon([tuple(q) for q in px[t]], fill=int(t))
    tid = np.asarray(img, np.int64)
    ys, xs = np.nonzero(tid >= 0)
    t = tid[ys, xs]
    if ring > 0:
        from scipy import ndimage
        dist, (iy, ix) = ndimage.distance_transform_edt(tid < 0, return_indices=True)
        ry, rx = np.nonzero((tid < 0) & (dist <= ring + 0.5))
        t = np.concatenate([t, tid[iy[ry, rx], ix[ry, rx]]])
        ys, xs = np.concatenate([ys, ry]), np.concatenate([xs, rx])
    a, b, c = px[t, 0], px[t, 1], px[t, 2]
    q = np.stack([xs + 0.5, ys + 0.5], -1)
    v0, v1, v2 = b - a, c - a, q - a
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    w1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
    w2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
    raw = np.stack([1 - w1 - w2, w1, w2], -1)
    inside = (raw >= -1e-6).all(1)  # the texel's centre lies in its triangle (edge texels PIL adds don't)
    bary = np.clip(raw, 0, 1)
    bary /= bary.sum(1, keepdims=True)
    if ring > 0:  # extrapolated, unless the uv triangle is too thin for its plane to say where (a sliver)
        span = np.maximum.reduce([np.linalg.norm(v0, axis=1), np.linalg.norm(v1, axis=1),
                                  np.linalg.norm(c - b, axis=1)])
        height = np.abs(den) / np.maximum(span, 1e-12)  # texels across the triangle
        ok = ~inside & (height > 0.5)
        bary[ok] = raw[ok]
    drawn = np.arange(len(t)) < int((tid >= 0).sum())  # (the ring texels come after the drawn ones)
    return (ys, xs), t, bary, np.concatenate(tpart), inside, drawn


def uv_islands(parts: dict) -> np.ndarray:
    """UV island id per triangle (over all parts, in order): triangles joined across edges whose two corners have
    the same vertices and uvs on both sides."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    keys, tris = [], []
    t0 = 0
    for pi, p in enumerate(parts.values()):
        cv = p["corner_vert"].reshape(-1, 3).astype(np.int64)
        uv = np.round(p["uv"].reshape(-1, 3, 2) * 2 ** 20).astype(np.int64)
        for a, b in ((0, 1), (1, 2), (2, 0)):
            swap = cv[:, a] > cv[:, b]
            va, vb = np.where(swap, cv[:, b], cv[:, a]), np.where(swap, cv[:, a], cv[:, b])
            ua, ub = np.where(swap[:, None], uv[:, b], uv[:, a]), np.where(swap[:, None], uv[:, a], uv[:, b])
            keys.append(np.column_stack([np.full(len(cv), pi), va, vb, ua, ub]))
            tris.append(t0 + np.arange(len(cv)))
        t0 += len(cv)
    keys, tris = np.concatenate(keys), np.concatenate(tris)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.ravel()
    order = np.argsort(inv, kind="stable")
    same = inv[order][1:] == inv[order][:-1]  # consecutive triangles sharing an edge key
    a, b = tris[order][:-1][same], tris[order][1:][same]
    g = coo_matrix((np.ones(len(a)), (a, b)), shape=(t0, t0))
    return connected_components(g, directed=False)[1]


def _project(prims, P: np.ndarray, ys: np.ndarray, xs: np.ndarray, island: np.ndarray, vx: float, step: int = 4):
    """surface.newton for texels, cheaper: every `step`-th texel (both ways) is projected from the low poly; the
    rest start from their low-poly point moved by the offset interpolated from the anchors around them (on their
    own uv island), a step or two from converged. Where the low poly lies near the surface that is the point a
    start from the low poly finds; where it strays (bridged gaps, rounded-off corners) the nearest surface is
    ambiguous and the two may differ, equally on the surface (cabin5 at 6 mm texels: residuals the same or
    lower, 1.6-2x faster)."""
    anc = (ys % step == 0) & (xs % step == 0)
    X, G = P.copy(), np.zeros_like(P)
    if anc.sum() < 16 or anc.mean() > 0.5:
        return surface.newton(prims, P, 0.1 * vx, vx)
    X[anc], G[anc] = surface.newton(prims, P[anc], 0.1 * vx, vx)
    # the anchors' offsets on a grid, with their islands
    gy, gx = ys[anc] // step, xs[anc] // step
    H, W = gy.max() + 2, gx.max() + 2
    k = np.full((H, W), -1, np.int64)
    k[gy, gx] = np.flatnonzero(anc)
    rest = np.flatnonzero(~anc)
    cy, cx = ys[rest] // step, xs[rest] // step
    u, v = (xs[rest] % step) / step, (ys[rest] % step) / step
    off, wsum = np.zeros((len(rest), 3)), np.zeros(len(rest))
    for dy, dx, w in ((0, 0, (1 - u) * (1 - v)), (0, 1, u * (1 - v)), (1, 0, (1 - u) * v), (1, 1, u * v)):
        yy, xx = np.minimum(cy + dy, H - 1), np.minimum(cx + dx, W - 1)
        a = k[yy, xx]
        ok = (a >= 0) & (island[np.maximum(a, 0)] == island[rest])
        w = np.where(ok, w, 0.0)
        off += w[:, None] * (X[np.maximum(a, 0)] - P[np.maximum(a, 0)])
        wsum += w
    has = wsum > 1e-9
    start = P[rest].copy()
    start[has] += off[has] / wsum[has, None]
    X[rest], G[rest] = surface.newton(prims, start, 0.1 * vx, vx)
    return X, G


def _corners(parts: dict, key: str) -> np.ndarray:
    out = []
    for p in parts.values():
        v = p["verts"][p["corner_vert"]] if key == "pos" else p[key]
        out.append(v.reshape(len(p["corner_vert"]) // 3, 3, -1))
    return np.concatenate(out).astype(np.float64)


def _dilate(img: np.ndarray, filled: np.ndarray) -> np.ndarray:
    """Fill empty texels from the nearest filled one, so filtering and mips don't pull in background at seams."""
    from scipy import ndimage
    _, (iy, ix) = ndimage.distance_transform_edt(~filled, return_indices=True)
    return img[iy, ix]


def _fill_missed_3d(given: dict, baked: np.ndarray, miss: np.ndarray, ys, xs, P, part, log: list) -> dict:
    """bake(): each missed texel (rows of ys/xs/P/part, mask `miss`) from its MISS_FILL_3D nearest baked texels of the
    same part by surface position, inverse-distance weighted."""
    from scipy.spatial import cKDTree
    ok = baked[ys, xs]
    out = {k: v.copy() for k, v in given.items()}
    n = 0
    for pi in np.unique(part[miss]):
        src = np.flatnonzero(ok & (part == pi))
        dst = np.flatnonzero(miss & (part == pi))
        if len(src) < asset.MISS_FILL_3D or not len(dst):
            continue
        d, j = cKDTree(P[src]).query(P[dst], k=asset.MISS_FILL_3D)
        w = 1.0 / np.maximum(d, 1e-5) ** 2
        w /= w.sum(1, keepdims=True)
        sy, sx = ys[src][j], xs[src][j]
        for k, v in given.items():
            out[k][ys[dst], xs[dst]] = np.einsum("nk,nkc->nc", w, v[sy, sx].astype(np.float64)).astype(v.dtype)
        n += len(dst)
    if n:
        log.append(f"    {n} texels missed inside their triangle: filled from their {asset.MISS_FILL_3D} nearest baked texels on "
                   f"the surface")
    return out


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _across_seams(parts, given, baked, share, ys, xs, tri, P, fill, tpart, texel):
    """The texels past each island's edge (rasterize's ring: their point P is their triangle's plane carried on
    past the edge) take what the chart across the seam baked at that surface point: the low-poly triangle of the
    same part, on another island, that P lies on (within half a texel), its uv, Cycles' maps sampled there
    bilinearly. Then bilinear filtering at a chart's edge reads the surface beyond it, as the chart across reads
    it. Returns (given, baked, texels filled)."""
    from .decalmap import _closest_bary
    r = np.flatnonzero(fill)
    if not len(r):
        return given, baked, 0
    C, UV = _corners(parts, "pos"), _corners(parts, "uv")
    isl = uv_islands(parts)
    # global vertex ids per triangle, and each vertex's triangles (padded): the faces across an edge are found by
    # topology, not by distance (a decimated cylinder's strips are hundreds of texels long: their centres are far
    # from a point just past their side)
    tv, base = [], 0
    for p in parts.values():
        tv.append(p["corner_vert"].reshape(-1, 3).astype(np.int64) + base)
        base += len(p["verts"])
    tv = np.concatenate(tv)
    vs, fs = tv.ravel(), np.repeat(np.arange(len(tv)), 3)
    o = np.argsort(vs, kind="stable")
    vs, fs = vs[o], fs[o]
    start = np.searchsorted(vs, np.arange(base))
    rank = np.arange(len(vs)) - start[vs]
    cap = int(min(rank.max() + 1, 16))
    vf = np.full((base, cap), -1, np.int64)
    keep = rank < cap
    vf[vs[keep], rank[keep]] = fs[keep]
    A = tri[r]
    # the edge of its own triangle the texel lies past (its most negative barycentric), and the faces round that
    # edge's two vertices: the triangle across the seam and its neighbours
    e0, e1 = C[A, 1] - C[A, 0], C[A, 2] - C[A, 0]
    nrm = np.cross(e0, e1)
    q = P[r] - C[A, 0]
    n2 = np.maximum((nrm * nrm).sum(1), 1e-30)
    w1 = (np.cross(q, e1) * nrm).sum(1) / n2
    w2 = (np.cross(e0, q) * nrm).sum(1) / n2
    k_out = np.argmin(np.stack([1 - w1 - w2, w1, w2], 1), 1)
    va = tv[A, (k_out + 1) % 3]
    vb = tv[A, (k_out + 2) % 3]
    cand = np.concatenate([vf[va], vf[vb]], 1)
    best, bt, bw = np.full(len(r), np.inf), np.full(len(r), -1), np.zeros((len(r), 3))
    own_isl, own_part = isl[A], tpart[A]
    for j in range(cand.shape[1]):
        t = cand[:, j]
        okj = t >= 0
        t = np.where(okj, t, 0)
        w = _closest_bary(P[r], C[t, 0], C[t, 1], C[t, 2])
        d = np.linalg.norm(np.einsum("nk,nkc->nc", w, C[t]) - P[r], axis=1)
        better = okj & (isl[t] != own_isl) & (tpart[t] == own_part) & (d < best)
        best[better], bt[better], bw[better] = d[better], t[better], w[better]
    ok = (bt >= 0) & (best < texel)
    if not ok.any():
        return given, baked, 0
    uv = np.einsum("nk,nkc->nc", bw[ok], UV[bt[ok]])
    yy, xx = ys[r[ok]], xs[r[ok]]
    a = share[yy, xx][:, None]  # an edge texel part-baked keeps its own points' share: the rest from across
    from scipy import ndimage
    done = baked.copy()
    done[yy, xx] = True
    # (one pass: a second, reading the chart across with its edge texels already filled, measured worse: 1.08 -> 1.14)
    _, (iy, ix) = ndimage.distance_transform_edt(~baked, return_indices=True)
    out = {}
    for name, img in given.items():
        v = _bilinear(img[iy, ix], uv)  # (past its own edge, the chart across reads its nearest texel)
        o = img.copy()
        o[yy, xx] = a * img[yy, xx] + (1 - a) * v
        o[yy, xx, -1] = 1.0  # baked now
        out[name] = o
    return out, done, int(ok.sum())


def _bilinear(img: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """img (rows top first) at uvs as an engine samples it (bilinear, texel centres at (i + .5) / size, clamped)."""
    S = img.shape[0]
    x, y = uv[:, 0] * S - 0.5, (1 - uv[:, 1]) * S - 0.5
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    c = lambda a: np.clip(a, 0, S - 1)  # noqa: E731
    return (img[c(y0), c(x0)] * (1 - fx) * (1 - fy) + img[c(y0), c(x0 + 1)] * fx * (1 - fy)
            + img[c(y0 + 1), c(x0)] * (1 - fx) * fy + img[c(y0 + 1), c(x0 + 1)] * fx * fy)


def _srgb(lin: np.ndarray) -> np.ndarray:
    """linear [0, 1] -> sRGB-encoded"""
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.clip(lin, 0, None) ** (1 / 2.4) - 0.055)


def _png(path: Path, img: np.ndarray, srgb_input: bool = True, bits: int = 8):
    a = np.clip(img, 0, 1)
    if bits == 16:
        Image.fromarray((a[..., 0] * 65535 + 0.5).astype(np.uint16)).save(path)
        return
    a = (a * 255 + 0.5).astype(np.uint8)
    Image.fromarray(a[..., 0] if a.shape[-1] == 1 else a).save(path)
