"""A garment piece draped over a FINISHED garment as its collider (dress-garrett ak, 2026-10-18).

Why: a made piece grafted as a grid onto a frozen drape (cloth_made.notched_collar) builds the collar's fall and its
end at the notch as two surfaces joined at a corner: every seating patch on it moved the fault (a block became a wing,
a spike; five sessions, ai / aj). A tailor drafts the collar as its own piece, presses its roll and sews it at the neck
and the gorge, and the cloth lies where it lies. Here the piece is a grid [n stations along its sewn edge, m rows
across] with:
  - a DRAFT (flat uv per vertex: the thread frame; `draft_numbers` reads CB width, stand / fall, point, spring),
  - a PRESSED REST (3D, the shape the interfaced piece springs to: its roll kept, its ends turned flat onto what they
    lie on, `turn_columns`), the membrane and bending rest of the sim,
  - PINS (its sewn edge, and any rows that stay as made, e.g. the back's stand),
and is simulated ALONE (a small cloth_job, solver-neutral) with everything else frozen as one static collider
(`collider`: the finished garment, the garments under it, the body; faces right at the pins dropped so the sewn edge
can sit on its seam). The finished garment's own sim / hang is never touched.

Generic: any piece sewn along one edge onto a finished garment (collars, a lapel facing, a flap, a pocket flap)."""
from __future__ import annotations

import numpy as np

from .cloth_made import _rodrigues, _unit, closest, grid_faces


