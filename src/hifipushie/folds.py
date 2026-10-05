"""Fold lines: a crease along a line of a pattern piece with a rest angle and a strength, for any garment (a collar's
roll, a lapel's roll line, a placket or hem turned under, a pleat, a cuff turned back).

Garment key `folds` (a design table in cloth_designs.json may carry `folds` too):
  {"piece": name,
   "line": a line name of the piece | [pointOrMark, pointOrMark] | [[x, y], ...] (m) |
           {"edge": "a>b", "offset": m} (parallel to that edge of the piece, offset into it) | {"mid": "x" | "y"},
   "angle": deg, the dihedral on the outside (the face placed away from the body): 180 flat; 0 folded right over onto
            the outside (a collar's fall over its stand, a lapel onto the chest, a cuff turned back); 360 folded right
            under (a hem, a facing, a placket),
   "kind": "press" (a sharp crease: one row of hinges) | "roll" (the turn spread over an arc of `radius`, default 3 mm:
           as many rows as the mesh can carry),
   "strength": 0..1 (default 1 press, 0.5 roll): how hard the crease holds its angle (hinge bending x (1 + PRESS x
           strength)),
   "flap": optional point/mark name on the side that turns (default: the side with less sewn edge, then the smaller),
   "name": label}

What a fold is here:
- mesh (cloth.mesh): a row of vertices on the line (rows over the arc for a roll), so mesh edges run along the crease,
  the line's ends on outline vertices. `M["folds"]` records each fold's rows.
- placement (cloth.place -> `apply`): the piece is laid on its wrap unfolded, then the flap is turned about the row as
  far as the fold asks or as it clears what lies under it (`obstacles`: the piece's own base side, the body, other
  pieces) by `lay`: a fall lies on its stand, a lapel on the chest, nearly touching. The turn is found per station
  along the line (a collar's fall opens more over the shoulders than at the back).
- rest: a solver resting on the placement (Blender; ZOZO's made pieces) keeps the placed fold. A solver resting on the
  flat pattern (ZOZO's ordinary cloth) gets the hinge rest angles from `bend_reference` (the flat pattern folded at
  its lines) and the row's bending stiffness from `weights`.
A fold must run from outline to outline (a crease that ends inside a piece is a cone, which a flat rest can't hold):
pleats that die out stay seam gaps.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

from . import pattern

PRESS = 20.0  # a pressed crease's hinge bending, as a multiple of the cloth's, at strength 1
REST_TURN = math.radians(170.0)  # the most a hinge's rest angle turns (a full 180 is the two faces in one plane)
PLACE_TURN = math.radians(178.0)
ROLL_RADIUS = 0.003


def entries(Bp: dict) -> list:
    """The folds of a drafted garment (`Bp["folds"]`), with defaults filled in."""
    out = []
    for i, f in enumerate(Bp.get("folds") or []):
        if f["piece"] not in Bp["pieces"]:
            continue
        kind = f.get("kind", "press")
        if kind not in ("press", "roll"):
            raise ValueError(f"fold {f.get('name', i)}: kind is \"press\" or \"roll\", got {kind!r}")
        out.append(dict(f, kind=kind, angle=float(f.get("angle", 0.0)),
                        strength=float(f.get("strength", 1.0 if kind == "press" else 0.5)),
                        radius=float(f.get("radius", ROLL_RADIUS if kind == "roll" else 0.0)),
                        name=f.get("name") or f"{f['piece']}:fold{i}"))
    return out


def side_dist(L: np.ndarray, Q: np.ndarray) -> tuple:
    """Points Q against the polyline L: (signed distance, + on the left of its direction; arc position of the foot;
    segment index; fraction along it)."""
    a, b = L[:-1], L[1:]
    ab = b - a
    ln = np.maximum(np.linalg.norm(ab, axis=1), 1e-12)
    cum = np.r_[0, np.cumsum(ln)]
    sd, u, si, fr = (np.zeros(len(Q)) for _ in range(4))
    for s in range(0, len(Q), 2000):
        q = Q[s:s + 2000, None]
        t = np.clip(((q - a[None]) * ab[None]).sum(-1) / (ln * ln)[None], 0, 1)
        foot = a[None] + t[..., None] * ab[None]
        d = np.linalg.norm(q - foot, axis=-1)
        j = np.argmin(d, axis=1)
        r = np.arange(len(j))
        cr = ab[j, 0] * (Q[s:s + 2000, 1] - a[j, 1]) - ab[j, 1] * (Q[s:s + 2000, 0] - a[j, 0])
        sd[s:s + 2000] = np.where(cr >= 0, 1, -1) * d[r, j]
        fr[s:s + 2000] = t[r, j]
        si[s:s + 2000] = j
        u[s:s + 2000] = cum[j] + t[r, j] * ln[j]
    return sd, u, si.astype(np.int64), fr


def rows(pcs: dict, f: dict, h: float, sewn: np.ndarray | None = None, min_width: float = 0.0) -> dict:
    """A fold's rows in its piece's pattern coordinates: {"lines": [polyline, ...] (the line, then the rows a roll adds
    toward the flap), "sign": the flap's side of the line (+1 left of its direction), "turn": rad per row (+ = over
    onto the outside)}. sewn: sample points of the piece's sewn edges (they decide the flap: the side with less)."""
    pc = pcs[f["piece"]]
    P = pc["P"]
    L = pattern.fold_line(pcs, f)
    if "flap" in f:
        q = P[pattern.index_of(pc, f["flap"])] if f["flap"] in pc["names"] else np.asarray(pc["marks"][f["flap"]], float)
        sign = 1.0 if side_dist(L, q[None])[0][0] >= 0 else -1.0
    else:
        ns = [0, 0]
        if sewn is not None and len(sewn):
            s = side_dist(L, sewn)[0]
            s = s[np.abs(s) > 1e-4]
            ns = [int((s > 0).sum()), int((s < 0).sum())]
        if ns[0] != ns[1] and max(ns) > 0:
            sign = 1.0 if ns[0] < ns[1] else -1.0
        else:  # the smaller side
            lo, hi = P.min(0), P.max(0)
            gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 40), np.linspace(lo[1], hi[1], 40))
            G = np.c_[gx.ravel(), gy.ravel()]
            G = G[pattern._poly_inside(P, G)]
            s = side_dist(L, G)[0]
            sign = 1.0 if (s > 0).sum() <= (s < 0).sum() else -1.0
    turn = math.radians(180.0 - float(f["angle"]))
    # a roll: k hinges each turning turn / k, the rows between them `s` apart so the polygon is as wide as the arc's
    # circle (2 x radius for a full turn); as many rows as stay max(0.2 h, 2.5 mm) apart (closer rows are slivers), so
    # a tight roll on a coarse mesh is one crease
    k, s = 1, 0.0
    r = float(f.get("radius", 0.0))
    if f.get("kind") == "roll" and r > 0:
        for kk in range(5, 1, -1):
            den = sum(math.sin(j * abs(turn) / kk) for j in range(1, kk))
            sk = r * (1 - math.cos(abs(turn))) / max(den, 1e-9)
            if sk >= max(0.2 * h, 0.0025):
                k, s = kk, sk
                break
    if min_width > 0 and abs(turn) > math.pi / 2 and s * max(k - 1, 1) < min_width:
        # a solver whose layers can't lie closer than its collision distance (Blender): a U two rows across
        k, s = 2, min_width
    lines = [L]
    t = np.gradient(L, axis=0)
    nrm = np.c_[-t[:, 1], t[:, 0]]
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    tot = pattern.length(L)
    for j in range(1, k):
        Lj = L + sign * j * s * nrm
        ins = pattern._poly_inside(P, Lj)
        if ins.mean() < 0.8:  # the roll would run off the piece (a fold right beside the outline): fewer rows
            break
        Lj = pattern.fold_line(pcs, {"piece": f["piece"], "line": Lj.tolist(), "reach": 2 * k * s + 0.015})
        if pattern.length(Lj) < 0.8 * tot:
            break
        lines.append(Lj)
    return {"lines": lines, "sign": sign, "turn": turn / len(lines)}


