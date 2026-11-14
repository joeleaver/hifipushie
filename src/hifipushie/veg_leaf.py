"""Leaves, needles and twigs: the small assets a tree's foliage is made of (The Grove's "twigs", SpeedTree's leaf
meshes). A leaf is generated from botanical words (shape family, lobes, length, width, fold, curl, petiole); a twig
is a short shoot carrying leaves by its own phyllotaxis, or needles; `place` puts twigs on a grown tree (at shoot ends
and along leafy shoots). Twig meshes are the source for mesh foliage (close LODs, video) and, later, for the atlas
cards games use. Local frame: the twig runs along +y from the origin, +z is up (the side leaves turn to the light).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at veg_leaf.NAME: C422). veg_leaf_twig: twig meshes: a dead twig and a live one (leaves on their stems along
a shoot). veg_leaf_place: twigs on a tree: where dead and live twigs go, and the parts they make. veg_leaf_cards:
cards: a card's spec, a twig rasterized into its tile, the outline strip, the card's mesh. veg_leaf_atlas: the card
atlas: built once per key, cached on disk, its parts, variants and files.
"""
from __future__ import annotations

import math

import numpy as np
from . import moved

LEAF = {"shape": "ovate", "length": 0.07, "width": 0.55, "lobes": 4, "fold": 0.25, "curl": 0.25, "petiole": 0.15,
        "serrate": 0.0, "needle_width": 0.1, "bend": 0.0}  # bend: the blade curves sideways (a grass blade's arc), x its length  # needle_width: a needle's width / length (far wider than life: a mesh
# needle has to cover what hundreds of real ones do)
TWIG = {"length": 0.3, "leaves": 9, "arrangement": "alternate", "angle": 55, "droop": 0.15, "side_shoots": 0,
        "variants": 3, "per_m": 5.0, "where": "shoots", "spread": 45, "up": 0.3, "scale": [0.8, 1.15], "radius": 0.0025,
        "min_order": 1, "steps": 2, "sub_shoots": 0, "side_angle": 40, "side_length": 0.6, "side_taper": 0.58, "spray_angle": 57,
        "divergence": 137.5, "light": 0.7, "needles": "auto", "parted": 0.3, "forward": 0.7,
        "taper": 0.0, "flower": None,  # taper: leaves shrink toward the tip by this share (a frond's outline); flower:
        # {"form": "ray" | "cup" | "spike", "petals", "radius" m, "color", "center", "center_size", "spike": share of the stalk}
        "fascicle": 1, "needle_angle": None, "bud": 0.0,  # fascicles: needles per bundle (pines 2 / 3 / 5); [deg off the
        # shoot at the foliage's base, at its tip] (old needles stand out, young ones lie forward: a bottlebrush); a bud (m)
        "curl": 0.0, "tips": 0.0,  # a spray's side shoots: curl = they sweep forward along the twig (straight ones at
        # one angle read as a fern frond / a fishbone); tips = this much lighter toward every shoot's end (the year's growth)
        "face": 0.5}  # face: 1 = every twig's upper side to the sky (a roof of plates), 0 = rolled any way round its shoot
CARD = {"variants": 4, "size": 384, "verts": 7, "cup": 0.1, "cross": 1, "scale": 1.0, "twig": {}, "leaf": {}, "strips": 0,
        "end": False}  # end: one more card across the shoot with the twig's picture seen from its tip (a tuft is round)


def _profile(shape: str, t: np.ndarray, lobes: int) -> np.ndarray:
    """Half width (0..1) along the blade, t = 0 at the petiole."""
    if shape == "ovate":
        return np.sin(np.pi * t ** 0.75) ** 0.9
    if shape == "triangular":  # birch: widest low, a drawn-out tip
        return np.minimum(t / 0.2, 1.0) ** 0.8 * (1 - t) ** 0.85 * 1.25
    if shape == "lanceolate":
        return np.sin(np.pi * t ** 0.9) ** 1.1
    if shape == "lobed":  # oak: widest past the middle, round lobes and sinuses
        return np.sin(np.pi * t ** 1.35) ** 0.8 * (0.55 + 0.45 * np.abs(np.sin(np.pi * lobes * t)) ** 0.7)
    if shape == "linear":  # a grass blade: parallel-sided, a long drawn-out point
        return np.minimum(t / 0.04, 1.0) * np.minimum((1 - t) / 0.45, 1.0) ** 0.7
    if shape == "strap":  # iris, daffodil, a palm's leaflet: parallel, a short point
        return np.minimum(t / 0.06, 1.0) * np.minimum((1 - t) / 0.15, 1.0) ** 0.6
    if shape == "round":  # clover leaflet, nasturtium, a water lily's pad
        return np.sin(np.pi * np.clip(t, 0, 1)) ** 0.5
    if shape == "petal":  # widest near the tip, narrowing to a claw
        return np.sin(np.pi * t ** 1.8) ** 0.7
    raise ValueError(f"leaf shape {shape!r}: ovate, triangular, lanceolate, lobed, linear, strap, round or petal")


