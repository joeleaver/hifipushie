"""CHAIN LAY (N2c of docs/proposals/step5_rewrite.md, "The build" 1-2): step 5's START is the garment ASSEMBLED as chains
before it goes on the body. Replaces N2b's walk of each piece from one seam (its far seams started 10-30 cm apart and one
solve closing them at their mean tore the jacket into the neck). No role names, no garment names, no wear states.

Joe (2026-11-12): "in real life, the pieces would get assembled _before_ they get put on the body"; "Why do seams have to
gradually close using a solver at all?" They don't: every seam is ONE shared chain from the start (a node per sewn group,
cnet.root), nothing is ever apart, nothing is closed. Lengths are given; only bends are chosen.

lay(net, cnet, keep, body, plan, holds, frame=None) -> {X0, pulls, folds, ties, plies, reads, start, order};
cnet / keep from chain_lay_net.chain_network(net); frame: the contact the garment is assembled round (a thin body:
chain_settle.grown(body, s)); default body.contact.
1. ORDER (`order`): the piece with an edge step 4 names on a tape first (several: the one sewn to most), then always the
   piece sewn to most already-placed nodes; followers (plies, inside pieces) after the pieces they follow, the same way.
2. THE FIRST PIECE's taped edge is laid along its tape by its own arc length (piece_start.lay_on_tape) and pulled there.
3. EACH PIECE is sewn onto what is placed: its sewn nodes stay where they are (one chain); every other point of its
   flat goes off its nearest placed point by its flat offset, along the placed line and across it (`_ruled`), across
   continuing the surface of the cloth already sewn there (a seam is smooth: which way round comes from the garment,
   not the body), a follower lying back on it; the first piece away from its partners' tapes. Then BENT as rigidly as possible (`arap`: each point's neighbourhood its
   flat shape turned, out of the frame), so its links come out near their cut before any projection. Its planned folds are then turned (`_turn`): the smaller side of each fold
   row turned about the row by the plan's turn (split over the draft's rows), towards the outside where the draft's sign
   says so (sign x flat winding, as fold_rows reads it).
4. BENDS CLOSE THE LOOPS (`bend`): one projection (chain_net.project) over the nodes: every link at its cut (exact), the
   lines across at their flat length (exact on interfaced cloth, else at most), no node inside the frame. The pieces'
   shapes bend; no length is given up. A link still off its cut after it is a loop that cannot close by bends: named
   by its piece and seam with its gap in mm (the pattern's fault: back to step 4), never stretched.
5. UNSEWN FOLLOWERS (floating layers) are bound on their host (chain_solve_plies.bind), seeded there, then bent with
   the rest (4 runs again).
start: `measures` before and after the bends (links % off cut per piece, the loops named, fold turns, nodes inside).
FOLDS for chain_solve: step 2's planned turn per fold over the draft's rows (fold_rows). TIES: closures, a LAYER apart.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from scipy.spatial import cKDTree

from . import chain_net as cn
from .chain_core import GAP, LAYER, ChainRefused, hand_of
from .chain_lay_net import _side

CLOSE_TOL = 0.5  # % off its cut: past this after the bends, a link's loop cannot close by bends (named)
BEND_ITERS = 80  # projection passes of the bends
FOLD_THROUGH = 0.25  # a fold is not turned when its turning side carries more than this of a placed piece with no row
ARAP_ITERS = 30  # local / global rounds bending a piece sewn on to its placed nodes


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


def _unit(v):
    return v / max(float(np.linalg.norm(v)), 1e-12)


def _rot(ax, th):
    ax = _unit(ax)
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def _kabsch(A, B):
    ma, mb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ma).T @ (B - mb))
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0])
    R = Vt.T @ D @ U.T
    return R, mb - R @ ma


def _shared(cnet, root):
    """{(p, q): number of nodes pieces p and q share}."""
    out: dict = {}
    for r in np.unique(root):
        ps = sorted(set(cnet.piece[root == r].tolist()))
        for a in range(len(ps)):
            for b in range(a + 1, len(ps)):
                out[(ps[a], ps[b])] = out.get((ps[a], ps[b]), 0) + 1
    return out


def order(cnet, follow: dict, first: int) -> list:
    """Pieces in the order they are sewn (module doc, 1): every next one the piece sewn to most placed nodes."""
    sh = _shared(cnet, cnet.root)
    nb = lambda p, q: sh.get((min(p, q), max(p, q)), 0)
    out = [first]
    for group in ([p for p in range(len(cnet.names)) if cnet.names[p] not in follow and p != first],
                  [p for p in range(len(cnet.names)) if cnet.names[p] in follow]):
        left = list(group)
        while left:
            q = max(left, key=lambda p: (sum(nb(p, o) for o in out), -p))
            if sum(nb(q, o) for o in out) < 3:
                break
            out.append(q)
            left.remove(q)
    return out


def _away(cnet, p, part):
    """The centre of the step-3 tapes of the pieces p is sewn to outside its part (the first piece goes away from it)."""
    q = {int(cnet.piece[x]) for r in np.unique(cnet.root[cnet.piece == p]) for x in np.where(cnet.root == r)[0]}
    P = [t for x in sorted(q - set(part)) for t in [_tape_pts(cnet, cnet.names[x])] if t is not None]
    return np.concatenate(P).mean(0) if P else None


def _tape_pts(cnet, nm):
    st = cnet.M.get("starts") or {}
    T = st.get("tapes") or {}
    names = list((st.get("pieces") or {}).get(nm) or [])
    P = [np.asarray(T[t]["pts"], float) for t in names if t in T]
    if not P:
        return None
    P = np.concatenate(P)
    return P * [-1, 1, 1] if hand_of(nm) < 0 else P


def _ruled(cnet, p, Xn, placed, onto: bool, away=None):
    """Where piece p's flat goes from its placed nodes (module doc, 3): each other point off its nearest placed point by
    its flat offset, along the placed line (T) and across it (B). B continues the surface of the cloth already sewn
    there (a seam is smooth) or, onto=True (a follower), lies back on it; with no cloth there yet, B goes away from the
    point `away`. Returns the positions of p's points (k, 3)."""
    root = cnet.root
    pts = np.where(cnet.piece == p)[0]
    kn = placed[root[pts]]
    uv, K = cnet.uv[pts], Xn[root[pts[kn]]]
    ki = np.where(kn)[0]
    kd = cKDTree(uv[ki])
    Y = np.zeros((len(pts), 3))
    Y[ki] = K
    own = set(root[pts].tolist())
    T = np.zeros((len(ki), 3))
    B = np.zeros((len(ki), 3))
    t2 = np.zeros((len(ki), 2))
    cen = uv.mean(0)
    for m, k in enumerate(ki):
        nb = kd.query_ball_point(uv[k], 0.03)
        du, dx = uv[ki[nb]] - uv[k], K[nb] - K[m]
        tt = np.linalg.svd(du - du.mean(0))[2][0] if len(nb) > 2 else np.array([1.0, 0.0])
        T[m] = _unit((np.sign(du @ tt)[:, None] * dx).sum(0))
        t2[m] = tt
        r = root[pts[k]]
        q = np.where((root == r) & (cnet.piece != p))[0]
        d = np.zeros(3)
        for v in q:
            near = np.where((cnet.piece == cnet.piece[v]) & placed[root])[0]
            near = near[(np.linalg.norm(cnet.uv[near] - cnet.uv[v], axis=1) < 0.03)
                        & ~np.isin(root[near], list(own))]
            if len(near):
                d += (Xn[root[near]] - Xn[r]).mean(0)
        if not d.any() and away is not None:
            d = Xn[r] - away
            d = -d
        d = d - (d @ T[m]) * T[m]
        B[m] = _unit(d) * (1.0 if onto else -1.0)
    n2 = np.c_[-t2[:, 1], t2[:, 0]]
    n2 *= np.sign(((cen - uv[ki]) * n2).sum(1) + 1e-12)[:, None]
    fr = np.where(~kn)[0]
    if len(fr):
        _, j = kd.query(uv[fr])
        f = uv[fr] - uv[ki[j]]
        Y[fr] = K[j] + (f * t2[j]).sum(1)[:, None] * T[j] + (f * n2[j]).sum(1)[:, None] * B[j]
    return Y


