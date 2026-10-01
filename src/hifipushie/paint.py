"""Paint: colour and surface channels laid on the built surface, evaluated per point: every mesh vertex in look,
every texel in export_asset.

spec["paint"] = {name: layer, ...}: layers apply in order, each over the colour so far (every part starts
from its clay colour, spec["parts"][p]["color"]). Paint never changes geometry, so repainting doesn't rebuild.

layer = {"color": [r, g, b] (0..1, sRGB, as you'd pick it) | "#rrggbb", "roughness", "metallic", "specular": 0..1,
         (any of these channels; a layer changes only the ones it gives), "opacity": 0..1 (1),
         "part": name | [names] | "*" (default "body"), "height": m (relief, see below), plus any of the masks
         below as flat keys (multiplied together) and/or a "mask" stack (below). No mask = the whole part.}
Each part starts from spec["parts"][p]: "color" (clay palette), "roughness" (0.6), "metallic" (0), "specular"
(0.5 = the usual 4% reflectance of skin, cloth, plastic), and for see-through parts "transmission" (0..1: glass,
light through it; with "ior", 1.45) or "alpha" (0..1: coverage, a fade); in the scene and the GLB (a material of
its own sharing its atlas: KHR_materials_transmission + ior, or alpha blend). These show in exported game assets (export_asset), not
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
           "within": 0.02, "axis": {"bone": "forearm.L", "from": 0.7, "to": 1}} for a glove. With "at": joint,
           from/to are measured from that joint along dir: {"dir": [0, 0, 1], "at": "lm_chin", "from": -0.035,
           "to": -0.02} fades a beard shadow out under the jaw wherever the chin ends up.
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
  rings:   {"spacing": m (0.006), "warp": 0..1 (0.5), "range": [lo, hi] ([0.75, 0.9]), "seed"}: growth rings round
           each element's own axis (a log, a beam, a leg): 1 on the ring lines. Confine to end grain with
           {"facing": "element"}; the wood material's end grain has them.
  random:  {"range": [lo, hi] (default [0, 1]), "seed"}: one random 0..1 value per element (each book, board,
           stone, log and array copy its own), ramped between lo and hi: a narrow range is a threshold, so
           layers stacked with rising ones ([0.25, 0.26], [0.5, 0.51], [0.75, 0.76], each over the last) give a
           quarter of the books on a shelf each colour; a wide range with low opacity jitters every board's tone. A prefab's instances
           share one bake, so they share their values; make copies differ with an array inside the prefab.
  outline: {"points": [joint | {"at": joint, "offset"} | [x,y,z], ...], "dir": [0, 1, 0], "soft": m (0.001),
           "depth": m (0.03)}: 1 inside the closed outline as seen looking along dir (the view direction: [0, 1, 0]
           is a front view of a model facing -Y, [-1, 0, 0] its left side), like a shape drawn on a photo of the
           model: lips from the mouth landmarks, a beard's border. Follows the points when the model changes.
  painted: "<id>" | "new": a mask a person painted by hand in the Blender scene. `sync` gives the objects of
           the layer's parts a colour attribute "hp_paint:<layer>" showing it; they paint it in Vertex Paint
           (white = 1) and `pull` stores it as a point cloud (workspace/_painted/<id>.npz: it survives
           re-meshing, and each spec in history keeps its own) and writes the new id here. "new" starts an empty
           one. Works in mask stacks like any generator (levels, breakup, blur on it).
  image:   {"file": path | "id" | "text": {...}, "at": joint | blob | [x,y,z], "dir": [x,y,z] | "front"..., "size":
           [w, h] m, "up", "rotate", "depth", "facing", "channel": "alpha" | "luma" | "r" | "g" | "b" | "coverage",
           "flip", "mirror"}: an image laid on the surface as a projected decal (a painting, a printed page, a
           label, a logo). With "color": "image" on the layer, the layer paints the image's own colours; otherwise
           (or in a mask stack) it's a mask (a stencil). Text is an image too: {"text": {"string", "font", "size",
           "color", "align", ...}}. "wrap": "cylinder" (a label round a can or bottle: "axis", "span" deg or
           size in m round the surface, "seam" deg), "sphere" (a globe, a ball) or "surface" (a sticker lying on any
           curved surface: geodesic coordinates from its centre). "style": true runs its colours through the
           paint style. Details: images.py; look shows it per pixel, exports bake it.
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
import re
from pathlib import Path

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
              "random", "rings", "painted", "outline", "image", "mask")
PARAMS = {"path": ("width", "profile", "repeat", "scatter"), "near": ("within", "soft"), "facing": ("range",),
          "cavity": ("radius",)}
BLENDS = ("multiply", "add", "subtract", "min", "max", "screen", "overlay", "replace")
ENTRY_OPS = ("blend", "weight", "breakup", "levels", "invert", "blur")


def layers(spec: dict) -> dict:
    """The spec's paint layers with material layers expanded into their sub-layers (materials.py), in order, with
    the spec's paint style applied (`style_layer`)."""
    from . import materials
    st = (spec.get("style") or {}).get("paint") or {}
    out = {}
    for name, ly in (spec.get("paint") or {}).items():
        if "material" in ly:
            if st:
                ly = dict(ly)
                ly["scale"] = float(ly.get("scale", 1.0)) * float(st.get("pattern", 1.0))
                for k in ("wear", "dirt"):
                    ly[k] = float(ly.get(k, 0.3)) * float(st.get("weathering", 1.0))
            for sub, sl in materials.expand(name, ly, GENERATORS, PARAMS):
                out[sub] = style_layer(sl, st, patterns=False)
        else:
            out[name] = style_layer(ly, st)
    return out


