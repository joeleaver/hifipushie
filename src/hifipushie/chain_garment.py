"""CHAIN GARMENT: a garment built from its pattern and a body, as chains of the pattern's own lengths (chain_net.py). The
one way a garment is started (Joe 2026-11-01: "that should be the only path available to the agent for starting
clothing"). Input: a pattern (the flat mesh dict) and a body (V, T, at). A fit's positions are never read: Pattern
carries only PATTERN_KEYS, so a fit has no way in.

ROLES come from the pattern, not from names (read_roles): a piece with a "roll" fold is a FALL; the wholly interfaced piece
it is sewn to is its BAND; other wholly interfaced pieces closed on themselves are RINGS (cuffs, waistbands); a soft piece
sewn to itself is a TUBE (sleeves); other soft pieces are PANELS wrapped round the torso. A closure between two pieces is
the FRONT. A role the core can't build is refused by name; there is no fallback to another path.

THE ORDER (each from a visible fault; C259-C262): stiff parts first, soft parts hang from them, never the reverse.
THE STATE (T7, C287; chain_plan.py): built straight into the garment record's style plan (step 2): each closure in its
planned state, the plan's bend targets (collar spread) as the stages' targets; wear is derived from the plan (a
contradicting wear is refused); no closed garment is built and then styled open.
1. BAND: chains + exact lines, its pressed ring of its own button-to-buttonhole length, resting on the high points
   (chain_rest.rest_ring, C280). Stiff all along (pattern's interfacing), keeps its own shape: can't sink in plus a light
   rest pull, never follows the surface. Closed band: closed on its own button.
   Open band: the pressed curve kept round the back, relaxed straight past the side necks, started from a swung-open
   guess; the sewn front is limited: every neck-edge point at most its cut distance from the first fastened button
   (its start on the torso: nothing soft is built yet). Worn straight = mirror symmetric.
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
7. STRUCTURE (chain_structure.py, C279): the BUILD is measured beside the reference before any hang: the collar's
   clearance under the jaw, its top line's tilt, the points' spread and drop, the leaves lying; the front meeting and
   straight, the V (open); the hem level; sleeve length and cuff ease. Each row: target, source, and on FAIL what to
   change. The job ends "structure_failed" with its rows unless every row passes or is waived by name with a reason. The
   hang adds folds by design: a hung result never judges a structure fault, nor hides one.
7a. PRE-SIM APPROVAL (chain_presim.py): after a pass the job stops at "awaiting_approval" until the garment record's step
   7a is approved (or HIFIPUSHIE_PRESIM_APPROVAL=optional); the same call then resumes from built.pkl, never rebuilds.
8. HANG (hang()): the soft cloth under gravity in ZOZO, stiff parts held; lengths have the last word afterwards. Its gate:
   no face past the thread cap (chain_presim.threads_gate).
   The collider is the whole body: nothing is cut from it. An illegal start is a build fault and is refused by name.
   Worn over another garment (step 1's "over", chain_layers.py + chain_press.py, T12): the body + that garment's
   thickness + its stiff parts and details; the garment under is then fitted inside this one (visible parts by default).

Every stage ends in chain_net.project; Build.reads holds the numbers; a length that can't hold raises ChainRefused naming
the piece and the line and what to do next."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

from . import chain_net as cn
from .chain_net import BendSolve, Contact, Network, Threads, project, unit

PATTERN_KEYS = ("uv", "piece", "names", "F", "folds", "made", "grain", "sew", "sew_seam", "stitch", "marks", "closures",
                "points", "border", "stitch_lines", "roles")
GAP = 0.0045  # m: soft cloth and stiff parts stay this far off the body (ZOZO's reach + a mesh edge's sag over an arm)
RING_GAP = 0.004  # m: a stiff ring off a limb (ZOZO's reach): it hangs loose, so its gap is the solver's, no more
RING_H = 0.008  # m: mesh size on a stiff ring
UNDER = 0.002  # m: soft cloth under the fall
LAYER = 0.003  # m: one layer of cloth over another (the fall over the shirt, the over placket over the under)
FALL_GAP = GAP + LAYER + 0.002  # the fall rests on the soft cloth under it
REST = 0.1  # weight of the light rest pull (contact itself is 5)
CAP = 0.02  # thread cap of soft cloth (pattern_form.FIT_THREAD_CAP)
SHEAR_LIMIT = 0.27  # the weave's own limit on a mesh edge (zozo_hang.woven_limit, 2 % threads, jam 35 deg)
OPEN_SPREAD = 1.7  # default open wear: the collar points this many neck widths apart
MAX_FREE_PCT = 2.0  # % a free chain link may read off its cut at a stage's end before the build is refused


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
    stand: bool = False  # the band is a STAND: nothing turned over it (chain_roles)
    tube_groups: dict = field(default_factory=dict)  # piece -> the pieces of its several-piece tube (chain_roles)


def read_roles(net: Network) -> Roles:
    """The pattern's roles: chain_roles.read_roles (its doc: fall, band, stand, rings, tubes of one or more pieces,
    panels, the front lapped or edge to edge)."""
    from .chain_roles import read_roles as rr
    return rr(net)


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
        if self.wear.get("fastened_from") and self.roles.front:  # (style plan: a front fastened partly, T7)
            from .chain_plan import fasten_from
            self.roles.front = fasten_from(self.roles.front, int(self.wear["fastened_from"]))
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


def joined_faces(X, M, bV, bT) -> np.ndarray:
    """The garment's faces with sewn vertices shared and every piece facing outward (the spike's joined.py: pronounced
    seams were mostly per-piece shading). Used by every render of a chain build."""
    X = np.asarray(X, float)
    F = np.asarray(M["F"], np.int64).copy()
    pc = np.asarray(M["piece"])
    s = np.asarray(M["sew"], np.int64).reshape(-1, 2)
    s = s[np.linalg.norm(X[s[:, 0]] - X[s[:, 1]], axis=1) < 0.002]
    root = cn.union_roots(len(X), s)
    N = cn_vnormals(np.asarray(bV, float), np.asarray(bT, np.int64))
    kd = cKDTree(bV)
    for p in np.unique(pc):
        fi = np.where(pc[F[:, 0]] == p)[0]
        c = X[F[fi]].mean(1)
        n = np.cross(X[F[fi, 1]] - X[F[fi, 0]], X[F[fi, 2]] - X[F[fi, 0]])
        if (n * N[kd.query(c)[1]]).sum() < 0:
            F[fi] = F[fi][:, [0, 2, 1]]
    return root[F]


def zozo_legal() -> float:
    """The nearest a cloth point may start to the collider (ZOZO's contact offset + a hair)."""
    return 0.00203


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


class GarmentBuild(Build):
    """All stages. run() -> self.X (the chain build, before the hang)."""

    # ---- which cloth
    def _stiff_mask(self):
        net, R = self.net, self.roles
        whole = [p for p in (R.band, R.fall) if p] + list(R.rings)
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
    def rings(self):
        net, R = self.net, self.roles
        self.axes = {}
        self.reads["rings"] = {}
        for ring in R.rings:
            side = hand_of(ring)
            if side == 0:
                raise ChainRefused(f"{ring}: a ring not worn on a limb (a waistband?) has no chain build yet. next: tell the "
                                   "coordinator; don't fit it another way")
            tube = next((t for t in R.tubes if self.sewn_with(ring, t)), None)
            if tube is None:
                raise ChainRefused(f"{ring}: sewn to no tube piece. next: check its seams (pattern_check)")
            ax = self.axes.setdefault(side, LimbAxis(self.body, side))
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
        ax = self.axes.setdefault(side, LimbAxis(self.body, side))
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
            z = hz + y
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
        return X

    def soft_net(self, start=None, far_z=None):
        """Chains + lines of the soft cloth from its start, stiff nodes held; then surfaces; then the threads."""
        net, R = self.net, self.roles
        rs, uv = net.root, net.uv
        stiff_v = self._stiff_mask()
        if getattr(self, "extra_held", None) is not None:
            stiff_v = stiff_v | self.extra_held
        if getattr(self, "stay_v", None) is not None:  # (open wear: the buttoned cloth below the first button stays as built)
            stiff_v = stiff_v | self.stay_v
        held = np.zeros(net.n, bool)
        held[rs[stiff_v]] = True
        # sewn group mean for the free ones
        X0 = self.soft_start() if start is None else np.array(start, float)
        count = np.zeros(net.n)
        S_ = np.zeros((net.n, 3))
        np.add.at(S_, rs, X0)
        np.add.at(count, rs, 1)
        Xm = S_ / np.maximum(count, 1)[:, None]
        Xm = np.where(held[:, None], self.X, Xm)
        Xm = Xm[rs]
        soft_F = net.F[~np.isin(net.piece[net.F[:, 0]], [net.pid(p) for p in ([R.band, R.fall] + list(R.rings)) if p])]
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
        # surfaces between the chains
        known2 = held.copy()
        known2[chain_nodes] = True
        Z = cn.fill(Xf, Y, known2, uv, soft_F, ids=nodes, root=rs)
        Z = np.where(np.isin(np.arange(net.n), nodes)[:, None], Z, Y)[rs]
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
        for p in [q for q in (R.band, R.fall) if q]:
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

    def run(self):
        """Built straight into the planned state (T7, chain_plan.py): an open band is built open, never closed first."""
        t0 = time.time()
        if getattr(self, "drape", None):  # (T13 C297: draped pieces: the held line built, the free cloth a start to fall from)
            from .chain_drape import build_drape
            build_drape(self, t0)
        elif self.roles.stand:  # (a stand collar: nothing turned over it, its own closure open or closed; T8 C289)
            from .chain_roles import build_stand
            build_stand(self, t0)
        elif self.wear["state"] == "open" and self.roles.band and self.roles.front:
            from .chain_plan import build_open
            build_open(self, t0)
        else:
            if self.wear["state"] == "open":
                raise ChainRefused("open wear needs a band and a front closure in the pattern: next: build it closed")
            self.stiff_stage()
            self.rings()
            self.reads["stiff_closed_s"] = round(time.time() - t0, 1)
            self.soft_net()
            self._rest_fall()
        self.reads["chains"] = self.chain_read(self.X)
        self.reads["seam_gap_mm"] = round(self.net.seam_gap(self.X), 3)
        self.reads["build_s"] = round(time.time() - t0, 1)
        return self.X

    def chain_read(self, X) -> dict:
        """Chains at X. A soft link with both ends sewn to a stiff part is gathered into it (a sleeve into its cuff):
        it may only be shorter; those are read apart."""
        net = self.net
        held = np.zeros(net.n, bool)
        held[net.root[self._stiff_mask()]] = True
        both = held[net.link_i] & held[net.link_j]
        rep = net.chain_report(X)
        l = np.linalg.norm(X[net.link_j] - X[net.link_i], axis=1)
        e = np.abs(l / np.maximum(net.link_L, 1e-9) - 1) * 100
        free = ~both
        rep["free_worst_pct"] = round(float(e[free].max()), 3) if free.any() else 0.0
        rep["free_p99_pct"] = round(float(np.percentile(e[free], 99)), 3) if free.any() else 0.0
        k = int(np.argmax(np.where(free, e, -1)))
        c = int(np.where(net.link_of_chain == k)[0][0])
        rep["free_worst_line"] = (f"{net.names[net.chain_piece[c]]} {'fold line' if net.chain_kind[c] else 'edge'} at flat "
                                  f"({net.uv[net.chain_v[c, 0], 0]:.3f}, {net.uv[net.chain_v[c, 0], 1]:.3f})"
                                  + self._near_point(int(net.link_i[k]), net.names[net.chain_piece[c]]))
        over = (l - net.link_L) / np.maximum(net.link_L, 1e-9) * 100
        rep["gathered_links"] = int(both.sum())
        rep["held_longest_over_pct"] = round(float(over[both].max()), 2) if both.any() else 0.0
        return rep

    def _near_point(self, v: int, piece: str) -> str:
        """(C278) the worst link named by the pattern point nearest it on its piece: flat coordinates alone don't say
        where to alter_pattern."""
        net = self.net
        pts = [(n.split(":", 1)[1], i) for n, i in (net.M.get("points") or {}).items()
               if isinstance(i, (int, np.integer)) and n.startswith(piece + ":")]
        if not pts:
            return ""
        d = [float(np.linalg.norm(net.uv[i] - net.uv[v])) for _, i in pts]
        j = int(np.argmin(d))
        return f", {d[j] * 1000:.0f} mm from {piece}:{pts[j][0]}"

    def gate_lengths(self):
        """Lengths have the last word: a free chain link past MAX_FREE_PCT is refused by piece and line."""
        c = self.chain_read(self.X)
        self.reads["chains"] = c
        if c["free_worst_pct"] > MAX_FREE_PCT:
            raise ChainRefused(f"a length can't hold: {c['free_worst_line']} is {c['free_worst_pct']} % off its cut (limit "
                               f"{MAX_FREE_PCT} %). next: the pattern can't make this line on this body: look_pattern, then "
                               "alter_pattern at that line, pattern_check, chain_garment again")

    # ---- 7. the hang
    def hold_mask(self):
        net = self.net
        h = self._stiff_mask().copy()
        if getattr(self, "extra_held", None) is not None:
            h |= self.extra_held
        return np.isin(net.root, net.root[h])

    def write_job(self, jd: Path, fabric: dict, frames: int = 144, name: str = "chain_garment"):
        """The ZOZO job: the soft cloth under gravity, stiff parts held, the whole body the collider. A start ZOZO would
        refuse is refused here by name: it is the chain build's fault, never fixed by cutting, pushing or holding."""
        from . import cloth_job as cj, cloth_zozo as cz, zozo_hang as zh
        net = self.net
        X = np.asarray(self.X, float)
        uv, F = net.uv, net.F
        bV, bT = self.body.V, self.body.T
        hold = self.hold_mask()
        whole = self._stiff_mask()
        lg = zh.legality(X, F, bV, bT)
        if not lg["ok"]:
            w = lg["worst"][0] if lg["worst"] else None
            nm = net.names[net.piece[w[1][0]]] if w else "?"
            who = {}
            pr = zh.contact_pairs(X, F, bV, bT, zh.BODY_OFFSET + 1e-9)
            for c in pr["cloth"]:
                k_ = net.names[net.piece[c[c >= 0][0]]]
                who[k_] = who.get(k_, 0) + 1
            raise ChainRefused(f"illegal start: {lg['illegal']} cloth / body pairs inside ZOZO's contact offset ({lg['by_kind']}), nearest "
                               f"{lg['min_mm']} mm, worst on {nm}; by piece {who}. next: this is a chain-build fault; report it, nothing is pushed or cut")
        lim = zh.woven_limit()
        flat = np.c_[uv, np.zeros(len(uv))]
        R = flat.copy()
        R[whole] = X[whole]
        ci = np.where(hold)[0].astype(np.int64)
        arrays = dict(X=X, uv=uv, F=F, sew=net.sew, stitch=np.asarray(net.M.get("stitch", np.zeros((0, 2))), np.int64).reshape(-1, 2),
                      stiff=np.clip(np.maximum(self.pat.stiff, whole.astype(float)), 0, 1), piece=net.piece.astype(np.int64),
                      pins=np.zeros(0, np.int64), bodyV=bV, bodyT=bT, carryIdx=ci, carryPoses=X[ci][None], rest=R,
                      restIdx=np.where(whole)[0].astype(np.int64))
        made = [p for p in net.names if whole[net.verts(p)].all()]
        cfg = {"fabric": fabric, "name": name, "placement": "smooth", "wraps": {}, "made": made, "strain_limit": lim}
        jc = cj.job_config(cfg, net.names)
        jc["stages"] = [{"name": "settle", "frames": int(frames), "gravity": 1, "sew": True, "self_collision": True, "fixed": [], "body": True}]
        jc["snap"] = 24
        jd = Path(jd)
        jd.mkdir(parents=True, exist_ok=True)
        np.savez(jd / "in.npz", **arrays)
        (jd / "job.json").write_text(json.dumps(jc, indent=1, default=cj._jsonable))
        ss = zh.start_strain(arrays, jc)
        if not ss["ok"]:
            raise ChainRefused(f"start past the strain limit: {ss['over']} of {ss['faces']} faces, by piece {ss.get('by_piece')}; worst "
                               f"{ss.get('worst')}. next: a chain-build fault; report it, the limit is not a setting")
        self.reads["hang_start"] = {"legal_min_mm": lg["min_mm"], "strain_ok": True, "held": int(hold.sum()), "frames": int(frames)}
        return jd

    def finish_hang(self, V):
        """ZOZO's result back into the build: seams welded (a held side wins), lengths the last word, the body a floor."""
        net = self.net
        rs = net.root
        Vb = np.asarray(V, float)
        hold = self.hold_mask()
        cnt = np.bincount(rs, minlength=net.n).astype(float)
        S = np.zeros((net.n, 3))
        np.add.at(S, rs, Vb)
        M = S / np.maximum(cnt, 1)[:, None]
        M = np.where(hold[:, None], self.X, M)
        moved = np.linalg.norm(M[rs] - self.X, axis=1)
        I2, J2, L2, E2, _, fl2, th = self.final_links
        fl2 = fl2[:1]  # (the body: ZOZO has kept the cloth under the held fall; a squeezed point there must not stall the lengths)
        held = np.zeros(net.n, bool)
        held[rs[hold]] = True
        self.reads["hang_moved_mm"] = {"p50": round(float(np.median(moved[~hold]) * 1e3), 1), "p95": round(float(np.percentile(moved[~hold], 95) * 1e3), 1),
                                       "max": round(float(moved[~hold].max() * 1e3), 1), "drop_mm": round(float((self.X[~hold, 2] - M[rs][~hold, 2]).mean() * 1e3), 1)}
        self.reads["after_hang_before_lengths"] = {"threads": th.report(M[rs]), "chains_free_worst_pct": self.chain_read(M[rs])["free_worst_pct"]}
        n_chain = len(self.net.link_i) + len(self.net.lines()[0]) + len(self._closure_ties())
        Z = M.copy()
        # lengths the last word, the threads with them: a chain-only pass tears the cloth between the chains
        rd = {}
        for rnd in range(4):
            Z, rd = project(Z, I2, J2, L2, E2, held, fl2, threads=th, iters=30, step=0.004)
            self.log(f"after hang {rnd}: {rd}")
        # the chains last, with their moves carried into the cloth between them (a chain pass alone tears it, C263). Lines may
        # shorten here: a strip curved both ways by the hang can't keep every line across it exact and its chains too
        Ec = E2[:n_chain] & (np.arange(n_chain) < len(self.net.link_i))
        chain_nodes = np.unique(np.r_[self.net.link_i, self.net.link_j])
        rd2 = {}
        for rnd in range(3):
            Z0 = Z.copy()
            Z, rd2 = project(Z, I2[:n_chain], J2[:n_chain], L2[:n_chain], Ec, held, fl2, iters=40, step=0.003)
            kn = held.copy()
            kn[chain_nodes] = True
            for p in self.roles.panels + self.roles.tubes:
                v = net.verts(p)
                Fp = net.F[np.all(net.piece[net.F] == net.pid(p), axis=1)]
                k_ = np.zeros(net.n, bool)
                k_[v] = kn[rs[v]]
                Zr, Z0r = Z[rs], Z0[rs]
                filled = cn.fill(Z0r, Zr, k_, net.uv, Fp, v)
                free_ = v[~k_[v]]
                Z[rs[free_]] = filled[free_]
            self.log(f"chains after hang {rnd}: {rd2}")
        self.reads["hang_last_lengths"] = {"all": rd, "chains": rd2}
        self.X = Z[rs]
        self.reads["threads"] = th.report(self.X)
        self.reads["chains"] = self.chain_read(self.X)
        self.reads["seam_gap_mm"] = round(net.seam_gap(self.X), 3)
        return self.X


# ---- the job: what the MCP tools run (a worker process, so a hang never blocks the server)
def load_garment(model: str, garment: str, spec: dict | None = None) -> tuple:
    """(Pattern, Body, fabric) of a saved garment: the draft meshed flat with fold lines as edges (cloth.build place_only);
    positions in the result are dropped by Pattern, never read."""
    from . import bending, cloth, pattern_form as pf, store
    spec = spec or store.load(model)
    g = json.loads(json.dumps(spec["cloth"][garment]))
    g["mesh_refine"] = pf.form_refine(g)
    src, _ = pf.form_source(model, garment, spec, g)
    res = cloth.build(cloth._garment_for_sim(g), src, f"{model}:{garment}", log=lambda *_: None, place_only=True)
    M, B = res["mesh"], res["pieces"]
    st = cloth.interfacing(B, M)
    # a stiff ring keeps a smooth section: its chords must not sag into the limb (L^2 / 8R over a 25 mm wrist)
    rings = [n for i, n in enumerate(M["names"]) if st[np.asarray(M["piece"]) == i].mean() > 0.95 and n not in ("collar", "stand")]
    rings = [n for n in rings if not any(f.get("piece") == n and f.get("kind") == "roll" for f in M.get("folds") or [])]
    if rings:
        g["mesh_refine"] = list(g["mesh_refine"]) + [{"piece": rings, "h": RING_H}]
        res = cloth.build(cloth._garment_for_sim(g), src, f"{model}:{garment}", log=lambda *_: None, place_only=True)
        M, B = res["mesh"], res["pieces"]
    radius = {f["name"]: float(f["radius"]) for f in (B.get("folds") or []) if isinstance(f, dict) and f.get("radius") and f.get("name")}
    pat = pattern_from_mesh(M, cloth.interfacing(B, M), bending.weights(B, M, g), radius)
    body = Body(np.asarray(res["body"].V, float), np.asarray(res["body"].T, np.int64),
                {k: np.asarray(v, float) if np.ndim(v) else float(v) for k, v in res["body"].at.items()})
    return pat, body, res.get("fabric") or cloth.fabric(g)


def job_dir(model: str, garment: str, wear: str) -> Path:
    from . import store
    d = store.HOME / model / "chain" / f"{garment}_{wear}"
    d.mkdir(parents=True, exist_ok=True)
    return d


RUNNING = ("queued", "building", "resuming", "built", "hanging", "hung")  # stages a live worker is in; the rest are its ends
BUILD_GB = 8.0  # the build's real peak (rss read per job: status "peak_gb"); the hang declares its own kind


def job_key(spec: dict, garment: str, wear: dict) -> str:
    """What a job answers for: the body, this garment, the wear (from the style plan, T7), and the build's code
    (store.BUILD_VERSION: a job built by older stages is built again; C280). Another garment on the model doesn't change it."""
    from . import store
    rest = {k: v for k, v in spec.items() if k != "cloth"}
    wear = {k: v for k, v in wear.items() if k not in ("waive", "resume")}  # (a waiver re-reads the saved build, T2)
    return hashlib.sha1(json.dumps([rest, spec["cloth"][garment], wear, store.BUILD_VERSION], sort_keys=True,
                                   default=str).encode()).hexdigest()[:16]


def write_status(d: Path, **kw):
    p = Path(d) / "status.json"
    st = json.loads(p.read_text()) if p.exists() else {}
    st.update(kw)
    t = Path(d) / f"status.{os.getpid()}.tmp"
    t.write_text(json.dumps(st, default=str))
    t.replace(p)


_status = write_status


def status(d: Path) -> dict:
    p = Path(d) / "status.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _alive(pid) -> bool:
    try:
        text = Path(f"/proc/{int(pid)}/status").read_text()
    except (OSError, TypeError, ValueError):
        return False
    return not re.search(r"^State:\s+Z", text, re.M)  # (a dead child the server hasn't reaped is not a worker)


def live_status(d: Path) -> dict:
    """status(), with a worker that died mid-job (OOM kill, reboot) read as failed: its stage would say running for ever."""
    st = status(d)
    if st.get("stage") in RUNNING and "pid" in st and not _alive(st["pid"]) and status(d).get("stage") in RUNNING:
        tail = (Path(d) / "worker.log").read_text(errors="replace")[-300:] if (Path(d) / "worker.log").exists() else ""
        write_status(d, stage="failed", error=f"the worker died at stage {st['stage']} ({tail.strip() or 'no output'})")
        st = status(d)
    return st


def elapsed(st: dict) -> int:
    return int(time.time() - float(st.get("t0") or time.time()))


def worker(model: str, garment: str, wear: dict):
    """Build, structure, pre-sim approval (step 7a, chain_presim.py), then hang. Every stage writes its numbers to
    status.json; a refusal is a result, not a crash. wear["resume"]: the build is loaded from built.pkl, never rebuilt."""
    from . import chain_drape as cd, chain_presim as cp, chain_structure as cs, resources, zozo_hang as zh
    d = job_dir(model, garment, wear["state"])
    resume = wear.get("resume") or ""  # ("approved" / "waiver": from built.pkl, see chain_presim)
    _status(d, stage="resuming" if resume else "building", pid=os.getpid())
    note = lambda m: _status(d, note=str(m)[:200])
    waive = dict(wear.get("waive") or {})
    wear = {k: v for k, v in wear.items() if k not in ("waive", "resume")}
    import pickle
    try:
        if resume:  # (approved, or a waiver: the saved build, as it was)
            b, r = cp.load_build(d)
            pat, body, fabric = b.pat, b.body, r.get("fabric") or {}
        else:
            with resources.heavy(f"chain build {model}:{garment} {wear['state']}", gb=BUILD_GB, log=note):
                pat, body, fabric = load_garment(model, garment)
                if wear.get("under"):  # (worn over another garment: the body + its surface + its details, T9)
                    from . import chain_layers as cl
                    body = cl.layered_body(model, garment, body, wear["under"], log=note)
                b = GarmentBuild(pat, body, wear, log=lambda *_: None)
                b.drape = cd.info(model, garment, b.net)  # (T13: the plan's draped pieces, else None)
                b.run()
            bid = cp.save_build(d, b, pat, body, fabric)
            _status(d, stage="built", reads=b.reads, note="", build_s=elapsed(status(d)), peak_gb=round(_peak_gb(), 1),
                    build_id=bid, build_threads=b.reads.get("threads"))
        sc = status(d).get("structure") if resume == "approved" else None  # (approved as read: not read again)
        if not sc:
            sc = cs.check(b.X, pat.M, body.V, body.T, body.at, dict(wear, drape_reads=cd.build_reads(b)),
                          cs.load_plan(model, garment), waive)  # (C279, C286; T13: draped rows wait for the hang)
            sc["reads"].pop("front_gap_profile", None)
        _status(d, structure=sc)
        from . import chain_layers as cl  # (inside the garment under it, then the lengths: T9)
        cl.gate(b, body, put=lambda **kw: _status(d, **kw), refused=ChainRefused, d=d)  # (a refusal is answered first; structure rows stay beside it)
        if not cs.passed(sc):
            _status(d, stage="structure_failed")
            return
        gr_msg = gr_from_chain(model, garment, wear["state"], d, dict(status(d), stage="presim"))
        go, why, msg = cp.gate_presim(model, garment, wear["state"], d, status(d))
        if not go:  # (step 7a: nothing is hung that wasn't approved built)
            sheet = None
            try:
                from . import garment_record as gr
                sheet = str(gr.sheet(model, garment))
            except Exception:  # (the sheet is a look; its failure never loses the build)
                pass
            _status(d, stage=cp.AWAIT, presim=why, sheet=sheet, record="; ".join(m for m in (gr_msg, msg) if m))
            return
        jd = b.write_job(d / "zozo", fabric, name=f"chain:{model}:{garment}")
        _status(d, stage="hanging", reads=b.reads, presim=why)
        out, _ = zh.run(jd, log=note, timeout=3000)
        X = b.finish_hang(out["V"] if hasattr(out, "keys") else out[0])
        pickle.dump({"X": X, "M": pat.M, "bV": body.V, "bT": body.T, "reads": b.reads}, open(d / "final.pkl", "wb"))
        _status(d, stage="hung", reads=b.reads, note="")  # (a refusal below still leaves the hung result to look at)
        b.gate_lengths()
        if getattr(b, "drape", None):  # (T13: step 8's gate gains the draped rows, read on the hung cloth)
            hs = cd.hang_check(X, pat.M, body, cs.load_plan(model, garment), b.drape, waive)
            _status(d, hang_structure=hs)
            if not cs.passed(hs):
                _status(d, stage="hang_rows_failed", reads=b.reads)
                return
        _status(d, stage="done", reads=b.reads)
    except (ChainRefused, cd.DrapeRefused) as e:
        _status(d, stage="refused", refused=str(e))
    except Exception as e:  # (a crash is reported as one, with what it was doing)
        import traceback
        _status(d, stage="failed", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:])
    finally:  # (steps 5, 6 and 8 of the garment record; a refusal of the record's order is noted, the job stands)
        if status(d).get("stage") != cp.AWAIT:
            msg = gr_from_chain(model, garment, wear["state"], d, status(d))
            if msg:
                _status(d, record=msg)


