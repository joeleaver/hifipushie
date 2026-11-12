"""The skin's feature layers (skin.py calls `build` between its colour zones and its micro relief): spots and marks,
wrinkles, hair, scars, tattoos, make-up. Each is a few ordinary paint layers ("skin:<name>").

Every feature takes a number (its amount, 0..1) or an object {"amount", ...its own keys..., "where": [zones]
(replaces its default zones), "mask": [paint mask entries] (multiplied in: confine it any way paint can), "seed"}.

FEATURES (skin.features):
  freckles   {"amount", "size": m (0.0018)}: small tan macules, more melanin, clustered on nose, cheeks, forehead,
             shoulders and forearms; two sizes.
  moles      {"amount", "at": [point, ...] (placed ones: joints / [x, y, z] / {"at", "offset"}), "size": m (0.0025)}:
             a few dark brown nevi, some raised.
  age_spots  amount (default from age x sun): larger, sharper-edged brown patches on temples, cheekbones, backs of
             hands, forearms.
  blemishes  {"amount", "size"}: acne: red papules with a raised, slightly shiny centre, on cheeks, chin, forehead, jaw.
  veins      amount (default from age and thin skin): blue-green branching lines on backs of hands, inner wrists,
             forearms, temples; raised on old hands.
  flush      amount: more blood in cheeks, nose and ears (exertion, cold, embarrassment, rosacea).
  sunburn    amount: red on what faces the sun (forehead, nose, cheekbones, shoulders).
  tan        {"amount", "mask"}: more melanin; give "mask" to leave tan lines (e.g. [{"zone": "upper_arm", "invert": true}]).
WRINKLES (skin.wrinkles; every amount defaults from age, 0 turns one off, > 1 exaggerates; "amount" scales all):
  forehead, glabella (the "11" between the brows), crows_feet, under_eye, nasolabial, marionette, lip_lines (round
  the mouth), neck (rings), crepe (fine cross-hatched skin: cheeks, neck, hands, with age).
HAIR (skin.hair; colours sRGB):
  brows      {"color", "density": 0..1 (0.8), "thickness": 1, "length": m (0.006), "grey": 0..1, "drop": m (0: the
             brow lower, onto the orbital rim), "arch": 1 (x the landmarks' slope: 0 = level), "tilt": deg (the whole
             brow turned, tail up +), "fall": 1 (x how far the tail drops past the arch: 0.3 = a straight, rising
             brow), "lift": [inner, tail] m (each end up + / down -), "apart": m (both brows off the mid-line), "soft": 0..1 (a soft mass rather than hairs one by one), "feather": m (the band's lower edge fades over it: photos ~.0012-.0016), "shadow": x the skin-level shadow under the hairs (1; lower = gaps and a fading head show), "taper":
             0..1 (0.82: how much the band thins toward the tail; 0.95 = a clean thin tail on a thick brow), "tail":
             0..1 (1: how far along the hairs reach), "head": 0..0.6 (0: the share of the length over which the inner end fades
             in, sparse single hairs; 0.65 matches the photos' ramp), "head_density": 0..1 (0.05: the share of hairs kept at the inner end), "strands": 0..1 (0: fine hairs of their own tone, tips making the top edge, piled up not clipped; 1 = a young fine brow, .5 = a coarser older one)}: hairs as strokes, growing up at the inner end and out along the brow.
  lashes     {"color", "amount": 0..1 (0.7), "width": 1 (x the lash line's width, with lash geometry)}: the lash lines
             darkened (upper more).
  stubble    {"amount", "color", "where", "size": 1 (the dots' size), "count": 1 (hairs per area x, .25-4: density saturates at 1), "shadow": 1 (the under-skin shadow's strength; "shadow_color",
             "shadow_breakup": its noise, 0 = an even field: a dense stubble shadow reads as one grey-brown field),
             "grey": 0..1 (+ "grey_color": a share of white hairs: salt and pepper), "zones": {moustache, chin, soul_patch, jaw,
             cheeks, neck: weight 0..1.5 (1)} (where it grows: a goatee, bare cheeks)}: the beard area: a shadow under the
             skin plus hair dots.
  scalp      {"amount", "color", "hairline": 0..1 (0.5: how far it comes down the forehead)}: a shaved or cropped
             head: the shadow of hair under the scalp's skin plus cut hairs, with a hairline. (Longer hair is geometry:
             groom_hair.)
  body       {"amount", "color"}: fine dark hairs on forearms, shins, chest.
SCARS (skin.scars: a list): {"kind": "cut" | "surgical" | "keloid" | "burn" | "pockmarks", "path": [points] (cut,
  surgical, keloid: along a line) | "at": point + "radius": m | "zone": name (burn, pockmarks, keloid: a patch),
  "width": m, "age": 0 fresh (red, raised) .. 1 old (pale, flat, slightly shiny), "normal": [x, y, z] (surgical: out of
  the skin there, for the stitch marks; default [0, -1, 0])}. Scar tissue has no pores: the micro relief stops on it.
TATTOOS (skin.tattoos: a list): {"image": {a paint image: "file" | "text", "at", "size", "dir", "wrap": "surface" |
  "cylinder", ...}, "age": years (2), "opacity": 0.9, "ink": "#1c2026" (text and alpha-only images)}: ink in the
  dermis: multiplied into the skin under its relief and highlights; with age the lines spread, black turns blue-green
  and colours fade.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at skin_features.NAME: C422). skin_features_mouth: the mouth: inner lip values, the interior's values, GNM's
own mouth. skin_features_eyes: the eyes: the eye's base and its layers. skin_features_marks: marks on the skin:
wrinkles, freckles, scars, tattoos. skin_features_hair: hair on the skin: brows and lashes, stubble and its map.
skin_features_build: `build`: every feature's layers for a spec.
"""
from __future__ import annotations

