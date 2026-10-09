"""Stream beds for the 3D tiles: what lies under and beside a river's water, per point (texel or vertex), the same in
every tile and LOD (grids on the terrain's cells read as cubic B-splines, and noise).

The consumer's note (pushieworld 110; Joe: "streambeds aren't textured right, and they aren't typically empty, they
have clutter and debris, rocks"): with real water in the river the bed showed, and it was the meadow's grass and
earth, banks included, with nothing in the channel. What real streams have (terrain_guide.md "Stream beds", with
sources; photos in workspace/level_refs/streams):
- the bed's material follows the stream's ENERGY (its grade): bedrock and boulders on steep reaches (cascade,
  step-pool), cobbles and gravel on middling ones (plane-bed, riffles), sand and silt where the water slows (pools,
  slack margins). Along a reach riffles (shallow, coarse) and pools (deep, fine) alternate every 5-7 channel widths;
  in a bend the pool lies against the OUTER bank and a bar of gravel builds on the inside;
- the banks' foot is wet: a damp, darker band a hand or two above the water, moss and algae on stones at the water
  line;
- it is never empty: boulders (some standing proud of the water), cobble patches on bars and riffles, slabs at the
  margin of steep reaches, driftwood caught on rocks and stranded on outer bends and bar heads, reeds and sedges
  along slow margins, leaf litter in the slack.

Three things are made from the built terrain's own river data (T.river_water_lines: path, water level, width):
- `Streams`: grids round every river (distance to the water's edge, water level, energy, bend, pool phase, flow
  direction), and the per-point rules: `shares` (the bed's layers: gravel, silt, bedrock, the damp bank), `colour`,
  `relief` (the maps' cobble lumps), `dz` (the bed's SHAPE in Field.column via terrain_ground.Edits: pools deeper on
  the outside of bends, riffles shallower, bars inside bends, an uneven bed; only ever under the water, never the
  banks, and the bed stays under the water's level except a bar's top);
- `clutter`: instances for an engine (clutter.csv): river_rock, cobbles, slab, driftwood, reeds, litter, each with a
  `place` (water / margin / bank / bar);
- the tiling swatches for the new layers (`cobble_swatch`, `silt_swatch`).

Spec: `"streams": false` turns all of it off (the river as before); `"streams": {...}` overrides `CFG`'s numbers;
`rivers.<name>.bed = {"energy": 0..1 | [source .. mouth values]}` sets a river's character by hand (0 a slow silty
lowland stream, 1 a boulder torrent) instead of reading it off its grade."""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import noise

CFG = {
    "reach": 14.0,           # m beyond the water's nominal edge the stream's zone runs (banks, bank stones)
    "grade": [0.04, 0.30],   # bed grade where the energy is 0 .. 1 (real reach types change at 1.5 / 3 / 6.5%: a game
    # level's rivers are compressed in length, so steeper than their character; see the guide)
    "spacing": [6.0, 2.5],   # pool-to-pool spacing in channel widths, at energy 0 (riffle-pool) .. 1 (step-pool)
    "bend": 0.2,             # half-width / radius of curvature that counts as a full bend
    "pool": 0.55,            # m: a pool's extra depth (x the channel's size)
    "riffle": 0.45,          # share of the depth a riffle's crest takes back
    "bar": 0.10,             # m: a point bar's top over the water (0: bars stay awash)
    "lump": 0.07,            # m: the bed's unevenness (metre-scale)
    "min_depth": 0.08,       # m of water the shaped bed keeps (bars aside)
    "damp": 0.5,             # m above the water the bank is damp (wandering)
    "shape": True,           # the bed's shape (False: material and clutter only)
    "clutter": 1.0,          # density of the stream clutter (0: none)
}
LAYERS = ("gravel", "silt", "bank")  # the layers a terrain with running rivers gains (plus rock / wet_rock: bedrock)
LOOK = {  # sRGB
    "gravel": [0.44, 0.41, 0.36], "silt": [0.33, 0.29, 0.22], "bank": [0.25, 0.21, 0.15],
    "moss": [0.20, 0.28, 0.11], "algae": [0.24, 0.27, 0.14], "deep": [0.20, 0.23, 0.17],
}
KINDS = {  # clutter kinds: size = the largest plan dimension (m) at scale 1 x scale; squash relative (1 = the asset's
    # own proportions); z = the bed / ground under the pivot (the asset's pivot sinks it)
    "river_rock": {"scale": [0.35, 1.8], "squash": [0.75, 1.3], "what": "a rounded water-worn boulder"},
    "cobbles": {"scale": [0.6, 1.6], "squash": [0.8, 1.3], "what": "a patch of 5-15 rounded cobbles (6-25 cm each)"},
    "slab": {"scale": [0.5, 2.0], "squash": [0.7, 1.3], "what": "a flat bank stone / ledge piece"},
    "driftwood": {"scale": [0.8, 4.5], "squash": [0.7, 1.5], "what": "a bare log, branch or small jam; yaw = its long "
                  "axis (0 = along world +x)"},
    "reeds": {"scale": [0.5, 1.4], "squash": [0.75, 1.35], "what": "a reed / sedge clump rooted at the water line"},
    "litter": {"scale": [0.8, 2.5], "squash": [1.0, 1.0], "what": "a leaf and twig debris patch (a decal)"},
}
PLACES = ("", "water", "margin", "bank", "bar")
SPACING = {"river_rock": 1.1, "cobbles": 0.8, "slab": 1.5, "driftwood": 2.2, "reeds": 0.9, "litter": 2.0}


