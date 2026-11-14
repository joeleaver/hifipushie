"""Measuring a Terrain: report, drainage, export (a mixin of Terrain). Part of terrain (terrain.py has the overview; the class is terrain_model.Terrain)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import terrain
from .terrain import _accumulate, _area, _receivers

class _TerrainMeasure:
    """Measuring a Terrain: slope, the report, lengths in the spec's units, the highest ground, drainage,
    export."""

    # ------------------------------------------------ measuring
    def _slope(self, H=None):
        H = self.H if H is None else H
        gy, gx = np.gradient(H, self.cell)
        return np.degrees(np.arctan(np.hypot(gx, gy)))

    def report(self) -> str:
        from . import terrain_design_report
        from . import terrain_world
        out = terrain_world.report(self)
        if getattr(self, "detail", None):
            out.append(f"grid: the design at a {self.detail['cell']:g} m cell, rock, cover and the export at "
                       f"{self.cell:g} m (detail {self.detail['factor']}: faces get cells of their own); those stages "
                       f"took {self.detail.get('seconds', 0):.0f} s, about {self.detail.get('saved', 0):.0f} s more than "
                       f"at the design cell, and views and export are {self.detail['factor'] ** 2}x the cells. "
                       f"\"detail\": 1 turns it off (cliffs then 2-3 cells across: soft drapes)")
        elif self.spec.get("detail", "auto") == "auto" and getattr(self, "sea", None) is not None \
                and (self.sea["wc"] > 0.5).any():
            out.append(f"grid: {self.cell:g} m everywhere; detail stayed off because the fine grid would be over "
                       f"{__import__('hifipushie.terrain_detail', fromlist=['x']).MAX_SIDE} cells a side at this cell. A "
                       f"larger cell with detail on (or \"detail\": 2 anyway, slower) gives the cliffs finer cells")
        out.append("peaks/cols (authored -> built):")
        cols = self.spec.get("cols") or {}
        from .terrain_forms import measure_peak
        for n, (xy, h) in self.points.items():
            built = self.height(xy) if n in cols else self.summit(n)
            form = ""
            if n in getattr(self, "peak_forms", {}):
                m = measure_peak(self, n)
                form = (f"; {self.peak_forms[n]['form']}: falls {m['fall']:.0f} m in its first {m['at']:.0f} m, "
                        f"{m['aretes']} arêtes (crest angle median {m['crest']:.0f} deg: a knife edge ~100, rounded 150+), "
                        f"faces median {m['faces']:.0f} deg")
            tilt = self.spec.get("tilt")
            if tilt and n not in self._lone and abs(built - h) > 2:  # (lone hills are raised after the tilt: exact)
                down = tilt.get("down", "south")
                bt = math.radians({"north": 0, "east": 90, "south": 180, "west": 270}.get(
                    down, down if isinstance(down, (int, float)) else 180))
                (x0, y0), (x1, y1) = self.spec["extent"]
                off = -float(tilt.get("grade", 0.05)) * ((xy[0] - (x0 + x1) / 2) * math.sin(bt)
                                                         + (xy[1] - (y0 + y1) / 2) * math.cos(bt))
                if abs(off) > 2:
                    form += (f" (the frame's tilt {'raises' if off > 0 else 'lowers'} it {abs(off):.0f} m here: ridges and "
                             f"their peaks lean with the frame; give h {h - off:.0f} for {h:.0f} as built)")
            out.append(f"  {n}: {h:.0f} m -> {built:.0f} m" + form + (" (a pass notches it)" if any(
                np.hypot(*(np.array(p["xy"]) - xy)) < p["width"] + 3 * self.cell for p in self.passes.values()) else ""))
        for L in self.lines.values():
            if L.kind != "river":
                continue
            out.append(f"river {L.name}: {L.props['length']:.0f} m, {L.h[0]:.0f} -> {L.h[-1]:.0f} m, "
                       f"mean grade {100 * (L.h[0] - L.h[-1]) / L.props['length']:.1f}%")
            for s in (0.15, 0.5, 0.85):
                xy, h, tan = L.at(s)
                nrm = np.array([-tan[1], tan[0]])
                prof = []
                for side in (1, -1):
                    ds = np.arange(0, 1500 * self.k, self.cell)
                    hs = self.sample(xy + nrm * side * ds[:, None])
                    top = int(np.argmax(hs))
                    wall = hs[: top + 1]
                    lo = int(np.argmax(wall > h + 0.15 * (hs[top] - h)))
                    hi = int(np.argmax(wall > h + 0.85 * (hs[top] - h)))
                    if hi > lo:
                        slope = math.degrees(math.atan((wall[hi] - wall[lo]) / ((hi - lo) * self.cell)))
                    else:  # a short, steep bank: the whole rise over its whole run ("18 m over 10 m (0 deg)" before)
                        slope = math.degrees(math.atan((hs[top] - h) / max(ds[top], self.cell)))
                    prof.append(f"{hs[top] - h:.0f} m over {ds[top]:.0f} m ({slope:.0f} deg)")
                out.append(f"    @{s:.2f}: floor {L.h[np.searchsorted(L.s, s)]:.0f} m; left bank rises {prof[0]}, right {prof[1]}")
            # a trench: the bed well below the ground just beside its valley floor (a "U valley" cut as a slot gorge
            # through a basin floor, 35-120 m deep, and nothing said so)
            fl = L.props.get("floor", 60.0)
            step = max(1, len(L.xy) // 80)
            nrm = np.gradient(L.xy, axis=0)[::step]
            nrm = np.stack([-nrm[:, 1], nrm[:, 0]], 1) / (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9)
            p = L.xy[::step]
            off = fl / 2 + max(30.0, 3 * self.cell)
            bed = self.sample(p)
            banks = np.minimum(self.sample(p + nrm * off), self.sample(p - nrm * off))
            deep = np.where(L.s[::step] > 0.15, banks - bed, 0)  # (a source is often set into its valley head)
            if L.name in getattr(self, "_cut_rivers", ()):  # (a river cutting its own valley: its sides rise at their
                # grade by design; a trench is deeper than that)
                deep = deep - float(np.clip(L.props["side"], 0.3, 3.0)) * (off - fl / 2)
            k = int(np.argmax(deep))
            if deep[k] > max(12.0, 2 * self.world["gully"]):
                out.append(f"    trench: the bed runs up to {deep[k]:.0f} m below the ground {off:.0f} m either side "
                           f"(at [{p[k, 0]:.0f}, {p[k, 1]:.0f}]; {100 * (deep > 12).mean():.0f}% of its length over 12 m)")
                self.warnings.append(f"river {L.name!r} runs in a trench up to {deep[k]:.0f} m deep at [{p[k, 0]:.0f}, "
                                     f"{p[k, 1]:.0f}]: its heights (source/through/mouth z) are below the floor around it. "
                                     f"Raise its heights there, or lower the floor (a basin's floor range)")
        if getattr(self, "rib_count", 0):
            out.append(f"ribs (automatic): {self.rib_count} spurs off the ridges")
        for (a, b), length, top in self.divides:
            out.append(f"divide (automatic) between {a} and {b}: {length:.0f} m of crest, up to {top:.0f} m")
        from . import terrain_sea
        out += terrain_sea.report(self)
        from . import terrain_volcano, terrain_rock
        out += terrain_volcano.report(self)
        from . import terrain_lines
        out += terrain_lines.report(self)
        for n, (on, gap) in sorted(getattr(self, "cut_report", {}).items()):
            why = (f"it runs over a volcano or hill, {on:.0f} m of it under its path" if on > terrain.CUT_GAP else
                   f"its bed follows the ground the rest of the design made, {gap:+.0f} m")
            out.append(f"river {n} cuts its own valley ({why} at the median): the ground beyond its valley is left as "
                       f"it was. \"valley\": {{\"cut\": false}} makes it hold the solve's low ground instead (that "
                       f"raised the land round it)")
        from . import terrain_falls
        out += terrain_falls.report(self)
        from . import terrain_forms as forms_mod
        out += forms_mod.report_water(self)
        from . import terrain_stream_water
        out += terrain_stream_water.report_flow(self)
        if getattr(self, "ground_rms", None) is not None:
            out.append(f"ground texture (measured): gentle ground varies {self.ground_rms:.2f} m rms about its ~50 m "
                       f"trend ({self.ground_before:.2f} m before the undulation, swales and hummocks; plaster-smooth "
                       f"ground is under ~0.1 m). \"ground\": {{\"undulation\", \"swales\", \"hummocks\": 0..2}} tunes it")
        rk = terrain_rock.measure(self)
        if rk and rk["face_km2"] > 0.005:  # (0.2 ha of faces gave "22472 pits per km2": noise)
            out.append(f"rock faces (measured): {rk['face_km2'] * 100:.1f} ha over 45 deg; {100 * rk['turned']:.0f}% of it "
                       f"turned over 25 deg from the face's line (buttress and couloir sides; a smooth face is ~0%); "
                       f"{rk['pits_km2']:.0f} closed pits per km2 (round hollows: rock breaks in planes, not dimples), "
                       f"roundness {rk['rounded']:.2f} (median |curvature| x cell; faceted rock ~0.6-0.9, lumpy 1.2+); "
                       f"scree aprons below the cliffs: {rk['aprons']:.1f} ha (zone \"cliff_foot\")"
                       + (f"; cliffs over 60 deg are {rk['cliff_cells']:.1f} cells across in plan (median)"
                          if rk["cliff_cells"] else ""))
            if rk["cliff_cells"] and rk["cliff_cells"] < 3:
                out.append(f"  (cliffs over 60 deg are only {rk['cliff_cells']:.1f} cells across in plan at "
                                     f"a {self.cell:.1f} m cell: too few for detail on the face itself (they render as "
                                     f"large flat facets from close by). A finer \"cell\" (e.g. {self.cell / 2:.1f}) shows "
                                     f"more, at 4x the build time)")
        for name, lk in self.lakes.items():
            if lk.get("sea"):
                continue
            out.append(f"lake {name}: level {lk['level']:.0f} m, {lk.get('area', 0) / 1e4:.1f} ha, "
                       f"deepest {lk.get('depth', 0):.0f} m, lowest shore {lk.get('freeboard', 0):+.1f} m above the water"
                       + self._dam_report(name, lk) + self._bank_report(name, lk))
        out += terrain_design_report.report(self)
        if self.spec.get("caves"):  # (walked now: the tile export takes an hour on a big level)
            from . import terrain_caves_early
            cl, cw = terrain_caves_early.early(self)
            out += cl
            for w in cw:
                if w not in self.warnings:
                    self.warnings.append(w)
        out += self._highest()
        out += self._drainage()
        out += terrain_design_report.intent(self)
        if self.warnings:
            out.append("WARNINGS:")
            out += [f"  {w}" for w in self.warnings]
        return self._in_units("\n".join(out))

    def _in_units(self, text):
        """The report is built in metres; say it in the spec's units (and say when the scale was assumed)."""
        u = self.units
        head = ""
        if u["assumed"]:
            why = f"a typical {self.world['kind'].replace('_', ' ')} level" if self.world["kind"] else "a default"
            head = (f"scale: no units given, so the frame was taken as {self.size:.0f} m across ({why}; "
                    f"1 unit = {u['mu']:.3g} m); set \"units\" or \"across\" to change it. Report in units.\n")
        if u["mu"] == 1.0 and not u["assumed"]:
            return text
        import re
        name, mu = u["name"], u["mu"]

        def num(v, area=False):
            x = float(v) / (mu * mu if area else mu)
            return f"{x:.3g}" if abs(x) < 10 else f"{x:.0f}"

        text = re.sub(r"\[(-?[\d.]+), (-?[\d.]+)\]", lambda m: f"[{num(m[1])}, {num(m[2])}]", text)
        text = re.sub(r"(-?[\d.]+) km2\b", lambda m: f"{num(float(m[1]) * 1e6, True)} sq {name}", text)
        text = re.sub(r"(-?[\d.]+) ha\b", lambda m: f"{num(float(m[1]) * 1e4, True)} sq {name}", text)
        text = re.sub(r"(-?[\d.]+) m2\b", lambda m: f"{num(float(m[1]), True)} sq {name}", text)
        text = re.sub(r"(-?[\d.]+) m\b", lambda m: f"{num(m[1])} {name}", text)
        return head + text

    def _highest(self):
        """The frame's highest ground, and whether it's something the designer placed (the export's height range showed
        an unauthored 134 m ridge in a coast of 70 m clifftops)."""
        k = int(np.argmax(self.H))
        xy, z = self.P[k], float(self.H.ravel()[k])
        line = f"highest ground: {z:.0f} m at [{xy[0]:.0f}, {xy[1]:.0f}]"
        pk = {**(self.spec.get("cols") or {}), **(self.spec.get("peaks") or {})}
        near = [n for n, (p, h) in self.points.items()
                if np.linalg.norm(p - xy) < max(1.5 * float(pk.get(n, {}).get("radius", 0)), 200 * self.k, 5 * self.cell)]
        near += [L.name for L in self.lines.values() if L.kind == "ridge"
                 and cKDTree(L.xy).query(xy)[0] < max(150 * self.k, 4 * self.cell)]
        near += [n for n, m in getattr(self, "mesas", {}).items() if np.linalg.norm(np.array(m["xy"]) - xy) < 1.3 * m["radius"]]
        near += [n for n, V in getattr(self, "volcanoes", {}).items()
                 if n not in near and np.linalg.norm(np.array(V["xy"]) - xy) < V["rc"] + max(5 * self.cell, 0.25 * (V["R"] - V["rc"]))]
        top_authored = max([h for _, h in self.points.values()] + [float(L.h.max()) for L in self.lines.values()
                                                                   if L.kind == "ridge"] + [-np.inf])
        if near:
            return [line + f" ({', '.join(near[:2])})"]
        self.warnings.append(line + " is nothing you placed" + (f", {z - top_authored:.0f} m above your highest point"
                                                             if np.isfinite(top_authored) and z > top_authored else "")
                             + ": the tilt, a frame edge or automatic divides/ribs made it; probe it, or lower it with "
                               "\"border\" or the tilt")
        return [line + " (unauthored)"]

    def _drainage(self):
        """Pits (water can't leave, not a lake) and big unauthored streams (flow gathering away from the rivers)."""
        H = np.where(np.isnan(self.water), self.H, self.water)
        base = ~np.isnan(self.water)
        base[[0, -1], :] = base[:, [0, -1]] = True
        rec, dist, levels = _receivers(H, self.cell, base)
        import fastscapelib as fs  # its priority flood (skimage's reconstruction was pathologically slow on a tilt)
        grid = fs.RasterGrid(list(H.shape), [self.cell, self.cell], fs.NodeStatus.FIXED_VALUE)
        filled = fs.FlowGraph(grid, [fs.SingleFlowRouter(), fs.PFloodSinkResolver()]).update_routes(H.copy())
        depth = np.asarray(filled).reshape(H.shape) - H  # how deep water would stand (depression fill)
        hollows = (depth > 1.0) & np.isnan(self.water)
        hollows = ndimage.binary_opening(hollows)  # specks of a cell or two aren't worth a line
        lab_h, n_h = ndimage.label(hollows)
        area = _accumulate(rec, levels, self.cell).reshape(H.shape)
        near = np.zeros(H.shape, bool)
        for L in self.lines.values():
            if L.kind == "river":
                m, _ = self._stamp(L, L.props["floor"] / 2 + 80 * self.k)
                near |= m
        stray = (area > 250_000 * self.k ** 2) & ~near & np.isnan(self.water)
        for sn, st in self.sites.items():  # water running through a pad: it floods the village (unwarned before)
            pad = np.hypot(self.X - st["xy"][0], self.Y - st["xy"][1]) <= st["radius"]
            big = pad & (area > 100_000 * self.k ** 2) & np.isnan(self.water)
            if big.any():
                self.warnings.append(f"site {sn!r}: a stream draining {_area(float(area[big].max()))} runs through the pad: "
                                     f"move the site, give the stream a river, or accept a culvert")
        lab, n = ndimage.label(stray)
        out = [f"drainage: {n_h} hollows over 1 m deep outside lakes (would hold water)"]
        if n_h:
            big = ndimage.sum(np.ones(H.shape), lab_h, range(1, n_h + 1))
            said = set()
            for k in np.argsort(-big)[:3]:
                yy, xx = np.nonzero(lab_h == k + 1)
                closed = [n for n, b in self.basins.items() if b["floor"][yy, xx].mean() > 0.5]
                if closed and closed[0] in said:
                    continue
                said.add(closed[0]) if closed else None
                if closed:
                    top = float((H[yy, xx] + depth[yy, xx]).max())
                    out.append(f"  basin {closed[0]} is enclosed: real water would rise to {top:.0f} m and spill at its "
                               f"lowest rim point; the lake keeps its own level (fine for a designed level)")
                    continue
                why = ""  # (what made it and what to change: a designer read an 8.6 m pit on an "open meadow" clifftop)
                sea = getattr(self, "sea", None)
                if sea and np.shape(sea.get("sd")) == H.shape and sea.get("cliff_asked"):
                    dsea = float(np.abs(sea["sd"][yy, xx]).min())
                    if dsea < 150:
                        why = (f": {dsea:.0f} m behind the sea cliffs, whose tops are raised to their asked height "
                               f"({sea['cliff_asked'][0]:g}-{sea['cliff_asked'][1]:g} m) above the ground the tilt "
                               "brings to the coast, so the land behind them is a bowl; lower sea.cliffs.height, raise "
                               "world.base or tilt less, or put a lake landform in it")
                out.append(f"  hollow {_area(big[k] * self.cell ** 2)}, {depth[yy, xx].max():.1f} m deep at "
                           f"[{self.xs[xx].mean():.0f}, {self.ys[yy].mean():.0f}]" + why)
        if n:
            sizes = ndimage.maximum(area, lab, range(1, n + 1))
            said = []
            for k in np.argsort(-sizes):
                yy, xx = np.nonzero(lab == k + 1)
                j = np.argmax(area[yy, xx])
                p = np.array([self.xs[xx[j]], self.ys[yy[j]]])
                if any(np.linalg.norm(p - q) < 100 * self.k for q in said):  # one stream, not three reports of it
                    continue
                said.append(p)
                out.append(f"  unauthored stream draining {_area(area[yy[j], xx[j]])} at [{p[0]:.0f}, {p[1]:.0f}]")
                if len(said) == 3:
                    break
        return out

    def export(self, out_dir, size: int | None = None, engine: str | None = None):
        """For an engine, north-up: height (float32 .npy absolute, 16-bit PNG and a Unity .raw both offset to 0 with the
        range in meta.json), an 8-bit density mask per cover layer, water, roads, sites, playable and walls masks,
        splat weights for the ground layers (tree layers are instances, not ground textures), trees.csv, and meta.json
        with everything placed (sites with their planes, passes, routes, rivers with their water, fords, lakes).
        `size` resamples to an engine grid along the longer side (Unity 257/513/1025/2049: 2^n + 1; Unreal 505/1009/
        2017); `engine` "unity" picks the next 2^n + 1 when no size is given."""
        from PIL import Image
        from . import terrain_design_cover
        out = Path(out_dir)
        (out / "masks").mkdir(parents=True, exist_ok=True)
        ny, nx = self.H.shape
        n = max(nx, ny)
        if not size and engine == "unity":
            size = 2 ** math.ceil(math.log2(max(n - 1, 32))) + 1
        k = (size - 1) / (n - 1) if size else 1.0
        # engines want square heightmaps (Unity 2^n+1): a non-square frame is padded on its short side with the edge
        # continued, and meta.json says which part is the level
        pad = (n - ny, n - nx) if size else (0, 0)
        shape = (size, size) if size else (ny, nx)

        def grid(a, order=1):
            a = a[::-1].astype(np.float32)
            if size and any(pad):
                a = np.pad(a, ((0, pad[0]), (0, pad[1])), mode="edge")
            if not size:
                return a
            yy, xx = np.meshgrid(np.linspace(0, n - 1, shape[0]), np.linspace(0, n - 1, shape[1]), indexing="ij")
            return ndimage.map_coordinates(a, [yy, xx], order=order, mode="nearest").astype(np.float32)

        H = grid(self.H, 3)
        lo, hi = float(H.min()), float(H.max())
        np.save(out / "height.npy", H)
        q = np.round((H - lo) / max(hi - lo, 1e-6) * 65535).astype(np.uint16)
        Image.fromarray(q).save(out / "height.png")
        # Unity's RAW import: 16-bit little-endian ("Windows" byte order), first row = the south edge (z = 0)
        q[::-1].astype("<u2").tofile(out / "height.raw")

        def mask(name, m):
            Image.fromarray((np.clip(grid(m), 0, 1) * 255).astype(np.uint8)).save(out / "masks" / f"{name}.png")

        for name, m in self.cover.items():
            mask(name, m)  # densities (for trees, detail), each 0..1 on its own
        # splat weights for the ground layers, painted in order, each over what's below; "ground" is what's left; they
        # sum to 1. Tree layers are instances (trees.csv) and stay out: a forest's weight had painted its ground green
        ground = [nm for nm in self.cover if not terrain_design_cover.tree_kind(self, nm)]
        rest = np.ones(self.X.shape)
        weights = {}
        for name in reversed(ground):
            weights[name] = self.cover[name] * rest
            rest = rest * (1 - self.cover[name])
        weights["ground"] = rest
        order = ground + ["ground"]
        for i in range(0, len(order), 4):
            chans = [grid(weights[nm]) for nm in order[i:i + 4]]
            while len(chans) < 4:
                chans.append(np.zeros_like(chans[0]))
            rgba = (np.clip(np.stack(chans, -1), 0, 1) * 255).astype(np.uint8)
            Image.fromarray(rgba, "RGBA").save(out / f"splat{i // 4}.png")
        inst = terrain_design_cover.trees(self)
        with open(out / "trees.csv", "w") as f:
            f.write("x,y,z,kind,layer\n")
            layers = getattr(self, "tree_layers", {})
            for x, y, z, li in inst:
                nm, kind = layers.get(int(li), ("", ""))
                f.write(f"{x:.2f},{y:.2f},{z:.2f},{kind},{nm}\n")
        dry = np.isnan(self.water)
        mask("water", ~dry)
        roads = self.masks.get("routes", np.zeros(self.X.shape))
        mask("roads", roads)
        mask("sites", self.masks.get("sites", np.zeros(self.X.shape)))
        walls, inside = np.zeros(self.X.shape), np.zeros(self.X.shape, bool)
        for W in self.walls.values():
            inside |= W["inside"]
            s = ndimage.distance_transform_edt(~W["inside"]) * self.cell
            walls = np.maximum(walls, (s > 0) & (s <= W["band"] + self.cell))
        gates = np.zeros(self.X.shape, bool)
        for p in self.passes.values():
            gates |= p["corridor"]
        ways = gates | (roads > 0.5)  # the way in is the road as built, not only the pass's straight notch
        walkable = dry & (self._slope() <= 45)
        # playable: inside the walls (and along the roads and passes that lead in); with no walls, walkable dry ground
        playable = (inside | ways) if self.walls else (walkable | ways)
        mask("playable", playable & (dry | ways))
        mask("walls", walls * ~ways)
        cell = self.cell / k
        (x0, y0), (x1, y1) = self.spec["extent"]
        span = (n - 1) * self.cell  # the square the grid covers (padded frames reach past the level)
        rivers = {}
        from . import terrain_stream_water
        wet = terrain_stream_water.wet_design(self) if getattr(self, "river_water_lines", None) else {"rivers": {}, "pools": []}
        for nm, L in self.lines.items():
            if L.kind != "river":
                continue
            rw = getattr(self, "river_water_lines", {}).get(nm)
            pts = [[*map(float, xy), float(h)] for xy, h in zip(L.xy[::4], L.h[::4])]
            river = {"bed_xyz": [[round(v, 2) for v in p] for p in pts]}
            if rw is not None:
                # the FULL width the water covers as the ground holds it (river_water_lines' width is a half width:
                # meta gave that, and a game trimming its water to +- width / 2 cut real water; pushieworld note 126),
                # the widest of the samples each written point stands for
                ww = ndimage.maximum_filter1d(np.asarray(wet["rivers"].get(nm, 2 * np.asarray(rw["width"])), float), 5,
                                              mode="nearest")
                ww = np.where(np.asarray(rw["width"]) > 0, ww, 0.0)
                river["water"] = [[round(float(x), 2), round(float(y), 2), round(float(z), 2), round(float(w), 2)]
                                  for (x, y), z, w in zip(rw["xy"][::4], rw["level"][::4], ww[::4])]
                q = np.asarray(wet.get("flow", {}).get(nm, np.full(len(rw["xy"]), np.nan)), float)
                if np.isfinite(q).any():  # (the flow the channel carries at its design level: pushieworld note 121)
                    qm = -ndimage.maximum_filter1d(-np.where(np.isfinite(q), q, np.inf), 5, mode="nearest")
                    river["flow_m3s"] = [None if not np.isfinite(v) else round(float(v), 2) for v in qm[::4]]
                    river["design_flow_m3s"] = round(float(np.nanpercentile(q, 10)), 2)
            rivers[nm] = river
        falls = [{**f, "pool": {**f["pool"], "wet_radius": r}} if f.get("pool") and r is not None else f
                 for f, r in zip(getattr(self, "falls", None) or [], wet["pools"] or [None] * len(self.falls or []))]
        from .terrain_sea import cliff_feet
        from . import terrain_lines
        meta = {"extent": self.spec["extent"], "cell": cell, "height_range": [lo, hi], "size": [H.shape[1], H.shape[0]],
                "north_up": True, "pixel_0_0": "north-west corner",
                "height_npy": "float32, absolute metres, north-up",
                "height_png": "16-bit, north-up, offset to 0: height = lo + value / 65535 * (hi - lo)",
                "unity": {"raw": "height.raw", "resolution": H.shape[0], "depth": 16, "byte_order": "Windows (little-endian)",
                          "flip_vertically": False, "rows": "first row is the south edge",
                          "terrain_size": [span, hi - lo, span], "position": [x0, lo, y1 - span],
                          "axes": "Unity x = east, z = north, y = up"},
                "level_pixels": [int(round((nx - 1) * k)) + 1, int(round((ny - 1) * k)) + 1],
                "padded": "the level is the top-left part; the rest continues its edges" if any(pad) else "",
                "splat": {f"splat{i // 4}.png": order[i:i + 4] for i in range(0, len(order), 4)},
                "masks": {"water": "open water", "roads": "road beds", "sites": "site pads", "walls": "wall faces",
                          "playable": "inside the walls and along the ways in" if self.walls else
                          "dry ground a person can walk (45 deg or less) and the roads",
                          **{nm: "density 0..1" for nm in self.cover}},
                "trees": "trees.csv (x, y, z, kind, layer), world metres; tree layers aren't in the splats",
                "rivers": rivers, "rivers_water": "per point [x, y, water surface z, water width m]: the full width the "
                                                  "water covers as the ground holds it, centred on the point (0 where "
                                                  "it's dry or in a lake); flow_m3s per point (null over a fall), the flow "
                                                  "the channel as built carries at that level (Manning), and "
                                                  "design_flow_m3s (its 10th percentile: what the river holds without "
                                                  "spilling): size a water simulation's sources by it",
                **({"falls": falls, "falls_note": __import__("hifipushie.terrain_falls", fromlist=["x"]).META_NOTE}
                   if getattr(self, "falls", None) else {}),  # (waterfalls, terrain_falls)
                "fords": {nm: {"at": f["xy"], "river": f["river"], "width": f["width"], "depth": f["depth"],
                               "bed": round(self.height(f["xy"]), 2)} for nm, f in getattr(self, "fords", {}).items()},
                "cover": {nm: (self.spec.get("cover") or {}).get(nm, {}).get("type", nm) for nm in self.cover},
                "lakes": {nm: {"level": lk["level"], "at": lk["xy"], **({"sea": True} if lk.get("sea") else {})}
                          for nm, lk in self.lakes.items()},
                "cliff_feet": cliff_feet(self),  # (sea cliffs: where to set caves or notches against the face)
                "lines": terrain_lines.meta(self),  # hedges, walls...:
                # per piece [x, y, ground z] points; the engine places wall and fence meshes along them
                "sites": {nm: {"at": st["xy"], "level": st["level"], "radius": st["radius"], "fall": st.get("fall", 0.0),
                               "falls_toward": st.get("toward", [0, 0]),
                               "plane": "z = level - fall * ((x - at.x) * falls_toward.x + (y - at.y) * falls_toward.y)",
                               **({"prop": {**st["prop"], "xyz": [*st["xy"], round(self.height(np.array(st["xy"])), 3)],
                                            "yaw_note": "compass bearing the prop faces: 0 north, 90 east"}}
                                  if st.get("prop") else {})}
                          for nm, st in self.sites.items()},
                "passes": {nm: {"at": p["xy"], "saddle": round(self.height(np.array(p["xy"])), 2), "width": p["width"]}
                           for nm, p in self.passes.items()},
                "routes": {nm: {"width": L.props["width"], "points_xyz": np.c_[L.xy, L.h][::2].round(2).tolist()}
                           for nm, L in self.routes.items()}}
        (out / "meta.json").write_text(json.dumps(meta, indent=1))
        return out
