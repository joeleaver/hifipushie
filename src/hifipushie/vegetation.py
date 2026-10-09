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
"""

from __future__ import annotations

import copy
import json
import math
import time
from pathlib import Path

import numpy as np
from numba import njit
from scipy import ndimage

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


def _mix(x):
    x = np.asarray(x, np.uint64)
    with np.errstate(over="ignore"):
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return x ^ (x >> np.uint64(31))


def _child(key, i):
    with np.errstate(over="ignore"):
        return _mix(np.asarray(key, np.uint64) * np.uint64(0x9E3779B97F4A7C15) + np.asarray(i, np.uint64) + np.uint64(1))


def _u(key, salt):
    """Uniform [0, 1) from a key."""
    return (_child(key, 1000 + salt) >> np.uint64(11)).astype(np.float64) / float(1 << 53)


# ---------------------------------------------------------------- kernels

@njit(cache=True)
def _collect(parent, qnode, Q, size):
    n = len(parent)
    for i in range(n):
        Q[i] = qnode[i]
        size[i] = 1
    for i in range(n - 1, 0, -1):
        Q[parent[i]] += Q[i]
        size[parent[i]] += size[i]


@njit(cache=True)
def _distribute(parent, main, order, Q, qtip, qlat, lam, v0, v, vtip, vlat):
    """Extended Borchert-Honda: hand the resource out from the root. qlat = the summed light of a node's lateral
    buds; vlat = the resource of them together."""
    n = len(parent)
    den = np.zeros(n)
    for i in range(n):
        o = min(order[i], len(lam) - 1)
        den[i] = lam[o] * qtip[i] + (1.0 - lam[o]) * qlat[i]
    for i in range(1, n):
        p = parent[i]
        o = min(order[p], len(lam) - 1)
        den[p] += (lam[o] if main[i] else 1.0 - lam[o]) * Q[i]
    v[0] = v0
    for i in range(n):
        if i > 0:
            p = parent[i]
            o = min(order[p], len(lam) - 1)
            w = lam[o] if main[i] else 1.0 - lam[o]
            v[i] = v[p] * w * Q[i] / den[p] if den[p] > 1e-12 else 0.0
        o = min(order[i], len(lam) - 1)
        if den[i] > 1e-12:
            vtip[i] = v[i] * lam[o] * qtip[i] / den[i]
            vlat[i] = v[i] * (1.0 - lam[o]) * qlat[i] / den[i]
        else:
            vtip[i] = 0.0
            vlat[i] = 0.0


@njit(cache=True)
def _pipe(parent, mem, tip_area, expo, area):
    n = len(parent)
    kids = np.zeros(n, np.int32)
    for i in range(1, n):
        kids[parent[i]] += 1
    for i in range(n):
        area[i] = mem[i] + (tip_area if kids[i] == 0 else 0.0)
    for i in range(n - 1, 0, -1):
        area[parent[i]] += area[i]
    # area holds the sum of d^n: the radius is its n-th root
    for i in range(n):
        area[i] = area[i] ** (1.0 / expo)


@njit(cache=True)
def _pose(parent, off, pin, pinpos, order, radius, leafy, theta, sag, sag_max, sag_trunk, pos, R, g0, gx, gy):
    """Bend under weight, then forward kinematics. off = each node's internode in its parent's rest frame; theta =
    how far its internode has bent so far (it never bends back: wood sets). The ground (z = g0 + gx x + gy y) holds
    up what sags onto it: a limb rests on it."""
    n = len(parent)
    m = np.zeros(n)
    mx = np.zeros(n)
    my = np.zeros(n)
    for i in range(1, n):
        p = parent[i]
        L = math.sqrt(off[i, 0] ** 2 + off[i, 1] ** 2 + off[i, 2] ** 2)
        w = radius[i] * radius[i] * L * 3.14 + (0.0006 if leafy[i] else 0.0)
        m[i] = w
        mx[i] = w * 0.5 * (pos[i, 0] + pos[p, 0])
        my[i] = w * 0.5 * (pos[i, 1] + pos[p, 1])
    for i in range(n - 1, 0, -1):
        p = parent[i]
        m[p] += m[i]
        mx[p] += mx[i]
        my[p] += my[i]
    for i in range(1, n):
        p = parent[i]
        if m[i] > 0:
            ax = mx[i] / m[i] - pos[p, 0]
            ay = my[i] / m[i] - pos[p, 1]
            arm = math.sqrt(ax * ax + ay * ay)
            k = sag if order[i] > 0 else sag * sag_trunk
            t = k * 5e-7 * m[i] * arm / (radius[i] ** 4 + 1e-12)
            if t > sag_max:
                t = sag_max
            if t > theta[i]:
                theta[i] = t
    d = np.zeros(3)
    for i in range(1, n):
        p = parent[i]
        if pin[i]:
            for a in range(3):
                pos[i, a] = pinpos[i, a]
                for b in range(3):
                    R[i, a, b] = 1.0 if a == b else 0.0
            continue
        for a in range(3):
            d[a] = R[p, a, 0] * off[i, 0] + R[p, a, 1] * off[i, 1] + R[p, a, 2] * off[i, 2]
        # rotate d toward straight down by theta: axis = d x (0, 0, -1)
        kx, ky = -d[1], d[0]
        kn = math.sqrt(kx * kx + ky * ky)
        L = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        t = theta[i] * (kn / L if L > 0 else 0.0)  # (a vertical internode has no lever)
        if order[i] > 0 and kn > 1e-9 and L > 0:
            # the ground stops the bend: an internode that would dip under it turns only as far as resting on it, and
            # what it carries turns with it (a limb sagged onto the ground lies there and its end rises again)
            fl = g0 + gx * (pos[p, 0] + d[0]) + gy * (pos[p, 1] + d[1]) + radius[i]
            sn = (fl - pos[p, 2]) / L
            if sn < 0.95:
                e_min = math.asin(sn) if sn > -1.0 else -1.5708
                e0 = math.asin(max(-1.0, min(1.0, d[2] / L)))
                if e0 - t < e_min:
                    t = e0 - e_min
                    if t < -0.6:
                        t = -0.6
        if kn > 1e-9 and abs(t) > 1e-6:
            kx /= kn
            ky /= kn
            c, s = math.cos(t), math.sin(t)
            # Rodrigues, axis (kx, ky, 0)
            r00 = c + kx * kx * (1 - c)
            r01 = kx * ky * (1 - c)
            r02 = ky * s
            r10 = kx * ky * (1 - c)
            r11 = c + ky * ky * (1 - c)
            r12 = -kx * s
            r20 = -ky * s
            r21 = kx * s
            r22 = c
            for b in range(3):
                a0, a1, a2 = R[p, 0, b], R[p, 1, b], R[p, 2, b]
                R[i, 0, b] = r00 * a0 + r01 * a1 + r02 * a2
                R[i, 1, b] = r10 * a0 + r11 * a1 + r12 * a2
                R[i, 2, b] = r20 * a0 + r21 * a1 + r22 * a2
            x = r00 * d[0] + r01 * d[1] + r02 * d[2]
            y = r10 * d[0] + r11 * d[1] + r12 * d[2]
            z = r20 * d[0] + r21 * d[1] + r22 * d[2]
            d[0], d[1], d[2] = x, y, z
        else:
            for a in range(3):
                for b in range(3):
                    R[i, a, b] = R[p, a, b]
        for a in range(3):
            pos[i, a] = pos[p, a] + d[a]
        if order[i] > 0:
            fl = g0 + gx * pos[i, 0] + gy * pos[i, 1] + radius[i]
            if pos[i, 2] < fl:
                pos[i, 2] = fl


@njit(cache=True)
def _shed(parent, main, born, pin, Q, size, cut, step, thr, age, dead):
    n = len(parent)
    dead[0] = False
    for i in range(1, n):
        if dead[parent[i]]:
            dead[i] = True
        elif cut[i]:
            dead[i] = True
        elif (not main[i]) and (not pin[i]) and step - born[i] >= age and Q[i] < thr[i] * size[i]:
            dead[i] = True
        else:
            dead[i] = False


# ---------------------------------------------------------------- the tree

_FIELDS = {"pos": (np.float64, 3), "off": (np.float64, 3), "pinpos": (np.float64, 3), "parent": (np.int32, 0),
           "order": (np.int8, 0), "main": (np.bool_, 0), "born": (np.int16, 0), "key": (np.uint64, 0),
           "tip": (np.bool_, 0), "nb": (np.uint8, 0), "phi": (np.float64, 0), "theta": (np.float64, 0),
           "pin": (np.bool_, 0), "mem": (np.float64, 0), "axis": (np.int32, 0), "starve": (np.uint8, 0),
           "R": (np.float64, 33), "guide": (np.int16, 0), "vig": (np.float32, 0), "budstep": (np.int16, 0)}


class _Nodes:
    def __init__(self, cap=4096):
        self.n = 0
        self.cap = cap
        for k, (t, d) in _FIELDS.items():
            setattr(self, "_" + k, np.zeros((cap,) + ((3, 3) if d == 33 else (d,) if d else ()), t))

    def __getattr__(self, k):
        if k in _FIELDS:
            return getattr(self, "_" + k)[: self.n]
        raise AttributeError(k)

    def add(self, m, **kw):
        if self.n + m > self.cap:
            self.cap = max(2 * self.cap, self.n + m)
            for k in _FIELDS:
                a = getattr(self, "_" + k)
                b = np.zeros((self.cap,) + a.shape[1:], a.dtype)
                b[: self.n] = a[: self.n]
                setattr(self, "_" + k, b)
        s = slice(self.n, self.n + m)
        for k in _FIELDS:
            a = getattr(self, "_" + k)
            if k in kw:
                a[s] = kw[k]
            else:
                a[s] = 0
        self.n += m
        return np.arange(s.start, s.stop)

    def keep(self, mask):
        idx = np.flatnonzero(mask)
        new = -np.ones(self.n, np.int64)
        new[idx] = np.arange(len(idx))
        for k in _FIELDS:
            a = getattr(self, "_" + k)
            a[: len(idx)] = a[idx]
        self.n = len(idx)
        p = self.parent
        p[1:] = new[p[1:]]
        return new


def _per(lst, order):
    lst = lst if isinstance(lst, (list, tuple)) else [lst]
    o = np.minimum(np.asarray(order), len(lst) - 1)
    return np.asarray(lst, dtype=float)[o]


def _norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _compass(d):
    if isinstance(d, str):
        a = {"n": 0, "ne": 45, "e": 90, "se": 135, "s": 180, "sw": 225, "w": 270, "nw": 315}[d.lower()]
        return np.array([math.sin(math.radians(a)), math.cos(math.radians(a)), 0.0])  # +y north, +x east
    return np.asarray(d, float)


TAIL = 0.7


def _shadow(src, lo, dims, a, b, depth, tilt, weight=1.0, tail=TAIL):
    """The shadow grid of leafy points src (cell units, origin lo), each casting `weight` (its internode's length:
    short internodes carry less leaf)."""
    C = np.zeros(dims)
    ij = np.clip((src - lo).astype(np.int64), 0, np.array(dims) - 1)
    np.add.at(C, (ij[:, 0], ij[:, 1], ij[:, 2]), weight)
    S = np.zeros(dims)
    for q in range(depth + 1):
        w = 2 * q + 1
        B = C if q == 0 else ndimage.uniform_filter(C, size=(w, w, 1), mode="constant") * (w * w)
        if q:
            sx, sy = int(round(q * tilt[0])), int(round(q * tilt[1]))
            if sx or sy:
                B = ndimage.shift(B, (sx, sy, 0), order=0, mode="constant")
            S[:, :, :-q] += a * b ** (-q) * B[:, :, q:]
        else:
            S += a * B
    # below the pyramid the shade fades instead of ending: cut off at `depth`, the light came back exactly that far
    # under every foliage layer and the next layer formed there (crowns in level bands `depth` cells apart)
    if tail > 0 and depth > 0 and dims[2] > depth + 1:
        last = a * b ** (-depth) * B
        acc = np.zeros(dims[:2])
        for z in range(dims[2] - 1, -1, -1):
            zs = z + depth + 1
            if zs < dims[2]:
                acc = tail * (acc + last[:, :, zs])
            S[:, :, z] += acc
    return S


def _inside(P, vol):
    """Points (m) inside a prune volume."""
    if "box" in vol:
        lo, hi = np.asarray(vol["box"][0], float), np.asarray(vol["box"][1], float)
        return np.all((P >= np.minimum(lo, hi)) & (P <= np.maximum(lo, hi)), axis=1)
    if "sphere" in vol:
        c, r = np.asarray(vol["sphere"][0], float), float(vol["sphere"][1])
        return np.linalg.norm(P - c, axis=1) <= r
    if "above" in vol:
        return P[:, 2] >= float(vol["above"])
    raise ValueError(f"prune volume needs box, sphere, above, below or under: {vol}")


def _envelope(P, env):
    """How far outside the envelope each point (m) is, in units of its softness (0 inside)."""
    if env is None:
        return np.zeros(len(P))
    z0, z1 = env.get("base", 0.0), env["top"]
    r = env["radius"]
    t = np.clip((P[:, 2] - z0) / max(z1 - z0, 1e-6), 0, 1)
    # `lean` [dx, dy]: how far the crown's middle has moved by its top (a wind-flagged wedge)
    c = np.asarray(env.get("center", [0, 0]), float)[None] + t[:, None] * np.asarray(env.get("lean", [0, 0]), float)[None]
    sh = env.get("shape", "ellipsoid")
    if sh == "ellipsoid":
        rr = r * np.sqrt(np.clip(1 - (2 * t - 1) ** 2, 0, 1))
    elif sh == "cone":
        rr = r * (1 - t)
    elif sh == "column":
        rr = r * np.ones_like(t)
    elif sh == "umbrella":  # a flat wide top over a narrow underside (a wind-clipped pine, an acacia)
        rr = r * np.clip(0.25 + 1.5 * t, 0, 1) * np.where(t > 0.9, np.sqrt(np.clip(1 - ((t - 0.9) / 0.1) ** 2, 0, 1)) * 0.3 + 0.7, 1.0)
    elif sh == "dome":  # widest low, rounded top
        rr = r * np.sqrt(np.clip(1 - t ** 2, 0, 1))
    elif sh == "profile":  # [[t, share of radius], ...] bottom to top
        pr = np.asarray(env["profile"], float)
        rr = r * np.interp(t, pr[:, 0], pr[:, 1])
    else:
        raise ValueError(f"envelope shape {sh!r}: ellipsoid, cone, column, dome, umbrella or profile")
    soft = env.get("soft", 0.15 * r)
    d = np.linalg.norm(P[:, :2] - c, axis=1) - rr
    d = np.maximum(d, np.maximum(P[:, 2] - z1, z0 - P[:, 2]))
    return np.clip(d / soft, 0, None)


def _path(pts, smooth=True):
    """A drawn path as a dense polyline + its arc lengths: through the points on a Catmull-Rom curve (a path of
    straight legs grew as a limb with corners)."""
    pts = np.asarray(pts, float)
    if smooth and len(pts) >= 3:
        P = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
        out = []
        for i in range(1, len(P) - 2):
            n = max(2, int(np.ceil(np.linalg.norm(P[i + 1] - P[i]) / 0.4)))
            t = (np.arange(n) / n)[:, None]
            out.append(0.5 * ((2 * P[i]) + (-P[i - 1] + P[i + 1]) * t + (2 * P[i - 1] - 5 * P[i] + 4 * P[i + 1] - P[i + 2]) * t ** 2
                              + (-P[i - 1] + 3 * P[i] - 3 * P[i + 1] + P[i + 2]) * t ** 3))
        pts = np.vstack(out + [pts[-1:]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return pts, np.concatenate([[0], np.cumsum(seg)])


def _along(pts, cum, s):
    s = np.clip(s, 0, cum[-1])
    i = min(np.searchsorted(cum, s, side="right") - 1, len(pts) - 2)
    t = (s - cum[i]) / max(cum[i + 1] - cum[i], 1e-12)
    return pts[i] + t * (pts[i + 1] - pts[i])


def ground_at(spec: dict, xy) -> np.ndarray:
    """The ground's height (m) under [x, y] points: `environment.ground` {"level": m at the plant's foot (0), "slope":
    deg, "toward": [x, y] the way it falls}. Nothing a plant grows or carries may lie under it."""
    g = ((spec.get("environment") or {}).get("ground") or {})
    xy = np.atleast_2d(np.asarray(xy, float))[:, :2]
    z = np.full(len(xy), float(g.get("level", 0.0)))
    if g.get("slope"):
        t = np.asarray(g.get("toward", [1, 0]), float)
        z = z - math.tan(math.radians(float(g["slope"]))) * (xy @ (t / max(np.linalg.norm(t), 1e-9)))
    return z


def steps_of(s: dict) -> int:
    return int(np.clip(round(s["age"] / s["habit"]["years_per_step"]), 2, 80))


def limb_id(key) -> str:
    """A limb's lasting name: from its bud's lineage, so the same bud has it whatever else changes on the tree."""
    v_, out = int(key) % 36 ** 4, ""
    for _ in range(4):
        out = "0123456789abcdefghijklmnopqrstuvwxyz"[v_ % 36] + out
        v_ //= 36
    return "L" + out


def find_limb(tree: dict, ref: str):
    """The axis a limb reference names: a guide's name, a limb id ("Lk7f3", lasting), or a compass name ("SW2", of
    this grown tree only). None when the tree has no such limb."""
    if ref in tree["guides"]:
        return tree["guides"][ref]
    if isinstance(ref, str) and len(ref) == 5 and ref[0] == "L":
        for ai, a in enumerate(tree["axes"]):
            if a["order"] == 1 and "node" in a and a["node"] < len(tree["key"]) and tree["axis"][a["node"]] == ai \
                    and limb_id(tree["key"][a["node"]]) == ref:
                return ai
    L = next((q for q in limbs(tree) if q["name"] == ref), None)
    return None if L is None else L["axis"]


def stout_path(tree: dict, n0: int, kids: dict | None = None) -> np.ndarray:
    """A limb as an eye follows it: from node n0 on through the stoutest child at every fork, to a shoot's end. (The
    growth's own axis often ends a metre out, where a side shoot took over.)"""
    if kids is None:
        kids = {}
        for i in range(1, len(tree["parent"])):
            kids.setdefault(int(tree["parent"][i]), []).append(i)
    rad, out, q = tree["radius"], [int(n0)], int(n0)
    while kids.get(q):
        q = max(kids[q], key=lambda c: rad[c])
        out.append(q)
    return np.array(out)