def row_samples(lines: list, ring: np.ndarray, h: float) -> list:
    """Where each row's vertices go ([(m, 2) arrays], ends included): every 0.8 h, but beside the outline (within
    0.7 h) at the feet of the outline's own vertices, so the strip between is a ladder and the row's points stay
    joined by edges. Rows after the first take the first's fractions."""
    L = lines[0]
    sd, u, _, _ = side_dist(L, ring)
    tot = float(np.sum(np.linalg.norm(np.diff(L, axis=0), axis=1)))
    tw = np.sort(u[(np.abs(sd) < 0.7 * h) & (u > 0.35 * h) & (u < tot - 0.35 * h)])
    n = max(1, int(round(tot / (0.8 * h))))
    uni = np.linspace(0, tot, n + 1)[1:-1]
    if len(tw):
        uni = uni[np.min(np.abs(uni[:, None] - tw[None]), axis=1) > 0.5 * h]
    us = np.sort(np.r_[tw, uni])
    keep = []
    for x in us:  # no two closer than 0.35 h
        if not keep or x - keep[-1] > 0.35 * h:
            keep.append(x)
    fr = np.r_[0.0, np.asarray(keep) / tot, 1.0]
    out = []
    for Lr in lines:
        seg = np.linalg.norm(np.diff(Lr, axis=0), axis=1)
        cum = np.r_[0, np.cumsum(seg)]
        s = fr * cum[-1]
        out.append(np.c_[np.interp(s, cum, Lr[:, 0]), np.interp(s, cum, Lr[:, 1])])
    return out


