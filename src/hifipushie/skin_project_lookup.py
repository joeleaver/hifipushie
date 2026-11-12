"""The atlas at surface points (the image wrap): closest texel, the lookup, the cut's sides. Part of the skin projection (skin_project.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_project
from .skin_project import _sstep
from .skin_project_atlas import mesh_uv

def _closest(P, A, B, C):
    """Closest points of triangles (A, B, C) to points P, all (n, 3): barycentric (n, 3)."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = P - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = P - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = np.maximum(va + vb + vc, 1e-30)
    v, w = vb / den, vc / den
    out = np.stack([1 - v - w, v, w], 1)
    def setw(m, val):
        out[m] = val[m]
    e = np.zeros_like(out)
    t = np.clip(d1 / np.maximum(d1 - d3, 1e-30), 0, 1)
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    e[:] = np.stack([1 - t, t, np.zeros_like(t)], 1)
    setw(m, e)
    t = np.clip(d2 / np.maximum(d2 - d6, 1e-30), 0, 1)
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    e[:] = np.stack([1 - t, np.zeros_like(t), t], 1)
    setw(m, e)
    t = np.clip((d4 - d3) / np.maximum((d4 - d3) + (d5 - d6), 1e-30), 0, 1)
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    e[:] = np.stack([np.zeros_like(t), 1 - t, t], 1)
    setw(m, e)
    out[(d1 <= 0) & (d2 <= 0)] = [1, 0, 0]
    out[(d3 >= 0) & (d4 <= d3)] = [0, 1, 0]
    out[(d6 >= 0) & (d5 <= d6)] = [0, 0, 1]
    return out


