"""Skin from PROJECTION (the `skin_project` tool): a model's fitted reference pictures laid into the head's own
texture space (the one human mesh's UV atlas, GNM's layout on the head), DE-LIT into albedo, the unseen filled, and
kept as two images the skin lays like any other paint: spec["skin"]["projection"] = {"albedo", "detail", "box", ...}
-> layers "skin:projection" (colour) and "skin:projection_detail" (fine relief), image wrap "uv" (images.py).

What each step does, and what it cannot know (the report says the same per model):
  PROJECT   per texel of the head's atlas and per picture: the picture's colour where its camera sees that skin (the
            view's own fitted camera and expression), the facing angle, and a confidence.
  EXCLUDE   what is not this skin: the picture's hair, clothing and backdrop (the picture's own parse: MediaPipe's
            multiclass segmenter, Apache 2.0; without it a colour rule), the lid margins (lashes, a misregistered eye),
            ears whose picture does not land on the model's ear (measured: the report says so), skin seen at a
            grazing angle.
  DE-LIGHT  picture = albedo x shading. The shading is what THIS head's geometry does under a low-frequency light:
            order-2 spherical harmonics through each texel's own visibility (so ambient occlusion and soft
            self-shadow are in it), plus one soft key light with its cast shadow, per picture and per colour channel,
            fitted on the face's plain skin with the albedo held smooth, then re-fitted against the views' agreed
            albedo (the same skin seen by two pictures has one albedo). What the fit explains is light and goes;
            everything else stays in the albedo: pigment (lips, brows, stubble shadow, freckles, redness), fine lines,
            AND the shading of forms the head does not have (a bag's shadow, a fold's dark side): that part is
            AMBIGUOUS, reported per region as "dark the light does not explain" (neutral = shadow-like, coloured =
            pigment-like), never silently called pigment.
  BLEND     the views' albedos by confidence in two bands (broad colour with wide weights, fine detail from the best
            view), so no seam and no double image.
  FILL      what no picture saw: the mirror image where the other side was seen (INFERRED, lower confidence), then
            OUR procedural skin (the model's own paint layers, evaluated at the texels) retoned to the projected skin
            around it and given fine texture of the projected skin's own statistics, so there is no patch edge.
  DETAIL    a relief map from the albedo's fine dark LINES where the picture is trusted (crow's feet, forehead and
            under-eye lines; coherent line bundles only: specks, hairs and freckles are pigment, not grooves).

  atlas(base)                  the head's texture space (texel -> triangle, barycentric)
  make(name, ...)              the whole pipeline -> {"albedo", "raw", "detail", "conf", "source", "report", ...}
  apply(name, out=None, ...)   make + files + spec["skin"]["projection"] saved
  lookup(spec, pos)            (u, v, weight) of surface points in the atlas (image wrap "uv"); both=True: two
                               coordinate sets blended across the atlas' cut (u, v, u2, v2, s, weight)

Where the code is (split by responsibility, as C424): this module is the family's base: EVERY constant, the colour
helpers and `stale`. skin_project_atlas: UVs, the atlas, interp, image. skin_project_sample: a picture onto the atlas,
what is not this skin. skin_project_light: the fitted light, our albedo. skin_project_eyes: the iris read.
skin_project_detail: region masks and the pipeline's steps. skin_project_make: `make`. skin_project_lookup: the atlas
at surface points. skin_project_model: layers, check, apply, the stage light, the residual, marks.
"""
from __future__ import annotations

import numpy as np
from . import moved

