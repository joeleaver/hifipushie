"""CHAIN NETWORK: a garment as chains of its pattern's own lengths (Joe 2026-10-29: "This is how we should build clothes,
right here"; C259, C260). The general core; nothing here knows a shirt, a collar or a cuff. chain_garment.py builds on it.

The model: a flat pattern (uv, F, piece, names, sew, folds: the mesh dict cloth.build makes; nothing else, and never a
fit's positions).
- NODES: sewn points are ONE node (union-find over M["sew"] only; closures are wear, not seams: they are never merged).
- CHAINS: every boundary edge of every piece and every fold row is a link at its exact cut length.
- LINES across a piece: hold the chains apart. Exact on interfaced cloth (and where the caller says the cloth lies flat);
  elsewhere AT MOST their flat length (cloth that curves may bring its edges nearer, never further).
- ONLY BENDS ARE FREE. Lengths are never measured after placing points: every stage ends in project(), which moves the
  nodes as little as possible until every length holds (fast projection, Goldenthal 2007: J J^T lambda = C), and
  reports what could not hold by piece and line (Report). Nothing is hidden and no setting loosens it.
- CONTACT: a Contact is a surface with a side. "Can't sink in" is an inequality; a light rest pull is a separate, weak term
  of the bend solve. Nothing follows a surface at an offset.
- STIFFNESS: bending weights come from the interfacing kind (bending.BEND_KIND) x BEND_BASE, one constant.
- SOFT CLOTH: stretch is read along the THREADS (the deformation gradient's warp and weft columns); mesh edges on the bias
  may shear (they carry only the weave's own limit, shear_limit()).

mirror_map() is two-way: the first all-pieces attempt built it one way, so every right-side node mirrored onto itself and
the mirror step halved its x every pass: the whole net collapsed onto the centre line (C261)."""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree

BEND_BASE = 0.4  # bending weight of plain cloth in the bend solve; interfacing multiplies it (bending.BEND_KIND)
H0 = 0.002  # m: the link length BEND_BASE is stated at (bend residuals are scaled to any other link length)
HARD = 20.0  # length residual weight in the bend solve; project() has the last word anyway
EXACT_TOL = 1e-4  # a chain holds when no link is more than this fraction off its cut length
ATMOST_TOL = 1e-3  # a line / thread holds within this fraction over


def unit(v):
    v = np.asarray(v, float)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _closest_on_tris(P, A, B, C):
    """Closest point on triangles ABC to P, row by row (Ericson 5.1.5)."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = P - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = P - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-20, 1e-20, den)
    Q = A + ab * (vb / den)[:, None] + ac * (vc / den)[:, None]  # interior

    def put(m, q):
        Q[m] = q[m]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        put((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0), B + (C - B) * t[:, None])
        t = d2 / (d2 - d6)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), A + ac * t[:, None])
        t = d1 / (d1 - d3)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), A + ab * t[:, None])
    put((d6 >= 0) & (d5 <= d6), C)
    put((d3 >= 0) & (d4 <= d3), B)
    put((d1 <= 0) & (d2 <= 0), A)
    return Q


class Contact:
    """A surface and the side cloth may be on. query(P) -> (signed distance on the allowed side, unit normal towards it).
    side=+1: the triangles' outward side."""

    def __init__(self, V, T, side: float = 1.0, k: int = 10):
        self.V, self.T = np.asarray(V, float), np.asarray(T, np.int64)
        self.side, self.k = float(side), int(min(k, len(self.T)))
        tri = self.V[self.T]
        self.fn = unit(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]))
        self.c = tri.mean(1)
        self.kd = cKDTree(self.c)

    def query(self, P):
        P = np.asarray(P, float)
        if not len(P):
            return np.zeros(0), np.zeros((0, 3))
        _, J = self.kd.query(P, k=self.k)
        J = np.asarray(J).reshape(len(P), self.k)
        Pr = np.repeat(P, self.k, axis=0)
        t = self.T[J.ravel()]
        Q = _closest_on_tris(Pr, self.V[t[:, 0]], self.V[t[:, 1]], self.V[t[:, 2]])
        d = np.linalg.norm(Pr - Q, axis=1).reshape(len(P), self.k)
        b = np.argmin(d, axis=1)
        r = np.arange(len(P))
        Qb = Q.reshape(len(P), self.k, 3)[r, b]
        fn = self.fn[J[r, b]] * self.side
        dv = P - Qb
        dist = d[r, b]
        s = np.where((dv * fn).sum(1) >= 0, 1.0, -1.0)
        n = np.where((dist > 1e-7)[:, None], unit(dv) * s[:, None], fn)
        # (a point off an edge of a tiny facet: the facet's own normal side decides; the direction is the true closest one)
        return s * dist, n


