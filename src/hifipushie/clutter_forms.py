"""The forms as fields: Stone, Wood, Bush. Part of clutter (clutter.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import noise

# ------------------------------------------------------------------------------------------------------- the forms
def _smax(vals, k):
    out = vals[0]
    for v in vals[1:]:
        if np.ndim(k) == 0 and k <= 0:
            out = np.maximum(out, v)
        else:
            h = np.clip(0.5 + 0.5 * (v - out) / k, 0, 1)
            out = out * (1 - h) + v * h + k * h * (1 - h)
    return out


def _rot(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def _u(rng, r):
    return float(rng.uniform(r[0], r[1])) if isinstance(r, (list, tuple)) else float(r)


class Stone:
    """One loose block. Its faces are planes at oblique angles round an ellipsoid of three unequal axes (a loose block
    broke along three or four joint sets at random obliquity, never a box), a pair of off-parallel bedding faces
    (`bedded`), one or two corners broken off deep and several shallow chips; met in a smooth max whose radius grows
    upward (tops weather rounder than undersides), wider low than high (`taper`: a stable base), blended toward a
    bent ellipsoid (`round`: water-worn; `bend`: a bean), with thin partings along tilted beds (`beds`), maybe a
    split (`split`) and a dent (`dent`)."""

    def __init__(self, rng, form, size=1.0, centre=(0, 0, 0), flat=False):
        f = form
        self.size = size
        ay, az = _u(rng, f["aspect"][0]), _u(rng, f["aspect"][1])
        self.half = 0.5 * size * np.array([1.0, ay, az])
        self.c = np.asarray(centre, float)
        t = f["tumble"] * (0.3 if flat else 1.0)
        ax = rng.normal(0, 1, 3)
        ax[2] *= 0.3
        self.R = _rot([0, 0, 1], rng.uniform(0, 360)) @ _rot(ax / np.linalg.norm(ax), rng.uniform(-t, t))
        a, b, c = self.half
        N, D = [], []

        def support(n):  # the ellipsoid's reach along n
            return float(np.linalg.norm(np.asarray(n) * self.half))

        def plane(n, share):
            n = np.asarray(n, float) / np.linalg.norm(n)
            N.append(n)
            D.append(support(n) * share)
        # bedding: a top and an underside, off parallel
        dip, daz = math.radians(_u(rng, f["dip"])), rng.uniform(0, 2 * math.pi)
        self.bed_n = np.array([math.sin(dip) * math.cos(daz), math.sin(dip) * math.sin(daz), math.cos(dip)])
        if rng.uniform() < f["bedded"]:
            w = math.radians(f["tilt"])
            plane(self.bed_n + w * rng.normal(0, 1, 3), rng.uniform(0.78, 0.95))
            plane(-self.bed_n + 1.5 * w * rng.normal(0, 1, 3), rng.uniform(0.7, 0.9))
        # the major faces: directions spread over the sphere (a golden spiral turned at random), each jittered
        nf = int(rng.integers(f["faces"][0], f["faces"][1] + 1))
        g = (1 + 5 ** 0.5) / 2
        i = np.arange(nf)
        z = 1 - 2 * (i + 0.5) / nf
        dirs = np.c_[np.sqrt(1 - z * z) * np.cos(2 * np.pi * i / g), np.sqrt(1 - z * z) * np.sin(2 * np.pi * i / g), z]
        axq = rng.normal(0, 1, 3)
        Q = _rot([0.0, 0.0, 1.0], rng.uniform(0, 360)) @ _rot(axq / np.linalg.norm(axq), rng.uniform(0, 360))
        jit = math.radians(f["jitter"])
        for d_ in dirs @ Q.T:
            n = d_ + jit * rng.normal(0, 1, 3)
            if N and max(float(n @ m) / np.linalg.norm(n) for m in N) > 0.93:
                continue  # (nearly a face that is already there)
            plane(n, rng.uniform(f["face_in"][0], f["face_in"][1]))
        for ax_ in range(3):  # (never unbounded: a few faces may leave a side open; these lie outside a closed block)
            for sg in (1.0, -1.0):
                n = np.zeros(3)
                n[ax_] = sg
                if not N or max(float(n @ m) for m in N) < 0.8:
                    N.append(n)
                    D.append(self.half[ax_] * 1.12)
        base = (np.array(N), np.array(D))
        corners = self._corners(*base)
        # corners broken off: one or two deep, the rest shallow
        nch = int(rng.integers(f["chips"][0], f["chips"][1] + 1))
        deep = int(rng.integers(f["broken"][0], f["broken"][1] + 1))
        for j in range(nch):
            if len(corners):
                n = corners[int(rng.integers(len(corners)))] / self.half + 0.35 * rng.normal(0, 1, 3)
            else:
                n = rng.normal(0, 1, 3)
            n /= np.linalg.norm(n)
            if j < deep and n[2] < -0.2:
                n[2] = abs(n[2])  # (the big breaks are where they show: not under the block)
            reach = float((corners @ n).max()) if len(corners) else support(n)
            N.append(n)
            D.append(reach * (1 - (_u(rng, f["break"]) if j < deep else _u(rng, f["chip"]))))
        self.N, self.D = np.array(N), np.array(D)
        self.tone = rng.uniform(-1, 1, len(N))
        self.bevel = f["bevel"] * size
        self.top_round = f["top_round"]
        self.taper = f["taper"]
        self.round = f["round"]
        self.bend = f["bend"] * rng.choice([-1, 1]) * rng.uniform(0.6, 1.0)
        self.beds = []
        for _ in range(int(rng.integers(f["beds"][0], f["beds"][1] + 1))):
            n = self.bed_n + math.radians(12.0) * rng.normal(0, 1, 3)  # (partings are never quite parallel)
            self.beds.append((n / np.linalg.norm(n), rng.choice([-1, 1]) * rng.uniform(0.25, 0.8) * c, _u(rng, f["bed_thick"]) * size, _u(rng, f["bed_set"]) * size,
                              rng.uniform(0, 2 * math.pi), rng.uniform(0.15, 0.5)))
        self.split = None
        if rng.uniform() < f["split"]:
            n = np.array([rng.normal(), rng.normal(), 0.35 * rng.normal()])
            n /= np.linalg.norm(n)
            self.split = (n, rng.uniform(-0.25, 0.25) * a, _u(rng, f["split_gap"]) * size, int(rng.integers(1 << 30)))
        self.dent = None
        if rng.uniform() < f["dent"]:
            n = np.array([rng.normal(), rng.normal(), abs(rng.normal()) * 0.6 + 0.2])
            n /= np.linalg.norm(n)
            r = rng.uniform(0.3, 0.5) * size * az
            self.dent = (n * self.half * 1.0 + n * r * 0.72, r)
        self.lumps, self.lump_size, self.seed = f["lumps"] * size, f["lump_size"] * size, int(rng.integers(1 << 30))
        ext = np.abs(corners).max(0) if len(corners) else self.half
        ext = np.maximum(ext, self.half) * (1 + abs(self.taper) * 0.5) + abs(self.bend) * c
        self.r_bound = float(np.linalg.norm(ext)) * 1.05 + 0.02
        cw = np.array([[sx * ext[0], sy * ext[1], sz * ext[2]] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) @ self.R.T + self.c
        self.lo, self.hi = cw.min(0) - 0.03 * size - 0.01, cw.max(0) + 0.03 * size + 0.01

    def _corners(self, N, D):
        """Vertices of the polyhedron {N p <= D} (triples of planes), for chip depths."""
        out = []
        n = len(N)
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(j + 1, n):
                    A = N[[i, j, k]]
                    if abs(np.linalg.det(A)) < 1e-3:
                        continue
                    p = np.linalg.solve(A, D[[i, j, k]])
                    if (N @ p <= D + 1e-6).all():
                        out.append(p)
        return np.array(out) if out else np.zeros((0, 3))

    def local(self, p):
        return (p - self.c) @ self.R

    def sd(self, p, info=False):
        q0 = self.local(p)
        q = q0
        zr = np.clip(q0[:, 2] / self.half[2], -1.3, 1.3)
        if self.taper or self.bend:
            q = q0.copy()
            if self.bend:  # a bean: the long axis bowed
                q[:, 2] = q[:, 2] + self.bend * self.half[2] * ((q0[:, 0] / self.half[0]) ** 2 - 0.4)
            if self.taper:  # wider low, narrower high
                q[:, :2] = q[:, :2] / (1 - 0.5 * self.taper * zr)[:, None]
        vals = q @ self.N.T - self.D  # (n, planes)
        k = self.bevel * (1 + self.top_round * np.clip(0.5 + 0.5 * zr, 0, 1)) if self.top_round else self.bevel
        d = _smax([vals[:, i] for i in range(vals.shape[1])], k)
        if self.round > 0:
            kk = np.linalg.norm(q / self.half, axis=1)
            de = (kk - 1.0) * self.half.min() * (0.6 + 0.4 * np.minimum(kk, 2.0) / 2.0) / 0.8
            d = (1 - self.round) * d + self.round * de
        zb = q0 @ self.bed_n
        for n, z0, th, dep, az, cover in self.beds:  # a parting: a thin groove round part of the block
            w = np.clip(1 - np.abs(q0 @ n - z0) / th, 0, 1)
            w = w * w * (3 - 2 * w)
            ang = np.arctan2(q0[:, 1], q0[:, 0])
            along = np.clip((np.cos(ang - az) - (1 - 2 * cover)) / 0.4, 0, 1)
            d = d + dep * w * along
        if self.split is not None:  # a crack through the block: a V groove along a wandering plane
            n, off, gap, sd_ = self.split
            x = q0 @ n - off + 0.03 * self.size * (noise.fbm(q0, 0.25 * self.size, 2, sd_) - 0.5) * 2
            d = d + np.clip(1 - np.abs(x) / gap, 0, 1) ** 2 * 2.5 * gap
        if self.dent is not None:
            pc, r = self.dent
            dd = r - np.linalg.norm(q0 - pc, axis=1)
            d = _smax([d, dd], 0.35 * r)
        if self.lumps:
            d = d + self.lumps * (noise.fbm(q0, self.lump_size, 2, self.seed) - 0.5) * 2
        if not info:
            return d
        o = np.argsort(vals, axis=1)
        i1, i2 = o[:, -1], o[:, -2]
        r = np.arange(len(q))
        return d, {"face": i1, "edge": vals[r, i1] - vals[r, i2], "tone": self.tone[i1], "bed": zb, "q": q0,
                   "axis": None}


class Wood:
    """A piece of driftwood: a crooked tapering stem, broken stubs, maybe a fork; round cones met softly."""

    def __init__(self, rng, form, size=1.0, centre=(0, 0, 0), yaw=0.0, pitch=0.0):
        f = form
        L = _u(rng, f["length"]) * size
        r0 = _u(rng, f["radius"]) * size
        r1 = r0 * _u(rng, f["taper"])
        n = 6
        t = np.linspace(-0.5, 0.5, n)
        ph = rng.uniform(0, 6.28, 2)
        P = np.c_[t * L, f["crook"] * L * np.sin(3.0 * t + ph[0]) + 0.3 * f["crook"] * L * np.sin(9 * t + ph[1]),
                  0.5 * f["crook"] * L * np.sin(2.3 * t + ph[1])]
        Rr = np.linspace(r0, r1, n)
        segs = [(P[i], P[i + 1], Rr[i], Rr[i + 1]) for i in range(n - 1)]
        self.n_main = len(segs)
        for _ in range(int(rng.integers(f["stubs"][0], f["stubs"][1] + 1))):
            i = int(rng.integers(0, n - 2))
            a = P[i] + (P[i + 1] - P[i]) * rng.uniform()
            d = np.array([rng.uniform(0.2, 0.8), rng.normal(), 0.45 * rng.normal()])
            d /= np.linalg.norm(d)
            l = _u(rng, f["stub"]) * size
            segs.append((a, a + d * l, Rr[i] * 0.55, Rr[i] * 0.3))
        if rng.uniform() < f["fork"]:
            i = int(rng.integers(1, n - 2))
            d = np.array([0.8, rng.choice([-1, 1]) * rng.uniform(0.4, 0.8), rng.uniform(-0.08, 0.18)])
            d /= np.linalg.norm(d)
            l = rng.uniform(0.25, 0.45) * L
            m = P[i] + d * l * 0.5 + 0.03 * L * rng.normal(0, 1, 3)
            segs.append((P[i], m, Rr[i] * 0.7, Rr[i] * 0.5))
            segs.append((m, P[i] + d * l, Rr[i] * 0.5, Rr[i] * 0.3))
        nr = int(rng.integers(f["roots"][0], f["roots"][1] + 1))
        if nr:  # a root plate: the butt swells, roots fan out square to the stem and a little back
            ax0 = (P[1] - P[0]) / np.linalg.norm(P[1] - P[0])
            e1 = np.cross(ax0, [0, 0, 1.0])
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(ax0, e1)
            segs[0] = (segs[0][0], segs[0][1], r0 * 1.45, segs[0][3])
            for i in range(nr):
                a = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / nr
                d = math.cos(a) * e1 + math.sin(a) * e2 - ax0 * rng.uniform(0.1, 0.45)
                d /= np.linalg.norm(d)
                l = rng.uniform(0.1, 0.2) * size
                m_ = P[0] + d * l * 0.55 + 0.02 * size * rng.normal(0, 1, 3)
                segs.append((P[0] + ax0 * 0.01, m_, r0 * 0.75, r0 * 0.42))
                segs.append((m_, P[0] + d * l - ax0 * 0.03 * size, r0 * 0.42, r0 * 0.16))
        self.broken = f["broken"]
        self.ends = (P[0].copy(), P[-1].copy(), (P[1] - P[0]) / np.linalg.norm(P[1] - P[0]), (P[-1] - P[-2]) / np.linalg.norm(P[-1] - P[-2]), r0, r1, nr > 0)
        R = _rot([0, 0, 1], math.degrees(yaw)) @ _rot([0, 1, 0], math.degrees(pitch))
        c = np.asarray(centre, float)
        self.ends = (self.ends[0] @ R.T + c, self.ends[1] @ R.T + c, self.ends[2] @ R.T, self.ends[3] @ R.T, r0, r1, nr > 0)
        self.segs = [(a @ R.T + c, b @ R.T + c, ra, rb) for a, b, ra, rb in segs]
        self.bevel = f["bevel"] * size
        self.lumps, self.lump_size, self.seed = f["lumps"] * size, f["lump_size"] * size, int(rng.integers(1 << 30))
        self.c = c
        self.tone = rng.uniform(-1, 1, len(self.segs))
        self.r_bound = 0.5 * L + r0 * 2 + 0.2 * size
        ends = np.array([[a - ra, a + ra, b - rb, b + rb] for a, b, ra, rb in self.segs]).reshape(-1, 3)
        self.lo, self.hi = ends.min(0) - 0.02 * size, ends.max(0) + 0.02 * size

    def sd(self, p, info=False):
        best = np.full(len(p), 1e9)
        soft = None
        ax = np.zeros((len(p), 3))
        sc = np.zeros(len(p))
        ton = np.zeros(len(p))
        second = np.full(len(p), 1e9)
        s0 = 0.0
        for k, (a, b, ra, rb) in enumerate(self.segs):
            ab = b - a
            l2 = float(ab @ ab)
            t = np.clip(((p - a) @ ab) / l2, 0, 1)
            # a blunt broken end: beyond the end the distance grows along the axis (no round cap)
            d = np.linalg.norm(p - a - t[:, None] * ab, axis=1) - (ra + (rb - ra) * t)
            better = d < best
            second = np.where(better, best, np.minimum(second, d))
            if info:
                ax[better] = ab / math.sqrt(l2)
                sc[better] = s0 + t[better] * math.sqrt(l2)
                ton[better] = self.tone[k]
            best = np.minimum(best, d)
            h = self.bevel
            soft = d if soft is None else (lambda x, y: np.minimum(x, y) - h * np.clip(1 - np.abs(x - y) / (4 * h), 0, 1) ** 2)(soft, d) if h > 0 else np.minimum(soft, d)
            s0 += math.sqrt(l2)
        d = soft
        if self.lumps:
            d = d + self.lumps * (noise.fbm(p - self.c, self.lump_size, 2, self.seed) - 0.5) * 2
        if self.broken:  # the stem's ends broken off: a jagged oblique face instead of a round cap (splinters along the grain)
            e0, e1, a0, a1, r0, r1, rooted = self.ends
            for e, a, r, sgn, skip in ((e0, a0, r0, -1.0, rooted), (e1, a1, r1, 1.0, False)):
                if skip:
                    continue
                x = (p - e) @ a * sgn
                near = np.linalg.norm(p - e, axis=1) < 4 * r
                if near.any():
                    q = p[near] - e
                    perp = q - np.outer(q @ a, a)
                    jag = self.broken * r * (1.6 * (noise.fbm(perp / (0.35 * r) + self.seed % 97, 1.0, 2, self.seed + 3) - 0.5) + 0.8 * perp @ np.cross(a, [0.3, 0.2, 1.0]) / r)
                    d[near] = np.maximum(d[near], x[near] + 0.4 * r - jag)
        if not info:
            return d
        return d, {"face": np.zeros(len(p), int), "edge": np.full(len(p), 1.0), "tone": ton, "bed": sc,
                   "q": p - self.c, "axis": ax}


class Bush:
    """A bush's body: a dome going straight down to the ground with lobes round it, met softly."""

    def __init__(self, rng, form, size=1.0):
        f = form
        ay, H = _u(rng, f["aspect"][0]), _u(rng, f["aspect"][1]) * size
        self.H = H
        self.c = np.zeros(3)
        R = 0.5 * size
        self.stems = []
        # closed styles (blobby, cartoon): a cluster of gumdrop lumps of different sizes, every one standing ON THE GROUND
        # (straight down below its middle) and run softly into its neighbours: a toy bush. (Lumps held up on stems read
        # as mushroom clouds on wire legs.) One closed body: its LODs are the rocks' decimation, not a hull per lump.
        self.gum = not f.get("open", True)
        self.lumpy = False
        if self.gum:
            self.ell = []
            n = int(rng.integers(f["clumps"][0], f["clumps"][1] + 1))
            a0 = rng.uniform(0, 2 * math.pi)
            for i in range(n):
                r = (0.3 if i == 0 else rng.uniform(0.17, 0.25)) * size
                a = a0 + 2 * math.pi * i / n + rng.uniform(-0.3, 0.3)
                d = (0.07 if i == 0 else rng.uniform(0.24, 0.33)) * size
                top = (1.0 if i == 0 else rng.uniform(0.45, 0.78)) * H
                rz = 0.85 * r
                c = np.array([d * math.cos(a), d * math.sin(a) * ay, max(top - rz, 0.25 * r)])
                self.ell.append((c, np.array([r, r, rz]) * rng.uniform(0.94, 1.08, 3)))
        else:
            # (centre, radii): the main dome, then the lobes
            self.ell = [(np.array([0.0, 0.0, 0.1 * H]), np.array([0.8 * R, 0.8 * R * ay, 0.84 * H]))]  # (a dome: widest at the ground)
        for _ in range(0 if self.gum else int(rng.integers(f["lobes"][0], f["lobes"][1] + 1))):
            a = rng.uniform(0, 2 * math.pi)
            r = _u(rng, f["lobe"]) * size
            o = _u(rng, f["lobe_out"])
            zc = rng.uniform(0.12, 0.62) * H
            shrink = math.sqrt(max(1 - (zc / H) ** 2, 0.15))  # (the dome is narrower up there)
            c = np.array([(R - 0.6 * r) * o * shrink * math.cos(a), (R * ay - 0.6 * r) * o * shrink * math.sin(a), zc])
            c[2] = min(c[2], H - 0.8 * r)
            self.ell.append((c, np.array([r, r, 0.85 * r]) * rng.uniform(0.9, 1.15, 3)))
        self.tone = rng.uniform(-1, 1, len(self.ell))
        self.join = f["join"] * size
        self.lumps, self.lump_size, self.seed = f["lumps"] * size, f["lump_size"] * size, int(rng.integers(1 << 30))
        self.lo = np.array([-R * 1.25, -R * 1.25, -0.12 * size])
        self.hi = np.array([R * 1.25, R * 1.25, H * 1.2])
        self.r_bound = 2.0 * size
        self.ground_z = 0.0

    def sd(self, p, info=False):
        ds = []
        for i, (c, r) in enumerate(self.ell):
            q = p - c
            if self.gum:  # round above its middle, below it a longer half that the ground cuts at 0.8 of its width: a tucked foot
                q = q.copy()
                q[:, 2] = np.where(q[:, 2] < 0, q[:, 2] * r[2] / max(1.65 * c[2], 1e-3), q[:, 2])
            elif i == 0:
                q = q.copy()
                q[:, 2] = np.maximum(q[:, 2], 0.0)  # (straight down below its middle: a bush stands on the ground)
            else:
                q = q.copy()
                q[:, 2] = np.where(q[:, 2] < 0, q[:, 2] * 0.6, q[:, 2])  # (lobes hang a little)
            k = np.linalg.norm(q / r, axis=1)
            ds.append((k - 1.0) * r.min())
        D = np.stack(ds, 1)
        d = D[:, 0]
        for i in range(1, D.shape[1]):
            h = np.clip(0.5 + 0.5 * (d - D[:, i]) / self.join, 0, 1)
            d = d * (1 - h) + D[:, i] * h - self.join * h * (1 - h)
        if self.lumps:
            d = d + self.lumps * (noise.fbm(p, self.lump_size, 2, self.seed) - 0.5) * 2
        d = np.maximum(d, -(p[:, 2] + 0.1))  # closed under the ground
        if not info:
            return d
        o = np.argsort(D, axis=1)
        r_ = np.arange(len(p))
        return d, {"face": o[:, 0], "edge": D[r_, o[:, 1]] - D[r_, o[:, 0]] if D.shape[1] > 1 else np.full(len(p), 1.0),
                   "tone": self.tone[o[:, 0]], "bed": p[:, 2], "q": p, "axis": None}

    def surface(self, dirs, origin):
        """Where rays from `origin` along unit `dirs` leave the body (bisection)."""
        lo, hi = np.zeros(len(dirs)), np.full(len(dirs), 1.5)
        for _ in range(22):
            mid = 0.5 * (lo + hi)
            ins = self.sd(origin + dirs * mid[:, None]) < 0
            lo, hi = np.where(ins, mid, lo), np.where(ins, hi, mid)
        return origin + dirs * (0.5 * (lo + hi))[:, None]