VERSION = 1
SIZE = 2048              # texels across the head's box of the atlas (~0.21 mm a texel)
PAD = 0.004              # atlas units round the head's faces
DEPTH_TOL = 0.002        # m: a texel is seen when it lies this near the camera's own depth buffer
FACE = (0.22, 0.7)       # cos(skin normal, way to the camera): no trust .. full
N_DIRS = 128             # directions of the visibility / light basis (a Fibonacci set over the sphere)
VIS_MM = 0.5             # mm per pixel of the visibility depth maps
KEY_DISC = 7.0           # deg: the key light's half-angle (soft shadow edges)
KEY_SHARE = 0.1          # ... and give this share of the plain skin's light (a "key" that lights nothing is noise)
KEY_GAIN = 0.03          # a key light must cut the fit's residual by this share to be kept
MU = 0.6                 # how far the lights' re-fit follows the views' agreed low-frequency albedo (0: flat skin)
LOW_MM = 6.0             # mm: "low frequency" of the albedo for the re-fit
BAND_MM = 1.2            # mm: the split between the broad band (wide weights) and the fine band (best view)
SHADE_FLOOR = 0.4        # shading under this share of a view's median is not divided out further (noise), and counts less
CAVITY_AO = 0.65         # a texel whose ambient occlusion is under this is one of the model's cavities (nostril, lip line)
CAVITY_MM = 2.5          # mm: "near" such a cavity (a Gaussian's sigma)
CAVITY_DARK = 0.62       # skin there under this x its surroundings (5 mm, same region) is a misplaced cavity's dark
DIP_MM = 3.0             # mm: "its surroundings" for the rule below
DIP = (0.75, 0.92)       # the fitted shading against its 3 mm surroundings: a crease of the MODEL from the second, fully one at the first
DIP_OVER = 1.05          # ... there the de-lit albedo may not exceed this x its own surroundings outside the crease
SHINE = (1.25, 0.3)      # a highlight: luminance over this x the local (1 cm) mean is compressed to this share
MIRROR_CONF = 0.45       # the mirrored side's confidence against a direct view's
EAR_BESIDE = 0.25        # an ear is left out when this share of the band beside the model's ear is skin in the picture
EAR_INSIDE = 0.75        # ... or under this share of the model's ear is
LID_BAND = 0.0013        # m: no picture this near the eyeball's surface (lashes, the margin; grows with the lids' misfit)
LID_OPEN = (0.0003, 0.0006)   # m from the eyeball: the image is transparent within the first, opaque from first + second (the
                         # wet line and caruncle are the live skin's; wider, our eyelid tint showed as a pink ring)

HAIR_GROW = 0.003        # m: the picture's hair grown by this (wisps, its shadow line)
SKIN_DE = 20.0           # (no parser) Lab distance from the picture's skin past which a texel above the brows is hair
OFF_SKIN = 42.0          # (no parser) ... past which a texel anywhere off the features is not skin
DETAIL_MM = (0.35, 0.9)  # mm: the line detector's scales (Gaussian sigmas)
DETAIL_DEPTH = 0.00012   # m: the relief of a full-strength line
INPAINT_MM = (1.5, 3.0, 6.0, 12.0)   # mm: holes are filled from the projected skin within these reaches, nearest first (a lid band, a
                         # nostril, a wisp, the hairline's first centimetre); beyond the last: our skin, retoned

LINE = (0.02, 0.06)      # a line's contrast (log luminance at its own scale): none .. full strength
DETAIL_LID = 0.006       # m: no detail this near the eyeball's surface (the lids)
COHERENT_MM = 2.5        # mm: lines count as grooves where their directions agree over this distance
Y = np.array([0.2126, 0.7152, 0.0722])


