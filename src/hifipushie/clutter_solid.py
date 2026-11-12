"""Cells, the spray tile, bush cards, and `Solid`: one piece's field from its style. Part of clutter (clutter.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import noise
from .clutter import _layered
from .clutter_forms import Bush, Stone, Wood, _u

def _cells(q, size, seed):
    """3D cells (jittered points on a lattice): (distance to the nearest point, to the second nearest, the nearest's
    own random 0..1), distances in m."""
    g = q / size
    b = np.floor(g).astype(np.int64)
    f1 = np.full(len(q), 1e9)
    f2 = np.full(len(q), 1e9)
    cid = np.zeros(len(q))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = b + [dx, dy, dz]
                jx = noise._hash(c[:, 0], c[:, 1], c[:, 2], seed)
                jy = noise._hash(c[:, 0], c[:, 1], c[:, 2], seed + 1)
                jz = noise._hash(c[:, 0], c[:, 1], c[:, 2], seed + 2)
                d = np.linalg.norm(c + np.stack([jx, jy, jz], 1) - g, axis=1)
                nearer = d < f1
                f2 = np.where(nearer, f1, np.minimum(f2, d))
                cid = np.where(nearer, noise._hash(c[:, 0], c[:, 1], c[:, 2], seed + 3), cid)
                f1 = np.minimum(f1, d)
    return f1 * size, f2 * size, cid


def spray_tile(px: int, paint: dict, color, season: dict, seed: int):
    """A leaf spray's picture for a card: (rgb (px, px, 3) sRGB, alpha (px, px)); the stem runs up the middle from the
    bottom edge, leaves alternate along it. The colour is bled under the alpha."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    sp = paint["spray"]
    rng = np.random.default_rng(seed)
    S = 4 * px
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    col = np.asarray(color, float)
    if season.get("mix") is not None:
        col = col * (1 - season["amount"]) + np.asarray(season["mix"], float) * season["amount"]
    n = int(rng.integers(sp["leaves"][0], sp["leaves"][1] + 1))
    bend = rng.uniform(-0.12, 0.12)
    stem = lambda t: np.array([0.5 + bend * math.sin(t * 2.2) + 0.02 * math.sin(t * 9), 1.0 - 0.9 * t])
    pts = [tuple((stem(t) * S).tolist()) for t in np.linspace(0, 1, 20)]
    wood = tuple(int(255 * c) for c in np.clip(col * [1.1, 0.8, 0.7] * 0.6, 0, 1)) + (255,)
    dr.line(pts, fill=wood, width=max(2, S // 90))
    steps = int(paint.get("steps") or 0)
    order = sorted(range(n), key=lambda i: i)  # (from the base up: later leaves over earlier ones)
    for i in order:
        t = (i + 0.6) / (n + 0.4) * rng.uniform(0.95, 1.05)
        t = min(t, 1.0)
        base = stem(t)
        side = 1 if i % 2 == 0 else -1
        ang = math.radians(rng.uniform(32, 62)) * side if i < n - 1 else rng.uniform(-0.2, 0.2)
        d = np.array([math.sin(ang), -math.cos(ang)])
        L = _u(rng, sp["leaf"]) / 0.34 * (0.75 + 0.35 * math.sin(math.pi * min(t + 0.15, 1.0)))  # (in tile units: a tile is ~0.34 m)
        W = L * sp["round"]
        nrm = np.array([-d[1], d[0]])
        poly = []
        for u in np.linspace(0, 1, 9):
            w = W * 0.5 * math.sin(math.pi * u ** 0.8) * (1 if u < 1 else 0)
            poly.append(base + d * L * u + nrm * w)
        for u in np.linspace(1, 0, 9)[1:]:
            w = W * 0.5 * math.sin(math.pi * u ** 0.8)
            poly.append(base + d * L * u - nrm * w)
        tone = 1 + sp["tones"] * rng.uniform(-1, 1) - 0.25 * (1 - t)
        if steps:
            tone = round(tone * steps) / steps
        c = tuple(int(255 * x) for x in np.clip(col * tone, 0, 1)) + (255,)
        xy = [tuple((np.asarray(q_) * S).tolist()) for q_ in poly]
        dr.polygon(xy, fill=c, outline=(tuple(int(255 * x) for x in np.clip(col * 0.25, 0, 1)) + (255,)) if sp.get("outline") else None)
        if sp.get("outline"):
            dr.line(xy + [xy[0]], fill=tuple(int(255 * x) for x in np.clip(col * 0.25, 0, 1)) + (255,), width=max(2, int(sp["outline"] * S)))
        if sp.get("midrib"):
            dr.line([tuple((base * S).tolist()), tuple(((base + d * L * 0.9) * S).tolist())],
                    fill=tuple(int(255 * x) for x in np.clip(col * tone * (1 + sp["midrib"]), 0, 1)) + (255,), width=max(1, S // 300))
        if season.get("flowers") and paint.get("flowers") and rng.uniform() < paint["flowers"] * 1.6:
            fc = tuple(int(255 * x) for x in paint["flower_color"]) + (255,)
            ce = (base + d * L * rng.uniform(0.1, 0.5)) * S
            r = paint["flower_size"] / 0.34 * S * rng.uniform(0.9, 1.4)
            dr.ellipse([ce[0] - r, ce[1] - r, ce[0] + r, ce[1] + r], fill=fc)
    im = im.resize((px, px), Image.LANCZOS)
    a = np.asarray(im, float) / 255.0
    alpha = a[..., 3]
    rgb = a[..., :3]
    solid = alpha > 0.5
    if solid.any():
        idx = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        rgb = rgb[idx[0], idx[1]]
    return rgb, alpha


def bush_cards(solid, cfg, k: int, share: float, grow: float, tiles: list, base: int):
    """The leaf sprays of variant k: quads standing out of the dome, each drawn from both sides with the SAME normal
    (out of the bush and up: a spray lit by its own face flickers). share = how many of them (the first ones), grow =
    drawn this much larger. Returns {"V", "N", "UV", "T", "F", "wind"} or None."""
    f = solid.form
    rng = np.random.default_rng([cfg["seed"], k, 911])
    n0 = int(rng.integers(f["cards"][0], f["cards"][1] + 1)) if f["cards"][1] > 0 else 0
    if n0 <= 0 or not tiles:
        return None
    B = solid.parts[0]
    az = rng.uniform(0, 2 * math.pi) + np.arange(n0) * 2.399963  # golden angle: spread round
    el = np.radians(np.degrees(np.arcsin(rng.uniform(0.0, 0.97, n0))))  # (even over the dome: most on its sides)
    dirs = np.c_[np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)]
    org = np.array([0.0, 0.0, 0.3 * B.H])
    P = B.surface(dirs, org)
    g = _grad(B.sd, P, 0.02)
    Nn = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
    size = rng.uniform(f["card"][0], f["card"][1], n0)
    roll = rng.uniform(0, math.pi, n0)
    pick = rng.integers(0, len(tiles), n0)
    phase = rng.uniform(0, 1, n0)
    n = max(0, int(round(n0 * share)))
    if n == 0:
        return None
    V, N, UV, T, F, W = [], [], [], [], [], []
    for i in range(n):
        a = Nn[i] * (1 - f["card_up"]) + np.array([0, 0, 1.0]) * f["card_up"]
        a /= np.linalg.norm(a)
        r0 = np.cross(a, [0, 0, 1.0])
        r0 = r0 / np.linalg.norm(r0) if np.linalg.norm(r0) > 1e-6 else np.array([1.0, 0, 0])
        r1 = np.cross(a, r0)
        rt = r0 * math.cos(roll[i]) + r1 * math.sin(roll[i])
        L = size[i] * grow
        b = P[i] - a * L * (1 - f["card_out"])
        w = 0.5 * L
        q = [b - rt * w, b + rt * w, b + rt * w + a * L, b - rt * w + a * L]
        nn = Nn[i] * 0.6 + np.array([0, 0, 0.8])
        nn /= np.linalg.norm(nn)
        x0, y0, tw = tiles[pick[i]]
        m = 1.5
        uv = [[x0 + m, y0 + tw - m], [x0 + tw - m, y0 + tw - m], [x0 + tw - m, y0 + m], [x0 + m, y0 + m]]
        o = len(V)
        V += q
        N += [nn] * 4
        UV += uv
        tt = rt - nn * (nn @ rt)
        tt /= np.linalg.norm(tt)
        wsg = 1.0 if np.cross(nn, tt) @ a > 0 else -1.0
        T += [np.r_[tt, wsg]] * 4
        F += [[o, o + 1, o + 2], [o, o + 2, o + 3], [o, o + 2, o + 1], [o, o + 3, o + 2]]
        tr = lambda z: float(np.clip(z / B.H, 0, 1.3) ** 1.5)
        W += [[tr(q[0][2]), 0.5, phase[i], 0.0], [tr(q[1][2]), 0.5, phase[i], 0.0], [tr(q[2][2]), 1.0, phase[i], 1.0], [tr(q[3][2]), 1.0, phase[i], 1.0]]
    return {"V": np.array(V), "N": np.array(N), "UV": np.array(UV, float) / base, "T": np.array(T), "F": np.array(F), "wind": np.array(W)}


class Solid:
    """A variant: one or more pieces as a hard union (a cluster of cobbles, a jam of logs), seated on the ground."""

    def __init__(self, cfg: dict, k: int):
        rng = np.random.default_rng([cfg["seed"], k, 77])
        f = cfg["form"]
        vf = cfg.get("variant_forms")
        self.lods_x = 1.0
        if vf:
            o = dict(vf[k % len(vf)])
            self.lods_x = float(o.pop("lods_x", 1.0))
            f = _layered(cfg["_layers"], o)
        self.wood = cfg["material"] == "wood"
        self.form = f
        if cfg["shape"] == "bush":
            self.parts = [Bush(rng, f)]
            self.lumpy = self.parts[0].lumpy
        elif self.wood:
            n = int(rng.integers(f["pieces"][0], f["pieces"][1] + 1))
            self.parts = []
            for i in range(n):
                if n == 1:
                    self.parts.append(Wood(rng, f))
                    continue
                s = 1.0 if i == 0 else rng.uniform(0.45, 0.85)
                yaw = rng.uniform(-1, 1) * f["pile"] * math.pi * 0.5 if i else 0.0
                z = 0.5 * i * _u(rng, f["radius"]) * 1.6
                self.parts.append(Wood(rng, f, s, (rng.uniform(-0.15, 0.15), rng.uniform(-0.12, 0.12), z), yaw,
                                       rng.uniform(-0.1, 0.1) * (i > 0)))
        elif f.get("cluster"):
            cl = f["cluster"]
            n = int(rng.integers(cl["count"][0], cl["count"][1] + 1))
            self.parts, placed = [], []
            for i in range(n * 30):
                if len(self.parts) >= n:
                    break
                s = _u(rng, cl["stone"])
                r = 0.5 * math.sqrt(rng.uniform()) * (1 - s)
                a = rng.uniform(0, 2 * math.pi)
                xy = np.array([r * math.cos(a), r * math.sin(a) * 0.8])
                if any(np.linalg.norm(xy - q) < (0.5 - 0.5 * cl.get("pile", 0.3)) * (s + t) for q, t in placed):
                    continue
                placed.append((xy, s))
                self.parts.append(Stone(rng, f, s, (xy[0], xy[1], 0.0), flat=True))
        else:
            self.parts = [Stone(rng, f, 1.0, flat=cfg["kind"] == "slab")]
            if rng.uniform() < f["lean"]:  # a second block against the first
                a0 = rng.uniform(0, 2 * math.pi)
                s2 = rng.uniform(0.38, 0.55)
                h = self.parts[0].half
                self.parts.append(Stone(rng, f, s2, (0.75 * h[0] * math.cos(a0) * 1.0, 0.9 * h[1] * math.sin(a0), -h[2] + 0.42 * s2 * 0.5)))
        self.cluster = len(self.parts) > 1 or getattr(self, "lumpy", False)
        self.sink_share = f["sink"]
        lo = np.min([p.lo for p in self.parts], 0)
        hi = np.max([p.hi for p in self.parts], 0)
        self.lo, self.hi = lo, hi
        self.sink_share = f["sink"]

    def sd(self, p, info=False):
        if not info:
            out = self.parts[0].sd(p)
            for q in self.parts[1:]:
                near = np.linalg.norm(p - q.c, axis=1) < q.r_bound + 0.05
                d = np.full(len(p), 1e3)
                d[near] = q.sd(p[near])
                # far from a piece its distance is at least its bound's
                d[~near] = np.linalg.norm(p[~near] - q.c, axis=1) - q.r_bound
                out = np.minimum(out, d)
            return out
        d, I = self.parts[0].sd(p, True)
        I = {k: (np.array(v) if v is not None else None) for k, v in I.items()}
        I["part"] = np.zeros(len(p), int)
        for j, q in enumerate(self.parts[1:], 1):
            d2, I2 = q.sd(p, True)
            b = d2 < d
            for k in I:
                if k != "part" and I[k] is not None:
                    I[k][b] = I2[k][b]
            I["part"][b] = j
            d = np.minimum(d, d2)
        return d, I


# -------------------------------------------------------------------------------------------------- mesh and LODs
def _grad(fn, p, h):
    g = np.empty_like(p)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = fn(p + e) - fn(p - e)
    return g / (2 * h)
