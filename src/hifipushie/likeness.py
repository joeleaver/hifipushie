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
    """The items; `control` says what the staged fit uses: "solve <measure>" (humanfit.solve, wired), the stage's own
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
