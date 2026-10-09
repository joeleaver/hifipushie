"""Clutter kit: the small solids a terrain is scattered with by the ten thousand (boulders, water-worn river rocks,
cobble patches, bank slabs, driftwood), as game assets in a style.

How prop artists make them: sculpt a HIGH form, decimate to a few LODs, bake the high form's normals / occlusion /
colour onto the low ones, scatter with yaw / scale / squash so three or four shapes never read as clones. Here the high
form is a signed distance (as the terrain's rock is), so the rock speaks the cliffs' language: a block bounded by two
JOINT families and BEDDING planes (terrain_stack / terrain_blocks), corners chipped off, soft beds set back, weathered
round by a smooth max (`bevel`) or water-worn toward an ellipsoid (`round`). Driftwood is crooked round cones with
stubs. A preset (`clutter_presets/<kind>.json`) says what the thing is; a style sheet (`clutter_styles/<style>.json`)
says how that style shapes and paints it (blobby = pebbles, anime = crisp planes + painted bands, cartoon = few big
facets + a dark edge, pixar = soft sculpt + gradient); colours start from the terrain's rock colour turned by the
terrain style's saturation / value.

Each variant (a seed) is meshed once, decimated per LOD (pyfqmr), put back on the field; ONE atlas per asset holds
every variant: six box-projected charts a variant (a texel = the first surface a ray along that axis meets, so every
LOD reads the same picture by POSITION and nothing is unwrapped), baked from the field itself + a bake-only micro
relief: albedo, tangent normal (TANGENT written: the chart's own axes), occlusion / roughness. Files and json follow
the plant contract (veg_export.CONTRACT; `<stem>_seasons.json` with grade "clutter").

Metres, Z up; the asset is authored at scale 1 = 1 m largest plan dimension, pivot at the ground line (`sink_m` of it
is below)."""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import numpy as np

from . import noise

HERE = Path(__file__).parent
ROCK_SRGB = [0.36, 0.34, 0.31]  # terrain_rock.base_colour's grey rock: the reference a style turns
WOOD_SRGB = [0.44, 0.41, 0.36]   # weathered, barkless wood (silver grey)

FORM = {  # a rock's form; ranges are drawn per variant
    "aspect": [[0.6, 0.85], [0.42, 0.62]],  # mid / long and short / long axis (long = 1: the largest plan dimension)
    "faces": [6, 9],          # major faces, at oblique angles all round
    "jitter": 16.0,           # deg: how far each face's direction strays from an even spread
    "face_in": [0.7, 0.95],   # each face's distance from the middle, as a share of the ellipsoid's reach that way
    "bedded": 0.7,            # probability of a pair of off-parallel bedding faces (a flat-ish top and underside)
    "tilt": 8.0,              # deg: how far off parallel they are
    "dip": [5.0, 35.0],       # deg: the bedding's tilt (a fallen block's beds are never level)
    "tumble": 14.0,           # deg: the whole block tipped
    "chips": [4, 8],          # corners / edges broken off (planes), of which
    "broken": [1, 2],         # are deep breaks
    "break": [0.2, 0.42],     # a deep break's depth, as a share of the block's reach in that direction
    "chip": [0.04, 0.14],     # a shallow chip's
    "bevel": 0.06,            # m: arrises rounded (weathering)
    "top_round": 1.5,         # the top's arrises rounded this much more than the foot's (x bevel, added)
    "taper": 0.22,            # wider at the base than at the top (0 = a prism)
    "round": 0.0,             # 0..1: toward an ellipsoid (water-worn)
    "bend": 0.0,              # a bean: the long axis bowed, x the height
    "dent": 0.0,              # probability of one soft dent
    "split": 0.0,             # probability of a crack through the block
    "split_gap": [0.012, 0.03],  # m: its half width
    "beds": [0, 2],           # partings along the bedding (thin grooves round part of the block)
    "bed_set": [0.008, 0.02],  # m: their depth
    "bed_thick": [0.006, 0.016],  # m: their half width
    "lumps": 0.02,            # m: slow unevenness of the faces
    "lump_size": 0.35,        # m
    "sink": 0.26,             # share of the height below the ground line (the mass sits IN the ground)
    "lean": 0.0,              # probability of a second, smaller block leaning on the first
    "cluster": None,          # {"count": [7, 13], "stone": [0.1, 0.26], "pile": 0.3}: many small stones as one asset
}
PAINT = {  # how the surface is painted (albedo multipliers round 1) and what relief only the maps carry
    "tone": 0.1, "tone_size": 0.25,   # slow tone patches
    "face_tone": 0.06,                # each joint / chip face its own tone
    "speckle": 0.05,                  # mineral grain (per texel-ish)
    "edge_light": 0.12,               # worn arrises paler (convex)
    "cavity": 0.25,                   # cracks and hollows darker (concave)
    "ink": 0.0, "ink_width": 0.012,   # a dark line along arrises (cartoon)
    "bands": 0.0, "band_thick": [0.03, 0.12], "band_tones": [-0.6, 0.2, 0.7, -0.25],  # painted strata along the bedding
    "gradient": 0.0,                  # lighter top, darker foot (0..1)
    "top_light": 0.0,                 # up-facing faces lighter (a clear top plane)
    "foot": 0.3, "foot_height": 0.1,  # the band above the ground line darker (damp, soil-stained): m at 1 m across
    "top": 0.25, "top_color": [0.5, 0.52, 0.36], "top_size": 0.12,  # lichen / moss on up-facing rock
    "lichen": 0.35, "lichen_size": 0.13,  # crusts: round patches in clusters, on tops and on one side (the weather side)
    "lichen_colors": [[0.5, 0.53, 0.45], [0.56, 0.57, 0.5], [0.62, 0.55, 0.3], [0.6, 0.61, 0.56], [0.47, 0.5, 0.44]],  # grey-greens, one ochre, pale
    "streaks": 0.2, "streak_width": 0.035,  # darker rain streaks running down steep faces from the top
    "foot_color": [0.2, 0.2, 0.12], "foot_tint": 0.35,  # the foot band stained toward soil / algae (with `foot`)
    "minerals": [[1.0, 1.0, 1.0], [1.05, 1.0, 0.94], [0.96, 0.99, 1.03], [1.03, 0.98, 0.92]],  # each variant's own rock: x the colour
    "moss": 0.0, "moss_color": [0.25, 0.36, 0.14], "moss_band": [0.15, 0.6],  # a mossy band (share of height)
    "ao": 0.6,                        # occlusion strength (also baked half into the albedo's foot)
    "roughness": 0.9,
    "grain": 0.0015, "grain_size": 0.02,     # m: bake-only relief
    "cracks": 0.004, "crack_size": 0.3,
    "laminae": 0.0, "lamina": 0.012,
    "pits": 0.0,
    "normals": 30.0,                  # deg: LOD faces meeting sharper than this keep their own normals (0 = all smooth)
}
WOOD = {
    "pieces": [1, 1],          # logs in the asset (a jam: several)
    "length": [0.85, 1.0],     # of the main piece (x = 1)
    "radius": [0.075, 0.105],  # at the butt
    "taper": [0.45, 0.8],      # tip radius / butt radius
    "crook": 0.05,             # sideways wander of the axis, x length
    "stubs": [1, 4],           # broken branch stubs
    "stub": [0.05, 0.16],      # their length
    "fork": 0.3,               # probability the piece forks (a branch)
    "roots": [0, 0],           # root stubs fanning from the butt (a root plate)
    "broken": 0.6,             # how jagged the broken ends are (0 = sawn)
    "bevel": 0.012,
    "lumps": 0.006, "lump_size": 0.12,
    "sink": 0.18,
    "pile": 0.5,               # a jam: how far pieces lie across each other (0 = parallel)
}
WOOD_PAINT = {
    "tone": 0.12, "tone_size": 0.2, "streak": 0.2, "streak_size": [0.25, 0.012], "speckle": 0.03,
    "edge_light": 0.1, "cavity": 0.3, "ink": 0.0, "ink_width": 0.008, "gradient": 0.1, "ao": 0.6, "roughness": 0.85,
    "grooves": 0.003, "groove_size": 0.012, "cracks": 0.003, "crack_size": 0.2, "normals": 40.0,
    "top": 0.0, "top_color": [0.5, 0.52, 0.36], "top_size": 0.1, "moss": 0.0, "moss_color": [0.25, 0.36, 0.14],
    "moss_band": [0.0, 0.5], "top_light": 0.0, "foot": 0.25, "foot_height": 0.03,
    "lichen": 0.1, "lichen_size": 0.04, "lichen_colors": [[0.62, 0.65, 0.56], [0.72, 0.62, 0.3]], "streaks": 0.0, "streak_width": 0.03,
    "foot_color": [0.2, 0.2, 0.12], "foot_tint": 0.3, "minerals": [[1.0, 1.0, 1.0], [1.06, 1.0, 0.92], [0.94, 0.98, 1.04], [1.04, 0.97, 0.9]],
    "bark": 0.35, "bark_color": [0.2, 0.14, 0.09], "bark_size": 0.18,   # patches of bark still on (dark, rough, proud)
    "bleach": 0.25,           # sun-bleached paler on top
}
BUSH = {  # a clutter bush: a lumpy leafy dome (closed, opaque) + leaf sprays on alpha cards breaking its outline
    "aspect": [[0.8, 1.0], [0.6, 0.8]],  # depth / width and height / width of the dome
    "lobes": [3, 6],          # lobes round the main dome
    "lobe": [0.2, 0.3],       # their radius, x the width
    "lobe_out": [0.5, 0.85],  # how far out from the middle they sit (1 = at the dome's edge)
    "join": 0.1,              # m: how softly lobes run together (small = distinct clumps)
    "lumps": 0.03, "lump_size": 0.22,
    "cards": [24, 30],        # leaf sprays standing out of the dome at LOD 0 (0 = none: a closed style)
    "card": [0.3, 0.42],      # their length, m
    "card_out": 0.58,          # the share of a spray standing out past the dome's surface
    "card_up": 0.35,          # how far sprays turn upward from straight out
    "cards_lod": [1.0, 0.5, 0.2],  # the share of the sprays each LOD keeps (kept ones drawn larger)
    "sink": 0.0,
}
BUSH_PAINT = {
    "tone": 0.1, "tone_size": 0.3, "face_tone": 0.1, "speckle": 0.0, "edge_light": 0.1, "cavity": 0.35, "ink": 0.0, "ink_width": 0.02,
    "gradient": 0.3, "top_light": 0.15, "foot": 0.12, "foot_height": 0.1, "ao": 0.6, "roughness": 0.8, "normals": 0.0,
    "top": 0.0, "top_color": [0.5, 0.52, 0.36], "top_size": 0.1, "moss": 0.0, "moss_color": [0.25, 0.36, 0.14], "moss_band": [0.0, 0.5],
    "lichen": 0.0, "lichen_size": 0.05, "lichen_colors": [[0.6, 0.6, 0.5]], "streaks": 0.0, "streak_width": 0.03, "foot_color": [0.12, 0.14, 0.08],
    "foot_tint": 0.0, "minerals": [[1.0, 1.0, 1.0], [1.06, 1.02, 0.9], [0.92, 1.0, 1.0], [1.0, 0.95, 0.85]],
    "leaf_size": 0.04,        # m: the painted leaves on the dome (cells); 0 = none (a flat colour)
    "leaf_tone": 0.25,        # each leaf's own tone
    "leaf_gap": 0.55,         # how dark the gaps between leaves are
    "leaf_bump": 0.004,       # m: each leaf a small dome in the normal map
    "steps": 0,               # tones cut into this many flat steps (painted look); 0 = continuous
    "flowers": 0.25, "flower_color": [0.95, 0.8, 0.15], "flower_size": 0.014,  # in the spring picture
    "spray": {"leaves": [10, 16], "leaf": [0.07, 0.1], "round": 0.42, "tones": 0.25, "outline": 0.0, "midrib": 0.3},  # a card's picture
}
LITTER = {  # a debris patch: fallen leaves, twigs and bits lying on the ground, as one alpha card (a decal with a mesh)
    "leaves": [70, 110],      # in the summer picture (autumn x `autumn`, winter x `winter`)
    "leaf": [0.05, 0.085],    # m: a leaf's length at 1 m across
    "round": 0.55,            # width / length
    "lobed": 0.0,             # 0..1: how deeply lobed (oak)
    "twigs": [5, 10], "twig": [0.12, 0.3],
    "bits": [20, 40],         # bark and stone crumbs
    "tones": 0.3,             # each leaf's own tone
    "steps": 0,               # tones cut into steps (painted)
    "outline": 0.0,           # a dark line round each leaf (x the tile)
    "shadow": 0.45,           # each leaf darkens what lies under its edge
    "autumn": 1.7, "winter": 0.8, "spring": 0.7,
    "colors": {"summer": [[0.36, 0.27, 0.16], [0.42, 0.33, 0.2], [0.3, 0.24, 0.15]],
               "autumn": [[0.72, 0.5, 0.14], [0.66, 0.3, 0.1], [0.78, 0.62, 0.2], [0.5, 0.3, 0.14]],
               "winter": [[0.24, 0.18, 0.12], [0.3, 0.23, 0.15], [0.2, 0.16, 0.12]],
               "spring": [[0.3, 0.23, 0.15], [0.36, 0.28, 0.17], [0.38, 0.44, 0.2]]},
    "twig_color": [0.22, 0.17, 0.12],
    "dome": 0.02,             # m: the patch's middle lifted (it lies over the ground's small bumps)
    "sink": 0.0,
}
LEAF_SRGB = [0.26, 0.36, 0.17]  # scrub (sage / gorse green)
LEAF_SEASONS = {"spring": {"mix": [0.42, 0.6, 0.2], "amount": 0.35, "flowers": 1.0}, "summer": {},
                "autumn": {"mix": [0.5, 0.44, 0.2], "amount": 0.3}, "winter": {"mix": [0.27, 0.3, 0.22], "amount": 0.5}}
LODS = {"bush": [170, 80, 40], "rock": [300, 100, 44], "cluster": [360, 120, 40], "wood": [220, 80, 24], "jam": [520, 170, 56]}
LOD_IOU = 0.9  # a LOD's outline against LOD 0's, mean of 8 directions: under it a single stone's LOD is its hull
LOD_SWITCH = [14.0, 40.0, 130.0]  # m x the instance's scale: LOD 1 from, LOD 2 from, gone at (fade over the last fifth)
ATLAS = 1024


# ---------------------------------------------------------------------------------------------------------- specs
def presets() -> list:
    return sorted(p.stem for p in (HERE / "clutter_presets").glob("*.json"))


def styles() -> list:
    return ["realistic"] + sorted(p.stem for p in (HERE / "clutter_styles").glob("*.json") if p.stem != "realistic")


def _merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def style_sheet(style) -> dict:
    """A style's clutter sheet (name or {"sheet": name, ...overrides})."""
    over = {}
    if isinstance(style, dict):
        over = {k: v for k, v in style.items() if k != "sheet"}
        style = style.get("sheet", "realistic")
    style = style or "realistic"
    p = HERE / "clutter_styles" / f"{style}.json"
    if not p.exists():
        raise ValueError(f"clutter style {style!r} unknown ({', '.join(styles())})")
    st = _merge(json.loads(p.read_text()), over)
    st["name"] = style
    return st


def _layered(layers, variant):
    """A form from its layers: the preset's, a variant's own (proportions), the style's, the style's multipliers, the
    spec's. The style comes after the variant: a pebble style rounds every variant, whatever its proportions."""
    pre, st_form, st_scale, own = layers
    form = _merge(_merge(_merge(pre, variant), st_form), own)
    for k, x in (st_scale or {}).items():
        if k in form and form[k] is not None:
            form[k] = (np.asarray(form[k], float) * x).tolist() if isinstance(form[k], list) else form[k] * x
    return form


