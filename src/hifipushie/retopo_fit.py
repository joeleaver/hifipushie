"""Fitting: the fit onto the surface, the neck cut, the mouth zip, graft_head, untangling. Part of retopo (retopo.py has the overview)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import sdf, surface
from .spec import expand_mirror, resolve_point
from .retopo import _lap, _tip_side, _unit, _vnormals, edges, topology, tris
from .retopo_patches import _loops_round

# ---------------------------------------------------------------------------------------------------- fitting
def _fit(V, L, S, prims, voxel, regions, dom, keep, fixed, reach=0.12, rounds=50):
    """Shoot free vertices along their normals to the nearest crossing of their region's surface, then relax
    along the surface and re-project; fixed vertices stay, kept ones (mouth bag) follow their neighbours."""
    T = tris(L, S)
    E = edges(L, S)
    N = _vnormals(V, T)
    free = ~keep & ~fixed
    t = np.linspace(-reach, reach, 121)
    f = np.full((len(V), len(t)), np.nan)
    for k, reg in enumerate(regions):
        m = (dom == k) & free
        if m.any():
            f[m] = sdf.field_at(reg or prims, V[m][:, None, :] + t[None, :, None] * N[m][:, None, :], margin=reach)
    m = free & (dom < 0)
    if m.any():
        f[m] = sdf.field_at(prims, V[m][:, None, :] + t[None, :, None] * N[m][:, None, :], margin=reach)
    ff = np.nan_to_num(f, nan=1.0)
    sgn = np.signbit(ff)
    cost = np.where(sgn[:, 1:] != sgn[:, :-1], np.abs(0.5 * (t[1:] + t[:-1]))[None, :], np.inf)
    k = cost.argmin(1)
    i = np.arange(len(V))
    ok = np.isfinite(cost[i, k]) & free
    f0, f1 = ff[i, k], ff[i, k + 1]
    tt = t[k] + (t[k + 1] - t[k]) * f0 / np.where(f0 - f1 == 0, 1, f0 - f1)
    V = V.copy()
    V[ok] += tt[ok, None] * N[ok]
    missed = free & ~ok

    def newton(X, it, m):
        X = X.copy()
        X[m] = surface.newton(prims, X[m], voxel * 0.125, voxel, iterations=it)[0]
        return X
    V = newton(V, 40, missed)
    V = newton(V, 8, free)
    deg = np.bincount(E.ravel(), minlength=len(V))
    for _ in range(rounds):
        N = _vnormals(V, T)
        lap = _lap(V, E, deg)
        dv = lap - (lap * N).sum(1, keepdims=True) * N
        X = V + 0.5 * dv
        X[keep] = V[keep] + 0.5 * lap[keep]
        X[free] = surface.newton(prims, X[free], voxel * 0.125, voxel, iterations=6)[0]
        X[fixed] = V[fixed]
        V = X
    return V, int(missed.sum())


def _neck_cut(V, L, S, c, n, side, gap):
    """A mesh cut at the closed quad loop round the neck nearest the graft plane on its own side (side -1: the
    body, below; +1: the head, above), at least `gap` from the plane, the far side dropped. A loop, not the plane:
    cut by the plane, the rims zigzagged a face deep and the bridge between them twisted."""
    faces, nb, ef = topology(L, S)
    V = np.asarray(V, float)
    u = (V - c) @ n
    rad = np.linalg.norm(np.cross(V - c, n), axis=1)
    near = set(np.flatnonzero((side * u > gap) & (side * u < gap + 0.09) & (rad < 0.12)).tolist())
    e1 = _unit(np.cross(n, [1.0, 0, 0]))
    e2 = np.cross(n, e1)
    best = None
    for path in _loops_round(V, faces, nb, ef, near, 300):
        if not all(p in near for p in path):
            continue
        q = V[path] - c
        ang = np.arctan2(q @ e2, q @ e1)
        wn = np.sum((np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi) / (2 * np.pi)
        if abs(round(wn)) != 1:
            continue
        d = float(np.abs(u[path]).max())
        if best is None or d < best[0]:
            best = (d, path)
    if best is None:
        raise ValueError(f"graft: no closed neck loop on the {'head' if side > 0 else 'body'} side of the plane")
    loop = best[1]
    far = int(np.argmax(-side * u))
    drop = _tip_side(loop, nb, far) - set(loop)
    kept = [f for f in faces if not any(v in drop for v in f)]
    used = sorted({v for f in kept for v in f})
    rm = np.full(len(V), -1)
    rm[used] = np.arange(len(used))
    return V[used], np.array([rm[v] for f in kept for v in f]), np.array([len(f) for f in kept])


def _zip_mouth(V, L, S, seam, reach=0.04):
    """The open mouth of a head mesh without its mouth bag (GNM's skin) zipped shut: the boundary loop round the
    lips split at its corners, each lower-lip vertex welded to the upper one at the same place along the lip. Left
    open over closed lips, the lips' inner rims projected onto one another and flecked."""
    faces = [list(map(int, L[a:a + k])) for a, k in zip(np.r_[0, np.cumsum(S)[:-1]], S)]
    cnt: dict = {}
    for f in faces:
        for k in range(len(f)):
            e = (min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)]))
            cnt[e] = cnt.get(e, 0) + 1
    V = np.asarray(V, float).copy()
    nbr: dict = {}
    for (a, b), c in cnt.items():
        if c == 1 and np.linalg.norm(V[a] - seam) < reach and np.linalg.norm(V[b] - seam) < reach:
            nbr.setdefault(a, []).append(b)
            nbr.setdefault(b, []).append(a)
    if not nbr or any(len(v) != 2 for v in nbr.values()):
        return V, L, S, 0
    loops, seen = [], set()
    for start in nbr:
        if start in seen:
            continue
        lp, prev = [start], None
        while True:
            nx = [w for w in nbr[lp[-1]] if w != prev]
            prev = lp[-1]
            if nx[0] == lp[0]:
                break
            lp.append(nx[0])
        seen |= set(lp)
        loops.append(lp)
    loop = max(loops, key=len)
    x = V[loop, 0]
    i0, i1, m = int(np.argmin(x)), int(np.argmax(x)), len(loop)
    a = [loop[(i0 + k) % m] for k in range((i1 - i0) % m + 1)]
    b = [loop[(i1 + k) % m] for k in range((i0 - i1) % m + 1)][::-1]
    up, lo = (a, b) if V[a, 2].mean() > V[b, 2].mean() else (b, a)
    arc = lambda P: np.r_[0, np.cumsum(np.linalg.norm(np.diff(V[P], axis=0), axis=1))] / max(
        float(np.linalg.norm(np.diff(V[P], axis=0), axis=1).sum()), 1e-9)
    su, sl = arc(up), arc(lo)
    to = np.arange(len(V))
    for v, t in zip(lo[1:-1], sl[1:-1]):
        to[v] = up[int(np.argmin(np.abs(su - t)))]
    for k, v in enumerate(up[1:-1], 1):
        V[v] = 0.5 * (V[v] + V[lo[int(np.argmin(np.abs(sl - su[k])))]])
    out = []
    for f in faces:
        g = [int(to[v]) for v in f]
        g = [v for k, v in enumerate(g) if v != g[k - 1]]
        if len(set(g)) >= 3:
            out.append(g)
    used = sorted({v for f in out for v in f})
    rm = np.full(len(V), -1)
    rm[used] = np.arange(len(used))
    return V[used], np.array([rm[v] for f in out for v in f]), np.array([len(f) for f in out]), len(up)