def _ss(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


def config(T):
    """The spec's stream settings (CFG with "streams": {...} over it), or None when "streams" is false."""
    s = getattr(T, "spec", {}).get("streams", True)
    if s is False:
        return None
    s = s if isinstance(s, dict) else {}
    unknown = set(s) - set(CFG)
    if unknown:
        raise ValueError(f"streams: unknown keys {sorted(unknown)} (have {', '.join(CFG)})")
    return {**CFG, **s}


def _energy(T, name, grade, s, cfg):
    bed = ((getattr(T, "spec", {}).get("rivers") or {}).get(name) or {}).get("bed") or {}
    e = bed.get("energy", "auto") if isinstance(bed, dict) else "auto"
    if e is None or e == "auto":
        return _ss(cfg["grade"][0], cfg["grade"][1], grade)
    e = np.atleast_1d(np.asarray(e, float))
    if len(e) == 1:
        return np.full(len(s), float(np.clip(e[0], 0, 1)))
    u = s / max(float(s[-1]), 1e-9)
    return np.clip(np.interp(u, np.linspace(0, 1, len(e)), e), 0, 1)


class Streams:
    """The rivers' grids on the terrain's cells ([iy, ix], windowed per tile by the incremental export like any cell
    grid) and the per-point rules. `any` is False for a terrain without running water: nothing reads the rest."""

    def __init__(self, T, cfg=None):
        self.cfg = cfg = cfg or config(T) or dict(CFG)
        self.x0, self.y0, self.c = float(T.xs[0]), float(T.ys[0]), float(T.cell)
        self.names, self.reaches = [], []
        lines = getattr(T, "river_water_lines", None) or {}
        shape = T.H.shape
        reach = float(cfg["reach"])
        self.far = far = reach + 4.0
        sd = np.full(shape, far)
        G = {k: np.zeros(shape) for k in ("level", "energy", "bend", "phi", "w", "tx", "ty")}
        rid = np.zeros(shape, np.int8)
        c = self.c
        X, Y = np.asarray(T.X, float), np.asarray(T.Y, float)
        for name, rw in lines.items():
            xy, lv, w = np.asarray(rw["xy"], float), np.asarray(rw["level"], float), np.asarray(rw["width"], float)
            if len(xy) < 4 or not (w > 0).any():
                continue
            step = np.linalg.norm(np.diff(xy, axis=0), axis=1)
            s = np.r_[0, np.cumsum(step)]
            ds = max(float(np.mean(step)), 1e-3)
            sm = lambda a, m: ndimage.gaussian_filter1d(np.asarray(a, float), max(m / ds, 0.5), axis=0, mode="nearest")
            grade = sm(np.clip(-np.gradient(sm(lv, 12.0), s), 0, None), 15.0)
            ws = np.minimum(sm(np.where(w > 0, w, 0.0), 4.0), np.where(w > 0, w, 0.0) + 2.0)
            live = ws > 0.3
            xs_ = sm(xy, 6.0)
            t = np.gradient(xs_, axis=0)
            t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
            th = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
            kappa = sm(np.gradient(th, s), 10.0)
            wide = np.maximum(ws, 1.5)
            bend = np.clip(kappa * wide / float(cfg["bend"]), -1, 1) * _ss(2.5, 5.0, wide)  # (a torrent doesn't meander)
            en = _energy(T, name, grade, s, cfg)
            sp = cfg["spacing"][0] + (cfg["spacing"][1] - cfg["spacing"][0]) * en
            seed = int(sum(ord(ch) for ch in name)) % 997
            jit = noise.fbm(np.c_[s, np.zeros(len(s)), np.zeros(len(s))], 40.0, 2, seed=701 + seed) - 0.5
            phi = np.cumsum(np.r_[0, step] / (sp * 2 * wide)) + 0.6 * jit
            k_live = np.flatnonzero(live)
            if len(k_live) < 3:
                continue
            # cells within reach of the live channel
            tree = cKDTree(xy[k_live])
            rmax = float(ws.max()) + far + 3 * c
            lo, hi = xy[k_live].min(0) - rmax, xy[k_live].max(0) + rmax
            ix0, ix1 = np.clip(((np.array([lo[0], hi[0]]) - self.x0) / c).astype(int) + [0, 2], 0, shape[1])
            iy0, iy1 = np.clip(((np.array([lo[1], hi[1]]) - self.y0) / c).astype(int) + [0, 2], 0, shape[0])
            sub = (slice(iy0, iy1), slice(ix0, ix1))
            P = np.c_[X[sub].ravel(), Y[sub].ravel()]
            d0, j = tree.query(P, distance_upper_bound=rmax)
            ok = np.isfinite(d0)
            if not ok.any():
                continue
            q = np.flatnonzero(ok)
            i = k_live[j[q]]
            # the nearer of the two segments round the nearest sample: a continuous parameter along the line
            best_d, best_f = np.full(len(q), np.inf), i.astype(float)
            for a_, b_ in ((np.maximum(i - 1, 0), i), (i, np.minimum(i + 1, len(xy) - 1))):
                A, B = xy[a_], xy[b_]
                ab = B - A
                tt = np.clip(np.einsum("ij,ij->i", P[q] - A, ab) / np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-12), 0, 1)
                dd = np.linalg.norm(P[q] - (A + tt[:, None] * ab), axis=1)
                better = dd < best_d
                best_d = np.where(better, dd, best_d)
                best_f = np.where(better, a_ + tt * (b_ - a_), best_f)
            at = lambda arr: np.interp(best_f, np.arange(len(arr)), arr)
            wv = at(ws)
            tx, ty = at(t[:, 0]), at(t[:, 1])
            foot = np.c_[at(xy[:, 0]), at(xy[:, 1])]
            side = np.sign(tx * (P[q, 1] - foot[:, 1]) - ty * (P[q, 0] - foot[:, 0]))  # (+1 left of the flow)
            sdv = np.minimum(best_d - wv, far)
            flat = np.ravel_multi_index(np.unravel_index(q, (iy1 - iy0, ix1 - ix0)), (iy1 - iy0, ix1 - ix0))
            cur = sd[sub].ravel()[flat]
            take = sdv < cur
            f_ = flat[take]

            def put(grid, val):
                g = grid[sub].ravel()
                g[f_] = val[take]
                grid[sub] = g.reshape(iy1 - iy0, ix1 - ix0)
            put(sd, sdv)
            put(G["level"], at(lv))
            put(G["energy"], at(en))
            put(G["bend"], at(bend) * side)  # (> 0: the inside of the bend)
            put(G["phi"], at(phi))
            put(G["w"], wv)
            put(G["tx"], tx)
            put(G["ty"], ty)
            g = rid[sub].ravel()
            g[f_] = len(self.names) + 1
            rid[sub] = g.reshape(iy1 - iy0, ix1 - ix0)
            self.names.append(name)
            # reaches for the report: stretches of one character
            cls = np.digitize(en, [0.15, 0.4, 0.7])
            self.reaches.append({"name": name, "s": s, "energy": en, "grade": grade, "width": 2 * ws, "live": live,
                                 "class": cls, "xy": xy, "level": lv})
        self.any = bool(self.names)
        self.zone = (sd < reach + 1.0).astype(np.uint8)
        if not self.any:
            return
        self.sd = np.ascontiguousarray(sd)
        for k, v in G.items():
            setattr(self, k, np.ascontiguousarray(v))
        self.rid = rid
        ford = np.zeros(shape)
        for f in (getattr(T, "fords", None) or {}).values():
            fw = float(f.get("width", 8.0))
            ford = np.maximum(ford, _ss(1.4 * fw, 0.8 * fw, np.hypot(X - f["xy"][0], Y - f["xy"][1])))
        keep = np.zeros(shape)
        for m_ in ("sites", "routes"):
            if m_ in getattr(T, "masks", {}):
                keep = np.maximum(keep, np.clip(np.asarray(T.masks[m_], float), 0, 1))
        self.ford = np.ascontiguousarray(np.maximum(ford, ndimage.gaussian_filter(keep, 1.0)))

    # ---- at points
    def _at(self, a, xy):
        from .terrain_ground import _grid_at
        return _grid_at(a, xy, self.x0, self.y0, self.c)

    def in_zone(self, x, y):
        iy = np.clip(np.rint((y - self.y0) / self.c).astype(np.int64), 0, self.zone.shape[0] - 1)
        ix = np.clip(np.rint((x - self.x0) / self.c).astype(np.int64), 0, self.zone.shape[1] - 1)
        return np.flatnonzero(self.zone[iy, ix])

    def river_of(self, xy):
        iy = np.clip(np.rint((xy[:, 1] - self.y0) / self.c).astype(np.int64), 0, self.zone.shape[0] - 1)
        ix = np.clip(np.rint((xy[:, 0] - self.x0) / self.c).astype(np.int64), 0, self.zone.shape[1] - 1)
        return self.rid[iy, ix].astype(int) - 1

    def sample(self, xy):
        """The grids at points (in the zone): dict of sd (m to the water's nominal edge, negative in the channel),
        level, energy 0..1, bend (-1 outside .. 1 inside of a bend), phi (pool phase, cycles), w (half width m),
        t (flow direction, (n, 2)), ford 0..1, u (0 mid-channel .. 1 at the edge)."""
        g = {k: self._at(getattr(self, k), xy) for k in ("sd", "level", "energy", "bend", "phi", "w", "tx", "ty",
                                                         "ford")}
        g["energy"] = np.clip(g["energy"], 0, 1)
        g["bend"] = np.clip(g["bend"], -1, 1)
        g["ford"] = np.clip(g["ford"], 0, 1)
        g["u"] = np.clip(1 + g["sd"] / np.maximum(g["w"], 0.5), 0, 1.5)
        t = np.c_[g.pop("tx"), g.pop("ty")]
        g["t"] = t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-6)
        return g

    def forms(self, xy, g=None):
        """(pool, riffle, bar) 0..1 at points: pools every few widths and against the outer bank of a bend, riffles
        between them, bars on the inside of bends toward the bank."""
        g = g or self.sample(xy)
        Pf = np.c_[xy, np.zeros(len(xy))]
        pr = np.sin(2 * np.pi * g["phi"]) + 0.5 * (noise.fbm(Pf, 9.0, 2, seed=716) - 0.5)
        e = g["energy"]
        outer = _ss(0.2, 0.7, -g["bend"])
        pool = np.maximum(_ss(0.15, 0.8, pr) * (1 - 0.35 * np.abs(g["bend"])), outer) * (1 - g["ford"])
        riffle = _ss(0.15, 0.8, -pr) * (1 - outer)
        bar = _ss(0.2, 0.6, g["bend"]) * _ss(0.3, 0.75, g["u"]) * (1 - 0.6 * e) * (1 - g["ford"])
        return pool, riffle, bar

    # ---- the bed's shape (terrain_ground.Edits.column)
    def dz(self, x, y, h):
        """The height change of columns whose ground is h: only under the water (the banks keep their ground), the
        bed kept `min_depth` under the water's level except a bar's top."""
        cfg = self.cfg
        out = np.zeros(len(x))
        if not self.any or not cfg["shape"]:
            return out
        k = self.in_zone(x, y)
        if not len(k):
            return out
        xy = np.c_[x[k], y[k]]
        g = self.sample(xy)
        dep = g["level"] - h[k]
        m = _ss(0.05, 0.4, dep) * _ss(1.5, 0.0, g["sd"]) * (1 - g["ford"])
        kk = np.flatnonzero(m > 1e-4)
        if not len(kk):
            return out
        g = {a: b[kk] for a, b in g.items()}
        xy, dep, m = xy[kk], dep[kk], m[kk]
        pool, riffle, bar = self.forms(xy, g)
        Pf = np.c_[xy, np.zeros(len(xy))]
        size = np.clip(g["w"] / 6.0, 0.35, 1.2)  # (a brook's pools are shallower than a river's)
        # pools: deepest toward the outer bank in a bend, mid-channel on a straight
        skew = _ss(0.9, 0.2, np.abs(g["u"] - 0.25 - 0.45 * _ss(0.1, 0.6, -g["bend"])))
        d = -cfg["pool"] * size * pool * (0.35 + 0.65 * skew)
        d += cfg["riffle"] * riffle * np.maximum(dep - 0.18, 0.0) * (1 - pool)
        lump = noise.fbm(Pf, 1.4, 2, seed=717) - 0.5 + 0.6 * (noise.fbm(Pf, 4.0, 2, seed=718) - 0.5)
        d += 2 * cfg["lump"] * (0.5 + g["energy"]) * lump
        # a bar: the bed rises toward the inner bank to just over the water
        d += bar * (dep + cfg["bar"] * _ss(0.45, 0.9, g["u"]))
        top = dep - cfg["min_depth"] + bar * (cfg["min_depth"] + cfg["bar"])  # (the most the bed may rise)
        d = np.minimum(d, np.maximum(top, 0.0))
        out[k[kk]] = m * d
        return out

    # ---- materials
    def shares(self, P, N=None):
        """The stream's ground at points, or None when none is near: {"k": indices into P, "bed" (the wet bed 0..1),
        "damp" (the bank's wet band), "gravel" / "silt" / "rock" (shares of the bed, sum 1), "dep" (water depth m,
        negative above it), "moss", "bar", "pool", "energy", "u"}."""
        if not self.any:
            return None
        k = self.in_zone(P[:, 0], P[:, 1])
        if not len(k):
            return None
        xy, z = P[k, :2], P[k, 2]
        g = self.sample(xy)
        Pf = np.c_[xy, np.zeros(len(k))]
        wob = noise.fbm(Pf, 1.7, 2, seed=711) - 0.5
        dep = g["level"] - z
        gate = _ss(3.0, 1.0, g["sd"])
        bed = _ss(-0.07, 0.07, dep + 0.08 * wob) * gate
        damp = _ss(self.cfg["damp"] * (1 + 1.2 * wob), 0.05, -dep) * _ss(4.5, 2.0, g["sd"]) * (1 - bed)
        pool, riffle, bar = self.forms(xy, g)
        e = g["energy"]
        n5 = noise.fbm(Pf, 5.0, 2, seed=712)
        n2 = noise.fbm(Pf, 1.6, 3, seed=713)
        rock = _ss(0.55, 0.95, e + 0.5 * (n5 - 0.5)) * _ss(0.42, 0.6, noise.fbm(Pf, 3.5, 3, seed=714)) * \
            (1 - g["ford"])
        slow = _ss(0.5, 0.12, e)
        slack = _ss(0.72, 1.0, g["u"]) * (1 - _ss(0.0, 0.4, g["bend"]))  # (the margins' slack water)
        silt = slow * np.maximum(pool * _ss(0.85, 0.3, g["u"]), 0.7 * slack) * _ss(0.3, 0.5, n2 + 0.35 * pool) + \
            (1 - slow) * 0.5 * pool * _ss(0.55, 0.7, n2)  # (sand in a torrent's plunge pools)
        silt = np.clip(silt * (1 - bar) * (1 - rock) * (1 - g["ford"]), 0, 1)
        moss = np.exp(-((dep + 0.06) / 0.16) ** 2) * (0.4 + 0.6 * noise.fbm(Pf, 0.9, 2, seed=715))
        return {"k": k, "bed": bed, "damp": damp, "gravel": np.clip(1 - rock - silt, 0, 1), "silt": silt, "rock": rock,
                "dep": dep, "moss": moss, "bar": bar, "pool": pool, "riffle": riffle, "energy": e, "u": g["u"],
                "sd": g["sd"]}

    def colour(self, P, c, rc, st):
        """The display colour (sRGB) at the stream's points P (= the rows st["k"]): c the ground's colour as painted,
        rc the rock's. The bed's own materials under the water (wet: darker; fine and greenish in pools, paler dry
        gravel on bars), moss and algae at the water line, the bank's damp band darker."""
        n = len(P)
        Pf = np.c_[P[:, :2], np.zeros(n)]
        dep = st["dep"]
        wetd = _ss(-0.05, 0.1, dep)
        # cobbles and gravel: stones' tones at 0.6 m and patches at 2.5 m (the stones themselves are the swatch's)
        mot = 0.55 * (noise.fbm(Pf, 0.6, 2, seed=721) - 0.5) + 0.45 * (noise.fbm(Pf, 2.5, 2, seed=722) - 0.5)
        warm = noise.fbm(Pf, 3.0, 2, seed=723) - 0.5
        gr = np.asarray(LOOK["gravel"]) * (1 + 0.5 * mot)[:, None] * (1 + warm[:, None] * np.array([0.10, 0.0, -0.12]))
        # (wet stone is darker, not black: the water over it darkens it again in the engine; riffles' clean coarse
        # stones paler, the pools' duller)
        gr = gr * (1.12 - 0.24 * wetd - 0.10 * _ss(0.2, 1.0, dep))[:, None]
        gr = gr * (1 + 0.16 * st["riffle"] - 0.14 * st["pool"])[:, None]
        si = np.asarray(LOOK["silt"]) * (1 + 0.16 * (noise.fbm(Pf, 1.8, 2, seed=724) - 0.5))[:, None]
        deep = _ss(0.3, 1.2, dep)[:, None]
        si = (si * (1 - 0.5 * deep) + np.asarray(LOOK["deep"]) * 0.5 * deep) * (1.0 - 0.3 * wetd)[:, None]
        br = rc * (1.0 - 0.5 * wetd)[:, None]
        bedc = gr * st["gravel"][:, None] + si * st["silt"][:, None] + br * st["rock"][:, None]
        # moss and algae on the stones at the water line (not on silt)
        ms = (st["moss"] * (st["gravel"] + st["rock"]) * 0.55)[:, None]
        bedc = bedc * (1 - ms) + np.asarray(LOOK["moss"]) * ms
        al = (_ss(0.05, 0.4, dep) * st["pool"] * 0.25 * (st["gravel"] + st["rock"]))[:, None]
        bedc = bedc * (1 - al) + np.asarray(LOOK["algae"]) * al
        # the bank's damp band: the ground's own colour darker, bare damp earth showing through it
        dm = st["damp"][:, None]
        bank = c * 0.62 * 0.45 + np.asarray(LOOK["bank"]) * 0.55 * (1 + 0.3 * mot[:, None])
        out = c * (1 - dm) + bank * dm
        b = st["bed"][:, None]
        return np.clip(out * (1 - b) + bedc * b, 0, 1)

    def relief(self, P, w, texel):
        """The bed's fine relief as a plan gradient (n, 2), for the maps' normals: cobble and boulder lumps where the
        gravel layer weighs w (each octave fading where the texel can't carry it)."""
        n = len(P)
        g = np.zeros((n, 2))
        k = np.flatnonzero(w > 1e-3)
        if not len(k):
            return g
        Pf = np.c_[P[k, :2], np.zeros(len(k))]
        e = 0.04
        O = np.array([[e, 0, 0], [-e, 0, 0], [0, e, 0], [0, -e, 0]])
        vis = lambda size: float(_ss(3.0 * texel, 5.0 * texel, size))
        for amp, size, seed in ((0.05, 0.9, 731), (0.03, 0.4, 732)):
            v = vis(size)
            if v <= 1e-3:
                continue
            f = (noise.fbm(np.concatenate([Pf + o for o in O]), size, 2, seed=seed) ** 2).reshape(4, -1)
            g[k] += (w[k] * v * amp)[:, None] * np.c_[(f[0] - f[1]) / (2 * e), (f[2] - f[3]) / (2 * e)]
        return g

    # ---- the report
    def report(self):
        """Lines per river: its reaches by character (from the bed's grade, or as set)."""
        names = ["slow (silt and gravel, reeds)", "riffle-pool (gravel and cobbles)", "plane-bed / step-pool (cobbles "
                 "and boulders)", "cascade (boulders and bedrock)"]
        out = []
        for r in self.reaches:
            live = r["live"]
            if not live.any():
                continue
            parts = []
            s, cls = r["s"], r["class"]
            i = int(np.flatnonzero(live)[0])
            end = int(np.flatnonzero(live)[-1])
            while i <= end:
                j = i
                while j < end and cls[j + 1] == cls[i]:
                    j += 1
                if s[j] - s[i] >= 15 or not parts:
                    parts.append(f"{s[i]:.0f}-{s[j]:.0f} m {names[cls[i]]} (grade {100 * r['grade'][i:j + 1].mean():.0f}%, "
                                 f"{r['width'][i:j + 1].mean():.0f} m wide)")
                i = j + 1
            out.append(f"stream bed {r['name']}: " + "; ".join(parts))
        return out


