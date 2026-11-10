"""CHAIN SOFT: stages 3 and 4 of the chain build (chain_garment.py's docstring is the spec): the stiff RINGS and the SOFT
NETWORK (panels on garment-sized torso rings, tubes on the limb's axis), the block-in start (F10), TorsoRings and LimbAxis.
Moved out of chain_garment.py as a mixin of GarmentBuild (R3a, behaviour-preserving)."""
from __future__ import annotations

import math
import os

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

from . import chain_net as cn
from .chain_net import Contact, Threads, project, unit
from .chain_core import (CAP, GAP, LAYER, RING_GAP, SHEAR_LIMIT, UNDER, Body, ChainRefused, hand_of, zozo_legal)


def uses_blockin_start(build) -> bool:
    """(F10, C333) The block-in start is the default whenever the plan's style has a blockin; env HIFIPUSHIE_BLOCKIN_START=0
    turns it off (a comparison run)."""
    return getattr(build, "blockin", None) is not None and os.environ.get("HIFIPUSHIE_BLOCKIN_START", "1") != "0"


def blockin_of(build):
    """(F10) The build's step-2 block-in, built once per build (the ring's height and the start read the same one)."""
    if getattr(build, "_blockin_built", None) is None:
        from .garment_blockin import build as _bbuild
        build._blockin_built = _bbuild(build.blockin, build.body)
    return build._blockin_built


class TorsoRings:
    """Garment-sized rings per height: the torso's convex section (arms left out, so hollows are bridged), offset until
    its perimeter is the pattern's own width at that height. index 0 = centre front, going towards +X."""
    DZ, NS = 0.01, 720

    def __init__(self, body: Body, width_of, gap: float):
        V, at = body.V, body.at
        self.hz = float(body.p("hps.L")[2])
        self.z0 = float(at["crotch_z"]) - 0.2
        sx = abs(float(body.p("shoulder.L")[0]))
        self.armpit = float(at["armpit_z"])
        zs = np.arange(self.z0, self.hz + 0.03, self.DZ)
        hulls, t = [], []
        last = None
        tpit = None
        for z in zs[::-1] * 0 + zs:  # bottom up
            # (arms left out: they leave the torso downwards at an angle; the hands hang wide of the hips)
            lim = sx if z >= self.armpit + 0.03 else min(0.83 * sx + max(self.armpit - 0.03 - z, 0.0) * 0.4, 1.25 * sx)
            s = V[(np.abs(V[:, 2] - z) < 0.012) & (np.abs(V[:, 0]) < lim), :2]
            if len(s) >= 6:
                s = np.r_[s, s * [-1, 1]]
                h = s[ConvexHull(s).vertices]
                last = h
            hulls.append(last)
            need = width_of(z - self.hz)
            per = float(np.linalg.norm(np.diff(np.r_[last, last[:1]], axis=0), axis=1).sum()) if last is not None else 0.0
            tk = (need - per) / (2 * math.pi) if need else None
            if z <= self.armpit and tk is not None:
                tpit = tk
            t.append(max(gap + 0.002, tk if (z <= self.armpit and tk is not None) else (tpit if tpit is not None else gap + 0.002)))
        first = next(h for h in hulls if h is not None)
        hulls = [first if h is None else h for h in hulls]
        self.t = np.array(t)
        from scipy.ndimage import gaussian_filter1d
        self.t = gaussian_filter1d(self.t, 3, mode="nearest")
        self.R, self.P = [], []
        for h, tt in zip(hulls, self.t):
            e = np.diff(np.r_[h[-1:], h, h[:1]], axis=0)
            n = unit(np.c_[e[:, 1], -e[:, 0]])
            nv = unit(n[:-1] + n[1:])
            Q = h + nv * tt
            Q = np.r_[Q, Q[:1]]
            s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
            q = np.linspace(0, s[-1], self.NS, endpoint=False)
            P = np.c_[np.interp(q, s, Q[:, 0]), np.interp(q, s, Q[:, 1])]
            cy = P[:, 1].mean()
            k = int(np.argmin(np.abs(P[:, 0]) + 10 * (P[:, 1] > cy)))
            self.R.append(np.roll(P, -k, axis=0))
            self.P.append(float(s[-1]))
        self.R, self.P = np.array(self.R), np.array(self.P)

    def at_x(self, x, z, back: bool):
        """Point on the front (or back) half of the ring at height z whose X is x (above the armpit the cloth runs flat
        across the chest and back to the armhole; arc length would carry it round the side)."""
        z = np.clip(np.asarray(z, float), self.z0, self.z0 + self.DZ * (len(self.R) - 1.001))
        fk = (z - self.z0) / self.DZ
        k = fk.astype(int)
        out = np.zeros((len(z), 3))
        out[:, 2] = z
        for ki in np.unique(np.r_[k, k + 1]):
            Rg = self.R[ki]
            n = self.NS // 2
            half = Rg[: n + 1]  # centre front -> +X side -> centre back
            top = int(np.argmax(half[:, 0]))
            hx, hy = (half[top:, 0], half[top:, 1]) if back else (half[: top + 1, 0], half[: top + 1, 1])
            o = np.argsort(hx)
            for m_, wgt in ((k == ki, 1 - (fk - k)), (k + 1 == ki, fk - k)):
                if m_.any():
                    ax_ = np.abs(np.asarray(x, float)[m_])
                    out[m_, 0] += wgt[m_] * np.sign(np.asarray(x, float)[m_]) * np.minimum(ax_, hx[o][-1])
                    out[m_, 1] += wgt[m_] * np.interp(ax_, hx[o], hy[o])
        return out

    def at(self, s, z, half_back=None):
        """Point(s) at arc s from centre front (+ towards +X); half_back: s counted from centre back instead (s = x)."""
        z = np.clip(np.asarray(z, float), self.z0, self.z0 + self.DZ * (len(self.R) - 1.001))
        fk = (z - self.z0) / self.DZ
        k = fk.astype(int)
        f = (fk - k)[:, None]

        def on(ki):
            per = self.P[ki]
            sv = np.asarray(s, float) if half_back is None else per / 2 - np.asarray(s, float)
            a = (sv / per % 1.0) * self.NS
            i = a.astype(int) % self.NS
            g = (a - np.floor(a))[:, None]
            return self.R[ki, i] * (1 - g) + self.R[ki, (i + 1) % self.NS] * g
        xy = on(k) * (1 - f) + on(k + 1) * f
        return np.c_[xy, z]


