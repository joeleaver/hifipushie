"""CHAIN LAY (N2b of docs/proposals/step5_rewrite.md, "The build" step 1): step 5's ISOMETRIC START of the chains, and
what chain_solve needs beside it. Replaces N2's whole-surface seed (chain_seed, deleted: it mapped every surface point
between the tape loops and started with seams 6-10 cm open). No role names, no garment names, no wear states.

Joe: "lengths given, only bends chosen"; "place where we measure"; the START is isometric: every chain is walked by its
own links, so its lengths are exact by construction; a seam whose two exactly-laid sides cannot meet is a gap, measured
and named (the pattern's or the tape's), never stretched closed.

lay(net, cnet, keep, body, plan) -> {X0, pulls, folds, ties, plies, reads, start}; cnet / keep from
chain_lay_net.chain_network(net). Per piece, on its outline (net's own boundary loop):
1. ON A TAPE: a piece with an edge step 4 names on a tape (starts.edges) has that edge (its longest outline run sewn to
   cloth outside its own part) laid along the tape by arc length (piece_start.lay_on_tape: a centre piece from its
   middle, the half sewn to ".L" cloth on +X, the rest mirrored), and pulled there (soft).
2. FROM ITS SEAM: every other piece, the one with the longest outline run sewn to laid cloth next: that run is laid
   along its partner's laid line by its own arc length.
3. THE REST OF THE OUTLINE is walked from both ends of the laid run, link by link at its cut: each link leaves along the
   flat's direction carried in a frame (the run end's tangent and the body's normal there, turned with the normal as the
   walk goes: a development of the flat onto the body), in the body's tangent plane, kept GAP off the body, length
   restored. The flat's side goes AWAY from the cloth the run is sewn to (the first piece: away from its partners'
   step-3 tapes). The two walkers meet opposite the run: that link is the piece's closing gap (reported).
   Fold rows are walked the same way from their laid end; any other chain point goes off its nearest laid one.
4. FOLLOWERS (chain_holds.read: plies, floating layers, inside pieces): bound on their host (chain_solve_plies.bind)
   and seeded there.
The start's own measures (start): links % off cut per piece (0 by construction but for closing links), seam gaps by
piece pair (mm: the honest number), closing gaps.
FOLDS: step 2's planned turn per fold, split over the draft's rows. TIES: each closure's tied pairs, a LAYER apart.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from .chain_core import GAP, LAYER, ChainRefused, hand_of

TURN_STEP = 15  # degrees between the guide turns tried (_best_guide)
DOWN_W = 0.05  # m: what a guide whose flat -y runs against its length path (cos = -1) costs, against seam distance
MIRROR_TOL = 1e-4  # m: a piece's flat is its other side's mirrored within this
N_GUIDE = 60  # steps of a guide's straight walk on the body (each point's own step: its flat distance / N_GUIDE)


def partners(net) -> dict:
    """{vertex: [vertices of other pieces sewn to it]}."""
    out: dict = {}
    for a, b in net.sew:
        if net.piece[a] != net.piece[b]:
            out.setdefault(int(a), []).append(int(b))
            out.setdefault(int(b), []).append(int(a))
    return out


def refuse_untaped(net, followers):
    st = net.M.get("starts") or {}
    T, names, edges = st.get("tapes") or {}, st.get("pieces") or {}, st.get("edges") or {}
    bad = [p for p in net.names if p not in followers and not any(n in T for n in names.get(p) or [])
           and not edges.get(p) and not edges.get(p[:-2])]
    if bad:
        raise ChainRefused(f"step 4 names no tape for {', '.join(bad)}: back to step 4, declare tapes (draft_pattern "
                           "declarations.tapes) on the step-3 tapes each piece was drafted on; nothing is guessed")


def _run(mask):
    """(start, length) of the longest circular run of True in mask."""
    n = len(mask)
    if mask.all():
        return 0, n
    best, cur = (0, 0), None
    for i in range(2 * n):
        if mask[i % n]:
            cur = i if cur is None else cur
            if i - cur + 1 > best[1] and i - cur < n:
                best = (cur % n, i - cur + 1)
        else:
            cur = None
    return best


def _unit(v):
    return v / max(float(np.linalg.norm(v)), 1e-12)


class _Walker:
    """Lays flat links onto the body (module doc, 3)."""

    def __init__(self, cnet, body, X, done):
        self.net, self.ct, self.X, self.done = cnet, body.contact, X, done

    def frame(self, v, prev, s):
        """(t flat, T, B, n, s) at laid point v, its tangent from laid point prev."""
        n = self.ct.query(self.X[v].reshape(1, 3))[1][0]
        T = self.X[v] - self.X[prev]
        T = _unit(T - (T @ n) * n)
        return _unit(self.net.uv[v] - self.net.uv[prev]), T, np.cross(n, T), n, s

    def guide(self, ids, fr, o):
        """Where the flat puts ids: from laid point o, each along the body's surface (GAP off it) in its flat direction
        mapped by frame fr, for its flat distance: a straight walk on the surface (a geodesic), N_GUIDE steps."""
        t, T, B, n, s = fr
        f = self.net.uv[ids] - self.net.uv[o]
        dist = np.linalg.norm(f, axis=1)
        d = np.outer(f @ t, T) + s * np.outer(f @ np.array([-t[1], t[0]]), B)
        d = d / np.maximum(np.linalg.norm(d, axis=1), 1e-12)[:, None]
        P = np.repeat(self.X[o][None], len(ids), 0)
        h = (dist / N_GUIDE)[:, None]
        for _ in range(N_GUIDE):
            P = P + h * d
            sd, nr = self.ct.query(P)
            P = P + nr * (GAP - sd)[:, None]
            d = d - (d * nr).sum(1)[:, None] * nr
            d = d / np.maximum(np.linalg.norm(d, axis=1), 1e-12)[:, None]
        return P

    def walk(self, seq, G):
        """Lay seq[1:] link by link from laid seq[0]: each link at its cut, aimed at its point's guide G[v], GAP off."""
        for a, b in zip(seq[:-1], seq[1:]):
            L = float(np.linalg.norm(self.net.uv[b] - self.net.uv[a]))
            P = self.X[a] + L * _unit(G[b] - self.X[a])
            for _ in range(3):
                sd, nr = self.ct.query(P.reshape(1, 3))
                if sd[0] >= GAP - 1e-5:
                    break
                P = self.X[a] + L * _unit(P + nr[0] * (GAP - sd[0]) - self.X[a])
            self.X[b], self.done[b] = P, True