# ---------------------------------------------------------------------------------------------- clutter

def clutter(T, mats, field, box=None, seed=11):
    """Stream clutter as rows [x, y, z, kind index (into KINDS), scale, yaw deg, squash, place index (PLACES), river
    index]: rounded boulders in the channel (more and bigger with the stream's energy, in clusters and in rows across
    the steps; the bigger ones stand proud of the water) and on the banks, cobble patches on bars, riffles and
    margins, slabs along steep margins, driftwood caught on boulders and stranded on outer bends and bar heads, reeds
    along slow margins, litter in the slack. Deterministic; nothing on fords, routes or sites. box: [[x0, y0],
    [x1, y1]]."""
    S = getattr(mats, "streams", None)
    empty = np.zeros((0, 9))
    if S is None or not S.any or S.cfg["clutter"] <= 0:
        return empty
    dens = float(S.cfg["clutter"])
    kinds = list(KINDS)
    iy, ix = np.nonzero(S.zone)
    zx0, zx1 = S.x0 + ix.min() * S.c - S.c, S.x0 + ix.max() * S.c + S.c
    zy0, zy1 = S.y0 + iy.min() * S.c - S.c, S.y0 + iy.max() * S.c + S.c
    if box is not None:
        (bx0, by0), (bx1, by1) = box
        zx0, zx1, zy0, zy1 = max(zx0, bx0), min(zx1, bx1), max(zy0, by0), min(zy1, by1)
    if zx1 <= zx0 or zy1 <= zy0:
        return empty
    out = []
    rocks = None
    for ki, kind in enumerate(kinds):
        sp = SPACING[kind]
        # (the lattice is anchored at the world's origin, so a block's rows are the whole level's rows)
        xs = np.arange(np.floor(zx0 / sp) - 1, np.ceil(zx1 / sp) + 2) * sp  # (a cell past the box: jitter crosses it)
        ys = np.arange(np.floor(zy0 / sp) - 1, np.ceil(zy1 / sp) + 2) * sp
        gx, gy = np.meshgrid(xs, ys)
        xy = np.c_[gx.ravel(), gy.ravel()]
        h3 = lambda a, b: noise._hash(np.rint(xy[:, 0] / sp).astype(np.int64), np.rint(xy[:, 1] / sp).astype(np.int64),
                                      np.full(len(xy), a, np.int64), seed + b)
        xy = xy + (np.c_[h3(1, ki), h3(2, ki)] - 0.5) * 0.9 * sp
        u_keep, u_a, u_b, u_c = h3(3, ki), h3(4, ki), h3(5, ki), h3(6, ki)
        k = S.in_zone(xy[:, 0], xy[:, 1])
        k = k[(xy[k, 0] >= zx0) & (xy[k, 0] < zx1) & (xy[k, 1] >= zy0) & (xy[k, 1] < zy1)]
        if not len(k):
            continue
        xy, u_keep, u_a, u_b, u_c = xy[k], u_keep[k], u_a[k], u_b[k], u_c[k]
        h, cs = field.column(xy[:, 0], xy[:, 1])
        g = S.sample(xy)
        ok = (cs > 0.75) & (g["ford"] < 0.25) & (g["sd"] < S.cfg["reach"])
        if mats.sea is not None:
            ok &= h > mats.sea + 0.1
        xy, h, u_keep, u_a, u_b, u_c = xy[ok], h[ok], u_keep[ok], u_a[ok], u_b[ok], u_c[ok]
        g = {a: b[ok] for a, b in g.items()}
        n = len(xy)
        if not n:
            continue
        Pf = np.c_[xy, np.zeros(n)]
        dep = g["level"] - h
        e, sd, u = g["energy"], g["sd"], g["u"]
        pool, riffle, bar = S.forms(xy, g)
        inwater = (dep > 0.04) & (sd < 0.5)
        flow = np.degrees(np.arctan2(g["t"][:, 1], g["t"][:, 0]))
        lo, hi = KINDS[kind]["scale"]
        sq0, sq1 = KINDS[kind]["squash"]
        squash = sq0 + (sq1 - sq0) * u_c
        yaw = 360.0 * u_b
        place = np.zeros(n, int)
        z = h.copy()
        if kind == "river_rock":
            clus = 0.25 + 1.5 * _ss(0.42, 0.68, noise.fbm(Pf, 4.0, 2, seed=741))
            rows = _ss(0.7, 0.95, -np.sin(2 * np.pi * g["phi"])) * _ss(0.3, 0.7, e)  # (the steps of a step-pool reach)
            edge = _ss(0.45, 0.9, u)
            p_w = (0.03 + 0.42 * e ** 1.5) * clus * (edge + (1 - edge) * (0.4 + 0.6 * _ss(0.1, 0.5, e))) + 0.5 * rows
            p_w = p_w * (1 + 0.8 * riffle)
            p_w = p_w * (1 - 0.7 * pool * (1 - rows))
            hb = -dep
            p_b = (0.012 + 0.12 * e) * clus * _ss(5.0, 1.0, sd) * (hb < 1.6) * (0.6 + 0.8 * _ss(0.1, 0.6, -g["bend"]))
            p = np.where(inwater, p_w, np.where(sd > -0.5, p_b, 0.0))
            med = 0.42 + 0.55 * e + 0.25 * rows
            scale = np.clip(med * np.exp(0.5 * _normal(u_a)), lo, np.minimum(hi, np.maximum(0.5, 1.3 * g["w"])))
            squash = np.where(scale > 1.0, sq0 + (1.0 - sq0) * u_c, squash)  # (big ones sit lower: slabby)
            place = np.where(inwater, 1, np.where(-dep < 0.3, 2, 3))
        elif kind == "cobbles":
            margin = _ss(-1.4, -0.3, sd) * _ss(1.2, 0.2, sd)
            shallow = _ss(0.55, 0.15, dep)
            st = S.shares(np.c_[xy, h])
            silt = np.zeros(n)
            if st is not None:
                silt[st["k"]] = st["silt"]
            p = np.maximum(np.maximum(0.8 * bar, 0.3 * riffle * (0.4 + 0.6 * shallow)), 0.4 * margin) * (1 - silt) * \
                (0.35 + 0.65 * _ss(0.05, 0.4, e)) * (0.5 + _ss(0.4, 0.6, noise.fbm(Pf, 2.5, 2, seed=742)))
            p = p * ((dep > -0.3) & (sd < 1.5))
            scale = lo + (hi - lo) * u_a ** 1.5
            place = np.where(bar > 0.4, 4, np.where(dep > 0.03, 1, 2))
        elif kind == "slab":
            p = 0.22 * _ss(0.35, 0.75, e) * _ss(-1.2, -0.2, sd) * _ss(2.0, 0.6, sd) * \
                _ss(0.45, 0.65, noise.fbm(Pf, 5.0, 2, seed=743))
            scale = lo + (hi - lo) * u_a ** 1.3
            yaw = flow + 40 * (u_b - 0.5)
            place = np.where(dep > 0.03, 1, 2)
        elif kind == "driftwood":
            margin = _ss(-1.5, -0.2, sd) * _ss(1.5, 0.3, sd)
            p = margin * (0.02 + 0.16 * _ss(0.2, 0.7, -g["bend"])) + 0.12 * bar * _ss(0.4, 0.0, dep) * (sd < 0.5)
            p = p * (0.4 + 1.2 * _ss(0.5, 0.7, noise.fbm(Pf, 12.0, 2, seed=744)))  # (in drifts, bare stretches between)
            scale = np.clip(1.6 * np.exp(0.55 * _normal(u_a)), lo, np.minimum(hi, 2.5 * g["w"] + 1.5))
            yaw = flow + 50 * (u_b - 0.5)  # (stranded along the flow)
            place = np.where(bar > 0.4, 4, 2)
        elif kind == "reeds":
            slow = _ss(0.45, 0.15, e)
            st = S.shares(np.c_[xy, h])
            rk = np.zeros(n)
            if st is not None:
                rk[st["k"]] = st["rock"]
            p = 0.6 * slow * (np.abs(sd) < 1.2) * _ss(-0.3, -0.1, dep) * _ss(0.35, 0.2, dep) * \
                _ss(0.5, 0.62, noise.fbm(Pf, 7.0, 2, seed=745)) * (1 - 0.6 * bar) * (1 - rk) * \
                (1 - 0.7 * _ss(0.2, 0.6, -g["bend"]))  # (the outer bank is cut, not reedy)
            scale = lo + (hi - lo) * u_a
            place = np.full(n, 2)
        else:  # litter: leaf and twig drifts in the slack of pools and on the bank's foot
            p = 0.22 * pool * (np.abs(sd) < 1.0) * _ss(0.6, 0.2, e) + 0.05 * (sd > 0.4) * (sd < 4.0) * (-dep < 1.0)
            p = p * _ss(0.4, 0.6, noise.fbm(Pf, 6.0, 2, seed=746))
            scale = lo + (hi - lo) * u_a
            place = np.where(sd > 0.4, 3, 2)
        keep = u_keep < np.clip(p * dens, 0, 1)
        if not keep.any():
            continue
        R = np.c_[xy, z, np.full(n, ki), scale, np.mod(yaw, 360.0), squash, place, S.river_of(xy)][keep]
        if kind == "river_rock":
            R = _thin(R, 0.42)
            rocks = (R, g["t"][keep], g["w"][keep])
        elif kind == "slab":
            R = _thin(R, 0.5)
        elif kind == "driftwood":
            R = _thin(R, 0.6)
            # logs caught on the upstream side of the big boulders standing in the water, lying across the flow
            if rocks is not None and len(rocks[0]):
                Rr = rocks[0]
                tdir = _dirs(S, Rr[:, :2])
                hh = noise._hash(np.rint(Rr[:, 0] * 10).astype(np.int64), np.rint(Rr[:, 1] * 10).astype(np.int64),
                                 np.full(len(Rr), 7, np.int64), seed + 91)
                h2 = noise._hash(np.rint(Rr[:, 0] * 10).astype(np.int64), np.rint(Rr[:, 1] * 10).astype(np.int64),
                                 np.full(len(Rr), 8, np.int64), seed + 92)
                sel = (Rr[:, 7] == 1) & (Rr[:, 4] > 0.85) & (hh < 0.3 * dens)
                if sel.any():
                    q = Rr[sel]
                    td = tdir[sel]
                    pos = q[:, :2] - td * (0.45 * q[:, 4:5] + 0.15)
                    hz, _ = field.column(pos[:, 0], pos[:, 1])
                    wq = S.sample(pos)["w"]
                    ln = np.clip(1.2 + 2.2 * h2[sel], lo, np.minimum(hi, 2.2 * wq + 1.0))
                    yw = np.degrees(np.arctan2(td[:, 1], td[:, 0])) + 90 + 70 * (hh[sel] / (0.3 * dens) - 0.5)
                    R = np.concatenate([R, np.c_[pos, hz, np.full(len(q), ki), ln, np.mod(yw, 360.0),
                                                 0.9 + 0.5 * h2[sel], np.ones(len(q)), q[:, 8]]])
        out.append(R)
    return np.concatenate(out) if out else empty


