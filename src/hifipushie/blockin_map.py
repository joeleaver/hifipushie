"""THE PATTERN ON ITS BLOCK-IN (F9, C327-): step 4's check and step 5's start, one map.

Each drafted piece is mapped onto its block-in region (garment_blockin: the region between its seam lines):
1. the region FLATTENED by least squares conformal maps (`lscm`: Levy et al.; two far boundary points pinned at their
   3D distance, so the flat keeps the region's size);
2. the piece's border matched to the region's border BY ITS SEAM ENDS: each pattern seam laid along the block-in's line
   between the same two pieces (several lines between one pair: the one nearest the piece's guide start) by arc length;
   each free edge (a hem, an opening) along the region's free border between the two seam ends it joins;
3. the piece's inside laid harmonically inside that border (in the region's flat), then lifted onto the region in 3D.
Both sides of a seam take the SAME point of the line: the start's seams are closed by construction, nothing inside.

STEP 4 CHECK (`check`): per seam the pattern's length vs the block-in line (`map:<seam>`), per piece its flat area vs its
region's (`area:<piece>`), per piece the mapped edges' stretch (along / across the grain, p10 / p90): a little
compression is the ease standing off at hollows (PASS); a seam off by more than max(SEAM_MM, SEAM_PCT) FAILS naming the
piece, the seam and which way (the pattern too long / too short there), back to step 4.
STEP 5 START (`start`): the mapped positions for every soft piece (stiff pieces keep their built place); the start's
length row then reads the map's distortion: expected, small, settled by the chains (bent, never stretched away).
Nothing names a garment.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree

SEAM_MM = 25.0     # a seam within this of its block-in line is the ease standing off (PASS)
SEAM_PCT = 5.0     # ... or within this share of it, whichever is larger
AREA_PCT = 12.0    # a piece's flat area within this of its region's


def _soft(b) -> list:
    return list(b.roles.panels) + list(b.roles.tubes)


def lscm(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Least squares conformal flattening of a disc-like mesh (V, F local); two far boundary vertices pinned at their 3D
    distance. Returns (n, 2)."""
    n = len(V)
    T = V[F]
    e1 = T[:, 1] - T[:, 0]
    e2 = T[:, 2] - T[:, 0]
    x1 = np.linalg.norm(e1, axis=1)
    ex = e1 / np.maximum(x1, 1e-12)[:, None]
    nrm = np.cross(e1, e2)
    A2 = np.linalg.norm(nrm, axis=1)
    ey = np.cross(nrm / np.maximum(A2, 1e-12)[:, None], ex)
    x2, y2 = (e2 * ex).sum(1), (e2 * ey).sum(1)
    xs = np.c_[np.zeros(len(F)), x1, x2]
    ys = np.c_[np.zeros(len(F)), np.zeros(len(F)), y2]
    s = 1 / np.sqrt(np.maximum(A2, 1e-14))
    rows, cols, wr, wi = [], [], [], []
    for k in range(3):
        a, b = (k + 1) % 3, (k + 2) % 3
        rows.append(np.arange(len(F)))
        cols.append(F[:, k])
        wr.append((xs[:, b] - xs[:, a]) * s)
        wi.append((ys[:, b] - ys[:, a]) * s)
    r, c, wr, wi = map(np.concatenate, (rows, cols, wr, wi))
    Mr = sparse.csr_matrix((wr, (r, c)), shape=(len(F), n))
    Mi = sparse.csr_matrix((wi, (r, c)), shape=(len(F), n))
    from .chain_net import boundary_edges
    bv = np.unique(boundary_edges(F))
    P = V[bv]
    i0 = bv[np.argmax(np.linalg.norm(P - P.mean(0), axis=1))]
    i1 = bv[np.argmax(np.linalg.norm(V[bv] - V[i0], axis=1))]
    pin = {i0: (0.0, 0.0), i1: (float(np.linalg.norm(V[i1] - V[i0])), 0.0)}
    free = np.setdiff1d(np.arange(n), list(pin))
    A = sparse.bmat([[Mr, -Mi], [Mi, Mr]]).tocsc()
    x_p = np.zeros(2 * n)
    for i, (u, v) in pin.items():
        x_p[i], x_p[n + i] = u, v
    keep = np.r_[free, n + free]
    Ak = A[:, keep]
    sol = spsolve((Ak.T @ Ak).tocsc(), -(Ak.T @ (A @ x_p)))
    x = x_p.copy()
    x[keep] = sol
    return np.c_[x[:n], x[n:]]


