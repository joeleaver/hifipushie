"""ASSEMBLE AND DRESS ROLLED PANELS (N2d of docs/proposals/step5_rewrite.md, "The build" 2-3).

The unknowns are the panels' numbers (chain_panels: 8 per panel, ~150-190 for a jacket), never points. One small
least-squares fit (scipy least_squares, finite-difference Jacobian over the panels each residual touches):
- SEAMS: every sew pair's two points at their panels' maps coincide (the residual IS the seam gap). Seams are one chain
  end to end (chain_seams.join_seams), so a seam is matched point for point along its whole length.
- HINGES: a fold row's points on both its panels coincide, and the turned panel's direction across the row is the plan's
  turn (chain_panels.hinge_read).
- TIES: closures' pairs a LAYER apart.
- ROLL: a stiff panel's curvature is a weight (stiff cloth rolls little), never a limit.
- ASSEMBLE (`assemble`): a soft keep-out from the body's skeleton (chain_settle.skeleton: which way round, arms in
  sleeves, neck in the collar) and a weak pull of each panel's centre to its start (the fit is small: it stays near).
- DRESS (`dress`): the same numbers refitted with the body at full size: every point off the body (one-sided, GAP),
  the girth tapes each piece was drafted on pulling its points at their height (chain_settle.girth_pulls), seams,
  hinges and ties as in assembly.
- CLOSE (`close`): ONE final projection of the chain points (chain_net.project, every link exact, nodes off the body)
  to close what rigid panels cannot (darts, ease: a doubly-curved garment); how far it moved points and links is read.
Every read: seam gaps per seam (mm, mean / max), hinge turns vs plan, roll radii, points inside, tape distances.
Rigid rolled panels cannot assemble a doubly-curved garment exactly: the gaps left are the honest report, never hidden.
Nothing here knows a garment, a piece's role or a wear state.
"""
from __future__ import annotations

import time

import numpy as np
import scipy.sparse as sp
from scipy.optimize import least_squares

from .chain_core import GAP, LAYER
from .chain_panels import NP

W_SEAM = 1.0
W_HINGE = 1.0  # row points of a hinge on both its panels
W_TURN = 0.05  # m per unit of direction off the planned turn
W_STIFF = 0.002  # m per 1/m of a stiff panel's roll
W_KEEP = 1.0  # per m inside the keep-out
KEEP_R = 0.035  # m: no point nearer the skeleton than this while assembling
W_START = 0.02  # pull of a panel's centre towards its start (per m)
W_BODY = 2.0  # per m under GAP when dressing
W_TAPE = 0.3  # a girth tape's pull (per m)
TIE_W = 0.5


def _seg_dist(P, S):
    a, b = S[:, 0], S[:, 1]
    ab = b - a
    t = np.clip(((P[:, None] - a[None]) * ab[None]).sum(2) / np.maximum((ab * ab).sum(1), 1e-12)[None], 0, 1)
    return np.linalg.norm(P[:, None] - (a[None] + t[..., None] * ab[None]), axis=2).min(1)