class LimbAxis:
    """A limb's smooth axis from the body's shoulder, elbow and wrist, with a frame: o (outer side), f (front side)."""

    def __init__(self, body: Body, side: float):
        from scipy.ndimage import gaussian_filter1d
        m = np.array([side, 1, 1])
        S, E, W = body.p("shoulder.L") * m, body.p("elbow.L") * m, body.p("wrist.L") * m
        # (the landmark is the shoulder's surface; the axis runs inside the arm, its radius under it)
        S = S - side * unit(np.cross(unit(E - S), [0, 1.0, 0])) * 0.2 * abs(S[0])
        d = unit(W - E)
        P = np.array([S - unit(E - S) * 0.15, S, E, W, W + d * 0.2])
        s0 = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        q = np.arange(0, s0[-1], 0.002)
        C = np.column_stack([np.interp(q, s0, P[:, k]) for k in range(3)])
        C = gaussian_filter1d(C, 18, axis=0, mode="nearest")
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
        # s measured from the shoulder point
        self.s = s - s[int(np.argmin(np.linalg.norm(C - S, axis=1)))]
        self.C = C
        self.d = unit(np.gradient(C, axis=0))
        self.o = side * unit(np.cross(self.d, [0, 1.0, 0]))
        f = unit(np.cross(self.o, self.d))
        self.f = f * np.sign(-(f[:, 1]).mean())
        self.wrist = float(self.s[int(np.argmin(np.linalg.norm(C - W, axis=1)))])

    def at(self, s):
        s = np.asarray(s, float)
        g = lambda A: np.column_stack([np.interp(s, self.s, A[:, k]) for k in range(3)])
        return g(self.C), unit(g(self.o)), unit(g(self.f)), unit(g(self.d))


