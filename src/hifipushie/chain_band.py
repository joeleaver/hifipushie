"""CHAIN BAND: stage 1 of the chain build (chain_garment.py's docstring is the spec): the collar BAND, its pressed ring
resting on the high points, tied on its own button or untied (the sewn front limited from the topmost tied front pair).
Moved out of chain_garment.py as a mixin of Build (R3a, behaviour-preserving); Build and GarmentBuild stay in chain_garment."""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

from . import chain_net as cn
from .chain_net import BendSolve, project, unit
from .chain_core import (GAP, LAYER, REST, ChainRefused, hand_of)


class BandStages:
    """Build's stage 1, the band (mixed into chain_garment.Build)."""

    # ---- 1. the band
    def _neck_ring(self, C: float):
        """The closed neckline's start from the body: an ellipse through the neck's own landmarks, tilted CB -> CF, of
        perimeter C (the band's length between its button and buttonhole)."""
        b = self.body
        cb, cf, hps = b.p("cb_neck"), b.p("cf_neck"), b.p("hps.L")
        a0, b0 = abs(hps[0]), (cb[1] - cf[1]) / 2
        yc = (cb[1] + cf[1]) / 2
        per = math.pi * (3 * (a0 + b0) - math.sqrt((3 * a0 + b0) * (a0 + 3 * b0)))
        k = C / per
        return a0 * k, b0 * k, yc, (cb[2] + cf[2]) / 2, (cb[2] - cf[2]) / 2

    def band_closed(self):
        net, R = self.net, self.roles
        if R.band is None:
            return
        if R.band_closure is None:
            raise ChainRefused(f"{R.band}: no closure on the band; next: add its button to the pattern (design_garment)")
        uv = net.uv
        soft_sewn = set()
        for p in R.panels:
            soft_sewn |= set(self.sewn_with(R.band, p))
        c2s = self.sewn_with(R.fall, R.band)
        sb, st = self.order_x(soft_sewn), self.order_x(c2s.values())
        self.sb, self.st, self.c2s = sb, st, c2s
        # which end of the band goes to which side: the seam to a ".L" piece tells
        left = [p for p in R.panels if hand_of(p) > 0]
        su = np.sign(np.mean([uv[v, 0] for v in self.sewn_with(R.band, left[0])])) if left else 1.0
        self.band_su = su
        cl = R.band_closure["v"][0]
        xb = sorted(uv[cl, 0])
        LB = np.linalg.norm(np.diff(uv[sb], axis=0), axis=1)
        sB = np.r_[0, np.cumsum(LB)]
        mid = int(np.argmin(np.abs(uv[sb, 0] - 0.5 * (xb[0] + xb[1]))))
        i0, i1 = int(np.argmin(np.abs(uv[sb, 0] - xb[0]))), int(np.argmin(np.abs(uv[sb, 0] - xb[1])))
        C = sB[i1] - sB[i0]
        a, b, yc, zc, dz = self._neck_ring(C)
        th = (sB - sB[mid]) / C * 2 * np.pi * su  # 0 = centre back, + = towards worn +X
        hz = self.body.p("hps.L")[2]
        B = np.c_[a * np.sin(th), yc + b * np.cos(th), zc + dz * np.cos(th) + (hz - zc) * np.sin(th) ** 2]
        from .chain_rest import rest_ring
        side = B[np.argmax(B[:, 0])]  # it rests on the high points: it may drop and tip front-down about the side necks (C280)
        B, self.reads["band_rest"] = rest_ring(B, self.body.contact, GAP, np.array([0.0, side[1], side[2]]))
        kb = cKDTree(uv[sb, :1])
        cross = np.array([(j, int(kb.query(uv[v, :1])[1])) for j, v in enumerate(st)])
        hgt = np.linalg.norm(uv[st] - uv[sb[cross[:, 1]]], axis=1)
        for phi in np.radians(np.arange(0, 41, 2.5)):  # the band leans with the neck: the least tilt forward that clears it
            T = B[cross[:, 1]] + np.array([0.0, -math.sin(phi), math.cos(phi)]) * hgt[:, None]
            if self.body.contact.query(T)[0].min() >= GAP:
                break
        self.X[net.root[sb]] = B
        self.X[net.root[st]] = T
        self.X[net.root[R.band_closure["v"][0][0]]] = B[i1]
        rs = net.root
        nb, nt = rs[sb], rs[st]
        free = np.unique(np.r_[nb, nt])
        cbn = rs[sb[mid]]
        free = free[free != cbn]
        S = BendSolve(self.X, free)
        S.add_links(nb[:-1], nb[1:], LB, np.ones(len(LB), bool))
        S.add_links(nt[:-1], nt[1:], np.linalg.norm(np.diff(uv[st], axis=0), axis=1), np.ones(len(st) - 1, bool))
        ev = cross[::4]
        S.add_links(nt[ev[:, 0]], nb[ev[:, 1]], hgt[ev[:, 0]], np.ones(len(ev), bool))
        wb, wt = cn.BEND_BASE * net.bend[sb[1:-1]], cn.BEND_BASE * net.bend[st[1:-1]]
        S.add_bend(nb, wb)
        S.add_bend(nt, wt)
        S.add_contact(nt, self.body.contact, GAP)
        S.add_contact(nb, self.body.contact, GAP, rest=REST)
        # closed on its own button: bottom and top at the button x lie on the centre line, the two ends one over the other
        rows = []
        for ch, chain in ((sb, nb), (st, nt)):
            ja, jb = int(np.argmin(np.abs(uv[ch, 0] - xb[0]))), int(np.argmin(np.abs(uv[ch, 0] - xb[1])))
            rows += [([chain[ja]], [1.0], 0, 0.0, cn.HARD), ([chain[jb]], [1.0], 0, 0.0, cn.HARD),
                     ([chain[ja], chain[jb]], [1.0, -1.0], 1, 0.0, cn.HARD), ([chain[ja], chain[jb]], [1.0, -1.0], 2, 0.0, cn.HARD)]
        # worn straight: mirror symmetric (back to the button x; the tabs past it are the lap)
        for ch, chain in ((sb, nb), (st, nt)):
            kk = cKDTree(uv[ch, :1] * [-1])
            mj = kk.query(uv[ch, :1] - 2 * np.mean(xb))[1]
            for q in range(len(ch)):
                if q < mj[q] and xb[0] < uv[ch[q], 0] < xb[1]:
                    rows += [([chain[q], chain[mj[q]]], [1.0, 1.0], 0, 0.0, 1.0), ([chain[q], chain[mj[q]]], [1.0, -1.0], 1, 0.0, 1.0),
                             ([chain[q], chain[mj[q]]], [1.0, -1.0], 2, 0.0, 1.0)]
        S.add_linear(rows)

        def upright(Y):  # the band stays upright: its top above its bottom
            d = Y[nt[ev[:, 0]], 2] - Y[nb[ev[:, 1]], 2] - 0.012
            bad = d < 0
            m = len(ev)
            r = 10 * np.where(bad, d, 0.0)
            g = np.zeros((m, 3))
            g[:, 2] = 10.0 * bad
            k = np.arange(m)
            return np.r_[r], np.r_[k, k], np.r_[nt[ev[:, 0]], nb[ev[:, 1]]], np.r_[g, -g]
        S.add_fn(upright)
        self.X = S.solve(60)
        self._band_lines = (nb, nt, ev, hgt, LB)
        self._band_project(held=np.isin(np.arange(net.n), [cbn]))
        self.reads["band"] = self._band_read()

    def _band_project(self, held, extra_limit=None):
        net = self.net
        nb, nt, ev, hgt, LB = self._band_lines
        Lt = np.linalg.norm(np.diff(net.uv[self.st], axis=0), axis=1)
        I = np.r_[nb[:-1], nt[:-1], nt[ev[:, 0]]]
        J = np.r_[nb[1:], nt[1:], nb[ev[:, 1]]]
        L = np.r_[LB, Lt, hgt[ev[:, 0]]]
        if getattr(self, "_end_links", None) is not None:  # (F3: a stand's end edges, chains_roles.stand_ring)
            I, J, L = (np.r_[a, b] for a, b in zip((I, J, L), self._end_links))
        Xn, rd = project(self.X, I, J, L, np.ones(len(L), bool), held, [(self.body.contact, np.r_[nb, nt], GAP)],
                         limit=extra_limit)
        self.X = Xn
        return rd

    def _band_read(self):
        nb, nt, ev, hgt, LB = self._band_lines
        l = np.linalg.norm(np.diff(self.X[nb], axis=0), axis=1)
        sd, _ = self.body.contact.query(self.X[np.r_[nb, nt]])
        return {"neckline_mm": round(float(l.sum() * 1e3), 1), "cut_mm": round(float(LB.sum() * 1e3), 1),
                "worst_link_pct": round(float(np.abs(l / LB - 1).max() * 100), 3), "min_gap_mm": round(float(sd.min() * 1e3), 2)}

    def hold_start(self, hold):
        """Where the topmost TIED front pair starts, before any soft cloth: its cut distance below the front's neck point
        (sewn to the band, already built), down the body's centre front, a gap and a layer off it. (cf_shirt: the closed
        build's button sat 90 mm (cut) below the neck point; the torso-ring start put it 39 mm lower and 20 mm forward,
        and the band opened against it stretched its links 9x.) Was chain_plan.button_start (the first fastened button)."""
        net, R = self.net, self.roles
        p = R.front["over"]
        bvp = hold[0] if net.piece[hold[0]] == net.pid(p) else hold[1]
        sew = list(self.sewn_with(p, R.band))
        L = np.linalg.norm(net.uv[sew] - net.uv[bvp], axis=1)
        top = self.X[net.root[sew[int(np.argmin(L))]]].copy()
        ys = np.arange(top[1] - 0.15, top[1] + 0.15, 0.001)
        for z in np.arange(top[2], top[2] - 3 * L.min(), -0.002):
            P = np.c_[np.zeros(len(ys)), ys, np.full(len(ys), z)]
            near = np.where(self.body.contact.query(P)[0] <= GAP + LAYER)[0]  # the front surface: first point from the front
            if not len(near):
                continue
            q = P[near[0]]
            if np.linalg.norm(q - top) >= L.min():
                return q
        return np.array([0.0, top[1], top[2] - L.min()])

    def band_untied(self):
        """The band's own closure left undone: its pressed ring (band_closed, its rest shape) opened (band_open). The
        sewn fronts are held to the topmost TIED front pair (started where hold_start puts it: nothing soft is built yet);
        with no front pair tied nothing holds them, their edges are free (C399)."""
        from .chain_plan import first_tied
        hold = first_tied(self.roles.front, self.net.uv)
        self.band_hold = hold
        if hold is not None:
            self.X[self.net.root[hold[0]]] = self.X[self.net.root[hold[1]]] = self.hold_start(hold)
            self.reads["button_start_mm"] = [round(float(c) * 1e3, 1) for c in self.X[self.net.root[hold[0]]]]
        self.band_open(hold)

    def band_open(self, hold=None):
        """The stiff band's own shape unbuttoned: pressed curve kept round the back (sewn to the back piece, held),
        relaxed straight past the side necks, started swung open; the sewn front limited by its cut distance to the
        topmost tied front pair (hold); none tied: not limited."""
        from scipy.spatial.transform import Rotation as Rot
        net, R = self.net, self.roles
        uv, rs = net.uv, net.root
        sb, st = self.sb, self.st
        nb, nt, ev, hgt, LB = self._band_lines
        # side necks: the band's ends of its seam to the back panels (those sewn to a piece worn across the back)
        backs = [p for p in R.panels if hand_of(p) == 0 and self.sewn_with(R.band, p)]
        bv = [v for p in backs for v in self.sewn_with(R.band, p)]
        hu = float(np.max(np.abs(uv[bv, 0] - np.mean(uv[sb, 0]))))
        cx = float(np.mean(uv[sb, 0]))
        self.hinge_u, self.band_cx = hu, cx
        fB = np.abs(uv[sb, 0] - cx) > hu
        B0, T0 = self.X[nb].copy(), self.X[nt].copy()
        self.closed_band = (B0, T0)
        Bg, Tg = B0.copy(), T0.copy()
        swing = math.radians(55)
        k0 = int(np.argmin(np.abs(uv[sb, 0] - (cx - hu)))), int(np.argmin(np.abs(uv[sb, 0] - (cx + hu))))
        kt = [int(np.argmin(np.abs(uv[st, 0] - uv[sb[k], 0]))) for k in k0]
        ramp = 0.12
        for sgn, kbi, kti in ((-1, k0[0], kt[0]), (1, k0[1], kt[1])):
            hb, ht = B0[kbi], T0[kti]
            ax = unit(ht - hb)
            own = np.sign(hb[0])
            for C, order in ((Bg, sb), (Tg, st)):
                s = np.sign(uv[order, 0] - cx) == sgn
                d = np.abs(uv[order, 0] - cx)
                sel = s & (d > hu)
                w = np.clip((d[sel] - hu) / ramp, 0, 1)
                w = w * w * (3 - 2 * w)
                test = Rot.from_rotvec(ax * swing).apply(C[sel][-1 if sgn > 0 else 0] - hb)[0] + hb[0] - C[sel][-1 if sgn > 0 else 0][0]
                ang = swing if test * own > 0 else -swing
                C[sel] = hb + np.array([Rot.from_rotvec(ax * ang * q).apply(c - hb) for c, q in zip(C[sel], w)])
        self.X[nb] = Bg
        self.X[nt] = Tg
        # the topmost tied front pair: the fronts stay closed there (none tied: nothing holds them, C399)
        cl = R.front
        bvs = hold
        limit = []
        if hold is not None:
            self.button = bvs
            bpos = self._button_centre()
            self.button_pos = bpos
        for p in ((cl["over"], cl["under"]) if hold is not None else ()):
            sew_ = self.sewn_with(p, R.band)
            for fv, sv in sew_.items():
                L = float(np.linalg.norm(uv[fv] - uv[bvs[0] if net.piece[bvs[0]] == net.pid(p) else bvs[1]]))
                if L < 0.25:  # (the whole neck edge sewn to this front)
                    limit.append((int(rs[sv]), bpos, L))
        self._open_limit = limit
        free = np.unique(np.r_[nb[fB], nt])
        S = BendSolve(self.X, free)
        S.add_links(nb[:-1], nb[1:], LB, np.ones(len(LB), bool))
        Lt = np.linalg.norm(np.diff(uv[st], axis=0), axis=1)
        S.add_links(nt[:-1], nt[1:], Lt, np.ones(len(Lt), bool))
        S.add_links(nt[ev[:, 0]], nb[ev[:, 1]], hgt[ev[:, 0]], np.ones(len(ev), bool))

        def front_w(u):
            w = np.clip((np.abs(u - cx) - hu) / 0.03, 0, 1)
            return w * w * (3 - 2 * w)
        for ch, C0, node in ((sb, B0, nb), (st, T0, nt)):
            k0_ = C0[2:] - 2 * C0[1:-1] + C0[:-2]
            rest = k0_ * (1 - front_w(uv[ch[1:-1], 0]))[:, None]  # the pressed curve relaxes past the side neck
            S.add_bend(node, cn.BEND_BASE * net.bend[ch[1:-1]], rest=rest)
        S.add_contact(np.r_[nb[fB], nt], self.body.contact, GAP)
        rows = []
        for ch, chain in ((sb, nb), (st, nt)):
            mj = cKDTree((uv[ch, :1] - cx) * [-1]).query(uv[ch, :1] - cx)[1]
            for q in range(len(ch)):
                if q < mj[q]:
                    rows += [([chain[q], chain[mj[q]]], [1.0, 1.0], 0, 0.0, 1.0), ([chain[q], chain[mj[q]]], [1.0, -1.0], 1, 0.0, 1.0),
                             ([chain[q], chain[mj[q]]], [1.0, -1.0], 2, 0.0, 1.0)]
        S.add_linear(rows)
        lim_id = np.array([k for k, _, _ in limit], np.int64)
        lim_L = np.array([L for _, _, L in limit])

        def tied(Y):  # the sewn front: at most its cut distance from the button
            d = Y[lim_id] - bpos
            l = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
            bad = l > lim_L
            return cn.HARD * np.where(bad, l - lim_L, 0.0), np.arange(len(l)), lim_id, (d / l[:, None]) * (cn.HARD * bad)[:, None]
        if limit:
            S.add_fn(tied)
        self.X = S.solve(60)
        held = np.ones(net.n, bool)
        held[free] = False
        rd = self._band_project(held, extra_limit=limit or None)
        self.reads["band_open"] = {**self._band_read(), "limit_over_mm": rd["limit_mm"],
                                   "ends_apart_mm": round(float(np.linalg.norm(self.X[nt[0]] - self.X[nt[-1]]) * 1e3), 1),
                                   "limited_points": len(limit)}

    def _button_centre(self):
        """Where the first fastened button sits (from the chain build, on the centre line)."""
        a, b = self.button
        p = 0.5 * (self.X[self.net.root[a]] + self.X[self.net.root[b]])
        p[0] = 0.0
        return p
