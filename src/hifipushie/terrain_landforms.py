"""Terrain's landforms: lakes, dams, fans, moraines, terraces (a mixin of Terrain). Part of terrain (terrain.py has the overview; the class is terrain_model.Terrain)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import noise
from .terrain import _area, compass, smoothstep

class _TerrainLandforms:
    """Terrain's landforms: lakes and their dams and banks, fans, moraines, terraces, filling the lakes."""

    # ------------------------------------------------ landforms
    def _smooth(self, a, r):
        return ndimage.gaussian_filter(a.astype(float), r / self.cell)

    def _landforms(self):
        lfs = self.spec.get("landforms") or {}
        prints = {}
        for name, lf in lfs.items():
            if lf.get("type") not in ("lake", "fan", "moraine", "terrace"):
                raise ValueError(f"landform {name!r}: needs \"type\": \"lake\" | \"fan\" | \"moraine\" | \"terrace\" "
                                 f"(got {lf.get('type')!r})")
            before = self.H.copy()
            getattr(self, "_lf_" + lf["type"])(name, lf)
            prints[name] = np.abs(self.H - before) > 0.5
        names = list(prints)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                both = (prints[a] & prints[b]).sum()
                if both > 0.1 * min(prints[a].sum(), prints[b].sum()) and both > 0:
                    self.warnings.append(f"landform {b!r} overlaps {a!r} ({both * self.cell ** 2 / 1e4:.1f} ha): "
                                         f"{b!r} is applied later and wins where they meet")
        self._prints = prints

    def _lf_lake(self, name, lf):
        """A basin carved to below a level, with a rim (rock bar or dam) up to the level where the ground is lower."""
        xy, _, _ = self.address(lf["at"])
        r = float(lf["radius"])
        # a lobed shoreline, not a circle: distance warped by noise that is smooth in space (warping by bearing
        # alone made radial star points)
        true_d = np.hypot(self.X - xy[0], self.Y - xy[1])
        lobe = noise.fbm(np.c_[self.P, np.full(len(self.P), 7.0)], 0.9 * r, 2, seed=int(xy[0] + xy[1]) % 1000)
        d = true_d + lf.get("lobes", 0.3) * r * 2 * (lobe.reshape(self.X.shape) - 0.5)
        drains = [b for b in self.basins.values() if np.allclose(b["falls"], xy)]
        level = float(lf["level"]) if "level" in lf else (drains[0]["lo"] if drains else self.height(xy))
        depth = float(lf.get("depth", 10))
        natural = isinstance(lf.get("dam"), str) and lf["dam"].replace("_", " ").replace("-", " ") in (
            "moraine", "rock bar", "rockbar", "bar", "rock")
        if natural and "level" not in lf:  # held partway down the valley: the dam's crest a little over the floor at
            # its site (the lake's downstream end), so the lake runs back up the valley from it
            tan0, _ = self._downstream(lf, xy, r, self.H)
            level = self.height(xy + tan0 * 0.95 * r) + max(0.6 * depth, 4.0)
        target = np.where(d < r, level - depth * np.clip(1 - (d / r) ** 2, 0, 1) ** 1.5 - 0.3,
                          level - 0.3 + 0.35 * (d - r))  # shore banks at ~19 deg rather than a step
        reach = smoothstep(1.6 * r, 1.1 * r, true_d)  # the bank only reshapes the shore, not the hills around it
        before = self.H
        self.H = self.H * (1 - reach) + np.minimum(self.H, self._smooth(target, 10 * self.k)) * reach
        dug = (before - self.H > 20) & (before > level + 20) & (d < r)
        if dug.sum() * self.cell ** 2 > 0.05 * math.pi * r * r:  # a lake is a dug-out disk: say when that ate land
            self.warnings.append(f"lake {name!r}: its disk ({r:.0f} m radius) dug out {_area(dug.sum() * self.cell ** 2)} "
                                 f"of ground standing over 20 m above its level (up to {float((before - self.H).max()):.0f} m "
                                 f"deep): a lake is a basin dug to its level everywhere inside its radius. Make it smaller "
                                 f"or move it off the high ground (for water around land use 'sea')")
        dam = lf.get("dam", True)
        if natural:
            self._natural_dam(name, lf, xy, r, level, before, "moraine" if dam == "moraine" else "rock bar")
            dam = False
        if dam:
            # an embankment wherever the ground (before digging) was below the crest: its inner face rises from the
            # water's edge, a level top, an outer face at 1:2.5 down to the ground. On a slope that is a bank across the
            # downhill side only ("downhill": a farm pond); uphill the dug bank is the shore. (A ring raised on the dug
            # ground left an uphill rim; a separate berm below the pond left a trough and spilled at its ends)
            crest = level + float(lf.get("freeboard", 1.0 if dam == "downhill" else 1.5))
            # (a crest at least 3 cells wide: at 1.6 cells the later smoothing left one cell with 0.8 m of freeboard)
            top = float(lf.get("crest_width", max(3.0, 0.1 * r, 3 * self.cell)))
            rise = crest - (level - 0.3)
            d_in = r + 2.0 * rise
            # (the lake's side runs on down at 1:2 under the water to the ground: starting at the water's edge, on a
            # slope the bank stood as a wall as tall as the fall across the lake, 12 m at 60 deg on the island's pond,
            # which the tile export took for a cliff)
            bank = np.where(d < r, level - 0.3 - (r - d) / 2.0,
                            np.where(d < d_in, level - 0.3 + (d - r) / 2.0,
                                     np.where(d < d_in + top, crest, crest - (d - d_in - top) / 2.5)))
            low = self._smooth(before, 2 * self.cell) < crest
            fill = np.where(low & (true_d < 3 * r), np.minimum(bank, crest), -np.inf)
            self.dams[name] = fill > self.H + 0.05
            self.H = np.maximum(self.H, fill)
        # dam false: a natural lake, holding only what the ground holds (the report says if it leaks)
        self.lakes[name] = {"xy": xy.tolist(), "level": level, "r": r, "id": len(self.lakes) + 1,
                            "reach": 8.0 if lf.get("_dam") else 2.5}  # (a dammed valley lake runs far up the valley)
        lf["_centre"] = xy.tolist()

    def _downstream(self, lf, xy, r, H):
        """Which way a lake's valley runs down: a river through the lake, "toward", or down the ground smoothed at the
        lake's size. Returns (unit vector, the river or None)."""
        tan = None
        if lf.get("toward"):
            cd = compass(lf["toward"])
            tan = cd if cd is not None else self.address(lf["toward"])[0] - xy
        riv = None
        for L in self.lines.values():
            if L.kind == "river":
                dd = np.hypot(*(L.xy - xy).T)
                if dd.min() < 1.5 * r:
                    riv = L
                    if tan is None:
                        i = int(np.argmin(dd))
                        tan = L.xy[min(i + 3, len(L.xy) - 1)] - L.xy[max(i - 3, 0)]
                    break
        if tan is None:
            g = np.gradient(self._smooth(H, r), self.cell)
            iy, ix = int(round((xy[1] - self.ys[0]) / self.cell)), int(round((xy[0] - self.xs[0]) / self.cell))
            iy, ix = int(np.clip(iy, 0, len(self.ys) - 1)), int(np.clip(ix, 0, len(self.xs) - 1))
            tan = -np.array([g[1][iy, ix], g[0][iy, ix]])
        return np.asarray(tan, float) / (np.linalg.norm(tan) + 1e-9), riv

    def _natural_dam(self, name, lf, xy, r, level, before, kind):
        """A lake held partway down a sloping valley floor by what a glacier left across it: a moraine (a rounded ridge of
        till bowed downstream, hummocky) or a rock bar (a rock step, gentle on the lake side, a steep face below). It
        runs right across the valley at the lake's downstream end (it only rises where the ground is lower than its
        crest, so it ends against the valley sides by itself), with a spillway notch at the lake's level where the water
        leaves (the river, or the lowest point of the crest line). The floor beyond it carries on down."""
        tan, riv = self._downstream(lf, xy, r, before)
        nrm = np.array([-tan[1], tan[0]])
        v = np.stack([self.X - xy[0], self.Y - xy[1]], -1)
        u, s = v @ tan, v @ nrm
        fb = float(lf.get("freeboard", 2.0 if kind == "moraine" else 3.0))
        crest = level + fb
        Wd = float(lf.get("dam_width", max(0.45 * r if kind == "moraine" else 0.3 * r, 4 * self.cell)))
        u_d = 0.95 * r + 0.5 * Wd - 0.12 * s ** 2 / max(r, 1.0)  # its crest line, bowed downstream
        x = u - u_d  # across the dam: - upstream (lake side), + downstream
        wob = noise.fbm(np.c_[self.P, np.full(len(self.P), 91.0)], max(0.3 * Wd, 3 * self.cell), 2,
                        seed=int(xy[0] * 7 + xy[1]) % 997).reshape(self.X.shape)
        # upstream the lake's own bank from its bed up to the crest; downstream a face falling to the valley floor at a
        # moraine's (22 deg) or a rock step's (58 deg) slope, wherever that floor is (a profile that ended at the lake's
        # level left a 300 m plateau at lake level ending in a 50 m scarp)
        if kind == "moraine":  # rounded, its crest hummocky
            up = np.clip(1 + x / Wd, 0, 1)
            top = crest + 0.35 * fb * (wob - 0.5)
            z = np.where(x < 0, level - 1.0 + (top - level + 1.0) * np.sin(0.5 * np.pi * up) ** 1.3,
                         top - 0.25 * fb * np.clip(x / (0.3 * Wd), 0, 1) ** 2
                         - np.tan(math.radians(22)) * np.maximum(x - 0.3 * Wd, 0))
            z = np.where(x < -Wd, -np.inf, z)
        else:  # a rock step: 1:3 up from the lake, a flattish top, then a steep face down to the floor below
            up = np.clip(1 + x / Wd, 0, 1)
            z = np.where(x < 0, level - 1.0 + (fb + 1.0) * up, crest - np.tan(math.radians(58)) * np.maximum(x - 0.25 * Wd, 0))
            z = z + 0.25 * fb * (wob - 0.5)
            z = np.where(x < -Wd, -np.inf, z)
        # the spillway: where the river crosses, or the crest line's lowest ground (the water leaves over it)
        line = (np.abs(x) < max(self.cell, 0.1 * Wd)) & (np.abs(s) < 4 * r)
        if riv is not None:
            pts = riv.xy[(riv.xy - xy) @ tan > 0]
            dl = cKDTree(pts).query(self.P)[0].reshape(self.X.shape) if len(pts) else np.full(self.X.shape, np.inf)
            k = np.argmin(np.where(line, dl, np.inf))
        else:
            k = np.argmin(np.where(line, self._smooth(before, 2 * self.cell), np.inf))
        sp = self.P[k]
        notch_w = float(lf.get("spillway", max(8.0, riv.props["floor"] * 0.6 if riv is not None else 8.0)))
        # a channel through the dam from the lake's level, falling through it (a moraine's in a gentle cut, a rock
        # bar's down its face in rapids)
        dn = np.abs((self.X - sp[0]) * nrm[0] + (self.Y - sp[1]) * nrm[1])
        grade = 0.08 if kind == "moraine" else 0.5
        z_ch = level + 0.1 - grade * np.maximum(x, 0)
        # the cut's sides slope back at ~30 deg (a moraine's) or 60 (rock), not a vertical slot
        side = math.tan(math.radians(30 if kind == "moraine" else 60))
        z = np.where(x > -Wd, np.minimum(z, z_ch + side * np.maximum(dn - notch_w / 2, 0)), z)
        on = (np.abs(x) < 2.5 * Wd) & (z > self.H) & (np.abs(s) < 5 * r)
        self.H = np.where(on, z, self.H)
        # the lake side of the dam is the lake's own bank: dig back to the lake where the bowl was (the dam's inner
        # toe stood in the water)
        if kind == "rock bar":
            self.hard |= on & (x > -0.3 * Wd)
            self.hardness = np.where(on & (x > -0.3 * Wd), 0.1, self.hardness)
        m = on & (z > before + 0.5)
        self.vzones = getattr(self, "vzones", {})
        self.vzones[f"{name}.dam"] = m
        lf["_dam"] = {"kind": kind, "crest": crest, "spillway": sp.tolist(), "tangent": tan.tolist(), "width": Wd}
        site = float(self.height(xy + tan * (0.95 * r + 0.5 * Wd), before))
        tall = crest - site
        if tall > max(30.0, 0.25 * r):
            self.warnings.append(f"lake {name!r}: its {kind} stands {tall:.0f} m over the valley floor at its site "
                                 f"({site:.0f} m): a wall, not a {kind}. Lower the level toward {site + 8:.0f} m (leave "
                                 f"\"level\" out and it's set from the floor), or move the lake up the valley")

    def _dam_report(self, name, lk):
        """A valley lake's natural dam as built: its crest above the water, the spillway's lip, how far the water runs
        up the valley, and how far the floor falls below the dam (the lake is held partway down)."""
        lf = (self.spec.get("landforms") or {}).get(name) or {}
        dm = lf.get("_dam")
        if not dm or not lk.get("area"):
            return ""
        m = self.vzones.get(f"{name}.dam") if hasattr(self, "vzones") else None
        crest = float(np.percentile(self.H[m], 90)) if m is not None and m.any() else dm["crest"]
        sp = np.array(dm["spillway"])
        lip = float(self.height(sp))
        tan = np.array(dm["tangent"])
        wet = self.lake_id == lk["id"]
        up = float(-(((self.P - np.array(lk["xy"])) @ tan)[wet.ravel()]).min()) if wet.any() else 0.0
        below = float(self.height(sp + tan * 2.5 * dm["width"]))
        return (f"; held by a {dm['kind']} across the valley (crest ~{crest - lk['level']:+.1f} m over the water, "
                f"spillway lip {lip - lk['level']:+.1f} m at [{sp[0]:.0f}, {sp[1]:.0f}]); the water runs {up:.0f} m up "
                f"the valley from the lake's centre; the floor below the dam is {lk['level'] - below:.0f} m lower")

    def _bank_report(self, name, lk):
        """A dammed lake's embankment as built (measured): how deep the water stands against it, its lowest crest over
        the water, the crest's width; warnings when the lake stands on a slope or the bank is too slight to hold."""
        m = self.dams.get(name)
        if m is None or not m.any() or not lk.get("area"):
            return ""
        lf = (self.spec.get("landforms") or {}).get(name) or {}
        level = lk["level"]
        wet = self.lake_id == lk["id"]
        by = ndimage.binary_dilation(m, iterations=2) & wet
        deep = float((level - self.H[by]).max()) if by.any() else 0.0
        d = np.hypot(self.X - lk["xy"][0], self.Y - lk["xy"][1])
        near = wet & (d < max(lk["r"] / 3, 2 * self.cell))

        def spilt(f):  # the water raised f m: does it leave the lake (past its banks' own widening)?
            lab, _ = ndimage.label(self.H < level + f)
            ids = np.unique(lab[near if near.any() else wet])
            w = np.isin(lab, ids[ids > 0])
            room = ndimage.binary_dilation(wet, iterations=int(math.ceil(3.0 * f / self.cell)) + 2)
            return bool((w & ~room).any())
        free = 0.0
        for f in np.arange(0.25, 4.01, 0.25):
            if spilt(float(f)):
                break
            free = float(f)
        # how thick the ground that holds the water is, half the freeboard up: from the water to lower ground outside
        hold = level + 0.5 * max(free, 0.25)
        lab, _ = ndimage.label(self.H < hold)
        ids = np.unique(lab[wet])
        inner = np.isin(lab, ids[ids > 0])
        outer = (self.H < hold) & ~inner
        dist = ndimage.distance_transform_edt(~outer) * self.cell if outer.any() else np.full(self.H.shape, np.inf)
        edge = ndimage.binary_dilation(inner) & ~inner
        width = float(dist[edge].min()) if edge.any() else float("inf")
        asked = float(lf.get("depth", 10))

        def warn(w):
            if w not in self.warnings:
                self.warnings.append(w)
        if deep > max(2 * asked, asked + 3):
            warn(f"lake {name!r} stands on a slope: the water is {deep:.0f} m deep against its dam where depth {asked:g} "
                 f"was asked. Put it on flatter ground, make it smaller, or lower its level")
        if free < 1.0:
            warn(f"lake {name!r}: raised {free + 0.25:.2f} m its water leaves over the dam (freeboard under {free + 0.25:.2f} "
                 f"m: a coarse mesh of the ground can dip under the water): raise \"freeboard\"")
        if width < 3 * self.cell:
            warn(f"lake {name!r}: its dam is only {width:.1f} m thick half the freeboard over the water, under 3 cells "
                 f"of {self.cell:g} m: set \"crest_width\" or a finer cell")
        return (f"; dammed: {deep:.0f} m deep at the dam (asked {asked:g}), freeboard {free:.2f} m+, the dam "
                f"{width:.0f} m thick at {hold - level:+.2f} m")

    def _lf_fan(self, name, lf):
        """A debris cone where a steep stream meets flatter ground: spreads downslope from the stream's mouth."""
        xy, _, tan = self.address(lf["at"])
        if tan is None:
            raise ValueError(f"fan {name!r}: 'at' must be on a river (e.g. 'burn.mouth') so it knows which way to spread")
        base = self.floor
        v = np.stack([self.X - xy[0], self.Y - xy[1]], -1)
        d = np.linalg.norm(v, axis=-1)
        ahead = (v @ tan) / (d + 1e-9)
        spread = np.clip((ahead + 0.3) / 0.6, 0, 1)
        cone = lf["height"] * np.clip(1 - d / lf["radius"], 0, 1) ** 1.3 * spread * (self.t < 0.5)
        self.H = np.where(cone > 0, np.maximum(self.H, self._smooth(base + cone, 20 * self.k)), self.H)
        lf["_centre"] = (xy + tan * lf["radius"] * 0.35).tolist()

    def _lf_moraine(self, name, lf):
        """A ridge of till across a valley where a glacier's snout stood, bowed downstream, breached by the river."""
        river = lf["across"].split("@")[0]
        xy, _, tan = self.address(lf["across"])
        nrm = np.array([-tan[1], tan[0]])
        v = np.stack([self.X - xy[0], self.Y - xy[1]], -1)
        u, w = v @ tan, v @ nrm
        L = self.lines[river]
        u = u + 0.0006 / self.k * w ** 2
        bump = lf["height"] * np.exp(-(u / lf["width"]) ** 2)
        breach = 1 - np.exp(-(w / (L.props["floor"] * 0.3)) ** 2)
        self.H += bump * breach * np.clip(1 - self.t / 0.45, 0, 1)
        lf["_centre"] = (xy + nrm * L.props["floor"]).tolist()

    def _lf_terrace(self, name, lf):
        """A flat bench on one bank at a height above the river: cuts the slope above, fills below."""
        L = self.lines[lf["along"]]
        side = 1 if lf.get("side", "left") == "left" else -1
        d, i = cKDTree(L.xy).query(self.P)
        d, i = d.reshape(self.X.shape), i.reshape(self.X.shape)
        tan = np.gradient(L.xy, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True)
        nrm = np.stack([-tan[:, 1], tan[:, 0]], 1) * side
        v = np.stack([self.X, self.Y], -1) - L.xy[i]
        on_side = (v * nrm[i]).sum(-1) > 0
        inner = L.props["floor"] / 2
        band = np.clip(np.minimum(d - inner, inner + lf["width"] - d) / (30 * self.k) + 0.5, 0, 1)
        along = np.clip(np.minimum(L.s[i] - lf["from"], lf["to"] - L.s[i]) * L.props["length"] / (60 * self.k) + 0.5, 0, 1)
        w = self._smooth(band * along * on_side, 15 * self.k)
        self.H = self.H * (1 - w) + (L.h[i] + lf["height"]) * w
        cxy, _, ctan = L.at((lf["from"] + lf["to"]) / 2)
        lf["_centre"] = (cxy + np.array([-ctan[1], ctan[0]]) * side * (inner + lf["width"] / 2)).tolist()

    def _fill_lakes(self):
        """Each lake fills the ground below its own level connected to its centre. Real water in an enclosed basin
        would rise to the basin's lowest rim; for a designed level that's rarely wanted, so a leak is reported and
        the water kept to the lake's own neighbourhood."""
        self.water[:] = np.nan
        self.lake_id = np.zeros(self.X.shape, int)
        self.warnings = [w for w in self.warnings if not w.startswith("lake ")]  # this runs twice
        for name, lk in self.lakes.items():
            if lk.get("sea"):
                from . import terrain_sea
                wet = terrain_sea.fill(self, lk) & np.isnan(self.water)
                self.water[wet] = lk["level"]
                self.lake_id[wet] = lk["id"]
                lk.update(area=wet.sum() * self.cell ** 2, depth=float((lk["level"] - self.H[wet]).max()) if wet.any() else 0)
                continue
            xy, level, r = np.array(lk["xy"]), lk["level"], lk["r"]
            d = np.hypot(self.X - xy[0], self.Y - xy[1])
            below = self.H < level
            lab, _ = ndimage.label(below)
            near = (d < max(r / 3, 2 * self.cell)) & below
            if not near.any():
                lk.update(area=0, depth=0)
                why = [o for o, p in self._prints.items() if o != name and (p & (d < r)).any()]
                self.warnings.append(f"lake {name!r} holds no water: the ground at its centre is above its level "
                                     f"{level:.0f} m" + (f" (raised by {', '.join(why)})" if why else ""))
                continue
            ids = np.unique(lab[near])
            wet = np.isin(lab, ids[ids > 0])
            def spills(w):
                return (w & (d > lk.get("reach", 2.5) * r)).any() or w[[0, -1], :].any() or w[:, [0, -1]].any()

            if spills(wet):
                # water finds its own level: the highest that stays in its basin (cropping it at a radius left water
                # standing over land at the crop)
                edge = wet & (d > 1.3 * r)
                k = np.argmin(np.where(edge, d, np.inf))
                lo_l, hi_l = float(self.H[near].min()), level
                for _ in range(14):
                    mid = (lo_l + hi_l) / 2
                    lab2, _ = ndimage.label(self.H < mid)
                    ids2 = np.unique(lab2[near & (self.H < mid)])
                    w2 = np.isin(lab2, ids2[ids2 > 0])
                    lo_l, hi_l = (mid, hi_l) if not spills(w2) else (lo_l, mid)
                lf = (self.spec.get("landforms") or {}).get(name, {})
                if lf.get("dam", True):  # (it told a designer with "dam": true set to set it)
                    fix = (f"its dam reaches only {3 * r:.0f} m from the centre and the ground falls away past it: "
                           f"move the lake where the valley narrows, lower the level, or put a moraine across the valley "
                           f"below it")
                else:
                    fix = "dam it (\"dam\": true), move it, or lower the level"
                self.warnings.append(f"lake {name!r} at {level:.0f} m would spill out near [{self.P[k, 0]:.0f}, "
                                     f"{self.P[k, 1]:.0f}]: its water stands at {lo_l:.1f} m, the most its basin holds; "
                                     + fix)
                level = lk["level"] = lo_l
                below = self.H < level
                lab, _ = ndimage.label(below)
                near = (d < max(r / 3, 2 * self.cell)) & below
                if not near.any():
                    lk.update(area=0, depth=0)
                    continue
                ids = np.unique(lab[near])
                wet = np.isin(lab, ids[ids > 0])
            self.water[wet] = level
            self.lake_id[wet] = lk["id"]
            lk.update(area=wet.sum() * self.cell ** 2, depth=float((level - self.H[wet]).max()) if wet.any() else 0)
            shore = ndimage.binary_dilation(wet) & ~wet
            lk["freeboard"] = float(self.H[shore].min() - level) if shore.any() else 0
        from . import terrain_forms as forms
        forms.water(self)
