"""Cliff overlay: the game-standard split of 3D terrain. The heightmap stays the base (tiled on the world grid, as an
engine's terrain system wants it); every stretch steeper than a threshold, and every place a cave, arch or notch opens,
gets a separate 3D mesh cut from the same rock field (terrain_field.Field: facets, beds, volumes), laid over it.

How the two fit without cutting holes except where a void must show through:
- The region: S(x, y) in 0..1, 1 on ground steeper than `cliff_slope` (and the rock character's own mask) and round
  every opening, easing to 0 over `cliff_margin` metres. Pointwise (a grid read bilinearly), so tiles agree.
- The heightmap is pushed into the rock under the region: eroded in plan by a ball of radius push x S^PUSH_POW (every
  point moves back along the face's normal), so it lies behind the cliff face, hidden, where S is near 1.
- The cliff mesh is a closed shell of rock: the front is the full field with the ground part sunk by sink x
  sink_share(S) (all of it at the region's edge, none from S = SINK_EDGE: the front is the true ground over most of the
  margin and crosses the heightmap ~0.2 m down), the back `thick` metres behind the smooth ground (and `cave_wall`
  metres round every void, so caves stay closed). Where the sink > thick the shell has no thickness: it pinches out
  under the heightmap on its own, no open edges to hide.
- Holes: heightmap cells whose surface would stand in a void (a cave mouth, an arch's side, a doline's shaft) are cut
  (a hole mask per tile) and the region grows round them, so the cliff mesh carries the ground there.
The ground tiles are written as heightmaps (.npy float metres, 16-bit PNG), hole masks, splats, and as glTF grid
meshes with LODs and skirts (for viewers and engines without a terrain system).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at terrain_cliffs.NAME: C422). terrain_cliffs_checks: checks on the ground against the cliffs: buried over
ground, exposed buried, floating, lifted, lakes. terrain_cliffs_ground: the ground tiles: normals, a tile, the fine
and baked ground, skirts, the ground check.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import fieldjit
from . import terrain_mesh as tm
from . import terrain_field, terrain_tile_mesh
from . import moved

def _smooth(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


SINK_EDGE = 0.2   # the cliff front sinks only where S < this (1 - smoothstep(0, SINK_EDGE, S)), all of `sink` at S = 0
PUSH_POW = 3.0    # the heightmap is pushed back by push x S^PUSH_POW
# where the front sinks toward the region's edge it dives under the heightmap; the strip that shows before they cross
# (a few cm) was baked as what it is, a steep dive: rock-coloured (its 0.4 m normal picked the rock layer) and shaded
# as a crease, a thin dark dashed line on the grass along every overlay edge (pushieworld note 104). Its maps take the
# true ground's normal instead: fully where S < SINK_EDGE, easing out by SINK_EDGE + UNSUNK_BAND (CliffField.lift)
UNSUNK_BAND = 0.05
# (2026-10-01: sunk by sink x (1 - S) and pushed by push x S, the two crossed where both were metres down (pebble: S 0.73,
# 2.5 m under the true ground) and the visible surface sagged into a trench along every overlay edge, a V crease the
# arch view at 150 m measured as an overlay edge excess of 2.0. Now they cross near S 0.18, ~0.25 m down.)
def sink_share(S):
    """How much of `sink` the cliff front is sunk by at region weight S."""
    return 1.0 - _smooth(0.0, SINK_EDGE, S)


def _faced(base):
    """The field's ground grid with each waterfall's face cut in (terrain_falls.Faces: the column is a step on the
    lip line, the plunge pool's ground below it), for the shell's back. From the grid alone the back followed the
    grid's ramp over the face's foot and stood 1-3 m over the pushed heightmap round the pool (pushieworld note 123:
    the worst buried faces were all at falls)."""
    H = base.H
    faces = getattr(base, "faces", None)
    if faces is None or not faces.any:
        return H
    H = H.copy()
    ny, nx = H.shape
    for F in faces.items:
        r = F["r"]
        i0, i1 = max(0, int((F["c"][0] - r - base.x0) / base.c)), min(nx, int((F["c"][0] + r - base.x0) / base.c) + 2)
        j0, j1 = max(0, int((F["c"][1] - r - base.y0) / base.c)), min(ny, int((F["c"][1] + r - base.y0) / base.c) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        X, Y = np.meshgrid(base.x0 + base.c * np.arange(i0, i1), base.y0 + base.c * np.arange(j0, j1))
        h = np.asarray(base.column(X.ravel(), Y.ravel())[0], float).reshape(X.shape)
        H[j0:j1, i0:i1] = np.minimum(H[j0:j1, i0:i1], h)
    return H


class Region:
    """Where the cliff meshes go (S), the pushed heightmap and the holes, on the world's heightmap lattice (spacing
    `d` = tile / (samples - 1), from the tile grid's origin: tiles' samples are lattice nodes)."""

    def __init__(self, T, base: terrain_field.Field, G: terrain_tile_mesh.Grid, cfg: dict):
        self.base, self.G = base, G
        hm = int(cfg["heightmap"]) or 65
        self.d = d = G.tile / (hm - 1)
        rock = base.rock
        relief = rock.get("relief", 1.4 * rock["facets"] + 0.7 * rock["bedding"]) if rock else 0.0
        self.push = float(cfg.get("push", relief + 0.6))          # heightmap moved back under the cliff face
        self.thick = float(cfg.get("thick", self.push + 1.5))     # shell: rock kept behind the smooth ground
        self.sink = float(cfg.get("sink", self.thick + relief + 0.8))  # front buried at the region's edge
        self.wall = float(cfg["cave_wall"])
        # the shell's back: the ground moved `thick` m into the rock (the solid eroded by a ball: a true offset surface,
        # as a height grid like the terrain's, read as a cubic B-spline). It used to be `thick` behind the COLUMN's own
        # plane, (z - h) x cos(slope) > -thick: the same on an even slope, but under a sheer face's columns (84 deg sea
        # cliffs on 0.64 m cells: cos 0.04-0.1) that is thick / cos = 50-100 m straight down, a buried sheet thinner
        # than a voxel hanging under every cliff (slice_a: 262k of one tile's 439k triangles more than 10 m under
        # their column's ground, the lattice's bottom cutting it open at z -95), and behind the face a slab as thin as
        # the face is wide in plan. Neither could be decimated: pyfqmr folds a sub-voxel sheet into fins at any count.
        kc = max(1, int(math.ceil(self.thick / base.c)))
        yy, xx = np.mgrid[-kc:kc + 1, -kc:kc + 1]
        r2 = (xx * xx + yy * yy) * base.c ** 2
        ball = np.sqrt(np.maximum(self.thick ** 2 - r2, 0.0))
        self.back = np.ascontiguousarray(ndimage.gaussian_filter(
            ndimage.grey_erosion(_faced(base), footprint=r2 <= self.thick ** 2, structure=ball, mode="nearest"), 0.7))
        m = float(cfg["cliff_margin"])
        self.nx = int(round(G.span[0] / d)) + 1
        self.ny = int(round(G.span[1] / d)) + 1
        xs = G.origin[0] + np.arange(self.nx) * d
        ys = G.origin[1] + np.arange(self.ny) * d
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        # (the grid's own ground, without the ground edits: a bunker's cut face or the turf's step at a cliff lip is
        # not a cliff; counted as one, the heightmap was pushed 4 m down round every bunker into a square pit)
        h, cs = getattr(base, "_column", base.column)(X.ravel(), Y.ravel())
        slope = np.degrees(np.arccos(np.clip(cs, 0, 1))).reshape(X.shape)
        th = float(cfg["cliff_slope"])
        st = _smooth(th - 4.0, th + 2.0, slope)
        if rock is not None:  # (every face the rock character touches is in the region)
            st = np.maximum(st, np.clip(base.steep_at(X.ravel(), Y.ravel()).reshape(X.shape) * 4, 0, 1))
        if getattr(base, "fall", None) is not None:  # (and where fallen blocks lie: the heightmap can't hold them)
            st = np.maximum(st, np.clip(base.fall_at(X.ravel(), Y.ravel()).reshape(X.shape) * 4, 0, 1))
        # a dammed lake's embankment is ground, not a cliff: taken for one (a steep lake-side face), the heightmap was
        # pushed 5-9 m down its face and its 2 m crest eroded away with it, so the dam stood only in the cliff meshes
        # and the tile heightmaps held no lake (pushieworld note 106: flooded, 134,000 m2 for 3,300)
        dams = getattr(T, "dams", None) or {}
        if dams:
            dm = np.zeros(base.H.shape)
            for a in dams.values():
                if np.shape(a) == dm.shape:
                    dm = np.maximum(dm, a)
            if dm.any():
                k_ = max(1, int(math.ceil((m + self.push) / base.c)))
                dm = ndimage.gaussian_filter(ndimage.maximum_filter(dm, size=2 * k_ + 1), 1.0)
                w = ndimage.map_coordinates(dm, [(Y.ravel() - base.y0) / base.c, (X.ravel() - base.x0) / base.c],
                                            order=1, mode="nearest").reshape(X.shape)
                st = st * (1.0 - np.clip(w, 0, 1))
        self.steep = self._grow(st, m)
        self.S = self.steep.copy()
        # how far the heightmap is pushed in: the full push under cliffs; round an opening only a little (the cliff
        # mesh's ground there is the true ground; pushed deeper, a heightmap round a lava tube's skylight went through
        # the tube's 4 m roof and every round of holes pushed it further)
        # (0.35 m let the rock's roughness round a lava pit's rim stand behind the heightmap: 3% showed through)
        self.push_open = float(cfg.get("push_open", 0.9))
        self.Rg = self.push * self.steep ** PUSH_POW
        self.holes = np.zeros((self.nx - 1, self.ny - 1), bool)  # per lattice cell
        # openings: where the heightmap (pushed) would stand in a void. Only near subtracted volumes.
        self.voids = [v for v in base.vols if v.op == "subtract"]
        self._open_rounds(X, Y, m)

    def _grow(self, a, m):
        k = max(1, int(round(m / self.d)))
        g = ndimage.maximum_filter(a, size=2 * k + 1)
        # (bounded where the blur has died out, 3 sigma past the grown mask: cut at the grown mask itself, S fell from
        # ~0.6 to 0 in one lattice step. The front there drops from the true ground to `sink` under it and the
        # heightmap was already pushed (0.6 m round kaze_cave's doline): the front's vertical edge and the shell's
        # back stood in the open along the region's edge, a dark crack with the buried colour in it)
        r = int(np.ceil(3 * 0.35 * k))
        keep = ndimage.maximum_filter(a, size=2 * (k + r) + 1) > 0
        return np.clip(ndimage.gaussian_filter(g, 0.35 * k), 0, 1) * keep

    def _open_rounds(self, X, Y, m):
        if not self.voids:
            return
        box = np.zeros(X.shape, bool)
        for v in self.voids:
            box |= (X >= v.lo[0]) & (X <= v.hi[0]) & (Y >= v.lo[1]) & (Y <= v.hi[1])
        ii, jj = np.nonzero(box)
        for _ in range(8):
            x, y = X[ii, jj], Y[ii, jj]
            hb = self.height(x, y)
            air = np.zeros(len(x), bool)
            for e in (0.05, 0.4, 0.9):
                air |= self.base.value(np.c_[x, y, hb - e]) > 0
            A = np.zeros(X.shape, bool)
            A[ii[air], jj[air]] = True
            # a cell is a hole if any corner stands in the void; one more cell round it
            cells = A[:-1, :-1] | A[1:, :-1] | A[:-1, 1:] | A[1:, 1:]
            cells = ndimage.binary_dilation(cells, iterations=1)
            new = cells & ~self.holes
            self.holes |= cells
            node = np.zeros(X.shape, float)
            node[:-1, :-1] = np.maximum(node[:-1, :-1], self.holes)
            node[1:, :-1] = np.maximum(node[1:, :-1], self.holes)
            node[:-1, 1:] = np.maximum(node[:-1, 1:], self.holes)
            node[1:, 1:] = np.maximum(node[1:, 1:], self.holes)
            op = self._grow(node, m)
            self.S = np.maximum(self.steep, op)
            # (round an opening too by op^PUSH_POW: pushed in proportion to op, the heightmap lay 0.3-0.6 m under the
            # front (the true ground) where the region begins, a step with its shadow round kaze_cave's doline)
            self.Rg = np.maximum(self.push * self.steep ** PUSH_POW, self.push_open * op ** PUSH_POW)
            if not new.any():
                break

    # ---- pointwise
    def s(self, x, y):
        if fieldjit.ON and self.S.dtype == np.float64 and self.S.ndim == 2:
            return fieldjit.linear_at(self.S, tm._f64(x), tm._f64(y), float(self.G.origin[0]),
                                      float(self.G.origin[1]), float(self.d))
        q = (np.asarray(x, float) - self.G.origin[0]) / self.d
        r = (np.asarray(y, float) - self.G.origin[1]) / self.d
        return ndimage.map_coordinates(self.S, [q, r], order=1, mode="nearest")

    def height(self, x, y, riser=None, wmin=0.0):
        """The pushed heightmap: the ground eroded in plan by a ball of radius push x S (so it lies behind the cliff
        face by about that much). riser: the turf step's half-width (terrain_ground.Edits; the maps' crisper one)."""
        x, y = np.asarray(x, float).ravel(), np.asarray(y, float).ravel()
        h, _ = self.base.column(x, y) if riser is None else self._col_riser(x, y, riser, wmin)
        R = ndimage.map_coordinates(self.Rg, [(x - self.G.origin[0]) / self.d, (y - self.G.origin[1]) / self.d],
                                    order=1, mode="nearest")
        k = np.flatnonzero(R > 1e-3)
        if not len(k):
            return h
        st = 0.25  # (offsets 0.5 m apart left a regular faceted grid in the pushed ground, visible in its normal map)
        g = np.arange(-self.push, self.push + 1e-9, st)
        ox, oy = np.meshgrid(g, g)
        ox, oy = ox.ravel(), oy.ravel()
        rr = np.hypot(ox, oy)
        sel = rr <= self.push + 1e-9
        ox, oy, rr = ox[sel], oy[sel], rr[sel]
        best = h[k].copy()
        for a, b, r in zip(ox, oy, rr):
            ok = r < R[k]
            if not ok.any():
                continue
            kk = k[ok]
            hh, _ = self.base.column(x[kk] + a, y[kk] + b)
            best[ok] = np.minimum(best[ok], hh - np.sqrt(np.maximum(R[kk] ** 2 - r * r, 0.0)))
        h = h.copy()
        h[k] = np.minimum(h[k], best)
        return h

    def _col_riser(self, x, y, riser, wmin=0.0):
        b = self.base
        h, s = b._edited_column(x, y, riser, wmin)
        if getattr(b, "faces", None) is not None:  # (the waterfalls' faces, as Field.column)
            h = b.faces.column(x, y, h, lambda a, c: b._edited_column(a, c, riser, wmin)[0])
        return h, s

    def back_at(self, x, y):
        """The shell's back at columns: its height and slope factor (see `back`)."""
        b = self.base
        if fieldjit.ON:
            return fieldjit.column(self.back, tm._f64(x), tm._f64(y), b.x0, b.y0, b.c)
        r = (np.asarray(y, float) - b.y0) / b.c
        q = (np.asarray(x, float) - b.x0) / b.c
        e = 0.5
        rr = np.concatenate([r, r, r, r + e, r - e])
        qq = np.concatenate([q, q + e, q - e, q, q])
        v = ndimage.map_coordinates(self.back, [rr, qq], order=3, prefilter=False, mode="nearest").reshape(5, -1)
        gx = (v[1] - v[2]) / (2 * e * b.c)
        gy = (v[3] - v[4]) / (2 * e * b.c)
        return v[0], 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)

    def tile_holes(self, i, j, n):
        """The hole mask of tile (i, j): (n - 1) x (n - 1) cells, row 0 north (like the heightmap PNGs)."""
        a, b = i * (n - 1), j * (n - 1)
        H = np.zeros((n - 1, n - 1), bool)
        sub = self.holes[a:a + n - 1, b:b + n - 1]
        H[:sub.shape[0], :sub.shape[1]] = sub
        return H.T[::-1]

    def tile_live(self, lo, hi, pad):
        q0 = max(0, int((lo[0] - pad - self.G.origin[0]) / self.d))
        q1 = int((hi[0] + pad - self.G.origin[0]) / self.d) + 2
        r0 = max(0, int((lo[1] - pad - self.G.origin[1]) / self.d))
        r1 = int((hi[1] + pad - self.G.origin[1]) / self.d) + 2
        return bool(self.S[q0:q1, r0:r1].max() > 0)


