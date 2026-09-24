"""Paint layers as a shader-node program for the Blender scene (scene.py, blender_scene.py).

The split: this code measures what needs the exact field or the geometry, per vertex, as mesh attributes
(ao, sky, curvature, thickness, distances to elements for "near", and any generator Blender can't do natively
yet: path, cells, tiles, weave, blurred entries, mirrored ".L" layers); Blender's nodes do the compositing
(noise, ramps, facing, axis, breakup, levels, blend modes, opacity, colour and the other channels), per pixel.

Positions and normals the masks see are the "wpos"/"wnrm" attributes: world space for scene parts, and for a
prefab's parts where its bake instance stands (as the export bakes it), so every instance shows the same paint.

Noise: our fbm and Blender's Noise Texture have different value distributions, and ranges in specs are tuned to
ours, so Blender's is remapped through a quantile curve (noise_quantiles.json) before any range is applied.

Round trip: a spec-level layer's opacity and colour, and the main numbers of its own mask entries (ranges,
noise scale, within, axis from/to), are named Value / RGB nodes ("hp:<json path>"); scene.pull reads them back.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import paint
from .spec import SpecError

NATIVE = {"facing", "axis", "noise", "ao", "sky", "thickness", "cavity", "near", "mask", "tiles", "cells"}
QUANTILES = json.loads(Path(__file__).with_name("noise_quantiles.json").read_text())


class _Compiler:
    def __init__(self, spec: dict):
        self.spec = spec
        self.inputs = set()  # field inputs needed: ao, sky, curvature, thickness
        self.fallbacks = {}  # attr -> ("gen", layer, stack name, entry, tag) | ("layer", name) | ("dist", layer, near)
        self.where = {}  # attr -> the parts it's measured on
        self.parts = ()  # the parts of the layer being compiled

    def attr(self, kind, *args, key=None, parts=()) -> str:
        """A measured input's attribute name. key: what makes two of them the same measurement (a material's
        confining "near" is on every one of its sub-layers: measure it once); parts: where it's needed."""
        key = hashlib.sha1(json.dumps([kind, *(args if key is None else key)], sort_keys=True,
                                      default=str).encode()).hexdigest()[:10]
        name = f"g_{key}"
        if name not in self.fallbacks:
            self.fallbacks[name] = (kind, *args)
            self.where[name] = set()
        self.where[name] |= set(parts)
        return name

    def stretch(self, st):
        """[dx, dy, dz, factor], or ["grain", factor, seed attr] along each vertex's element (paint._stretch)."""
        if not st:
            return None
        if st.get("dir") == "element":
            self.inputs |= {"grain", "grain_seed"}
            return ["grain", float(st.get("factor", 6.0)), "grain_seed"]
        d = np.asarray(st.get("dir", [0, 0, 1]), float)
        return [*(d / np.linalg.norm(d)), float(st.get("factor", 6.0))]

    def entry(self, e: dict, name: str, tag: str, path: list | None, layer: str | None = None) -> dict:
        """One stack entry as a node program entry. name: the stack's name as paint's _stack sees it (a nested
        mask's is its parent entry's tag); layer: the top-level layer it belongs to. path: its place in the spec
        (to expose its numbers)."""
        layer = layer or name
        gen = next((g for g in paint.GENERATORS if g in e), None)
        out = {"blend": e.get("blend", "multiply"), "weight": float(e.get("weight", 1.0)),
               "post": {k: e[k] for k in ("breakup", "levels", "invert") if k in e}, "expose": {}}
        if gen is None:
            if "blur" in e:
                raise NotImplementedError("blur on the mask so far")
            return {**out, "gen": None}
        if gen not in NATIVE or "blur" in e:
            raw = {k: v for k, v in e.items() if k not in ("breakup", "levels", "invert", "blend", "weight")}
            # a path is seated by its tag; every other generator is the same wherever it's written
            key = (layer, name, raw, tag) if gen == "path" else (raw,)
            return {**out, "gen": "input", "attr": self.attr("gen", layer, name, raw, tag, key=key, parts=self.parts),
                    "range": None}
        if gen == "facing":
            from .realism import direction
            lo, hi = e.get("range", [0.0, 0.7])
            if path:
                out["expose"] = {"range0": path + ["range", 0], "range1": path + ["range", 1]}
            if e["facing"] == "element":  # |normal . the element's axis|: a per-vertex vector attribute
                self.inputs.add("grain")
                return {**out, "gen": "facing", "dir": "grain", "range": [lo, hi]}
            return {**out, "gen": "facing", "dir": np.asarray(direction(self.spec, e["facing"], name), float).tolist(),
                    "range": [lo, hi]}
        if gen == "axis":
            ax = e["axis"]
            if "bone" in ax:
                from .spec import expand_mirror, resolve_point
                s = expand_mirror(self.spec)
                b = s["bones"][ax["bone"]]
                a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
                d = bb - a
                dvec, off = d / (d @ d), -(a @ d) / (d @ d)
                rng = [float(ax.get("from", 0.0)), float(ax.get("to", 1.0))]
            else:
                d = np.asarray(ax.get("dir", [0, 0, 1]), float)
                dvec, off = d / np.linalg.norm(d), 0.0
                rng = [float(ax["from"]), float(ax["to"])]
                if path:
                    out["expose"] = {"range0": path + ["axis", "from"], "range1": path + ["axis", "to"]}
            return {**out, "gen": "axis", "dir": dvec.tolist(), "offset": float(off), "range": rng}
        if gen == "noise":
            nz = e["noise"]
            st = nz.get("stretch")
            if path:
                out["expose"] = {"scale": path + ["noise", "scale"], "range0": path + ["noise", "range", 0],
                                 "range1": path + ["noise", "range", 1]}
            return {**out, "gen": "noise", "scale": float(nz.get("scale", 0.03)), "octaves": int(nz.get("octaves", 3)),
                    "seed": int(nz.get("seed", 0)), "warp": float(nz.get("warp", 0.0)),
                    "stretch": self.stretch(st),
                    "range": list(nz.get("range", [0.45, 0.6]))}
        if gen == "tiles":  # laid on the three axis planes, u along the direction, w across (paint._planar)
            t = e["tiles"]
            planes = []
            for ax in range(3):
                a_ = paint._AXES[ax]
                dd = np.asarray(t.get("dir") if t.get("dir") is not None else paint._IN_PLANE[ax], float)
                dd = dd - (dd @ a_) * a_
                if np.linalg.norm(dd) < 0.3:
                    dd = np.asarray(paint._IN_PLANE[ax], float)
                dd = dd / np.linalg.norm(dd)
                planes.append([dd.tolist(), np.cross(a_, dd).tolist()])
            L, H = (float(x) for x in t.get("size", [0.2, 0.1]))
            gap = float(t.get("gap", 0.005))
            return {**out, "gen": "tiles", "planes": planes, "size": [L, H], "gap": gap,
                    "bevel": float(t.get("bevel", 0.5 * gap)), "offset": t.get("offset", 0.5),
                    "seed": int(t.get("seed", 0)), "mode": t.get("mode", "gaps")}
        if gen == "cells":
            c = e["cells"]
            mode = c.get("mode", "edges")
            st = c.get("stretch")
            return {**out, "gen": "cells", "scale": float(c.get("scale", 0.03)), "mode": mode,
                    "jitter": float(c.get("jitter", 1.0)), "seed": int(c.get("seed", 0)),
                    "stretch": self.stretch(st),
                    "range": list(c.get("range", {"edges": [0.15, 0.0], "distance": [0.35, 0.1], "id": [0.0, 1.0]}[mode]))}
        if gen in ("ao", "sky", "thickness"):
            self.inputs.add(gen)
            if path:
                out["expose"] = {"range0": path + [gen, 0], "range1": path + [gen, 1]}
            return {**out, "gen": "input", "attr": gen, "range": [float(e[gen][0]), float(e[gen][1])]}
        if gen == "cavity":
            self.inputs.add("curvature")
            r0, r1 = e.get("radius", [0.03, 0.006])
            return {**out, "gen": "input", "attr": "curvature", "sign": -1.0 if e["cavity"] == "concave" else 1.0,
                    "range": [1 / r0, 1 / r1]}
        if gen == "near":
            within, soft = float(e.get("within", 0.0)), max(float(e.get("soft", 0.01)), 1e-6)
            if path:
                out["expose"] = {"within": path + ["within"]}
            return {**out, "gen": "near", "attr": self.attr("dist", layer, e["near"], key=(e["near"],), parts=self.parts),
                    "within": within, "soft": soft}
        if gen == "mask":
            sub = e["mask"]
            return {**out, "gen": "mask", "entries": [self.entry(s, tag, paint._tag(tag, i), None, layer)
                                                     for i, s in enumerate(sub)]}
        raise SpecError(f"paint {name!r}: unknown generator {gen!r}")

    def layer(self, name: str, ly: dict) -> dict:
        ps = ly.get("part", "body")
        self.parts = ("*",) if ps == "*" else tuple([ps] if isinstance(ps, str) else ps)
        own = "_of" not in ly  # a spec-level layer (not a material's sub-layer): its numbers are exposed
        stack = [{g: ly[g], **{k: ly[k] for k in paint.PARAMS.get(g, ()) if k in ly}} for g in paint.GENERATORS
                 if g in ly and g != "mask"]
        tags = [None] * len(stack)
        paths = [["paint", name] if own else None] * len(stack)
        if "mask" in ly:
            stack += ly["mask"]
            tags += list(range(len(ly["mask"])))
            paths += [["paint", name, "mask", i] if own else None for i in range(len(ly["mask"]))]
        channels = {c: (paint.colour(ly[c]).tolist() if c == "color" else float(ly[c])) for c in paint.CHANNELS if c in ly}
        expose = {"opacity": ["paint", name, "opacity"]} if own else {}
        if own and "color" in ly:
            expose["color"] = ["paint", name, "color"]
        if name.endswith(".L"):  # mirrored: the whole mask measured here (max of the point and its mirror)
            entries = [{"gen": "input", "attr": self.attr("layer", name, parts=self.parts), "range": None, "blend": "multiply",
                        "weight": 1.0, "post": {}, "expose": {}}]
        else:
            try:
                entries = [self.entry(e, name, paint._tag(name, t), p) for e, t, p in zip(stack, tags, paths)]
            except NotImplementedError:
                entries = [{"gen": "input", "attr": self.attr("layer", name, parts=self.parts), "range": None, "blend": "multiply",
                            "weight": 1.0, "post": {}, "expose": {}}]
        parts = ly.get("part", "body")
        return {"name": name, "parts": parts if isinstance(parts, list) else [parts], "channels": channels,
                "height": float(ly.get("height", 0.0)),
                "opacity": float(ly.get("opacity", 1.0)), "entries": entries, "expose": expose}


