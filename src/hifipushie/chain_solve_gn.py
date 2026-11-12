"""CHAIN SOLVE, the Levenberg-Marquardt pass (chain_solve.py is the spec): the whole energy as weighted residuals, every
node free, minimised with sparse analytic Jacobians. Projective dynamics (chain_solve._PD) does the big moves cheaply but
its springs lock rotations (a fold's far side turns only as fast as its edges' frozen directions let it); Gauss-Newton
linearises the directions every pass, so a side turns as one. Residuals (rows / their own scale, sqrt of the weight):
links and exact edges (strain), at-most edges past their length, bending rows (linear), pulls (/ REF), fold turns
(radians; the exact dihedral gradient: far corners along their faces' normals / their heights, the edge's ends the
negative split by where the corners project on it, so a rigid motion moves no turn), ties (/ REF), and points nearer
the body than the gap (/ REF)."""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from sksparse.cholmod import CholeskyFactor
from threadpoolctl import threadpool_limits

from . import chain_solve_plies as pl
from . import chain_solve_terms as terms

W_CONTACT = 1e3  # weight of a point nearer the body than its gap (rows / REF)


def _rows(R, C, V, r, nodes, grads):
    """Append Jacobian entries: r (rows), nodes (k,), grads (k, 3)."""
    for d in range(3):
        R.append(r)
        C.append(3 * nodes + d)
        V.append(grads[:, d])


def residuals(Xn, t, w, ct, gap, jac: bool = True):
    """(r, J) of the whole energy at Xn (nodes). w: the weights (chain_solve's module constants, as a dict)."""
    nid = t["nid"]
    nn = len(Xn)
    rs, R, C, V = [], [], [], []
    m = 0

    def spring(i, j, L, wt, atmost):
        nonlocal m
        dv = Xn[j] - Xn[i]
        l = np.maximum(np.linalg.norm(dv, axis=1), 1e-12)
        c = (l - L) / L
        if atmost is not None:
            c = np.where(atmost, np.maximum(c, 0), c)
        s = np.sqrt(wt)
        rs.append(s * c)
        if jac:
            g = dv / l[:, None] * (s / L)[:, None]
            g = g * (c != 0)[:, None]  # (an at-most edge short of its length: zero rows, kept, so the pattern is fixed)
            r = m + np.arange(len(i))
            _rows(R, C, V, r, j, g)
            _rows(R, C, V, r, i, -g)
        m += len(i)

    li, lj, L, _ = t["links"]
    spring(li, lj, L, np.full(len(L), w["link"]), None)
    ei, ej, eL, ex = t["edges"]
    spring(ei, ej, eL, np.full(len(eL), w["edge"]), ~ex)
    # bending (linear)
    Sb = sp.diags(np.sqrt(t["Wb"])) @ t["Sb"]
    rs.append(Sb @ Xn)  # (rows, 3): flattened below as 3 rows each
    if jac:
        co = Sb.tocoo()
        for d in range(3):
            R.append(m + 3 * co.row + d)
            C.append(3 * co.col + d)
            V.append(co.data)
    rs[-1] = rs[-1].ravel()
    m += 3 * Sb.shape[0]
    for p in t["pulls"]:
        n_ = nid[p["ids"]]
        s = np.sqrt(p["w"]) / w["ref"]
        rs.append((s * (Xn[n_] - p["to"])).ravel())
        if jac:
            for d in range(3):
                R.append(m + 3 * np.arange(len(n_)) + d)
                C.append(3 * n_ + d)
                V.append(np.full(len(n_), s))
        m += 3 * len(n_)
    for f in t["folds"]:
        q = f["quads"]
        a, b, c, d = (nid[q[:, k].astype(np.int64)] for k in range(4))
        psi, e, x, y = terms.turn_of(Xn, a, b, c, d, q[:, 4])
        s = np.sqrt(w["fold"] * f["weight"])
        rs.append(s * np.angle(np.exp(1j * (psi - f["target"]))))
        if jac:
            el = np.linalg.norm(Xn[b] - Xn[a], axis=1)
            uc, ud = Xn[c] - Xn[a], Xn[d] - Xn[a]
            sc, sd_ = (uc * e).sum(1) / el, (ud * e).sum(1) / el
            rc = np.linalg.norm(uc - (uc * e).sum(1, keepdims=True) * e, axis=1)
            rd = np.linalg.norm(ud - (ud * e).sum(1, keepdims=True) * e, axis=1)
            td = -np.sin(psi)[:, None] * x + np.cos(psi)[:, None] * y
            gc, gd = y / rc[:, None], td / rd[:, None]
            ga = -(1 - sc)[:, None] * gc - (1 - sd_)[:, None] * gd
            gb = -sc[:, None] * gc - sd_[:, None] * gd
            r = m + np.arange(len(a))
            for nd, g in ((a, ga), (b, gb), (c, gc), (d, gd)):
                _rows(R, C, V, r, nd, s * g)
        m += len(a)
    if t["ties"]:
        ta = nid[np.array([x_[0] for x_ in t["ties"]])]
        tb = nid[np.array([x_[1] for x_ in t["ties"]])]
        tg = np.array([x_[2] for x_ in t["ties"]])
        s = np.sqrt(w["tie"]) / w["ref"]
        dv = Xn[tb] - Xn[ta]
        l = np.maximum(np.linalg.norm(dv, axis=1), 1e-12)
        # (a tie at gap 0 is a vector row: on each other, any way round; else its distance)
        vec = tg < 1e-6
        rv = (s * dv[vec]).ravel()
        rs.append(rv)
        if jac and vec.any():
            k = np.where(vec)[0]
            for d in range(3):
                R += [m + 3 * np.arange(len(k)) + d] * 2
                C += [3 * tb[k] + d, 3 * ta[k] + d]
                V += [np.full(len(k), s), np.full(len(k), -s)]
        m += len(rv)
        k = np.where(~vec)[0]
        rs.append(s * (l[k] - tg[k]))
        if jac and len(k):
            g = dv[k] / l[k, None] * s
            r = m + np.arange(len(k))
            _rows(R, C, V, r, tb[k], g)
            _rows(R, C, V, r, ta[k], -g)
        m += len(k)
    for b in t.get("plies") or ():  # (N2: plies / layers on their host, chain_solve_plies)
        rp, k = pl.residual_rows(Xn, b, w["ply"], w["ref"], m, R, C, V, jac)
        rs.append(rp)
        m += k
    if ct is not None:
        sdist, nrm = ct.query(Xn)
        sh = np.where(sdist < gap)[0]
        s = np.sqrt(w["contact"]) / w["ref"]
        rs.append(s * (gap - sdist[sh]))
        if jac and len(sh):
            _rows(R, C, V, m + np.arange(len(sh)), sh, -s * nrm[sh])
        m += len(sh)
    r = np.concatenate(rs) if rs else np.zeros(0)
    if not jac:
        return r, None
    J = sp.coo_matrix((np.concatenate(V), (np.concatenate(R), np.concatenate(C))), shape=(m, 3 * nn)).tocsr()
    return r, J


