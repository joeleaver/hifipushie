"""Swept-back tied hair as a groomer builds it (2026-10-11, "tesshair3"; Joe on the row / curtain construction: "flat
across her head instead of swept back and hanging down. This is a super common hairstyle, so we need to be able to get
it right and repeat/riff on it").

What groomers do (Autodesk's XGen forum on ponytails: one description for the pulled-back head hair, another for the
long hair that leaves the tie, guides rooted on the scalp and run to the tie, a clump scale that draws them into it;
SideFX's forum on long hair: guides laid in layers from the bottom up, upper layers over lower; Vellum practice: a
couple of hundred guides hung under gravity with a bend stiffness and collisions, strands generated from them
afterwards; Polycount on strays: their own description, one hair a guide) is what this module does:

  gather(): a FLOW FIELD over the scalp. Roots all over the scalp inside the hairline (blue noise + a row on the
      hairline), each traced along the head toward the tie: at every step the direction is "toward the tie along the
      surface" + "away from the parting" (where there is one) + "down the head" by looseness (sag). The way never
      leaves the hair (it stays above the hairline: over the ears, not across the temples' skin) unless `overhang` /
      `ears` let it. Height: the hair lifts off the scalp at its root (root_lift), stands off the head most halfway
      (puff), and hair rooted further from the tie lies over hair rooted nearer (body).
  tail(): every lock of the tail leaves the tie inside a cone round the tie's direction and FALLS: its direction
      turns to gravity as fast as `stiff` lets it, it lies on the neck / shoulder / back (the body's collider), and
      the bundle is scaled to `fullness` afterwards. No axis the locks are arranged round: a bundle of hanging locks.
  escaped(): pieces that never reached the tie: each a handful of single hairs that share one fall beside the face
      (or down the nape) and fray apart toward their ends.
  style(): THE STYLE. A small set of words and 0..1 numbers (`groom.tied`) -> the tie, parting, strand dials:
      a ponytail one can repeat on any head and riff on.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at hair_flow.NAME: C422). hair_flow_gather: the gather: roots, paths over the head, and `gather`.
hair_flow_tail: the tail and escaped pieces. hair_flow_wisps: wisps, curls and the halo. hair_flow_style: the style:
its parameters and `style`.
"""
from __future__ import annotations

import numpy as np
from . import moved

X = np.array([1.0, 0.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])
STEP_DEG = 5.0


def _wrap(az):
    return ((np.asarray(az, float) + 180.0) % 360.0) - 180.0


