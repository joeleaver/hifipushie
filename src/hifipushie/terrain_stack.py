"""A jointed rock column: the form of a sea stack (or any free-standing pillar of bedded, jointed rock) as a signed
distance, for the 3D tiles (terrain_mesh.Stack).

How real stacks are made (Old Harry, the Twelve Apostles, Duncansby, Yesnaby, the Old Man of Hoy; photos and measures
in workspace/level_refs/stacks): the sea widens JOINTS (near-vertical fracture sets, usually two roughly at right
angles and a minor diagonal one) until a block of headland stands alone. So the plan is a polygon of joint faces, the
walls are near-vertical planes, and the outline changes where BLOCKS fell out along joints and bedding planes: a face
steps back above a bed over part of its width (a ledge ending in a re-entrant corner), an open joint is a vertical slot,
a corner is missing over a few beds. Beds show as fine lines and small ledges (the field's rock relief and the
textures), the top is the bed it broke at (flat, tilted by the dip) or, on a slender stack, two joint faces leaning
together (a spire), the waterline is undercut by a notch and the foot has fallen blocks round it.

Every face's offset is the column's polygon offset minus its `cuts` (each a box window in (height, position along the
face) with soft edges `ramp` m wide, never a jump: a jump meshes as shards), leaning in `batter` deg and wandering
slowly; the faces meet in a smooth max with `bevel` m (rounded arrises). Every number has a default here (`FORM`); a
terrain style can override them per stack (sheet `rock.stack`, terrain_style.stack_form). Pointwise and deterministic:
tiles agree."""
from __future__ import annotations

import math

import numpy as np

FORM = {
    "size": [0.95, 1.15],       # the first family's half width x r
    "cross": [75.0, 105.0],     # deg between the two joint families
    "aspect": [0.7, 1.0],       # the second family's half width x the first's (oblong plans)
    "chamfer": 0.55,            # probability a corner is cut by the minor (diagonal) family
    "chamfer_cut": [0.72, 0.92],  # where it cuts: x the corner's distance along the diagonal
    "bevel": 0.35,              # m: edges and arrises rounded (smooth max)
    "levels": 1.1,              # beds a face steps back at, per height-in-widths
    "p_step": 0.5,              # per face per level: a block fell (the face steps back above it)
    "step": [0.06, 0.22],       # x r: how far
    "p_partial": 0.6,           # a step only over part of the face (a ledge ending in a re-entrant corner)
    "slots": 0.5,               # open joints per face (vertical slots over part of the height)
    "slot": [0.15, 0.4],        # x r: their depth (width 1.2-3 m)
    "corners": 0.35,            # per corner: a block missing over a few beds
    "ramp": 1.0,                # m: every cut's soft edge (>= 2 voxels: a sharper one meshes as shards)
    "batter": 2.5,              # deg: each face leans in
    "batter_spread": 2.0,       # deg: +- per face
    "wander": 0.03,             # x r: each face's slow wander over the height
    "dip": [1.0, 6.0],          # deg: the top bed's tilt
    "p_spire": 0.35,            # probability of a spire top for a slender stack (height / width over `slender`)
    "slender": 2.4,
    "spire": [24.0, 36.0],      # deg from vertical of the spire's faces
    "notch": 0.7,               # x min(0.3 r, 1.6 m): the waterline notch's depth
    "boulders": [2, 5],         # fallen blocks round the foot (count range)
    "boulder": [0.1, 0.22],     # x r, their half size (at least 0.7 m)
}


def form(over=None):
    """FORM with a style's overrides (unknown keys refused)."""
    over = dict(over or {})
    bad = set(over) - set(FORM)
    if bad:
        raise ValueError(f"stack form keys {sorted(bad)} unknown ({', '.join(sorted(FORM))})")
    return {**FORM, **over}


def smax_many(vals, k):
    """Smooth max of a list of arrays, the cubic smin's mirror pairwise (k <= 0: hard max)."""
    out = vals[0]
    for v in vals[1:]:
        if k <= 0:
            out = np.maximum(out, v)
        else:
            h = np.maximum(k - np.abs(out - v), 0.0) / k
            out = np.maximum(out, v) + h * h * h * k * (1.0 / 6.0)
    return out


