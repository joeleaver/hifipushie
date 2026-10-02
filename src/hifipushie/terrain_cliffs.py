"""Cliff overlay: the game-standard split of 3D terrain. The heightmap stays the base (tiled on the world grid, as an
engine's terrain system wants it); every stretch steeper than a threshold, and every place a cave, arch or notch opens,
gets a separate 3D mesh cut from the same rock field (terrain_mesh.Field: facets, beds, volumes), laid over it.

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
meshes with LODs and skirts (for viewers and engines without a terrain system)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import fieldjit
from . import terrain_mesh as tm


def _smooth(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


SINK_EDGE = 0.2   # the cliff front sinks only where S < this (1 - smoothstep(0, SINK_EDGE, S)), all of `sink` at S = 0
PUSH_POW = 3.0    # the heightmap is pushed back by push x S^PUSH_POW
# (2026-10-01: sunk by sink x (1 - S) and pushed by push x S, the two crossed where both were metres down (pebble: S 0.73,
# 2.5 m under the true ground) and the visible surface sagged into a trench along every overlay edge, a V crease the
# arch view at 150 m measured as an overlay edge excess of 2.0. Now they cross near S 0.18, ~0.25 m down.)


def sink_share(S):
    """How much of `sink` the cliff front is sunk by at region weight S."""
    return 1.0 - _smooth(0.0, SINK_EDGE, S)


class Region:
    """Where the cliff meshes go (S), the pushed heightmap and the holes, on the world's heightmap lattice (spacing
    `d` = tile / (samples - 1), from the tile grid's origin: tiles' samples are lattice nodes)."""

    def __init__(self, T, base: tm.Field, G: tm.Grid, cfg: dict):
        self.base, self.G = base, G
        hm = int(cfg["heightmap"]) or 65
        self.d = d = G.tile / (hm - 1)
        rock = base.rock
        relief = rock.get("relief", 1.4 * rock["facets"] + 0.7 * rock["bedding"]) if rock else 0.0
        self.push = float(cfg.get("push", relief + 0.6))          # heightmap moved back under the cliff face
        self.thick = float(cfg.get("thick", self.push + 1.5))     # shell: rock kept behind the smooth ground
        self.sink = float(cfg.get("sink", self.thick + relief + 0.8))  # front buried at the region's edge
        self.wall = float(cfg["cave_wall"])
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
        return np.clip(ndimage.gaussian_filter(g, 0.35 * k), 0, 1) * (g > 0)

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
            self.Rg = np.maximum(self.push * self.steep ** PUSH_POW, self.push_open * op)
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
        h, s = b._column(x, y)
        return b.edits.column(x, y, h, s, b._column, riser, wmin) if getattr(b, "edits", None) is not None \
            else (h, s)

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


class CliffField:
    """The shell the cliff meshes are cut from (see the module docstring). Looks like a terrain_mesh.Field to the tile
    exporter: column, solid, value, value_gradient, rock."""

    def __init__(self, base: tm.Field, region: Region):
        self.base, self.region = base, region
        self.rock, self.vols = base.rock, base.vols
        self.zpad = region.thick + region.sink  # (the tile's lattice reaches this far under the ground)
        self.vol_pad = region.wall + 3.0  # (and this far under a void: its shell of rock)

    def column(self, x, y):
        return self.base.column(x, y)

    def steep_at(self, x, y):
        return self.base.steep_at(x, y)

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
            return out
        front = self.base.solid(p[k], Fg[k] + R.sink * sink_share(S[k]), s[k])
        # (round a void the shell behind the face reaches 2 m past the cave wall, so it meets the rock round the
        # void: a gap between them left sealed air pockets inside the rock, meshed as floating bubbles)
        back = np.minimum(-(Fg[k] + R.thick), dv[k] - (R.wall + 2.0))
        # (rounded where front and back meet: a hard crease there shaded as shards)
        out[k] = tm.smax(front, back, 0.8)
        # round every void, the whole rock (unsunk) within cave_wall of it, up to just under the ground: the sunk
        # front alone sliced off a lava tube's roof wherever the tube ran shallower than `sink`
        kv = np.flatnonzero(near_void[k])
        if len(kv):
            q = k[kv]
            out[q] = tm.smin(out[q], self._void_rock(p[q], Fg[q], s[q], dv[q]), 0.5)
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
        return out

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
        return _Front()

    def value_gradient(self, p, h):
        tet = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
        f = self.value((p[:, None, :] + h * tet[None]).reshape(-1, 3)).reshape(-1, 4)
        return f.mean(1), (f @ tet) / (4 * h)


# ---------------------------------------------------------------- the ground tiles

def ground_normals(R: Region, x, y, e=0.25):
    hx = (R.height(x + e, y) - R.height(x - e, y)) / (2 * e)
    hy = (R.height(x, y + e) - R.height(x, y - e)) / (2 * e)
    n = np.c_[-hx, -hy, np.ones_like(hx)]
    return n / np.linalg.norm(n, axis=1, keepdims=True)


def ground_tile(R: Region, mats, i, j, lo, n, lods, out: Path, cfg):
    """One ground tile: the pushed heightmap (npy + 16-bit PNG over `hrange`), its hole mask, and grid meshes per LOD
    (stride 2^k, hole cells dropped, skirts down along shared borders). Returns the manifest entry and stats."""
    from PIL import Image
    G = R.G
    s = np.linspace(0, G.tile, n)
    X, Y = np.meshgrid(lo[0] + s, lo[1] + s, indexing="ij")  # [ix, iy]
    Hh = R.height(X.ravel(), Y.ravel()).reshape(n, n)
    holes = R.tile_holes(i, j, n)  # rows north
    hn = Hh.T[::-1].astype(np.float32)
    np.save(out / "heightmaps" / f"height_{i}_{j}.npy", hn)
    hr = cfg["_hrange"]
    q = np.round((hn - hr[0]) / (hr[1] - hr[0]) * 65535).clip(0, 65535).astype(np.uint16)
    Image.fromarray(q).save(out / "heightmaps" / f"height_{i}_{j}.png")
    entry = {"i": i, "j": j, "min": [float(lo[0]), float(lo[1])], "max": [float(lo[0] + G.tile), float(lo[1] + G.tile)],
             "heightmap": f"heightmaps/height_{i}_{j}.npy", "lods": []}
    if holes.any():
        Image.fromarray((holes * 255).astype(np.uint8)).save(out / "heightmaps" / f"holes_{i}_{j}.png")
        entry["holes"] = f"heightmaps/holes_{i}_{j}.png"
        entry["hole_cells"] = int(holes.sum())
    hole_ij = holes[::-1].T  # [ix, iy] cells
    P0 = np.c_[X.ravel(), Y.ravel(), Hh.ravel()]
    N0 = ground_normals(R, X.ravel(), Y.ravel())
    from .profiling import span
    with span("ground/vertex weights"):
        W0, C0 = mats.weights(P0, N0)
    trans = tm._to_gltf(np.array([[lo[0], lo[1], 0.0]]))[0]
    origin = np.array([lo[0], lo[1], 0.0])
    mat = cfg["_ground_mat"]
    fine = None
    for k in range(lods):
        st = 2 ** k
        idx = np.arange(0, n, st)
        m = len(idx)
        vid = (idx[:, None] * n + idx[None, :])
        P, Nn, W, C = P0[vid.ravel()], N0[vid.ravel()], W0[vid.ravel()], C0[vid.ravel()]
        # a coarse cell is a hole if any fine cell in it is
        hc = np.zeros((m - 1, m - 1), bool)
        for a in range(st):
            for b in range(st):
                sub = hole_ij[a::st, b::st][:m - 1, :m - 1]
                hc[:sub.shape[0], :sub.shape[1]] |= sub
        a_, b_ = np.meshgrid(np.arange(m - 1), np.arange(m - 1), indexing="ij")
        v00 = a_ * m + b_
        v10, v01, v11 = v00 + m, v00 + 1, v00 + m + 1
        keep = ~hc.ravel()
        F = np.concatenate([np.c_[v00.ravel(), v10.ravel(), v11.ravel()],
                            np.c_[v00.ravel(), v11.ravel(), v01.ravel()]])[np.r_[keep, keep]]
        images, binfo = None, None
        if cfg.get("maps") and len(F):
            if fine is None:
                with span("ground/fine heightmap"):
                    fine = _fine_ground(R, lo, G.tile, cfg)
            with span(f"ground/lod{k}/maps"):
                prim, images, binfo = _ground_baked(R, mats, fine, P, Nn, W, F, k, lo, origin, cfg, out,
                                                    f"ground_{i}_{j}_lod{k}")
            prims = [prim]
        else:
            prims = [tm._prim(P - origin, Nn, C, W, F, 0, {"role": "surface"}, mats, lo, cfg)]
        # skirts on shared borders: down by how far this LOD's edge strays from the finest one (+ a margin)
        sk = _ground_skirts(P0, n, st, G, lo)
        if sk is not None:
            SP, SF, sv = sk
            prims.append(tm._prim(SP - origin, np.repeat(N0[sv], 2, 0), np.repeat(C0[sv], 2, 0),
                                  np.repeat(W0[sv], 2, 0), SF, 1, {"role": "skirt"}, mats, lo, cfg))
        fn = f"ground_{i}_{j}_lod{k}.glb"
        from . import terrain_bake
        tm.write_glb(out / fn, f"ground_{i}_{j}_lod{k}", prims, trans,
                     mat + ([terrain_bake.material("terrain_baked")] if images else []),
                     extras={"tile": [i, j], "lod": k, "ground": True}, images=images)
        entry["lods"].append({"file": fn, "triangles": int(len(F)), "bytes": (out / fn).stat().st_size})
        if binfo:
            entry["lods"][-1]["maps"] = binfo
        if k == int(cfg["collision"]):
            cf = f"ground_collision_{i}_{j}.glb"
            tm.write_glb(out / cf, f"ground_collision_{i}_{j}", [{"attrs": {"POSITION": tm._to_gltf(P - origin)},
                                                                  "indices": F}], trans, None,
                         extras={"tile": [i, j], "collision": True})
            entry["collision"] = cf
    return entry


def _fine_ground(R: Region, lo, tile, cfg, pad=5):
    """The pushed heightmap on a fine lattice (the ground maps' LOD 0 texel, `pad` texels past the tile each side,
    nodes on the world lattice so neighbours agree): heights and their gradient, sampled bilinearly."""
    n0 = 2 ** int(math.ceil(math.log2(max(tile * float(cfg["ground_density"]), 16))))
    t = tile / n0
    ax = np.arange(-pad, n0 + pad + 1) * t
    X, Y = np.meshgrid(lo[0] + ax, lo[1] + ax, indexing="ij")
    ed = getattr(R.base, "edits", None)  # (the turf's step crisper in the maps than in the mesh)
    Hg = R.height(X.ravel(), Y.ravel(), None if ed is None else max(ed.lip_cfg["maps"], 1.5 * t),
                  1.5 * t).reshape(X.shape)
    gx, gy = np.gradient(Hg, t)
    return {"x0": lo[0] - pad * t, "y0": lo[1] - pad * t, "t": t, "H": Hg, "gx": gx, "gy": gy, "n0": n0}


def _ground_baked(R, mats, fine, P, N, W, F, k, lo, origin, cfg, out, stem):
    """A ground tile LOD with maps: uv = the tile's square (row 0 north), colour/normal/ORM baked from the pushed
    heightmap sampled at each texel (finer than the grid mesh), AO from the rock field."""
    from PIL import Image
    from . import terrain_bake as tb
    size = max(32, fine["n0"] >> k)
    tile = R.G.tile
    # texel centres on the tile's edges (u = 0.5 / size at the west edge, 1 - 0.5 / size at the east): both tiles bake
    # the same border points, so sampling there matches whatever the sampler's wrap mode (a half-texel inset put the
    # two sides a texel apart: 1 m at LOD 2)
    s_ = (size - 1) / size
    uv = np.c_[0.5 / size + (P[:, 0] - lo[0]) / tile * s_, 0.5 / size + (1 - (P[:, 1] - lo[1]) / tile) * s_]
    T4 = tb.tangents(P, N, uv, F)

    def sample(a, x, y):
        return ndimage.map_coordinates(a, [(x - fine["x0"]) / fine["t"], (y - fine["y0"]) / fine["t"]], order=1,
                                       mode="nearest")

    def surface(Pl, Nl):
        x, y = Pl[:, 0], Pl[:, 1]
        X = np.c_[x, y, sample(fine["H"], x, y)]
        G = np.c_[-sample(fine["gx"], x, y), -sample(fine["gy"], x, y), np.ones(len(x))]
        return X, G / np.linalg.norm(G, axis=1, keepdims=True), np.zeros(len(x), bool)
    maps, info = tb.bake(surface, R.base, mats, P, N, T4, uv, F, (size, size), cfg["_layer_rough"],
                         texel=tile / size)
    (out / "maps").mkdir(exist_ok=True)
    wfiles = []
    for g, w in enumerate(maps["weights"]):
        fn = f"maps/{stem}_weights{g}.png"
        Image.fromarray(w, "RGBA").save(out / fn)
        wfiles.append(fn)
    images = [(tb.jpeg(maps["basecolor"]), "image/jpeg"), (tb.png(maps["orm"], "RGB"), "image/png"),
              (tb.png(maps["normal"], "RGB"), "image/png")]
    attrs = {"POSITION": tm._to_gltf(P - origin), "NORMAL": tm._to_gltf(N),
             "TANGENT": np.c_[tm._to_gltf(T4[:, :3]), T4[:, 3]], "TEXCOORD_0": uv}
    sq = int(cfg["splat"])
    if sq:
        mg = int(cfg["splat_margin"])
        Nn = sq + 2 * mg
        Q = P - origin
        attrs["TEXCOORD_1"] = np.c_[(Q[:, 0] / tile * sq + mg) / Nn, 1 - (Q[:, 1] / tile * sq + mg) / Nn]
    for g in range(0, W.shape[1], 4):
        w = W[:, g:g + 4]
        attrs[f"_WEIGHTS{g // 4}"] = np.c_[w, np.zeros((len(w), 4 - w.shape[1]))]
    info.update(size=[size, size], texels_per_m=round(size / tile, 2), weights=wfiles)
    info.pop("height_range_m", None)
    return {"attrs": attrs, "indices": F, "material": 2, "extras": {"role": "surface"}}, images, info


def _ground_skirts(P0, n, st, G, lo):
    """Skirt strips hanging from each shared border edge of a stride-`st` grid (vertical, as deep as the edge's
    worst sag against the finest samples, + 0.3 m)."""
    grid = P0.reshape(n, n, 3)
    sides = []
    for ax, pos, sl in ((0, 0, (0, slice(None))), (0, 1, (n - 1, slice(None))), (1, 0, (slice(None), 0)),
                        (1, 1, (slice(None), n - 1))):
        lim = lo[ax] + pos * G.tile
        if not (G.lo[ax] < lim < G.hi[ax]):
            continue
        line = grid[sl]  # (n, 3) along the other axis
        ids = np.arange(n)
        vid = (ids * n + sl[1]) if ax == 1 else (sl[0] * n + ids)
        sides.append((line, vid, ax, pos))
    if not sides:
        return None
    SP, SF, sv = [], [], []
    for line, vid, ax, pos in sides:
        k = np.arange(0, n, st)
        z = line[k, 2]
        zi = np.interp(np.arange(n), k, z)
        dev = np.abs(zi - line[:, 2])
        depth = max(0.3, 1.25 * float(dev.max()) + 0.3) if st > 1 else 0.3
        # every LOD hangs its skirt deep enough for the coarsest neighbour it may meet (4x its own stride)
        k4 = np.arange(0, n, 4)
        zc = np.interp(np.arange(n), k4, line[k4, 2])
        depth = max(depth, 1.25 * float(np.abs(zc - line[:, 2]).max()) + 0.3)
        top = line[k]
        bot = top - np.array([0, 0, depth])
        pts = np.empty((2 * len(k), 3))
        pts[0::2], pts[1::2] = top, bot
        off = sum(len(s_) for s_ in SP)
        SP.append(pts)
        sv.append(vid[k])
        for q in range(len(k) - 1):
            a, b = off + 2 * q, off + 2 * q + 2
            # facing out of the tile: winding by side (either way it's double-sided)
            SF += [(a, b, a + 1), (b, b + 1, a + 1)] if (ax == 0) != (pos == 1) else [(b, a, a + 1), (b, a + 1, b + 1)]
    return np.vstack(SP), np.array(SF, np.int64), np.concatenate(sv)


def ground_check(out: Path, M: dict, R: Region | None = None, memo=None, tile_keys=None) -> dict:
    """Ground tiles read back: shared borders identical per LOD (vertices and edges), heightmap edges identical, and
    how much of the pushed heightmap under the cliff meshes would show through their faces."""
    failures, summary = [], {}
    tiles = {(e["i"], e["j"]): e for e in M["ground"]}
    lods = len(next(iter(tiles.values()))["lods"])
    data = {}
    for (i, j), e in tiles.items():
        for k, L in enumerate(e["lods"]):
            tr, prims = tm.read_glb(out / L["file"])
            P = tm._from_gltf(prims[0]["POSITION"].astype(np.float64)) + tm._from_gltf(tr[None])[0]
            data[i, j, k] = (P, prims[0]["indices"])
    bad_edges = 0
    for (i, j) in tiles:
        for di, dj, ax in ((1, 0, 0), (0, 1, 1)):
            if (i + di, j + dj) not in tiles:
                continue
            lim = tiles[i, j]["max"][ax]
            for k in range(lods):
                A, B = data[i, j, k], data[i + di, j + dj, k]
                sa = {tuple(p) for p in A[0][A[0][:, ax] == lim]}
                sb = {tuple(p) for p in B[0][B[0][:, ax] == lim]}
                if sa != sb:
                    bad_edges += 1
                    failures.append(f"ground {i},{j} / {i + di},{j + dj} LOD {k}: border vertices differ")
    hm_bad = 0
    for (i, j), e in tiles.items():
        h = np.load(out / e["heightmap"])
        if (i + 1, j) in tiles:
            hm_bad += int(np.any(h[:, -1] != np.load(out / tiles[i + 1, j]["heightmap"])[:, 0]))
        if (i, j + 1) in tiles:
            hm_bad += int(np.any(h[0, :] != np.load(out / tiles[i, j + 1]["heightmap"])[-1, :]))
    if hm_bad:
        failures.append(f"{hm_bad} heightmap tile edges differ from their neighbours'")
    if M.get("maps"):
        ms = tm.map_seams(out, M["ground"], lods, memo=memo)
        summary["map_seams"] = ms
        for key, r in ms.items():
            if not r["ok"]:
                failures.append(f"ground {key}: baked maps differ across tile borders in {r['bad']}: "
                                + ", ".join(f"{c} p50/p95 {r[c]}" for c in r["bad"]))
    summary["ground_border_mismatches"] = bad_edges
    summary["heightmap_edges_differing"] = hm_bad
    if R is not None:
        # where the region is solid cliff (S > 0.9), the heightmap must stay behind the shell's front
        pts = []
        for (i, j), e in tiles.items():
            P, _ = data[i, j, 0]
            s = R.s(P[:, 0], P[:, 1])
            pts.append(P[s > 0.9])
        P = np.vstack(pts) if pts else np.zeros((0, 3))
        if len(P):
            f = CliffField(R.base, R).front(P)
            show = f > 0.05
            summary["heightmap_through_cliff_pct"] = round(100 * float(show.mean()), 3)
            if show.mean() > 0.02:
                failures.append(f"the pushed heightmap shows through the cliff faces at {show.mean():.1%} of the "
                                f"samples under them (e.g. at {P[show][:3].round(1).tolist()})")
        # every sample of the heightmap left standing (not in a hole) must be on or in rock, not in a void
        air = []
        for (i, j), e in tiles.items():
            P, F = data[i, j, 0]
            used = np.unique(F)
            Q = P[used]
            near = np.zeros(len(Q), bool)
            for v in R.voids:
                near |= np.all((Q[:, :2] >= v.lo[:2]) & (Q[:, :2] <= v.hi[:2]), axis=1)
            if near.any():
                Q = Q[near]
                air.append(Q[R.base.value(Q - [0, 0, 0.05]) > 0.02])
        A = np.vstack(air) if air else np.zeros((0, 3))
        summary["heightmap_in_voids"] = int(len(A))
        if len(A):
            failures.append(f"{len(A)} heightmap vertices stand in a void (a hole missing), e.g. "
                            f"{A[:3].round(1).tolist()}")
    if R is not None and M.get("tiles"):
        fl = floating(out, M, R, memo=memo, tile_keys=tile_keys)
        summary["cliff_components"] = fl["components"]
        summary["floating_components"] = len(fl["floating"])
        for f in fl["floating"][:5]:
            failures.append(f"a cliff-mesh piece floats clear of the ground ({f['triangles']} triangles, lowest "
                            f"{f['clearance_m']:.2f} m over the heightmap, at {f['at']})")
    summary["failures"] = len(failures)
    return {"summary": summary, "failures": failures}


def floating(out: Path, M: dict, R: Region, lod: int = 0, tol: float = 0.15, memo=None, tile_keys=None) -> dict:
    """Connected pieces of the cliff meshes (LOD `lod`, every tile welded by position) that never reach down to the
    ground: a piece is grounded if some vertex lies at or under the pushed heightmap (+ tol) or under the sea floor
    it stands on; one that doesn't floats in the air (a stack's head cut off by the rock relief, a shell fragment).
    Each tile's clearances (pointwise) can come from `memo` by its GLB's bytes and `tile_keys[i, j]` (what the pushed
    heightmap reads there: the incremental export's field key)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from . import terrain_incremental as inc
    Ps, Fs, Cs, off = [], [], [], 0
    for e in M["tiles"]:
        L = e["lods"][lod]
        if not L:
            continue
        tr, prims = tm.read_glb(out / L["file"])
        o = tm._from_gltf(tr[None])[0]
        tp = []
        for p in prims:
            if p["extras"].get("role") == "skirt":
                continue
            P = tm._from_gltf(p["POSITION"].astype(np.float64)) + o
            Ps.append(P)
            tp.append(P)
            Fs.append(p["indices"] + off)
            off += len(P)
        if tp:
            Q = np.vstack(tp)
            key = None
            if memo is not None and tile_keys is not None and (e["i"], e["j"]) in tile_keys:
                key = inc._h("clearance", inc.file_hash(out / L["file"]), tile_keys[e["i"], e["j"]])
            c = memo.get(key) if key is not None else None
            if c is None:
                c = Q[:, 2] - R.height(Q[:, 0], Q[:, 1])
                if key is not None:
                    memo.put(key, c)
            Cs.append(c)
    if not Ps:
        return {"components": 0, "floating": []}
    P, F = np.vstack(Ps), np.vstack(Fs)
    _, uid, inv = np.unique(np.round(P, 4), axis=0, return_index=True, return_inverse=True)
    F = inv.ravel()[F]
    P = P[uid]
    n = len(P)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]]])
    ncomp, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    clear = np.concatenate(Cs)[uid]  # (pointwise: each tile's own, the same as over all points at once)
    # a piece that runs off the exported block (an `only` export: the tile beyond wasn't made, but the world goes on)
    # continues there: on a wall steep all the way across the block the shell never came down to the ground inside it
    have = {(g["i"], g["j"]) for g in M.get("ground", [])} or {(e["i"], e["j"]) for e in M["tiles"]}
    G = R.G
    off = np.zeros(len(P), bool)
    for ax in (0, 1):
        t = (P[:, ax] - G.origin[ax]) / G.tile
        on = np.abs(t - np.round(t)) < 1e-6
        inner = (P[:, ax] > G.lo[ax] + 1e-6) & (P[:, ax] < G.hi[ax] - 1e-6)
        k = np.flatnonzero(on & inner)
        if not len(k):
            continue
        line = np.round(t[k]).astype(int)
        other = np.floor((P[k, 1 - ax] - G.origin[1 - ax]) / G.tile).astype(int)
        for side in (line - 1, line):  # the tiles either side of the plane
            ij = [(s_, o) if ax == 0 else (o, s_) for s_, o in zip(side, other)]
            off[k] |= np.array([q not in have for q in ij])
    clear = np.where(off, -np.inf, clear)
    low = np.full(ncomp, np.inf)
    np.minimum.at(low, lab, clear)
    tri = np.bincount(lab[F[:, 0]], minlength=ncomp)
    out_ = []
    for c in np.flatnonzero(low > tol):
        at = P[lab == c].mean(0)
        out_.append({"triangles": int(tri[c]), "clearance_m": float(low[c]), "at": at.round(1).tolist()})
    out_.sort(key=lambda f: -f["triangles"])
    return {"components": int(ncomp), "floating": out_}
