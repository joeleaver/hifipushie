"""Game garments by PATTERN-SPACE REMESH (opt-in proof, 2026-10-19; docs/notes/cloth.md "garment-game proof").

What game artists do with a Marvelous Designer / CLO drape: the sim is the HIGH poly; the game garment is a separate
clean LOW mesh, retopologised on the FLAT pattern and transferred back onto the drape (the pattern layout is the UV
set), folds baked high -> low into normal / AO maps, hidden inner layers cut away. This module does that from a frozen
drape (cloth.py result pickle), alongside the existing export path (asset.export + lods.py), never changing it:

  drape = load(pkl)                         sim V / F, per-vertex panel id + flat-pattern uv (metres), sew pairs, made parts
  low = remesh(drape, h)                    every panel re-gridded in 2D at edge h, mapped onto the drape through the
                                            panel's own 2D -> 3D (barycentric in the sim triangle), seams resampled ONCE
                                            and shared by both sides (no cracks, no T-junctions); made parts re-gridded
                                            from their own (u, v) grids
  keep = covered_cull(low, covers, poses)   an under garment's faces covered in EVERY pose (rest + the export's clip
                                            frames), eroded by a margin, are deleted (replaces per-triangle cull + push-under);
                                            a cover just BEHIND a vertex also counts (CULL_BACK_REACH)
  build(..., layer_gap=chord_sag(cover LOD, cover drape), gap_rings=1)
                                            the kept-but-covered ring sits the cover's chord sag deeper at THAT LOD (a coarse
                                            cover's faces sink 2 mm at LOD0, 22 mm at LOD3); the bake casts from the ungapped
                                            surface (V_bake). pierce_faces (triangle-triangle) is the gate measure
  game = shell(low, keep, t)                outer faces + explicit inner faces (offset t, reversed: codified A7) + a rim on
                                            free edges only ("thickness on the edges")
  atlas(game)                               the pattern layout packed into one square: UVs, texel density known up front
  LODs = remesh at coarser h                no decimation; every LOD is the same method at a lower density

The bake (normal from the drape, AO with the body) and the GLB are blender_garment_game.py (one Blender job).
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay, cKDTree

from hifipushie import validated

INNER_T = 0.001  # m: the inner (back) faces sit this far inside the outer ones (explicit back faces, codified A7)
CORNER_DEG = 30.0  # a pattern outline turning more than this at a vertex is a corner: free runs keep it
MADE_MIN_ROWS = 8  # a made part (collar, stand, cuff) keeps at least this many rows across: a collar's roll is a fold
# under the cover, not exposed; 0 = the proof4/5 cull, which kept every poking sleeve face because it "looked uncovered")
PIERCE_REACH = 0.015  # m: an under vertex with its cover this close BEHIND it (along -normal) pokes through


# ---------------------------------------------------------------- drape


# ---------------------------------------------------------------- panel boundaries and seams

def _loops(F: np.ndarray) -> list[list[int]]:
    """Closed boundary loops of a triangle set, as vertex lists."""
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    u, c = np.unique(e, axis=0, return_counts=True)
    b = u[c == 1]
    nxt = {}
    for a, z in b:
        nxt.setdefault(int(a), []).append(int(z)); nxt.setdefault(int(z), []).append(int(a))
    seen, loops = set(), []
    for s in nxt:
        if s in seen:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            cand = [x for x in nxt[cur] if x != prev and (x not in seen or (x == s and len(loop) > 2))]
            if not cand:
                break
            prev, cur = cur, cand[0]
            if cur == s:
                break
            loop.append(cur); seen.add(cur)
        loops.append(loop)
    return loops


class MPath:
    """Even-odd point-in-polygon (closed vertex list)."""

    def __init__(self, P: np.ndarray):
        self.A, self.B = P[:-1], P[1:]

    def contains_points(self, Q: np.ndarray, chunk: int = 4000) -> np.ndarray:
        out = np.zeros(len(Q), bool)
        A, B = self.A, self.B
        for a in range(0, len(Q), chunk):
            q = Q[a:a + chunk, None, :]
            cond = (A[None, :, 1] > q[..., 1]) != (B[None, :, 1] > q[..., 1])
            dy = np.where(np.abs(B[:, 1] - A[:, 1]) < 1e-15, 1e-15, B[:, 1] - A[:, 1])
            xi = A[None, :, 0] + (q[..., 1] - A[None, :, 1]) * (B[:, 0] - A[:, 0])[None] / dy[None]
            out[a:a + chunk] = (cond & (q[..., 0] < xi)).sum(1) % 2 == 1
        return out


def _area2(P: np.ndarray) -> float:
    return 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))


def _interp_chain(X: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Points at fractional indices f along the chain X (n, k)."""
    i = np.clip(np.floor(f).astype(int), 0, len(X) - 2)
    t = (f - i)[:, None]
    return X[i] * (1 - t) + X[i + 1] * t