import numpy as np

from .spec import SpecError
from . import moved

FEATURES = ("freckles", "moles", "age_spots", "blemishes", "veins", "flush", "sunburn", "tan")
WRINKLES = ("amount", "forehead", "glabella", "glabella_side", "crows_feet", "under_eye", "nasolabial", "marionette", "lip_lines", "neck", "crepe")
HAIR = ("brows", "lashes", "stubble", "scalp", "body")
SCARS = ("cut", "surgical", "keloid", "burn", "pockmarks")
COMMON = {"amount", "where", "mask", "seed"}


def _opt(v, what: str, extra=()) -> dict | None:
    """A feature's value as {"amount", ...} (None when off)."""
    if v is None or v is False:
        return None
    if v is True:
        v = 1.0
    if isinstance(v, (int, float)):
        v = {"amount": float(v)}
    if not isinstance(v, dict):
        raise SpecError(f"skin {what}: a number (its amount) or an object")
    bad = set(v) - COMMON - set(extra)
    if bad:
        raise SpecError(f"skin {what}: unknown keys {sorted(bad)} (have {', '.join(sorted(COMMON | set(extra)))})")
    out = {"amount": 1.0, **v}
    return out if float(out["amount"]) > 0 else None


def _zones(names, grow=1.0) -> list:
    return [{"zone": {"name": n, "grow": grow}, **({"blend": "max"} if i else {})} for i, n in enumerate(names)]


def _where(o: dict, default: list, have: dict) -> list:
    """The feature's zones as one nested mask entry (zones the model has no joints for are left out)."""
    names = o.get("where") or [z for z in default if _has(z, have)]
    return [{"vertex": True, "mask": _zones(names)}] if names else []


BODY_NEED = {"shoulder": "arms", "elbow": "arms", "forearm": "arms", "upper_arm": "arms", "knee": "legs", "foot": "feet",
             "sole": "feet", "chest": "torso", "collarbone": "face"}


def _has(zone: str, have: dict) -> bool:
    stem = zone[:-2] if zone.endswith((".L", ".R")) else zone
    if stem in BODY_NEED:
        return bool(have.get(BODY_NEED[stem]))
    if stem in ("knuckles", "hand", "palm", "back_of_hand", "fingertips", "nails", "wrist_inner"):
        return bool(have.get("hands"))
    return bool(have.get("face"))


def _dots(scale: float, radius: float, share: float, seed: int, soft: float = 0.5) -> list:
    """Mask entries: round dots of `radius` (m), one in `share` of the cells of a `scale` (m) jittered lattice."""
    r = radius / scale
    e = [{"cells": {"scale": scale, "mode": "distance", "range": [round(r, 4), round(r * (1 - soft), 4)], "seed": seed}}]
    if share < 1:
        e.append({"cells": {"scale": scale, "mode": "id", "range": [round(1 - share - 0.02, 4), round(1 - share + 0.02, 4)], "seed": seed}})
    return e


def _lines(scale: float, width: float, dir_, factor: float, seed: int, warp: float = 0.0) -> list:
    """Mask entries: wandering lines `scale` (m) apart: the 0.5 contour of a noise stretched along dir (factor > 1:
    lines run along dir; < 1: sheets across it, e.g. horizontal rings with dir up)."""
    nz = {"scale": scale, "octaves": 2, "seed": seed, "stretch": {"dir": list(dir_), "factor": factor},
          **({"warp": warp} if warp else {})}
    w = float(np.clip(width, 0.005, 0.2))
    return [{"noise": {**nz, "range": [0.5 - w, 0.5 - 0.3 * w]}}, {"noise": {**nz, "range": [0.5 + w, 0.5 + 0.3 * w]}}]


