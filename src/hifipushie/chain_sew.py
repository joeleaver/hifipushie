"""FLAT THEN SEW (F7, C321-): the soft start is exact at every moment, the way Marvelous Designer / CLO start a garment.

Joe (2026-11-03): "If we're measuring correctly, how could it ever fail _or_ stretch?" F6 found every build stretched at
its START (the trousers 1063 %): rows wrapped round a loop's axis at each flat row's own width are not the flat. Now:

1. ARRANGE (`arrange`): every soft piece is its own flat mesh, laid round its body region a stand-off away. The region
   is the old start's (piece_start: the loops / paths its own measurements were taken on, its side, front / back): that
   start is only a GUIDE. Each piece is laid on ONE cylinder round a straight axis (a tube: its measured axis over the
   piece's reach; a panel: upright through the body's middle at its height): a single cylinder bend is exact, so every
   link reads its cut. The flat's along (y) runs along the axis, its across (x) round it; which way each runs, where the
   piece's middle faces and the radius come from the guide (the radius never less than the body under it plus
   STANDOFF, never so small that the piece laps itself).
2. SEW (`sew`): each seam's sewn point pairs pulled together in SEW_ROUNDS steps (the gap to close shrinks by a share
   each round), every pattern length a hard constraint at every round (chain_net.project: the chains exact, each flat
   mesh edge at most its flat length, so cloth bends and folds and never stretches; lengths solved last in each round),
   the body an obstacle at GAP. Stiff parts (bands, stands, cuffs) are built first and held.
3. A seam whose gap stays over SEW_TOL once every length holds is a PATTERN FAULT named there (`gate_sew`): the seam,
   the gap in mm, the pieces' measurement lists; back to step 4. It is never stretched shut.

Gates (chain_stages.check): ARRANGE (`arrange_length`: lengths as laid, a verdict at MAX_FREE_PCT; reads ~0) and SEW
(`sew_length`, `sew:<seam>` gaps). The START gate then reads the sewn start, its `start_length` a verdict too.
Nothing names a garment or a limb: axes, sides and faces are the guide's, the guide is the pattern's own measurements.
"""
from __future__ import annotations

import numpy as np

STANDOFF = 0.012  # m: a laid piece's least distance off the body under it (outside GAP: the sew pulls it in)
SEW_ROUNDS = 80  # most rounds the seams close in (each round: the pull, then the lengths alone)
SEW_ITERS = 6  # project passes for the pull (the lengths alone get three times as many)
PULL = 0.008  # m: the most a sewn pair comes nearer in one round (small: the lengths restore it without a jump)
CLOSE = 0.0003  # m: the pull runs on until every sewn pair is this near (then each group shares its mean)
STALL = 4  # rounds: the summed seam gaps falling by less than 0.05 mm a pair a round over these = stalled
SEW_TOL = 0.002  # m: a seam is closed when its widest sewn pair is this near (the chain stage merges them)
REACH = 0.04  # m: body this far outside the guide's own radius still counts as under the piece
RADII = (1.0, 1.1, 1.2, 1.35, 1.5, 1.75, 2.0, 2.5, 3.0)  # the radius tried, x the guide's / the flat's own
INSIDE_SHARE = 0.05  # share of a laid group's points allowed nearer the body than STANDOFF (the sew's floor lifts them)
LAP = 0.97  # a piece laid round a cylinder covers at most this share of its turn (never laps itself)
SOFT_FLOOR = None  # (the floor is chain_garment.GAP; read at call time)


def _unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n > 1e-12, n, 1.0)


def _soft(b) -> list:
    return list(b.roles.panels) + list(b.roles.tubes)


# ---------------------------------------------------------------- lengths at vertex level (pieces apart)
def vertex_lengths(b, X) -> dict:
    """Every chain link on its own piece (chain_v, not the sewn roots: pieces lie apart until sewn) and every soft mesh
    edge against its flat length: worst chain %, and per piece edges p50 / p90 / max % (+ stretched)."""
    net = b.net
    X = np.asarray(X, float)
    soft = np.isin(net.piece, [net.pid(p) for p in _soft(b)])
    cv = np.asarray(net.chain_v)
    k = soft[cv[:, 0]]
    l = np.linalg.norm(X[cv[k, 1]] - X[cv[k, 0]], axis=1)
    sg = (l / np.maximum(np.asarray(net.chain_L)[k], 1e-9) - 1) * 100
    e = np.abs(sg)  # (a chord across a bend reads a little short: 1 - sinc, never long)
    out = {"chain_worst_pct": round(float(e.max()), 3) if len(e) else 0.0,
           "chain_stretch_pct": round(float(max(sg.max(), 0.0)), 3) if len(e) else 0.0, "edges": {}}
    E, L0 = net.edges, net.flat
    ee = (np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.maximum(L0, 1e-9) - 1) * 100
    for p in _soft(b):
        m = net.piece[E[:, 0]] == net.pid(p)
        if m.any():
            out["edges"][p] = [round(float(x), 2) for x in (np.percentile(ee[m], 50), np.percentile(ee[m], 90), ee[m].max())]
    out["edge_worst_pct"] = max([v[2] for v in out["edges"].values()] or [0.0])
    return out