def _arc_fracs(X: np.ndarray, n: int) -> np.ndarray:
    """n+1 fractional chain indices evenly spaced in arc length along X."""
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(X, axis=0), axis=1))])
    return np.interp(np.linspace(0, s[-1], n + 1), s, np.arange(len(X), dtype=float))


def boundaries(drape: dict, h) -> dict:
    """Every kept panel's outer loop split into runs (seam runs and free runs), each resampled at ~h. A seam is
    resampled ONCE (canonical fractions along its pair list) and both sides take those samples: the 3D point is the
    mean of the two sides, so the two panels meet exactly. Returns {piece: {"loop2d", "loop3d", "gid", "free"}}:
    gid = a global id per boundary sample (shared by both sides of a seam), free = per loop edge, not on a seam.
    h: one edge length, or {piece name: h} (a seam takes the finer of its two sides; garment_export: stiff pieces finer)."""
    V, uv, F, pc = drape["V"], drape["uv"], drape["F"], drape["piece"]
    hd = h if isinstance(h, dict) else None
    hp = (lambda n: hd[n]) if hd is not None else (lambda n: h)
    sew, ss = drape["sew"], drape["sew_seam"]
    side = {}  # vertex -> (seam, 'a'|'b', partner)
    for (a, b), s in zip(sew, ss):
        side.setdefault(int(a), []).append((int(s), 0, int(b)))
        side.setdefault(int(b), []).append((int(s), 1, int(a)))

    def lab(u, v):
        for (s, k, _) in side.get(u, []):
            if any(s2 == s and k2 == k for (s2, k2, _) in side.get(v, [])):
                return (s, k)
        return None

    runs = {}
    for i, n in enumerate(drape["names"]):
        if n in drape["drop"]:
            continue
        Fi = F[(pc[F] == i).all(1)]
        loops = _loops(Fi)
        loop = max(loops, key=lambda L: abs(_area2(uv[L])))
        if _area2(uv[loop]) < 0:
            loop = loop[::-1]
        labs = [lab(loop[j], loop[(j + 1) % len(loop)]) for j in range(len(loop))]
        # free runs break at the pattern's corners (a run resampled evenly would cut a hem corner off)
        P = uv[loop]
        d0, d1 = P - np.roll(P, 1, 0), np.roll(P, -1, 0) - P
        cosang = (d0 * d1).sum(1) / np.maximum(np.linalg.norm(d0, axis=1) * np.linalg.norm(d1, axis=1), 1e-15)
        corner = cosang < np.cos(np.radians(CORNER_DEG))
        seg = np.cumsum(corner)
        labs = [("free", int(seg[j])) if lb is None else lb for j, lb in enumerate(labs)]
        # rotate so the loop starts at a label change
        ch = [j for j in range(len(labs)) if labs[j] != labs[j - 1]]
        r0 = ch[0] if ch else 0
        loop, labs = loop[r0:] + loop[:r0], labs[r0:] + labs[:r0]
        rr, j = [], 0
        while j < len(labs):
            k = j
            while k + 1 < len(labs) and labs[k + 1] == labs[j]:
                k += 1
            rr.append((labs[j], [loop[x % len(loop)] for x in range(j, k + 2)]))
            j = k + 1
        runs[n] = rr
    # canonical seam samples, keyed by the frozenset of side-a vertices / side-b vertices
    canon, gid_n = {}, [0]

    def new_ids(m):
        a = list(range(gid_n[0], gid_n[0] + m)); gid_n[0] += m
        return a

    for n, rr in runs.items():
        for lb, ch in rr:
            if lb[0] == "free" or lb[1] != 0:
                continue
            s = lb[0]
            pa = {int(a): int(b) for (a, b), t in zip(sew, ss) if t == s}
            A = np.array(ch); B = np.array([pa[x] for x in ch])
            L = 0.5 * (np.linalg.norm(np.diff(V[A], axis=0), axis=1).sum() + np.linalg.norm(np.diff(V[B], axis=0), axis=1).sum())
            m = max(1, int(round(L / min(hp(n), hp(drape["names"][int(pc[B[0]])])))))
            f = _arc_fracs(0.5 * (V[A] + V[B]), m)
            P = 0.5 * (_interp_chain(V[A], f) + _interp_chain(V[B], f))
            c = {"P": P, "uvA": _interp_chain(uv[A], f), "uvB": _interp_chain(uv[B], f), "gid": new_ids(m + 1)}
            canon[frozenset(A.tolist())] = (c, 0, A[0])
            canon[frozenset(B.tolist())] = (c, 1, B[0])
    out = {}
    for n, rr in runs.items():
        L2, L3, G, FR = [], [], [], []
        for lb, ch in rr:
            key = frozenset(ch)
            if lb[0] != "free" and key in canon:
                c, k, first = canon[key]
                u2 = c["uvB" if k else "uvA"]; P = c["P"]; g = list(c["gid"])
                if ch[0] != first:
                    u2, P, g = u2[::-1], P[::-1], g[::-1]
                free = False
            else:
                X = np.array(ch)
                m = max(1, int(round(np.linalg.norm(np.diff(V[X], axis=0), axis=1).sum() / hp(n))))
                f = _arc_fracs(uv[X], m)
                u2, P, g, free = _interp_chain(uv[X], f), _interp_chain(V[X], f), new_ids(m + 1), True
            L2.append(u2[:-1]); L3.append(P[:-1]); G += g[:-1]; FR += [free] * (len(u2) - 1)
        out[n] = {"loop2d": np.concatenate(L2), "loop3d": np.concatenate(L3), "gid": np.array(G), "free": np.array(FR)}
    # run ends: a corner where seams of 3 panels meet carries different ids on each run: weld those within 3 mm
    return out


