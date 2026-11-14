"""Terrain materials: the layers a point of the surface gets and their colours. Part of the terrain mesh
(terrain_mesh.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import terrain_mesh
from . import fieldjit, noise
from .profiling import span as _span
from .terrain_mesh import _f64, smoothstep
from .terrain_relief import _bed_noise, bed_planes, strata
from .terrain_volumes import _sea

# ---------------------------------------------------------------- materials
def rock_colours(T):
    """sRGB per terrain cell: the colour the heightfield views paint on rock there (terrain_rock.colour when it
    exists, else the same rule as terrain_views.ground_colours: the kind's rock, sandstone for arid kinds, and every
    rock-type cover layer, e.g. black lava or a cliff's grey, over it where its mask is)."""
    from . import terrain_design_cover
    from . import terrain_rock
    f = getattr(terrain_rock, "colour", None)
    if f is not None:
        return np.asarray(f(T), float)
    arid = T.world["kind"] in ("canyon", "dunes", "plateau")
    hn = (T.H - T.H.min()) / max(np.ptp(T.H), 1)
    base = np.array([0.58, 0.38, 0.26]) if arid else np.array(terrain_rock.params(T).get("rock_colour",
                                                                                       terrain_mesh.LAYERS["rock"]["color"]))
    c = base + 0.06 * hn[..., None]
    for name, m in T.cover.items():
        spec = terrain_design_cover._spec_cover(T, name)
        if terrain_mesh.LAYER_OF.get(spec.get("type", name)) == "rock":
            a = np.clip(m, 0, 1)[..., None]
            c = c * (1 - a) + np.array(terrain_design_cover.cover_colour(T, name)) * a
    tone = (getattr(T, "rock", None) or {}).get("tone") if isinstance(getattr(T, "rock", None), dict) else None
    if tone is not None and np.shape(tone) == T.H.shape:
        c = c * np.asarray(tone)[..., None]
    return c


class Materials:
    """Per-vertex layer weights (for engines: world-space/triplanar tiling layers blended by weight) and a display
    colour (the reference material's vertex colour), both from the global masks at the vertex's position and the
    field's normal there: continuous across seams."""

    def __init__(self, T, field):
        from . import terrain_design_cover
        from .terrain_views import ground_colours
        self.T, self.field = T, field
        self.sea = _sea(T)
        order = []
        self.cover = []
        from . import terrain_ground
        from . import terrain_ground_model
        for name, m in T.cover.items():
            c = terrain_design_cover._spec_cover(T, name)
            typ = c.get("type", name)
            layer = terrain_mesh.LAYER_OF.get(typ, "grass")
            tree = bool(c.get("trees"))
            self.cover.append((name, layer, 0.6 if tree else 1.0, terrain_ground.KIND_OF.get(typ)))
            order.append(layer)
        self.layers = list(dict.fromkeys(order + ["rock", "earth"] + (["sand", "wet_rock"] if self.sea is not None
                                                                      else [])))
        # a stream's bed and banks (terrain_stream): its layers come last, so the older layers keep their channels
        ed0 = getattr(field, "edits", None) or getattr(getattr(field, "base", None), "edits", None)
        self.streams = getattr(ed0, "streams", None)
        if self.streams is not None:
            from . import terrain_stream
            self.layers = list(dict.fromkeys(self.layers + ["wet_rock", *terrain_stream.LAYERS]))
        col = ground_colours(T, cover=True)
        wet = ~np.isnan(T.water)
        col[wet] = np.array(terrain_mesh.LAYERS["sand"]["color"]) * 0.8
        if getattr(T, "spec", {}).get("ground_character", True) is not False:
            # (a cell's cover colour sampled as is drew every cover edge as the grid's staircase: fairways were cut-out
            # stickers with stepped edges; softened over about a cell, and warped a little where sampled)
            col = np.stack([ndimage.gaussian_filter(col[..., i], 0.9) for i in range(3)], -1)
        self.display = col
        if getattr(T, "spec", {}).get("ground_character", True) is not False:
            # the bare ground's colour (slope, height, roads, water) as a grid; the covers are painted over it per point
            # with the same crisp weights as the layers (from the cell grid, a fairway's or a bunker's edge was the
            # grid's 2-cell blur however crisp its weight: soft stickers)
            bare = ground_colours(T, cover=False)
            bare[wet] = np.array(terrain_mesh.LAYERS["sand"]["color"]) * 0.8
            self.display_bare = np.stack([ndimage.gaussian_filter(bare[..., i], 0.9) for i in range(3)], -1)
            self.cover_col = {name: np.asarray(terrain_design_cover.cover_colour(T, name), float) for name, *_ in self.cover}
        self.rock_grid = rock_colours(T)
        steep = T._slope() > 45
        self.rock_ref = np.median(self.rock_grid[steep] if steep.any() else self.rock_grid.reshape(-1, 3), 0)
        self.routes = T.masks.get("routes")
        # the ground's character between the rock faces (terrain_ground): turf edges, shore, variation, cover kinds
        ed = getattr(field, "edits", None) or getattr(getattr(field, "base", None), "edits", None)
        self.ground = terrain_ground_model.Ground(T, field.H, self.sea, ed) if getattr(T, "spec", {}).get(
            "ground_character", True) is not False else None
        if self.ground is not None:  # (its per-cover grids made now, not lazily per worker)
            for name, layer, k, kind in self.cover:
                if kind == "mown":
                    self.ground.mown_sd(name, T.cover[name])
                    self.ground.stripe_frame(name, T.cover[name])
        for name in T.cover:  # (made now: a lazy cache filled in some processes and not others)
            self._covf(name)

    def layer_ref(self, name):
        """A layer's reference look for the manifest (rock: this terrain's own rock colour)."""
        ref = dict(terrain_mesh.LAYERS[name])
        if name == "rock":
            ref["color"] = [round(float(x), 3) for x in self.rock_ref]
        elif name == "wet_rock":
            ref["color"] = [round(float(x) * 0.45, 3) for x in self.rock_ref]
        return ref

    def _grid(self, a, xy):
        """A per-cell grid (cover, colours) at points: a cubic B-spline over the cells (approximating, no prefilter:
        smooth and never overshooting). Bilinear it had a crease in its gradient on every cell line, and the per-cell
        variation (tone, strata, slope-dependent beds) showed as a quilt of cell-sized squares on the rock, plainest
        from 100 m and more (5 m cells on the alps)."""
        T = self.T
        if fieldjit.ON:
            return fieldjit.grid_at(np.ascontiguousarray(a, dtype=np.float64), _f64(xy[:, 0]), _f64(xy[:, 1]),
                                    float(T.xs[0]), float(T.ys[0]), float(T.cell))
        return ndimage.map_coordinates(np.asarray(a, float), [(xy[:, 1] - T.ys[0]) / T.cell,
                                                              (xy[:, 0] - T.xs[0]) / T.cell],
                                       order=3, prefilter=False, mode="nearest")

    def _covf(self, name):
        """A cover's mask as a contiguous float64 grid (made once: per call it was most of a weights call)."""
        cache = self.__dict__.setdefault("_covf_cache", {})
        if name not in cache:
            cache[name] = np.ascontiguousarray(self.T.cover[name], dtype=np.float64)
        return cache[name]

    def _cover_d(self, name, kind, xy):
        """A cover's weight (0..1) at points: its mask as a cubic spline over the cells, cut crisp where the ground
        character asks: a bunker at its dug edge, a mown piece along the mower's line (as a 2-cell blur both read as
        soft-edged stickers)."""
        d = np.clip(self._grid(self._covf(name), xy), 0, 1)
        g = self.ground
        if g is None:
            return d
        e = g.edits.bunker_of(name)
        if e is not None:
            return smoothstep(0.06, -0.06, e(xy)) * np.clip(2 * d, 0, 1)
        if kind == "mown":
            return smoothstep(0.3, -0.3, g.mown_sd(name, self.T.cover[name])(xy)) * np.clip(2 * d, 0, 1)
        return d

    def _covers(self, P):
        """(per-layer weights, kinds, mown stripes [(weight, -1..1)], rest) as painted (later layers over earlier);
        kinds: terrain_ground.KIND_OF's mown/rough/scrub, plus "cut": the first cut, a mown band round each mown piece
        taken out of the rough round it."""
        xy = P[:, :2]
        n = len(P)
        W = {k: np.zeros(n) for k in self.layers}
        rest = np.ones(n)
        kinds, mown = {}, []
        bands = []
        for name, layer, k, kind in reversed(self.cover):  # painted in order: later layers over earlier
            d = self._cover_d(name, kind, xy) * k
            W[layer] += d * rest
            if kind is not None and self.ground is not None:
                kinds[kind] = kinds.get(kind, 0.0) + d * rest
                if kind == "mown":
                    mown.append((d * rest, self.ground.stripes(P, name, self.T.cover[name], along=True)))
                    bands.append(self.ground.first_cut(P, name, self.T.cover[name]))
            rest *= 1 - d
        if bands and "rough" in kinds:
            cut = np.minimum(np.max(bands, 0), kinds["rough"])
            kinds["rough"] = kinds["rough"] - cut
            kinds["cut"] = cut
        return W, kinds, mown, rest

    def _route(self, xy, kinds):
        """0..0.8: how worn the routes' ground is at points (None: no routes). Only off mown turf: a way across a fairway
        or a green is walked on grass (painted over everything it read as a pale sandy band across the fairways)."""
        if self.routes is None:
            return None
        r = np.clip(self._grid(self.routes.astype(float), xy), 0, 1) * 0.8
        if self.ground is not None and kinds:
            turf = np.clip(np.asarray(kinds.get("mown", 0.0) + kinds.get("cut", 0.0), float), 0, 1)
            r = r * (1.0 - smoothstep(0.1, 0.6, turf))
        return r

    def _paint(self, xy, wxy, rd=None):
        """The display colour before the ground's character: the bare ground's grid (at the warped points), each
        cover's colour painted over it in order with its weight (crisp-edged covers at the points themselves, the
        rest at the warped ones), the roads over everything (sRGB)."""
        c = np.stack([self._grid(self.display_bare[..., i], wxy) for i in range(3)], 1)
        rest = np.ones(len(xy))
        acc = np.zeros((len(xy), 3))
        g = self.ground
        for name, layer, k, kind in reversed(self.cover):
            crisp = kind == "mown" or g.edits.bunker_of(name) is not None
            d = (self._cover_d(name, kind, xy) if crisp else
                 np.clip(self._grid(self._covf(name), wxy), 0, 1)) * k
            acc += (d * rest)[:, None] * self.cover_col[name]
            rest = rest * (1 - d)
        c = acc + rest[:, None] * c
        if rd is not None:
            arid = self.T.world["kind"] in ("canyon", "dunes", "plateau")
            rd = np.broadcast_to(np.asarray(rd, float), (len(xy),))[:, None]
            c = c * (1 - rd) + (np.array([0.78, 0.66, 0.5]) if arid else np.array([0.55, 0.47, 0.36])) * rd
        return c

    def relief(self, P, Wt, texel):
        """The ground's maps-only relief (terrain_ground_model.Ground.relief) as a plan gradient (n, 2), weighted by the
        grass layers (not on rock or sand), or None without ground character."""
        if self.ground is None:
            return None
        _, kinds, mown, _ = self._covers(P)
        w = sum(Wt[:, self.layers.index(nm)] for nm in ("grass", "turf", "scrub") if nm in self.layers)
        if not np.isscalar(w):
            kinds = {k: v * w for k, v in kinds.items()}
            mown = [(m * w, st) for m, st in mown]
        g = self.ground.relief(self, P, kinds, mown, texel)
        if self.streams is not None:  # (a stream bed's cobble lumps)
            g = g + self.streams.relief(P, np.asarray(Wt[:, self.layers.index("gravel")], float), texel)
        return g

    def kinds(self, P):
        """The cover kinds (terrain_ground.KIND_OF: mown, rough, scrub; "cut": the first cut round mown pieces) at
        points, as painted (later layers over earlier)."""
        return self._covers(P)[1]

    def weights(self, P, N):
        with _span("materials.weights"):
            return self._weights(P, N)

    def _weights(self, P, N):
        xy = P[:, :2]
        n = len(P)
        W, kinds, mown, rest = self._covers(P)
        W["earth"] += rest
        r = self._route(xy, kinds)
        if r is not None:
            for key in W:
                W[key] *= 1 - r
            W["earth"] += r
        # rock: steep or overhanging faces (from the field's normal), and anything below the heightfield's ground
        # (a cave's walls and roof, an arch's soffit)
        slope = np.degrees(np.arccos(np.clip(N[:, 2], -1, 1)))
        below = smoothstep(0.3, 1.2, -self.field.ground(P))
        rock = np.maximum(smoothstep(38, 58, slope), below)
        under = None
        if self.ground is not None:  # the turf's ragged edge back from a lip, rock breaking through, the splash zone
            g_rock, under, shore, ledge = self.ground.rock(self, P, N)
            g_rock = np.maximum(g_rock - shore * W.get("sand", 0.0), 0.0)  # (beaches stay sand)
            for key in ("forest_floor",):  # (not under trees)
                if key in W:
                    g_rock = g_rock * (1 - W[key])
            rock = np.maximum(rock, g_rock)
            # (green on the faces' ledges near a top, off the wet band and out of caves)
            rock = rock * (1 - ledge * (1 - below) * smoothstep(self.sea + 2.5, self.sea + 4.0, P[:, 2])
                           if self.sea is not None else 1 - ledge * (1 - below))
        if getattr(self.field, "fall", None) is not None:  # (a fallen block: anything standing clear of the ground)
            rock = np.maximum(rock, smoothstep(0.05, 0.25, self.field.ground(P)) *
                              np.clip(4 * self.field.fall_at(P[:, 0], P[:, 1]), 0, 1))
        tide = np.zeros(n)
        if self.sea is not None:  # under water: sand, unless rock
            wet = smoothstep(0.2, 1.2, self.sea - P[:, 2])
            for key in W:
                W[key] *= 1 - wet
            W["sand"] += wet
            # the splash zone: rock dark and wet from the water up a couple of metres, higher inside caves and notches
            # its upper edge wanders a metre and more (a level line read as paint), wettest right at the water
            sh = 1.6 * (noise.fbm(P * np.array([1.0, 1.0, 0.3]), 4.0, 2, seed=77) - 0.5)
            tide = smoothstep(self.sea + 2.2 + 1.5 * below + sh, self.sea + 0.3, P[:, 2]) ** 1.3
        for key in W:
            W[key] *= 1 - rock
        W["rock"] += rock * (1 - tide)
        if "wet_rock" in W:
            W["wet_rock"] += rock * tide
        sbed = self.streams.shares(P, N) if self.streams is not None else None
        if sbed is not None:
            # a stream's bed under its water (gravel and cobbles, silt in the slack, bedrock on steep reaches) and the
            # damp foot of its banks, over whatever the ground had there; steep faces stay rock (wet near the water)
            ks = sbed["k"]
            away = 1.0 if self.sea is None else 1 - smoothstep(0.2, 1.2, self.sea - P[ks, 2])  # (the sea's own bed)
            sbed["bed"], sbed["damp"] = sbed["bed"] * away, sbed["damp"] * away
            face = rock[ks]
            wetn = np.clip(sbed["bed"] + sbed["damp"], 0, 1)
            W["wet_rock"][ks] += W["rock"][ks] * wetn
            W["rock"][ks] *= 1 - wetn
            bed, damp = sbed["bed"] * (1 - face), sbed["damp"] * (1 - face)
            for key in W:
                if key not in ("rock", "wet_rock"):
                    W[key][ks] *= 1 - bed - damp
            W["gravel"][ks] += bed * sbed["gravel"]
            W["silt"][ks] += bed * sbed["silt"]
            W["wet_rock"][ks] += bed * sbed["rock"]
            W["bank"][ks] += damp
        Wm = np.stack([W[k] for k in self.layers], 1)
        Wm /= np.maximum(Wm.sum(1, keepdims=True), 1e-9)
        # display colour: the terrain's own preview colours (cover, roads, slope), rock over steep faces and caves
        if self.ground is not None:  # (cover edges wander ~0.6 m: not the grid's straight runs)
            Pf = P * np.array([1.0, 1.0, 0.0])
            wxy = xy + 0.6 * np.c_[noise.fbm(Pf, 4.0, 2, seed=631) - 0.5, noise.fbm(Pf, 4.0, 2, seed=632) - 0.5]
            c = self._paint(xy, wxy, self._route(wxy, kinds))
        else:
            c = np.stack([self._grid(self.display[..., i], xy) for i in range(3)], 1)
        if self.ground is not None:
            if "sand" in W:
                kinds["sand"] = W["sand"]
            c = self.ground.tint(self, P, N, c, kinds, mown)
        if self.sea is not None:
            wet = smoothstep(0.2, 1.2, self.sea - P[:, 2])[:, None]
            c = c * (1 - wet) + np.array(terrain_mesh.LAYERS["sand"]["color"]) * 0.8 * wet
        # the rock's own colour where the heightfield views paint it (the kind's rock, strata bands, rock cover
        # layers such as black lava or a cliff's grey), not one grey for every terrain
        rc = np.stack([self._grid(self.rock_grid[..., i], xy) for i in range(3)], 1)
        if self.field.rock is not None:  # beds and facets differ in tone (a single grey read as plaster)
            r = self.field.rock
            g = self.field.grain_at(P[:, 0], P[:, 1]) if self.field.grain is not None else None
            B = bed_planes(P, r, g)
            kb, fr = B["kb"], B["f"]
            # each bed's tone changes along the strike too (one tone per bed was a band ruled across the wall)
            calm = 0.35 if r.get("blocks") else 1.0  # (blocks carry the tone where they exist: less blotchy noise)
            if r.get("blocks") and getattr(self.field, "thin", None) is not None:
                # thin fins and stacks (an arch's fin) take little relief (Field.thin: carved, their tops floated off),
                # so their beds show in colour instead: Durdle Door's banding, not a smooth tan wall
                calm = calm + (1.0 - calm) * np.clip(self._grid(self.field.thin, xy), 0, 1) * terrain_mesh.THIN_TONE
            th = lambda k: 1 + calm * (-0.16 + 0.26 * _bed_noise(xy, k, 40.0, r["seed"] + 30))
            # (each bed's tone eases into the next over ~0.2 m where the plane shows, a step aliased along every
            # bedding plane in the maps; over metres where it doesn't: no line there)
            e = np.minimum(0.45, (0.2 + (1 - B["pres"]) * 4.0) / r["bed"])
            lo_, hi_ = smoothstep(-e, e, fr), smoothstep(-e, e, fr - 1)
            tone = th(kb - 1) * (1 - lo_) + th(kb) * (lo_ - hi_) + th(kb + 1) * hi_
            # (a smooth noise: the facet lattice's tone had straight edges and read as a checker of squares)
            tone = tone * (1 + calm * (-0.08 + 0.12 * (2 * noise.fbm(P, r["size"], 2, seed=r["seed"] + 40) - 1)))
            tone = tone * (1 + calm * (-0.07 + 0.14 * noise.fbm(P, 2.5 * r["size"], 2, seed=r["seed"] + 31)))
            rc = rc * tone[:, None]
            if r.get("blocks"):
                rc = block_colour(P, N, rc, r, self.field.face_dir(P[:, 0], P[:, 1]),
                                  lines=not getattr(self, "lines_in_maps", False))
            bf = self.field
            while bf is not None and not hasattr(bf, "thin_at"):
                bf = getattr(bf, "base", None)
            if terrain_mesh.THIN_RELIEF > 0 and terrain_mesh.THIN_STRATA["depth"] > 0 and bf is not None and getattr(bf, "thin_parts", None):
                # thin rock's strata in colour too: soft beds (sitting back) darker and warmer, hard ones paler
                _, tw = bf.thin_at(P)
                kt = np.flatnonzero(tw > 1e-3)
                if len(kt):
                    zoff = r["bed_offset"](P[kt, :2]) if r.get("bed_offset") else 0.0
                    so = strata(P[kt], zoff, r["seed"], tone=True)
                    st = np.sqrt(tw[kt])  # (as the geometry's strata)
                    f = 1 + st * terrain_mesh.THIN_STRATA["tone"] * (0.3 - so)
                    rc[kt] = rc[kt] * f[:, None] * (1 + st[:, None] * 0.06 * so[:, None] * np.array([1.0, 0.0, -1.0]))
        # crevices, joints and the backs of overhangs darker (how open the field is half a metre out along the
        # normal: a cheap occlusion that needs no ray tracing, the same in every engine)
        d = 0.8
        open_ = np.clip(self.field.value(P + d * N) / d, 0, 1)
        # (lighter with the rock structure: its recesses are already shaded by geometry and the AO map; with this too
        # every slot read as black-outlined)
        lo = 0.66 if (self.field.rock or {}).get("blocks") else 0.55
        rc = rc * (lo + (1 - lo) * open_)[:, None]
        if under is not None:  # (the rock just under the turf's lip: shaded by the overhanging mat)
            from .terrain_ground import LOOK
            rc = rc * (1 - (1 - LOOK["undercut"]) * under)[:, None]
        if sbed is not None:  # (the bed and the damp bank, under the rock faces: those wet and darker by the water)
            ks = sbed["k"]
            c[ks] = self.streams.colour(P[ks], c[ks], rc[ks], sbed)
            rc[ks] = rc[ks] * (1 - 0.45 * np.clip(sbed["bed"] + sbed["damp"], 0, 1)[:, None])
        c = c * (1 - rock[:, None]) + rc * (1 - 0.55 * tide[:, None]) * rock[:, None]  # wet: its own rock, darker
        return Wm.astype(np.float32), c


# block_colour's spread: per bed and per block (+-), thin packages darker, the share of freshly spalled blocks and how
# much paler (and warmer, per channel) they are; weathering along the beds (+-) and the darkening under each ledge
def block_colour(P, N, rc, r, fd, lines=True):
    """Rock colour from the block structure (terrain_blocks): each block and course weathered to its own tone, the
    joints and bedding planes as dark lines (eased to the line over ~0.15 m: a step aliases in the maps), dark water
    stains streaking down the faces in patches, pale grey-green lichen on ledge tops. Structure-driven colour instead
    of blotchy noise."""
    from . import terrain_blocks
    B = r["blocks"]
    zoff = r["bed_offset"](P[:, :2]) if r.get("bed_offset") else 0.0
    I = terrain_blocks.ids(P, B, fd, zoff)
    sd = B["seed"] + 500
    hsh = lambda i, j, s_: noise._hash(i, j, np.zeros_like(i), sd + s_)
    # 0 at an edge, 1 from 0.25 m (narrower lines stair-stepped on 16/m texels seen from 5 m)
    ease = lambda e: (lambda x: x * x * (3 - 2 * x))(np.clip(e / 0.25, 0, 1))
    K, j = I["K"], I["j"]
    eb = ease(I["bed_edge"])
    # each bed its own tone (thin packages darker), each block a little different; tones ease to neutral at their edges
    # (equal on both sides: no step to alias); closed joints show only as that tone change and the face's own tilt
    # (whole blocks only a little: +-13% per block read as pasted flat rectangles, a patchwork, at 40 m (n01). What
    # separates faces on real limestone/sandstone is weathering that runs along the beds and down from the ledges, with
    # soft transitions; the blocks' own geometry and the lines do the rest)
    # (a thin package is darker only where it sits back, by as much as it does (terrain_blocks._bed_value's stretches
    # and depth): darker all along, it was a ruled band across the pebble chasm)
    rec = terrain_blocks.package_recess(P[:, :2], K, j, B)
    tone = 1 + (terrain_mesh.BLOCK_TONE["bed"] * (2 * hsh(K, j, 1) - 1) - terrain_mesh.BLOCK_TONE["thin"] * I["thin"] * rec) * eb
    # (lines=False: the open bed planes and joints are drawn crisp from the lines map, terrain_swatch_lines.structure_lines)
    dark = 0.5 * I["bed_crack"] * (1 - eb) * lines  # (bed planes: faint; the geometry draws the ledges)
    fresh = np.zeros(len(P))
    # (a block's tone is not uniform across it: weathering wanders within the face, and a spall bares only part of it;
    # a flat tone per block with crisp edges read as masonry tiles)
    within = noise.fbm(P, 1.6, 2, seed=sd + 6)
    spall = smoothstep(0.4, 0.6, noise.fbm(P, 1.8, 2, seed=sd + 7))  # (0.7 m read as camouflage at 40 m)
    for m, (bi, w) in enumerate(zip(I["blocks"], I["weights"])):
        jj = (K * 16 + j) * 5 + m
        e_m = ease(I["edges"][m])
        tone = tone * (1 + w * terrain_mesh.BLOCK_TONE["block"] * (2 * hsh(bi, jj, 2) - 1) * e_m * (0.55 + 0.9 * within))
        fresh = np.maximum(fresh, w * (hsh(bi, jj, 3) < terrain_mesh.BLOCK_TONE["p_fresh"]) * e_m * spall)
        if lines:
            dark = np.maximum(dark, w * (1 - ease(I["open"][m])))  # (open joints only: most boundaries are closed)
    # freshly spalled faces: paler and warmer (unweathered rock under the grey patina)
    tone = tone * (1 + terrain_mesh.BLOCK_TONE["fresh"] * fresh * eb)
    dark = np.maximum(dark, np.clip(1.6 * I["master"], 0, 1))  # (master joints: always open)
    tone = tone * (1 - 0.18 * dark)
    # stains: dark streaks hanging from the ledges (each super-bed's top), 0.25-0.8 m wide, 2-12 m long, narrowing and
    # fading down; a few per 10 m along the face, in patches. (Stretched noise made ink blots.)
    vert = np.clip((0.7 - np.abs(N[:, 2])) / 0.4, 0, 1)
    fdn = fd / np.maximum(np.linalg.norm(fd, axis=1, keepdims=True), 1e-9)
    u = P[:, 0] * -fdn[:, 1] + P[:, 1] * fdn[:, 0]  # (along the face)
    d = I["below_top"]
    K1 = I["K"]
    patch = np.clip((noise.fbm(P * np.array([1.0, 1.0, 0.3]), 25.0, 2, seed=sd + 4) - 0.4) / 0.2, 0, 1)
    stain = np.zeros(len(P))
    # (candidates every 3 m, a fifth present: every 1.5 m with half present read as a comb from 150 m)
    c0 = np.floor(u / 3.0).astype(np.int64)
    for dc in (-1, 0, 1):
        c = c0 + dc
        uc = (c + 0.5 + 0.8 * (hsh(c, K1, 10) - 0.5)) * 3.0
        L = 2.0 + 10.0 * hsh(c, K1, 11)
        wd = (0.25 + 0.55 * hsh(c, K1, 12)) * (1 - 0.5 * np.clip(d / L, 0, 1))
        on = hsh(c, K1, 13) < 0.22
        across = np.clip(1 - np.abs(u - uc) / wd, 0, 1)
        down = np.clip(1 - d / L, 0, 1) ** 1.5 * np.clip(d / 0.3, 0, 1)
        stain = np.maximum(stain, on * (across * (2 - across)) * down)
    tone = tone * (1 - 0.32 * stain * patch * vert)
    # weathering along the beds: tone bands a few metres long and under a metre tall, following the bed coordinate
    # (soft: no edge to alias), and each ledge's underside darker for a metre or so (runoff and shade), easing in from
    # the plane itself (a step there aliases in the maps)
    bz = P[:, 2] + zoff
    band = noise._value_noise(np.ascontiguousarray(np.c_[u / 6.0, bz / 0.9, K1 * 0.37]), sd + 8)
    tone = tone * (1 + terrain_mesh.BLOCK_TONE["along"] * (2 * band - 1) * vert)
    ul = np.exp(-d / 1.2) * smoothstep(0.0, 0.2, d) * (0.5 + noise._value_noise(
        np.ascontiguousarray(np.c_[u / 9.0, K1 * 0.53, np.zeros(len(P))]), sd + 9))
    tone = tone * (1 - terrain_mesh.BLOCK_TONE["under_ledge"] * ul * vert)
    out = rc * tone[:, None] * (1 + (fresh * eb)[:, None] * np.array(terrain_mesh.BLOCK_TONE["warm"]))
    # lichen on tops: up-facing ledges and block tops, patchy, a dull grey-green (pale lichen read as foam on the ledges)
    up = np.clip((N[:, 2] - 0.4) / 0.35, 0, 1)
    li = np.clip((noise.fbm(P, 0.9, 2, seed=sd + 5) - 0.55) / 0.2, 0, 1) * up
    lichen = rc * np.array([0.8, 0.86, 0.72])
    return out * (1 - 0.5 * li[:, None]) + lichen * (0.5 * li[:, None])


def _linear(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
