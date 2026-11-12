"""The reference pictures as a MEASUREMENT of the skin (the `skin_from_reference` tool): what the procedural skin has
a parameter for is read off the fitted references and the parameters are set from the read. The picture is never the
albedo (likeness_texture is that test: it bakes the picture's light, brushwork and hair, and seams where no camera
looked); the result is the ordinary procedural skin, clean under any light and from any angle.

The instrument is DIFFERENTIAL. Per fitted reference view:
  P  the picture, cropped to the block-in's box
  R  OUR dressed head (the stage: bare skin + eyes) through the same camera under the picture's own fitted light
  A  our albedo at each pixel's surface point (the paint layers evaluated in Python: `albedo`)
  the picture's albedo  T = A x P / R  (the ratio image: the light, the shading, the scattering and the camera's tone
  curve cancel as far as our head and light stand in for theirs; what is left is where the skins differ).
Reads are region means of T against A, and for everything but the base tone DOUBLE differences: a region against the
face's plain skin in the same picture, so exposure and white balance cancel too. The base tone itself needs an
anchor in the picture (`anchor`): the sclera (ours through the same camera: exposure and white balance), else a
plain neutral backdrop (white balance only: the tone's lightness is kept), else nothing (tone not read).

Trust: a pixel counts where the model shows skin facing its camera (`FACE`), the picture's own parser says skin
(faceparse: no hair, cloth, backdrop), and neither picture nor render is clipped.

  capture(name)            -> the views' frames (P, R, surface points, trust), cached on disk by content
  read(name)               -> the measurements (dict + text)
  fit(name, read)          -> new spec["skin"] + the side-effect report
  apply(name, out=None)    -> read + fit + save (to `out`, or onto `name`)

Where the code is (split by responsibility, as C414): this module holds the constants and the colour spaces.
skin_read_frames: the dressed stage, `capture`, `trust`, the atlas source, our albedo. skin_read_context: the anchor,
the tone, the shade's colour, the regions. skin_read_reads: lips, freckles, brows, irises, `read`. skin_read_params:
what the fit may set. skin_read_fit: `fit`, `apply`. skin_read_folds: the fold detectors, `fold_read`.
skin_read_fold_fit: `fold_text`, `fold_fit`.
"""
from __future__ import annotations

import numpy as np
from . import moved

VERSION = 1
N = 512                 # px across a view's crop (the block-in's box)
FACE = (0.35, 0.7)      # cos between the skin's normal and the way to the camera: no trust .. full
CLIP = (0.02, 0.97)     # picture / render values (0..1, any channel) outside this are clipped: not read
STAGE = "_sr_"          # this reader's own dressed stages (never the look_skin / judging-sheet ones)
# the dressed render's light before it is re-aimed to the picture's own (blockin_look.photo_lighting): a big soft source
# above and in front, a weak frontal fill, a pale room (the judging sheets' stage light)
LIGHT = {"lights": [{"dir": [0.08, -0.74, 0.67], "energy": 3.3, "color": [1.0, 0.975, 0.95], "angle": 38,
                     "window": {"size": [1.4, 1.0], "distance": 2.2, "gain": 0.2}},
                    {"dir": [0.0, -1.0, 0.05], "energy": 0.7, "color": [1.0, 0.98, 0.97], "angle": 40, "shadow": False,
                     "specular": 0.0}],
         "world": {"color": [0.8, 0.8, 0.8], "strength": 0.45}, "view": "Standard", "exposure": 0.0}
EEVEE = {"fast_gi_resolution": "1", "fast_gi_quality": 1.0, "fast_gi_step_count": 16, "fast_gi_ray_count": 4}


def _lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(lin):
    lin = np.clip(np.asarray(lin, float), 0, None)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def lab(lin):
    """CIE Lab (D65) of LINEAR rgb."""
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = np.clip(np.asarray(lin, float), 0, None) @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _unlab(L):
    """LINEAR rgb of CIE Lab (D65): lab's inverse."""
    L = np.asarray(L, float)
    fy = (L[..., 0] + 16) / 116
    f = np.stack([fy + L[..., 1] / 500, fy, fy - L[..., 2] / 200], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    Mi = np.linalg.inv(np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]]))
    return xyz @ Mi.T


