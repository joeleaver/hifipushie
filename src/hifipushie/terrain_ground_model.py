"""`Edits` (what the design cuts and lays) and `Ground` (the ground's kinds, looks and relief over the terrain). Part of the terrain's ground (terrain_ground.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import terrain_ground
from . import noise
from .terrain_ground import _grid_at, _ss, config, signed_distance

class Edits:
    """Ground edits finer than the terrain grid, evaluated per point in Field.column (so the heightmap tiles, the
    cliff overlay, the collision and both bakes agree): the turf's step at its ragged edge back from every cliff lip,
    and bunkers cut crisp into the turf. `zone` (cells, on the terrain grid) says where any of it can be: elsewhere
    the column is untouched (and costs one lookup)."""

    def __init__(self, T, H, bunkers=(), cfg=None, streams=None):
        cfg = cfg or config(T) or {"lip": dict(terrain_ground.LIP), "bunker": dict(terrain_ground.BUNKER)}
        self.streams = streams if streams is not None and streams.any else None  # (terrain_stream: the beds' shape)
        self.lip_cfg, self.bunker_cfg = cfg["lip"], cfg["bunker"]
        self.x0, self.y0, self.c = float(T.xs[0]), float(T.ys[0]), float(T.cell)
        c = self.c
        gy, gx = np.gradient(H, c)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        steep = slope > self.lip_cfg["steep"]
        # tops: within a cliff's height of the highest ground near it (the foot is far below its neighbours' max)
        r = max(1, int(round(3.0 / c)))
        top = H >= ndimage.maximum_filter(H, size=2 * r + 1) - 1.5
        self.lip_d = np.where(steep.any(), ndimage.distance_transform_edt(~steep) * c, 1e3)
        sea = (getattr(T, "sea", None) or {}).get("level") if isinstance(getattr(T, "sea", None), dict) else None
        if sea is not None:  # (a top over the sea: not the platform or a beach at a cliff's foot)
            top = top & (H > float(sea) + 2.5)
        self.top = ndimage.gaussian_filter(top.astype(float), 0.7)
        reach = min(self.lip_cfg["band"] * 2.8, self.lip_cfg["max"]) + self.lip_cfg["riser"] + 2 * c
        zone = ndimage.binary_dilation((self.lip_d < reach) & (self.top > 0.01), iterations=2) \
            if self.lip_cfg["turf"] > 0 else np.zeros(H.shape, bool)
        self.bunkers = []
        self.bunker_names = []
        for m, depth, *name in bunkers:
            m = np.asarray(m, float)
            if not (m > 0.3).any():
                continue
            # one signed distance grid per trap (connected piece), over its own box: a cover's traps lie all over
            # the level
            lab, nl = ndimage.label(m > 0.05)
            parts = []
            for sl in ndimage.find_objects(lab):
                iy, ix = sl
                box = [[float(T.xs[ix.start]) - c, float(T.ys[iy.start]) - c],
                       [float(T.xs[ix.stop - 1]) + c, float(T.ys[iy.stop - 1]) + c]]
                pad = 3.0
                parts.append((np.array(box) + np.array([[-pad, -pad], [pad, pad]]),
                              signed_distance(T, m, self.bunker_cfg["res"], pad, box)))
            self.bunkers.append((parts, float(depth)))
            self.bunker_names.append(name[0] if name else None)
            zone |= ndimage.binary_dilation(m > 0.05, iterations=2)
        if self.streams is not None and self.streams.cfg["shape"]:
            zone |= self.streams.zone > 0
        self.zone = zone.astype(np.uint8)
        self.any = bool(zone.any())

    def _in_zone(self, x, y):
        iy = np.clip(np.rint((y - self.y0) / self.c).astype(np.int64), 0, self.zone.shape[0] - 1)
        ix = np.clip(np.rint((x - self.x0) / self.c).astype(np.int64), 0, self.zone.shape[1] - 1)
        return np.flatnonzero(self.zone[iy, ix])

    def lip(self, P):
        """(d to the lip m, the turf edge's set-back m, top 0..1) at points: the edge wanders 0.15-2.6 x the band
        (metre-scale bites and tongues), capped at `max`."""
        xy = P[:, :2]
        d = _grid_at(self.lip_d, xy, self.x0, self.y0, self.c)
        top = np.clip(_grid_at(self.top, xy, self.x0, self.y0, self.c), 0, 1)
        Pf = np.c_[xy, np.zeros(len(xy))]
        wob = 0.15 + 2.5 * noise.fbm(Pf, 2.6, 4, seed=611) ** 1.3 + 0.35 * (noise.fbm(Pf, 0.7, 2, seed=614) - 0.5)
        edge = np.minimum(self.lip_cfg["band"] * wob, self.lip_cfg["max"])
        return d, edge, top

    def bare(self, P, w=None):
        """0..1: the bare band between the turf's edge and the lip (the turf stepped off), its riser +-w m."""
        d, edge, top = self.lip(P)
        w = self.lip_cfg["riser"] if w is None else w
        return _ss(edge + w, edge - w, d) * top, d, edge, top

    @staticmethod
    def _sd_parts(parts, xy):
        out = np.full(len(xy), 3.0)  # (outside every trap's box: well outside)
        for box, sd in parts:
            k = np.flatnonzero((xy[:, 0] >= box[0, 0]) & (xy[:, 0] <= box[1, 0]) & (xy[:, 1] >= box[0, 1])
                               & (xy[:, 1] <= box[1, 1]))
            if len(k):
                out[k] = np.minimum(out[k], sd(xy[k]))
        return out

    def bunker_of(self, name):
        """The signed distance (m, negative inside) to the named bunker cover's edges, as a function of plan points
        (None if it has none)."""
        if name not in self.bunker_names:
            return None
        parts = self.bunkers[self.bunker_names.index(name)][0]
        return lambda xy: self._sd_parts(parts, np.atleast_2d(np.asarray(xy, float)))

    def bunker_sd(self, xy):
        """The signed distance to the nearest bunker's edge (m, negative inside; 3 m where there is none near)."""
        out = np.full(len(xy), 3.0)
        for parts, _ in self.bunkers:
            out = np.minimum(out, self._sd_parts(parts, xy))
        return out

    def dz(self, x, y, riser=None, wmin=0.0):
        """The height change at columns (only meaningful in the zone); riser: the turf step's half-width (m, default
        the config's); wmin: the least width of any cut face (a bunker's), for maps baked at a coarse texel."""
        P = np.c_[x, y, np.zeros(len(x))]
        out = np.zeros(len(x))
        if self.lip_cfg["turf"] > 0:
            b, *_ = self.bare(P, riser)
            ls = getattr(self, "lip_scale", None)
            if ls is not None:  # (a terrain style's share of the turf step: blobby none; realistic cells exactly 1)
                k = ndimage.map_coordinates(ls, [(P[:, 1] - self.y0) / self.c, (P[:, 0] - self.x0) / self.c],
                                            order=1, mode="nearest")
                b = b * k
            out -= self.lip_cfg["turf"] * b
        bc = self.bunker_cfg
        for parts, depth in self.bunkers:
            s = self._sd_parts(parts, P[:, :2])
            # the cut face over `riser` m inside the edge, a flat-ish floor following the ground's lie, the turf's lip
            # raised a little just outside (mown up to the edge)
            out -= depth * _ss(0.0, -max(bc["riser"], wmin), s)
            out += bc["lip"] * depth * _ss(0.9, 0.25, s) * _ss(-0.05, 0.1, s)
        return out

    def column(self, x, y, h, s, raw, riser=None, wmin=0.0):
        """Field.column with the edits: h + dz, the slope factor the grid's own. (From the edited surface's gradient,
        s changed wherever dz varied, the top's fade included: on a cliff face below a lip the field (z - h) s, metres
        under the top, moved the face and broke its rock into floating pieces and shards. The field is steeper than 1
        across a riser instead, as with any modifier.) raw: the unedited column (unused, kept for callers)."""
        if not self.any:
            return h, s
        k = self._in_zone(x, y)
        if not len(k):
            return h, s
        h = np.array(h, float, copy=True)
        h[k] = h[k] + self.dz(x[k], y[k], riser, wmin)
        if self.streams is not None:  # (a stream's bed: pools, riffles, bars; only under its water)
            h[k] = h[k] + self.streams.dz(x[k], y[k], h[k], riser)
        return h, s


class Ground:
    """Grids the ground's character needs (on the terrain grid, from the meshed ground `H`: the field's own copy, with
    arch necks and dolines dug in), and the per-point rules."""

    def __init__(self, T, H, sea_level=None, edits=None):
        self.T = T
        self.sea = sea_level
        c = float(T.cell)
        gy, gx = np.gradient(H, c)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        # the turf's edge back from every lip: the field's own (Edits), so colour and the geometric step agree
        self.edits = edits if edits is not None else Edits(T, H)
        self.lip_d, self.top = self.edits.lip_d, self.edits.top
        # moisture: hollows (positive Laplacian of the ground smoothed over ~6 m) wet, crests dry
        Hs = ndimage.gaussian_filter(H, max(1.0, 6.0 / c))
        lap = ndimage.laplace(Hs) / (c * c)
        self.wet = np.clip(lap / 0.02, -1, 1)
        # sun: a slope's share facing the noon sun (northern hemisphere: south), dry
        self.sunny = np.clip(-gy / np.maximum(np.hypot(gx, gy), 1e-6), -1, 1) * _ss(5, 25, slope)
        self.slope = slope
        sd = getattr(T, "sea", None)
        self.sea_d = np.asarray(sd["sd"], float) if sd is not None and "sd" in sd else None
        self._dir = {}

    # ---- grids at points (cubic B-spline on the grid: smooth, the same in every tile)
    def _at(self, mats, a, xy):
        return mats._grid(a, xy)

    def stripe_frame(self, name, mask):
        """The mowing frame of a mown cover: each piece of it (a fairway, a green) is mown in straight passes along
        its long axis (the principal axis of its cells), stripes counted across it from its centre. Grids per cell
        (nearest piece): the across direction (nx, ny) and the centre. A frame that turned with the zone put metres of
        phase into every degree (positions are hundreds of metres from the origin)."""
        if name not in self._dir:
            c = float(self.T.cell)
            m = np.asarray(mask, float) > 0.3
            lab, nl = ndimage.label(m)
            frame = np.zeros((nl + 1, 4))
            X, Y = self.T.X, self.T.Y
            for k in range(1, nl + 1):
                sel = lab == k
                xs, ys = X[sel], Y[sel]
                cx, cy = xs.mean(), ys.mean()
                if len(xs) < 3:
                    frame[k] = [1.0, 0.0, cx, cy]
                    continue
                cov = np.cov(np.c_[xs - cx, ys - cy].T)
                w, v = np.linalg.eigh(cov)
                frame[k] = [v[0, 0], v[1, 0], cx, cy]  # (the smaller axis: across the piece)
            if nl:
                _, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
                near = lab[iy, ix]
            else:
                near = np.zeros(m.shape, int)
            self._dir[name] = frame[near]
        return self._dir[name]

    def mown_sd(self, name, mask):
        """The signed distance (m, negative inside) to a mown cover's edge: the mower's line (terrain_ground
        .signed_distance at 1 m)."""
        key = ("sd", name)
        if key not in self._dir:
            self._dir[key] = signed_distance(self.T, mask, 1.0, 8.0)
        return self._dir[key]

    def first_cut(self, P, name, mask):
        """0..1: the first cut, a band `CUT` m wide (wandering a little) round a mown piece, mown a little longer than
        it (a fairway's collar between it and the rough)."""
        sd = self.mown_sd(name, mask)(P[:, :2])
        w = terrain_ground.CUT["width"] * (1 + terrain_ground.CUT["wander"] * (2 * noise.fbm(np.c_[P[:, :2], np.zeros(len(P))], 9.0, 2,
                                                                   seed=651) - 1))
        return _ss(-0.12, 0.12, sd) * _ss(w + 0.12, w - 0.12, sd)

    def stripes(self, P, name, mask, along=False):
        """-1..1 alternating bands STRIPE["width"] m wide across a mown piece (a mower's passes, crisp-edged);
        along=True also gives the mower's direction (n, 2)."""
        F = self.stripe_frame(name, mask)
        T = self.T
        iy = np.clip(np.rint((P[:, 1] - T.ys[0]) / T.cell).astype(np.int64), 0, F.shape[0] - 1)
        ix = np.clip(np.rint((P[:, 0] - T.xs[0]) / T.cell).astype(np.int64), 0, F.shape[1] - 1)
        f = F[iy, ix]
        across = (P[:, 0] - f[:, 2]) * f[:, 0] + (P[:, 1] - f[:, 3]) * f[:, 1]
        st = np.clip(terrain_ground.STRIPE["edge"] * np.sin(np.pi * across / terrain_ground.STRIPE["width"]), -1, 1)
        if along:  # (the mower's direction: along the piece, across the across-axis)
            return st, np.c_[-f[:, 1], f[:, 0]]
        return st

    def relief(self, mats, P, kinds, mown, texel):
        """The ground's own fine relief as a plan gradient (n, 2), for the maps' normals only (Field.column carries
        no sub-cell grass): tussocks in long grass, lumps under scrub, and the mower's stripes (blades laid one way,
        then the other: a tilt of the turf along the mower's direction, light and dark with the sun). Each octave fades
        out where the texel can't carry it (feature < 3 texels), so the far LODs agree with the near ones."""
        n = len(P)
        g = np.zeros((n, 2))
        Pf = np.c_[P[:, :2], np.zeros(n)]
        e = 0.05
        O = np.array([[e, 0, 0], [-e, 0, 0], [0, e, 0], [0, -e, 0]])
        vis = lambda size: _ss(3.0 * texel, 5.0 * texel, size)

        def grad(fn, k):
            Q = Pf[k]
            v = fn(np.concatenate([Q + o for o in O])).reshape(4, -1)
            return np.c_[(v[0] - v[1]) / (2 * e), (v[2] - v[3]) / (2 * e)]
        one = lambda key: np.clip(np.zeros(n) + kinds.get(key, 0.0), 0, 1)
        rough, scrub, cut = one("rough"), one("scrub"), one("cut")
        R = terrain_ground.RELIEF
        for amp, size, seed, w in ((R["tussock"], 1.2, 661, rough), (R["clump"], 2.6, 662, rough + 0.5 * scrub),
                                   (R["bush"], 1.6, 663, scrub), (R["cut"], 0.5, 664, cut)):
            w = w * vis(size)
            k = np.flatnonzero(w > 1e-3)
            if len(k):
                # (peaked: tussocks and lumps stand up from flatter ground between them)
                g[k] += w[k, None] * amp * grad(lambda Q, s_=size, sd=seed: noise.fbm(Q, s_, 2, seed=sd) ** 2, k)
        # (stripes 7 m wide: every LOD carries them, their edges no crisper than ~2.5 texels: a crisp edge differed
        # across tile borders)
        soft = min(1.0, terrain_ground.STRIPE["width"] / (np.pi * 2.5 * texel) / terrain_ground.STRIPE["edge"])
        for w, (st, al) in mown:
            st = np.clip(st * soft, -1, 1) if soft < 1 else st
            g += (np.clip(w, 0, 1) * st * terrain_ground.STRIPE["tilt"])[:, None] * al
        return g

    def rock(self, mats, P, N):
        """Extra rock (0..1) on gentle ground: the bare band along a lip (a ragged turf edge), rock breaking through
        near edges, the wave/splash zone. Returns (rock, undercut darkening 0..1, shore share)."""
        xy = P[:, :2]
        # the turf's edge wanders 0.15-2.6 x the band (metre-scale bites and tongues); bare between it and the lip,
        # where the ground has stepped down the turf's thickness (Edits.dz)
        bare, d, edge, top = self.edits.bare(P, self.edits.lip_cfg["maps"])
        # the rock right under the turf's lip is shaded (the mat overhangs it a little)
        under = _ss(edge - 0.45, edge - 0.05, d) * _ss(edge + 0.05, edge - 0.05, d) * top
        # patches breaking through: near lips, more of them closer, small (1-3 m) and ragged
        near = _ss(terrain_ground.LIP["patches"], 1.0, d) * top
        pat = noise.fbm(P * np.array([1.0, 1.0, 0.0]), 2.2, 3, seed=612)
        patch = _ss(0.72 - 0.16 * near, 0.76 - 0.16 * near, pat) * near
        rock = np.maximum(bare, patch)
        # turf and thrift on the faces' ledges near the top: up-facing rock in patches keeps a skin of green
        ledge = _ss(0.72, 0.9, N[:, 2]) * _ss(terrain_ground.LIP["patches"] + 6.0, 2.0, d) * _ss(0.5, 0.62, noise.fbm(P, 1.8, 3,
                                                                                                         seed=615)) \
            * (1 - top)  # (below the top: on the face)
        shore = np.zeros(len(P))
        if self.sea is not None:
            sh = terrain_ground.SHORE + 1.6 * (noise.fbm(P * np.array([1.0, 1.0, 0.0]), 6.0, 2, seed=613) - 0.5)
            # (above the water: the seabed stays sand)
            shore = _ss(self.sea + sh + 0.4, self.sea + sh - 0.4, P[:, 2]) * _ss(self.sea - 0.4, self.sea - 0.1, P[:, 2])
            if self.sea_d is not None:  # (only by the sea, not a low inland hollow)
                shore = shore * _ss(40.0, 15.0, self._at(mats, self.sea_d, xy))
            rock = np.maximum(rock, shore)
        return np.clip(rock, 0, 1), under, shore, ledge

    def scrub(self, mats, P, scrub, natural):
        """(scrub share, clump 0..1): asked scrub, plus unkept grass turning to scrub on slopes past ~20 deg; the
        bushes' clumps (1-4 m) within it."""
        Pf = P * np.array([1.0, 1.0, 0.0])
        sl = self._at(mats, self.slope, P[:, :2])
        sc = np.clip(scrub + natural * _ss(20.0, 36.0, sl) * 0.8 * (0.4 + 0.6 * noise.fbm(Pf, 30.0, 2, seed=626)),
                     0, 1)
        # (patches of 3-8 m holding several bushes: one bush per 2 m noise blob read as rubble from 150 m)
        return sc, _ss(0.45, 0.56, noise.fbm(Pf, 5.0, 3, seed=627))

    def tint(self, mats, P, N, c, kinds, mown_dirs):
        """The ground colour c (sRGB, the covers' own) varied by situation and kind. kinds: {"mown"|"cut"|"rough"|
        "scrub"|"sand": weight per point}; mown_dirs: [(weight, (stripes -1..1, mower direction (n, 2)))]."""
        xy = P[:, :2]
        n = len(P)
        Pf = P * np.array([1.0, 1.0, 0.0])
        lum = lambda col: col @ np.array([0.3, 0.59, 0.11])
        one = lambda k: np.clip(np.zeros(n) + kinds.get(k, 0.0), 0, 1)
        mown, cut, scrub = one("mown"), one("cut"), one("scrub")
        natural = np.clip(one("rough") + scrub, 0, 1)  # (unmown grass; not sand, tracks, forest)
        # macro patches (60 m and 15 m): brightness +-9%, hue toward straw or lush
        m1 = noise.fbm(Pf, 60.0, 2, seed=621) - 0.5
        m2 = noise.fbm(Pf, 15.0, 2, seed=622) - 0.5
        wet = self._at(mats, self.wet, xy)
        sunny = self._at(mats, self.sunny, xy)
        dry = np.clip(0.5 * m1 + 0.35 * m2 - 0.45 * wet + 0.25 * sunny, -1, 1)
        kept = np.clip(mown + cut, 0, 1)  # (mown ground is watered and fed: evener)
        out = c * (1 + (0.18 * m1 + 0.10 * m2) * (1 - 0.5 * kept))[:, None]
        tow = lambda col, a: out * (1 - a[:, None]) + np.asarray(col) * lum(out)[:, None] / lum(np.asarray(col)) * \
            a[:, None]
        # (tones carried at the ground's own brightness: a hue shift, not a paint-over)
        out = tow(terrain_ground.LOOK["straw"], np.clip(dry, 0, 1) * (0.08 * natural + 0.03 * kept))
        out = tow(terrain_ground.LOOK["lush"], np.clip(-dry, 0, 1) * 0.45)
        # salt-burnt turf above the sea (unmown): patchy within ~30 m of the shore
        if self.sea_d is not None:
            sd = self._at(mats, self.sea_d, xy)
            salt = _ss(32.0, 6.0, sd) * natural * (0.25 + 0.55 * noise.fbm(Pf, 9.0, 2, seed=623))
            out = out * (1 - 0.15 * salt[:, None]) + np.asarray(terrain_ground.LOOK["salt"]) * 0.15 * salt[:, None]
        # rough: tussocks (the maps' own relief: Ground.relief) lit straw-tipped on top, shaded between, and straw
        # patches (3 m); the mid distance reads its texture from these
        rough = np.clip(natural - scrub, 0, 1)
        tus = noise.fbm(Pf, 1.2, 2, seed=661) ** 2
        t1 = noise.fbm(P, 0.9, 2, seed=624) - 0.5
        t2 = noise.fbm(Pf, 3.0, 2, seed=625) - 0.5
        out = out * (1 + rough * (0.34 * (tus - 0.3) + 0.12 * t1 + 0.12 * t2))[:, None]
        out = tow(terrain_ground.LOOK["straw"], rough * np.clip(t2 * 1.4, 0, 1) * 0.12 + rough * _ss(0.45, 0.8, tus) * 0.1)
        # scrub on slopes (natural grass turns to scrub from ~22 deg) and where asked: clumps 1-4 m with dry gaps
        sc, clump = self.scrub(mats, P, scrub, natural)
        scol = np.asarray(terrain_ground.LOOK["scrub"]) * (0.8 + 0.4 * noise.fbm(Pf, 1.1, 2, seed=628))[:, None]
        gap = np.asarray(terrain_ground.LOOK["scrub_gap"])
        s_col = scol * clump[:, None] + gap * (1 - clump[:, None])
        out = out * (1 - sc[:, None]) + s_col * sc[:, None]
        # sand: wet and darker in the swash (up to ~0.9 m over the sea), a wrack line of weed and drift at the high
        # water mark, dry sand above with shell and pebble grit, shingle toward the back (a beach was one smooth cream
        # ramp)
        sand = one("sand")
        if sand.any() and self.sea is not None:
            z = P[:, 2] - self.sea
            wv = 0.35 * (noise.fbm(Pf, 7.0, 2, seed=641) - 0.5)
            wet = _ss(1.0 + wv, 0.55 + wv, z)
            wrack = np.exp(-((z - 1.25 - 1.5 * wv) / 0.18) ** 2) * _ss(0.45, 0.7, noise.fbm(Pf, 1.6, 3, seed=642))
            grit = noise.fbm(P, 0.25, 2, seed=643) - 0.5
            # swash lines: thin darker bands along the shore where waves stopped (the sand's own contours)
            sw = np.exp(-((np.mod(z * 7.0 + 2.0 * wv, 1.0) - 0.5) / 0.08) ** 2) * _ss(1.6, 0.8, z) * (1 - wet)
            # coarse shingle patches up the beach (darker, grey)
            shg = _ss(0.55, 0.72, noise.fbm(Pf, 4.0, 3, seed=645)) * _ss(1.4, 2.4, z)
            f = (0.9 - 0.38 * wet) * (1 - 0.45 * wrack) * (1 - 0.1 * sw) * (1 - 0.25 * shg) * \
                (1 + 0.14 * grit + 0.1 * (noise.fbm(Pf, 5.0, 2, seed=644) - 0.5))
            sc_ = np.c_[f * (1 - 0.06 * shg), f * (1 - 0.03 * wet - 0.04 * shg), f * (1 - 0.08 * wet - 0.1 * wrack)]
            out = out * (1 - sand[:, None]) + out * sc_ * sand[:, None]
        # mown: even, striped along the mower's passes (crisp-edged bands, +-STRIPE tone; the turf's lean in the maps'
        # normals does the rest, light one way and dark the other), faint mottling; the first cut a shade darker and
        # unstriped
        if mown.any():
            st = np.zeros(n)
            wsum = np.zeros(n)
            for w, ph in mown_dirs:
                ph = ph[0] if isinstance(ph, tuple) else ph
                st += w * ph
                wsum += w
            st = st / np.maximum(wsum, 1e-9)
            core = _ss(0.55, 0.9, mown)
            # (mottling at 3 m and 0.8 m: the mid distance's texture on a fairway, stripes aside)
            mot = 0.6 * (noise.fbm(Pf, 3.0, 2, seed=652) - 0.5) + 0.4 * (noise.fbm(Pf, 0.8, 2, seed=653) - 0.5)
            out = out * (1 + terrain_ground.STRIPE["tone"] * st * core + 0.2 * mot * mown)[:, None]
        if cut.any():
            out = out * (1 - 0.1 * cut)[:, None]
            out = tow(terrain_ground.LOOK["lush"], cut * 0.25)
        return np.clip(out, 0, 1)
