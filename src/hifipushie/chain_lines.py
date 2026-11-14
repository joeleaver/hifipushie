"""CHAIN LINES (N2j): the LINES ACROSS a piece are real CHAINS, so a piece may CURVE but never SQUASH.

Joe's rule: every straight line across a piece keeps its flat length. N2b-N2i held each line across (a Delaunay ruling
between chain points) only AT MOST its flat length, meant to let the cloth curve round the body (a curved piece's chord
is shorter than flat); the solve could not tell curving from squashing and paid every conflict by narrowing pieces
(N2i's jacket: 16-45 % of the lines across over 15 % short, sleeve tops' median 0.87 of flat), and the boundary chains,
exact in length, snaked in the narrowed pieces: the wobble.

Here each line across is a chain sampled every SPACING, its links EXACT at their flat length, bending along it like any
chain: a bent line's chord shortens (the piece curves), its arc never does (the piece can't squash). Two families per
piece, along its grain and across it (the weave's own threads: the cloth's bias still shears), on ONE LATTICE: a lattice
point is shared by its two lines (a grid of threads, no surface mesh). Per family, every lattice line is cut into the
intervals the piece's outline and fold rows leave (a line never crosses a fold row: the fold turns its chains there);
each interval's lattice points (kept MARGIN x SPACING off the outline and every fold row) are its interior points, its
ends the piece's chain points nearest where it meets the outline / row. Any link longer than SPLIT x spacing (an end
link, or an interval too narrow for a lattice point: a hem allowance, a band) gets evenly spaced points of its own: one
long straight link can't bend across (a strip end's single link held its width flat, its pulled edges 10 mm off).

lines(uv, pts, poly, rows, grain_deg, spacing) -> (new uv (k, 2), chains [list of point refs], family per chain):
refs >= 0 are ids into uv (chain points pts), refs < 0 are -1 - (index into new uv). Nothing here knows a garment, a
piece's role or a wear state.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

SPACING = 0.03  # m: the lattice step: lines across every SPACING, each sampled every SPACING (the brief: ~20-30 mm)
MARGIN = 0.4  # x SPACING: a lattice point nearer the outline or a fold row than this is left out (no stub links)
SPLIT = 1.25  # x SPACING: a line's link longer than this is split evenly (its own points, on no lattice)
EDGE = 0.1  # x SPACING: an interval whose middle is nearer the outline / a row than this runs along it: not a line
SNAP = 0.6  # x SPACING: a line's end goes to the nearest chain point within this of where it meets the outline / row


def _segs(poly, rows, uv):
    """Every segment of the closed outline and of each fold row: (A (m, 2), B (m, 2))."""
    A, B = [poly, *[uv[r[:-1]] for r in rows]], [np.roll(poly, -1, axis=0), *[uv[r[1:]] for r in rows]]
    return np.concatenate(A), np.concatenate(B)


def _hits(o, d, A, B):
    """Parameters s where the line o + s d (d unit) meets the segments AB, sorted."""
    e = B - A
    den = d[0] * e[:, 1] - d[1] * e[:, 0]
    ok = np.abs(den) > 1e-12
    w = A - o
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (w[:, 0] * e[:, 1] - w[:, 1] * e[:, 0]) / den
        u = (w[:, 0] * d[1] - w[:, 1] * d[0]) / den
    m = ok & (u >= -1e-9) & (u <= 1 + 1e-9)
    return np.unique(np.round(s[m], 9))


def _dist(q, A, B):
    """Distance of points q (n, 2) to the nearest segment AB."""
    e = B - A
    t = np.clip(((q[:, None] - A[None]) * e[None]).sum(2) / np.maximum((e * e).sum(1), 1e-18)[None], 0, 1)
    return np.linalg.norm(q[:, None] - (A[None] + t[..., None] * e[None]), axis=2).min(1)


def _inside(poly, q):
    x, y = q[:, 0][:, None], q[:, 1][:, None]
    a, b = poly, np.roll(poly, -1, axis=0)
    c = (a[:, 1] > y) != (b[:, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
    return (c & (x < xc)).sum(1) % 2 == 1


def lines(uv, pts, poly, rows, grain_deg: float = 90.0, spacing: float = SPACING):
    """The piece's lines across (module doc)."""
    pts = np.asarray(pts, np.int64)
    g = np.radians(grain_deg)
    D = np.array([[np.cos(g), np.sin(g)], [-np.sin(g), np.cos(g)]])  # (family 0 runs along the grain, 1 across)
    A, B = _segs(poly, rows, uv)
    c0 = poly.mean(0)
    st = (poly - c0) @ D.T  # (outline in (along, across) coordinates)
    lo, hi = np.floor(st.min(0) / spacing) - 1, np.ceil(st.max(0) / spacing) + 1
    I, J = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1), indexing="ij")
    lat = c0 + (I.ravel()[:, None] * spacing) * D[0] + (J.ravel()[:, None] * spacing) * D[1]
    ok = _inside(poly, lat)
    ok[ok] = _dist(lat[ok], A, B) > MARGIN * spacing
    key = {(int(i), int(j)): k for k, (i, j) in enumerate(zip(I.ravel()[ok], J.ravel()[ok]))}
    new = list(lat[ok])
    kd = cKDTree(uv[pts])
    chains, fam = [], []
    at = lambda r: uv[r] if r >= 0 else new[-1 - r]

    def snap(q):
        dd, k = kd.query(q)
        return int(pts[k]) if dd < SNAP * spacing else None

    for f in (0, 1):
        d, n_ = D[f], D[1 - f]
        idx = (I if f == 1 else J).ravel()  # (the other family's index names the line)
        for m in np.unique(idx):
            o = c0 + m * spacing * n_
            s = _hits(o, d, A, B)
            for a, b in zip(s[:-1], s[1:]):
                mid = (o + 0.5 * (a + b) * d)[None]
                if b - a < 1e-6 or not _inside(poly, mid)[0] or _dist(mid, A, B)[0] < EDGE * spacing:
                    continue  # (outside, or a lattice line running ALONG the outline / a row: no line across)
                ks = np.arange(np.ceil(a / spacing), np.floor(b / spacing) + 1)  # (lattice steps along the line)
                inner = [key[(int(k), int(m)) if f == 0 else (int(m), int(k))] for k in ks
                         if ((int(k), int(m)) if f == 0 else (int(m), int(k))) in key]
                ea, eb = snap(o + a * d), snap(o + b * d)
                ch = ([ea] if ea is not None else []) + [-1 - k for k in inner] + ([eb] if eb is not None else [])
                if len(ch) < 2 or (not inner and ea == eb):
                    continue
                full = [ch[0]]  # (a gap longer than SPLIT x spacing, an end link or a narrow interval with no lattice
                for r in ch[1:]:  # point, is sampled too: one long straight link can't bend across)
                    pa, pb = at(full[-1]), at(r)
                    k = int(np.ceil(np.linalg.norm(pb - pa) / (SPLIT * spacing)))
                    for t in np.arange(1, k) / k:
                        new.append(pa + t * (pb - pa))
                        full.append(-len(new))
                    full.append(r)
                chains.append(full)
                fam.append(f)
    used = sorted({-1 - r for ch in chains for r in ch if r < 0})  # (a lattice point no line reached is dropped)
    ren = {old: k for k, old in enumerate(used)}
    chains = [[r if r >= 0 else -1 - ren[-1 - r] for r in ch] for ch in chains]
    return np.asarray(new).reshape(-1, 2)[used], chains, fam