# ---------------------------------------------------------------- remesh

def _bary_map(uvp: np.ndarray, Q: np.ndarray, Vp: np.ndarray, Fp: np.ndarray) -> np.ndarray:
    """3D points for 2D points Q through the panel's sim triangles (uvp -> Vp): barycentric in the containing
    triangle (the nearest one, clamped, at the rim)."""
    A, B, C = uvp[Fp[:, 0]], uvp[Fp[:, 1]], uvp[Fp[:, 2]]
    tree = cKDTree((A + B + C) / 3)
    _, cand = tree.query(Q, k=min(12, len(Fp)))
    best = np.full(len(Q), -np.inf); W = np.zeros((len(Q), 3)); T = np.zeros(len(Q), int)
    for j in range(cand.shape[1]):
        t = cand[:, j]
        v0, v1, v2 = B[t] - A[t], C[t] - A[t], Q - A[t]
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        den = np.where(np.abs(den) < 1e-16, 1e-16, den)
        b1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
        b2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
        w = np.stack([1 - b1 - b2, b1, b2], 1)
        score = w.min(1)
        better = score > best
        best[better], W[better], T[better] = score[better], w[better], t[better]
    W = np.clip(W, 0, None); W /= W.sum(1, keepdims=True)
    return np.einsum("nk,nkd->nd", W, Vp[Fp[T]])


