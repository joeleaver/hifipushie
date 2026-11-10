"""CHAIN STIFF: stage 5 and the stiff stages' order (chain_garment.py's docstring is the spec): closure ties, the open
PLACKETS, the stiff pieces' remaining chains (stiff_last, stiff_stage), the thread read, and the fall resting on the soft
cloth under it. Moved out of chain_garment.py as a mixin of GarmentBuild (R3a, behaviour-preserving)."""
from __future__ import annotations

import math

import numpy as np

from .chain_net import Contact, project
from .chain_core import (LAYER, ChainRefused)


class StiffStages:
    """GarmentBuild's plackets and stiff stages (mixed into chain_garment.GarmentBuild)."""

    def _closure_ties(self):
        """Fastened pairs of a closure between two pieces: a layer apart (root a, root b, distance)."""
        from .chain_roles import tie_gap
        net, R = self.net, self.roles
        out = []
        if R.front:
            for (a, b), c in zip(R.front["v"], R.front.get("closed") or []):
                if c:
                    out.append((net.root[a], net.root[b], tie_gap(R.front, LAYER)))
        return np.array(out, float).reshape(-1, 3)

    # ---- 5. plackets, open
    def plackets(self, Xclosed):
        """Each placket is a stiff strip that folds out of plane along a crease through the first fastened button: solved
        so its sewn top edge reaches the open band. Above the crease it folds, the rest stays; the fold acts on the real
        shape, so nothing jumps at the crease. The over side stays in front of the under side."""
        from scipy.optimize import minimize
        net, R = self.net, self.roles
        uv, rs = net.uv, net.root
        cl = R.front
        extra = np.zeros(net.n, bool)
        rep = {}
        Xnew = self.X.copy()
        for pname, bv, over in ((cl["over"], cl["v"][0][0], 1.0), (cl["under"], cl["v"][0][1], -1.0)):
            pv = net.verts(pname)
            rows = [r for f, r in net.fold_rows() if f["piece"] == pname]
            if not rows:
                raise ChainRefused(f"{pname}: no pressed fold marks its placket. next: declare the placket fold in the pattern")
            fx = float(np.median(uv[rows[0], 0]))
            ex = float(uv[pv, 0].min() if fx > 0 else uv[pv, 0].max())
            lo, hi = sorted((ex, fx))
            yb = float(uv[bv, 1])
            BL = 0.02
            strip = pv[(uv[pv, 0] >= lo - 1e-5) & (uv[pv, 0] <= hi + 1e-5) & (uv[pv, 1] > yb - BL)]
            sew_ = self.sewn_with(pname, R.band)
            top = np.array(sorted(v for v in sew_ if lo - 1e-5 <= uv[v, 0] <= hi + 1e-5), np.int64)
            piv = Xclosed[bv].copy()
            piv[0] = 0.0
            piv[1] -= over * LAYER / 2
            near = strip[np.abs(uv[strip, 1] - yb) < 0.012]
            A_, B_ = np.c_[uv[near], np.zeros(len(near))], Xclosed[near]
            ca, cb = A_.mean(0), B_.mean(0)
            Us, _, Vt = np.linalg.svd((A_ - ca).T @ (B_ - cb))
            Rf = Vt.T @ Us.T
            if np.linalg.det(Rf) < 0:
                Vt[-1] *= -1
                Rf = Vt.T @ Us.T

            def Mf(Q):
                return (np.c_[Q - uv[bv], np.zeros(len(Q))]) @ Rf.T + piv

            def fold(Q, al, ph, soft=0.004):
                dir2 = np.array([math.cos(al), math.sin(al)])
                nor2 = np.array([-dir2[1], dir2[0]])
                sd = (Q - uv[bv]) @ nor2
                ws = np.clip(sd / soft + 0.5, 0, 1)
                ws = ws * ws * (3 - 2 * ws)
                k3 = Rf @ np.r_[dir2, 0.0]
                p3 = Mf(Q) - piv
                c_, s_ = np.cos(ph * ws)[:, None], np.sin(ph * ws)[:, None]
                return piv + p3 * c_ + np.cross(k3, p3) * s_ + k3 * (p3 @ k3)[:, None] * (1 - c_), sd
            Tgt = self.X[rs[top]]
            best = None
            for al in np.radians(np.arange(-75, 76, 3)):
                for ph in np.radians(np.arange(-178, 179, 4)):
                    Y_, sd_ = fold(uv[top], al, ph)
                    if (sd_ < 0).any():
                        continue  # the crease stays below the whole top edge
                    c_ = float(((Y_ - Tgt) ** 2).sum())
                    if best is None or c_ < best[0]:
                        best = (c_, al, ph)
            if best is None:
                raise ChainRefused(f"{pname}: no crease through the first fastened button clears the placket's top edge. "
                                   "next: check the button position against the neck (design_garment)")
            r_ = minimize(lambda q: float(((fold(uv[top], q[0], q[1])[0] - Tgt) ** 2).sum()), best[1:], method="Nelder-Mead",
                          options={"xatol": 1e-3, "fatol": 1e-9})
            al, ph = r_.x
            # the strip is all the crease folds, and BL past it: a steep crease folds cloth below the button too, and a
            # strip cut at a fixed height below the button tore there (T7: front.L edge +59 % 14 mm under the button)
            xr = pv[(uv[pv, 0] >= lo - 1e-5) & (uv[pv, 0] <= hi + 1e-5)]
            strip = np.union1d(strip, xr[fold(uv[xr], al, ph)[1] > -BL])
            Yt, sdt = fold(uv[top], al, ph)
            res = Tgt - Yt
            o_ = np.argsort(uv[top, 0])
            pos, sd_ = fold(uv[strip], al, ph)
            tt = np.clip(sd_ / np.maximum(np.interp(uv[strip, 0], uv[top[o_], 0], sdt[o_]), 1e-4), 0, 1)
            pos += np.column_stack([np.interp(uv[strip, 0], uv[top[o_], 0], res[o_, k]) for k in range(3)]) * tt[:, None]
            pos = pos + (Xclosed[strip] - Mf(uv[strip])) * (1 - tt)[:, None]
            below = sd_ < -0.002
            pos[below, 1] = Xclosed[strip[below], 1]
            Xnew[strip] = pos
            Xnew[top] = Tgt
            extra[bv] = True
            extra[top] = True
            rep[pname] = {"crease_deg": round(math.degrees(al), 1), "fold_deg": round(math.degrees(ph), 1),
                          "top_edge_off_mm": round(float(np.linalg.norm(res, axis=1).max() * 1e3), 2)}
        self.reads["plackets"] = rep
        self.extra_held = extra
        return Xnew

    # ---- the whole build
    def stiff_last(self):
        """Every other edge and fold row of the stiff pieces, as chains, between the ones already fixed."""
        net, R = self.net, self.roles
        rs = net.root
        for p in [q for q in (R.band, R.fall) if q and (q != R.band or hasattr(self, "sb"))]:  # (F1: stages that ran)
            pid = net.pid(p)
            m = net.chain_piece == pid
            ids = net.link_of_chain[m]
            I, J, L = net.link_i[ids], net.link_j[ids], net.link_L[ids]
            fixed = np.zeros(net.n, bool)
            fixed[:] = True
            mv = np.unique(np.r_[I, J])
            base = rs[np.r_[self.sb, self.st]] if p == R.band else rs[np.r_[self.fall_ch["neck"], self.fall_ch["outer"], self.fall_ch["endL"], self.fall_ch["endR"]]]
            fixed[mv] = False
            fixed[base] = True
            self.X, rd = project(self.X, I, J, L, np.ones(len(I), bool), fixed, iters=20, step=0.004)
            self.X = self.X[rs]
            self.reads[f"{p}_edges"] = rd

    def stiff_stage(self):
        if self.roles.band is None:  # (F1: nothing on the neck: a fall needs its band, read_roles refuses that)
            return
        self.band_closed() if not hasattr(self, "sb") else self.band_open()
        self.fall_build()
        self.fill_band()
        self.fall_surface()
        self.stiff_last()

    def thread_read_all(self):
        self.reads["threads"] = self.thread_model.report(self.X)

    def _cloth_contact(self):
        """The soft cloth as built, outward side up: what a stiff leaf rests on."""
        net, R = self.net, self.roles
        F = net.F[~np.isin(net.piece[net.F[:, 0]], [net.pid(p) for p in ([R.band, R.fall] + list(R.rings)) if p])].copy()
        X = self.X
        fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
        bn = self.body.contact.query(X[F].mean(1))[1]
        flip = (fn * bn).sum(1) < 0
        F[flip] = F[flip][:, [0, 2, 1]]
        return Contact(X, F)

    def _rest_fall(self):
        """The stiff fall rests on the soft cloth built under it (its stand-off is the garment's ease, not the skin's): the
        fall is solved again on that, then the soft cloth again under the fall. Stiff first still: the band never moves."""
        if not self.roles.fall:
            return
        self.under_cloth = self._cloth_contact()
        self.fall_build()
        self.fall_surface()
        self.stiff_last()
        self.soft_net(start=self.X.copy())
