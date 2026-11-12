"""class Terrain: a terrain built from its spec (its init, addresses, texture; its other methods are in mixins), and `load`. Part of terrain (terrain.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import terrain
from . import noise
from .terrain import Line, normalise, smoothstep
from .terrain_skeleton import _TerrainSkeleton
from .terrain_harmonic import _TerrainBase
from .terrain_features import _TerrainFeatures
from .terrain_landforms import _TerrainLandforms
from .terrain_measure import _TerrainMeasure

# ---------------------------------------------------------------- the terrain
class Terrain(_TerrainSkeleton, _TerrainBase, _TerrainFeatures, _TerrainLandforms, _TerrainMeasure):
    def __init__(self, spec: dict):
        from . import terrain_design as design
        from .terrain_erode import erode
        self.source = spec
        spec = normalise(spec)
        self.spec = spec
        self.units = spec["_units"]
        (x0, y0), (x1, y1) = spec["extent"]
        self.size = max(x1 - x0, y1 - y0)
        self.k = self.size / terrain.REFERENCE_SIZE  # landscape defaults (noise, ribs, erosion scales) scale with the frame
        self.cell = c = float(spec.get("cell", self.size / 400))
        from . import terrain_world as world
        self.world = world.resolve(self)  # the kind of terrain, its compression, player-scale detail
        world.fill_heights(self)
        self.xs = np.arange(x0, x1 + c / 2, c)
        self.ys = np.arange(y0, y1 + c / 2, c)
        self.X, self.Y = np.meshgrid(self.xs, self.ys)  # [iy, ix]
        self.P = np.stack([self.X.ravel(), self.Y.ravel()], 1)
        self.warnings: list[str] = []
        self.points = {}
        for group in ("peaks", "cols"):
            for n, p in (spec.get(group) or {}).items():
                self.points[n] = (np.array(p["at"], float), float(p["h"]))
        self.zones = dict(spec.get("zones") or {})
        self.lines: dict[str, Line] = {}
        self.lakes: dict[str, dict] = {}
        self.dams: dict[str, np.ndarray] = {}  # per dammed lake: the cells its embankment raised
        self.sites: dict[str, dict] = {}
        self.routes: dict[str, Line] = {}
        self.walls: dict[str, dict] = {}
        self.passes: dict[str, dict] = {}
        self.canyons, self.mesas, self.fords = {}, {}, {}
        self.masks: dict[str, np.ndarray] = {}   # what each design element occupies (sites, routes, ...)
        self.water = np.full(self.X.shape, np.nan)
        self._ridges()
        self._rivers()
        self.H = self._river_base()
        from . import terrain_forms as forms
        forms.carve(self)  # canyons cut into the plateau, mesas stood on it
        for c in self.canyons.values():  # water ends in a canyon's river: base level for erosion
            m, _ = self._stamp(self.lines[c["river"]], c["floor"] / 2)
            self._fixed_river |= m
        self.H0 = self.H.copy()
        self._texture()
        from . import terrain_sea
        terrain_sea.apply(self)  # the sea and its coast: before lakes, sites and routes, which use its shores
        self._landforms()
        self._fill_lakes()  # lake shores are addresses sites use
        # rugged after the water exists (zones near the sea or a lake were empty before it), never under it
        design.rugged(self)
        design.apply(self)
        pre = self.H.copy()
        erode(self)  # after the design: its places are protected, and lakes are where water ends
        forms.settle(self)  # caprocks stay flat
        from . import terrain_volcano
        terrain_volcano.settle(self, pre)  # volcano forms keep their shape; erosion adds detail
        from . import terrain_detail
        import time as _time
        _t0 = _time.time()
        terrain_detail.refine(self, terrain_detail.factor(self))  # finer cells from here: faces get cells of their own
        terrain_detail.ground(self)  # rolling ground: undulation, swales, hummocks (after erosion smoothed them)
        from . import terrain_lines
        terrain_lines.apply(self)  # hedges, stone walls, fences, banks, ditches, lines of trees
        from . import terrain_rock
        terrain_rock.apply(self)  # buttresses, couloirs, ledges and a boulder foot on every steep face
        design.check(self)
        self._fill_lakes()
        self.cover = design.cover(self)
        if getattr(self, "detail", None):  # what the finer cells cost: these stages ran on f^2 as many cells
            fine = _time.time() - _t0
            self.detail["seconds"] = fine
            self.detail["saved"] = fine * (1 - 1 / self.detail["factor"] ** 2)

    # ------------------------------------------------ addresses
    def address(self, ref):
        """(xy, ground height there, direction or None). See terrain_guide.md for the forms."""
        from . import terrain_design as design
        if isinstance(ref, dict) and "from" in ref:
            xy, _, d = self.address(ref["from"])
            xy = xy + np.array(ref.get("offset", [0, 0]), float)
            return xy, self.height(xy), d
        if isinstance(ref, (list, tuple)):
            xy = np.array(ref[:2], float)
            return xy, self.height(xy), None
        if not isinstance(ref, str):
            raise ValueError(f"bad address {ref!r}")
        if ref in self.points:
            xy = self.points[ref][0]
            return xy, self.height(xy), None
        if ref.startswith("edge:"):  # "edge:w" (its middle) or "edge:w@0.3" (from the south / west end), just inside
            side, _, f = ref[5:].partition("@")
            f = float(f) if f else 0.5
            (x0, y0), (x1, y1) = self.spec["extent"]
            m = 2 * self.cell
            xy = {"w": (x0 + m, y0 + f * (y1 - y0)), "e": (x1 - m, y0 + f * (y1 - y0)),
                  "s": (x0 + f * (x1 - x0), y0 + m), "n": (x0 + f * (x1 - x0), y1 - m)}[side[0]]
            xy = np.array(xy, float)
            inward = {"w": (1, 0), "e": (-1, 0), "s": (0, 1), "n": (0, -1)}[side[0]]
            return xy, self.height(xy), np.array(inward, float)
        if ref == "cliff_foot" or ref.startswith("cliff_foot:"):  # the sea cliffs' foot nearest an address (or the
            # frame's middle): direction into the rock (for caves and notches set against the face)
            from .terrain_sea import cliff_feet
            feet = cliff_feet(self, spacing=max(3 * self.cell, 5.0))
            if not feet:
                raise ValueError(f"{ref!r}: there are no sea cliffs (sea.cliffs) to stand at the foot of")
            near = self.address(ref.split(":", 1)[1])[0] if ":" in ref else self.P.mean(0)
            f = min(feet, key=lambda f_: np.hypot(*(np.array(f_["xy"]) - near)))
            xy = np.array(f["xy"], float)
            return xy, float(f["z"]), -np.array(f["out"], float)
        if ref == "highest" or ref.startswith("highest:"):
            m = design.region(self, ref.split(":", 1)[1]) > 0.5 if ":" in ref else np.ones(self.X.shape, bool)
            k = int(np.argmax(np.where(m, self.H, -np.inf)))
            xy = self.P[k]
            return xy, self.height(xy), None
        if "_rim" in ref.split("@")[0] and "." in ref and ref.split(".")[0] in getattr(self, "canyons", {}):
            from .terrain_forms import rim_address
            return rim_address(self, ref)
        if ref in getattr(self, "fords", {}):
            xy = np.array(self.fords[ref]["xy"])
            return xy, self.height(xy), None
        if ref in getattr(self, "mesas", {}):
            xy = np.array(self.mesas[ref]["xy"])
            return xy, self.height(xy), None
        if ref.endswith("_shore") and "." in ref:
            lake, side = ref.rsplit(".", 1)
            return self._shore(lake, side[:-len("_shore")])
        if ref in self.sites:
            xy = np.array(self.sites[ref]["xy"])
            return xy, self.height(xy), None
        for V in getattr(self, "volcanoes", {}).values():  # "<volcano>.crater", a collapse by name
            if ref in V["collapses"]:
                xy = np.array(V["collapses"][ref]["floor_xy"])
                return xy, self.height(xy), np.array(V["collapses"][ref]["a"])
        if ref.endswith(".crater") and ref[:-7] in getattr(self, "volcanoes", {}):
            xy = np.array(self.volcanoes[ref[:-7]]["xy"])
            return xy, self.height(xy), None
        if ref in self.passes:
            xy = np.array(self.passes[ref]["xy"])
            return xy, self.height(xy), None
        if ref in (self.spec.get("passes") or {}):  # before it's cut
            return self.address(self.spec["passes"][ref]["at"])
        if ref in self.lakes:
            xy = np.array(self.lakes[ref]["xy"])
            return xy, self.height(xy), None
        if "@" in ref:
            name, s = ref.split("@")
            line = self.lines.get(name) or self.routes.get(name)
            if line is None:
                raise ValueError(f"unknown line {name!r} in {ref!r}")
            xy, h, tan = line.at(float(s))
            return xy, self.height(xy), tan
        if "." in ref and ref.rsplit(".", 1)[0] in self.lines:
            name, end = ref.rsplit(".", 1)
            xy, h, tan = self.lines[name].at(0.0 if end == "source" else 1.0)
            return xy, self.height(xy), tan
        if getattr(self, "sea", None) and ref in self.sea.get("beach_at", {}):  # a named beach: its middle on the coast
            xy = np.array(self.sea["beach_at"][ref])
            return xy, self.height(xy), None
        if getattr(self, "sea", None) and ref in self.sea["coves"]:  # a cove: the middle of its bay
            xy = np.array(self.sea["coves"][ref]["xy"])
            return xy, self.height(xy), np.array(self.sea["coves"][ref]["inland"])
        if ref in self.lines or ref in self.routes:  # a line by name: its middle (the whole line for "near" zones)
            xy, h, tan = (self.lines.get(ref) or self.routes[ref]).at(0.5)
            return xy, self.height(xy), tan
        if ref in (self.spec.get("landforms") or {}):
            lf = self.spec["landforms"][ref]
            xy = np.array(lf["_centre"], float) if "_centre" in lf else self._early_xy(ref)  # not built yet
            return xy, self.height(xy), None
        if ref in self.zones or ":" in ref or ref in design.NAMED_REGIONS:
            xy = design.centroid(self, design.region(self, ref))
            return xy, self.height(xy), None
        raise ValueError(f"unknown address {ref!r}")

    def _shore(self, lake, side):
        """The point of a lake's shore furthest toward a compass side, and the direction out of the lake there."""
        dirs = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0), "northeast": (1, 1),
                "northwest": (-1, 1), "southeast": (1, -1), "southwest": (-1, -1)}
        d = np.array(dirs[side], float)
        d /= np.linalg.norm(d)
        wet = ~np.isnan(self.water) & (self.lake_id == self.lakes[lake]["id"])
        if not wet.any():
            raise ValueError(f"lake {lake!r} holds no water, so it has no shore")
        if self.lakes[lake].get("sea"):  # the sea's north shore: the coast on the land's north side; inland from there
            land = self.sea["land"]
            coast = wet & ndimage.binary_dilation(~wet & land)
            pts = np.stack([self.X[coast], self.Y[coast]], 1)
            c = np.array([self.X[land].mean(), self.Y[land].mean()])
            k = int(np.argmax((pts - c) @ d))
            inland = c - pts[k]
            return pts[k], self.height(pts[k]), inland / (np.linalg.norm(inland) + 1e-9)
        edge = wet & ~ndimage.binary_erosion(wet)
        pts = np.stack([self.X[edge], self.Y[edge]], 1)
        c = np.array([self.X[wet].mean(), self.Y[wet].mean()])
        k = int(np.argmax((pts - c) @ d))
        return pts[k], self.height(pts[k]), d

    def summit(self, name):
        """A peak's built height: the highest ground within its own top (map, report and probes all use this)."""
        xy, _ = self.points[name]
        if name in getattr(self, "volcanoes", {}):  # a volcano's top is its rim, round its crater
            V = self.volcanoes[name]
            return float(self.H[np.hypot(self.X - xy[0], self.Y - xy[1]) <= V["rc"] + 3 * self.cell].max())
        p = (self.spec.get("peaks") or {}).get(name) or (self.spec.get("cols") or {}).get(name) or {}
        # within half its top's radius (on a tilt, higher ground uphill inside the whole radius read as its summit)
        r = max(0.5 * float(p.get("radius", 0)), min(40 * self.k, 3 * self.cell), 1.5 * self.cell)
        return float(self.H[np.hypot(self.X - xy[0], self.Y - xy[1]) <= r].max())

    def height(self, xy, H=None):
        H = getattr(self, "H", None) if H is None else H
        if H is None:  # before the ground exists (zones for the base itself): no height yet
            return float("nan")
        return float(self.sample(np.atleast_2d(xy), H)[0])

    def sample(self, xy, H=None):
        H = self.H if H is None else H
        return ndimage.map_coordinates(H, [(xy[:, 1] - self.ys[0]) / self.cell, (xy[:, 0] - self.xs[0]) / self.cell],
                                       order=1, mode="nearest")

    # ------------------------------------------------ processes
    def _texture(self):
        pts = np.c_[self.P, np.zeros(len(self.P))]
        relief = np.minimum(np.maximum(self.crest - self.floor, 0), terrain.RELIEF_CAP * self.k)
        steep = np.clip(self._slope() / 35, 0, 1)
        rough = (0.3 + 0.7 * steep) * np.clip(self.t, 0, 1) ** 0.7  # rock high and steep; floors stay smooth
        crestward = 1 - 0.7 * smoothstep(0.85, 1.0, self.t)  # lumps right on a crest read as pinnacles
        W = self.world
        if W["kind"]:
            # landform structure (spur-and-gully systems a few hundred metres apart): part of the proportions, so it
            # scales with the level; wide and moderate (deep narrow flutes were the problem, not structure)
            land = 1 - np.abs(2 * noise.fbm(pts, 0.06 * self.size, 3, seed=3) - 1)
            self.H += rough * crestward * 0.02 * relief * 2 * (land.reshape(self.X.shape) - 0.5)
            # player-scale roughness: metres, by the kind of terrain, never by the relief
            ridged = 1 - np.abs(2 * noise.fbm(pts, 3 * W["crag"], 3, seed=4) - 1)
            fine = noise.fbm(pts, 1.1 * W["crag"], 2, seed=5)
            self.H += rough * crestward * W["bumps"] * 2 * (ridged.reshape(self.X.shape) - 0.5)
            self.H += rough * 0.4 * W["bumps"] * 2 * (fine.reshape(self.X.shape) - 0.5)
            # floors and plateau tops: a gentle swell and hummocks at player scale (rough is ~0 there: a plateau read as
            # flat plaster from the air)
            swell = noise.fbm(np.c_[self.P, np.full(len(self.P), 21.0)], 6 * W["crag"], 3, seed=6).reshape(self.X.shape)
            # (a swell only: the crag-scale term pocked flat tops like a golf ball)
            self.H += (1 - np.clip(rough / 0.3, 0, 1)) * W["bumps"] * 1.4 * (swell - 0.5)
            return
        ridged = 1 - np.abs(2 * noise.fbm(pts, 120 * self.k, 3, seed=3) - 1)
        gully = noise.fbm(pts, 45 * self.k, 2, seed=5)
        self.H += rough * 0.03 * relief * crestward * (ridged.reshape(self.X.shape) - 0.5)
        self.H += rough * 4 * self.k * (gully.reshape(self.X.shape) - 0.5)


def load(path, log=None) -> Terrain:
    """The built terrain of a spec file, through the disk cache (terrain_cache: keyed by the spec and the build's code)."""
    from . import terrain_cache
    return terrain_cache.build(json.loads(Path(path).read_text()), log=log)