def _locate(UV, F, Q2, k: int = 12):
    """For 2D points Q2: (triangle, barycentrics) in the flat (UV, F); points outside clamp to the nearest triangle."""
    C = UV[F].mean(1)
    _, J = cKDTree(C).query(Q2, k=min(k, len(F)))
    J = np.atleast_2d(J)
    best = np.zeros(len(Q2), int)
    bary = np.zeros((len(Q2), 3))
    worst = np.full(len(Q2), np.inf)
    for col in range(J.shape[1]):
        t = J[:, col]
        A, B, Cc = UV[F[t, 0]], UV[F[t, 1]], UV[F[t, 2]]
        v0, v1, v2 = B - A, Cc - A, Q2 - A
        d = v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0]
        d = np.where(np.abs(d) < 1e-14, 1e-14, d)
        l1 = (v2[:, 0] * v1[:, 1] - v2[:, 1] * v1[:, 0]) / d
        l2 = (v0[:, 0] * v2[:, 1] - v0[:, 1] * v2[:, 0]) / d
        l = np.c_[1 - l1 - l2, l1, l2]
        out = -np.minimum(l, 0).sum(1)
        better = out < worst
        worst = np.where(better, out, worst)
        best = np.where(better, t, best)
        bary = np.where(better[:, None], l, bary)
    bary = np.clip(bary, 0, None)
    bary /= np.maximum(bary.sum(1, keepdims=True), 1e-12)
    return best, bary


def _to_flat(V, F, UV, P3):
    """3D points on the region -> its flat (closest triangle, barycentric)."""
    from .chain_net import _closest_on_tris
    C = V[F].mean(1)
    _, J = cKDTree(C).query(P3, k=min(8, len(F)))
    J = np.atleast_2d(J)
    best, dist = J[:, 0].copy(), np.full(len(P3), np.inf)
    Qb = np.zeros_like(P3)
    for col in range(J.shape[1]):
        t = J[:, col]
        Q = _closest_on_tris(P3, V[F[t, 0]], V[F[t, 1]], V[F[t, 2]])
        d = np.linalg.norm(Q - P3, axis=1)
        m = d < dist
        dist, best, Qb = np.where(m, d, dist), np.where(m, t, best), np.where(m[:, None], Q, Qb)
    A, B, Cc = V[F[best, 0]], V[F[best, 1]], V[F[best, 2]]
    v0, v1, v2 = B - A, Cc - A, Qb - A
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = np.maximum(d00 * d11 - d01 * d01, 1e-18)
    l1 = (d11 * d20 - d01 * d21) / den
    l2 = (d00 * d21 - d01 * d20) / den
    l = np.clip(np.c_[1 - l1 - l2, l1, l2], 0, None)
    l /= np.maximum(l.sum(1, keepdims=True), 1e-12)
    return (UV[F[best]] * l[:, :, None]).sum(1)


def _arc(P):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    return s / max(s[-1], 1e-12), float(s[-1])


def _along(line, f):
    s, _ = _arc(line)
    return np.c_[[np.interp(f, s, line[:, k]) for k in range(line.shape[1])]].T


