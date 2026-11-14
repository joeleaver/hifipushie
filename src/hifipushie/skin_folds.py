"""Folds: the soft-tissue lines and bulges a face's SHAPE model does not make (GNM's identity space has no eye bags,
no deep nasolabial fold, no crisp lid crease): spec["skin"]["folds"]. Each is a named anatomical feature placed from
the head's own landmarks (a path over the skin in interocular units: FOLDS), with the path's measured placement as
parameters (what skin_read reads off the reference pictures), laid as colour AND relief from ONE unique map on the
head (skin_marks' sphere wrap, as the stubble / freckle / base maps are):

  r  the groove: a soft valley along the path (painted height down + a darker, redder crease line)
  g  the roll beside it: a bulge (painted height up): the bag over a tear trough, the cheek's pad over a nasolabial fold
  b  the fold's own shade: a wider, soft darkening (what the valley's occlusion does to the light)

skin["folds"] = {name: amount | {"amount": 0..1.5, "width": mm (the feature's default), "roll": 0..1.5 (x the
  feature's own roll), "L": {"amount": x (times the fold's), "shift": [mm, ...] (the line moved ACROSS its landmark path,
  at stations evenly spaced along it; + = the feature's `plus` side), "extent": [t0, t1] (the part of the path that
  shows, 0..1)}, "R": {...}}}   (a centre-line fold takes "shift" / "extent" directly)

RELIEF IS GEOMETRY (skinfolds, 2026-10-12; skin["fold_relief"] = "geometry", the default): each fold is a modifier
of the skin part's FIELD (`prims`, sdf kind "tissue"): a profile across the path (RELIEF: a groove, a roll rising
from the groove's line on the plus side: the bag over a tear trough, the cheek's pad over a nasolabial fold, the
hooding over a lid's crease, and for the lid a platform under it) swept along the same landmark path with the same
amount / shift / extent per side, so what skin_read measures drives it. It is in the built surface: every render,
the silhouette, raking light, the export's high-poly (its normal / AO maps; the low-poly as far as its triangles
go). The displacement fades out toward the lid margins and the lip line (KEEP) and can never push the skin onto the
eyeball (BALL). Amount 0 = no primitive: nothing is evaluated, the build key is the fold-free model's. The paths are
seated on the part's field WITHOUT the folds (`field_surface`), in the paint map, the reader and the geometry alike.
skin["fold_relief"] = "paint" keeps the old painted height (bump in the look): it shades like a groove 0.2-0.8 mm
deep seen from the front, never changes the silhouette, and a raking light or a profile view shows a flat cheek.
The map then carries the COLOUR only (the crease line's tint, the soft shade): b.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at skin_folds.NAME: C422). skin_folds_surface: the surfaces folds are laid on: `_Surface`, the head's frame,
the field surface and the map surface, cached. skin_folds_map: A fold in the map: its own crease snapped, its paths,
`fold_map`. skin_folds_geometry: the folds as geometry: the profile, tissue kept and moved, keep lines, `prims`,
expression folds, `build`, `reference`.
"""
from __future__ import annotations

import numpy as np

from .spec import SpecError
from . import moved

VERSION = 12
PX = 0.0001            # m a map pixel at the face
DEPTH = 0.0009         # m: the groove layer's painted depth at map value 1
BULGE = 0.0010         # m: the roll layer's painted height at map value 1
STATION = 0.001        # m between stations along a path (the map's and the reader's)
N_SHIFT = 9            # shift is given at this many stations by default (any number is taken: interpolated)