class Fit:
    """The residual over the panels' numbers (module doc). keep: skeleton segments; contact: the body; pulls."""

    def __init__(self, pan, ties=(), TH0=None, keep=None, contact=None, pulls=(), sub=1):
        c = pan.cnet
        self.pan, self.c = pan, c
        own = pan.owner
        sew = c.sew[(own[c.sew] >= 0).all(1)]
        self.sew = sew
        self.ties = [(a, b, d) for a, b, d in ties if own[a] >= 0 and own[b] >= 0]
        self.TH0, self.keep, self.contact, self.pulls = TH0, keep, contact, list(pulls)
        self.stiff = np.array([float(c.stiff[p["ids"]].mean()) for p in pan.panels])
        self.pts = np.where(own >= 0)[0][::sub]
        self.C0 = None if TH0 is None else np.array([pan.place(TH0[k], k, p["c"][None])[0] for k, p in
                                                     enumerate(pan.panels)])
        self._sparsity()

    def _blocks(self):
        """[(rows, [panels])] in residual order."""
        pan, own = self.pan, self.pan.owner
        out = [(3, [own[a], own[b]]) for a, b in self.sew]
        for h in pan.hinges:
            out += [(3, [h["base"], h["turned"]])] * len(h["row"]) + [(3, [h["base"], h["turned"]])]
        out += [(1, [own[a], own[b]]) for a, b, _ in self.ties]
        out += [(1, [k]) for k in range(pan.n)]
        if self.keep is not None:
            out += [(1, [own[i]]) for i in self.pts]
            out += [(3, [k]) for k in range(pan.n)]
        if self.contact is not None:
            out += [(1, [own[i]]) for i in self.pts]
        for p in self.pulls:
            out += [(3, [own[i]]) for i in p["ids"] if own[i] >= 0]
        return out

    def _sparsity(self):
        R, C = [], []
        r = 0
        for nr, ps in self._blocks():
            for q in range(nr):
                for k in set(ps):
                    R += [r + q] * NP
                    C += list(range(k * NP, k * NP + NP))
            r += nr
        self.m = r
        self.S = sp.coo_matrix((np.ones(len(R)), (R, C)), shape=(r, self.pan.n * NP)).tocsr()

    def residual(self, x):
        pan, c, own = self.pan, self.c, self.pan.owner
        TH = x.reshape(pan.n, NP)
        X = pan.positions(TH)
        out = [W_SEAM * (X[self.sew[:, 0]] - X[self.sew[:, 1]]).ravel()]
        for h in pan.hinges:
            uv = c.uv[h["row"]]
            out.append(W_HINGE * (pan.place(TH[h["base"]], h["base"], uv) - pan.place(TH[h["turned"]], h["turned"], uv)).ravel())
            wb, tgt, _ = pan.hinge_read(TH, h)
            out.append(W_TURN * (wb - tgt))
        if self.ties:
            a, b, d = map(np.asarray, zip(*self.ties))
            out.append(TIE_W * (np.linalg.norm(X[a.astype(int)] - X[b.astype(int)], axis=1) - d))
        out.append(W_STIFF * self.stiff * TH[:, 7])
        if self.keep is not None:
            out.append(W_KEEP * np.maximum(0.0, KEEP_R - _seg_dist(X[self.pts], self.keep)))
            C = np.array([pan.place(TH[k], k, p["c"][None])[0] for k, p in enumerate(pan.panels)])
            out.append(W_START * (C - self.C0).ravel())
        if self.contact is not None:
            sd, _ = self.contact.query(X[self.pts])
            out.append(W_BODY * np.maximum(0.0, GAP - sd))
        for p in self.pulls:
            m = own[p["ids"]] >= 0
            out.append(W_TAPE * p.get("weight", 1.0) * (X[p["ids"][m]] - p["to"][m]).ravel())
        return np.concatenate(out)

    def solve(self, TH, iters=60, log=None):
        t0 = time.time()
        r = least_squares(self.residual, TH.ravel(), jac_sparsity=self.S, max_nfev=iters, x_scale="jac",
                          method="trf", tr_solver="lsmr")
        if log:
            log(f"panels fit: cost {r.cost:.5f} after {r.nfev} evaluations, {time.time() - t0:.0f} s")
        return r.x.reshape(self.pan.n, NP), {"cost": round(float(r.cost), 6), "evals": int(r.nfev),
                                             "seconds": round(time.time() - t0, 1)}


def seam_gaps(pan, TH) -> dict:
    """{'a ~ b': [mean, max] mm} over every sew pair, by the two pieces (a piece sewn to itself: 'a ~ a')."""
    c, own = pan.cnet, pan.owner
    X = pan.positions(TH)
    out: dict = {}
    for a, b in c.sew:
        if own[a] < 0 or own[b] < 0:
            continue
        k = " ~ ".join(sorted((c.names[c.piece[a]], c.names[c.piece[b]])))
        out.setdefault(k, []).append(float(np.linalg.norm(X[a] - X[b])) * 1e3)
    for h in pan.hinges:
        uv = c.uv[h["row"]]
        d = np.linalg.norm(pan.place(TH[h["base"]], h["base"], uv) - pan.place(TH[h["turned"]], h["turned"], uv), axis=1)
        out.setdefault(f"hinge {h['name']}", []).extend((d * 1e3).tolist())
    return {k: [round(float(np.mean(v)), 1), round(float(np.max(v)), 1)] for k, v in sorted(out.items(),
                                                                                            key=lambda t: -max(t[1]))}