# ------------------------------------------------------------------------------------------------ the style
HEIGHTS = {"nape": -25.0, "low": -6.0, "mid": 15.0, "high": 40.0, "top": 65.0}
SIDES = {"centre": 0.0, "center": 0.0, "left": 30.0, "right": -30.0}
TIED = {
    "tie": "low",         # where the tie sits: nape | low | mid | high | top, or degrees of elevation from the head centre
    "side": "centre",     # centre | left | right (the person's own), or degrees round from the back's middle (+ = left)
    "tightness": 0.5,     # 0 = loose (hair sags between root and tie, stands off the head, hangs over the hairline)
                          # .. 1 = scraped back tight and flat
    "lift": None,         # 0..1: volume at the roots and over the top (default: 1 - tightness)
    "volume": None,       # (tesshair7) the hair's BODY over the head: 0 = a cap lying on the skull .. 1 = big loose hair.
                          # The hair stands up out of its root (and out of the parting, on both banks) and bends
                          # over, arcs out and down the side before the tie takes it back, in layers. A number, or
                          # {"amount": 0..1, "crown" / "sides" / "nape": x the amount there (default 1 / 1 / 1),
                          # "root": 0..1 (how steeply it stands at the root: 0 = eases off the scalp over ~4 cm,
                          # 1 = stands straight up and bends within ~1 cm), "arc": 0..1 (how far the way falls
                          # sideways / down from the root before it turns to the tie), "layers": 0..1 (0 = one shell,
                          # 1 = locks at every height from the scalp up: a thick mass), "hold": 0..1 (0 = drawn in
                          # to the tie from halfway, 1 = full until just before it; default 1 - tightness)};
                          # default: `lift`
    "part": "centre",     # centre | left | right | none (none = combed straight back)
    "ears": "tucked",     # tucked (the hair passes over the ears' tops, behind them) | covered (it hangs over them)
    "tail": {},           # {"kind": "tail" | "bun" | "plait" | "none", "length": m, "fullness": 0..1, "wave": 0..1,
                          #  "to": "back" | "shoulder"}
    "wisps": None,        # the short soft hair that never reached the tie, as small clumps of fine hairs that fall
                          # along the face: an amount 0..1, or {"amount": 0..1, "where": ["part", "front", "temple",
                          # "sideburn", "nape"], "length": [m, m], "softness": 0..1 (0 = small defined locks, 1 = wide
                          # and frizzy)}; default by neatness (none on a neat head)
    "escaped": None,      # single stray HAIRS (wires alone: wisps are the soft ones): a count a side, or {"count":
                          # n | [right, left], "where": ["part", "temple", "ear", "nape"], "length": [m, m]}; default 0
    "front": None,        # the FRONT on its own (tesshair6): 0..1 or {"looseness": 0..1 (the hair in front of the ears
                          # sags and stands off the head as if the style were that much looser there; the back stays
                          # as tight as `tightness`), "drape": 0..1 (how far it hangs over the forehead's corners and
                          # temples), "locks": n a side (thick loosened locks that swoop from beside the part across
                          # the forehead's corner and tuck back over the temple; default round(3 x looseness))}
    "hairline": None,     # 0..1: how SOFT the hair's edge is: 0 = a clean hard line (gelled, a wig's edge) .. 1 = the
                          # hairline thins out over a cm, with baby hairs along it and a part that wanders; default
                          # 0.8 - 0.3 x neatness (every real hairline is soft; only its amount is style)
    "neatness": 0.5,      # 0 = slept in (strays, a halo, uneven) .. 1 = every hair in place
    "half": False,        # true = half up: only the top section is tied, the rest hangs loose (`length` m of it)
    "length": 0.3,        # m: the loose hair's length for half up
    "detail": None,       # {"tie": {...}, "strands": {...}}: overrides of what the style makes (hair_tied's own keys)
}
VOLUME = {"amount": 0.0, "crown": 1.0, "sides": 1.0, "nape": 1.0, "root": 0.6, "arc": None, "layers": None, "hold": None,
          "locks": None, "cross": None}
VOLUME_M = (0.034, 0.03, 0.014)  # m the top layer stands off the scalp at volume 1: crown, sides, nape
TAIL = {"kind": "tail", "length": 0.25, "fullness": 0.5, "wave": 0.3, "to": "back", "tousle": None}
# tousle 0 = brushed (locks apart, an even end, nothing leaves the outline) .. 1 = tousled (a ragged end, stray hairs
# all round, strands crossing); default 0.05 + 0.75 x wave
# fullness 0 = a sleek thin tail .. 1 = bushy (the bundle's radius 1.8 .. 6 cm, more locks, more air and frizz);
# wave 0 = straight .. 1 = loose waves (every lock its own, 1.6 cm of swing at 1)
WISP_STYLE = {"amount": 0.5, "where": ["part", "front", "temple", "sideburn"], "length": [0.04, 0.12], "softness": 0.6,
              "loose": None, "curls": None, "halo": None}  # curls: fine separate CURLED locks a side that escape at the forehead's
# corners, the temples and in front of the ears (hair_flow_wisps.curls); default round(9 x amount)  # loose: THICK loose locks a side (forehead corner / temple); default round(2.5 x amount)
# the strand dials a tied style starts from (spec["hair"]["strands"] wins)
STRANDS = {"count": 70000, "thickness": 0.7, "flat": 1.4, "clump_size": 0.004, "stray": 0.8, "roots": 1.0, "under": 1.6,
           "under_length": 0.025, "soft": 0.022, "tips": 0.6, "tip_spread": 0.6, "wavelength": 0.12}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("hair_flow_gather", "hair_flow_tail", "hair_flow_wisps", "hair_flow_style")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
