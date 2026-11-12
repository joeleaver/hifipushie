"""Repetition: prefabs placed as instances, and arrays of elements. Both expand into ordinary joints, bones and
blobs before kits and mirroring, so everything downstream (strokes, paint, parts, export) sees plain elements.

  "prefabs":   {name: {"joints": {...}, "bones": {...}, "blobs": {...}, "symmetry": false}}
               a reusable piece in its own local frame (metres, its origin where it's placed; e.g. a chair
               with its origin on the floor under the seat centre, facing -Y). "symmetry": true mirrors its
               own ".L" elements across its local X first.
  "instances": {name: {"use": prefab, "at": [x, y, z], "rot": [deg x, y, z] (0), "scale": s (1),
                       "part": name | {prefab part: part} (keep the prefab's), "tags": [...],
                       "on": element | tag | instance | [names], "lift": m}}
               a placed copy. Its elements are named "<instance>/<element>" and tagged with the instance
               and prefab names, so paint "near", "targets" and deletes can take "chair1" or "chair" for all
               of them. An instance named ".L" is mirrored whole (a pair of bedside tables).
               "on": set the instance down on those elements' top surface at its x, y (its z is ignored; "lift"
               raises it): a cup "on": "table1/top", a jar on "shelf#1", books on "bookshelf1/shelf#2" (an
               element's name means that element: "shelf" is an array's first copy; a tag, all it tags). Found
               after everything else is placed (on instances too, in order), and again whenever the support
               moves, so props stay put on furniture that's moved or resized. Prefab origins go on the floor.
  "array" on a bone or blob: {"count": n, "offset": [dx, dy, dz] (per copy), "rot": [deg] (per copy, about
               "pivot", default the element's own centre), "jitter": {"offset": [jx, jy, jz], "rot": [deg],
               "size": fraction}, "seed": 0}, or a list of those for a grid (each applied to all copies so far).
               Per copy, "vary": {key: [lo, hi]} draws any numeric field (lists per component) from a range:
               {"r_a": [0.13, 0.17], "r_b": [0.10, 0.13], "bow": [[-0.02, -0.01], [0.02, 0.01]]}; "flip":
               "alternate" | "random" turns a bone end for end (butt ends alternating course by course).
               Copy 0 keeps the element's name; the others are "<name>#<i>" (".L" stays at the end); all are
               tagged with the element's name. Logs, planks, shingles, fence posts, a ring of stones.

"weather": [{"tags": [...], "jitter": {"offset": m | [x, y, z], "rot": deg | [x, y, z], "size": fraction},
              "settle": m (sinks up to that much), "lean": deg | [x, y] (tilts), "sag": m (bones bow down in the
              middle), "lumpy": {...}, "chips": {...}, "seed"}, ...]
             time and use applied to everything carrying those tags (or names). Instances (by instance, prefab or
             instance tag) move as a whole: a chair pushed askew, a table sunk into a soft floor. Write one
             entry per event in the story ("the porch settled", "the ridge beam sags", "the chairs get pushed
             around"). Deterministic per seed.

"walls": {name: {"path": [[x, y], ...], "height": m (2.4), "thickness": m (0.1), "base": z (0), "style": "boards"
             (vertical boards, "board": width 0.15, each a little different) | "solid", "part", "tags", "lumpy",
             "openings": [{"at": metres along the path | [x, y] (the nearest point of the path), "width" (0.9),
             "height" (2.0 for doors), "sill" (0: a doorway; 0.9 for a window), "name", "frame": prefab (origin
             at the bottom centre of the opening, facing -Y), "window": prefab (origin at the opening's centre),
             "door": prefab (hinge at its origin, the leaf along local +X), "hinge": "left" | "right" (the end
             nearer the path's start or its end), "swing": "left" | "right" (the side of the wall it opens to,
             walking along the path), "open": deg (0 closed)}]}}
             a partition or plain wall in one entry: boards (or a box) along each straight run, a box cut per
             opening targeted at this wall only, and the frame, window and door placed and turned to fit. The
             pieces are ordinary elements and instances ("<wall>_<opening>_door", tagged with the wall and the
             opening) and check walks a person through every door opening. Log walls stay arrays of bones with
             their own cuts.
"between" on a bone: {"between": array, "depth": m, "inset": m, "part", "tags", "lumpy"} fills the seam between
             neighbouring copies of a bone array (course above course): one flat bone per pair along their
             mid-line, bowed as they are and as tall as their gap, `depth` either side of it (default 3/4 of their
             radius: recessed). Chinking between logs, mortar between rails. "inset" stops it short of the ends.

"tags": [...] on any bone or blob groups elements under names of your choice ("logs", "furniture"). Anywhere a
list of element names is taken (paint "near", a cut's "targets", delete with "tag") a tag stands for its members.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at assemble.NAME: C422). assemble_shapes: shapes: walls and their openings, a style's shape, deformed blobs.
assemble_arrays: prefabs and arrays: placing a prefab's instance, arrays between and along, steps. assemble_place:
placing on things: footprints, scatter, heights, clearance, supports, the top of what is below. assemble_weather:
weather on instances and elements. assemble_expand: `expand`: a spec's prefabs, instances, arrays, walls and scatter
made into its own blobs; placements.
"""
from __future__ import annotations

