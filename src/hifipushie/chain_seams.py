"""SEAMS ARE ONE CHAIN END TO END (N2d of docs/proposals/step5_rewrite.md, "The build" 0).

A seam is drafted as sew pairs; some seams are sparse (a 20 cm seam joined at 4 pairs), so between two pairs the two
sides were two separate chains of the network and nothing made them meet. join_seams makes every sewn edge ONE chain:
between two consecutive sew pairs of the same two outlines, each side gets a point at every arc fraction the other side
has a point at (a boundary edge split, its one face split in two), and the matching points are sewn. Both sides are then
the same number of points at the same arc fractions between their sewn ends; nothing is moved, no length is changed
(a split point lies on its edge, so the outline's length is its cut).

join_seams(M, stiff, bend) -> (M2, stiff2, bend2, new): M2 a copy of the pattern mesh with the new points appended (old
ids unchanged: folds, closures, points keep their meaning), new: (k, 3) [p, q, t] per appended point, so any per-vertex
array can be carried (lerp(p, q, t)). A run is joined only when both sides are boundary arcs holding no other point sewn
across the same seam, and their lengths agree within RATIO (else it is a corner between two seams, left alone).
A seam whose ONE side runs along several pieces (an armhole: a sleeve's cap against a front, a side and a back) is matched
across the junctions: the other side's run walks on through a sewn junction onto the next piece (both junction points
sewn to the one point at their fraction), so the whole armhole is one shared chain.
Nothing here knows a garment or a piece.
"""
from __future__ import annotations

import numpy as np

from . import chain_net as cn

RATIO = 1.5  # two arcs between consecutive sew pairs are one seam's run when their lengths agree within this ratio
MIN_GAP = 1e-4  # m: a fraction this near an existing point (in length) is that point, nothing inserted


def _loops(uv, F, piece, names):
    out = {}
    tmp = cn.Network.__new__(cn.Network)
    tmp.F, tmp.piece, tmp.names = F, piece, names
    for nm in names:
        out[names.index(nm)] = cn.Network.loop(tmp, nm)
    return out


def _arc(loop, i, j, step):
    """Loop indices from i to j walking `step` (+1 / -1)."""
    n = len(loop)
    out = [i]
    k = i
    while k != j:
        k = (k + step) % n
        out.append(k)
        if len(out) > n:
            return None
    return out


def _cum(uv, ids):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(uv[ids], axis=0), axis=1))]


def _walk(lp, k0, step, sewn):
    """Loop indices from k0 walking `step` up to and including the first sewn point (None: round the whole loop)."""
    n = len(lp)
    out, k = [k0], k0
    while True:
        k = (k + step) % n
        if k == k0:
            return None
        out.append(k)
        if int(lp[k]) in sewn:
            return out


def _b_paths(loops, pos, part, sewn, pb, kb, ends):
    """The other side of a run: from b1 (pb's loop index kb) along pb's outline to the first sewn point; that point is
    one of `ends` (b2: the same piece), or a JUNCTION sewn to a point of another piece whose outline runs on, unsewn, to
    one of `ends` (a seam whose one side runs along several pieces: an armhole against a front, a side and a back).
    Yields [segment ids, ...]; consecutive segments' end / start are sewn to each other."""
    lb = loops[pb]
    for sb in (1, -1):
        w = _walk(lb, kb, sb, sewn)
        if w is None or len(w) < 2:
            continue
        g = lb[w]
        c = int(g[-1])
        if c in ends:
            yield [g]
            continue
        for c2 in part.get(c, ()):
            if c2 not in pos or pos[c2][0] == pb:
                continue
            q, kq = pos[c2]
            for sq in (1, -1):
                w2 = _walk(loops[q], kq, sq, sewn)
                if w2 is not None and len(w2) >= 2 and int(loops[q][w2[-1]]) in ends:
                    yield [g, loops[q][w2]]


