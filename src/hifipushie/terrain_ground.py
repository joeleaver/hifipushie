"""Ground character for the 3D tiles' maps: what the ground looks like between the rock faces, per point (texel or
vertex), the same in every tile and LOD (pointwise on global grids and noise).

The whole-level round (2026-10-02; the user on pebble from 150 m: "WTF?", a cave "with a cover over it"): the ground
was one flat colour per cover layer (plaster), fairways flat light-green stickers, cliffs grey shells on a green
mound with turf rolling over every lip. Compared with photos of real coast (Pebble Beach's 7th, Cornish cliff tops,
Durdle Door), real ground varies at every scale and by its situation:
- the turf ends back from a cliff's lip along a ragged edge (bare rock and a dark undercut below the turf mat), and
  rock breaks through in patches near the edges and on thin-soiled knolls;
- the wave and splash zone is bare rock or sand: no grass within ~1.5 m of the sea;
- grass is drier and paler on convex ground, sun-facing slopes and the salt-burnt first tens of metres above the sea,
  lusher in hollows; patches at tens of metres, tussocks at a metre;
- cover kinds read differently: "mown" (fairways, greens, lawns: even, bright, striped by the mower, a first-cut ring
  at its edge), "rough" (long grass: olive, straw-tipped, tussocky), "scrub" (low bushes: dark grey-green clumps
  with dry gaps, on slopes and near cliffs). Plain "meadow"/"grass" covers are rough; they turn to scrub on
  steeper slopes.
Colour and layer weight (Materials), the maps' own fine relief (Ground.relief: normals only), and two ground edits
finer than the terrain grid that ARE geometry (Edits, applied in Field.column): the turf's step at its edge back from a
cliff lip, and bunkers cut crisp."""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import noise


