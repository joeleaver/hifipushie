"""CHAIN SOLVE, THE FINAL STEP (chain_solve.py is the spec; N2h of docs/proposals/step5_rewrite.md): the hard constraints
made exact WHILE BENDING LEAST. It replaces the minimum-displacement projection (Goldenthal et al. 2007), whose metric
is the identity: it moved each point as little as possible until its lengths held, with no bending at all, so a chain
longer than its room took the slack as a zigzag (N2g: 1,913 zigzags, links 5 % median after its 40-pass cap).

Each pass is one equality-constrained Gauss-Newton step (sequential quadratic programming):
    minimise 1/2 dx^T (Js^T Js + ALPHA I) dx + (Js^T rs)^T dx   subject to   Jc dx = -c
- rs, Js: the SOFT terms of chain_solve_gn.residuals (bending along chains and across lines, fold turns, pulls, plies)
  with the hard terms' weights set to zero: the step bends least, keeps folds at plan and tapes where they pull.
- c, Jc: the HARD terms, linearised: every link at its cut, other edges no longer than their flat length (active
  only when over), ties at their gap, points nearer the body than the gap put out to it (active
  only when under). The active set is re-read every pass.
- ALPHA: a proximal metric per node (rows / REF^2 like a pull of weight ALPHA_W) that keeps the KKT matrix definite
  and each pass local; it damps nothing the soft terms want.
RESTORING (each round, before and after the soft pass): the KKT step with no soft gradient (the correction smallest
in H's metric: a fix is taken as a smooth bend), kept only if it lowers |c|^2; else a damped Gauss-Newton step on
|c|^2, (Jc^T Jc + mu H) dx = -Jc^T c, damping raised until it does (N2h: the undamped projection diverged on the
jacket's collar from links 28 % off, worst 34 -> 990 % in 24 passes, with or without contact).
The KKT system [[H, Jc^T], [Jc, -EPS I]] is quasi-definite and solved by a sparse LU (3 x nodes + active rows, ~25k at
the jacket's 3k nodes: well under a second). THE SOFT PASSES (N2i): a trust region on ONE MERIT, phi = soft energy +
NU x |hard violation|^2: each pass the SQP step capped at the radius, the radius set by actual / predicted drop of phi;
it stops when an accepted step lowers phi by less than DONE_DROP of it (converged), then restores once. The report says
how many passes it took and whether it converged (and the hard terms hold).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

from . import chain_solve_gn as gn

ALPHA_W = 1e-3  # proximal weight per node, as a pull of this weight per REF (1 cm)
EPS = 1e-10  # the KKT matrix's regularisation of the constraint block
TOL = 1e-4  # links within this fraction of their length (edges: no longer than it)
TOL_POS = 1e-5  # m: ties and contact within this
DONE_MOVE = 5e-5  # m: a trust radius this small that still lowers nothing: a minimum of the merit
DONE_DROP = 1e-4  # an accepted step lowering the merit by less than this fraction of it is the last
STEP = 0.005  # m: a restoring pass's largest move, and the first trust radius
RADIUS_MAX = 0.05  # m: the trust radius grows to at most this
NU_W = 10.0  # the merit's violation weight: TOL on every hard row weighs this x the starting soft energy
RHO_TAKE, RHO_SHRINK, RHO_GROW = 0.1, 0.25, 0.75  # actual / predicted merit drop: take, shrink, grow
ITERS = 200  # solves at most (restoring and soft)
RESTORE = 40  # restoring passes per round at most
MU0 = 1e-6  # the first damping of a restoring pass the KKT step made worse (x H, whose entries are ~1e5 x Jc^T Jc's)


def hard_rows(Xn, t, ct, gap):
    """The hard constraints at Xn (nodes), linearised: (Jc (m x 3nn) csr, c (m,), read {worst, tie_mm, deep_mm})."""
    nid = t["nid"]
    li, lj, L, _ = t["links"]
    ei, ej, eL = t["edges"]
    I, J_, Ls = np.r_[li, ei], np.r_[lj, ej], np.r_[L, eL]
    exact = np.r_[np.ones(len(L), bool), np.zeros(len(eL), bool)]
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
    terms hold after the merit's trust region settles (module doc)."""
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
        mu = 0.0  # (0: the KKT step; else the damped Gauss-Newton step on |c|^2 with this damping in H's metric)
        Jc, c, rd_ = hard_rows(X, t, ct, gap)
        for _ in range(RESTORE):
            if _holds(rd_) or n_kkt >= iters:
                return X, rd_
            if mu == 0.0:
                dx = _kkt(H, Jc, np.zeros(3 * nn), c)
            else:
                A = (Jc.T @ Jc + mu * H).tocsc()
                dx = splu(A, permc_spec="MMD_AT_PLUS_A").solve(-(Jc.T @ c)).reshape(-1, 3)
            n_kkt += 1
            mx = float(np.linalg.norm(dx, axis=1).max())
            dx = dx * (STEP / mx) if mx > STEP else dx
            ok = False
            for s_ in (1.0, 0.5, 0.25):  # (halvings cost a residual each, no solve)
                Xt = X + s_ * dx
                Jt, ctt, rdt_ = hard_rows(Xt, t, ct, gap)
                if float(ctt @ ctt) < float(c @ c) or rdt_["worst"] < rd_["worst"] and rdt_["deep_mm"] <= rd_["deep_mm"]:
                    ok = True
                    break
            if ok:
                X, Jc, c, rd_ = Xt, Jt, ctt, rdt_
                mu = 0.0 if mu <= MU0 else mu / 4
            else:  # (the linearisation lied, e.g. a link nearly folded on itself: damp, never diverge)
                mu = MU0 if mu == 0.0 else mu * 8
        return X, rd_

    # (N2i: ONE MERIT, phi = soft energy + NU x |hard violation|^2 (NU scaled so a violation of TOL on every hard row
    # weighs NU_W x the starting soft energy), and a TRUST REGION on it: the full SQP step, capped at the radius; the
    # ratio of phi's actual to its model's predicted drop grows or shrinks the radius; stop when an accepted step drops
    # phi by less than DONE_DROP of it. N2h restored after every soft pass and accepted only a soft-energy drop with every
    # hard term holding, capped at 5 mm: every jacket solve ran to its 200-pass cap.)
    E, H, g = metric(Xn)
    Xn, rd = restore(Xn, H)
    E, H, g = metric(Xn)
    Jc, c, rd = hard_rows(Xn, t, ct, gap)
    Ls = np.r_[t["links"][2], t["edges"][2]]
    nu = NU_W * max(E, 1e-12) / max(float(np.sum((TOL * Ls) ** 2)), 1e-30)
    phi = E + nu * float(c @ c)
    while n_kkt < iters:
        dx = _kkt(H, Jc, g, c)
        n_kkt += 1
        mx = float(np.linalg.norm(dx, axis=1).max())
        if mx > radius:
            dx *= radius / mx
        d = dx.ravel()
        lin = c + Jc @ d
        pred = -(2 * float(g @ d) + float(d @ ((H - I3) @ d))) + nu * (float(c @ c) - float(lin @ lin))
        Xt = Xn + dx
        Et, Ht, gt = metric(Xt)
        Jt, ctt, rdt = hard_rows(Xt, t, ct, gap)
        phit = Et + nu * float(ctt @ ctt)
        rho = (phi - phit) / pred if pred > 0 else -1.0
        if log:
            log(f"  final {n_kkt}: phi {phi:.5g} -> {phit:.5g} (rho {rho:.2f}), move {min(mx, radius) * 1e3:.3f} mm "
                f"(radius {radius * 1e3:.2f}), worst {rdt['worst'] * 100:.4f} %, deep {rdt['deep_mm']:.3f} mm")
        if rho > RHO_TAKE:
            drop = (phi - phit) / max(phi, 1e-30)
            Xn, E, H, g, Jc, c, rd, phi = Xt, Et, Ht, gt, Jt, ctt, rdt, phit
            if rho > RHO_GROW and mx >= radius:
                radius = min(RADIUS_MAX, 2 * radius)
            elif rho < RHO_SHRINK:
                radius *= 0.5
            if drop < DONE_DROP:
                conv = True
                break
        else:
            radius *= 0.25
            if radius <= DONE_MOVE:
                conv = True  # (no step of any size lowers the merit: a minimum of it)
                break
    Xn, rd = restore(Xn, H)  # (the hard terms made to hold where the merit settled)
    if not _holds(rd):
        conv = False
    rd = {k: round(float(v), 6) for k, v in rd.items()}
    return Xn, n_kkt, conv, rd