def limbs(tree: dict, count: int = 12, min_share: float = 0.12) -> list[dict]:
    """The tree's main limbs, named so they can be talked about and taken over: first-order branches, the stoutest
    `count` whose base is at least `min_share` of the trunk's radius there. A drawn limb has its guide's name; a grown
    one is named by where its end points and its rank up the trunk ("SW2" = the second limb up that ends to the
    south-west). Names are of THIS grown tree: an edit that regrows it may rename them; take_limb makes one a guide,
    which keeps its name and shape."""
    P, par, ax, rad = tree["pos"], tree["parent"], tree["axis"], tree["radius"]
    yps = tree["spec"]["habit"]["years_per_step"]
    gname = {ai: g for g, ai in tree["guides"].items()}
    kids = {}
    for i in range(1, len(par)):
        kids.setdefault(int(par[i]), []).append(i)
    out = []
    for ai, a in enumerate(tree["axes"]):
        if a["order"] != 1 or "node" not in a:
            continue
        n0 = a["node"]
        if n0 >= len(P) or tree["order"][n0] != 1 or ax[n0] != ai:
            continue
        nodes = np.flatnonzero(ax == ai)
        if len(nodes) < 3:
            continue
        base = int(par[n0])
        if rad[n0] < min_share * rad[base] and ai not in gname:
            continue
        sub, stack = [], [int(n0)]
        while stack:
            q = stack.pop()
            sub.append(q)
            stack.extend(kids.get(q, ()))
        sub = np.array(sub)
        far = P[sub][np.argmax(np.linalg.norm(P[sub] - P[base], axis=1))]
        d = far - P[base]
        nodes = stout_path(tree, n0, kids)
        seg = np.linalg.norm(np.diff(np.vstack([P[base], P[nodes]]), axis=0), axis=1).sum()
        out.append({"axis": ai, "guide": gname.get(ai), "at": P[base].round(2).tolist(), "height": round(float(P[base][2]), 2),
                    "diameter": round(float(2 * rad[n0]), 3), "length": round(float(seg), 2), "end": P[nodes[-1]].round(2).tolist(),
                    "reach": round(float(np.linalg.norm(P[sub][:, :2] - P[1][:2], axis=1).max()), 2), "low": round(float(P[sub][:, 2].min()), 2),
                    "high": round(float(P[sub][:, 2].max()), 2), "nodes": int(len(sub)),
                    "born_year": round(float(tree["born"][n0] * yps), 1), "key": str(int(tree["key"][n0])),
                    "id": gname.get(ai) or limb_id(tree["key"][n0]),
                    "compass": _compass_name(d)})
    out.sort(key=lambda L: -L["diameter"])
    keep = [L for L in out if L["guide"]] + [L for L in out if not L["guide"]][:count]
    keep.sort(key=lambda L: L["height"])
    seen = {}
    for L in keep:
        if L["guide"]:
            L["name"] = L["guide"]
        else:
            seen[L["compass"]] = seen.get(L["compass"], 0) + 1
            L["name"] = f"{L['compass']}{seen[L['compass']]}"
    return keep