def graft_head(V, L, S, spec: dict, prims, log: list, unsub: int = 1, gap: float = 0.006):
    """A base with a grafted head (GNM) keeps the head's own quads: the template's face, carried onto a head of
    other proportions, folded round the mouth and jaw however the landmarks were set. The head's skin quads
    un-subdivided `unsub` times in Blender (12k -> 6k quads), both meshes cut `gap` clear of the graft plane, the
    two neck loops bridged, then the head and the bridge projected onto the field (strokes on the face count) and
    the bridge relaxed. Returns (V, L, S)."""
    import copy
    import tempfile
    from . import asset_budget
    from . import base_measures
    s = expand_mirror(spec)
    b = copy.deepcopy(spec["base"])
    b["head"] = {**b["head"], "subdivide": 0}
    h = base_measures.head_of(s, b)
    c, n = h["plane"][0], h["plane"][1]
    HL = np.array([v for f in h["faces"] for v in f])
    HS = np.array([len(f) for f in h["faces"]])
    Vb, Lb, Sb = _neck_cut(V, L, S, c, n, -1, 0.004)  # (the template's neck rings tilt up to the nape)
    Vh, Lh, Sh = _neck_cut(h["verts"], HL, HS, c, n, +1, -0.002)  # (GNM's neck rings tilt across the plane)
    if h.get("lips_zipped"):  # the head's own mesh is closed at the lips' contact (base_gnm_parts._zip_lips): the seam is
        # an edge loop already, on the field's lip line
        log.append(f"head: lips closed in the head mesh ({h['lips_zipped']} seam vertices)")
    elif "lm_lip_seam" in s["joints"] and float(np.linalg.norm(h["lm68"][62] - h["lm68"][66])) < 0.0015:
        Vh, Lh, Sh, nz = _zip_mouth(Vh, Lh, Sh, resolve_point(s, "lm_lip_seam"))
        log.append(f"head: the closed mouth zipped ({nz} upper-lip vertices)" if nz else "head: mouth left open")
    with tempfile.TemporaryDirectory(prefix="hifipushie-graft-") as tmp:
        tmp = Path(tmp)
        np.savez(tmp / "body.npz", verts=Vb, loops=Lb, sizes=Sb)
        np.savez(tmp / "head.npz", verts=Vh, loops=Lh, sizes=Sh)
        asset_budget._blender({"mode": "graft_topology", "body": str(tmp / "body.npz"), "head": str(tmp / "head.npz"),
                        "plane_c": list(map(float, c)), "plane_n": list(map(float, n)), "gap": 0.08, "unsub": unsub,
                        "cuts": 2, "out": str(tmp / "out.npz")})
        z = np.load(tmp / "out.npz")
        V2, L2, S2, br = z["verts"].astype(float), z["loops"], z["sizes"], z["bridge"]
    head = ((V2 - c) @ n > 0) | br
    lo = np.min([p.lo for p in prims], 0)
    hi = np.max([p.hi for p in prims], 0)
    voxel = float((hi - lo).max()) / 200
    V2[head] = surface.newton(prims, V2[head], voxel * 0.125, voxel, iterations=12)[0]
    E = edges(L2, S2)
    deg = np.bincount(E.ravel(), minlength=len(V2))
    T = tris(L2, S2)
    rel = br.copy()  # the bridge and two rings round it (the plane-cut rims zigzag) relaxed along the surface
    for _ in range(2):
        rel[E[rel[E[:, 0]] | rel[E[:, 1]]].ravel()] = True
    if "lm_lip_seam" in s["joints"]:  # and the zipped lips' seam (their inner rims folded against each other)
        sm = np.array(resolve_point(s, "lm_lip_seam"))
        mc = np.array(resolve_point(s, "lm_mouth_corner.L"))
        q = V2 - sm
        rel |= (np.abs(q[:, 0]) < abs(mc[0] - sm[0]) + 0.004) & (np.abs(q[:, 2]) < 0.004) & (np.abs(q[:, 1]) < 0.012)
    for _ in range(60):
        N = _vnormals(V2, T)
        lap = _lap(V2, E, deg)
        dv = lap - (lap * N).sum(1, keepdims=True) * N
        V2[rel] = V2[rel] + 0.5 * dv[rel]
        V2[rel] = surface.newton(prims, V2[rel], voxel * 0.125, voxel, iterations=4)[0]
    log.append(f"head: the grafted head's own quads (un-subdivided x{unsub}), bridged at the neck: {len(V2)} verts, "
               f"{len(S2)} faces ({(S2 == 4).mean():.0%} quads)")
    return V2, L2, S2