def edges_of(F):
    F = np.asarray(F, np.int64)
    return np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1), axis=0)


def boundary_edges(F):
    F = np.asarray(F, np.int64)
    u, c = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1), axis=0, return_counts=True)
    return u[c == 1]


def union_roots(n: int, pairs) -> np.ndarray:
    """Union-find: root per vertex. The root is the group's smallest id, so it doesn't depend on the pairs' order."""
    par = np.arange(n)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in np.asarray(pairs, np.int64).reshape(-1, 2):
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            par[max(ra, rb)] = min(ra, rb)
    return np.array([find(i) for i in range(n)])


class Network:
    """The pattern as a network. M: the pattern mesh; stiff: per-vertex interfacing share 0..1 (cloth.interfacing);
    bend: per-vertex bending weight factor (bending.interfacing_kinds; 1 = plain)."""

    def __init__(self, M: dict, stiff=None, bend=None):
        forbidden = [k for k in ("A", "X", "fit", "V") if k in M]
        if forbidden:
            raise ValueError(f"chain network: the pattern mesh carries positions ({forbidden}); a chain build reads the "
                             "pattern and the body only, never a fit")
        self.M = M
        self.uv = np.asarray(M["uv"], float)
        self.F = np.asarray(M["F"], np.int64)
        self.piece = np.asarray(M["piece"])
        self.names = list(M["names"])
        self.n = len(self.uv)
        self.sew = np.asarray(M["sew"], np.int64).reshape(-1, 2)
        self.stiff = np.zeros(self.n) if stiff is None else np.asarray(stiff, float)
        self.bend = np.ones(self.n) if bend is None else np.asarray(bend, float)
        self.root = union_roots(self.n, self.sew)
        self.edges = edges_of(self.F)
        self.flat = np.linalg.norm(self.uv[self.edges[:, 0]] - self.uv[self.edges[:, 1]], axis=1)
        self._chain_links()

    # ---- the chains
    def pid(self, name: str) -> int:
        return self.names.index(name)

    def verts(self, name: str) -> np.ndarray:
        return np.where(self.piece == self.pid(name))[0]

    def fold_rows(self):
        """(fold entry, row vertices in order) for every fold row of the pattern."""
        out = []
        for f in self.M.get("folds") or []:
            for row in f.get("rows") or []:
                r = np.unique(np.asarray(row, np.int64))
                P = self.uv[r] - self.uv[r].mean(0)
                ax = np.linalg.svd(P, full_matrices=False)[2][0]  # a fold line runs one way: ordered along it
                out.append((f, r[np.argsort(P @ ax)]))
        return out

    def _chain_links(self):
        be = boundary_edges(self.F)
        fold_e = []
        fname = []
        for f, row in self.fold_rows():
            # (a fold row is a pattern line: consecutive row points are a link of it, at their flat distance)
            fold_e.append(np.c_[row[:-1], row[1:]])
            fname += [f.get("name", f["piece"])] * (len(row) - 1)
        fe = np.concatenate(fold_e) if fold_e else np.zeros((0, 2), np.int64)
        e = np.r_[be, np.sort(fe, axis=1)]
        kind = np.r_[np.zeros(len(be), int), np.ones(len(fe), int)]  # 0 edge, 1 fold line
        _, ui = np.unique(e, axis=0, return_index=True)
        e, kind = e[ui], kind[ui]
        L = np.linalg.norm(self.uv[e[:, 0]] - self.uv[e[:, 1]], axis=1)
        a, b = self.root[e[:, 0]], self.root[e[:, 1]]
        keep = a != b  # (a link whose two ends are sewn together closes a cut: the cloth is gathered there, no length)
        self.closed_links = e[~keep]
        self.chain_v = e[keep]
        self.chain_L = L[keep]
        self.chain_kind = kind[keep]
        self.chain_piece = self.piece[self.chain_v[:, 0]]
        # a seam's two sides between the same two sewn points: one link, the mean of its sides; the difference is the
        # pattern's truing error, read and reported (seam_mismatch), never stretched in
        i, j = np.minimum(a[keep], b[keep]), np.maximum(a[keep], b[keep])
        key = i.astype(np.int64) * self.n + j
        uk, inv = np.unique(key, return_inverse=True)
        s, c = np.zeros(len(uk)), np.zeros(len(uk))
        np.add.at(s, inv, self.chain_L)
        np.add.at(c, inv, 1)
        hi, lo = np.zeros(len(uk)), np.full(len(uk), np.inf)
        np.maximum.at(hi, inv, self.chain_L)
        np.minimum.at(lo, inv, self.chain_L)
        self.link_i, self.link_j = (uk // self.n).astype(np.int64), (uk % self.n).astype(np.int64)
        self.link_L = s / c
        self.link_cut = np.stack([lo, hi], 1)
        self.link_of_chain = inv

    def seam_mismatch(self) -> dict:
        """The pattern's truing: the largest difference between a seam's two sides over one link (mm, %)."""
        d = self.link_cut[:, 1] - self.link_cut[:, 0]
        k = int(np.argmax(d)) if len(d) else 0
        return {"max_mm": round(float(d[k]) * 1e3, 3) if len(d) else 0.0,
                "max_pct": round(float(d[k] / max(self.link_L[k], 1e-9) * 100), 2) if len(d) else 0.0}

    def loop(self, name: str) -> np.ndarray:
        """A piece's outline as one ordered loop of its vertices (the longest loop when a piece has several)."""
        p = self.pid(name)
        Fp = self.F[np.all(self.piece[self.F] == p, axis=1)]
        be = boundary_edges(Fp)
        nb: dict = {}
        for a, b in be:
            nb.setdefault(int(a), []).append(int(b))
            nb.setdefault(int(b), []).append(int(a))
        seen, best = set(), []
        for s in nb:
            if s in seen:
                continue
            path, prev, cur = [s], None, s
            seen.add(s)
            while True:
                nx = [q for q in nb[cur] if q != prev and q not in path[-2:]]
                nx = [q for q in nx if q not in seen] or []
                if not nx:
                    break
                prev, cur = cur, nx[0]
                seen.add(cur)
                path.append(cur)
            if len(path) > len(best):
                best = path
        return np.array(best, np.int64)

    def arc(self, name: str, members) -> np.ndarray:
        """The stretch of a piece's outline that runs through `members` (an ordered path): the shortest arc of the loop
        holding them all."""
        lp = self.loop(name)
        m = np.isin(lp, np.asarray(list(members), np.int64))
        if not m.any():
            return np.zeros(0, np.int64)
        idx = np.where(m)[0]
        gaps = np.diff(np.r_[idx, idx[0] + len(lp)])
        k = int(np.argmax(gaps))  # the largest gap is the part of the loop not in the arc
        start = idx[(k + 1) % len(idx)]
        return np.roll(lp, -start)[: len(lp) - int(gaps[k]) + 1]

    def lines_across(self, name: str, step: int = 4, band: float = 0.006) -> np.ndarray:
        """Chain-point pairs across a piece along its two flat axes: rows (a, b)."""
        p = self.pid(name)
        m = self.chain_piece == p
        cv = np.unique(self.chain_v[m])
        if len(cv) < 6:
            return np.zeros((0, 2), np.int64)
        out = []
        for ax in (0, 1):
            o = cv[np.argsort(self.uv[cv, 1 - ax])]
            for i in range(0, len(o), step):
                sel = o[np.abs(self.uv[o, 1 - ax] - self.uv[o[i], 1 - ax]) < band]
                if len(sel) >= 2:
                    out.append((sel[np.argmin(self.uv[sel, ax])], sel[np.argmax(self.uv[sel, ax])]))
        out = np.unique(np.sort(np.array(out), axis=1), axis=0)
        return out[out[:, 0] != out[:, 1]]

    def lines(self, step: int = 4) -> tuple:
        """Every piece's lines across as root ids: (i, j, L, exact). Interfaced at both ends: exact; else at most."""
        I, J, L, E = [], [], [], []
        for nm in self.names:
            ln = self.lines_across(nm, step)
            if not len(ln):
                continue
            I.append(self.root[ln[:, 0]])
            J.append(self.root[ln[:, 1]])
            L.append(np.linalg.norm(self.uv[ln[:, 0]] - self.uv[ln[:, 1]], axis=1))
            E.append((self.stiff[ln[:, 0]] > 0.5) & (self.stiff[ln[:, 1]] > 0.5))
        I, J, L, E = map(np.concatenate, (I, J, L, E))
        k = I != J
        return I[k], J[k], L[k], E[k]

    # ---- reads
    def chain_report(self, X, tol: float = EXACT_TOL) -> dict:
        """Chains measured at X: worst link overall and by piece (fold lines named), % off the cut."""
        X = np.asarray(X, float)
        l = np.linalg.norm(X[self.link_j] - X[self.link_i], axis=1)
        e = np.abs(l / np.maximum(self.link_L, 1e-9) - 1) * 100
        by: dict = {}
        for k, c in enumerate(self.link_of_chain):
            nm = self.names[self.chain_piece[k]]
            kind = "fold line" if self.chain_kind[k] else "edge"
            key = f"{nm} {kind}"
            by[key] = max(by.get(key, 0.0), float(e[c]))
        return {"worst_pct": round(float(e.max()), 3) if len(e) else 0.0, "ok": bool(len(e) == 0 or e.max() <= tol * 100 * 1.5),
                "p99_pct": round(float(np.percentile(e, 99)), 3) if len(e) else 0.0, "links": len(e),
                "by_line": {k: round(v, 3) for k, v in sorted(by.items(), key=lambda t: -t[1])}}

    def seam_gap(self, X) -> float:
        """Largest distance between two sewn points, mm."""
        if not len(self.sew):
            return 0.0
        return float(np.linalg.norm(X[self.sew[:, 0]] - X[self.sew[:, 1]], axis=1).max() * 1e3)

    def spread(self, X):
        """Copy each root's position to its sewn group."""
        return np.asarray(X, float)[self.root]


def mirror_map(net: Network, pairs=(), solo=()) -> np.ndarray:
    """vertex -> its mirror vertex, TWO-WAY (a one-way map sends one side onto itself: the collapse, C261). pairs:
    (left, right, flat x sign between them); solo: pieces symmetric about their own x = 0. Unmapped vertices map to -1."""
    mir = -np.ones(net.n, np.int64)
    uv = net.uv
    for a, b, sx in pairs:
        pa, pb = net.verts(a), net.verts(b)
        mir[pa] = pb[cKDTree(uv[pb] * [sx, 1]).query(uv[pa])[1]]
        mir[pb] = pa[cKDTree(uv[pa] * [sx, 1]).query(uv[pb])[1]]
    for a in solo:
        pa = net.verts(a)
        mir[pa] = pa[cKDTree(uv[pa] * [-1, 1]).query(uv[pa])[1]]
    return mir


class Threads:
    """Thread stretch of soft faces: each face's warp and weft columns of the deformation gradient, for project()."""

    def __init__(self, uv, F, cap: float, root=None):
        uv, self.F = np.asarray(uv, float), np.asarray(F, np.int64)
        a, b, c = uv[self.F[:, 0]], uv[self.F[:, 1]], uv[self.F[:, 2]]
        e1, e2 = b - a, c - a
        det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        ok = np.abs(det) > 1e-12
        self.F = (self.F if root is None else np.asarray(root)[self.F])[ok]
        e1, e2, det = e1[ok], e2[ok], det[ok]
        # dX/du = g[:, 1] (X1 - X0) + g[:, 2] (X2 - X0), etc.: the shape gradients of the three corners
        gu = np.c_[-(e2[:, 1] - e1[:, 1]), e2[:, 1], -e1[:, 1]] / det[:, None]
        gv = np.c_[-(e1[:, 0] - e2[:, 0]), -e2[:, 0], e1[:, 0]] / det[:, None]
        self.g = np.stack([gu, gv], 1)  # (faces, 2 threads, 3 corners)
        self.cap = float(cap)

    def stretch(self, X):
        P = X[self.F]  # (f, 3, 3)
        col = np.einsum("fti,fid->ftd", self.g, P)
        return np.linalg.norm(col, axis=2) - 1.0, col

    def report(self, X) -> dict:
        s, _ = self.stretch(X)
        s = s.max(1)
        return {"p99_pct": round(float(np.percentile(s, 99) * 100), 2), "max_pct": round(float(s.max() * 100), 2),
                "over_cap": int((s > self.cap + ATMOST_TOL).sum()), "faces": len(s)}


def _solve(J, C, eps):
    m = J.shape[0]
    A = (J @ J.T + eps * sp.identity(m, format="csr")).tocsc()
    try:
        lam = splu(A, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0, options={"SymmetricMode": True}).solve(C)
    except RuntimeError:  # (singular: heavier regularisation; the outer loop keeps its measure)
        lam = splu((J @ J.T + 1e3 * eps * sp.identity(m, format="csr")).tocsc()).solve(C)
    return J.T @ lam


def project(X, i, j, L, exact, held=None, contacts=(), threads=None, iters: int = 30, step: float = 0.02,
            limit=None, eps: float = 1e-7, log=None) -> tuple:
    """THE LAST WORD: move the free points as little as possible until every length holds.
    X (n, 3); links i, j, L, exact (bool: else at most L); held (bool n); contacts: [(Contact, ids, gap)], ids may be a
    gap array too; threads: Threads (each thread at most 1 + cap, ids as X); limit: [(k, c, R)]: |X[k] - c| <= R.
    Each pass: the violated constraints, linearised, solved in one sparse system (J J^T lambda = C). `step` caps a pass's
    largest move (m). Returns (X, read: worst_exact, worst_atmost %, inside (points under their gap), passes)."""
    X = np.array(X, float)
    n = len(X)
    held = np.zeros(n, bool) if held is None else np.asarray(held, bool)
    fid = -np.ones(n, np.int64)
    fid[~held] = np.arange(int((~held).sum()))
    nf = int((~held).sum())
    i, j = np.asarray(i, np.int64), np.asarray(j, np.int64)
    L, exact = np.asarray(L, float), np.asarray(exact, bool)
    both_held = held[i] & held[j]
    read = {}
    for it in range(iters):
        dv = X[j] - X[i]
        l = np.maximum(np.linalg.norm(dv, axis=1), 1e-12)
        c = l - L
        act = (exact | (c > 0)) & ~both_held
        u = dv / l[:, None]
        Rows, Cols, Vals, Cs = [], [], [], []
        m = 0
        ka = np.where(act)[0]
        for side, sgn in ((j, 1.0), (i, -1.0)):
            f = fid[side[ka]]
            k = f >= 0
            r = np.arange(len(ka))[k]
            for d in range(3):
                Rows.append(r)
                Cols.append(3 * f[k] + d)
                Vals.append(sgn * u[ka[k], d])
        Cs.append(c[ka])
        m += len(ka)
        worst_ex = float(np.abs(c[exact & ~both_held] / np.maximum(L[exact & ~both_held], 1e-9)).max()) if (exact & ~both_held).any() else 0.0
        worst_am = float(np.maximum(c[~exact & ~both_held] / np.maximum(L[~exact & ~both_held], 1e-9), 0).max()) if (~exact & ~both_held).any() else 0.0
        inside = 0
        deepest = 0.0
        for ct, ids, gap in contacts:
            ids = np.asarray(ids, np.int64)
            mv = ~held[ids]
            gp = np.full(len(ids), float(gap)) if np.ndim(gap) == 0 else np.asarray(gap, float)
            ids, gp = ids[mv], gp[mv]
            if not len(ids):
                continue
            sd, nrm = ct.query(X[ids])
            short = sd < gp
            inside += int(short.sum())
            if short.any():
                deepest = max(deepest, float(np.max((gp - sd)[short])))
                f = fid[ids[short]]
                r = m + np.arange(len(f))
                for d in range(3):
                    Rows.append(r)
                    Cols.append(3 * f + d)
                    Vals.append(nrm[short, d])
                Cs.append((sd - gp)[short])
                m += len(f)
        thr = 0.0
        if threads is not None:
            s, col = threads.stretch(X)
            over = s - threads.cap
            ff, tt = np.where(over > 0)
            thr = float(over.max()) if over.size else 0.0
            if len(ff):
                dirs = unit(col[ff, tt])  # (k, 3)
                r = m + np.arange(len(ff))
                for corner in range(3):
                    v = threads.F[ff, corner]
                    f = fid[v]
                    k = f >= 0
                    for d in range(3):
                        Rows.append(r[k])
                        Cols.append(3 * f[k] + d)
                        Vals.append(threads.g[ff[k], tt[k], corner] * dirs[k, d])
                Cs.append(over[ff, tt])
                m += len(ff)
        lim_bad = 0.0
        if limit:
            for k_, cen, R in limit:
                dv_ = X[k_] - cen
                ln = float(np.linalg.norm(dv_))
                if ln > R and fid[k_] >= 0:
                    lim_bad = max(lim_bad, ln - R)
                    for d in range(3):
                        Rows.append(np.array([m]))
                        Cols.append(np.array([3 * fid[k_] + d]))
                        Vals.append(np.array([dv_[d] / ln]))
                    Cs.append(np.array([ln - R]))
                    m += 1
        read = {"worst_exact_pct": round(worst_ex * 100, 4), "worst_atmost_pct": round(worst_am * 100, 4),
                "under_gap": inside, "deepest_mm": round(deepest * 1e3, 3), "thread_over_pct": round(thr * 100, 3),
                "limit_mm": round(lim_bad * 1e3, 3), "passes": it + 1}
        if log:
            log(f"  project {it}: {read}")
        if (worst_ex <= EXACT_TOL and worst_am <= ATMOST_TOL and deepest <= 2e-5 and thr <= ATMOST_TOL
                and lim_bad < 2e-5) or m == 0:
            break
        J = sp.coo_matrix((np.concatenate(Vals), (np.concatenate(Rows), np.concatenate(Cols))), shape=(m, 3 * nf)).tocsr()
        C_all = np.concatenate(Cs)

        def merit(Y):
            d_ = np.linalg.norm(Y[j] - Y[i], axis=1) - L
            d_ = np.where(exact, d_, np.maximum(d_, 0))
            tot = float(np.sum(d_[~both_held] ** 2))
            for ct, ids, gap in contacts:
                ids = np.asarray(ids, np.int64)
                mv_ = ~held[ids]
                sd_ = ct.query(Y[ids[mv_]])[0]
                g_ = float(gap) if np.ndim(gap) == 0 else np.asarray(gap, float)[mv_]
                tot += float(np.sum(np.minimum(sd_ - g_, 0) ** 2))
            if threads is not None:
                tot += float(np.sum(np.maximum(threads.stretch(Y)[0] - threads.cap, 0) ** 2)) * 1e-4
            return tot
        m0 = merit(X)
        # Levenberg: damping rises when a linearised step overshoots (short links rotate), falls when it is taken
        Y = X
        for tr in range(6):
            dx = -_solve(J, C_all, eps).reshape(-1, 3)
            nd = np.linalg.norm(dx, axis=1)
            dx *= np.minimum(1.0, step / np.maximum(nd, 1e-12))[:, None]  # (each point's own cap: one far point can't freeze the rest)
            done = False
            for s in (1.0, 0.5, 0.25):
                Y = X.copy()
                Y[~held] += s * dx
                if merit(Y) < m0:
                    done = True
                    break
            if done:
                eps = max(eps * (0.5 if s == 1.0 else 2.0), 1e-7)
                break
            eps = min(eps * 16, 1.0)
        if not done:
            break
        X = Y
    return X, read


class BendSolve:
    """Bends as little as the lengths allow (Levenberg-Marquardt on sparse analytic Jacobians) over the free nodes.
    Residual terms: add_links (hard), add_bend (second differences along a chain, with a rest curve), add_contact (can't
    sink in, plus a light rest pull), add_linear (mirror, ties, targets), add_fn (anything: returns r, rows, cols, vals)."""

    def __init__(self, X, free):
        self.X = np.array(X, float)
        self.free = np.asarray(free, np.int64)
        self.fid = -np.ones(len(self.X), np.int64)
        self.fid[self.free] = np.arange(len(self.free))
        self.nv = 3 * len(self.free)
        self.lin_rows, self.lin_cols, self.lin_vals, self.lin_b = [], [], [], []
        self.nlin = 0
        self.terms = []

    def add_links(self, i, j, L, exact, w=HARD):
        i, j, L, exact = np.asarray(i, np.int64), np.asarray(j, np.int64), np.asarray(L, float), np.asarray(exact, bool)

        def term(X):
            dv = X[j] - X[i]
            l = np.maximum(np.linalg.norm(dv, axis=1), 1e-12)
            c = l - L
            act = exact | (c > 0)
            r = w * np.where(act, c, 0.0)
            u = (dv / l[:, None]) * (w * act)[:, None]
            k = np.arange(len(i))
            return r, np.r_[k, k], np.r_[j, i], np.r_[u, -u]
        self.terms.append(term)

    def add_contact(self, ids, ct: Contact, gap, w=5.0, rest: float = 0.0, rest_gap=None):
        ids = np.asarray(ids, np.int64)
        ids = ids[self.fid[ids] >= 0]
        gap = np.full(len(ids), float(gap)) if np.ndim(gap) == 0 else np.asarray(gap, float)
        rg = gap if rest_gap is None else (np.full(len(ids), float(rest_gap)) if np.ndim(rest_gap) == 0 else np.asarray(rest_gap, float))

        def term(X):
            sd, n = ct.query(X[ids])
            sink = sd < gap
            r1 = w * np.where(sink, sd - gap, 0.0)
            g1 = n * (w * sink)[:, None]
            if rest <= 0:
                return r1, np.arange(len(ids)), ids, g1
            r2 = rest * (sd - rg)
            k = np.arange(len(ids))
            return np.r_[r1, r2], np.r_[k, k + len(ids)], np.r_[ids, ids], np.r_[g1, n * rest]
        self.terms.append(term)

    def add_bend(self, chain, weight, rest=None, h=None):
        """chain: node ids in order. weight: per-interior-point or scalar (BEND_BASE x the kind). rest: rest second
        differences (m-1 ... ) of a curve the chain keeps (a stiff piece's own pressed shape), default straight."""
        ch = np.asarray(chain, np.int64)
        m = len(ch) - 2
        if m <= 0:
            return
        w = np.full(m, float(weight)) if np.ndim(weight) == 0 else np.asarray(weight, float)
        L = np.linalg.norm(np.diff(self.X[ch], axis=0), axis=1) if h is None else np.full(len(ch) - 1, float(h))
        hm = np.maximum(0.5 * (L[1:] + L[:-1]), 1e-5)
        w = w * (H0 / hm) ** 1.5
        rs = np.zeros((m, 3)) if rest is None else np.asarray(rest, float)
        for d in range(3):
            base = self.nlin + d * m
            k = np.arange(m)
            self.lin_rows += [base + k] * 3
            self.lin_cols += [3 * ch[:-2] + d, 3 * ch[1:-1] + d, 3 * ch[2:] + d]
            self.lin_vals += [w, -2 * w, w]
            self.lin_b.append(w * rs[:, d])
        self.nlin += 3 * m

    def add_linear(self, rows):
        """rows: [([node ids], [coeffs], component, target, weight)]: weight (sum coeff x[node, component] - target)."""
        for ids, cf, d, tgt, w in rows:
            ids = np.asarray(ids, np.int64)
            self.lin_rows.append(np.full(len(ids), self.nlin))
            self.lin_cols.append(3 * ids + d)
            self.lin_vals.append(w * np.asarray(cf, float))
            self.lin_b.append(np.array([w * float(tgt)]))
            self.nlin += 1

    def add_fn(self, fn):
        self.terms.append(fn)

    def _mat(self):
        r = np.concatenate(self.lin_rows) if self.lin_rows else np.zeros(0, np.int64)
        c3 = np.concatenate(self.lin_cols) if self.lin_cols else np.zeros(0, np.int64)
        v = np.concatenate(self.lin_vals) if self.lin_vals else np.zeros(0)
        b = np.concatenate(self.lin_b) if self.lin_b else np.zeros(0)
        fk = self.fid[c3 // 3]
        keep = fk >= 0
        # (held nodes' columns go to the right side)
        A = sp.coo_matrix((v[keep], (r[keep], 3 * fk[keep] + c3[keep] % 3)), shape=(self.nlin, self.nv)).tocsr()
        Af = sp.coo_matrix((v[~keep], (r[~keep], c3[~keep])), shape=(self.nlin, 3 * len(self.X))).tocsr()
        return A, Af, b

    def solve(self, iters: int = 40, mu: float = 1e-3, log=None):
        A, Af, b = self._mat()
        off = Af @ self.X.ravel() - b if self.nlin else np.zeros(0)
        X = self.X

        def residual(Y):
            r_ = [A @ Y[self.free].ravel() + off] if self.nlin else []
            Js = [A] if self.nlin else []
            for t in self.terms:
                r, rows, nodes, g = t(Y)
                f = self.fid[nodes]
                k = f >= 0
                Js.append(sp.coo_matrix((g[k].ravel(), (np.repeat(rows[k], 3), np.repeat(3 * f[k], 3) + np.tile([0, 1, 2], int(k.sum())))),
                                        shape=(len(r), self.nv)).tocsr())
                r_.append(r)
            return np.concatenate(r_), sp.vstack(Js).tocsr()
        r, J = residual(X)
        cost = float(r @ r)
        for it in range(iters):
            H = (J.T @ J).tocsc()
            gr = J.T @ r
            d0 = sp.diags(np.maximum(H.diagonal(), 1e-6))
            ok = False
            for tr in range(8):
                try:
                    dx = splu((H + mu * d0).tocsc()).solve(-gr)
                except RuntimeError:
                    mu *= 10
                    continue
                Y = X.copy()
                st = dx.reshape(-1, 3)
                big = float(np.linalg.norm(st, axis=1).max())
                Y[self.free] += st * min(1.0, 0.02 / max(big, 1e-12))
                r2, J2 = residual(Y)
                c2 = float(r2 @ r2)
                if c2 < cost:
                    gain = (cost - c2) / max(cost, 1e-20)
                    X, r, J, cost = Y, r2, J2, c2
                    mu = max(mu / 3, 1e-7)
                    ok = True
                    break
                mu *= 4
            if log and it % 5 == 0:
                log(f"  bend {it}: cost {cost:.5e} mu {mu:.1e}")
            if not ok or gain < 1e-5:
                break
        self.X = X
        return X


def fill(Xref, X, known, uv, F, ids=None, root=None):
    """Surfaces between fixed chains: the displacement of the known vertices carried over the pattern mesh by a Laplace
    solve (edge weights 1 / flat length), added to the reference shape. known: bool per vertex. F: faces to fill over.
    root: sewn groups fill as one point (pieces then carry the displacement across their seams)."""
    F = np.asarray(F, np.int64)
    e = edges_of(F)
    w = 1.0 / np.maximum(np.linalg.norm(uv[e[:, 0]] - uv[e[:, 1]], axis=1), 1e-5)
    if root is not None:
        e = np.asarray(root)[e]
        k = e[:, 0] != e[:, 1]
        e, w = e[k], w[k]
        ids = np.unique(e) if ids is None else ids
    ids = np.unique(F) if ids is None else np.asarray(ids, np.int64)
    li = -np.ones(len(X), np.int64)
    li[ids] = np.arange(len(ids))
    a, b = li[e[:, 0]], li[e[:, 1]]
    n = len(ids)
    Lm = sp.coo_matrix((np.r_[w, w], (np.r_[a, b], np.r_[b, a])), shape=(n, n)).tocsr()
    Lm = (sp.diags(np.asarray(Lm.sum(1)).ravel()) - Lm).tocsr()
    kn = np.asarray(known, bool)[ids]
    fr = ~kn
    Y = np.array(X, float)
    if not fr.any():
        return Y
    D = (np.asarray(X, float) - np.asarray(Xref, float))[ids]
    A = Lm[fr][:, fr].tocsc()
    rhs = -(Lm[fr][:, kn] @ D[kn])
    lu = splu(A + 1e-9 * sp.identity(A.shape[0], format="csc"))
    Y[ids[fr]] = np.asarray(Xref, float)[ids[fr]] + np.column_stack([lu.solve(rhs[:, k]) for k in range(3)])
    return Y