STYLE_PAINT = ("saturation", "value", "pattern", "weathering")


def style_layer(ly: dict, st: dict, patterns: bool = True) -> dict:
    """A layer as the paint style has it: colours through `style_rgb`, pattern sizes (noise, cells, tiles, weave)
    times style "pattern" (materials take it as their "scale" instead)."""
    if not st:
        return ly
    ly = dict(ly)
    if "color" in ly and ly["color"] != "image":
        ly["color"] = style_rgb(colour(ly["color"], "color"), st).tolist()
    k = float(st.get("pattern", 1.0))
    if patterns and k != 1.0:
        ly = _scale_patterns(ly, k)
    return ly


def _scale_patterns(e: dict, k: float) -> dict:
    e = dict(e)
    for g in ("noise", "cells", "weave"):
        if isinstance(e.get(g), dict):
            v = dict(e[g])
            v["scale"] = float(v.get("scale", {"noise": 0.03, "cells": 0.03, "weave": 0.0025}[g])) * k
            e[g] = v
    if isinstance(e.get("tiles"), dict):
        v = dict(e["tiles"])
        v["size"] = [float(x) * k for x in v.get("size", [0.2, 0.1])]
        e["tiles"] = v
    if isinstance(e.get("mask"), list):
        e["mask"] = [_scale_patterns(m, k) if isinstance(m, dict) else m for m in e["mask"]]
    return e


def style_rgb(rgb, st: dict) -> np.ndarray:
    """An sRGB colour as the paint style has it: saturation and value (brightness) scaled in HSV."""
    import colorsys
    if not st or (float(st.get("saturation", 1.0)) == 1.0 and float(st.get("value", 1.0)) == 1.0):
        return np.asarray(rgb, float)[:3]
    h, sat, v = colorsys.rgb_to_hsv(*[float(x) for x in np.asarray(rgb, float)[:3]])
    sat = min(1.0, sat * float(st.get("saturation", 1.0)))
    v = min(1.0, v * float(st.get("value", 1.0)))
    return np.array(colorsys.hsv_to_rgb(h, sat, v))