def resolve(spec: dict) -> dict:
    """A clutter spec with its preset under it and its style's numbers laid over the form and paint:
    {"kind": preset, "style": name | {...}, "seed", "variants", "form": {...}, "paint": {...}, "color": sRGB,
    "lods": [triangles...], "atlas": px, "moss", "wet"}. Unknown keys are refused."""
    kind = spec.get("kind", "boulder")
    p = HERE / "clutter_presets" / f"{kind}.json"
    if not p.exists():
        raise ValueError(f"clutter kind {kind!r} unknown ({', '.join(presets())})")
    pre = json.loads(p.read_text())
    st = style_sheet(spec.get("style"))
    mat = pre.get("material", "rock")
    base_form, base_paint = ((WOOD, WOOD_PAINT) if mat == "wood" else (BUSH, BUSH_PAINT) if mat == "leaf" else (LITTER, {}) if mat == "litter"
                             else (FORM, PAINT))
    S = st.get(mat) or {}
    layers = (_merge(base_form, pre.get("form")), S.get("form"), S.get("scale"), spec.get("form"))
    form = _layered(layers, None)
    paint = _merge(_merge(_merge(base_paint, pre.get("paint")), S.get("paint")), spec.get("paint"))
    for name, d, ref in (("form", form, base_form), ("paint", paint, base_paint)):
        bad = set(d) - set(ref)
        if bad:
            raise ValueError(f"clutter {name} keys {sorted(bad)} unknown ({', '.join(sorted(ref))})")
    known = {"kind", "style", "seed", "variants", "form", "paint", "color", "lods", "atlas", "name", "moss", "wet"}
    bad = set(spec) - known
    if bad:
        raise ValueError(f"clutter spec keys {sorted(bad)} unknown ({', '.join(sorted(known))})")
    if spec.get("moss") is not None:
        paint["moss"] = float(spec["moss"])
    from .terrain_style import _hsv
    col = st.get("colour") or {}
    ref = spec.get("color") or S.get("color") or pre.get("color") or (WOOD_SRGB if mat == "wood" else LEAF_SRGB if mat == "leaf" else ROCK_SRGB)
    color = spec.get("color") or _hsv(ref, col.get("saturation", 1.0) * S.get("saturation", 1.0),
                                      col.get("value", 1.0) * S.get("value", 1.0))
    shape = pre.get("shape") or ("cluster" if form.get("cluster") else "rock")
    if mat == "litter":
        LODS.setdefault("litter", [8, 2])
    return {"kind": kind, "material": mat, "shape": shape, "style": st["name"], "seed": int(spec.get("seed", 1)),
            "variants": int(spec.get("variants", pre.get("variants", 4))), "form": form, "paint": paint,
            "color": [float(c) for c in color], "lods": list(spec.get("lods") or pre.get("lods") or LODS[shape]),
            "atlas": int(spec.get("atlas", pre.get("atlas", ATLAS))), "about": pre.get("about", ""),
            "collision": pre.get("collision", "convex" if shape == "rock" else None),
            "wet": _merge({"darken": 0.55, "roughness": 0.25, "band": pre.get("wet_band", 0.0)}, spec.get("wet") if isinstance(spec.get("wet"), dict) else None),
            "variant_forms": pre.get("variant_forms"), "_layers": layers,
            "seasons": ({se: dict(v, mix=_hsv(v["mix"], col.get("saturation", 1.0), col.get("value", 1.0))) if v else {} for se, v in LEAF_SEASONS.items()}
                        if mat == "leaf" else {"summer": {}}),
            "snow": st.get("snow"), "size_range": pre.get("size_range"), "place": pre.get("place")}


# ------------------------------------------------------------------------------------------------------- the forms
def _smax(vals, k):
    out = vals[0]
    for v in vals[1:]:
        if np.ndim(k) == 0 and k <= 0:
            out = np.maximum(out, v)
        else:
            h = np.clip(0.5 + 0.5 * (v - out) / k, 0, 1)
            out = out * (1 - h) + v * h + k * h * (1 - h)
    return out


