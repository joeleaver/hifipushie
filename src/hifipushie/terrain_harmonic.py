"""Terrain's harmonic base: the solve and `_base` (a mixin of Terrain). Part of terrain (terrain.py has the overview; the class is terrain_model.Terrain)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage, sparse
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree

from . import terrain
from . import noise
from .terrain import Line

class _TerrainBase:
    """Terrain's harmonic base: the solve, a line's stamp, the frame's edges, and `_base`, the heights solved
    between crests and floors."""

    # ------------------------------------------------ harmonic base
    def _solve(self, fixed: np.ndarray, rhs: list[np.ndarray]) -> list[np.ndarray]:
        ny, nx = self.X.shape
        n = nx * ny
        idx = np.arange(n).reshape(ny, nx)
        rows, cols = [], []
        deg = np.zeros(n)
        for a, b in ((idx[:, 1:].ravel(), idx[:, :-1].ravel()), (idx[1:, :].ravel(), idx[:-1, :].ravel())):
            for i, j in ((a, b), (b, a)):
                rows.append(i); cols.append(j)
                np.add.at(deg, i, 1)
        rows, cols = np.concatenate(rows), np.concatenate(cols)
        f = fixed.ravel()
        keep = ~f[rows]
        A = sparse.csc_matrix((np.r_[-np.ones(keep.sum()), np.where(f, 1.0, deg)],
                               (np.r_[rows[keep], np.arange(n)], np.r_[cols[keep], np.arange(n)])), shape=(n, n))
        lu = splu(A)
        return [lu.solve(np.where(f, r.ravel(), 0.0)).reshape(ny, nx) for r in rhs]

    def _stamp(self, line: Line, radius: float):
        """Cells within radius of a line, and for each cell its nearest sample index."""
        d, i = cKDTree(line.xy).query(self.P, distance_upper_bound=radius + self.cell)
        m = d <= max(radius, self.cell * 0.75)
        return m.reshape(self.X.shape), np.where(m, i, 0).reshape(self.X.shape)

    def _edges(self):
        """Fixed frame-edge cells and their heights. "border": a height, or per side {"n"|"s"|"e"|"w": height |
        "open"}; an open side has no height of its own (the ground carries on as it goes)."""
        b = self.spec.get("border", "open")
        sides = b if isinstance(b, dict) else {k: b for k in "nsew"}
        shape = self.X.shape
        fix, val = np.zeros(shape, bool), np.zeros(shape)
        for k, sl in (("s", (0, slice(None))), ("n", (-1, slice(None))), ("w", (slice(None), 0)), ("e", (slice(None), -1))):
            v = sides.get(k, "open")
            if v != "open":
                fix[sl] = True
                val[sl] = float(v)
        return fix, val

    def _base(self):
        shape = self.X.shape
        low_fix, low = self._edges()
        prof = np.full(shape, terrain.PROFILES["V"])
        high_fix, high, crest = np.zeros(shape, bool), np.zeros(shape), np.zeros(shape)
        self._fixed_river = np.zeros(shape, bool)
        river_id = np.zeros(shape, int)
        from .terrain_forms import canyon_rivers
        cut = canyon_rivers(self.spec)
        rivers = [L for L in self.lines.values() if L.kind == "river" and L.name not in cut
                  and L.name not in getattr(self, "_cut_rivers", ())]  # (rivers cutting their own valley: _river_base)
        for k, L in enumerate(rivers, 1):
            m, i = self._stamp(L, L.props["floor"] / 2)
            if L.props["hanging"]:  # the lip: leave the last stretch free, so the step is steep, not a wall
                into = self.lines[L.props["into"]].props["floor"]
                m &= (1 - L.s[i]) * L.props["length"] > 3 * L.props["hanging"] + into / 2
            low_fix |= m; low[m] = L.h[i[m]]; prof[m] = L.props["p"]
            self._fixed_river |= m
            river_id[m] = k
        self.basins = {}
        for name, b in (self.spec.get("basins") or {}).items():
            F, floor_h, wall_p = self._basin(name, b)
            keep = F & ~self._fixed_river  # authored rivers inside a basin keep their own heights
            low_fix |= keep; low[keep] = floor_h[keep]; prof[keep] = wall_p
            prof[~low_fix & self.basins[name]["wall"]] = wall_p
        for L in self.lines.values():
            if L.kind == "ridge":
                m, i = self._stamp(L, 0)
                high_fix |= m; high[m] = L.h[i[m]]; crest[m] = L.props["crest"]
                low_fix &= ~m  # a ridge reaching the frame's edge stays a ridge
        # a peak no ridge passes through stands alone (a hill, a knoll): not a constraint (a fixed disk next to a fixed
        # floor makes a walled mesa) but a dome raised on whatever ground is there, after the base (_hills)
        on_ridge = {p for r in (self.spec.get("ridges") or {}).values() for p in r["through"] if isinstance(p, str)}
        self._lone = [n for n in self.points if n not in on_ridge]
        sea = self.spec.get("sea")
        land_plain = None
        if sea:  # the sea is low ground: the land falls to it (a ring of peaks with nothing low around it stood as a
            # plateau at its basin floor's height)
            lvl = float(sea.get("level", 0.0))
            if "land" in sea and not low_fix.any() and not high_fix.any():
                # a coast drawn as a land zone with nothing else holding the ground (no ridges, rivers, basins or
                # border): the land is a plain at world.base (+ tilt, hills), like a coast without a zone. Solved from
                # the seabed alone it sagged to the seabed, so a low coast stood at sea level 100 m inland and raised
                # cliffs left hollows behind them.
                from . import terrain_design as design
                try:
                    land_plain = (design.region(self, sea["land"]) < 0.5, lvl - 0.5 * float(sea.get("depth", 30.0)))
                except (AttributeError, ValueError):
                    land_plain = None
            if land_plain is None and "land" in sea:
                from . import terrain_design as design
                try:
                    out = design.region(self, sea["land"]) < 0.5
                except (AttributeError, ValueError):  # a land zone made from the ground itself: not yet
                    out = None
                if out is not None:
                    if not high_fix.any() and self._fixed_river.any():
                        # a land zone with rivers but no ridges: the land away from the rivers stays at world.base
                        # (solved between the rivers and the seabed alone, a stream made the whole coast sink: sites
                        # 18 m -> 2 m, ground 0 m a kilometre inland)
                        fl = max((L.props["floor"] for L in self.lines.values() if L.kind == "river"), default=60.0)
                        reach = 2.0 * fl + 120.0 * self.k
                        far = (ndimage.distance_transform_edt(~self._fixed_river) * self.cell > reach) & ~out & ~low_fix
                        low_fix |= far
                        low[far] = self.world["base"]
                    out &= ~high_fix
                    low_fix |= out
                    low[out] = lvl - 0.5 * float(sea.get("depth", 30.0))
            elif not low_fix.any() and high_fix.any():  # ridges with nothing low: the frame's edges at the land's base
                # (a plain stays a plain at world.base with its tilt: pinning the edges at the sea floor had ignored the
                # base and put a coast's farmland at 0 m)
                for sl in ((0, slice(None)), (-1, slice(None)), (slice(None), 0), (slice(None), -1)):
                    low_fix[sl] = True
                    low[sl] = self.world["base"]
        plain = not low_fix.any() and not high_fix.any()  # a tile of open ground: a plain at the base height (+ tilt, hills)
        if not low_fix.any() and not plain:
            raise ValueError("nothing low: add a river or a basin, or give the frame's edge a height (\"border\")")

        if land_plain is not None:
            plain = True

        def solve():
            if plain:
                base = self.world["base"]
                self.floor, self.prof = np.full(shape, base), prof
                if land_plain is not None:  # the sea's side at the seabed (the shore forms reshape the coast)
                    self.floor = np.where(land_plain[0], land_plain[1], self.floor)
                self.crest, self.round, self.t = self.floor.copy(), np.zeros(shape), np.zeros(shape)
                return
            self.floor, self.prof = self._solve(low_fix, [low, prof])
            if high_fix.any():
                t, = self._solve(low_fix | high_fix, [np.where(high_fix, 1.0, 0.0)])
                self.crest, self.round = self._solve(high_fix, [high, crest])
                self.t = np.clip(t, 0, 1)
            else:  # no ridges at all (a tile of rolling ground, hills only): the low ground is the ground
                self.crest, self.round, self.t = self.floor.copy(), np.zeros(shape), np.zeros(shape)

        solve()
        self.divides = []
        extra = []
        if self.spec.get("divides", True) and len(rivers) > 1:
            add = self._divides(rivers, river_id, high_fix)
            if add is not None:
                extra.append(add)
        if self.spec.get("ribs", True) and high_fix.any():
            add = self._ribs(high_fix, low_fix)
            if add is not None:
                extra.append(add)
        if extra:
            for m, h in extra:
                m = m & ~low_fix
                high_fix |= m; high[m] = h[m]; crest[m] = 1.0
            solve()
        s = self.t ** self.prof
        s = (1 - self.round) * s + self.round * (1 - (1 - s) ** 2)
        self.hard = np.zeros(self.X.shape, bool)  # rock that resists erosion (cliff bands)
        self.hardness = np.ones(self.X.shape)  # erodibility factor: 1 soil ... ~0 rock that stands
        for b in self.basins.values():  # basin walls get a mountainside's profile, and a character
            prof = self._wall_profile(b)
            u = np.linspace(0, 1, len(prof))
            t = self.t
            if b.get("_zones_t"):
                # a designed profile is laid out by horizontal distance, floor's edge to crest (the harmonic t crowds
                # toward the crest and floor, so each band came out at another slope: cliffs 37 deg, scree 48)
                d_floor = ndimage.distance_transform_edt(~b["floor"]) * self.cell
                t = np.where(b["wall"], np.clip(d_floor / np.maximum(d_floor + b["d_crest"], 1e-6), 0, 1), t)
            if b["character"] in ("buttressed", "broken", "tiered"):
                # buttresses and couloirs: along the ring the face's profile shifts out and in, so rock ribs stand
                # proud between gullies (a smooth face read as drapery; ~900 m apart they read as lobes, not ribs)
                spacing = max(0.4 * b["width"], 80 * self.k)
                a1 = b["arc"] / spacing
                n1 = noise.fbm(np.c_[a1.ravel(), np.zeros((a1.size, 2))], 1.0, 3, seed=73).reshape(self.X.shape)
                amp = {"buttressed": 0.3, "broken": 0.45, "tiered": 0.15}[b["character"]]
                if b.get("_zones_t"):  # (a designed profile keeps its bands' slopes: shifting t by 0.3 stretched the
                    amp *= 0.3         # cliffs to 47 deg; the rock pass breaks the face up instead)
                t = np.clip(t + amp * (2 * n1 - 1) * np.sin(np.pi * np.clip(t, 0, 1)), 0, 1)
            s = np.where(b["wall"], np.interp(t, u, prof), s)
            # the band(s) wander up and down the face (one even ring read as a built wall)
            pts = np.c_[self.P, np.zeros(len(self.P))]
            shift = 0.12 * (2 * noise.fbm(pts, 500 * self.k, 2, seed=71).reshape(self.X.shape) - 1)
            if b.get("_zones_t"):  # (a designed profile's cliffs are where it put them: the hard band too)
                shift = np.zeros(self.X.shape)
                b["t_prof"] = np.where(b["wall"], t, np.nan)  # (the bands are re-cut on the final ground for cover)
            if b.get("_zones_t"):  # each band of the designer's profile as a zone ("valley.scree"), edges ragged: scree
                # runs down in tongues into the forest below it, the treeline ragged under the cliffs
                tong = noise.fbm(np.c_[b["arc"].ravel() / max(60 * self.k, 4 * self.cell),
                                       np.full(self.X.size, 4.0), np.zeros(self.X.size)], 1.0, 2, seed=77)
                rag = 0.05 * (2 * tong.reshape(self.X.shape) - 1)
                tz = t + rag * np.sin(np.pi * np.clip(t, 0, 1))
                # (rock bands keep the geometry's own edge: a ragged edge put scree slopes in the cliffs' zone)
                rocky = {"cliffs", "crags", "slabs"}
                hard = np.zeros(self.X.shape, bool)
                for kind, (t0, t1) in b["_zones_t"].items():
                    if kind in rocky:
                        hard |= (t >= t0) & (t < t1 + (1 if t1 >= 1 else 0))
                b["zones"] = {kind: b["wall"] & ((t >= t0) & (t < t1 + (1 if t1 >= 1 else 0)) if kind in rocky else
                                                 (tz >= t0) & (tz < t1 + (1 if t1 >= 1 else 0)) & ~hard)
                              for kind, (t0, t1) in b["_zones_t"].items()}
            for at0 in b["_bands"]:
                at = at0 + shift  # (breaking a band made climbable gaps: "unclimbable" wins that one)
                band = b["wall"] & (t >= at - 0.03) & (t <= at + b["_ft"] + 0.03)
                self.hard |= band
                self.hardness = np.where(band, 0.2, self.hardness)  # (0 made a palisade: it stood, all else went)
            if b.get("_zones_t"):
                b["_s"] = np.interp(t, u, prof)
        H = self.floor + np.maximum(self.crest - self.floor, 0) * s
        for b in self.basins.values():
            if "_s" in b:  # a designed profile runs from the floor's edge to the ridge itself (the crest field sags
                # between ribs: the cliffs at the top came out at 47 deg over 60% of the relief)
                _, (fy, fx_) = ndimage.distance_transform_edt(~b["floor"], return_indices=True)
                fe = self.floor[fy, fx_]
                H = np.where(b["wall"], fe + np.maximum(b["crest_here"] - fe, 0) * b.pop("_s"), H)
        tilt = self.spec.get("tilt")  # the whole frame leans: {"down": "south" | bearing deg, "grade": 0.07}
        if tilt:
            down = tilt.get("down", "south")
            b = math.radians({"north": 0, "east": 90, "south": 180, "west": 270}.get(down, down if isinstance(down, (int, float)) else 180))
            (x0, y0), (x1, y1) = self.spec["extent"]
            along = (self.X - (x0 + x1) / 2) * math.sin(b) + (self.Y - (y0 + y1) / 2) * math.cos(b)
            H = H - float(tilt.get("grade", 0.05)) * along  # lower toward `down`
        from . import terrain_volcano
        self._before_forms = H  # (what the volcanoes and lone hills stand on: _river_base)
        H = terrain_volcano.build(self, self._hills(H))  # volcanoes stand on the base, as large-scale ground
        from .terrain_forms import peak_forms
        return peak_forms(self, H)  # summits carved to their form (pyramid, horn)