def _normal(u):
    """A standard normal from a uniform (an approximation good to ~3 sigma)."""
    u = np.clip(u, 1e-4, 1 - 1e-4)
    return 4.91 * (u ** 0.14 - (1 - u) ** 0.14)


def _dirs(S, xy):
    return S.sample(xy)["t"]


def _thin(R, share):
    """Greedy thinning: a piece closer to a bigger one than `share` x the sum of their sizes goes (stones don't
    stand inside each other; spacing follows size, not a grid)."""
    if len(R) < 2:
        return R
    order = np.argsort(-R[:, 4], kind="stable")
    R = R[order]
    tree = cKDTree(R[:, :2])
    alive = np.ones(len(R), bool)
    rmax = float(R[:, 4].max())
    for i in range(len(R)):
        if not alive[i]:
            continue
        for j in tree.query_ball_point(R[i, :2], share * (R[i, 4] + rmax)):
            if j > i and alive[j] and np.hypot(*(R[j, :2] - R[i, :2])) < share * (R[i, 4] + R[j, 4]):
                alive[j] = False
    R = R[alive]
    return R[np.lexsort((R[:, 0], R[:, 1]))]


def counts(S, C):
    """{river: {kind: n}} and per river the share of in-water river rocks standing proud of the water is not known
    here (it needs the water's depth): see `summary`."""
    out = {}
    kinds = list(KINDS)
    for r, name in enumerate(S.names):
        sel = C[C[:, 8] == r] if len(C) else C
        out[name] = {k: int((sel[:, 3] == i).sum()) for i, k in enumerate(kinds)}
    return out


