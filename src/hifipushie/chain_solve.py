"""CHAIN SOLVE (N1 of docs/proposals/step5_rewrite.md): step 5's ONE solve. Lengths are given; only bends are chosen.
NOTHING IS HELD: every point of every piece is free in every pass, and every link is solved. (The old build held its
rule-placed points and chain_net.project skipped every link with both ends held: links came out 2569 % and 13415 % over
their cut and were only read out. That can't happen here: there is no set of points a constraint may skip.)

solve(net, X0, body, ties, folds, pulls, stiffness) -> (X, report)
- net: the flat pattern's chain_net.Network (links at their cut, sewn groups merged by `root`, uv, piece, stiff, bend).
- X0 (n, 3): a seed (N2 makes it from the tapes); only where to start, never a target.
- body: anything with .contact (chain_core.Body) or a chain_net.Contact; no point may end nearer than `gap`.
- ties: (a, b, gap) vertex pairs brought to a distance (a button on its hole a LAYER apart; 0 = on each other).
- folds: {row: vertex ids in order along a fold line, turn_deg, toward (+1: the plies close on the side F's face normals
  point to), weight, name}. turn 0 = flat on; 180 = right back onto itself (chain_crease's measure).
- pulls: {ids, to (k, 3), weight, name}: soft pulls of points towards where the body was measured (the tapes). Never pins.
- stiffness: per-vertex bending weight (default chain_net.BEND_BASE x net.bend: interfacing high, plain cloth low).

HARD: every link at its cut (reported past TOL_PCT), every other mesh edge exact where interfaced at both ends else at
most its flat length, no point nearer the body than gap, every tie at its gap. SOFT: bending (each point towards its
flat neighbourhood's shape: chain_solve_terms' affine stencils, so a stiff piece keeps its flat shape), fold turns,
pulls. When the soft terms ask for what the hard ones forbid (two pulls further apart than the cloth is long), the hard
ones win and the soft residual is reported: never a stretched link.

THE METHOD, and why. Rounds of
1. PROJECTIVE DYNAMICS (Bouaziz et al. 2014), quasi-static: each term is a row block S with a weight; the local step
   projects each term onto its own constraint set (a link onto its length, an edge onto at most its length, a fold quad
   onto its turn, a tie onto its gap; bending and pulls are linear and need none) and the global step solves
   (sum w S^T S + prox I) X = sum w S^T P + prox X_prev, one matrix for x, y and z, CONSTANT, factored once. After each
   global step points inside the body are put back out at the gap. Why: it does the big moves (a seed 30 % stretched, a
   tube closing round a limb, a 170 degree fold) robustly, each pass is one back-substitution, and it never diverges
   (each pass lowers the energy), so the jacket's ~24k points cost seconds, not hours. Then PD_STIFFEN: the same passes
   with the link and edge weights x10, x100 (one refactor each): the big moves are made, so stiffer springs now only
   take the strain out (N1b: the LM pass at 1.5k points started at E 6e3, links 14 % off; after these stages E ~1,
   links 0.1 %; the soft optimum barely moves). Contact rows in PD's matrix were tried: an isotropic row holds a node
   where it first touched (a sleeve could not slide round its arm), E at LM's start went UP 10-25x.
2. FAST PROJECTION (Goldenthal et al. 2007, as chain_net.project, over every point): the hard constraints, linearised,
   solved in one sparse system per pass (J J^T lambda = C), moving the points as little as possible until each holds to
   PROJ_TOL. Why: PD's springs only approach a length; the projection makes it exact. It is the last word of the solve.
The report reads the residuals at the end (chain_solve_terms.report). Deterministic: no random numbers, fixed orders,
direct factorisations. Self-contact is not handled here (N1); plies and layers are N2's constraints.
Factors (PD's and LM's): CHOLMOD, METIS ordering, supernodal, analysed once per solve and refactored (gn.Factor says why,
with N1c's numbers). PD runs 200 passes, then 100 per stiffening (N1c, 6k points: 400 first passes gave LM the same 11
factors and E 4.32 vs 4.33; 100 cost LM 5 more factors, dearer than the 100 passes saved).
"""
from __future__ import annotations

import time

import numpy as np
import scipy.sparse as sp
from sksparse.cholmod import CholeskyFactor
from threadpoolctl import threadpool_limits