def gr_from_chain(model: str, garment: str, wear: str, d: Path, st: dict) -> str:
    try:
        from . import garment_record as gr
        return gr.from_chain(model, garment, wear, d, st)
    except Exception as e:  # (the record never breaks a build)
        return f"record: not written: {type(e).__name__}: {e}"


def _peak_gb() -> float:
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def render_views(X, M, bV, bT, out: str, views=None, focus: str | None = None, size: int = 640, log=print) -> list:
    """Sewn vertices joined, every piece facing outward. focus None: the whole figure, on the body; "neck": the collar
    close, on the body; a piece's name: that piece ALONE, large, four sides. Returns [(view, path)]."""
    from . import cloth, resources
    X = np.asarray(X, float)
    F = joined_faces(X, M, bV, bT)
    names = list(M["names"])
    pc = np.asarray(M["piece"])
    cloth_part = {"name": "shirt", "V": X, "F": F, "color": "#a9c4e6"}
    body_part = {"name": "body", "V": bV, "F": bT, "color": "#c4bcb4"}
    if focus in names:
        Fp = np.asarray(M["F"])[pc[np.asarray(M["F"])[:, 0]] == names.index(focus)]
        ids = np.unique(Fp)
        P = X[ids]
        parts = [dict(cloth_part, F=joined_faces(X, M, bV, bT)[pc[np.asarray(M["F"])[:, 0]] == names.index(focus)])]
        lo, hi = P.min(0), P.max(0)
        c, r = 0.5 * (lo + hi), 0.55 * float((hi - lo).max()) + 0.005
        box = [(c - r).tolist(), (c + r).tolist()]
        views = views or [("front", [0, -1, 0.1]), ("back", [0, 1, 0.1]), ("left", [1, 0, 0.1]), ("right", [-1, 0, 0.1])]
    elif focus == "neck":
        z = float(X[pc == names.index(next(n for n in names if n in ("collar", "stand")) if any(n in names for n in ("collar", "stand")) else names[0]), 2].mean())
        parts = [body_part, cloth_part]
        box = [[-0.14, -0.2, z - 0.1], [0.14, 0.09, z + 0.09]]
        views = views or [("front", [0, -1, 0.1]), ("three", [-0.6, -0.8, 0.15]), ("side", [-1, 0, 0.05]), ("back", [0, 1, 0.3])]
    else:
        parts = [body_part, cloth_part]
        lo, hi = X.min(0), X.max(0)
        box = [[lo[0] - 0.05, lo[1] - 0.05, lo[2] - 0.03], [hi[0] + 0.05, hi[1] + 0.05, float(np.asarray(bV)[:, 2].max()) + 0.02]]
        views = views or [("front", [0, -1, 0.05]), ("three", [-0.6, -0.8, 0.1]), ("side", [-1, 0, 0.05]), ("back", [0, 1, 0.05])]
    res = []
    with resources.heavy(f"look chain {Path(out).name}", gb=3.0, gpu=True, log=log):
        for nm, dv in views:
            p = cloth.render(parts, f"{out}_{nm}", views=[{"name": nm, "dir": list(dv)}], resolution=size, box=box)[0]
            res.append((nm, str(p)))
    return res


if __name__ == "__main__":
    import sys
    worker(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