# ---------------------------------------------------------------- 1. arrange
def _axis(b, p: str, G: np.ndarray):
    """(point, direction) of the straight axis piece p is laid round: a tube's measured axis over the guide's reach,
    else upright through the body's middle at the guide's height."""
    from .piece_start import axis_for
    if p in b.roles.tubes:
        ax = axis_for(b, p)
        A = np.asarray(ax.C)
        near = np.argmin(np.linalg.norm(G[::max(1, len(G) // 400), None, :] - A[None, ::2, :], axis=2), axis=1) * 2
        lo, hi = int(near.min()), int(near.max())
        S = A[lo:hi + 1] if hi - lo >= 2 else A
        c = S.mean(0)
        d = _unit(np.linalg.svd(S - c)[2][0]) if len(S) > 2 else np.array([0, 0, 1.0])
        return c, d * np.sign(d[2] or 1.0)
    V = np.asarray(b.body.V)
    z0, z1 = float(G[:, 2].min()), float(G[:, 2].max())
    k = (V[:, 2] > z0) & (V[:, 2] < z1)
    W = V[k] if k.sum() > 20 else V
    return np.array([0.0, float(W[:, 1].mean()), float(G[:, 2].mean())]), np.array([0, 0, 1.0])


def _frame(d):
    e1 = _unit(np.cross(d, [0, 1.0, 0]) if abs(d[1]) < 0.9 else np.cross(d, [1.0, 0, 0]))
    return e1, np.cross(d, e1)


def _fit(b, p: str, G: np.ndarray, c=None, d=None) -> dict:
    """Piece p's cylinder read off its guide G: axis (c, d), frame, the guide's heights / angles / radii, which way the
    flat's y runs along the axis (sy), the least radius the flat needs (never lapping itself)."""
    uv = b.net.uv[b.net.verts(p)]
    if c is None:
        c, d = _axis(b, p, G)
    e1, e2 = _frame(d)
    Q = G - c
    h = Q @ d
    rv = Q - np.outer(h, d)
    sy = 1.0 if np.corrcoef(h, uv[:, 1])[0, 1] >= 0 else -1.0
    return dict(p=p, uv=uv, c=c, d=d, e1=e1, e2=e2, h=h, phi=np.arctan2(rv @ e2, rv @ e1), rg=np.linalg.norm(rv, axis=1),
                sy=sy, h0=float(np.mean(h - sy * uv[:, 1])), Rmin=float(np.ptp(uv[:, 0])) / (2 * np.pi * LAP))


def _clear(b, f: dict, R: float, span=None) -> float:
    """The radius that clears the body the guide went round (in the piece's reach; within its angles when given) by
    STANDOFF."""
    V = np.asarray(b.body.V) - f["c"]
    hb = V @ f["d"]
    k = (hb > f["h"].min() - 0.01) & (hb < f["h"].max() + 0.01)
    rb = np.linalg.norm(V[k] - np.outer(hb[k], f["d"]), axis=1)
    under = rb < float(f["rg"].max()) + REACH  # (the body the guide went round, not the other leg or a hand)
    if span is not None:
        pb = np.arctan2(V[k] @ f["e2"], V[k] @ f["e1"])
        under &= np.abs(np.angle(np.exp(1j * (pb[:, None] - span[None, :])))).min(axis=1) < 0.15
    return max(R, float(rb[under].max()) + STANDOFF) if under.any() else R


def _clear_share(b, fits: dict, R0: float) -> float:
    """The least radius from R0 up (RADII steps) at which at most INSIDE_SHARE of the group's points, each laid the
    guide's way round, lie nearer the body than STANDOFF (a hip the leg's cylinder passes is the sew's to wrap, not a
    reason to lay the whole leg a hip's width out)."""
    for k in RADII:
        R = R0 * k
        P = np.concatenate([_place(f, f["uv"], 1.0, float(np.angle(np.mean(np.exp(1j * (f["phi"] - f["uv"][:, 0] / R))))),
                                   R) for f in fits.values()])
        if float((b.body.contact.query(P[::3])[0] < STANDOFF).mean()) <= INSIDE_SHARE:
            return R
    return R


def _place(f: dict, uv, sx: float, a: float, R: float) -> np.ndarray:
    th = a + sx * uv[:, 0] / R
    hh = f["h0"] + f["sy"] * uv[:, 1]
    return f["c"] + np.outer(hh, f["d"]) + R * (np.cos(th)[:, None] * f["e1"] + np.sin(th)[:, None] * f["e2"])


def lay(b, p: str, f: dict, R: float, X: np.ndarray, placed: np.ndarray, taken=()) -> tuple[np.ndarray, dict]:
    """Piece p on its cylinder (exact by construction): which way round (sx) and where its middle faces (a) chosen so its
    seams lie nearest the cloth already placed (stiff parts built first, the pieces laid before it); with nothing placed
    to sew to, the guide's own way round. Returns (positions, how)."""
    net = b.net
    v = net.verts(p)
    loc = -np.ones(net.n, np.int64)
    loc[v] = np.arange(len(v))
    S = net.sew
    mine = np.r_[S[(loc[S[:, 0]] >= 0) & placed[S[:, 1]]], S[(loc[S[:, 1]] >= 0) & placed[S[:, 0]]][:, ::-1]]
    uv = f["uv"]
    best = None
    for sx in (1.0, -1.0):
        ag = float(np.angle(np.mean(np.exp(1j * (f["phi"] - sx * uv[:, 0] / R)))))
        cands = [ag] if not len(mine) else list(np.linspace(-np.pi, np.pi, 120, endpoint=False)) + [ag]
        for a in cands:
            if len(mine):
                cost = float(np.sum((_place(f, uv[loc[mine[:, 0]]], sx, a, R) - X[mine[:, 1]]) ** 2))
                ac = a + sx * float(np.mean(uv[:, 0])) / R  # (never on top of a piece of its tube already laid)
                hw = float(np.ptp(uv[:, 0])) / (2 * R)
                for aq, hq in taken:
                    o = max(0.0, hw + hq - abs(float(np.angle(np.exp(1j * (ac - aq))))))
                    cost += (o * R) ** 2 * len(mine)
            else:
                cost = float(np.mean(np.angle(np.exp(1j * (f["phi"] - a - sx * uv[:, 0] / R))) ** 2))
            if best is None or cost < best[0]:
                best = (cost, sx, a)
    _, sx, a = best
    f["taken"] = (a + sx * float(np.mean(uv[:, 0])) / R, float(np.ptp(uv[:, 0])) / (2 * R))
    how = {"radius_mm": round(R * 1e3, 1), "axis": [round(float(x), 3) for x in f["d"]],
           "turned_by": "its seams to the cloth placed" if len(mine) else "the guide"}
    return _place(f, uv, sx, a, R), how


def arrange(b, guide: np.ndarray) -> np.ndarray:
    """Every soft piece laid on a cylinder (a tube group's pieces on one, round its measured axis), stiff pieces as
    built, .R pieces as their .L's mirror. Said in reads["sew"]["laid"]."""
    from .chain_stages import mirror_starts
    net = b.net
    G = np.asarray(guide, float)
    X = np.array(G, float)
    stiff = b._stiff_mask()
    X[stiff] = b.X[stiff]
    placed = stiff.copy()
    laid, done = {}, set()
    soft = _soft(b)
    for p in soft:
        if p in done or p.endswith(".R") and p[:-2] + ".L" in soft:
            continue
        grp = [q for q in ((b.roles.tube_groups or {}).get(p) or [p]) if q not in done]
        grp.sort(key=lambda q: -float(np.ptp(net.uv[net.verts(q), 0])))  # (the widest first)
        f0 = _fit(b, grp[0], G[net.verts(grp[0])])
        fits = {q: f0 if q == grp[0] else _fit(b, q, G[net.verts(q)], f0["c"], f0["d"]) for q in grp}
        R = max(float(np.percentile(np.concatenate([f["rg"] for f in fits.values()]), 75)),
                sum(f["Rmin"] for f in fits.values()))
        R = _clear_share(b, fits, R)
        taken = []
        for q in grp:
            v = net.verts(q)
            X[v], laid[q] = lay(b, q, fits[q], R, X, placed, taken)
            taken.append(fits[q]["taken"])
            placed[v] = True
            done.add(q)
    for q in soft:
        if q not in laid and q[:-2] + ".L" in laid:
            laid[q] = dict(laid[q[:-2] + ".L"], turned_by=f"the mirror of {q[:-2]}.L")
    b.reads.setdefault("sew", {})["laid"] = laid
    return mirror_starts(b, X)  # (a .R piece laid as its .L's mirror: a reflection, exact)


# ---------------------------------------------------------------- 2. sew
def _links(b):
    """Vertex-level lengths: soft chains exact (chain_v), every soft mesh edge at most its flat length."""
    net = b.net
    cv, cL = np.asarray(net.chain_v), np.asarray(net.chain_L)
    E, L0 = net.edges, net.flat
    return (np.r_[cv[:, 0], E[:, 0]], np.r_[cv[:, 1], E[:, 1]], np.r_[cL, L0],
            np.r_[np.ones(len(cL), bool), np.zeros(len(L0), bool)])


def seam_gaps(b, X) -> dict:
    """{seam index: (widest sewn pair gap m, its vertex a, b)}."""
    net = b.net
    S = net.sew
    ss = np.asarray(net.M.get("sew_seam", np.zeros(len(S), int)))
    g = np.linalg.norm(X[S[:, 0]] - X[S[:, 1]], axis=1)
    out = {}
    for si in np.unique(ss):
        k = np.where(ss == si)[0]
        j = k[int(np.argmax(g[k]))]
        out[int(si)] = (float(g[j]), int(S[j, 0]), int(S[j, 1]))
    return out


def sew(b, X, rounds: int = SEW_ROUNDS, iters: int = SEW_ITERS) -> np.ndarray:
    """Close every seam a PULL at a time, lengths hard every round: each sewn pair may come at most PULL nearer (at
    most its gap less PULL), then the lengths alone are solved to convergence (lengths last: never stretched shut).
    Stops when every seam is within SEW_TOL, or when the widest gap stalls (a seam the lengths won't let close: the
    gate names it). `rounds` caps the rounds. Reads in b.reads["sew"]."""
    from .chain_garment import GAP
    from .chain_net import project
    net = b.net
    X = np.array(X, float)
    held = b._stiff_mask().copy()
    soft_ids = np.where(~held & np.isin(net.piece, [net.pid(p) for p in _soft(b)]))[0]
    I, J, L, E = _links(b)
    S = net.sew
    floor = [(b.body.contact, soft_ids, GAP)]
    log, hist = [], []

    def lengths(Y, n):  # (with the body as the floor; where the floor and the lengths can't both hold, the lengths win:
        # the cloth left through the body is read by START's inside rows, never stretched round it)
        Y, rd = project(Y, I, J, L, E, held, floor, iters=n, step=PULL)
        if max(rd.get("worst_exact_pct", 0), rd.get("worst_atmost_pct", 0)) > 0.5:
            Y, rd = project(Y, I, J, L, E, held, [], iters=n, step=PULL)
        return Y, rd
    gap_of = lambda Y: np.linalg.norm(Y[S[:, 0]] - Y[S[:, 1]], axis=1)
    for r in range(rounds):
        g = gap_of(X)
        if not len(S) or g.max() <= CLOSE:
            break
        tgt = np.maximum(g - PULL, 0.0)
        X, _ = project(X, np.r_[I, S[:, 0]], np.r_[J, S[:, 1]], np.r_[L, tgt], np.r_[E, np.zeros(len(S), bool)],
                       held, floor, iters=iters, step=PULL)
        X, rd = lengths(X, 3 * iters)  # lengths last: never stretched shut
        gm = float(gap_of(X).max())
        log.append((r, round(gm * 1e3, 1), rd.get("worst_exact_pct"), rd.get("worst_atmost_pct")))
        hist.append(float(gap_of(X).sum()))
        if len(hist) > STALL and hist[-1 - STALL] - hist[-1] < STALL * 1e-3 * max(1, len(S)) * 0.05:
            break  # (stalled: the lengths hold the seams apart)
    X, _ = lengths(X, 10 * iters)  # (the lengths have the last word)
    if len(S) and gap_of(X).max() <= SEW_TOL:  # (closed: each sewn group at its mean, a sub-mm move, then lengths)
        rt = net.root
        M_ = np.zeros((net.n, 3))
        np.add.at(M_, rt, X)
        cnt = np.bincount(rt, minlength=net.n)
        Xs = (M_ / np.maximum(cnt, 1)[:, None])[rt]
        X = np.where(held[:, None] | (cnt[rt] < 2)[:, None], X, Xs)
    rs = b.reads.setdefault("sew", {})
    rs["rounds"] = log
    rs["lengths"] = vertex_lengths(b, X)
    rs["gaps_mm"] = {seam_name(b, si): round(g * 1e3, 1) for si, (g, _, _) in seam_gaps(b, X).items()}
    return X


def seam_name(b, si: int) -> str:
    """A seam by its pieces (the sewn pair's two sides): 'front.L~back.L#3'."""
    net = b.net
    ss = np.asarray(net.M.get("sew_seam", np.zeros(len(net.sew), int)))
    k = np.where(ss == si)[0]
    if not len(k):
        return f"#{si}"
    a, c = net.sew[k[0]]
    return f"{net.names[net.piece[a]]}~{net.names[net.piece[c]]}#{si}"


# ---------------------------------------------------------------- gates (chain_stages GATES "arrange", "sew")
def gate_arrange(b, X) -> dict:
    from .chain_garment import MAX_FREE_PCT
    from .chain_stages import _row, verdict
    ln = vertex_lengths(b, X)
    w = max(ln["chain_stretch_pct"], ln["edge_worst_pct"])  # (stretch: a chord across a bend reads a little short)
    rows = [_row("arrange_length", round(w, 3), MAX_FREE_PCT, w <= MAX_FREE_PCT,
                 "MAX_FREE_PCT: each piece laid flat on one cylinder (exact): every chain and mesh edge at its cut",
                 "the ARRANGE lay (chain_sew.lay) is not exact: a bug in the lay, not the pattern")]
    return verdict("arrange", rows, {"lengths": ln, "laid": (b.reads.get("sew") or {}).get("laid")})


def gate_sew(b, X) -> dict:
    from .chain_garment import MAX_FREE_PCT
    from .chain_stages import _row, verdict
    ln = vertex_lengths(b, X)
    w = max(ln["chain_stretch_pct"], ln["edge_worst_pct"])  # (stretch: a chord across a bend reads a little short)
    rows = [_row("sew_length", round(w, 3), MAX_FREE_PCT, w <= MAX_FREE_PCT,
                 "MAX_FREE_PCT: the sew holds every length at every round (lengths solved last)",
                 "the SEW solve stretched cloth: a bug in chain_sew.sew, not the pattern")]
    meas = ((b.net.M.get("starts") or {}).get("pieces") or {})
    nr = len((b.reads.get("sew") or {}).get("rounds") or [])
    for si, (g, va, vb) in sorted(seam_gaps(b, X).items()):
        pa, pb = b.net.names[b.net.piece[va]], b.net.names[b.net.piece[vb]]
        names = sorted(set(meas.get(pa) or []) | set(meas.get(pb) or []))
        rows.append(_row(f"sew:{seam_name(b, si)}", round(g * 1e3, 1), round(SEW_TOL * 1e3, 1), g <= SEW_TOL,
                         "a seam closes by bending alone, every pattern length held (chain_sew.sew); limit SEW_TOL",
                         f"PATTERN FAULT: {pa}{b._near_point(va, pa)} can't reach {pb}{b._near_point(vb, pb)} without "
                         f"stretch ({g * 1e3:.0f} mm short, every length held, {nr} sew rounds): the pieces too small "
                         f"round the body there; check the measurements / ease they were drafted from "
                         f"({', '.join(names) or 'none listed'}) at step 4. (UNPROVEN, F7: a quasi-static sew can also "
                         f"stall short of a seam that closes; when step 4's body_lengths rows pass there, suspect the sew)",
                         "mm"))
    return verdict("sew", rows, {"lengths": ln, "gaps_mm": (b.reads.get("sew") or {}).get("gaps_mm"),
                                 "rounds": (b.reads.get("sew") or {}).get("rounds")})


def flat_then_sew(b, guide: np.ndarray) -> np.ndarray:
    """THE START: arrange (gated), sew (gated); the sewn copies then share one place (the chain stage merges them)."""
    from . import chain_stages as cst
    X = arrange(b, guide)
    b.stage_arranged = X.copy()
    cst.check(b, "arrange", X)
    X = sew(b, X)
    cst.check(b, "sew", X)
    return X