def runs(M) -> list:
    """[(A ids, [B segment ids, ...])]: the seams' runs between consecutive sew pairs whose two sides hold unsewn points
    (module doc); the B side may cross one sewn junction onto a second piece (_b_paths)."""
    uv, F, piece = np.asarray(M["uv"], float), np.asarray(M["F"], np.int64), np.asarray(M["piece"])
    names = list(M["names"])
    sew = np.asarray(M["sew"], np.int64).reshape(-1, 2)
    loops = _loops(uv, F, piece, names)
    pos = {}
    for p, lp in loops.items():
        for k, v in enumerate(lp):
            pos[int(v)] = (p, k)
    part: dict = {}
    for a, b in sew:
        part.setdefault(int(a), set()).add(int(b))
        part.setdefault(int(b), set()).add(int(a))
    sewn = set(part)
    out, seen = [], set()
    for a1, b1 in sew:
        for a1, b1 in ((int(a1), int(b1)), (int(b1), int(a1))):
            if a1 not in pos or b1 not in pos:
                continue
            pa, ka = pos[a1]
            pb, kb = pos[b1]
            la, lb = loops[pa], loops[pb]
            for sa in (1, -1):
                k = (ka + sa) % len(la)
                while int(la[k]) not in sewn and k != ka:
                    k = (k + sa) % len(la)
                a2 = int(la[k])
                if k == ka or (k - ka) % len(la) in (1, len(la) - 1):
                    continue  # (no unsewn point between: already one chain)
                for segs in _b_paths(loops, pos, part, sewn, pb, kb, set(part.get(a2, ())) - {b1}):
                    ia = la[_arc(la, ka, k, sa)]
                    flat = set(np.concatenate(segs).tolist())
                    if set(ia.tolist()) & flat:
                        continue
                    LA, LB = _cum(uv, ia)[-1], sum(_cum(uv, g)[-1] for g in segs)
                    if min(LA, LB) <= 0 or max(LA, LB) / min(LA, LB) > RATIO:
                        continue
                    b2 = int(segs[-1][-1])
                    key = frozenset([(min(a1, b1), max(a1, b1)), (min(a2, b2), max(a2, b2))])
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append((ia, segs))
    return out


def join_seams(M, stiff=None, bend=None):
    """(M2, stiff2, bend2, new) (module doc)."""
    uv = [tuple(x) for x in np.asarray(M["uv"], float)]
    F = [list(f) for f in np.asarray(M["F"], np.int64)]
    piece = list(np.asarray(M["piece"]))
    sew = [tuple(s) for s in np.asarray(M["sew"], np.int64).reshape(-1, 2)]
    new = []
    face_of: dict = {}
    for fi, f in enumerate(F):
        for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            face_of.setdefault(frozenset(e), []).append(fi)

    def split(p, q, t):
        """A point on edge p-q at t: its face split; returns the new id."""
        v = len(uv)
        P, Q = np.array(uv[p]), np.array(uv[q])
        uv.append(tuple(P + t * (Q - P)))
        piece.append(piece[p])
        new.append((p, q, t))
        for fi in face_of.pop(frozenset((p, q)), []):
            f = F[fi]
            c = next(x for x in f if x not in (p, q))
            k = f.index(p)
            if f[(k + 1) % 3] == q:
                f1, f2 = [p, v, c], [v, q, c]
            else:
                f1, f2 = [q, v, c], [v, p, c]
            F[fi] = f1
            F.append(f2)
            for fid, ff in ((fi, f1), (len(F) - 1, f2)):
                for e in ((ff[0], ff[1]), (ff[1], ff[2]), (ff[2], ff[0])):
                    lst = face_of.setdefault(frozenset(e), [])
                    if fid not in lst:
                        lst.append(fid)
            face_of[frozenset((c, p))] = [x for x in face_of.get(frozenset((c, p)), []) if F[x].count(p) and F[x].count(c)]
            face_of[frozenset((c, q))] = [x for x in face_of.get(frozenset((c, q)), []) if F[x].count(q) and F[x].count(c)]
        return v

    def insert(ids, fr):
        """Points on the polyline ids at arc fractions fr (sorted): existing or new ids."""
        ids = list(ids)
        U = np.array([uv[i] for i in ids])
        s = _cum(U, np.arange(len(ids)))
        L = s[-1]
        got = []
        for f in fr:
            d = f * L
            k = int(np.clip(np.searchsorted(s, d) - 1, 0, len(ids) - 2))
            if abs(s[k] - d) < MIN_GAP:
                got.append(ids[k])
                continue
            if abs(s[k + 1] - d) < MIN_GAP:
                got.append(ids[k + 1])
                continue
            t = (d - s[k]) / max(s[k + 1] - s[k], 1e-12)
            v = split(ids[k], ids[k + 1], t)
            ids.insert(k + 1, v)
            s = np.insert(s, k + 1, d)
            got.append(v)
        return got

    U0 = np.asarray(M["uv"], float)
    for ia, segs in runs(M):
        sa = _cum(U0[ia], np.arange(len(ia)))
        sl = [_cum(U0[g], np.arange(len(g))) for g in segs]
        LB = sum(x[-1] for x in sl)
        fb, acc = [], 0.0
        for x in sl:
            fb += list((acc + x) / LB)
            acc += x[-1]
        fr = np.unique(np.round(np.r_[sa[1:-1] / sa[-1], fb], 9))
        fr = fr[(fr > 1e-9) & (fr < 1 - 1e-9)]
        ga = insert(ia, fr)
        acc = 0.0
        for g, x in zip(segs, sl):
            lo, hi = acc / LB, (acc + x[-1]) / LB
            m = (fr >= lo - 1e-9) & (fr <= hi + 1e-9)
            gb = insert(g, np.clip((fr[m] - lo) / max(hi - lo, 1e-12), 0, 1))
            sew += list(zip(np.asarray(ga)[m].tolist(), gb))
            acc += x[-1]
    M2 = dict(M)
    M2.update(uv=np.array(uv, float), F=np.array(F, np.int64), piece=np.array(piece),
              sew=np.unique(np.sort(np.array(sew, np.int64), axis=1), axis=0))
    nw = np.array(new, float).reshape(-1, 3)

    def carry(a):
        if a is None:
            return None
        a = np.asarray(a, float)
        if not len(nw):
            return a.copy()
        p, q, t = nw[:, 0].astype(int), nw[:, 1].astype(int), nw[:, 2]
        out = np.r_[a, np.zeros(len(nw))]
        for k in range(len(nw)):  # (in order: a split point may lie on an edge of an earlier one)
            out[len(a) + k] = out[p[k]] + t[k] * (out[q[k]] - out[p[k]])
        return out
    return M2, carry(stiff), carry(bend), nw


