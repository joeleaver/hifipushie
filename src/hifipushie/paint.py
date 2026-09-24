"""Paint: colour and surface channels laid on the built surface, evaluated per point: every mesh vertex in look,
every texel in export_asset.

spec["paint"] = {name: layer, ...}: layers apply in order, each over the colour so far (every part starts
from its clay colour, spec["parts"][p]["color"]). Paint never changes geometry, so repainting doesn't rebuild.

layer = {"color": [r, g, b] (0..1, sRGB, as you'd pick it) | "#rrggbb", "roughness", "metallic", "specular": 0..1,
         (any of these channels; a layer changes only the ones it gives), "opacity": 0..1 (1),
         "part": name | [names] | "*" (default "body"), "height": m (relief, see below), plus any of the masks
         below as flat keys (multiplied together) and/or a "mask" stack (below). No mask = the whole part.}
Each part starts from spec["parts"][p]: "color" (clay palette), "roughness" (0.6), "metallic" (0), "specular"
(0.5 = the usual 4% reflectance of skin, cloth, plastic). These show in exported game assets (export_asset), not
in the clay views: wet lips roughness 0.2, skin 0.5-0.6, cloth 0.8-0.9 with specular 0.3, metal buckles
metallic 1 with roughness 0.3, eyes roughness 0.05 with specular 0.7.

Masks (generators, each 0..1 per point):
  path:    surface addresses exactly as for strokes ({"bone", "t", "side", "around"} or {"at", "offset", "dir"},
           later points inheriting), with "width" (half-width, m; a number or one per control point) and
           "profile": "flat" (default: solid with a soft rim) | "soft" | "round" | "sharp". One point = a spot.
           "repeat" and "scatter" work as for strokes (spots, stripes, freckles). Paint doesn't print through
           to the far side of a thin part (it only covers skin facing the way the path's skin faces).
  near:    [element names] (bones, blobs, kit output such as "face_eye.L", "hand_f2_3.L", or a kit's name for
           all it generates, e.g. "hand.L"): skin within "within"
           (m, default 0) of those primitives' own surfaces, fading over "soft" (m, 0.01) beyond. A primitive's
           own surface is inside the blended skin, so "within" ~ the blend radius covers its whole footprint.
  facing:  [x, y, z]: by how much the skin faces that way (normal . dir), ramping from "range"[0] to "range"[1]
           (default [0, 0.7]). [0, 0, 1] with a dark colour darkens the back; [0, 0, -1] lightens the belly
           (countershading). "element": along the point's own element's long axis, either way (|normal . axis|):
           the cut ends of logs, beams and boards (end grain).
  axis:    {"dir": [x, y, z], "from": a, "to": b} ramps 0 -> 1 as position . dir goes from a to b (world metres),
           or {"bone": name, "from": t0, "to": t1} along a bone (0 at its start joint, 1 at its end; outside the
           range it clamps): tail tips, gloved hands, socks, fading limbs. It ramps across the whole part (the
           feet lie past a forearm's end too): confine it with "near", e.g. {"near": ["forearm.L", "hand.L"],
           "within": 0.02, "axis": {"bone": "forearm.L", "from": 0.7, "to": 1}} for a glove.
  cavity:  "concave" | "convex", "radius": [r0, r1] (m, default [0.03, 0.006]): zero where the surface is
           curved gentler than radius r0 (mean curvature), full where tighter than r1. Dirt in creases,
           light on ridges and knuckles. Depends a little on the build resolution.
  noise:   {"scale": m (feature size, 0.03), "range": [lo, hi] (0.45, 0.6), "octaves": 3, "seed": 0}: fractal
           noise thresholded softly between lo and hi. Mottling, blotches, patches; narrow ranges give crisp
           patches, wide ones soft variation. Combine with other masks to confine it.
  ao:      [a, b]: ambient occlusion (1 open, 0 enclosed, all parts occluding each other) ramped 0 at a to 1 at b,
           e.g. [0.95, 0.6]: 1 in armpits, under the jaw, where clothes meet skin. Grime, dirt, darkening.
  sky:     [a, b]: openness to the sky above (1 open, 0 under a roof, eave, table or overhang), reaching far
           beyond AO. [0.6, 0.2] = sheltered (dust, cobwebs, dry dirt under eaves); [0.5, 0.9] = exposed
           (rain-washed, sun-bleached, moss and lichen on tops, snow).
  thickness: [a, b] (m): how far the part goes on behind the skin, e.g. [0.04, 0.012]: 1 on ears, fingers, the
           nose wings (thin, backlit: reddish for subsurface later). Thick bodies read as ~0.08 * model size.
  cells:   {"scale": m (cell size, 0.03), "mode": "edges" | "distance" | "id", "jitter": 0..1 (1), "seed",
           "range", "stretch"}: 3D Voronoi. edges = F2-F1, 0 on the borders (default range [0.15, 0]: lines
           between cells: scales, plates, cracked skin); distance = from each cell's centre (range [0.35, 0.1]
           = a bump per cell: warts, pebbles); id = a random 0..1 per cell (colour jitter, patchy scales).
  random:  {"range": [lo, hi] (default [0, 1]), "seed"}: one random 0..1 value per element (each book, board,
           stone, log and array copy its own), ramped between lo and hi: a narrow range is a threshold, so
           layers stacked with rising ones ([0.25, 0.26], [0.5, 0.51], [0.75, 0.76], each over the last) give a
           quarter of the books on a shelf each colour; a wide range with low opacity jitters every board's tone. A prefab's instances
           share one bake, so they share their values; make copies differ with an array inside the prefab.
  tiles:   {"size": [along, across] (m), "gap" (m), "offset": 0.5 | "random" (row stagger), "dir", "seed",
           "mode": "gaps" (1 in the joints, fading over "bevel") | "bevel" (0 at a joint rising to 1: a tile's
           rounded face, for height) | "id" (random per tile)}: bricks, planks, flagstones, shingles.
  weave:   {"scale": thread spacing (m), "dir"}: plain weave, 1 on the crown of the upper thread (height, shading).
           Threads need ~4 texels (or vertices) across to show; finer ones fade to an even mid value.
           tiles and weave are 2D patterns laid on the three axis planes, blended by the normal (triplanar).
  noise also takes "warp" (0..2: the lookup displaced by another noise: torn, swirly grunge instead of round
           blobs) and "stretch": {"dir": [x,y,z], "factor": 6} (features that much longer that way: streaks,
           drips with [0,0,1], wood grain, fur direction). "dir": "element" stretches along each point's own
           element (a log's, a leg's, a board's long axis) and gives every element its own piece of the
           pattern: grain that follows each piece of a chair. Noise and cells are solid 3D: no UV seams.

Materials: {"material": "cloth" | "leather" | "wood" | "planks" | "brick" | "stone" | "metal" | "rust" | "moss", ...}
expands into ready-made layers (see MATERIALS below): start there, then add your own layers on top.

Mask stack: "mask": [entry, ...] builds a mask in steps, after any flat keys above (which multiply). Each entry
is one generator (any of the keys above, with its parameters inside the entry, e.g. {"path": [...], "width":
0.01} or {"ao": [0.95, 0.6]}, or {"mask": [...]} for a nested stack), combined with the mask so far by
  "blend": "multiply" (default) | "add" | "subtract" | "min" | "max" | "screen" | "overlay" | "replace",
  "weight": 0..1 (1): how much of the blend to apply.
The first generator starts the mask (its blend is ignored). Any entry may also take, applied to its own value
before blending (or, in an entry with no generator, to the mask so far):
  "breakup": amount | {"amount": 0.5, "scale": 0.03, "sharpness": 0.5, "octaves", "seed"}: noise shifts the
           threshold, so the mask is eaten into irregularly and crisply rather than faded. This is what turns
           cavity/ao/facing into weathering (see the recipes).
  "levels": [lo, hi] or [lo, hi, gamma]: remap lo..hi to 0..1 (contrast; gamma > 1 grows the mask).
  "invert": true.
  "blur": m: average over a disc of that radius across the surface. Only points near a change are resampled,
           but it evaluates the blurred part 12 times there: blur cheap generators (path, near, noise).

Recipes (on their own layers, usually one colour/roughness each):
  edge wear   {"cavity": "convex", "radius": [0.05, 0.012], "breakup": {"amount": 0.35, "scale": 0.012,
              "sharpness": 0.7}}: pale chipped skin on brows, knuckles, nose; bare metal on armour edges.
  grime       [{"ao": [0.55, 0.3], "breakup": {"amount": 0.3, "scale": 0.04}},
              {"cavity": "concave", "radius": [0.04, 0.01], "blend": "max"}]: dirt in folds and occluded places.
              AO is broad (it reaches ~2% of the model size): a whole face between brow, cheeks and nose, or arms
              close to the body, read 0.4-0.7. Keep grime to ao < ~0.5 and let tight cavity do the creases;
              check the mask with look(paint_layer=...) and tighten the range rather than lowering opacity.
  plate/tone  per-cell tone jitter {"cells": {"scale": s, "mode": "id", "range": [0.3, 1]}} at the scales' own
              size reads as skin; crisp noise blotches (narrow noise range) read as camouflage.
  dust, moss  [{"facing": [0, 0, 1], "range": [0.3, 0.9], "breakup": 0.4}, {"ao": [0.5, 0.9]}]: on top
              surfaces, not in the sheltered ones.
  cloth grunge [{"noise": {"scale": 0.05, "warp": 1.2, "range": [0.45, 0.75]}}, {"ao": [0.9, 0.5],
              "blend": "screen"}]; drips: {"noise": {"scale": 0.02, "stretch": {"dir": [0,0,1], "factor": 8},
              "range": [0.6, 0.75]}} times an "axis" band.
  scales      {"cells": {"scale": 0.02}} with "height": -0.001 (grooves between them); warts: cells "distance"
              with "height": 0.002, confined by noise.

Height: a layer's "height": m (+ out of the surface) times its mask adds relief without geometry. In exports
(export_asset) it goes into the height map and tilts the normal map at texel resolution: pores, scales, weave.
look shows it only in the shading (the vertex normals tilt), at the build's vertex spacing, so judge fine relief
in close-ups with shading="raking", and in the export's preview. A layer may have height and no colour.

Feedback: look(paint_layer="name") shows that layer's final mask in false colour (purple 0, yellow 1). The
coverage numbers count only visible skin (not what's buried under clothes).

Symmetry: a layer named ".L" is mirrored (its masks, noise included, evaluated at the vertex and at its mirror
image, whichever is stronger); a centre-named layer isn't, so asymmetric markings are plain names. AO,
cavity and thickness are always the point's own.

Colour detail can't be finer than the mesh in look: about one voxel (see look's info line); exports paint every
texel. Judge colour with look(shading="flat") (unlit colour) as well as the clay views.
"""

