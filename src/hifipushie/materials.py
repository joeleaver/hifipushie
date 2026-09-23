"""Materials: a paint layer {"material": name, ...} expands into several ordinary paint layers (base, pattern,
relief, wear, dirt), like a kit expands into bones. Everything they use is a plain generator, so a material is
a starting point you can read (get_model doesn't show the expansion, but this list does) and rebuild by hand.

layer = {"material": "cloth" | "leather" | "wood" | "planks" | "brick" | "stone" | "metal" | "rust",
         "part", "opacity" (scales every sub-layer), any masks (flat keys or a "mask" stack: they confine the
         whole material, e.g. "near" a bone, a "path"), plus the material's parameters below.}
Common parameters: "color" (the main colour, sRGB), "scale" (multiplies every pattern size, 1), "wear" and
"dirt" (0..1: opacity of the edge-wear and grime sub-layers), "seed", and "dir" (a world direction for the
pattern's long axis: threads, grain, rows of bricks or planks; default: horizontal on walls, X on floors).
Sub-layers are named "<layer>:<sub>" (look(paint_layer="walls:mortar") shows one); coverage is reported for
the material's own confining mask.

Tiled and woven patterns are laid out on the three axis planes and blended by the normal (triplanar): exact on
flat walls and floors, a soft blend where a curved surface turns from one plane to the next.

  cloth    color "#6b5a45", "thread": weave spacing (m, 0.004; needs ~4 texels, finer fades to flat), dir: plain weave relief, thread shading,
           slight fading; roughness 0.9, specular 0.3. Shirts, sacks, blankets, trousers.
  leather  color "#5a3a24", "grain" (m, 0.0025): pebbled grain, darker creases, polished (smoother, lighter) wear.
  wood     color "#8a6240", dir = grain: streaky grain with fine relief, growth lines, a few knots. Carved or
           solid wooden things; "planks" for boards.
  planks   wood + boards "size": [length, width] (m, [1.2, 0.14]), "gap" (0.004), rows staggered by a third,
           each board its own tone. Floors, walls, tabletops, crates.
  brick    color "#8a4a32", "mortar": colour ("#b3aa98"), "size": [w, h] (m, [0.215, 0.065]), "gap" (0.01):
           running bond, recessed mortar, per-brick tone, chipped edges with wear.
  stone    color "#7d7a72", "mortar" ("#9a9488"), "size" (m, stone diameter 0.14), "gap" (0.012), "moss"
           (0..1, 0): irregular stones (voronoi), domed faces, recessed joints; fieldstone walls, cobbles,
           chimneys, hearths.
  metal    color "#9a9a9a", "roughness" (0.35): metallic, roughness variation, fine directional scratches,
           bright worn edges, dark grime in cavities. Iron, steel, pots, buckles ("color" "#c8a96a" for brass).
  rust     metal + "rust" (0..1, 0.5): patches of flaking rust (dull, rough, slightly raised) where it's
           occluded and at random.
"""

from __future__ import annotations

import numpy as np

from .spec import SpecError

COMMON = ("color", "scale", "wear", "dirt", "seed", "dir")
PARAMS = {"cloth": ("thread",), "leather": ("grain",), "wood": (), "planks": ("size", "gap"),
          "brick": ("mortar", "size", "gap"), "stone": ("mortar", "size", "gap", "moss"),
          "metal": ("roughness",), "rust": ("roughness", "rust")}
DEFAULT_COLOR = {"cloth": "#6b5a45", "leather": "#5a3a24", "wood": "#8a6240", "planks": "#8a6240",
                 "brick": "#8a4a32", "stone": "#7d7a72", "metal": "#9a9a9a", "rust": "#8a8a86"}


def _rgb(c):
    from .paint import colour
    return colour(c)


def shade(c, k: float) -> list:
    """The colour darker (k < 1) or lighter (k > 1, toward white)."""
    c = _rgb(c)
    out = c * k if k <= 1 else c + (1 - c) * (k - 1)
    return [round(float(x), 4) for x in np.clip(out, 0, 1)]


def _dirt(p, s):
    return {"color": shade(p["color"], 0.35), "roughness": 0.9, "opacity": p["dirt"], "mask": [
        {"ao": [0.6, 0.3], "breakup": {"amount": 0.3, "scale": 0.05 * s, "seed": p["seed"] + 5}},
        {"cavity": "concave", "radius": [0.02, 0.005], "blend": "max"}]}


