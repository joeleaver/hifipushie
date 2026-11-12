"""Vegetation: trees grown by a self-organising model (Palubicki et al. 2009), steered the way artists steer them.

A plant spec is botanical words (species preset + habit overrides, age, environment) plus the artist's direct
controls (guides = drawn axes at any branch order, prune volumes, a soft crown envelope, forces). `grow` simulates
the tree step by step:

  1. light: every leafy node shades a pyramid of voxels below it (shadow propagation); the environment adds shade
     (a stand's canopy, neighbours, the envelope);
  2. bud fate: light is summed toward the root and a resource handed back out (extended Borchert-Honda; `apical`
     = the share the continuing axis takes: > 0.5 excurrent, < 0.5 decurrent); a bud's resource is its shoot's
     number of metamers and their length;
  3. shoots: direction = the bud's own + toward light + tropism (per branch order) + forces; guides place their
     nodes on the drawn path exactly;
  4. shedding: a branch whose light per internode falls under `shed` is dropped (clear boles, open interiors);
     prune volumes cut;
  5. widths by the pipe model (with a memory of shed branches); branches bend under their weight (`sag`) and the
     bend sets.

The simulation's unit is the metamer (`unit` m). Everything random is hashed from a bud's lineage (never drawn from
a shared stream), so the same spec gives the same tree and an edit only changes what it shades.
Conventions: metres, Z up, the trunk's foot at the origin.

Where the code is (split by responsibility, as C424): this module is the family's base: EVERY constant, the defaults,
presets and `resolve`. vegetation_kernels: lineage hashing and the growth kernels. vegetation_tree: nodes, shadow,
envelope, limbs. vegetation_grow: `grow` (one function of 733 lines). vegetation_measures: silhouettes and measures.
vegetation_fit: fit_habit, fit_form.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

VERSION = 2
PRESETS = Path(__file__).with_name("vegetation_presets")

DEAD_NODES = 600  # the most nodes remembered of one limb the shade killed
# how a limb killed by shade decays over `habit.dead_keep` years (spec `deadwood` overrides): `break` = the share of its
# length broken off by the end (never shorter than `stub` m), `twig` = [m, m] the radius under which twigs have fallen
# when it has just died / at the end, `droop` = [deg, deg] how far it hangs down then, `bow` = how far it bows along its
# length (m per m), `shrink` = barkless wood's girth against the living limb's
DEAD = {"break": 0.75, "stub": 0.25, "twig": [0.0012, 0.009], "droop": [6, 28], "bow": 0.12, "shrink": 0.85}

# every habit key, with what it means (the guide lists these); per-order lists repeat their last entry
DEFAULT = {
    "plant": "tree",  # "tree" = grown (this module); "clump" = assembled from cards in layers (veg_small: grass, ferns, flowers, palms)
    "clump": None,  # {"layers": [...], "size": 1.0}: see veg_small.LAYER
    "sward": None,  # plant "sward": plain grass as a tile of blades (veg_sward: variant mown | meadow | rough, height, density...)
    "age": 40, "seed": 1, "height": None,
    "habit": {
        "years_per_step": 1.5,  # one simulated flush = this many years (old trees: > 1)
        "unit": 0.35,  # m per metamer at full vigour
        "vigour": 3.0,  # resource per unit of light (alpha)
        "apical": [0.52, 0.50],  # per order: the continuing axis's share (lambda)
        "apical_old": None,  # the trunk's apical control once old (decurrent crowns of old broadleaves)
        "apical_fade": [0.4, 0.8],  # the fade's start and end, as a share of the age simulated
        "leader": 0,  # metamers a step the trunk's tip is sure of while young (a conifer's leader)
        "leader_until": 1.0,
        "shoot_max": [3, 2],  # per order: most metamers a step
        "length": [1.0, 0.9, 0.8],  # per order: metamer length x unit
        "buds": [1],  # per order: lateral buds per node
        "divergence": [137.5],  # per order: degrees between successive nodes' buds
        "plane": [False],  # per order: buds lie in the horizontal plane (a spruce's flat sprays)
        "whorl": [False],  # per order: lateral buds only on a flush's last metamer
        "angle": [50, 45],  # per order of the PARENT: [0] = limbs leaving the trunk, [1] = branches leaving limbs
        "bud_break": [1.0],  # per order: chance a lateral bud can ever break
        "bud_each": False,  # the chance holds for each bud of a node by itself (one or two limbs of a whorl), not for the whorl
        "bud_life": 5,  # steps a lateral bud stays able to break
        "max_order": 5,
        "light": 0.35,  # pull toward the light (xi)
        "tropism": [0.25, 0.05, 0.0],  # per order: + up, - down (eta)
        "plagio": [0.0],  # per order: pull toward a set elevation (horizontal branches)
        "elevation": [10],  # per order: that elevation, degrees
        "jitter": [0.12],  # per order: how crooked the shoots run
        "shed": 0.12,  # light per internode under which a branch is dropped
        "ground_clear": 0.05,  # m over the ground no shoot grows under: a hanging shoot stops there, a limb that sags onto the ground rests on it and its end turns up
        "shed_age": 2,
        "shadow": [0.25, 1.6, 6],  # a, b, depth of the shadow pyramid
        "shadow_tail": 0.7,  # how the shade carries on below the pyramid (0 = it ends: light-demanding trees in layers)
        "leaf_steps": 2,  # steps a node keeps its leaves (evergreens: more)
        "sag": 0.4, "sag_max": 0.25,  # bend under weight; the most one internode bends (rad)
        "pipe": 2.3,  # d^n = sum of the children's d^n
        "tip_radius": 0.004,  # m
        "ring": 0.0008,  # m of radius every living piece of wood adds a year, whatever it carries (girth)
        "force_orders": [0.15, 0.6, 1.0],  # per order: how much wind and forces turn a shoot (a trunk resists)
        "flare": 1.5, "flare_height": 0.6,  # the trunk's foot
        "uneven": [0.0],  # per order: each axis's own pace, +- this share of the segment length (ragged outlines)
        "slowing": [0],  # per order: steps after which an axis's shoots are half as long (0 = never): old branchlets creep
        "limb_pace": None,  # per order: the most a side axis extends in a step, as a share of what the trunk's leader does then (apical control: the whole tree's shoots shorten together as it ages)
        "tip_life": [0],  # per order: steps an axis keeps extending (0 = for ever). Spruce branchlets, spur shoots
        "stand_shed": 0.0,  # added to `shed` inside a stand (setting forest / edge): shade-bearers that hold a skirt in the open self-prune there
        "sdi_max": 1100,  # the most a closed stand of the species carries (Reineke's stand density index, metric): caps a stand tree's girth by its spacing
        "dead_keep": 0,  # years a limb the shade killed stays on the trunk as a thin grey stub (spruce 30, pine 10, broadleaves 3-8)
        "stems": 1, "stem_angle": 22,  # stems from the foot (a shrub, a hazel stool, a multi-stemmed birch) and how far they lean out, deg
        "clear": 0.0,  # m of trunk that never branches (the bole of a tree that grew up browsed or shaded)
    },
    "environment": {"setting": "open"},
    "guides": {}, "prune": [], "envelope": None, "forces": [],
    "leaves": {"shape": "ovate", "length": 0.07, "color": [0.16, 0.3, 0.08], "twig": {}},  # see veg_leaf.LEAF / TWIG
    "bark": {"kind": "furrowed"},
    "season": "summer",  # spring (leaves.spring colour, smaller leaves) | summer | autumn (leaves.autumn colour) | winter (deciduous: bare) | bare | dead
    "style": None,  # "blobby" | {"sheet": name, ...overrides}: the same grown plant dressed another way (veg_style; growth never reads it)
    "snow": 0.0, "wet": 0.0,  # 0..1: snow lying on what faces up; rain-dark, glossy bark and leaves (looks; export variants)
    "decay": None,  # {"min_radius": m}: wood thinner than this has fallen (a dead or storm-broken tree)
    "trunk_diameter": None,  # m at the foot: thick wood is scaled to it
    "limb_diameter": None,  # m: the stoutest limb's girth where it leaves the trunk (trunk_diameter then sizes the trunk alone)
    "trunk_taper": None,  # with trunk_diameter: the share of it the trunk loses by its top (0.1 = a column)
    "dead": [],  # [{a volume | "limb": name, "min_radius": m}]: wood that died and stayed: leafless, barkless, its thin ends gone
    "roots": None,  # {"count": 5, "spread": 2.0, "height": 0.8}: root flares at the foot (buttresses when tall)
    "deadwood": None,  # how shade-killed limbs decay over habit.dead_keep years: see DEAD
    "cuts": [],  # [{"year", a volume, "every", "until_year", "sprouts"}]: cut then, and the tree sprouts from the cut
}


# what a number usually is (get_plant shows these beside the resolved values: an override is never a blind guess)
HABIT_INFO = {
    "years_per_step": "1-3: years one growth step stands for; steps = age / this (2-80 steps). Smaller = more, finer steps",
    "unit": "0.2-0.5 m: a shoot segment at full vigour; overall scale (with `height` set, the unit is rescaled to reach it)",
    "vigour": "3-8: growth per unit of light. +1 can double the nodes; 7+ on a broadleaf makes 100k+ nodes and a huge trunk",
    "apical": "0.44-0.66 per order: the continuing shoot's share. trunk > 0.55 keeps one leader, < 0.5 dissolves into limbs",
    "apical_old": "0.36-0.46 or null: the trunk's apical once old", "apical_fade": "[start, end] as shares of the age",
    "leader": "0-2 segments a step the trunk's tip is sure of", "leader_until": "0-1 share of the age",
    "shoot_max": "1-4 per order: most segments a shoot grows in a step", "length": "0.25-1.1 per order: segment length x unit",
    "buds": "1-6 per order: side buds per node", "divergence": "deg per order: 137.5 spiral, 180 two-ranked",
    "plane": "per order: buds lie level (flat sprays)", "whorl": "per order: buds only at each step's last segment",
    "angle": "30-80 deg, by the parent's order: [0] = limbs off the trunk, [1] = branches off limbs", "bud_break": "0.3-1 per order: chance a bud can ever grow",
    "bud_each": "true: `bud_break` is drawn for each bud of a node (a pine keeps one or two limbs of a whorl of four); false: for the node's buds together (whole whorls or none)",
    "bud_life": "2-7 steps a bud stays able to grow", "max_order": "2-5: deepest branching",
    "light": "0.1-0.4: pull toward open light", "tropism": "-1.2..0.5 per order: + up, - down (hanging)",
    "plagio": "0-0.6 per order: pull toward `elevation`", "elevation": "deg above level per order, for plagio",
    "jitter": "0.03-0.5 per order: crookedness (curving, with momentum). trunk 0.03-0.15, gnarled limbs 0.4-0.5",
    "shed": "0-0.3: light per segment under which a branch is dropped", "shed_age": "steps before a branch can be shed",
    "shadow": "[strength 0.03-0.25, falloff 1.6-3, depth 2-6]: each leafy segment's shade",
    "shadow_tail": "0-0.8: shade carried on below `shadow`'s depth; 0.7 keeps crowns from forming level bands, 0 for shade-bearers that hold foliage to the ground (spruce)",
    "leaf_steps": "2-6: steps a segment keeps its leaves (evergreens more)", "sag": "0.3-3: bend under weight",
    "sag_max": "0.2-0.35 rad: the most one segment bends", "pipe": "2-2.5: how fast branches thin (2 = thick limbs)",
    "tip_radius": "0.003-0.006 m: a shoot end's radius", "ring": "0.0008-0.003 m of radius wood adds a year whatever it carries (girth); one number for all wood, or per order: a conifer's side branches barely thicken ([0.003, 0.0005, 0.0002]) while an oak's limbs do",
    "force_orders": "per order: how much wind/forces turn shoots", "flare": "1.3-1.8: the foot's swelling",
    "flare_height": "m the flare fades over",
    "uneven": "0-0.5 per order: every axis grows at its own pace, +- this share (a ragged outline instead of a turned cone)",
    "slowing": "per order: growth steps after which an axis's new segments are half as long, a third at twice that... (0 = never). A spruce's hanging branchlets 3-5: they creep on for decades, so their young needles stay near the limb all along it",
    "stand_shed": "0-0.2 added to `shed` when the tree stands in a stand (setting forest or edge): a spruce keeps its skirt in the open (shed 0) and self-prunes to a top third of live crown in a forest (0.15-0.2)",
    "sdi_max": "600-1600: Reineke's maximum stand density index (stems / ha at 25 cm dbh). In a stand with a spacing, a stem is no stouter than 25 cm x (sdi_max / stems per ha)^(1/1.6): Norway spruce ~1500, Scots pine ~1000, oak ~700, birch ~800 (Pretzsch & Biber 2005 give spruce 1609, pine 990, beech 1172, oak 578-ish; rounded); 0 = no cap",
    "dead_keep": "years a limb killed by shade stays on the trunk as dead wood (twiggy at first, a short spur at the end: `deadwood`) before it falls: Norway spruce 30-45 (a stand's interior is a ladder of dead whorls), Scots pine 15-25 (it sheds cleaner), oak 5-10, birch 2-4; 0 = they fall at once. Guesses: dead branches persist for decades (Makinen 1999), the years per species are not sourced",
    "stems": "1-12 stems rising from the foot: a shrub or a multi-stemmed tree (each is a trunk: order 0)", "stem_angle": "deg the extra stems lean outward at the foot (10 tight, 35 open)",
    "ground_clear": "0.03-1.5 m over the ground no shoot grows under: hanging shoots (a weeping willow's curtains) stop there (0.4-1.2 = a browse or mowing line), a limb that sags to the ground rests on it and its growing end turns up",
    "limb_pace": "null or per order [-, 0.8, 0.6]: a side shoot's most growth in a step as a share of the leader's at that age (needs slowing[0]); under 1 the leader stays ahead for life (a conifer's spire, a stand-grown pole), over 1 old limbs catch it up (a rounded or flat old crown)",
    "tip_life": "per order: growth steps an axis keeps extending, 0 = for ever (short-lived hanging branchlets: 6-10; limbs that stop reaching: 20-30)", "clear": "0-6 m of trunk that never branches",
}


def preset(name: str) -> dict:
    p = PRESETS / f"{name}.json"
    if not p.exists():
        raise ValueError(f"no species preset {name!r}; presets: {species()}")
    return json.loads(p.read_text())


def species() -> list[str]:
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve(spec: dict) -> dict:
    """The spec over its species preset over the defaults."""
    s = DEFAULT
    if spec.get("species"):
        s = _merge(s, preset(spec["species"]))
    s = _merge(s, spec)
    unknown = set(s["habit"]) - set(DEFAULT["habit"])
    if unknown:
        raise ValueError(f"unknown habit keys {sorted(unknown)}; known: {sorted(DEFAULT['habit'])}")
    vol = {"box", "sphere", "above", "below", "under"}

    def keys(what, d, ok):  # (a key we don't know was being accepted and ignored: an until_year on a prune)
        bad = set(d) - ok
        if bad:
            raise ValueError(f"{what}: unknown keys {sorted(bad)}; it takes {sorted(ok)}")

    keys("the spec", s, set(DEFAULT) | {"species", "about", "look", "style", "set"})
    for i, pr in enumerate(s.get("prune") or []):
        keys(f"prune {i}", pr, vol | {"from_year"})
        if not vol & set(pr):
            raise ValueError(f"prune {i} needs one of {sorted(vol)}")
    for i, c in enumerate(s.get("cuts") or []):
        keys(f"cut {i}", c, vol | {"year", "every", "until_year", "sprouts", "sprout_nodes", "boll"})
        if "year" not in c or not vol & set(c):
            raise ValueError(f"cut {i} needs a year and one of {sorted(vol)}")
    for i, c in enumerate(s.get("dead") or []):
        keys(f"dead {i}", c, vol | {"limb", "min_radius", "from"})
        if not (vol | {"limb"}) & set(c):
            raise ValueError(f"dead {i} needs a limb's name or one of {sorted(vol)}")
    if s.get("roots"):
        keys("roots", s["roots"], {"count", "spread", "height", "under"})
    if s.get("plant") == "sward":
        from . import veg_sward
        veg_sward.validate(s)
        return s
    if s.get("plant") not in ("tree", "clump"):
        raise ValueError(f'plant {s.get("plant")!r}: "tree" (grown), "clump" (assembled from cards in layers) or "sward" (a tile of grass blades)')
    if s.get("plant") == "clump":
        from . import veg_small
        veg_small.validate(s)
    for g, gd in (s.get("guides") or {}).items():
        keys(f"guide {g}", gd, {"path", "from_year", "until_year", "vigour", "free", "on", "straight", "bare", "replaces"})
        if len(gd.get("path") or []) < 2:
            raise ValueError(f"guide {g} needs a path of at least two [x, y, z] points")
    return s


# ---------------------------------------------------------------- hashing (lineage keys)
_M = np.uint64(0xFFFFFFFFFFFFFFFF)

# ---------------------------------------------------------------- the tree
_FIELDS = {"pos": (np.float64, 3), "off": (np.float64, 3), "pinpos": (np.float64, 3), "parent": (np.int32, 0),
           "order": (np.int8, 0), "main": (np.bool_, 0), "born": (np.int16, 0), "key": (np.uint64, 0),
           "tip": (np.bool_, 0), "nb": (np.uint8, 0), "phi": (np.float64, 0), "theta": (np.float64, 0),
           "pin": (np.bool_, 0), "mem": (np.float64, 0), "axis": (np.int32, 0), "starve": (np.uint8, 0),
           "R": (np.float64, 33), "guide": (np.int16, 0), "vig": (np.float32, 0), "budstep": (np.int16, 0)}

TAIL = 0.7

FORM_KEYS = ("height", "width_over_height", "crown_ratio", "widest_at", "dbh_cm", "top_off", "nodes")


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("vegetation_kernels", "vegetation_tree", "vegetation_grow", "vegetation_measures", "vegetation_fit")