import math

import numpy as np
from . import moved

def _euler_of(R: np.ndarray) -> list[float]:
    """XYZ euler angles (deg) of a rotation matrix, as euler_matrix builds them (Rz @ Ry @ Rx)."""
    sy = -R[2, 0]
    if abs(sy) < 0.999999:
        ry = math.asin(sy)
        rx = math.atan2(R[2, 1], R[2, 2])
        rz = math.atan2(R[1, 0], R[0, 0])
    else:  # gimbal lock
        ry = math.copysign(math.pi / 2, sy)
        rx = math.atan2(-R[1, 2], R[1, 1])
        rz = 0.0
    return [round(math.degrees(a), 6) for a in (rx, ry, rz)]


def _r(v) -> list[float]:
    return [round(float(x), 7) for x in v]


_CACHE: dict[str, dict] = {}
_ON: dict[str, dict] = {}  # expand's content key -> {instance: its resolved "at"} for instances placed "on"
_SCATTERED: dict[str, dict] = {}  # expand's content key -> the instances spec["scatter"] generated
NOTES: dict[str, list] = {}  # expand's content key -> things worth telling (scatter that didn't all fit)

WALL_KEYS = {"path", "height", "thickness", "base", "style", "board", "part", "tags", "openings", "lumpy", "round",
             "seed", "blend", "chips"}
OPENING_KEYS = {"at", "width", "height", "sill", "door", "hinge", "open", "swing", "frame", "window", "part", "name"}

STYLE_SHAPE = ("round", "lumpy", "chips", "blend", "bow", "chunk", "deform")

SCATTER_KEYS = {"use", "on", "count", "area", "spacing", "rot", "scale", "seed", "tags", "part"}


# ---- selection -------------------------------------------------------------------------------------------------
def select(s: dict, names, kinds=("bones", "blobs")) -> list[str]:
    """Element names for a list of names: each an element, or a tag (instances, arrays and "tags"), in `s`
    (an expanded spec). Unknown names are returned as they are, for the caller to report."""
    out = []
    for n in ([names] if isinstance(names, str) else names):
        # an array's first copy keeps the array's name, which is also the tag of every copy: take both
        hits = [e for k in kinds for e, el in s.get(k, {}).items() if e == n or n in (el.get("tags") or [])]
        out += hits if hits else [n]
    return list(dict.fromkeys(out))


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("assemble_shapes", "assemble_arrays", "assemble_place", "assemble_weather", "assemble_expand")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