def _seam_chains(b) -> dict:
    """{seam index: (piece a, piece b, ordered vertex chain on a, its partners on b, flat length m)}."""
    from .chain_net import boundary_edges
    from .garment_blockin import _chains
    net = b.net
    S = net.sew
    ss = np.asarray(net.M.get("sew_seam", np.zeros(len(S), int)))
    out = {}
    for si in np.unique(ss):
        k = ss == si
        a = S[k, 0]
        partner = dict(zip(S[k, 0].tolist(), S[k, 1].tolist()))
        pa, pb = net.names[net.piece[a[0]]], net.names[net.piece[S[k, 1][0]]]
        Fp = net.F[net.piece[net.F[:, 0]] == net.pid(pa)]
        E = boundary_edges(Fp)
        on = np.zeros(net.n, bool)
        on[a] = True
        ch = _chains(E[on[E[:, 0]] & on[E[:, 1]]], None)
        if not ch:
            continue
        c = np.asarray(max(ch, key=len))
        L = float(np.linalg.norm(np.diff(net.uv[c], axis=0), axis=1).sum())
        out[int(si)] = (pa, pb, c, np.asarray([partner.get(int(v), -1) for v in c]), L)
    return out


def _region_mesh(blk, piece):
    i = blk.names.index(piece)
    F = blk.F[blk.region == i]
    used = np.unique(F)
    remap = np.full(len(blk.V), -1)
    remap[used] = np.arange(len(used))
    return blk.V[used], remap[F]


def _match(b, blk, guide) -> dict:
    """{seam index: (block-in line (k, 3) oriented along the pattern chain, step-1 name)}: each pattern seam to the
    block-in line between the same two pieces nearest its guide start."""
    out = {}
    for si, (pa, pb, c, cb, L) in _seam_chains(b).items():
        key = (pa, pb) if (pa, pb) in blk.seams else (pb, pa)
        lines = blk.seams.get(key) or []
        if not lines:
            continue
        G = guide[c]
        j = int(np.argmin([np.linalg.norm(l.mean(0) - G.mean(0)) for l in lines]))
        line = lines[j]
        if np.linalg.norm(line[0] - G[0]) + np.linalg.norm(line[-1] - G[-1]) > \
                np.linalg.norm(line[-1] - G[0]) + np.linalg.norm(line[0] - G[-1]):
            line = line[::-1]
        out[si] = (line, blk.seam_of[key][j])
    return out


