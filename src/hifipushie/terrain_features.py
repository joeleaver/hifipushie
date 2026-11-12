"""Terrain's basins, hills, ribs and divides (a mixin of Terrain). Part of terrain (terrain.py has the overview; the class is terrain_model.Terrain)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import terrain
from .terrain import _from_top, compass, smoothstep

class _TerrainFeatures:
    """What Terrain's base is solved from besides ridges and rivers: basin walls and floors, lone hills, ribs,
    divides, and an address resolved before any ground exists."""

    def _wall_profile(self, b):
        """Height fraction s(t) across a basin wall, t from the floor's edge (0) to the crest (1): a concave scree foot,
        one cliff band at `band_at` (its height `band`, at min_slope + 14 deg), steady slopes above easing to the crest.
        Built as slope weights (the band's weight is its steepness), so the whole face averages its intended slope."""
        n = 512
        t = np.linspace(0, 1, n)
        if b.get("from_top"):  # the designer's profile: bands from the crest down, each at its own slope
            bands = b["from_top"][::-1]  # floor edge first
            run = np.array([sh / math.tan(math.radians(sl)) for _, sh, sl in bands])
            edges = np.r_[0, np.cumsum(run / run.sum())]
            wgt = np.zeros(n)
            b["_zones_t"] = {}
            for (kind, sh, sl), t0, t1 in zip(bands, edges[:-1], edges[1:]):
                m = (t >= t0) & (t < t1 + (1e-9 if t1 >= 1 else 0))
                u = np.clip((t - t0) / max(t1 - t0, 1e-9), 0, 1)
                g = math.tan(math.radians(sl))
                if kind == "scree":  # concave: steepest at its top, easing out at its toe
                    g = g * (0.75 + 0.5 * u)
                wgt = np.where(m, g, wgt)
                b["_zones_t"][kind] = (float(t0), float(t1))
            cl = b["_zones_t"].get("cliffs")
            b["_bands"], b["_ft"] = ([cl[0]], cl[1] - cl[0]) if cl else ([], 0.0)
            s = np.r_[0, np.cumsum((wgt[1:] + wgt[:-1]) / 2)]
            return s / s[-1]
        rest = math.tan(math.radians(b["avg"]))
        wgt = rest * (0.45 + 0.75 * smoothstep(0.0, 0.3, t) - 0.35 * smoothstep(0.75, 1.0, t))
        steep = math.tan(math.radians(min(b["min_slope"] + 14, 80)))  # margin: erosion and the grid soften it
        # each band is `band` tall plus the grid's rounding at its lip and foot (the check measures the tallest steep
        # stretch: tiered bands sharing the height made "unclimbable" walls of 17 m steps)
        tall = b["band"] + 0.6 * self.cell * steep
        width = max(b["relief"] / math.tan(math.radians(b["avg"])), 1e-6)
        ft = min(0.4, (tall / steep) / width)  # one band's share of the width
        n_bands = b["bands"] or (3 if b["character"] == "tiered" else 1)
        ats = [b["band_at"]] if n_bands == 1 else list(np.linspace(0.2, 0.75, n_bands))
        if n_bands * ft > 0.6:  # no room for them all at full height: shorter bands (the wall check will say so)
            ft = 0.6 / n_bands
        for at in ats:
            wgt = np.where((t >= at) & (t < at + ft), steep, wgt)
        b["_ft"], b["_bands"] = ft, ats
        s = np.r_[0, np.cumsum((wgt[1:] + wgt[:-1]) / 2)]
        return s / s[-1]

    def _hills(self, H):
        """Lone peaks as domes on the ground beneath: a rounded top of `radius`, flanks falling at about `flanks`
        degrees (default 18) to the surrounding ground. Their footprint is protected from basin floors and such."""
        lift = np.zeros(H.shape)
        for n in self._lone:
            xy, h = self.points[n]
            p = (self.spec.get("peaks") or {}).get(n) or (self.spec.get("cols") or {}).get(n) or {}
            d = np.hypot(self.X - xy[0], self.Y - xy[1])
            under = self.height(xy, H)
            rise = h - under
            if rise <= 0:
                self.warnings.append(f"hill {n!r} ({h:.0f} m) is below the ground there ({under:.0f} m): it adds nothing")
                continue
            top = float(p.get("radius", max(0.02 * self.size, 1.5 * self.cell)))
            foot = top + rise / math.tan(math.radians(p.get("flanks", 18)))
            if p.get("base_radius"):  # its footprint, given directly: the flanks follow
                foot = max(float(p["base_radius"]), top + self.cell)
            u = np.clip((d - top) / (foot - top), 0, 1)
            # overlapping hills meet in a saddle, never stack: the higher dome wins (summed, a hill on a neighbour's flank
            # stood 6 m over its asked height)
            lift = np.maximum(lift, rise * 0.5 * (1 + np.cos(np.pi * u)) * (d < foot))
        return H + lift

    def _early_xy(self, ref):
        """An address resolved before any ground exists (for the skeleton): points, lines, landform centres."""
        if isinstance(ref, (list, tuple)):
            return np.array(ref[:2], float)
        if ref in self.points:
            return self.points[ref][0]
        if isinstance(ref, str) and ref.startswith("edge:"):  # (a basin's falls_to on the frame's edge was an error)
            side, _, f = ref[5:].partition("@")
            f = float(f) if f else 0.5
            (x0, y0), (x1, y1) = self.spec["extent"]
            m = 2 * self.cell
            return np.array({"w": (x0 + m, y0 + f * (y1 - y0)), "e": (x1 - m, y0 + f * (y1 - y0)),
                             "s": (x0 + f * (x1 - x0), y0 + m), "n": (x0 + f * (x1 - x0), y1 - m)}[side[0]], float)
        lfs = self.spec.get("landforms") or {}
        if ref in lfs:
            return self._early_xy(lfs[ref].get("at") or lfs[ref].get("across"))
        if "@" in ref:
            name, s = ref.split("@")
            return self.lines[name].at(float(s))[0]
        if "." in ref:
            name, end = ref.rsplit(".", 1)
            return self.lines[name].at(0.0 if end == "source" else 1.0)[0]
        if ref in self.zones or ref.startswith("quadrant:"):
            from . import terrain_design as design
            try:
                return design.centroid(self, design.region(self, ref))
            except (AttributeError, ValueError):  # a zone defined by the ground (above/below/slope) isn't there yet
                pass
        raise ValueError(f"can't place {ref!r} before the ground exists: use a compass direction (\"north\"), a peak, "
                         f"col, landform, line, a zone drawn on the map, or [x, y]")

    def _basin(self, name, b):
        """A valley floor inside a closed ridge: a bowl from `floor` [low, high] that drains to `falls_to`, and between
        the floor's edge and the crest a wall as wide as its steepness allows (the wall is the mountainside itself)."""
        from skimage.draw import polygon
        L = self.lines.get(b["inside"])
        if L is None:
            raise ValueError(f"basin {name!r}: 'inside' must name a ridge: a closed ring, or a horseshoe with \"opens\"")
        ring = L.xy
        if not L.props.get("closed"):
            # a valley open to one side: a horseshoe ridge, the open side running out of the frame (the floor carries on
            # to the edge there: no wall, the valley's mouth)
            op = b.get("opens")
            ends = L.xy[[0, -1]]
            if op is None:  # the way between the horseshoe's ends, away from the ridge
                mid = ends.mean(0)
                v = mid - L.xy.mean(0)
                op = v / (np.linalg.norm(v) + 1e-9)
            cd = compass(op) if isinstance(op, str) else np.asarray(op, float)
            if cd is None and isinstance(op, str) and op.startswith("edge:"):
                cd = compass(op[5:6])
            if cd is None:
                raise ValueError(f"basin {name!r}: \"opens\" is a compass side (\"south\") or \"edge:s\"; its ridge "
                                 f"{b['inside']!r} doesn't close, so the valley needs a side to open to")
            cd = cd / (np.linalg.norm(cd) + 1e-12)
            far = 3 * self.size * cd
            ring = np.vstack([ends[0] + far, L.xy, ends[1] + far])
            # the mouth: past the nearer end the walls stop (a wall check ran down the rays from the ends and failed there)
            mouth = (cd, float((ends @ cd).min()))
        else:
            mouth = None
        inside = np.zeros(self.X.shape, bool)
        rr, cc = polygon((ring[:, 1] - self.ys[0]) / self.cell, (ring[:, 0] - self.xs[0]) / self.cell, self.X.shape)
        inside[rr, cc] = True
        lo, hi = b.get("floor", [None, None])
        crest_min = float(np.percentile(L.h, 5))  # passes will notch lower; they're exempt
        w = b.get("walls", {})
        # a real mountainside averages 25-40 deg: a scree foot, cliff band(s), easier upper slopes. "Unclimbable" needs
        # only one band steep and tall enough, not the whole face (that read as a draped curtain)
        slope = float(w.get("min_slope", 45))
        avg = float(w.get("average", 32))
        if avg > slope + 8:  # the cliff band (min_slope + 14) must stay steeper than the face around it
            asked = "average" in (((self.source.get("basins") or {}).get(name) or {}).get("walls") or {})
            self.warnings.append(f"basin {name!r}: " + ("walls.average" if asked else "the kind's face slope")
                                 + f" {avg:.0f} deg is steeper than its cliff band allows (min_slope {slope:.0f} + 8): "
                                 f"built at {slope + 8:.0f}; raise min_slope for steeper walls")
            avg = slope + 8
        from_top = _from_top(w.get("from_top"), slope, name)
        if from_top:  # the wall's width follows from its bands: each share of the height at its own slope
            avg = math.degrees(math.atan(1 / sum(sh / math.tan(math.radians(sl)) for _, sh, sl in from_top)))
        # each stretch of wall is as wide as the crest behind it needs at that slope (a big peak has a big footprint;
        # one width from the lowest crest made the high stretches 58 deg)
        dist, near = cKDTree(L.xy).query(self.P)
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(L.xy, axis=0), axis=1))][near].reshape(self.X.shape)
        crest_here = ndimage.gaussian_filter(L.h[near].reshape(self.X.shape), 150 * self.k / self.cell)
        need = np.maximum(3 * self.cell, (crest_here - hi) / math.tan(math.radians(avg)))
        if "width" in w:
            need = np.full(self.X.shape, float(w["width"]))
        F = inside & (dist.reshape(self.X.shape) >= need)
        F = ndimage.binary_opening(F, iterations=2)
        if "width" not in w and F.any() and lo is not None and hi is not None and hi > lo:
            # the face starts at the floor's edge, which is lower than `hi` where the floor is low (by the drain, or on
            # the low side of a tilted floor): size those stretches for their real relief (sized from `hi`, a wall
            # asked at 45 deg came out 54)
            fl0 = self._floor_heights(b, F, lo, hi, name)
            _, (fy, fx_) = ndimage.distance_transform_edt(~F, return_indices=True)
            edge_h = fl0[fy, fx_]
            need = np.maximum(3 * self.cell, (crest_here - edge_h) / math.tan(math.radians(avg)))
            F = inside & (dist.reshape(self.X.shape) >= need)
            F = ndimage.binary_opening(F, iterations=2)
        width = float(np.median(need[inside & ~F])) if (inside & ~F).any() else float(need.mean())
        if not F.any():
            raise ValueError(f"basin {name!r}: walls {width:.0f} m wide leave no floor; lower the floor's high end "
                             f"or the crest, or widen the ring")
        fl, fx, sink = self._floor_heights(b, F, lo, hi, name, full=True)
        self._fixed_river |= sink  # water ends here: base level for erosion
        wall = inside & ~F
        band = float(w.get("height", max(30.0, 0.08 * (crest_min - hi))))  # the cliff band's height
        if from_top and "height" not in w:  # the cliffs' share of the wall (the check measures it)
            band = sum(sh for k, sh, _ in from_top if k == "cliffs") * max(float(np.median(L.h)) - hi, 1.0) * 0.8
        self.basins[name] = {"floor": F, "wall": wall, "inside": inside, "width": width, "lo": lo, "hi": hi,
                             "min_slope": slope, "falls": fx.tolist(), "band": band, "avg": avg,
                             "relief": float(np.median(L.h)) - hi, "band_at": float(w.get("band_at", 0.3)),
                             "arc": arc, "character": w.get("character", "tiered"), "bands": int(w.get("bands", 0)),
                             "mouth": mouth, "from_top": from_top, "d_crest": dist.reshape(self.X.shape),
                             "crest_here": ndimage.gaussian_filter(L.h[near].reshape(self.X.shape), 2.0)}
        return F, fl, terrain.PROFILES.get(w.get("profile", "straight"), 1.0)

    def _floor_heights(self, b, F, lo, hi, name, full=False):
        """A basin floor's heights over the grid (meaningful on F): from `lo` at the drain to `hi` at the floor's edge."""
        fx = self._early_xy(b["falls_to"]) if b.get("falls_to") else np.array(
            [self.X[F].mean(), self.Y[F].mean()])
        lfs = self.spec.get("landforms") or {}
        r = 0.5 * lfs[b["falls_to"]]["radius"] if isinstance(b.get("falls_to"), str) and b["falls_to"] in lfs else 60.0 * self.k
        sink = (np.hypot(self.X - fx[0], self.Y - fx[1]) < r) & F
        if not sink.any():
            fy, fxx = np.nonzero(F)
            c = [float(self.xs[fxx].mean()), float(self.ys[fy].mean())]
            dmin = float(np.hypot(self.X[F] - fx[0], self.Y[F] - fx[1]).min())
            raise ValueError(f"basin {name!r}: falls_to {b.get('falls_to')!r} at [{fx[0]:.0f}, {fx[1]:.0f}] isn't on the "
                             f"basin floor: the walls take the ground there. The floor spans x {self.xs[fxx].min():.0f}-"
                             f"{self.xs[fxx].max():.0f}, y {self.ys[fy].min():.0f}-{self.ys[fy].max():.0f} (centre "
                             f"[{c[0]:.0f}, {c[1]:.0f}]), {dmin:.0f} m from it: move it onto the floor, or lower the floor's "
                             f"high end / the crest so the walls take less room")
        # the floor ramps by relative distance, drain -> edge (harmonic from a small drain is logarithmic: a flat
        # plateau with the drain sunk in a funnel)
        d_sink = ndimage.distance_transform_edt(~sink) * self.cell
        d_edge = ndimage.distance_transform_edt(F) * self.cell
        u = ndimage.gaussian_filter(d_sink / np.maximum(d_sink + d_edge, 1e-6), 3)
        if b.get("rises_toward"):  # the floor tilts: mostly along the drain -> this address, a little toward every edge
            rt = b["rises_toward"]
            cd = compass(rt)
            if cd is not None:  # a direction: rising across the whole floor that way
                proj = (self.P - fx) @ cd
                ax = cd * max(float(proj[F.ravel()].max()), self.cell)
            else:
                ax = self._early_xy(rt) - fx
            along = np.clip(((self.P - fx) @ ax) / (ax @ ax), 0, 1).reshape(self.X.shape)
            u = 0.75 * along + 0.25 * u
        p = {"bowl": 1.0, "flat": 2.5, "open": 0.7}[b.get("shape", "bowl")]  # flat: level, tipping up at the edge
        fl = lo + (hi - lo) * np.clip(u, 0, 1) ** p
        return (fl, fx, sink) if full else fl

    def _ribs(self, high_fix, low_fix):
        """Spurs running down from every ridge at irregular spacing: they break long mountain walls into
        spur-and-gully, which harmonic slopes (smooth between crest and floor) never have. Each rib is traced
        downhill on the first solution and stands a little proud of it, fading out toward the valley."""
        cfg = self.spec.get("ribs") if isinstance(self.spec.get("ribs"), dict) else {}
        every, proud = cfg.get("every", 320.0 * self.k), cfg.get("proud", 0.07)
        s = self.t ** self.prof
        H = self.floor + np.maximum(self.crest - self.floor, 0) * s
        gy, gx = np.gradient(H, self.cell)
        rng = np.random.default_rng(5)
        m, hv = np.zeros(self.X.shape, bool), np.zeros(self.X.shape)
        count = 0
        for L in self.lines.values():
            if L.kind != "ridge":
                continue
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(L.xy, axis=0), axis=1))]
            pos = every * rng.uniform(0.3, 1.0)
            while pos < d[-1] - every * 0.3:
                i = int(np.searchsorted(d, pos))
                tan = L.xy[min(i + 1, len(L.xy) - 1)] - L.xy[max(i - 1, 0)]
                tan /= np.linalg.norm(tan) + 1e-12
                for side in (1, -1):
                    p = L.xy[i] + side * np.array([-tan[1], tan[0]]) * 3 * self.cell
                    path = [L.xy[i]]
                    for _ in range(int(900 * self.k / self.cell)):
                        iy, ix = int(round((p[1] - self.ys[0]) / self.cell)), int(round((p[0] - self.xs[0]) / self.cell))
                        if not (0 < iy < len(self.ys) - 1 and 0 < ix < len(self.xs) - 1) or low_fix[iy, ix] or self.t[iy, ix] < 0.35:
                            break
                        g = np.array([gx[iy, ix], gy[iy, ix]])
                        if np.linalg.norm(g) < 0.05:
                            break
                        path.append(p.copy())
                        p = p - g / np.linalg.norm(g) * self.cell
                    if len(path) < 8:
                        continue
                    path = np.array(path)
                    hs = self.sample(path, H)
                    relief = hs[0] - hs[-1]
                    u = np.linspace(0, 1, len(path))
                    hs = hs + proud * relief * np.sin(np.pi * np.clip(u * 1.3, 0, 1)) ** 0.7 * (1 - u)
                    ij = np.round((path[:, ::-1] - [self.ys[0], self.xs[0]]) / self.cell).astype(int)
                    ij = np.clip(ij, 0, [len(self.ys) - 1, len(self.xs) - 1])  # (a ridge wandering past the frame)
                    ok = ~high_fix[ij[:, 0], ij[:, 1]]
                    ok[:3] = False  # leave the crest itself to the ridge
                    m[ij[ok, 0], ij[ok, 1]] = True
                    hv[ij[ok, 0], ij[ok, 1]] = hs[ok]
                    count += 1
                pos += every * rng.uniform(0.6, 1.4)
        self.rib_count = count
        return (m, hv) if count else None

    def _divides(self, rivers, river_id, high_fix):
        """Crests along the medial line between neighbouring rivers that no authored ridge separates."""
        dist, (iy, ix) = ndimage.distance_transform_edt(river_id == 0, return_indices=True)
        dist *= self.cell
        label = river_id[iy, ix]
        bnd = np.zeros(label.shape, bool)
        bnd[:, 1:] |= label[:, 1:] != label[:, :-1]
        bnd[1:, :] |= label[1:, :] != label[:-1, :]
        near_ridge = ndimage.distance_transform_edt(~high_fix) * self.cell < 3 * self.cell
        cand = bnd & (self.t < 0.5) & ~near_ridge & (dist > 2 * self.cell)
        cand[[0, -1], :] = cand[:, [0, -1]] = False
        if not cand.any():
            return None
        side = np.array([0.0] + [L.props["side"] for L in rivers])[label]
        side = ndimage.minimum_filter(side, 3)
        cap = self.crest.max()
        h = np.minimum(self.floor + dist * side, np.where(self.crest > self.floor + 20 * self.k, self.crest, cap))
        pairs = {}
        la, lb = label, ndimage.maximum_filter(label, 3)
        for a, b, hh in zip(la[cand], lb[cand], h[cand]):
            key = tuple(sorted((rivers[a - 1].name, rivers[max(b, 1) - 1].name)))
            if key[0] != key[1]:
                pairs.setdefault(key, []).append(hh)
        self.divides = [(k, len(v) * self.cell, max(v)) for k, v in pairs.items()]
        self._divide_mask = cand
        return cand, h
