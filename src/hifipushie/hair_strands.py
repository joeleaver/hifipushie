"""Hair as strands: the groom on Blender's own hair system (Hair Curves + the Essentials hair node groups).

`spec["hair"]["style"] = "strands"`. The spec's locks stay what a model reasons in (a spine with a width, a thickness
and a shape along it); here they become GUIDES:

  locks on the head / locks that leave it   one guide curve a lock, carrying the lock's section per point. Children
        are spread across that section (a lens: `blender_strands.lens_group`), so a lock is a flat clump of strands,
        not a rope round its guide.
  the scalp layer   short flow guides all over the scalp inside the hairline (their direction read off the locks
        above them), children by Blender's "Interpolate Hair Curves" on the scalp mesh's UV map, density from the
        hairline's fade and the parting. It is the hair's root: the soft hairline, the baby hairs, the cover under
        the locks (what the dark underlayer shell was for solid locks).

`spec["hair"]["strands"]` holds the groom numbers (hair_cards.STRANDS). They are 0..1 dials mapped here onto the
ranges that work (`physical`): the spike behind this found frizz of 0.2-0.4 mm right and 2-4 mm a cloud, and clumping
every strand of a lock to its guide a rope, so the dials can't reach those. Everything Blender needs is `job`: the
scalp mesh, the guide files and each object's modifier stack with its numbers, so the mapping is testable without
Blender and a person sees ordinary Essentials modifiers.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at hair_strands.NAME: C422). hair_strands_guides: guides: a lock's guides, the scalp and collision meshes,
zones, the scalp's UVs, the under guides. hair_strands_job: the strands job: modifier stacks, `job`, the npz hash and
the key. hair_strands_eval: evaluated strands: evaluate and its cache, strands of a model, the tile job and lines, the
cap chart.
"""
from __future__ import annotations

import numpy as np
from . import moved

LENS = "hp_lens"
STRAND_RADIUS = 0.00004  # m: a real hair (0.03-0.05 mm), at REAL_COUNT strands; fewer strands are drawn wider so
REAL_COUNT = 100000  # the head stays covered (a path tracer draws true widths: 30k hairs at 0.08 mm were a pale haze)
UNDER_PER_M2 = 3.6e5  # scalp-layer strands per m2 of scalp at under = 1 and 30k strands
SEED_SPACING = 0.011  # m between the scalp layer's flow guides
# Cycles' hair BSDF vs the look colour: a lit mass of strands renders = A x colour^p per linear channel (multiple
# scattering lightens it: measured on a short grey-brown cut, 7 colours black .. blond under the salon lights:
# 0.646 x c^0.307, Garrett's #55504b 3.5-4x too light). The look colour goes through the inverse (blender_strands.
# material); A 0.75 instead of the fitted 0.646 because a colourless floor (~0.09 linear: the white specular lobe and
# the sky) is in every measure and can't be inverted. After: grey / blond within 5%, #55504b x1.35-1.45 (EEVEE's own
# strand material: x1.6-1.8), near-blacks stay at the floor. look.cycles_fit overrides ([1, 1] = off).
# Applied to the colour's luminance with the hue kept (per channel the 1/p power tripled every channel ratio).
CYCLES_FIT = (0.75, 0.307)
# what each 0..1 dial may reach (the top of each range is where it still reads as hair)
import os as _os
SAFE = {
    "sub_wave": float(_os.environ.get("HS_SUB_WAVE", 0.25)),  # a sub clump's own swing, x the lock's wave
    "frizz_m": 0.0006,  # single strands off their neighbours: 0.2-0.4 mm reads as hair, 2 mm+ as a cloud
    "loose_m": 0.006,  # strands wandering TOGETHER (low frequency): loosens a lock without fuzzing it
    "clump": 0.9,  # how far a strand is drawn to its sub clump's line at clump = 1 (never to the lock's one line)
    "wander_m": 0.0025,  # a single strand's own slow wander off its clump
    "flyaway": 0.12,  # share of a lock's strands that let go of it
    "flyaway_m": 0.02,  # how far a fly-away gets at its tip (x 2 on hair that leaves the head)
    "tips": 0.55,  # share of its length the shortest strand of a lock loses
    "roots": 0.12,  # share of a lock's length over which its strands' starts are staggered
    "curl_m": 0.006,  # radius of the ringlet a strand winds round its clump at curl = 1
    "halo": 0.10,  # share of the strands that are short broken hairs standing off the hair at halo = 1
    "halo_m": 0.012,  # m such a hair stands off its lock at its end (x 0.3..1.3 per hair)
    "halo_len": 0.05,  # m it runs (x 0.4..1.4)
}
WISPS = "hair_guides_wisp"  # the object of the locks of single hairs (lock["hairs"] = n)
WISP_RADIUS = 0.8  # x the strand radius for single hairs (alone against skin a strand reads thicker than in a mass)
EDGE_RAMP = 0.008  # m over which a LOOSE lock's strand count ramps up to full (rule 15) ...
EDGE_START = 0.0035  # ... from this far inside the hairline (the first loose roots)
EDGE_MIN = 0.15  # the share of its strands a loose lock rooted on the line keeps
EVEN_EDGE = 0.012  # m inside the hairline before the even layer starts (its children there hung over the forehead)
EVEN_LEN = 0.07  # m: the even (cover) layer's strand length
EVEN_ALL = 0.999  # strands.even at or over this: every strand from the even roots, the locks are guides only
EVEN_FRONT = 0.015  # ... over the face (|az| < 50): children of guides that fall past the face rule hung in front of it
LOOSE_HALO = 2.0  # x the halo share on LOOSE hair (a long head's crown fly-aways: at 1 x the halo read 0.05 vs 0.22-0.25)
SOFT_HALO = (3.0, 0.65, 0.6)  # halo_soft = 1: x (1 + 3) halo hairs, their stand-off x 0.35 (~4 mm), length x 0.4 (~2 cm)
HALO_MAX = 0.2  # the halo share at most (a guard: loose x2 x soft x4 reached 0.56 of the strands, the hair a thin veil of
# broken hairs: hair-heads)


