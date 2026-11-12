"""The HAIR READER (the `hair_from_reference` tool; hair-garrett, 2026-10-14): the model's fitted reference pictures as a
MEASUREMENT of the hair, and a START groom / look set from what was measured. Like skin_from_reference: the picture is
never the texture; what the groom and look have a parameter for is read off the pictures, the parameters are set from
the read, and the reply says measured vs set, INFERRED where a picture can't show it, and which view each colour target
came from.

Per fitted reference view (human_refs.json: picture + humanfit camera):
  hair / skin / backdrop probabilities from the face parsers (faceparse: MediaPipe's multiclass + BiSeNet, averaged for
  hair), a pixel-level HAIRNESS a = where the pixel lies between the backdrop's colour (0) and the dense hair's (1),
  the bare skull's silhouette (the model's scalp projected through the camera) and mm a pixel at the head.
Measures (each a function of arrays, so tests run without the nets):
  outline   per image angle from the head centre: mm from the skull's edge to the solid hair's edge where the hair
            meets the backdrop (STAND-OFF, rule 1), by head region (the ray's grazing point on the scalp); the edge's
            ROUGHNESS (mm, against its own 15 deg average) and the HALO density (mean hairness 0.5-4 mm outside the solid
            edge: 0 a cut-out .. 1 solid; rule 4), WISPS (detached hair pieces within 12 mm, per 10 cm of outline; rule 7)
  hairline  every hair / bare-skin boundary pixel cast onto the scalp: the line's height per azimuth (front, temples,
            sideburns, nape; -> groom.hairline.front_points), its SOFTNESS (mm from 20 % to 80 % hair across the
            line, rule 6) and BABY HAIRS (detached specks on the skin side, per cm of line)
  parting   the strand direction field over the top in the authority view: a part is a sharp change of strand
            direction (and a fine line of scalp); position (m off the centre line, his left / right), softness (mm).
            Not seen -> INFERRED from the way the front is combed (rule 5)
  colour    colour_bands + colour_variation of the dense hair in the AUTHORITY view (the front unless told:
            references can disagree on colour between views; the others are checks), a two-mode split into the
            pigmented hair and the light / grey strands, and the light share BY REGION (top, front, sides, back:
            salt and pepper greys at the temples first) (rules 8-11)
  length    not visible on a short cut (the hair lies over itself): INFERRED from the stand-off by region

  frames(name)            -> per view: picture, masks, camera numbers (cached per process)
  read(name)              -> {"views": [...], "summary": {...}, "text"}
  start(r, spec)          -> {"hair": {style, groom patch, strands, look}, "rows": [(key, set, from)], "text"}
  apply(name, out=None)   -> read + start + groom (to `out`, a copy, or onto `name`)

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at hair_read.NAME: C422). hair_read_capture: capture: the frames of a reference (picture, parse, rays), and a
render read as a picture. hair_read_measures: measures on a frame: hairness, outline rays, edge softness, the
hairline, baby hairs, the strand field, the parting, waviness, lengths, the colour split. hair_read_read: the read:
what the pictures say of the hair, its summary and text. hair_read_compare: compare a groom's render with its
reference read, and the colour step toward it. hair_read_start: the start: a first groom from a read, its text, and
`apply`.
"""
from __future__ import annotations

import numpy as np
from . import moved

VERSION = 1
NETS = ("mediapipe", "bisenet")
SKIN_CLASSES = (1, 14)        # BiSeNet face skin, neck (not ears 7, 8: hair over an ear is not a hairline)
HALO_BAND = (0.5, 4.0)        # mm outside the solid edge read as halo
WISP_REACH = 12.0             # mm: detached hair pieces this far out count as wisps
ROUGH_DEG = 15.0              # deg: the outline's own smooth trend (roughness is what is left)
REGIONS = ("front", "top", "crown", "sides", "back", "nape")


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _lab_px(a):
    """CIE Lab of sRGB 0..255 pixels (..., 3)."""
    from .hair_card_fit import _lab
    return np.stack(_lab(np.asarray(a, float)), -1)


def _hex(rgb) -> str:
    c = np.clip(np.round(np.asarray(rgb, float)), 0, 255).astype(int)
    return "#%02x%02x%02x" % tuple(c)