def map_pieces(b, blk, guide: np.ndarray) -> tuple[np.ndarray, dict]:
    """(X with every soft piece on its region, reads). Pieces without a region keep `guide`."""
    from .chain_net import boundary_edges
    from .garment_blockin import _chains
    net = b.net
    X = np.array(guide, float)
    chains = _seam_chains(b)
    lines = _match(b, blk, guide)
    fixed = {}  # net vertex -> 3D on the block-in
    for si, (pa, pb, c, cb, L) in chains.items():
        if si not in lines:
            continue
        f, _ = _arc(net.uv[c])
        P = _along(lines[si][0], f)
        for v, w, p in zip(c, cb, P):
            fixed[int(v)] = p
            if w >= 0:
                fixed[int(w)] = p
    reads = {"pieces": {}, "unmapped": []}
    for p in _soft(b):
        if p not in blk.names:
            reads["unmapped"].append(p)
            continue
        RV, RF = _region_mesh(blk, p)
        UV = lscm(RV, RF)
        vs = net.verts(p)
        Fp = net.F[net.piece[net.F[:, 0]] == net.pid(p)]
        bE = boundary_edges(Fp)
        bv = np.unique(bE)
        # free border runs: between seam-fixed ends, along the region's free border
        rbE = boundary_edges(RF)
        # (region border vertices not on a seam line with another region = its free border)
        on_line = np.zeros(len(RV), bool)
        allL = np.concatenate([l for k_, ls in blk.seams.items() if p in k_ for l in ls]) if any(p in k_ for k_ in blk.seams) else np.zeros((0, 3))
        if len(allL):
            d, _ = cKDTree(allL).query(RV)
            on_line = d < 1e-6
        freeE = rbE[~(on_line[rbE[:, 0]] & on_line[rbE[:, 1]])]
        fchains = [np.asarray(c_) for c_ in _chains(freeE, None)]
        loose = [int(v) for v in bv if int(v) not in fixed]
        on = np.zeros(net.n, bool)
        on[loose] = True
        for run in _chains(bE[on[bE[:, 0]] | on[bE[:, 1]]], None):
            run = np.asarray(run)
            ends = [v for v in (run[0], run[-1]) if int(v) in fixed]
            inner = [int(v) for v in run if int(v) not in fixed]
            if not inner or not fchains:
                continue
            fr = np.concatenate([RV[c_] for c_ in fchains])
            kd = cKDTree(fr)
            if len(ends) == 2:
                i0, i1 = kd.query(fixed[int(ends[0])])[1], kd.query(fixed[int(ends[1])])[1]
                ci = np.cumsum([0] + [len(c_) for c_ in fchains])
                k0 = np.searchsorted(ci, i0, side="right") - 1
                line = fr[min(i0, i1):max(i0, i1) + 1] if np.searchsorted(ci, i1, side="right") - 1 == k0 else None
                if line is not None and len(line) > 1:
                    if i0 > i1:
                        line = line[::-1]
                    f, _ = _arc(net.uv[run])
                    for v, q in zip(run, _along(line, f)):
                        if int(v) not in fixed:
                            fixed[int(v)] = q
                    continue
            for v in inner:  # (no two seam ends to run between: the nearest free border point)
                fixed[v] = fr[kd.query(guide[v])[1]]
        # harmonic inside, in the region's flat
        loc = {int(v): i for i, v in enumerate(vs)}
        Fl = np.vectorize(loc.get)(Fp)
        n = len(vs)
        E = np.unique(np.sort(np.r_[Fl[:, [0, 1]], Fl[:, [1, 2]], Fl[:, [2, 0]]], axis=1), axis=0)
        W = sparse.coo_matrix((np.ones(2 * len(E)), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n)).tocsr()
        Lp = sparse.diags(np.asarray(W.sum(1)).ravel()) - W
        bl = np.array([loc[v] for v in fixed if v in loc], int)
        if len(bl) < 3:
            reads["unmapped"].append(p)
            continue
        B2 = _to_flat(RV, RF, UV, np.array([fixed[int(vs[i])] for i in bl]))
        il = np.setdiff1d(np.arange(n), bl)
        U = np.zeros((n, 2))
        U[bl] = B2
        Lii = Lp[il][:, il].tocsc()
        rhs = -Lp[il][:, bl] @ B2
        U[il] = np.c_[spsolve(Lii, rhs[:, 0]), spsolve(Lii, rhs[:, 1])]
        t, l = _locate(UV, RF, U)
        P3 = (RV[RF[t]] * l[:, :, None]).sum(1)
        P3[bl] = np.array([fixed[int(vs[i])] for i in bl])
        X[vs] = P3
        reads["pieces"][p] = {"region_cm2": round(_area(RV, RF) * 1e4, 1), "flat_cm2": round(_area(np.c_[net.uv[vs], np.zeros(n)], Fl) * 1e4, 1),
                              "stretch": stretch(net, X, p)}
    reads["lines"] = {int(si): nm for si, (_, nm) in lines.items()}
    return X, reads


def _area(V, F) -> float:
    T = V[F]
    return float(0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1).sum())


def stretch(net, X, p) -> dict:
    """Mapped / flat per face along the grain (uv y) and across (uv x): p10 / p50 / p90 (< 1: the pattern longer)."""
    Fp = net.F[net.piece[net.F[:, 0]] == net.pid(p)]
    uv = net.uv[Fp]
    P = X[Fp]
    D = np.stack([uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]], 2)  # (f, 2, 2): columns are flat edges
    E3 = np.stack([P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]], 2)    # (f, 3, 2)
    ok = np.abs(np.linalg.det(D)) > 1e-12
    J = E3[ok] @ np.linalg.inv(D[ok])                              # (f, 3, 2): d3D / d(u, v)
    q = lambda a: [round(float(x), 3) for x in np.percentile(a, [10, 50, 90])]
    return {"across": q(np.linalg.norm(J[:, :, 0], axis=1)), "along": q(np.linalg.norm(J[:, :, 1], axis=1))}


