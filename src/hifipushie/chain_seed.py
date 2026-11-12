"""CHAIN SEED (N2 of docs/proposals/step5_rewrite.md, "The build" steps 1-2): step 5's start from the TAPES alone, and
what chain_solve needs beside it (pulls, folds, ties, ply bindings). No role names, no garment names, no wear states.

Joe (2026-11-11): "lengths given, only bends chosen"; "place where we measure". The old start laid each piece by a RULE
for its role (rings round the neck, torso hulls, limb axes) and held it. Here every piece starts where step 3 measured
the lines step 4 says it was drafted on, and nothing is held: the seed is only where chain_solve starts.

1. A piece naming no step-3 tape with geometry (plies, floating layers and inside pieces excepted: they follow their
   host) is REFUSED by name (P2's rule), never guessed.
2. EDGE ON A TAPE: a piece with an edge step 4 names on a tape (starts.edges) has that edge (its longest outline run
   sewn to cloth outside its own part) laid along the tape by arc length from the end they share (piece_start.lay_on_tape:
   a centre piece from its middle, the -X half mirrored). Its interior goes off that edge by its flat distance, along
   the body's surface direction across the edge, to the side away from the cloth it is sewn to.
3. BETWEEN TAPES: a piece with girth loops and length paths is mapped onto the body between them. The loops' centres give
   an axis; each loop is a radius profile round it; a flat point's height below the piece's top is arc length down its
   highest length path (the top of the piece at that path's top, P2's panel rule), which gives its level on the axis;
   at that level the ring between the neighbouring loops (clamped past the end ones) is walked by the point's flat x
   (the draft's x = 0 line) from an ORIGIN: where the ring crosses the centre line at the front or the back, or where the
   length path crosses it, either way round. Which of these six is the one the TAPES and the SEWING say: first the one
   lying nearest its own length paths (place where measured), then sweeps adding how far its sewn points land from their
   partners, until none changes (seam distance alone from a blind first pick stuck every torso piece on the front: a
   local minimum where fronts and backs agreed with each other). Points inside the body are lifted GAP out.
4. FOLLOWERS (chain_holds.read: plies, floating layers, inside pieces): bound to their host by chain_solve_plies (a
   LAYER per layer on the host's inner side, the side its normals point away from the body) and seeded there.
PULLS: the points laid on an edge tape, and the points on a girth loop's level, pulled (soft) to where they were laid.
FOLDS: step 2's planned turn per fold, split over the draft's rows (cloth.mesh puts 2 rows on a fold, each turning half).
TIES: each closure's tied pairs (closure_ties via chain_plan.apply_tie), a LAYER apart.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from scipy.spatial import cKDTree

from .chain_core import GAP, LAYER, ChainRefused

K = 256  # samples round a ring
LOOP_PULL = 0.006  # m: points within this of a girth loop's level are pulled to it


def outline(net, piece: str) -> np.ndarray:
    """The piece's outer boundary loop, ordered (its longest boundary cycle)."""
    v = set(net.verts(piece).tolist())
    F = net.F[np.isin(net.F, list(v)).all(1)]
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1)
    u, c = np.unique(E, axis=0, return_counts=True)
    nb: dict = {}
    for a, b in u[c == 1]:
        nb.setdefault(int(a), []).append(int(b))
        nb.setdefault(int(b), []).append(int(a))
    best, seen = [], set()
    for s in nb:
        if s in seen:
            continue
        cyc, prev, cur = [s], None, s
        while True:
            seen.add(cur)
            nxt = [x for x in nb[cur] if x != prev and (x not in seen or (x == s and len(cyc) > 2))]
            if not nxt or nxt[0] == s:
                break
            prev, cur = cur, nxt[0]
            cyc.append(cur)
        if len(cyc) > len(best):
            best = cyc
    return np.array(best, np.int64)


def partners(net) -> dict:
    """{vertex: [vertices of other pieces sewn to it]}."""
    out: dict = {}
    for a, b in net.sew:
        if net.piece[a] != net.piece[b]:
            out.setdefault(int(a), []).append(int(b))
            out.setdefault(int(b), []).append(int(a))
    return out