WHOLE_ADDS = __import__("os").environ.get("HIFIPUSHIE_WHOLE_ADDS") == "1"  # (see CliffField._with_adds: off until sea stacks mesh cleanly solid; the decimation's error now
# counts faces out in front of the rock, which keeps the hollow's walls inside)


class CliffField:
    """The shell the cliff meshes are cut from (see the module docstring). Looks like a terrain_field.Field to the tile
    exporter: column, solid, value, value_gradient, rock."""

    def __init__(self, base: terrain_field.Field, region: Region):
        self.base, self.region = base, region
        self.rock, self.vols = base.rock, base.vols
        self.zpad = region.thick + region.sink  # (the tile's lattice reaches this far under the ground)
        self.vol_pad = region.wall + 3.0  # (and this far under a void: its shell of rock)

    def column(self, x, y):
        return self.base.column(x, y)

    def steep_at(self, x, y):
        return self.base.steep_at(x, y)

    def zlow(self, x, y):
        """The lowest the shell reaches under columns: its back (the tile lattice's bottom; voids add their boxes)."""
        return self.region.back_at(x, y)[0] - 1.0

    def ground(self, p):
        return self.base.ground(p)

    def empty(self, lo, hi):
        """A tile the shell can't reach (no region, no void)."""
        if self.region.tile_live(lo, hi, 2.0):
            return False
        return not any(b[1][0] >= lo[0] and b[0][0] <= hi[0] and b[1][1] >= lo[1] and b[0][1] <= hi[1]
                       for b in self._boxes())

    def _boxes(self):
        """Each void's box grown to hold the whole shell round it (the tube's own box is cut off under its floor,
        about 2 m down: the wall's rock ended in a flat face there, and its normals were zero)."""
        if not hasattr(self, "_bx"):
            m = self.region.wall + 3.0
            self._bx = []
            for v in self.region.voids:
                r = float(np.max(np.maximum(v.rw, v.rh))) + 2.0 if hasattr(v, "rw") else 0.0
                self._bx.append((np.minimum(v.lo, v.nodes.min(0) - r - m) if hasattr(v, "nodes") else v.lo - m,
                                 np.maximum(v.hi, v.nodes.max(0) + r + m) if hasattr(v, "nodes") else v.hi + m))
        return self._bx

    def _void(self, p):
        d = np.full(len(p), np.inf)
        for v, (lo, hi) in zip(self.region.voids, self._boxes()):
            k = np.flatnonzero(np.all((p >= lo) & (p <= hi), axis=1))
            if len(k):
                d[k] = np.minimum(d[k], v.sd(p[k]))
        return d

    def solid(self, p, Fg, s):
        """Shell value from the ground's distance Fg at p (s: the column's slope factor)."""
        R = self.region
        S = R.s(p[:, 0], p[:, 1])
        dv = self._void(p)
        near_void = np.isfinite(dv) & (dv < R.wall + 2.0)
        out = np.full(len(p), 1e3)  # outside the region and away from voids: air (the shell can't be there)
        k = np.flatnonzero((S > 0) | near_void)
        if not len(k):
            return self._with_adds(p, Fg, s, out)
        front = self.base.solid(p[k], Fg[k] + R.sink * sink_share(S[k]), s[k])
        # (round a void the shell behind the face reaches 2 m past the cave wall, so it meets the rock round the
        # void: a gap between them left sealed air pockets inside the rock, meshed as floating bubbles)
        hb, sb = R.back_at(p[k, 0], p[k, 1])  # (the ground moved `thick` into the rock: see Region.back)
        back = np.minimum((hb - p[k, 2]) * sb, dv[k] - (R.wall + 2.0))
        # (rounded where front and back meet: a hard crease there shaded as shards)
        out[k] = tm.smax(front, back, 0.8)
        # round every void, the whole rock (unsunk) within cave_wall of it, up to just under the ground: the sunk
        # front alone sliced off a lava tube's roof wherever the tube ran shallower than `sink`
        kv = np.flatnonzero(near_void[k])
        if len(kv):
            q = k[kv]
            out[q] = tm.smin(out[q], self._void_rock(p[q], Fg[q], s[q], dv[q]), 0.5)
        return self._with_adds(p, Fg, s, out)

    ADD_PAD = 1.0  # m round a solid volume (a sea stack) where the whole rock is kept

    def _adds(self, p):
        """Distance to the solid volumes the rock is built of on top of the heightfield (sea stacks, rubble mounds)."""
        if not hasattr(self, "_add_vols"):
            self._add_vols = [v for v in self.base.vols if v.op == "add"]
        d = np.full(len(p), np.inf)
        for v in self._add_vols:
            k = np.flatnonzero(np.all((p >= v.lo) & (p <= v.hi), axis=1))
            if len(k):
                d[k] = np.minimum(d[k], v.sd(p[k]))
        return d

    def _with_adds(self, p, Fg, s, out, sunk=None):
        """A solid volume is all rock in the shell: the shell's back is the heightfield's ground moved in, and inside a
        sea stack that ground is the heightfield's own slim core: the back stood 16 m up inside the island's Kaze stacks
        and hollowed them from the sea floor up. The cavity's buried faces, free of the decimation's error (it is
        measured on the visible rock), were pulled out through the stack's wall at LOD 1-2: white triangles 10-20 m
        across in the engine, and pieces of the stack floating free."""
        if not WHOLE_ADDS:
            return out
        da = self._adds(p)
        k = np.flatnonzero(da < self.ADD_PAD + 1.0)
        if len(k):
            full = self.base.solid(p[k], Fg[k].copy(), s[k]) if sunk is None else sunk[k]
            out[k] = tm.smin(out[k], tm.smax(full, da[k] - self.ADD_PAD, 0.5), 0.2)
        return out

    TOP = 0.5  # m: the rock round a void stops this far under the ground (the heightmap's place)

    def _void_rock(self, p, Fg, s, dv):
        full = self.base.solid(p, Fg.copy(), s)
        return tm.smax(tm.smax(full, dv - self.region.wall, 0.5), Fg + self.TOP, 0.5)

    def front(self, p):
        """The visible surface's own field: the rock, its ground part sunk toward the region's edge, and the rock round
        every void unsunk. Faces of the shell where this is ~0 are seen, the rest is its buried back."""
        p = np.asarray(p, float)
        h, s = self.base.column(p[:, 0], p[:, 1])
        S = self.region.s(p[:, 0], p[:, 1])
        Fg = (p[:, 2] - h) * s
        out = self.base.solid(p, Fg + self.region.sink * sink_share(S), s)
        dv = self._void(p)
        kv = np.flatnonzero(np.isfinite(dv) & (dv < self.region.wall + 2.0))
        if len(kv):  # (the full rock there: its buried outer skin and cap read deep inside it, so they're "buried")
            out[kv] = np.minimum(out[kv], self.base.solid(p[kv], Fg[kv].copy(), s[kv]))
        return self._with_adds(p, Fg, s, out)

    def value(self, p):
        p = np.asarray(p, float)
        h, s = self.base.column(p[:, 0], p[:, 1])
        return self.solid(p, (p[:, 2] - h) * s, s)

    def front_field(self):
        """The visible rock alone (what the maps are baked from): value / value_gradient of `front`."""
        cf = self

        class _Front:
            rock, vols = cf.rock, cf.vols

            def value(self, p):
                return cf.front(p)

            def value_gradient(self, p, h):
                tet = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
                f = cf.front((p[:, None, :] + h * tet[None]).reshape(-1, 3)).reshape(-1, 4)
                return f.mean(1), (f @ tet) / (4 * h)

            def unsunk(self, p, h):
                """(w, g): how far the front at p is the sunk construction (0 where it is the true ground, 1 where
                it sinks: UNSUNK_BAND) and the true ground's field gradient there (the rock unsunk)."""
                return cf.unsunk(p, h)

            def lift(self, p):
                return cf.lift(p)

            def relief_at(self, x, y):
                """The rock character's weight at columns (terrain_field.Field.relief_at)."""
                return cf.base.relief_at(x, y)

            def designed_step(self, x, y):
                """True at columns where the ground has designed steps finer than the grid (terrain_ground.Edits'
                zone: the turf's riser at a lip, a bunker's cut edge and raised lip)."""
                e = getattr(cf.base, "edits", None)
                out = np.zeros(len(x), bool)
                if e is not None and e.any:
                    out[e._in_zone(np.asarray(x, float), np.asarray(y, float))] = True
                if getattr(cf.base, "fall", None) is not None:  # (and fallen blocks: chipped boxes on the ground)
                    out |= np.asarray(cf.base.fall_at(x, y)) > 0
                return out

            def near_volume(self, p):
                """True at points within a few metres of a volume (a cave's mouth, a stack's foot: built edges)."""
                return np.minimum(cf._void(p), cf._adds(p)) < cf.region.wall + 2.0
        return _Front()

    def lift(self, p):
        """(w, q): how far the front at points p is the sunk construction (0 where it is the true ground, 1 where
        it sinks: see UNSUNK_BAND), and the points moved up onto the true ground over them (what their maps should show)."""
        p = np.asarray(p, float)
        S = self.region.s(p[:, 0], p[:, 1])
        # (by S, not by how far it is sunk: the dive starts at SINK_EDGE so steeply that a normal stencil a few cm
        # across already saw it; past the edge the front IS the true ground, so the two normals agree where w eases)
        w = 1.0 - _smooth(SINK_EDGE, SINK_EDGE + UNSUNK_BAND, S)
        q = p.copy()
        k = np.flatnonzero(w > 0)
        if len(k):
            q[k, 2] = self.base.column(p[k, 0], p[k, 1])[0]
            if self.region.voids:  # (round a void the front is the whole rock, not sunk: nothing to lift)
                dv = self._void(p[k])
                near = np.isfinite(dv) & (dv < self.region.wall + 2.0)
                w[k[near]] = 0.0
                q[k[near]] = p[k[near]]
        return w, q

    def unsunk(self, p, h):
        """See front_field: (w, the true ground's gradient over each point)."""
        w, q = self.lift(p)
        g = np.zeros_like(np.asarray(p, float))
        k = np.flatnonzero(w > 0)
        if len(k):
            g[k] = self.base.value_gradient(q[k], h)[1]
        return w, g

    def value_gradient(self, p, h):
        tet = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
        f = self.value((p[:, None, :] + h * tet[None]).reshape(-1, 3)).reshape(-1, 4)
        return f.mean(1), (f @ tet) / (4 * h)


OVER_GROUND = 0.5  # m: a buried face whose centre stands this far over its ground tile's heightmap is counted

EXPOSED_OFF = 0.5  # m out from a buried face's centre (along its normal) where the open air must not be
EXPOSED_LIMIT = 2.0  # m2 of buried faces in the open per tile LOD: over it is a failure

LAKE_AREA = 1.5  # a lake flooded on the tile heightmaps may cover this x its designed area (or 1 / this) at most


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_cliffs_checks", "terrain_cliffs_ground")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
