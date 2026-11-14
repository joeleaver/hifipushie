"""Unique mark maps for the face: stubble hairs and freckles drawn on the head's OWN surface, once per model, the way a
character texture artist paints them into a unique map instead of tiling a swatch (a tiled freckle swatch showed its
6 cm repeat; tiled stubble dots read as a grey block with no beard line, no growth direction and no density zones).

How: the skin part's field is meshed in a box round the head (`head_mesh`, cached); marks are scattered on that
mesh by area x a density field built from the face's landmarks (so they follow edits of the head); each mark is drawn
into one image laid as a sphere wrap round a centre inside the head (`images` "wrap": "sphere": u, v from the
direction alone, per pixel in the shader, so the map holds on any head shape). A mark's footprint is drawn through
the wrap's local Jacobian, so it keeps its true size and shape in millimetres wherever it lands on the map.

Stubble (`stubble_map`): hairs as short cut strokes (blunt, ~0.1 mm wide) leaving the skin at an angle and lying
along the beard's growth direction (down on cheeks / jaw / chin, down and out from the philtrum on the moustache,
toward the throat under the chin), density by zone (moustache and chin full, the mouth-corner connector and the
cheeks thinner, fading to the cheek line), the cheek line and neckline crisp when trimmed and feathered when grown
out, patchiness by a low noise, salt and pepper by a share of white hairs. Channels: r = dark hairs, g = white
hairs, b = the shadow of the dark hair under and at the skin (the roots' local count, blurred ~1.5 mm: no roots, no
shadow, so patches, grey hairs and beard lines all carry into it).

Freckles (`freckle_map`): ephelides as irregular macules (lobed outlines, soft edges of their own), lognormal sizes,
clustered (a low noise to a power), on what faces the sun (nose bridge and dorsum, the malar cheeks, forehead,
upper lip less, nothing under the chin); a share darker; a few moles (rounder, sharper, darker, some raised).
Channels: r = light freckles, g = dark freckles, b = moles.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at skin_marks.NAME: C422). skin_marks_map: the surface marks are placed on (the head's mesh, curvature,
scatter) and the map they are drawn into (sphere, pixels, frames, draw). skin_marks_beard: the beard: zones, density,
direction, the hairs' tones, the stubble map. skin_marks_freckles: freckles: their density and their map.
skin_marks_pores: the base skin: pore zones, the pore field, pixel points, the base map (pores, micro relief, fine
colour).
"""
from __future__ import annotations

import numpy as np
from . import moved

VERSION = 24
SUB_DASH, SUB_GAP = 2.0, 0.4   # the under-skin shafts in the shadow channel: their gain, the shadow left between them
MAX_PX = 8192

# stubble styles: length (m) of the exposed hair, the shadow's weight, edge (0 natural .. 1 crisply trimmed), density
# scale, patchiness, how far the cheeks fill (0 thin .. 1 as the chin); hair grows ~0.4 mm a day
STUBBLE_STYLES = {
    "clean": {"length": 0.00005, "shadow": 0.22, "trim": 0.0, "density": 1.0, "patchy": 0.1, "cheeks": 0.55},
    "five_oclock": {"length": 0.0004, "shadow": 0.6, "trim": 0.0, "density": 1.0, "patchy": 0.15, "cheeks": 0.55},
    "short": {"length": 0.0014, "shadow": 0.75, "trim": 0.0, "density": 1.0, "patchy": 0.1, "cheeks": 0.6},
    "designer": {"length": 0.004, "shadow": 0.6, "trim": 1.0, "density": 1.0, "patchy": 0.15, "cheeks": 0.7},
    "heavy": {"length": 0.008, "shadow": 0.55, "trim": 0.25, "density": 1.0, "patchy": 0.2, "cheeks": 0.8},
    "patchy": {"length": 0.002, "shadow": 0.5, "trim": 0.0, "density": 0.8, "patchy": 0.75, "cheeks": 0.3},
}
HAIRS_PER_M2 = 8.0e5   # ~80 / cm2 where the beard is full (moustache, chin: 70-85 measured)

_MESH: dict = {}


def _ramp(x, a, b):
    """0 at a, 1 at b (either order), smoothstep."""
    den = np.asarray(b, float) - a
    t = np.clip((np.asarray(x, float) - a) / np.where(np.abs(den) > 1e-15, den, 1e-15), 0, 1)
    return t * t * (3 - 2 * t)


def _unit(v):
    v = np.asarray(v, float)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


BEARD_ZONES = ("moustache", "chin", "soul_patch", "jaw", "cheeks", "neck")

FRECKLE_ZONES = {"face": 0.35, "nose": 1.0, "cheeks": 1.0, "forehead": 0.55, "upper_lip": 0.35, "chin": 0.3}

# ---- the base skin: pores, micro relief, fine colour -----------------------------------------------------------------

# pores by zone: (pores per cm2 that read, median radius m). Nose and the medial cheeks coarse, forehead and chin
# middling, the rest of the face fine (sebaceous follicles: largest and densest on the nose and beside it)
PORE_ZONES = {"nose": (240.0, 0.00016), "cheek": (170.0, 0.00013), "forehead": (120.0, 0.00009), "chin": (150.0, 0.00011),
              "face": (60.0, 0.00007)}
BASE_VERSION = 13
BASE_PX = 0.00008   # m a pixel at the face: pores 0.13-0.35 mm across are 2-4 pixels


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("skin_marks_map", "skin_marks_beard", "skin_marks_freckles", "skin_marks_pores")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