def _first(cnet, p, loop, pt, part, body, reads, pulls):
    """The first piece's taped edge on its tape by its own arc (module doc, 2): (ids, positions)."""
    from .piece_start import lay_on_tape
    nm = cnet.names[p]
    ext = np.array([any(cnet.piece[q] not in part for q in pt.get(int(v), ())) for v in loop])
    if not ext.any():
        raise ChainRefused(f"{nm}: its taped edge is sewn to nothing: back to step 4")
    k0 = int(np.argmin(ext)) if not ext.all() else 0
    ext_r = np.roll(ext, -k0)
    s0 = int(np.argmax(ext_r))
    n = int(np.argmin(ext_r[s0:])) if not ext_r[s0:].all() else len(ext_r) - s0
    run = np.roll(loop, -k0)[s0:s0 + n]
    centre = cnet.uv[run, 0].min() < 0 < cnet.uv[run, 0].max()
    mid = int(np.argmin(np.abs(cnet.uv[run, 0]))) if centre else None
    su = 1.0
    if centre:
        later = [hand_of(cnet.names[cnet.piece[q]]) for v in run[mid + 1:] for q in pt.get(int(v), ())]
        su = -1.0 if sum(later) < 0 else 1.0
    Pc, rd = lay_on_tape(SimpleNamespace(net=cnet, body=body, reads=reads), nm, run, mid=mid, su=su)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cnet.uv[run], axis=0), axis=1))]
    sp = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Pc, axis=0), axis=1))]
    k = mid if mid is not None else 0  # (the lifted line is longer than the tape: re-laid on it by the edge's own arc)
    Pc = np.column_stack([np.interp(s - s[k] + sp[k], sp, Pc[:, d]) for d in range(3)])
    pulls.append({"ids": run.copy(), "to": Pc.copy(), "weight": 1.0, "name": f"{nm} edge on {rd['tape']}"})
    reads[nm] = {"laid": f"edge on tape {rd['tape']} ({rd['edge_mm']} of {rd['tape_mm']} mm)"}
    return run, Pc