def summary(S, C, box=None):
    """Report lines: the clutter per river (and how many of the rocks in the water stand proud of it), a WARNING for
    a river with none."""
    lines = []
    kinds = list(KINDS)
    for r, name in enumerate(S.names):
        sel = C[C[:, 8] == r] if len(C) else np.zeros((0, 9))
        if not len(sel):
            if box is None:
                lines.append(f"WARNING stream clutter {name}: none placed (the channel has no rocks, wood or reeds; is "
                             f"\"streams\".clutter 0, or the river all ford / route?)")
            continue
        n = {k: int((sel[:, 3] == i).sum()) for i, k in enumerate(kinds)}
        rk = sel[(sel[:, 3] == kinds.index("river_rock")) & (sel[:, 7] == 1)]
        proud = ""
        if len(rk):
            dep = S.sample(rk[:, :2])["level"] - rk[:, 2]
            top = 0.6 * rk[:, 4] * rk[:, 6] * 0.8
            proud = f" ({int((top > dep).sum())} of {len(rk)} rocks in the water stand proud of it)"
        lines.append(f"stream clutter {name}: " + ", ".join(f"{v} {k}" for k, v in n.items() if v) + proud)
    return lines


def manifest(S, C):
    """The export manifest's "clutter" section for the stream kinds."""
    return {"kinds": {k: {"scale_m": v["scale"], "squash": v["squash"], "what": v["what"], "z": "surface"}
                      for k, v in KINDS.items()},
            "places": {"water": "in the channel, its base on the bed under the water", "margin": "at the water line",
                       "bank": "on the bank beside the water", "bar": "on a gravel bar inside a bend",
                       "": "dry ground (the older kinds)"},
            "how": "clutter.csv rows x,y,z,kind,scale,yaw,squash,place: scale = the piece's largest plan dimension in "
                   "metres, squash = its height relative to the asset's own proportions (instance scale (s, s, s x "
                   "squash) on an asset 1 m across), yaw degrees about up (driftwood: its long axis, 0 = along +x), z "
                   "= the ground or bed under its pivot (kinds with \"z\": \"surface\"; the asset's pivot sinks it). "
                   "Water depth at a row = the river's level there (rivers in meta / the manifest) minus z.",
            "rivers": counts(S, C)}