def force_edges(X: np.ndarray, tri: np.ndarray, pairs: list) -> tuple[np.ndarray, int]:
    """Triangles with each pair (a, b) made an edge where one flip does it (the two triangles on the edge crossing
    a-b). Returns (triangles, pairs still missing)."""
    tri = tri.copy()
    missing = 0
    for a, b in pairs:
        has = ((tri == a).any(1) & (tri == b).any(1)).any()
        if has:
            continue
        ta = np.where((tri == a).any(1))[0]
        done = False
        for i in ta:
            c, d = [v for v in tri[i] if v != a]
            j = np.where((tri == c).any(1) & (tri == d).any(1) & (tri == b).any(1))[0]
            if len(j):
                # a, b on opposite sides of c-d and c, d on opposite sides of a-b: the quad is convex
                cr = lambda p, q, r: (X[q, 0] - X[p, 0]) * (X[r, 1] - X[p, 1]) - (X[q, 1] - X[p, 1]) * (X[r, 0] - X[p, 0])
                if cr(a, b, c) * cr(a, b, d) < 0 and cr(c, d, a) * cr(c, d, b) < 0:
                    t1, t2 = [a, c, b], [a, b, d]
                    for t in (t1, t2):
                        if cr(t[0], t[1], t[2]) < 0:
                            t[1], t[2] = t[2], t[1]
                    tri[i], tri[j[0]] = t1, t2
                    done = True
                    break
        missing += not done
    return tri, missing


# ---------------------------------------------------------------- turning a flap