def remesh_panel(drape: dict, name: str, bd: dict, h: float, lines=()) -> dict:
    """One panel re-gridded in 2D at edge ~h (boundary samples + a hex grid inside, Delaunay, trimmed to the
    panel), mapped onto the drape. lines: 2D polylines inside the panel (fold lines: a collar's roll, a pressed front
    band) sampled at h / 2 and kept as vertex rows, so a fold isn't cut by a chord (garment_export). Returns {"V", "uv", "T", "gid" (boundary vertices; -1 inside), "free_edges"}."""
    i = drape["names"].index(name)
    pc, F = drape["piece"], drape["F"]
    Fi = F[(pc[F] == i).all(1)]
    loop2, loop3 = bd["loop2d"], bd["loop3d"]
    nb = len(loop2)
    poly = MPath(np.vstack([loop2, loop2[:1]]))
    lo, hi = loop2.min(0), loop2.max(0)
    dy = h * np.sqrt(3) / 2
    ys = np.arange(lo[1] + dy / 2, hi[1], dy)
    pts = [np.stack([np.arange(lo[0] + (h / 2 if r % 2 else 0), hi[0], h), np.full_like(np.arange(lo[0] + (h / 2 if r % 2 else 0), hi[0], h), y)], 1)
           for r, y in enumerate(ys)]
    G = np.concatenate(pts) if pts else np.zeros((0, 2))
    G = G[poly.contains_points(G)] if len(G) else G
    dense = np.concatenate([_interp_chain(np.vstack([loop2, loop2[:1]]), np.linspace(0, nb, nb * 10 + 1))])
    if len(G):
        dd, _ = cKDTree(dense).query(G)
        G = G[dd > 0.6 * h]
    Ls = [np.asarray(L, float) for L in lines if len(L) > 1]
    if Ls:
        S = np.concatenate([_interp_chain(L, np.linspace(0, len(L) - 1, max(2, int(np.ceil(
            np.linalg.norm(np.diff(L, axis=0), axis=1).sum() / (0.5 * h))) + 1))) for L in Ls])
        S = S[poly.contains_points(S)]
        if len(S):
            S = S[cKDTree(dense).query(S)[0] > 0.3 * h]
        if len(G) and len(S):
            G = G[cKDTree(S).query(G)[0] > 0.45 * h]
        G = np.vstack([G, S]) if len(S) else G
    P2 = np.vstack([loop2, G])
    tri = Delaunay(P2).simplices
    cen = P2[tri].mean(1)
    ok = poly.contains_points(cen)
    # chords between non-neighbouring boundary samples must run inside the panel
    for a, b in ((0, 1), (1, 2), (2, 0)):
        ia, ib = tri[:, a], tri[:, b]
        chord = (ia < nb) & (ib < nb) & ~(((ia - ib) % nb == 1) | ((ib - ia) % nb == 1))
        mid = 0.5 * (P2[ia] + P2[ib])
        dmid, _ = cKDTree(dense).query(mid)
        ok &= ~chord | (poly.contains_points(mid) & (dmid > 0.05 * h))
    tri = tri[ok]
    # same winding as the sim's triangles of this panel (their uv orientation)
    su = drape["uv"]
    sgn_sim = np.sign(np.median([_area2(su[f]) for f in Fi[:200]]))
    if np.sign(np.median([_area2(P2[t]) for t in tri[:200]])) != sgn_sim:
        tri = tri[:, ::-1]
    V3 = np.vstack([loop3, _bary_map(su, G, drape["V"], Fi) if len(G) else np.zeros((0, 3))])
    gid = np.concatenate([bd["gid"], -np.ones(len(G), int)])
    e = set(map(tuple, np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), 1).tolist()))
    missing = sum((min(j, (j + 1) % nb), max(j, (j + 1) % nb)) not in e for j in range(nb))
    free_e = [(j, (j + 1) % nb) for j in range(nb) if bd["free"][j]]
    return {"V": V3, "uv": P2, "T": tri, "gid": gid, "free_edges": np.array(free_e, int).reshape(-1, 2),
            "missing_boundary_edges": int(missing), "name": name}


def outward(P: np.ndarray, N: np.ndarray, body: np.ndarray) -> np.ndarray:
    """N with its sign turned away from the nearest body point (orientation-free tests)."""
    _, i = cKDTree(body).query(P)
    return N * np.where((N * (P - body[i])).sum(1) < 0, -1.0, 1.0)[:, None]