# ---------------------------------------------------------------------------------------------- swatches

def cobble_swatch(size=2.0, res=256, seed=4251):
    """A tileable bed swatch (top view, periodic): rounded cobbles and pebbles packed on gravel, 3-22 cm (a few big,
    many small: no two rows alike), each its own tone (grey, buff, a few dark or pale), dark wet gaps between, grit on
    the stones. Returns what terrain_ground.grass_swatch returns."""
    from .terrain_swatch import spectral
    L = float(size)
    n = int(round(L * res))
    rng = np.random.default_rng(seed)
    t = L / n
    hgt = 0.004 * spectral(n, 1.2, seed + 1, lo=10)
    tone = 0.62 + 0.10 * spectral(n, 0.8, seed + 2, lo=12)  # (the gravel between: darker)
    tint = np.zeros((n, n, 3))
    ns = int(1500 * (L / 2.0) ** 2)
    rad = np.clip(0.028 * np.exp(0.55 * rng.standard_normal(ns)), 0.012, 0.11)
    order = np.argsort(rad)  # (small first: the big stones lie on top)
    cen = rng.random((ns, 2)) * n
    for q in order:
        r = rad[q] / t
        cx, cy = cen[q]
        el = rng.uniform(0.6, 1.0)
        a = rng.uniform(0, np.pi)
        ri = int(r + 2)
        ii, jj = np.mgrid[int(cy) - ri:int(cy) + ri + 1, int(cx) - ri:int(cx) + ri + 1]
        dx, dy = jj - cx, ii - cy
        ca, sa = np.cos(a), np.sin(a)
        d2 = ((dx * ca + dy * sa) / r) ** 2 + ((-dx * sa + dy * ca) / (r * el)) ** 2
        dome = rad[q] * 0.55 * np.sqrt(np.clip(1 - d2, 0, 1))
        sl = (ii % n, jj % n)
        m = (d2 < 1) & (dome + 0.2 * rad[q] > hgt[sl])
        if not m.any():
            continue
        u = rng.random()
        tn = rng.uniform(0.85, 1.2) if u < 0.75 else (rng.uniform(0.55, 0.75) if u < 0.9 else rng.uniform(1.3, 1.5))
        hv, tv, cv = hgt[sl], tone[sl], tint[sl]
        hv[m] = np.maximum(hv[m], dome[m])
        tv[m] = tn * (0.86 + 0.14 * np.sqrt(np.clip(1 - d2[m], 0, 1)))  # (a little darker toward each stone's foot)
        cv[m] = rng.normal(0, 0.035) * np.array([1.0, 0.2, -1.0])
        hgt[sl], tone[sl], tint[sl] = hv, tv, cv
    grit = spectral(n, 0.5, seed + 3, lo=30)
    tone = tone * (1 + 0.06 * grit)
    # the gaps between stones are deep and dark (shadowed, wet)
    low = ndimage.gaussian_filter(hgt, 2.0, mode="wrap")
    tone = tone * (0.8 + 0.2 * _ss(-0.006, 0.004, hgt - low))
    alb = tone[..., None] * (1 + tint)
    alb = alb / alb.reshape(-1, 3).mean(0)
    hgt = ndimage.gaussian_filter(hgt, 0.6, mode="wrap")
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": np.ones((n, n)), "size_m": L,
            "texels_per_m": n / L, "n": n}