class _Rings:
    """A piece's girth loops as radius profiles round the axis through their centres (module doc, 3)."""

    def __init__(self, loops, down):
        C = np.array([L.mean(0) for L in loops])
        a = np.asarray(down, float) if len(C) < 2 else C[-1] - C[0]
        if len(C) >= 2:
            a = np.linalg.svd(C - C.mean(0))[2][0]
        a = a / np.linalg.norm(a)
        if a @ down < 0:
            a = -a
        self.a, self.c0 = a, C.mean(0)
        e1 = np.array([0.0, -1.0, 0.0]) - a * (-a[1])
        if np.linalg.norm(e1) < 0.3:
            e1 = np.array([0.0, 0.0, 1.0]) - a * a[2]
        self.e1 = e1 / np.linalg.norm(e1)
        self.e2 = np.cross(a, self.e1)
        self.th = np.linspace(-np.pi, np.pi, K, endpoint=False)
        prof = []
        for L, c in zip(loops, C):
            rel = L - c
            t = np.arctan2(rel @ self.e2, rel @ self.e1)
            r = np.linalg.norm(rel - np.outer(rel @ a, a), axis=1)
            o = np.argsort(t)
            prof.append((float((c - self.c0) @ a), c - self.c0 - ((c - self.c0) @ a) * a,
                         np.interp(self.th, t[o], r[o], period=2 * np.pi)))
        prof.sort(key=lambda p: p[0])
        self.s = np.array([p[0] for p in prof])
        self.lat = np.array([p[1] for p in prof])
        self.r = np.array([p[2] for p in prof])

    def ring(self, s):
        """(K, 3) ring at axis level s, between the neighbouring loops (clamped past the end ones)."""
        if len(self.s) == 1 or s <= self.s[0]:
            lat, r = self.lat[0], self.r[0]
        elif s >= self.s[-1]:
            lat, r = self.lat[-1], self.r[-1]
        else:
            k = int(np.searchsorted(self.s, s)) - 1
            f = (s - self.s[k]) / (self.s[k + 1] - self.s[k])
            lat, r = (1 - f) * self.lat[k] + f * self.lat[k + 1], (1 - f) * self.r[k] + f * self.r[k + 1]
        dirs = np.outer(np.cos(self.th), self.e1) + np.outer(np.sin(self.th), self.e2)
        return self.c0 + s * self.a + lat + r[:, None] * dirs


def _origin(R, kind, P_path):
    """Index round ring R of the origin: the centre line's crossing at the front / back, or the length path's point."""
    if kind == "path":
        return int(np.argmin(np.linalg.norm(R - P_path, axis=1)))
    x = R[:, 0]
    want = -1.0 if kind == "front" else 1.0
    idx = [i for i in range(K) if x[i] * x[(i + 1) % K] <= 0 and np.sign(R[i, 1]) == want]
    return idx[0] if idx else None


def _walk(R, i0, u):
    """Points at arc lengths u (signed) round closed ring R from index i0."""
    Rr = np.roll(R, -i0, axis=0)
    Rc = np.r_[Rr, Rr[:1]]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Rc, axis=0), axis=1))]
    uu = np.mod(u, s[-1])
    return np.column_stack([np.interp(uu, s, Rc[:, k]) for k in range(3)])


def _between(net, piece, ct, cand):
    """(X of piece's vertices, levels, loop levels) for one candidate (origin kind, dir); None when it has no origin."""
    from .piece_start import _at, _lift, _tapes_of
    loops, paths = _tapes_of(net, piece)
    v = net.verts(piece)
    uv = net.uv[v]
    tops = [(max(P[0, 2], P[-1, 2]), P if P[0, 2] >= P[-1, 2] else P[::-1]) for _, P in paths]
    Q = max(tops, key=lambda t: t[0])[1] if tops else None
    down = (Q[-1] - Q[0]) if Q is not None else np.array([0, 0, -1.0])
    rg = _Rings([L for _, L in loops], down / np.linalg.norm(down))
    dy = uv[:, 1].max() - uv[:, 1]
    if Q is not None:
        Lq = float(np.linalg.norm(np.diff(Q, axis=0), axis=1).sum())
        P, _ = _at(Q, np.minimum(dy, Lq))
        P = P + np.maximum(dy - Lq, 0)[:, None] * (Q[-1] - Q[-2]) / np.linalg.norm(Q[-1] - Q[-2])
    else:
        P = rg.c0 + np.outer(dy - dy.min(), rg.a)
    s = (P - rg.c0) @ rg.a
    kind, sg = cand
    X = np.zeros((len(v), 3))
    lv = np.round(s / 0.004)
    for L_ in np.unique(lv):
        m = lv == L_
        R = rg.ring(float(L_) * 0.004)
        i0 = _origin(R, kind, P[m].mean(0))
        if i0 is None:
            return None
        X[m] = _walk(R, i0, sg * uv[m, 0])
    X = _lift(ct, X, GAP)
    return X, s, rg.s


def refuse_untaped(net, followers):
    st = net.M.get("starts") or {}
    T, names, edges = st.get("tapes") or {}, st.get("pieces") or {}, st.get("edges") or {}
    bad = [p for p in net.names if p not in followers and not any(n in T for n in names.get(p) or [])
           and not edges.get(p) and not edges.get(p[:-2])]
    if bad:
        raise ChainRefused(f"step 4 names no tape for {', '.join(bad)}: back to step 4, declare tapes (draft_pattern "
                           "declarations.tapes) on the step-3 tapes each piece was drafted on; nothing is guessed")


