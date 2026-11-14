"""Unwrap: adjacency and components, charts split and packed, split corners, tangents. Part of the terrain's bake (terrain_bake.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import terrain_bake
from .terrain_bake import _unit

def _adjacency(P, F):
    """Face pairs sharing an edge (vertices welded by position)."""
    _, wid = np.unique(np.round(P, 6), axis=0, return_inverse=True)
    wid = wid.ravel()
    W = wid[F]
    e = np.concatenate([W[:, [0, 1]], W[:, [1, 2]], W[:, [2, 0]]])
    f = np.tile(np.arange(len(F)), 3)
    key = np.minimum(e[:, 0], e[:, 1]) * (wid.max() + 1) + np.maximum(e[:, 0], e[:, 1])
    o = np.argsort(key, kind="stable")
    same = key[o][1:] == key[o][:-1]
    return f[o][:-1][same], f[o][1:][same]


def _components(n, a, b):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    g = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
    return connected_components(g, directed=False)[1]


def _raster(tris, W, H):
    """Triangle id per texel (-1 none) for texel-space triangles (m, 3, 2): x right, y down."""
    from PIL import Image, ImageDraw
    img = Image.new("I", (W, H), -1)
    d = ImageDraw.Draw(img)
    for t, q in enumerate(tris):
        d.polygon([(float(x), float(y)) for x, y in q], fill=int(t))
    return np.asarray(img, np.int64)


def unwrap(P, F, density, max_size, margin=3):
    """Charts and a packed atlas for one mesh. Returns (corner uv (m, 3, 2) in 0..1, glTF convention: v down),
    the atlas size, the density used (texels/m) and the chart id per face."""
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    area = np.linalg.norm(fn, axis=1) / 2
    fn = _unit(fn)
    score = fn @ terrain_bake._DIRS.T
    lab = np.argmax(score, 1)
    a, b = _adjacency(P, F)
    for _ in range(3):  # fewer ragged charts: a face joins the label most of its neighbours have, if it faces it
        cnt = np.zeros((len(F), 6))
        np.add.at(cnt, (a, lab[b]), 1)
        np.add.at(cnt, (b, lab[a]), 1)
        best = np.argmax(cnt, 1)
        ok = (cnt[np.arange(len(F)), best] >= 2) & (score[np.arange(len(F)), best] > 0.35)
        lab = np.where(ok, best, lab)
    same = lab[a] == lab[b]
    comp = _components(len(F), a[same], b[same])
    # 2D coordinates per corner (metres) in each chart's own projection
    U = np.array([terrain_bake._UV[k][0] for k in range(6)], float)
    V = np.array([terrain_bake._UV[k][1] for k in range(6)], float)
    C = P[F]  # (m, 3, 3)
    uv = np.stack([(C * U[lab][:, None, :]).sum(2), (C * V[lab][:, None, :]).sum(2)], -1)
    charts = []
    for cid in range(comp.max() + 1):
        fs = np.flatnonzero(comp == cid)
        charts += _split(fs, uv, P, F)
    # a chart longer than about half the atlas it needs is cut in two (a 64 m cliff in one piece forced an atlas
    # twice the size, 10-20% filled)
    side = math.sqrt(max(area.sum(), 1e-6) * density ** 2 / 0.6)
    lim = max(64.0, 0.5 * min(2 ** math.ceil(math.log2(max(side, 1.0))), max_size)) / density
    out, todo = [], list(charts)
    while todo:
        fs = todo.pop()
        q = uv[fs].reshape(-1, 2)
        if len(fs) > 1 and float(np.max(np.ptp(q, 0))) > lim:
            c = P[F[fs]].mean(1)
            ax = int(np.argmax(np.ptp(c, 0)))
            m = np.median(c[:, ax])
            a_, b_ = fs[c[:, ax] <= m], fs[c[:, ax] > m]
            if len(a_) and len(b_):
                todo += [a_, b_]
                continue
        out.append(fs)
    return _pack(out, uv, area, density, max_size, margin)


def _split(fs, uv, P, F, depth=0):
    """A chart as face lists that don't overlap in their projection (split in two along its longest 3D axis while
    the triangles' summed area exceeds their union's)."""
    q = uv[fs].reshape(-1, 2)
    lo, hi = q.min(0), q.max(0)
    ext = float(max(hi - lo))
    if len(fs) < 3 or depth > 8 or ext <= 0:
        return [fs]
    s = 256.0 / ext
    t = (uv[fs] - lo) * s
    e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    A = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() / 2
    ids = _raster(t, int(math.ceil((hi - lo)[0] * s)) + 2, int(math.ceil((hi - lo)[1] * s)) + 2)
    union = float((ids >= 0).sum())
    if union >= 0.93 * A - 2 * len(fs):  # (edge texels: thin triangles cover less than their area)
        return [fs]
    c = P[F[fs]].mean(1)
    ax = int(np.argmax(np.ptp(c, 0)))
    m = np.median(c[:, ax])
    left, right = fs[c[:, ax] <= m], fs[c[:, ax] > m]
    if not len(left) or not len(right):
        return [fs]
    return _split(left, uv, P, F, depth + 1) + _split(right, uv, P, F, depth + 1)


def _pack(charts, uv, area, density, max_size, margin):
    """Shelf packing of the charts' boxes (each turned to its smallest box) into a power-of-two square atlas."""
    boxes = []
    for fs in charts:
        q = uv[fs].reshape(-1, 2)
        c = q.mean(0)
        # the chart's principal axes: its smallest box
        cov = np.cov((q - c).T) if len(q) > 2 else np.eye(2)
        w, E = np.linalg.eigh(cov)
        R = E[:, ::-1]
        if np.linalg.det(R) < 0:
            R[:, 1] *= -1  # (a rotation, not a mirror: faces keep their winding)
        r = (q - c) @ R
        boxes.append((fs, c, R, r.min(0), r.max(0)))
    d = float(density)
    grow = 1.0
    B = 4  # packing on 4-texel blocks
    for _ in range(40):
        masks = [_chart_mask(uv[fs], c, R, lo, hi, d, margin, B) for fs, c, R, lo, hi in boxes]
        need = sum(float(m.sum()) for m in masks) * B * B * grow
        size = 2 ** max(6, int(math.ceil(math.log2(math.sqrt(need)))))
        if size > max_size:  # the density the cap allows
            d *= min(0.97, math.sqrt(max_size ** 2 / need))
            continue
        place = _raster_pack(masks, size // B)
        if place is not None:
            place = [(x * B, y * B) for x, y in place]
            break
        if size == max_size:
            d *= 0.93
        else:
            grow *= 1.3
    else:
        raise RuntimeError("uv packing failed")
    # as tall as the charts reach (to 128 texels): a half-empty square atlas wasted half its texels
    used = max(y + m.shape[0] * B for (x, y), m in zip(place, masks))
    H = min(size, max(64, 128 * int(math.ceil(used / 128))))
    out = np.zeros(uv.shape)
    cid = np.zeros(len(uv), np.int64)
    for k, ((fs, c, R, lo, hi), (x, y)) in enumerate(zip(boxes, place)):
        r = ((uv[fs] - c) @ R - lo) * d + margin + np.array([x, y])
        out[fs] = r / np.array([size, H])
        cid[fs] = k
    # our v runs up the chart (up the image); glTF's v runs down the image
    out[..., 1] = 1.0 - out[..., 1]
    return out, (size, H), d, cid


def _chart_mask(uvf, c, R, lo, hi, d, margin, B):
    """A chart's footprint on B-texel blocks (x, y = u, v), grown by `margin` texels for its gutter."""
    t = ((uvf - c) @ R - lo) * d + margin
    w, h = int(math.ceil((hi - lo)[0] * d + 2 * margin)), int(math.ceil((hi - lo)[1] * d + 2 * margin))
    ids = _raster(t, max(w, 1), max(h, 1)) >= 0
    ids |= ndimage.binary_dilation(ids, iterations=margin)
    nb = (-(-h // B), -(-w // B))
    m = np.zeros((nb[0] * B, nb[1] * B), bool)
    m[:h, :w] = ids
    m = m.reshape(nb[0], B, nb[1], B).any((1, 3))
    return m


def _raster_pack(masks, n):
    """Bottom-left placement of block masks (rows = v) on an n x n grid, largest first: the first free spot found by
    correlating each mask with what's taken. Returns [(x, y)] or None if they don't fit."""
    from scipy.signal import fftconvolve
    occ = np.zeros((n, n), np.float32)
    order = sorted(range(len(masks)), key=lambda k: -masks[k].sum())
    place = [None] * len(masks)
    for k in order:
        m = masks[k]
        h, w = m.shape
        if h > n or w > n:
            return None
        if occ.any():
            ov = fftconvolve(occ, m[::-1, ::-1].astype(np.float32), mode="valid")
            free = np.argwhere(ov < 0.5)
        else:
            free = np.array([[0, 0]])
        if not len(free):
            return None
        y, x = free[np.lexsort((free[:, 1], free[:, 0]))[0]]
        occ[y:y + h, x:x + w] += m
        place[k] = (int(x), int(y))
    return place


def split_corners(P, N, F, uvc, extra=None, ids=None):
    """New vertices per (vertex, uv) pair: glTF wants one uv per vertex. extra: per-vertex arrays carried along. ids:
    per-corner integers (m, 3) that split vertices too (the detail UV's plane); the result's "ids" per vertex."""
    key = np.c_[F.reshape(-1), np.round(uvc.reshape(-1, 2) * 2 ** 22).astype(np.int64)]
    if ids is not None:
        key = np.c_[key, np.asarray(ids).reshape(-1)]
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    src = F.reshape(-1)[first]
    out = {"P": P[src], "N": N[src], "uv": uvc.reshape(-1, 2)[first], "F": inv.reshape(-1, 3), "src": src}
    for k, v in (extra or {}).items():
        out[k] = v[src]
    if ids is not None:
        out["ids"] = np.asarray(ids).reshape(-1)[first]
    return out


def tangents(P, N, uv, F):
    """Per-vertex TANGENT (xyz, w) for glTF: xyz along +u, bitangent = cross(N, T) * w along -v (up the image)."""
    p0, p1, p2 = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    t0, t1, t2 = uv[F[:, 0]], uv[F[:, 1]], uv[F[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    d1, d2 = t1 - t0, t2 - t0
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-20, 1e-20, det)
    Tf = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det[:, None]   # dP/du
    Bf = -(e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det[:, None]  # -dP/dv
    # as MikkTSpace does it (Blender, Unity and Unreal recompute tangents that way and ignore ours): per corner the
    # face's tangent projected off the vertex normal and normalised, weighted by the corner's angle. Baking against
    # any other frame decodes wrong in those engines (lines along chart and tile borders, where frames differ most)
    Tv, Bv = np.zeros_like(P), np.zeros_like(P)
    C = P[F]
    for c in range(3):
        a_, b_ = C[:, (c + 1) % 3] - C[:, c], C[:, (c + 2) % 3] - C[:, c]
        ang = np.arccos(np.clip((_unit(a_) * _unit(b_)).sum(1), -1, 1))
        n = N[F[:, c]]
        tc = _unit(Tf - n * (Tf * n).sum(1, keepdims=True))
        np.add.at(Tv, F[:, c], tc * ang[:, None])
        np.add.at(Bv, F[:, c], _unit(Bf) * ang[:, None])
    T = _unit(Tv - N * (Tv * N).sum(1, keepdims=True))
    bad = np.linalg.norm(T, axis=1) < 0.5
    if bad.any():  # (a degenerate corner: any direction across the normal)
        alt = _unit(np.cross(N[bad], np.where(np.abs(N[bad, 2:3]) < 0.9, [[0, 0, 1.0]], [[1.0, 0, 0]])))
        T[bad] = alt
    w = np.where((np.cross(N, T) * Bv).sum(1) < 0, -1.0, 1.0)
    return np.c_[T, w]