def _smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * h * k * (1.0 / 6.0)


def _win(x, a, b, ramp):
    """1 inside [a, b], 0 outside, smoothstep edges `ramp` wide centred on a and b (a, b may be +-inf)."""
    lo = np.ones_like(x) if not np.isfinite(a) else np.clip((x - a) / ramp + 0.5, 0, 1)
    hi = np.ones_like(x) if not np.isfinite(b) else np.clip((b - x) / ramp + 0.5, 0, 1)
    return lo * lo * (3 - 2 * lo) * hi * hi * (3 - 2 * hi)


def _u(rng, ab):
    return float(rng.uniform(ab[0], ab[1]))


class Column:
    """A jointed rock column standing at `xy` from `base` to `top` (m), about `r` m in radius. `sea`: the waterline
    (the notch's height and the boulders; None = neither). `stage`: "auto" | "broad" | "slender" | "spire" |
    "stump" (auto: by height / width)."""

    def __init__(self, xy, base, top, r, seed, sea=None, stage="auto", over=None):
        self.f = F = form(over)
        self.xy, self.base, self.top, self.r = np.asarray(xy, float), float(base), float(top), float(r)
        self.sea = None if sea is None else float(sea)
        rng = np.random.default_rng(int(seed))
        H = self.top - self.base
        # plan: two joint families, each face at its own offset
        a = rng.uniform(0, math.pi)
        b = a + math.radians(_u(rng, F["cross"]))
        da = r * _u(rng, F["size"])
        db = da * _u(rng, F["aspect"])
        planes = []  # [angle, offset]
        for ang, d in ((a, da), (b, db), (a + math.pi, da), (b + math.pi, db)):
            planes.append([ang, d * rng.uniform(0.85, 1.12)])
        corners = []
        P = list(planes)
        for i in range(4):
            j = (i + 1) % 4
            ni = np.array([math.cos(planes[i][0]), math.sin(planes[i][0])])
            nj = np.array([math.cos(planes[j][0]), math.sin(planes[j][0])])
            c = np.linalg.solve(np.array([ni, nj]), np.array([planes[i][1], planes[j][1]]))  # the corner
            corners.append((i, j, c))
            if rng.uniform() < F["chamfer"]:
                n = (ni + nj) / np.linalg.norm(ni + nj)
                P.append([math.atan2(n[1], n[0]), float(c @ n) * _u(rng, F["chamfer_cut"])])
        self.n = np.array([[math.cos(p[0]), math.sin(p[0])] for p in P])
        self.tg = np.c_[-self.n[:, 1], self.n[:, 0]]  # along each face
        self.d0 = np.array([p[1] for p in P])
        m = len(P)
        width = da + db
        slender = H / max(width, 1e-6)
        if stage == "auto":
            stage = "spire" if slender > F["slender"] and rng.uniform() < F["p_spire"] else \
                ("stump" if slender < 0.6 else ("slender" if slender > 1.8 else "broad"))
        self.stage = stage
        # cuts: (face, z0, z1, t0, t1, depth) with depth > 0 = the face set back
        z_lo, z_hi = self.base + 0.1 * H + 2.0, self.top - max(0.1 * H, 2.0)
        cuts = []
        n_lev = max(1, int(round(F["levels"] * slender + rng.uniform(-0.5, 0.5))))
        levels = np.sort(rng.uniform(z_lo, z_hi, n_lev)) if z_hi > z_lo + 2 else np.zeros(0)
        p_step = np.full(len(levels), F["p_step"])
        if stage == "spire":  # (Duncansby: the taper is blocks falling off at bed after bed, not two smooth slopes)
            up = np.sort(rng.uniform(self.base + 0.45 * H, self.top - 0.18 * H, max(2, n_lev)))
            levels = np.r_[levels, up]
            p_step = np.r_[p_step, np.full(len(up), 0.65)]
        half = lambda i: float(r * 1.4)  # (a face's half length: generous, the window is cut by the polygon anyway)
        for zk, ps in zip(levels, p_step):
            for i in range(4):  # (the main faces; chamfers follow their neighbours' cuts through the polygon)
                if rng.uniform() >= ps:
                    continue
                dep = _u(rng, F["step"]) * r * (0.75 if zk > self.base + 0.45 * H and stage == "spire" else 1.0)
                if rng.uniform() < F["p_partial"]:
                    t0 = rng.uniform(-0.5, 0.5) * half(i)
                    t = (t0, np.inf) if rng.uniform() < 0.5 else (-np.inf, t0)
                else:
                    t = (-np.inf, np.inf)
                cuts.append((i, zk, np.inf, t[0], t[1], dep))
        for i in range(4):  # open joints: vertical slots over part of the height
            for _ in range(rng.poisson(F["slots"])):
                w = rng.uniform(0.9, 2.2)
                t0 = rng.uniform(-0.6, 0.6) * half(i)
                z0 = rng.uniform(self.base - 2, self.base + 0.6 * H)  # (open from the top down: the sea widened it)
                # (on a spire the slots stop under the taper: cut into the blade they left slivers)
                z1 = self.top + 3 if stage != "spire" else self.base + 0.6 * H
                if z1 > z0 + 3:
                    cuts.append((i, z0, z1, t0 - w / 2, t0 + w / 2, _u(rng, F["slot"]) * r))
        for i, j, c in corners:  # a block missing at a corner over a few beds: both faces set back by its size
            if rng.uniform() >= F["corners"]:
                continue
            s = rng.uniform(0.2, 0.45) * r
            z0 = rng.uniform(self.base, z_hi)
            z1 = z0 + rng.uniform(3.0, max(4.0, 0.3 * H))
            ti = float(c @ self.tg[i])
            tj = float(c @ self.tg[j])
            cuts.append((i, z0, z1, *((ti - 2.5 * s, np.inf) if ti > 0 else (-np.inf, ti + 2.5 * s)), s))
            cuts.append((j, z0, z1, *((tj - 2.5 * s, np.inf) if tj > 0 else (-np.inf, tj + 2.5 * s)), s))
        self.cuts = cuts
        self.batter = np.tan(np.radians(F["batter"] + rng.uniform(-1, 1, m) * F["batter_spread"]))
        self.wph = rng.uniform(0, 2 * math.pi, (m, 2))
        self.wl = H * rng.uniform(0.35, 0.7, (m, 2))
        dip = math.radians(_u(rng, F["dip"]))
        dd = rng.uniform(0, 2 * math.pi)
        self.tilt = np.array([math.cos(dd), math.sin(dd)]) * math.tan(dip)
        self.spire = None
        if stage == "spire":
            # faces of the first family leaning together, each at its own angle, the ridge off-centre; the second
            # family's faces lean in more gently (a pointed ridge, not a cone)
            self.spire = (math.radians(_u(rng, F["spire"])), math.radians(_u(rng, F["spire"])),
                          math.radians(_u(rng, [F["spire"][0] * 0.6, F["spire"][1] * 0.8])),
                          rng.uniform(-0.25, 0.25) * da, rng.uniform(-0.3, 0.3) * db)
        self.notch = F["notch"] * min(0.3 * r, 1.6) * rng.uniform(0.3, 1.2, m)  # (deeper where the swell hits)
        # boulders: chipped blocks round the foot, tumbled, on the sea floor and awash
        self.boulders = []
        if self.sea is not None:
            for _ in range(int(rng.integers(F["boulders"][0], F["boulders"][1] + 1))):
                th = rng.uniform(0, 2 * math.pi)
                u = np.array([math.cos(th), math.sin(th)])
                nu = self.n[:4] @ u
                sup = float(np.min(np.where(nu > 0.2, self.d0[:4] / np.maximum(nu, 1e-3), np.inf)))
                hs = max(0.7, _u(rng, F["boulder"]) * r) * rng.uniform(0.6, 1.3, 3) * np.array([1, 1, 0.7])
                c = u * (sup + hs.max() * rng.uniform(-0.2, 0.7))  # (leaning on the foot: never alone in deep water)
                ztop = self.sea + rng.uniform(-0.6, 1.0) * hs[2]
                hs[2] = max(0.5 * (ztop - (self.base - 1.0)), hs[2])
                zc = ztop - hs[2]
                R = _rot(rng.uniform(0, math.pi), rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35))
                chip = rng.normal(size=3)
                chip /= np.linalg.norm(chip)
                self.boulders.append((np.r_[c, zc], hs, R, chip, rng.uniform(0.5, 0.8)))
        # each block leans on the foot: drawn in until it overlaps the column (alone in deep water it would float)
        placed, self.boulders = self.boulders, []
        self.reach = float(self.d0.max()) + 2.0
        for c, hs, R, chip, cf in placed:
            u = c[:2] / max(np.linalg.norm(c[:2]), 1e-9)
            for _ in range(40):
                zz = np.linspace(self.base - 0.5, c[2], 4)
                pts = np.c_[np.repeat((self.xy + c[:2])[None], 4, 0), zz]
                if float(self.sd(pts).min()) < -0.35 * float(hs.min()):
                    break
                c = np.r_[c[:2] - 0.25 * u, c[2]]
            placed_c = c
            self.boulders.append((placed_c, hs, R, chip, cf))
        bmax = max([np.linalg.norm(bb[0][:2]) + bb[1].max() * 1.8 for bb in self.boulders], default=0.0)
        self.reach = max(float(self.d0.max()) + F["wander"] * r + 1.0, bmax + 0.5)

    def offsets(self, q, z):
        """Each face's offset at points (q: plan offsets from the centre, z): (n, m)."""
        F = self.f
        d = np.repeat(self.d0[None, :], len(z), 0)
        for i, z0, z1, t0, t1, dep in self.cuts:
            t = q @ self.tg[i]
            rp = max(F["ramp"], 1.2 * dep)  # (a deep cut hands over as far as it goes in: the field stays distance-like)
            d[:, i] -= dep * _win(z, z0, z1, rp) * _win(t, t0, t1, rp)
        d = np.maximum(d, 0.5 * self.d0[None, :])  # (cuts never eat a section through: it stands on its own rock)
        dz = (z - self.base)[:, None]
        d = d - dz * self.batter[None, :]
        w = F["wander"] * self.r
        d = d + w * (0.6 * np.sin(2 * math.pi * dz / self.wl[None, :, 0] + self.wph[None, :, 0])
                     + 0.4 * np.sin(2 * math.pi * dz / self.wl[None, :, 1] + self.wph[None, :, 1]))
        if self.sea is not None:
            d = d - np.exp(-((z - self.sea - 0.9) / 1.2) ** 2)[:, None] * self.notch[None, :]
        return d

    def sd(self, p):
        p = np.asarray(p, float)
        q = p[:, :2] - self.xy
        z = p[:, 2]
        d = self.offsets(q, z)
        k = self.f["bevel"]
        f = smax_many([q @ self.n[i] - d[:, i] for i in range(len(self.n))], k)
        top = [z - (self.top - q @ self.tilt)]
        if self.spire is not None:
            a1, a2, a3, oa, ob = self.spire
            for nn, ang, off in ((self.n[0], a1, oa), (self.n[2], a2, -oa), (self.n[1], a3, ob), (self.n[3], a3, -ob)):
                # a face through the ridge line (at `off` across, the top's height) leaning `ang` from vertical
                top.append((q @ nn - off) * math.cos(ang) + (z - self.top) * math.sin(ang))
        f = smax_many([f] + top, k)
        f = smax_many([f, (self.base - 1.0) - z], 0.3)
        for c, hs, R, chip, cf in self.boulders:
            loc = (p - (np.r_[self.xy, 0] + c)) @ R
            rr = 0.3 * float(hs.min())
            qq = np.abs(loc) - (hs - rr)
            bx = np.linalg.norm(np.maximum(qq, 0), axis=1) + np.minimum(qq.max(1), 0) - rr
            bx = smax_many([bx, loc @ chip - cf * float(np.abs(hs) @ np.abs(chip))], 0.3)  # (a corner knocked off)
            f = _smin(f, bx, 0.4)
        return f * 0.95


def _rot(yaw, a, b):
    cy, sy, ca, sa, cb, sb = math.cos(yaw), math.sin(yaw), math.cos(a), math.sin(a), math.cos(b), math.sin(b)
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
    Ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    return Rz @ Rx @ Ry