def _rot(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def _u(rng, r):
    return float(rng.uniform(r[0], r[1])) if isinstance(r, (list, tuple)) else float(r)


class Stone:
    """One loose block. Its faces are planes at oblique angles round an ellipsoid of three unequal axes (a loose block
    broke along three or four joint sets at random obliquity, never a box), a pair of off-parallel bedding faces
    (`bedded`), one or two corners broken off deep and several shallow chips; met in a smooth max whose radius grows
    upward (tops weather rounder than undersides), wider low than high (`taper`: a stable base), blended toward a
    bent ellipsoid (`round`: water-worn; `bend`: a bean), with thin partings along tilted beds (`beds`), maybe a
    split (`split`) and a dent (`dent`)."""

    def __init__(self, rng, form, size=1.0, centre=(0, 0, 0), flat=False):
        f = form
        self.size = size
        ay, az = _u(rng, f["aspect"][0]), _u(rng, f["aspect"][1])
        self.half = 0.5 * size * np.array([1.0, ay, az])
        self.c = np.asarray(centre, float)
        t = f["tumble"] * (0.3 if flat else 1.0)
        ax = rng.normal(0, 1, 3)
        ax[2] *= 0.3
        self.R = _rot([0, 0, 1], rng.uniform(0, 360)) @ _rot(ax / np.linalg.norm(ax), rng.uniform(-t, t))
        a, b, c = self.half
        N, D = [], []

        def support(n):  # the ellipsoid's reach along n
            return float(np.linalg.norm(np.asarray(n) * self.half))

        def plane(n, share):
            n = np.asarray(n, float) / np.linalg.norm(n)
            N.append(n)
            D.append(support(n) * share)
        # bedding: a top and an underside, off parallel
        dip, daz = math.radians(_u(rng, f["dip"])), rng.uniform(0, 2 * math.pi)
        self.bed_n = np.array([math.sin(dip) * math.cos(daz), math.sin(dip) * math.sin(daz), math.cos(dip)])
        if rng.uniform() < f["bedded"]:
            w = math.radians(f["tilt"])
            plane(self.bed_n + w * rng.normal(0, 1, 3), rng.uniform(0.78, 0.95))
            plane(-self.bed_n + 1.5 * w * rng.normal(0, 1, 3), rng.uniform(0.7, 0.9))
        # the major faces: directions spread over the sphere (a golden spiral turned at random), each jittered
        nf = int(rng.integers(f["faces"][0], f["faces"][1] + 1))
        g = (1 + 5 ** 0.5) / 2
        i = np.arange(nf)
        z = 1 - 2 * (i + 0.5) / nf
        dirs = np.c_[np.sqrt(1 - z * z) * np.cos(2 * np.pi * i / g), np.sqrt(1 - z * z) * np.sin(2 * np.pi * i / g), z]
        axq = rng.normal(0, 1, 3)
        Q = _rot([0.0, 0.0, 1.0], rng.uniform(0, 360)) @ _rot(axq / np.linalg.norm(axq), rng.uniform(0, 360))
        jit = math.radians(f["jitter"])
        for d_ in dirs @ Q.T:
            n = d_ + jit * rng.normal(0, 1, 3)
            if N and max(float(n @ m) / np.linalg.norm(n) for m in N) > 0.93:
                continue  # (nearly a face that is already there)
            plane(n, rng.uniform(f["face_in"][0], f["face_in"][1]))
        for ax_ in range(3):  # (never unbounded: a few faces may leave a side open; these lie outside a closed block)
            for sg in (1.0, -1.0):
                n = np.zeros(3)
                n[ax_] = sg
                if not N or max(float(n @ m) for m in N) < 0.8:
                    N.append(n)
                    D.append(self.half[ax_] * 1.12)
        base = (np.array(N), np.array(D))
        corners = self._corners(*base)
        # corners broken off: one or two deep, the rest shallow
        nch = int(rng.integers(f["chips"][0], f["chips"][1] + 1))
        deep = int(rng.integers(f["broken"][0], f["broken"][1] + 1))
        for j in range(nch):
            if len(corners):
                n = corners[int(rng.integers(len(corners)))] / self.half + 0.35 * rng.normal(0, 1, 3)
            else:
                n = rng.normal(0, 1, 3)
            n /= np.linalg.norm(n)
            if j < deep and n[2] < -0.2:
                n[2] = abs(n[2])  # (the big breaks are where they show: not under the block)
            reach = float((corners @ n).max()) if len(corners) else support(n)
            N.append(n)
            D.append(reach * (1 - (_u(rng, f["break"]) if j < deep else _u(rng, f["chip"]))))
        self.N, self.D = np.array(N), np.array(D)
        self.tone = rng.uniform(-1, 1, len(N))
        self.bevel = f["bevel"] * size
        self.top_round = f["top_round"]
        self.taper = f["taper"]
        self.round = f["round"]
        self.bend = f["bend"] * rng.choice([-1, 1]) * rng.uniform(0.6, 1.0)
        self.beds = []
        for _ in range(int(rng.integers(f["beds"][0], f["beds"][1] + 1))):
            n = self.bed_n + math.radians(12.0) * rng.normal(0, 1, 3)  # (partings are never quite parallel)
            self.beds.append((n / np.linalg.norm(n), rng.choice([-1, 1]) * rng.uniform(0.25, 0.8) * c, _u(rng, f["bed_thick"]) * size, _u(rng, f["bed_set"]) * size,
                              rng.uniform(0, 2 * math.pi), rng.uniform(0.15, 0.5)))
        self.split = None
        if rng.uniform() < f["split"]:
            n = np.array([rng.normal(), rng.normal(), 0.35 * rng.normal()])
            n /= np.linalg.norm(n)
            self.split = (n, rng.uniform(-0.25, 0.25) * a, _u(rng, f["split_gap"]) * size, int(rng.integers(1 << 30)))
        self.dent = None
        if rng.uniform() < f["dent"]:
            n = np.array([rng.normal(), rng.normal(), abs(rng.normal()) * 0.6 + 0.2])
            n /= np.linalg.norm(n)
            r = rng.uniform(0.3, 0.5) * size * az
            self.dent = (n * self.half * 1.0 + n * r * 0.72, r)
        self.lumps, self.lump_size, self.seed = f["lumps"] * size, f["lump_size"] * size, int(rng.integers(1 << 30))
        ext = np.abs(corners).max(0) if len(corners) else self.half
        ext = np.maximum(ext, self.half) * (1 + abs(self.taper) * 0.5) + abs(self.bend) * c
        self.r_bound = float(np.linalg.norm(ext)) * 1.05 + 0.02
        cw = np.array([[sx * ext[0], sy * ext[1], sz * ext[2]] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) @ self.R.T + self.c
        self.lo, self.hi = cw.min(0) - 0.03 * size - 0.01, cw.max(0) + 0.03 * size + 0.01

    def _corners(self, N, D):
        """Vertices of the polyhedron {N p <= D} (triples of planes), for chip depths."""
        out = []
        n = len(N)
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(j + 1, n):
                    A = N[[i, j, k]]
                    if abs(np.linalg.det(A)) < 1e-3:
                        continue
                    p = np.linalg.solve(A, D[[i, j, k]])
                    if (N @ p <= D + 1e-6).all():
                        out.append(p)
        return np.array(out) if out else np.zeros((0, 3))

    def local(self, p):
        return (p - self.c) @ self.R

    def sd(self, p, info=False):
        q0 = self.local(p)
        q = q0
        zr = np.clip(q0[:, 2] / self.half[2], -1.3, 1.3)
        if self.taper or self.bend:
            q = q0.copy()
            if self.bend:  # a bean: the long axis bowed
                q[:, 2] = q[:, 2] + self.bend * self.half[2] * ((q0[:, 0] / self.half[0]) ** 2 - 0.4)
            if self.taper:  # wider low, narrower high
                q[:, :2] = q[:, :2] / (1 - 0.5 * self.taper * zr)[:, None]
        vals = q @ self.N.T - self.D  # (n, planes)
        k = self.bevel * (1 + self.top_round * np.clip(0.5 + 0.5 * zr, 0, 1)) if self.top_round else self.bevel
        d = _smax([vals[:, i] for i in range(vals.shape[1])], k)
        if self.round > 0:
            kk = np.linalg.norm(q / self.half, axis=1)
            de = (kk - 1.0) * self.half.min() * (0.6 + 0.4 * np.minimum(kk, 2.0) / 2.0) / 0.8
            d = (1 - self.round) * d + self.round * de
        zb = q0 @ self.bed_n
        for n, z0, th, dep, az, cover in self.beds:  # a parting: a thin groove round part of the block
            w = np.clip(1 - np.abs(q0 @ n - z0) / th, 0, 1)
            w = w * w * (3 - 2 * w)
            ang = np.arctan2(q0[:, 1], q0[:, 0])
            along = np.clip((np.cos(ang - az) - (1 - 2 * cover)) / 0.4, 0, 1)
            d = d + dep * w * along
        if self.split is not None:  # a crack through the block: a V groove along a wandering plane
            n, off, gap, sd_ = self.split
            x = q0 @ n - off + 0.03 * self.size * (noise.fbm(q0, 0.25 * self.size, 2, sd_) - 0.5) * 2
            d = d + np.clip(1 - np.abs(x) / gap, 0, 1) ** 2 * 2.5 * gap
        if self.dent is not None:
            pc, r = self.dent
            dd = r - np.linalg.norm(q0 - pc, axis=1)
            d = _smax([d, dd], 0.35 * r)
        if self.lumps:
            d = d + self.lumps * (noise.fbm(q0, self.lump_size, 2, self.seed) - 0.5) * 2
        if not info:
            return d
        o = np.argsort(vals, axis=1)
        i1, i2 = o[:, -1], o[:, -2]
        r = np.arange(len(q))
        return d, {"face": i1, "edge": vals[r, i1] - vals[r, i2], "tone": self.tone[i1], "bed": zb, "q": q0,
                   "axis": None}


class Wood:
    """A piece of driftwood: a crooked tapering stem, broken stubs, maybe a fork; round cones met softly."""

    def __init__(self, rng, form, size=1.0, centre=(0, 0, 0), yaw=0.0, pitch=0.0):
        f = form
        L = _u(rng, f["length"]) * size
        r0 = _u(rng, f["radius"]) * size
        r1 = r0 * _u(rng, f["taper"])
        n = 6
        t = np.linspace(-0.5, 0.5, n)
        ph = rng.uniform(0, 6.28, 2)
        P = np.c_[t * L, f["crook"] * L * np.sin(3.0 * t + ph[0]) + 0.3 * f["crook"] * L * np.sin(9 * t + ph[1]),
                  0.5 * f["crook"] * L * np.sin(2.3 * t + ph[1])]
        Rr = np.linspace(r0, r1, n)
        segs = [(P[i], P[i + 1], Rr[i], Rr[i + 1]) for i in range(n - 1)]
        self.n_main = len(segs)
        for _ in range(int(rng.integers(f["stubs"][0], f["stubs"][1] + 1))):
            i = int(rng.integers(0, n - 2))
            a = P[i] + (P[i + 1] - P[i]) * rng.uniform()
            d = np.array([rng.uniform(0.2, 0.8), rng.normal(), 0.45 * rng.normal()])
            d /= np.linalg.norm(d)
            l = _u(rng, f["stub"]) * size
            segs.append((a, a + d * l, Rr[i] * 0.55, Rr[i] * 0.3))
        if rng.uniform() < f["fork"]:
            i = int(rng.integers(1, n - 2))
            d = np.array([0.8, rng.choice([-1, 1]) * rng.uniform(0.4, 0.8), rng.uniform(-0.08, 0.18)])
            d /= np.linalg.norm(d)
            l = rng.uniform(0.25, 0.45) * L
            m = P[i] + d * l * 0.5 + 0.03 * L * rng.normal(0, 1, 3)
            segs.append((P[i], m, Rr[i] * 0.7, Rr[i] * 0.5))
            segs.append((m, P[i] + d * l, Rr[i] * 0.5, Rr[i] * 0.3))
        nr = int(rng.integers(f["roots"][0], f["roots"][1] + 1))
        if nr:  # a root plate: the butt swells, roots fan out square to the stem and a little back
            ax0 = (P[1] - P[0]) / np.linalg.norm(P[1] - P[0])
            e1 = np.cross(ax0, [0, 0, 1.0])
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(ax0, e1)
            segs[0] = (segs[0][0], segs[0][1], r0 * 1.45, segs[0][3])
            for i in range(nr):
                a = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / nr
                d = math.cos(a) * e1 + math.sin(a) * e2 - ax0 * rng.uniform(0.1, 0.45)
                d /= np.linalg.norm(d)
                l = rng.uniform(0.1, 0.2) * size
                m_ = P[0] + d * l * 0.55 + 0.02 * size * rng.normal(0, 1, 3)
                segs.append((P[0] + ax0 * 0.01, m_, r0 * 0.75, r0 * 0.42))
                segs.append((m_, P[0] + d * l - ax0 * 0.03 * size, r0 * 0.42, r0 * 0.16))
        self.broken = f["broken"]
        self.ends = (P[0].copy(), P[-1].copy(), (P[1] - P[0]) / np.linalg.norm(P[1] - P[0]), (P[-1] - P[-2]) / np.linalg.norm(P[-1] - P[-2]), r0, r1, nr > 0)
        R = _rot([0, 0, 1], math.degrees(yaw)) @ _rot([0, 1, 0], math.degrees(pitch))
        c = np.asarray(centre, float)
        self.ends = (self.ends[0] @ R.T + c, self.ends[1] @ R.T + c, self.ends[2] @ R.T, self.ends[3] @ R.T, r0, r1, nr > 0)
        self.segs = [(a @ R.T + c, b @ R.T + c, ra, rb) for a, b, ra, rb in segs]
        self.bevel = f["bevel"] * size
        self.lumps, self.lump_size, self.seed = f["lumps"] * size, f["lump_size"] * size, int(rng.integers(1 << 30))
        self.c = c
        self.tone = rng.uniform(-1, 1, len(self.segs))
        self.r_bound = 0.5 * L + r0 * 2 + 0.2 * size
        ends = np.array([[a - ra, a + ra, b - rb, b + rb] for a, b, ra, rb in self.segs]).reshape(-1, 3)
        self.lo, self.hi = ends.min(0) - 0.02 * size, ends.max(0) + 0.02 * size

    def sd(self, p, info=False):
        best = np.full(len(p), 1e9)
        soft = None
        ax = np.zeros((len(p), 3))
        sc = np.zeros(len(p))
        ton = np.zeros(len(p))
        second = np.full(len(p), 1e9)
        s0 = 0.0
        for k, (a, b, ra, rb) in enumerate(self.segs):
            ab = b - a
            l2 = float(ab @ ab)
            t = np.clip(((p - a) @ ab) / l2, 0, 1)
            # a blunt broken end: beyond the end the distance grows along the axis (no round cap)
            d = np.linalg.norm(p - a - t[:, None] * ab, axis=1) - (ra + (rb - ra) * t)
            better = d < best
            second = np.where(better, best, np.minimum(second, d))
            if info:
                ax[better] = ab / math.sqrt(l2)
                sc[better] = s0 + t[better] * math.sqrt(l2)
                ton[better] = self.tone[k]
            best = np.minimum(best, d)
            h = self.bevel
            soft = d if soft is None else (lambda x, y: np.minimum(x, y) - h * np.clip(1 - np.abs(x - y) / (4 * h), 0, 1) ** 2)(soft, d) if h > 0 else np.minimum(soft, d)
            s0 += math.sqrt(l2)
        d = soft
        if self.lumps:
            d = d + self.lumps * (noise.fbm(p - self.c, self.lump_size, 2, self.seed) - 0.5) * 2
        if self.broken:  # the stem's ends broken off: a jagged oblique face instead of a round cap (splinters along the grain)
            e0, e1, a0, a1, r0, r1, rooted = self.ends
            for e, a, r, sgn, skip in ((e0, a0, r0, -1.0, rooted), (e1, a1, r1, 1.0, False)):
                if skip:
                    continue
                x = (p - e) @ a * sgn
                near = np.linalg.norm(p - e, axis=1) < 4 * r
                if near.any():
                    q = p[near] - e
                    perp = q - np.outer(q @ a, a)
                    jag = self.broken * r * (1.6 * (noise.fbm(perp / (0.35 * r) + self.seed % 97, 1.0, 2, self.seed + 3) - 0.5) + 0.8 * perp @ np.cross(a, [0.3, 0.2, 1.0]) / r)
                    d[near] = np.maximum(d[near], x[near] + 0.4 * r - jag)
        if not info:
            return d
        return d, {"face": np.zeros(len(p), int), "edge": np.full(len(p), 1.0), "tone": ton, "bed": sc,
                   "q": p - self.c, "axis": ax}


class Bush:
    """A bush's body: a dome going straight down to the ground with lobes round it, met softly."""

    def __init__(self, rng, form, size=1.0):
        f = form
        ay, H = _u(rng, f["aspect"][0]), _u(rng, f["aspect"][1]) * size
        self.H = H
        self.c = np.zeros(3)
        R = 0.5 * size
        # (centre, radii): the main dome, then the lobes
        self.ell = [(np.array([0.0, 0.0, 0.1 * H]), np.array([0.8 * R, 0.8 * R * ay, 0.84 * H]))]  # (a dome: widest at the ground)
        for _ in range(int(rng.integers(f["lobes"][0], f["lobes"][1] + 1))):
            a = rng.uniform(0, 2 * math.pi)
            r = _u(rng, f["lobe"]) * size
            o = _u(rng, f["lobe_out"])
            zc = rng.uniform(0.12, 0.62) * H
            shrink = math.sqrt(max(1 - (zc / H) ** 2, 0.15))  # (the dome is narrower up there)
            c = np.array([(R - 0.6 * r) * o * shrink * math.cos(a), (R * ay - 0.6 * r) * o * shrink * math.sin(a), zc])
            c[2] = min(c[2], H - 0.8 * r)
            self.ell.append((c, np.array([r, r, 0.85 * r]) * rng.uniform(0.9, 1.15, 3)))
        self.tone = rng.uniform(-1, 1, len(self.ell))
        self.join = f["join"] * size
        self.lumps, self.lump_size, self.seed = f["lumps"] * size, f["lump_size"] * size, int(rng.integers(1 << 30))
        self.lo = np.array([-R * 1.25, -R * 1.25, -0.12 * size])
        self.hi = np.array([R * 1.25, R * 1.25, H * 1.2])
        self.r_bound = 2.0 * size
        self.ground_z = 0.0

    def sd(self, p, info=False):
        ds = []
        for i, (c, r) in enumerate(self.ell):
            q = p - c
            if i == 0:
                q = q.copy()
                q[:, 2] = np.maximum(q[:, 2], 0.0)  # (straight down below its middle: a bush stands on the ground)
            else:
                q = q.copy()
                q[:, 2] = np.where(q[:, 2] < 0, q[:, 2] * 0.6, q[:, 2])  # (lobes hang a little)
            k = np.linalg.norm(q / r, axis=1)
            ds.append((k - 1.0) * r.min())
        D = np.stack(ds, 1)
        d = D[:, 0]
        for i in range(1, D.shape[1]):
            h = np.clip(0.5 + 0.5 * (d - D[:, i]) / self.join, 0, 1)
            d = d * (1 - h) + D[:, i] * h - self.join * h * (1 - h)
        if self.lumps:
            d = d + self.lumps * (noise.fbm(p, self.lump_size, 2, self.seed) - 0.5) * 2
        d = np.maximum(d, -(p[:, 2] + 0.1))  # closed under the ground
        if not info:
            return d
        o = np.argsort(D, axis=1)
        r_ = np.arange(len(p))
        return d, {"face": o[:, 0], "edge": D[r_, o[:, 1]] - D[r_, o[:, 0]] if D.shape[1] > 1 else np.full(len(p), 1.0),
                   "tone": self.tone[o[:, 0]], "bed": p[:, 2], "q": p, "axis": None}

    def surface(self, dirs, origin):
        """Where rays from `origin` along unit `dirs` leave the body (bisection)."""
        lo, hi = np.zeros(len(dirs)), np.full(len(dirs), 1.5)
        for _ in range(22):
            mid = 0.5 * (lo + hi)
            ins = self.sd(origin + dirs * mid[:, None]) < 0
            lo, hi = np.where(ins, mid, lo), np.where(ins, hi, mid)
        return origin + dirs * (0.5 * (lo + hi))[:, None]


def _cells(q, size, seed):
    """3D cells (jittered points on a lattice): (distance to the nearest point, to the second nearest, the nearest's
    own random 0..1), distances in m."""
    g = q / size
    b = np.floor(g).astype(np.int64)
    f1 = np.full(len(q), 1e9)
    f2 = np.full(len(q), 1e9)
    cid = np.zeros(len(q))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = b + [dx, dy, dz]
                jx = noise._hash(c[:, 0], c[:, 1], c[:, 2], seed)
                jy = noise._hash(c[:, 0], c[:, 1], c[:, 2], seed + 1)
                jz = noise._hash(c[:, 0], c[:, 1], c[:, 2], seed + 2)
                d = np.linalg.norm(c + np.stack([jx, jy, jz], 1) - g, axis=1)
                nearer = d < f1
                f2 = np.where(nearer, f1, np.minimum(f2, d))
                cid = np.where(nearer, noise._hash(c[:, 0], c[:, 1], c[:, 2], seed + 3), cid)
                f1 = np.minimum(f1, d)
    return f1 * size, f2 * size, cid


def spray_tile(px: int, paint: dict, color, season: dict, seed: int):
    """A leaf spray's picture for a card: (rgb (px, px, 3) sRGB, alpha (px, px)); the stem runs up the middle from the
    bottom edge, leaves alternate along it. The colour is bled under the alpha."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    sp = paint["spray"]
    rng = np.random.default_rng(seed)
    S = 4 * px
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    col = np.asarray(color, float)
    if season.get("mix") is not None:
        col = col * (1 - season["amount"]) + np.asarray(season["mix"], float) * season["amount"]
    n = int(rng.integers(sp["leaves"][0], sp["leaves"][1] + 1))
    bend = rng.uniform(-0.12, 0.12)
    stem = lambda t: np.array([0.5 + bend * math.sin(t * 2.2) + 0.02 * math.sin(t * 9), 1.0 - 0.9 * t])
    pts = [tuple((stem(t) * S).tolist()) for t in np.linspace(0, 1, 20)]
    wood = tuple(int(255 * c) for c in np.clip(col * [1.1, 0.8, 0.7] * 0.6, 0, 1)) + (255,)
    dr.line(pts, fill=wood, width=max(2, S // 90))
    steps = int(paint.get("steps") or 0)
    order = sorted(range(n), key=lambda i: i)  # (from the base up: later leaves over earlier ones)
    for i in order:
        t = (i + 0.6) / (n + 0.4) * rng.uniform(0.95, 1.05)
        t = min(t, 1.0)
        base = stem(t)
        side = 1 if i % 2 == 0 else -1
        ang = math.radians(rng.uniform(32, 62)) * side if i < n - 1 else rng.uniform(-0.2, 0.2)
        d = np.array([math.sin(ang), -math.cos(ang)])
        L = _u(rng, sp["leaf"]) / 0.34 * (0.75 + 0.35 * math.sin(math.pi * min(t + 0.15, 1.0)))  # (in tile units: a tile is ~0.34 m)
        W = L * sp["round"]
        nrm = np.array([-d[1], d[0]])
        poly = []
        for u in np.linspace(0, 1, 9):
            w = W * 0.5 * math.sin(math.pi * u ** 0.8) * (1 if u < 1 else 0)
            poly.append(base + d * L * u + nrm * w)
        for u in np.linspace(1, 0, 9)[1:]:
            w = W * 0.5 * math.sin(math.pi * u ** 0.8)
            poly.append(base + d * L * u - nrm * w)
        tone = 1 + sp["tones"] * rng.uniform(-1, 1) - 0.25 * (1 - t)
        if steps:
            tone = round(tone * steps) / steps
        c = tuple(int(255 * x) for x in np.clip(col * tone, 0, 1)) + (255,)
        xy = [tuple((np.asarray(q_) * S).tolist()) for q_ in poly]
        dr.polygon(xy, fill=c, outline=(tuple(int(255 * x) for x in np.clip(col * 0.25, 0, 1)) + (255,)) if sp.get("outline") else None)
        if sp.get("outline"):
            dr.line(xy + [xy[0]], fill=tuple(int(255 * x) for x in np.clip(col * 0.25, 0, 1)) + (255,), width=max(2, int(sp["outline"] * S)))
        if sp.get("midrib"):
            dr.line([tuple((base * S).tolist()), tuple(((base + d * L * 0.9) * S).tolist())],
                    fill=tuple(int(255 * x) for x in np.clip(col * tone * (1 + sp["midrib"]), 0, 1)) + (255,), width=max(1, S // 300))
        if season.get("flowers") and paint.get("flowers") and rng.uniform() < paint["flowers"] * 1.6:
            fc = tuple(int(255 * x) for x in paint["flower_color"]) + (255,)
            ce = (base + d * L * rng.uniform(0.1, 0.5)) * S
            r = paint["flower_size"] / 0.34 * S * rng.uniform(0.9, 1.4)
            dr.ellipse([ce[0] - r, ce[1] - r, ce[0] + r, ce[1] + r], fill=fc)
    im = im.resize((px, px), Image.LANCZOS)
    a = np.asarray(im, float) / 255.0
    alpha = a[..., 3]
    rgb = a[..., :3]
    solid = alpha > 0.5
    if solid.any():
        idx = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        rgb = rgb[idx[0], idx[1]]
    return rgb, alpha


def bush_cards(solid, cfg, k: int, share: float, grow: float, tiles: list, base: int):
    """The leaf sprays of variant k: quads standing out of the dome, each drawn from both sides with the SAME normal
    (out of the bush and up: a spray lit by its own face flickers). share = how many of them (the first ones), grow =
    drawn this much larger. Returns {"V", "N", "UV", "T", "F", "wind"} or None."""
    f = solid.form
    rng = np.random.default_rng([cfg["seed"], k, 911])
    n0 = int(rng.integers(f["cards"][0], f["cards"][1] + 1)) if f["cards"][1] > 0 else 0
    if n0 <= 0 or not tiles:
        return None
    B = solid.parts[0]
    az = rng.uniform(0, 2 * math.pi) + np.arange(n0) * 2.399963  # golden angle: spread round
    el = np.radians(np.degrees(np.arcsin(rng.uniform(0.0, 0.97, n0))))  # (even over the dome: most on its sides)
    dirs = np.c_[np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)]
    org = np.array([0.0, 0.0, 0.3 * B.H])
    P = B.surface(dirs, org)
    g = _grad(B.sd, P, 0.02)
    Nn = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
    size = rng.uniform(f["card"][0], f["card"][1], n0)
    roll = rng.uniform(0, math.pi, n0)
    pick = rng.integers(0, len(tiles), n0)
    phase = rng.uniform(0, 1, n0)
    n = max(0, int(round(n0 * share)))
    if n == 0:
        return None
    V, N, UV, T, F, W = [], [], [], [], [], []
    for i in range(n):
        a = Nn[i] * (1 - f["card_up"]) + np.array([0, 0, 1.0]) * f["card_up"]
        a /= np.linalg.norm(a)
        r0 = np.cross(a, [0, 0, 1.0])
        r0 = r0 / np.linalg.norm(r0) if np.linalg.norm(r0) > 1e-6 else np.array([1.0, 0, 0])
        r1 = np.cross(a, r0)
        rt = r0 * math.cos(roll[i]) + r1 * math.sin(roll[i])
        L = size[i] * grow
        b = P[i] - a * L * (1 - f["card_out"])
        w = 0.5 * L
        q = [b - rt * w, b + rt * w, b + rt * w + a * L, b - rt * w + a * L]
        nn = Nn[i] * 0.6 + np.array([0, 0, 0.8])
        nn /= np.linalg.norm(nn)
        x0, y0, tw = tiles[pick[i]]
        m = 1.5
        uv = [[x0 + m, y0 + tw - m], [x0 + tw - m, y0 + tw - m], [x0 + tw - m, y0 + m], [x0 + m, y0 + m]]
        o = len(V)
        V += q
        N += [nn] * 4
        UV += uv
        tt = rt - nn * (nn @ rt)
        tt /= np.linalg.norm(tt)
        wsg = 1.0 if np.cross(nn, tt) @ a > 0 else -1.0
        T += [np.r_[tt, wsg]] * 4
        F += [[o, o + 1, o + 2], [o, o + 2, o + 3], [o, o + 2, o + 1], [o, o + 3, o + 2]]
        tr = lambda z: float(np.clip(z / B.H, 0, 1.3) ** 1.5)
        W += [[tr(q[0][2]), 0.5, phase[i], 0.0], [tr(q[1][2]), 0.5, phase[i], 0.0], [tr(q[2][2]), 1.0, phase[i], 1.0], [tr(q[3][2]), 1.0, phase[i], 1.0]]
    return {"V": np.array(V), "N": np.array(N), "UV": np.array(UV, float) / base, "T": np.array(T), "F": np.array(F), "wind": np.array(W)}


class Solid:
    """A variant: one or more pieces as a hard union (a cluster of cobbles, a jam of logs), seated on the ground."""

    def __init__(self, cfg: dict, k: int):
        rng = np.random.default_rng([cfg["seed"], k, 77])
        f = cfg["form"]
        vf = cfg.get("variant_forms")
        self.lods_x = 1.0
        if vf:
            o = dict(vf[k % len(vf)])
            self.lods_x = float(o.pop("lods_x", 1.0))
            f = _layered(cfg["_layers"], o)
        self.wood = cfg["material"] == "wood"
        self.form = f
        if cfg["shape"] == "bush":
            self.parts = [Bush(rng, f)]
        elif self.wood:
            n = int(rng.integers(f["pieces"][0], f["pieces"][1] + 1))
            self.parts = []
            for i in range(n):
                if n == 1:
                    self.parts.append(Wood(rng, f))
                    continue
                s = 1.0 if i == 0 else rng.uniform(0.45, 0.85)
                yaw = rng.uniform(-1, 1) * f["pile"] * math.pi * 0.5 if i else 0.0
                z = 0.5 * i * _u(rng, f["radius"]) * 1.6
                self.parts.append(Wood(rng, f, s, (rng.uniform(-0.15, 0.15), rng.uniform(-0.12, 0.12), z), yaw,
                                       rng.uniform(-0.1, 0.1) * (i > 0)))
        elif f.get("cluster"):
            cl = f["cluster"]
            n = int(rng.integers(cl["count"][0], cl["count"][1] + 1))
            self.parts, placed = [], []
            for i in range(n * 30):
                if len(self.parts) >= n:
                    break
                s = _u(rng, cl["stone"])
                r = 0.5 * math.sqrt(rng.uniform()) * (1 - s)
                a = rng.uniform(0, 2 * math.pi)
                xy = np.array([r * math.cos(a), r * math.sin(a) * 0.8])
                if any(np.linalg.norm(xy - q) < (0.5 - 0.5 * cl.get("pile", 0.3)) * (s + t) for q, t in placed):
                    continue
                placed.append((xy, s))
                self.parts.append(Stone(rng, f, s, (xy[0], xy[1], 0.0), flat=True))
        else:
            self.parts = [Stone(rng, f, 1.0, flat=cfg["kind"] == "slab")]
            if rng.uniform() < f["lean"]:  # a second block against the first
                a0 = rng.uniform(0, 2 * math.pi)
                s2 = rng.uniform(0.38, 0.55)
                h = self.parts[0].half
                self.parts.append(Stone(rng, f, s2, (0.75 * h[0] * math.cos(a0) * 1.0, 0.9 * h[1] * math.sin(a0), -h[2] + 0.42 * s2 * 0.5)))
        self.cluster = len(self.parts) > 1
        self.sink_share = f["sink"]
        lo = np.min([p.lo for p in self.parts], 0)
        hi = np.max([p.hi for p in self.parts], 0)
        self.lo, self.hi = lo, hi
        self.sink_share = f["sink"]

    def sd(self, p, info=False):
        if not info:
            out = self.parts[0].sd(p)
            for q in self.parts[1:]:
                near = np.linalg.norm(p - q.c, axis=1) < q.r_bound + 0.05
                d = np.full(len(p), 1e3)
                d[near] = q.sd(p[near])
                # far from a piece its distance is at least its bound's
                d[~near] = np.linalg.norm(p[~near] - q.c, axis=1) - q.r_bound
                out = np.minimum(out, d)
            return out
        d, I = self.parts[0].sd(p, True)
        I = {k: (np.array(v) if v is not None else None) for k, v in I.items()}
        I["part"] = np.zeros(len(p), int)
        for j, q in enumerate(self.parts[1:], 1):
            d2, I2 = q.sd(p, True)
            b = d2 < d
            for k in I:
                if k != "part" and I[k] is not None:
                    I[k][b] = I2[k][b]
            I["part"][b] = j
            d = np.minimum(d, d2)
        return d, I


# -------------------------------------------------------------------------------------------------- mesh and LODs
def _grad(fn, p, h):
    g = np.empty_like(p)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = fn(p + e) - fn(p - e)
    return g / (2 * h)


def _onto(fn, V, h, steps=3):
    for _ in range(steps):
        g = _grad(fn, V, h)
        st = g * (fn(V) / np.maximum((g * g).sum(1), 1e-9))[:, None]
        ln = np.linalg.norm(st, axis=1, keepdims=True)
        V = V - st * np.minimum(1.0, 0.03 / np.maximum(ln, 1e-9))  # (never a long jump: a far vertex's Newton step can leave the form)
    return V


def _volume(solid: Solid, n=88):
    span = solid.hi - solid.lo
    vox = float(span.max()) / n
    ax = [solid.lo[i] + np.arange(int(span[i] / vox) + 2) * vox for i in range(3)]
    G = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    v = np.concatenate([solid.sd(G[i: i + 200000]) for i in range(0, len(G), 200000)]).reshape([len(a) for a in ax])
    return v, ax, vox


def _mesh(vol, ax, vox):
    from skimage import measure
    V, F, _, _ = measure.marching_cubes(vol, 0.0, spacing=(vox,) * 3)
    V = V + [ax[0][0], ax[1][0], ax[2][0]]
    F = np.ascontiguousarray(F[:, ::-1])  # (skimage winds for an increasing-inward field: ours is negative inside)
    c = V[F].mean(1)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    if (np.einsum("ij,ij->i", fn, c - V.mean(0))).sum() < 0:
        F = np.ascontiguousarray(F[:, ::-1])
    return V, F


def _sound(V, F) -> bool:
    """Closed and manifold: every edge has exactly two faces (pyfqmr can leave a fin: twin faces on one edge)."""
    if not len(F):
        return False
    e = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt == 2).all())


def _decimate(V, F, target):
    """pyfqmr to a count: the result nearest the target from several aggressiveness values (a smooth pebble overshoots
    far below the target at a high one, a crisp block stalls above it at a low one), going on from a stall."""
    if len(F) <= target:
        return V, F
    import pyfqmr

    def run(V_, F_, agg, border=True):
        q = pyfqmr.Simplify()
        q.setMesh(np.ascontiguousarray(V_, np.float64), np.ascontiguousarray(F_, np.int32))
        q.simplify_mesh(target_count=int(target), aggressiveness=agg, preserve_border=border, verbose=False)
        V2, F2, _ = q.getMesh()
        return np.asarray(V2, float), np.asarray(F2, np.int64)
    best = None
    for agg in (5, 3, 7, 2, 1, 0.5, 9):
        r = run(V, F, agg)
        ok = _sound(*r)
        miss = abs(len(r[1]) - target) / target + (0.5 if len(r[1]) < 0.9 * target else 0.0) + (0.0 if ok else 10.0)
        if best is None or miss < best[0]:
            best = (miss, r)
        if ok and 0.95 * target <= len(r[1]) <= 1.08 * target:
            break
    best = best[1]
    for _ in range(4):  # (stalled far above the target: go on from where it stopped)
        if len(best[1]) <= 1.25 * target:
            break
        r = run(best[0], best[1], 9, False)
        if len(r[1]) >= len(best[1]) or len(r[1]) < 0.9 * target or not _sound(*r):
            break
        best = r
    return best


def _drop_specks(V, F, keep_share=0.02):
    """Pieces of a mesh too small to matter (a cluster's stone decimated to a sliver)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(V)
    e = np.r_[F[:, [0, 1]], F[:, [1, 2]]]
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)), directed=False)
    area = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    fl = lab[F[:, 0]]
    tot = np.bincount(fl, area, minlength=lab.max() + 1)
    cnt = np.bincount(fl, minlength=lab.max() + 1)
    ok = (tot[fl] > keep_share * tot.max()) & (cnt[fl] >= 4)
    return F[ok]