def _place(cnet, p, Xn, placed, frame, reads, onto=False, away=None):
    """Sew piece p onto the placed nodes (module doc, 3)."""
    root, nm = cnet.root, cnet.names[p]
    pts = np.where(cnet.piece == p)[0]
    Ref = np.c_[cnet.uv[pts], np.zeros(len(pts))]
    kn = placed[root[pts]]
    if kn.sum() < 2:
        raise ChainRefused(f"{nm}: sewn to {int(kn.sum())} placed point(s): nothing to sew it on by (back to step 4)")
    Xr = np.zeros((cnet.n, 3))
    Xr[pts] = _ruled(cnet, p, Xn, placed, onto, away)
    Y = Xr.copy()
    new = pts[~kn]
    F = cnet.F[cnet.piece[cnet.F[:, 0]] == p]
    Y[pts] = arap(Ref, Y[pts], kn, cn.edges_of(np.searchsorted(pts, F)), frame)
    Xn[root[new]] = Y[new]
    placed[root[new]] = True
    a, b = cnet.chain_v[cnet.chain_piece == p].T
    e = np.abs(np.linalg.norm(Y[b] - Y[a], axis=1) / cnet.chain_L[cnet.chain_piece == p] - 1) * 100
    reads.setdefault(nm, {}).update(sewn_on=int(kn.sum()), links_bent_max_pct=round(float(e.max()), 1))


