"""Likeness: a checklist of facial features, measured the same way on a reference picture and on the model.

The user (2026-10-08): "a checklist of facial features to specifically look for and match from references. Your image
comprehension is good, but it works better if it knows where to focus." So:

- `likeness.json` is the checklist (FISWG's component list + likeness artists' order + Farkas' landmarks: see
  likeness_guide.md). Each item: what to look at, which views show it, a MEASURE, a tolerance, the control that fixes
  it, and the fitting stage it belongs to (big to small, as artists work).
- Every measure is a 2D quantity in the reference picture, read on BOTH sides through the same fitted camera
  (human_refs.json): the photo's points and the model's points, in mm at the face's depth. Where it can, both sides
  use the SAME detector (MediaPipe Face Landmarker, 478 points) on the photo and on a clay render of the model through
  that camera, so a definition the detector gets wrong (a jaw contour, iris vs eyeball centre) is wrong the same way
  on both. Where it can't (no detector, a point the clay can't show: brows are paint), the model's own landmarks are
  used and the item says so.
- `measure_reference(name)`: the target sheet (every item measured on the references once, with its view, confidence
  or "unmeasurable"), saved as <model>/likeness_targets.json.
- `report(name)`: the table ranked by miss beyond tolerance, and FOCUS PANELS (photo | model at the same crop and
  camera, the feature drawn on both) for the top misses.
- `stages(name)` / `fit_stage(...)`: the staged fit from the sheet in artists' order (see STAGES), each through an
  existing humanfit control with its integrity gate, earlier stages' points kept as targets in later ones.

This module measures and focuses; it changes a model only through humanfit's guarded fits (fit_stage).

Where the code is (split by responsibility, as C414): this module holds the constants, the checklist and LEVERS.
likeness_detect: MediaPipe detection. likeness_render: the clay render. likeness_measure: Side and value.
likeness_sides: photo_sides, model_sides, measure_sides. likeness_compare: measure_reference, compare.
likeness_notes: what the pictures can support, the table's text. likeness_panels: focus panels, report.
likeness_stages: the stage plan and the lever helpers. likeness_fit: fit_stage, the profile fit, fit_likeness.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from . import moved

CHECKLIST = Path(__file__).with_name("likeness.json")
VENV = os.environ.get("HIFIPUSHIE_MEDIAPIPE", "/mnt/data/hifipushie/facerefs_venv")
DETECT_PX = 768       # the face crop is scaled to this before detection (MediaPipe works on ~200-800 px faces)
NEAR = 0.02  # m: faces nearer the camera than this (or behind it) are not drawn: a close phone camera beside the head
# put the body behind it, and those projected through the eye as screen-filling triangles
RENDER_PX = 900       # the model's render of the face box, across its longer side
TARGETS = "likeness_targets.json"

# dlib's 68 from MediaPipe's 478 (the table onemesh2's detect.py used for human_refs.json)
MP68 = [162, 234, 93, 58, 172, 136, 149, 148, 152, 377, 378, 365, 397, 288, 323, 454, 389,
        71, 63, 105, 66, 107, 336, 296, 334, 293, 301,
        168, 197, 5, 4, 75, 97, 2, 326, 305,
        33, 160, 158, 133, 153, 144, 362, 385, 387, 263, 373, 380,
        61, 39, 37, 0, 267, 269, 291, 405, 314, 17, 84, 181,
        78, 82, 13, 312, 308, 317, 14, 87]
MP_EYES = (468, 473)   # iris centres: the subject's right (image left), left
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150,
        136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
_MP_TO_LM = {m: i for i, m in enumerate(MP68)}
_MP_TO_LM[MP_EYES[0]] = 69   # humanfit: 68 = eye.L (subject's left), 69 = eye.R
_MP_TO_LM[MP_EYES[1]] = 68


def checklist() -> list:
    """The items; `control` says what the staged fit uses: "solve <measure>" (humanfit_solve.solve, wired), the stage's own
    control (fit_outline, fit_hood), or GAP + what a person would use by hand."""
    out = json.loads(CHECKLIST.read_text())["items"]
    for it in out:
        c = it["control"]
        if it.get("solve"):
            it["control"] = f"solve {it['solve']}"
        elif it["id"] in LEVERS:
            it["control"] = f"lever {LEVERS[it['id']][0]}"
        elif not any(w in c for w in ("fit_outline", "fit_hood")) and it["measure"]["kind"] != "judge":
            it["control"] = ("" if c.startswith("GAP") else "GAP: ") + c.replace("fit_views", "points by hand (fit_views / nudge)")
    return out


def stage_names() -> list:
    return json.loads(CHECKLIST.read_text())["stages"]


# ---- detection (MediaPipe in its own venv: Apache-2.0, not a dependency of the package) ----------------------------
_DETECT_SRC = r'''
import json, sys
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision
from PIL import Image
opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=sys.argv[2]), num_faces=1,
                                    output_face_blendshapes=True, output_facial_transformation_matrixes=True)
det = vision.FaceLandmarker.create_from_options(opts)
out = []
for p in sys.argv[3:]:
    im = Image.open(p).convert("RGB")
    res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(im)))
    if not res.face_landmarks:
        out.append(None)
        continue
    d = {"P": [[q.x * im.size[0], q.y * im.size[1]] for q in res.face_landmarks[0]]}
    if res.face_blendshapes:
        d["bs"] = {b.category_name: round(float(b.score), 4) for b in res.face_blendshapes[0]}
    if res.facial_transformation_matrixes:
        d["M"] = np.asarray(res.facial_transformation_matrixes[0], float).tolist()
    out.append(d)
json.dump(out, open(sys.argv[1], "w"))
'''

_RUN = []
KEY = np.array([-0.35, -0.45, -0.82])  # camera frame (x right, y down, z into the picture): a soft key from the upper left

KEY /= np.linalg.norm(KEY)
SKIN = np.array([222.0, 196.0, 176.0])

SHADOW_MM = 0.25     # shadow / AO depth maps: mm per map pixel
AO_DIRS = 96         # AO: directions over the sphere (a Fibonacci set), each one orthographic depth map


OCCLUDE_R = 0.2      # m: occluders are the mesh within this of the eyes' midpoint (a one-mesh body is 1.7 m tall:

SOFT_N = 16   # soft shadows: samples over the light's disc

REFIT = ("three_quarter", "profile")  # views whose camera is refitted on the detector's points (a loose painting)
REFIT_ROUNDS = 2
INFER_TOL = 1.5     # a profile item read from a three-quarter view ("inferred"): its tolerance x this
SPECIAL = ("shape", "jaw", "contour")   # measured in compare (they need the model's render or a trace), not from points alone

SHADE_LIGHT = "sh"   # the shading rows' light: "sh" (fit_light_sh) | "linear" (fit_light: c0 + w.n), as before 2026-10-10

MIRROR = {61: 291, 234: 454, 33: 263, 133: 362, 145: 374, 159: 386, 129: 358, 98: 327, 172: 397, 105: 334, 70: 300,
          107: 336, 52: 282, 58: 288, 136: 365, 116: 345, 123: 352, 50: 280, 205: 425, 147: 376, 187: 411, 93: 323}

CONTOUR_WHY = {"upper_lip": "the lips don't break this contour (no notch between them at this angle)",
               "lower_lip": "the lips don't break this contour (no notch between them at this angle)",
               "forehead_slope": "the trace doesn't run 4 cm up the forehead"}

# ---- what a set of pictures can support -----------------------------------------------------------------------------
YAW_DOUBT = 6.0        # deg between the detector's head yaw and the fitted camera's: past it the picture isn't one projection
YAW_MM = 0.5           # mm of tolerance added per degree of that doubt on a turned view's depth items (1 deg ~ 1 mm of gap)
YAW_ITEMS = ("nose_gap", "nose_tip", "cheek_line", "chin_projection", "brow_ridge")
EXPR = {"smile": (("mouthSmileLeft", "mouthSmileRight"), 0.3), "mouth open": (("jawOpen",), 0.15),
        "squint": (("eyeBlinkLeft", "eyeBlinkRight", "eyeSquintLeft", "eyeSquintRight"), 0.45),
        "brows raised": (("browInnerUp", "browOuterUpLeft", "browOuterUpRight"), 0.4),
        "frown": (("browDownLeft", "browDownRight"), 0.45)}
# THE RULE: an expression read on a reference is not the person's shape. The items it moves are fitted through the
# model's POSE (base.head.pose: an expression), not its identity; the neutral head keeps typical values.
EXPR_BIAS = {"squint": ["eye_opening", "eye_aspect", "upper_lid_show", "brow_eye"],
             "frown": ["brow_eye", "brow_tilt", "brow_arch"],
             "brows raised": ["brow_eye", "brow_arch", "brow_tilt", "eye_opening", "upper_third"],
             "smile": ["mouth_corner_tilt", "mouth_width", "nasolabial_fold", "upper_lip", "eye_opening", "width_mouth"],
             "mouth open": ["lower_third", "lower_over_middle", "face_height", "chin_height", "upper_lip", "lower_lip",
                            "lip_ratio", "mouth_line"]}
# item -> the pose lever that takes it when an expression biases it (path, step, range, default)
EXPR_LEVERS = {"eye_opening": ("pose.lid_upper", 0.001, (-0.003, 0.004), 0.0),
               "brow_eye": ("pose.brow_inner", -0.001, (-0.004, 0.003), 0.0),
               "mouth_corner_tilt": ("pose.smile", 0.001, (-0.004, 0.004), 0.0)}

# ---- focus panels: photo | model at the same crop and camera, the feature drawn on both -----------------------------
PANEL_PX = 300
PHOTO_COL, MODEL_COL = (255, 60, 40), (40, 210, 255)

# ---- staged fitting from the sheet: big to small, each stage through an existing control, guarded ------------------
JAW_CONTOUR = set(range(0, 7)) | set(range(10, 17))  # the 68's jaw contour: GNM's and the detector's differ (onemesh2):
#                                                     widths come from the outline fit instead; the chin (7-9) stays

_PHOTOS = {}

LEVERS = {
    # item id: (path in base.head, step, (lo, hi), default) -- 1-D secant fits on the item's own signed miss
    "cheek_hollow": ("shape.hollow", 0.002, (0.0, 0.008), 0.0),
    "corner_temple": ("shape.planes", 0.3, (2.0, 3.2), 2.0),
    "corner_cheekbone": ("shape.planes", 0.3, (2.0, 3.2), 2.0),
    "corner_jaw": ("shape.jaw_angle", 0.0015, (0.0, 0.005), 0.0),
    "brow_ridge": ("features.brow_ridge", 0.5, (-1.5, 1.5), 0.0),
    "under_eye": ("shape.under_eye", 0.3, (0.0, 1.0), 0.0),
    # onemesh2's jaw control (base.head.shape.jawline: the mandible as an L), driven by the traced jaw
    "jaw_gonion_lobe": ("shape.jawline.below_lobe", 0.008, (0.02, 0.07), 0.045),
    "jaw_gonion_mouth": ("shape.jawline.below_lobe", 0.008, (0.02, 0.07), 0.045),
    "jaw_ramus": ("shape.jawline.forward", 0.006, (-0.01, 0.02), 0.004),
    "jaw_neck_step": ("shape.jawline.tuck", 0.003, (0.0, 0.008), 0.0),
    "canthal_tilt": ("nudge:eye_outer.L:z", 0.001, (-0.004, 0.004), 0.0),
    "nose_length": ("nudge:nose_tip:z", 0.002, (-0.006, 0.006), 0.0),
    "nose_projection": ("nudge:nose_tip:y", -0.002, (-0.006, 0.006), 0.0),
    "mouth_corner_tilt": ("pose.smile", 0.001, (-0.004, 0.004), 0.0),
}

LEVERS["prof_brow_ridge"] = ("features.brow_ridge", 0.4, (-1.5, 1.5), 0.0)

LEVERS["prof_nose_base"] = ("shape.nose_tip.up", 5.0, (-10.0, 25.0), 0.0)   # the tip turned up / down (deg)
LEVERS["prof_tip_height"] = ("shape.nose_tip.up", 5.0, (-10.0, 25.0), 0.0)
# onemesh2's controls (581dc3e): the tip blunted, the chin's own form
LEVERS["prof_tip_radius"] = ("shape.nose_tip.round", 0.4, (0.0, 1.5), 0.0)
LEVERS["prof_chin"] = ("shape.chin.project", 0.002, (-0.004, 0.010), 0.0)
LEVERS["width_chin"] = ("shape.chin.width", 0.002, (-0.006, 0.010), 0.0)
LEVERS["prof_cheek_line"] = ("shape.hollow", 0.002, (0.0, 0.008), 0.0)
# (facesliders, 2026-10-09) the eye items on the one mesh's face sliders (faceslide.py: morph targets in [-1, 1]):
# the corner tilt turns the fissure on the ball (it was a landmark nudge), the platform's show is the fold's edge,
# the under-eye's depth the tear trough, the brow ridge the skin over the supraorbital rim (features.brow_ridge moved
# the forehead's slope instead: likeloop). Crease height / depth are read by faceslide.read_eyes (the detector has no
# crease point) and solved by faceslide.fit.
LEVERS["canthal_tilt"] = ("sliders.canthal_tilt", 0.25, (-1.0, 1.0), 0.0)
LEVERS["upper_lid_show"] = ("sliders.eye_platform", 0.25, (-1.0, 1.0), 0.0)
LEVERS["under_eye"] = ("sliders.eye_tear_trough", 0.25, (-1.0, 1.0), 0.0)
LEVERS["brow_ridge"] = ("sliders.brow_ridge", 0.25, (-1.0, 1.0), 0.0)
LEVERS["prof_brow_ridge"] = ("sliders.brow_ridge", 0.25, (-1.0, 1.0), 0.0)
# the mouth's: the bow's depth, the lips' eversion (volume forward: what the profile and the E-line see)
LEVERS["cupid_bow"] = ("sliders.lip_bow", 0.25, (-1.0, 1.0), 0.0)
LEVERS["lip_projection"] = ("sliders.lip_upper_roll", 0.25, (-1.0, 1.0), 0.0)
LEVERS["prof_upper_lip"] = ("sliders.lip_upper_roll", 0.25, (-1.0, 1.0), 0.0)
LEVERS["prof_lower_lip"] = ("sliders.lip_lower_roll", 0.25, (-1.0, 1.0), 0.0)
# the nose's dorsal widths (shading items: the side wall off the dorsal line against the dorsum)
LEVERS["radix_width"] = ("sliders.nose_radix_width", 0.25, (-1.0, 1.0), 0.0)
LEVERS["dorsum_width"] = ("sliders.nose_dorsum_width", 0.25, (-1.0, 1.0), 0.0)
LEVER_VIEWS = {"shape": ("front",)}   # shading is scored on the front photo only (a painting's light isn't one light)


BARE = {"nose_tip": "up"}   # controls that may be a bare number: which key of their dict form it is

PROFILE_PARTS = {   # part -> (region group(s), contour, heights it reads (levels, mm either side), landmarks held)
    "nose": ("nose_region", "nose", None, None),
    "chin": (["chin_region", "lower_lip_region"], "outer", ("sto", 6.0, "chin", 9.0),
             [i for i in range(17, 68) if i not in (55, 56, 57, 58, 59, 65, 66, 67)]),
    # the cheek's fullness at the mouth's height (the far cheek's line in a turned view), the front outline held
    "cheek": (["left_cheek_region", "right_cheek_region"], "outer", ("sn", 2.0, "sto", 10.0), list(range(17, 68))),
}
PROFILE_ITEMS = {"cheek": ["prof_cheek_line"], "nose": ["prof_nose_tip", "prof_nose_gap", "prof_nose_length", "prof_bridge_bow"],
                 "chin": ["prof_chin", "prof_chin_height", "prof_mentolabial"]}
PROFILE_ROUNDS = 5
PROFILE_DONE = 1.5    # mm rms of the contour's miss at its vertices: done


PROFILE_FRONT = {"nose": list(range(27, 36)), "chin": [7, 8, 9, 56, 57, 58]}


PROFILE_HOLD_N = 60     # region vertices held in the front picture's plane
PROFILE_HOLD_W = 3      # ... each counted this many times against a contour vertex
PROFILE_GAIN = 0.7      # share of the contour's miss asked a round (to the contour, not past it)
PROFILE_SIGMA = 1.6     # a round that takes the region's components past this is not taken (plausibility)


# The modules this one was split into (C419). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("likeness_detect", "likeness_render", "likeness_measure", "likeness_sides", "likeness_compare",
           "likeness_notes", "likeness_panels", "likeness_stages", "likeness_fit")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
