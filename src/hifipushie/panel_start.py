"""PANEL START (N2e of docs/proposals/step5_rewrite.md, "The build" 1): every point's start position from its piece's OWN
tapes (step 4's piece and edge tapes, step 3's lines: piece_start / draft_tapes), live, for the rolled panels to be
fitted to (chain_panels.Panels.fit_start). N2d started from a saved per-vertex X0 of the old roles placement; gone.

- EDGE-TAPED piece (step 4 names a tape for an edge: a collar's neck edge on the neckline): the edge's points (the
  outline between its named points) are laid on the tape by arc length from the centre line both ways (the -X half on
  the tape mirrored; a sided piece from its centre-line end, as piece_start.lay_on_tape); the rest of the flat stands
  up from its nearest edge point (offset along the tape by its flat offset along the edge, up by its offset off it).
- GIRTH-TAPED piece (it names girth loops; a .R piece reads them mirrored): rolled round the line through the loops'
  centres at their radius (+ GAP, interpolated by height), the grain along that line pointing up, its top at the top of
  the length paths it names, centred round the line at the angle of those paths; the cloth's outside (the flat's +z
  times its winding) faces out. Where the paths give no angle (they run on the line) the piece faces -Y, and pieces
  sharing the same loops spread round the line (`spin` turns them: several starts).
- NO TAPE: refused by name (P2), never guessed.
starts(cnet, body, skip, spin) -> (Xs (n, 3) per chain point, nan for skipped pieces, edge pulls, read).
Nothing here knows a garment, a piece's role or a wear state.
"""
from __future__ import annotations

import numpy as np

from .chain_core import GAP, ChainRefused, hand_of
from .piece_start import _at, _lift, from_centre

NO_ANGLE = 0.3  # paths whose mean lies nearer the line than this x the radius give no angle round it


def _grain(cnet, nm):
    g = np.radians(float((cnet.M.get("grain") or {}).get(nm, 90.0)))
    return np.array([np.cos(g), np.sin(g)])


def _wind(cnet, ids):
    from .chain_lay_net import _wind as w
    F = cnet.F[np.isin(cnet.F, ids).all(1)]
    return w(cnet.uv, F) if len(F) else 1.0


def _tapes(st, nm):
    T = st.get("tapes") or {}
    mir = [-1, 1, 1] if hand_of(nm) < 0 else [1, 1, 1]
    loops, paths = [], []
    for n in (st.get("pieces") or {}).get(nm) or []:
        if n in T:
            (loops if T[n]["kind"] == "loop" else paths).append(np.asarray(T[n]["pts"], float) * mir)
    return loops, paths