def compile(spec: dict) -> dict:
    """{"layers": [...], "inputs": [field inputs], "fallbacks": {attr: what}, "quantiles": ...}."""
    c = _Compiler(spec)
    layers = [c.layer(n, ly) for n, ly in paint.layers(spec).items()] if spec.get("paint") else []
    # per part, the scalar inputs its layers read, packed three to a vector attribute (hp0, hp1, ...)
    need: dict = {}
    for ly in layers:
        used = sorted(_attrs(ly["entries"]))
        for p in ly["parts"]:
            need.setdefault(p, [])
            need[p] += [a for a in used if a not in need[p]]
    if "*" in need:
        star = need.pop("*")
        for p in list(need) + [p for p in spec.get("parts") or {} if p not in need]:
            need.setdefault(p, [])
            need[p] += [a for a in star if a not in need[p]]
    packing = {p: {a: [f"hp{i // 3}", i % 3] for i, a in enumerate(attrs)} for p, attrs in need.items()}
    return {"layers": layers, "inputs": sorted(c.inputs), "fallbacks": c.fallbacks, "quantiles": QUANTILES,
            "where": {k: sorted(v) for k, v in c.where.items()}, "packing": packing}


def _attrs(entries: list) -> set:
    out = set()
    for e in entries:
        if e.get("attr"):
            out.add(e["attr"])
        if (e.get("stretch") or [None])[0] == "grain":  # each element's own piece of the pattern
            out.add(e["stretch"][2])
        if e.get("gen") == "mask":
            out |= _attrs(e["entries"])
    return out