def _compass_name(d) -> str:
    if np.linalg.norm(d[:2]) < 0.25 * abs(d[2]):
        return "UP"
    a = math.degrees(math.atan2(d[0], d[1])) % 360  # +y = north, +x = east
    return ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[int((a + 22.5) // 45) % 8]


def limb_path(tree: dict, limb: dict, points: int = 7) -> list:
    """A limb's own axis as a guide path: from where it leaves the trunk to its end, `points` of them evenly along."""
    nodes = stout_path(tree, tree["axes"][limb["axis"]]["node"])
    pts = np.vstack([tree["pos"][tree["parent"][nodes[0]]], tree["pos"][nodes]])
    cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    k = int(max(3, min(points, len(pts))))
    return [_along(pts, cum, t).round(3).tolist() for t in np.linspace(0, cum[-1], k)]


def grow(spec: dict, unit_scale: float | None = None, log=None) -> dict:
    """Grow the tree. Returns arrays in metres (pos, parent, radius, order, born, axis, key, tip, leafy), axes, and
    stats. With `height`, an unedited run is grown first and its height sets the unit, so edits stay in metres."""
    s = resolve(spec)
    if s.get("plant") == "sward":  # a tile of blades, not a plant with a skeleton
        from . import veg_sward
        return veg_sward.grow(s)
    if s.get("plant") == "clump":  # assembled, not grown
        from . import veg_small
        return veg_small.grow(s)
    h = s["habit"]
    t0 = time.perf_counter()
    if s.get("height") and unit_scale is None:
        bare = {k: v for k, v in spec.items() if k not in ("guides", "prune", "envelope", "forces", "height", "cuts", "dead")}
        ref = grow(bare, unit_scale=1.0)
        k = float(s["height"]) / max(ref["height"], 1e-6)
        if abs(k - 1) > 0.02:
            out = grow(spec, unit_scale=k)
            out["stats"]["unit_scale"] = round(k, 3)
            out["stats"]["grow_s"] = round(time.perf_counter() - t0, 3)
            return out
        unit_scale = 1.0
    unit = h["unit"] * (unit_scale or 1.0)
    steps = steps_of(s)
    yps = h["years_per_step"]
    seed = np.uint64(int(s["seed"]) * 2654435761 % (1 << 62) + 12345)
    sa, sb, sd = h["shadow"]
    sd = int(sd)
    env = s.get("environment") or {}
    light = _norm(np.asarray(env.get("light", [0, 0, 1]), float))
    tilt = (-light[0] / max(light[2], 0.3), -light[1] / max(light[2], 0.3))  # shadows fall away from the light
    wind = env.get("wind")
    wdir = _compass(wind["from"]) * -1 if wind else None  # the way it blows
    wstr = float(wind.get("strength", 0.5)) if wind else 0.0
    g_ = env.get("ground") or {}  # the ground in growth units: z = g0u + [x, y] . gvu
    g0u = float(g_.get("level", 0.0)) / unit
    gvu = np.zeros(2)
    if g_.get("slope"):
        t_ = np.asarray(g_.get("toward", [1, 0]), float)
        gvu = -math.tan(math.radians(float(g_["slope"]))) * t_ / max(np.linalg.norm(t_), 1e-9)
    clear_u = float(h["ground_clear"]) / unit
    forces = [(np.asarray(f["dir"], float) * float(f.get("strength", 1.0)), f.get("orders")) for f in s.get("forces") or []]
    stand = env.get("stand") if env.get("setting") in ("forest", "stand", "edge") or env.get("stand") else None
    if env.get("setting") in ("forest", "edge") and stand is None:
        stand = {}
    if env.get("setting") == "edge":  # a stand's edge: closed behind, open to one side (foliage down that side only)
        stand = {**stand, "open_side": env.get("open_side", stand.get("open_side", [1, 0]))}
    dead_log_ = []  # limbs the shade killed: (the trunk node's key, direction, girth, step)
    prunes = s.get("prune") or []
    cuts = []
    for c in s.get("cuts") or []:  # the steps each cut is made at
        y, last_y = float(c["year"]), float(c.get("until_year", s["age"]))
        ys = [y]
        while c.get("every") and ys[-1] + float(c["every"]) <= last_y:
            ys.append(ys[-1] + float(c["every"]))
        cuts.append(({int(round(q / yps)) for q in ys}, c))
    cut_log = []
    bolls = {}  # node key -> swelling: where a pollard is cut again and again the wood heals into a knuckled head
    envl = s.get("envelope")

    # guides: paths in metres -> units; each starts at a step
    guides = []
    for name, g in (s.get("guides") or {}).items():
        pts, cum = _path(np.asarray(g["path"], float) / unit, smooth=not g.get("straight"))
        st = int(round(g.get("from_year", 0) / yps))
        until = g.get("until_year")
        en = int(round(until / yps)) if until is not None else None
        guides.append({"name": name, "pts": pts, "cum": cum, "start": st, "end": en, "s": 0.0, "node": -1,
                       "vigour": float(g.get("vigour", 1.0)), "done": False, "free": bool(g.get("free", False)),
                       "on": g.get("on"), "bare": float(g.get("bare", 0.0))})
    guides.sort(key=lambda g: (g["start"], g["name"]))
    # a limb taken over as a guide: the shoot it was grown from is not made again (its lineage key)
    replaced = np.array([int(k) for g in (s.get("guides") or {}).values() for k in (g.get("replaces") or [])], np.uint64)

    T = _Nodes()
    T.add(1, key=_mix(seed), tip=False, guide=-1, R=np.eye(3))
    axes = [{"order": 0, "node": 1, "guide": None}]
    trunk = next((g for g in guides if g["start"] == 0 and np.linalg.norm(g["pts"][0]) < 1.5), None)
    if trunk is None:  # the first internode: straight up
        T.add(1, pos=[0, 0, 1.0], off=[0, 0, 1.0], parent=0, main=True, key=_child(_mix(seed), 0), tip=True,
              nb=0, guide=-1, R=np.eye(3), vig=1.0)
        for si_ in range(1, int(h["stems"])):  # more stems from the same foot, leaning out round it
            a_ = 2.399963 * si_ + 6.283 * float(_u(_child(_mix(seed), 300), 1))
            t_ = math.radians(float(h["stem_angle"]) * (0.6 + 0.8 * float(_u(_child(_mix(seed), 300 + si_), 2))))
            d_ = [math.sin(t_) * math.cos(a_), math.sin(t_) * math.sin(a_), math.cos(t_)]
            axes.append({"order": 0, "node": T.n, "guide": None, "born": 0})
            T.add(1, pos=d_, off=d_, parent=0, main=True, key=_child(_mix(seed), 300 + si_), tip=True,
                  nb=0, guide=-1, R=np.eye(3), vig=1.0, axis=len(axes) - 1)
    else:  # a drawn trunk: its path is the seedling
        trunk.update(node=0, axis=0)
        axes[0]["guide"] = trunk["name"]

    def new_axis(order, guide=None):
        axes.append({"order": int(order), "guide": guide, "born": step})
        return len(axes) - 1

    lam_young = list(h["apical"])
    ring_l = h["ring"] if isinstance(h["ring"], (list, tuple)) else [h["ring"]]  # (per order, or one number for all wood)
    step = 0
    tip_life = any(h["tip_life"])
    slowing = any(h["slowing"])
    for step in range(steps):
        for when, c in cuts:  # a cut made now: the wood goes, the stubs sprout (pollard, coppice, a lopped limb)
            if step not in when or T.n < 3:
                continue
            Pm_ = T.pos * unit
            if "under" in c:
                hit = (T.order > 0) & (Pm_[:, 2] < float(c["under"]))
            elif "below" in c:
                hit = (~T.main) & (T.order == 1) & (Pm_[T.parent, 2] < float(c["below"]))
            else:
                hit = _inside(Pm_, c)
            hit[:2] = False
            gone = hit.copy()
            par_ = T.parent
            for i in range(2, T.n):
                gone[i] |= gone[par_[i]]
            if not gone.any():
                cut_log.append({"year": round(step * yps, 1), "nodes": 0, "stubs": 0})
                continue
            first_ = gone & ~gone[par_]
            stubs = np.unique(par_[first_])
            new = T.keep(~gone)
            for g in guides:
                if g["node"] >= 0:
                    g["node"] = int(new[g["node"]])
                    if g["node"] < 0:
                        g["done"] = True
            stubs = new[stubs]
            stubs = stubs[stubs > 0]
            if float(c.get("boll", 1.0)) > 1.0:
                for q_ in stubs:
                    k_b = int(T.key[q_])
                    bolls[k_b] = min(bolls.get(k_b, 1.0) + (float(c["boll"]) - 1.0) * 0.5, float(c["boll"]))
            k_sp = int(c.get("sprouts", 4))
            if k_sp:
                more = [stubs]
                for _ in range(int(c.get("sprout_nodes", 1)) - 1):  # ... and the nodes just under the cut
                    q = T.parent[more[-1]]
                    more.append(q[q > 0])
                sp = np.unique(np.concatenate(more))
                if len(sp) > 12:  # (re-cutting a head leaves a stub per rod: only the stoutest dozen sprout again)
                    sp = sp[np.lexsort((T.born[sp], T.order[sp]))[:12]]
                T.nb[sp] = k_sp
                T.budstep[sp] = step
                T.starve[sp] = 0
            cut_log.append({"year": round(step * yps, 1), "nodes": int(gone.sum()), "stubs": int(len(stubs))})
        n = T.n
        P = T.pos
        age_t = (step + 1) / steps
        lam = np.array(lam_young, float)
        if h.get("apical_old") is not None:
            f0, f1 = h["apical_fade"]
            w = float(np.clip((age_t - f0) / max(f1 - f0, 1e-6), 0, 1))
            lam[0] = lam[0] + w * (h["apical_old"] - lam[0])
        # ---- 1. light
        leafy = (step - T.born) < h["leaf_steps"]
        leafy[0] = False
        cell = 1.0
        lo = P.min(0) - (sd + 3)
        hi = P.max(0) + (sd + 3)
        while np.prod((hi - lo) / cell) > 6e6:
            cell *= 1.5
        dims = tuple(np.ceil((hi - lo) / cell).astype(int) + 1)
        wl = np.clip(T.vig.astype(float), 0.05, 1.5)
        S = _shadow(P[leafy] / cell, lo / cell, dims, sa, sb, sd, tilt, wl[leafy], tail=float(h["shadow_tail"]))
        ij = np.clip(((P - lo) / cell).astype(np.int64), 1, np.array(dims) - 2)
        s_here = S[ij[:, 0], ij[:, 1], ij[:, 2]]
        Qn = np.clip(1.0 - s_here + sa * leafy * wl, 0.0, 1.0)
        Sg = ndimage.gaussian_filter(S, 1.5)  # (the raw grid's gradient stacks shoots in voxel layers)
        G = np.stack([Sg[ij[:, 0] + 1, ij[:, 1], ij[:, 2]] - Sg[ij[:, 0] - 1, ij[:, 1], ij[:, 2]],
                      Sg[ij[:, 0], ij[:, 1] + 1, ij[:, 2]] - Sg[ij[:, 0], ij[:, 1] - 1, ij[:, 2]],
                      Sg[ij[:, 0], ij[:, 1], ij[:, 2] + 1] - Sg[ij[:, 0], ij[:, 1], ij[:, 2] - 1]], 1)
        V = -G / (2 * sa)
        V = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1.0)  # at most a unit pull
        Pm = P * unit
        top = P[:, 2].max()
        if stand is not None:  # a closed stand: the canopy's top rises with the tree; light falls off below it and away from the gap
            gap = stand.get("gap", 0.18) * max(top, 4.0)
            if env.get("spacing") or stand.get("spacing"):  # m between the stand's trees: its own share of the canopy
                gap = min(gap, 0.55 * float(env.get("spacing") or stand["spacing"]) / unit)
            depth = stand.get("depth", 0.35) * max(top, 4.0)
            zc = top * stand.get("height", 1.0)
            r = np.linalg.norm(P[:, :2], axis=1)
            side = np.clip((r - gap) / max(0.5 * gap, 1e-6), 0, 1) * np.clip((zc - P[:, 2]) / max(depth, 1e-6), 0, 1.5)  # (over a whole gap width, crowns 4 m apart interlocked 8 m wide)
            # the canopy's own shade deepens steadily below its top (a step at one depth made a stand tree's crown all or nothing:
            # live to the ground or a tuft, on a hair of `stand_shed`)
            below = np.clip((zc - P[:, 2]) / max(2.0 * depth, 1e-6), 0, 1) * stand.get("floor", 0.8)
            closed = np.ones(n)
            if stand.get("open_side") is not None:  # the open side keeps its light
                od = _norm(np.asarray(list(stand["open_side"])[:2], float))
                we = np.clip(0.5 - 0.5 * (P[:, :2] @ od) / max(gap, 1e-6), 0, 1)
                side, below = side * we, below * we
                closed = we
            Qn = np.clip(Qn - stand.get("strength", 1.0) * (side + below), 0, 1)
            V[:, :2] -= 0.5 * stand.get("strength", 1.0) * side[:, None] * _norm(np.c_[P[:, 0], P[:, 1]] + 1e-9)
        for nb_ in env.get("neighbours") or []:  # crowns beside it: {"at": [x, y], "height", "radius"} (m)
            c = np.asarray(nb_["at"], float)
            d = np.linalg.norm(Pm[:, :2] - c, axis=1)
            hh = nb_.get("height", 10.0) * min(1.0, age_t * 1.2)
            sh = np.clip(1 - d / (nb_.get("radius", 4.0) * 2.0), 0, 1) * np.clip((hh - Pm[:, 2]) / (0.3 * hh + 1e-6), 0, 1)
            Qn = np.clip(Qn - sh, 0, 1)
            V[:, :2] += 0.6 * sh[:, None] * _norm(Pm[:, :2] - c)
        if envl is not None:
            out_ = _envelope(Pm, envl)
            Qn = np.clip(Qn - envl.get("strength", 1.0) * out_, 0, 1)
        if wind:  # the windward side's buds suffer
            cen = P[leafy].mean(0) if leafy.any() else P.mean(0)
            rad = max(np.linalg.norm(P[:, :2] - cen[:2], axis=1).max(), 1.0)
            ex = np.clip(-((P - cen) @ wdir) / rad, 0, 1) * np.clip(P[:, 2] / max(top, 1), 0, 1)
            Qn = np.clip(Qn * (1 - wstr * ex), 0, 1)
        cut = np.zeros(n, bool)
        for vol in prunes:  # (a prune with no from_year is a cut on the finished tree: after the loop)
            if "from_year" in vol and step >= int(round(vol["from_year"] / yps)):
                if "under" in vol:
                    c_ = (T.order > 0) & (Pm[:, 2] < float(vol["under"]))
                elif "below" in vol:  # clear the trunk: laterals leaving it under this height
                    c_ = (~T.main) & (T.order == 1) & (Pm[T.parent, 2] < float(vol["below"]))
                else:
                    c_ = _inside(Pm, vol)
                cut |= c_ & ~T.pin
        Qn[cut] = 0
        # ---- 2. bud fate
        dead_bud = (step - np.maximum(T.born, T.budstep)) > h["bud_life"]
        T.nb[dead_bud] = 0
        qtip = Qn * T.tip
        qlat = Qn * T.nb
        Q = np.zeros(n)
        size = np.zeros(n, np.int64)
        _collect(T.parent, qtip + qlat, Q, size)
        v = np.zeros(n)
        vtip = np.zeros(n)
        vlat = np.zeros(n)
        _distribute(T.parent, T.main, T.order, Q, qtip, qlat, lam, h["vigour"] * Q[0], v, vtip, vlat)
        # ---- 4 (before growth, on last step's light). shedding and pruning
        dead = np.zeros(n, bool)
        thr_ = np.full(n, float(h["shed"]))
        if stand is not None:  # a stand's shade-bearers self-prune (`stand_shed`); on an edge's open side they keep their skirt
            thr_ = thr_ + h["stand_shed"] * closed
        # wood past its last living branch (no tip, no bud, no leaf beyond it) is dead: it goes like any shaded branch
        # (a limb whose own tip had stopped trailed on for decades as a bare sagging snake)
        LQ = np.zeros(n)
        _collect(T.parent, leafy.astype(float), LQ, np.zeros(n, np.int64))
        cut |= (Q <= 0) & (LQ <= 0) & (T.order > 0) & ~T.pin & ((step - T.born) >= h["shed_age"] + 2)
        _shed(T.parent, T.main, T.born, T.pin, Q, size, cut, step, thr_, h["shed_age"], dead)
        if dead.any():
            # the pipe model remembers what it carried
            area = np.zeros(n)
            _pipe(T.parent, T.mem, 1.0, h["pipe"], area)
            first = dead & ~dead[T.parent]
            if h["dead_keep"]:  # a limb off the trunk dies but stays for years: its wood is remembered as it was, and
                # put back at the end as dead wood, as far decayed as its years (twigs fallen, broken back, drooping)
                roots_ = first & (T.order == 1) & (T.order[T.parent] == 0)
                if stand is not None:  # in a stand the branches a limb loses stay on it too: its dead twigs
                    roots_ |= first & (T.order >= 2)
                roots_ = np.flatnonzero(roots_)
                if len(roots_):
                    own = np.full(n, -1)
                    own[roots_] = roots_
                    for j_ in np.flatnonzero(dead):  # (parents come first)
                        if own[j_] < 0:
                            own[j_] = own[T.parent[j_]]
                    rad_m = area * h["tip_radius"] + (step + 1 - T.born) * (yps * _per(ring_l, T.order))
                    for i_ in roots_:
                        ix = np.flatnonzero(own == i_)[:DEAD_NODES]
                        loc = {int(q_): k_ for k_, q_ in enumerate(ix)}
                        dead_log_.append({"pk": int(T.key[T.parent[i_]]), "step": step, "key": T.key[ix].copy(), "root": int(T.order[i_]),
                                          "pos": (T.pos[ix] - T.pos[T.parent[i_]]) * unit,
                                          "par": np.array([loc.get(int(T.parent[q_]), -1) for q_ in ix]), "rad": rad_m[ix].copy(),
                                          "order": T.order[ix].copy(), "axis": T.axis[ix].copy(), "born": T.born[ix].copy()})
            np.add.at(T.mem, T.parent[first], 0.6 * area[first] ** h["pipe"])
            keep = ~dead
            new = T.keep(keep)
            for g in guides:
                if g["node"] >= 0:
                    g["node"] = int(new[g["node"]])
                    if g["node"] < 0:
                        g["done"] = True
            vtip, vlat, V, Qn = vtip[keep], vlat[keep], V[keep], Qn[keep]
            n = T.n
        # ---- 3. shoots
        order = T.order.astype(int)
        nmax = _per(h["shoot_max"], order).astype(int)
        nt = np.minimum(np.floor(vtip).astype(int), nmax) * T.tip
        if h["leader"] and age_t <= h["leader_until"]:
            lead = T.tip & (T.order == 0)
            nt[lead] = np.maximum(nt[lead], int(h["leader"]))
        gnode = {g["node"]: g for g in guides if g["node"] >= 0 and not g["done"]}
        for i in gnode:
            nt[i] = 0  # a guide's tip grows along its path, below
        per_bud = np.where(T.nb > 0, vlat / np.maximum(T.nb, 1), 0)
        ob = np.minimum(order + 1, 99)
        can = (_u(T.key, 7) < _per(h["bud_break"], ob)) | (T.budstep > 0)  # (a cut's sprouts always can)
        if h["bud_each"]:
            can = can | (T.nb > 1)  # (each bud is drawn below)
        nl = np.minimum(np.floor(per_bud).astype(int), _per(h["shoot_max"], ob).astype(int)) * (T.nb > 0) * can
        nl[order >= h["max_order"]] = 0
        # starving tips die
        st = T.starve
        hungry = T.tip & (nt == 0)
        st[hungry] = np.minimum(st[hungry] + 1, 200)
        st[~hungry] = 0
        T.tip[(st > 3) & (T.order > 0) & ~T.pin] = False
        if tip_life:  # determinate axes: after their years they stop reaching (their buds may still break)
            ab = np.fromiter((a.get("born", 0) for a in axes), np.int64, len(axes))
            lf_ = _per(h["tip_life"], order)
            old = T.tip & (lf_ > 0) & (step - ab[T.axis] >= lf_) & ~T.pin
            T.tip[old] = False
            nt[old] = 0

        par = T.parent
        dir_here = _norm(T.pos - T.pos[par])
        dir_here[0] = [0, 0, 1]
        up = np.array([0.0, 0.0, 1.0])

        def shoots(src, count, d0, order_new, keys, vres, is_main, phi0, axis_ids):
            """Grow `count[k]` metamers from node src[k] in direction d0[k]; returns the last node of each."""
            last = src.copy()
            d = d0.copy()
            # a shoot keeps turning the way it was turning: crookedness as curves, not a kink at every node
            turn = np.where(is_main[:, None], dir_here[src] - dir_here[par[src]], 0.0)
            alive = np.arange(len(src))
            ln = (0.45 + 0.55 * np.clip(vres / _per(h["shoot_max"], order_new), 0, 1)) * _per(h["length"], order_new)
            ln = ln * (1 + _per(h["uneven"], order_new) * (2 * _u(_mix(axis_ids.astype(np.uint64) + seed), 9) - 1))
            if slowing:  # an old axis creeps
                sl_ = _per(h["slowing"], order_new)
                born_ = np.fromiter((axes[a_].get("born", 0) for a_ in axis_ids), np.float64, len(axis_ids))
                ln = np.where(sl_ > 0, ln / (1 + (step - born_) / np.maximum(sl_, 1e-9)), ln)
            if h["limb_pace"]:  # no side shoot outgrows the leader's pace at this age
                s0_ = _per(h["slowing"], np.zeros(1, int))[0]
                lead_ = _per(h["shoot_max"], np.zeros(1, int))[0] * _per(h["length"], np.zeros(1, int))[0] / (1 + (step / s0_ if s0_ > 0 else 0.0))
                cap_ = _per(h["limb_pace"], order_new) * lead_ / np.maximum(_per(h["shoot_max"], order_new), 1)
                ln = np.where(order_new > 0, np.minimum(ln, cap_), ln)
            eta = _per(h["tropism"], order_new)
            jit = _per(h["jitter"], order_new)
            pl = _per(h["plagio"], order_new)
            el = np.radians(_per(h["elevation"], order_new))
            nbuds = _per(h["buds"], np.minimum(order_new, 99)).astype(int)
            whorl = _per(h["whorl"], order_new).astype(bool)
            div = np.radians(_per(h["divergence"], order_new))
            for j in range(int(count.max()) if len(count) else 0):
                a = alive[count[alive] > j]
                if not len(a):
                    break
                kj = _child(keys[a], 10 + j)
                rnd = np.stack([_u(kj, 1), _u(kj, 2), _u(kj, 3)], 1) * 2 - 1
                mom = 0.65 * np.clip(jit[a] / 0.3, 0, 1)
                # a side shoot's first segment leaves at its own angle: light and tropism bend what follows (they were
                # folding it back along its parent: angle 40 measured 23)
                w1 = np.where(is_main[a], 1.0, 0.2)[:, None] if j == 0 else 1.0
                dd = d[a] + w1 * (h["light"] * V[src[a]] + eta[a, None] * up + jit[a, None] * 0.6 * rnd) + mom[:, None] * turn[a]
                fw = _per(h["force_orders"], order_new[a])[:, None]
                for fv, fo in forces:
                    m_ = np.ones(len(a), bool) if fo is None else np.isin(order_new[a], fo)
                    dd = dd + (m_[:, None] * fw if fo is None else m_[:, None]) * fv
                if wind:
                    dd = dd + 0.5 * wstr * wdir * fw
                dd = _norm(dd)
                if pl[a].any():  # toward a set elevation, keeping the heading
                    hz = _norm(dd * [1, 1, 0] + 1e-9 * d[a])
                    tgt = hz * np.cos(el[a])[:, None] + up * np.sin(el[a])[:, None]
                    dd = _norm(dd + pl[a, None] * (tgt - dd))
                p0 = T.pos[last[a]]
                o = dd * ln[a, None]
                # the ground: nothing grows into it. A hanging shoot stops over it (`ground_clear`); any other slides
                # along it, and its own pull to the light turns it up from there
                end = p0 + o
                fl_ = g0u + end[:, :2] @ gvu + clear_u
                low_ = end[:, 2] < fl_
                if low_.any():
                    # (hanging: steeply down, or an order that hangs by habit; a side shoot's first segment always
                    # grows: its axis is counted on)
                    stop = low_ & ((dd[:, 2] < -0.5) | (eta[a] < -0.3)) & ((j > 0) | is_main[a])
                    sl_ = low_ & ~stop
                    oz = np.minimum(np.maximum(fl_ - p0[:, 2], 0.35 * ln[a]), 0.9 * ln[a])  # (its end turns up, ~20 deg; from under the line it climbs to it)
                    hl = np.sqrt(np.maximum(ln[a] ** 2 - oz ** 2, 1e-12))
                    hz_ = _norm(dd * [1, 1, 0] + 1e-9)
                    o[sl_] = (hz_ * hl[:, None] + up * oz[:, None])[sl_]
                    dd[sl_] = _norm(o[sl_])
                    if stop.any():
                        count[a[stop]] = j  # (it ends here; its tip lives and may try again when the tree has moved)
                        a, kj, dd, o, p0 = a[~stop], kj[~stop], dd[~stop], o[~stop], p0[~stop]
                        if not len(a):
                            continue
                Rp = T.R[last[a]]
                off = np.einsum("nji,nj->ni", Rp, o)  # into the parent's rest frame
                endm = (count[a] == j + 1)
                nbn = np.where(whorl[a] & ~endm, 0, nbuds[a])
                nbn[order_new[a] >= h["max_order"]] = 0
                nbn[(order_new[a] == 0) & ((p0[:, 2] + o[:, 2]) * unit < h["clear"])] = 0
                ids = T.add(len(a), pos=p0 + o, off=off, parent=last[a], order=order_new[a],
                            main=(is_main[a] if j == 0 else True), born=step, key=kj, tip=False, nb=nbn,
                            phi=phi0[a] + (j + 1) * div[a], R=Rp, guide=-1, axis=axis_ids[a], vig=ln[a])
                last[a] = ids
                turn[a] = dd - d[a]
                d[a] = dd
            return last

        # terminal shoots
        ti = np.flatnonzero(nt > 0)
        if len(ti):
            T.tip[ti] = False
            last = shoots(ti, nt[ti], dir_here[ti], order[ti], T.key[ti], vtip[ti], np.ones(len(ti), bool), T.phi[ti],
                          T.axis[ti].copy())
            T.tip[last] = True
        # lateral shoots: every bud of the node breaks together (a whorl)
        li = np.flatnonzero(nl > 0)
        if len(li):
            src, bud = [], []
            for b in range(int(T.nb[li].max())):
                m_ = li[T.nb[li] > b]
                src.append(m_)
                bud.append(np.full(len(m_), b))
            src, bud = np.concatenate(src), np.concatenate(bud)
            o_new = order[src] + 1
            a_ = dir_here[src]
            plane = _per(h["plane"], o_new).astype(bool)
            ref = np.where(np.abs(a_[:, 2:3]) > 0.95, np.array([[1.0, 0, 0]]), up[None])
            u_ = _norm(np.cross(a_, ref))
            w_ = np.cross(u_, a_)
            phi = np.where(plane, np.round(T.phi[src] / math.pi) * math.pi, T.phi[src]) + 2 * math.pi * bud / T.nb[src]
            ang = np.radians(_per(h["angle"], o_new - 1)) * (0.85 + 0.3 * _u(T.key[src], 20 + 1))  # by the PARENT's order
            d0 = a_ * np.cos(ang)[:, None] + (u_ * np.cos(phi)[:, None] + w_ * np.sin(phi)[:, None]) * np.sin(ang)[:, None]
            keys = _child(T.key[src], 100 + bud)
            if h["bud_each"]:
                ok_ = (T.nb[src] <= 1) | (_u(keys, 7) < _per(h["bud_break"], o_new)) | (T.budstep[src] > 0)
                src, bud, o_new, d0, keys = src[ok_], bud[ok_], o_new[ok_], d0[ok_], keys[ok_]
            if len(replaced):
                ok_ = ~np.isin(_child(keys, 10), replaced)
                src, bud, o_new, d0, keys = src[ok_], bud[ok_], o_new[ok_], d0[ok_], keys[ok_]
            ax0 = len(axes)
            for k_ in range(len(src)):
                new_axis(o_new[k_])
            first = T.n + np.arange(len(src))  # (pass 0 makes every shoot's first metamer, in order)
            last = shoots(src, nl[src], d0, o_new, keys, per_bud[src], np.zeros(len(src), bool),
                          _u(keys, 5) * 2 * math.pi, ax0 + np.arange(len(src)))
            for k_, f_ in enumerate(first):
                axes[ax0 + k_]["node"] = int(f_)
            T.tip[last] = True
            T.nb[li] = 0
        # ---- guides
        for gi, g in enumerate(guides):
            if g["done"] or step < g["start"]:
                continue
            pts, cum = g["pts"], g["cum"]
            if g["node"] < 0:  # attach: a lateral from the nearest wood, the stoutest of what's about equally near
                dist = np.linalg.norm(T.pos - pts[0], axis=1)
                cand = np.ones(T.n, bool)
                if g["on"]:  # ... of the guide (or "trunk") it's drawn on
                    on = next((q for q in guides if q["name"] == g["on"]), None)
                    cand = (T.order == 0) if g["on"] == "trunk" else \
                        (T.axis == on["axis"]) if on is not None and "axis" in on else cand
                    if not cand.any():
                        cand = np.ones(T.n, bool)
                dist = np.where(cand, dist, 1e9)
                near = np.flatnonzero(dist <= dist.min() + 0.75)
                near = near[T.order[near] == T.order[near].min()]
                base = int(near[np.argmin(dist[near])])
                g["node"], g["axis"] = base, new_axis(int(T.order[base]) + 1, g["name"])
                g["first"] = True
            left = cum[-1] - g["s"]
            remaining = max((g["end"] if g["end"] is not None else steps) - step, 1)
            want = left / remaining * g["vigour"] if g["end"] is not None else 2.2 * g["vigour"]
            nm = int(max(1, min(math.ceil(want / 1.0), 8)))
            ln = min(left, max(want, 0.6)) / nm
            o_g = axes[g["axis"]]["order"]
            node = g["node"]
            if not g.get("first") and T.guide[node] == gi:  # (never the wood it leaves: that was killing a young trunk's leader)
                T.tip[node] = False
            for j in range(nm):
                if g["s"] >= cum[-1] - 1e-6:
                    break
                g["s"] = min(g["s"] + ln, cum[-1])
                p = _along(pts, cum, g["s"])
                kj = _child(_child(seed, 5000 + gi), int(round(g["s"] * 16)))
                nbn = int(_per(h["buds"], o_g)) if o_g < h["max_order"] else 0
                if (o_g == 0 and p[2] * unit < h["clear"]) or g["s"] * unit < g["bare"]:
                    nbn = 0  # (a drawn trunk has its clear bole too; a limb may be drawn bare for its first metres)
                i_ = T.add(1, pos=p, pinpos=p, off=p - T.pos[node], parent=node, order=o_g,
                           main=(not g.pop("first", False)) or o_g == 0, born=step, key=kj, tip=False, nb=nbn,
                           phi=T.phi[node] + math.radians(float(_per(h["divergence"], o_g))), R=np.eye(3),
                           guide=gi, axis=g["axis"], pin=not g["free"], vig=1.0)[0]
                axes[g["axis"]].setdefault("node", int(i_))
                node = int(i_)
            g["node"] = node
            T.tip[node] = True
            if g["s"] >= cum[-1] - 1e-6:
                g["done"] = True  # the path is drawn: the tip grows on by itself
        # ---- 5. widths, bending
        n = T.n
        area = np.zeros(n)
        _pipe(T.parent, T.mem, 1.0, h["pipe"], area)
        rad = area * (h["tip_radius"] / unit) + (step + 1 - T.born) * (yps * _per(ring_l, T.order) / unit)
        leafy = (step - T.born) < h["leaf_steps"]
        if h["sag"] > 0:
            _pose(T.parent, T.off, T.pin, T.pinpos, T.order, rad, leafy, T.theta, h["sag"], h["sag_max"],
                  0.0, T.pos, T.R, g0u + 0.03 / unit, gvu[0], gvu[1])
        if log:
            log(f"step {step}: {T.n} nodes, top {T.pos[:, 2].max() * unit:.1f} m")

    n = T.n
    area = np.zeros(n)
    _pipe(T.parent, T.mem, 1.0, h["pipe"], area)
    radius = area * h["tip_radius"] + (steps - T.born) * (yps * _per(ring_l, T.order))
    radius[0] = radius[1] if n > 1 else radius[0]
    pos = T.pos * unit
    # the foot flares
    radius = radius * (1 + (h["flare"] - 1) * np.exp(-pos[:, 2] / max(h["flare_height"], 1e-6)) * (T.order == 0))
    leafy = (steps - 1 - T.born) < h["leaf_steps"]
    leafy[0] = False
    kids = np.bincount(T.parent[1:], minlength=n)
    first = {}
    for i in range(1, n):
        first.setdefault(int(T.axis[i]), i)
    for i, a in enumerate(axes):
        a.pop("node", None)
        if i in first:
            a["node"] = first[i]
    ax_names = {}
    for i, a in enumerate(axes):
        if a.get("guide"):
            ax_names[a["guide"]] = i
    out = {"pos": pos, "parent": T.parent.copy(), "radius": radius, "order": T.order.copy(), "born": T.born.copy(),
           "axis": T.axis.copy(), "key": T.key.copy(), "tip": T.tip.copy(), "leafy": leafy, "main": T.main.copy(),
           "pin": T.pin.copy(), "ends": kids == 0, "unit": unit, "steps": steps, "axes": axes, "guides": ax_names,
           "height": float(pos[:, 2].max()), "spec": s}
    if s.get("trunk_diameter"):  # girth in metres: thick wood scaled to it, twigs left as they are
        r1, tip_r = float(radius[1]), 3 * h["tip_radius"]
        k_ = 0.5 * float(s["trunk_diameter"]) / max(r1, 1e-9)
        w_ = np.clip((radius - tip_r) / max(r1 - tip_r, 1e-9), 0, 1) ** 0.5
        if s.get("limb_diameter"):  # the trunk alone
            w_ = w_ * (T.order == 0)
        out["radius"] = radius = radius * (1 + (k_ - 1) * w_)
        if s.get("trunk_taper") is not None:  # a column: the trunk keeps its girth to its top, whatever it carries
            tr = np.flatnonzero(T.order == 0)
            zt = max(float(pos[tr, 2].max()), 1e-6)
            want = 0.5 * float(s["trunk_diameter"]) * (1 - float(s["trunk_taper"]) * pos[tr, 2] / zt)
            radius[tr] = np.maximum(radius[tr], want) if not s.get("cuts") else want
            out["radius"] = radius
    elif stand is not None and (env.get("spacing") or stand.get("spacing")) and h["sdi_max"]:
        # a stand's stems are as stout as its stocking allows (Reineke 1933: N x (dbh / 25 cm)^1.6 <= the species' most):
        # the pipe model and the ring sized a tree by its own wood alone, and 3 m apart stood 42 cm stems (173 m2 / ha)
        sp_ = float(env.get("spacing") or stand["spacing"])
        cap = 0.25 * (float(h["sdi_max"]) / (1e4 / sp_ ** 2)) ** (1 / 1.6) * (1.0 if stand.get("open_side") is None else 1.25)
        tr = np.flatnonzero(T.order == 0)
        if len(tr) > 2 and pos[tr, 2].max() > 1.3:
            dbh = 2 * float(np.interp(1.3, pos[tr, 2], radius[tr]))
            if dbh > cap:
                r1, tip_r = 0.5 * dbh, 3 * h["tip_radius"]
                w_ = np.clip((radius - tip_r) / max(r1 - tip_r, 1e-9), 0, 1) ** 0.5
                out["radius"] = radius = radius * (1 + (cap / dbh - 1) * w_)
                out["stand_dbh_cap"] = round(cap, 3)
    if s.get("limb_diameter") and (T.order == 1).any():  # limbs sized by themselves: a fat trunk under ordinary limbs
        o1 = np.flatnonzero((T.order == 1) & (T.order[T.parent] == 0))
        rl, tip_r = float(radius[o1].max()), 3 * h["tip_radius"]
        k_ = 0.5 * float(s["limb_diameter"]) / max(rl, 1e-9)
        w_ = np.clip((radius - tip_r) / max(rl - tip_r, 1e-9), 0, 1) ** 0.5 * (T.order > 0)
        out["radius"] = radius = radius * (1 + (k_ - 1) * w_)

    def subset(keep, leafless=False):
        nonlocal n
        keep = keep.copy()
        keep[:2] = True
        par0 = out["parent"]
        for i in range(2, len(keep)):  # (parents come first: a cut takes everything it carries)
            keep[i] &= keep[par0[i]]
        new = -np.ones(len(keep), np.int64)
        new[keep] = np.arange(int(keep.sum()))
        for k_ in ("pos", "radius", "order", "born", "axis", "key", "tip", "leafy", "main", "pin", "dead", "shade_dead"):
            out[k_] = out[k_][keep]
        par = new[par0[keep]]
        par[0] = 0
        out["parent"] = par.astype(np.int32)
        n = int(keep.sum())
        out["ends"] = np.bincount(par[1:], minlength=n) == 0
        if leafless:
            out["leafy"] = np.zeros(n, bool)
        out["height"] = float(out["pos"][:, 2].max())
        first = {}
        for i in range(1, n):
            first.setdefault(int(out["axis"][i]), i)
        for i, a in enumerate(axes):
            a.pop("node", None)
            if i in first:
                a["node"] = first[i]

    if bolls:  # swell the cut ends, easing out ~4 radii down the wood that carries them
        r_ = out["radius"]
        fac = np.ones(n)
        for i_ in np.flatnonzero(np.isin(out["key"], np.array(list(bolls), np.uint64))):
            if out["order"][i_] > 1:
                continue  # (a head, not every rod's stub)
            k_b, q_, d_ = bolls[int(out["key"][i_])], int(i_), 0.0
            reach = max(4.0 * float(r_[i_]), 0.3)
            while q_ > 0 and d_ < reach:
                fac[q_] = max(fac[q_], 1 + (k_b - 1) * (1 - d_ / reach) ** 2)
                p_ = int(out["parent"][q_])
                d_ += float(np.linalg.norm(out["pos"][q_] - out["pos"][p_]))
                q_ = p_
        out["radius"] = r_ * fac
    out["dead"] = np.zeros(n, bool)
    out["shade_dead"] = np.zeros(n, bool)
    if dead_log_:  # the limbs the shade killed within `dead_keep` years, as dead wood on the trunk
        where = {int(k_): i_ for i_, k_ in enumerate(out["key"])}
        add = {k_: [] for k_ in ("pos", "parent", "radius", "order", "born", "axis", "key")}
        keep_y = float(h["dead_keep"])
        dk = {**DEAD, **(s.get("deadwood") or {})}
        n_add = 0
        for L_ in sorted(dead_log_, key=lambda e_: (e_["root"], e_["step"])):  # (limbs first: their dead branches hang on them)
            age_ = (steps - L_["step"]) * yps
            if age_ > keep_y or L_["pk"] not in where or len(L_["pos"]) == 0:
                continue
            f_ = age_ / keep_y  # 0 = just died .. 1 = about to fall
            Pd, pr_, rd = L_["pos"], L_["par"], L_["rad"]
            m0 = len(Pd)
            u1, u2, u3 = (float(_u(_child(np.uint64(L_["key"][0]), 70 + q_), 1)) for q_ in range(3))
            seg_ = np.linalg.norm(Pd - np.where(pr_[:, None] >= 0, Pd[np.maximum(pr_, 0)], 0.0), axis=1)
            along = np.zeros(m0)
            for q_ in range(m0):
                along[q_] = seg_[q_] + (along[pr_[q_]] if pr_[q_] >= 0 else 0.0)
            reach = float(along.max())
            # broken back with the years (the oldest, lowest whorls are short spurs), fine twigs first
            ok_ = along <= max(reach * (1 - dk["break"] * f_ ** 0.8) * (0.7 + 0.3 * u1), min(reach, dk["stub"]))
            un = _u(L_["key"], 73)
            ok_ &= (rd >= (dk["twig"][0] + (dk["twig"][1] - dk["twig"][0]) * f_) * (0.5 + un)) | (np.arange(m0) == 0)
            for q_ in range(1, m0):
                ok_[q_] &= pr_[q_] >= 0 and ok_[pr_[q_]]
            ok_[0] = True
            # it hangs: turned down about its foot, and bowed down along its length
            hd = _norm(Pd[min(m0 - 1, 2)] * [1, 1, 0] + 1e-9)
            ang = math.radians(dk["droop"][0] + (dk["droop"][1] - dk["droop"][0]) * f_) * (0.6 + 0.8 * u2)
            hx = Pd @ hd
            ca_, sa_ = math.cos(ang), math.sin(ang)
            Pn = Pd + hd[None] * (hx * ca_ + Pd[:, 2] * sa_ - hx)[:, None]
            Pn[:, 2] = -hx * sa_ + Pd[:, 2] * ca_ - dk["bow"] * (0.4 + 0.6 * f_) * along ** 2 / max(reach, 1e-6)
            w_ = where[L_["pk"]]
            base_ = out["pos"][w_] if w_ < n else np.asarray(add["pos"][w_ - n])
            new_i = -np.ones(m0, np.int64)
            amap = {}
            for q_ in np.flatnonzero(ok_):
                new_i[q_] = n + n_add
                where.setdefault(int(L_["key"][q_]), n + n_add)
                n_add += 1
                a0 = int(L_["axis"][q_])
                if a0 not in amap:
                    amap[a0] = len(axes)
                    axes.append({"order": int(L_["order"][q_]), "guide": None, "born": int(L_["born"][q_]), "dead": True})
                add["pos"].append(base_ + Pn[q_])
                add["parent"].append(where[L_["pk"]] if pr_[q_] < 0 else int(new_i[pr_[q_]]))
                add["radius"].append(max(float(rd[q_]) * dk["shrink"], 0.0015))
                add["order"].append(int(L_["order"][q_]))
                add["born"].append(int(L_["born"][q_]))
                add["axis"].append(amap[a0])
                add["key"].append(_child(np.uint64(L_["key"][q_]), 80))
        m_ = len(add["pos"])
        if m_:
            out["pos"] = np.vstack([out["pos"], np.asarray(add["pos"])])
            out["parent"] = np.concatenate([out["parent"], np.asarray(add["parent"], np.int32)])
            out["radius"] = np.concatenate([out["radius"], add["radius"]])
            out["order"] = np.concatenate([out["order"], np.asarray(add["order"], out["order"].dtype)])
            out["born"] = np.concatenate([out["born"], np.asarray(add["born"], out["born"].dtype)])
            out["axis"] = np.concatenate([out["axis"], np.asarray(add["axis"], out["axis"].dtype)])
            out["key"] = np.concatenate([out["key"], np.asarray(add["key"], np.uint64)])
            for k_, val in (("tip", False), ("leafy", False), ("main", True), ("pin", False)):
                out[k_] = np.concatenate([out[k_], np.full(m_, val)])
            out["dead"] = np.concatenate([out["dead"], np.ones(m_, bool)])
            out["shade_dead"] = np.concatenate([np.zeros(n, bool), np.ones(m_, bool)])  # (not an artist's dead wood)
            n += m_
            out["ends"] = np.bincount(out["parent"][1:], minlength=n) == 0
            for i_ in range(n - m_, n):
                axes[int(out["axis"][i_])].setdefault("node", i_)
    # nothing lies under the ground: wood that drooped into it lies along it
    gz_ = ground_at(s, out["pos"][:, :2]) + 0.03 + out["radius"]
    low_ = (out["pos"][:, 2] < gz_) & (out["order"] > 0)
    out["pos"][low_, 2] = gz_[low_]
    grounded_ = int(low_.sum())
    cut_n = 0
    for vol in prunes:  # cuts on the finished tree: nothing else changes
        if "from_year" in vol:
            continue
        P_, o_ = out["pos"], out["order"]
        if "under" in vol:  # nothing hangs under this height (the trunk stays)
            c_ = (o_ > 0) & (P_[:, 2] < float(vol["under"]))
        elif "below" in vol:  # limbs that leave the trunk under this height
            c_ = (~out["main"]) & (o_ == 1) & (P_[out["parent"], 2] < float(vol["below"]))
        else:
            c_ = _inside(P_, vol)
        c_ &= ~out["pin"]
        if c_.any():
            before = n
            subset(~c_)
            cut_n += before - n
    dead_log = []
    for dd in s.get("dead") or []:  # dead wood kept on the live tree: a stag-headed oak's antlers, a snag limb
        if "limb" in dd:
            ai_ = find_limb(out, dd["limb"])
            if ai_ is None or "node" not in out["axes"][ai_]:  # (an edit regrew the tree without it: said, not fatal)
                dead_log.append({"what": f"limb {dd['limb']}", "missing": True})
                continue
            m_ = np.zeros(n, bool)
            m_[out["axes"][ai_]["node"]] = True
            if dd.get("from"):  # only past this many metres along it
                nd_ = stout_path(out, out["axes"][ai_]["node"])
                cum_ = np.cumsum(np.linalg.norm(out["pos"][nd_] - out["pos"][out["parent"][nd_]], axis=1))
                m_[:] = False
                later = nd_[cum_ >= float(dd["from"])]
                if len(later):
                    m_[later[0]] = True
        elif "under" in dd or "below" in dd:
            raise ValueError("dead takes box, sphere, above or a limb")
        else:
            m_ = _inside(out["pos"], dd)
            m_[:2] = False
        for i_ in range(2, n):
            m_[i_] |= m_[out["parent"][i_]]
        out["dead"] |= m_
        out["leafy"] = out["leafy"] & ~m_
        gone = m_ & (out["radius"] < float(dd.get("min_radius", 0.012)))
        zs_ = out["pos"][m_][:, 2] if m_.any() else np.zeros(1)
        before_ = n
        if gone.any():
            subset(~gone)
        dead_log.append({"what": f"limb {dd['limb']}" if "limb" in dd else next(f"{k_} {dd[k_]}" for k_ in ("above", "box", "sphere") if k_ in dd),
                         "nodes": int(m_.sum()), "broken_off": int(before_ - n), "low": round(float(zs_.min()), 1), "high": round(float(zs_.max()), 1)})
    dec = s.get("decay")
    if dec and dec.get("min_radius"):
        subset(out["radius"] >= float(dec["min_radius"]), leafless=True)
    out["stats"] = {"nodes": int(n), "steps": steps, "height_m": round(out["height"], 2),
                    "trunk_diameter_m": round(float(2 * out["radius"][1]) if n > 1 else 0, 3),
                    "max_order": int(out["order"].max()), "grow_s": round(time.perf_counter() - t0, 3),
                    "pruned_nodes": int(cut_n), "cuts": cut_log, "dead": dead_log, "on_ground": grounded_,
                    "dead_stubs": int(out["dead"].sum()) if dead_log_ else 0}
    return out


# ---------------------------------------------------------------- silhouettes and measures

def silhouette(tree: dict, azimuth: float = 0.0, px_per_m: float = 20.0, leaves: bool = True, pad: float = 0.5):
    """An orthographic side view as a boolean mask (rows top to bottom) and its frame {x0, z1, px_per_m}: branches as
    lines of their own width, leaves as discs. Milliseconds: what measures and fits look at."""
    from PIL import Image, ImageDraw
    P, par, rad = tree["pos"], tree["parent"], tree["radius"]
    c, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    x = P[:, 0] * c + P[:, 1] * s_
    z = P[:, 2]
    lx = lz = lr = np.zeros(0)
    if leaves:  # each twig as a disc of about its own size
        from . import veg_leaf
        tw = veg_leaf.place_live(tree)
        if len(tw["pos"]):
            tl = {**veg_leaf.TWIG, **(tree["spec"]["leaves"].get("twig") or {})}["length"]
            cen = tw["pos"] + tw["frame"][:, :, 1] * (0.5 * tl * tw["scale"])[:, None]
            lx, lz, lr = cen[:, 0] * c + cen[:, 1] * s_, cen[:, 2], 0.45 * tl * tw["scale"]
    x0 = min(x.min(), lx.min() if len(lx) else 0) - pad
    x1 = max(x.max(), lx.max() if len(lx) else 0) + pad
    z1 = max(z.max(), lz.max() if len(lz) else 0) + pad
    W, H = int((x1 - x0) * px_per_m) + 1, int(z1 * px_per_m) + 1
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    X, Y = (x - x0) * px_per_m, (z1 - z) * px_per_m
    wpx = np.maximum(1, np.round(2 * rad * px_per_m)).astype(int)
    for i in range(1, len(P)):
        p = par[i]
        d.line([X[p], Y[p], X[i], Y[i]], fill=255, width=int(wpx[i]))
    if len(lx):
        r = np.maximum(1.0, lr * px_per_m)
        LX, LY = (lx - x0) * px_per_m, (z1 - lz) * px_per_m
        for i in range(len(lx)):
            d.ellipse([LX[i] - r[i], LY[i] - r[i], LX[i] + r[i], LY[i] + r[i]], fill=255)
    return np.asarray(im) > 0, {"x0": x0, "z1": z1, "px_per_m": px_per_m}


def _rows(mask):
    """Per row: leftmost, rightmost filled column (or -1)."""
    any_ = mask.any(1)
    left = np.where(any_, mask.argmax(1), -1)
    right = np.where(any_, mask.shape[1] - 1 - mask[:, ::-1].argmax(1), -1)
    return any_, left, right


def shape_measures(mask: np.ndarray, levels: int = 20) -> dict:
    """What a silhouette says about the tree's form, in units of its height: crown width, the bole (height where the
    crown starts: the lowest level at least a quarter as wide as the widest), the height of the widest point, the
    width profile bottom to top, how lopsided it is about the trunk's foot, and porosity (sky inside the outline)."""
    any_, left, right = _rows(mask)
    rows = np.flatnonzero(any_)
    top, bot = rows[0], rows[-1]
    H = bot - top + 1
    foot = slice(bot - max(2, H // 50), bot + 1)
    cx = 0.5 * (left[foot][any_[foot]].mean() + right[foot][any_[foot]].mean())
    width = np.where(any_, right - left + 1, 0)[top: bot + 1][::-1].astype(float)  # bottom to top
    lft = np.where(any_, cx - left, 0)[top: bot + 1][::-1]
    rgt = np.where(any_, right - cx, 0)[top: bot + 1][::-1]
    k = max(3, H // 40)
    sm = ndimage.uniform_filter1d(width, k)
    wmax = sm.max()
    crown0 = int(np.argmax(sm >= 0.25 * wmax))
    filled = sum(int(r - l + 1) for a, l, r in zip(any_, left, right) if a)
    t = (np.arange(levels) + 0.5) / levels
    hh = np.arange(H) / H
    return {"width_over_height": round(float(wmax / H), 3), "bole": round(float(crown0 / H), 3),
            "widest_at": round(float(np.argmax(sm) / H), 3),
            "crown_aspect": round(float(wmax / max(H - crown0, 1)), 3),
            "lopsided": round(float((ndimage.uniform_filter1d(rgt, k).max() - ndimage.uniform_filter1d(lft, k).max()) / max(wmax, 1)), 3),
            "porosity": round(float(1 - mask.sum() / max(filled, 1)), 3),
            "profile": [round(float(v), 3) for v in np.interp(t, hh, sm) / H],
            "_cx": float(cx), "_top": int(top), "_bot": int(bot)}


def _outline(mask, size=256):
    """The row-filled outline, scaled to `size` rows tall, the trunk's foot at the centre column."""
    from PIL import Image
    m = shape_measures(mask, 4)
    any_, left, right = _rows(mask)
    f = np.zeros_like(mask)
    for i in np.flatnonzero(any_):
        f[i, left[i]: right[i] + 1] = True
    f = f[m["_top"]: m["_bot"] + 1]
    sc = size / f.shape[0]
    w = max(1, int(round(f.shape[1] * sc)))
    g = np.asarray(Image.fromarray(f.astype(np.uint8) * 255).resize((w, size), Image.BILINEAR)) > 127
    out = np.zeros((size, 3 * size), bool)
    x0 = int(round(1.5 * size - m["_cx"] * sc))
    a, b = max(x0, 0), min(x0 + w, 3 * size)
    out[:, a:b] = g[:, a - x0: b - x0]
    return out


def outline_iou(mask_a, mask_b, flip: bool = True) -> float:
    """IoU of two silhouettes' row-filled outlines at equal height, feet together (the better of both mirrorings)."""
    A, B = _outline(mask_a), _outline(mask_b)
    best = 0.0
    for Bm in ([B, B[:, ::-1]] if flip else [B]):
        best = max(best, float((A & Bm).sum() / max((A | Bm).sum(), 1)))
    return round(best, 3)


def branch_angles(tree: dict, order: int = 1) -> dict:
    """Angles of the axes of one order: where they leave their parent (insertion, degrees off the parent's
    direction) and how their far half lies (elevation above the horizontal)."""
    P, par, ax = tree["pos"], tree["parent"], tree["axis"]
    ins, elev = [], []
    for a in tree["axes"]:
        if a["order"] != order or "node" not in a:
            continue
        n0 = a["node"]
        if n0 >= len(P) or tree["order"][n0] != order:
            continue
        nodes = np.flatnonzero(ax == ax[n0])
        if len(nodes) < 2:
            continue
        p = par[n0]
        d_par = _norm(P[p] - P[par[p]]) if p > 0 else np.array([0, 0, 1.0])
        ins.append(math.degrees(math.acos(float(np.clip(_norm(P[n0] - P[p]) @ d_par, -1, 1)))))
        tip = nodes[-1]
        mid = nodes[len(nodes) // 2]
        d = _norm(P[tip] - P[mid]) if tip != mid else _norm(P[tip] - P[p])
        elev.append(math.degrees(math.asin(float(np.clip(d[2], -1, 1)))))
    q = lambda v: [round(float(x), 1) for x in np.percentile(v, [10, 50, 90])] if len(v) else []
    return {"n": len(ins), "insertion_p10_50_90": q(ins), "elevation_p10_50_90": q(elev)}


def traced_mask(polygon, size=None) -> np.ndarray:
    """A silhouette from an outline traced on the photo by eye (image px, closed): what to use when the tree fills
    the frame or stands against other trees."""
    from PIL import Image, ImageDraw
    P = np.asarray(polygon, float)
    lo = np.floor(P.min(0)).astype(int)
    w, h = (np.ceil(P.max(0)).astype(int) - lo + 1)
    im = Image.new("L", (int(w), int(h)), 0)
    ImageDraw.Draw(im).polygon([tuple(q) for q in (P - lo)], fill=255)
    return np.asarray(im) > 0


def reference_mask(image, crop=None, foot=None, tol=30.0, horizon=None, trunk=40, exclude=(), close=1, edge=0.03,
                   polygon=None) -> np.ndarray:
    """A tree's silhouette from a photo of it against the sky. A pixel is tree when its colour is more than `tol`
    from its row's background, read at the left and right edges of `crop` [x0, y0, x1, y1] (which must be sky there;
    the crop ends at the trunk's foot, x = `foot`). Below `horizon` (image y: where ground or far trees start) only
    +-`trunk` px round the foot count, against that band's own edges. `exclude` rectangles (image px) are dropped;
    the biggest piece is kept. Look at the mask before trusting its numbers."""
    from PIL import Image
    if polygon is not None:
        return traced_mask(polygon)
    im = np.asarray(Image.open(image).convert("RGB")).astype(np.float64)
    x0, y0, x1, y1 = crop
    reg = im[y0:y1, x0:x1]
    H, W = reg.shape[:2]

    def differs(a):
        k = max(2, int(edge * a.shape[1]))
        L, R = np.median(a[:, :k], axis=1), np.median(a[:, -k:], axis=1)
        L, R = ndimage.uniform_filter1d(L, 9, axis=0), ndimage.uniform_filter1d(R, 9, axis=0)
        t = np.linspace(0, 1, a.shape[1])[None, :, None]
        return np.linalg.norm(a - (L[:, None] * (1 - t) + R[:, None] * t), axis=2) > tol

    m = differs(reg)
    if horizon is not None and horizon < y1:
        h = max(int(horizon) - y0, 0)
        m[h:] = False
        c = int(foot) - x0
        a, b = max(c - 2 * trunk, 0), min(c + 2 * trunk, W)
        m[h:, a:b] = differs(reg[h:, a:b])
    for ex0, ey0, ex1, ey1 in exclude:
        m[max(ey0 - y0, 0): max(ey1 - y0, 0), max(ex0 - x0, 0): max(ex1 - x0, 0)] = False
    if close:
        m = ndimage.binary_closing(m, iterations=int(close))
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n:
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        m = lab == int(np.argmax(sizes))
    return m


def line_directions(gray: np.ndarray, region: np.ndarray, sigma: float = 1.5, rho: float = 5.0) -> dict:
    """Which way the lines in an image run (branches against the sky, or our own silhouette), as angles from the
    vertical (0 = upright, 90 = level): structure tensor, weighted by how line-like and how strong each pixel is,
    inside `region`. Returns p25/p50/p75 and the share steeper than 30 deg / flatter than 60 deg. The same measure
    on a winter photo and on a bare silhouette at the same pixel scale compares branch angles without tracing."""
    g = np.asarray(gray, float)
    gx = ndimage.gaussian_filter(g, sigma, order=(0, 1))
    gy = ndimage.gaussian_filter(g, sigma, order=(1, 0))
    jxx, jyy, jxy = (ndimage.gaussian_filter(v, rho) for v in (gx * gx, gy * gy, gx * gy))
    tr = jxx + jyy
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / np.maximum(tr, 1e-12)
    th = 0.5 * np.arctan2(2 * jxy, jxx - jyy)  # the gradient's direction; the line runs across it
    ang = np.degrees(np.abs(np.arctan2(np.sin(th), np.cos(th))))  # gradient from the x axis
    ang = np.where(ang > 90, 180 - ang, ang)  # gradient level (0) = an upright line: already "from the vertical"
    w = (coh * tr)[region]
    a = ang[region]
    if w.sum() <= 0:
        return {"p25": 0.0, "p50": 0.0, "p75": 0.0, "upright": 0.0, "level": 0.0}
    o = np.argsort(a)
    cw = np.cumsum(w[o]) / w.sum()
    q = lambda f: float(a[o][min(np.searchsorted(cw, f), len(a) - 1)])
    return {"p25": round(q(0.25), 1), "p50": round(q(0.5), 1), "p75": round(q(0.75), 1),
            "upright": round(float(w[a < 30].sum() / w.sum()), 3), "level": round(float(w[a > 60].sum() / w.sum()), 3)}


def _filled(mask):
    any_, left, right = _rows(mask)
    f = np.zeros_like(mask)
    for i in np.flatnonzero(any_):
        f[i, left[i]: right[i] + 1] = True
    return f


def photo_branch_directions(image, mask_args: dict, crown_from: float = 0.3) -> dict:
    """line_directions of a winter photo inside the tree's outline, above `crown_from` of its height (off the trunk)."""
    from PIL import Image
    R = reference_mask(image, **mask_args)
    im = np.asarray(Image.open(image).convert("L")).astype(float)
    if mask_args.get("polygon") is not None:
        P = np.asarray(mask_args["polygon"])
        x0, y0 = int(np.floor(P[:, 0].min())), int(np.floor(P[:, 1].min()))
    else:
        x0, y0 = mask_args["crop"][0], mask_args["crop"][1]
    g = im[y0: y0 + R.shape[0], x0: x0 + R.shape[1]]
    reg = _filled(R)[: g.shape[0], : g.shape[1]]
    rows = np.flatnonzero(reg.any(1))
    reg[int(rows[-1] - crown_from * (rows[-1] - rows[0])):] = False
    out = line_directions(g, reg)
    out["height_px"] = int(rows[-1] - rows[0])
    return out


def tree_branch_directions(tree: dict, azimuth: float, height_px: int, crown_from: float = 0.3) -> dict:
    """The same measure on our bare silhouette, drawn as tall in pixels as the photo's tree."""
    m, _ = silhouette(tree, azimuth, height_px / max(tree["height"], 1e-6), leaves=False)
    reg = _filled(m)
    rows = np.flatnonzero(reg.any(1))
    reg[int(rows[-1] - crown_from * (rows[-1] - rows[0])):] = False
    return line_directions(255.0 * (~m), reg)


# ---------------------------------------------------------------- fitting a habit to a reference silhouette

def _set_path(d: dict, path: str, value):
    """habit key 'apical.0' = element 0 of the list (a scalar becomes a list)."""
    k, _, i = path.partition(".")
    if not i:
        d[k] = value
        return
    lst = list(d[k]) if isinstance(d.get(k), (list, tuple)) else [d.get(k)]
    while len(lst) <= int(i):
        lst.append(lst[-1])
    lst[int(i)] = value
    d[k] = lst


def match(tree: dict, ref_mask: np.ndarray, bare: bool = False, azimuths=(0, 90), px_per_m: float = 12.0) -> dict:
    """How a grown tree compares with a reference silhouette: outline IoU (best azimuth) and both sets of measures."""
    mr = shape_measures(ref_mask)
    best = None
    for az in azimuths:
        m, _ = silhouette(tree, az, px_per_m, leaves=not bare)
        iou = outline_iou(ref_mask, m)
        if best is None or iou > best[0]:
            best = (iou, az, m)
    mo = shape_measures(best[2])
    keys = ("width_over_height", "bole", "widest_at", "crown_aspect", "lopsided", "porosity")
    return {"iou": best[0], "azimuth": best[1], "ours": {k: mo[k] for k in keys}, "ref": {k: mr[k] for k in keys},
            "mask": best[2]}


def droop(tree: dict, bole: float) -> float:
    """Share of the shoot ends hanging under the crown's base (bole x height), more than 1.5 m out from the trunk:
    limbs drooped to the ground, which an outline fit would otherwise reward."""
    e = tree["pos"][tree["ends"]]
    if not len(e):
        return 0.0
    low = (e[:, 2] < bole * tree["height"] * 0.85) & (np.linalg.norm(e[:, :2], axis=1) > 1.5)
    return float(low.mean())


def fit_habit(spec: dict, ref_mask: np.ndarray, params: dict, bare: bool = False, iters: int = 60, seeds=(1, 2),
              nodes=(3000, 30000), rng_seed: int = 0, log=None, directions: dict | None = None,
              elevation: tuple | None = None, droop_max: float | None = None) -> dict:
    """Search habit numbers so the grown tree's outline matches a reference: `params` = {habit path: [lo, hi]}
    ("apical.0" = the list's element 0; integer bounds stay integers). Random search, then shrinking steps round
    the best; scored on outline IoU over `seeds` minus misses in width/height and bole, and node counts outside
    `nodes`. Returns {"habit": the fitted overrides, "score", "iou", "log"}. A fit's numbers go into a preset or a
    spec; nothing is kept hidden."""
    rng = np.random.default_rng(rng_seed)
    names = list(params)
    lo = np.array([params[k][0] for k in names], float)
    hi = np.array([params[k][1] for k in names], float)
    isint = [all(isinstance(v, int) for v in params[k]) for k in names]
    base = resolve(spec)["habit"]

    def vec0():
        out = []
        for k in names:
            a, _, i = k.partition(".")
            v = base[a]
            v = (v[min(int(i), len(v) - 1)] if isinstance(v, list) else v) if i else v
            out.append(float(v if v is not None else 0.5 * (params[k][0] + params[k][1])))
        return np.clip(np.array(out), lo, hi)

    def score(x):
        hb = {}
        full = copy.deepcopy(base)
        for k, v, ii in zip(names, x, isint):
            _set_path(full, k, int(round(v)) if ii else round(float(v), 4))
        for k in {n.partition(".")[0] for n in names}:
            hb[k] = full[k]
        tot, ious = 0.0, []
        for sd in seeds:
            sp = _merge(spec, {"seed": sd, "habit": hb})
            sp.pop("height", None)
            T = grow(sp)
            m = match(T, ref_mask, bare=bare)
            n = T["stats"]["nodes"]
            pen = abs(m["ours"]["width_over_height"] - m["ref"]["width_over_height"]) * 0.3 \
                + abs(m["ours"]["bole"] - m["ref"]["bole"]) * 0.8 \
                + 1.5 * max(0.0, droop(T, m["ref"]["bole"]) - (0.02 if droop_max is None else droop_max)) \
                + 0.15 * max(0.0, math.log(nodes[0] / max(n, 1))) + 0.15 * max(0.0, math.log(n / nodes[1]))
            if directions:  # branch directions against the winter photo's (deg from vertical)
                dv = tree_branch_directions(T, m["azimuth"], directions["height_px"])
                pen += 0.006 * abs(dv["p50"] - directions["p50"]) + 0.3 * abs(dv["level"] - directions["level"])
            if elevation:  # the first-order limbs' far halves, inside a stated band (deg above level)
                el = branch_angles(T, 1)["elevation_p10_50_90"]
                if el:
                    pen += 0.006 * (max(0.0, elevation[0] - el[1]) + max(0.0, el[1] - elevation[1]))
            tot += m["iou"] - pen
            ious.append(m["iou"])
        return tot / len(seeds), float(np.mean(ious)), hb

    x = vec0()
    best = (*score(x), x)
    hist = [(round(best[0], 3), round(best[1], 3))]
    for it in range(iters):
        if it < iters // 2:
            c = lo + rng.random(len(names)) * (hi - lo) if it % 3 == 0 else np.clip(best[3] + rng.normal(0, 0.25, len(names)) * (hi - lo), lo, hi)
        else:
            w = 0.12 * (1 - (it - iters // 2) / max(iters - iters // 2, 1)) + 0.03
            c = np.clip(best[3] + rng.normal(0, w, len(names)) * (hi - lo) * (rng.random(len(names)) < 0.5), lo, hi)
        r = score(c)
        if r[0] > best[0]:
            best = (*r, c)
            if log:
                log(f"{it}: score {r[0]:.3f} iou {r[1]:.3f} {json.dumps(r[2])}")
        hist.append((round(r[0], 3), round(r[1], 3)))
    return {"habit": best[2], "score": round(best[0], 3), "iou": round(best[1], 3), "log": hist}


# ---------------------------------------------------------------- form across ages and settings

def crown_measures(tree: dict) -> dict:
    """The tree's form read off its own live foliage (not a silhouette): height (m), crown width / height (mean of four
    azimuths, 1st-99th percentile of leafy wood), live crown depth / height (above the 3rd percentile of leafy wood),
    the height of the widest level / height, girth at 1.3 m (cm), how far the top stands off the foot (m), and the
    living first-order limbs. What a forester's crown ratio and crown width are, so targets can come from tables."""
    P, o = tree["pos"], tree["order"]
    live = tree["leafy"] & ~tree["dead"]
    H = float(tree["height"])
    L = P[live] if live.sum() > 3 else P
    base = float(np.percentile(L[:, 2], 3))
    w = []
    for az in (0, 45, 90, 135):
        x = L[:, 0] * math.cos(math.radians(az)) + L[:, 1] * math.sin(math.radians(az))
        w.append(np.percentile(x, 99) - np.percentile(x, 1))
    W = float(np.mean(w))
    zs = np.linspace(base, H, 11)
    reach = []
    for a, b in zip(zs[:-1], zs[1:]):
        m = (L[:, 2] >= a) & (L[:, 2] < b)
        reach.append(float(np.percentile(np.linalg.norm(L[m, :2], axis=1), 95)) if m.sum() > 5 else 0.0)
    k = int(np.argmax(reach))
    tr = (o == 0) & ~tree["dead"]
    dbh = 200 * float(np.interp(1.3, P[tr][:, 2], tree["radius"][tr])) if tr.sum() > 2 and H > 1.3 else 0.0
    limbs_ = int(((o == 1) & (o[tree["parent"]] == 0) & ~tree["dead"]).sum())
    return {"height": round(H, 2), "width_over_height": round(W / max(H, 1e-6), 3), "crown_ratio": round(1 - base / max(H, 1e-6), 3),
            "widest_at": round(0.5 * (zs[k] + zs[k + 1]) / max(H, 1e-6), 3), "dbh_cm": round(dbh, 1),
            "top_off": round(float(np.linalg.norm(P[int(np.argmax(P[:, 2])), :2])), 2), "limbs": limbs_,
            "nodes": int(len(P))}


def form_cases(spec: dict, cases: list, seeds=(1,)) -> list:
    """Grow the spec once per case ({"age", "environment"?, "name"?, + target bands}) and seed; returns each case with
    its mean `measures`. The same habit at several ages and settings: a preset tuned at one age is a single point."""
    out = []
    for c in cases:
        ms = []
        for sd in seeds:
            sp = _merge(spec, {"seed": sd, "age": c["age"], "environment": c.get("environment") or {"setting": "open"}})
            sp.pop("height", None)
            ms.append(crown_measures(grow(sp)))
        out.append({**c, "measures": {k: round(float(np.mean([m[k] for m in ms])), 3) for k in ms[0]},
                    "spread": {k: round(float(np.ptp([m[k] for m in ms])), 3) for k in ("width_over_height", "crown_ratio")}})
    return out


FORM_KEYS = ("height", "width_over_height", "crown_ratio", "widest_at", "dbh_cm", "top_off", "nodes")


def form_miss(cases: list) -> float:
    """How far measured cases lie outside their target bands ({key: [lo, hi]}), each miss as a share of the band's
    middle; 0 = every measure inside its band."""
    tot = 0.0
    for c in cases:
        for k in FORM_KEYS:
            if k in c:
                lo, hi = c[k]
                v = c["measures"][k]
                tot += float(c.get("weight", 1.0)) * (max(0.0, lo - v) + max(0.0, v - hi)) / max(0.5 * (abs(lo) + abs(hi)), 1e-6)
    return tot


def fit_form(spec: dict, cases: list, params: dict, iters: int = 60, seeds=(1, 2), rng_seed: int = 0, log=None) -> dict:
    """Search habit numbers so ONE habit meets crown targets at several ages and settings (`cases`: {"age",
    "environment", and bands like "width_over_height": [0.4, 0.55], "crown_ratio", "widest_at", "height", "dbh_cm",
    "nodes"}). `params` as fit_habit's. The outline fit (fit_habit) matches one photo; this keeps a species right
    from a sapling to a veteran, in the open and in a stand, against numbers that can be sourced (yield tables,
    crown-ratio studies, measured photos). Returns {"habit", "miss", "cases"}."""
    rng = np.random.default_rng(rng_seed)
    names = list(params)
    lo = np.array([params[k][0] for k in names], float)
    hi = np.array([params[k][1] for k in names], float)
    isint = [all(isinstance(v, int) for v in params[k]) for k in names]
    base = resolve(spec)["habit"]

    def vec0():
        out = []
        for k in names:
            a, _, i = k.partition(".")
            v = base[a]
            v = (v[min(int(i), len(v) - 1)] if isinstance(v, list) else v) if i else v
            out.append(float(v if v is not None else 0.5 * (params[k][0] + params[k][1])))
        return np.clip(np.array(out), lo, hi)

    def score(x):
        full = copy.deepcopy(base)
        for k, v, ii in zip(names, x, isint):
            a, _, i = k.partition(".")
            if i and isinstance(full[a], list) and len(full[a]) <= int(i):
                full[a] = full[a] + [full[a][-1]] * (int(i) + 1 - len(full[a]))
            _set_path(full, k, int(round(v)) if ii else round(float(v), 4))
        hb = {k: full[k] for k in {n.partition(".")[0] for n in names}}
        cs = form_cases(_merge(spec, {"habit": hb}), cases, seeds)
        return form_miss(cs), hb, cs

    x = vec0()
    best = (*score(x), x)
    if log:
        log(f"start: miss {best[0]:.3f}")
    for it in range(iters):
        if it < iters // 2:
            c = lo + rng.random(len(names)) * (hi - lo) if it % 4 == 0 else np.clip(best[3] + rng.normal(0, 0.2, len(names)) * (hi - lo) * (rng.random(len(names)) < 0.6), lo, hi)
        else:
            w = 0.1 * (1 - (it - iters // 2) / max(iters - iters // 2, 1)) + 0.03
            c = np.clip(best[3] + rng.normal(0, w, len(names)) * (hi - lo) * (rng.random(len(names)) < 0.4), lo, hi)
        r = score(c)
        if r[0] < best[0]:
            best = (*r, c)
            if log:
                log(f"{it}: miss {r[0]:.3f} {json.dumps(r[1])}")
        if best[0] <= 0:
            break
    return {"habit": best[1], "miss": round(best[0], 3), "cases": best[2]}