def lookup(base: dict, pos: np.ndarray, k: int = 8, both: bool = False) -> tuple:
    """(u, v, weight) of surface points in the head's atlas (atlas units): the closest point of the head's own mesh
    (the template at rest), its triangle's atlas coordinates. weight: 0 off the head (REACH) and along the atlas' cut
    (SEAM: one per-vertex coordinate set cannot cross it; the layer under shows there).

    both=True: (u, v, u2, v2, s, weight), no fade at the cut. Near the cut (CUT_BAND, its two sides coloured
    consistently along it: side A, side B) (u, v) is side A's map and (u2, v2) side B's, each extrapolated across the
    cut from the nearest cut edge's triangle on that side (unclamped barycentrics), and s = side B's share, smooth
    across the cut (0 / 1 outside the band); elsewhere both sets are the point's own coordinates. A consumer samples
    the image at both and mixes by s: continuous across the cut (a fade there showed as a light stripe down the back
    of Garrett's neck, the layer under at every uv-wrapped layer's cut)."""
    from scipy.spatial import cKDTree
    key = hashlib.sha1(json.dumps([base, skin_project.VERSION, "lookup4"], sort_keys=True, default=str).encode()).hexdigest()
    if skin_project._LOOK.get("key") != key:
        at = mesh_uv(base)
        V, T, uvT = at["V"], at["T"], at["uvT"]
        nT = len(T)
        Tall = np.r_[T, at["other"]] if len(at["other"]) else T
        cen = V[Tall].mean(1)
        # the cut: edges whose two triangles disagree on a shared vertex's coordinates
        ed: dict = {}
        seam, stri = [], []
        for t in range(len(T)):
            for a, b in ((0, 1), (1, 2), (2, 0)):
                e = (min(T[t, a], T[t, b]), max(T[t, a], T[t, b]))
                ua, ub = (uvT[t, a], uvT[t, b]) if T[t, a] < T[t, b] else (uvT[t, b], uvT[t, a])
                if e in ed:
                    if np.abs(ed[e][0] - ua).sum() + np.abs(ed[e][1] - ub).sum() > 1e-5:
                        seam.append(e)
                        stri.append((ed[e][2], t))
                else:
                    ed[e] = (ua, ub, t)
        fs = (0.0, 0.25, 0.5, 0.75, 1.0)
        sp = np.concatenate([V[[a for a, _ in seam]] * (1 - f) + V[[b for _, b in seam]] * f for f in fs]) if seam else np.zeros((0, 3))
        skin_project._LOOK.clear()
        skin_project._LOOK.update(key=key, V=V, T=Tall, nT=nT, uvT=uvT, tree=cKDTree(cen), seam=cKDTree(sp) if len(sp) else None,
                     seam_edge=np.tile(np.arange(len(seam)), len(fs)), cut=_cut_sides(V, T, uvT, seam, stri))
    L = skin_project._LOOK
    P = np.asarray(pos, float)
    u, v, w = np.full(len(P), -1.0), np.full(len(P), -1.0), np.zeros(len(P))
    d0, _ = L["tree"].query(P)
    near = np.flatnonzero(d0 < 0.03)
    if not len(near):
        return u, v, w
    Pn = P[near]
    _, cand = L["tree"].query(Pn, k=k)
    best = np.full(len(Pn), np.inf)
    bu = np.zeros((len(Pn), 2))
    own = np.zeros(len(Pn), bool)
    for j in range(k):
        t = cand[:, j]
        A, B, C = (L["V"][L["T"][t, i]] for i in range(3))
        b = _closest(Pn, A, B, C)
        Q = b[:, :1] * A + b[:, 1:2] * B + b[:, 2:] * C
        d = np.linalg.norm(Q - Pn, axis=1)
        m = d < best
        best[m] = d[m]
        inat = t < L["nT"]
        own[m] = inat[m]
        mm_ = m & inat
        bu[mm_] = (b[mm_, :, None] * L["uvT"][t[mm_]]).sum(1)
    # every point gets the head atlas' coordinates of its nearest HEAD triangle, even off the head (weight 0 there): a
    # vertex left at (-1, -1) dragged the interpolated coordinates of its triangles across the atlas (a ragged colour
    # band where the head met the neck)
    miss = ~own
    if miss.any():
        hc = L.get("htree")
        if hc is None:
            L["htree"] = hc = cKDTree(L["V"][L["T"][:L["nT"]]].mean(1))
        _, hcand = hc.query(Pn[miss], k=k)
        hb = np.full(int(miss.sum()), np.inf)
        for j in range(k):
            t = hcand[:, j]
            A, B, C = (L["V"][L["T"][t, i]] for i in range(3))
            b = _closest(Pn[miss], A, B, C)
            Q = b[:, :1] * A + b[:, 1:2] * B + b[:, 2:] * C
            d = np.linalg.norm(Q - Pn[miss], axis=1)
            m = d < hb
            hb[m] = d[m]
            sub = np.flatnonzero(miss)[m]
            bu[sub] = (b[m, :, None] * L["uvT"][t[m]]).sum(1)
    wt = (1 - _sstep((best - skin_project.REACH[0]) / skin_project.REACH[1])) * own      # (the body, the mouth's sock: not the head's atlas)
    # ... faded in from the body's triangles over BODY_FADE (a per-vertex 1 / 0 step there drew a jagged colour line
    # where the head met the neck, whatever the image's own alpha did)
    if L.get("otree") is None and len(L["T"]) > L["nT"]:
        L["otree"] = cKDTree(L["V"][L["T"][L["nT"]:]].mean(1))
    if L.get("otree") is not None:
        do = L["otree"].query(Pn)[0]
        wt *= _sstep(do / skin_project.BODY_FADE)
    if not both:
        if L["seam"] is not None:
            ds = L["seam"].query(Pn)[0]
            wt *= _sstep((ds - skin_project.SEAM[0]) / skin_project.SEAM[1])
        u[near], v[near], w[near] = bu[:, 0], bu[:, 1], wt
        return u, v, w
    ua, ub, s = bu.copy(), bu.copy(), np.zeros(len(Pn))
    if L["seam"] is not None and len(L["cut"]["A"]):
        ds, si = L["seam"].query(Pn)
        # side and s out to 4 bands (a triangle straddling where the extrapolated set stops must see the same side at its
        # corners: the set's weight is 0 there), the other side's map only out to 2 bands
        zone = np.flatnonzero(ds < 4 * skin_project.CUT_BAND)
        if len(zone):
            e = L["seam_edge"][si[zone]]
            cut, Pz = L["cut"], Pn[zone]
            ea, eb = L["V"][cut["ev"][e, 0]], L["V"][cut["ev"][e, 1]]
            d = eb - ea
            tq = np.clip(((Pz - ea) * d).sum(1) / np.maximum((d * d).sum(1), 1e-30), 0, 1)
            side_b = ((Pz - (ea + tq[:, None] * d)) * cut["nB"][e]).sum(1) > 0
            sd = np.where(side_b, ds[zone], -ds[zone])
            s[zone] = _sstep(0.5 + sd / skin_project.CUT_BAND)
            xa = _affine_uv(L, cut["A"][e], Pz)
            xb = _affine_uv(L, cut["B"][e], Pz)
            own = bu[zone]
            # the point's own coordinates stand for its side's map unless its nearest triangle is the other side's
            # (a point just off the surface at the cut)
            mine = np.where(side_b[:, None], xb, xa)
            other = np.where(side_b[:, None], xa, xb)
            ok = np.abs(own - mine).sum(1) <= np.abs(own - other).sum(1)
            mine = np.where(ok[:, None], own, mine)
            far = ds[zone] > 2 * skin_project.CUT_BAND
            other = np.where(far[:, None], mine, other)
            ua[zone] = np.where(side_b[:, None], other, mine)
            ub[zone] = np.where(side_b[:, None], mine, other)
    out = [np.full(len(P), -1.0) for _ in range(4)] + [np.zeros(len(P)), np.zeros(len(P))]
    for o, x in zip(out, (ua[:, 0], ua[:, 1], ub[:, 0], ub[:, 1], s, wt)):
        o[near] = x
    return tuple(out)