def measure(spec: dict, prog: dict, pos: np.ndarray, nrm: np.ndarray, part: np.ndarray, names: list[str],
            voxel: float, streams: dict, what: str = "all", given: dict | None = None) -> dict:
    """Every per-vertex input the program needs, at these points (world positions and normals; part = index
    into names, the model's part names): {attr: (n,) float32}. what: "field" (ao, sky, curvature, thickness:
    they depend on the geometry only), "masks" (the measured masks and distances) or "all". given: inputs
    measured elsewhere (Cycles' ao and sky), used as they are, by masks too."""
    import sys
    import time
    from .surface import Points
    pts = Points(spec, pos, nrm, part, names, voxel, cache=dict(given or {}), streams=streams)
    times = {}
    out = {}
    for k in (prog["inputs"] if what in ("all", "field") else []):
        if k in (given or {}):
            continue
        t = time.time()
        out[k] = pts.get(k).astype(np.float32)
        times[k] = time.time() - t
        print(f"[measure] {k}: {times[k]:.1f}s ({len(pos)} points)", file=sys.stderr, flush=True)
    layers = paint.layers(spec)
    for attr, fb in (prog["fallbacks"].items() if what in ("all", "masks") else []):
        t = time.time()
        kind = fb[0]
        val = np.zeros(len(pos), np.float32)
        ps = prog["where"].get(attr) or ["*"]
        ps = names if "*" in ps else ps
        idx = np.flatnonzero(np.isin(part, [names.index(p) for p in ps if p in names]))
        if kind == "dist":
            _, lname, near = fb
            val[idx] = _distance(spec, lname, near, pos[idx])
        else:
            lname = fb[1]
            ly = layers[lname]
            if kind == "gen":
                _, lname, sname, e, tag = fb
            if len(idx):
                view = paint._View(pts, idx)
                if kind == "layer":
                    val[idx] = paint.layer_mask(spec, lname, ly, view)
                else:
                    gen = next(g for g in paint.GENERATORS if g in e)
                    g = paint._generate(spec, sname, gen, e, tag, view)
                    if "blur" in e:
                        g = paint._blurred(lambda v: paint._generate(spec, sname, gen, e, tag, v), view,
                                           float(e["blur"]), g)
                    val[idx] = g
        out[attr] = val
        dt = time.time() - t
        times[f"{fb[0]}:{fb[1]}"] = times.get(f"{fb[0]}:{fb[1]}", 0.0) + dt
        print(f"[measure] {fb[0]} {fb[1]}: {dt:.1f}s", file=sys.stderr, flush=True)
    measure.times = times
    return out


def _distance(spec: dict, lname: str, near, pos: np.ndarray) -> np.ndarray:
    """Distance to the named elements' own surfaces (as paint's near measures it, before within/soft)."""
    from . import sdf
    from .spec import compile_prims
    want = [near] if isinstance(near, str) else list(near)
    prims = {p.name: p for p in compile_prims(spec)}
    from .assemble import select
    from .spec import expand_mirror
    asked = set(want)
    want = [w for w in select(expand_mirror(spec), want) if w in prims or w in asked]
    for w in list(want):  # kit names
        if w in (spec.get("kits") or {}) and w not in prims:
            stem, sfx = (w[:-2], w[-2:]) if w.endswith((".L", ".R")) else (w, "")
            want.remove(w)
            want += [n for n, p in prims.items() if n.startswith(stem + "_") and n.endswith(sfx)
                     and p.kind in sdf.SDF and p.kind != "shell" and p.op == "add"]
    missing = [w for w in want if w not in prims]
    if missing:
        raise SpecError(f"paint {lname!r}: no bone or blob {missing}")
    d = np.full(len(pos), np.inf)
    for w in want:
        p = prims[w]
        d = np.minimum(d, sdf.SDF[p.kind](pos, p.params))
    return d