def _soft(S) -> float:
    return float(np.clip(S.get("halo_soft", 0.0) or 0.0, 0.0, 1.0))


WISP_FAN = 2.0  # a thin free lock (a wisp, < 16 mm) opens to (1 + this) x its width toward the tip, round in section


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def physical(S: dict, free: bool = False, tail: bool = True) -> dict:
    """The dials as the numbers Blender's nodes take (metres, factors). `free`: hair that has left the head."""
    c = lambda k: float(np.clip(S[k], 0.0, 1.0))  # noqa: E731
    count = max(int(S["count"]), 200)
    return {
        "count": count,
        "radius": float(STRAND_RADIUS * float(S["thickness"]) * np.clip((REAL_COUNT / count) ** 0.8, 0.8, 4.0)),
        "wave_random": c("random") * (1.0 if free else 0.6),
        "stray": c("stray"),
        "tip_radius": float(np.clip(1.0 - 0.8 * float(S["taper"]), 0.1, 1.0)),
        "clump": SAFE["clump"] * c("clump") * (float(_os.environ.get("HS_FREE_CLUMP", 0.7)) if free else 1.0),
        # (a swing wider than ~a third of its wavelength folds back on itself: tight curls are small AND short)
        "wave": min(SAFE["sub_wave"] * float(np.clip(S["wave"], 0.0, 0.03)), 0.35 * float(np.clip(S["wavelength"], 0.01, 1.0))) * (1.0 if free else 0.3),
        "wavelength": float(np.clip(S["wavelength"], 0.01, 1.0)),
        "curl01": c("curl") * (1.0 if free else 0.3),
        "wander": SAFE["wander_m"] * c("loose") * (2.0 if free else 1.0),
        "clump_size": float(np.clip(S["clump_size"], 0.002, 0.03)),
        "clump_shape": float(np.clip(S["clump_shape"], 0.0, 1.0)),
        "tip_spread01": c("tip_spread"),
        "frizz": SAFE["frizz_m"] * c("frizz") * (1.5 if free else 1.0),
        "loose": SAFE["loose_m"] * c("loose") * (2.0 if free else 1.0),
        "loose_scale": 1.0 / max(float(S["wavelength"]), 0.02) * 0.6,
        "flyaway": SAFE["flyaway"] * c("flyaway"),
        "flyaway_m": SAFE["flyaway_m"] * (2.0 if free else 1.0),
        "tips": SAFE["tips"] * c("tips") * (1.3 if free else 1.0),
        "roots": SAFE["roots"] * c("roots") * (0.3 if free else 1.0),
        "curl": SAFE["curl_m"] * c("curl") * (1.0 if free else 0.3),
        "curl_freq": 1.0 / max(float(S["wavelength"]), 0.01),
        # (a tail has its fly-aways; short hairs standing off it all round made it a bottle brush: quartered on hair that
        # left the head IN A TAIL. Loose hair (groom.loose: free locks, no tie) keeps the dial: rule 4, hair-garrett)
        "halo": min(SAFE["halo"] * float(np.clip(S.get("halo", 0.0), 0.0, 1.0)) * (0.25 if (free and tail) else LOOSE_HALO if free else 1.0)
                    * (1.0 + SOFT_HALO[0] * _soft(S)), HALO_MAX),
        # halo_soft: closer to the hair and shorter (a fuzz a few mm deep), x (1 - k x ..)
        "halo_m": SAFE["halo_m"] * (1.0 - SOFT_HALO[1] * _soft(S)),
        "halo_len": SAFE["halo_len"] * (1.0 - SOFT_HALO[2] * _soft(S)),
    }