def _weld_corners(pieces: list[dict], tol: float = 0.003) -> None:
    """Seam samples share ids by construction; run ends where 3 panels meet carry separate ids on each run: give
    boundary samples within tol of each other one id and one (mean) position."""
    idx = [(k, j) for k, p in enumerate(pieces) for j in np.nonzero(p["gid"] >= 0)[0]]
    if not idx:
        return
    X = np.array([pieces[k]["V"][j] for k, j in idx])
    g = np.array([pieces[k]["gid"][j] for k, j in idx])
    par = {int(x): int(x) for x in g}

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for a, b in cKDTree(X).query_pairs(tol):
        ra, rb = f(int(g[a])), f(int(g[b]))
        if ra != rb:
            par[ra] = rb
    root = np.array([f(int(x)) for x in g])
    acc = {}
    for r, x in zip(root, X):
        acc.setdefault(r, []).append(x)
    for (k, j), r in zip(idx, root):
        pieces[k]["gid"][j] = r
        pieces[k]["V"][j] = np.mean(acc[r], 0)


# ---------------------------------------------------------------- one mesh, normals, layers

def merged(pieces: list[dict], keep: dict | None = None) -> dict:
    """Pieces as one split-vertex mesh: V, uv (pattern metres), T, piece id per vertex, weld (vertex -> welded id:
    seams share one), N (normals averaged over welded vertices). keep {piece name: face mask}."""
    Vs, Us, Ts, P, W, off, wn = [], [], [], [], [], 0, 0
    for k, p in enumerate(pieces):
        T = p["T"] if keep is None else p["T"][keep[p["name"]]]
        Vs.append(p["V"]); Us.append(p["uv"]); Ts.append(T + off); P.append(np.full(len(p["V"]), k))
        w = np.where(p["gid"] >= 0, p["gid"] + 10 ** 7, np.arange(len(p["V"])) + off)
        W.append(w); off += len(p["V"])
    V, uv, T, pid, w = np.vstack(Vs), np.vstack(Us), np.vstack(Ts), np.concatenate(P), np.concatenate(W)
    _, weld = np.unique(w, return_inverse=True)
    return {"V": V, "uv": uv, "T": T, "piece": pid, "weld": weld, "N": normals(V, T, weld)}