def arap(Ref, Y, kn, e, frame=None, iters: int = ARAP_ITERS, gap: float = GAP):
    """As-rigid-as-possible bending of a piece (Sorkine and Alexa 2007): its flat Ref (k, 3) on its edges e (lines across
    and links), its known points kn kept at Y, every other point where each neighbourhood is its flat shape turned
    (local: the best rotation per point; global: one Laplace solve), pushed GAP out of the frame. Returns Y."""
    import scipy.sparse as sp
    from scipy.sparse.linalg import splu
    Y = np.array(Y, float)
    fr = np.where(~kn)[0]
    if not len(fr) or not len(e):
        return Y
    k = len(Ref)
    i, j = e[:, 0], e[:, 1]
    w = 1.0 / np.maximum(np.linalg.norm(Ref[i] - Ref[j], axis=1), 1e-5)
    Lm = sp.coo_matrix((np.r_[w, w], (np.r_[i, j], np.r_[j, i])), shape=(k, k)).tocsr()
    Lm = (sp.diags(np.asarray(Lm.sum(1)).ravel()) - Lm).tocsr()
    A = splu(Lm[fr][:, fr].tocsc())
    B = Lm[fr][:, np.where(kn)[0]]
    dp = Ref[i] - Ref[j]
    for _ in range(iters):
        dx = Y[i] - Y[j]
        S = np.zeros((k, 3, 3))
        o = w[:, None, None] * dp[:, :, None] * dx[:, None, :]
        np.add.at(S, i, o)
        np.add.at(S, j, o)
        U, _, Vt = np.linalg.svd(S)
        d = np.sign(np.linalg.det(np.einsum("kij,kjl->kil", np.transpose(Vt, (0, 2, 1)), np.transpose(U, (0, 2, 1)))))
        Vt[:, 2] *= np.where(d == 0, 1.0, d)[:, None]
        R = np.einsum("kij,kjl->kil", np.transpose(Vt, (0, 2, 1)), np.transpose(U, (0, 2, 1)))
        r = 0.5 * w[:, None] * np.einsum("kij,kj->ki", R[i] + R[j], dp)
        b = np.zeros((k, 3))
        np.add.at(b, i, r)
        np.add.at(b, j, -r)
        rhs = b[fr] - B @ Y[kn]
        Y[fr] = np.column_stack([A.solve(rhs[:, c]) for c in range(3)])
        if frame is not None:
            sd, nr = frame.query(Y[fr])
            m = sd < gap
            Y[fr[m]] += nr[m] * (gap - sd[m])[:, None]
    return Y


def _uv_wind(net, piece) -> float:
    v = net.verts(piece)
    F = net.F[np.isin(net.F, v).all(1)]
    a, b, c = net.uv[F[:, 0]], net.uv[F[:, 1]], net.uv[F[:, 2]]
    u, w = b - a, c - a
    return 1.0 if float((u[:, 0] * w[:, 1] - u[:, 1] * w[:, 0]).sum()) >= 0 else -1.0


def _draft_fold(net, f, bid):
    fd = next((d for d in net.M.get("folds") or [] if d.get("piece") == f["on"] and d.get("name") == f["fold"]), None)
    if fd is None:
        raise ChainRefused(f"fold {bid}: the draft has no fold {f['fold']} on {f['on']}: back to step 4")
    return fd


def _fold_side(cnet, loop, row, pts):
    """The points of pts on the fold row's smaller side: the outline arc between the row's ends that encloses the smaller
    area with the row, and the points inside it (never by the row's line extended: that cuts the whole piece)."""
    from .chain_lay_net import _inside
    uv = cnet.uv
    i0 = int(np.argmin(np.linalg.norm(uv[loop] - uv[row[0]], axis=1)))
    i1 = int(np.argmin(np.linalg.norm(uv[loop] - uv[row[-1]], axis=1)))
    n = len(loop)
    best = None
    for arc in (loop[(i0 + np.arange((i1 - i0) % n + 1)) % n], loop[(i1 + np.arange((i0 - i1) % n + 1)) % n][::-1]):
        P = np.r_[uv[arc], uv[row[::-1][1:-1]]]
        area = 0.5 * abs(float((P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]).sum()))
        if best is None or area < best[0]:
            best = (area, arc, P)
    _, arc, P = best
    m = _inside(P, uv[pts]) | np.isin(pts, arc)
    return pts[m & ~np.isin(pts, row)]


