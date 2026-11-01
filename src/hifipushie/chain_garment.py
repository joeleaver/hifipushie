"""CHAIN GARMENT: a garment built from its pattern and a body, as chains of the pattern's own lengths (chain_net.py). The
one way a garment is started (Joe 2026-11-01: "that should be the only path available to the agent for starting
clothing"). Input: a pattern (the flat mesh dict) and a body (V, T, at). A fit's positions are never read: Pattern
carries only PATTERN_KEYS, so a fit has no way in.

ROLES come from the pattern, not from names (read_roles): a piece with a "roll" fold is a FALL; the wholly interfaced piece
it is sewn to is its BAND; other wholly interfaced pieces closed on themselves are RINGS (cuffs, waistbands); a soft piece
sewn to itself is a TUBE (sleeves); other soft pieces are PANELS wrapped round the torso. A closure between two pieces is
the FRONT. A role the core can't build is refused by name; there is no fallback to another path.

THE ORDER (each from a visible fault; C259-C262): stiff parts first, soft parts hang from them, never the reverse.
1. BAND: chains + exact lines, closed round the neck on its own button. Stiff all along (pattern's interfacing), keeps its
   own shape, rests on the high points: can't sink in plus a light rest pull, never follows the surface.
   Open wear: the closed band's pressed curve kept round the back, relaxed straight past the side necks, started from a
   swung-open guess; the sewn front is limited: every neck-edge point at most its cut distance from the first fastened
   button. Worn straight = mirror symmetric.
2. FALL on the held band: roll line, outer edge, ends: exact chains; lines across may shorten where the leaf curves, full
   width where it lies flat at the back; the point's triangle is rigid. Outside faces out.
3. RINGS: a stiff circle of the piece's own closed length, where the tube's own length reaches, clear of the body.
4. SOFT NETWORK: panels wrapped on a garment-sized ring per height (the torso's convex section, offset until its perimeter
   is the pattern's width there), tubes on the limb's axis at the pattern's width. Sewn points one node, stiff nodes held,
   chains + lines projected with the body as a floor: the start is legal by construction, nothing is pushed afterwards.
5. PLACKETS (open): a stiff strip folds out of plane along a solved crease through the first fastened button (in-plane
   rotation stretches); the fold acts on the real shape so nothing jumps at the crease; over side over under side.
6. SURFACES fill between fixed chains (fold turn: a half circle of the pattern's radius round the band top; the band stays
   under the fall; corner patch at the leaf's neck end).
7. HANG (hang()): the soft cloth under gravity in ZOZO, stiff parts held; lengths have the last word afterwards.
   The collider is the whole body: nothing is cut from it. An illegal start is a build fault and is refused by name.

Every stage ends in chain_net.project; Build.reads holds the numbers; a length that can't hold raises ChainRefused naming
the piece and the line and what to do next."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

from . import chain_net as cn
from .chain_net import BendSolve, Contact, Network, Threads, project, unit

PATTERN_KEYS = ("uv", "piece", "names", "F", "folds", "made", "grain", "sew", "sew_seam", "stitch", "marks", "closures",
                "points", "border", "stitch_lines")
GAP = 0.0045  # m: soft cloth and stiff parts stay this far off the body (ZOZO's reach + a mesh edge's sag over an arm)
LAYER = 0.003  # m: one layer of cloth over another (the fall over the shirt, the over placket over the under)
FALL_GAP = GAP + LAYER + 0.002  # the fall rests on the soft cloth under it
REST = 0.1  # weight of the light rest pull (contact itself is 5)
CAP = 0.02  # thread cap of soft cloth (pattern_form.FIT_THREAD_CAP)
SHEAR_LIMIT = 0.27  # the weave's own limit on a mesh edge (zozo_hang.woven_limit, 2 % threads, jam 35 deg)
OPEN_SPREAD = 1.7  # default open wear: the collar points this many neck widths apart
MAX_LINK_PCT = 0.05  # a chain link further off than this after the last projection is refused


class ChainRefused(ValueError):
    """A build that can't hold. The message names the piece, the line, the number and the next step."""


@dataclass
class Pattern:
    """Pattern data only (never positions)."""
    M: dict
    stiff: np.ndarray
    bend: np.ndarray
    fold_radius: dict = field(default_factory=dict)  # fold name / piece -> roll radius (m)