def _hand(W, cnet, run, c, interior_uv):
    """s: the flat's side mapped so the piece's interior goes away from point c (module doc, 3)."""
    vote = 0.0
    for k in range(1, len(run)):
        t, T, B, n, _ = W.frame(run[k], run[k - 1], 1.0)
        qb = (interior_uv - cnet.uv[run[k]]) @ np.array([-t[1], t[0]])
        vote += np.sign(qb) * np.sign((c - W.X[run[k]]) @ B)
    return -1.0 if vote > 0 else 1.0


def _tape_centre(cnet, pieces):
    st = cnet.M.get("starts") or {}
    T = st.get("tapes") or {}
    P = []
    for p in pieces:
        for nm in (st.get("pieces") or {}).get(p) or []:
            if nm in T:
                Q = np.asarray(T[nm]["pts"], float)
                P.append(Q * [-1, 1, 1] if hand_of(p) < 0 else Q)
    return np.concatenate(P).mean(0) if P else None


def _lay_piece(W, cnet, p, loop, pt, part, body, reads, pulls, away=1.0):
    """Lay piece p's outline (module doc, 1-3)."""
    X, done = W.X, W.done
    nm = cnet.names[p]
    if any(done[loop]):
        raise ChainRefused(f"{nm}: laid twice")
    ext = np.array([any(cnet.piece[q] not in part for q in pt.get(int(v), ())) for v in loop])
    laid = np.array([any(done[q] for q in pt.get(int(v), ())) for v in loop])
    edges = (cnet.M.get("starts") or {}).get("edges") or {}
    taped = bool(edges.get(nm) or (hand_of(nm) and edges.get(nm[:-2])))
    r0, rn = _run(ext if taped and not laid.any() else laid)
    if rn < 2:
        raise ChainRefused(f"{nm}: no run of its outline is sewn to laid cloth (or on a tape): back to step 4")
    run = loop[(r0 + np.arange(rn)) % len(loop)]
    sewn_to = sorted({int(cnet.piece[q]) for v in run for q in pt.get(int(v), ()) if cnet.piece[q] not in part
                      and (done[q] or not laid.any())})
    if taped and not laid.any():
        from .piece_start import lay_on_tape
        centre = cnet.uv[run, 0].min() < 0 < cnet.uv[run, 0].max()
        mid = int(np.argmin(np.abs(cnet.uv[run, 0]))) if centre else None
        su = 1.0
        if centre:
            later = [hand_of(cnet.names[cnet.piece[q]]) for v in run[mid + 1:] for q in pt.get(int(v), ())]
            su = -1.0 if sum(later) < 0 else 1.0
        Pc, rd = lay_on_tape(SimpleNamespace(net=cnet, body=body, reads=reads), nm, run, mid=mid, su=su)
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cnet.uv[run], axis=0), axis=1))]
        sp = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Pc, axis=0), axis=1))]
        k0 = mid if mid is not None else 0  # (lifted GAP off the skin the tape's line is longer: re-laid on it by the
        q = s - s[k0] + sp[k0]  # edge's own arc length from where it starts, so its links stay at their cut)
        Pc = np.column_stack([np.interp(q, sp, Pc[:, k]) for k in range(3)])
        X[run], done[run] = Pc, True
        pulls.append({"ids": run.copy(), "to": Pc.copy(), "weight": 1.0, "name": f"{nm} edge on {rd['tape']}"})
        reads[nm] = {"laid": f"edge on tape {rd['tape']} ({rd['edge_mm']} of {rd['tape_mm']} mm)"}
        c = _tape_centre(cnet, [cnet.names[q] for q in sewn_to])
    else:
        P = np.array([next(X[q] for q in pt[int(v)] if done[q]) for v in run])
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cnet.uv[run], axis=0), axis=1))]
        sp = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        X[run] = np.column_stack([np.interp(s, sp, P[:, k]) for k in range(3)])
        if s[-1] > sp[-1]:  # (the run is longer than its partner's line: carried on straight past its end)
            far = s > sp[-1]
            X[run[far]] = P[-1] + np.outer(s[far] - sp[-1], _unit(P[-1] - P[-2]))
        done[run] = True
        c = np.mean([X[np.where(cnet.piece == q)[0]][done[cnet.piece == q]].mean(0) for q in sewn_to], axis=0)
        reads[nm] = {"laid": f"from its seam with {', '.join(cnet.names[q] for q in sewn_to)} ({rn} points)"}
    if c is None:
        c = X[run].mean(0) - np.array([0, 0, 0.1])
    sg = away * _hand(W, cnet, run, c, cnet.uv[loop].mean(0))
    o = run[len(run) // 2]
    ids = np.where(cnet.piece == p)[0]
    G = np.zeros((cnet.n, 3))
    G[ids], reads[nm]["turn_deg"] = _best_guide(W, cnet, nm, ids, o, W.frame(o, run[len(run) // 2 - 1], sg), pt)
    if rn < len(loop):
        rest = loop[(r0 + rn + np.arange(len(loop) - rn)) % len(loop)]
        h = (len(rest) + 1) // 2
        W.walk(np.r_[run[-1], rest[:h]], G)
        W.walk(np.r_[run[0], rest[::-1][: len(rest) - h]], G)
        reads[nm]["closes_between"] = [int(rest[h - 1]), int(rest[h])] if h < len(rest) else [int(rest[-1]), int(run[0])]
    reads[nm]["side"] = sg
    return G


def _down_frame(W, cnet, nm, fr):
    """The frame turned about the body's normal so the flat's -y (the draft's length, P2's panel rule) runs down the
    piece's highest step-3 length path, where it was measured; unchanged for a piece naming none."""
    from .piece_start import _tapes_of
    _, paths = _tapes_of(cnet, nm)
    tops = [P if P[0, 2] >= P[-1, 2] else P[::-1] for _, P in paths if len(P) >= 2]
    if not tops:
        return fr
    Q = max(tops, key=lambda P: P[0, 2])
    t, T, B, n, s = fr
    D = Q[-1] - Q[0]
    D = D - (D @ n) * n
    if np.linalg.norm(D) < 1e-6:
        return fr
    D = _unit(D)
    return np.array([0.0, -1.0]), D, np.cross(n, D), n, s


def _best_guide(W, cnet, nm, ids, o, fr, pt):
    """The guide turned about the body's normal at o to where its SEAMS say: the turn (every TURN_STEP degrees) whose
    guide puts the piece's points sewn to laid cloth nearest their partners, plus DOWN_W x how far the flat's -y
    leaves the piece's highest step-3 length path (_down_frame). Returns (guide, turn in degrees)."""
    t0, T0, B0, n, s = fr
    dn = _down_frame(W, cnet, nm, fr)
    D = dn[1] if dn is not fr else None
    sewn = [(v, next(q for q in pt[int(v)] if W.done[q])) for v in ids
            if not W.done[v] and any(W.done[q] for q in pt.get(int(v), ()))]
    best = None
    for deg in range(0, 360, TURN_STEP):
        a = np.radians(deg)
        T = np.cos(a) * T0 + np.sin(a) * B0
        f = (t0, T, np.cross(n, T), n, s)
        tp = np.array([-t0[1], t0[0]])
        cost = 0.0
        if D is not None:  # (the flat's -y mapped by f)
            m = _unit(-t0[1] * T + s * (-tp[1]) * np.cross(n, T))
            cost += DOWN_W * (1 - float(m @ D))
        if sewn:
            a_, b_ = np.array(sewn).T
            Gs = W.guide(a_, f, o)
            cost += float(np.linalg.norm(Gs - W.X[b_], axis=1).mean())
        if best is None or cost < best[0] - 1e-9:
            best = (cost, deg, f)
    return W.guide(ids, best[2], o), best[1]


def _mirror(W, cnet, q, reads):
    """The other side's piece (".L" <-> ".R"), laid as q's mirror image (x -> -x: lengths exact, seams as q's) when
    its flat is q's mirrored point for point; returns its index, or None."""
    nm = cnet.names[q]
    if not hand_of(nm):
        return None
    other = nm[:-2] + (".R" if nm.endswith(".L") else ".L")
    if other not in cnet.names:
        return None
    r = cnet.names.index(other)
    a, b = np.where(cnet.piece == q)[0], np.where(cnet.piece == r)[0]
    if len(a) != len(b) or W.done[b].any():
        return None
    from scipy.spatial import cKDTree
    dist, k = cKDTree(cnet.uv[a] * [-1, 1]).query(cnet.uv[b])
    if dist.max() > MIRROR_TOL:
        return None
    W.X[b], W.done[b] = W.X[a[k]] * [-1, 1, 1], True
    reads[other] = {"laid": f"mirror of {nm}"}
    return r


def _rows_and_rest(W, cnet, p, G):
    """Fold rows walked from their laid points (an unlaid stretch from both ends), then any other chain point of p at
    its guide."""
    done = W.done
    for f in cnet.M.get("folds") or []:
        for row in f.get("rows") or []:
            row = np.asarray(row, np.int64)
            if cnet.piece[row[0]] != p or done[row].all():
                continue
            if not done[row].any():
                W.X[row[0]], done[row[0]] = G[row[0]], True
            k = np.flatnonzero(done[row])
            a, b = int(k[0]), int(k[-1])
            if a > 0:
                W.walk(row[: a + 1][::-1], G)
            if b < len(row) - 1:
                W.walk(row[b:], G)
            for i, j in _stretches(~done[row]):
                m = (j - i + 2) // 2
                W.walk(row[i - 1:i + m], G)
                if not done[row[i:j + 1]].all():
                    W.walk(row[i:j + 2][::-1][: j - i + 2 - m], G)
    v = np.where(cnet.piece == p)[0]
    left = v[~done[v]]
    W.X[left], done[left] = G[left], True
    return len(left)


def _stretches(m):
    """(first, last) index of each run of True in m."""
    out, i = [], 0
    while i < len(m):
        if m[i]:
            j = i
            while j + 1 < len(m) and m[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def _start_measures(cnet, X, reads) -> dict:
    """Links % off cut on each piece's own points; seam gaps by piece pair (mm)."""
    a, b = cnet.chain_v[:, 0], cnet.chain_v[:, 1]
    e = np.abs(np.linalg.norm(X[b] - X[a], axis=1) / np.maximum(cnet.chain_L, 1e-12) - 1) * 100
    by: dict = {}
    for k in np.argsort(-e):
        nm = cnet.names[cnet.chain_piece[k]]
        by.setdefault(nm, round(float(e[k]), 3))
    gaps: dict = {}
    for i, j in cnet.sew:
        pi, pj = cnet.names[cnet.piece[i]], cnet.names[cnet.piece[j]]
        if pi == pj:
            continue
        key = " ~ ".join(sorted((pi, pj)))
        gaps[key] = max(gaps.get(key, 0.0), float(np.linalg.norm(X[i] - X[j])) * 1e3)
    return {"links_max_pct": round(float(e.max()), 3), "links_over_2pct": int((e > 2).sum()), "links": len(e),
            "links_by_piece_max_pct": by, "seam_gap_mm": {k: round(v, 1) for k, v in sorted(gaps.items(), key=lambda t: -t[1])}}


def lay(net, cnet, keep, body, plan: dict | None = None, holds=None) -> dict:
    """The start and chain_solve's inputs (module doc)."""
    from . import chain_holds, chain_solve_plies as cp
    plan = plan or {}
    h = holds or chain_holds.read(net)
    follow = {**h.plies, **h.layers, **h.inside}
    refuse_untaped(cnet, follow)
    pid = {nm: k for k, nm in enumerate(cnet.names)}
    part = {pid[p]: {pid[q] for q in pa.pieces} for pa in h.parts for p in pa.pieces}
    idx = -np.ones(net.n, np.int64)
    idx[keep] = np.arange(len(keep))
    loops = {pid[nm]: idx[net.loop(nm)] for nm in cnet.names}
    pt = partners(cnet)
    X, done = np.zeros((cnet.n, 3)), np.zeros(cnet.n, bool)
    W = _Walker(cnet, body, X, done)
    reads: dict = {}
    pulls: list = []
    edges = (cnet.M.get("starts") or {}).get("edges") or {}
    todo = [pid[p] for p in cnet.names if p not in follow]
    first = [q for q in todo if edges.get(cnet.names[q]) or (hand_of(cnet.names[q]) and edges.get(cnet.names[q][:-2]))]
    if not first:
        raise ChainRefused("step 4 names no edge on a tape: back to step 4 (a piece's edge on the tape it was drafted on)")
    left = 0
    def score(q):
        return sum(any(done[x] for x in pt.get(int(v), ())) for v in loops[q])
    while todo:
        q = first.pop(0) if first else max(todo, key=score)
        if q not in todo:
            continue
        G = _lay_piece(W, cnet, q, loops[q], pt, part.get(q, {q}), body, reads, pulls)
        left += _rows_and_rest(W, cnet, q, G)
        todo.remove(q)
        r = _mirror(W, cnet, q, reads)
        if r in todo:
            todo.remove(r)
    fl, walked = [pid[p] for p in follow], set()
    while fl:  # (a follower sewn to laid cloth is walked from that seam too, on its host's side)
        q = max(fl, key=score)
        fl.remove(q)
        if score(q) >= 2:
            G = _lay_piece(W, cnet, q, loops[q], pt, set(), body, reads, pulls, away=-1.0)
            left += _rows_and_rest(W, cnet, q, G)
            walked.add(cnet.names[q])
            r = _mirror(W, cnet, q, reads)
            if r in fl:
                fl.remove(r)
                walked.add(cnet.names[r])
    sign = {p: _out_sign(cnet, p, X, body) for p in cnet.names if p not in follow}
    k_of = {p: 1 for p in follow}
    for p, host in h.inside.items():
        k_of[p] = 1 + sum(1 for hh in h.layers.values() if hh == host)
    plies = []
    for p in sorted(follow, key=lambda q: follow[q] in follow):  # (a follower of a follower after its host)
        b = cp.bind(cnet, {p: follow[p]}, k_of, sign)[0]
        if p not in walked:  # (sewn to nothing laid: seeded on its host, a layer in)
            X[b["ids"]] = (b["w"][:, :, None] * X[b["tri"]]).sum(1) + b["d"][:, None] * cp.normals(X, b["tri"], b["hostF"])
            done[b["ids"]] = True
        sign[p] = _out_sign(cnet, p, X, body)
        plies.append(b)
        reads.setdefault(p, {}).update(follows=follow[p], layers_in=k_of[p])
    start = _start_measures(cnet, X, reads)
    start["placed_off_nearest"] = left
    return {"X0": X, "pulls": pulls, "folds": fold_rows(cnet, plan, sign), "ties": tie_pairs(cnet, plan),
            "plies": plies, "reads": reads, "start": start}


def _out_sign(net, piece, X, body) -> float:
    """+1 when the piece's F normals point away from the body at the start (area weighted), else -1."""
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


def fold_rows(net, plan, sign) -> list:
    """chain_solve folds: step 2's turn per planned fold, split over the draft's rows. Which way: the draft's fold sign
    read in the flat's own winding (sign x uv winding: +1 = onto the side the flat's +z faces), then into F's normals
    on the body by the piece's out sign."""
    out = []
    for bid, f in sorted((plan.get("folds") or {}).items()):
        fd = next((d for d in net.M.get("folds") or [] if d.get("piece") == f["on"] and d.get("name") == f["fold"]), None)
        if fd is None:
            raise ChainRefused(f"fold {bid}: the draft has no fold {f['fold']} on {f['on']}: back to step 4")
        rows = [np.asarray(r, np.int64) for r in fd.get("rows") or []]
        way = float(fd.get("sign", 1.0)) * _uv_wind(net, f["on"]) * sign.get(f["on"], 1.0)
        for k, r in enumerate(rows):
            out.append({"row": r, "turn_deg": float(f["turn_deg"]) / len(rows), "toward": way, "weight": 1.0,
                        "name": f"{bid}#{k}"})
    return out


def tie_pairs(net, plan) -> list:
    """(a, b, LAYER) for every tied pair of every closure (closure_ties, through chain_plan.apply_tie)."""
    from .chain_plan import apply_tie
    out = []
    ties = plan.get("ties") or {}
    for c in net.M.get("closures") or []:
        t = ties.get(c.get("name"))
        cl = apply_tie(c, t, net.uv) if t is not None else c
        for (a, b), on in zip(cl.get("v") or [], cl.get("closed") or []):
            if on:
                out.append((int(a), int(b), LAYER))
    return out
