"""Caves as skeletons (like a creature's joints and bones): named nodes (entrances and chambers) joined by passages,
subtracted from the rock of the 3D terrain field (terrain_mesh). A cave's `kind` sets how it's built:

- "sea": carved by waves at the cliff foot. Floors at or just under the sea (the water runs in), wide low passages
  with flat floors, domed chambers. Entrances where the passage meets a cliff.
- "karst": dissolved along the rock's bedding. Keyhole passages (a round tube along a bedding plane with a slot cut
  down below it by the stream), floors that follow the beds and step between them, tall halls. Entrances are
  sinkholes (a shaft from the surface) or a hillside mouth.
- "lava": a tube left by a lava flow, a few metres under the ground it follows. Wide, round-roofed, flat floored;
  skylights where the roof fell in.

Spec (lengths in the terrain's units; "at" is any terrain address):
  "caves": {"name": {"kind": "sea" | "karst" | "lava", "width"?: m, "height"?: m,
      "entrances": {"door": {"at": address, "shaft"?: true}},
      "chambers": {"hall": {"at": address, "depth"?: m below the ground | "z"?: floor height, "size"?: m | [rx, rz]}},
      "passages": [["door", "hall"], {"from": "hall", "to": "top", "via"?: [[x, y], ...], "width"?, "height"?}]}}

Every node's floor is resolved first (entrances where the cave meets the open, chambers by depth or height), then
passages run floor to floor. `check(T, caves, field)` walks a person through every passage with the capsule rule of
measure.clearance (1.8 m tall, 0.25 m radius) and reports floor, headroom, width, steps and water.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at terrain_caves.NAME: C422). terrain_caves_build: building caves: `build`, one cave's passage, its flow
profile, switchbacks. terrain_caves_walk: walking through: `check` on the built tiles. terrain_caves_early: the early
check (set_terrain / check_terrain): the collision floor and steps, light, the survey, the fixes it names.
"""
from __future__ import annotations

import numpy as np
from . import moved

KINDS = {
    "sea": {"width": 6.0, "height": 4.5, "chamber": 8.0, "depth": None, "rough": 0.4},
    "karst": {"width": 4.0, "height": 4.5, "chamber": 9.0, "depth": 18.0, "rough": 0.12, "doline": 18.0, "relief": 0.0,
              "rough_scale": 6.0},
    "lava": {"width": 7.0, "height": 4.5, "chamber": 9.0, "depth": 7.5, "rough": 0.25},
}


class Cave:
    def __init__(self, name, kind, nodes, edges, tubes, notes, dolines=()):
        self.name, self.kind, self.nodes, self.edges, self.tubes, self.notes = name, kind, nodes, edges, tubes, notes
        self.dolines = list(dolines)  # ground edits (terrain_relief.dig_doline)


SWING = 30.0  # m: how far a walkable lava tube's switchbacks reach either side of its flow's line

# ---------------------------------------------------------------- the early check (set_terrain / check_terrain)
GRADE_WALK = 0.25  # the steepest a cave floor stays a walk (sustained, over GRADE_RUN m): ~14 deg
GRADE_RUN = 10.0
ROOF_MIN = 1.0  # m of rock over a passage's roof away from its entrances (less: it opens to the sky)
BED_SPREAD = 12.0  # m (Gaussian sigma) over which a karst floor's climb onto its beds is spread
MOUTH_EASE = 20.0  # m from a hillside mouth over which a karst floor takes on its bedding planes' wander
MOUTH = 15.0  # m from an entrance where the roof may thin out (a mouth daylights by design)


STEP_PROBE = 0.9  # m over the walk's floor where a collision floor is looked for (a knee: a step up still counts)
RISER_STEP = 0.1  # m between samples of the collision floor for risers
RISER_DEG = 45.0  # a floor steeper than this is a riser (a character controller's wall unless it steps up)


def _line_length(L) -> float:
    n = (getattr(L, "props", None) or {}).get("length")
    if n:
        return float(n)
    return float(np.linalg.norm(np.diff(np.asarray(L.xy, float), axis=0), axis=1).sum())


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_caves_build", "terrain_caves_walk", "terrain_caves_early")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
