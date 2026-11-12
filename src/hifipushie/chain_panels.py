"""ROLLED PANELS (N2d of docs/proposals/step5_rewrite.md, "The build" 1): every piece of the pattern is its flat outline
mapped by a DEVELOPABLE map with a handful of numbers, so lengths are given and only bends are chosen, literally.

Joe (2026-11-12) chose "Rolled panels, bends" after three runs failed at one point: turning flats into an assembled 3D
shape with positions as the unknowns (N2c: links 300-2,900 % off their cut before any bend). Here no point is ever a
free variable:
- A PANEL is a piece's flat (or a part of it between fold rows) mapped by: a ROLL round a cylinder (the axis's direction
  in the flat, phi, and its curvature, kappa: 0 = flat) then a rigid motion (a rotation vector and a translation): 8
  numbers. The map is ISOMETRIC by construction: every link of every chain is at its cut whatever the numbers
  (`roll`: (s, t) -> (s, sin(k t) / k, (1 - cos(k t)) / k), the flat's +z onto the surface's normal).
- A FOLD ROW splits its piece into panels (each point's side of each row; row points belong to both) joined by a
  HINGE along the row with one angle: the turned panel's direction across the row against the plan's turn (the turn
  split over the draft's rows, towards the side the draft's sign says: sign x the flat's winding, +1 = the flat's +z).
  The turned side of a row is its smaller side.
- A piece sewn to nothing (a ply that follows its host) is not a panel: it is bound on its host afterwards.
Panels(cnet, plan, skip) -> .panels [{piece, ids, c (flat centre)}], .owner (point -> its first panel), .hinges.
place(th, k, uv) / positions(th): the map; fit_start(Xs): each panel's numbers fitted to a start (Kabsch then the roll).
Nothing here knows a garment, a piece's role or a wear state.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .chain_lay_net import _side

NP = 8  # numbers per panel: rotation vector (3), translation (3), roll axis angle in the flat, roll curvature


def roll(uv, phi, kappa):
    """The flat uv (n, 2, about the panel's centre) rolled round a cylinder: (n, 3) local, isometric (module doc)."""
    c, s_ = np.cos(phi), np.sin(phi)
    s = uv[:, 0] * c + uv[:, 1] * s_
    t = -uv[:, 0] * s_ + uv[:, 1] * c
    a = kappa * t
    if abs(kappa) < 1e-6:
        y, z = t - kappa * t ** 3 * kappa / 6, kappa * t * t / 2
    else:
        y, z = np.sin(a) / kappa, (1 - np.cos(a)) / kappa
    # (back into the flat's own axes so phi = 0, kappa = 0 is the identity on the plane)
    return np.c_[s * c - y * s_, s * s_ + y * c, z]


def roll_normal(uv, phi, kappa):
    t = -uv[:, 0] * np.sin(phi) + uv[:, 1] * np.cos(phi)
    a = kappa * t
    ny = -np.sin(a)
    return np.c_[-ny * np.sin(phi), ny * np.cos(phi), np.cos(a)]


class Panels:
    """The panels of a chains-only network (module doc)."""

    def __init__(self, cnet, plan=None, skip=()):
        from .chain_lay import _draft_fold, _uv_wind
        self.cnet = cnet
        plan = plan or {}
        rows_of: dict = {}
        for bid, f in sorted((plan.get("folds") or {}).items()):
            fd = _draft_fold(cnet, f, bid)
            rows = [np.asarray(r, np.int64) for r in fd.get("rows") or []]
            way = float(fd.get("sign", 1.0)) * _uv_wind(cnet, f["on"])
            for r in rows:
                rows_of.setdefault(cnet.pid(f["on"]), []).append((r, float(f["turn_deg"]) / len(rows), way, bid))
        self.panels, self.hinges = [], []
        self.owner = -np.ones(cnet.n, np.int64)
        for p, nm in enumerate(cnet.names):
            if nm in skip:
                continue
            ids = np.where(cnet.piece == p)[0]
            rows = rows_of.get(p, [])
            if not rows:
                self._add(nm, ids)
                continue
            S = np.stack([_side(cnet.uv, r, cnet.uv[ids]) for r, *_ in rows], 1)
            for k, (r, _, _, _) in enumerate(rows):  # (the smaller side of each row is its turned side)
                sm = [np.ptp(cnet.uv[ids[S[:, k] == s_]], 0).prod() if (S[:, k] == s_).any() else 0 for s_ in (1, -1)]
                if sm[0] > sm[1]:
                    S[:, k] *= -1  # (-1: the base side, +1: the turned side)
            sig = np.unique(S[(S != 0).all(1)], axis=0)
            pan = {}
            for g in sig:
                m = ((S == g) | (S == 0)).all(1)
                pan[tuple(g)] = self._add(nm, ids[m])
            for k, (r, turn, way, bid) in enumerate(rows):
                for g in sig:
                    if g[k] != 1:
                        continue
                    g0 = g.copy()
                    g0[k] = -1
                    if tuple(g0) not in pan:
                        continue
                    a, b = pan[tuple(g0)], pan[tuple(g)]
                    on = r[np.isin(r, self.panels[a]["ids"]) & np.isin(r, self.panels[b]["ids"])]
                    if len(on) < 2:
                        continue
                    d = cnet.uv[on[-1]] - cnet.uv[on[0]]
                    m2 = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-12)
                    tp = self.panels[b]["ids"]
                    if (cnet.uv[tp].mean(0) - cnet.uv[on].mean(0)) @ m2 < 0:
                        m2 = -m2
                    self.hinges.append({"base": a, "turned": b, "row": on, "turn_deg": turn, "way": way,
                                        "mid": cnet.uv[on].mean(0), "across": m2, "name": f"{bid}#{k}"})
        self.n = len(self.panels)
        self.shared = [(h["base"], h["turned"], h["row"]) for h in self.hinges]

    def _add(self, nm, ids):
        k = len(self.panels)
        self.panels.append({"piece": nm, "ids": ids, "c": self.cnet.uv[ids].mean(0)})
        free = self.owner[ids] < 0
        self.owner[ids[free]] = k
        return k

    # ---- the map
    def place(self, th, k, uv):
        """Panel k's numbers th (NP,) applied to flat points uv (n, 2)."""
        L = roll(uv - self.panels[k]["c"], th[6], th[7])
        return Rotation.from_rotvec(th[:3]).apply(L) + th[3:6]

    def normal(self, th, k, uv):
        return Rotation.from_rotvec(th[:3]).apply(roll_normal(uv - self.panels[k]["c"], th[6], th[7]))

    def positions(self, TH, which=None):
        """(n, 3): every point at its owner panel's map (which: a per-point panel instead of the owner)."""
        which = self.owner if which is None else which
        X = np.full((self.cnet.n, 3), np.nan)
        for k in range(self.n):
            m = which == k
            if m.any():
                X[m] = self.place(TH[k], k, self.cnet.uv[m])
        return X

    def hinge_read(self, TH, h, eps=1e-3):
        """(turned panel's direction across the row, target direction, measured turn deg) at the row's middle."""
        a, b, mid, m = h["base"], h["turned"], h["mid"][None], h["across"][None]
        pa0, pa1 = self.place(TH[a], a, mid), self.place(TH[a], a, mid + eps * m)
        pb1 = self.place(TH[b], b, mid + eps * m)
        wa = (pa1 - pa0)[0] / eps
        wb = (pb1 - self.place(TH[b], b, mid))[0] / eps
        n = self.normal(TH[a], a, mid)[0] * h["way"]
        th = np.radians(h["turn_deg"])
        tgt = np.cos(th) * wa + np.sin(th) * n
        got = np.degrees(np.arctan2(wb @ n, wb @ wa))
        return wb, tgt, float(got)

    def fit_start(self, Xs):
        """Each panel's numbers fitted to start positions Xs (n, 3) of the network's points: (P, NP)."""
        TH = np.zeros((self.n, NP))
        for k, P in enumerate(self.panels):
            ids = P["ids"]
            A = np.c_[self.cnet.uv[ids] - P["c"], np.zeros(len(ids))]
            B = Xs[ids]
            ma, mb = A.mean(0), B.mean(0)
            U, _, Vt = np.linalg.svd((A - ma).T @ (B - mb))
            D = np.diag([1.0, 1.0, np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0])
            R = Vt.T @ D @ U.T
            th0 = np.r_[Rotation.from_matrix(R).as_rotvec(), mb - R @ ma, 0.0, 0.0]
            best = None
            for phi in (0.0, np.pi / 2):  # (the roll axis along either flat axis; the fit takes the better)
                for kap in (-4.0, 4.0):
                    x0 = th0.copy()
                    x0[6], x0[7] = phi, kap
                    r = least_squares(lambda t: (self.place(t, k, self.cnet.uv[ids]) - B).ravel(), x0, max_nfev=200)
                    if best is None or r.cost < best.cost:
                        best = r
            TH[k] = best.x
        return TH