def leaf_mesh(leaf: dict) -> dict:
    """One leaf blade: V (unit = metres), F, shade per vertex (midrib pale, edge darker), along (0 base, 1 tip)."""
    lf = {**LEAF, **leaf}
    k = 16 if lf["shape"] == "lobed" else 7
    t = np.linspace(0, 1, k + 1)
    L = lf["length"]
    w = _profile(lf["shape"], t, int(lf["lobes"])) * 0.5 * lf["width"] * L
    if lf["serrate"]:
        w = w * (1 + lf["serrate"] * (np.arange(k + 1) % 2 - 0.5))
    y = lf["petiole"] * L + t * L
    zmid = -lf["curl"] * L * t ** 2
    zedge = zmid + lf["fold"] * w
    xb = lf["bend"] * L * t ** 2
    V = np.vstack([np.c_[xb, y, zmid], np.c_[xb - w, y, zedge], np.c_[xb + w, y, zedge],
                   [[-0.004 * L / 0.07, 0, 0], [0.004 * L / 0.07, 0, 0]]])
    F = []
    for i in range(k):
        m0, m1, l0, l1, r0, r1 = i, i + 1, k + 1 + i, k + 2 + i, 2 * k + 2 + i, 2 * k + 3 + i
        F += [[m0, m1, l1], [m0, l1, l0], [m0, r1, m1], [m0, r0, r1]]
    b = 3 * (k + 1)
    F.append([b, b + 1, 0])  # the petiole
    shade = np.concatenate([np.full(k + 1, 1.0), np.full(2 * (k + 1), 0.82), [0.9, 0.9]])
    along = np.concatenate([t, t, t, [0, 0]])
    return {"V": V, "F": np.array(F), "shade": shade, "along": along}


def _rot(axis, ang):
    axis = axis / np.linalg.norm(axis)
    c, s = math.cos(ang), math.sin(ang)
    x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def _frame(d, up=(0, 0, 1.0)):
    """Columns x, y = d, z: z as near `up` as it can be."""
    d = d / np.linalg.norm(d)
    z = np.asarray(up, float) - d * (d @ np.asarray(up, float))
    if np.linalg.norm(z) < 1e-6:
        z = np.array([1.0, 0, 0]) - d * d[0]
    z /= np.linalg.norm(z)
    return np.stack([np.cross(d, z), d, z], axis=1)


def _stem(pts, r0, r1, sides=3):
    """A thin tube along a polyline."""
    m = len(pts)
    V, F = [], []
    for i, p in enumerate(pts):
        d = pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]
        Fr = _frame(d)
        r = r0 + (r1 - r0) * i / max(m - 1, 1)
        for j in range(sides):
            a = 2 * math.pi * j / sides
            V.append(p + r * (math.cos(a) * Fr[:, 0] + math.sin(a) * Fr[:, 2]))
    for i in range(m - 1):
        for j in range(sides):
            a, b = i * sides + j, i * sides + (j + 1) % sides
            F += [[a, b, b + sides], [a, b + sides, a + sides]]
    return np.array(V), np.array(F)


DEAD_TWIG = {"forks": 9.0, "depth": 3, "crook": 0.35, "broken": 0.3, "lichen": 0.0, "lichen_color": [0.62, 0.66, 0.56],
             "flat": 0.35, "fork_angle": [35, 80], "child": [0.25, 0.6]}

_ATLAS: dict = {}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("veg_leaf_twig", "veg_leaf_place", "veg_leaf_cards", "veg_leaf_atlas")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