def _girth(cnet, nm, ids, loops, paths, spin):
    """Start positions of a girth-taped piece's points (module doc)."""
    C = np.array([L.mean(0) for L in loops])
    if len(loops) >= 2:
        a = np.linalg.svd(C - C.mean(0))[2][0]
    else:
        a = np.array([0.0, 0.0, 1.0])
    a = a if a[2] >= 0 else -a
    o = C.mean(0)
    hl = (C - o) @ a
    rl = np.array([np.linalg.norm((L - L.mean(0)) - np.outer((L - L.mean(0)) @ a, a), axis=1).mean() for L in loops])
    order = np.argsort(hl)
    hl, rl = hl[order], rl[order]
    e1 = np.cross(a, [1.0, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    P = np.concatenate(paths) if paths else np.zeros((0, 3))
    top = float(((P - o) @ a).max()) if len(P) else float(hl[-1])
    th0, how = None, "faces -Y (its paths give no angle)"
    if len(P):
        m = P.mean(0) - o
        m = m - (m @ a) * a
        if np.linalg.norm(m) > NO_ANGLE * rl.mean():
            th0, how = float(np.arctan2(m @ e2, m @ e1)), "at its paths' angle"
    if th0 is None:
        th0 = float(np.arctan2(-(e2[1]), -(e1[1])))  # (the angle of -Y round the line)
    th0 += spin
    uv = cnet.uv[ids]
    gd = _grain(cnet, nm)
    al = uv @ gd
    ac = uv @ np.array([-gd[1], gd[0]])
    w = _wind(cnet, ids)
    h = top - (al.max() - al)
    r = np.interp(h, hl, rl) + GAP
    th = th0 + w * (ac - 0.5 * (ac.min() + ac.max())) / r
    X = o + h[:, None] * a + r[:, None] * (np.cos(th)[:, None] * e1 + np.sin(th)[:, None] * e2)
    return X, {"tapes": "girth", "loops": len(loops), "angle": how, "radius_mm": [round(float(x * 1e3)) for x in rl]}


def _edge_ids(cnet, nm, arc, idx):
    """The piece's outline points from the arc's first named point to its last through the others (shorter way);
    idx: pattern vertex id -> chain point id."""
    pts = cnet.M.get("points") or {}
    names = [x for x in arc.split(">")]
    vs = []
    for n in names:
        k = f"{nm}:{n}"
        if k not in pts:
            raise ChainRefused(f"{nm}: edge arc {arc!r} names point {n!r} the pattern doesn't have: back to step 4")
        vs.append(int(idx[int(pts[k])]))
    lp = list(cnet.loop(nm))
    pos = {v: i for i, v in enumerate(lp)}
    out = []
    near = lambda v: pos[v] if v in pos else int(np.argmin(np.linalg.norm(cnet.uv[lp] - cnet.uv[v], axis=1)))
    for p, q in zip(vs[:-1], vs[1:]):
        i, j = near(p), near(q)
        n = len(lp)
        fw = [lp[(i + t) % n] for t in range((j - i) % n + 1)]
        bw = [lp[(i - t) % n] for t in range((i - j) % n + 1)]
        seg = fw if len(fw) <= len(bw) else bw
        out += seg if not out else seg[1:]
    return np.array(out, np.int64)


def _edge(cnet, nm, ids, em, T, body, idx, Xs=None):
    """Start positions of an edge-taped piece and the pulls of its edge points to their tape (module doc)."""
    names = sorted({e["tape"] for e in em.values()})
    if len(names) != 1 or names[0] not in T:
        raise ChainRefused(f"{nm}: its edge must name one step-3 tape, it names {names}: back to step 4")
    Q = from_centre(T[names[0]]["kind"], T[names[0]]["pts"])
    E = np.unique(np.concatenate([_edge_ids(cnet, nm, e["arc"], idx) for e in em.values()]))
    # (the edge's points ordered along the OUTLINE, arc length measured along it (never across a gap between the
    # edge's arcs): from the centre line's crossing nearer the edge (a centre piece), or from the end nearer x = 0)
    lp = np.array(cnet.loop(nm))
    U = cnet.uv[lp]
    cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.r_[U, U[:1]], axis=0), axis=1))]
    per, at = cum[-1], cum[:-1]
    on = np.isin(lp, E)
    if hand_of(nm):
        k = np.flatnonzero(on)
        sp = (at[k] - at[k[0]]) % per
        gap = np.diff(np.r_[np.sort(sp), per])
        st0 = at[k[(np.argsort(sp)[(int(np.argmax(gap)) + 1) % len(k)])]]  # (the arc starts after its largest gap)
        s = (at[k] - st0) % per
        o = np.argsort(s)
        E, s = lp[k[o]], s[o]
        U = cnet.uv[E]
        d = s if abs(U[0, 0]) <= abs(U[-1, 0]) else s[-1] - s
    else:  # (a centre piece: each half goes to the side of the started pieces it is sewn to (C444: a winding rule put
        # both halves on the wrong side, crossing every seam); sewn to none started: the half whose cloth outside (flat
        # +z x winding) faces out with its flat +x at -X, seen from behind with the grain up, is the worn -X half)
        xs = np.flatnonzero(np.sign(U[:, 0]) != np.sign(np.roll(U[:, 0], -1)))  # (outline crossings of x = 0)
        sd = lambda c: (at[on] - at[c] + per / 2) % per - per / 2
        c = xs[np.argmin([np.abs(sd(c)).mean() for c in xs])]
        E, U = lp[on], cnet.uv[lp[on]]
        side = -_wind(cnet, ids)
        if Xs is not None:
            mine = cnet.piece == cnet.pid(nm)
            a, b = cnet.sew[:, 0], cnet.sew[:, 1]
            a, b = np.r_[a, b], np.r_[b, a]
            k = mine[a] & ~mine[b] & ~np.isnan(Xs[b, 0])
            vote = float((np.sign(cnet.uv[a[k], 0]) * np.sign(Xs[b[k], 0])).sum())
            side = np.sign(vote) if vote else side
        d = np.abs(sd(c)) * np.sign(side * U[:, 0])
        o = np.argsort(sd(c))
        E, U, d = E[o], U[o], d[o]
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(U, axis=0), axis=1))]
    sgn = -1.0 if hand_of(nm) < 0 else 1.0
    P, L = _at(Q, np.abs(d))
    P[d * sgn < 0] *= [-1, 1, 1]
    P = _lift(body.contact, P, GAP)
    if np.abs(d).max() > L + 0.002:
        raise ChainRefused(f"{nm}: tape {names[0]!r} runs {L * 1e3:.0f} mm from the centre line, its edge needs "
                           f"{np.abs(d).max() * 1e3:.0f} mm: back to step 3")
    # (the rest of the flat from its nearest edge point: along the tape by its flat offset along the edge, up by its
    # offset off the edge into the piece; a stiff piece stands from its edge, the fit turns it)
    tf = np.gradient(U, axis=0)
    tf /= np.maximum(np.linalg.norm(tf, axis=1, keepdims=True), 1e-12)
    t3 = np.gradient(P, axis=0)
    t3 /= np.maximum(np.linalg.norm(t3, axis=1, keepdims=True), 1e-12)
    nf = np.c_[-tf[:, 1], tf[:, 0]]
    inner = cnet.uv[ids].mean(0)
    nf *= np.sign(((inner - U) * nf).sum(1))[:, None] + (((inner - U) * nf).sum(1) == 0)[:, None]
    k = np.argmin(np.linalg.norm(cnet.uv[ids][:, None] - U[None], axis=2), axis=1)
    D = cnet.uv[ids] - U[k]
    X = P[k] + (D * tf[k]).sum(1)[:, None] * t3[k] + np.abs((D * nf[k]).sum(1))[:, None] * np.array([0, 0, 1.0])
    pull = {"ids": E, "to": P, "weight": 1.0, "name": f"{nm} edge on {names[0]}"}
    return X, pull, {"tapes": "edge", "tape": names[0], "edge_mm": round(float(d.max() - min(d.min(), 0.0)) * 1e3, 1),
                     "tape_mm": round(L * 1e3, 1)}