def _wear(p, s, k=1.35, **extra):
    return {"color": shade(p["color"], k), "opacity": p["wear"], **extra, "mask": [
        {"cavity": "convex", "radius": [0.03, 0.008],
         "breakup": {"amount": 0.35, "scale": 0.01 * s, "sharpness": 0.7, "seed": p["seed"] + 3}}]}


def _cloth(p, s):
    t = float(p.get("thread", 0.004)) * s
    w = {"scale": t, **({"dir": p["dir"]} if "dir" in p else {})}
    return [("base", {"color": p["color"], "roughness": 0.9, "specular": 0.3}),
            ("weave", {"height": 0.25 * t, "mask": [{"weave": w}]}),
            ("threads", {"color": shade(p["color"], 0.75), "opacity": 0.45, "mask": [{"weave": w, "invert": True}]}),
            ("fade", {"color": shade(p["color"], 1.12), "opacity": 0.25, "mask": [
                {"noise": {"scale": 0.15 * s, "range": [0.35, 0.85], "seed": p["seed"]}}]}),
            ("wear", _wear(p, s, 1.25, roughness=1.0)),
            ("dirt", _dirt(p, s))]


def _leather(p, s):
    g = float(p.get("grain", 0.0025)) * s
    return [("base", {"color": p["color"], "roughness": 0.55, "specular": 0.45}),
            ("grain", {"color": shade(p["color"], 0.8), "opacity": 0.5, "height": -0.15 * g, "mask": [
                {"cells": {"scale": g, "range": [0.12, 0.0], "seed": p["seed"]}}]}),
            ("creases", {"color": shade(p["color"], 0.6), "opacity": 0.6, "mask": [
                {"cavity": "concave", "radius": [0.015, 0.004]}]}),
            ("tone", {"color": shade(p["color"], 0.8), "opacity": 0.4, "mask": [
                {"noise": {"scale": 0.06 * s, "range": [0.35, 0.8], "seed": p["seed"] + 1}}]}),
            ("wear", _wear(p, s, 1.3, roughness=0.3)),
            ("dirt", _dirt(p, s))]


def _grain(p, s, dir_):
    d = {"dir": dir_, "factor": 14}
    return [("grain", {"color": shade(p["color"], 0.72), "opacity": 0.55, "height": -0.0003, "mask": [
                {"noise": {"scale": 0.006 * s, "stretch": d, "range": [0.45, 0.7], "seed": p["seed"]}}]}),
            ("rings", {"color": shade(p["color"], 0.6), "opacity": 0.45, "mask": [
                {"noise": {"scale": 0.025 * s, "stretch": {"dir": dir_, "factor": 25}, "warp": 0.4,
                           "range": [0.52, 0.56], "seed": p["seed"] + 7}},
                {"noise": {"scale": 0.025 * s, "stretch": {"dir": dir_, "factor": 25}, "warp": 0.4,
                           "range": [0.6, 0.56], "seed": p["seed"] + 7}, "blend": "multiply"}]}),
            ("knots", {"color": shade(p["color"], 0.45), "opacity": 0.8, "mask": [
                {"cells": {"scale": 0.3 * s, "mode": "distance", "range": [0.09, 0.05], "seed": p["seed"] + 2,
                           "stretch": {"dir": dir_, "factor": 1.6}}},
                {"cells": {"scale": 0.3 * s, "mode": "id", "range": [0.7, 0.75], "seed": p["seed"] + 2},
                 "blend": "multiply"}]})]


def _default_dir(p, fallback):
    return p.get("dir", fallback)


def _wood(p, s):
    d = _default_dir(p, [1, 0, 0])
    return ([("base", {"color": p["color"], "roughness": 0.7, "specular": 0.4})] + _grain(p, s, d)
            + [("wear", _wear(p, s, 1.25, roughness=0.5)), ("dirt", _dirt(p, s))])


def _planks(p, s):
    d = _default_dir(p, [1, 0, 0])
    L, W = (float(x) * s for x in p.get("size", [1.2, 0.14]))
    gap = float(p.get("gap", 0.004)) * s
    t = {"size": [L, W], "gap": gap, "offset": 1 / 3, "dir": d, "seed": p["seed"]}
    return ([("base", {"color": p["color"], "roughness": 0.7, "specular": 0.4}),
             ("boards", {"color": shade(p["color"], 0.78), "opacity": 0.6, "mask": [
                 {"tiles": {**t, "mode": "id"}, "levels": [0.2, 1.0]}]}),
             ("boards_light", {"color": shade(p["color"], 1.15), "opacity": 0.4, "mask": [
                 {"tiles": {**t, "mode": "id", "seed": p["seed"] + 1}, "levels": [0.5, 1.0]}]})]
            + _grain(p, s, d)
            + [("gaps", {"color": shade(p["color"], 0.25), "roughness": 0.9, "height": -0.003 * s, "mask": [
                {"tiles": {**t, "mode": "gaps", "bevel": 0.6 * gap}}]}),
               ("wear", _wear(p, s, 1.25, roughness=0.5)), ("dirt", _dirt(p, s))])