def _ss(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


def _hex(c):
    return np.array([int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]) if isinstance(c, str) else np.asarray(c, float)


# what each cover type is, as ground character (types not listed: none of it)
KIND_OF = {"mown": "mown", "lawn": "mown", "fairway": "mown", "green": "mown", "grass": "rough", "meadow": "rough",
           "rough": "rough", "pasture": "rough", "scrub": "scrub", "heath": "scrub", "orchard": "rough"}

LOOK = {  # sRGB
    "straw": [0.66, 0.60, 0.38],        # dry grass, seed heads
    "lush": [0.25, 0.42, 0.14],         # damp hollows
    "salt": [0.58, 0.53, 0.37],         # salt-burnt turf near the sea
    "scrub": [0.25, 0.30, 0.19],        # coastal scrub clumps (sage grey-green)
    "scrub_gap": [0.36, 0.37, 0.24],    # dry grass and litter between them
    "undercut": 0.55,                   # rock just under the turf's edge: shaded
}
LIP = {"band": 1.4, "patches": 7.0, "steep": 50.0, "turf": 0.7, "riser": 0.35, "maps": 0.12, "max": 3.2}
# turf edge set back ~band m (wandering 0.15-2.6x, at most `max` m: inside the cliff overlay's margin); rock patches
# within `patches` m of a lip; a lip = ground steeper than `steep` deg below a top. Geometry: the ground steps down
# `turf` m at the turf's edge (the mat's thickness) onto the bare lip, over a riser +-`riser` m wide (a real step in
# the field: the heightmap, the cliff overlay and both bakes see it); the maps bake it crisper, +-max(`maps`, 2.5
# texels) (+-0.18 m in the meshed field made black shards at the cliff meshes' 0.5 m voxels and pieces floating off
# the lip, and a riser sharper than a couple of texels differed across tile borders).
# Spec: "ground_character": {"lip": {...}}.
STRIPE = {"width": 7.0, "edge": 5.0, "tilt": 0.25, "tone": 0.16}  # mower stripes: m wide, edge crispness, the
# blades' lean as a slope along the mower's way (light one way, dark the other), and the colour step (+-)
RELIEF = {"tussock": 0.07, "clump": 0.06, "bush": 0.16, "cut": 0.01}  # maps-only ground relief, m (fbm^2 heights)
CUT = {"width": 2.2, "wander": 0.25}  # the first cut round mown pieces: m wide, +- share wandering
SHORE = 1.6  # no grass within this many metres above the sea (wandering +-0.8)
BUNKER = {"riser": 0.55, "lip": 0.12, "res": 0.25}  # a bunker's cut face (m across), its turf lip (x depth), sd grid m


def config(T):
    """The spec's ground character settings ({"lip": {...}}), or None when "ground_character" is false."""
    g = getattr(T, "spec", {}).get("ground_character", True)
    if g is False:
        return None
    g = g if isinstance(g, dict) else {}
    return {"lip": {**LIP, **(g.get("lip") or {})}, "bunker": {**BUNKER, **(g.get("bunker") or {})}}


def _grid_at(a, xy, x0, y0, c):
    """A per-cell grid [iy, ix] at points, as Materials._grid reads it (cubic B-spline, no prefilter)."""
    from . import fieldjit
    if fieldjit.ON:
        return fieldjit.grid_at(np.ascontiguousarray(a, dtype=np.float64), np.ascontiguousarray(xy[:, 0], np.float64),
                                np.ascontiguousarray(xy[:, 1], np.float64), float(x0), float(y0), float(c))
    return ndimage.map_coordinates(np.asarray(a, float), [(xy[:, 1] - y0) / c, (xy[:, 0] - x0) / c], order=3,
                                   prefilter=False, mode="nearest")


def signed_distance(T, mask, res=0.5, pad=6.0, box=None, thr=0.5):
    """A smooth signed distance (m, negative inside) to the edge of a cover mask's `thr` contour (the mask read as
    Materials reads it), on a `res` m lattice over `box` ([[x0, y0], [x1, y1]], default the mask's extent) + pad, as
    a function of plan points with .grid/.frame (a cubic spline: the incremental export crops it per tile). Edges cut
    from it are crisp (a mower's line, a bunker's cut) where the cell mask itself is a 2-cell blur."""
    from . import fieldjit
    from .terrain_incremental import Frame
    c = float(T.cell)
    if box is None:
        box = [[float(T.xs[0]), float(T.ys[0])], [float(T.xs[-1]), float(T.ys[-1])]]
    (x0, y0), (x1, y1) = np.asarray(box, float) + np.array([[-pad, -pad], [pad, pad]])
    xs = np.arange(x0, x1 + res, res)
    ys = np.arange(y0, y1 + res, res)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    m = ndimage.map_coordinates(np.asarray(mask, float), [(Y.ravel() - T.ys[0]) / c, (X.ravel() - T.xs[0]) / c],
                                order=3, prefilter=False, mode="nearest").reshape(X.shape)
    inside = m > thr
    if inside.any() and not inside.all():
        sd = np.where(inside, -(ndimage.distance_transform_edt(inside) - 0.5),
                      ndimage.distance_transform_edt(~inside) - 0.5) * res
    else:
        sd = np.full(X.shape, -pad if inside.all() else pad)
    sd = ndimage.gaussian_filter(sd, 0.8)
    coef = ndimage.spline_filter(sd, order=3)
    xs0, ys0 = float(xs[0]), float(ys[0])

    def f(xy):
        xy = np.atleast_2d(np.asarray(xy, float))
        if fieldjit.ON:
            return fieldjit.grid_at(coef, np.ascontiguousarray(xy[:, 1], np.float64),
                                    np.ascontiguousarray(xy[:, 0], np.float64), ys0, xs0, res)
        return ndimage.map_coordinates(coef, [(xy[:, 0] - xs0) / res, (xy[:, 1] - ys0) / res], order=3,
                                       prefilter=False, mode="nearest")
    f.grid, f.frame = coef, Frame("sd", coef.shape, "xy", xs0, ys0, res)
    return f


class Edits:
    """Ground edits finer than the terrain grid, evaluated per point in Field.column (so the heightmap tiles, the
    cliff overlay, the collision and both bakes agree): the turf's step at its ragged edge back from every cliff lip,
    and bunkers cut crisp into the turf. `zone` (cells, on the terrain grid) says where any of it can be: elsewhere
    the column is untouched (and costs one lookup)."""

    def __init__(self, T, H, bunkers=(), cfg=None):
        cfg = cfg or config(T) or {"lip": dict(LIP), "bunker": dict(BUNKER)}
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
        w = CUT["width"] * (1 + CUT["wander"] * (2 * noise.fbm(np.c_[P[:, :2], np.zeros(len(P))], 9.0, 2,
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
        st = np.clip(STRIPE["edge"] * np.sin(np.pi * across / STRIPE["width"]), -1, 1)
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
        R = RELIEF
        for amp, size, seed, w in ((R["tussock"], 1.2, 661, rough), (R["clump"], 2.6, 662, rough + 0.5 * scrub),
                                   (R["bush"], 1.6, 663, scrub), (R["cut"], 0.5, 664, cut)):
            w = w * vis(size)
            k = np.flatnonzero(w > 1e-3)
            if len(k):
                # (peaked: tussocks and lumps stand up from flatter ground between them)
                g[k] += w[k, None] * amp * grad(lambda Q, s_=size, sd=seed: noise.fbm(Q, s_, 2, seed=sd) ** 2, k)
        # (stripes 7 m wide: every LOD carries them, their edges no crisper than ~2.5 texels: a crisp edge differed
        # across tile borders)
        soft = min(1.0, STRIPE["width"] / (np.pi * 2.5 * texel) / STRIPE["edge"])
        for w, (st, al) in mown:
            st = np.clip(st * soft, -1, 1) if soft < 1 else st
            g += (np.clip(w, 0, 1) * st * STRIPE["tilt"])[:, None] * al
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
        near = _ss(LIP["patches"], 1.0, d) * top
        pat = noise.fbm(P * np.array([1.0, 1.0, 0.0]), 2.2, 3, seed=612)
        patch = _ss(0.72 - 0.16 * near, 0.76 - 0.16 * near, pat) * near
        rock = np.maximum(bare, patch)
        # turf and thrift on the faces' ledges near the top: up-facing rock in patches keeps a skin of green
        ledge = _ss(0.72, 0.9, N[:, 2]) * _ss(LIP["patches"] + 6.0, 2.0, d) * _ss(0.5, 0.62, noise.fbm(P, 1.8, 3,
                                                                                                         seed=615)) \
            * (1 - top)  # (below the top: on the face)
        shore = np.zeros(len(P))
        if self.sea is not None:
            sh = SHORE + 1.6 * (noise.fbm(P * np.array([1.0, 1.0, 0.0]), 6.0, 2, seed=613) - 0.5)
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
        out = tow(LOOK["straw"], np.clip(dry, 0, 1) * (0.08 * natural + 0.03 * kept))
        out = tow(LOOK["lush"], np.clip(-dry, 0, 1) * 0.45)
        # salt-burnt turf above the sea (unmown): patchy within ~30 m of the shore
        if self.sea_d is not None:
            sd = self._at(mats, self.sea_d, xy)
            salt = _ss(32.0, 6.0, sd) * natural * (0.25 + 0.55 * noise.fbm(Pf, 9.0, 2, seed=623))
            out = out * (1 - 0.15 * salt[:, None]) + np.asarray(LOOK["salt"]) * 0.15 * salt[:, None]
        # rough: tussocks (the maps' own relief: Ground.relief) lit straw-tipped on top, shaded between, and straw
        # patches (3 m); the mid distance reads its texture from these
        rough = np.clip(natural - scrub, 0, 1)
        tus = noise.fbm(Pf, 1.2, 2, seed=661) ** 2
        t1 = noise.fbm(P, 0.9, 2, seed=624) - 0.5
        t2 = noise.fbm(Pf, 3.0, 2, seed=625) - 0.5
        out = out * (1 + rough * (0.34 * (tus - 0.3) + 0.12 * t1 + 0.12 * t2))[:, None]
        out = tow(LOOK["straw"], rough * np.clip(t2 * 1.4, 0, 1) * 0.12 + rough * _ss(0.45, 0.8, tus) * 0.1)
        # scrub on slopes (natural grass turns to scrub from ~22 deg) and where asked: clumps 1-4 m with dry gaps
        sc, clump = self.scrub(mats, P, scrub, natural)
        scol = np.asarray(LOOK["scrub"]) * (0.8 + 0.4 * noise.fbm(Pf, 1.1, 2, seed=628))[:, None]
        gap = np.asarray(LOOK["scrub_gap"])
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
            out = out * (1 + STRIPE["tone"] * st * core + 0.2 * mot * mown)[:, None]
        if cut.any():
            out = out * (1 - 0.1 * cut)[:, None]
            out = tow(LOOK["lush"], cut * 0.25)
        return np.clip(out, 0, 1)


# ---------------------------------------------------------------- the grass detail (a tiling swatch, like the rock's)

GRASS = {"size": 2.0, "res": 256, "blades": 26000, "length": (0.03, 0.09), "dry": 0.12}
SWATCHES = {  # the tiling grass detail per ground layer: blades per 4 m2, blade length m, dry share, clumpiness,
    # blade lean (0 = any way, 1 = all one way), tip lift
    "turf": {"layers": ["turf"], "blades": 70000, "length": (0.012, 0.035), "dry": 0.03, "clump": 0.35,
             "seed": 4241, "fade": (30.0, 110.0)},  # mown: short, dense, even (fine: it can show farther)
    "grass": {"layers": ["grass", "scrub"], "blades": 22000, "length": (0.05, 0.16), "dry": 0.2, "clump": 1.0,
              "seed": 4243},  # long grass: clumpy, straw blades among the green
    "sand": {"layers": ["sand"], "gen": "sand", "seed": 4245},  # wind ripples in patches, grit, pebbles and shell
}


def sand_swatch(size=None, res=None, seed=4245):
    """A tileable sand swatch (top view, periodic, as grass_swatch returns it): wind/wave ripples ~8-12 cm apart in
    wandering patches (crests a little paler), grit speckle, scattered pebbles and shell (1-4 cm, darker and paler),
    so a beach isn't a smooth cream ramp at eye level."""
    from .terrain_swatch import spectral
    L = float(size or GRASS["size"])
    n = int(round(L * (res or GRASS["res"])))
    rng = np.random.default_rng(seed)
    t = L / n
    yy, xx = np.mgrid[0:n, 0:n] * t
    # ripples: crests along a direction that wanders, wavelength ~0.1 m, in patches; integer cycles per swatch so it
    # wraps (the phase field is periodic noise)
    mx, my = int(round(0.94 * L / 0.1)), int(round(0.34 * L / 0.1))  # (whole cycles across the swatch both ways)
    warp = spectral(n, 2.6, seed + 1, lo=3) * 1.6
    ph = 2 * np.pi * (mx * xx + my * yy) / L + warp * 2 * np.pi
    rip = np.sin(ph) + 0.35 * np.sin(2 * ph + 1.0)
    patch = np.clip(0.5 + 1.4 * spectral(n, 2.2, seed + 2, lo=4), 0, 1)
    hgt = 0.004 * rip * patch
    grit = spectral(n, 0.6, seed + 3, lo=8)
    alb = 1 + 0.10 * grit + 0.05 * rip * patch
    # pebbles and shell: discs 1-4 cm, splatted on the torus
    npb = int(260 * (L / 2.0) ** 2)
    c = rng.random((npb, 2)) * n
    rad = rng.uniform(0.005, 0.02, npb) / t
    tone = np.where(rng.random(npb) < 0.6, rng.uniform(0.45, 0.75, npb), rng.uniform(1.15, 1.35, npb))
    for (cx, cy), r, tn in zip(c, rad, tone):
        i0, i1 = int(cy - r - 1), int(cy + r + 2)
        j0, j1 = int(cx - r - 1), int(cx + r + 2)
        ii, jj = np.mgrid[i0:i1, j0:j1]
        d = np.hypot(ii - cy, jj - cx) / max(r, 1e-6)
        m = np.clip(1.2 - d, 0, 1)
        sl = (ii % n, jj % n)
        alb[sl] = alb[sl] * (1 - m) + tn * m
        hgt[sl] = np.maximum(hgt[sl], 0.6 * r * t * np.sqrt(np.clip(1 - d * d, 0, 1)))
    alb = np.repeat(alb[..., None], 3, -1) * np.array([1.0, 0.99, 0.96])
    alb = alb / alb.reshape(-1, 3).mean(0)
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": np.ones((n, n)), "size_m": L,
            "texels_per_m": n / L, "n": n}


def grass_swatch(size=None, res=None, seed=4243, blades=None, length=None, dry=None, clump=1.0):
    """A tileable turf swatch (top view, periodic): blades as short strokes splatted on the torus (lit tips, dark
    gaps between them), clumps 0.1-0.4 m, dry blades straw-coloured. Returns {"albedo" (n, n, 3) multiplier, mean 1;
    "height" m; "normal" (n, n, 3) tangent space (+x east, +y north); "rough"; "size_m"; "texels_per_m"; "n"}. Below
    the ground maps' texel (4/m) the macro colour is mush at eye level; this is what an engine tiles over it."""
    from .terrain_swatch import spectral
    L = float(size or GRASS["size"])
    n = int(round(L * (res or GRASS["res"])))
    rng = np.random.default_rng(seed)
    nb = int((blades or GRASS["blades"]) * (L / 2.0) ** 2)
    length = length or GRASS["length"]
    dry = GRASS["dry"] if dry is None else dry
    clump_n = spectral(n, 2.2, seed + 1, lo=5)  # (-1..1, 0.1-0.4 m)
    # blades seeded more densely in the clumps
    px = rng.random((nb * 2, 2)) * n
    cl = 0.5 + 0.5 * clump_n[px[:, 1].astype(int) % n, px[:, 0].astype(int) % n]
    keep = rng.random(nb * 2) < (0.6 - 0.25 * clump) + 0.5 * clump * cl
    px = px[keep][:nb]
    nb = len(px)
    ang = rng.random(nb) * 2 * np.pi
    ln = rng.uniform(*length, nb) * n / L
    dry = rng.random(nb) < dry
    hgt = np.zeros((n, n))
    tip = np.zeros((n, n))
    dryi = np.zeros((n, n))
    cnt = np.zeros((n, n))
    hb = 0.004 + 0.12 * float(np.mean(length))  # (taller blades stand higher)
    for t in np.linspace(0, 1, 9):
        q = px + (t * ln)[:, None] * np.c_[np.cos(ang), np.sin(ang)]
        ix, iy = q[:, 0].astype(int) % n, q[:, 1].astype(int) % n
        np.add.at(hgt, (iy, ix), 0.004 + hb * t)
        np.add.at(tip, (iy, ix), t)
        np.add.at(dryi, (iy, ix), dry * 1.0)
        np.add.at(cnt, (iy, ix), 1.0)
    hgt = ndimage.gaussian_filter(hgt, 0.6, mode="wrap") + 0.012 * clump * clump_n
    cover = 1 - np.exp(-cnt / 2.0)  # (how much of the texel blades cover; the rest is shadowed gap)
    tipm = tip / np.maximum(cnt, 1e-9)
    drym = np.clip(dryi / np.maximum(cnt, 1e-9), 0, 1)
    tone = (0.62 + 0.38 * cover) * (0.85 + 0.3 * tipm) * (1 + 0.12 * clump * clump_n)
    tone = ndimage.gaussian_filter(tone, 0.5, mode="wrap")
    straw = np.array([1.45, 1.30, 0.75])  # (a dry blade against the green: warmer and paler)
    alb = tone[..., None] * (1 + drym[..., None] * (straw - 1))
    alb = alb / alb.reshape(-1, 3).mean(0)
    t = L / n
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * t)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * t)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    rough = 1.0 + 0.1 * (1 - cover)
    return {"albedo": alb, "height": hgt - hgt.mean(), "normal": nrm, "rough": rough / rough.mean(), "size_m": L,
            "texels_per_m": n / L, "n": n}


def write_grass(out_dir, layers=None):
    """The grass swatches' images in out_dir/materials (rows top = north), as terrain_swatch.write lays the rock's:
    <kind>_detail_albedo (linear, x 2 = the multiplier), _normal (tangent: +x east, +y north), _height (16-bit), one
    set per SWATCHES kind whose layers exist (`layers`: the terrain's layer names; None = all). Returns the manifest
    entry: the first swatch's keys at the top (as before) and every swatch under "swatches"."""
    from PIL import Image
    from .terrain_swatch import tileability
    d = out_dir / "materials"
    d.mkdir(exist_ok=True)
    q8 = lambda a: np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)
    out = []
    for kind, P in SWATCHES.items():
        lay = [nm for nm in P["layers"] if layers is None or nm in layers]
        if not lay:
            continue
        S = sand_swatch(seed=P["seed"]) if P.get("gen") == "sand" else \
            grass_swatch(seed=P["seed"], blades=P["blades"], length=P["length"], dry=P["dry"], clump=P["clump"])
        hr = float(max(np.abs(S["height"]).max(), 1e-4))
        imgs = {"albedo": q8(0.5 * S["albedo"]), "normal": q8(S["normal"] * 0.5 + 0.5),
                "height": np.round((S["height"] / hr * 0.5 + 0.5) * 65535).astype(np.uint16)}
        files, seams = {}, {}
        prefix = "grass" if kind == "grass" else kind
        for k, a in imgs.items():
            fn = f"materials/{prefix}_detail_{k}.png"
            Image.fromarray(np.ascontiguousarray(a[::-1]), "I;16" if a.dtype == np.uint16 else None).save(out_dir / fn)
            files[k] = fn
            seams[k] = tileability(a)
        out.append({"kind": kind, "layers": lay, **files, "size_m": S["size_m"], "texels_per_m": S["texels_per_m"],
                    "fade_m": list(P.get("fade", GRASS_FADE)),
                    "height_m": round(hr, 5), "wrap_seam": seams})
    if not out:
        return None
    return {**{k: v for k, v in out[0].items() if k != "kind"}, "swatches": out,
            "projection": "top: uv = world (x, y) / size_m", "fade_m": list(GRASS_FADE),
            "recipe": "Per swatch, where its layers weigh w (_WEIGHTS / the weights map), on ground and cliff tiles: "
                      "uv = worldpos.xy / size_m, and a second sampling at uv / 1.618 + (0.37, 0.71), mixed 50/50 to "
                      "break the repeat; albedo: macro x (1 + w f (2 albedo - 1)); normal: the detail normal (+x east, "
                      "+y north) RNM-combined onto the macro normal by w f; f = 1 - smoothstep(fade_m[0], fade_m[1], "
                      "view distance)."}