def _hex(c) -> list:
    from .paint import colour
    return [round(float(x), 4) for x in colour(c, "skin hair color")]


def _shade(c, k: float) -> list:
    return [round(float(np.clip(x * k, 0, 1)), 4) for x in c]


def hair_default(tone: dict, age: float) -> list:
    """Hair colour when none is given: dark brown, greying from ~45."""
    g = float(np.clip((age - 55) / 30, 0, 1))
    base = np.array([0.13, 0.085, 0.06]) * (1.0 - 0.3 * tone["melanin"])
    return [round(float(x), 4) for x in base + g * (np.array([0.5, 0.5, 0.5]) - base)]


INNER_LIP_COLOR = [0.38, 0.148, 0.11]  # (r29: [0.38, 0.11, 0.11] rendered the band over the smile's upper teeth (175, 101, 103) sRGB, G/R 0.58, magenta beside our vermilion (G/R 0.62); the reference's wet inner lip (jaw open) is the vermilion's own hue, G/R 0.66 vs 0.65, a little lighter: G linear 0.39 x R) linear: the wet inner lip (mucosa): redder and darker than the vermilion, lighter than the bag

INNER_LIP_FADE = 0.3  # the ring outside the contact ring: the wet line fading into the vermilion
MOUTH_DEEP_COLOR = [0.035, 0.008, 0.008]  # linear: the mouth's interior (GNM's sock) a few rings in: dark, a throat
MOUTH_DARK_SIDE = (0.55, 0.8, 0.003, 0.006)  # (r32) the sock also darkens past this share of the mouth's half width (ramp a..b), from this depth behind the lips' front (ramp, m): the side walls in shadow; None = off
MOUTH_DARK_DEPTH = (0.008, 0.012)  # (4-8 mm: dark sock shards at the closed seam, expr_r11) m behind the lips' front: the sock darkens fully over this (by depth, beside the rings)
TONGUE_BACK = (0.04, 0.06)  # (r28: back with JAW_TONGUE off, expr_r23 jaw row worse than r22) (r26: with JAW_TONGUE's bowed dorsum the front sees rest depths 41-62 mm (p5-p95), so 40-60 turned 74% of the visible tongue dark) (r23: 28-50 mm: jawOpen sees the dorsum 36-42 mm back, so it read (122, 58, 58) sRGB with a black band, "tongue missing", expr_r19) (r17: 12-30 mm blacked out the whole visible dorsum, v32) m behind the tongue's tip: its colour darkens to MOUTH_DEEP_COLOR over this (None: off)
TEETH_BACK = (0.009, 0.022, 0.8, [0.1, 0.075, 0.06])  # m behind each row's front (along the mouth's `out`), strength,
# linear colour: the teeth darkened toward the molars (expr_r16 smile: "the teeth run all the way into the mouth corners";
# a real smile's outer teeth fall into the buccal corridor's shadow; flat-coloured teeth stayed lit to the corners)
MOUTH_DEEP_RINGS = 2  # (3 left the sock walls at the corners lit pink in jawOpen: "raw red fleshy shapes", expr_r7) rings of the sock from the lips' rim over which the inner lip red darkens to MOUTH_DEEP_COLOR

FRAME_PAST = 0.0022   # m: the upper lash line's dark frame past the outer canthus (the visible eye's outer end)
CANTHUS_TIP = 0.0012  # m: the inner corner's dark point, on past the caruncle's pocket toward the nose
LOWER_FRAME = 0.8     # the lower lash line's weight against the upper's (was 0.55: weak, the eye read short)
EYE_OCCLUSION = 0.5   # skin.eyes.occlusion default (the lids' shadow on the ball). mouth_eye_bias: at 1 it takes 0.6-0.8 mm of the
#                       detector's eye opening and ~0.5 mm of the fissure against photos; proposed 0.5 (docs/notes/mouth_eye_bias.md)
EYE_KEYS = ("iris", "iris_size", "pupil", "veins", "sclera", "tear", "waterline", "limbal", "limbal_width",
            "iris_contrast", "gloss", "occlusion", "caruncle", "crease", "canthus", "iris_inner", "iris_inner_to")

SHADOW_GAIN = 1.6   # (0.85 before the shadow map carried the under-skin shafts' grain: its mean fell ~1/2)
CAST_DEPTH = 0.6   # the shafts seen through the skin are darker than the old even wash (gate: ref_30 / 29 / 28 beard - cheek)
CAST_SAT = 0.15   # its chroma kept (the rest goes to a neutral grey of the same luminance)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("skin_features_mouth", "skin_features_eyes", "skin_features_marks", "skin_features_hair",
           "skin_features_build")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
