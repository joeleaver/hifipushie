"""The block-in's EYE step (blockin2, 2026-10-10; eyeruler / eyelid / orbit, 2026-10-11). Joe: "we shouldn't really
ever use our 'fix' [lidfold]"; "We are treating the crease as if it's different from the eyelid but it's not".

ORDER: the ORBIT first (eye depth, brow over the eye: face_ruler's orbit rows, mm:eyes_forward ...: a big-mass
decision), then this step; the lid hangs between the brow and the ball, so the step says when the orbit rows are unread
or off (orbit_status). The step is IDENTITY ONLY by default: in GNM the open-eye fold is an identity feature and the
eye-region expression only shears the lid-to-brow sheet (eyelid: it never forms a fold; the |e| 3-5 of older steps was
standing in for identity). expression=True adds GNM's symmetric eye-region pairs for a real POSE (a squint).
  1. THE OPENING (solve): the identity for the picture's lid margins and corners in mm (the eye ruler: edges, the iris
     as a circle through the limbus; a small picture: the detector's lids in iris radii), with gnm_mm's measures, the
     socket readings and the landmarks off the eyes held where the block-in put them; a picture without a fold line
     (hooded): the visible platform.
  2. THE LID AS ONE STRUCTURE (the shape term): margin, platform on the ball, the turn, the drape, on GNM's own lid
     rings, the turn on the picture's fold line, the margins of 1 held. Default fold="crisp": RECIPE A
     (blockin_lid.fold_step / gnm_fold_design.fold: a designed crisp fold, brows and measures held; turn ~45 deg where the
     donor solve gave ~30). fold="donor": blockin_lid.lid_step toward a donor head's lid (#376). It replaces the three-section template match (crease="s376" | "fold" | "s540" still runs
     that older term: nothing needs it; kept to reproduce the gk_* / er_* models).
  3. THE EYEBALL GUARD: our ball is seated on six lid landmarks, not the lid's surface; a lid lying on the ball can
     let it through (el_f3's brown patch). The lid's stand-off from our ball is measured on the shipped head and the
     designed platform lifted until it clears (blockin_lid.GUARD); reported.
What is NOT here, by decision (Joe, 2026-10-11): the skin-over-skin overhang of her fold (GNM has none) is left alone:
no fine layer, no painted fold line, no crease make-up, no liner.
No lidfold, no lid pose offsets: the result ships as base.head.identity (+ base.head.expression only with
expression=True), the lid pose (lid_upper / lid_lower) cleared.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at blockin_eyes.NAME: C422). blockin_eyes_reader: the model's readers (world frame: Z up, faces -Y): slices,
chains, `Reader`, the crease's shape, the profile. blockin_eyes_evidence: the picture's evidence: the limbus, the
iris' scale and check, photo and ruler evidence, the crease target, the socket. blockin_eyes_solve: the solve:
`solve`, the orbit's status, `eye_step`, and their texts.
"""
from __future__ import annotations

import numpy as np
from . import moved

NE = 20                 # symmetric eye-region expression pairs solved
SIG_LID = 0.05          # iris radii
SIG_TPS = 0.3           # mm
SIG_HOLD = 0.3          # mm (landmarks off the eyes); brows SIG_BROW
SIG_BROW = 1.0
D_LINE = 1.2            # mm: the crease's local depth when the picture shows a line (Tess: 0.7 solved to 0.74 and did not read dressed; 1.2 did)
SIG_LINE = 0.1
DARK_LINE = 0.15        # the picture's fold line darkness above which "a line is there"
HOODED_SHOW = 0.5       # mm: the visible platform when the picture shows no fold line (hooded: the fold covers it)
SIG_HOODED = 0.5
# The crease as a SHAPE (gnmcrease 2; Joe on the sampled heads: #376 / #540 read right dressed, the deepest solve
# (gd_T30, valley 1.64 mm) had the right darkness but the wrong fold). What separates them is the lid's cross-section,
# not depth or the picture's darkness: a low crease (2.4-3 mm over the margin), a short platform (1.7-2.4 mm) that
# barely recedes, and a full fold coming forward above it, the fold line parallel to the lashes; gd_T30 was a sunken lid
# (the platform 4 mm back into the socket, the crease the floor of the hollow at 5 mm). So when the picture shows a
# line, the step matches the upper lid's sections (inner third / pupil / outer third, relative to the lid margin,
# arclength 0.5-8 mm) to a template from GNM's own population (CREASE_SHAPES, blockin_crease.npz: "fold" = the mean of
# the 30 / 1200 sampled heads with a low, narrow, parallel crease; "s376" / "s540" = Joe's two). SUPERSEDED as the
# default by the whole-lid solve (blockin_lid); the picture's line darkness is not a target and is not painted.
CREASE = "lid"          # the shape term: "lid" = none here, the whole-lid solve follows (blockin_lid; the default);
                        # "s376" | "fold" | "s540" = the older three-section template; None = the oldest height + depth target