# name -> path [(anchor joint, offset in interocular units)] on the LEFT side (".L" anchors: mirrored to the right;
# without: one centre-line fold), "plus": the anatomical direction of + shift (a world vector the across direction is
# signed by), width (mm, the valley's full width at half depth), depth (share of DEPTH at amount 1), tint (the crease
# line's darkening at amount 1), shade (the wide soft darkening), roll (bulge: (offset mm toward plus, width mm,
# share of BULGE)) or None, search (mm either side of the path the reader looks), res (mm a picture pixel: coarser
# pictures answer "cannot tell"), about.
FOLDS = {
    # (skinfolds2, nlpath.py on six heads: the old path passed the mouth 10-12 mm outside the cheilion and then DROPPED
    # STRAIGHT DOWN for 10 mm (x constant): 20-24 deg from the vertical as a whole, "too upright, too close to the
    # mouth". A nasolabial fold leaves the alar crease at 30-40 deg from the vertical, passes 12-15 mm outside the
    # cheilion and goes on OUTWARD, ending about level with the lower lip)
    "nasolabial": {"path": [("lm_nostril.L", (0.08, 0.02, 0.03)), ("lm_mouth_corner.L", (0.17, 0.06, 0.13)),
                            ("lm_mouth_corner.L", (0.24, 0.1, -0.1))], "plus": (1, 0, 0.3), "width": 4.5, "depth": 0.8, "snap": 7.0,
                   "tint": 0.35, "shade": 0.2, "roll": (4.5, 5.0, 0.35), "search": 6.0, "res": 1.6,
                   "about": "the fold from the nose's wing past the mouth's corner (the cheek's pad over it)"},
    # (from under the corner's own dimple: a young mouth's corner shadow is not a marionette line)
    # (skinfolds2: it began 8 mm UNDER the corner, a 3 mm groove straight down at 9 deg: on Garrett a short nick, "a
    # scar". The labiomandibular fold begins AT the commissure and runs down and a little out (15-25 deg) toward the
    # jaw's edge, soft and wide, the jowl's pad standing beside it)
    "marionette": {"path": [("lm_mouth_corner.L", (0.05, 0.0, -0.05)), ("lm_mouth_corner.L", (0.085, 0.03, -0.22)),
                            ("lm_mouth_corner.L", (0.15, 0.07, -0.42))],
                   "plus": (1, 0, 0), "width": 6.0, "depth": 0.7, "tint": 0.12, "shade": 0.2, "roll": (6.0, 7.0, 0.3),
                   "search": 5.0, "res": 1.4, "min_extent": 0.65, "read_from": 0.3,   # (its first third lies in the mouth corner's own shadow)
                   "about": "the soft fold from the mouth's corner down and a little out toward the jaw (the jowl's pad beside it)"},
    "commissure": {"path": [("lm_mouth_corner.L", (0.06, 0.01, -0.01)), ("lm_mouth_corner.L", (0.09, 0.03, -0.05)),
                            ("lm_mouth_corner.L", (0.115, 0.05, -0.10))],
                   "plus": (1, 0, 0.5), "width": 5.0, "depth": 0.6, "tint": 0.1, "shade": 0.3, "roll": None,
                   "search": 3.5, "res": 1.0, "read": False,
                   "read_why": "the mouth's own corner and its shadow lie inside this feature's window: on photographs of a smooth young face it read 0.14-0.19 and was laid at the cap",
                   "about": "the depression at the mouth's corner (a soft pit turning the corner down)"},
    "mouth_corner": {"path": [("lm_mouth_corner.L", (0.06, 0.01, 0.0)), ("lm_mouth_corner.L", (0.18, 0.07, -0.03))],
                     "plus": (0, 0, 1), "width": 1.4, "depth": 0.45, "tint": 0.5, "shade": 0.15, "roll": None,
                     "search": 2.5, "res": 0.7, "about": "the crease running out from the mouth's corner"},
    "mentolabial": {"path": [("lm_lip_lower", (-0.3, 0.04, -0.13)), ("lm_lip_lower", (0.0, 0.0, -0.15)),
                             ("lm_lip_lower", (0.3, 0.04, -0.13))], "plus": (0, 0, 1), "width": 4.0, "depth": 0.6,
                    "tint": 0.2, "shade": 0.25, "roll": None, "search": 4.0, "res": 1.6,
                    "about": "the groove between the lower lip and the chin"},
    # (the orbit's lower rim: from under the inner corner down, and UP again toward the outer corner: with three
    # points running on down and out the bag over it was a box with a cut end, not a crescent)
    # (the lid-cheek junction lies ~10 mm under the lid's margin: at 0.215 x the pupils' distance, 13 mm, Garrett's
    # painted troughs sat at the upper end of the reader's window and were read along 15-31 % of the path)
    "tear_trough": {"path": [("lm_eye_inner.L", (0.03, 0.0, -0.08)), ("lm_lid_lower_in.L", (0.0, 0.0, -0.15)),
                             ("lm_lid_lower.L", (0.02, 0.0, -0.175)), ("lm_lid_lower_out.L", (0.05, 0.0, -0.15)),
                             ("lm_eye_outer.L", (0.05, 0.0, -0.09))], "plus": (0, 0, 1), "width": 3.5, "depth": 0.7,
                    "tint": 0.25, "shade": 0.25, "roll": (4.0, 4.0, 0.8), "search": 5.0, "res": 1.6,
                    "about": "the groove under the lower lid; its roll is the eye bag over it"},
    # (along the upper margin's own landmarks, a crease height over each: with three points the ends cut across the
    # opening's corners and were seated inside the socket)
    "lid_fold": {"path": [("lm_eye_inner.L", (0.035, 0.0, 0.045)), ("lm_lid_upper_in.L", (0.0, 0.0, 0.058)),
                          ("lm_lid_upper.L", (0.0, 0.0, 0.062)), ("lm_lid_upper_out.L", (0.0, 0.0, 0.058)),
                          ("lm_eye_outer.L", (0.025, 0.0, 0.04))], "plus": (0, 0, 1), "width": 1.2, "depth": 0.3,
                 "tint": 1.3, "shade": 0.5, "roll": None, "search": 2.0, "flank": 1.0, "res": 0.5, "smooth": 4.0,
                 "about": "the upper eyelid's crease line (the fold GNM's lids only hint at)"},
    # (Joe on Garrett, 2026-10-12: a NOTCHED chin: a shallow midline dip in the chin's lower front with a soft lobe each
    # side. GNM's identity does not make it unforced. A centre-line groove whose roll stands on BOTH sides)
    "chin_notch": {"path": [("lm_chin", (0.0, 0.0, 0.2)), ("lm_chin", (0.0, 0.0, 0.1)), ("lm_chin", (0.0, 0.0, 0.0))],
                   "plus": (1, 0, 0), "width": 5.0, "depth": 0.7, "tint": 0.1, "shade": 0.25, "roll": (5.0, 5.0, 0.4), "search": 4.0,
                   "res": 1.0, "read": False,
                   "read_why": "no detector yet: under a frontal light a chin's midline dip is its own shading, and a beard hides it",
                   "about": "the chin's midline notch / cleft with a soft lobe each side (roll = the lobes' height)"},
    "glabella": {"path": [("lm_brow_inner.L", (-0.035, -0.01, 0.1)), ("lm_brow_inner.L", (-0.015, -0.01, -0.08))],
                 "plus": (1, 0, 0), "width": 1.4, "depth": 0.6, "tint": 0.5, "shade": 0.15, "roll": None, "search": 3.0,
                 "res": 0.7, "about": "the vertical frown lines between the brows"},
}
# The folds' RELIEF as geometry, mm at amount 1 (x the side's amount along the path; "roll" x the fold's `roll`):
#   depth   the groove's depth (its width is the fold's `width`, full width at half depth)
#   roll    (peak offset toward plus, sigma, height, shoulder): the bulge beside the groove, rising from the groove's
#           own line over `shoulder` (a symmetric bump there half filled the groove: lidfold's finding)
#   plat    (depth, height): the skin on the minus side a little in over `height` (a lid's pretarsal platform)
#   reach   how far along the normal the move is felt (it never reaches through a lid or into a nostril)
RELIEF = {
    # (nasolabial 0.6 deep at 3.5 mm wide and marionette 0.5 read, on Garrett at amounts 0.9-1.5, as incised lines with
    # a pit where each began beside the mouth: a nasolabial fold is mostly the cheek's pad standing over the lip)
    "nasolabial": {"depth": 0.4, "roll": (5.0, 3.4, 1.3, 3.0), "reach": 4.0},
    # (roll 0.8 over a 4 mm shoulder drew a second crease parallel to the nasolabial fold: "claw marks")
    "marionette": {"depth": 0.3, "roll": (7.0, 5.0, 0.5, 6.5), "reach": 5.0},
    "commissure": {"depth": 0.45, "reach": 3.0},
    "mouth_corner": {"depth": 0.3, "reach": 3.0},
    "mentolabial": {"depth": 0.8, "reach": 4.0},
    "tear_trough": {"depth": 0.6, "roll": (4.6, 2.4, 1.4, 2.6), "reach": 4.0},
    # over: (peak offset mm, sigma mm, shoulder mm): where the groove cannot go in (the eyeball under a thin lid), the
    # depth it lacks stands OUT as a tight ridge just over the line instead: the fold's own lip (skinfolds2: the hard
    # stop at the ball broke Tess's crease mid-lid, where the lid lies thinnest)
    # (broad and low: a tight lip, 0.85 mm within a millimetre, was a PALE RAISED WELT under a frontal light: a lit
    # ridge where hers is a shadowed groove with no ridge over it. Now 60 % of the missing depth over 2-5 mm)
    "lid_fold": {"depth": 0.85, "roll": (2.3, 2.6, 0.6, 2.6), "plat": (0.15, 2.5), "over": (2.2, 2.8, 1.8, 0.6), "reach": 3.0},
    "glabella": {"depth": 0.35, "reach": 3.0},
    "chin_notch": {"depth": 0.9, "roll": (5.5, 3.5, 0.6, 4.0), "sym": True, "reach": 5.0},
}
END = 0.007               # m: a fold's relief comes in from nothing over this length at each end of its extent
# With the relief in the surface, what a tight crease still lacks in a rasterised render is its own OCCLUSION (skin
# lying on skin: no light gets in; EEVEE has none at 0.5 mm): the crease line's share of a dark multiply layer
# (folds_crease), 0.6 x the groove's width. Without it a lid's crease at amount 1 was a faint line (foldval's truth
# pictures: read_lid darkness 0.05-0.13, a photograph's fold line reads 0.15-0.4).
OCCLUSION = {"chin_notch": 0.0, "lid_fold": 1.1, "nasolabial": 0.35, "marionette": 0.08, "mouth_corner": 0.4, "glabella": 0.45, "mentolabial": 0.0,
             "tear_trough": 0.0, "commissure": 0.15}