def pattern_from_mesh(M: dict, stiff=None, bend=None, fold_radius: dict | None = None) -> Pattern:
    m = {k: M[k] for k in PATTERN_KEYS if k in M}
    n = len(m["uv"])
    return Pattern(m, np.zeros(n) if stiff is None else np.asarray(stiff, float),
                   np.ones(n) if bend is None else np.asarray(bend, float), dict(fold_radius or {}))


@dataclass
class Body:
    V: np.ndarray
    T: np.ndarray
    at: dict

    def __post_init__(self):
        self.V, self.T = np.asarray(self.V, float), np.asarray(self.T, np.int64)
        self.contact = Contact(self.V, self.T)

    def p(self, k):
        return np.asarray(self.at[k], float)


@dataclass
class Roles:
    band: str | None
    fall: str | None
    rings: list
    tubes: list
    panels: list
    front: dict | None
    band_closure: dict | None
    fold: dict | None


def read_roles(net: Network) -> Roles:
    names = net.names
    whole = {n: float(net.stiff[net.verts(n)].mean()) > 0.95 for n in names}
    sewn: dict = {n: set() for n in names}
    self_sewn = set()
    for a, b in net.sew:
        pa, pb = names[net.piece[a]], names[net.piece[b]]
        if pa == pb:
            self_sewn.add(pa)
        else:
            sewn[pa].add(pb)
            sewn[pb].add(pa)
    fold = next((f for f in net.M.get("folds") or [] if f.get("kind") == "roll"), None)
    fall = fold["piece"] if fold else None
    band = None
    if fall:
        cand = [p for p in sewn[fall] if whole[p]]
        if not cand:
            raise ChainRefused(f"{fall}: a roll piece sewn straight to the body cloth (no interfaced band): a chain build "
                               "needs the band it stands on. next: add a band to the pattern (design_garment)")
        band = cand[0]
    closures = net.M.get("closures") or []
    band_cl = next((c for c in closures if band and c["over"] == band), None)
    front = next((c for c in closures if c["over"] != c["under"]), None)
    rings = [n for n in names if whole[n] and n not in (band, fall)]
    tubes = [n for n in names if not whole[n] and n in self_sewn]
    panels = [n for n in names if not whole[n] and n not in tubes]
    return Roles(band, fall, rings, tubes, panels, front, band_cl, fold)


def hand_of(name: str) -> float:
    """Which side a piece is worn on, by the repo's own naming rule: ".L" = +X, ".R" = -X, else on the centre."""
    return 1.0 if name.endswith(".L") else (-1.0 if name.endswith(".R") else 0.0)


