"""Terrain's skeleton: ridges, rivers and the valleys they cut (a mixin of Terrain). Part of terrain (terrain.py has the overview; the class is terrain_model.Terrain)."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from . import terrain
from . import noise
from .terrain import Line, _arclen, _catmull, _same

class _TerrainSkeleton:
    """Terrain's skeleton: points, ridges, wandering lines, the rivers' base and the valleys they cut."""

    # ------------------------------------------------ skeleton
    def _pt(self, ref):
        if isinstance(ref, str) and "@" in ref:  # a point on a line already built: "north_ridge@0.6"
            name, s = ref.split("@")
            xy, h, _ = self.lines[name].at(float(s))
            return np.array([*xy, h])
        if isinstance(ref, str):
            if ref not in self.points:
                raise ValueError(f"unknown point {ref!r}: ridges pass through peaks, cols, 'line@0.4' or [x, y, z]")
            xy, h = self.points[ref]
            return np.array([*xy, h])
        if len(ref) == 2 or ref[2] is None:  # a height left out: chosen from the kind, like a peak's
            z = self.world["base"] + 0.85 * self.world["relief"]
            self.filled.append(f"ridge point [{ref[0]:.0f}, {ref[1]:.0f}] h {z:.0f} m")
            return np.array([ref[0], ref[1], z], float)
        return np.array(ref, float)

    def _ridges(self):
        for name, r in (self.spec.get("ridges") or {}).items():
            through = list(r["through"])
            closed = bool(r.get("closed"))
            if len(through) > 2 and _same(through[0], through[-1]):
                through, closed = through[:-1], True
            ctrl = np.array([self._pt(p) for p in through])
            xy, ki = _catmull(ctrl[:, :2], self.cell / 2, closed)
            hs = np.r_[ctrl[:, 2], ctrl[:1, 2]] if closed else ctrl[:, 2]
            h = np.empty(len(xy))
            for j in range(len(ki) - 1):
                a, b = ki[j], ki[j + 1]
                u = np.linspace(0, 1, b - a + 1)
                h[a:b + 1] = hs[j] + (hs[j + 1] - hs[j]) * u * u * (3 - 2 * u)  # peaks and cols level off
            xy = self._wander(xy, ki, r.get("wander", 1.0), seed=len(self.lines))
            s, _ = _arclen(xy)
            self.lines[name] = Line(name, "ridge", xy, h, s, {"crest": terrain.CRESTS[r.get("crest", "arete")], "closed": closed})

    def _wander(self, xy, ki, amount, seed):
        """Real crests never run as smooth arcs between summits: bend each span sideways with low noise, most in its
        middle, none at the peaks and cols themselves (they stay where the designer put them)."""
        if not amount:
            return xy
        tan = np.gradient(xy, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-12
        nrm = np.stack([-tan[:, 1], tan[:, 0]], 1)
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
        n = noise.fbm(np.c_[d / 1.0, np.zeros((len(d), 2))], 350 * self.k, 3, seed=97 + seed) - 0.5
        env = np.zeros(len(xy))
        for a, b in zip(ki[:-1], ki[1:]):
            span = d[b] - d[a]
            env[a:b + 1] = np.sin(np.pi * np.linspace(0, 1, b - a + 1)) * min(0.07 * span, 150 * self.k)
        return xy + nrm * (2 * n * env * amount)[:, None]

    def _river_base(self):
        """The harmonic base, with each river either MAKING its valley or CUTTING one. A river's bed holds the low
        ground of the solve, so a river drawn down ground the rest of the design already made (a beck down a volcano's
        flank, its bed heights read off the old ground) raised everything round it by tens of metres (pushieworld note
        115: +69 m, 122 ha). Such a river cuts its valley instead: the base is solved without it and its valley is cut
        into that ground (its floor at the bed, sides at its profile's grade, never steeper than 1:0.3 nor gentler than
        1:3), so the ground beyond the valley stays as it was. Which: `valley.cut` true / false, else automatic: a river
        running over a volcano or a lone hill (forms stood on the base after the solve: their own height under its path,
        median, over max(CUT_GAP, CUT_SHARE x its fall); pinned there, the form stood on the raised base), or one whose
        bed follows the ground made without it (median within CUT_GAP m: its heights read off that ground; not in a
        basin), cuts. Rivers that make their valleys (beds well above or below the ground made without them: the vale
        river 40 m above, alpine and basin rivers) are solved as before."""
        from .terrain_forms import canyon_rivers
        names = [n for n, L in self.lines.items() if L.kind == "river" and n not in canyon_rivers(self.spec)]
        given = {n: ((self.spec.get("rivers") or {}).get(n, {}).get("valley") or {}).get("cut") for n in names}
        self._cut_rivers = {n for n, v in given.items() if v}
        auto = [n for n, v in given.items() if v is None]
        self.cut_report = {}
        others = any(self.spec.get(k) for k in ("sea", "basins", "ridges")) or any(
            v != "open" for v in (self.spec.get("border", "open") if isinstance(self.spec.get("border", "open"), dict)
                                  else {"all": self.spec.get("border", "open")}).values())
        if auto and others:  # (with nothing else holding the ground the rivers make the land: a plain's rivers)
            keep = {k: (v.copy() if isinstance(v, (list, dict, set)) else v) for k, v in self.__dict__.items()}
            self._cut_rivers = self._cut_rivers | set(auto)
            try:
                H0 = self._base()
                forms = H0 - self._before_forms
                basin = np.zeros(H0.shape)
                for b in self.basins.values():
                    basin = np.maximum(basin, b["inside"] if "inside" in b and b["inside"] is not None else b["floor"])
            except ValueError:  # (nothing low without them: they make the land)
                H0 = None
            self.__dict__.clear()
            self.__dict__.update(keep)
            if H0 is not None:
                for n in auto:
                    L = self.lines[n]
                    on = float(np.median(self.sample(L.xy, forms)))
                    gap = float(np.median(self.sample(L.xy, H0) - L.h))
                    inside = float(np.mean(self.sample(L.xy, basin.astype(float)) > 0.5))
                    if on > max(terrain.CUT_GAP, terrain.CUT_SHARE * float(L.h.max() - L.h.min())) or (abs(gap) < terrain.CUT_GAP and inside < 0.5):
                        self._cut_rivers.add(n)
                        self.cut_report[n] = (on, gap)
        H = self._base()
        for n in sorted(self._cut_rivers):
            H = self._cut_valley(H, self.lines[n])
        return H

    def _cut_valley(self, H, L):
        """A river's own valley cut into the ground: floor at its bed, `floor` m wide, sides rising at its profile's
        grade (0.3..3), a rounded shoulder where they meet the ground; only ever lowers. The floor is erosion's base
        level, like a valley-making river's."""
        fh = L.props["floor"] / 2
        g = float(np.clip(L.props["side"], 0.3, 3.0))
        deep = float(np.max(self.sample(L.xy, H) - L.h)) if len(L.xy) else 0.0
        if deep <= 0:
            return H
        reach = fh + deep / g + 3 * self.cell
        d, i = cKDTree(L.xy).query(self.P, distance_upper_bound=reach)
        ok = np.isfinite(d)
        d = d.reshape(H.shape)
        i = np.minimum(i, len(L.xy) - 1).reshape(H.shape)
        ok = ok.reshape(H.shape)
        d = np.where(ok, d, reach)
        z = L.h[i] + g * np.maximum(d - fh, 0.0)
        k = max(2 * self.cell, 6.0)  # (the shoulder: a smooth min over ~k m of height)
        hh = np.clip(0.5 + 0.5 * (H - z) / k, 0, 1)
        cutz = z * hh + H * (1 - hh) - k * hh * (1 - hh)
        out = np.where(ok, np.minimum(H, cutz), H)
        self._fixed_river |= ok & (d <= max(fh, 0.75 * self.cell))
        return out

    def _rivers(self):
        todo = dict(self.spec.get("rivers") or {})
        for name, r in todo.items():  # (an unknown key was dropped silently: pushieworld's `falls` before they existed)
            odd = sorted(k for k in r if k not in terrain.RIVER_KEYS and not str(k).startswith("_"))
            if odd:
                self.warnings.append(f"river {name!r}: unknown key(s) {odd} ignored (a river takes "
                                     f"{', '.join(sorted(terrain.RIVER_KEYS))})")
        while todo:
            progressed = False
            for name, r in list(todo.items()):
                if r.get("into") and r["into"] not in self.lines:
                    continue
                for key in ("source", "mouth"):  # (an [x, y] source crashed with an IndexError)
                    if key in r and len(r[key]) < 3:
                        raise ValueError(f"river {name!r}: its {key} needs a height, [x, y, z] (the river's heights come "
                                         f"from its source, its through points that have a z, and its mouth)")
                src = np.array(r["source"], float)
                mid = [np.array(p, float) for p in r.get("through", [])]
                if r.get("into"):
                    parent = self.lines[r["into"]]
                    last = mid[-1][:2] if mid else src[:2]
                    j = int(cKDTree(parent.xy).query(last)[1])
                    j = min(j + int(100 / self.cell), len(parent.xy) - 1)  # joins a little downstream
                    mouth = np.array([*parent.xy[j], parent.h[j] + r.get("hanging", 0)])
                else:
                    mouth = np.array(r["mouth"], float)
                ctrl = np.vstack([src[:2], *[m[:2] for m in mid], mouth[:2]])
                xy, ki = _catmull(ctrl, self.cell / 2)
                s, length = _arclen(xy)
                k = r.get("concavity", 1.6)  # graded rivers: steep near the source, flattening downstream
                known = [(0, src[2])] + [(ki[i + 1], m[2]) for i, m in enumerate(mid) if len(m) > 2] + [(len(xy) - 1, mouth[2])]
                h = np.empty(len(xy))
                for (a, ha), (b, hb) in zip(known[:-1], known[1:]):
                    u = (s[a:b + 1] - s[a]) / max(s[b] - s[a], 1e-9)
                    h[a:b + 1] = hb + (ha - hb) * (1 - u) ** k
                from . import terrain_falls  # (waterfalls: steps in the profile, the rest of its fall gentler)
                h, falls = terrain_falls.profile(name, h, s, terrain_falls.parse(name, r, length))
                v = r.get("valley") or {}
                prof = v.get("profile", "V")
                self.lines[name] = Line(name, "river", xy, h, s, {
                    "p": terrain.PROFILES[prof], "side": float(v.get("sides", terrain.SIDE_GRADE[prof])),
                    "floor": float(v.get("floor", 30 * self.k)), "length": length,
                    "into": r.get("into"), "hanging": r.get("hanging", 0), "falls": falls})
                del todo[name]
                progressed = True
            if not progressed:
                raise ValueError(f"rivers joining unknown rivers: {sorted(todo)}")