# the crease line's occlusion is this wide (x the groove's sigma; a lid's 0.3 mm line at 0.6 was under a pixel of a
# 0.25 mm picture and read 0.05 dark where a photographed fold line, ~1 mm of skin lying on skin, reads 0.3)
OCC_WIDTH = {"lid_fold": 1.15}
HOOD_DROP = 1.7           # mm: at hood 1 the lid fold's line comes this much down toward the lashes at its outer end
HOOD_ROLL = 1.6           # ... and its roll stands this much higher there (x 1 + HOOD_ROLL x hood)
HOOD_KEEP = 0.3           # ... and reaches this much nearer the lid's margin (the keep-out x 1 - HOOD_KEEP x hood)
KEEP = (0.0012, 0.0032)   # m: no displacement within KEEP[0] of a lid margin or the lips, all of it from KEEP[1]
BALL = 0.0004             # m: the skin a fold pushes in stays this far outside the eyeball
STEP = 0.0005             # m between the geometry's samples along a path
KEYS = {"amount", "width", "roll", "depth", "hood", "L", "R", "shift", "extent"}
SIDE_KEYS = {"amount", "shift", "extent"}


def sided(name: str) -> bool:
    return any(a.endswith(".L") for a, _ in FOLDS[name]["path"])


def options(folds: dict | None) -> dict:
    """skin["folds"] validated: {name: {"amount", "width", "roll", "sides": {"L" | "R" | "": {"amount", "shift",
    "extent"}}}} (folds with amount 0 left out)."""
    out = {}
    if not folds:
        return out
    if not isinstance(folds, dict) or set(folds) - set(FOLDS):
        raise SpecError(f"skin folds: {{name: amount | {{...}}}} over {', '.join(FOLDS)}")
    for name, v in folds.items():
        v = {"amount": float(v)} if isinstance(v, (int, float)) else dict(v or {})
        if set(v) - KEYS:
            raise SpecError(f"skin folds.{name}: unknown keys {sorted(set(v) - KEYS)} (have {', '.join(sorted(KEYS))})")
        a = float(v.get("amount", 1.0))
        if not 0 <= a <= 1.5:
            raise SpecError(f"skin folds.{name}: amount is 0..1.5")
        if a <= 0:
            continue
        sides = {}
        for s in ((".L", ".R") if sided(name) else ("",)):
            q = v.get(s[1:]) if s else {k: v[k] for k in ("shift", "extent") if k in v}
            q = dict(q or {})
            if set(q) - SIDE_KEYS:
                raise SpecError(f"skin folds.{name}: a side takes amount, shift, extent")
            ext = [float(x) for x in q.get("extent", (0.0, 1.0))]
            if len(ext) != 2 or not 0 <= ext[0] < ext[1] <= 1:
                raise SpecError(f"skin folds.{name}: extent is [t0, t1] within 0..1")
            sides[s] = {"amount": float(np.clip(q.get("amount", 1.0), 0, 3)), "shift": [float(x) for x in q.get("shift", [])], "extent": ext}
        if not 0 <= float(v.get("roll", 1.0)) <= 3 or not 0 <= float(v.get("depth", 1.0)) <= 3:
            raise SpecError(f"skin folds.{name}: roll and depth are 0..3 (x the feature's own)")
        hood = float(v.get("hood", 0.0))
        if not 0 <= hood <= 1.5 or (hood and name != "lid_fold"):
            raise SpecError(f"skin folds.{name}: hood is 0..1.5, on lid_fold only (the roll's skin hanging toward the lashes at the outer end)")
        out[name] = {"amount": a, "width": float(v.get("width", FOLDS[name]["width"])), "roll": float(v.get("roll", 1.0)),
                     "depth": float(v.get("depth", 1.0)), "sides": sides, **({"hood": hood} if hood else {})}
    return out