def validate(spec: dict) -> None:
    st = spec.get("style") or {}
    bad = set(st) - {"name", "shape", "paint", "look", "sheet"}
    if bad:
        raise SpecError(f"style: unknown keys {sorted(bad)} (have name, shape, paint, look, sheet)")
    lk = st.get("look") or {}
    bad = set(lk) - {"lights", "world", "look", "exposure", "view"}
    if bad:
        raise SpecError(f"style.look: unknown keys {sorted(bad)} (have lights, world, look, exposure, view)")
    for i, L in enumerate(lk.get("lights") or []):
        if "dir" not in L or set(L) - {"dir", "energy", "color", "angle", "shadow"}:
            raise SpecError(f"style.look.lights[{i}]: needs dir; takes dir, energy, color, angle, shadow")
    bad = set(st.get("paint") or {}) - set(STYLE_PAINT)
    if bad:
        raise SpecError(f"style.paint: unknown keys {sorted(bad)} (have {', '.join(STYLE_PAINT)})")
    for name, ly in layers(spec).items():
        if not any(c in ly for c in (*CHANNELS, "height")):
            raise SpecError(f"paint {name!r}: needs at least one of {', '.join(CHANNELS)}, height")
        if "height" in ly and not isinstance(ly["height"], (int, float)):
            raise SpecError(f"paint {name!r}: height is a number (m, + out of the surface, times the mask)")
        if ly.get("color") == "image":
            if not isinstance(ly.get("image"), dict):
                raise SpecError(f"paint {name!r}: \"color\": \"image\" takes the colours of the layer's own "
                                f"\"image\" key (a flat key on the layer, not in its mask stack)")
        elif "color" in ly:
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


def _gens(ly: dict, key: str):
    """Every value of generator `key` a layer (or a mask stack entry) gives, nested stacks included."""
    if key in ly:
        yield ly[key]
    for e in ly.get("mask") or []:
        if isinstance(e, dict):
            yield from _gens(e, key)


def side_warnings(spec: dict) -> list[str]:
    """Centre-named layers that point only at one side's elements: a ".L" name on the elements doesn't make the
    layer mirror (only the layer's own name does), so these paint one side. Returned for the edit summary."""
    out = []
    for name, ly in (spec.get("paint") or {}).items():
        if not isinstance(ly, dict) or name.endswith((".L", ".R")):
            continue
        names = []
        for near in _nears(ly):
            names += [near] if isinstance(near, str) else [n for n in near if isinstance(n, str)]
        for path in _gens(ly, "path"):
            for pt in path if isinstance(path, list) else []:
                if isinstance(pt, dict):
                    names += [pt[k] for k in ("bone", "at", "on") if isinstance(pt.get(k), str)]
                    if isinstance(pt.get("at"), dict) and isinstance(pt["at"].get("bone"), str):
                        names.append(pt["at"]["bone"])
        for side, other in ((".L", ".R"), (".R", ".L")):
            if names and all(n.endswith(side) for n in names):
                what = "near/path" if any(True for _ in _gens(ly, "path")) else "near"
                out.append(f"paint {name!r}: {what} names only {'left' if side == '.L' else 'right'}-side elements "
                           f"({', '.join(sorted(set(names)))}), so it paints one side; name the layer "
                           f"'{name}.L' to paint both sides, or add the '{other}' names for one-sided paint")
    return out