class Factor:
    """CHOLMOD on the LM matrix: the symbolic factor (METIS ordering, supernodal) computed ONCE from the matrix's
    sparsity pattern, which never changes between passes (only the values and the damping do), then a numeric factor
    per pass. The pattern is fixed by construction: the Jacobian keeps every link / edge row (zeros where inactive) and
    every node's own 3x3 block is in (contact rows touch only those). One BLAS / OpenMP thread: N1c measured, at load
    80-100 on 24 cores, 4 threads spinning against each other at 1-10 s a factor (6k points) vs 0.13-0.44 s on one;
    24k points 0.6-1.8 s a factor (metis; amd 1.9-3.0, nesdis 1-2.9) vs splu 18-32 s. (N1b's ctypes CHOLMOD was slow for
    that reason: the system OpenBLAS's threads, not the method.)"""

    def __init__(self, J, nn):
        Jp = J.copy()
        Jp.data[:] = 1.0
        P = sp.tril((Jp.T @ Jp) + sp.kron(sp.identity(nn), np.ones((3, 3))), format="csc")
        P.sort_indices()
        self.n = P.shape[0]
        self.indices, self.indptr = P.indices, P.indptr
        cols = np.repeat(np.arange(self.n), np.diff(P.indptr))
        self.key = cols.astype(np.int64) * self.n + P.indices
        self.diag = np.searchsorted(self.key, np.arange(self.n, dtype=np.int64) * (self.n + 1))
        with threadpool_limits(1):
            self.F = CholeskyFactor(self._csc(np.ones(len(self.key))), lower=True, order="metis",
                                    supernodal_mode="supernodal")  # (symbolic only: the pattern)

    def _csc(self, data):
        return sp.csc_array((data, self.indices, self.indptr), shape=(self.n, self.n))

    def values(self, H):
        """H (any pattern inside the analysed one) as data on the analysed pattern (lower triangle)."""
        L = sp.tril(H, format="coo")
        k = L.col.astype(np.int64) * self.n + L.row
        pos = np.searchsorted(self.key, k)
        if (pos >= len(self.key)).any() or (self.key[np.minimum(pos, len(self.key) - 1)] != k).any():
            raise ValueError("LM matrix entry outside the analysed pattern (the Jacobian's pattern changed)")
        d = np.zeros(len(self.key))
        d[pos] = L.data  # (J^T J is canonical: no duplicates)
        return d

    def solve(self, d, damp, g):
        """Factor (data d + damp on the diagonal) and solve for g."""
        d = d.copy()
        d[self.diag] += damp
        with threadpool_limits(1):
            self.F.factorize(self._csc(d))
            return self.F.solve(g)