GRASS_FADE = (20.0, 70.0)  # m: the grass detail fades out with the view distance (its 2 m repeat shows beyond)


# ---------------------------------------------------------------- ground clutter (placeholder instances)

CLUTTER = {  # kind: grid spacing m (jittered grid samples kept by probability)
    "bush": 1.3,       # coastal scrub / heath clumps, 0.5-1.4 m: in scrub, on its clumps (the maps' dark clumps)
    "tussock": 0.7,    # long-grass tussocks, 0.3-0.6 m: in rough grass, off scrub and the first cut
    "tallgrass": 0.3,  # long grass filling in round the eye (renders only, like an engine's grass near the camera)
    "boulder": 1.6,    # rocks 0.3-1.5 m: in clusters on the shore's splash zone and where rock breaks through
}
TREE_LIP = {"default": 4.0, "cypress": 1.5, "shrub": 2.0}  # trees: m in from the turf's edge back from a lip
CLUTTER_NEAR = {"tallgrass": 28.0}  # kinds placed only this close to the render's eyes (m), thinning out with distance
CLUTTER_LIP = {"keep": 1.8, "hug": 7.0, "squash": 0.45}  # bushes: none within `keep` m of the turf's edge (back from
# a cliff's lip), hugging the ground (height x squash, broader) out to `hug` m: wind-shorn, not perched on the edge