class SoftStages:
    """GarmentBuild's rings and soft network (mixed into chain_garment.GarmentBuild)."""

    # ---- which cloth
    def _stiff_mask(self):
        net, R = self.net, self.roles
        whole = [p for p in (R.band, R.fall) if p] + list(R.rings)
        if R.holds is not None:  # (R3b: a stiff host's plies are held with it; a floating layer is never moved)
            whole += [p for p, h in R.holds.plies.items() if h in whole] + list(R.holds.layers)
        m = np.isin(net.piece, [net.pid(p) for p in whole])
        return m

    def _front_panels(self):
        R = self.roles
        return [p for p in (R.front or {}).values() if isinstance(p, str) and p in R.panels] if R.front else []

    def _width_of(self):
        """The garment's whole width at a flat height y (below the armhole): twice (front half + back half)."""
        net, R = self.net, self.roles
        uv = net.uv
        fr = [p for p in R.panels if hand_of(p) > 0 and (not R.front or p in (R.front["over"], R.front["under"]))]
        bk = [p for p in R.panels if hand_of(p) == 0 or (hand_of(p) > 0 and R.front and p not in (R.front["over"], R.front["under"]))]  # (a back cut in halves from CB: its .L half)

        def w(y):
            out = 0.0
            for group in (fr, bk):
                best = 0.0
                for p in group:
                    v = net.verts(p)
                    s = v[np.abs(uv[v, 1] - y) < 0.012]
                    if len(s):
                        best = max(best, float(np.abs(uv[s, 0]).max()))
                out += best
            return 2 * out
        return w

    # ---- 3. rings
    def rings(self, only=None):
        """Each stiff ring resting on the body (all of R.rings, or `only` these): round the limb its tube goes round, or
        round the body (chain_loops.body_ring)."""
        net, R = self.net, self.roles
        if not hasattr(self, "axes"):
            self.axes = {}
        self.reads.setdefault("rings", {})
        for ring in (R.rings if only is None else only):
            side = hand_of(ring)
            if side == 0:  # (F1: a centre ring is a stiff band on a body loop: a waistband by its seam, a belt by its length)
                from .chain_loops import body_ring
                body_ring(self, ring)
                continue
            tube = next((t for t in R.tubes if self.sewn_with(ring, t)), None)
            if tube is None:
                raise ChainRefused(f"{ring}: sewn to no tube piece. next: check its seams (pattern_check)")
            from .piece_start import axis_for
            ax = axis_for(self, tube)
            sew_ = self.sewn_with(ring, tube)
            rv = net.verts(ring)
            cl = next((c for c in net.M.get("closures") or [] if c["over"] == ring), None)
            if cl is None:
                raise ChainRefused(f"{ring}: no closure of its own: a ring closes on a button. next: add it to the pattern")
            u = net.uv[rv]
            a, b = cl["v"][0]
            C = abs(float(net.uv[a, 0] - net.uv[b, 0]))
            y0 = float(np.mean([net.uv[v, 1] for v in sew_]))
            r = C / (2 * math.pi)
            tv = net.verts(tube)
            Lt = float(net.uv[tv, 1].max() - net.uv[tv, 1].min())
            ub = float(net.uv[b, 0])
            s_end = Lt
            sw = list(sew_.items())
            bestphase = None
            T_ = self.body.T
            V = np.r_[self.body.V, self.body.V[T_].mean(1), self.body.V[T_[:, [0, 1]]].mean(1), self.body.V[T_[:, [1, 2]]].mean(1),
                      self.body.V[T_[:, [2, 0]]].mean(1)]  # (the surface, not only its vertices)
            hgt_ = float(np.ptp(u[:, 1]))
            W_ = float(np.ptp(u[:, 0]))
            vf = np.abs(u[:, 1] - y0) / hgt_
            ug = RING_GAP * 2 * math.pi

            def section(s_mid, half):
                """The limb's convex section over a stretch of the axis, in the frame at s_mid."""
                c0, o0, f0, d0 = (q[0] for q in ax.at(np.array([s_mid])))
                rel = V - c0
                nr = (np.abs(rel @ d0) < half) & (np.linalg.norm(rel, axis=1) < 0.09)
                if nr.sum() < 6:
                    return None
                q = np.c_[rel[nr] @ o0, rel[nr] @ f0]
                return q[ConvexHull(q).vertices]

            def ring_at(h, per_want, fr):
                per = float(np.linalg.norm(np.diff(np.r_[h, h[:1]], axis=0), axis=1).sum())
                t = (per_want - per) / (2 * math.pi)
                e = np.diff(np.r_[h[-1:], h, h[:1]], axis=0)
                nn = unit(np.c_[e[:, 1], -e[:, 0]])
                Q = h + unit(nn[:-1] + nn[1:]) * t
                Q = np.roll(Q, -int(np.argmin(np.abs(np.arctan2(Q[:, 1], Q[:, 0])))), axis=0)  # (every section starts on the same side)
                Q = np.r_[Q, Q[:1]]
                sa = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
                sq = (fr % 1.0) * sa[-1]
                return np.c_[np.interp(sq, sa, Q[:, 0]), np.interp(sq, sa, Q[:, 1])]

            def perim(h):
                return float(np.linalg.norm(np.diff(np.r_[h, h[:1]], axis=0), axis=1).sum())
            best = None
            from . import zozo_hang as zh
            Fr_ = net.F[np.all(net.piece[net.F] == net.pid(ring), axis=1)]
            for k in range(40):  # the ring's shape: the limb's own sections, each at the ring's own closed length; a
                # buttoned cuff flares towards its seam (one button: the overlap opens there), never past the cut width
                P = None
                h0, h1 = section(s_end + 0.25 * hgt_, 0.25 * hgt_ + 0.002), section(s_end + 0.75 * hgt_, 0.25 * hgt_ + 0.002)
                if h0 is not None and h1 is not None:
                    C0, C1 = max(C, perim(h0) + ug), max(C, perim(h1) + ug)
                    if C0 <= W_ and C1 <= W_:
                        Cv = C0 + (C1 - C0) * vf
                        if bestphase is None:  # the ring turned to meet its tube: the sewn points at their own angles
                            rvid = {int(q): i for i, q in enumerate(rv)}
                            ti = np.array([rvid[q] for q, _ in sw])
                            tp = self._tube_points(tube, np.array([q for _, q in sw]), s_end)
                            Cc0, o0_, f0_, _d = ax.at(np.full(len(sw), s_end))
                            ang_t = np.arctan2(((tp - Cc0) * f0_).sum(1), ((tp - Cc0) * o0_).sum(1))
                            bc = None
                            for dn in (1.0, -1.0):
                                for ph_ in np.linspace(0, 1, 48, endpoint=False):
                                    frs = dn * (u[ti, 0] - ub) / Cv[ti] + ph_
                                    pr = ring_at(h0, C0, frs)
                                    ang_r = np.arctan2(pr[:, 1], pr[:, 0])
                                    cost = float((1 - np.cos(ang_r - ang_t)).sum())
                                    if bc is None or cost < bc[0]:
                                        bc = (cost, dn, ph_)
                            bestphase = bc[1:]
                        fr = bestphase[0] * (u[:, 0] - ub) / Cv + bestphase[1]
                        p0, p1 = ring_at(h0, C0, fr), ring_at(h1, C1, fr)
                        pp = p0 + (p1 - p0) * vf[:, None]
                        lap = LAYER * np.clip(bestphase[0] * (u[:, 0] - ub) / Cv, 0, 1)
                        rad = unit(pp - pp.mean(0))
                        pp = pp + rad * lap[:, None]
                        Cc, o, f, d = ax.at(s_end + 0.5 * hgt_ * np.ones(len(u)))
                        Cc2 = Cc + d * ((np.abs(u[:, 1] - y0) - 0.5 * hgt_))[:, None]
                        P = Cc2 + o * pp[:, 0:1] + f * pp[:, 1:2]
                        Xt_ = self.X.copy()
                        Xt_[rv] = P
                        sdm = min(float(self.body.contact.query(P)[0].min()),  # (faces and edges too, as ZOZO reads them)
                                  zh.legality(Xt_, Fr_, self.body.V, self.body.T)["min_mm"] * 1e-3)
                        if best is None or sdm > best[0]:
                            best = (sdm, P, s_end, C0, C1)
                        if sdm >= RING_GAP:
                            break
                s_end -= 0.005
            P = None
            if best is not None and best[0] >= zozo_legal():
                _, P, s_end, C0, C1 = best
                self.reads.setdefault("ring_closed_at", {})[ring] = {"mm": [round(C0 * 1e3, 1), round(C * 1e3, 1), round(C1 * 1e3, 1)], "gap_mm": round(best[0] * 1e3, 2)}
            if P is None:
                raise ChainRefused(f"{ring}: closed length {C * 1e3:.0f} mm does not clear the limb anywhere up the {tube}. "
                                   "next: lengthen the ring in the pattern (alter_pattern)")
            self.X[rv] = P
            self.X[net.root[rv]] = P
            self.reads["rings"][ring] = {"radius_mm": round(r * 1e3, 1), "at_mm_along_limb": round(s_end * 1e3, 1), "tube_mm": round(Lt * 1e3, 1)}
            self.reads["rings"][ring]["slid_back_mm"] = round((Lt - s_end) * 1e3, 1)
            self._ring_s = getattr(self, "_ring_s", {})
            self._ring_s[tube] = s_end

    # ---- 4. the soft start
    def _tube_points(self, t, v, s_end=None):
        """Vertices v of tube t at their start: rows round the limb's axis at the pattern's width."""
        net, R = self.net, self.roles
        if t in R.tube_groups:  # (a tube of several pieces: a two-piece sleeve; T8)
            from .chain_roles import tube_group_points
            return tube_group_points(self, t, v)
        uv = net.uv
        side = hand_of(t)
        from .piece_start import axis_for
        ax = axis_for(self, t)
        tv = net.verts(t)
        xa, ya = uv[tv, 0], uv[tv, 1]
        fp = [p for p in R.panels if self.sewn_with(t, p) and R.front and p in (R.front["over"], R.front["under"])]
        sf = float(np.sign(np.mean([uv[q, 0] for q in self.sewn_with(t, fp[0])]))) if fp else 1.0
        ytop, ybot = float(ya.max()), float(ya.min())
        L = ytop - ybot
        s_end = getattr(self, "_ring_s", {}).get(t, L) if s_end is None else s_end
        bins = np.round(ya / 0.01).astype(int)
        wmax = {b: float(xa[bins == b].max() - xa[bins == b].min()) for b in np.unique(bins)}
        wide = max(wmax.values())
        yw = float(ya[np.argmax(np.abs(xa))])  # the cap (rows above the widest): whole width, so its edge rings the armhole
        x, y = uv[v, 0], uv[v, 1]
        w = np.array([wide if yy >= yw else max(wmax[int(round(yy / 0.01))], 0.06) for yy in y])
        s = (ytop - y) * s_end / L
        Cc, o, f, d = ax.at(s)
        ph = 2 * math.pi * x * sf / w
        return Cc + (np.cos(ph)[:, None] * o + np.sin(ph)[:, None] * f) * (w / (2 * math.pi))[:, None]

    def soft_start(self):
        net, R = self.net, self.roles
        uv = net.uv
        hz = float(self.body.p("hps.L")[2])
        rings = TorsoRings(self.body, self._width_of(), GAP)
        self.torso = rings
        X = self.X.copy()
        from .chain_roles import edge_to_edge
        over = R.front["over"] if R.front and not edge_to_edge(R.front) else None  # (edge to edge: no lap, no layer)
        for p in R.panels:
            v = net.verts(p)
            x, y = uv[v, 0], uv[v, 1]
            from .piece_start import panel_dz
            z = hz + y + panel_dz(self, p)  # (F4: between its own tapes; no paths: hung from the hps)
            hand = hand_of(p)
            isfront = bool(R.front and p in (R.front["over"], R.front["under"]))
            P = rings.at(x, z) if isfront else rings.at(x, z, half_back=True)
            wz = np.clip((z - (rings.armpit - 0.04)) / 0.08, 0, 1)
            wz = (wz * wz * (3 - 2 * wz))[:, None]
            P = P * (1 - wz) + rings.at_x(x, z, not isfront) * wz
            if p == over:  # the over side lies a layer outside the under side, fading away from the centre
                w = np.clip((0.12 - np.abs(x)) / 0.06, 0, 1)
                cen = np.array([0.0, float(self.body.p("cf_neck")[1] + self.body.p("cb_neck")[1]) / 2])
                P[:, :2] += unit(P[:, :2] - cen) * (LAYER * w)[:, None]
            X[v] = P
        for t in R.tubes:
            v = net.verts(t)
            X[v] = self._tube_points(t, v)
        from .chain_stages import mirror_starts
        from .piece_start import turn_to_seams
        X = mirror_starts(self, turn_to_seams(self, X))  # (F5 C314: a .R piece starts as its .L's mirror, never solved on its own)
        # (F9, F10: started on the step-2 SDF block-in: each piece mapped onto its region, seams closed. THE start when the
        # plan has a blockin (the job sets build.blockin from it); HIFIPUSHIE_BLOCKIN_START=0 turns it off for a comparison)
        if uses_blockin_start(self):
            from .blockin_map import start as _bstart
            return _bstart(self, blockin_of(self), X)
        # (F7: flat then sewn: exact, but its sew stalls before the seams close on the trousers: OPT-IN until it closes them,
        # HIFIPUSHIE_SEW_START=1 or build.sew_start = True; coordinator 2026-11-03)
        if getattr(self, "sew_start", os.environ.get("HIFIPUSHIE_SEW_START") == "1"):  # (that lay is the GUIDE)
            self.sew_start_used = True
            from .chain_sew import flat_then_sew
            X = flat_then_sew(self, X)
        return X

    def soft_net(self, start=None, far_z=None):
        """Chains + lines of the soft cloth from its start, stiff nodes held; then surfaces; then the threads."""
        net, R = self.net, self.roles
        rs, uv = net.root, net.uv
        stiff_v = self._stiff_mask()
        if getattr(self, "extra_held", None) is not None:
            stiff_v = stiff_v | self.extra_held
        if getattr(self, "stay_v", None) is not None:  # (a placket fold: the tied cloth below its pair stays as built)
            stiff_v = stiff_v | self.stay_v
        held = np.zeros(net.n, bool)
        held[rs[stiff_v]] = True
        # sewn group mean for the free ones
        X0 = self.soft_start() if start is None else np.array(start, float)
        from . import chain_stages as cst  # (F5: each stage gated where it ends, cheapest first)
        if start is None:
            cst.check(self, "start", X0)
        count = np.zeros(net.n)
        S_ = np.zeros((net.n, 3))
        np.add.at(S_, rs, X0)
        np.add.at(count, rs, 1)
        Xm = S_ / np.maximum(count, 1)[:, None]
        Xm = np.where(held[:, None], self.X, Xm)
        Xm = Xm[rs]
        soft_F = net.F[~np.isin(net.piece[net.F[:, 0]], [net.pid(p) for p in ([R.band, R.fall] + list(R.rings) + R.carried) if p])]
        far_z = float(self.body.at["armpit_z"]) - 0.04 if far_z is None else far_z
        nodes = np.unique(rs[soft_F])
        ring_near = np.zeros(net.n, bool)
        for t in R.tubes:
            tv = net.verts(t)
            ring_near[rs[tv[uv[tv, 1] > uv[tv, 1].max() - 0.45]]] = False
        # the seams' moves carried into each piece (per piece: two sides of a seam start apart)
        count_g = np.bincount(rs, minlength=net.n)
        sewn_v = count_g[rs] > 1
        Xf = Xm.copy()
        for p in R.panels + R.tubes:
            v = net.verts(p)
            Fp = net.F[np.all(net.piece[net.F] == net.pid(p), axis=1)]
            kn = np.zeros(net.n, bool)
            kn[v] = sewn_v[v] | held[rs[v]] | ((X0[v, 2] < far_z) & np.isin(p, R.panels))
            Yv = X0.copy()
            Yv[v[kn[v]]] = Xm[v[kn[v]]]
            Xf[v] = cn.fill(X0, Yv, kn, uv, Fp, v)[v]
        Xf = Xf[rs]
        # the chains and lines (the stiff pieces' own are held)
        li, lj, lL, lE = net.lines()
        I, J = np.r_[net.link_i, li], np.r_[net.link_j, lj]
        L, E = np.r_[net.link_L, lL], np.r_[np.ones(len(net.link_L), bool), lE]
        ties = self._closure_ties()
        if len(ties):
            I, J = np.r_[I, ties[:, 0].astype(int)], np.r_[J, ties[:, 1].astype(int)]
            L, E = np.r_[L, ties[:, 2]], np.r_[E, np.ones(len(ties), bool)]
        chain_nodes = np.unique(np.r_[net.link_i, net.link_j, li, lj])
        cf = chain_nodes[~held[chain_nodes]]
        floor = [(self.body.contact, cf, GAP)]
        uf = self._under_fall(Xf, cf)
        if uf is not None and len(uf[1]):
            floor.append((uf[0], uf[1], UNDER))
        Y = Xf
        nbr: dict = {}
        for a, b in zip(net.link_i, net.link_j):
            nbr.setdefault(int(a), set()).add(int(b))
            nbr.setdefault(int(b), set()).add(int(a))
        two = np.array([v for v, q in nbr.items() if len(q) == 2 and not held[v]], np.int64)
        n0 = np.array([sorted(nbr[int(v)])[0] for v in two], np.int64)
        n1 = np.array([sorted(nbr[int(v)])[1] for v in two], np.int64)
        rd = {}
        for rnd in range(4):
            Y, rd = project(Y, I, J, L, E, held, floor, iters=20, step=0.015)
            self.log(f"chains round {rnd}: {rd}")
            if rnd < 3:
                Y[two] = 0.8 * Y[two] + 0.1 * (Y[n0] + Y[n1])
        Y, rd = project(Y, I, J, L, E, held, floor, iters=40, step=0.015)
        self.reads["soft_chains"] = rd
        cst.check(self, "chains", Y[rs])
        # surfaces between the chains
        known2 = held.copy()
        known2[chain_nodes] = True
        Z = cn.fill(Xf, Y, known2, uv, soft_F, ids=nodes, root=rs)
        Z = np.where(np.isin(np.arange(net.n), nodes)[:, None], Z, Y)[rs]
        cst.check(self, "surfaces", Z)  # (before the thread solve: the lay's own crumpling, told apart from the solve's)
        # threads, chains last
        E_all = net.edges[~np.all(stiff_v[net.edges], axis=1)]
        Lm = np.linalg.norm(uv[E_all[:, 0]] - uv[E_all[:, 1]], axis=1) * (1 + SHEAR_LIMIT)
        ei, ej = rs[E_all[:, 0]], rs[E_all[:, 1]]
        k = ei != ej
        I2, J2 = np.r_[I, ei[k]], np.r_[J, ej[k]]
        L2, E2 = np.r_[L, Lm[k]], np.r_[E, np.zeros(int(k.sum()), bool)]
        th = Threads(uv, soft_F, CAP, root=rs)
        fl2 = [(self.body.contact, nodes[~held[nodes]], GAP)]
        uf = self._under_fall(Z, nodes[~held[nodes]])
        under = [(uf[0], uf[1], UNDER)] if uf is not None and len(uf[1]) else []
        fl2 = fl2 + under
        for rnd in range(3):
            Z, rd2 = project(Z, I2, J2, L2, E2, held, fl2, threads=th, iters=40, step=0.008)
            Z, rd3 = project(Z, I, J, L, E, held, fl2, iters=30, step=0.008)  # lengths last
            self.log(f"mesh round {rnd}: {rd2} / {rd3}")
        # the floor seen by faces and edges, not only points (a 20 mm chord sags onto a sharp bump): a point whose element
        # comes nearer than ZOZO's reach gets that much more floor, and the lengths are solved again with it
        from . import zozo_hang as zh
        ids_ = nodes[~held[nodes]]
        gaps = np.full(net.n, GAP)
        F_r = rs[soft_F]
        F_r = F_r[(F_r[:, 0] != F_r[:, 1]) & (F_r[:, 1] != F_r[:, 2]) & (F_r[:, 0] != F_r[:, 2])]
        for rnd in range(6):
            pr = zh.contact_pairs(Z, F_r, self.body.V, self.body.T, zh.REACH)
            self.log(f"edge floor {rnd}: {len(pr['d'])} pairs under reach")
            if not len(pr["d"]):
                break
            for c, dv in zip(pr["cloth"], pr["d"]):
                c = c[c >= 0]
                gaps[c] = np.maximum(gaps[c], self.body.contact.query(Z[c])[0] + (zh.REACH - dv) + 0.0006)
            fl3 = [(self.body.contact, ids_, gaps[ids_])] + under
            Z, rd3 = project(Z, I2, J2, L2, E2, held, fl3, threads=th, iters=20, step=0.008)
            Z, rd3 = project(Z, I, J, L, E, held, fl3, iters=25, step=0.008)
            fl2 = fl3
        self.reads["last_lengths"] = rd3
        self.X = Z[rs]
        self.reads["soft_mesh"] = rd2
        self.reads["threads"] = th.report(self.X)
        self.thread_model = th
        self.final_links = (I2, J2, L2, E2, held, fl2, th)

    def _under_fall(self, Y, nodes):
        """The soft cloth stays under the fall: its underside as a Contact and the soft nodes in its footprint."""
        net, R = self.net, self.roles
        if not R.fall:
            return None
        uv = net.uv
        F = net.F[np.all(net.piece[net.F] == net.pid(R.fall), axis=1)]
        kn = cKDTree(uv[self.fall_ch["neck"]])
        leaf = kn.query(uv)[0] > self.droll + 0.004  # the leaf, past the turn
        F = F[leaf[F].all(1)]
        fn = np.cross(Y[F[:, 1]] - Y[F[:, 0]], Y[F[:, 2]] - Y[F[:, 0]])
        bn = self.body.contact.query(Y[F].mean(1))[1]
        flip = (fn * bn).sum(1) < 0
        F[flip] = F[flip][:, [0, 2, 1]]
        ct = Contact(Y, F, side=-1.0)
        ids = np.unique(F)
        edge = set(int(v) for k_ in ("outer", "endL", "endR") for v in self.fall_ch[k_])
        inner = ids[[int(v) not in edge for v in ids]]
        d, j = cKDTree(Y[ids]).query(Y[nodes])
        q = ids[j]
        at_edge = np.isin(q, list(edge))
        # a node nearest the leaf's edge counts unless it lies past that edge (in the leaf's own plane, away from the leaf)
        kin = cKDTree(Y[inner])
        qin = inner[kin.query(Y[q])[1]]
        away = unit(Y[q] - Y[qin])
        past = ((Y[nodes] - Y[q]) * away).sum(1) > 0.002
        return ct, nodes[(d < 0.03) & ~(at_edge & past)]