LM_DROP = 1e-3  # a pass that lowers E by less than this fraction ends the polish (N1b: 6k points, the last 6 of 17
# passes took E 4.295 -> 4.283; the projection then moves it as much)
REFACTOR = 4  # factors a pass may try (mu x 16 each) before the pass is called converged
BACKTRACK = 6  # halvings of a rejected step along its own direction before a refactor at a higher damping


RETRACT = 6  # Jacobi sweeps of retract after each trial step


def retract(Xn, t, sweeps: int = None):
    """Each trial step put back near the lengths (links and exact edges to theirs, at-most edges no longer): a GN step
    rotates a stiff link by its tangent, so the link comes out longer by ~ theta^2 / 2 and the step is rejected for
    strain the linear model can't see (N1b: 19 passes at 6k, each cut by backtracking). A few Jacobi sweeps of
    position-based projection (each node moved by the mean of its constraints' halves) remove that second-order
    stretch; the step is then judged on the energy it actually changes."""
    li, lj, L, _ = t["links"]
    ei, ej, eL, ex = t["edges"]
    I, J_, Ls = np.r_[li, ei], np.r_[lj, ej], np.r_[L, eL]
    atmost = np.r_[np.zeros(len(L), bool), ~ex]
    nn = len(Xn)
    cnt = np.bincount(np.r_[I, J_], minlength=nn).astype(float)[:, None]
    cnt = np.maximum(cnt, 1.0)
    for _ in range(RETRACT if sweeps is None else sweeps):
        dv = Xn[J_] - Xn[I]
        l = np.maximum(np.linalg.norm(dv, axis=1), 1e-12)
        c = l - Ls
        c[atmost & (c < 0)] = 0.0
        corr = (0.5 * c / l)[:, None] * dv
        D = np.zeros_like(Xn)
        for d in range(3):
            D[:, d] = np.bincount(I, corr[:, d], nn) - np.bincount(J_, corr[:, d], nn)
        Xn = Xn + D / cnt
    return Xn


def polish(Xn, t, w, ct, gap, iters: int = 30, mu: float = 1e-2, log=None):
    """Levenberg-Marquardt over every node; returns (Xn, passes, final energy, factors). A factor is the dear part (~4 s
    at 24k points), so a rejected step is first halved along its own direction (a residual each, no factor) and the
    damping raised to match for the next pass; only a step no halving makes better is refactored at mu x 16.
    (Pushing points out of the body after each step instead of a contact residual was tried: the pushes undo the
    lengths, E 0.3 -> 7e4 on a tube. CG preconditioned by an earlier pass's factor: it did not converge in 40
    iterations on 26 of 29 passes, the matrix moves too much between passes.)"""
    r, J = residuals(Xn, t, w, ct, gap)
    if "lm_factor" not in t:  # (analysed once per solve: every round's passes share the pattern)
        t["lm_factor"] = Factor(J, len(Xn))
    fac = t["lm_factor"]
    E = float(r @ r)
    k = nf = 0
    for k in range(iters):
        H = J.T @ J
        g = J.T @ r
        dg = H.diagonal()
        d = fac.values(H)
        ok = False
        for _ in range(REFACTOR):
            dx = -fac.solve(d, mu * (dg + 1e-9), g).reshape(-1, 3)
            nf += 1
            s = 1.0
            for _ in range(BACKTRACK + 1):
                Xt = retract(Xn + s * dx, t)
                rt, _ = residuals(Xt, t, w, ct, gap, jac=False)
                Et = float(rt @ rt)
                if Et < E:
                    ok = True
                    break
                s *= 0.5
            if ok:
                break
            mu *= 16.0
        mv = float(np.abs(Xt - Xn).max())
        if log:
            log(f"  lm {k}: E {E:.4g} -> {Et:.4g} mu {mu:.2g} step {s:.3g} move {mv * 1e3:.3f} mm")
        if not ok:
            break
        drop = (E - Et) / max(E, 1e-30)
        Xn, mu = Xt, (max(mu / 3.0, 1e-9) if s == 1.0 else mu / s)
        r, J = residuals(Xn, t, w, ct, gap)
        E = float(r @ r)
        if drop < LM_DROP:
            break
    return Xn, k + 1, E, nf