def check(b, blk, guide: np.ndarray) -> dict:
    """STEP 4 rows: the pattern vs its block-in, per seam and per piece (garment_blockin regions)."""
    from .chain_sew import seam_name
    rows = []
    lines = _match(b, blk, guide)
    for si, (pa, pb, c, cb, L) in sorted(_seam_chains(b).items()):
        nm = seam_name(b, si)
        if si not in lines:
            rows.append(dict(id=f"map:{nm}", status="UNMEASURED", why=f"no block-in line between {pa} and {pb}: a seam "
                             "plane or region missing in step 2's blockin", back_to="2"))
            continue
        line, step1 = lines[si]
        Lb = float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum())
        d = (L - Lb) * 1e3
        tol = max(SEAM_MM, SEAM_PCT / 100 * Lb * 1e3)
        row = dict(id=f"map:{nm}", status="PASS" if abs(d) <= tol else "FAIL", value=round(d, 1),
                   target=f"|pattern - block-in| <= {tol:.0f} mm (max({SEAM_MM:.0f} mm, {SEAM_PCT:.0f} %))",
                   ours={"pattern_mm": round(L * 1e3), "blockin_mm": round(Lb * 1e3), "step1_seam": step1})
        if row["status"] == "FAIL":
            row.update(why=f"{pa}'s {step1} seam is {abs(d):.0f} mm too {'long' if d > 0 else 'short'} for the block-in "
                           f"({L * 1e3:.0f} vs {Lb * 1e3:.0f} mm)", back_to="4",
                       change=f"redraw {pa}'s {step1} edge {'shorter' if d > 0 else 'longer'} by {abs(d):.0f} mm (and its "
                              f"partner on {pb}), or the block-in (step 2) if the design is what's wrong")
        rows.append(row)
    X, rd = map_pieces(b, blk, guide)
    for p, r in rd["pieces"].items():
        a = r["flat_cm2"] / max(r["region_cm2"], 1e-9) - 1
        st = r["stretch"]
        way = []
        if st["along"][1] < 1 - AREA_PCT / 100:
            way.append(f"too long along the grain (mapped x{st['along'][1]})")
        if st["along"][1] > 1 + AREA_PCT / 100:
            way.append(f"too short along the grain (x{st['along'][1]})")
        if st["across"][1] < 1 - AREA_PCT / 100:
            way.append(f"too wide (mapped x{st['across'][1]})")
        if st["across"][1] > 1 + AREA_PCT / 100:
            way.append(f"too narrow (x{st['across'][1]})")
        ok = abs(a) * 100 <= AREA_PCT and not way
        row = dict(id=f"area:{p}", status="PASS" if ok else "FAIL", value=round(a * 100, 1),
                   target=f"flat area within {AREA_PCT:.0f} % of its region; median stretch along / across within it",
                   ours={**r})
        if not ok:
            row.update(why=f"{p} {'larger' if a > 0 else 'smaller'} than its region by {abs(a) * 100:.0f} %"
                           + (f"; {', '.join(way)}" if way else ""), back_to="4",
                       change=f"redraw {p} to its region (step 4), or the block-in's region (step 2)")
        rows.append(row)
    fails = [r for r in rows if r["status"] == "FAIL"]
    return {"verdict": "FAIL" if fails else "PASS", "rows": rows, "map": rd, "X": X}


def start(b, blk, guide: np.ndarray) -> np.ndarray:
    """STEP 5's start: every soft piece on its region (seams closed: shared points); stiff pieces keep their place."""
    X, rd = map_pieces(b, blk, guide)
    held = b._stiff_mask()
    X = np.where(held[:, None], guide, X)
    b.reads["blockin_start"] = {k: v for k, v in rd.items()}
    b.blockin_start_used = True
    return X