def check_refs(spec: dict, prims: list) -> None:
    """Names paint points at must exist: each "near" resolves to primitives, each "part" is a part of the model,
    each axis bone is a bone.
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
            from . import sdf
            shapeless = [g for g in got if by_name[g].kind not in sdf.SDF or by_name[g].kind == "shell"]
            if shapeless:
                raise SpecError(f"paint {name!r}: near {shapeless} reshape the surface (strokes) and have no surface "
                                f"of their own to be near: name the element under them, or paint a path along the "
                                f"stroke's path instead")
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
        for img in _gens(ly, "image"):  # a decal must resolve and land on the layer's own parts
            from . import images
            if expanded is None:
                expanded = expand_mirror(spec)
            if not isinstance(img, dict):
                continue
            fr = images.frame(spec, img, expanded, what=f"paint {name!r} image", parts=lp)
            on = [p for p in prims if p.op == "add" and (lp == "*" or p.part in ([lp] if isinstance(lp, str) else lp))]
            on = [p for p in prims if p.part in {q.part for q in on}]  # with their cuts
            if images.coverage(fr, on) == 0:
                raise SpecError(f"paint {name!r}: image at {img.get('at', img.get('axis'))!r} hits nothing on part(s) "
                                f"{lp!r} within its depth {fr['depth']:.3f} m of the decal's {fr['wrap']} surface (centre {np.round(fr['c'], 3).tolist()}, "
                                f"dir {np.round(fr['dir'], 2).tolist()}): check at/dir, or raise depth")
        for ax in _gens(ly, "axis"):
            if isinstance(ax, dict) and "bone" in ax:
                if expanded is None:
                    expanded = expand_mirror(spec)
                if ax["bone"] not in expanded["bones"]:
                    raise SpecError(f"paint {name!r}: axis bone {ax['bone']!r} doesn't exist (removed or renamed?)")


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
    if g == "rings" and not (isinstance(e[g], dict) and set(e[g]) <= {"spacing", "warp", "range", "seed"}):
        raise SpecError(f"paint {name!r}: rings is {{\"spacing\"?: m, \"warp\"?: 0..1, \"range\"?: [lo, hi], \"seed\"?}}")
    if g == "random" and not (isinstance(e[g], dict) and set(e[g]) <= {"range", "seed"}):
        raise SpecError(f"paint {name!r}: random is {{\"range\"?: [lo, hi], \"seed\"?: n}}: one value per element")
    if g == "painted" and not (isinstance(e[g], str) and (e[g] == "new" or (
            re.fullmatch(r"[0-9a-f]{16}", e[g]) and painted_path(e[g]).exists()))):
        from . import store
        raise SpecError(f"paint {name!r}: painted is the id of a hand-painted mask (a point cloud `pull` stores "
                        f"under {store.HOME / '_painted'}/<id>.npz), or \"new\" to start one; {e[g]!r} isn't one")
    if g == "image":
        from . import images
        img = e[g]
        if not isinstance(img, dict):
            raise SpecError(f"paint {name!r}: image is an object: {{\"file\" | \"id\" | \"text\", \"at\", "
                            f"\"dir\", \"size\": [w, h], ...}}")
        bad = set(img) - images.KEYS
        if bad:
            raise SpecError(f"paint {name!r}: image: unknown keys {sorted(bad)} (have {', '.join(sorted(images.KEYS))})")
        if sum(k in img for k in ("file", "id", "text")) != 1:
            raise SpecError(f"paint {name!r}: image takes one of \"file\", \"id\", \"text\"")
        if "text" in img:
            t = img["text"]
            if not (isinstance(t, dict) and isinstance(t.get("string"), str)):
                raise SpecError(f"paint {name!r}: image text is {{\"string\": \"...\", \"font\", \"size\", ...}}")
            bad = set(t) - images.TEXT_KEYS
            if bad:
                raise SpecError(f"paint {name!r}: image text: unknown keys {sorted(bad)} "
                                f"(have {', '.join(sorted(images.TEXT_KEYS))})")
            if t.get("align", "left") not in ("left", "center", "right", "justify"):
                raise SpecError(f"paint {name!r}: image text align is left, center, right or justify")
        if img.get("channel", "alpha") not in images.CHANNELS:
            raise SpecError(f"paint {name!r}: image channel is one of {', '.join(images.CHANNELS)}")
        wrap = img.get("wrap", "planar")
        if wrap not in images.WRAPS:
            raise SpecError(f"paint {name!r}: image wrap is one of {', '.join(images.WRAPS)}")
        sz = img.get("size")
        if not ((isinstance(sz, list) and len(sz) == 2 and any(sz) and all(x is None or float(x) > 0 for x in sz))
                or ("span" in img and wrap in ("cylinder", "sphere"))):
            raise SpecError(f"paint {name!r}: image size is [width, height] in m, > 0 (one may be null: from the "
                            f"image's aspect)" + ("; or a span in degrees" if wrap in ("cylinder", "sphere") else ""))
        if "at" not in img and not (wrap == "cylinder" and "axis" in img):
            raise SpecError(f"paint {name!r}: image needs \"at\" (its centre: a joint, a blob, [x, y, z])")
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
                if c == "color" and ly[c] == "image":  # the picture's own colours (sRGB, as every colour here)
                    from . import images
                    view = _View(pts, idx)
                    fr = images.frame(spec, ly["image"], _expanded(spec), what=f"paint {name!r} image",
                                       parts=ly.get("part", "body"))
                    _, val = images.evaluate(fr, view.v, view.n)
                    arr[idx] += a * (val - arr[idx])
                    continue
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


_EXP: dict = {}


def _expanded(spec: dict) -> dict:
    """expand_mirror(spec), cached by content (image placements resolve their joints and blobs on it)."""
    from .spec import expand_mirror, geometry
    k = hashlib.sha1(json.dumps(geometry(spec), sort_keys=True, default=float).encode()).hexdigest()
    if k not in _EXP:
        if len(_EXP) > 8:
            _EXP.pop(next(iter(_EXP)))
        _EXP[k] = expand_mirror(spec)
    return _EXP[k]


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
    if gen == "rings":
        r = e["rings"]
        sp = float(r.get("spacing", 0.006))
        rad = np.linalg.norm(view.get("radial"), axis=1)
        seed = view.get("grain_seed")
        wob = float(r.get("warp", 0.5)) * sp * (2 * noise(v, {"scale": 8 * sp, "octaves": 2, "seed": int(r.get("seed", 0))}) - 1)
        ph = (rad + seed * 7.31 * sp + wob) / sp
        lo, hi = r.get("range", [0.75, 0.9])
        return _ramp(0.5 + 0.5 * np.cos(2 * np.pi * ph), float(lo), float(hi))
    if gen == "random":
        r = e["random"]
        lo, hi = r.get("range", [0.0, 1.0])
        return _ramp(element_random(view.get("grain_seed"), int(r.get("seed", 0))), float(lo), float(hi))
    if gen == "painted":
        return painted_values(e["painted"], v, n)
    if gen == "outline":
        return _outline_mask(spec, name, e["outline"], v, n)
    if gen == "image":  # a mirrored view (a ".L" layer) sees the picture unmirrored on the other side
        from . import images
        on = sorted({view.pts.part_names[i] for i in np.unique(view.pts.part[view.idx])}) if len(view) else None
        fr = images.frame(spec, e["image"], _expanded(spec), what=f"paint {name!r} image", parts=on)
        if view.mirror:
            fr = {**fr, "flip": not fr["flip"]}
        return images.evaluate(fr, v, n)[0]
    if gen == "mask":
        sub = e["mask"]
        return _stack(spec, tag, sub, list(range(len(sub))), view)
    raise SpecError(f"paint {name!r}: unknown generator {gen!r}")


# ---- hand-painted masks -----------------------------------------------------------------------------------------
# A mask a person painted in the Blender scene (a colour attribute "hp_paint:<layer>", see scene.pull) is kept as a
# point cloud on the surface (world position, normal, value 0..1, the spacing it was painted at), content-addressed
# under workspace/_painted/<id>.npz, so it survives re-meshing and every spec in history keeps its own.

def painted_path(pid: str) -> Path:
    """Where a hand-painted mask lives. The id comes from the spec, so it must be a content id (save_painted's 16 hex
    digits), never a path: "../x" would otherwise reach outside the workspace (artist contract, specs are data)."""
    from . import store
    if not (isinstance(pid, str) and re.fullmatch(r"[0-9a-f]{16}", pid)):
        raise SpecError(f"hand-painted mask id {pid!r} isn't one (16 hex digits, as pull stores them)")
    return store.HOME / "_painted" / f"{pid}.npz"


def hand_painted(spec: dict) -> dict:
    """The spec's layers with a hand-painted mask: {layer: (id or "new", parts)}; the id is the layer's flat
    "painted" key, else its mask stack's first painted entry."""
    out = {}
    for name, ly in (spec.get("paint") or {}).items():
        pid = ly.get("painted") or next((e["painted"] for e in ly.get("mask") or []
                                         if isinstance(e, dict) and "painted" in e), None)
        if pid:
            parts = ly.get("part", "body")
            out[name] = (pid, [parts] if isinstance(parts, str) else list(parts))
    return out


