"""class Streams: the streams of a terrain. Part of terrain streams (terrain_stream.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import terrain_stream
from . import noise
from .terrain_stream import _energy, _shore, _ss, config

class Streams:
    """The rivers' grids on the terrain's cells ([iy, ix], windowed per tile by the incremental export like any cell
    grid) and the per-point rules. `any` is False for a terrain without running water: nothing reads the rest."""

    def __init__(self, T, cfg=None):
        self.cfg = cfg = cfg or config(T) or dict(terrain_stream.CFG)
        self.x0, self.y0, self.c = float(T.xs[0]), float(T.ys[0]), float(T.cell)
        self.names, self.report_reaches = [], []
        lines = getattr(T, "river_water_lines", None) or {}
        shape = T.H.shape
        reach = float(cfg["reach"])
        self.far = far = reach + 4.0
        sd = np.full(shape, far)
        G = {k: np.zeros(shape) for k in ("level", "energy", "bend", "phi", "w", "tx", "ty", "side", "still")}
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
            # (which bank: +1 left of the flow; easing through 0 over the middle of the channel)
            put(G["side"], side * np.clip(best_d / np.maximum(0.35 * wv, 0.5), 0, 1))
            put(G["w"], wv)
            put(G["tx"], tx)
            put(G["ty"], ty)
            g = rid[sub].ravel()
            g[f_] = len(self.names) + 1
            rid[sub] = g.reshape(iy1 - iy0, ix1 - ix0)
            self.names.append(name)
            # reaches for the report: stretches of one character
            cls = np.digitize(en, [0.15, 0.4, 0.7])
            self.report_reaches.append({"name": name, "s": s, "energy": en, "grade": grade, "width": 2 * ws, "live": live,
                                 "class": cls, "xy": xy, "level": lv, "bend": bend})
        # lakes (not the sea): still water with a shore (terrain_shore): no pools, riffles, bars or cut banks
        for name, mask, level in (_shore.still_waters(T) if cfg.get("lakes", True) else ()):
            sdl = _shore.signed_distance(mask, c, far)
            take = (sdl < sd) & (sdl < far - 1e-6)
            if not take.any():
                continue
            sd[take] = sdl[take]
            for k_, v_ in (("level", level), ("energy", 0.0), ("bend", 0.0), ("phi", 0.25), ("w", 6.0), ("tx", 1.0),
                           ("ty", 0.0), ("side", 0.0), ("still", 1.0)):
                G[k_][take] = v_
            rid[take] = len(self.names) + 1
            self.names.append("lake " + name)
        self.any = bool(self.names)
        self.zone = (sd < reach + 1.0).astype(np.uint8)
        if not self.any:
            return
        self.sd = np.ascontiguousarray(sd)
        for k, v in G.items():
            setattr(self, k, np.ascontiguousarray(v))
        self.rid = rid
        # waterfalls (terrain_falls): the plunge pool (1 inside, 0 past 1.4 radii) and the face's foot (fallen blocks)
        falls = [f for f in (getattr(T, "falls", None) or []) if f.get("into") != "sea"]  # (local: the grids are
        if falls:  # what tiles read, windowed; a list on self made every fall edit a global change)
            plunge, foot, lipw = np.zeros(shape), np.zeros(shape), np.zeros(shape)
            from .terrain_falls import HOLD_CELLS, HOLD_MIN
            hold = max(HOLD_CELLS * float(T.cell), HOLD_MIN)
            for f in falls:
                pc, R = np.array(f["pool"]["xyz"][:2]), float(f["pool"]["radius"])
                plunge = np.maximum(plunge, _ss(1.4 * R, 0.8 * R, np.hypot(X - pc[0], Y - pc[1])))
                lip = np.mean(np.array(f["lip"])[:, :2], 0)
                t_ = np.array(f["flow"], float)
                al = (X - lip[0]) * t_[0] + (Y - lip[1]) * t_[1]
                ac = np.abs(-(X - lip[0]) * t_[1] + (Y - lip[1]) * t_[0])
                reach = 0.35 * float(f["drop"]) + 3.0
                foot = np.maximum(foot, _ss(-0.5, 0.5, al) * _ss(reach, 0.5 * reach, al) *
                                  _ss(0.5 * f["width"] + reach, 0.5 * f["width"], ac))
                # the lip: water-worn bedrock across the channel for the face's hold upstream of the lip line. The
                # level grid can't say it's under water there (its cells straddle the drop: the pool's level pulled
                # it down), so the lip read as dry bank and bare earth: a flat tan slab (pushieworld note 124)
                lipw = np.maximum(lipw, _ss(-hold - 2.0, -hold, al) * _ss(0.6, 0.0, al) *
                                  _ss(0.5 * f["width"] + 1.5, 0.5 * f["width"] + 0.3, ac))
            self.plunge, self.foot, self.lip = (np.ascontiguousarray(a) for a in (plunge, foot, lipw))
        ford = np.zeros(shape)
        for f in (getattr(T, "fords", None) or {}).values():
            fw = float(f.get("width", 8.0))
            ford = np.maximum(ford, _ss(1.4 * fw, 0.8 * fw, np.hypot(X - f["xy"][0], Y - f["xy"][1])))
        keep = np.zeros(shape)
        for m_ in ("sites", "routes"):
            if m_ in getattr(T, "masks", {}):
                keep = np.maximum(keep, np.clip(np.asarray(T.masks[m_], float), 0, 1))
        self.ford = np.ascontiguousarray(np.maximum(ford, ndimage.gaussian_filter(keep, 1.0)))

    @property
    def reaches(self):
        """Per river, its samples along the path (s, energy, grade, width, bend, level, xy): for the report and the
        manifest only. Kept under `report_reaches`, which the incremental export's fingerprint skips: what the tiles
        read is the grids (windowed per tile), and these whole-river arrays made any river edit a global change."""
        return self.report_reaches

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
                                                         "ford", "side", "still")}
        g["still"] = np.clip(g["still"], 0, 1)
        g["energy"] = np.clip(g["energy"], 0, 1)
        for k in ("plunge", "foot", "lip"):  # (waterfalls only)
            g[k] = np.clip(self._at(getattr(self, k), xy), 0, 1) if hasattr(self, k) else np.zeros(len(xy))
        g["side"] = np.clip(g["side"], -1, 1)
        g["curve"] = np.clip(g["bend"], -1, 1)  # (the path's own bends)
        # along a straight reach the thalweg still wanders from bank to bank (alternate bars): a pool against one
        # bank, the next against the other, a bar opposite each; real bends override it
        alt = self.cfg["alternate"] * _ss(2.0, 4.0, g["w"]) * np.sin(np.pi * g["phi"]) * g["side"] * (1 - g["still"])
        g["bend"] = np.clip(g["curve"] - alt * (1 - np.abs(g["curve"])), -1, 1)
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
        run = 1 - g["still"]  # (still water has none of them)
        pl = g.get("plunge", 0.0)  # (a waterfall's plunge pool: a pool, nothing else)
        return np.maximum(pool * run, pl), riffle * run * (1 - pl), bar * run * (1 - pl)

    # ---- the bed's shape (terrain_ground.Edits.column)
    def cut(self, xy, g):
        """(outer 0..1, cut height m, inner 0..1, cut distance m) at points: where the bank is a cut bank and how
        high, where it is the bar's side, and how far from the water's nominal edge the cut stands at most (on low
        flat ground the bank never reaches the cut's height: cut by height alone the channel widened to the zone's
        edge)."""
        lo, hi = self.cfg["cut"]
        near = _ss(6.0, 4.0, g["sd"]) * (1 - g["ford"])
        n = noise.fbm(np.c_[xy, np.zeros(len(xy))], 7.0, 2, seed=751)
        hc = (lo + (hi - lo) * n) * np.clip(g["w"] / 5.0, 0.5, 1.2)
        outer = _ss(0.15, 0.5, -g["bend"]) * near * (1.0 if hi > 0 else 0.0) * (1 - g["still"])
        inner = _ss(0.15, 0.5, g["bend"]) * near * (1 - g["still"])
        return outer, hc, inner, 0.5 + 2.4 * hc

    def dz(self, x, y, h, riser=None):
        """The height change of columns whose ground is h. Under the water: pools, riffles, bars, an uneven bed, kept
        `min_depth` under the water's level except a bar's top. The bank's foot within a few metres of the water: on
        the OUTER side (of a bend, or of the thalweg's wander) the graded ramp is cut back to a low near-vertical step
        (`cut` m high: the turf ends at its top, the water stands at its foot); on the inner side the ramp's foot is
        flattened into the bar. Ground higher than the cut, fords, routes and sites keep theirs. riser: the cut
        face's half-width in plan (the maps bake it crisper than the mesh)."""
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
        # the banks' foot (above the water, and the first dm under it so the two meet)
        outer, hc, inner, sdc = self.cut(xy, g)
        hb = -dep
        rp = float(self.cfg["cut_riser"] if riser is None else riser)
        e = max(0.33 * rp, 0.04)  # (the riser, as a height)
        face = (1 - _ss(hc - e, hc + e, hb)) * _ss(sdc + rp, sdc - rp, g["sd"])
        b = -(np.maximum(hb, 0.0) + 0.2 * _ss(-0.35, 0.0, hb)) * face * outer * (hb > -0.35)
        b -= 0.65 * np.maximum(hb, 0.0) * _ss(0.8, 0.1, hb) * inner  # (the bar's side: the ramp's foot laid flat)
        out[k] = b
        m = _ss(0.05, 0.4, dep) * _ss(1.5, 0.0, g["sd"]) * (1 - g["ford"]) * (1 - g["still"])
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
        out[k[kk]] += m * d
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
        # (a lake's level hardly moves: its damp foot is half a river's; at the full height a gentle shore wore a
        # bare brown ring 3-4 m wide, a reservoir's drawdown)
        top = self.cfg["damp"] * (1 + 1.2 * wob) * (1 - 0.55 * g["still"])
        # (wet through for `damp` m above the water, moist and fading to twice that: on a steep bank the wet band alone
        # was a line a metre wide)
        damp = np.maximum(_ss(top, 0.15, -dep), 0.45 * _ss(2.2 * top, 0.5 * top, -dep)) * _ss(7.0, 3.5, g["sd"]) * \
            (1 - bed)
        pool, riffle, bar = self.forms(xy, g)
        e = g["energy"]
        # the cut bank's face (bare damp earth from the water up to the turf's edge) and the bar's dry side
        outer, hc, inner, sdc = self.cut(xy, g)
        hb = -dep
        cutf = outer * _ss(hc + 0.12, hc - 0.06, hb) * _ss(sdc + 0.6, sdc + 0.2, g["sd"]) * (hb > -0.1) * (1 - bed)
        damp = np.maximum(damp, cutf)
        dry = inner * _ss(0.5, 0.15, hb) * _ss(3.5, 1.5, g["sd"]) * (1 - bed) * \
            _ss(0.35, 0.55, noise.fbm(Pf, 3.0, 2, seed=752) + 0.3 * inner)
        damp = damp * (1 - dry)
        # sorting across the channel: coarse along the thalweg (toward the outer bank), finer toward the inner margin
        v = -np.tanh(4 * g["bend"]) * np.clip(g["u"], 0, 1)  # (+1 at the outer bank, -1 at the inner)
        coarse = _ss(1.0, 0.3, np.abs(v - 0.45 * np.abs(g["bend"]))) * (1 - 0.6 * _ss(0.7, 1.0, g["u"]))
        n5 = noise.fbm(Pf, 5.0, 2, seed=712)
        n2 = noise.fbm(Pf, 1.6, 3, seed=713)
        rock = _ss(0.55, 0.95, e + 0.5 * (n5 - 0.5)) * _ss(0.42, 0.6, noise.fbm(Pf, 3.5, 3, seed=714)) * \
            (1 - g["ford"])
        slow = _ss(0.5, 0.12, e)
        slack = _ss(0.72, 1.0, g["u"]) * (1 - _ss(0.0, 0.4, g["bend"]))  # (the margins' slack water)
        silt = slow * np.maximum(pool * _ss(0.85, 0.3, g["u"]), 0.7 * slack) * _ss(0.3, 0.5, n2 + 0.35 * pool) + \
            (1 - slow) * 0.5 * pool * _ss(0.55, 0.7, n2)  # (sand in a torrent's plunge pools)
        # (and fines in patches a few metres across wherever the water is slow: a bed of nothing but cobbles from bank
        # to bank read as one texture)
        silt = np.maximum(silt, 0.75 * slow * _ss(0.5, 0.64, noise.fbm(Pf, 5.5, 3, seed=719)) * (1 - 0.7 * riffle))
        silt = np.maximum(silt, 0.8 * (1 - coarse) * (1 - 0.8 * e) * _ss(0.42, 0.6, noise.fbm(Pf, 3.0, 3, seed=720)))
        silt = np.clip(silt * (1 - bar) * (1 - rock) * (1 - g["ford"]), 0, 1)
        # a lake's bed: gravel and pebbles along the shore (in patches), silt from a few metres in
        lake = np.clip(_ss(-0.8, -3.5, g["sd"]) + 0.6 * _ss(0.45, 0.6, n2), 0, 1)
        silt = silt * (1 - g["still"]) + lake * g["still"]
        rock = rock * (1 - g["still"])
        # (the bar's dry side is bed too: gravel above the water)
        # a fall's lip: bedrock under the sheet of water going over (terrain_falls), whatever the level grid says
        lw = g["lip"] * gate
        bed = np.maximum(bed, lw)
        damp = damp * (1 - lw)
        dry = dry * (1 - lw)
        rock = np.maximum(rock, lw)
        silt = silt * (1 - lw)
        tot = bed + dry
        rock = np.where(tot > 1e-6, rock * bed / np.maximum(tot, 1e-6), rock)
        silt = np.where(tot > 1e-6, silt * bed / np.maximum(tot, 1e-6), silt)
        bed = tot
        moss = np.exp(-((dep + 0.06) / 0.16) ** 2) * (0.4 + 0.6 * noise.fbm(Pf, 0.9, 2, seed=715))
        return {"k": k, "bed": bed, "damp": damp, "gravel": np.clip(1 - rock - silt, 0, 1), "silt": silt, "rock": rock,
                "dep": dep, "moss": moss, "bar": bar, "pool": pool, "riffle": riffle, "energy": e, "u": g["u"],
                "sd": g["sd"], "coarse": coarse, "cut": cutf, "hc": hc}

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
        # (coarse along the thalweg: bigger, more contrasted stones; the fine margins evener and a shade paler)
        co = st["coarse"]
        gr = np.asarray(terrain_stream.LOOK["gravel"]) * (1 + (0.3 + 0.45 * co) * mot)[:, None] * \
            (1 + warm[:, None] * np.array([0.10, 0.0, -0.12])) * (1.08 - 0.14 * co)[:, None]
        # (wet stone is darker, not black: the water over it darkens it again in the engine; riffles' clean coarse
        # stones paler, the pools' duller)
        # (dry gravel on a bar is pale, far paler than the wet bed beside it: the photos' bars are the brightest thing
        # in the channel)
        gr = gr * (1.38 - 0.50 * wetd - 0.10 * _ss(0.2, 1.0, dep))[:, None]
        gr = gr * (1 + 0.22 * st["riffle"] - 0.24 * st["pool"] * _ss(0.15, 0.6, dep))[:, None]
        si = np.asarray(terrain_stream.LOOK["silt"]) * (1 + 0.16 * (noise.fbm(Pf, 1.8, 2, seed=724) - 0.5))[:, None]
        deep = _ss(0.3, 1.2, dep)[:, None]
        si = (si * (1 - 0.5 * deep) + np.asarray(terrain_stream.LOOK["deep"]) * 0.5 * deep) * (1.0 - 0.3 * wetd)[:, None]
        br = rc * (1.0 - 0.5 * wetd)[:, None]
        bedc = gr * st["gravel"][:, None] + si * st["silt"][:, None] + br * st["rock"][:, None]
        # moss and algae on the stones at the water line (not on silt)
        ms = (st["moss"] * (st["gravel"] + st["rock"]) * 0.7)[:, None]
        bedc = bedc * (1 - ms) + np.asarray(terrain_stream.LOOK["moss"]) * ms
        al = (_ss(0.05, 0.4, dep) * st["pool"] * 0.25 * (st["gravel"] + st["rock"]))[:, None]
        bedc = bedc * (1 - al) + np.asarray(terrain_stream.LOOK["algae"]) * al
        # the bank's damp band: the ground's own colour darker, bare damp earth showing through it
        dm = st["damp"][:, None]
        bank = c * 0.62 * 0.45 + np.asarray(terrain_stream.LOOK["bank"]) * 0.55 * (1 + 0.3 * mot[:, None])
        # the cut face: bare earth, darkest under the turf's overhanging edge, roots and stones as flecks
        cf = st["cut"][:, None]
        hb = -dep
        under = _ss(st["hc"] - 0.3, st["hc"] - 0.05, hb)[:, None]
        fleck = (noise.fbm(P * np.array([1.0, 1.0, 4.0]), 0.25, 2, seed=725) - 0.5)[:, None]
        face = np.asarray(terrain_stream.LOOK["bank"]) * (1.05 - 0.35 * under) * (1 + 0.5 * fleck)
        bank = bank * (1 - cf) + face * cf
        out = c * (1 - dm) + bank * dm
        b = st["bed"][:, None]
        return np.clip(out * (1 - b) + bedc * b, 0, 1)

    def relief(self, P, w, texel, coarse=None):
        """The bed's fine relief as a plan gradient (n, 2), for the maps' normals, where the gravel layer weighs w
        (each octave fading where the texel can't carry it). Stones are flat-topped lumps standing on gravel, not a
        sheet of domes (fbm ** 2 everywhere at one strength was the "bubble wrap"), and how many and how big follows
        the bed: big and close along the thalweg and on riffles, few and small toward the inner margin, nearly none
        in pools and on the fines; a boulder-sized octave on steep reaches."""
        n = len(P)
        g = np.zeros((n, 2))
        k = np.flatnonzero(w > 1e-3)
        if not len(k):
            return g
        Pf = np.c_[P[k, :2], np.zeros(len(k))]
        # the bed's sorting at these points (points outside the zone keep a middling bed)
        co, rough, big = np.full(len(k), 0.5), np.ones(len(k)), np.zeros(len(k))
        st = self.shares(P[k]) if self.any else None
        if st is not None:
            j = st["k"]
            co[j] = st["coarse"]
            rough[j] = (0.45 + 0.9 * st["coarse"]) * (1 + 0.5 * st["riffle"]) * (1 - 0.65 * st["pool"]) * \
                (1 - 0.5 * _ss(0.6, 1.0, st["u"]) * (1 - st["bar"]))
            big[j] = _ss(0.35, 0.8, st["energy"]) * (0.4 + 0.6 * st["coarse"])
        e = 0.04
        O = np.array([[e, 0, 0], [-e, 0, 0], [0, e, 0], [0, -e, 0]])
        vis = lambda size: float(_ss(3.0 * texel, 5.0 * texel, size))
        Q = np.concatenate([Pf + o for o in O])
        thr = np.tile(0.62 - 0.2 * co, 4)  # (coarse bed: more of it is stone)
        for amp, size, seed, wt in ((0.06, 0.9, 731, rough), (0.03, 0.4, 732, rough), (0.14, 2.2, 733, big)):
            v = vis(size)
            if v <= 1e-3 or not (wt > 1e-3).any():
                continue
            f = noise.fbm(Q, size, 2, seed=seed)
            f = _ss(thr - 0.02, thr + 0.1, f) * (0.8 + 0.2 * f)  # (a steep side, a nearly flat top)
            f = f.reshape(4, -1)
            g[k] += (w[k] * wt * v * amp)[:, None] * np.c_[(f[0] - f[1]) / (2 * e), (f[2] - f[3]) / (2 * e)]
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
                if s[j] - s[i] >= 15:
                    parts.append(f"{s[i]:.0f}-{s[j]:.0f} m {names[cls[i]]} (grade {100 * r['grade'][i:j + 1].mean():.0f}%, "
                                 f"{r['width'][i:j + 1].mean():.0f} m wide)")
                i = j + 1
            out.append(f"stream bed {r['name']}: " + "; ".join(parts))
            wide = live & (r["width"] > 5.0)
            bmax = float(np.abs(r["bend"][wide]).max()) if wide.any() else 0.0
            if bmax < 0.5:
                out.append(f"stream bed {r['name']}: its path hardly bends (the tightest bend is {bmax:.1f} of a full one; a "
                           f"full bend turns on a radius of 5 half-widths), so pools, bars and cut banks alternate from side to side as in a "
                           f"straight channel; for point bars inside real bends give the river more `through` points "
                           f"(meanders with a radius of 2-4 channel widths)")
        return out
