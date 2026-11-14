"""CHAIN SOLVE, THE FINAL STEP (chain_solve.py is the spec; N2h of docs/proposals/step5_rewrite.md): the hard constraints
made exact WHILE BENDING LEAST. It replaces the minimum-displacement projection (Goldenthal et al. 2007), whose metric
is the identity: it moved each point as little as possible until its lengths held, with no bending at all, so a chain
longer than its room took the slack as a zigzag (N2g: 1,913 zigzags, links 5 % median after its 40-pass cap).

Each pass is one equality-constrained Gauss-Newton step (sequential quadratic programming):
    minimise 1/2 dx^T (Js^T Js + ALPHA I) dx + (Js^T rs)^T dx   subject to   Jc dx = -c
- rs, Js: the SOFT terms of chain_solve_gn.residuals (bending along chains and across lines, fold turns, pulls, plies)
  with the hard terms' weights set to zero: the step bends least, keeps folds at plan and tapes where they pull.
- c, Jc: the HARD terms, linearised: every link at its cut, interfaced edges exact, other edges no longer than their
  flat length (active only when over), ties at their gap, points nearer the body than the gap put out to it (active
  only when under). The active set is re-read every pass.
- ALPHA: a proximal metric per node (rows / REF^2 like a pull of weight ALPHA_W) that keeps the KKT matrix definite
  and each pass local; it damps nothing the soft terms want.
The KKT system [[H, Jc^T], [Jc, -EPS I]] is quasi-definite and solved by a sparse LU (3 x nodes + active rows, ~25k at
the jacket's 3k nodes: well under a second). A pass's largest move is capped at STEP. It stops when every hard term
holds (links within TOL, ties and contact within 0.01 mm) and the last move is under DONE_MOVE; the report says how
many passes it took and whether it converged.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

from . import chain_solve_gn as gn

ALPHA_W = 1e-3  # proximal weight per node, as a pull of this weight per REF (1 cm)
EPS = 1e-10  # the KKT matrix's regularisation of the constraint block
TOL = 1e-4  # links and exact edges within this fraction of their length
TOL_POS = 1e-5  # m: ties and contact within this
DONE_MOVE = 5e-5  # m: a soft pass moving no point further than this, with the hard terms holding, is the last
DONE_DROP = 1e-4  # ... or one lowering the soft energy by less than this fraction
STEP = 0.005  # m: a pass's largest move, and the soft pass's largest trust radius
ITERS = 80  # KKT solves at most (restoring and soft)
RESTORE = 8  # restoring passes per round at most


def hard_rows(Xn, t, ct, gap):
    """The hard constraints at Xn (nodes), linearised: (Jc (m x 3nn) csr, c (m,), read {worst, tie_mm, deep_mm})."""
    nid = t["nid"]
    li, lj, L, _ = t["links"]
    ei, ej, eL, ex = t["edges"]
    I, J_, Ls = np.r_[li, ei], np.r_[lj, ej], np.r_[L, eL]
    exact = np.r_[np.ones(len(L), bool), ex]
    nn = len(Xn)
    dv = Xn[J_] - Xn[I]
    l = np.maximum(np.linalg.norm(dv, axis=1), 1e-12)
    c = l - Ls
    act = exact | (c > 0)
    worst = float(np.max(np.abs(c[act]) / Ls[act])) if act.any() else 0.0
    u = dv / l[:, None]
    ka = np.where(act)[0]
    R, C, V, Cs = [], [], [], [c[ka]]
    r0 = np.arange(len(ka))
    for side, sg in ((J_, 1.0), (I, -1.0)):
        for d in range(3):
            R.append(r0)
            C.append(3 * side[ka] + d)
            V.append(sg * u[ka, d])
    m = len(ka)
    tie_bad = 0.0
    if t["ties"]:
        ti = nid[np.array([x[0] for x in t["ties"]], np.int64)]
        tj = nid[np.array([x[1] for x in t["ties"]], np.int64)]
        tg = np.array([x[2] for x in t["ties"]], float)
        dvt = Xn[tj] - Xn[ti]
        lt = np.linalg.norm(dvt, axis=1)
        vec = (tg < 1e-6) | (lt < 1e-9)  # (on each other: three rows, one per axis)
        k = np.where(vec)[0]
        if len(k):
            tie_bad = max(tie_bad, float(lt[k].max()))
            for d in range(3):
                r = m + 3 * np.arange(len(k)) + d
                R += [r, r]
                C += [3 * tj[k] + d, 3 * ti[k] + d]
                V += [np.ones(len(k)), -np.ones(len(k))]
            Cs.append(dvt[k].ravel())
            m += 3 * len(k)
        k = np.where(~vec)[0]
        if len(k):
            tie_bad = max(tie_bad, float(np.abs(lt[k] - tg[k]).max()))
            ut = dvt[k] / lt[k, None]
            r = m + np.arange(len(k))
            for d in range(3):
                R += [r, r]
                C += [3 * tj[k] + d, 3 * ti[k] + d]
                V += [ut[:, d], -ut[:, d]]
            Cs.append(lt[k] - tg[k])
            m += len(k)
    deep = 0.0
    if ct is not None:
        sd, nrm = ct.query(Xn)
        sh = np.where(sd < gap)[0]
        if len(sh):
            deep = float(np.max(gap - sd[sh]))
            r = m + np.arange(len(sh))
            for d in range(3):
                R.append(r)
                C.append(3 * sh + d)
                V.append(nrm[sh, d])
            Cs.append(sd[sh] - gap)
            m += len(sh)
    Jc = sp.coo_matrix((np.concatenate(V), (np.concatenate(R), np.concatenate(C))), shape=(m, 3 * nn)).tocsr()
    return Jc, np.concatenate(Cs), {"worst": worst, "tie_mm": tie_bad * 1e3, "deep_mm": deep * 1e3}


def soft_weights(w):
    """The LM weights with the hard terms off (they are constraints here)."""
    return {**w, "link": 0.0, "edge": 0.0, "tie": 0.0, "contact": 0.0}


def _kkt(H, Jc, rhs_g, c):
    m = Jc.shape[0]
    K = sp.bmat([[H, Jc.T], [Jc, -EPS * sp.identity(m)]], format="csc")
    try:
        sol = splu(K, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0, options={"SymmetricMode": True}).solve(
            np.r_[-rhs_g, -c])
    except RuntimeError:  # (a singular pivot: the general ordering)
        sol = splu(K).solve(np.r_[-rhs_g, -c])
    return sol[:H.shape[0]].reshape(-1, 3)


def _holds(rd):
    return rd["worst"] <= TOL and rd["tie_mm"] <= TOL_POS * 1e3 and rd["deep_mm"] <= TOL_POS * 1e3


def step(Xn, t, w, ct, gap, iters: int = ITERS, log=None):
    """The final step (module doc): returns (Xn, passes, converged, read). Each round: RESTORE (KKT passes with no soft
    gradient: the hard terms made exact by the correction smallest in the soft terms' own metric, so a fix is taken as
    a smooth bend, not a kink), then one SOFT pass (bend least on the constraints' tangent, its move capped by a trust
    radius), kept only if the soft energy after restoring is lower, else the radius halves. Converged when the hard
    terms hold and the soft pass moves less than DONE_MOVE (or its radius is that small)."""
    ws = soft_weights(w)
    nn = len(Xn)
    alpha = ALPHA_W / w["ref"] ** 2
    I3 = sp.identity(3 * nn, format="csc") * alpha
    Xn = Xn.copy()
    n_kkt, conv, radius, rd = 0, False, STEP, {}

    def metric(X):
        rs, Js = gn.residuals(X, t, ws, None, gap)
        return float(rs @ rs), (Js.T @ Js).tocsc() + I3, Js.T @ rs

    def restore(X, H):
        nonlocal n_kkt
        for _ in range(RESTORE):
            Jc, c, rd_ = hard_rows(X, t, ct, gap)
            if _holds(rd_) or n_kkt >= iters:
                return X, rd_
            dx = _kkt(H, Jc, np.zeros(3 * nn), c)
            n_kkt += 1
            mx = float(np.linalg.norm(dx, axis=1).max())
            X = X + (dx * (STEP / mx) if mx > STEP else dx)
        return X, hard_rows(X, t, ct, gap)[2]

    E, H, g = metric(Xn)
    Xn, rd = restore(Xn, H)
    E, H, g = metric(Xn)
    while n_kkt < iters:
        Jc, c, rd = hard_rows(Xn, t, ct, gap)
        dx = _kkt(H, Jc, g, c)
        n_kkt += 1
        mx = float(np.linalg.norm(dx, axis=1).max())
        if mx > radius:
            dx *= radius / mx
        Xt, rdt = restore(Xn + dx, H)
        Et, Ht, gt = metric(Xt)
        if log:
            log(f"  final {n_kkt}: E {E:.5g} -> {Et:.5g}, move {min(mx, radius) * 1e3:.3f} mm (radius "
                f"{radius * 1e3:.2f}), worst {rdt['worst'] * 100:.4f} %, deep {rdt['deep_mm']:.3f} mm")
        if Et <= E and _holds(rdt):
            drop = (E - Et) / max(E, 1e-30)
            Xn, E, H, g, rd = Xt, Et, Ht, gt, rdt
            if min(mx, radius) <= DONE_MOVE or drop < DONE_DROP:
                conv = True
                break
            radius = min(STEP, 2 * radius)
        else:
            radius *= 0.5
            if radius <= DONE_MOVE:
                conv = _holds(rd)
                break
    if not _holds(rd):
        conv = False
    rd = {k: round(float(v), 6) for k, v in rd.items()}
    return Xn, n_kkt, conv, rd