def normals(V: np.ndarray, T: np.ndarray, weld: np.ndarray | None = None) -> np.ndarray:
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    n = np.zeros_like(V)
    for c in range(3):
        np.add.at(n, T[:, c], fn)
    if weld is not None:
        acc = np.zeros((weld.max() + 1, 3)); np.add.at(acc, weld, n); n = acc[weld]
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def ray_hits(O: np.ndarray, D: np.ndarray, V: np.ndarray, T: np.ndarray, reach: float, chunk: int = 2000) -> np.ndarray:
    """Per ray (origin O, unit dir D), the distance to the first triangle of (V, T) within reach (inf: none)."""
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    cen = (A + B + C) / 3
    rmax = float(np.max(np.linalg.norm(np.stack([A, B, C], 1) - cen[:, None], axis=2), initial=0.0))
    tree = cKDTree(cen)
    res = np.full(len(O), np.inf)
    for a in range(0, len(O), chunk):
        idx = np.arange(a, min(a + chunk, len(O)))
        near = tree.query_ball_point(O[idx] + D[idx] * reach / 2, reach / 2 + rmax)
        vi = np.repeat(idx, [len(x) for x in near])
        if not len(vi):
            continue
        ti = np.concatenate([np.asarray(x, np.int64) for x in near])
        e1, e2, d = B[ti] - A[ti], C[ti] - A[ti], D[vi]
        pv = np.cross(d, e2); det = (e1 * pv).sum(1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = O[vi] - A[ti]
        u = (tv * pv).sum(1) * inv
        qv = np.cross(tv, e1)
        w = (d * qv).sum(1) * inv
        t = (e2 * qv).sum(1) * inv
        hit = ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (t > 1e-6) & (t < reach)
        np.minimum.at(res, vi[hit], t[hit])
    return res


def pierce_count(under_V, under_T, cover_V, cover_T, body, reach: float = PIERCE_REACH, weld=None) -> int:
    """Under vertices with a cover surface BEHIND them (toward the body, within reach): poking through the cover."""
    used = np.unique(under_T)
    N = outward(under_V, normals(under_V, under_T, weld), body)
    t = ray_hits(under_V[used], -N[used], cover_V, cover_T, reach)
    return int(np.isfinite(t).sum())


def _seg_tri(P0: np.ndarray, P1: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    """Per row: does segment P0 -> P1 cross triangle ABC (strictly inside both, Moller-Trumbore)?"""
    d = P1 - P0
    e1, e2 = B - A, C - A
    pv = np.cross(d, e2); det = (e1 * pv).sum(1)
    ok = np.abs(det) > 1e-18
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    tv = P0 - A
    u = (tv * pv).sum(1) * inv
    qv = np.cross(tv, e1)
    w = (d * qv).sum(1) * inv
    t = (e2 * qv).sum(1) * inv
    return ok & (u > eps) & (w > eps) & (u + w < 1 - eps) & (t > eps) & (t < 1 - eps)


def crossing_faces(under_V, under_T, cover_V, cover_T, chunk: int = 200000) -> np.ndarray:
    """Face mask of `under`: faces that INTERSECT a face of the cover (triangle-triangle, exact: two non-coplanar
    triangles intersect iff an edge of one crosses the other). Unlike a per-vertex test it sees an under face that
    pokes through between vertices, where the two layers' chords cross (coarse re-grids on different sample lines)."""
    Au, Bu, Cu = under_V[under_T[:, 0]], under_V[under_T[:, 1]], under_V[under_T[:, 2]]
    Ac, Bc, Cc = cover_V[cover_T[:, 0]], cover_V[cover_T[:, 1]], cover_V[cover_T[:, 2]]
    cu, cc = (Au + Bu + Cu) / 3, (Ac + Bc + Cc) / 3
    ru = np.max(np.linalg.norm(np.stack([Au, Bu, Cu], 1) - cu[:, None], axis=2), axis=1)
    rc = np.max(np.linalg.norm(np.stack([Ac, Bc, Cc], 1) - cc[:, None], axis=2), axis=1)
    near = cKDTree(cc).query_ball_point(cu, ru + float(rc.max(initial=0.0)))
    fu = np.repeat(np.arange(len(under_T)), [len(x) for x in near])
    out = np.zeros(len(under_T), bool)
    if not len(fu):
        return out
    fc = np.concatenate([np.asarray(x, np.int64) for x in near])
    keep = np.linalg.norm(cu[fu] - cc[fc], axis=1) <= ru[fu] + rc[fc]
    fu, fc = fu[keep], fc[keep]
    for a in range(0, len(fu), chunk):
        i, j = fu[a:a + chunk], fc[a:a + chunk]
        Tu = (Au[i], Bu[i], Cu[i]); Tc = (Ac[j], Bc[j], Cc[j])
        hit = np.zeros(len(i), bool)
        for x, y in ((0, 1), (1, 2), (2, 0)):
            hit |= _seg_tri(Tu[x], Tu[y], *Tc)  # an under edge through the cover face
            hit |= _seg_tri(Tc[x], Tc[y], *Tu)  # a cover edge through the under face
        out[i[hit]] = True
    return out


def _sheet(n: int, size: float, z) -> tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(0, size, n)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = z(X, Y) if callable(z) else np.full_like(X, z)
    q = np.arange(n * n).reshape(n, n)
    a, b, c, d = q[:-1, :-1].ravel(), q[1:, :-1].ravel(), q[1:, 1:].ravel(), q[:-1, 1:].ravel()
    return np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1), np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])