def _turn(cnet, p, Xn, plan, frame, reads, loop, done, placed):
    """Turn piece p's planned folds (module doc, 3). A node another fold already turned stays as it is; a fold whose
    turning side carries more than FOLD_THROUGH of a placed piece with no fold row of its own is not turned: that cloth
    can't fold there (named, back to step 4)."""
    root, nm = cnet.root, cnet.names[p]
    pts = np.where(cnet.piece == p)[0]
    rowed = {d.get("piece") for d in cnet.M.get("folds") or [] if d.get("rows")}
    for bid, f in sorted((plan.get("folds") or {}).items()):
        if f["on"] != nm:
            continue
        fd = _draft_fold(cnet, f, bid)
        rows = [np.asarray(r, np.int64) for r in fd.get("rows") or []]
        way = float(fd.get("sign", 1.0)) * _uv_wind(cnet, nm)
        side = np.unique(root[_fold_side(cnet, loop, rows[0], pts)]) if rows else np.zeros(0, np.int64)
        through = []
        for q in range(len(cnet.names)):
            qn = np.unique(root[cnet.piece == q])
            if q != p and cnet.names[q] not in rowed and placed[qn].all():
                frac = float(np.isin(qn, side).mean())
                if frac > FOLD_THROUGH:
                    through.append(f"{cnet.names[q]} ({frac:.0%})")
        if through:
            reads.setdefault(nm, {})[f"not turned {bid}"] = (f"its turning side carries {', '.join(through)}, which has "
                                                            "no fold row there: back to step 4 (a roll row on it)")
            continue
        for row in rows:
            rn = np.unique(root[row])
            mv = np.setdiff1d(np.unique(root[_fold_side(cnet, loop, row, pts)]), np.r_[rn, list(done)].astype(np.int64))
            if not len(mv):
                continue
            a = Xn[root[row[0]]]
            ax = _unit(Xn[root[row[-1]]] - a)
            _, nb = frame.query(Xn[rn].mean(0)[None])
            sg = 1.0 if np.cross(ax, Xn[mv].mean(0) - a) @ (way * nb[0]) >= 0 else -1.0
            R = _rot(ax, sg * np.radians(float(f["turn_deg"]) / len(rows)))
            Xn[mv] = (Xn[mv] - a) @ R.T + a
        done.update(side.tolist())
        reads.setdefault(nm, {})[f"turned {bid}"] = float(f["turn_deg"])


def node_links(cnet):
    """(i, j, L, exact) over nodes: every chain link at its cut (a seam's two sides: one link at their mean), then the
    lines across at their flat length (exact where interfaced at both ends, else at most)."""
    r = cnet.root
    a, b = np.sort(r[cnet.chain_v], axis=1).T
    k = a != b
    key, inv = np.unique(np.c_[a[k], b[k]], axis=0, return_inverse=True)
    L = np.bincount(inv.ravel(), cnet.chain_L[k]) / np.bincount(inv.ravel())
    e = np.sort(r[cnet.edges], axis=1)
    m = e[:, 0] != e[:, 1]
    ex = (cnet.stiff[cnet.edges[:, 0]] > 0) & (cnet.stiff[cnet.edges[:, 1]] > 0)
    return (np.r_[key[:, 0], e[m, 0]], np.r_[key[:, 1], e[m, 1]], np.r_[L, cnet.flat[m]],
            np.r_[np.ones(len(key), bool), ex[m]])


def bend(cnet, Xn, frame, gap=GAP, log=None):
    """The bends (module doc, 4): (Xn, project's read)."""
    i, j, L, ex = node_links(cnet)
    nodes = np.unique(cnet.root)
    cts = [] if frame is None else [(frame, nodes, gap)]
    return cn.project(Xn, i, j, L, ex, contacts=cts, iters=BEND_ITERS, log=log)


def _fold_turns(cnet, X, plan) -> dict:
    """Median measured turn (deg) of each planned fold's rows: the angle between the faces either side of each row link."""
    out = {}
    for bid, f in sorted((plan.get("folds") or {}).items()):
        fd = _draft_fold(cnet, f, bid)
        got = []
        for row in fd.get("rows") or []:
            row = np.asarray(row, np.int64)
            for a, b in zip(row[:-1], row[1:]):
                fs = cnet.F[(cnet.F == a).any(1) & (cnet.F == b).any(1)]
                if len(fs) != 2:
                    continue
                n = np.cross(X[fs[:, 1]] - X[fs[:, 0]], X[fs[:, 2]] - X[fs[:, 0]])
                n = n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
                got.append(np.degrees(np.arccos(np.clip(n[0] @ n[1], -1, 1))))
        if got:
            out[bid] = {"planned": float(f["turn_deg"]), "median": round(float(np.median(got)), 1),
                        "off": round(abs(float(np.median(got)) - float(f["turn_deg"])), 1)}
    return out