def _tape_cost(net, piece, Xp):
    """Mean distance from the piece's length paths to the piece laid there: it lies over the lines it was measured on."""
    from .piece_start import _tapes_of
    _, paths = _tapes_of(net, piece)
    if not paths:
        return 0.0
    return float(cKDTree(Xp).query(np.concatenate([P for _, P in paths]))[0].mean())


def _seam_cost(net, v, X, pt, Xall, done):
    d = []
    for k, a in enumerate(v):
        for b in pt.get(int(a), ()):
            if done[b]:
                d.append(np.linalg.norm(X[k] - Xall[b]))
    return float(np.mean(d)) if d else 0.0


CANDS = [(k, s) for k in ("front", "back", "path") for s in (1.0, -1.0)]


def _lay_edge(net, body, piece, own, pt, X, done, reads):
    """(module doc, 2) the piece's edge on its tape, its interior off it; returns (X of its verts, laid ids, laid X)."""
    from .piece_start import _lift, lay_on_tape
    v = net.verts(piece)
    ring = outline(net, piece)
    sewn = np.array([any(net.names[net.piece[b]] not in own for b in pt.get(int(a), ())) for a in ring])
    best, cur = (0, 0), None
    for i in range(2 * len(ring)):  # (the longest run round the loop)
        if sewn[i % len(ring)]:
            cur = i if cur is None else cur
            if i - cur + 1 > best[1] - best[0] and i - cur < len(ring):
                best = (cur, i + 1)
        else:
            cur = None
    chain = ring[np.arange(best[0], best[1]) % len(ring)]
    centre = net.uv[v, 0].min() < 0 < net.uv[v, 0].max()
    b = SimpleNamespace(net=net, body=body, reads=reads)
    pos = np.searchsorted(v, chain)
    anchor = [X[q] for a in chain for q in pt.get(int(a), ()) if done[q]]
    out = None
    for su in (1.0, -1.0):
        mid = int(np.argmin(np.abs(net.uv[chain, 0]))) if centre else None
        Pc, rd = lay_on_tape(b, piece, chain, mid=mid, su=su)
        t = np.gradient(Pc, axis=0)
        t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]
        _, nb = body.contact.query(Pc)
        side = np.cross(nb, t)
        side /= np.maximum(np.linalg.norm(side, axis=1), 1e-12)[:, None]
        dist, k = cKDTree(net.uv[chain]).query(net.uv[v])
        for sg in (1.0, -1.0):
            Xp = _lift(body.contact, Pc[k] + sg * dist[:, None] * side[k], GAP)
            Xp[pos] = Pc
            c = _seam_cost(net, v, Xp, pt, X, done)
            far = -np.linalg.norm(Xp.mean(0) - np.mean(anchor, axis=0)) if anchor else 0.0
            key = (round(c, 3), far)
            if out is None or key < out[0]:
                out = (key, Xp, rd)
    reads[piece] = {"edge_on": out[2]["tape"], "edge_mm": out[2]["edge_mm"], "tape_mm": out[2]["tape_mm"],
                    "seam_mm": round(out[0][0] * 1e3, 1)}
    return out[1], chain, out[1][pos]


