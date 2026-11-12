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
from scipy.sparse.linalg import splu

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
            r = m + np.arange(len(i))
            act = c != 0
            _rows(R, C, V, r[act], j[act], g[act])
            _rows(R, C, V, r[act], i[act], -g[act])
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


def polish(Xn, t, w, ct, gap, iters: int = 30, mu: float = 1e-4, log=None):
    """Levenberg-Marquardt over every node; returns (Xn, passes, final energy). (Pushing points out of the body after
    each step instead of a contact residual was tried: the pushes undo the lengths, E 0.3 -> 7e4 on a tube.)"""
    r, J = residuals(Xn, t, w, ct, gap)
    E = float(r @ r)
    k = 0
    for k in range(iters):
        H = (J.T @ J).tocsc()
        g = J.T @ r
        dg = H.diagonal()
        ok = False
        for _ in range(20):
            A = (H + sp.diags(mu * (dg + 1e-9))).tocsc()
            dx = -splu(A, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0,
                       options={"SymmetricMode": True}).solve(g)  # (SPD: no pivoting; 2.7 s -> ms a factor)
            Xt = Xn + dx.reshape(-1, 3)
            rt, _ = residuals(Xt, t, w, ct, gap, jac=False)
            Et = float(rt @ rt)
            if Et < E:
                ok = True
                break
            mu *= 4.0
        if log:
            log(f"  lm {k}: E {E:.4g} -> {Et:.4g} mu {mu:.2g}")
        if not ok:
            break
        drop = (E - Et) / max(E, 1e-30)
        Xn, mu = Xt, max(mu / 3.0, 1e-9)
        r, J = residuals(Xn, t, w, ct, gap)
        E = float(r @ r)
        if drop < 1e-4:
            break
    return Xn, k + 1, E