from . import chain_net as cn
from . import chain_solve_gn as gn
from . import chain_solve_terms as terms
from .chain_core import GAP

W_LINK = 0.03  # PD weight of a link's strain (dimensionless rows). LOW on purpose: PD's springs aim at their current
# directions, so stiff ones lock rotations (a stiff collar pulled onto a neckline: 27 mm off at 1e3, 3.5 at 10; a 170
# degree fold's halves 25 degrees out of plane at 10, 0.3 mm at 0.03). Lengths are the LM pass's and projection's job.
W_EDGE = 0.003  # PD weight of an interior edge's strain
W_FOLD = 30.0  # PD weight of a fold quad's turn (rows / flat distance from the hinge)
W_TIE = 1e3  # PD weight of a tie (rows / REF)
REF = 0.01  # m: pulls and ties are weighed per this distance (weight 1: 1 cm off costs as much as a strain of 1)
PROX = 1e-3  # PD's proximal weight per node (rows / REF): keeps the matrix definite, damps nothing measurable
ROUND_TOL = 0.01  # a round whose projection changes E by less than this fraction is the last
TOL_PCT = 2.0  # a link past this % off its cut is reported (over_tol)
PROJ_TOL = 1e-4  # the projection's own target: links and exact edges within this fraction
STEP = 0.02  # m: a projection pass's largest move
PD_STIFFEN = (10.0, 100.0)  # the warm start's later stages: link and edge weights x these, refactored once each
PD_STAGE_ITERS = 100  # PD passes per later stage
PUSH_EVERY = 4  # PD passes between pushes out of the body (a body query is the PD pass's dearest part)
# the Levenberg-Marquardt pass's weights (chain_solve_gn): it linearises directions, so the hard terms may be stiff
W_GN = {"link": 1e4, "edge": 1e3, "fold": W_FOLD, "tie": W_TIE, "contact": gn.W_CONTACT, "ref": REF}


def _blocks(net, X0, ties, folds, pulls, stiffness, ct):
    """The solve's terms on nodes (sewn groups) and everything the report reads."""
    nid, nn = terms.nodes_of(net)
    cnt = np.bincount(nid, minlength=nn).astype(float)
    Xn = np.zeros((nn, 3))
    np.add.at(Xn, nid, np.asarray(X0, float))
    Xn /= cnt[:, None]
    li, lj, L, lp = terms.links(net, nid)
    ei, ej, eL, ex = terms.edges(net, nid, li, lj)
    folds = list(folds)
    fq = terms.fold_quads(net, folds)
    row_v = np.unique(np.concatenate([q["quads"][:, :2].ravel() for q in fq])).astype(np.int64) if fq else []
    stiff_w = cn.BEND_BASE * np.asarray(net.bend, float) if stiffness is None else np.asarray(stiffness, float)
    Sb, Wb, _ = terms.bend_rows(net, nid, nn, stiff_w, skip=row_v)
    if fq:  # (a fold row bends across itself, never along: row_rows)
        Sr, Wr = terms.row_rows(net, nid, nn, stiff_w, [f["row"] for f in folds])
        Sb, Wb = sp.vstack([Sb, Sr]).tocsr(), np.r_[Wb, Wr]
    T = [(int(a), int(b), float(g)) for a, b, g in ([t["a"], t["b"], t["gap"]] if isinstance(t, dict) else t
                                                     for t in ties)]
    P = []
    for k, p in enumerate(pulls):
        ids = np.asarray(p["ids"], np.int64)
        P.append({"ids": ids, "to": np.asarray(p["to"], float).reshape(len(ids), 3), "w": float(p.get("weight", 1.0)),
                  "name": p.get("name", f"pull{k}")})
    return {"nid": nid, "nn": nn, "Xn": Xn, "links": (li, lj, L, lp), "edges": (ei, ej, eL, ex), "folds": fq,
            "Sb": Sb, "Wb": Wb, "ties": T, "pulls": P, "ct": ct}


def _diff_rows(i, j, nn):
    m = len(i)
    r = np.r_[np.arange(m), np.arange(m)]
    return sp.coo_matrix((np.r_[np.ones(m), -np.ones(m)], (r, np.r_[j, i])), shape=(m, nn)).tocsr()