def region_name(az, el) -> np.ndarray:
    """The groom's regions (volume / length keys) of scalp points: top (el >= 55, toward the front), crown (el >= 55,
    behind, under 75 deg), front (within 45 deg of the face), sides (45-120), back, nape (low at the back)."""
    az = np.asarray(az, float)
    el = np.asarray(el, float)
    fa = np.abs(((az + 180) % 360) - 180)
    r = np.where(fa < 45, "front", np.where(fa < 120, "sides", np.where(el > -15, "back", "nape")))
    return np.where(el >= 55, np.where((fa < 100) | (el >= 75), "top", "crown"), r)


# ------------------------------------------------------------------------------------------------ camera helpers
def cam_eye(cam: dict):
    from . import humanfit_views
    R = humanfit_views._cam_rot(cam)
    return np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float), R


def pixel_rays(cam: dict, uv):
    """World ray directions of pixels (u right, v down) through a humanfit camera."""
    eye, R = cam_eye(cam)
    w, h = cam["size"]
    uv = np.atleast_2d(np.asarray(uv, float))
    dc = np.stack([(uv[:, 0] - w / 2) / cam["f"], (uv[:, 1] - h / 2) / cam["f"], np.ones(len(uv))], 1)
    D = dc @ R
    return eye, D / np.linalg.norm(D, axis=1, keepdims=True)


def onto_scalp(sc, cam: dict, uv, height: float = 0.0, step: float = 0.001, chunk: int = 4000):
    """Pixels -> where their camera rays first come within `height` m of the scalp: (points (n, 3), hit (n,) bool,
    graze (n, 3) = each ray's closest approach to the scalp: the silhouette's point for an outline pixel)."""
    eye, D = pixel_rays(cam, uv)
    dist = float(np.linalg.norm(sc.C - eye))
    ts = np.arange(dist - 0.22, dist + 0.06, step)
    P = np.zeros((len(D), 3))
    G = np.zeros((len(D), 3))
    hit = np.zeros(len(D), bool)
    for s in range(0, len(D), chunk):
        d = D[s:s + chunk]
        Q = eye + ts[None, :, None] * d[:, None, :]
        _, _, hh = sc.coords(Q.reshape(-1, 3))
        hh = hh.reshape(len(d), len(ts)) - height
        neg = hh < 0
        k = np.where(neg.any(1), np.argmax(neg, 1), np.argmin(hh, 1))
        hit[s:s + chunk] = neg.any(1)
        P[s:s + chunk] = Q[np.arange(len(d)), k]
        G[s:s + chunk] = Q[np.arange(len(d)), np.argmin(hh, 1)]
    return P, hit, G


# ------------------------------------------------------------------------------------------------ capture
_FRAMES: dict = {}


def _lin_hex(h) -> np.ndarray:
    from .hair import _lin
    return _lin(h)  # ("#rrggbb" or [r, g, b] sRGB floats)


def _srgb_list(c) -> list:
    """Linear rgb -> [r, g, b] sRGB floats, 4 decimals: look.seen without 8-bit quantisation."""
    c = np.clip(np.asarray(c, float), 0, 1)
    return [round(float(x), 4) for x in np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)]


def _hex_lin(c) -> str:
    c = np.clip(np.asarray(c, float), 0, 1)
    return _hex(255 * np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055))


# ------------------------------------------------------------------------------------------------ the start

# fine, straight, dense short hair: many thin strands, no wave / curl, little clumping (long-hair dials made noodles)
CROP = {"strands": {"count": 600000, "thickness": 0.9, "clump": 0.1, "stray": 0.9, "roots": 0.9, "loose": 0.0,
                    "frizz": 0.02, "wave": 0.0, "curl": 0.0, "tips": 0.6, "tip_spread": 0.3, "under_length": 0.01}}
SHORT_MM = 30.0     # mm: a mean stand-off under this (and no region over 1.5x) is a short cut
LIFT_SPREAD = 0.005  # m a laid short lock's strands stand over its guide (render stand-off ~ lift + this)
LOOSE_THICK = 0.003  # m: a short laid lock's thickness (6 mm sank half the strands into the skin: curls)
LONG_BELOW = 0.12  # m under the head centre: hair reaching lower (past the jaw) is loose LONG hair
GREY_CHROMA = 1.0  # light mode chroma / dark mode chroma under this: the light hairs are GREY (else lit pigmented hair)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("hair_read_capture", "hair_read_measures", "hair_read_read", "hair_read_compare", "hair_read_start")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