def set_painted(spec: dict, layer: str, pid: str) -> None:
    """Point the layer's hand-painted entry (as `hand_painted` finds it) at a new cloud, or add one as a flat key."""
    ly = spec["paint"][layer]
    if "painted" in ly:
        ly["painted"] = pid
        return
    for e in ly.get("mask") or []:
        if isinstance(e, dict) and "painted" in e:
            e["painted"] = pid
            return
    ly["painted"] = pid


def save_painted(pos: np.ndarray, nrm: np.ndarray, val: np.ndarray, spacing: np.ndarray) -> str:
    """Store a painted mask (points with value > 0, plus the zeros next to them so it fades out where the person
    stopped; spacing: each point's mesh voxel) and return its id."""
    import hashlib
    from scipy.spatial import cKDTree
    val = np.clip(np.asarray(val, np.float64), 0, 1)
    spacing = np.broadcast_to(np.asarray(spacing, np.float64), val.shape)
    on = val > 1e-3
    keep = on.copy()
    if on.any() and (~on).any():
        d, _ = cKDTree(pos[on]).query(pos[~on], distance_upper_bound=3 * float(spacing.max()))
        keep[np.flatnonzero(~on)[d < 3 * spacing[~on]]] = True
    arrays = {"pos": np.asarray(pos, np.float32)[keep], "nrm": np.asarray(nrm, np.float32)[keep],
              "val": val.astype(np.float32)[keep], "spacing": spacing.astype(np.float32)[keep]}
    h = hashlib.sha1()
    for k in sorted(arrays):
        h.update(k.encode() + np.round(arrays[k], 5).tobytes())
    pid = h.hexdigest()[:16]
    f = painted_path(pid)
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez(f, **arrays)
    return pid