class _PD:
    """Quasi-static projective dynamics over the nodes (see the module doc)."""

    def __init__(self, t):
        nn, nid = t["nn"], t["nid"]
        li, lj, L, _ = t["links"]
        ei, ej, eL, ex = t["edges"]
        self.t = t
        self.stiff = 1.0
        self.F = None  # (CHOLMOD: analysed once, the pattern is the same at every stiffening; gn.Factor's notes)
        B = []  # (S, W, kind)
        B.append((_diff_rows(li, lj, nn), W_LINK / np.maximum(L, 1e-9) ** 2, "link"))
        B.append((_diff_rows(ei, ej, nn), W_EDGE / np.maximum(eL, 1e-9) ** 2, "edge"))
        B.append((t["Sb"], t["Wb"], "bend"))
        for p in t["pulls"]:
            n_ = nid[p["ids"]]
            B.append((sp.coo_matrix((np.ones(len(n_)), (np.arange(len(n_)), n_)), shape=(len(n_), nn)).tocsr(),
                      np.full(len(n_), p["w"] / REF ** 2), "pull"))
        for f in t["folds"]:
            q = f["quads"].astype(np.int64)
            a, c, d = nid[q[:, 0]], nid[q[:, 2]], nid[q[:, 3]]
            S = sp.vstack([_diff_rows(a, c, nn), _diff_rows(a, d, nn)]).tocsr()
            B.append((S, None, "fold"))  # (weights need the flat distances from the hinge: finish())
        if t["ties"]:
            ta = nid[np.array([x[0] for x in t["ties"]])]
            tb = nid[np.array([x[1] for x in t["ties"]])]
            B.append((_diff_rows(ta, tb, nn), np.full(len(ta), W_TIE / REF ** 2), "tie"))
        self.B = B

    def finish(self, net, stiffen: float = 1.0):
        """Fold weights need the flat distances (set here), then the constant matrix is factored. stiffen scales the
        link and edge weights (the later stages of the warm start)."""
        B = []
        k = 0
        for S, W, kind in self.B:
            if kind == "fold":
                f = self.t["folds"][k]
                q = f["quads"].astype(np.int64)
                h = np.r_[np.linalg.norm(net.uv[q[:, 2]] - net.uv[q[:, 0]], axis=1),
                          np.linalg.norm(net.uv[q[:, 3]] - net.uv[q[:, 0]], axis=1)]
                W = W_FOLD * f["weight"] / h ** 2
                k += 1
            elif kind in ("link", "edge"):
                W = W * (stiffen / self.stiff)
            B.append((S, W, kind))
        self.B = B
        self.stiff = stiffen
        nn = self.t["nn"]
        A = sp.identity(nn, format="csr") * (PROX / REF ** 2)
        for S, W, _ in B:
            A = A + S.T @ sp.diags(W) @ S
        self.M = sp.hstack([S.T @ sp.diags(W) for S, W, _ in B], format="csr")  # (a pass's right side: one product)
        A = sp.tril(A, format="csc")
        A.sort_indices()
        with threadpool_limits(1):
            if self.F is None:
                self.F = CholeskyFactor(A, lower=True, order="metis", supernodal_mode="supernodal")
            self.F.factorize(A)

    def targets(self, Xn):
        t = self.t
        out = []
        fk = 0
        _, _, L, _ = t["links"]
        _, _, eL, ex = t["edges"]
        pk = 0
        for S, W, kind in self.B:
            D = S @ Xn
            if kind == "link":
                out.append(cn.unit(D) * L[:, None])
            elif kind == "edge":
                l = np.linalg.norm(D, axis=1)
                out.append(cn.unit(D) * np.where(ex, eL, np.minimum(l, eL))[:, None])
            elif kind == "bend":
                out.append(np.zeros_like(D))
            elif kind == "pull":
                out.append(t["pulls"][pk]["to"])
                pk += 1
            elif kind == "fold":
                out.append(self._fold_target(Xn, t["folds"][fk]))
                fk += 1
            elif kind == "tie":
                g = np.array([x[2] for x in t["ties"]])
                out.append(cn.unit(D) * g[:, None])
        return out

    def _fold_target(self, Xn, f):
        """Each quad's far corners turned about its edge, half the error each, to the planned turn."""
        nid = self.t["nid"]
        q = f["quads"]
        a, b, c, d = (nid[q[:, k].astype(np.int64)] for k in range(4))
        psi, e, x, y = terms.turn_of(Xn, a, b, c, d, q[:, 4])
        half = np.angle(np.exp(1j * (f["target"] - psi))) / 2
        uc, ud = Xn[c] - Xn[a], Xn[d] - Xn[a]
        pc, pd = (uc * e).sum(1), (ud * e).sum(1)
        rc = np.linalg.norm(uc - pc[:, None] * e, axis=1)
        rd = np.linalg.norm(ud - pd[:, None] * e, axis=1)
        ac, ad = np.pi - half, psi + half
        tc = pc[:, None] * e + rc[:, None] * (np.cos(ac)[:, None] * x + np.sin(ac)[:, None] * y)
        td = pd[:, None] * e + rd[:, None] * (np.cos(ad)[:, None] * x + np.sin(ad)[:, None] * y)
        return np.r_[tc, td]

    def step(self, Xn):
        rhs = Xn * (PROX / REF ** 2) + self.M @ np.concatenate(self.targets(Xn))
        with threadpool_limits(1):
            return self.F.solve(rhs)