def seed(net, body, wear: dict | None = None, holds=None) -> dict:
    """The start and chain_solve's inputs (module doc): {X0, pulls, folds, ties, plies, reads}."""
    from . import chain_holds, chain_solve_plies as cp
    wear = wear or {}
    h = holds or chain_holds.read(net)
    follow = {**h.plies, **h.layers, **h.inside}
    refuse_untaped(net, follow)
    part = {p: set(pa.pieces) for pa in h.parts for p in pa.pieces}
    edges = (net.M.get("starts") or {}).get("edges") or {}
    pt = partners(net)
    X = np.zeros((net.n, 3))
    done = np.zeros(net.n, bool)
    reads: dict = {}
    pulls = []
    ring_pieces = [p for p in net.names if p not in follow and not (edges.get(p) or edges.get(p[:-2]))]
    edge_pieces = [p for p in net.names if p not in follow and p not in ring_pieces]
    pick, lev = {}, {}
    for sweep in range(4):  # (each piece's origin and way round: the choice its sewing agrees with)
        changed = 0
        for p in ring_pieces:
            v = net.verts(p)
            best = None
            for c in CANDS:
                r = _between(net, p, body.contact, c)
                if r is None:
                    continue
                cost = _seam_cost(net, v, r[0], pt, X, done) * (sweep > 0) + _tape_cost(net, p, r[0])
                if best is None or cost < best[0] - 1e-6:
                    best = (cost, c, r)
            if best is None:
                raise ChainRefused(f"{p}: its tapes give no ring to lay it on: back to step 3 / 4 (its girth loops)")
            changed += pick.get(p) != best[1]
            pick[p], lev[p] = best[1], best[2]
            X[v], done[v] = best[2][0], True
        if sweep and not changed:
            break
    for p in ring_pieces:
        v = net.verts(p)
        Xp, s, ls = lev[p]
        near = np.min(np.abs(s[:, None] - ls[None]), axis=1) < LOOP_PULL
        if near.any():
            pulls.append({"ids": v[near], "to": Xp[near], "weight": 1.0, "name": f"{p} loops"})
        reads[p] = {"between": f"origin {pick[p][0]}, way {int(pick[p][1])}",
                    "seam_mm": round(_seam_cost(net, v, Xp, pt, X, done) * 1e3, 1)}
    for p in edge_pieces:
        v = net.verts(p)
        Xp, chain, Pc = _lay_edge(net, body, p, part.get(p, {p}), pt, X, done, reads)
        X[v], done[v] = Xp, True
        pulls.append({"ids": chain, "to": Pc, "weight": 1.0, "name": f"{p} edge"})
    sign = {p: _out_sign(net, p, X, body) for p in net.names if done[net.verts(p)].all()}
    k_of = {p: 1 for p in follow}
    for p, host in h.inside.items():
        k_of[p] = 1 + sum(1 for hh in h.layers.values() if hh == host)
    plies = []
    for p in sorted(follow, key=lambda q: follow[q] in follow):  # (a follower of a follower after its host)
        b = cp.bind(net, {p: follow[p]}, k_of, sign)[0]
        X[b["ids"]] = (b["w"][:, :, None] * X[b["tri"]]).sum(1) + b["d"][:, None] * cp.normals(X, b["tri"], b["hostF"])
        done[b["ids"]] = True
        sign[p] = _out_sign(net, p, X, body)
        plies.append(b)
        reads[p] = {"follows": follow[p], "layers_in": k_of[p]}
    folds = fold_rows(net, wear, sign)
    return {"X0": X, "pulls": pulls, "folds": folds, "ties": tie_pairs(net, wear), "plies": plies, "reads": reads}


def _out_sign(net, piece, X, body) -> float:
    """+1 when the piece's F normals point away from the body at the seed (area weighted), else -1."""
    v = net.verts(piece)
    F = net.F[np.isin(net.F, v).all(1)]
    c = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    _, nb = body.contact.query(X[F].mean(1))
    return 1.0 if float((c * nb).sum()) >= 0 else -1.0


def _uv_wind(net, piece) -> float:
    v = net.verts(piece)
    F = net.F[np.isin(net.F, v).all(1)]
    a, b, c = net.uv[F[:, 0]], net.uv[F[:, 1]], net.uv[F[:, 2]]
    u, w = b - a, c - a
    return 1.0 if float((u[:, 0] * w[:, 1] - u[:, 1] * w[:, 0]).sum()) >= 0 else -1.0


def fold_rows(net, wear, sign) -> list:
    """chain_solve folds: step 2's turn per planned fold, split over the draft's rows. Which way: the draft's fold sign
    read in the flat's own winding (sign x uv winding: +1 = onto the side the flat's +z faces), then into F's normals
    on the body by the piece's out sign."""
    out = []
    for bid, f in sorted((wear.get("folds") or {}).items()):
        fd = next((d for d in net.M.get("folds") or [] if d.get("piece") == f["on"] and d.get("name") == f["fold"]), None)
        if fd is None:
            raise ChainRefused(f"fold {bid}: the draft has no fold {f['fold']} on {f['on']}: back to step 4")
        rows = [np.asarray(r, np.int64) for r in fd.get("rows") or []]
        way = float(fd.get("sign", 1.0)) * _uv_wind(net, f["on"]) * sign.get(f["on"], 1.0)
        for k, r in enumerate(rows):
            out.append({"row": r, "turn_deg": float(f["turn_deg"]) / len(rows), "toward": way, "weight": 1.0,
                        "name": f"{bid}#{k}"})
    return out


def tie_pairs(net, wear) -> list:
    """(a, b, LAYER) for every tied pair of every closure (closure_ties, through chain_plan.apply_tie)."""
    from .chain_plan import apply_tie
    out = []
    ties = wear.get("ties") or {}
    for c in net.M.get("closures") or []:
        t = ties.get(c.get("name"))
        cl = apply_tie(c, t, net.uv) if t is not None else c
        for (a, b), on in zip(cl.get("v") or [], cl.get("closed") or []):
            if on:
                out.append((int(a), int(b), LAYER))
    return out