def _brick(p, s):
    w, h = (float(x) * s for x in p.get("size", [0.215, 0.065]))
    gap = float(p.get("gap", 0.01)) * s
    t = {"size": [w, h], "gap": gap, "offset": 0.5, "seed": p["seed"], **({"dir": p["dir"]} if "dir" in p else {})}
    mortar = p.get("mortar", "#b3aa98")
    return [("base", {"color": p["color"], "roughness": 0.85, "specular": 0.4}),
            ("tone", {"color": shade(p["color"], 0.7), "opacity": 0.6, "mask": [
                {"tiles": {**t, "mode": "id"}, "levels": [0.3, 1.0]}]}),
            ("tone_light", {"color": shade(p["color"], 1.2), "opacity": 0.35, "mask": [
                {"tiles": {**t, "mode": "id", "seed": p["seed"] + 1}, "levels": [0.6, 1.0]}]}),
            ("speckle", {"color": shade(p["color"], 0.6), "opacity": 0.35, "height": -0.0005 * s, "mask": [
                {"noise": {"scale": 0.004 * s, "range": [0.62, 0.72], "seed": p["seed"] + 4}}]}),
            ("chips", {"color": shade(p["color"], 1.15), "opacity": p["wear"], "height": -0.002 * s, "mask": [
                {"tiles": {**t, "mode": "gaps", "gap": gap, "bevel": 1.5 * gap},
                 "breakup": {"amount": 0.45, "scale": 0.012 * s, "sharpness": 0.8, "seed": p["seed"] + 6}}]}),
            ("mortar", {"color": mortar, "roughness": 0.95, "height": -0.005 * s, "mask": [
                {"tiles": {**t, "mode": "gaps", "bevel": 0.5 * gap}}]}),
            ("dirt", _dirt(p, s))]


def _stone(p, s):
    size = float(p.get("size", 0.14)) * s
    g = float(p.get("gap", 0.012)) * s / size  # in cell units, as cells "edges" measures
    c = {"scale": size, "seed": p["seed"]}
    out = [("base", {"color": p["color"], "roughness": 0.85, "specular": 0.4}),
           ("tone", {"color": shade(p["color"], 0.72), "opacity": 0.6, "mask": [
               {"cells": {**c, "mode": "id", "range": [0.2, 1.0]}}]}),
           ("tone_warm", {"color": shade([0.55, 0.47, 0.38], 1.0), "opacity": 0.3, "mask": [
               {"cells": {**c, "mode": "id", "seed": p["seed"] + 1, "range": [0.6, 1.0]}}]}),
           ("grunge", {"color": shade(p["color"], 0.65), "opacity": 0.25, "mask": [
               {"noise": {"scale": 0.03 * s, "warp": 1.0, "range": [0.5, 0.8], "seed": p["seed"] + 3}}]}),
           ("pits", {"color": shade(p["color"], 0.7), "opacity": 0.5, "height": -0.0006 * s, "mask": [
               {"noise": {"scale": 0.004 * s, "range": [0.66, 0.76], "seed": p["seed"] + 4}}]}),
           ("dome", {"height": 0.006 * s, "mask": [{"cells": {**c, "mode": "edges", "range": [g, g + 0.2]}}]}),
           ("mortar", {"color": p.get("mortar", "#9a9488"), "roughness": 0.95, "mask": [
               {"cells": {**c, "mode": "edges", "range": [g, 0.6 * g]}}]}),
           ("wear", _wear(p, s, 1.2)), ("dirt", _dirt(p, s))]
    if float(p.get("moss", 0)) > 0:
        out.append(("moss", {"color": "#4f6a2a", "roughness": 0.95, "opacity": float(p["moss"]), "mask": [
            {"facing": [0, 0, 1], "range": [0.2, 0.8]},  # tops, and a little in the joints of walls
            {"cells": {**c, "mode": "edges", "range": [2.5 * g, g]}, "blend": "max", "weight": 0.15},
            {"facing": [0, 0, 1], "range": [-0.6, 0.0], "blend": "multiply"},  # never on overhangs
            {"levels": [0, 1], "breakup": {"amount": 0.4, "scale": 0.04 * s, "seed": p["seed"] + 8}}]}))
    return out