def clutter(T, mats, field, kinds=("bush", "boulder"), box=None, near=None, seed=7):
    """Ground clutter as instances [[x, y, z, kind index, scale, yaw, squash]] (kind index into `kinds`; squash: the
    height's share of the scale), from the same masks the maps paint: bushes on the scrub's clumps (kept back from
    cliff lips, low and wind-shorn near them), tussocks in rough grass, tall grass filling in round the eye (near
    only), boulders in clusters on rock (the splash zone, rock breaking through near lips; never on sand, sunk a
    little). Engines would scatter these from the layer weights with their own detail system; this is the placement
    and the reference density. box: [[x0, y0], [x1, y1]]; near: (points (n, 2+), radius) keeps only samples within
    radius of any point (render views). Steep ground, water, routes and sites are left bare."""
    if mats.ground is None:
        return np.zeros((0, 7))
    (x0, y0), (x1, y1) = box or T.spec["extent"]
    out = []
    for ki, kind in enumerate(kinds):
        sp = CLUTTER[kind]
        if kind in CLUTTER_NEAR:  # (each eye's own small box)
            if near is None:
                continue
            r = min(float(near[1]), CLUTTER_NEAR[kind])
            for ei, e in enumerate(np.asarray(near[0], float)):
                bx0, by0 = max(x0, e[0] - r), max(y0, e[1] - r)
                bx1, by1 = min(x1, e[0] + r), min(y1, e[1] + r)
                if bx1 <= bx0 or by1 <= by0:
                    continue
                C = _clutter_strip(T, mats, field, kind, ki, np.arange(bx0, bx1, sp), np.arange(by0, by1, sp), sp,
                                   (e[None], r), np.random.default_rng([seed, ki, ei]))
                if len(C):
                    out.append(C)
            continue
        ys = np.arange(y0, y1, sp)
        rows = max(1, int(1_000_000 // max(1, len(np.arange(x0, x1, sp)))))  # (in strips: a big map is 10^7 samples)
        for r0 in range(0, len(ys), rows):
            C = _clutter_strip(T, mats, field, kind, ki, np.arange(x0, x1, sp), ys[r0:r0 + rows], sp, near,
                               np.random.default_rng([seed, ki, r0]))
            if len(C):
                out.append(C)
    return np.concatenate(out) if out else np.zeros((0, 7))


def _clutter_strip(T, mats, field, kind, ki, xs, ys, sp, near, rng):
    gx, gy = np.meshgrid(xs, ys)
    xy = np.c_[gx.ravel(), gy.ravel()]
    xy = xy + rng.uniform(-0.45, 0.45, xy.shape) * sp
    dn = None
    if near is not None:
        from scipy.spatial import cKDTree
        dn, _ = cKDTree(np.asarray(near[0], float)[:, :2]).query(xy)
        xy, dn = xy[dn < near[1]], dn[dn < near[1]]
    if not len(xy):
        return np.zeros((0, 7))
    h, cs = field.column(xy[:, 0], xy[:, 1])
    P = np.c_[xy, h]
    ok = cs > 0.82  # (under ~35 deg)
    if mats.sea is not None:
        ok &= h > mats.sea - 0.2
    if not np.isnan(T.water).all():
        wet = mats._grid((~np.isnan(T.water)).astype(float), xy) > 0.3
        if mats.sea is None:
            ok &= ~wet
    for m in ("routes", "sites"):
        if m in T.masks:
            ok &= mats._grid(np.asarray(T.masks[m], float), xy) < 0.2
    P = P[ok]
    if dn is not None:
        dn = dn[ok]
    if not len(P):
        return np.zeros((0, 7))
    n = len(P)
    N = np.tile([0.0, 0.0, 1.0], (n, 1))
    kd = mats.kinds(P)
    Wl, _ = mats.weights(P, N)
    lw = lambda *names: sum((Wl[:, mats.layers.index(k)] for k in names if k in mats.layers), np.zeros(n))
    green = np.clip(lw("grass", "scrub") * 1.25, 0, 1)  # (where the maps paint grass: not on sand or rock)
    u = rng.random(n)
    scale = rng.uniform(0.6, 1.4, n)
    squash = np.ones(n)
    one = lambda k: np.clip(np.zeros(n) + kd.get(k, 0.0), 0, 1)
    # how far into the top from the turf's edge (cliff lips): bushes and grass keep back from the bare lip
    bare, d, edge, top = mats.ground.edits.bare(P)
    into = np.where(top > 0.3, d - edge, 1e3)
    if kind == "bush":
        sc, clump = mats.ground.scrub(mats, P, one("scrub"), np.clip(one("rough") + one("scrub"), 0, 1))
        L = CLUTTER_LIP
        p = sc * clump * 0.9 * _ss(L["keep"], L["keep"] + 1.0, into) * green
        hug = _ss(L["keep"] + 0.5, L["hug"], into)  # 0 at the edge .. 1 well back
        squash = L["squash"] + (1 - L["squash"]) * hug
        scale = scale * (1 + 0.35 * (1 - hug))  # (broader where it hugs the ground)
    elif kind in ("tussock", "tallgrass"):
        sc, _ = mats.ground.scrub(mats, P, one("scrub"), one("rough"))
        p = one("rough") * (1 - sc) * (1 - bare) * _ss(0.2, 0.8, into) * green
        if kind == "tussock":
            p = p * 0.6
        else:  # (dense by the eye, thinning out to the radius: an engine's grass draw distance)
            r = CLUTTER_NEAR["tallgrass"]
            p = p * 0.9 * (_ss(r, 0.45 * r, dn) if dn is not None else 1.0)
            scale = rng.uniform(0.7, 1.3, n)
    else:  # (on the ground the maps make rock: never on a beach's sand), in clusters
        rock, _, shore, _ = mats.ground.rock(mats, P, N)
        wr = lw("rock", "wet_rock")
        clus = _ss(0.42, 0.62, noise.fbm(np.c_[P[:, :2], np.zeros(n)], 7.0, 2, seed=671))
        p = _ss(0.55, 0.8, wr) * (shore * 0.6 + np.clip(rock - shore, 0, 1) * 0.2) * clus
        scale = scale * (0.6 + 0.8 * clus)  # (bigger in the thick of a cluster)
        P[:, 2] -= 0.12 * scale  # (sunk: a boulder sits in the ground, it isn't set on it)
    keep = u < p
    k = int(keep.sum())
    if not k:
        return np.zeros((0, 7))
    return np.c_[P[keep], np.full(k, ki), scale[keep], rng.uniform(0, 360, n)[keep], squash[keep]]