def mesh_check(V, F) -> dict:
    """A LOD's soundness with its chart seams welded: edges with one face (open) or more than two (non-manifold),
    faces of no area."""
    _, inv = np.unique(np.round(V, 6), axis=0, return_inverse=True)
    G = inv.reshape(-1)[F]
    e = np.sort(np.r_[G[:, [0, 1]], G[:, [1, 2]], G[:, [2, 0]]], axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    ar = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    return {"triangles": int(len(F)), "open_edges": int((cnt == 1).sum()), "nonmanifold_edges": int((cnt > 2).sum()),
            "degenerate": int((ar < 1e-10).sum())}


def silhouette(V, F, azimuth, elevation=10.0, px=220.0, frame=None):
    """A mesh's filled outline from a direction (deg), orthographic: (mask, frame); frame = (x0, y0, w, h) px."""
    from PIL import Image, ImageDraw
    a, e = math.radians(azimuth), math.radians(elevation)
    d = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    r = np.array([-math.sin(a), math.cos(a), 0.0])
    u = np.cross(d, r)
    X, Y = V @ r * px, -(V @ u) * px
    if frame is None:
        x0, y0 = math.floor(X.min()) - 3, math.floor(Y.min()) - 3
        frame = (x0, y0, int(math.ceil(X.max()) - x0 + 4), int(math.ceil(Y.max()) - y0 + 4))
    im = Image.new("L", (frame[2], frame[3]), 0)
    dr = ImageDraw.Draw(im)
    T = np.stack([X[F] - frame[0], Y[F] - frame[1]], -1).reshape(len(F), 6)
    for t in T.tolist():
        dr.polygon(t, fill=255)
    return np.asarray(im) > 0, frame


def silhouette_iou(A, B, directions=8) -> list:
    """Outline IoU of mesh B against mesh A ((V, F) each) from `directions` azimuths round it (10 and 35 deg up)."""
    out = []
    for i in range(directions):
        m0, fr = silhouette(A[0], A[1], 360.0 * i / directions, 10.0 if i % 2 == 0 else 35.0)
        m1, _ = silhouette(B[0], B[1], 360.0 * i / directions, 10.0 if i % 2 == 0 else 35.0, frame=fr)
        out.append(float((m0 & m1).sum() / max((m0 | m1).sum(), 1)))
    return out


def outline_measures(V, F, directions=8) -> dict:
    """What a boulder's side outlines say (the measures read off reference photos): height / width, corners (the
    outline simplified to 4% of its size), the share of the outline that is straight (within 1.5% over a tenth of
    its length), top width / base width (at 80% / 20% of the height)."""
    hw, corners, taper = [], [], []
    for i in range(directions):
        m, _ = silhouette(V, F, 360.0 * i / directions, 5.0)
        rows = np.flatnonzero(m.any(1))
        cols = np.flatnonzero(m.any(0))
        h, w = len(rows), len(cols)
        hw.append(h / w)
        wid = lambda fr: m[rows[0] + int(fr * (h - 1))].sum()
        taper.append(wid(0.2) / max(wid(0.8), 1))
        # the outline as the row extents, simplified
        L = np.array([[np.flatnonzero(m[r])[0], r] for r in rows], float)
        Rr = np.array([[np.flatnonzero(m[r])[-1], r] for r in rows[::-1]], float)
        poly = np.r_[L, Rr]
        corners.append(len(_rdp(poly, 0.04 * max(h, w))))
    return {"height_over_width": round(float(np.mean(hw)), 3), "hw_range": [round(float(min(hw)), 2), round(float(max(hw)), 2)],
            "corners": round(float(np.mean(corners)), 1), "top_over_base": round(float(np.mean(taper)), 3)}


def _rdp(P, eps):
    if len(P) < 3:
        return P
    a, b = P[0], P[-1]
    ab = b - a
    l = np.linalg.norm(ab)
    d = np.abs(ab[0] * (P[:, 1] - a[1]) - ab[1] * (P[:, 0] - a[0])) / l if l > 1e-9 else np.linalg.norm(P - a, axis=1)
    i = int(d.argmax())
    if d[i] <= eps:
        return np.array([a, b])
    return np.r_[_rdp(P[: i + 1], eps)[:-1], _rdp(P[i:], eps)]


CHARTS = [(0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1)]  # (axis, sign)


def _chart_axes(a, s):
    """A chart's picture axes in the solid's frame: (u axis index, u sign, row axis index, row sign). Side charts are
    upright (rows run down = -z), the top chart is a map (rows run -y), mirrored as seen from that side."""
    if a == 2:
        return (0, 1, 1, -s)
    h = 1 if a == 0 else 0
    return (h, (s if a == 0 else -s), 2, -1)


def _chart_rect(k, cell):
    """Chart k's pixel rectangle inside a variant's cell (3 x 2 charts): x0, y0, w, h."""
    w, h = cell // 3, cell // 2
    return (k % 3) * w, (k // 3) * h, w, h


def _uv_of(P, a, s, lo, hi, rect, margin=3):
    ui, us, ri, rs = _chart_axes(a, s)
    x0, y0, w, h = rect
    fu = (P[:, ui] - lo[ui]) / (hi[ui] - lo[ui])
    fr = (P[:, ri] - lo[ri]) / (hi[ri] - lo[ri])
    if us < 0:
        fu = 1 - fu
    if rs < 0:
        fr = 1 - fr
    return np.c_[x0 + margin + fu * (w - 2 * margin), y0 + margin + fr * (h - 2 * margin)]


def _pieces(V, F):
    """A mesh's connected pieces [(V, F)], largest surface first."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(V)
    e = np.r_[F[:, [0, 1]], F[:, [1, 2]]]
    k, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)), directed=False)
    out = []
    for c in range(k):
        f = F[lab[F[:, 0]] == c]
        if len(f) < 4:
            continue
        used = np.unique(f)
        re = np.full(n, -1)
        re[used] = np.arange(len(used))
        Vc, Fc = V[used], re[f]
        area = 0.5 * np.linalg.norm(np.cross(Vc[Fc[:, 1]] - Vc[Fc[:, 0]], Vc[Fc[:, 2]] - Vc[Fc[:, 0]]), axis=1).sum()
        out.append((area, Vc, Fc))
    out.sort(key=lambda t: -t[0])
    return out


def _join(parts):
    V, F, o = [], [], 0
    for v, f in parts:
        V.append(v)
        F.append(f + o)
        o += len(v)
    return np.concatenate(V), np.concatenate(F)


def cluster_lod(V, F, target):
    """A patch of stones at a budget: every stone its own greedy hull, faces shared by surface; the smallest stones
    are left out when their share would be under a tetrahedron-and-a-bit (never a folded sliver, never over budget)."""
    P = _pieces(V, F)
    while True:
        tot = sum(a ** 0.75 for a, _, _ in P)
        share = [max(int(target * a ** 0.75 / tot), 0) for a, _, _ in P]
        if len(P) > 1 and share[-1] < 8:
            P = P[:-1]
            continue
        break
    return _join([_hull(v, max(8, sh)) for (a, v, f), sh in zip(P, share)])


def wood_lod(solid, sides: int, rings: int, stubs: bool):
    """Driftwood at a low budget, built: every piece a tube of `sides` round its own axis (rings along the main stem,
    2 on a fork or stub), ends capped. A decimator leaves a thin stem a string of slivers."""
    out = []
    for W in solid.parts:
        main = W.segs[: W.n_main]
        chains = [main] + ([[sg] for sg in W.segs[W.n_main:]] if stubs else [[sg] for sg in W.segs[W.n_main:] if np.linalg.norm(sg[1] - sg[0]) > 0.2])
        for ch in chains:
            pts = [ch[0][0]] + [sg[1] for sg in ch]
            rad = [ch[0][2]] + [sg[3] for sg in ch]
            if len(pts) > rings:  # fewer rings: keep the ends, even picks between
                idx = np.unique(np.round(np.linspace(0, len(pts) - 1, rings)).astype(int))
                pts, rad = [pts[i] for i in idx], [rad[i] for i in idx]
            pts, rad = np.array(pts), np.array(rad)
            V, F = [], []
            up = np.array([0.0, 0.0, 1.0])
            for i, (c, r) in enumerate(zip(pts, rad)):
                d = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
                d /= np.linalg.norm(d)
                a = np.cross(d, up if abs(d[2]) < 0.9 else np.array([1.0, 0, 0]))
                a /= np.linalg.norm(a)
                b = np.cross(d, a)
                for k in range(sides):
                    t = 2 * math.pi * (k + 0.5) / sides
                    V.append(c + r * 1.08 * (math.cos(t) * a + math.sin(t) * b))
            for i in range(len(pts) - 1):
                for k in range(sides):
                    p0, p1 = i * sides + k, i * sides + (k + 1) % sides
                    q0, q1 = p0 + sides, p1 + sides
                    F += [[p0, p1, q1], [p0, q1, q0]]
            n = len(V)
            V += [pts[0], pts[-1]]
            for k in range(sides):
                F.append([n, (k + 1) % sides, k])
                e = (len(pts) - 1) * sides
                F.append([n + 1, e + k, e + (k + 1) % sides])
            V, F = np.array(V), np.array(F)
            # outward: flip if the first face points at the axis
            fn = np.cross(V[F[0, 1]] - V[F[0, 0]], V[F[0, 2]] - V[F[0, 0]])
            if fn @ (V[F[0]].mean(0) - pts[0]) < 0:
                F = F[:, ::-1]
            out.append((V, F))
    return _join(out)


def lod_mesh(solid: Solid, V, F, target, cfg, cell, origin, base, h, hull=False, pre=None):
    """One LOD: decimated (or `pre` = a mesh built for it), back on the field, split into charts (uv by position),
    smooth normals from the field (split where faces meet sharply), tangents from the charts."""
    if pre is not None:
        V2, F2 = pre
    elif hull:
        V2, F2 = _hull(V, target)
    else:
        V2, F2 = _decimate(V, F, target)
        F2 = _drop_specks(V2, F2) if solid.cluster else F2
        V2 = _onto(solid.sd, V2, h, 2)
    # (degenerate faces after the move)
    ar = np.linalg.norm(np.cross(V2[F2[:, 1]] - V2[F2[:, 0]], V2[F2[:, 2]] - V2[F2[:, 0]]), axis=1)
    F2 = F2[ar > 1e-9]
    fnorm = np.cross(V2[F2[:, 1]] - V2[F2[:, 0]], V2[F2[:, 2]] - V2[F2[:, 0]])
    fnorm /= np.maximum(np.linalg.norm(fnorm, axis=1, keepdims=True), 1e-12)
    N = _smooth_normal(solid, V2, h)
    # a flipped smooth normal (thin parts): take the faces' own
    vn = np.zeros_like(V2)
    for c in range(3):
        np.add.at(vn, F2[:, c], fnorm)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    bad = (N * vn).sum(1) < 0.2
    N[bad] = vn[bad]
    chart = np.array([CHARTS.index((int(a), int(np.sign(n[a]) or 1))) for n, a in zip(fnorm, np.abs(fnorm).argmax(1))])
    sharp = math.cos(math.radians(cfg["paint"]["normals"])) if cfg["paint"]["normals"] > 0 else -2.0
    # corners: (vertex, chart, own-normal flag) -> output vertex
    P, Nn, UV, T, idx, key = [], [], [], [], np.zeros_like(F2), {}
    for fi in range(len(F2)):
        a, s = CHARTS[chart[fi]]
        for c in range(3):
            v = int(F2[fi, c])
            own = (fnorm[fi] @ N[v]) < sharp
            kk = (v, int(chart[fi]), fi if own else -1)
            if kk not in key:
                key[kk] = len(P)
                P.append(V2[v])
                Nn.append(fnorm[fi] if own else N[v])
            idx[fi, c] = key[kk]
    P, Nn = np.array(P), np.array(Nn)
    UV = np.zeros((len(P), 2))
    T = np.zeros((len(P), 4))
    vchart = np.zeros(len(P), int)
    for (v, ch, _), o in key.items():
        vchart[o] = ch
    for ch, (a, s) in enumerate(CHARTS):
        m = vchart == ch
        if not m.any():
            continue
        rect = _chart_rect(ch, cell)
        px = _uv_of(P[m], a, s, solid.lo, solid.hi, rect)
        UV[m] = (px + origin) / base
        T[m] = _tangents(Nn[m], a, s)
    return {"V": P, "N": Nn, "UV": UV, "T": T, "F": idx, "triangles": int(len(idx)), "chart": chart}


def _smooth_normal(solid, P, h):
    g = _grad(solid.sd, P, max(h * 4, 0.012))
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)


def _tangents(N, a, s):
    """glTF TANGENT for a chart: xyz = the picture's +u direction made square to the normal, w so that
    cross(N, T) * w points UP the picture (glTF's +Y of a normal map; rows run down)."""
    ui, us, ri, rs = _chart_axes(a, s)
    tu = np.zeros(3)
    tu[ui] = us
    up = np.zeros(3)
    up[ri] = -rs
    T = tu[None] - N * (N @ tu)[:, None]
    ln = np.linalg.norm(T, axis=1, keepdims=True)
    T = np.where(ln > 1e-6, T / np.maximum(ln, 1e-6), np.cross(N, up)[..., :])
    w = np.sign((np.cross(N, T) * up[None]).sum(1))
    w[w == 0] = 1
    return np.c_[T, w]


# ---------------------------------------------------------------------------------------------------------- the bake
def _cracks(p, q, seed):
    """0..1: fracture traces. A crack is where a wandering PLANE meets the surface (a joint's trace: a line that runs
    on across faces and stops), a handful per stone, each present along stretches. Isolines of a noise drew closed
    loops: worm doodles."""
    rng = np.random.default_rng(seed + 2)
    size = p["crack_size"]
    out = np.zeros(len(q))
    for i in range(6):
        n = rng.normal(0, 1, 3)
        n /= np.linalg.norm(n)
        off = rng.uniform(-0.28, 0.28)
        w = rng.uniform(0.0025, 0.006)
        x = q @ n - off + 0.035 * size / 0.3 * (noise.fbm(q, 0.5 * size, 2, seed + 30 + i) - 0.5) * 2
        on = np.clip((noise.fbm(q + 7.1 * i, 1.2 * size, 1, seed + 40 + i) - 0.45) / 0.08, 0, 1)
        out = np.maximum(out, np.clip(1 - np.abs(x) / w, 0, 1) * on * rng.uniform(0.5, 1.0))
    return out


def _micro(cfg, I, P, seed):
    """Bake-only relief (m, + = out of the rock): grain, cracks, laminae along the bedding, grooves along wood."""
    p = cfg["paint"]
    q = I["q"]
    h = np.zeros(len(P))
    if p.get("grain"):
        h += p["grain"] * (noise.fbm(q, p["grain_size"], 2, seed + 1) - 0.5) * 2
    if p.get("cracks"):
        h -= p["cracks"] * _cracks(p, q, seed)
    if p.get("laminae"):
        zb = I["bed"] + 0.004 * noise.fbm(q, 0.15, 2, seed + 4)
        t = np.abs(((zb / p["lamina"]) % 1.0) - 0.5) * 2
        h -= p["laminae"] * np.clip(1 - t / 0.25, 0, 1) * (noise.fbm(q, 0.2, 1, seed + 5) > 0.4)
    if p.get("pits"):
        r = noise.fbm(q, 0.03, 2, seed + 6)
        h -= p["pits"] * np.clip((r - 0.62) / 0.1, 0, 1)
    if p.get("leaf_bump") and p.get("leaf_size"):
        f1, _, _ = _cells(q, p["leaf_size"], seed + 31)
        h += p["leaf_bump"] * np.clip(1 - f1 / (0.6 * p["leaf_size"]), 0, 1)
    if p.get("bark") and I.get("axis") is not None:
        ax_ = I["axis"]
        al_ = (q * ax_).sum(1, keepdims=True)
        bq = (q - ax_ * al_) / (0.4 * p["bark_size"]) + ax_ * al_ / p["bark_size"]
        h += 0.004 * np.clip((noise.fbm(bq, 1.0, 2, seed + 51) - (0.62 - 0.3 * p["bark"])) / 0.05, 0, 1)
    if p.get("grooves") and I.get("axis") is not None:
        ax = I["axis"]
        perp = q - ax * (q * ax).sum(1, keepdims=True)
        st = perp / p["groove_size"] + ax * (q * ax).sum(1, keepdims=True) / (p["groove_size"] * 30)
        h += p["grooves"] * (noise.fbm(st, 1.0, 2, seed + 7) - 0.5) * 2
    return h


def _paint(cfg, solid, P, Nrm, I, curv, ao, zrel, seed, zg=None, season=None, variant=0):
    """Albedo (sRGB) and roughness at surface points."""
    p = cfg["paint"]
    q = I["q"]
    tone = 1.0 + p["tone"] * (noise.fbm(q, p["tone_size"], 3, seed + 11) - 0.5) * 2
    tone = tone * (1 + p.get("face_tone", 0) * I["tone"])
    if p.get("speckle"):
        tone = tone * (1 + p["speckle"] * ((noise.fbm(q, 0.012, 2, seed + 12) - 0.5) * 2 + (noise.fbm(q, 0.05, 2, seed + 22) - 0.5) * 2))
    if p.get("streak") and I.get("axis") is not None:
        ax = I["axis"]
        al = (q * ax).sum(1, keepdims=True)
        st = (q - ax * al) / p["streak_size"][1] + ax * al / p["streak_size"][0]
        tone = tone * (1 + p["streak"] * (noise.fbm(st, 1.0, 3, seed + 13) - 0.5) * 2)
    if p.get("bands"):
        zb = I["bed"] + 0.01 * (noise.fbm(q, 0.3, 2, seed + 14) - 0.5)
        lo, hi = p["band_thick"]
        # bands of wandering thickness: a warped coordinate cut into unit cells, each cell one of the tones
        wz = zb / (0.5 * (lo + hi)) + 0.8 * (noise.fbm(np.c_[zb, zb * 0, zb * 0] + 3.1, hi * 2.0, 1, seed + 15) - 0.5) * (hi - lo) / (lo + hi) * 4
        cell = np.floor(wz).astype(np.int64)
        tn = np.asarray(p["band_tones"], float)
        pick = tn[(noise._hash(cell, cell * 0 + 5, cell * 0 + 9, seed + 16) * len(tn)).astype(int) % len(tn)]
        tone = tone * (1 + p["bands"] * pick)
    if p.get("cracks"):
        tone = tone * (1 - min(0.6, p["cavity"] * 1.6) * np.clip(_cracks(p, q, seed), 0, 1))
    flower = None
    if p.get("leaf_size"):
        f1, f2, cid = _cells(q, p["leaf_size"], seed + 31)
        tone = tone * (1 + p["leaf_tone"] * (cid - 0.5) * 2)
        gap = np.clip(1 - (f2 - f1) / (0.3 * p["leaf_size"]), 0, 1)
        tone = tone * (1 - p["leaf_gap"] * gap * gap)
        if season and season.get("flowers") and p.get("flowers"):
            g1, _, gid = _cells(q, p["flower_size"] * 3.2, seed + 41)
            flower = (g1 < p["flower_size"]) & (gid < p["flowers"]) & (Nrm[:, 2] > -0.1)
    if p.get("steps"):
        tone = np.round(tone * p["steps"] * 2) / (p["steps"] * 2)
    if season and season.get("mix") is not None:
        cfg = dict(cfg, color=(np.asarray(cfg["color"], float) * (1 - season["amount"]) + np.asarray(season["mix"], float) * season["amount"]).tolist())
    col = np.asarray(cfg["color"], float)[None] * tone[:, None]
    mn = p.get("minerals")
    if mn:
        col = col * np.asarray(mn[variant % len(mn)], float)[None]
    if p.get("bark") and I.get("axis") is not None:  # bark still on in patches
        ax_ = I["axis"]
        al_ = (q * ax_).sum(1, keepdims=True)
        bq = (q - ax_ * al_) / (0.4 * p["bark_size"]) + ax_ * al_ / p["bark_size"]
        bm = np.clip((noise.fbm(bq, 1.0, 2, seed + 51) - (0.62 - 0.3 * p["bark"])) / 0.05, 0, 1)
        rib = 0.75 + 0.5 * noise.fbm((q - ax_ * al_) / 0.012 + ax_ * al_ / 0.2, 1.0, 2, seed + 52)
        col = col * (1 - bm[:, None]) + np.asarray(p["bark_color"], float)[None] * rib[:, None] * bm[:, None]
    if p.get("bleach"):
        col = col * (1 + p["bleach"] * np.clip(Nrm[:, 2], 0, 1))[:, None]
    if p.get("streaks"):  # rain streaks: narrow in plan, long down the face, strongest under the top edge
        st_ = noise.fbm(np.c_[q[:, 0] / p["streak_width"], q[:, 1] / p["streak_width"], q[:, 2] / 0.9], 1.0, 2, seed + 53)
        steep = np.clip(1 - np.abs(Nrm[:, 2]) / 0.7, 0, 1)
        sm = np.clip((st_ - 0.56) / 0.1, 0, 1) * steep * np.clip(0.35 + zrel, 0, 1)
        col = col * (1 - p["streaks"] * sm)[:, None]
    # curvature: convex arrises worn pale, concave darker; an ink line along arrises
    cv = np.clip(curv, -1, 1)
    col = col * (1 + p["edge_light"] * np.clip(cv, 0, 1) - p["cavity"] * np.clip(-cv, 0, 1))[:, None]
    if p.get("ink"):
        e = np.clip(1 - np.abs(I["edge"]) / p["ink_width"], 0, 1)
        e = np.maximum(e, np.clip(cv * 1.5 - 0.35, 0, 1))
        col = col * (1 - p["ink"] * e * e * (3 - 2 * e))[:, None]
    up = Nrm[:, 2]
    if p.get("gradient"):
        col = col * (1 + p["gradient"] * (np.clip(zrel, 0, 1) - 0.5) + 0.5 * p["gradient"] * (up * 0.5))[:, None]
    if p.get("top_light"):
        col = col * (1 + p["top_light"] * (np.clip(up, 0, 1) ** 1.5 - 0.3))[:, None]
    if p.get("foot") and zg is not None:
        fz = np.clip(1 - zg / p["foot_height"], 0, 1)
        col = col * (1 - p["foot"] * fz * fz * (0.7 + 0.6 * noise.fbm(q, 0.08, 2, seed + 23)))[:, None]
    if p.get("foot_tint") and zg is not None:
        fz = np.clip(1 - zg / (1.4 * p["foot_height"]), 0, 1) * np.clip((noise.fbm(q, 0.1, 2, seed + 54) - 0.3) / 0.3, 0, 1)
        col = col * (1 - p["foot_tint"] * fz[:, None]) + np.asarray(p["foot_color"], float)[None] * (p["foot_tint"] * fz)[:, None]
    if p.get("lichen"):  # crusts: round patches (cells), in clusters, on tops and the weather side
        f1, _, cid = _cells(q, p["lichen_size"], seed + 55)
        wx = np.array([math.cos(seed * 1.7), math.sin(seed * 1.7), 0.0])
        where = np.clip(np.maximum((up - 0.2) / 0.5, (Nrm @ wx - 0.2) / 0.5), 0, 1)
        clus = np.clip((noise.fbm(q, 0.3, 2, seed + 56) - 0.5 + 0.35 * p["lichen"]) / 0.1, 0, 1)
        r_ = p["lichen_size"] * (0.35 + 0.4 * cid)  # (big enough that neighbours run together into blotches)
        ragged = 1 + 0.5 * (noise.fbm(q, 0.02, 2, seed + 57) - 0.5) * 2
        m = np.clip((r_ * ragged - f1) / 0.008, 0, 1) * where * clus * (cid < 0.3 + 0.7 * p["lichen"])
        m = m * (0.45 + 0.3 * noise.fbm(q, 0.01, 2, seed + 58))  # (a thin crust: the rock shows through)
        lc = np.asarray(p["lichen_colors"], float)
        pick = lc[(cid * 97).astype(int) % len(lc)]
        col = col * (1 - m[:, None]) + pick * m[:, None]
    if p.get("top"):
        m = np.clip((up - 0.45) / 0.35, 0, 1) * np.clip((noise.fbm(q, p["top_size"], 3, seed + 17) - 0.42) / 0.14, 0, 1)
        m = m * p["top"]
        col = col * (1 - m[:, None]) + np.asarray(p["top_color"], float)[None] * (0.85 + 0.3 * noise.fbm(q, 0.02, 2, seed + 18))[:, None] * m[:, None]
    if p.get("moss"):
        b0, b1 = p["moss_band"]
        band = np.clip((zrel - b0) / 0.08, 0, 1) * np.clip((b1 - zrel) / 0.15, 0, 1)
        m = band * np.clip((noise.fbm(q, 0.09, 3, seed + 19) - 0.5 + 0.5 * p["moss"]) / 0.15, 0, 1) * np.clip(0.6 + up, 0, 1)
        m = np.clip(m * min(1.0, 2 * p["moss"]), 0, 1)
        col = col * (1 - m[:, None]) + np.asarray(p["moss_color"], float)[None] * (0.8 + 0.4 * noise.fbm(q, 0.015, 2, seed + 20))[:, None] * m[:, None]
    col = col * (1 - 0.5 * p["ao"] * (1 - ao))[:, None]
    if flower is not None and flower.any():
        col[flower] = np.asarray(p["flower_color"], float)
    rough = np.clip(p["roughness"] * (1 + 0.08 * (tone - 1) * 4), 0.05, 1.0)
    return np.clip(col, 0, 1), rough


def _dilate(img, solid_mask, rounds=6):
    """Filled texels spread into empty ones (nearest), so mips and bilinear taps at chart edges read rock."""
    from scipy import ndimage
    if solid_mask.all() or not solid_mask.any():
        return img
    idx = ndimage.distance_transform_edt(~solid_mask, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def _raster_normals(L, pix, ch, rect):
    """LOD 0's interpolated vertex normals per texel of chart ch: (h, w, 3) and a mask (what the engine's shading
    starts from there; the baked normal is told apart from THIS, so flat faces with their own normals stay flat)."""
    x0, y0, w, h = rect
    out = np.zeros((h, w, 3))
    got = np.zeros((h, w), bool)
    F, N = L["F"], L["N"]
    for f in F[L["chart"] == ch]:
        p = pix[f] - [x0, y0]
        lo = np.maximum(np.floor(p.min(0)).astype(int) - 1, 0)
        hi = np.minimum(np.ceil(p.max(0)).astype(int) + 2, [w, h])
        if (hi <= lo).any():
            continue
        X, Y = np.meshgrid(np.arange(lo[0], hi[0]) + 0.5, np.arange(lo[1], hi[1]) + 0.5)
        d = (p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1])
        if abs(d) < 1e-9:
            continue
        a = ((p[1, 1] - p[2, 1]) * (X - p[2, 0]) + (p[2, 0] - p[1, 0]) * (Y - p[2, 1])) / d
        b = ((p[2, 1] - p[0, 1]) * (X - p[2, 0]) + (p[0, 0] - p[2, 0]) * (Y - p[2, 1])) / d
        c = 1 - a - b
        m = (a > -0.15) & (b > -0.15) & (c > -0.15)
        if not m.any():
            continue
        n = a[..., None] * N[f[0]] + b[..., None] * N[f[1]] + c[..., None] * N[f[2]]
        sl = (slice(lo[1], hi[1]), slice(lo[0], hi[0]))
        inside = (a >= 0) & (b >= 0) & (c >= 0)
        take = m & (inside | ~got[sl])
        out[sl][take] = n[take]
        got[sl] |= take
    ln = np.linalg.norm(out, axis=2, keepdims=True)
    return out / np.maximum(ln, 1e-9), got


def bake_variant(cfg, solid: Solid, vol, ax, vox, cell, seed, low=None, ground=None):
    """A variant's six charts: (albedo (cell, cell, 3) sRGB, normal (.., 3) tangent, orm (.., 3), filled mask)."""
    from scipy import ndimage
    p = cfg["paint"]
    albs = {se: np.zeros((cell, cell, 3)) for se in cfg["seasons"]}
    nrm = np.zeros((cell, cell, 3))
    nrm[..., 2] = 1
    orm = np.ones((cell, cell, 3))
    orm[..., 2] = 0
    filled = np.zeros((cell, cell), bool)
    lo, hi = solid.lo, solid.hi
    zbot = None
    for ch, (a, s) in enumerate(CHARTS):
        x0, y0, w, h = _chart_rect(ch, cell)
        ui, us, ri, rs = _chart_axes(a, s)
        m = 3
        fu = (np.arange(w) + 0.5 - m) / (w - 2 * m)
        fr = (np.arange(h) + 0.5 - m) / (h - 2 * m)
        if us < 0:
            fu = 1 - fu
        if rs < 0:
            fr = 1 - fr
        cu = lo[ui] + fu * (hi[ui] - lo[ui])
        cr = lo[ri] + fr * (hi[ri] - lo[ri])
        # the volume resampled on (depth along a) x (rows) x (cols)
        vo = np.moveaxis(vol, (a, ri, ui), (0, 1, 2))
        gi = (cr - ax[ri][0]) / vox
        gj = (cu - ax[ui][0]) / vox
        JJ, II = np.meshgrid(gj, gi)
        nd = vo.shape[0]
        stack = np.stack([ndimage.map_coordinates(vo[d], [II, JJ], order=1, mode="nearest") for d in range(nd)])
        if s > 0:
            stack = stack[::-1]
        inside = stack < 0
        first = inside.argmax(0)
        hit = inside.any(0) & (first > 0)
        f1 = np.take_along_axis(stack, first[None], 0)[0]
        f0 = np.take_along_axis(stack, np.maximum(first - 1, 0)[None], 0)[0]
        frac = np.where(hit, f0 / np.maximum(f0 - f1, 1e-9), 0)
        dpos = (first - 1 + frac)
        depth = ax[a][-1] - dpos * vox if s > 0 else ax[a][0] + dpos * vox
        rr, cc = np.nonzero(hit)
        if not len(rr):
            continue
        P = np.zeros((len(rr), 3))
        P[:, a] = depth[rr, cc]
        P[:, ri] = cr[rr]
        P[:, ui] = cu[cc]
        e = np.zeros(3)
        e[a] = 1
        for _ in range(3):  # onto the exact field along the ray
            P[:, a] -= np.clip(solid.sd(P), -vox, vox) * s * 0.9
        d, I = solid.sd(P, True)
        hstep = max(0.0025, vox * 0.25)

        def fine(X):
            dd, II_ = solid.sd(X, True)
            return dd - _micro(cfg, II_, X, seed)
        g = _grad(fine, P, hstep)
        nh = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
        Ns = _smooth_normal(solid, P, vox)
        if low is not None:
            Nl, got = _raster_normals(low[0], low[1], ch, (x0, y0, w, h))
            use = got[rr, cc] & ((Nl[rr, cc] * Ns).sum(1) > 0.2)
            Ns = np.where(use[:, None], Nl[rr, cc], Ns)
        T4 = _tangents(Ns, a, s)
        Bt = np.cross(Ns, T4[:, :3]) * T4[:, 3:4]
        nt = np.c_[(nh * T4[:, :3]).sum(1), (nh * Bt).sum(1), np.maximum((nh * Ns).sum(1), 0.05)]
        nt /= np.linalg.norm(nt, axis=1, keepdims=True)
        # curvature (the field's Laplacian at two sizes) and occlusion (the field a little way out)
        r1 = max(0.02, 3 * vox)
        lap = sum(solid.sd(P + o) for o in (np.eye(3)[i] * r1 * sg for i in range(3) for sg in (1, -1))) - 6 * d
        curv = lap / r1 * 0.35 - 0.12 / 1.0
        curv = np.clip((lap / r1 - 0.25) * 0.9, -1, 1)
        ao = np.ones(len(P))
        for r in (0.03, 0.08, 0.18):
            ao = np.minimum(ao, np.clip(solid.sd(P + Ns * r) / r, 0, 1) * 0.5 + 0.5 * ao)
        ztop, zbot = hi[2] - 0.05, lo[2] + 0.05
        zrel = (P[:, 2] - zbot) / max(ztop - zbot, 1e-6)
        Y, X = y0 + rr, x0 + cc
        for se, sv in cfg["seasons"].items():
            col, rough = _paint(cfg, solid, P, nh, I, curv, ao, zrel, seed, zg=P[:, 2] - ground if ground is not None else None, season=sv, variant=seed % 1000)
            albs[se][Y, X] = col
        nrm[Y, X] = nt
        orm[Y, X, 0] = 1 - p["ao"] * (1 - ao)
        orm[Y, X, 1] = rough
        filled[Y, X] = True
    # dilate per chart so charts don't bleed into each other
    for ch in range(6):
        x0, y0, w, h = _chart_rect(ch, cell)
        sl = (slice(y0, y0 + h), slice(x0, x0 + w))
        for im in list(albs.values()) + [nrm, orm]:
            im[sl] = _dilate(im[sl], filled[sl])
    return albs, nrm, orm, filled


# -------------------------------------------------------------------------------------------------------- building
def build(spec: dict, progress=None) -> dict:
    """Make the asset: every variant's LODs + collision hull and the shared atlas. Returns {"cfg", "variants": [{"name",
    "lods": [mesh...], "collision": (V, F) | None, "size", "height", "sink"}], "albedo", "normal", "orm"} (pictures
    0..1 floats; meshes Z up in metres, pivot on the ground line)."""
    cfg = resolve(spec)
    nv = cfg["variants"]
    bush = cfg["shape"] == "bush"
    grid = 3 if bush else 1 if nv == 1 else 2 if nv <= 4 else 3
    base = cfg["atlas"]
    cell = base // grid
    albs = {se: np.zeros((base, base, 4)) for se in cfg["seasons"]}
    for a_ in albs.values():
        a_[..., :3] = cfg["color"]
        a_[..., 3] = 1.0
    tiles = []
    if bush and cfg["form"]["cards"][1] > 0:  # the sprays' pictures: the cells after the variants'
        for t in range(grid * grid - nv):
            c = nv + t
            x0, y0 = (c % grid) * cell, (c // grid) * cell
            tiles.append((x0, y0, cell))
            for se, sv in cfg["seasons"].items():
                rgb, al = spray_tile(cell, cfg["paint"], cfg["color"], sv, cfg["seed"] * 100 + t)
                albs[se][y0: y0 + cell, x0: x0 + cell, :3] = rgb
                albs[se][y0: y0 + cell, x0: x0 + cell, 3] = al
    nrm = np.zeros((base, base, 3))
    nrm[..., 2] = 1
    orm = np.ones((base, base, 3))
    orm[..., 2] = 0
    out = []
    for k in range(nv):
        solid = Solid(cfg, k)
        vol, ax, vox = _volume(solid, 96 if solid.cluster or solid.wood else 80)
        V, F = _mesh(vol, ax, vox)
        V = _onto(solid.sd, V, vox * 0.5, 1)
        solid.lo, solid.hi = V.min(0) - vox, V.max(0) + vox  # (the charts' frame: tight round the form)
        # normalise: largest plan dimension 1 m, centred in plan, the ground line `sink` of the height above the bottom
        lo, hi = V.min(0), V.max(0)
        plan = float(max(hi[0] - lo[0], hi[1] - lo[1]))
        height = float(hi[2] - lo[2])
        sink = cfg["form"]["sink"] * height
        if bush:
            sink = float(solid.parts[0].ground_z - lo[2])
        scale = 1.0 / plan
        shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -(lo[2] + sink)])
        origin = np.array([(k % grid) * cell, (k // grid) * cell], float)
        seed = cfg["seed"] * 1000 + k
        lods, ious = [], []
        for j, tgt in enumerate(cfg["lods"]):
            tgt = int(round(tgt * solid.lods_x))
            single = cfg["shape"] in ("rock", "bush") and not solid.cluster
            hull = single and tgt <= 40  # (a near-convex stone's last LOD: its hull, never a folded sliver)
            pre = None
            if solid.wood and (j or len(solid.parts) > 1):  # built tubes: LOD 1 five sides, LOD 2 three; a jam always
                sides, rings = ((7, 6) if j == 0 else (5, 5) if j == 1 else (3, 4))
                stubs = j < 2
                while True:
                    pre = wood_lod(solid, sides, rings, stubs=stubs)
                    if len(pre[1]) <= 1.1 * tgt or (sides == 3 and rings == 2 and not stubs):
                        break
                    if sides == 3 and rings == 2:  # still over with every stub and root as a tube: the stems alone
                        stubs, sides, rings = False, 5, 5
                        continue
                    sides, rings = (sides - 1, rings) if sides > 3 else (sides, rings - 1)
            elif solid.cluster and cfg["shape"] != "wood" and len(solid.parts) > 2:  # a patch of stones: a hull each
                pre = cluster_lod(V, F, tgt)
            L = lod_mesh(solid, V, F, tgt, cfg, cell, origin, base, vox * 0.5, hull=hull, pre=pre)
            bad = False
            if pre is None and not hull:
                chk = mesh_check(L["V"], L["F"])
                bad = L["triangles"] > 1.3 * tgt or chk["open_edges"] > 0 or chk["nonmanifold_edges"] > 0
            if bad and cfg["shape"] in ("rock", "bush") and not (solid.cluster and len(solid.parts) > 2):  # stalled or torn: its hull
                L = lod_mesh(solid, V, F, tgt, cfg, cell, origin, base, vox * 0.5, hull=True)
            if bad and solid.wood:  # built tubes
                sides, rings = 8, 6
                while True:
                    pre = wood_lod(solid, sides, rings, True)
                    if len(pre[1]) <= 1.1 * tgt or sides == 3:
                        break
                    sides -= 1
                L = lod_mesh(solid, V, F, tgt, cfg, cell, origin, base, vox * 0.5, pre=pre)
            iou = float(np.mean(silhouette_iou((lods[0]["V"], lods[0]["F"]), (L["V"], L["F"])))) if j else 1.0
            if j and pre is None and cfg["shape"] == "rock" and not hull and iou < LOD_IOU and not (solid.cluster and len(solid.parts) > 2):  # the decimation changed the outline: the hull keeps it
                L2 = lod_mesh(solid, V, F, tgt, cfg, cell, origin, base, vox * 0.5, hull=True)
                i2 = float(np.mean(silhouette_iou((lods[0]["V"], lods[0]["F"]), (L2["V"], L2["F"]))))
                if i2 > iou:
                    L, iou = L2, i2
            L["iou"] = round(iou, 3)
            lods.append(L)
        a_, n_, o_, _ = bake_variant(cfg, solid, vol, ax, vox, cell, seed, low=(lods[0], lods[0]["UV"] * base - origin), ground=float(lo[2] + sink))
        sl = (slice(int(origin[1]), int(origin[1]) + cell), slice(int(origin[0]), int(origin[0]) + cell))
        nrm[sl], orm[sl] = n_, o_
        for se in albs:
            albs[se][sl][..., :3] = a_[se]
        for j, L in enumerate(lods):
            if bush:  # wind channels; the sprays joined on
                Bz = solid.parts[0].H
                tr = np.clip(L["V"][:, 2] / Bz, 0, 1.3) ** 1.5
                L["wind"] = np.c_[tr, 0.2 * tr, np.full(len(tr), 0.37 * k % 1.0), np.zeros(len(tr))]
                sh = cfg["form"]["cards_lod"]
                C = bush_cards(solid, cfg, k, sh[min(j, len(sh) - 1)], 1.0 + 0.25 * j, tiles, base)
                if C is not None:
                    o = len(L["V"])
                    for key in ("V", "N", "UV", "T", "wind"):
                        L[key] = np.r_[L[key], C[key]]
                    L["F"] = np.r_[L["F"], C["F"] + o]
                    L["triangles"] = int(len(L["F"]))
                    L["cards"] = int(len(C["F"]) // 4)
            L["V"] = (L["V"] + shift) * scale
        col = None
        if cfg["collision"] == "convex":
            col = _hull((lods[min(1, len(lods) - 1)]["V"]), 24)
        out.append({"name": f"v{k}", "lods": lods, "collision": col, "height": round(height * scale, 4),
                    "sink": round(sink * scale, 4), "bounds": [((lo + shift) * scale).round(4).tolist(), ((hi + shift) * scale).round(4).tolist()]})
        if progress:
            progress(f"{cfg['kind']} {cfg['style']} variant {k}: " + " / ".join(str(L["triangles"]) for L in lods) + " triangles")
    return {"cfg": cfg, "variants": out, "albedo": albs, "normal": nrm * 0.5 + 0.5, "orm": orm}


def _hull(V, faces):
    """A convex hull with at most `faces` triangles: (V, F) outward. Grown greedily: from the six axis extremes, the
    point farthest outside the hull so far is added until the count is reached (the best outline for the count)."""
    from scipy.spatial import ConvexHull
    h = ConvexHull(V)
    P = V[h.vertices]
    if len(h.simplices) > faces:
        pick = list(dict.fromkeys([int(P[:, a].argmax()) for a in range(3)] + [int(P[:, a].argmin()) for a in range(3)]))
        while True:
            try:
                hh = ConvexHull(P[pick])
            except Exception:
                hh = None
            if hh is not None and len(hh.simplices) + 2 > faces:
                break
            if hh is None:
                rest = [i for i in range(len(P)) if i not in pick]
                if not rest:
                    break
                pick.append(rest[0])
                continue
            out = (P @ hh.equations[:, :3].T + hh.equations[:, 3]).max(1)
            out[pick] = -1
            i = int(out.argmax())
            if out[i] <= 1e-6:
                break
            pick.append(i)
        P = P[pick]
        h = ConvexHull(P)
        P = P[h.vertices]
        h = ConvexHull(P)
    F = h.simplices.copy()
    c = P.mean(0)
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    flip = (fn * (P[F].mean(1) - c)).sum(1) < 0
    F[flip] = F[flip][:, ::-1]
    return P, F


# ------------------------------------------------------------------------------------------------------------ files
def _png(a) -> bytes:
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(np.clip(np.asarray(a) * 255 + 0.5, 0, 255).astype(np.uint8)).save(b, "PNG")
    return b.getvalue()


def _yup(v):
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1)


class Glb:
    """A small glTF 2.0 writer: meshes with POSITION / NORMAL / TANGENT / TEXCOORD_0 / COLOR_0, external or embedded
    images, extras."""

    def __init__(self):
        self.buf = bytearray()
        self.views, self.acc, self.meshes, self.nodes, self.mats, self.tex, self.images, self.scene = [], [], [], [], [], [], [], []
        self.samplers = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}]

    def _view(self, data: bytes, target=None):
        while len(self.buf) % 4:
            self.buf.append(0)
        v = {"buffer": 0, "byteOffset": len(self.buf), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.buf += data
        self.views.append(v)
        return len(self.views) - 1

    def accessor(self, a, kind, ctype=5126, target=34962, minmax=False):
        a = np.ascontiguousarray(a, {5126: np.float32, 5125: np.uint32, 5123: np.uint16}[ctype])
        acc = {"bufferView": self._view(a.tobytes(), target), "componentType": ctype, "count": int(len(a) if kind != "SCALAR" else a.size), "type": kind}
        if minmax:
            acc["min"], acc["max"] = a.min(0).tolist(), a.max(0).tolist()
        self.acc.append(acc)
        return len(self.acc) - 1

    def image(self, uri=None, data=None):
        if uri is not None:
            self.images.append({"uri": uri})
        else:
            self.images.append({"bufferView": self._view(data), "mimeType": "image/png"})
        self.tex.append({"source": len(self.images) - 1, "sampler": 0})
        return len(self.tex) - 1

    def material(self, m: dict):
        self.mats.append(m)
        return len(self.mats) - 1

    def mesh(self, name, V, F, N=None, T=None, UV=None, C=None, material=None, extras=None, wind=None):
        at = {"POSITION": self.accessor(_yup(V), "VEC3", minmax=True)}
        if N is not None:
            n = _yup(N)
            n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
            at["NORMAL"] = self.accessor(n, "VEC3")
        if T is not None:
            t = _yup(T[:, :3])
            t = t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
            at["TANGENT"] = self.accessor(np.c_[t, T[:, 3]], "VEC4")
        if UV is not None:
            at["TEXCOORD_0"] = self.accessor(UV, "VEC2")
        if wind is not None:  # the plants' wind channels (veg_export.WIND_RECIPE)
            at["TEXCOORD_1"] = self.accessor(wind[:, :2], "VEC2")
            at["TEXCOORD_2"] = self.accessor(wind[:, 2:], "VEC2")
            at["_WIND"] = self.accessor(wind, "VEC4")
        if C is not None:
            at["COLOR_0"] = self.accessor(np.clip(C, 0, 1), "VEC3" if C.shape[1] == 3 else "VEC4")
        F = np.asarray(F)
        big = len(V) > 65535
        prim = {"attributes": at, "indices": self.accessor(F.reshape(-1), "SCALAR", 5125 if big else 5123, 34963), "mode": 4}
        if material is not None:
            prim["material"] = material
        m = {"name": name, "primitives": [prim]}
        if extras:
            m["extras"] = extras
        self.meshes.append(m)
        return len(self.meshes) - 1

    def node(self, name, mesh=None, translation=None, in_scene=True, extras=None):
        n = {"name": name}
        if mesh is not None:
            n["mesh"] = mesh
        if translation is not None:
            n["translation"] = [float(translation[0]), float(translation[2]), float(-translation[1])]
        if extras:
            n["extras"] = extras
        self.nodes.append(n)
        if in_scene:
            self.scene.append(len(self.nodes) - 1)
        return len(self.nodes) - 1

    def write(self, path, extras=None, generator="hifipushie clutter"):
        while len(self.buf) % 4:
            self.buf.append(0)
        G = {"asset": {"version": "2.0", "generator": generator}, "scene": 0, "scenes": [{"nodes": self.scene}],
             "nodes": self.nodes, "meshes": self.meshes, "accessors": self.acc, "bufferViews": self.views,
             "buffers": [{"byteLength": len(self.buf)}]}
        if self.mats:
            G["materials"] = self.mats
        if self.tex:
            G["textures"], G["images"], G["samplers"] = self.tex, self.images, self.samplers
        if extras:
            G["asset"]["extras"] = extras
        js = json.dumps(G, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        with open(path, "wb") as f:
            f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(self.buf)))
            f.write(struct.pack("<I4s", len(js), b"JSON") + js)
            f.write(struct.pack("<I4s", len(self.buf), b"BIN\x00") + bytes(self.buf))
        return str(path)


ALPHA_MIPS = ("import the albedo WITH mipmaps and scale alpha up by the mip level in the shader so thin leaves survive (as the groundcover grade): "
              "alpha = (a - cutoff) * (1 + lod * 0.25) / max(fwidth(a), 1e-4) + 0.5 for alpha to coverage, or a *= 1 + lod * 0.25 before the "
              "cut; the dome itself is opaque (alpha 1), so a far bush never thins to nothing")
WET_RECIPE = ("wet rock: below the water line + `band` x the instance's height (and anywhere it rains), albedo *= mix(1, darken, wet), "
              "roughness = mix(roughness, wet roughness, wet); a river rock standing in water: wet = 1 below the line, fading "
              "over ~5 cm above it")
TINT_RECIPE = ("ROCK MATCHES ITS CLIFFS BY A PER-INSTANCE COLOUR: the pictures hold this style's default rock colour (`color_linear`). Per "
               "instance (MultiMesh instance colour / INSTANCE_CUSTOM, multiplied into the albedo in linear RGB): tint = (the rock colour of the "
               "terrain where it stands: the terrain styles manifest's rock layer colour for the style region, linear) / color_linear x "
               "instance_tints[hash(row) % n] x (0.92 + 0.16 x hash). Lichen, moss and the damp foot shift a little with it, which reads fine. "
               "The four variants already differ in mineral tone (baked); instance_tints adds warm / cool / brown stones on top")
INSTANCE_TINTS = [[1.0, 1.0, 1.0], [1.05, 1.0, 0.94], [0.96, 0.99, 1.03], [1.04, 0.98, 0.91], [0.95, 0.95, 0.95]]
INSTANCE_RECIPE = ("one MultiMesh per variant per LOD (per cell of the world): instance = translate(row x, y, z) * rotate_up(yaw) * "
                   "scale(s, s, s * squash); variant = hash(row) % variants; switch LODs by distance / s at `lod_switch_m` "
                   "(x the instance's scale), fade out over the last fifth before `cull`. The pivot is the ground line: the "
                   "mesh below it (sink_m x scale) is buried. Never scale below ~0.6 or above ~1.8 of size_range without "
                   "another kind: texel and facet sizes are made for that range")


def litter_tile(px: int, f: dict, season: str, sat_val, seed: int):
    """A debris patch's picture from above: (rgb (px, px, 3) sRGB, alpha). Leaves lie thickest in the middle and thin
    out raggedly; each casts a little shade on what is under it; twigs and crumbs between."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    from .terrain_style import _hsv
    rng = np.random.default_rng(seed)  # (the same seed every season: the same patch, leaves added or gone)
    S = 3 * px
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    pal = [np.asarray(_hsv(c, sat_val[0], sat_val[1])) for c in f["colors"].get(season, f["colors"]["summer"])]
    n0 = int(rng.integers(f["leaves"][0], f["leaves"][1] + 1))
    lobe = rng.uniform(0, 2 * math.pi, 3)

    def spot():  # a ragged round patch: denser in the middle, lobed outline
        while True:
            a = rng.uniform(0, 2 * math.pi)
            r = 0.44 * rng.uniform() ** 0.7 * (1 + 0.18 * math.sin(3 * a + lobe[0]) + 0.1 * math.sin(5 * a + lobe[1]))
            if r < 0.44:
                return np.array([0.5 + r * math.cos(a), 0.5 + r * math.sin(a)])
    tw = tuple(int(255 * c) for c in _hsv(f["twig_color"], sat_val[0], sat_val[1])) + (255,)
    for _ in range(int(rng.integers(f["bits"][0], f["bits"][1] + 1))):
        c = spot() * S
        r = rng.uniform(0.004, 0.01) * S
        dr.ellipse([c[0] - r, c[1] - r * 0.7, c[0] + r, c[1] + r * 0.7], fill=tw)
    leaves = []
    for i in range(n0):
        leaves.append((spot(), rng.uniform(0, 2 * math.pi), _u(rng, f["leaf"]), rng.uniform(-1, 1), int(rng.integers(0, 8)), rng.uniform()))
    keep = {"summer": 1.0, "autumn": f["autumn"], "winter": f["winter"], "spring": f["spring"]}.get(season, 1.0)
    extra = np.random.default_rng(seed + 5)
    if keep > 1:
        for i in range(int(n0 * (keep - 1))):
            leaves.append((spot(), extra.uniform(0, 2 * math.pi), _u(extra, f["leaf"]), extra.uniform(-1, 1), int(extra.integers(0, 8)), extra.uniform()))
    else:
        leaves = [l for l in leaves if l[5] < keep]
    for j in range(int(rng.integers(f["twigs"][0], f["twigs"][1] + 1))):
        c, a, L = spot(), rng.uniform(0, 2 * math.pi), _u(rng, f["twig"])
        d = np.array([math.cos(a), math.sin(a)])
        k = rng.uniform(-0.15, 0.15)
        pts = [tuple(((c + d * L * (t - 0.5) + np.array([-d[1], d[0]]) * k * L * math.sin(math.pi * t)) * S).tolist()) for t in np.linspace(0, 1, 8)]
        dr.line(pts, fill=tw, width=max(2, int(0.006 * S)))
    for c, a, L, tn, ci, _ in leaves:
        d = np.array([math.cos(a), math.sin(a)])
        nrm = np.array([-d[1], d[0]])
        W = L * f["round"]
        poly = []
        us = np.linspace(0, 1, 13)
        for sgn, seq in ((1, us), (-1, us[::-1][1:-1])):
            for u in seq:
                w = W * 0.5 * math.sin(math.pi * u ** 0.75)
                if f["lobed"]:
                    w *= 1 - f["lobed"] * 0.5 * (0.5 + 0.5 * math.cos(u * 5 * 2 * math.pi))
                poly.append(c + d * L * (u - 0.5) + nrm * w * sgn)
        tone = 1 + f["tones"] * tn
        if f["steps"]:
            tone = round(tone * f["steps"]) / f["steps"]
        col = np.clip(pal[ci % len(pal)] * tone, 0, 1)
        xy = [tuple((q * S).tolist()) for q in poly]
        if f["shadow"]:
            sh = [tuple((q * S + [0.004 * S, 0.006 * S]).tolist()) for q in poly]
            dr.polygon(sh, fill=tuple(int(255 * x * (1 - f["shadow"])) for x in col) + (255,))
        dr.polygon(xy, fill=tuple(int(255 * x) for x in col) + (255,))
        if f["outline"]:
            dr.line(xy + [xy[0]], fill=tuple(int(255 * x * 0.3) for x in col) + (255,), width=max(2, int(f["outline"] * S)))
        else:
            dr.line([tuple(((c - d * L * 0.5) * S).tolist()), tuple(((c + d * L * 0.45) * S).tolist())],
                    fill=tuple(int(255 * x * 0.75) for x in col) + (255,), width=max(1, S // 400))
    im = im.resize((px, px), Image.LANCZOS)
    a = np.asarray(im, float) / 255.0
    alpha, rgb = a[..., 3], a[..., :3]
    solid = alpha > 0.5
    if solid.any():
        idx = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        rgb = rgb[idx[0], idx[1]]
    return rgb, alpha


def _export_litter(cfg: dict, out: Path, stem: str, progress=None) -> dict:
    """A debris patch: LOD 0 an octagon lifted a little in the middle (8 triangles), LOD 1 a quad; one RGBA picture
    per season (all variants in it); no normal map (a flat lie: the vertex normal is the ground's up)."""
    from . import veg_export
    f = cfg["form"]
    nv = cfg["variants"]
    grid = 1 if nv == 1 else 2
    base = cfg["atlas"]
    cell = base // grid
    st = style_sheet(cfg["style"]).get("colour") or {}
    sv = (st.get("saturation", 1.0), st.get("value", 1.0))
    season_tex = {}
    for se in ("summer", "spring", "autumn", "winter"):
        im = np.zeros((base, base, 4))
        for k in range(nv):
            rgb, al = litter_tile(cell, f, se, sv, cfg["seed"] * 100 + k)
            x0, y0 = (k % grid) * cell, (k // grid) * cell
            im[y0: y0 + cell, x0: x0 + cell, :3], im[y0: y0 + cell, x0: x0 + cell, 3] = rgb, al
        fn = f"{stem}_albedo.png" if se == "summer" else f"{stem}_albedo_{se}.png"
        (out / fn).write_bytes(_png(im))
        season_tex[se] = fn
    mext = {"hifipushie_clutter": {"kind": cfg["kind"], "style": cfg["style"], "grade": "clutter"}, "alpha_mips": ALPHA_MIPS}

    def mat(g):
        return g.material({"name": "litter", "pbrMetallicRoughness": {"baseColorTexture": {"index": g.image(season_tex["summer"])}, "metallicFactor": 0.0, "roughnessFactor": 0.9},
                           "alphaMode": "MASK", "alphaCutoff": 0.5, "extras": mext})

    def mesh(k, lod):
        x0, y0 = (k % grid) * cell, (k // grid) * cell
        if lod == 0:
            a = np.arange(8) * math.pi / 4 + math.pi / 8
            r = 0.5 / math.cos(math.pi / 8)
            V = np.r_[[[0, 0, f["dome"]]], np.c_[r * np.cos(a), r * np.sin(a), np.zeros(8)]]
            F = np.array([[0, 1 + i, 1 + (i + 1) % 8] for i in range(8)])
        else:
            V = np.array([[-0.5, -0.5, 0.004], [0.5, -0.5, 0.004], [0.5, 0.5, 0.004], [-0.5, 0.5, 0.004]])
            F = np.array([[0, 1, 2], [0, 2, 3]])
        V = np.clip(V, [-0.5, -0.5, 0], [0.5, 0.5, 1])
        UV = np.c_[(x0 + (V[:, 0] + 0.5) * cell) / base, (y0 + (0.5 - V[:, 1]) * cell) / base]
        N = np.tile([0, 0, 1.0], (len(V), 1))
        return V, F, N, UV
    variants, on = [], []
    for k in range(nv):
        files = []
        for lod in (0, 1):
            V, F, N, UV = mesh(k, lod)
            g = Glb()
            g.node("litter", g.mesh(f"v{k}_LOD{lod}_litter", V, F, N, None, UV, material=mat(g)))
            fn = f"{stem}_v{k}_LOD{lod}.glb"
            g.write(out / fn)
            files.append({"lod": lod, "file": fn, "triangles": int(len(F)), "vertices": int(len(V)), "outline_iou": 1.0})
            on.append({"file": fn, "mesh": f"v{k}_LOD{lod}_litter", "primitive": 0})
        variants.append({"name": f"v{k}", "lods": files, "collision": None, "collision_triangles": 0, "height_m": f["dome"], "sink_m": 0.0,
                         "bounds": [[-0.5, -0.5, 0], [0.5, 0.5, f["dome"]]]})
    g = Glb()
    m = mat(g)
    for k in range(nv):
        V, F, N, UV = mesh(k, 0)
        g.node(f"v{k}", g.mesh(f"v{k}_LOD0_litter", V, F, N, None, UV, material=m), translation=(1.2 * k, 0, 0))
    g.write(out / f"{stem}.glb")

    def state(se):
        hidden = se == "snow"
        return {"material": "litter", "baseColorFactor": [1, 1, 1, 1], "roughnessFactor": 0.9, "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": False,
                "hidden": hidden, "baseColorTexture": {"file": season_tex.get(se, season_tex["winter"])}}
    J = {"contract": {"version": veg_export.CONTRACT, "changes": veg_export.CONTRACT_LOG,
                      "rule": "an engine should refuse a version or a slot it doesn't know: every slot is in slot_list"},
         "grade": "clutter", "kind": cfg["kind"], "style": {"name": cfg["style"], "foliage": None}, "about": cfg["about"], "glb": f"{stem}.glb",
         "lods": [{"lod": j, "triangles": [v["lods"][j]["triangles"] for v in variants], "grade": "clutter"} for j in (0, 1)],
         "slot_list": [{"slot": "litter", "on": on, "hidden_in": ["snow"], "channels": ["NORMAL", "POSITION", "TEXCOORD_0"]}],
         "slots": {"litter": state("summer")}, "default": "summer", "variants": [],
         "seasons": {se: {"litter": state(se)} for se in ("spring", "summer", "autumn", "winter", "snow")},
         "snow": None, "impostor": None, "alpha_mips": ALPHA_MIPS,
         "clutter": {"size_m": 1.0, "what_scale_means": "instance scale = the patch's width in metres", "height_m": f["dome"], "sink_m": 0.0,
                     "pivot": "the ground: lay it ON the surface, turned to the ground's normal (a decal with a mesh); draw after the terrain with a small depth bias, or lift it 1 cm",
                     "size_range_m": cfg["size_range"], "place": cfg["place"], "variants": variants,
                     "lod_switch_m": {"lod1": 8.0, "lod2": None, "cull": 30.0, "times": "the instance's scale"},
                     "instancing": INSTANCE_RECIPE, "collision": None, "wet": None, "tint": None,
                     "textures": {"atlas_px": base, "shared_by": "every variant and LOD", "mipmaps": True, "normal": None,
                                  "seasons": "a season is another albedo picture (same uv, the same patch with leaves added or gone): seasons.<season>.litter.baseColorTexture.file; hidden under snow"}},
         "note": "a debris patch is one alpha-MASK card per variant; cast no shadow, receive shadows"}
    (out / f"{stem}_seasons.json").write_text(json.dumps(J, indent=1))
    return J


def export(spec: dict, out_dir, stem: str | None = None, progress=None) -> dict:
    """Write a clutter asset into out_dir: <stem>_v<k>_LOD<j>.glb per variant and LOD, <stem>_v<k>_collision.glb
    (convex hull, node `..-convcolonly`), the shared <stem>_albedo[_<season>] / _normal / _orm.png (referenced by uri),
    <stem>.glb (every variant's LOD 0 in a row, to look at), <stem>_seasons.json (the plant contract's shape: grade
    "clutter", kind, slots, lods, variants, sizes, recipes). Returns the json."""
    from . import veg_export
    from .terrain_style import _srgb_lin as _lin
    cfg = resolve(spec)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = stem or f"ck_{cfg['kind']}_{cfg['style']}"
    if cfg["material"] == "litter":
        return _export_litter(cfg, out, stem, progress)
    B = build(spec, progress)
    leaf = cfg["material"] == "leaf"
    slot = {"wood": "wood", "leaf": "foliage"}.get(cfg["material"], "rock")
    tex, season_tex = {}, {}
    for se, im in B["albedo"].items():
        fn = f"{stem}_albedo.png" if se == "summer" else f"{stem}_albedo_{se}.png"
        (out / fn).write_bytes(_png(im if leaf else im[..., :3]))
        season_tex[se] = fn
    tex["albedo"] = season_tex["summer"]
    for nm, im in (("normal", B["normal"]), ("orm", B["orm"])):
        tex[nm] = f"{stem}_{nm}.png"
        (out / tex[nm]).write_bytes(_png(im))
    mext = {"hifipushie_clutter": {"kind": cfg["kind"], "style": cfg["style"], "grade": "clutter", "wet": cfg["wet"]}}
    if leaf:
        mext["alpha_mips"] = ALPHA_MIPS
        mext["wind"] = veg_export.WIND_RECIPE

    def mat(g):
        a_, n_, o_ = g.image(tex["albedo"]), g.image(tex["normal"]), g.image(tex["orm"])
        m = {"name": slot, "pbrMetallicRoughness": {"baseColorTexture": {"index": a_}, "metallicRoughnessTexture": {"index": o_},
                                                      "metallicFactor": 0.0, "roughnessFactor": 1.0},
             "normalTexture": {"index": n_}, "occlusionTexture": {"index": o_}, "extras": mext}
        if leaf:
            m["alphaMode"], m["alphaCutoff"] = "MASK", 0.5
        return g.material(m)
    variants, on = [], []
    for v in B["variants"]:
        files = []
        for j, L in enumerate(v["lods"]):
            g = Glb()
            g.node(f"{slot}", g.mesh(f"{v['name']}_LOD{j}_{slot}", L["V"], L["F"], L["N"], L["T"], L["UV"], material=mat(g), wind=L.get("wind")))
            fn = f"{stem}_{v['name']}_LOD{j}.glb"
            g.write(out / fn)
            files.append({"lod": j, "file": fn, "triangles": L["triangles"], "vertices": int(len(L["V"])), "outline_iou": L.get("iou", 1.0),
                          **({"cards": L.get("cards", 0)} if leaf else {})})
            on.append({"file": fn, "mesh": f"{v['name']}_LOD{j}_{slot}", "primitive": 0})
        colf = None
        if v["collision"] is not None:
            g = Glb()
            g.node(f"{stem}_{v['name']}-convcolonly", g.mesh("collision", v["collision"][0], v["collision"][1]))
            colf = f"{stem}_{v['name']}_collision.glb"
            g.write(out / colf)
        variants.append({"name": v["name"], "lods": files, "collision": colf, "collision_triangles": int(len(v["collision"][1])) if colf else 0,
                         "height_m": v["height"], "sink_m": v["sink"], "bounds": v["bounds"]})
    g = Glb()
    m = mat(g)
    for i, v in enumerate(B["variants"]):
        L = v["lods"][0]
        g.node(f"{v['name']}", g.mesh(f"{v['name']}_LOD0_{slot}", L["V"], L["F"], L["N"], L["T"], L["UV"], material=m, wind=L.get("wind")), translation=(1.4 * i, 0, 0))
    g.write(out / f"{stem}.glb", extras={"hifipushie_clutter": {"kind": cfg["kind"], "style": cfg["style"]}})

    def state(se):
        st = {"material": slot, "baseColorFactor": [1, 1, 1, 1], "roughnessFactor": 1.0, "alphaMode": "MASK" if leaf else "OPAQUE", "doubleSided": False,
              "hidden": False, "baseColorTexture": {"file": season_tex.get(se, season_tex.get("winter" if se == "snow" else "summer", tex["albedo"]))},
              "normalTexture": {"file": tex["normal"]},
              "ormTexture": {"file": tex["orm"], "channels": "R occlusion, G roughness, B metallic (0)"}}
        if leaf:
            st["alphaCutoff"] = 0.5
        return st
    snow = veg_export.snow_numbers({}, None)
    snow.pop("variant", None)
    channels = ["NORMAL", "POSITION", "TANGENT", "TEXCOORD_0"] + (["TEXCOORD_1", "TEXCOORD_2", "_WIND"] if leaf else [])
    J = {"contract": {"version": veg_export.CONTRACT, "changes": veg_export.CONTRACT_LOG,
                      "rule": "an engine should refuse a version or a slot it doesn't know: every slot is in slot_list"},
         "grade": "clutter", "kind": cfg["kind"], "style": {"name": cfg["style"], "foliage": "a closed leafy dome + leaf sprays on alpha cards (one material)" if leaf else None},
         "about": cfg["about"],
         "glb": f"{stem}.glb",
         "lods": [{"lod": j, "triangles": [v["lods"][j]["triangles"] for v in variants], "grade": "clutter"} for j in range(len(cfg["lods"]))],
         "slot_list": [{"slot": slot, "on": on, "hidden_in": [], "channels": channels}],
         "slots": {slot: state("summer")},
         "default": "summer", "variants": [],
         "seasons": {se: {slot: state(se)} for se in ("spring", "summer", "autumn", "winter", "snow")},
         "snow": snow, "impostor": None,
         "clutter": {"size_m": 1.0, "what_scale_means": "instance scale = the largest plan dimension in metres (the mesh is 1 m at scale 1" + (", its sprays a little more)" if leaf else ")"),
                     "height_m": round(float(np.mean([v["height_m"] for v in variants])), 3),
                     "sink_m": round(float(np.mean([v["sink_m"] for v in variants])), 3),
                     "pivot": "the ground line: place it ON the surface; sink_m (x scale) of the mesh is below it",
                     "size_range_m": cfg["size_range"], "place": cfg["place"],
                     "variants": variants, "lod_switch_m": {"lod1": LOD_SWITCH[0], "lod2": LOD_SWITCH[1], "cull": LOD_SWITCH[2], "times": "the instance's scale"},
                     "color_srgb": [round(c, 4) for c in cfg["color"]], "color_linear": [round(float(c), 4) for c in _lin(cfg["color"])],
                     "wet": {**cfg["wet"], "recipe": WET_RECIPE}, "tint": TINT_RECIPE if slot == "rock" else None,
                     "instance_tints": INSTANCE_TINTS if slot == "rock" else None, "instancing": INSTANCE_RECIPE,
                     "collision": ("convex hull per variant (<stem>_v<k>_collision.glb, node name ends -convcolonly); scale with the instance"
                                   if cfg["collision"] else None),
                     "textures": {"atlas_px": cfg["atlas"], "shared_by": "every variant and LOD of this folder (uv by position: box charts)",
                                  "mipmaps": True, "normal": "tangent space, OpenGL (+Y up), TANGENT written in the meshes",
                                  "seasons": "a season changes only the albedo picture (same uv): seasons.<season>.<slot>.baseColorTexture.file" if leaf else None}},
         "note": ("a clutter bush has ONE slot (foliage: the dome and its sprays, alpha MASK); a season = another albedo picture; snow = the winter picture + the snow numbers on the vertex NORMAL"
                  if leaf else "a clutter solid has one slot and no season variants: seasons are the same material (snow = the snow numbers on the vertex NORMAL)")}
    if leaf:
        J["alpha_mips"] = ALPHA_MIPS
        J["wind"] = veg_export.WIND_RECIPE
    (out / f"{stem}_seasons.json").write_text(json.dumps(J, indent=1))
    return J


def report(J: dict) -> str:
    c = J["clutter"]
    v = c["variants"]
    lines = [f"clutter {J['kind']} in style {J['style']['name']} (contract {J['contract']['version']}, grade clutter): {len(v)} variants, "
             f"height {c['height_m']} m at 1 m across, {c['sink_m']} m of it below the ground line",
             "triangles per LOD: " + "; ".join(f"LOD{l['lod']} " + "/".join(str(t) for t in l["triangles"]) for l in J["lods"]),
             "outline IoU against LOD 0 (8 directions): " + "; ".join(
                 f"LOD{j} " + "/".join(f"{x['lods'][j]['outline_iou']:.2f}" for x in v) for j in range(1, len(J["lods"])))
             + ("  WARNING: a LOD under 0.9 pops" if any(l_["outline_iou"] < 0.9 for x in v for l_ in x["lods"]) else ""),
             f"LOD switch at {c['lod_switch_m']['lod1']} / {c['lod_switch_m']['lod2']} m x scale, gone at {c['lod_switch_m']['cull']} m x scale",
             "collision: " + (f"convex hulls of {'/'.join(str(x['collision_triangles']) for x in v)} triangles" if c["collision"] else "none (walked over)"),
             f"textures: {c['textures']['atlas_px']} px " + ("albedo / normal / orm" if c['textures'].get('normal') else "albedo (alpha), a picture per season") + " shared by all variants and LODs",
             f"files: {J['glb']} (all variants, to look at), <stem>_v<k>_LOD<j>.glb, <stem>_seasons.json"]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------- looks, kits, manifest
def look(folders, out: str, distances=(2.5, 10.0, 40.0), lods=(0, 1, 2), scale: float = 1.0, clay: bool = False, season: str = "summer") -> str:
    """A sheet of exported clutter folders (a row each): every variant side by side on rough grass at each distance
    with the LOD drawn there; the far views are centre crops of a 1280 x 720 frame at a 50 deg lens, enlarged (real
    pixels). Blender (EEVEE), ~10 s a picture. Returns `out`."""
    import os
    import subprocess
    import tempfile
    from PIL import Image, ImageDraw
    from .render import BLENDER
    tmp = Path(tempfile.mkdtemp(prefix="cklook"))
    rows = []
    for fi, fo in enumerate([folders] if isinstance(folders, (str, Path)) else folders):
        fo = Path(fo)
        J = json.loads(next(fo.glob("*_seasons.json")).read_text())
        cl = J["clutter"]
        vs = cl["variants"]
        n = len(vs)
        width = n * 1.25 * scale
        tiles = []
        items, views, meta = [], [], []
        for di, (d0, lod) in enumerate(zip(distances, lods)):
            oy = 300.0 * di
            items += [{"glb": str(fo / v["lods"][min(lod, len(v["lods"]) - 1)]["file"]), "at": [(i - (n - 1) / 2) * 1.25 * scale, oy, 0],
                       "yaw": 25 * i, "scale": scale} for i, v in enumerate(vs)]
            d = max(d0, width * 0.95 + 0.8) if di == 0 else d0
            png = tmp / f"r{fi}_{di}.png"
            views.append({"eye": [0.35 * d, oy - d, 1.6 if d > 3 else 1.1], "look": [0, oy, cl["height_m"] * scale * 0.35], "fov": 50, "out": str(png), "res": [1280, 720]})
            meta.append((d0, d, lod, png))
        job = {"items": items, "clay": clay, "views": views}
        tex = (J.get("seasons", {}).get(season) or {})
        job["albedo"] = next((v_["baseColorTexture"]["file"] for v_ in tex.values() if isinstance(v_, dict) and v_.get("baseColorTexture")), None) if season != "summer" else None
        jp = tmp / f"j{fi}.json"
        jp.write_text(json.dumps(job))
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(HERE / "blender_clutter.py"), "--", str(jp)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ})
        for d0, d, lod, png in meta:
            im = Image.open(png).convert("RGB")
            ppm = 640 / 0.4663 / (d * 1.06)
            cw = int(min(1280, max(120, (width + 0.6) * ppm)))
            ch = int(cw * 360 / 960)
            z = max(1, 960 // cw)
            cy = 360 + int(0.02 * 720)
            t = im.crop((640 - cw // 2, cy - ch // 2, 640 + cw // 2, cy + ch // 2)).resize((960, 360), Image.NEAREST if z > 1 else Image.LANCZOS)
            ImageDraw.Draw(t).text((6, 4), f"{fo.name}  {d0:g} m  LOD{lod}" + (f"  (x{z} pixels)" if z > 1 else ""), fill=(255, 255, 255))
            tiles.append(t)
        rows.append(tiles)
    sheet = Image.new("RGB", (960 * len(distances), 360 * len(rows)))
    for r, tiles in enumerate(rows):
        for c, t in enumerate(tiles):
            sheet.paste(t, (960 * c, 360 * r))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return str(out)


SHORT = {"realistic": "real"}
# terrain clutter kinds -> what to draw them with (assets of this kit, or plants delivered beside them)
TERRAIN_KINDS = {
    "bush": {"asset": "bush", "z": "surface", "what": "scrub bush; squash < 1 near cliff lips (wind-shorn)"},
    "boulder": {"asset": "boulder", "z": "sunk 0.12 x scale already (old rows): lift by sink_m x scale, or accept it", "what": "angular boulders on rock and shores"},
    "river_rock": {"asset": "river_rock", "z": "surface", "what": "water-worn boulders in and beside a channel"},
    "cobbles": {"asset": "cobbles", "z": "surface", "what": "a patch of cobbles as one asset"},
    "slab": {"asset": "slab", "z": "surface", "what": "flat bank stones"},
    "driftwood": {"asset": "driftwood", "z": "surface, or the water surface - 6 cm when afloat", "what": "logs, branches, a jam (variants)"},
    "litter": {"asset": "litter", "z": "surface", "what": "a leaf / twig debris card"},
    "reeds": {"plant": "reed_ground", "z": "surface (root at or just under the water line)", "what": "reed clump, groundcover grade: scale = width / the json's clump width"},
    "sedge": {"plant": "grass_ground", "z": "surface", "what": "a bank tussock: the grass tuft (groundcover grade, cards), scale = width / 0.45; a `sedge` preset of its own is not made yet"},
    "tussock": {"plant": "grass_ground", "z": "surface", "what": "a grass tuft (groundcover grade), 0.45 m"},
    "tallgrass": {"plant": "grass_ground", "z": "surface", "what": "the same tuft drawn taller (scale 1.5); or leave it to the sward"},
}


def manifest(root) -> dict:
    """Write <root>/clutter.json: terrain clutter kind -> the folder to draw it with, per style (what exists under
    root), with the instance convention. An engine reads this once, then each folder's <stem>_seasons.json."""
    root = Path(root)
    sts = styles()
    kinds = {}
    for kind, how in TERRAIN_KINDS.items():
        per = {}
        for st in sts:
            f = root / f"{SHORT.get(st, st)}_{how.get('asset') or how['plant']}"
            js = list(f.glob("*_seasons.json")) if f.is_dir() else []
            if js:
                J = json.loads(js[0].read_text())
                per[st] = {"folder": f.name, "json": js[0].name, "grade": J.get("grade"), "contract": J.get("contract", {}).get("version"),
                           "variants": len(J["clutter"]["variants"]) if J.get("clutter") else 1}
        pre = HERE / "clutter_presets" / f"{how.get('asset')}.json"
        info = json.loads(pre.read_text()) if how.get("asset") and pre.exists() else {}
        kinds[kind] = {"what": how["what"], "z": how["z"], "kit": "clutter" if how.get("asset") else "plant (groundcover grade)",
                       "size_range_m": info.get("size_range"), "place": info.get("place"), "styles": per,
                       "missing": [st for st in sts if st not in per]}
    M = {"about": "terrain clutter kinds (clutter.csv / the tiles manifest's clutter.kinds) -> the asset folder that draws each, per style",
         "row": "x, y, z, kind, scale, yaw, squash[, place]: scale = the largest plan dimension in m (assets are 1 m at scale 1), yaw deg about up (0 = the "
                "asset's +X along world +X), squash = RELATIVE height (1 = the asset's own proportions): instance = T(x, y, z) * Rz(yaw) * S(scale, scale, scale * squash)",
         "variant": "variant = hash(row) % variants (a folder's json lists them); mirror in x for every other row if you want more",
         "lods": "each folder's json: clutter.lod_switch_m x the instance's scale",
         "kinds": kinds}
    (root / "clutter.json").write_text(json.dumps(M, indent=1))
    return M


def kit(root, kinds=None, style_names=None, progress=None, **over) -> dict:
    """Export a whole kit into root (<style>_<kind>/ folders, "realistic" -> "real") and write the manifest."""
    out = {}
    for st in style_names or styles():
        for kind in kinds or presets():
            sh = SHORT.get(st, st)
            J = export({"kind": kind, "style": st, **over}, Path(root) / f"{sh}_{kind}", stem=f"ck_{kind}_{sh}", progress=progress)
            out[f"{sh}_{kind}"] = J
            if progress:
                progress(report(J))
    manifest(root)
    return out