_PAINTED: dict = {}


def painted_values(pid: str, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    """A painted mask at surface points: the painted points within two of their spacings that face the same way,
    weighted by distance (so it doesn't bleed through a thin board to the other side). 0 where nothing was
    painted."""
    from scipy.spatial import cKDTree
    if pid == "new":
        return np.zeros(len(v))
    if pid not in _PAINTED:
        f = painted_path(pid)
        if not f.exists():
            raise SpecError(f"hand-painted mask {pid!r} is missing ({f})")
        with np.load(f) as z:
            c = {k: z[k] for k in z.files}
        c["tree"] = cKDTree(c["pos"]) if len(c["pos"]) else None
        _PAINTED[pid] = c
    c = _PAINTED[pid]
    out = np.zeros(len(v))
    if c["tree"] is None:
        return out
    d, i = c["tree"].query(v, k=8, distance_upper_bound=2.0 * float(c["spacing"].max()))
    ok = np.isfinite(d)
    i = np.where(ok, i, 0)
    r = 2.0 * c["spacing"][i].astype(np.float64)
    face = np.clip(np.einsum("nkc,nc->nk", c["nrm"][i].astype(np.float64), n) * 2 - 0.4, 0, 1)
    w = np.where(ok & (d < r), (1 - np.minimum(d, r) / r) ** 2 * face, 0.0)
    ws = w.sum(1)
    has = ws > 1e-9
    out[has] = (w[has] * c["val"][i][has]).sum(1) / ws[has]
    return out


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
    off = 0.0
    if "at" in ax:  # from/to measured from a joint's position along dir
        from .spec import expand_mirror, resolve_point
        off = float(resolve_point(expand_mirror(spec), ax["at"]) @ d)
    return _ramp(v @ d - off, float(ax["from"]), float(ax["to"]))


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


def _outline_mask(spec: dict, name: str, o: dict, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    """1 inside a closed outline of named points (joints/landmarks, or {"at", "offset"}), as seen along "dir" (a
    region drawn on the model as if on a photo of it: lips, a beard's border), fading over "soft" (m) across its
    edge; only skin facing the viewer (normal . -dir > 0) and within "depth" (m, 0.03) of the outline's own points
    along dir (not the back of the head behind it)."""
    from .spec import expand_mirror, resolve_point
    s = expand_mirror(spec)
    d = np.asarray(o.get("dir", [0, 1, 0]), float)
    d /= np.linalg.norm(d)
    P = []
    for p in o["points"]:
        if isinstance(p, dict):
            q = resolve_point(s, p["at"]) + np.asarray(p.get("offset", [0, 0, 0]), float)
        elif isinstance(p, str):
            q = resolve_point(s, p)
        else:
            q = np.asarray(p, float)
        P.append(q)
    P = np.array(P)
    if len(P) < 3:
        raise SpecError(f"paint {name!r}: an outline needs 3+ points")
    up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.9 else np.array([0, 1.0, 0])
    a = np.cross(up, d)
    a /= np.linalg.norm(a)
    b = np.cross(d, a)
    Q = np.c_[P @ a, P @ b]
    X = np.c_[v @ a, v @ b]
    inside = np.zeros(len(v), bool)
    dist = np.full(len(v), np.inf)
    for i in range(len(Q)):
        p0, p1 = Q[i], Q[(i + 1) % len(Q)]
        cross = ((p0[1] > X[:, 1]) != (p1[1] > X[:, 1]))
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = p0[0] + (X[:, 1] - p0[1]) * (p1[0] - p0[0]) / (p1[1] - p0[1])
        inside ^= cross & (X[:, 0] < xint)
        e = p1 - p0
        t = np.clip(((X - p0) @ e) / max(float(e @ e), 1e-12), 0, 1)
        dist = np.minimum(dist, np.linalg.norm(X - (p0 + t[:, None] * e), axis=1))
    soft = max(float(o.get("soft", 0.001)), 1e-5)
    sd = np.where(inside, dist, -dist)  # + inside
    val = np.clip(0.5 + sd / (2 * soft), 0, 1)
    val = val * val * (3 - 2 * val)
    dep = v @ d
    lo, hi = float((P @ d).min()), float((P @ d).max())
    band = float(o.get("depth", 0.03))
    val *= ((dep > lo - band) & (dep < hi + band)).astype(float)
    return val * _ramp(-(n @ d), 0.0, 0.3)


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
    from . import anatomy, kits, strokes
    from .spec import geometry
    base = strokes.seat_joints(anatomy.expand(kits.expand(geometry(spec))))
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


def _path_entries(ly: dict, part):
    """(entry, part) for every path a layer gives, its mask stack's (nested) included; a stack entry is seated
    on the layer's part."""
    if "path" in ly:
        yield ly, ly.get("part", part)
    for e in ly.get("mask") or []:
        if isinstance(e, dict):
            yield from _path_entries(e, part)


def check_paths(spec: dict) -> None:
    """Seat every paint path now (cached by content, so the sync reuses it): a path that can't be seated fails
    the edit that made it, not a sync or look minutes later."""
    for name, ly in layers(spec).items():
        part = ly.get("part", "body")
        for e, pn in _path_entries(ly, part):
            if not isinstance(pn, str) or pn == "*":
                continue  # seated per part the points are on, at paint time
            _seated_paths(spec, name, {**e, "part": pn})


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
