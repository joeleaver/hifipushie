"""STEP 4 of drape first, the TOILE (docs/proposals/drape_first.md): the garment's 3D surface on the body, built from the
approved steps 0-3 and the agent's declaration, never from a garment's name. Spikes R1 / R2 / R2b (C489-C491) made into
a general builder; toile_style.py adds the opening and turned flaps, toile_gate.py the rows and the look, toile_tool.py
the record.

THE BODY FIELD: the body's signed distance on a grid (GRID_H), closed by CLOSE_M (the hollows between the shoulder
blades and under the buttocks bridged), smoothed; round the neck not closed (the neckline stays the body's).
EASE: the field moved out by k(z) w(theta): k per step-0 fit level, CALIBRATED until the toile's tape at that level (the
convex hull of its section, the arms left out) equals step 0's planned garment girth; w = W_SIDE + (1 - W_SIDE) cos^2
from the front (front and back take more ease than the side seams). Above the top level the ease tapers to
EASE_ABOVE_MM (the shoulders: the cloth lies on them).
SLEEVES (declared): a smooth tapered TUBE round the arm, never the arm's offset: its axis a quadratic through the arm's
section centres, its radius the section's tape / 2 pi + the declared ease (top -> wrist), made monotone from the wrist up
(a sleeve tapers; it does not follow the biceps / forearm) and held at the biceps above it, swelling the declared crown
from the biceps up to the shoulder; the tube runs up into the shoulder (TUBE_INTO_M) and the ARMHOLE CONE (toile_geom,
C491: the body's arm-root loop scaled about the shoulder point to the declared armhole length, carried out from the
shoulder joint) cuts its crown. The torso is pushed off the arm only inside the cone above the underarm, from
UNDER_PUSH_M outside it below (an eased tube fuses with the torso under the arm into a web). Below the underarm the
tube and torso meet at a crease (their blend narrows to UNDER_BLEND_M): the sleeve's underarm is a tube's underside, not
a web to the body (R3d: the web made the cap a saddle that flattened 2.5-8.8 % SHORT of its armhole).
THE CAP'S EASE (C496): a tailor eases the cap into the armhole: the sleeve's crown stands proud of the armhole as a
dome. The armhole line itself is untouched (the field changes only inside the cone, from zero at the cone with zero
slope); inside it a roll CAP_BAND_M wide rises by CAP_RISE x the ease x the tube's top radius, full over the crown and
nothing at the underarm (cos of the angle round the cone from the shoulder point, CAP_UNDER_COS). Flattened, the dome's
lines parallel to the seam are longer than the seam: the cap comes out longer than its armhole by about the ease
(`sleeves.cap_ease_pct`, default CAP_EASE_PCT: a set-in tailored sleeve's 6-9 %).
HANG (declared hang_from: a step-0 fit level or "none"): below that level the torso's section is that level's, straight
down, plus a flare meeting the lowest level's planned girth at the hem (a jacket hangs from the seat).
PAD (declared): a wedge of the declared thickness under the shell (toile_geom.pad_thickness), its own part, the shell
over it at PAD_GAP_M.
The toile is cut at the neckline (the neck tape's loop), at the sleeve hem (a step-0 height) square to the sleeve, and at
the hem (step 0's hem height: the grid's floor). Metres; Blender axes; the body's left is +X."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import ConvexHull

from .toile_geom import Cone, largest, outward, length, pad_thickness, resample, smin, smooth01

GRID_H = 0.006        # m: the field's grid
CLOSE_M = 0.025       # m: the body's hollows bridged (a closing)
W_SIDE = 0.35         # the ease's weight at the side (1 at front and back)
EASE_ABOVE_MM = (12.0, 6.0)  # the ease 11 / 19 cm above the top fit level (the shoulders)
TUBE_INTO_M = 0.06    # the sleeve tube's axis starts this far up into the shoulder
BICEPS_AT = 0.30      # the biceps: this share down the arm
CONE_BACK_M = 0.05    # the cone's apex: this far in along the arm's axis from the shoulder point
UNDER_PUSH_M = 0.02   # below the underarm the arm is pushed out of the torso from this far outside the cone
PAD_GAP_M = 0.002     # the shell over the pad
MIN_GAP_M = 0.002     # the cloth never nearer the body than this (the union with the body's offset)
UNDER_BLEND_M = 0.004  # m: the tube / torso blend below the underarm (above it 0.015)
CAP_EASE_PCT = 7.5    # % a tailored set-in sleeve's cap ease when the declaration states none (6-9 %)
CAP_BAND_M = 0.05     # the cap's roll: this wide inside the armhole cone
CAP_RISE = 2.0        # its rise = CAP_RISE x ease x the tube's top radius (ARAP gives the boundary part of the roll)
CAP_UNDER_COS = -0.35  # the roll fades to nothing where cos(angle from the shoulder point) reaches this (underarm)
CALIBRATE = 5         # ease calibration passes
MIR = np.array([-1.0, 1, 1])


@dataclass
class Inputs:
    """What the toile reads: the body (V, T triangles), step 3's tapes {name: points (n, 3)}, step 0's fit levels
    {name: (z m, planned garment girth m)} and heights {name: z m}, step 2's traces {id: {"xz", "corners"}} and row
    marks {id: (n, 2) xz} in model metres, and the declaration."""
    V: np.ndarray
    T: np.ndarray
    tapes: dict
    levels: dict
    heights: dict
    decl: dict
    traces: dict = field(default_factory=dict)
    marks: dict = field(default_factory=dict)
    wrists: dict = field(default_factory=dict)  # {"photo": [x, z] from step 2's body marks, "model": [x, z]}, folded +x


def folded(P):
    return P * np.where(P[:, :1] < 0, MIR, 1)


class Toile:
    """build() fills: F (the field), xs / ys / zs, FD (its interpolator), cone, arm geometry, info, meshes."""

    def __init__(self, inp: Inputs, log=print):
        from .chain_net import Contact
        self.inp, self.log, self.d = inp, log, inp.decl
        self.parts = set(self.d.get("parts") or [])
        self.CT = Contact(np.asarray(inp.V, float), np.asarray(inp.T, np.int64))
        self.info = {"parts": ["body"] + sorted(self.parts)}

    # ---------------------------------------------------------------- the body field
    def grid(self):
        inp, h = self.inp, GRID_H
        self.hem = float(inp.heights["hem"])
        neck = np.asarray(inp.tapes["neck"], float)
        ztop = float(neck[:, 2].max()) + 0.06
        V = np.asarray(inp.V, float)
        m = (V[:, 2] > self.hem - 0.02) & (V[:, 2] < ztop)
        self.xs = np.arange(-np.abs(V[m, 0]).max() - 0.07, np.abs(V[m, 0]).max() + 0.07 + h / 2, h)
        self.ys = np.arange(V[m, 1].min() - 0.07, V[m, 1].max() + 0.07 + h / 2, h)
        self.zs = np.arange(self.hem, ztop + h / 2, h)
        G = np.stack(np.meshgrid(self.xs, self.ys, self.zs, indexing="ij"), -1).reshape(-1, 3)
        self.G = G
        shape = (len(self.xs), len(self.ys), len(self.zs))
        sd = np.empty(len(G))
        for i in range(0, len(G), 200000):
            sd[i:i + 200000] = self.CT.query(G[i:i + 200000])[0]
        sd = sd.reshape(shape)
        dil = sd <= CLOSE_M
        sdc = ndimage.gaussian_filter(np.where(dil, CLOSE_M - ndimage.distance_transform_edt(dil) * h, sd), 1.0)
        # no closing round the neck (above the neckline's lowest point - 4 cm, within 11 cm of the neck's axis)
        self.cn = neck[:, :2].mean(0)
        GX, GY, GZ = (G[:, i].reshape(shape) for i in range(3))
        wn = np.clip((0.11 - np.hypot(GX - self.cn[0], GY - self.cn[1])) / 0.03, 0, 1) * \
            np.clip((GZ - (neck[:, 2].min() - 0.04)) / 0.03, 0, 1)
        self.sdc = sdc + (ndimage.gaussian_filter(sd, 0.7) - sdc) * wn
        self.sd = sd
        self.shape = shape
        chest = np.asarray(inp.tapes["chest"], float)
        self.yc = float(chest[:, 1].mean())
        self.log(f"body field {shape}")

    def onto_body(self, P, gap=0.0, passes=4):
        P = np.array(P, float)
        for _ in range(passes):
            s, n = self.CT.query(P)
            P = P - (s - gap)[:, None] * n
        return P

    # ---------------------------------------------------------------- the arm: axis, armhole cone, the tube
    def arm(self):
        tp = self.inp.tapes
        self.sh = folded(np.asarray(tp["shoulderToWrist"], float)[:1])[0]
        wr = folded(np.asarray(tp["wrist"], float)).mean(0)
        A = wr - self.sh
        self.alen = float(np.linalg.norm(A))
        self.A = A / self.alen
        af, ab = folded(np.asarray(tp["armhole_front"], float)), folded(np.asarray(tp["armhole_back"], float))
        self.sp = af[0]
        loop = np.r_[af, ab[::-1][1:]]
        root = length(loop)
        want = float(self.d["armhole"]["length_mm"]) / 1000
        loop = self.onto_body(resample(self.sp + want / root * (loop - self.sp), 0.005))
        self.armhole = loop
        self.cone = Cone(self.sh, self.A, loop, back=CONE_BACK_M)
        self.z_ua = float(loop[:, 2].min())
        self.info["armhole"] = {"arm_root_mm": round(root * 1000, 1), "declared_mm": round(want * 1000, 1),
                                "on_body_mm": round(length(np.r_[loop, loop[:1]]) * 1000, 1),
                                "underarm_z": round(self.z_ua, 3)}
        ca = loop.mean(0)
        na = np.linalg.svd(loop - ca)[2][2]
        na = na if na @ (self.sh - np.array([0, 0, self.sh[2]])) > 0 else -na
        Q = np.asarray(self.inp.V, float)
        Q = Q[Q[:, 0] > 0]
        tq = (Q - self.sh) @ self.A
        dax = np.linalg.norm(Q - (self.sh + np.clip(tq, 0, self.alen)[:, None] * self.A), axis=1)
        sel = ((Q - ca) @ na > 0.01) & (tq > 0) & (tq < self.alen) & (dax < 0.10)
        Q, tq = Q[sel], tq[sel]
        e1 = np.cross(self.A, [0, 1.0, 0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(self.A, e1)
        Cs, Ts, Gr = [], [], []
        for b0, b1 in zip(*(lambda b: (b[:-1], b[1:]))(np.linspace(tq.min(), self.alen, 15))):
            m = (tq >= b0) & (tq < b1)
            if m.sum() < 30:
                continue
            q = Q[m]
            p2 = np.c_[q @ e1, q @ e2]
            hull = ConvexHull(p2)
            c2 = p2[hull.vertices].mean(0)
            Cs.append(c2[0] * e1 + c2[1] * e2 + (q @ self.A).mean() * self.A)
            Ts.append(float((Cs[-1] - self.sh) @ self.A))
            Gr.append(hull.area)
        if len(Ts) < 4:
            raise ValueError("toile: the arm has too few sections outside the armhole to lay a sleeve (an arm against "
                             "the body, or the armhole declared too long)")
        Cs, Ts, Gr = np.array(Cs), np.array(Ts), np.array(Gr)
        cf = [np.polyfit(Ts, Cs[:, i], 2) for i in range(3)]
        self.tax = np.r_[-TUBE_INTO_M, Ts, self.alen + 0.04]
        self.CAX = np.c_[[np.polyval(c, self.tax) for c in cf]].T
        sl = self.d.get("sleeves") or {}
        e_top, e_wr = (np.asarray(sl.get("ease_mm", (0, 0)), float) / 1000).tolist()
        raw = Gr / (2 * np.pi) + e_top + (e_wr - e_top) * np.clip(Ts / self.alen, 0, 1)
        mono = np.maximum.accumulate(raw[::-1])[::-1]
        kb = int(np.argmin(np.abs(Ts - BICEPS_AT * self.alen)))
        mono[:kb] = mono[kb]
        sm = np.convolve(np.r_[mono[0], mono, mono[-1]], [0.25, 0.5, 0.25], "valid")
        crown = float(sl.get("crown_mm", 0)) / 1000
        self.RAX = np.r_[sm[0], sm, sm[-1]] + crown * np.clip((Ts[kb] - self.tax) / max(Ts[kb], 1e-3), 0, 1)
        if "sleeves" in self.parts:
            self.info["sleeve"] = {"t_mm": np.round(Ts * 1000).tolist(), "arm_tape_mm": np.round(Gr * 1000, 1).tolist(),
                                   "tube_round_mm": np.round(2 * np.pi * sm * 1000, 1).tolist(),
                                   "ease_mm": [e_top * 1000, e_wr * 1000], "crown_mm": crown * 1000}

    def axis_param(self, P):
        best, rr = np.full(len(P), np.inf), np.zeros(len(P))
        for j in range(len(self.CAX) - 1):
            dv = self.CAX[j + 1] - self.CAX[j]
            u = np.clip(((P - self.CAX[j]) @ dv) / (dv @ dv), 0, 1)
            dist = np.linalg.norm(P - (self.CAX[j] + u[:, None] * dv), axis=1)
            r = self.RAX[j] + u * (self.RAX[j + 1] - self.RAX[j])
            b = dist - r < best - rr if j else np.ones(len(P), bool)
            best, rr = np.where(b, dist, best), np.where(b, r, rr)
        return best, rr

    def tube(self, P):
        Q = folded(P)
        dist, r = self.axis_param(Q)
        return np.maximum(dist - r, -0.015 - self.cone.sdist(Q))

    def armness(self, P, shift=0.0):
        Q = folded(np.atleast_2d(P))
        t = np.clip((Q - self.sh) @ self.A, 0, self.alen)
        dx = np.linalg.norm(Q - (self.sh + t[:, None] * self.A), axis=1)
        return smooth01((self.cone.sdist(Q) - shift) / 0.04 + 0.5) * np.clip((0.13 - dx) / 0.03, 0, 1)

    # ---------------------------------------------------------------- ease, calibrated per level
    def girth_slice(self, Fs, z):
        """The tape round the field's section at z (its convex hull), the arms left out: metres."""
        from skimage import measure
        C = measure.find_contours(Fs, 0)
        if not C:
            return 0.0, 0.0
        Q = np.concatenate([np.c_[np.interp(c[:, 0], np.arange(len(self.xs)), self.xs),
                                  np.interp(c[:, 1], np.arange(len(self.ys)), self.ys)] for c in C])
        Q = Q[self.armness(np.c_[Q, np.full(len(Q), z)]) < 0.5]
        return (ConvexHull(Q).area, float(np.abs(Q[:, 0]).max())) if len(Q) > 3 else (0.0, 0.0)

    def kz(self, z):
        return int(np.argmin(np.abs(self.zs - max(z, self.hem + 0.003))))

    def ease_fields(self):
        """The calibrated torso + sleeves field (before hang and pad)."""
        G, sh = self.G, self.shape
        th = np.arctan2(G[:, 0], -(G[:, 1] - self.yc))
        W = (W_SIDE + (1 - W_SIDE) * np.cos(th) ** 2).reshape(sh)
        Tb = np.full(len(G), 1.0)
        Ar = np.empty(len(G))
        for i in range(0, len(G), 200000):
            P = G[i:i + 200000]
            if "sleeves" in self.parts:
                Tb[i:i + 200000] = self.tube(P)
            below = smooth01((self.z_ua - P[:, 2]) / 0.03)
            Ar[i:i + 200000] = np.maximum(self.armness(P, UNDER_PUSH_M), self.armness(P, -UNDER_PUSH_M) * below)
        Tb, Ar = Tb.reshape(sh), Ar.reshape(sh)
        kb = 0.015 - (0.015 - UNDER_BLEND_M) * smooth01((self.z_ua - self.zs[None, None, :]) / 0.03)
        hang = self.d.get("hang_from")
        z_hang = self.inp.levels[hang][0] if hang not in (None, "none") else -np.inf
        cal = sorted((z, n) for n, (z, _) in self.inp.levels.items() if z >= z_hang - 1e-6)
        if not cal:
            raise ValueError("toile: no step-0 fit level at or above hang_from to set the ease by")
        k = {n: (self.inp.levels[n][1] - self.girth_slice(self.sdc[:, :, self.kz(z)], z)[0]) / (2 * np.pi * 0.675)
             for z, n in cal}
        top = cal[-1][0]
        ZS = self.zs[None, None, :]
        for it in range(CALIBRATE):
            KZ = [z for z, _ in cal] + [top + 0.11, top + 0.19]
            KV = [k[n] for _, n in cal] + [EASE_ABOVE_MM[0] / 1000, EASE_ABOVE_MM[1] / 1000]
            E = np.interp(ZS, KZ, KV) * W
            Ft = ndimage.gaussian_filter(self.sdc - E, 0.8) + 0.08 * Ar
            F0 = smin(Ft, Tb, kb) if "sleeves" in self.parts else Ft
            got = {n: self.girth_slice(F0[:, :, self.kz(z)], z)[0] for z, n in cal}
            for z, n in cal:
                k[n] += (self.inp.levels[n][1] - got[n]) / (2 * np.pi * 0.675)
        self.info["ease_k_mm"] = {n: round(k[n] * 1000, 1) for _, n in cal}
        self.z_hang = z_hang
        return self.crown(F0) if "sleeves" in self.parts else F0

    def crown(self, F0):
        """The cap's ease (module doc): the field pulled out inside the armhole cone over the crown."""
        pct = float((self.d.get("sleeves") or {}).get("cap_ease_pct", CAP_EASE_PCT))
        rise = CAP_RISE * pct / 100 * float(self.RAX[1])
        out = np.empty(len(self.G))
        for i in range(0, len(self.G), 200000):
            Q = folded(self.G[i:i + 200000])
            s = self.cone.sdist(Q)
            ps = self.cone.polar(Q)[0] - self.cone.polar(self.sp)[0][0]
            t = np.clip((Q - self.sh) @ self.A, 0, self.alen)
            dx = np.linalg.norm(Q - (self.sh + t[:, None] * self.A), axis=1)
            band = np.where((s > 0) & (s < CAP_BAND_M), np.sin(np.pi * np.clip(s, 0, CAP_BAND_M) / CAP_BAND_M) ** 2, 0.0)
            out[i:i + 200000] = rise * band * smooth01((np.cos(ps) - CAP_UNDER_COS) / (1 - CAP_UNDER_COS)) * \
                np.clip((0.16 - dx) / 0.03, 0, 1)
        self.info["sleeve"]["cap"] = {"ease_pct": pct, "rise_mm": round(rise * 1000, 1), "band_mm": CAP_BAND_M * 1000,
                                      "underarm_blend_mm": UNDER_BLEND_M * 1000}
        return F0 - out.reshape(self.shape)

    # ---------------------------------------------------------------- hang below a level, the pad
    def hang(self, F0):
        if not np.isfinite(self.z_hang):
            return F0
        ks = self.kz(self.z_hang)
        g_seat, xt = self.girth_slice(F0[:, :, ks], self.zs[ks])
        cols = (np.abs(self.xs) <= xt + 0.02)[:, None]
        SEAT = np.where(cols, F0[:, :, ks], 1.0)
        below = [(z, n) for n, (z, _) in self.inp.levels.items() if z < self.z_hang - 1e-6]
        flare, F_in = 0.0, F0.copy()
        if below:
            zl, nl = min(below)
            flare = max(0.0, (self.inp.levels[nl][1] - g_seat) / (2 * np.pi)) / max(self.zs[ks] - max(zl, self.hem), 1e-3)
        for it in range(1 + CALIBRATE * bool(below)):  # (the flare calibrated where the gate reads that level's tape)
            F0 = F_in.copy()
            for kk in range(ks):
                F0[:, :, kk] = np.where(cols, SEAT - flare * (self.zs[ks] - self.zs[kk]), F_in[:, :, kk])
            if not below or it == CALIBRATE:
                break
            zr = max(zl, self.hem + 0.004)
            kr = self.kz(zr)
            short = self.inp.levels[nl][1] - self.girth_slice(np.where(cols, F0[:, :, kr], 1.0), self.zs[kr])[0]  # (the hands beside it left out)
            flare = max(0.0, flare + short / (2 * np.pi) / max(self.zs[ks] - self.zs[kr], 1e-3))
        self.info["hang"] = {"from": self.d.get("hang_from"), "z": round(float(self.zs[ks]), 3),
                             "round_mm": round(g_seat * 1000, 1), "flare_mm_per_m": round(flare * 1000, 1)}
        return F0

    def pad(self, F0):
        neck = folded(np.asarray(self.inp.tapes["neck"], float))
        hps = neck[np.argmin(np.linalg.norm(neck[:, :2] - self.sp[:2], axis=1))]
        SH = self.onto_body(np.linspace(hps, self.sp, 30))
        o = np.argsort(SH[:, 0])
        self.y_sh = lambda x: np.interp(x, SH[o, 0], SH[o, 1])
        self.z_sh = lambda x: np.interp(x, SH[o, 0], SH[o, 2])
        self.shoulder_line = SH
        self.PADF = None
        if "pad" not in self.parts:
            return F0
        T = float(self.d["pad"]["thickness_mm"]) / 1000
        TH = np.concatenate([pad_thickness(self.G[i:i + 200000], self.sp[0], self.y_sh, self.z_sh, T)
                             for i in range(0, len(self.G), 200000)]).reshape(self.shape)
        self.PADF = np.maximum(F0 - TH, -F0)  # the pad's own solid: from the shell's inside out to its thickness
        self.info["pad"] = {"thickness_mm": T * 1000, "kind": "a wedge under the shell, its own part"}
        return F0 - (TH + PAD_GAP_M * smooth01(TH / 0.002))

    # ---------------------------------------------------------------- the field's surface
    def grad(self, P, e=1e-3):
        g = np.stack([(self.FD(P + e * np.eye(3)[i]) - self.FD(P - e * np.eye(3)[i])) / (2 * e) for i in range(3)], 1)
        return g / (np.linalg.norm(g, axis=1, keepdims=True) + 1e-12)

    def onto(self, P):
        n, t = self.grad(P), np.zeros(len(P))
        for _ in range(8):
            f = self.FD(P + t[:, None] * n)
            df = (self.FD(P + (t + 1e-3)[:, None] * n) - f) / 1e-3
            t = t - f / np.where(np.abs(df) > 0.1, df, 1.0)
        return P + t[:, None] * n

    def front_hit(self, x, z):
        """The toile seen from the front: the first surface point along +y at (x, z)."""
        yy = np.arange(self.ys[0], self.yc, 0.002)
        out = []
        for xi, zi in zip(np.atleast_1d(x), np.atleast_1d(z)):
            f = self.FD(np.c_[np.full(len(yy), xi), yy, np.full(len(yy), zi)])
            k = max(1, int(np.argmax(f < 0)))
            out.append([xi, yy[k - 1] + 0.002 * f[k - 1] / (f[k - 1] - f[k] + 1e-12), zi])
        return self.onto(np.array(out))

    def mesh(self, Fd):
        from skimage import measure
        V, F, _, _ = measure.marching_cubes(Fd, 0.0, spacing=(GRID_H,) * 3)
        V, F = largest(V + np.array([self.xs[0], self.ys[0], self.zs[0]]), F)
        return V, outward(V, F)

    def build(self):
        from . import toile_style
        self.grid()
        self.arm()
        F0 = self.hang(self.ease_fields())
        # nothing inside the body: where the arm's push (or a hollow's smoothing) took the cloth into the body, it lies
        # on the body at MIN_GAP_M instead (R2b: 14 mm in at the underarm; the skin showed at the front shoulder)
        self.F = np.minimum(self.pad(F0), self.sd - MIN_GAP_M)
        self.FD = RegularGridInterpolator((self.xs, self.ys, self.zs), self.F, bounds_error=False, fill_value=1.0)
        V, F = self.mesh(self.F)
        self.log(f"meshed {len(V)} v")
        self.meshes = toile_style.cut(self, V, F)
        if self.PADF is not None:
            Vp, Fp = self.mesh(self.PADF)
            keep = Vp[Fp].mean(1)[:, 0] > 0
            Vp, Fp = largest(Vp, Fp[keep])
            self.meshes["pad.L"] = (Vp, Fp)
            self.meshes["pad.R"] = (Vp * MIR, Fp[:, ::-1])
            self.info["pad"]["piece_bbox_mm"] = np.round((Vp.max(0) - Vp.min(0)) * 1000, 1).tolist()
        return self