def _lab_scale(L, k: float):
    """Lab colours of the same surfaces k x as bright (linear)."""
    L = np.asarray(L, float)
    fy = (L[..., 0] + 16) / 116
    f = np.stack([fy + L[..., 1] / 500, fy, fy - L[..., 2] / 200], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * k
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


# ---------------------------------------------------------------- the read
ZONES = ("forehead", "temple", "glabella", "nose_bridge", "nose_tip", "nose_wing", "cheek", "cheekbone", "cheek_side",
         "under_eye", "eyelid", "upper_lip", "philtrum", "mouth_corner", "soul_patch", "chin", "jaw", "jowl")
PLAIN = ("forehead", "cheek", "cheekbone", "nose_bridge", "chin")   # the face's plain skin: the double differences' zero
RHO_BLUR = 1.0          # px: picture and render are blurred this much before their ratio (sub-pixel misregistration)
RHO_CLIP = 4.0          # a pixel whose ratio is this far (x) from the view's median is not skin as we model it
MIN_PX = 40             # a region with fewer trusted pixels (weight sum) is NOT READ
SCLERA_PX = 60          # the sclera anchor needs this many pixels in a view
LIGHT_WHITE = np.array([1.0, 0.976, 0.953])   # our stage light's colour (key and fill), for the backdrop anchor
NEUTRAL = 7.0           # a backdrop within this Lab chroma of grey counts as neutral
LIGHT_SPREAD = 0.06     # a view whose picture / render ratio changes colour across the face by this much (rms of log

WHITE_ALBEDO = 0.8      # a white shirt / collar / paper: what the lightness anchor takes its albedo to be
WHITE_PX = 250          # it needs this many pixels in a view's crop
WHITE_CHROMA = 9.0      # ... within this Lab chroma of grey (after the backdrop's white balance, when there is one)
TONE_BOUND = 3.0        # L*: how far the plain skin's albedo may move from the PRIOR tone's without an exposure anchor
TONE_BOUND_WHITE = 8.0  # ... and with a known white in the picture (its albedo and its light are INFERRED: 0.8, lit as the face)
TONE_CHROMA = 5.0       # Lab a*b*: how far the plain skin's COLOUR may move from the prior's on a backdrop's white balance (a
                        # backdrop "neutral within 7" may be 7 of real colour: Garrett's painted one read his skin +9 b*, and
                        # exposed like the picture the head came out 5 b* too yellow: "orange")

TONE_CHROMA_WHITE = 10.0
TONE_SIGMA = 1.0        # L*: the solve's hold on the prior's lightness (the bound is checked after it)
TONE_SIGMA_WHITE = 12.0   # (the white leads, the bound holds: at 4 the prior took two thirds of what the white said)
WHITE_SIGMA = 0.15      # log: what a white's exposure is worth


WHITE_BACKDROP = 0.8    # a "white" darker than this x a neutral backdrop in the same picture is a pale grey thing, not a white
WHITE_OVER_SKIN = 1.1   # ... and it is brighter than the lit skin by this (albedo 0.8 against at most ~0.65)

SHADE_Q = (0.7, 1.35)    # the shade's colour exponents are kept within this (1 = neutral shade)
SHADE_SIGMA = 1.5        # log: how freely a region's lightness is given to SHADE the head does not cast (a deeper-set
                         # eye, the jaw's turn from the light, a light the fit got wrong) rather than to pigment (at 0.6
                         # a third of Tess's lid shade still pulled on the lid tints: 3.4 L of 15)

PRUNE = 0.25             # half chi2 units: a parameter's move worth less than this to the fit is taken back
PRIOR_TONE = 6.0         # x PRIOR for the tone's three numbers: melanin / blood / undertone trade against each other
                         # (the same colour from many triples); loose, blood ran to 0 on Tess and every layer that
                         # multiplies the tone's blood (lips, lids, flush) went inert, the lips brown from melanin alone

SHADE_SIGMA_PLAIN = 0.05  # ... on the plain zones (the lit skin the exposure is levelled on)
SHADE_SIGMA_BEARD = 0.05  # ... where a beard may be laid: its shadow IS a lightness (little colour of its own)
SHADE_MAX = 0.7          # log: no region is more than this in shade (about -20 L*)
EXPOSURE_SIGMA = 0.2     # log: the free exposure without a white (the read is already levelled on the plain skin, and the
                         # model's plain L* is held to the prior: what is left to it is small. At 0.6 it traded against shade:
                         # on the synthetic F2 head exposure went to x 0.40 with every other region "26-32 L in shade")

SHADE_LOCAL = 0.03       # log: the hold on the shaded regions' lower quartile (shade is local)
SHADE_SAY = 0.1          # log: shade from here on is named in the reply
FACE_BOUND = 3.0         # L*: the WHOLE face's mean albedo (stubble apart) may leave the prior's by this much
ATLAS_SHADE_SIGMA = 0.15  # ... when the source is the de-lit ATLAS: the light and the head's own occlusion are already out,
                          # so what a region reads darker is pigment or a form the head lacks, not a wrong light: the
                          # tints may take it (Stage 2's forms take back what is form)

ATLAS_ZONE_BOUND = (12.0, 8.0)   # ... and the zones may leave the prior further (the measurement is one albedo, all views agreed)
ZONE_BOUND = (4.0, 5.0)  # L*, a*b*: a zone's offset from the face's mean may leave the prior's by this much (pigment that

# ---------------------------------------------------------------- lips: in image space, at the picture's own lips
LIP_YAW = 50.0          # deg: views turned further do not give the detector's lip outline


_MP_LIPS = {"outer_up": [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291], "outer_lo": [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291],
            "inner_up": [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308], "inner_lo": [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]}

# ---------------------------------------------------------------- fine marks: freckles (image space, per view)
SPECK = (0.35, 1.3)     # mm: the band (two Gaussian sigmas) a freckle lives in
SPECK_T = 0.035         # a speck is this much darker (log luminance) than its surround in that band
SPECK_MM = 0.5          # mm a pixel: coarser pictures cannot show freckles (NOT READ)
SPECK_SIZE = (0.4, 12.0)  # mm2: a speck's area

IRIS_R_PX = 10.0          # an iris under this radius (picture px) is not read for colour
IRIS_STEP = (0.2, 5.0)    # the most one read changes the iris' lightness (x); its hue is never clipped per channel
IRIS_Y = (0.012, 0.42)    # linear luminance an iris colour may have (near-black brown .. pale grey-blue)

# ---------------------------------------------------------------- the fit
BOUNDS = {"tone.melanin": (0.0, 1.0), "tone.blood": (0.0, 1.0), "tone.undertone": (-1.0, 1.0),
          "zones.forehead_yellow": (0.0, 3.0), "zones.midface_red": (0.0, 3.0), "zones.nose_red": (0.0, 3.0),
          "zones.perioral_red": (0.0, 3.0), "zones.lower_cool": (0.0, 2.0), "zones.under_eye": (0.0, 2.5),
          "zones.eyelids": (0.0, 2.5), "zones.periorbital": (0.0, 1.5), "features.flush": (0.0, 1.5),
          # (lips.melanin is x the TONE's melanin: on a very fair tone a dark lip needs 10-20. At 9, and lower.melanin no
          # lower than 0.4, Garrett's upper lip stayed 11 L lighter than the painting's: the "stuck" lips. skinfolds)
          "lips.blood": (0.15, 3.0), "lips.melanin": (0.2, 30.0), "lips.lower.blood": (0.3, 2.5), "lips.lower.melanin": (0.1, 2.5), "lips.strength": (0.4, 1.6),
          }
GROUPS = {"tone": ("tone.melanin", "tone.blood", "tone.undertone"),
          "zones": ("zones.forehead_yellow", "zones.midface_red", "zones.nose_red", "zones.perioral_red", "zones.lower_cool",
                    "features.flush"),
          "eyes": ("zones.under_eye", "zones.eyelids", "zones.periorbital"),
          "lips": ("lips.blood", "lips.melanin", "lips.strength", "lips.lower.blood", "lips.lower.melanin"),
          "stubble": (), "brows": (), "freckles": (), "eyeballs": (), "folds": ()}
# ("eyeballs", the iris colour, was not a default until 2026-10-13: on Tess's photographs it turned grey-green irises
# orange-brown: the picture's sclera sits in lid shadow, and the change was clipped per channel. Now read against the
# sclera's bright part with the hue kept (iris_colour): in the default set, so a head no longer keeps the default brown)
DEFAULT_GROUPS = ("tone", "zones", "eyes", "lips", "stubble", "brows", "freckles", "folds", "eyeballs")
SIGMA = (6.0, 0.8, 0.8)     # Lab: what a region's read is worth (lightness carries the shading we do not model)
EXPOSURE = 0.08           # log units: how closely the picture's unknown exposure is held to our skin's lightness. At 0.5
                          # (free) the tone ran DARK: the pigment model reaches a picture's chroma most cheaply by adding
                          # melanin (validation: melanin 0.48 for a truth of 0.30; Garrett came out a tanned
                          # orange-brown). Held, it still runs dark when the picture's skin is far more saturated than the
                          # start (validation: 0.54), stays within ~3 L on the two subjects. The tone's lightness is NOT
                          # a read: check it by eye.
# (also tried: holding the base tone's own L to 1.5. On the far synthetic truth the solve then bent the zones to find the
# chroma: perioral 2.8, flush 1.26, no beard. Taken out.)
BEARD_EVEN = 0.6          # the beard's zone scales are held to their mean this loosely (side zones read lightness, the least
                          # trusted number; free, a jaw at 1 beside cheeks at 0 drew a band with an edge)

LIP_SIGMA_L = 2.5         # the lips' lightness is theirs (a small region, read whole): trusted more than the skin's
IRIS_MM = 0.5             # mm a picture pixel: coarser, an iris is a handful of pixels of lid shadow (Garrett's read x 2)
BROW_COLOUR_MM = 0.8      # coarser, a brow's darkest third is half skin: its colour is not read (its density is)
FIT_POINTS = 50000         # the solve's points (region means do not need every pixel)
PRIOR = 0.04                # the pull back to the start, per share of a parameter's range (least change)
STUBBLE_PROTO = {"amount": 1.0, "style": "short"}
BEARD_MIN = 0.08            # a fitted beard weaker than this share of the prototype is no beard

# ---------------------------------------------------------------- folds: the checklist's detectors
FOLD_T = 0.02          # log luminance: a valley this deep, across a fold's path, is a fold there
FOLD_OWN = 0.7         # ... and this share of our own valley there deeper than ours (the head's own shading under another light)
FOLD_SHARE = 0.3       # ... along at least this share of the path's visible stations
FOLD_MAX = 0.42        # log luminance: deeper than this is not a crease of skin
FOLD_CONF = 0.5        # a fold is laid only from this confidence up
SYMMETRIC = ("tear_trough", "nasolabial", "marionette")   # folds of age that come in pairs: a side that shows a valley
# along too little of its path to count takes the read side's amount x its own valley's share of the other's (INFERRED)
BILATERAL = ("lid_fold",)   # folds every face has on both sides: one side's read stands in for the other
PLACE_MM = 0.7         # mm a picture pixel: coarser, a fold's PLACE across its path is not read (it is laid on its landmark
                       # path, whole): on Garrett's paintings (1.1-1.3 mm) the shifts came out +-5 mm from station to station and the
                       # second round's moves ran to -8 mm

FOLD_MOVE = 1.5        # mm: a fold of ours is moved only when the picture's lies this far from it (median)
FOLD_STEP = 0.25       # mm between a profile's samples
# what an amount-1 fold of ours reads as (median valley depth, log luminance, under the pictures' fitted lights):
# calibrated on synthetic heads (spikes/skinread/foldval.py); the second round corrects what this gets wrong
# (skinfolds, 2026-10-12: recalibrated on the folds as GEOMETRY, spikes/skinfolds/foldval.py case A: nasolabial 0.18 /
# 0.08 by side under a side light, marionette 0.07, mouth_corner 0.10 / 0.09, mentolabial 0.28, tear_trough 0.18 / 0.23,
# glabella 0.15 / 0.11)
# (skinfolds2, the new paths and reliefs, foldval case A on folds2.json: nasolabial 0.23 / 0.15, marionette 0.094,
# commissure 0.076, mouth_corner 0.15 / 0.10, mentolabial 0.27, glabella 0.13 / 0.105)
FOLD_REF = {"nasolabial": 0.19, "marionette": 0.09, "mouth_corner": 0.12, "mentolabial": 0.28, "tear_trough": 0.2,
            "lid_fold": 0.16, "glabella": 0.13, "commissure": 0.08, "chin_notch": 0.1}
# THE STEP (skinfolds): a fold lit from its side is not a valley but a lit / shaded STEP across its line (a painter's
# nasolabial fold under a lamp). Per station: the mean log luminance just past the line on the plus side minus the
# minus side's, the picture's over OURS (our head's own shading across the path cancels), signed by the fitted light:
# with the light from the plus side the wall under the roll is in shade (step < 0), from the minus side it is lit.
STEP_T = 0.045         # log luminance: a step this much over ours, with the light's sign, is a fold there
STEP_LINE = 1.0        # mm: the step's place along a fold may wander this much (rms about its median-filtered course)
STEP_RUN = 10.0        # mm: ... and it runs on at least this far
STEP_MIN = 0.3         # the step per unit of cross light below which it is our light's error, not a fold
STEP_MAX = 1.0         # a fold read by its step alone is laid at most this strong (the step follows the light's angle)
STEP_CROSS = 0.25      # the fitted light must lie this far across the path (|l . across|) for the step to mean a fold
# what an amount-1 fold of ours reads as a step per unit of cross light (|l . across|); calibrated like FOLD_REF
# (case A: nasolabial 0.46 / 0.32, mouth_corner 0.15 / 0.19, mentolabial 0.28, tear_trough 0.16 / 0.71, lid_fold 0.60 /
# 0.69, glabella 0.17 / 0.19)
STEP_REF = {"nasolabial": 0.39, "marionette": 0.2, "mouth_corner": 0.17, "mentolabial": 0.28, "tear_trough": 0.4,
            "lid_fold": 0.65, "glabella": 0.18, "commissure": 0.2, "chin_notch": 0.2}
# THE LID'S CREASE FROM THE LASH LINE (skinfolds): on a picture fine enough, the upper lid's fold line is searched up
# from the PICTURE's own lash line (lidfold.read_lid on the detector's lid: the strongest valley 1.2 mm+ over it, per
# column), not across the model's nominal path: that path sits a crease height over OUR lid and found, on Tess, a
# faint arc above her real fold. shift = the picture's height over the lash line - the nominal path's over the same
# line; amount from the line's darkness over ours.
LID_PRIOR = {"amount": 0.6, "show": (3.3, 2.0), "nominal": 3.45}   # a lid fold the pictures CANNOT resolve is laid from
# norms (INFERRED, said so): the platform show over the lashes, women / men (Price et al. 2009, lidfold.NORMS), against
# the nominal path's own height (0.062 x the pupils' distance); its roll (the hooding) grows with age
LID_COLS = (0.2, 0.35, 0.5, 0.65, 0.8)
LID_REACH = 8.5        # mm over the lashes the line is searched (further up is the brow's own shadow: 11-13 mm on a smooth head)
LID_DARK = 0.08        # read_lid's darkness (0..1): a line is there
LID_REF = 0.36         # what an amount-1 lid_fold of ours adds to that darkness (skinfolds2, lidcal.py: our crease at amount 1,
                       # read on the render at its full size, 0.35 / 0.37 by side; Tess's photographed fold: 0.32. Before
                       # the crease's occlusion was measured in 3D and vanished mid-lid: 0.06-0.10 at amount 1.2)

LEGACY = {"nasolabial": "nasolabial", "marionette": "marionette", "glabella": "glabella"}   # skin.wrinkles' own lines
LEGACY_SHARE = 0.5     # what one unit of the legacy wrinkle is taken to be worth in fold amount when it is replaced
# fields of fine lines (skin.wrinkles' swatch layers): zone, the picture resolution they need (mm a pixel), and what
# one unit of amount adds to the zone's fine-line energy over the cheek's
FIELDS = {"forehead": ("forehead", 0.45, 0.6), "crows_feet": ("crows_feet", 0.45, 0.5), "under_eye": ("under_eye", 0.45, 0.4),
          "lip_lines": ("upper_lip", 0.4, 0.4)}
FIELD_BAND = (0.25, 0.9)   # mm: the band fine lines live in
FIELD_FIT = False          # see fold_fit: the read failed its null
FIELD_T = 0.25             # a zone's fine-line energy this far over ours (x the cheek's) is a difference


# The modules this one was split into (C419). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("skin_read_frames", "skin_read_context", "skin_read_reads", "skin_read_params", "skin_read_fit",
           "skin_read_folds", "skin_read_fold_fit")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