def _selftest_pierce_faces():
    # two sheets crossing BETWEEN the under sheet's vertices: a coarse under sheet (10 cm grid, z = 0) and a fine cover
    # 3 mm above it everywhere except a dip to 4 mm below in a 3 cm disc centred between under vertices
    Vu, Tu = _sheet(5, 0.4, 0.0)
    c = np.array([0.15, 0.15])
    Vc, Tc = _sheet(81, 0.4, lambda X, Y: np.where(np.hypot(X - c[0], Y - c[1]) < 0.03, -0.004, 0.003))
    body = np.c_[Vu[:, :2], np.full(len(Vu), -0.1)]
    assert pierce_count(Vu, Tu, Vc, Tc, body) == 0, "the vertex test was expected to miss this case"
    n = pierce_faces(Vu, Tu, Vc, Tc)
    assert n >= 1, n
    # two parallel sheets 2 mm apart (different grids, offset sample lines): nothing crosses
    Vc2, Tc2 = _sheet(23, 0.41, 0.002)
    assert pierce_faces(Vu, Tu, Vc2 - [0.005, 0.005, 0], Tc2) == 0
    # a cover that dives through the whole under sheet: every under face under the crossing line is found
    Vc3, Tc3 = _sheet(9, 0.42, lambda X, Y: 0.05 * (X - 0.223))
    assert pierce_faces(Vu, Tu, Vc3 - [0.01, 0.007, 0], Tc3) == 8  # the column of 2 x 4 faces the plane x = 0.213 crosses


@validated.known_answer(_selftest_pierce_faces)
def pierce_faces(under_V, under_T, cover_V, cover_T) -> int:
    """Under faces that cross the cover (crossing_faces): the gate measure for an under layer showing through."""
    return int(crossing_faces(under_V, under_T, cover_V, cover_T).sum())


# ---------------------------------------------------------------- shell, atlas

def shell(m: dict, full_T: np.ndarray | None = None, t: float = INNER_T) -> dict:
    """Outer faces + explicit inner faces (offset t inward, reversed) + a rim strip on the garment's free edges
    (hems, lapel and collar edges, cuffs: boundary edges of full_T, the garment before any cull; an edge a cull opened
    is hidden and gets no rim). The inner copy shares the outer's uvs."""
    V, T, N = m["V"], m["T"], m["N"]
    n = len(V)
    Vi = V - N * t
    rims = []
    # free edges: boundary edges of the kept faces that are not seams (a seam edge has both ends welded to another piece)
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    key = np.sort(m["weld"][e], 1)
    u, inv, c = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    bnd = c[inv] == 1
    if full_T is not None:
        ef = np.concatenate([full_T[:, [0, 1]], full_T[:, [1, 2]], full_T[:, [2, 0]]])
        kf, cf = np.unique(np.sort(m["weld"][ef], 1), axis=0, return_counts=True)
        free = {tuple(x) for x in kf[cf == 1].tolist()}
        bnd &= np.array([tuple(x) in free for x in key.tolist()])
    for a, b in e[bnd]:
        rims.append([a, b, b + n]); rims.append([a, b + n, a + n])
    Tr = np.array(rims, int).reshape(-1, 3)
    out_T = np.vstack([T, T[:, ::-1] + n, Tr[:, ::-1]])
    return {"V": np.vstack([V, Vi]), "uv": np.vstack([m["uv"], m["uv"]]), "T": out_T,
            "N": np.vstack([N, -N]), "outer_faces": len(T), "inner_faces": len(T), "rim_faces": len(Tr)}


def atlas(pieces: list[dict], gap: float = 0.02) -> tuple[list[np.ndarray], float]:
    """The pattern layout packed into one square (shelf packing, pattern scale kept): per piece uv in [0, 1], and the
    square's side in metres (texel density = px / side)."""
    boxes = []
    for p in pieces:
        lo, hi = p["uv"].min(0), p["uv"].max(0)
        boxes.append((lo, hi - lo))
    area = sum((s[0] + gap) * (s[1] + gap) for _, s in boxes)
    side = np.sqrt(area) * 1.05
    for _ in range(40):
        x = y = rowh = 0.0
        pos = []
        order = sorted(range(len(boxes)), key=lambda k: -boxes[k][1][1])
        pos = [None] * len(boxes)
        for k in order:
            w, hh = boxes[k][1]
            if x + w > side:
                x, y, rowh = 0.0, y + rowh + gap, 0.0
            pos[k] = (x, y); x += w + gap; rowh = max(rowh, hh)
        if y + rowh <= side:
            break
        side *= 1.04
    uvs = [((p["uv"] - boxes[k][0]) + np.array(pos[k])) / side for k, p in enumerate(pieces)]
    return uvs, side


# ---------------------------------------------------------------- the MCP path (server.game_garment)