class _Near:
    """The body's distance query, asked only where it can matter: a point last measured d away that has moved m since
    can't be nearer than d - m (distance is 1-Lipschitz), so it is asked again only when d - m < gap + REACH. Every
    caller only acts on points nearer than the gap, so the answer is exact where it is used; elsewhere sd is that bound
    and the normal zero. (The full query costs ~40 us a point: 400 PD passes over ~24k points would be minutes.)"""
    REACH = 0.01

    def __init__(self, ct, gap):
        self.ct, self.gap = ct, float(gap)
        self.X = None

    def query(self, X):
        X = np.asarray(X, float)
        if self.X is None or len(self.X) != len(X):
            self.X, (self.sd, self.n) = X.copy(), self.ct.query(X)
            return self.sd.copy(), self.n.copy()
        lb = self.sd - np.linalg.norm(X - self.X, axis=1)
        ask = np.where(lb < self.gap + self.REACH)[0]
        sd, n = lb, np.zeros_like(X)
        if len(ask):
            s_, n_ = self.ct.query(X[ask])
            self.X[ask], self.sd[ask], self.n[ask] = X[ask], s_, n_
            sd[ask], n[ask] = s_, n_
        return sd, n


def _push_out(Xn, ct, gap):
    if ct is None:
        return Xn
    sd, nrm = ct.query(Xn)
    m = sd < gap
    Xn = Xn.copy()
    Xn[m] += (gap - sd[m])[:, None] * nrm[m]
    return Xn


def _project(Xn, t, ct, gap, iters: int = 40, log=None):
    """The hard constraints over every node (fast projection): links, edges (exact / at most), ties, contact."""
    nid = t["nid"]
    li, lj, L, _ = t["links"]
    ei, ej, eL, ex = t["edges"]
    I = np.r_[li, ei]
    J_ = np.r_[lj, ej]
    Ls = np.r_[L, eL]
    exact = np.r_[np.ones(len(L), bool), ex]
    ti = nid[np.array([x[0] for x in t["ties"]], np.int64)] if t["ties"] else np.zeros(0, np.int64)
    tj = nid[np.array([x[1] for x in t["ties"]], np.int64)] if t["ties"] else np.zeros(0, np.int64)
    tg = np.array([x[2] for x in t["ties"]], float)
    nn = len(Xn)
    Xn = Xn.copy()
    for it in range(iters):
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
            for dd in range(3):
                R.append(r0)
                C.append(3 * side[ka] + dd)
                V.append(sg * u[ka, dd])
        m = len(ka)
        tie_bad = 0.0
        for k in range(len(tg)):
            dvt = Xn[tj[k]] - Xn[ti[k]]
            lt = float(np.linalg.norm(dvt))
            if tg[k] < 1e-6 or lt < 1e-9:  # (on each other: three rows, one per axis)
                tie_bad = max(tie_bad, lt)
                for dd in range(3):
                    R += [np.array([m]), np.array([m])]
                    C += [np.array([3 * tj[k] + dd]), np.array([3 * ti[k] + dd])]
                    V += [np.array([1.0]), np.array([-1.0])]
                    Cs.append(np.array([dvt[dd]]))
                    m += 1
            else:
                tie_bad = max(tie_bad, abs(lt - tg[k]))
                ut = dvt / lt
                for dd in range(3):
                    R += [np.array([m]), np.array([m])]
                    C += [np.array([3 * tj[k] + dd]), np.array([3 * ti[k] + dd])]
                    V += [np.array([ut[dd]]), np.array([-ut[dd]])]
                Cs.append(np.array([lt - tg[k]]))
                m += 1
        deep = 0.0
        if ct is not None:
            sd, nrm = ct.query(Xn)
            sh = np.where(sd < gap)[0]
            if len(sh):
                deep = float(np.max(gap - sd[sh]))
                r = m + np.arange(len(sh))
                for dd in range(3):
                    R.append(r)
                    C.append(3 * sh + dd)
                    V.append(nrm[sh, dd])
                Cs.append(sd[sh] - gap)
                m += len(sh)
        if log:
            log(f"  project {it}: worst {worst * 100:.4f} %, tie {tie_bad * 1e3:.3f} mm, deep {deep * 1e3:.3f} mm")
        if worst <= PROJ_TOL and tie_bad <= 1e-5 and deep <= 1e-5:
            break
        Jm = sp.coo_matrix((np.concatenate(V), (np.concatenate(R), np.concatenate(C))), shape=(m, 3 * nn)).tocsr()
        dx = -cn._solve(Jm, np.concatenate(Cs), 1e-9).reshape(nn, 3)
        mx = float(np.linalg.norm(dx, axis=1).max())
        if mx > STEP:
            dx *= STEP / mx
        Xn = Xn + dx
    return Xn, it + 1