def wisp_physical(S: dict) -> dict:
    """The wisp object's numbers: single hairs (no clumps to join, no strays of strays), each keeps most of its length
    unless its lock says otherwise (`tip_loss`); strands.wisp's dials over the free hair's."""
    ph = physical({**S, **(S.get("free") or {}), **(S.get("wisp") or {})} if S.get("wisp") else S, free=True)
    return {**ph, "clump": 0.0, "flyaway": 0.0, "halo": 0.0, "tips": 0.35 * ph["tips"], "roots": 0.0}


def is_gather(lk: dict) -> bool:
    """A lock that runs over the head into a tie (hair_tied's gather rows)."""
    import re
    return bool(re.fullmatch(r"t\d*g\d+_\d+", str(lk.get("name", ""))))


def _smooth_field(p, seed: int, scale: float = 0.03) -> float:
    """A smooth value in [-1, 1] over space (a few sines of random direction, ~`scale` m): neighbours agree."""
    rg = np.random.default_rng([int(seed), 77])
    k = rg.normal(size=(4, 3))
    k = k / np.linalg.norm(k, axis=1, keepdims=True) * (2 * np.pi / scale) * rg.uniform(0.6, 1.4, (4, 1))
    a = rg.uniform(0, 2 * np.pi, 4)
    return float(np.clip(np.sin(k @ np.asarray(p, float) + a).sum() / 2.0, -1.0, 1.0))


GROOM_KEEP = 12  # evaluated grooms kept on disk (most recently used)

TILE_LEN = 0.16  # m: a tile's strands run this far (a card stretches its picture along the lock)
TILE_KIND = {  # per atlas tile kind: strands at a 160 px tile, sub clumps, tips x, where roots start (0..1 of the length), guide length x
    # (upper layers' roots start one by one over the first quarter: a row of cards has no root edge; a baby tile is
    # a few thin hairs with empty margins: dense and parallel they filled their quad, a brown stamp on the skin)
    "dense": (260, 6, 0.5, 0.02, 1.0), "medium": (120, 4, 1.0, 0.25, 1.0), "sparse": (44, 3, 1.4, 0.3, 1.0),
    "fly": (18, 1, 1.0, 0.03, 1.0), "baby": (16, 1, 1.6, 0.45, 0.85), "hairline": (330, 6, 0.5, 0.34, 1.0),
}

CAP_BASE_IN = 0.25  # the cap's opaque base starts this x soft inside the hairline (round 23: lever for the cards' skin gaps
# under the hairline; the groom's scalp tint covers the scalp by density right to the hairline)
CAP_PART_CUT = 0.8  # the base is cut by this share along the part (round 23: lever for the part's dark root lines)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("hair_strands_guides", "hair_strands_job", "hair_strands_eval")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