def _lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(lin):
    lin = np.clip(np.asarray(lin, float), 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def lab(lin):
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = np.asarray(lin, float) @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(np.maximum(xyz, 1e-9)), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- the atlas
_ATLAS: dict = {}

_MESH: dict = {}

WISP_NEAR = 0.03         # m: loose hairs are looked for this near the parser's hair
WISP_MM = 0.45           # mm: a hair's half-width as the line detector sees it
WISP_DARK = 0.07         # a line this much darker (log luminance, at its own scale) than its sides is a hair


VEIL_NEAR = 0.012        # m: a veil of hair / its shadow is looked for this near the parser's hair
VEIL_DARK = 0.35         # ... where the skin is this much darker (log luminance, 1.5 mm mean) than the skin away from the hair

STRAND_MM = 8.0          # mm: a dark thin line this long, connected to the parser's hair, is a strand of hair wherever it runs

# ---------------------------------------------------------------- the eyes
IRIS_YAW = 35.0          # deg: irises are read in views turned no further than this
IRIS_PX = 12.0           # the limbus' radius in pixels under which an eye is not read
EYE_RING = ((33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7),          # MediaPipe: the lid margins'
            (263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249))       # closed contour, subject's right, left
IRIS_BINS = np.linspace(0.0, 1.2, 25)
IRIS_ZONES = {"inner": (0.0, 0.55), "outer": (0.6, 0.86), "limbal": (0.9, 1.0)}   # shares of the limbus radius (inner starts at the pupil's edge)

# ---------------------------------------------------------------- the pipeline
PLAIN = ("forehead_region", "left_temple_region", "right_temple_region", "left_zygomatic_region", "right_zygomatic_region",
         "left_infraorbital_region", "right_infraorbital_region", "left_cheek_region", "right_cheek_region", "nose_region",
         "chin_region", "left_parotid_region", "right_parotid_region", "upper_lip_region")
NOT_PLAIN = ("upper_lip", "lower_lip", "left_brow_region", "right_brow_region", "middle_brow_region", "left_orbital_region",
             "right_orbital_region", "ears")
REGIONS = {"forehead": ("forehead_region",), "temple": ("left_temple_region", "right_temple_region"),
           "brow": ("left_brow_region", "right_brow_region", "middle_brow_region"),
           "orbit": ("left_orbital_region", "right_orbital_region"),
           "under_eye": ("left_infraorbital_region", "right_infraorbital_region"),
           "cheekbone": ("left_zygomatic_region", "right_zygomatic_region"), "cheek": ("left_cheek_region", "right_cheek_region"),
           "nose": ("nose_region",), "upper_lip_skin": ("upper_lip_region",), "lips": ("upper_lip", "lower_lip"),
           "lower_lip_skin": ("lower_lip_region",), "chin": ("chin_region",), "jaw_side": ("left_parotid_region", "right_parotid_region")}


BEARD_ZONES = ("upper_lip_skin", "lower_lip_skin", "chin", "jaw_side")   # where a beard's shadow may lie: out of the light's COLOUR fit

HARMONISE_MM = 12.0      # mm: the scale of a view's colour cast against the others (a wall's bounce, the fitted light's tint)

# ---------------------------------------------------------------- the atlas at surface points (image wrap "uv")
_LOOK: dict = {}
SEAM = (0.0015, 0.003)   # m: no picture within the first of the atlas' cut, full from the first + the second
CUT_BAND = 0.003           # m: lookup(both=True): side B's share s goes 0 -> 1 over this width, centred on the cut
BODY_FADE = 0.015          # m: the head atlas fades in this far from the body's triangles
REACH = (0.003, 0.004)   # m: full weight within the first of the head's own mesh, none past first + second


def stale(spec: dict) -> bool:
    """The projection was made on another head shape than the spec's (re-run skin_project after the head changes)."""
    from . import likeness_texture as lt
    pj = (spec.get("skin") or {}).get("projection") or {}
    return bool(pj.get("head")) and pj["head"] != lt.head_key(spec.get("base") or {})


# ---------------------------------------------------------------- the residual: procedural skin against the atlas
BANDS_MM = (6.0, 1.2)    # low: broader than the first; mid: between; fine: under the second

# ---------------------------------------------------------------- placed marks (moles), read in the atlas
MARK_MM = (0.5, 0.9, 1.5)   # mm: the blob detector's scales (a mark's radius is ~1.4 x the scale it answers at)
MARK_DARK = 0.10            # a mark is at least this much darker (log luminance, at its own scale) than its surroundings
MARK_ROUND = 0.45           # ... and round: the Hessian's smaller curvature over the larger (a line has ~0)
MARK_MAX = 16               # at most this many, the darkest first


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("skin_project_atlas", "skin_project_sample", "skin_project_light", "skin_project_eyes",
           "skin_project_detail", "skin_project_make", "skin_project_lookup", "skin_project_model")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