def geometry_key(skin: dict) -> dict | None:
    """What of spec["skin"] shapes the surface (spec.geometry keeps it as spec["tissue"]): the folds that have an
    amount, unless the relief is painted. None: nothing (the fold-free model's build key)."""
    if (skin or {}).get("fold_relief", "geometry") != "geometry":
        return None
    try:
        cfg = options(skin.get("folds"))
    except (SpecError, TypeError, ValueError):
        return None        # (said by skin_params.params where the skin is validated)
    cfg = {k: v for k, v in cfg.items() if any(q["amount"] > 0 for q in v["sides"].values())}
    return {"folds": cfg, "part": skin.get("part", "body"), "v": VERSION} if cfg else None


_SURF: dict = {}
_MAPSURF: dict = {}

SNAP_CURV = 0.035      # 1 / mm: the surface's own crease across a path is at least this concave (a 30 mm radius)
SNAP_SHARE = 0.4       # ... along this share of the path, or there is no crease of the head's own to follow

_SNAP: dict = {}

_KEEP_TREES: dict = {}

# FOLDS UNDER EXPRESSION (skinfolds2; Joe: "if it's additive to gnm, it won't play nice"). A fold laid in the neutral
# rides a face shape rigidly: the lid's crease would sit across a CLOSED lid, where a real one unfolds as the skin
# stretches over the globe; a nasolabial fold deepens on a smile. So each fold has a GAIN per ARKit shape (x its
# neutral amount at that shape's full weight; a shape's "Left" / "Right" acts on that side's fold, one without a side
# on both), and the exported morph target carries the difference: (gain - 1) x the fold's own displacement at each
# low-poly vertex, along the skin's normal. First step: geometry only. What a GLB can carry per target: POSITION and
# NORMAL deltas (vertex normals). The fold's NORMAL MAP and its painted line are one texture for all shapes: fading
# them with a shape needs a wrinkle-map blend on the engine side (a mask per fold region x the shape's weight): not
# in glTF core; noted for the engine. Gains are first guesses from anatomy, to be tuned on renders.
EXPRESSION = {
    "lid_fold": {"eyeBlink": 0.0, "eyeWide": 1.3, "eyeSquint": 0.5, "browDown": 1.2},
    "tear_trough": {"eyeSquint": 1.4, "cheekSquint": 1.4, "mouthSmile": 1.2, "eyeWide": 0.8},
    "nasolabial": {"mouthSmile": 1.5, "cheekSquint": 1.2, "noseSneer": 1.3, "jawOpen": 0.8, "mouthPucker": 0.6},
    "marionette": {"jawOpen": 0.6, "mouthFrown": 1.4, "mouthSmile": 0.5},
    "commissure": {"mouthSmile": 0.4, "mouthFrown": 1.3, "jawOpen": 0.7},
    "mouth_corner": {"mouthSmile": 1.4, "jawOpen": 0.6},
    "mentolabial": {"jawOpen": 0.7, "mouthShrugLower": 1.4, "mouthPucker": 1.2},
    "glabella": {"browDown": 1.6, "browInnerUp": 0.3},
    "chin_notch": {"mouthShrugLower": 0.6},
}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("skin_folds_surface", "skin_folds_map", "skin_folds_geometry")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