def reads(pan, TH) -> dict:
    """Seam gaps, hinge turns vs plan, roll radii by panel."""
    return {"seam_gaps_mm": seam_gaps(pan, TH),
            "hinges": {h["name"]: {"planned": h["turn_deg"], "got": round(pan.hinge_read(TH, h)[2], 1)}
                       for h in pan.hinges},
            "roll_radius_mm": {f"{p['piece']}#{k}": (round(1e3 / abs(TH[k, 7]), 0) if abs(TH[k, 7]) > 1e-3 else "flat")
                               for k, p in enumerate(pan.panels)}}


def nodes_of(pan, TH):
    """Per point: the mean over its sewn group (cnet.root) of its points at their owner panels (unowned: nan)."""
    c = pan.cnet
    X = pan.positions(TH)
    ok = ~np.isnan(X[:, 0])
    S = np.zeros((c.n, 3))
    n = np.zeros(c.n)
    np.add.at(S, c.root[ok], X[ok])
    np.add.at(n, c.root[ok], 1)
    Xn = S / np.maximum(n, 1)[:, None]
    return Xn[c.root], n[c.root] > 0


def assemble(pan, TH0, keep, ties=(), iters=40, log=None, sub=3):
    """(TH, read): the panels assembled off their start (module doc)."""
    f = Fit(pan, ties, TH0=TH0, keep=keep, sub=sub)
    TH, rd = f.solve(TH0, iters, log)
    rd.update(unknowns=pan.n * NP, residuals=f.m, **reads(pan, TH))
    return TH, rd


def dress(pan, TH, contact, pulls, ties=(), iters=25, log=None, sub=3):
    """(TH, read): the same numbers refitted on the body (module doc)."""
    f = Fit(pan, ties, contact=contact, pulls=pulls, sub=sub)
    TH, rd = f.solve(TH, iters, log)
    X = pan.positions(TH)
    m = ~np.isnan(X[:, 0])
    sd, _ = contact.query(X[m])
    rd.update(reads(pan, TH), inside=int((sd < 0).sum()), under_gap=int((sd < GAP - 1e-4).sum()))
    return TH, rd


def close(cnet, X, contact=None, iters=40, log=None):
    """(X, read): ONE projection of the chain points closing what panels leave open (module doc)."""
    from . import chain_net as cn
    from .chain_lay import node_links
    i, j, L, ex = node_links(cnet)
    nodes = np.unique(cnet.root)
    Xn = X.copy()
    cts = [] if contact is None else [(contact, nodes, GAP)]
    Y, rd = cn.project(Xn, i, j, L, ex, contacts=cts, iters=iters, log=log)
    Y = Y[cnet.root]
    mv = np.linalg.norm(Y - X, axis=1) * 1e3
    a, b = cnet.chain_v[:, 0], cnet.chain_v[:, 1]
    e = np.abs(np.linalg.norm(Y[b] - Y[a], axis=1) / np.maximum(cnet.chain_L, 1e-12) - 1) * 100
    return Y, {"moved_mm": {"median": round(float(np.median(mv)), 1), "p95": round(float(np.percentile(mv, 95)), 1),
                            "max": round(float(mv.max()), 1)},
               "links_pct": {"median": round(float(np.median(e)), 3), "p99": round(float(np.percentile(e, 99)), 3),
                             "max": round(float(e.max()), 3)}, "projection": rd}


def links_pct(cnet, X) -> dict:
    a, b = cnet.chain_v[:, 0], cnet.chain_v[:, 1]
    ok = ~np.isnan(X[a, 0]) & ~np.isnan(X[b, 0])
    e = np.abs(np.linalg.norm(X[b] - X[a], axis=1)[ok] / np.maximum(cnet.chain_L[ok], 1e-12) - 1) * 100
    return {"max": round(float(e.max()), 4), "p99": round(float(np.percentile(e, 99)), 4)}


__all__ = ["Fit", "assemble", "dress", "close", "reads", "seam_gaps", "nodes_of", "links_pct", "LAYER"]