FOLD = "crisp"          # the whole-lid solve's kind: "crisp" = recipe A (blockin_lid.fold_step / gnm_fold_design.fold: Joe,
                        # 2026-10-11, "as good as it has to get"), "donor" = lid_step toward a donor head's lid

SIG_SHAPE = 0.3         # mm per section point
SIG_LID_SHAPE = 0.02    # iris radii: the lid margins held harder with the shape term on (72 section points pulled the
                        # upper lid open 0.64 -> 0.75 vs the picture's 0.67 at SIG_LID)

SECTION_FR = (0.25, 0.5, 0.75)        # inner third, pupil, outer third (corner to corner)
SECTION_S = np.arange(0.5, 12.01, 0.5)  # mm of arclength from the lid margin (12: to 8 the lid matched but the fold's arc did not read)
SOCKET = ("orbital_rim", "lower_orbit", "eye_depth")   # the socket's readings held (humanmacro, population sd, on the
SIG_SOCKET = 0.15       # mesh WITH the expression): unheld, a fitted fold came with orbital_rim +1.1 / lower_orbit -0.9 sd
# The RULER's evidence (eye_ruler.read on the front picture: mm at the model in each eye's frame, from the iris centre
# found as a circle through the limbus). eyeruler, 2026-10-11: the detector's iris centre sits ~1 mm LOW on Tess's photo
# and on our renders, its lid points are 1-1.5 mm off, and GNM's lm68 corners are not the visible opening's ends, so
# "lids in iris radii at the pupil" matched an eye that was 1.3 mm too open at the top and 3 mm short.
RULER_COLS = np.array([-9.0, -6.0, -3.0, 0.0, 3.0, 6.0, 9.0])   # = eye_ruler.COLS
SIG_MARGIN = 0.15       # mm: a lid margin at a column (the reader's error is 0.2-0.3 mm; +-9 mm columns count half)
SIG_CORNER = 0.3        # mm: a canthus
LO_BIAS = 0.35          # mm: the picture reader puts the lower margin this much higher than the mesh's (waterline)
SIG_MM = 0.3            # mm: gnm_mm's 23 measures + the face's place held at the start's (eyeruler: with the lids matched
                        # in each eye's own frame the solve moved the EYEBALLS apart 1.5 mm to lengthen the inner corner,
                        # and the 68 landmarks don't see the vault, neck or ears: cranium_height -1.1 sd, neck_width -0.9)

RULER_MIN_PX = 30.0     # the picture's iris diameter (px) under which the ruler's margins are not used
OUT_RING = 1.2          # mm: the margin ring's lateral end past the picture's outer canthus (the eyeball's visible end
                        # reads 0.4 mm short under the lashes, and the ring tucks 0.8 mm behind the lids' meeting)

HOLD = [i for i in range(68) if not (36 <= i < 48 or 17 <= i < 27)]
BROWS = list(range(17, 27))


def _names():
    from . import base_identity
    n = [str(x) for x in base_identity._gnm_data()["expression_names"]]
    return [f"left_eye_region_{k:03d}" for k in range(NE)], [f"right_eye_region_{k:03d}" for k in range(NE)], n


_SHAPES: dict = {}

# ---- the picture's evidence ----------------------------------------------------------------------------------------
MIN_IRIS_PX = 12.0        # detector iris radius (px) under which the limbus is not read (Garrett's full-figure concept: a 5 px
                          # iris, 1.1 mm / px: the edge finder returned 9.8 mm where the painting's iris is ~11.6)

LIMBUS_OK = (0.7, 1.15)   # detector iris radius / limbus radius accepted (else the detector's own radius is kept)

_EB: dict = {}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("blockin_eyes_reader", "blockin_eyes_evidence", "blockin_eyes_solve")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