def starts(cnet, keep, body, skip=(), spin=None):
    """(Xs, edge pulls, read) (module doc). keep: the chain points' pattern vertex ids (chain_network); spin: {piece:
    radians} turning a girth-taped piece round its line."""
    idx = -np.ones(int(np.max(keep)) + 1, np.int64)
    idx[keep] = np.arange(len(keep))
    st = cnet.M.get("starts") or {}
    T = st.get("tapes") or {}
    spin = spin or {}
    Xs = np.full((cnet.n, 3), np.nan)
    pulls, rd = [], {}
    groups: dict = {}
    edged = lambda nm: (st.get("edges") or {}).get(nm) or (st.get("edges") or {}).get(nm[:-2] if hand_of(nm) else nm)
    order = sorted(range(len(cnet.names)), key=lambda p: bool(edged(cnet.names[p])))  # (edge-taped last: sides by seams)
    for p in order:
        nm = cnet.names[p]
        if nm in skip:
            continue
        ids = np.where(cnet.piece == p)[0]
        em = edged(nm) or {}
        loops, paths = _tapes(st, nm)
        if em:
            X, pull, r = _edge(cnet, nm, ids, em, T, body, idx, Xs)
            pulls.append(pull)
        elif loops:
            X, r = _girth(cnet, nm, ids, loops, paths, spin.get(nm, 0.0))
            if r["angle"].startswith("faces"):  # (no angle of its own: pieces sharing its loops spread round the line)
                key = (tuple(sorted((st.get("pieces") or {}).get(nm) or [])), hand_of(nm))
                groups.setdefault(key, []).append(nm)
                k = len(groups[key]) - 1
                if k:
                    X, r = _girth(cnet, nm, ids, loops, paths, spin.get(nm, 0.0) + 2 * np.pi * k / 2)
                r["spread"] = k
        else:
            raise ChainRefused(f"step 4 names no tape for {nm}: back to step 4, declare tapes.{nm} (the step-3 tapes it "
                               "was drafted on); a piece starts where it was measured, never guessed")
        Xs[ids] = X
        rd[nm] = r
    return Xs, pulls, rd