def _metal(p, s):
    r = float(p.get("roughness", 0.35))
    d = _default_dir(p, [1, 0, 0])
    return [("base", {"color": p["color"], "metallic": 1.0, "roughness": r, "specular": 0.5}),
            ("roughness_var", {"roughness": min(1.0, r + 0.2), "opacity": 0.7, "mask": [
                {"noise": {"scale": 0.03 * s, "warp": 0.8, "range": [0.4, 0.8], "seed": p["seed"]}}]}),
            ("scratches", {"color": shade(p["color"], 1.2), "roughness": max(0.05, r - 0.2), "opacity": 0.6,
                           "mask": [{"noise": {"scale": 0.003 * s, "stretch": {"dir": d, "factor": 30},
                                               "range": [0.66, 0.7], "seed": p["seed"] + 1}}]}),
            ("wear", _wear(p, s, 1.3, roughness=max(0.05, r - 0.15))),
            ("dirt", {**_dirt(p, s), "metallic": 0.2})]


def _rust(p, s):
    amt = float(p.get("rust", 0.5))
    lo = 0.78 - 0.3 * amt
    return _metal(p, s)[:-1] + [
        ("rust", {"color": "#7a3b1a", "metallic": 0.0, "roughness": 0.9, "specular": 0.3, "height": 0.0004 * s,
                  "mask": [{"noise": {"scale": 0.08 * s, "warp": 1.2, "octaves": 4, "range": [lo, lo + 0.08],
                                      "seed": p["seed"] + 9}},
                           {"ao": [0.9, 0.5], "blend": "screen", "weight": amt}]}),
        ("rust_dark", {"color": "#4a220f", "opacity": 0.6, "mask": [
            {"noise": {"scale": 0.012 * s, "range": [0.55, 0.7], "seed": p["seed"] + 10}},
            {"noise": {"scale": 0.08 * s, "warp": 1.2, "octaves": 4, "range": [lo + 0.04, lo + 0.14],
                       "seed": p["seed"] + 9}, "blend": "multiply"}]}),
        ("dirt", {**_dirt(p, s), "metallic": 0.0})]


BUILD = {"cloth": _cloth, "leather": _leather, "wood": _wood, "planks": _planks, "brick": _brick, "stone": _stone,
         "metal": _metal, "rust": _rust}


def expand(name: str, ly: dict, generator_keys, confine_params) -> list[tuple[str, dict]]:
    """A material layer's sub-layers as (name, layer) pairs, in order, confined by the layer's own masks."""
    mat = ly["material"]
    if mat not in BUILD:
        raise SpecError(f"paint {name!r}: unknown material {mat!r} (have {', '.join(BUILD)})")
    allowed = {"material", "part", "opacity", "mask", *COMMON, *PARAMS[mat], *generator_keys, *confine_params}
    unknown = set(ly) - allowed
    if unknown:
        raise SpecError(f"paint {name!r}: unknown keys {sorted(unknown)} for material {mat!r} "
                        f"(its parameters: {', '.join(COMMON + PARAMS[mat])})")
    p = {k: ly[k] for k in (*COMMON, *PARAMS[mat]) if k in ly}
    p.setdefault("color", DEFAULT_COLOR[mat])
    p.setdefault("seed", 0)
    p["wear"] = float(p.get("wear", 0.5))
    p["dirt"] = float(p.get("dirt", 0.5))
    subs = BUILD[mat](p, float(p.get("scale", 1.0)))
    conf = [{g: ly[g], **{k: ly[k] for k in confine_params.get(g, ()) if k in ly}} for g in generator_keys
            if g in ly and g != "mask"] + list(ly.get("mask") or [])
    stem, sfx = (name[:-2], name[-2:]) if name.endswith((".L", ".R")) else (name, "")
    op = float(ly.get("opacity", 1.0))
    out = []
    for sub, sl in subs:
        sl = dict(sl)
        sl["opacity"] = op * float(sl.get("opacity", 1.0))
        if "part" in ly:
            sl["part"] = ly["part"]
        if conf:
            sl["mask"] = list(sl.get("mask") or []) + [{"mask": conf, "blend": "multiply"}]
        sl["_of"] = name
        out.append((f"{stem}:{sub}{sfx}", sl))
    return out