def _geom(M: dict, fd: dict) -> dict:
    """Per row of a fold: the flap's vertices, each one's foot on the row (segment, fraction, arc position) and its
    distance from the first row (pattern coordinates)."""
    if "_g" in fd:
        return fd["_g"]
    k = M["names"].index(fd["piece"])
    sel = np.where(M["piece"] == k)[0]
    uv = M["uv"]
    out = []
    in_rows = np.zeros(len(uv), bool)
    d0 = None
    for r, row in enumerate(fd["rows"]):
        in_rows[row] = True
        L = uv[row]
        sd, u, si, fr = side_dist(L, uv[sel])
        if d0 is None:
            d0 = np.zeros(len(uv))
            d0[sel] = np.abs(sd)
        flap = (fd["sign"] * sd > 1e-7) & ~in_rows[sel]
        seg = np.linalg.norm(np.diff(L, axis=0), axis=1)
        out.append({"row": np.asarray(row), "v": sel[flap], "si": si[flap], "fr": fr[flap], "u": u[flap],
                    "len": float(seg.sum())})
    F = M["F"]
    Fp = F[M["piece"][F[:, 0]] == k]
    fl0 = np.zeros(len(uv), bool)
    fl0[out[0]["v"]] = True
    g = {"rows": out, "d0": d0, "base_tris": Fp[~fl0[Fp].any(1)], "tris": Fp, "flap0": fl0, "sel": sel}
    fd["_g"] = g
    return g