def solve(net: cn.Network, X0, body=None, ties=(), folds=(), pulls=(), stiffness=None, gap: float = GAP,
          pd_iters: int = 200, polish_rounds: int = 2,
          lm_iters: int = 30, log=None) -> tuple:
    """Every point free; see the module doc. Returns (X per vertex, report)."""
    t0 = time.time()
    ct = None if body is None else getattr(body, "contact", body)
    near = None if ct is None else _Near(ct, gap)
    t = _blocks(net, X0, ties, folds, pulls, stiffness, ct)
    pd = _PD(t)
    pd.finish(net)
    Xn = _push_out(t["Xn"], near, gap)
    passes, lm, nfac = [], [], []
    tm = {"setup": time.time() - t0}
    t1 = time.time()
    for npd in range(pd_iters):
        Xp, Xn = Xn, pd.step(Xn)
        if npd % PUSH_EVERY == 0 or npd == pd_iters - 1:
            Xn = _push_out(Xn, near, gap)
        if np.abs(Xn - Xp).max() < 1e-7:
            break
    for sf in PD_STIFFEN:  # (the big moves are made: stiffer springs now only take the strain out)
        pd.finish(net, sf)
        for k_ in range(PD_STAGE_ITERS):
            Xp, Xn = Xn, pd.step(Xn)
            if k_ % PUSH_EVERY == 0 or k_ == PD_STAGE_ITERS - 1:
                Xn = _push_out(Xn, near, gap)
            if np.abs(Xn - Xp).max() < 1e-7:
                break
    tm["pd"] = time.time() - t1
    tm["lm"] = tm["project"] = 0.0
    for rnd in range(polish_rounds):
        t1 = time.time()
        Xn, k, E, nf = gn.polish(Xn, t, W_GN, near, gap, iters=lm_iters, log=log)
        t2 = time.time()
        Xn, np_ = _project(Xn, t, near, gap, log=log)
        tm["lm"] += t2 - t1
        tm["project"] += time.time() - t2
        lm.append(k)
        nfac.append(nf)
        passes.append(np_)
        if log:
            log(f"round {rnd}: lm passes {k} ({nf} factors, E {E:.4g}), projection passes {np_}")
        Ep = float(np.sum(gn.residuals(Xn, t, W_GN, near, gap, jac=False)[0] ** 2))
        if abs(Ep - E) <= ROUND_TOL * E:  # (the projection barely moved the energy: another round would not either)
            break
    t["Xn"] = Xn
    X = Xn[t["nid"]]
    rep = terms.report(net, X, t, None if ct is None else (ct, gap), TOL_PCT)
    rep["seconds"] = round(time.time() - t0, 2)
    rep["points"] = int(net.n)
    rep["projection_passes"] = passes
    rep["lm_passes"] = lm
    rep["lm_factors"] = nfac
    rep["pd_passes"] = npd + 1
    rep["timing"] = {k: round(v, 2) for k, v in tm.items()}
    return X, rep