def _affine_uv(L: dict, t: np.ndarray, P: np.ndarray) -> np.ndarray:
    """Atlas coordinates of points P on triangles t's maps, extended past their edges: P projected onto each triangle's
    plane, its unclamped barycentrics times the triangle's corner coordinates."""
    A, B, C = (L["V"][L["T"][t, i]] for i in range(3))
    e1, e2, q = B - A, C - A, P - A
    d11, d12, d22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
    q1, q2 = (q * e1).sum(1), (q * e2).sum(1)
    den = np.maximum(d11 * d22 - d12 * d12, 1e-30)
    b1, b2 = (d22 * q1 - d12 * q2) / den, (d11 * q2 - d12 * q1) / den
    uv = L["uvT"][t]
    return uv[:, 0] * (1 - b1 - b2)[:, None] + uv[:, 1] * b1[:, None] + uv[:, 2] * b2[:, None]


def _cut_sides(V: np.ndarray, T: np.ndarray, uvT: np.ndarray, seam: list, stri: list) -> dict:
    """The atlas' cut edges with their two triangles named consistently along the cut: side A / side B. A cut vertex
    has one atlas copy per side; a triangle's copies at its cut edge are one side, the edge's other triangle's the
    other (copies equal on both sides, at a cut's end, join nothing). The copies' sides are a 2-colouring. Also nB:
    per edge, the unit in-surface direction from the edge into side B's triangle. {"ev", "A", "B", "nB"}."""
    par: dict = {}

    def find(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def node(vi, t):
        c = uvT[t][list(T[t]).index(vi)]
        return (int(vi), round(float(c[0]), 5), round(float(c[1]), 5))
    pairs, first = [], []
    for (a, b), (t0, t1) in zip(seam, stri):
        n0, n1 = [], []
        for vi in (a, b):
            x0, x1 = node(vi, t0), node(vi, t1)
            if x0 != x1:
                n0.append(x0)
                n1.append(x1)
                pairs.append((x0, x1))
        for ns in (n0, n1):
            for x in ns[1:]:
                par[find(x)] = find(ns[0])
        first.append(n0[0] if n0 else None)
    opp: dict = {}
    for x0, x1 in pairs:
        r0, r1 = find(x0), find(x1)
        opp.setdefault(r0, set()).add(r1)
        opp.setdefault(r1, set()).add(r0)
    col: dict = {}
    for r in opp:
        if r in col:
            continue
        col[r], todo = 0, [r]
        while todo:
            x = todo.pop()
            for y in opp[x]:
                if y not in col:
                    col[y] = 1 - col[x]
                    todo.append(y)
    A, B = [], []
    for (t0, t1), x in zip(stri, first):
        a_is_t0 = x is None or col.get(find(x), 0) == 0
        A.append(t0 if a_is_t0 else t1)
        B.append(t1 if a_is_t0 else t0)
    ev, B = np.asarray(seam, int).reshape(-1, 2), np.asarray(B, int)
    nB = np.zeros((len(ev), 3))
    if len(ev):
        d = V[ev[:, 1]] - V[ev[:, 0]]
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-30)
        x = V[T[B]].mean(1) - 0.5 * (V[ev[:, 0]] + V[ev[:, 1]])
        x -= (x * d).sum(1, keepdims=True) * d
        nB = x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-30)
    return {"ev": ev, "A": np.asarray(A, int), "B": B, "nB": nB}