def silt_swatch(size=2.0, res=256, seed=4253):
    """A tileable silt / damp earth swatch: smooth fine sediment with faint current ripples in patches, a scatter of
    small pebbles half sunk, dark leaf and twig flecks."""
    from .terrain_swatch import spectral
    L = float(size)
    n = int(round(L * res))
    rng = np.random.default_rng(seed)
    t = L / n
    yy, xx = np.mgrid[0:n, 0:n] * t
    mx, my = int(round(0.3 * L / 0.06)), int(round(0.95 * L / 0.06))
    warp = spectral(n, 2.4, seed + 1, lo=3) * 1.3
    ph = 2 * np.pi * (mx * xx + my * yy) / L + warp * 2 * np.pi
    patch = np.clip(0.3 + 1.6 * spectral(n, 2.0, seed + 2, lo=4), 0, 1)
    hgt = 0.002 * np.sin(ph) * patch + 0.003 * spectral(n, 1.5, seed + 4, lo=6)
    alb = 1 + 0.07 * spectral(n, 1.0, seed + 3, lo=6) + 0.03 * np.sin(ph) * patch
    for kind, cnt in (("pebble", int(90 * (L / 2.0) ** 2)), ("fleck", int(160 * (L / 2.0) ** 2))):
        c = rng.random((cnt, 2)) * n
        for cx, cy in c:
            if kind == "pebble":
                r, el, tn = rng.uniform(0.006, 0.022) / t, rng.uniform(0.6, 1.0), rng.uniform(0.75, 1.3)
            else:
                r, el, tn = rng.uniform(0.01, 0.03) / t, rng.uniform(0.15, 0.4), rng.uniform(0.45, 0.7)
            a = rng.uniform(0, np.pi)
            ri = int(r + 2)
            ii, jj = np.mgrid[int(cy) - ri:int(cy) + ri + 1, int(cx) - ri:int(cx) + ri + 1]
            dx, dy = jj - cx, ii - cy
            ca, sa = np.cos(a), np.sin(a)
            d = np.sqrt(((dx * ca + dy * sa) / r) ** 2 + ((-dx * sa + dy * ca) / (r * el)) ** 2)
            m = np.clip((1.15 - d) * 3, 0, 1)
            sl = (ii % n, jj % n)
            alb[sl] = alb[sl] * (1 - m) + tn * m
            if kind == "pebble":
                hgt[sl] = np.maximum(hgt[sl], 0.5 * r * t * np.sqrt(np.clip(1 - d * d, 0, 1)))
    alb = np.repeat(alb[..., None], 3, -1) * np.array([1.0, 0.98, 0.95])
    alb = alb / alb.reshape(-1, 3).mean(0)
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": np.ones((n, n)), "size_m": L,
            "texels_per_m": n / L, "n": n}