from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from .noise import _hash, fbm  # noqa: F401  (fbm is used by materials and tests too)
from .spec import SpecError

MIRROR = np.array([-1.0, 1.0, 1.0])
CHANNELS = ("color", "roughness", "metallic", "specular")
VERSION = 3  # bump when painting output changes, so cached painted meshes are redone


def colour(c, what: str = "color") -> np.ndarray:
    """sRGB 0..1 triple from [r, g, b] or "#rrggbb"."""
    if isinstance(c, str):
        s = c.lstrip("#")
        if len(s) != 6:
            raise SpecError(f"{what}: {c!r} isn't #rrggbb")
        return np.array([int(s[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    v = np.asarray(c, float)
    if v.shape[-1] < 3 or np.any(v[:3] < 0) or np.any(v[:3] > 1):
        raise SpecError(f"{what}: {c!r} isn't [r, g, b] in 0..1")
    return v[:3]


GENERATORS = ("path", "near", "facing", "axis", "cavity", "noise", "cells", "tiles", "weave", "ao", "thickness", "sky",
              "random", "mask")
PARAMS = {"path": ("width", "profile", "repeat", "scatter"), "near": ("within", "soft"), "facing": ("range",),
          "cavity": ("radius",)}
BLENDS = ("multiply", "add", "subtract", "min", "max", "screen", "overlay", "replace")
ENTRY_OPS = ("blend", "weight", "breakup", "levels", "invert", "blur")


def layers(spec: dict) -> dict:
    """The spec's paint layers with material layers expanded into their sub-layers (materials.py), in order."""
    from . import materials
    out = {}
    for name, ly in (spec.get("paint") or {}).items():
        if "material" in ly:
            for sub, sl in materials.expand(name, ly, GENERATORS, PARAMS):
                out[sub] = sl
        else:
            out[name] = ly
    return out


def validate(spec: dict) -> None:
    for name, ly in layers(spec).items():
        if not any(c in ly for c in (*CHANNELS, "height")):
            raise SpecError(f"paint {name!r}: needs at least one of {', '.join(CHANNELS)}, height")
        if "height" in ly and not isinstance(ly["height"], (int, float)):
            raise SpecError(f"paint {name!r}: height is a number (m, + out of the surface, times the mask)")
        if "color" in ly:
            colour(ly["color"], f"paint {name!r}")
        for c in ("roughness", "metallic", "specular"):
            if c in ly and not 0 <= float(ly[c]) <= 1:
                raise SpecError(f"paint {name!r}: {c} is 0..1")
        flat = {g: ly[g] for g in GENERATORS if g in ly and g != "mask"}
        unknown = set(ly) - {*CHANNELS, "height", "opacity", "part", "mask", "_of", *GENERATORS, *(k for v in PARAMS.values() for k in v)}
        if unknown:
            raise SpecError(f"paint {name!r}: unknown keys {sorted(unknown)}")
        for g in flat:
            _check_generator(name, g, ly)
        if "mask" in ly:
            _check_stack(name, ly["mask"])


def _nears(ly: dict):
    """Every "near" a layer (or a mask stack entry) names, nested stacks included."""
    if "near" in ly:
        yield ly["near"]
    for e in ly.get("mask") or []:
        if isinstance(e, dict):
            yield from _nears(e)


def check_refs(spec: dict, prims: list) -> None:
    """Names paint points at must exist: each "near" resolves to primitives, each "part" is a part of the model.
    Checked when the spec is saved, not minutes into a sync or export."""
    from .paintnodes import resolve_near
    from .spec import expand_mirror
    by_name = {p.name: p for p in prims}
    expanded = None
    parts = {p.part for p in prims} | set(spec.get("parts") or {}) | {"body"}
    els = {**(spec.get("bones") or {}), **(spec.get("blobs") or {})}
    for name, ly in layers(spec).items():
        lp = ly.get("part", "body")
        for pn in ([lp] if isinstance(lp, str) else lp):
            if pn != "*" and pn not in parts:
                raise SpecError(f"paint {name!r}: no part {pn!r} (parts: {', '.join(sorted(parts))})")
        for near in _nears(ly):
            if expanded is None:
                expanded = expand_mirror(spec)
            got, missing = resolve_near(spec, near, by_name, expanded)
            asked = [near] if isinstance(near, str) else list(near)
            empty = [a for a in asked if a not in by_name and not any(g == a or g.startswith((a + "/", a + "#"))
                                                                        for g in got)] if not got else missing
            bad = sorted(set(missing) | set(empty))
            if not bad:
                continue
            why = []
            for b in bad:
                el = els.get(b)
                if el is not None and el.get("op") in ("subtract", "intersect") and el.get("targets"):
                    why.append(f"{b!r} is a cut, folded into its targets {el['targets']}: it has no surface of "
                               f"its own to be near; name what it cuts, or elements beside the cut")
            raise SpecError(f"paint {name!r}: near names nothing for {bad}" + (": " + "; ".join(why) if why else
                            " (element, tag, instance, array or kit names)"))


def _check_stack(name: str, stack) -> None:
    if not isinstance(stack, list):
        raise SpecError(f"paint {name!r}: mask is a list of entries, e.g. [{{\"ao\": [0.9, 0.5]}}, "
                        f"{{\"noise\": {{}}, \"blend\": \"multiply\"}}]")
    for i, e in enumerate(stack):
        where = f"paint {name!r} mask[{i}]"
        if not isinstance(e, dict):
            raise SpecError(f"{where}: an entry is an object")
        gens = [g for g in GENERATORS if g in e]
        if len(gens) > 1:
            raise SpecError(f"{where}: one generator per entry, got {gens}")
        allowed = {*ENTRY_OPS, *gens, *(PARAMS.get(gens[0], ()) if gens else ())}
        unknown = set(e) - allowed
        if unknown:
            raise SpecError(f"{where}: unknown keys {sorted(unknown)} (allowed here: {sorted(allowed)})")
        if not gens and not any(k in e for k in ("levels", "invert", "blur")):
            raise SpecError(f"{where}: needs a generator ({', '.join(GENERATORS)}) or an op (levels, invert, blur)")
        if gens:
            _check_generator(name, gens[0], e)
            if gens[0] == "mask":
                _check_stack(name, e["mask"])
        if e.get("blend", "multiply") not in BLENDS:
            raise SpecError(f"{where}: blend is one of {', '.join(BLENDS)}")
        if "levels" in e and not (isinstance(e["levels"], list) and len(e["levels"]) in (2, 3)):
            raise SpecError(f"{where}: levels is [lo, hi] or [lo, hi, gamma]")


def _check_generator(name: str, g: str, e: dict) -> None:
    if g in ("tiles", "weave") and not isinstance(e[g], dict):
        raise SpecError(f"paint {name!r}: {g} is an object of parameters")
    if g == "tiles" and e[g].get("mode", "gaps") not in ("gaps", "bevel", "id"):
        raise SpecError(f"paint {name!r}: tiles mode is \"gaps\", \"bevel\" or \"id\"")
    if g == "cells" and (not isinstance(e[g], dict) or e[g].get("mode", "edges") not in ("edges", "distance", "id")):
        raise SpecError(f"paint {name!r}: cells is {{\"scale\", \"mode\": \"edges\" | \"distance\" | \"id\", ...}}")
    if g == "random" and not (isinstance(e[g], dict) and set(e[g]) <= {"range", "seed"}):
        raise SpecError(f"paint {name!r}: random is {{\"range\"?: [lo, hi], \"seed\"?: n}}: one value per element")
    if g == "cavity" and e[g] not in ("concave", "convex"):
        raise SpecError(f"paint {name!r}: cavity is \"concave\" or \"convex\"")
    if g in ("ao", "thickness", "sky") and not (isinstance(e[g], list) and len(e[g]) == 2):
        raise SpecError(f"paint {name!r}: {g} is [value at 0, value at 1], e.g. " +
                        ("[0.9, 0.5] (1 in occluded places)" if g == "ao" else "[0.03, 0.01] (1 where thin)"))


def _code_hash() -> str:
    """The painting code itself (this module, materials, noise, surface inputs): a recipe change repaints."""
    from pathlib import Path
    here = Path(__file__).parent
    h = hashlib.sha1()
    for f in ("paint.py", "materials.py", "noise.py", "surface.py"):
        h.update((here / f).read_bytes())
    return h.hexdigest()[:8]


_CODE = _code_hash()


def key(spec: dict) -> str:
    """What painted colours depend on besides the mesh (and the painting code)."""
    return hashlib.sha1(json.dumps([spec.get("paint"), spec.get("parts"), (spec.get("story") or {}).get("directions"),
                                    _CODE], sort_keys=True,
                                   default=float).encode()).hexdigest()[:12]


def apply(spec: dict, verts: np.ndarray, normals: np.ndarray, part: np.ndarray, part_names: list[str],
          base: np.ndarray, voxel: float, stats: dict | None = None, cache: dict | None = None,
          masks: dict | None = None) -> np.ndarray:
    """Painted sRGB colours (n, 3) for a built mesh, starting from `base` (each vertex's part clay colour).
    stats, if given, gets each layer's coverage: the fraction of its parts' vertices it paints at least half.
    cache: the vertices' field inputs (surface.Points), filled in as layers need them."""
    from .surface import Points
    pts = Points(spec, verts, normals, part, part_names, voxel, cache)
    return apply_channels(spec, pts, {"color": base[:, :3]}, stats, masks)["color"]


def bump(spec: dict, pts, eps: float, masks: dict | None = None):
    """Painted height (layers' "height" times their mask, summed; m) and the normals it tilts, or None when no
    layer has height. The slope comes from central differences `eps` apart across the surface (4 more
    evaluations of the height layers). masks: the layers' masks at pts, if apply_channels already made them."""
    from .surface import _frame, unit
    hl = {k: ly for k, ly in layers(spec).items() if ly.get("height")}
    if not hl:
        return None

    def height(p, given=None):
        h = np.zeros(len(p))
        for name, ly in hl.items():
            if given is not None and name in given:
                h += float(ly["height"]) * given[name]
                continue
            parts = ly.get("part", "body")
            parts = p.part_names if parts == "*" else ([parts] if isinstance(parts, str) else parts)
            idx = np.flatnonzero(np.isin(p.part, [p.part_names.index(q) for q in parts if q in p.part_names]))
            if len(idx):
                h[idx] += float(ly["height"]) * layer_mask(spec, name, ly, _View(p, idx))
        return h

    h0 = height(pts, masks)
    T, B = _frame(pts.normal)
    d = [height(pts.moved(pts.pos + s * eps * D, keep_inputs=True)) for D in (T, B) for s in (1, -1)]
    dT, dB = (d[0] - d[1]) / (2 * eps), (d[2] - d[3]) / (2 * eps)
    return h0, unit(pts.normal - dT[:, None] * T - dB[:, None] * B)


def part_defaults(spec: dict, part_names: list[str], part: np.ndarray) -> dict:
    """Every channel's starting value per point, from its part's definition."""
    from .store import part_colour
    defs = spec.get("parts") or {}
    col = np.array([part_colour(p, defs, i)[:3] for i, p in enumerate(part_names)])
    rough = np.array([float((defs.get(p) or {}).get("roughness", 0.6)) for p in part_names])
    metal = np.array([float((defs.get(p) or {}).get("metallic", 0.0)) for p in part_names])
    spec_ = np.array([float((defs.get(p) or {}).get("specular", 0.5)) for p in part_names])
    return {"color": col[part], "roughness": rough[part][:, None], "metallic": metal[part][:, None],
            "specular": spec_[part][:, None]}


def apply_channels(spec: dict, pts, base: dict, stats: dict | None = None, masks: dict | None = None) -> dict:
    """Paint every channel in `base` ({"color": (n, 3), "roughness": (n, 1), ...}) at arbitrary surface points
    (a surface.Points: mesh vertices, or texels of a baked texture). masks, if given, gets each layer's mask
    over all points (0 off its parts)."""
    out = {c: np.array(v, float) for c, v in base.items()}
    if not spec.get("paint"):
        return out
    validate(spec)
    for name, ly in layers(spec).items():
        parts = ly.get("part", "body")
        parts = pts.part_names if parts == "*" else ([parts] if isinstance(parts, str) else parts)
        idx = np.flatnonzero(np.isin(pts.part, [pts.part_names.index(p) for p in parts if p in pts.part_names]))
        if not len(idx):
            if stats is not None:
                stats[ly.get("_of") or name] = None
            continue  # e.g. a close-up that doesn't reach that part
        m = layer_mask(spec, name, ly, _View(pts, idx))
        of = ly.get("_of")
        if stats is not None and (of is None or of not in stats):  # a material reports its first sub-layer
            seen = pts.get("hidden")[idx] < 0.5  # skin under clothes or in an eye socket doesn't count
            stats[of or name] = float((m[seen] >= 0.5).mean()) if seen.any() else 0.0
        if masks is not None:
            masks[name] = np.zeros(len(pts))
            masks[name][idx] = m
        a = (float(ly.get("opacity", 1.0)) * m)[:, None]
        for c, arr in out.items():
            if c in ly:
                val = colour(ly[c]) if c == "color" else np.array([float(ly[c])])
                arr[idx] += a * (val[None] - arr[idx])
    return out


class _View:
    """Some of a Points set (idx), possibly mirrored across X: positions and normals as a mask sees them.
    Field inputs (ao, curvature, thickness) are always the point's own, mirrored or not."""

    def __init__(self, pts, idx: np.ndarray, mirror: bool = False):
        self.pts, self.idx, self.mirror = pts, idx, mirror
        self.v = pts.pos[idx] * MIRROR if mirror else pts.pos[idx]
        self.n = pts.normal[idx] * MIRROR if mirror else pts.normal[idx]

    def __len__(self):
        return len(self.idx)

    def get(self, key: str) -> np.ndarray:
        return self.pts.get(key)[self.idx]

    def mirrored(self) -> "_View":
        return _View(self.pts, self.idx, not self.mirror)

    def jittered(self, radius: float, k: int = 12):
        """k copies of these points moved across the surface (a Vogel disc of `radius`, Gaussian weights)."""
        from .surface import _frame
        P, N = self.pts.pos[self.idx], self.pts.normal[self.idx]
        U, V = _frame(N)
        i = np.arange(k) + 0.5
        r = radius * np.sqrt(i / k)
        a = i * 2.39996323  # golden angle
        w = np.exp(-2 * (r / radius) ** 2)
        views = []
        for rr, aa in zip(r, a):
            here = self.pts.__class__(self.pts.spec, P, N, self.pts.part[self.idx], self.pts.part_names,
                                      self.pts.voxel, streams=self.pts._streams)
            here.footprint = self.pts.footprint
            moved = here.moved(P + rr * (np.cos(aa) * U + np.sin(aa) * V))
            moved.footprint = self.pts.footprint
            views.append(_View(moved, np.arange(len(P)), self.mirror))
        return views, w / w.sum()


def _tag(name: str, i) -> str:
    """A stack entry's own name (paths seat as strokes named after it), keeping a ".L" suffix at the end."""
    if i is None:
        return name
    stem, sfx = (name[:-2], name[-2:]) if name.endswith((".L", ".R")) else (name, "")
    return f"{stem}~{i}{sfx}"


def layer_mask(spec: dict, name: str, ly: dict, view: _View) -> np.ndarray:
    """A layer's mask: its flat keys (each a generator, multiplied), then its "mask" stack, 0..1. A ".L" layer
    takes the stronger of the mask at the point and at its mirror image."""
    stack = [{g: ly[g], **{k: ly[k] for k in PARAMS.get(g, ()) if k in ly}} for g in GENERATORS
             if g in ly and g != "mask"]
    tags = [None] * len(stack)
    if "mask" in ly:
        stack += ly["mask"]
        tags += list(range(len(ly["mask"])))
    m = _stack(spec, name, stack, tags, view)
    if name.endswith(".L"):
        m = np.maximum(m, _stack(spec, name, stack, tags, view.mirrored()))
    return np.clip(m, 0, 1)


def _stack(spec: dict, name: str, stack: list, tags: list, view: _View) -> np.ndarray:
    m = None
    for j, (e, tag) in enumerate(zip(stack, tags)):
        gen = next((g for g in GENERATORS if g in e), None)
        if gen is None:  # an op on the mask so far
            if m is None:
                m = np.ones(len(view))
            if "blur" in e:
                m = _blurred(lambda v: _stack(spec, name, stack[:j], tags[:j], v), view, float(e["blur"]), m)
            m = _post(m, e, view)
            continue
        g = _generate(spec, name, gen, e, _tag(name, tag), view)
        if "blur" in e:
            g = _blurred(lambda v: _generate(spec, name, gen, e, _tag(name, tag), v), view, float(e["blur"]), g)
        g = _post(g, e, view)
        mode = e.get("blend", "multiply")
        if m is None:
            m = g  # the first generator starts the mask
            continue
        b = _blend(mode, m, g)
        wgt = float(e.get("weight", 1.0))
        m = np.clip(m + wgt * (b - m), 0, 1)
    return np.ones(len(view)) if m is None else m


def _blurred(fn, view: _View, radius: float, m0: np.ndarray) -> np.ndarray:
    """fn (a mask at a view's points) averaged over a disc of `radius` across the surface. m0 is fn unblurred:
    only points whose neighbourhood isn't constant in it get sampled (a cell grid of size radius finds them)."""
    if radius <= 0 or not len(view):
        return m0
    cell = np.floor(view.v / radius).astype(np.int64)
    keys, inv = np.unique(cell, axis=0, return_inverse=True)
    inv = inv.ravel()
    lo = np.full(len(keys), np.inf)
    hi = np.full(len(keys), -np.inf)
    np.minimum.at(lo, inv, m0)
    np.maximum.at(hi, inv, m0)
    code = lambda c: (c[:, 0] * 2_000_003 + c[:, 1]) * 2_000_029 + c[:, 2]  # noqa: E731
    kc = code(keys)
    order = np.argsort(kc)
    nlo, nhi = lo.copy(), hi.copy()
    for off in np.array(np.meshgrid([-1, 0, 1], [-1, 0, 1], [-1, 0, 1])).reshape(3, -1).T:
        q = code(keys + off)
        at = np.clip(np.searchsorted(kc, q, sorter=order), 0, len(kc) - 1)
        hit = kc[order[at]] == q
        nlo[hit] = np.minimum(nlo[hit], lo[order[at[hit]]])
        nhi[hit] = np.maximum(nhi[hit], hi[order[at[hit]]])
    varying = np.flatnonzero((nhi - nlo)[inv] > 1e-4)
    out = m0.copy()
    if len(varying):
        sub = _View(view.pts, view.idx[varying], view.mirror)
        views, w = sub.jittered(radius)
        out[varying] = sum(wi * fn(v) for v, wi in zip(views, w))
    return out


def _post(g: np.ndarray, e: dict, view: _View) -> np.ndarray:
    if "breakup" in e:  # noise shifts the threshold: edges chip, grime gathers in blotches
        b = e["breakup"]
        b = {"amount": float(b)} if isinstance(b, (int, float)) else b
        n = fbm(view.v, float(b.get("scale", 0.03)), int(b.get("octaves", 3)), int(b.get("seed", 0)))
        s = 0.5 * (1 - min(max(float(b.get("sharpness", 0.5)), 0.0), 0.98))
        g = _ramp(g + float(b.get("amount", 0.5)) * (2 * n - 1), 0.5 - s, 0.5 + s)
    if "levels" in e:
        lv = e["levels"]
        lo, hi = float(lv[0]), float(lv[1])
        g = np.clip((g - lo) / (hi - lo if hi != lo else 1e-9), 0, 1) ** (1 / float(lv[2]) if len(lv) > 2 else 1)
    if e.get("invert"):
        g = 1 - g
    return g


def _blend(mode: str, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if mode == "multiply":
        return a * b
    if mode == "add":
        return a + b
    if mode == "subtract":
        return a - b
    if mode == "min":
        return np.minimum(a, b)
    if mode == "max":
        return np.maximum(a, b)
    if mode == "screen":
        return 1 - (1 - a) * (1 - b)
    if mode == "overlay":
        return np.where(a < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    return b  # replace


def _generate(spec: dict, name: str, gen: str, e: dict, tag: str, view: _View) -> np.ndarray:
    """One generator's 0..1 value at the view's points."""
    v, n = view.v, view.n
    if gen == "path":  # seated on the part these points are on (the layer's, even from inside a mask stack)
        counts = np.bincount(view.pts.part[view.idx], minlength=len(view.pts.part_names))
        return _path_mask(spec, tag, {**e, "part": view.pts.part_names[int(np.argmax(counts))]}, v, n)
    if gen == "near":
        return _near_mask(spec, name, e, v)
    if gen == "facing":  # a direction, or one of the story's named directions ("weather", "sun"), or "element"
        from .realism import direction
        lo, hi = e.get("range", [0.0, 0.7])
        if e["facing"] == "element":
            return _ramp(np.abs((n * _grain(view)[0]).sum(1)), lo, hi)
        return _ramp(n @ direction(spec, e["facing"], f"paint {name!r}"), lo, hi)
    if gen == "axis":
        return _axis_mask(spec, name, e["axis"], v)
    if gen == "noise":
        nz = e["noise"]
        lo, hi = nz.get("range", [0.45, 0.6])
        return _ramp(noise(v, nz, _grain(view) if _along(nz) else None), lo, hi)
    if gen == "cells":
        c = e["cells"]
        mode = c.get("mode", "edges")
        val = cells(_stretch(v, c, _grain(view) if _along(c) else None), float(c.get("scale", 0.03)), mode, float(c.get("jitter", 1.0)), int(c.get("seed", 0)))
        lo, hi = c.get("range", {"edges": [0.15, 0.0], "distance": [0.35, 0.1], "id": [0.0, 1.0]}[mode])
        return _ramp(val, lo, hi)
    if gen == "cavity":
        r0, r1 = e.get("radius", [0.03, 0.006])
        curv = view.get("curvature")
        return _ramp(-curv if e["cavity"] == "concave" else curv, 1 / r0, 1 / r1)
    if gen == "tiles":
        t = e["tiles"]
        return _planar(lambda u, w: _tiles(u, w, t), v, n, t.get("dir"))
    if gen == "weave":
        w = e["weave"]
        sc = float(w.get("scale", 0.0025))
        val = _planar(lambda a, b: _weave(a, b, sc), v, n, w.get("dir"))
        # threads under ~3 points across can't be resolved: fade to the average instead of aliasing (like a mip)
        k = float(np.clip((sc / max(view.pts.footprint, 1e-9) - 2.0) / 2.0, 0, 1))
        return 0.55 + k * (val - 0.55)
    if gen in ("ao", "thickness", "sky"):
        a, b = e[gen]
        return _ramp(view.get(gen), float(a), float(b))
    if gen == "random":
        r = e["random"]
        lo, hi = r.get("range", [0.0, 1.0])
        return _ramp(element_random(view.get("grain_seed"), int(r.get("seed", 0))), float(lo), float(hi))
    if gen == "mask":
        sub = e["mask"]
        return _stack(spec, tag, sub, list(range(len(sub))), view)
    raise SpecError(f"paint {name!r}: unknown generator {gen!r}")


def element_random(seed: np.ndarray, salt: int = 0) -> np.ndarray:
    """A uniform 0..1 value per element from its grain_seed (a hash of its name), different for each salt."""
    x = np.sin(np.asarray(seed, np.float64) * 12989.8 + salt * 78.233 + 0.5) * 43758.5453
    return x - np.floor(x)


def _ramp(x, a, b):
    """0 at a, 1 at b (either order), smooth in between."""
    d = np.asarray(b - a, float)
    t = np.clip((x - a) / np.where(d == 0, 1e-12, d), 0, 1)
    return t * t * (3 - 2 * t)


def _axis_mask(spec: dict, name: str, ax: dict, v: np.ndarray) -> np.ndarray:
    if "bone" in ax:
        from .spec import expand_mirror, resolve_point
        s = expand_mirror(spec)
        b = s["bones"].get(ax["bone"])
        if b is None:
            raise SpecError(f"paint {name!r}: unknown bone {ax['bone']!r}")
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        d = bb - a
        t = (v - a) @ d / (d @ d)
        return _ramp(t, float(ax.get("from", 0.0)), float(ax.get("to", 1.0)))
    d = np.asarray(ax.get("dir", [0, 0, 1]), float)
    d = d / np.linalg.norm(d)
    return _ramp(v @ d, float(ax["from"]), float(ax["to"]))


_TAGS: dict[str, set] = {}


def _tag_names(spec: dict) -> set:
    """Every tag in the expanded spec (an array's first copy is named like its tag)."""
    import hashlib
    import json
    from .spec import expand_mirror, geometry
    key = hashlib.sha1(json.dumps(geometry(spec), sort_keys=True, default=float).encode()).hexdigest()
    if key not in _TAGS:
        if len(_TAGS) > 16:
            _TAGS.pop(next(iter(_TAGS)))
        s = expand_mirror(spec)
        _TAGS[key] = {t for k in ("bones", "blobs") for el in s.get(k, {}).values() for t in el.get("tags") or []}
    return _TAGS[key]


def _near_mask(spec: dict, name: str, ly: dict, v: np.ndarray) -> np.ndarray:
    from . import sdf
    from .spec import compile_prims
    want = [ly["near"]] if isinstance(ly["near"], str) else list(ly["near"])
    prims = {p.name: p for p in compile_prims(spec)}
    tagged = _tag_names(spec)
    for w in list(want):  # a kit name stands for everything it generates (hand.L -> hand_*.L)
        if w in (spec.get("kits") or {}) and w not in prims:
            stem, sfx = (w[:-2], w[-2:]) if w.endswith((".L", ".R")) else (w, "")
            want.remove(w)
            want += [n for n, p in prims.items() if n.startswith(stem + "_") and n.endswith(sfx) and p.kind in sdf.SDF
                     and p.kind != "shell" and p.op == "add"]
    if any(w not in prims or w in tagged for w in want):  # tags: instances, arrays, "tags" lists
        from .assemble import select
        from .spec import expand_mirror
        asked = set(want)
        # a tag's members include targeted cuts, which are folded into their targets (no primitive of their own)
        want = [w for w in select(expand_mirror(spec), want) if w in prims or w in asked]
    missing = [w for w in want if w not in prims]
    if missing:
        raise SpecError(f"paint {name!r}: no bone or blob {missing} (kit output names are listed by get_model)")
    d = np.full(len(v), np.inf)
    for w in want:
        p = prims[w]
        if p.kind not in sdf.SDF or p.kind == "shell":
            raise SpecError(f"paint {name!r}: {w!r} is a {p.kind}, not a shape")
        d = np.minimum(d, sdf.SDF[p.kind](v, p.params))
    within, soft = float(ly.get("within", 0.0)), float(ly.get("soft", 0.01))
    return 1 - _ramp(d, within, within + max(soft, 1e-6))


def _seated_paths(spec: dict, name: str, ly: dict) -> list[dict]:
    """The layer's path seated on the surface, as stroke samples (pts, nrm, width per sample), one per copy."""
    from . import kits, strokes
    from .spec import geometry
    base = strokes.seat_joints(kits.expand(geometry(spec)))
    base = copy.copy(base)
    base.pop("strokes", None)
    st = {"op": "clay", "path": ly["path"], "width": ly.get("width", 0.01), "depth": 0.001}
    for k in ("repeat", "scatter"):
        if k in ly:
            st[k] = ly[k]
    part = ly.get("part", "body")
    if isinstance(part, str) and part != "*" and part != "body":
        st["part"] = part
    return list(strokes._generate(base, {f"paint:{name}": st})["blobs"].values())


def _path_mask(spec: dict, name: str, ly: dict, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    from scipy.spatial import cKDTree
    from .sdf import PROFILES
    from .spec import _profile_norm
    prof_name = ly.get("profile", "flat")
    if prof_name not in PROFILES:
        raise SpecError(f"paint {name!r}: unknown profile {prof_name!r} (have {', '.join(PROFILES)})")
    prof = PROFILES[prof_name][0]
    out = np.zeros(len(v))
    for bl in _seated_paths(spec, name, ly):
        P, N, W = (np.asarray(bl[k], float) for k in ("pts", "nrm", "width"))
        N = N / np.linalg.norm(N, axis=1, keepdims=True)
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1) if len(P) > 1 else np.zeros(0)
        ds = np.concatenate([seg, [0.0]]) / 2 + np.concatenate([[0.0], seg]) / 2
        gain = ds / (W * _profile_norm(prof_name)) if len(P) > 1 else np.ones(1)
        reach = np.maximum(W, 0.02)  # along the normal: covers what strokes pushed in or out
        R = float(np.hypot(W.max(), 2 * reach.max()))
        step = float(ds[ds > 0].min()) if (ds > 0).any() else 1.0
        K = int(min(len(P), 2 * W.max() / step + 4))
        box = np.all((v >= P.min(0) - R) & (v <= P.max(0) + R), axis=1)
        sel = np.flatnonzero(box)
        if not len(sel):
            continue
        q = v[sel]
        dist, idx = cKDTree(P).query(q, k=K, distance_upper_bound=R)
        idx = idx.reshape(len(q), K)
        ok = idx < len(P)
        j = np.where(ok, idx, 0)
        r = q[:, None, :] - P[j]
        h = (r * N[j]).sum(-1)
        lat = np.sqrt(np.maximum((r * r).sum(-1) - h * h, 0.0)) / W[j]
        k = np.where(ok & (lat < 1.0), prof(np.minimum(lat, 1.0)), 0.0)
        k *= 1 - _ramp(np.abs(h), reach[j], 2 * reach[j])
        k *= _ramp((n[sel][:, None, :] * N[j]).sum(-1), 0.0, 0.3)  # skin facing the path's way: no print-through
        out[sel] = np.maximum(out[sel], np.clip((k * gain[j]).sum(1), 0, 1))
    return out


_AXES = np.eye(3)
_IN_PLANE = ([0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0])  # default long axis on each axis plane


def _planar(fn, v: np.ndarray, n: np.ndarray, d=None, sharp: float = 6.0) -> np.ndarray:
    """A 2D pattern fn(u, w) laid on the three axis planes and blended by how much the normal faces each
    (triplanar): exact on walls and floors, soft where a curved surface turns. u runs along `d` (projected
    into the plane; default horizontal on walls, X on floors), w across it."""
    wts = np.abs(n) ** sharp
    wts /= np.maximum(wts.sum(1, keepdims=True), 1e-12)
    out = np.zeros(len(v))
    for ax in range(3):
        sel = np.flatnonzero(wts[:, ax] > 1e-3)
        if not len(sel):
            continue
        a = _AXES[ax]
        dd = np.asarray(d if d is not None else _IN_PLANE[ax], float)
        dd = dd - (dd @ a) * a
        if np.linalg.norm(dd) < 0.3:  # the given direction is (nearly) this plane's normal
            dd = np.asarray(_IN_PLANE[ax], float)
        dd /= np.linalg.norm(dd)
        e = np.cross(a, dd)
        out[sel] += wts[sel, ax] * fn(v[sel] @ dd, v[sel] @ e)
    return out


def _tiles(u: np.ndarray, w: np.ndarray, t: dict) -> np.ndarray:
    """Running-bond tiles, "size": [along, across] (m), rows shifted by "offset" (0.5; "random"), joints "gap"
    wide. mode "gaps": 1 in the joints, fading over "bevel" (gap / 2); "bevel": 0 at the joint rising to 1
    over "bevel" (a tile's rounded face, for height); "id": a random 0..1 per tile."""
    L, H = (float(x) for x in t.get("size", [0.2, 0.1]))
    gap = float(t.get("gap", 0.005))
    bev = float(t.get("bevel", 0.5 * gap))
    seed = int(t.get("seed", 0))
    row = np.floor(w / H)
    off = t.get("offset", 0.5)
    shift = _hash(row.astype(np.int64), np.zeros_like(row, np.int64), np.zeros_like(row, np.int64), seed + 31) \
        if off == "random" else row * float(off)
    uu = u / L + shift
    col = np.floor(uu)
    fu, fw = uu - col, w / H - row
    dist = np.minimum.reduce([fu * L, (1 - fu) * L, fw * H, (1 - fw) * H])
    mode = t.get("mode", "gaps")
    if mode == "id":
        return _hash(col.astype(np.int64), row.astype(np.int64), np.zeros_like(row, np.int64), seed + 13)
    edge = _ramp(dist, gap / 2, gap / 2 + max(bev, 1e-6))
    return 1 - edge if mode == "gaps" else edge


def _weave(u: np.ndarray, w: np.ndarray, s: float) -> np.ndarray:
    """Plain weave, threads `s` apart: 1 on the crown of the thread on top, 0 in the holes."""
    fu, fw = u / s - np.floor(u / s), w / s - np.floor(w / s)
    over = (np.floor(u / s) + np.floor(w / s)) % 2 == 0
    warp = np.sqrt(np.maximum(np.sin(np.pi * fw), 0)) * (0.55 + 0.45 * np.sin(np.pi * fu))
    weft = np.sqrt(np.maximum(np.sin(np.pi * fu), 0)) * (0.55 + 0.45 * np.sin(np.pi * fw))
    return np.where(over, np.maximum(warp, 0.5 * weft), np.maximum(weft, 0.5 * warp))


GRAIN_OFFSET = np.array([97.3, 61.7, 83.1])  # x an element's grain_seed: each element its own piece of pattern


def _along(nz: dict) -> bool:
    return (nz.get("stretch") or {}).get("dir") == "element"


def _grain(view) -> tuple:
    """The view's points' element axes (mirrored with the view) and element seeds."""
    g = view.get("grain")
    return (g * MIRROR if view.mirror else g), view.get("grain_seed")


def _stretch(v: np.ndarray, nz: dict, grain: tuple | None = None) -> np.ndarray:
    """Positions squashed along "stretch": {"dir", "factor"}, so features come out `factor` times longer that way.
    dir "element": along each point's own element axis (grain = (axes, seeds)), offset by its element's seed."""
    st = nz.get("stretch")
    if not st:
        return v
    if st.get("dir") == "element":
        g, seed = grain
        g = g / np.linalg.norm(g, axis=1, keepdims=True)  # its length is the end-grain weight
        v = v - (1 - 1 / float(st.get("factor", 6.0))) * (v * g).sum(1)[:, None] * g
        return v + seed[:, None] * GRAIN_OFFSET[None]
    d = np.asarray(st.get("dir", [0, 0, 1]), float)
    d /= np.linalg.norm(d)
    return v - (1 - 1 / float(st.get("factor", 6.0))) * (v @ d)[:, None] * d[None]


def noise(v: np.ndarray, nz: dict, grain: tuple | None = None) -> np.ndarray:
    """A noise generator's raw 0..1 value: fbm, optionally stretched (streaks) and domain-warped (grunge)."""
    scale, octaves, seed = float(nz.get("scale", 0.03)), int(nz.get("octaves", 3)), int(nz.get("seed", 0))
    q = _stretch(v, nz, grain)
    warp = float(nz.get("warp", 0.0))
    if warp:  # displace the lookup by another noise: swirly, torn-looking grunge instead of round blobs
        off = np.stack([fbm(q, scale, 2, seed + 11 + 7 * k) for k in range(3)], 1) - 0.5
        q = q + (2 * warp * scale) * off
    return fbm(q, scale, octaves, seed)


def cells(v: np.ndarray, scale: float, mode: str = "edges", jitter: float = 1.0, seed: int = 0) -> np.ndarray:
    """3D Voronoi on a jittered lattice, `scale` apart: "edges" F2 - F1 (0 on the borders between cells, in
    units of scale), "distance" F1 (0 at each cell's centre), "id" a random 0..1 per cell."""
    q = v / scale
    base = np.floor(q).astype(np.int64)
    f1 = np.full(len(q), np.inf)
    f2 = np.full(len(q), np.inf)
    ident = np.zeros(len(q))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = base + np.array([dx, dy, dz])
                pt = c + 0.5 + jitter * (np.stack([_hash(c[:, 0], c[:, 1], c[:, 2], seed + 17 * k)
                                                   for k in range(3)], 1) - 0.5)
                d = np.linalg.norm(q - pt, axis=1)
                closer = d < f1
                f2 = np.where(closer, f1, np.minimum(f2, d))
                ident = np.where(closer, _hash(c[:, 0], c[:, 1], c[:, 2], seed + 99), ident)
                f1 = np.where(closer, d, f1)
    return {"edges": f2 - f1, "distance": f1, "id": ident}[mode]


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
