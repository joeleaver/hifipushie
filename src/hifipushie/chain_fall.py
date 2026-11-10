"""CHAIN FALL: stages 2 and 6 of the chain build on the neck (chain_garment.py's docstring is the spec): the FALL on the
held band (roll line, outer edge, ends), the stiff parts' surfaces between their fixed chains, and stiff_parts (band then
fall). Moved out of chain_garment.py as a mixin of Build (R3a, behaviour-preserving)."""
from __future__ import annotations

import math
import time

import numpy as np
from scipy.spatial import cKDTree

from . import chain_net as cn
from .chain_net import BendSolve, project, unit
from .chain_core import (FALL_GAP, GAP, LAYER, REST, ChainRefused, _keep_roots, _neighbours,
                         cn_vnormals)


class FallStages:
    """Build's stages 2 and 6, the fall and the stiff surfaces (mixed into chain_garment.Build)."""

    # ---- 2. the fall
    def _fall_chains(self):
        net, R = self.net, self.roles
        uv = net.uv
        neck = self.order_x(self.c2s)
        rows = [np.asarray(r, np.int64) for f, r in net.fold_rows() if f is R.fold or f.get("name") == R.fold.get("name")]
        roll = rows[0]
        roll = roll[net.piece[roll] == net.pid(R.fall)]
        roll = roll[np.argsort(uv[roll, 0])]
        lp = net.loop(R.fall)
        nset = set(int(v) for v in neck)
        m = np.array([int(v) in nset for v in lp])
        k = np.where(m)[0]
        gaps = np.diff(np.r_[k, k[0] + len(lp)])
        g = int(np.argmax(gaps))
        rest = np.roll(lp, -(int(k[g])))[: int(gaps[g]) + 1]  # neck end .. round the far side .. other neck end
        if uv[rest[0], 0] > uv[rest[-1], 0]:
            rest = rest[::-1]
        # the two points: the sharpest flat turns on that outline, one each side
        P = uv[rest]
        w = max(4, len(rest) // 60)
        a = unit(P[w:-w] - P[:-2 * w])
        b = unit(P[2 * w:] - P[w:-w])
        turn = np.abs(np.arctan2(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0], (a * b).sum(1)))
        mid = len(rest) // 2
        p1 = int(np.argmax(turn[: mid - w])) + w
        p2 = int(np.argmax(turn[mid - w:])) + mid
        end0, outer, end1 = rest[: p1 + 1], rest[p1: p2 + 1], rest[p2:]
        return neck, roll, outer, end0, end1[::-1]

    def fall_build(self):
        """The fall on the held band: chains + lines, little bending, resting on what is under it."""
        net, R = self.net, self.roles
        if R.fall is None:
            return
        uv, rs = net.uv, net.root
        neck, roll, outer, endL, endR = self._fall_chains()
        self.fall_ch = dict(neck=neck, roll=roll, outer=outer, endL=endL, endR=endR)
        nb, nt, ev, hgt, LB = self._band_lines
        c2s, sb, st = self.c2s, self.sb, self.st
        # the start: up the band to the roll line, then down outside it
        kt = cKDTree(uv[neck])
        T = self.X[rs[neck]]
        B = self.X[nb[cKDTree(uv[sb, :1]).query(uv[neck, :1])[1]]]
        tg = unit(np.gradient(T, axis=0))
        up = unit(T - B)
        up = unit(up - tg * (up * tg).sum(1, keepdims=True))
        yc = 0.5 * (self.body.p("cf_neck")[1] + self.body.p("cb_neck")[1])
        self.yc = yc
        out = np.cross(tg, up)
        out *= np.sign(out[:, 0] * T[:, 0] + out[:, 1] * (T[:, 1] - yc))[:, None]
        droll = np.median(kt.query(uv[roll])[0])
        self.droll = float(droll)
        cv = net.verts(R.fall)
        dv, jv = kt.query(uv[cv])
        fallang = math.radians(35)
        P = T[jv] + up[jv] * np.minimum(dv, droll)[:, None] + (np.maximum(dv - droll, 0))[:, None] * \
            (-up[jv] * math.cos(fallang) + out[jv] * math.sin(fallang)) + out[jv] * 0.004 * (dv > droll)[:, None]
        rootset = np.isin(rs[cv], rs[neck])
        self.X[rs[cv[~rootset]]] = P[~rootset]
        if self.wear["state"] == "open":
            pass  # (the leaves start from the band's own shape: the start above follows the open band)
        chains = dict(roll=roll, outer=outer, endL=endL, endR=endR)
        I, J, L, E = [], [], [], []
        for o in chains.values():
            I.append(rs[o[:-1]])
            J.append(rs[o[1:]])
            L.append(np.linalg.norm(np.diff(uv[o], axis=0), axis=1))
            E.append(np.ones(len(o) - 1, bool))
        # lines across: seam -> roll -> edge, every 15 points; full width where the fall lies flat at the back
        tr = unit(np.gradient(uv[roll], axis=0))

        def across(i, other):
            d = uv[other] - uv[roll[i]]
            return other[int(np.argmin(np.abs(d @ tr[i])))]
        hpsy = self.body.p("hps.L")[1]
        pairs, exact = [], []
        for i in range(0, len(roll), 15):
            # the leaf (roll -> outer edge) is stiff and lies open at its full cut width all round, in either wear: an
            # "at most" leaf folded narrow and the closed points stayed together at CF, standing off (C280, run 3). The
            # wrap over the band (neck -> roll) may shorten where it curves.
            for a, b, lf in ((across(i, neck), roll[i], False), (roll[i], across(i, outer), True)):
                pairs.append((a, b))
                exact.append(lf or (self.wear["state"] == "open" and bool(min(self.X[rs[a], 1], self.X[rs[b], 1]) > hpsy - 0.01)))
        mid = roll[int(np.argmin(np.abs(uv[roll, 0])))]
        for ec, oc in ((endL, 0), (endR, len(outer) - 1)):
            for k in (3, 6, 10, 15):  # each point keeps its cut corner
                a = ec[max(len(ec) - 1 - k, 0)]
                b = outer[min(max(oc + (k if oc == 0 else -k), 0), len(outer) - 1)]
                pairs.append((a, b))
                exact.append(False)
            re_ = roll[int(np.argmin(np.min(np.linalg.norm(uv[roll][:, None] - uv[ec][None], axis=2), axis=1)))]
            for ev2 in ec[np.linalg.norm(uv[ec] - uv[re_], axis=1) < 0.012]:
                if ev2 != re_:
                    pairs.append((re_, ev2))  # the roll line ends on the end edge
                    exact.append(True)
            corner = outer[oc]  # the point's triangle: rigid
            near_o = outer[np.linalg.norm(uv[outer] - uv[corner], axis=1) < 0.03]
            near_e = ec[np.linalg.norm(uv[ec] - uv[corner], axis=1) < 0.03]
            pts = np.unique(np.r_[near_o[::3], near_e[::3], corner])
            for a in range(len(pts)):
                for b in range(a + 1, len(pts)):
                    pairs.append((pts[a], pts[b]))
                    exact.append(True)
        pa = np.array(pairs)
        I.append(rs[pa[:, 0]])
        J.append(rs[pa[:, 1]])
        L.append(np.linalg.norm(uv[pa[:, 0]] - uv[pa[:, 1]], axis=1))
        E.append(np.array(exact))
        I, J, L, E = map(np.concatenate, (I, J, L, E))
        k = I != J
        I, J, L, E = I[k], J[k], L[k], E[k]
        free = np.setdiff1d(np.unique(np.r_[I, J]), rs[neck])
        S = BendSolve(self.X, free)
        S.add_links(I, J, L, E)
        for nm, o in chains.items():
            S.add_bend(rs[o], cn.BEND_BASE * net.bend[o[1:-1]])
        lie = rs[outer]
        S.add_contact(rs[np.r_[outer, roll]], self.body.contact, GAP)
        hy = hpsy - 0.01
        under = getattr(self, "under_cloth", None)  # the fall rests on what is under it: the body, then the cloth built there
        if under is None:
            S.add_contact(lie, self.body.contact, FALL_GAP, rest=REST)
        else:
            S.add_contact(lie, self.body.contact, FALL_GAP)
            S.add_contact(lie, under, LAYER, rest=REST)

        def outward(Y):  # outside faces out: the edge further from the neck axis than the roll
            a = rs[pa_o[:, 0]]
            b = rs[pa_o[:, 1]]
            Pa, Pb = Y[a] - [0, yc, 0], Y[b] - [0, yc, 0]
            ra, rb = np.linalg.norm(Pa[:, :2], axis=1), np.linalg.norm(Pb[:, :2], axis=1)
            d = rb - ra - 0.002
            bad = d < 0
            ga = np.c_[Pa[:, :2] / np.maximum(ra, 1e-9)[:, None], np.zeros(len(a))]
            gb = np.c_[Pb[:, :2] / np.maximum(rb, 1e-9)[:, None], np.zeros(len(a))]
            r = 10 * np.where(bad, d, 0.0)
            kk = np.arange(len(a))
            return r, np.r_[kk, kk], np.r_[a, b], np.r_[-ga * (10 * bad)[:, None], gb * (10 * bad)[:, None]]
        pa_o = np.array([(roll[i], across(i, outer)) for i in range(0, len(roll), 15)])
        S.add_fn(outward)
        rows = []
        pos = free[self.net.uv[free, 0] > 0.002]
        neg = free[self.net.uv[free, 0] < -0.002]
        if len(pos) and len(neg):
            mj = cKDTree(uv[neg] * [-1, 1]).query(uv[pos])[1]
            for a, j in zip(pos, mj):
                rows += [([a, neg[j]], [1.0, 1.0], 0, 0.0, 1.0), ([a, neg[j]], [1.0, -1.0], 1, 0.0, 1.0), ([a, neg[j]], [1.0, -1.0], 2, 0.0, 1.0)]
        if self.wear["state"] == "open":
            nbody = self.body.V
            zc = self.X[rs[st[len(st) // 2]], 2]
            nb_ = nbody[(np.abs(nbody[:, 2] - (zc - 0.02)) < 0.004) & (np.abs(nbody[:, 0]) < 0.1) & (nbody[:, 1] > yc - 0.1) & (nbody[:, 1] < yc + 0.1)]
            neckW = 2 * float(np.abs(nb_[:, 0]).max())
            ptx = float(self.wear["spread_mm"]) / 2000 if self.wear.get("spread_mm") else float(self.wear["spread"]) * neckW / 2
            self.reads["open_target_mm"] = round(2 * ptx * 1e3, 1)
            for ec in (endL, endR):
                p = rs[ec[-1]]
                s = np.sign(self.X[p, 0]) or 1.0
                if p in free:
                    rows.append(([p], [1.0], 0, s * ptx, 3.0))
        S.add_linear(rows)
        self.X = S.solve(60)
        held = np.ones(net.n, bool)
        held[free] = False
        fl = [(self.body.contact, free, GAP)]  # (lengths first: the rest on the cloth is the light pull above)
        Xn, rd = project(self.X, I, J, L, E, held, fl, iters=80, step=0.004)
        self.X = Xn
        self.fall_links = (I, J, L, E)
        l = np.linalg.norm(Xn[I] - Xn[J], axis=1) / np.maximum(L, 1e-9) - 1
        self.reads["fall"] = {"worst_chain_pct": round(float(np.abs(l[E]).max() * 100), 3), "worst_line_over_pct": round(float(max(l.max(), 0) * 100), 3),
                              "project": rd, "points_mm": [round(float(self.X[rs[e[-1]], c] * 1e3), 1) for e in (endL, endR) for c in (0, 1, 2)]}

    # ---- 6. surfaces of the stiff parts (between their fixed chains)
    def fill_band(self):
        net, R = self.net, self.roles
        rs = net.root
        if R.band is None or not hasattr(self, "sb"):  # (F1: only after the band stage ran)
            return
        for piece, known_v in ((R.band, np.r_[self.sb, self.st, getattr(self, "se", np.zeros(0, np.int64))].astype(np.int64)),):
            F = net.F[np.all(net.piece[net.F] == net.pid(piece), axis=1)]
            known = np.zeros(net.n, bool)
            known[known_v] = True
            ids = np.unique(F)
            Y = self.X.copy()
            Y[known_v] = self.X[rs[known_v]]
            Y[ids[~known[ids]]] = 0.0
            ref = np.zeros_like(Y)
            self.X = _keep_roots(self.net, cn.fill(ref, Y, known, net.uv, F, ids))

    def fall_surface(self):
        """The fall between its chains: the turn round the band top is a half circle of the pattern's radius; the rest a
        smooth fill; the fall stays a layer outside the band; a corner patch at the leaf's neck end."""
        net, R = self.net, self.roles
        if R.fall is None:  # (F1: no fall, no surface)
            return
        uv, rs = net.uv, net.root
        X = self.X
        ch = self.fall_ch
        neck, roll = ch["neck"], ch["roll"]
        r_t = float(self.pat.fold_radius.get(R.fold.get("name"), self.pat.fold_radius.get(R.fall, 0.0)))
        if r_t <= 0:
            raise ChainRefused(f"{R.fall} roll: no radius in the pattern's fold entry. next: give the fold a radius (design_garment)")
        S_ = X[rs[neck]]
        Bb = X[rs[self.sb[cKDTree(uv[self.sb, :1]).query(uv[neck, :1])[1]]]]
        n_ = len(S_)
        i_ = np.arange(n_)
        tg = unit(S_[np.clip(i_ + 5, 0, n_ - 1)] - S_[np.clip(i_ - 5, 0, n_ - 1)])
        up = S_ - Bb
        up = unit(up - tg * (up * tg).sum(1, keepdims=True))
        nn = np.cross(tg, up)
        nn *= np.sign(nn[:, 0] * S_[:, 0] + nn[:, 1] * (S_[:, 1] - self.yc))[:, None]
        kn2 = cKDTree(uv[neck])
        t_roll = float(np.median(kn2.query(uv[roll])[0]))
        L1 = max(t_roll - np.pi * r_t / 2, 0.0005)
        t_end = L1 + np.pi * r_t
        E2 = uv[neck]
        ea, eb = E2[:-1], E2[1:]
        cvs = net.verts(R.fall)
        vv = eb - ea

        def proj(p2):
            w_ = p2 - ea
            f0 = (w_ * vv).sum(1) / (vv * vv).sum(1)
            f = np.clip(f0, 0, 1)
            q = ea + vv * f[:, None]
            k = int(np.argmin(np.linalg.norm(p2 - q, axis=1)))
            over = 0.0
            if k == 0 and f0[0] < 0:
                over = f0[0] * np.linalg.norm(vv[0])
            if k == len(ea) - 1 and f0[k] > 1:
                over = (f0[k] - 1) * np.linalg.norm(vv[k])
            nrm = np.array([-vv[k, 1], vv[k, 0]]) / np.linalg.norm(vv[k])
            return k, f[k], over, abs((p2 - (ea[k] + vv[k] * f0[k])) @ nrm)
        fixed = set(int(v) for k_ in ("neck", "roll", "outer", "endL", "endR") for v in ch[k_])
        lerp = lambda A_, k, f: A_[k] * (1 - f) + A_[k + 1] * f
        ns = set(int(v) for v in np.r_[neck, ch["endL"], ch["endR"], ch["outer"]])  # (the chains stand; the turn fills between)
        for v in cvs:
            if int(v) in ns:
                continue
            k, f, over, tt = proj(uv[v])
            if tt > t_end:
                continue
            Sv = lerp(S_, k, f)
            tv = unit(lerp(tg, k, f))
            uu = unit(lerp(up, k, f))
            nv = unit(lerp(nn, k, f))
            Sv = Sv + tv * over
            if tt <= L1:
                X[v] = Sv + uu * tt + nv * 0.0003
            else:
                ph = (tt - L1) / r_t
                C_ = Sv + uu * L1 + nv * (r_t + 0.0003)
                X[v] = C_ - nv * r_t * np.cos(ph) + uu * r_t * np.sin(ph)
            fixed.add(int(v))
        for v in roll:
            fixed.add(int(v))
        F = net.F[np.all(net.piece[net.F] == net.pid(R.fall), axis=1)]
        known = np.zeros(net.n, bool)
        known[list(fixed)] = True
        known_ids = np.array(sorted(fixed))
        Y = X.copy()
        Y[known_ids[np.isin(known_ids, neck)]] = X[rs[known_ids[np.isin(known_ids, neck)]]]
        ids = np.unique(F)
        Yr = cn.fill(np.zeros_like(Y), Y, known, uv, F, ids)
        X[ids] = Yr[ids]
        # the fall stays a layer outside the band
        band_F = net.F[np.all(net.piece[net.F] == net.pid(R.band), axis=1)]
        sv = np.unique(band_F)
        kd = cKDTree(X[sv])
        VN = cn_vnormals(X, band_F)
        cen = np.array([0, self.yc, 0])
        VN[sv] *= np.sign(((X[sv] - cen)[:, :2] * VN[sv][:, :2]).sum(1))[:, None]
        cv = np.array([v for v in cvs if int(v) not in fixed])
        nbr = _neighbours(F)
        for it in range(30):
            dd, j = kd.query(X[cv])
            q, nq = X[sv[j]], VN[sv[j]]
            sd = ((X[cv] - q) * nq).sum(1)
            push = (sd < 0.0015) & (dd < 0.01)
            X[cv[push]] += 0.5 * nq[push] * (0.0015 - sd[push])[:, None]
            Xn = X.copy()
            for v in cv:
                Xn[v] = 0.5 * X[v] + 0.5 * X[nbr[int(v)]].mean(0)
            X[cv] = Xn[cv]
        # the band stays under the fall where they overlap (its tab past the collar's end)
        VNc = cn_vnormals(X, F)
        cvv = np.unique(F)
        VNc[cvv] *= np.sign(((X[cvv] - cen)[:, :2] * VNc[cvv][:, :2]).sum(1))[:, None]
        fall = cvv[kn2.query(uv[cvv])[0] > 0.008]
        fixed_b = set(int(v) for v in np.r_[self.sb, self.st])
        svb = np.array([v for v in sv if int(v) not in fixed_b])
        nbB = _neighbours(band_F)
        for it in range(30):
            kf = cKDTree(X[fall])
            dd, j = kf.query(X[svb])
            q, n2 = X[fall[j]], VNc[fall[j]]
            sd = ((X[svb] - q) * n2).sum(1)
            bad = (sd > -0.0008) & (dd < 0.008)
            X[svb[bad]] -= 0.6 * n2[bad] * (sd[bad] + 0.0008)[:, None]
            Xn = X.copy()
            for v in svb:
                Xn[v] = 0.6 * X[v] + 0.4 * X[nbB[int(v)]].mean(0)
            X[svb] = Xn[svb]
        self.X = _keep_roots(net, X)

    def stiff_parts(self):
        """Stages 1-2 (+ open): the band and its fall, chains then surfaces."""
        t0 = time.time()
        self.band_closed()
        self.reads["closed_band_s"] = round(time.time() - t0, 1)
        self.closed_stiff = None
        if self.roles.band is None:
            return
        if self.wear["state"] == "open":
            self.band_open()
        self.fall_build()
        self.fill_band()
        self.fall_surface()
        self.reads["stiff_s"] = round(time.time() - t0, 1)
