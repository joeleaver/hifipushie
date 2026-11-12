"""Paint: colour and surface channels laid on the built surface, evaluated per point: every mesh vertex in look,
every texel in export_asset.

spec["paint"] = {name: layer, ...}: layers apply in order, each over the colour so far (every part starts
from its clay colour, spec["parts"][p]["color"]). Paint never changes geometry, so repainting doesn't rebuild.

layer = {"color": [r, g, b] (0..1, sRGB, as you'd pick it) | "#rrggbb", "roughness", "metallic", "specular": 0..1,
         (any of these channels; a layer changes only the ones it gives), "opacity": 0..1 (1),
         "mix": "mix" (default: the colour replaces what's under it) | "multiply" (ink, stains, tattoos: it darkens
         and tints, the variation under it shows through) | "screen" | "overlay" | "soft_light" (colour only),
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
           "side": "both" measures unsigned (points INSIDE the shapes count only near their surface).
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
  spot:    {"at": point | [points], "radius": m | [rx, ry, rz] (or one per point), "soft": 0..1 (0.5), "line": false}:
           a soft ball (an ellipsoid on the world axes) round each point: 1 at its centre and out to (1 - soft) of
           the radius, 0 at the radius. A point is a joint, [x, y, z] or {"at": joint, "offset": [x, y, z]}, so it
           follows the model (the face's lm_* landmarks, finger joints, an elbow). Several points: the strongest.
           "line": true joins the points into one tapered line (radius per point): a scar, a crease, a lash line.
           Drawn per pixel, never mirrored by itself: give both sides' points.
  zone:    "name" | {"name", "grow": 1.0}: a named anatomical zone of a human built on a base (skin.py: "cheek.L",
           "forehead", "nose", "under_eye.R", "knuckles", "palm.L", ...; a name without .L/.R is both sides): spots
           placed from the face landmarks and body joints. `skin_reference` lists them.
  tile:    {"swatch": "pores" | "lines" | "coarse" | "lips" (skin_swatch.py) | "file": path, "size": m (one repeat,
           default the swatch's own), "range": [lo, hi], "vary": true, "rotate": false (true: turned a quarter turn)}: a tiling grey image laid on the three axis
           planes and blended by the normal, read as a 0..1 mask: micro relief (pores, skin lines) far finer than
           the mesh or a baked texel. "vary" mixes a second, larger copy in patches so the repeat doesn't show.
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
  "vertex": true: evaluate this entry per mesh vertex instead of per pixel in the scene's material (a broad, soft
           mask such as a zone confining a fine pattern: it costs the shader one number instead of its nodes).
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

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at paint.NAME: C422). paint_check: checks on a paint spec: validate, side warnings, references, stacks and
generators. paint_patterns: patterns: spots and tiling images, planar and tile coordinates, weave, grain, stretch,
noise, cells. paint_masks: masks: hand-painted values, element random, axis, outline, near and path masks.
paint_apply: applying paint: apply and its channels, bump, the view, a layer's mask and stack, blur, post, blend, the
generators; layers composited per point ahead of the node program.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from .noise import _hash, fbm  # noqa: F401  (fbm is used by materials and tests too)
from .spec import SpecError
from . import moved

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
              "random", "rings", "painted", "outline", "image", "spot", "tile", "zone", "mask")
MIXES = ("mix", "multiply", "screen", "overlay", "soft_light")
PARAMS = {"path": ("width", "profile", "repeat", "scatter"), "near": ("within", "soft", "side"), "facing": ("range",),
          "cavity": ("radius",)}
BLENDS = ("multiply", "add", "subtract", "min", "max", "screen", "overlay", "replace")
ENTRY_OPS = ("blend", "weight", "breakup", "levels", "invert", "blur", "vertex")


def layers(spec: dict) -> dict:
    """The spec's paint layers with material layers expanded into their sub-layers (materials.py), in order, with
    the spec's paint style applied (`style_layer`)."""
    from . import materials, skin
    st = (spec.get("style") or {}).get("paint") or {}
    out = {}
    own = spec.get("paint") or {}
    src = {**skin.layers(spec), **own} if spec.get("skin") else own  # the skin's layers lie under the model's own
    zoned = skin.uses_zones(src)
    for name, ly in src.items():
        if zoned:
            ly = skin.expand_zones(spec, ly, f"paint {name!r}")
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


def _code_hash() -> str:
    """The painting code itself (this module, materials, noise, surface inputs): a recipe change repaints."""
    from pathlib import Path
    here = Path(__file__).parent
    h = hashlib.sha1()
    for f in ("paint.py", *(f"{m}.py" for m in MODULES), "materials.py", "noise.py", "surface.py"):  # (paint.py was split, C427)
        h.update((here / f).read_bytes())
    return h.hexdigest()[:8]


def key(spec: dict) -> str:
    """What painted colours depend on besides the mesh (and the painting code)."""
    return hashlib.sha1(json.dumps([spec.get("paint"), spec.get("skin"), spec.get("parts"), (spec.get("story") or {}).get("directions"),
                                    _CODE], sort_keys=True,
                                   default=float).encode()).hexdigest()[:12]


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


TILE_VARY = (1.618, 0.07)  # the second copy's size (x the tile's), and the patch size of the mix between them (m)


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


_PAINTED: dict = {}


def _ramp(x, a, b):
    """0 at a, 1 at b (either order), smooth in between."""
    d = np.asarray(b - a, float)
    t = np.clip((x - a) / np.where(d == 0, 1e-12, d), 0, 1)
    return t * t * (3 - 2 * t)


_TAGS: dict[str, set] = {}

_AXES = np.eye(3)
_IN_PLANE = ([0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0])  # default long axis on each axis plane

GRAIN_OFFSET = np.array([97.3, 61.7, 83.1])  # x an element's grain_seed: each element its own piece of pattern


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("paint_check", "paint_patterns", "paint_masks", "paint_apply")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
_CODE = _code_hash()  # (below MODULES: the painting code is every module of the family)