def _untangle(V, L, S, prims, voxel, frozen, passes=12, log=None):
    """Faces turned against the field (tangles in tight creases): their vertices and two rings round them smoothed
    and re-projected, until none are left or passes run out."""
    T = tris(L, S)
    E = edges(L, S)
    deg = np.bincount(E.ravel(), minlength=len(V))
    nb = [[] for _ in range(len(V))]
    for a, b in E:
        nb[a].append(b)
        nb[b].append(a)
    bad = np.zeros(len(T), bool)
    for it in range(passes):
        bad = turned(V, T, prims) & ~frozen[T].all(1)
        if not bad.any():
            break
        m = np.zeros(len(V), bool)
        m[T[bad].ravel()] = True
        for _ in range(2):
            m[[j for i in np.flatnonzero(m) for j in nb[i]]] = True
        m &= ~frozen
        for _ in range(4):
            V[m] += 0.5 * _lap(V, E, deg)[m]
        V[m] = surface.newton(prims, V[m], voxel * 0.125, voxel, iterations=8)[0]
    if log is not None:
        log.append(f"untangle: {int(bad.sum())} faces still turned after {it + 1} passes")
    return V


def turned(V, T, prims, near=0.0015):
    """Triangles on the surface (centre within `near` of it) whose normal faces against the field's gradient."""
    c = V[T].mean(1)
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    g = sdf.gradient(prims, c, 1e-4)
    on = np.abs(sdf.field_at(prims, c, margin=0.01)) < near
    return ((fn * g).sum(1) < 0) & on