def _axis(H: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    """The sewn edge's tangent per station, evened along it (Gaussian, `sigma` stations): turned about the raw tangent,
    columns either side of a corner in the edge (the gorge meeting the neckline) cross (crushed cloth at the start, ak)."""
    T = np.gradient(np.asarray(H, float), axis=0)
    if sigma > 0:
        x = np.arange(len(H))
        W = np.exp(-0.5 * ((x[:, None] - x[None]) / sigma) ** 2)
        T = W @ _unit(T)
    return _unit(T)


def resample_columns(G: np.ndarray, widths: np.ndarray) -> np.ndarray:
    """G [n, m, 3] (or [n, m, 2]) re-run along each station's column to width[i] (arc length from row 0), m rows
    evenly spaced: past the column's own end it goes on along its last segment."""
    G = np.asarray(G, float)
    n, m = G.shape[:2]
    out = np.empty_like(G)
    for i in range(n):
        C = G[i]
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
        t = np.linspace(0.0, float(widths[i]), m)
        for d in range(G.shape[2]):
            out[i, :, d] = np.interp(t, s, C[:, d])
        far = t > s[-1]
        if far.any():
            u = _unit(C[-1] - C[-2])
            out[i, far] = C[-1] + (t[far] - s[-1])[:, None] * u
    return out


def col_lengths(G: np.ndarray) -> np.ndarray:
    return np.linalg.norm(np.diff(np.asarray(G, float), axis=1), axis=-1).sum(1)


def row_lengths(G: np.ndarray) -> np.ndarray:
    return np.linalg.norm(np.diff(np.asarray(G, float), axis=0), axis=-1).sum(0)


def draft_numbers(uv: np.ndarray, roll: np.ndarray | None = None) -> dict:
    """A drafted grid's numbers (mm): width at the centre station, at the ends (the point), spring (outer edge over
    sewn edge), and with `roll` [n] (row index of the roll line) stand / fall at the centre."""
    uv = np.asarray(uv, float)
    n = uv.shape[0]
    W = col_lengths(uv)
    rl = row_lengths(uv)
    out = {"width_cb_mm": round(float(W[n // 2]) * 1000, 1), "point_mm": [round(float(W[0]) * 1000, 1),
           round(float(W[-1]) * 1000, 1)], "neck_mm": round(float(rl[0]) * 1000, 1),
           "outer_mm": round(float(rl[-1]) * 1000, 1), "spring": round(float(rl[-1] / rl[0]), 3)}
    if roll is not None:
        c = n // 2
        r = int(roll[c])
        st = float(np.linalg.norm(np.diff(uv[c, : r + 1], axis=0), axis=1).sum())
        out.update(stand_cb_mm=round(st * 1000, 1), fall_cb_mm=round((float(W[c]) - st) * 1000, 1))
    return out


def under_draft(uv: np.ndarray, turn: float = 0.003) -> np.ndarray:
    """The undercollar's draft from the upper collar's: its outer edge `turn` in (the turn of cloth: the seam rolls
    under, out of sight), cut on the bias (thread frame turned 45 deg, so it shapes round the neck)."""
    uv = np.asarray(uv, float)
    W = col_lengths(uv)
    U = resample_columns(uv, np.maximum(W - turn, 1e-4))
    c = U.reshape(-1, 2).mean(0)
    a = np.radians(45.0)
    R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    return (U - c) @ R.T + c


def _side_dist(P, V, F):
    """Distance from P to the surface (V, F) and its sign by the faces' winding (+ = the side the normals face)."""
    Q, N, _ = closest(P, V, F)
    d = P - Q
    return np.linalg.norm(d, axis=1), (d * N).sum(1)


def turn_columns(G: np.ndarray, sel: np.ndarray, V: np.ndarray, F: np.ndarray, gap: float = 0.003,
                 max_deg: float = 120.0, smooth: float = 1.5, from_row: np.ndarray | None = None) -> tuple:
    """Each selected station's column turned as a board about the sewn edge's tangent (at row from_row[i], default
    0) until its outer point lies `gap` over the surface (V, F) on the side its middle starts on (a collar end turned
    flat onto the lapel, never through it). Angles evened along the stations (Gaussian `smooth`), unselected
    stations 0. Returns (G turned, {"deg", "outer_mm" before / after})."""
    G = np.asarray(G, float)
    n, m = G.shape[:2]
    sel = np.asarray(sel, bool)
    r0 = np.zeros(n, int) if from_row is None else np.asarray(from_row, int)
    H = G[np.arange(n), r0]
    k = _unit(np.gradient(G[:, 0], axis=0))
    rows = np.arange(m)[None] > r0[:, None]

    def turned(th):
        Y = _rodrigues(G - H[:, None], k, th) + H[:, None]
        return np.where(rows[..., None], Y, G)
    mid = m // 2
    _, s_mid0 = _side_dist(G[:, mid], V, F)
    side = np.sign(np.where(s_mid0 == 0, 1.0, s_mid0))
    grid = np.radians(np.arange(-max_deg, max_deg + 0.1, 2.0))
    best = np.zeros(n)
    score0 = np.abs(_side_dist(G[:, -1], V, F)[0] - gap)
    sc = np.full(n, np.inf)
    for t in grid:
        X = turned(np.full(n, t))
        d_o, s_o = _side_dist(X[:, -1], V, F)
        _, s_m = _side_dist(X[:, mid], V, F)
        ok = (np.sign(s_o) == side) & (np.sign(s_m) == side)
        cost = np.abs(d_o - gap) + 0.002 * abs(t)  # (the least turn among equal lies)
        b = ok & (cost < sc) & sel
        sc[b], best[b] = cost[b], t
    if smooth > 0:
        x = np.arange(n)
        Wg = np.exp(-0.5 * ((x[:, None] - x[None]) / smooth) ** 2) * sel[None]
        best = np.where(sel, (Wg @ best) / np.maximum(Wg.sum(1), 1e-9), 0.0)
    G2 = turned(best)
    f = lambda o: [round(float(np.median(o[sel])) * 1000, 1), round(float(o[sel].max()) * 1000, 1)] if sel.any() else []
    return G2, {"deg": np.round(np.degrees(best), 1), "outer_mm": {"before": f(score0 + gap),
                "after": f(_side_dist(G2[:, -1], V, F)[0])}}


def smooth_stations(G: np.ndarray, passes: int = 4, w: float = 0.5, fixed: np.ndarray | None = None) -> np.ndarray:
    """Laplacian smoothing along the stations (rows kept apart), the end stations and `fixed` [n, m] held."""
    G = np.array(G, float)
    fx = np.zeros(G.shape[:2], bool) if fixed is None else np.asarray(fixed, bool)
    for _ in range(passes):
        L = G.copy()
        L[1:-1] = 0.5 * (G[:-2] + G[2:])
        G = np.where(fx[..., None], G, G + w * (L - G))
    return G


def collider(parts: list, near: np.ndarray | None = None, radius: float = 0.004, labels: bool = False) -> tuple:
    """[(V, F), ...] as one static collider (V, F); faces with a vertex within `radius` of `near` (the pinned edge's
    points: they sit on their seam) left out. labels=True adds a third array: each collider vertex's index in `parts`
    (a solver's "collision-mesh vertex k" is then traceable to the part it came from)."""
    Vs, Fs, Ls, off = [], [], [], 0
    for k, (V, F) in enumerate(parts):
        V, F = np.asarray(V, float), np.asarray(F, np.int64)
        if not len(F):
            continue
        Vs.append(V)
        Fs.append(F + off)
        Ls.append(np.full(len(V), k))
        off += len(V)
    V, F, Lb = np.concatenate(Vs), np.concatenate(Fs), np.concatenate(Ls)
    if near is not None and len(near):
        from scipy.spatial import cKDTree
        near = np.asarray(near, float)
        d, _ = cKDTree(near).query(V)
        F = F[~(d[F] < radius).any(1)]
        # and faces with an EDGE passing within `radius` of a pin (a long edge whose ends are both far: ak's
        # collar-only sims failed at frame 0 on a pinned neck-seam vertex 1.4 mm from such an edge)
        drop = np.zeros(len(F), bool)
        for i, j in ((0, 1), (1, 2), (2, 0)) if len(F) else ():
            a, b = V[F[:, i]], V[F[:, j]]
            half = np.linalg.norm(b - a, axis=1) / 2
            L = cKDTree((a + b) / 2).query_ball_point(near, min(float(half.max()), 0.05) + radius)
            ks = np.unique(np.fromiter((k for l_ in L for k in l_), np.int64))
            if not len(ks):
                continue
            ab = b[ks] - a[ks]
            for q in near[np.unique(cKDTree(near).query((a[ks] + b[ks]) / 2, k=min(8, len(near)))[1])]:
                t = np.clip(((q - a[ks]) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-18), 0, 1)
                drop[ks] |= np.linalg.norm(a[ks] + t[:, None] * ab - q, axis=1) < radius
        F = F[~drop]
    used = np.unique(F)
    remap = -np.ones(len(V), np.int64)
    remap[used] = np.arange(len(used))
    return (V[used], remap[F], Lb[used]) if labels else (V[used], remap[F])


def job(X: np.ndarray, uv: np.ndarray, rest: np.ndarray, pinned: np.ndarray, coll: tuple, name: str = "over",
        fabric: str = "wool_coating", stiff: float = 1.0, frames: int = 72, settle_frames: int = 24,
        zozo: dict | None = None) -> tuple:
    """A cloth_job (cfg, arrays) for a grid piece [n, m] draped alone over the static collider `coll` (V, F): start
    X, thread frame uv, pressed rest (membrane + bending), `pinned` [n, m] held for the whole sim (sewn edge)."""
    n, m = X.shape[:2]
    F = grid_faces(n, m)
    Xf, uvf, Rf = X.reshape(-1, 3), uv.reshape(-1, 2), rest.reshape(-1, 3)
    pin = np.where(np.asarray(pinned, bool).reshape(-1))[0]
    allv = np.arange(len(Xf))
    # one sew pair between two neighbouring PINNED vertices (held, so it pulls nothing): the runner's report takes a
    # percentile over the sew gaps and an empty list crashed it after a finished sim (al, $0.02); cloth_zozo.py is
    # left unedited (its hash keys every cached sim)
    pg = np.asarray(pinned, bool)
    i0 = int(np.argmax(pg[:-1, 0] & pg[1:, 0]))
    sew = np.array([[i0 * m, (i0 + 1) * m]], np.int64) if pg[i0, 0] and pg[i0 + 1, 0] else np.zeros((0, 2), np.int64)
    arrays = {"X": Xf, "uv": uvf, "F": F, "piece": np.zeros(len(Xf), np.int64), "sew": sew,
              "stitch": np.zeros((0, 2), np.int64), "stiff": np.full(len(Xf), float(stiff)),
              "bodyV": np.asarray(coll[0], float), "bodyT": np.asarray(coll[1], np.int64),
              "carryIdx": pin, "carryPoses": Xf[pin][None], "hugIdx": pin, "restIdx": allv, "rest": Rf}
    z = {"rest": "flat"}
    z.update(zozo or {})
    cfg = {"name": name, "pieces": [name], "fabric": {"name": fabric}, "sew_frames": 4, "frames": int(frames),
           "settle_frames": int(settle_frames), "self_collision": True, "zozo": z, "backend": "zozo"}
    return cfg, arrays


def turn_onto_plane(G: np.ndarray, sel: np.ndarray, normal: np.ndarray, toward: np.ndarray, smooth: float = 1.5,
                    lift: float = 0.003, weight: np.ndarray | None = None, axis_sigma: float = 2.0) -> tuple:
    """Each selected station's column (rows 1..) turned about the sewn edge's tangent into the plane with `normal`
    (an end lying flat on the lapel), the one of the two in-plane ways that points along `toward` (outward, away from
    the gorge), then `lift` along the normal (its thickness over the cloth). Angles evened along the stations.
    weight [n] 0..1: the turn eased out over a transition (the end's angle, the mean over weight > 0.98, x weight):
    an end turned alone overlaps its unturned neighbour (crushed cloth at the start, ak)."""
    G = np.asarray(G, float)
    n, m = G.shape[:2]
    sel = np.asarray(sel, bool)
    N, T = _unit(np.asarray(normal, float)), _unit(np.asarray(toward, float))
    H = G[:, 0]
    k = _axis(H, axis_sigma)
    grid = np.radians(np.arange(-180.0, 180.0, 1.0))
    th = np.zeros(n)
    for i in np.where(sel)[0]:
        d0 = G[i, -1] - H[i]
        best = np.inf
        for t in grid:
            d = np.asarray(_rodrigues(d0[None], k[i][None], np.array([t]))).reshape(-1)[:3]
            u = _unit(d)
            cost = abs(float(u @ N)) + (1.0 if float(u @ T) < 0 else 0.0) + 1e-3 * abs(t)
            if cost < best:
                best, th[i] = cost, t
    if weight is not None:
        w = np.asarray(weight, float)
        full = sel & (w > 0.98)
        th = np.where(w > 0, w * float(np.mean(th[full])), 0.0) if full.any() else th
        sel = sel | (w > 0)
    elif smooth > 0:
        x = np.arange(n)
        Wg = np.exp(-0.5 * ((x[:, None] - x[None]) / smooth) ** 2) * sel[None]
        th = np.where(sel, (Wg @ th) / np.maximum(Wg.sum(1), 1e-9), 0.0)
    Y = _rodrigues(G - H[:, None], k, th) + H[:, None]
    wl = np.ones(n) if weight is None else np.asarray(weight, float)
    ramp = np.linspace(0, 1, m)[None, :, None] * lift * N * wl[:, None, None]
    Y = Y + np.where(sel[:, None, None], ramp, 0.0)
    rows = np.arange(m)[None] > 0
    return np.where((rows & sel[:, None])[..., None], Y, G), {"deg": np.round(np.degrees(th), 1)}


def flat_draft(R: np.ndarray) -> np.ndarray:
    """The flat pattern of a pressed grid R [n, m, 3]: the sewn edge laid as a plane curve at its own lengths, each
    column straight across at its own arc lengths, the curve's bend per station fitted so the rows keep R's lengths
    (a tailor's draft from the neckline and the fall-line measures). Returns uv [n, m, 2]."""
    R = np.asarray(R, float)
    n, m = R.shape[:2]
    t = np.c_[np.zeros(n), np.cumsum(np.linalg.norm(np.diff(R, axis=1), axis=-1), axis=1)]  # [n, m]
    ds0 = np.linalg.norm(np.diff(R[:, 0], axis=0), axis=-1)  # [n-1]
    dsj = np.linalg.norm(np.diff(R, axis=0), axis=-1)  # [n-1, m]
    tm = 0.5 * (t[1:] + t[:-1])
    # row spacing ~ ds0 (1 + kappa t): kappa per interval by least squares over the rows
    kap = ((dsj / np.maximum(ds0[:, None], 1e-9) - 1.0) * tm).sum(1) / np.maximum((tm ** 2).sum(1), 1e-12)
    ang = np.r_[0.0, np.cumsum(kap * ds0)]
    ang -= ang[n // 2]
    P = np.zeros((n, 2))
    mid = 0.5 * (ang[1:] + ang[:-1])
    P[1:] = np.cumsum(ds0[:, None] * np.c_[np.cos(mid), np.sin(mid)], axis=0)
    nrm = np.c_[-np.sin(ang), np.cos(ang)]
    return P[:, None, :] + t[..., None] * nrm[:, None, :]


def edge_pairs(X: np.ndarray, F: np.ndarray, coll: tuple, free: np.ndarray, clear: float) -> tuple:
    """Edges of the piece (X, F; an edge with a free end) closer than `clear` to an edge of the collider: (piece edge
    [k, 2], collider edge [k, 2], distance [k], direction collider -> piece [k, 3]). What a solver's edge-edge contact
    sees and a vertex-face test misses: a sharp collider edge (a shirt collar point) between two of the piece's vertices."""
    from scipy.spatial import cKDTree
    from .cloth import _seg_seg
    eg = lambda T: np.unique(np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1), axis=0)
    E, bE = eg(np.asarray(F)), eg(np.asarray(coll[1]))
    E = E[np.asarray(free, bool)[E].any(1)]
    bV = np.asarray(coll[0], float)
    reach = 0.03  # (as cloth_job.preflight: edge midpoints within 3 cm)
    L = cKDTree(bV[bE].mean(1)).query_ball_point(X[E].mean(1), reach)
    I = np.array([(i, k) for i, ks in enumerate(L) for k in ks], np.int64).reshape(-1, 2)
    if not len(I):
        return E[:0], bE[:0], np.zeros(0), np.zeros((0, 3))
    s_, t_, d = _seg_seg(X[E[I[:, 0], 0]], X[E[I[:, 0], 1]], bV[bE[I[:, 1], 0]], bV[bE[I[:, 1], 1]])
    b = d < clear
    I, s_, t_, d = I[b], np.asarray(s_)[b], np.asarray(t_)[b], d[b]
    P = X[E[I[:, 0], 0]] * (1 - s_[:, None]) + X[E[I[:, 0], 1]] * s_[:, None]
    Q = bV[bE[I[:, 1], 0]] * (1 - t_[:, None]) + bV[bE[I[:, 1], 1]] * t_[:, None]
    return E[I[:, 0]], bE[I[:, 1]], d, _unit(P - Q)


def clear_start(X: np.ndarray, coll: tuple, free: np.ndarray, clear: float = 0.0025, rounds: int = 4,
                F: np.ndarray | None = None) -> tuple:
    """Free points of X closer than `clear` to the collider moved straight away from their nearest point on it
    (unsigned: the start only has to be clear for the solver). With the piece's faces F (X a grid [n, m, 3] -> its
    grid faces), edges closer than `clear` to a collider EDGE are cleared too (both free ends moved along the pair's
    separation): ak's collar-only sims failed at frame 0 on such a pair (1.38 mm, every vertex >= 3 mm off the collider).
    Returns (X, points moved)."""
    X = np.array(X, float)
    sh = X.shape
    P = X.reshape(-1, 3)
    fr = np.asarray(free, bool).reshape(-1)
    moved = np.zeros(len(P), bool)
    for _ in range(rounds):
        Q = closest(P[fr], coll[0], coll[1])[0]
        d = P[fr] - Q
        L = np.linalg.norm(d, axis=1)
        b = L < clear
        if not b.any():
            break
        idx = np.where(fr)[0][b]
        P[idx] += _unit(d[b]) * (clear - L[b] + 1e-4)[:, None]
        moved[idx] = True
    if F is not None:
        for _ in range(rounds * 2):
            E, _, dd, dirn = edge_pairs(P, F, coll, fr, clear)
            if not len(E):
                break
            go = False
            for (a, b_), di, dv in zip(E, dd, dirn):
                if not (fr[a] and fr[b_]):  # one end pinned: moving the other only bends the edge about the pin
                    continue
                for v in (a, b_):
                    P[v] += dv * (clear - di + 1e-4)
                    moved[v] = True
                    go = True
            if not go:
                break
    return P.reshape(sh), int(moved.sum())


def support_surface(P: np.ndarray, origin: np.ndarray, normal: np.ndarray, ridge: float = 1e-3) -> callable:
    """A smooth surface through support points P (the cloth an end should lie on, e.g. a lapel by its gorge), as a
    height h(u, v) over the plane (origin, normal): quadratic, its curvature terms ridge-damped so it carries on past
    the points' edge (over the hole where nothing lies, above the gorge) without bending away. Returns
    f(Q [k, 3]) -> (height of Q over the surface along `normal` [k], the surface point under Q [k, 3])."""
    N = _unit(np.asarray(normal, float))
    a = np.array([1.0, 0, 0]) if abs(N[0]) < 0.9 else np.array([0, 1.0, 0])
    U = _unit(np.cross(N, a))
    W = np.cross(N, U)
    o = np.asarray(origin, float)

    def uvz(Q):
        D = np.asarray(Q, float) - o
        return D @ U, D @ W, D @ N

    u, v, z = uvz(P)
    s = max(float(np.sqrt(np.mean(u * u + v * v))), 1e-6)
    A = np.stack([np.ones_like(u), u / s, v / s, (u / s) ** 2, u * v / s ** 2, (v / s) ** 2], 1)
    reg = np.diag([0, 0, 0, 1.0, 1.0, 1.0]) * ridge * len(u)
    c = np.linalg.solve(A.T @ A + reg, A.T @ z)

    def f(Q):
        qu, qv, qz = uvz(Q)
        B = np.stack([np.ones_like(qu), qu / s, qv / s, (qu / s) ** 2, qu * qv / s ** 2, (qv / s) ** 2], 1)
        h = B @ c
        return qz - h, o + qu[:, None] * U + qv[:, None] * W + h[:, None] * N

    return f


def rest_on(G: np.ndarray, sel: np.ndarray, surf: callable, normal: np.ndarray, lift: float = 0.003,
            weight: np.ndarray | None = None, from_row: int = 1) -> tuple:
    """Rows from_row.. of the selected stations moved along `normal` onto the surface `surf` (support_surface) +
    `lift` (the cloth's thickness over it), by weight [n] (an eased transition). The pressed rest of an end that LIES
    on something (a collar end on the lapel carried past the gorge) instead of turned into a plane (ak's v1 / v2: the
    end in the lapel's plane floated 20-29 mm and stood as wings). Returns (G, {"moved_mm": per station max})."""
    G = np.array(G, float)
    n, m = G.shape[:2]
    N = _unit(np.asarray(normal, float))
    w = np.where(np.asarray(sel, bool), 1.0 if weight is None else np.asarray(weight, float), 0.0)
    mv = np.zeros(n)
    for i in np.where(w > 0)[0]:
        # LAID, not dropped: each segment of the column kept at its length, stepped along its own direction taken into
        # the surface's tangent plane and set on the surface + lift (dropping points along the normal stretched the
        # end 29 -> 45 mm and crushed rows 1-5 onto the seam row)
        L_ = np.zeros_like(G[i])
        L_[:from_row] = G[i, :from_row]
        for j in range(from_row, m):
            seg = G[i, j] - G[i, j - 1]
            ln = float(np.linalg.norm(seg))
            d = _unit(seg - (seg @ N) * N)
            P = L_[j - 1] + ln * d
            h, _ = surf(P[None])
            P = P + (lift * min(1.0, j / max(from_row + 1, 2)) - h[0]) * N
            L_[j] = L_[j - 1] + ln * _unit(P - L_[j - 1])
        Gi = (1 - w[i]) * G[i] + w[i] * L_
        mv[i] = float(np.linalg.norm(Gi - G[i], axis=1).max()) * 1000
        G[i] = Gi
    return G, {"moved_mm": np.round(mv, 1)}


def clear_self(X: np.ndarray, free: np.ndarray, gap: float, rounds: int = 6, margin: float = 1.6) -> tuple:
    """A grid piece's start [n, m, 3] cleared of what cloth_job.start_self_check calls crushed (a free vertex inside
    the contact `gap` of its own sheet, facing the same way): each such vertex moved off the face it nearly touches,
    along that face's normal, to margin x gap. al: the collar's columns crowd at the gorge corner (rows 1-3 next to
    the sewn edge's turn, 0.5-0.9 mm at a 1 mm gap). Returns (X, vertices moved)."""
    from .cloth_job import start_self_check
    X = np.array(X, float)
    n, m = X.shape[:2]
    F = grid_faces(n, m)
    P = X.reshape(-1, 3)
    pin = np.where(~np.asarray(free, bool).reshape(-1))[0]
    moved = set()
    for _ in range(rounds):
        arr = {"X": P, "F": F, "piece": np.zeros(len(P), np.int64), "carryIdx": pin}
        sc = start_self_check(arr, gap)
        if sc["ok"] or not sc["pairs"]:
            break
        for mm, v, f, fc in sc["pairs"]:
            a, b, c = P[F[f]]
            nf = _unit(np.cross(b - a, c - a))
            h = float((P[v] - a) @ nf)
            P[v] += nf * (np.sign(h) if h != 0 else 1.0) * max(0.0, margin * gap - abs(h))
            moved.add(int(v))
    return P.reshape(n, m, 3), len(moved)