def measures(cnet, X, plan=None, contact=None) -> dict:
    """Links % off cut per piece (per point: each side of a seam at its own cut), the loops that don't close (links past
    CLOSE_TOL, by piece pair, gap mm), seam gaps (0 by construction: a check), fold turns, points inside."""
    a, b = cnet.chain_v[:, 0], cnet.chain_v[:, 1]
    ln = np.linalg.norm(X[b] - X[a], axis=1)
    e = np.abs(ln / np.maximum(cnet.chain_L, 1e-12) - 1) * 100
    by: dict = {}
    for k in np.argsort(-e):
        by.setdefault(cnet.names[cnet.chain_piece[k]], round(float(e[k]), 3))
    i, j, L, ex = node_links(cnet)
    Xr = X  # (X is per point; a node's points coincide, so X at a root is the node's)
    l2 = np.linalg.norm(Xr[j] - Xr[i], axis=1)
    bad = ex & (np.abs(l2 / L - 1) * 100 > CLOSE_TOL)
    loops: dict = {}
    for u, v, ll, LL in zip(i[bad], j[bad], l2[bad], L[bad]):
        pp = sorted({cnet.names[q] for q in cnet.piece[(cnet.root == u) | (cnet.root == v)]})
        key = " ~ ".join(pp)
        loops[key] = max(loops.get(key, 0.0), round(float(ll - LL) * 1e3, 1))
    sides: dict = {}  # (a seam's two sides cut to different lengths: each side's own links, summed, mm over its cut)
    r = cnet.root
    shared = np.bincount(r, minlength=cnet.n) > 1
    for p in range(len(cnet.names)):
        m = (cnet.chain_piece == p) & shared[r[a]] & shared[r[b]]
        for k in np.where(m)[0]:
            pp = sorted({cnet.names[q] for q in cnet.piece[(r == r[a[k]]) | (r == r[b[k]])]} - {cnet.names[p]})
            if len(pp) != 1:
                continue
            key = " ~ ".join(sorted((cnet.names[p], pp[0])))
            d = sides.setdefault(key, {})
            d[cnet.names[p]] = d.get(cnet.names[p], 0.0) + float(ln[k] - cnet.chain_L[k]) * 1e3
    sides = {k: {q: round(x, 1) for q, x in v.items()} for k, v in sides.items()
             if max(abs(x) for x in v.values()) > 1.0}
    sew = cnet.sew
    gap = float(np.linalg.norm(X[sew[:, 0]] - X[sew[:, 1]], axis=1).max()) * 1e3 if len(sew) else 0.0
    out = {"links_max_pct": round(float(e.max()), 3), "links_over_2pct": int((e > 2).sum()), "links": len(e),
           "links_by_piece_max_pct": by, "loops_open_mm": dict(sorted(loops.items(), key=lambda t: -abs(t[1]))[:12]),
           "loops_open": len(loops), "seam_gap_mm": round(gap, 3),
           "sides_differ_mm": sides}
    if plan:
        out["folds"] = _fold_turns(cnet, X, plan)
    if contact is not None:
        sd, _ = contact.query(X)
        out["inside"] = int((sd < 0).sum())
        out["under_gap"] = int((sd < GAP - 1e-4).sum())
    return out