def _normals(X: np.ndarray, F: np.ndarray, n: int) -> np.ndarray:
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    N = np.zeros((n, 3))
    for c in range(3):
        np.add.at(N, F[:, c], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def _rodrigues(V: np.ndarray, W: np.ndarray, th: np.ndarray) -> np.ndarray:
    c, s = np.cos(th)[:, None], np.sin(th)[:, None]
    return V * c + np.cross(W, V) * s + W * (W * V).sum(1, keepdims=True) * (1 - c)


def turn_flap(X: np.ndarray, M: dict, fd: dict, t, face: float = 1.0) -> np.ndarray:
    """X with the fold's flap turned about its rows by t (0..1, a number or per vertex) of the fold's turn."""
    g = _geom(M, fd)
    X = X.copy()
    tv = np.full(len(X), float(t)) if np.isscalar(t) else np.asarray(t, float)
    for r in g["rows"]:
        row = r["row"]
        Pr = X[row]
        T = np.gradient(Pr, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
        v, si, fr = r["v"], r["si"], r["fr"][:, None]
        Q = Pr[si] * (1 - fr) + Pr[si + 1] * fr
        W = T[si] * (1 - fr) + T[si + 1] * fr
        W /= np.maximum(np.linalg.norm(W, axis=1, keepdims=True), 1e-12)
        # the flap lies on side `sign` of the row's direction: turning it toward the outside (the pattern face's normal
        # x face) is a rotation about sign x face x the row's direction
        X[v] = Q + _rodrigues(X[v] - Q, fd["sign"] * face * W, fd["turn"] * tv[v])
    return X


def samples(X: np.ndarray, F: np.ndarray, face: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Points on a triangle mesh (corners, edge midpoints, centre) and its outward normal at each (triangle normal x
    face)."""
    if not len(F):
        return np.zeros((0, 3)), np.zeros((0, 3))
    w = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1 / 3, 1 / 3, 1 / 3], [.5, .5, 0], [0, .5, .5], [.5, 0, .5]])
    P = np.einsum("kw,fwd->fkd", w, X[F]).reshape(-1, 3)
    n = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return P, np.repeat(face * n, len(w), axis=0)


def apply(X: np.ndarray, M: dict, fd: dict, face: float = 1.0, obstacles: list | None = None, lay: float = 0.002,
          t_max: float | None = None, t_min: float = 0.0, steps: int = 40, own_base: bool = True,
          wedge: float = 0.08) -> tuple:
    """The fold's flap turned as far as the fold asks, or as far as it stays clear of what is under it. obstacles:
    [(points, outward normals)] the flap stays outside of (the body, other pieces) by `lay`; the piece's own base side
    is one too (the flap lies on it: outside for a fold over, inside for a fold under). The turn is chosen per station
    along the line and eased along it. Returns (X, {"t": share of the turn per station, "turn_deg": [min, median,
    max]})."""
    g = _geom(M, fd)
    k = len(g["rows"])
    full = abs(fd["turn"]) * k
    # (a U of two rows or more can turn all the way: its layers are the U apart; one crease stops at PLACE_TURN)
    t_hi = (1.0 if k > 1 else min(1.0, PLACE_TURN / max(full, 1e-9))) if t_max is None else t_max
    flap = g["rows"][0]["v"]
    over = 1.0 if fd["turn"] >= 0 else -1.0
    # (points, normals, side, reach): a flap vertex is against an obstacle only where it stands over it (within
    # `reach` of a sample across the surface: past a band's edge its plane says nothing)
    hm = float(np.median(np.linalg.norm(X[g["tris"][:, 0]] - X[g["tris"][:, 1]], axis=1)))
    obs = [(np.asarray(o[0]), np.asarray(o[1]), 1.0, float(o[2]) if len(o) > 2 else 0.4 * hm) for o in (obstacles or [])
           if len(o[0])]
    if own_base and len(g["base_tris"]):
        p, n = samples(X, g["base_tris"], face)
        obs.append((p, n, over, 0.4 * hm))
    if not obs or not len(flap):
        Xo = turn_flap(X, M, fd, t_hi, face)
        return Xo, {"t": [t_hi], "turn_deg": [round(math.degrees(full * t_hi), 1)] * 3}
    trees = [(cKDTree(p), p, n, s, rc) for p, n, s, rc in obs]
    # (a single crease is a wedge: the flap may come as near its base as a wedge of slope `wedge` allows (4.5 deg; a
    # sim's start wants its first ring of vertices a contact gap off the base: place() sets it from the triangle
    # size), `lay` off it at most)
    need = np.minimum(lay, wedge * g["d0"][flap])
    u = g["rows"][0]["u"]
    tot = g["rows"][0]["len"]
    nb = max(1, int(round(tot / max(1e-6, np.median(np.linalg.norm(np.diff(M["uv"][g["rows"][0]["row"]], axis=0), axis=1))))))
    b = np.minimum((u / max(tot, 1e-9) * nb).astype(int), nb - 1)
    cand = t_hi - (t_hi - t_min) * np.linspace(0, 1, steps) ** 2  # (finer near the full turn)
    best = np.full(nb, np.nan)
    for t in cand:
        Xt = turn_flap(X, M, fd, t, face)[flap]
        ok = np.ones(len(flap), bool)
        for tree, p, n, s, rc in trees:
            d, i = tree.query(Xt)
            sd = ((Xt - p[i]) * n[i]).sum(1)
            tang = np.sqrt(np.maximum(d * d - sd * sd, 0.0))
            ok &= (tang > rc) | (sd * s >= need) | (d > 0.03)
        bad = np.bincount(b[~ok], minlength=nb) > 0
        new = np.isnan(best) & ~bad
        best[new] = t
        if not np.isnan(best).any():
            break
    best = np.where(np.isnan(best), t_min, best)
    # eased along the line: never more turned than a neighbour allows by much (the flap is one piece of cloth)
    sm = best.copy()
    for _ in range(2):
        pad = np.r_[sm[:1], sm, sm[-1:]]
        sm = np.minimum(sm, (pad[:-2] + sm + pad[2:]) / 3 + 0.02)
    pad = np.r_[sm[:1], sm, sm[-1:]]
    sm = np.minimum(sm, (pad[:-2] + 2 * sm + pad[2:]) / 4)
    tv = np.zeros(len(X))
    cen = (np.arange(nb) + 0.5) / nb * tot
    for r in g["rows"]:
        tv[r["v"]] = np.interp(r["u"] * tot / max(r["len"], 1e-9), cen, sm)
    Xo = turn_flap(X, M, fd, tv, face)
    deg = np.degrees(full * sm)
    return Xo, {"t": sm.round(3).tolist(), "turn_deg": [round(float(v), 1) for v in (deg.min(), np.median(deg), deg.max())]}


def bend_reference(M: dict, ref: np.ndarray, faces: dict | None = None, skip: set | None = None) -> np.ndarray:
    """A bending rest reference (positions hinge rest angles are read from): `ref` (the flat pattern for ordinary
    cloth) with every fold's flap turned to its rest angle. Pieces in `skip` (made pieces, resting as placed: their
    placement holds the fold) are left."""
    out = ref.copy()
    for fd in M.get("folds") or []:
        if skip and fd["piece"] in skip:
            continue
        k = len(fd["rows"])
        full = abs(fd["turn"]) * k
        out = turn_flap(out, M, fd, min(1.0, REST_TURN / max(full, 1e-9)), (faces or {}).get(fd["piece"], 1.0))
    return out


def weights(M: dict) -> np.ndarray:
    """Per vertex 0..1: the strength of the crease it lies on (0 off the fold rows)."""
    w = np.zeros(len(M["uv"]))
    for fd in M.get("folds") or []:
        for row in fd["rows"]:
            w[row] = np.maximum(w[row], fd["strength"])
    return w


def measure(V: np.ndarray, M: dict, fd: dict, face: float = 1.0) -> dict:
    """A fold as it lies in V: the dihedral turned across its rows (deg, median along the line), how far across the
    fold is (mm: the first base-side to the first flap-side vertices), and the gap between the flap and the base under
    it (mm, median / p90 over flap vertices more than 8 mm from the line that lie over the base)."""
    g = _geom(M, fd)
    N = _normals(V, g["tris"], len(V))
    row0, rowk = g["rows"][0]["row"], g["rows"][-1]["row"]
    F = g["tris"]
    in_any = np.zeros(len(V), bool)
    for r in g["rows"]:
        in_any[r["row"]] = True
    fl = g["flap0"] & ~in_any
    base_t = F[~g["flap0"][F].any(1) & ~in_any[F].all(1)]
    flap_t = F[(g["flap0"] | in_any)[F].all(1) & fl[F].any(1)]
    def side_normal(T):
        n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    out = {}
    tb = base_t[np.isin(base_t, row0).any(1)]
    tf = flap_t[np.isin(flap_t, rowk).any(1)]
    if len(tb) and len(tf):
        nb_, nf = side_normal(tb), side_normal(tf)
        cb, cf = V[tb].mean(1), V[tf].mean(1)
        j = cKDTree(cb).query(cf)[1]
        ang = np.degrees(np.arccos(np.clip((nb_[j] * nf).sum(1), -1, 1)))
        out["turn_deg"] = round(float(np.median(ang)), 1)
    far = np.where(fl & (g["d0"] > 0.008))[0]
    if len(far) and len(base_t):
        P, Nn = samples(V, base_t, face)
        d, i = cKDTree(P).query(V[far])
        over = d < 0.02
        if over.any():
            gp = np.abs(((V[far] - P[i]) * Nn[i]).sum(1))[over] * 1000
            out["gap_mm"] = [round(float(np.median(gp)), 1), round(float(np.percentile(gp, 90)), 1)]
            out["over"] = int(over.sum())
    # across the fold: the nearest base-side and flap-side vertices off the rows, at each row vertex
    bv = np.where(~g["flap0"] & ~in_any & (M["piece"] == M["names"].index(fd["piece"])))[0]
    fv = np.where(fl)[0]
    if len(bv) and len(fv):
        db, ib = cKDTree(V[bv]).query(V[row0])
        df, jf = cKDTree(V[fv]).query(V[rowk])
        out["across_mm"] = round(float(np.median(np.linalg.norm(V[bv[ib]] - V[fv[jf]], axis=1))) * 1000, 1)
    return out