class Build:
    """One garment build. X: per vertex; sewn groups share a position. reads: what each stage measured."""

    def __init__(self, pattern: Pattern, body: Body, wear: dict | None = None, log=print):
        self.pat, self.body, self.log = pattern, body, log
        self.wear = {"state": "closed", "spread": OPEN_SPREAD, **(wear or {})}
        self.net = Network(pattern.M, pattern.stiff, pattern.bend)
        self.roles = read_roles(self.net)
        self.X = np.zeros((self.net.n, 3))
        self.held = np.zeros(self.net.n, bool)
        self.reads: dict = {"seam_truing": self.net.seam_mismatch()}
        m = float(self.net.link_cut[:, 1].sum()) and self.net.seam_mismatch()["max_pct"]
        if self.reads["seam_truing"]["max_mm"] > 3.0:
            raise ChainRefused(f"a seam's two sides differ by {self.reads['seam_truing']['max_mm']} mm over one link: "
                               "next: true the pattern (pattern_check, alter_pattern); a chain can't be two lengths")
        self._mirror()

    # ---- helpers
    def _mirror(self):
        net = self.net
        pairs, solo = [], []
        for n in net.names:
            if n.endswith(".L"):
                r = n[:-2] + ".R"
                if r in net.names:
                    u = net.uv[net.verts(n), 0]
                    ur = net.uv[net.verts(r), 0]
                    same = abs(u.mean() - ur.mean()) < 0.5 * max(abs(u.mean()), abs(ur.mean()), 1e-3) or \
                        (abs(u.mean()) < 0.02 and abs(ur.mean()) < 0.02)
                    pairs.append((n, r, 1.0 if same else -1.0))
            elif not n.endswith(".R"):
                solo.append(n)
        self.mir = cn.mirror_map(net, pairs, solo)

    def _set(self, v, P):
        """Set positions of vertices v (sewn partners follow through the root)."""
        r = self.net.root[np.asarray(v, np.int64)]
        self.X[r] = P
        self.X[np.isin(self.net.root, r)] = self.X[self.net.root[np.isin(self.net.root, r)]]

    def _sync(self):
        self.X = self.X[self.net.root]

    def sewn_with(self, a: str, b: str) -> dict:
        """vertex of a -> vertex of b, for a seam between pieces a and b."""
        pa, pb = self.net.pid(a), self.net.pid(b)
        out = {}
        for x, y in self.net.sew:
            if self.net.piece[x] == pa and self.net.piece[y] == pb:
                out[int(x)] = int(y)
            elif self.net.piece[y] == pa and self.net.piece[x] == pb:
                out[int(y)] = int(x)
        return out

    def order_x(self, v):
        v = np.asarray(sorted(set(int(q) for q in v)), np.int64)
        return v[np.argsort(self.net.uv[v, 0])]

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

    def band_open(self):
        """The stiff band's own shape unbuttoned: pressed curve kept round the back (sewn to the back piece, held),
        relaxed straight past the side necks, started swung open; the sewn front limited by its cut distance to the first
        fastened button."""
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
        # the first fastened button: the fronts stay closed there
        cl = R.front
        bvs = cl["v"][0]
        self.button = bvs
        bpos = self._button_centre()
        self.button_pos = bpos
        limit = []
        for p in (cl["over"], cl["under"]):
            sew_ = self.sewn_with(p, R.band)
            for fv, sv in sew_.items():
                L = float(np.linalg.norm(uv[fv] - uv[bvs[0] if net.piece[bvs[0]] == net.pid(p) else bvs[1]]))
                if L < 0.09:
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
            S.add_bend(node, cn.BEND_BASE * net.bend[ch[1:-1]], rest=rest * (cn.H0 / np.maximum(np.linalg.norm(np.diff(C0, axis=0), axis=1)[1:], 1e-5)) ** 0)
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
        S.add_fn(tied)
        self.X = S.solve(60)
        held = np.ones(net.n, bool)
        held[free] = False
        rd = self._band_project(held, extra_limit=limit)
        self.reads["band_open"] = {**self._band_read(), "limit_over_mm": rd["limit_mm"],
                                   "ends_apart_mm": round(float(np.linalg.norm(self.X[nt[0]] - self.X[nt[-1]]) * 1e3), 1),
                                   "limited_points": len(limit)}

    def _button_centre(self):
        """Where the first fastened button sits (from the chain build, on the centre line)."""
        a, b = self.button
        p = 0.5 * (self.X[self.net.root[a]] + self.X[self.net.root[b]])
        p[0] = 0.0
        return p

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
            for a, b in ((across(i, neck), roll[i]), (roll[i], across(i, outer))):
                pairs.append((a, b))
                exact.append(bool(min(self.X[rs[a], 1], self.X[rs[b], 1]) > hpsy - 0.01))
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
        S.add_contact(rs[np.r_[outer, roll]], self.body.contact, GAP + LAYER)
        hy = hpsy - 0.01
        S.add_contact(lie, self.body.contact, FALL_GAP, rest=REST)

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
            ptx = float(self.wear["spread"]) * neckW / 2
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
        Xn, rd = project(self.X, I, J, L, E, held, [(self.body.contact, free, GAP + LAYER)])
        self.X = Xn
        self.fall_links = (I, J, L, E)
        l = np.linalg.norm(Xn[I] - Xn[J], axis=1) / np.maximum(L, 1e-9) - 1
        self.reads["fall"] = {"worst_chain_pct": round(float(np.abs(l[E]).max() * 100), 3), "worst_line_over_pct": round(float(max(l.max(), 0) * 100), 3),
                              "project": rd, "points_mm": [round(float(self.X[rs[e[-1]], c] * 1e3), 1) for e in (endL, endR) for c in (0, 1, 2)]}

    # ---- 6. surfaces of the stiff parts (between their fixed chains)
    def fill_band(self):
        net, R = self.net, self.roles
        rs = net.root
        for piece, known_v in ((R.band, np.r_[self.sb, self.st]),):
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
        ns = set(int(v) for v in neck)
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


def _keep_roots(net, X):
    return np.asarray(X, float)[net.root]


def cn_vnormals(X, F):
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    N = np.zeros_like(X)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return unit(N + 1e-30)


def _neighbours(F) -> dict:
    nb: dict = {}
    for a, b in cn.edges_of(F):
        nb.setdefault(int(a), []).append(int(b))
        nb.setdefault(int(b), []).append(int(a))
    return nb
