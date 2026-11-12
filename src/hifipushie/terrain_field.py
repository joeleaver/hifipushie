"""The terrain field: the signed distance of the whole world (ground, volumes, rock relief) and its metric, and
projection onto it. Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import terrain_mesh
from . import fieldjit, profiling
from .profiling import span as _span
from .terrain_mesh import _f64, smax, smin, smoothstep
from .terrain_relief import _local_thickness, _structure_grain, dig_bunker, dig_doline, hold_rivers, rock_relief
from .terrain_volumes import Tube, cut_neck

class Metric:
    """A Field read for distances (the AO's rays): its value with the waterfalls' slope taken from the faced column
    right up to the face (terrain_falls.SLOPE_NEAR: the meshing field keeps the grid's slope there, for the face's
    normals). Over a fall's lip the grid's slope under-reported the distance 6x and the AO found rock everywhere."""

    def __init__(self, field):
        self.field = field

    def value(self, p):
        if getattr(self.field, "faces", None) is None:
            return self.field.value(p)
        return self.field.value(p, metric=True)


class Field:
    def __init__(self, T, vols: list[Tube], rock=None, dolines=None, cuts=None, bunkers=None):
        self.H = np.ascontiguousarray(T.H, float)
        self.x0, self.y0, self.c = float(T.xs[0]), float(T.ys[0]), float(T.cell)
        self.vols = vols
        self.rock = rock
        self.floor_guard = None
        self.grain = None  # where the rock is cut up (gullies, concave, near the top of a face): finer facets
        self.micro = None  # fine rock relief evaluated only when baking maps (terrain_bake.micro_relief)
        self.fall = None  # where fallen blocks lie (a grid, 0..1)
        for d in dolines or ():  # 2.5D ground edits (karst dolines: grassy funnels into a throat)
            self.H = dig_doline(T, self.H, d)
        for c in cuts or ():  # (a sea arch's neck: the bays either side of it)
            self.H = cut_neck(T, self.H, c)
        from . import terrain_ground
        gcfg = terrain_ground.config(T)
        if gcfg is None:  # (no ground character: sand traps dug into the grid, as 2-cell blurs)
            for m, depth, *_ in bunkers or ():
                self.H = dig_bunker(T, self.H, m, depth)
        self.styles = []  # terrain styles that shape the rock (terrain_style_zones.rock_styles): weight grids + numbers
        H_unstyled = self.H
        if rock is not None and T.spec.get("styles"):
            from . import terrain_style_zones
            self.styles = terrain_style_zones.rock_styles(T)
            if self.styles:  # (a style's softened ground: blobby lips and forms; the heightmap tiles read it too)
                self.H = terrain_style_zones.soften_height(self.H, self.c, self.styles)
        if rock is not None:
            # where the rock character goes: steep ground (45-62 deg), as a smooth mask on the grid (~2 cells). From
            # each point's own column slope it switched on within 0.2 m at a cliff's lip (the B-spline's slope turns
            # fast there): the relief times that switch was a sub-voxel step in the field, meshed as black shards
            gy, gx = np.gradient(self.H, self.c)
            cs = 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)
            # (dilated a cell first: a sheer cliff is a cell or two wide in plan and smoothing alone halved it)
            self.steep = ndimage.gaussian_filter(ndimage.maximum_filter(smoothstep(0.71, 0.47, cs), 3), 1.0)
            # thin fins and stack tops (narrower than twice the relief's reach) take little relief: carving a few
            # metres into a 3 m wide fin cut its top off (a block floating 14 m over the sea at pebble's point)
            r_open = max(2, int(math.ceil(2.0 * rock["reach"] / self.c)))
            yy, xx = np.mgrid[-r_open:r_open + 1, -r_open:r_open + 1]
            disc = (xx * xx + yy * yy) <= r_open * r_open
            thin = smoothstep(0.5, 2.5, self.H - ndimage.grey_opening(self.H, footprint=disc))
            self.thin = ndimage.gaussian_filter(thin, 1.0)
            thin_u = self.thin if H_unstyled is self.H else ndimage.gaussian_filter(
                smoothstep(0.5, 2.5, H_unstyled - ndimage.grey_opening(H_unstyled, footprint=disc)), 1.0)
            # The relief's own weight keeps thin rock (an arch's fin, slim stacks, narrow headlands): bounded there by
            # the rock's local half-thickness at the point's height (`thin_cap`), so it can't carve through or cut a
            # top off. Field.steep (the cliff region, fallen blocks, the heightfield facets' removal) stays as before.
            self.relief_w = self.steep if terrain_mesh.THIN_RELIEF <= 0 else self.steep.copy()
            self.steep = self.steep * (1 - 0.9 * self.thin)
            if terrain_mesh.THIN_RELIEF <= 0:
                self.relief_w = self.steep
            else:
                # (on the ground before any style softened it: a thin piece runs along a coast across zones and its
                # height levels are the whole piece's, so softening one zone re-sliced the others)
                self.thin_parts = _local_thickness(H_unstyled, self.c, r_open, thin_u)
            # (from the ground before any style softened it: its percentile is global, so softening one zone moved
            # every other zone's facet sizes)
            self.grain = _structure_grain(T, H_unstyled, self.c)
            # the heightfield's own facets (terrain_rock: tipped planes on jittered ~5-17 m cells) taken back out where
            # the solid rock gets its own: two facet systems on one face made a moire of lozenges
            fdel = (getattr(T, "rock", None) or {}).get("facet_delta") if isinstance(getattr(T, "rock", None), dict) \
                else None
            if fdel is not None and np.shape(fdel) == self.H.shape:
                wr = np.clip(self.steep, 0, 1)
                for s in self.styles:  # (a softened style takes the heightfield's facets out everywhere in its zone)
                    if float(s["rock"].get("soften_m", 0) or 0) > 0:
                        wr = np.maximum(wr, s["w"])
                self.H = self.H - wr * fdel
            # (the facets taken out or a style's softening must not open a way round a river's banks: below
            # vale_river's 6 m fall a 19 m facet spire came out and left a 13 m pit beside the lip, under the lip's
            # water: the water solve filled it, outside every design; pushieworld note 126)
            self.H = hold_rivers(T, self.H, H_unstyled)
            # the faces' horizontal normal (downhill), smoothed over ~3 cells: which joint families cross a face
            sy, sx = np.gradient(ndimage.gaussian_filter(self.H, 3.0), self.c)
            self._fdx, self._fdy = -sx, -sy
            if rock.get("blocks") and rock["blocks"].get("fallen", 0) > 0:
                # where blocks that fell off the faces lie (terrain_blocks.fall_zone): at their feet, on gentler ground
                from . import terrain_blocks
                self.fall = terrain_blocks.fall_zone(self.H, self.c, self.steep) * float(rock["blocks"]["fallen"])
                for s in self.styles:  # (a style's share of fallen blocks: blobby none)
                    self.fall = self.fall * (1 - s["w"] * (1 - float(s["rock"].get("fallen", 1.0))))
        # ground edits finer than the grid, per point in `column` (terrain_ground.Edits): the turf's step back from
        # every cliff lip, bunkers cut crisp (as a 2-cell blur on the grid they read as soft dishes)
        self.streams = None  # (terrain_stream: the rivers' beds; None without running water)
        if gcfg is not None and (getattr(T, "river_water_lines", None) or
                                 any(not lk.get("sea") for lk in (getattr(T, "lakes", None) or {}).values())):
            from . import terrain_stream
            scfg = terrain_stream.config(T)
            if scfg is not None:
                st_ = terrain_stream.Streams(T, scfg)
                self.streams = st_ if st_.any else None
        self.edits = terrain_ground.Edits(T, self.H, bunkers or (), gcfg, self.streams) if gcfg is not None else None
        if self.edits is not None and any("lip" in s["rock"] for s in getattr(self, "styles", [])):
            # (a style's share of the turf's step at cliff lips: blobby's pillowed ground had crumbs at every lip)
            ls = np.ones(self.H.shape)
            for s in self.styles:
                ls = ls - s["w"] * (1.0 - float(s["rock"].get("lip", 1.0)))
            self.edits.lip_scale = np.ascontiguousarray(np.clip(ls, 0.0, None))
        # waterfalls: the face a step on the lip line and the falling sheet's clearance kept air (terrain_falls.Faces;
        # the grid's face was a 75-80 deg ramp 3.5 m long and the sheet fell onto it: pushieworld note 120)
        from . import terrain_falls
        self.faces = terrain_falls.Faces(T) if getattr(T, "falls", None) else None
        if self.faces is not None and not self.faces.any:
            self.faces = None

    def column(self, x, y, metric=False):
        """Ground height h and the slope correction 1 / sqrt(1 + |grad h|^2) at columns (with the ground edits:
        turf lips, bunkers; and the waterfalls' faces). metric: the faces' slope right up to the face (Metric: AO)."""
        h, s = self._edited_column(x, y)
        if getattr(self, "faces", None) is not None:
            col = lambda a, b: self._edited_column(a, b)[0]
            h, k, wk = self.faces.column(x, y, h, col, touched=True, near=not metric)
            k = k[wk > 0]
            wk = wk[wk > 0]
            if len(k):
                # the slope correction of the column as the faces leave it, not the grid's: the grid holds a fall's
                # face as a ramp over ~2 cells each way, and its s (0.15 on crown_beck's tall fall) on the lip's
                # level top under-reported the field there 6x, so the AO rays found rock everywhere: a black slab
                # in the game (pushieworld note 124)
                xk, yk = np.asarray(x, float)[k], np.asarray(y, float)[k]
                e = terrain_mesh.FACE_SLOPE_H
                hx = [self.faces.column(xk + d, yk, col(xk + d, yk), col) for d in (e, -e)]
                hy = [self.faces.column(xk, yk + d, col(xk, yk + d), col) for d in (e, -e)]
                gx, gy = (hx[0] - hx[1]) / (2 * e), (hy[0] - hy[1]) / (2 * e)
                s = np.array(s, float, copy=True)
                s[k] = s[k] + wk * (1.0 / np.sqrt(1.0 + gx * gx + gy * gy) - s[k])
        return h, s

    def _edited_column(self, x, y, riser=None, wmin=None):
        h, s = self._column(x, y)
        if getattr(self, "edits", None) is not None:
            return self.edits.column(np.asarray(x, float), np.asarray(y, float), h, s, self._column,
                                     getattr(self, "edit_riser", None) if riser is None else riser,
                                     getattr(self, "edit_wmin", 0.0) if wmin is None else wmin)
        return h, s

    def _column(self, x, y):
        if fieldjit.ON:
            x, y = _f64(x), _f64(y)
            return fieldjit.column(self.H, x, y, self.x0, self.y0, self.c)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        e = 0.5
        rr = np.concatenate([r, r, r, r + e, r - e])
        qq = np.concatenate([q, q + e, q - e, q, q])
        v = ndimage.map_coordinates(self.H, [rr, qq], order=3, prefilter=False, mode="nearest").reshape(5, -1)
        gx = (v[1] - v[2]) / (2 * e * self.c)
        gy = (v[3] - v[4]) / (2 * e * self.c)
        return v[0], 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)

    def _relief_cap(self, size):
        """How much of the rock character a passage's walls take: at most ~0.2 of its smaller radius (a 3 m tunnel
        doesn't take 2 m facets)."""
        amp = 1.4 * self.rock["facets"] if self.rock else 1.0
        return np.clip(0.2 * size / max(amp, 1e-6), 0.1, 1.0)

    def grain_at(self, x, y):
        if fieldjit.ON:
            return np.clip(fieldjit.grid_at(self.grain, _f64(x), _f64(y), self.x0, self.y0, self.c), 0, 1)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return np.clip(ndimage.map_coordinates(self.grain, [r, q], order=3, prefilter=False, mode="nearest"), 0, 1)

    def face_dir(self, x, y):
        """The face's horizontal normal at columns, as the smoothed ground's downhill gradient (its length the slope,
        tan): a smooth grid (cubic B-spline), so relief built on it stays continuous."""
        if fieldjit.ON:
            x, y = _f64(x), _f64(y)
            return np.stack([fieldjit.grid_at(a, x, y, self.x0, self.y0, self.c) for a in (self._fdx, self._fdy)], 1)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        v = np.stack([ndimage.map_coordinates(a, [r, q], order=3, prefilter=False, mode="nearest")
                      for a in (self._fdx, self._fdy)], 1)
        return v

    def steep_at(self, x, y):
        if fieldjit.ON:
            return fieldjit.grid_at(self.steep, _f64(x), _f64(y), self.x0, self.y0, self.c)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return ndimage.map_coordinates(self.steep, [r, q], order=3, prefilter=False, mode="nearest")

    def relief_at(self, x, y):
        """The rock relief's weight at columns: Field.steep without thin rock's cut (`thin_cap` bounds it there)."""
        rw = getattr(self, "relief_w", None)
        if rw is None or rw is self.steep:
            return self.steep_at(x, y)
        if fieldjit.ON:
            return fieldjit.grid_at(rw, _f64(x), _f64(y), self.x0, self.y0, self.c)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return ndimage.map_coordinates(rw, [r, q], order=3, prefilter=False, mode="nearest")

    def thin_at(self, p):
        """Thin rock at points: (hw, t): the rock's local half-thickness at the point's height (m; inf off thin rock)
        and how much thin rock's rules apply there (0..1: 0 where the rock is thick)."""
        hw_, t_ = np.full(len(p), np.inf), np.zeros(len(p))
        parts = getattr(self, "thin_parts", None)
        if not parts:
            return hw_, t_
        lab, comps = parts
        iy = np.clip(np.rint((p[:, 1] - self.y0) / self.c).astype(np.int64), 0, lab.shape[0] - 1)
        ix = np.clip(np.rint((p[:, 0] - self.x0) / self.c).astype(np.int64), 0, lab.shape[1] - 1)
        L = lab[iy, ix]
        for li in np.unique(L[L > 0]):
            k = np.flatnonzero(L == li)
            j0, i0, z0, dz, hw, tw = comps[li - 1]
            q = [(p[k, 2] - z0) / dz, (p[k, 1] - self.y0) / self.c - j0, (p[k, 0] - self.x0) / self.c - i0]
            hw_[k] = ndimage.map_coordinates(hw, q, order=1, mode="nearest")
            t_[k] = ndimage.map_coordinates(tw, q, order=1, mode="nearest")
        return hw_, t_

    @staticmethod
    def thin_cap(R, hw, t):
        """Rock relief R (+ carves) on thin rock, bounded by its local half-thickness hw: a soft clamp
        THIN_RELIEF x hw x tanh(R / that), blended in by t (0 where the rock is thick)."""
        k = np.flatnonzero(t > 0)
        if not len(k):
            return R
        out = np.asarray(R, float).copy()
        cap = np.maximum(terrain_mesh.THIN_RELIEF * hw[k], 1e-6)
        out[k] = out[k] + t[k] * (cap * np.tanh(out[k] / cap) - out[k])
        return out

    def fall_at(self, x, y):
        """0..1: the fallen blocks' density at columns (0 where there are none)."""
        if self.fall is None:
            return np.zeros(np.shape(x))
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return np.clip(ndimage.map_coordinates(self.fall, [r, q], order=1, mode="nearest"), 0, 1)

    def ground(self, p):
        h, s = self.column(p[:, 0], p[:, 1])
        return (p[:, 2] - h) * s

    def volumes(self, p, F, near=None, dvoid=None):
        """Each volume combined into F in order; `near` (if given) gets how close each point is to a volume, 0..1
        (rock character applies there); `dvoid` (if given) the distance to the nearest void (a subtract volume)."""
        for vol in self.vols:
            k = np.flatnonzero(np.all((p >= vol.lo) & (p <= vol.hi), axis=1))
            if not len(k):
                continue
            d, above, size = vol.sd(p[k], detail=True)
            if getattr(vol, "clip", None) is not None:  # (what it replaces: the ground within a cylinder over a plinth)
                rc, zc = vol.clip
                F[k] = smax(F[k], np.minimum(rc - np.hypot(p[k, 0] - vol.xy[0], p[k, 1] - vol.xy[1]), p[k, 2] - zc),
                            0.4)
            F[k] = smax(F[k], -d, vol.blend) if vol.op == "subtract" else smin(F[k], d, vol.blend)
            if dvoid is not None and vol.op == "subtract" and getattr(vol, "kind", None) != "arch":
                # (an arch goes through thin rock by design: its fin keeps thin rock's rules)
                dvoid[k] = np.minimum(dvoid[k], d)
            if near is not None:
                # rock relief on walls and roofs, scaled to the passage (a 1 m slot doesn't take 0.8 m facets), and
                # none on floors (a person walks there)
                w = smoothstep(terrain_mesh.NEAR, 0.0, d) * self._relief_cap(size) * smoothstep(0.3, 1.5, above)
                near[k] = np.maximum(near[k], w * vol.relief)
                if getattr(vol, "build", None) is not None and getattr(self, "build_w", None) is not None:
                    # (a volume whose relief may only carve, or build at most `build` m: see Stack)
                    # (1 on and in the stack, whatever share of the relief its size allows: weighted by that share the
                    # cap held only partly and a 0.46 m carve cut the top of an anime stack loose)
                    self.build_w[k] = np.maximum(self.build_w[k], smoothstep(terrain_mesh.NEAR, 0.0, d))
                if self.floor_guard is not None:
                    self.floor_guard[k] = np.minimum(self.floor_guard[k], np.where(np.isinf(above), 1.0,
                                                                                  smoothstep(0.3, 1.5, above)))
        return F

    def solid(self, p, F, s):
        """Volumes and rock character on top of the ground's distance F (s: the column's slope factor, cos slope)."""
        profiling.count("field.solid pts", len(p))
        with _span("field.solid", leaf=True):
            return self._solid(p, F, s)

    def _solid(self, p, F, s):
        near = np.zeros(len(p))
        self.floor_guard = np.ones(len(p))
        self.build_w = np.zeros(len(p)) if any(getattr(v, "build", None) is not None for v in self.vols) else None
        depth = -np.asarray(F, float).copy()  # (how far under the open ground: joints are a surface thing)
        dvoid = np.full(len(p), np.inf) if self.rock is not None else None
        F = self.volumes(p, F, near, dvoid)
        guard, self.floor_guard = self.floor_guard, None
        if self.fall is not None:  # fallen blocks at the faces' feet, unioned with a small fillet
            fz = self.fall_at(p[:, 0], p[:, 1])
            kf = np.flatnonzero((fz > 0) & (F < 3.0) & (F > -2.0))
            if len(kf):
                from . import terrain_blocks
                with _span("field.fallen", leaf=True):
                    # (the ground a block sits on: the column's, less what the rock relief carves there at most:
                    # seated on the column alone a block hung 0.7 m over relief-carved rock)
                    carve = terrain_mesh.FALL_SEAT * self.rock["reach"]
                    sd = terrain_blocks.fallen_sd(
                        p[kf], lambda xy: self.column(xy[:, 0], xy[:, 1])[0]
                        - carve * np.clip(self.relief_at(xy[:, 0], xy[:, 1]), 0, 1),
                        lambda xy: self.fall_at(xy[:, 0], xy[:, 1]), self.rock["blocks"])
                    F[kf] = smin(F[kf], sd, 0.3)  # (a fillet ~a voxel: a razor contact crease made slivers)
        if self.rock is not None:
            # steep ground (45-62 deg) and anything a volume shaped: faceted, jointed, bedded rock (not cave floors)
            rw = self.relief_at(p[:, 0], p[:, 1])
            nv = None
            if dvoid is not None and getattr(self, "thin_parts", None):
                # near a void (a cave or notch; arches go through thin rock by design) the rule stays the old one: the
                # rock between a face and the void behind it is thin whatever the grid says (full relief over a sea
                # cave's mouth cut a piece of its roof free 4 m over the heightmap; capping it by the slab's thickness
                # instead folded cave walls into shards)
                nv = smoothstep(terrain_mesh.THIN_VOID, 0.5 * terrain_mesh.THIN_VOID, dvoid)
                j = np.flatnonzero(nv > 0)
                if len(j):
                    rw = rw.copy()
                    rw[j] += nv[j] * (self.steep_at(p[j, 0], p[j, 1]) - rw[j])
            if dvoid is not None:  # (after thin rock's rule: it moves the weight back toward the face's)
                # a cave deep under a steep face takes the face's relief only near the open ground: deeper than the
                # relief's reach under it, its walls take their own passage-scaled share (`near`) and no more. The
                # face's weight is a column grid: taken at full size round a void 12 m under a 56 deg valley side,
                # its 1.8 m facets built a sheet of rock across crown_tube (pushieworld note 117: width 0, a 1.3 m
                # step), which the walk without rock relief (set_terrain's) never saw
                reach = self.rock["reach"]
                cv_ = smoothstep(terrain_mesh.NEAR, 0.0, dvoid) * (1.0 - smoothstep(2.0 * reach, reach, depth))
                j = np.flatnonzero(cv_ > 0)
                if len(j):
                    rw = rw.copy()
                    rw[j] *= 1.0 - cv_[j]
            if getattr(self, "faces", None) is not None:  # (none on a fall's lip, face and pool under its sheet)
                cm = self.faces.calm(p)
                if cm.any():
                    rw = rw * (1.0 - cm)
            w = np.maximum(rw * guard, near)
            k = np.flatnonzero((w > terrain_mesh.RELIEF_CUT) & (np.abs(F) < self.rock["reach"]))
            if len(k):
                # (the weight eased to 0 AT the cut: taken as it was, the relief stepped in at w = 0.01 as 1% of its
                # full size, a 2-3 cm step in the field along the weight's 0.01 contour, metres out on the grass round
                # every rock face; the maps' normals drew it as thin dark dashed cracks: pushieworld note 104)
                w = w.copy()
                w[k] = w[k] * smoothstep(terrain_mesh.RELIEF_CUT, terrain_mesh.RELIEF_FADE, w[k])
                g = self.grain_at(p[k, 0], p[k, 1]) if self.grain is not None else None
                fd = self.face_dir(p[k, 0], p[k, 1])
                a_ = rw[k] * guard[k]
                u = near[k] / np.maximum(a_ + near[k], 1e-9)  # (the volumes' share of the relief)
                profiling.count("field.rock pts", len(k))
                blk = I = None
                if self.rock.get("blocks") and self.micro is not None:
                    # (the maps' fine relief needs the rock structure's ids at the same points: computed together)
                    from . import terrain_blocks
                    with _span("field.blocks", leaf=True):
                        zoff = self.rock["bed_offset"](p[k, :2]) if self.rock.get("bed_offset") else 0.0
                        blk, I = terrain_blocks.structure(p[k], self.rock["blocks"], fd, zoff, want_ids=True,
                                                          sharp=getattr(self.micro, "sharp", None))
                        if "sharp" in I:  # (the maps' share of the blocks weighted as rock_relief weights them)
                            I["sharp"] = I["sharp"] * smoothstep(4.0, 1.5, depth[k]) * (1.0 - u) ** 3
                hw, tw = self.thin_at(p[k]) if terrain_mesh.THIN_RELIEF > 0 else (None, None)
                if nv is not None and tw is not None:  # (none of thin rock's rules near a void: see above)
                    tw = tw * (1.0 - nv[k])
                ts = tw
                jw = smoothstep(4.0, 1.5, depth[k])
                with _span("field.rock_relief", leaf=True):
                    if not self.styles:
                        R = w[k] * rock_relief(p[k], self.rock, g, jw, fd, u, blk, thin=ts)
                        mic = None
                    else:
                        R, mic = self._styled_relief(p[k], g, jw, fd, u, blk, ts)
                        R = w[k] * R
                    if self.build_w is not None:
                        # rock relief on a stack builds at most STACK_BUILD m and carves at most STACK_CARVE: built out over its notch it
                        # stood a lip of rock in the air (tl2_island stack2, a 30-triangle piece floating 0.75 m over
                        # the heightmap); blended by the stack's relief weight, so the field stays continuous
                        bw = self.build_w[k]
                        R = R + bw * (np.clip(R, -terrain_mesh.STACK_BUILD, terrain_mesh.STACK_CARVE) - R)
                    F[k] = F[k] + (R if tw is None else self.thin_cap(R, hw, tw))
                if self.micro is not None:  # (bake-only fine rock: below the meshing voxel, for the maps)
                    with _span("field.micro", leaf=True):
                        F[k] = F[k] + w[k] * (1.0 if mic is None else mic) * self.micro(p[k], fd, u, g, I)
        if getattr(self, "faces", None) is not None:  # (each fall's sheet falls through air: terrain_falls.Faces)
            F = self.faces.carve(p, F)
        # (per call: left on the Field, the incremental fingerprint walked it as a global input that changed every export)
        self.build_w = None
        return F

    def style_w(self, x, y):
        """Per rock-shaping style its weight at columns (cubic B-spline on the grid, as steep_at), and realistic's."""
        ws = []
        for s in self.styles:
            if fieldjit.ON:
                a = fieldjit.grid_at(s["w"], _f64(x), _f64(y), self.x0, self.y0, self.c)
            else:
                a = ndimage.map_coordinates(s["w"], [(np.asarray(y, float) - self.y0) / self.c,
                                                     (np.asarray(x, float) - self.x0) / self.c],
                                            order=3, prefilter=False, mode="nearest")
            ws.append(np.clip(a, 0, 1))
        real = np.clip(1.0 - np.sum(ws, axis=0), 0, 1) if ws else np.ones(np.shape(x))
        return ws, real

    def _styled_relief(self, p, g, jw, fd, u, blk, ts):
        """The rock relief where terrain styles shape the rock: realistic's where it weighs, each style's own (its
        `relief` multipliers on the realistic numbers, `pillow` grooves) where it does, mixed by their weights (smooth
        on the grid: continuous across zones and tiles). Also each point's share of the bake-only micro relief."""
        from . import terrain_style_zones
        ws, wr = self.style_w(p[:, 0], p[:, 1])
        R = np.zeros(len(p))
        mic = wr.copy()
        sub = lambda a, i: None if a is None else (a[i] if np.ndim(a) else a)

        def rel(i, rock):
            return rock_relief(p[i], rock, sub(g, i), sub(jw, i), sub(fd, i), sub(u, i),
                               sub(blk, i) if rock.get("blocks") is not None else None, thin=sub(ts, i))
        i = np.flatnonzero(wr > 1e-4)
        if len(i):
            R[i] += wr[i] * rel(i, self.rock)
        for s, a in zip(self.styles, ws):
            i = np.flatnonzero(a > 1e-4)
            if not len(i):
                continue
            Rk = s["rock"]
            rs = np.zeros(len(i))
            rv = terrain_style_zones.rock_variant(self.rock, Rk.get("relief"))
            if rv.get("facets", 0) > 0 or rv.get("bedding", 0) > 0 or rv.get("blocks"):
                rs += rel(i, rv)
            pl = Rk.get("pillow")
            if pl:
                rs += terrain_style_zones.pillow_carve(p[i], pl.get("size", 3.0), pl.get("depth", 0.8),
                                                 pl.get("round", 0.4), int(self.rock.get("seed", 0)) + 101,
                                                 pl.get("stretch", 1.0))
            if Rk.get("build") is not None:
                # (the most this style's relief may build out from the rock, m: cartoon's big facets built a slab out
                # over a sheer lip with a groove carved under it, a piece floating clear of the face: tl2_slice_a
                # [291, 104, 23]; carving is not capped)
                rs = np.maximum(rs, -float(Rk["build"]))
            R[i] += a[i] * rs
            mic[i] += a[i] * float(Rk.get("micro", 1.0))
        return R, mic

    def value(self, p, metric=False):
        p = np.asarray(p, float)
        h, s = self.column(p[:, 0], p[:, 1], metric) if metric else self.column(p[:, 0], p[:, 1])
        return self.solid(p, (p[:, 2] - h) * s, s)

    def value_gradient(self, p, h):
        tet = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
        f = self.value((p[:, None, :] + h * tet[None]).reshape(-1, 3)).reshape(-1, 4)
        return f.mean(1), (f @ tet) / (4 * h)


def _lattice_values(field, P, v):
    """Field values at lattice points, kept at least 1e-3 voxel from zero so every crossing lies strictly inside
    its lattice edge (both neighbours then agree which edges are crossed)."""
    F = field.value(P)
    eps = 1e-3 * v
    return np.where(np.abs(F) < eps, np.where(F < 0, -eps, eps), F)


def project(field, P, v, fixed=None, iterations=4):
    """Newton steps onto the zero set (capped at half a voxel), then unit normals from the field's gradient.
    `fixed`: (n, 3) bool, axes a vertex may not move along (border planes)."""
    with _span("project"):
        return _project(field, P, v, fixed, iterations)


def _project(field, P, v, fixed=None, iterations=4):
    P = P.astype(np.float64).copy()
    h = v / 8
    todo = np.arange(len(P))
    for _ in range(iterations):
        if not len(todo):
            break
        f, g = field.value_gradient(P[todo], h)
        if fixed is not None:
            g = np.where(fixed[todo], 0.0, g)
        step = (f / np.maximum((g * g).sum(1), 1e-12))[:, None] * g
        n = np.linalg.norm(step, axis=1, keepdims=True)
        step *= np.minimum(1.0, 0.5 * v / np.maximum(n, 1e-12))
        ok = np.isfinite(step).all(1)
        P[todo[ok]] -= step[ok]
        todo = todo[ok & (n[:, 0] > 1e-4 * v)]
    _, g = field.value_gradient(P, terrain_mesh.NORMAL_H * v)
    # (where the field is flat at the scale of the normal's stencil (the cliff shell's back deep under a lip, where
    # front and back are capped constants), the gradient is zero: a zero normal in the GLB (invalid glTF), and the
    # seam check read the two tiles' identical zero normals as "differ by 90 deg". Wider stencils, then up)
    for wide in (1.0, 4.0):
        flat = np.linalg.norm(g, axis=1) < 1e-6
        if not flat.any():
            break
        g[flat] = field.value_gradient(P[flat], wide * v)[1]
    flat = np.linalg.norm(g, axis=1) < 1e-6
    g[flat] = (0.0, 0.0, 1.0)
    N = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    return P, N