def lay(net, cnet, keep, body, plan: dict | None = None, holds=None, frame=None, log=None) -> dict:
    """The assembled start and chain_solve's inputs (module doc)."""
    from . import chain_holds, chain_solve_plies as cp
    plan = plan or {}
    frame = body.contact if frame is None else frame
    h = holds or chain_holds.read(net)
    follow = {**h.plies, **h.layers, **h.inside}
    refuse_untaped(cnet, follow)
    pid = {nm: k for k, nm in enumerate(cnet.names)}
    part = {pid[p]: {pid[q] for q in pa.pieces} for pa in h.parts for p in pa.pieces}
    idx = -np.ones(net.n, np.int64)
    idx[keep] = np.arange(len(keep))
    edges = (cnet.M.get("starts") or {}).get("edges") or {}
    taped = [pid[p] for p in cnet.names if p not in follow and (edges.get(p) or (hand_of(p) and edges.get(p[:-2])))]
    if not taped:
        raise ChainRefused("step 4 names no edge on a tape: back to step 4 (a piece's edge on the tape it was drafted on)")
    sh = _shared(cnet, cnet.root)
    first = max(taped, key=lambda p: (sum(v for k, v in sh.items() if p in k), -p))
    seq = order(cnet, follow, first)
    root = cnet.root
    Xn, placed = np.zeros((cnet.n, 3)), np.zeros(cnet.n, bool)
    reads: dict = {}
    pulls: list = []
    run, Pc = _first(cnet, first, idx[net.loop(cnet.names[first])], partners(cnet), part.get(first, {first}), body,
                     reads, pulls)
    Xn[root[run]], placed[root[run]] = Pc, True
    away = _away(cnet, first, part.get(first, {first}))
    done: set = set()
    for p in seq:
        _place(cnet, p, Xn, placed, frame, reads, onto=cnet.names[p] in follow, away=away if p == first else None)
        _turn(cnet, p, Xn, plan, frame, reads, idx[net.loop(cnet.names[p])], done, placed)
    left = [cnet.names[p] for p in range(len(cnet.names)) if p not in seq]
    if [p for p in left if p not in h.layers]:
        raise ChainRefused(f"{', '.join(p for p in left if p not in h.layers)}: sewn to nothing placed: back to step 4")
    before = measures(cnet, Xn[root], plan, frame)
    Xa = Xn.copy()
    Xn, rd = bend(cnet, Xn, frame, log=log)
    sign = {p: _out_sign(cnet, p, Xn[root], frame) for p in cnet.names if p not in left}
    plies = []
    k_of = {p: 1 for p in follow}
    for p, host in h.inside.items():
        k_of[p] = 1 + sum(1 for hh in h.layers.values() if hh == host)
    for p in sorted(follow, key=lambda q: follow[q] in follow):
        b = cp.bind(cnet, {p: follow[p]}, k_of, sign)[0]
        if p in left:  # (sewn to nothing: seeded on its host, a layer in)
            X = Xn[root]
            P = (b["w"][:, :, None] * X[b["tri"]]).sum(1) + b["d"][:, None] * cp.normals(X, b["tri"], b["hostF"])
            Xn[root[b["ids"]]] = P
            sign[p] = _out_sign(cnet, p, Xn[root], frame)
        plies.append(b)
        reads.setdefault(p, {}).update(follows=follow[p], layers_in=k_of[p])
    if left:
        Xn, rd = bend(cnet, Xn, frame, log=log)
    X0 = Xn[root]
    mv = np.linalg.norm(Xn[root] - Xa[root], axis=1)[np.isin(cnet.piece, [pid[p] for p in cnet.names if p not in left])]
    after = measures(cnet, X0, plan, frame)
    named = "; ".join([f"{k} open by {v} mm" for k, v in after["loops_open_mm"].items()] +
                      [f"{k}: its sides cut {v} mm apart" for k, v in after["sides_differ_mm"].items()])
    start = {"before_bends": before, "after_bends": after, "projection": rd, "closed": after["loops_open"] == 0,
             "named": (f"seams bends cannot close: {named}: back to step 4 (the pattern: those seams' lengths)"
                       if named else ""),
             "bend_move_mm": {"median": round(float(np.median(mv)) * 1e3, 1), "max": round(float(mv.max()) * 1e3, 1)}}
    return {"X0": X0, "pulls": pulls, "folds": fold_rows(cnet, plan, sign), "ties": tie_pairs(cnet, plan),
            "plies": plies, "reads": reads, "start": start, "order": [cnet.names[p] for p in seq]}


def _out_sign(net, piece, X, contact) -> float:
    """+1 when the piece's F normals point away from the body at the start (area weighted), else -1."""
    v = net.verts(piece)
    F = net.F[np.isin(net.F, v).all(1)]
    c = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    _, nb = getattr(contact, "contact", contact).query(X[F].mean(1))
    return 1.0 if float((c * nb).sum()) >= 0 else -1.0


def fold_rows(net, plan, sign) -> list:
    """chain_solve folds: step 2's turn per planned fold, split over the draft's rows. Which way: the draft's fold sign
    read in the flat's own winding (sign x uv winding: +1 = onto the side the flat's +z faces), then into F's normals
    on the body by the piece's out sign."""
    out = []
    for bid, f in sorted((plan.get("folds") or {}).items()):
        fd = _draft_fold(net, f, bid)
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