def carry_rows(X, nw):
    """Any per-vertex array (n, ...) carried onto the appended points (lerp along their edges, in order)."""
    X = np.asarray(X, float)
    out = np.concatenate([X, np.zeros((len(nw),) + X.shape[1:])])
    n = len(X)
    for k, (p, q, t) in enumerate(nw):
        out[n + k] = out[int(p)] + t * (out[int(q)] - out[int(p)])
    return out


FUSE_TOL = 0.010  # m: two points of one piece this far apart in the flat can't be one sewn node


def fused(M, tol: float = FUSE_TOL) -> list:
    """Sewn nodes that close a piece on itself by mistake (D4, C488): two points of ONE piece more than tol apart in the
    flat that end in one node only through other pieces' points (not sewn to each other: a dart's own pairs are). The
    s4-31 jacket's armholes: the front's top 54 mm sewn to the under sleeve, the back's shoulder to the top sleeve's
    front pitch, so shoulder point, underarm and pitches were ONE node; links stay exact (the armhole hangs in loops
    from it), so no link count sees it. M: a pattern mesh dict (sew, piece, uv, names). [(piece, a, b, mm)]."""
    sew = np.asarray(M["sew"], np.int64).reshape(-1, 2)
    piece, uv, names = np.asarray(M["piece"]), np.asarray(M["uv"], float), M["names"]
    par = {}

    def find(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a, b in sew:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            par[max(ra, rb)] = min(ra, rb)
    groups = {}
    for x in list(par):
        groups.setdefault(find(x), []).append(x)
    direct = {(int(min(a, b)), int(max(a, b))) for a, b in sew}
    out = []
    for g in groups.values():
        g = sorted(g)
        for i, a in enumerate(g):
            for b in g[i + 1:]:
                d = float(np.linalg.norm(uv[a] - uv[b]))
                if piece[a] == piece[b] and (a, b) not in direct and d > tol:
                    out.append((names[piece[a]], a, b, round(d * 1e3, 1)))
    return out