def walk(cnet, kind: int) -> list:
    """Every line across of one kind (2 along the grain, 3 across) as its points in order (open paths)."""
    cv = np.asarray(cnet.chain_v)[np.asarray(cnet.chain_kind) == kind]
    nb: dict = {}
    for a, b in cv.tolist():
        nb.setdefault(a, []).append(b)
        nb.setdefault(b, []).append(a)
    seen, out = set(), []
    for s in sorted(v for v, n in nb.items() if len(n) == 1):
        if s in seen:
            continue
        path, prev = [s], None
        while True:
            seen.add(path[-1])
            nx = [v for v in nb[path[-1]] if v != prev and v not in seen]
            if not nx:
                break
            prev = path[-1]
            path.append(nx[0])
        out.append(np.array(path, np.int64))
    return out


def wave(P, window: float = 0.05, closed: bool = False) -> float:
    """A chain's WAVINESS: its length over the length of itself smoothed at `window` (m; a moving average by arc length),
    minus 1. A straight or gently curved chain reads ~0; waves a few links long, which a one-link kink count misses,
    read as the extra length they take."""
    P = np.asarray(P, float)
    if closed:
        P = np.r_[P, P[:1]]
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    if s[-1] < 2 * window or len(P) < 4:
        return 0.0
    Q = np.array([P[(s >= t - window / 2) & (s <= t + window / 2)].mean(0) for t in s])
    if not closed:  # (the ends can't average symmetrically: kept as they are)
        e = (s < window / 2) | (s > s[-1] - window / 2)
        Q[e] = P[e]
    q = float(np.linalg.norm(np.diff(Q, axis=0), axis=1).sum())
    return float(s[-1] / max(q, 1e-12) - 1.0)
