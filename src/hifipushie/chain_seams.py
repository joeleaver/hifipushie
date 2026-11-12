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


def runs(M) -> list:
    """[(A ids, B ids)]: the seams' runs between consecutive sew pairs whose two sides hold unsewn points (module doc)."""
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
                for b2 in part.get(a2, ()):
                    if b2 not in pos or pos[b2][0] != pb or b2 == b1:
                        continue
                    kb2 = pos[b2][1]
                    for sb in (1, -1):
                        arc_b = _arc(lb, kb, kb2, sb)
                        if arc_b is None or len(arc_b) > len(lb) // 2 + 1:
                            continue
                        ib = lb[arc_b]
                        if any(int(v) in sewn for v in ib[1:-1]):
                            continue
                        ia = la[_arc(la, ka, k, sa)]
                        if pa == pb and set(ia.tolist()) & set(ib.tolist()):
                            continue
                        LA, LB = _cum(uv, ia)[-1], _cum(uv, ib)[-1]
                        if min(LA, LB) <= 0 or max(LA, LB) / min(LA, LB) > RATIO:
                            continue
                        key = frozenset([(min(a1, b1), max(a1, b1)), (min(a2, b2), max(a2, b2))])
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append((ia, ib))
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

    for ia, ib in runs(M):
        A = np.asarray(M["uv"], float)[ia]
        B = np.asarray(M["uv"], float)[ib]
        fa, fb = _cum(A, np.arange(len(ia)))[1:-1], _cum(B, np.arange(len(ib)))[1:-1]
        fr = np.unique(np.r_[fa / _cum(A, np.arange(len(ia)))[-1], fb / _cum(B, np.arange(len(ib)))[-1]])
        ga = insert(ia, fr)
        gb = insert(ib, fr)
        sew += list(zip(ga, gb))
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
