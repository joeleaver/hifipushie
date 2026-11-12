"""Face shapes: ARKit-named morph targets on the game-ready export of a character built with the face kit
(lipsync and expressions for oxidegen; design notes in spikes/face_shapes/README.md).

export_asset(face_shapes=True | [names]) gives every part that moves with the face (the body/head, the kit's teeth
and tongue parts) glTF morph targets named with ARKit blendshape names, on the SAME low-poly vertices as the neutral
mesh. A shape is a displacement of space, D_shape(x), built from the face kit's own anatomy (the lips' parting line,
the mouth corners, a jaw pivot, the lids' margins, brows, cheeks): each target vertex is the neutral vertex moved by
D at that point, so topology and vertex order are identical by construction, nothing is re-meshed or re-projected,
and a lip can't jump onto a tooth. Shapes are deltas, so they add; weight 1.0 is the full extent.

The mouth needs an interior: kits.face.mouth.interior (a slit between the lips through to a mouth bag; teeth and a
tongue in their own parts). The model is meshed with the slit open, so the lips' inner faces are real surfaces; the
export's NEUTRAL closes it (each lip moved half the slit toward the parting line), and jawOpen is a rotation of the
jaw region about the pivot, never a surface appearing. Weights (which region a point belongs to) are measured at the
meshed (open) position, where the upper and lower lip are told apart by the parting line; the move is applied at the
neutral (closed) one.

A GNM head (base.head.source "gnm", class GnmFace) works the other way: each shape is GNM's own expression basis,
solved as the least change of its regional components that moves some of the 68 landmarks and holds the rest (as
base_identity.pose_expression does), carried from the head's skin vertices onto the export's (inverse distance over the
nearest few; the bag, teeth and tongue, away from the skin, take the jaw's rigid motion fitted to the jaw line). It
needs base.head.interior (the kit's slit/bag/teeth/tongue behind the head's lips, base_implied.mouth_interior) and
base.head.mouth_gap >= 0.002 (lips parted while modelling; closed ones are zipped into one seam). The neutral
closes the lips through the basis too. Blinks are pushed out of the eyeball, and sealed on the low poly
(`GnmFace._lid_seal`): both lids' margins are brought onto one smooth line (the basis closes the eye, but each
low-poly margin vertex lands at its own height: a ragged line with dark slots). Only the lids move: a vertex takes the
correction by its distance from its lid's margin (none from 9 mm above / 4 mm below it), so cheek and brow stay.

Either way the neutral's last step is `Face.seal` on the low poly itself: the gap the close left between the lips
(measured across the mouth and a little back from its front, corners included) closed, the lips pressed 0.2 mm past
touching (GNM's close met only at the middle: Garrett's lips stayed ~1 mm apart, corners 5-7 mm open).

Which parts take the shapes (`Face.owns`): the skin the lips are in, the teeth, tongue and eyes, and parts listed in
face_shapes.parts (a beard or brow shell). Clothes never do (Garrett's collar followed his jaw 31 mm).

The export decimates with the lids and lips magnified (focuswarp.py), so the low poly has triangles where the shapes
move; those come on top of the export's budget, the other parts keep what they'd have had without face shapes.

spec["face_shapes"] (optional, stripped from geometry): {"amount": {name: scale (1 = default, 0 = flat)},
  "parts": [part names besides the face's own skin that take the skin's shapes],
  "jaw": {"pivot": joint | [x, y, z], "open": deg at jawOpen 1.0 (18; GNM 14, about the ears' landmarks), "depth": m
  below the parting line where the jaw stops (0.75 x head radius)},
  "lid_seal": false | amount 0..1 | {"amount", "over": m the upper margin goes past the line (0.0003), "band": m
  either side of the line drawn onto it (0.0015), "reach": [upper, lower] m of lid skin that follows (0.009, 0.004)}
  (GNM heads' blinks; false = the basis's own blink: softer skin, a thin slit of eyeball on a low poly)}

The export log gives each skin part's most uneven shapes (`unevenness`: how far a vertex's move lies outside the
range of its edge neighbours' moves, per metre of edge; a smooth shape reads ~0 however steep) and a WARNING over
0.2 for lid, brow, cheek and nose shapes: neighbouring vertices going different ways shear painted detail into a
sawtooth (a blink's under-eye shadow). Mouth shapes are listed but not warned: the lips part at the slit's ends.
The json has them per part as face_shape_unevenness.

Where the code is (split by responsibility, C417; constants back here, C422): this module holds the shape names,
presets, combos, small maths, EVERY constant of the family and the per-character fits (env_fits, character_fits,
refuse_sculpt). A constant is set at faceshapes.NAME (HP_FS_SET, tests, character_fits) and the other modules read it
as faceshapes.NAME when they use it. faceshapes_face: class Face (a kit face). faceshapes_gnm: class GnmFace, with its
methods in mixins by responsibility: faceshapes_gnm_solve (frame, solve, carry), faceshapes_gnm_moves (jaw, smile,
lip lifts), faceshapes_gnm_mouth (teeth, sock, cheeks), faceshapes_gnm_lids (the blink's seal), faceshapes_gnm_lips
(rings, corners, rolls, the seam). faceshapes_apply: apply, read_glb, face_of.
"""
from __future__ import annotations

import numpy as np

from .spec import SpecError
from . import moved

REQUIRED = ("jawOpen", "jawForward", "jawLeft", "jawRight", "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft",
            "mouthRight", "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight", "mouthDimpleLeft",
            "mouthDimpleRight", "mouthStretchLeft", "mouthStretchRight", "mouthRollLower", "mouthRollUpper",
            "mouthShrugLower", "mouthShrugUpper", "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft",
            "mouthLowerDownRight", "mouthUpperUpLeft", "mouthUpperUpRight")
RECOMMENDED = ("eyeBlinkLeft", "eyeBlinkRight", "browInnerUp", "browDownLeft", "browDownRight", "browOuterUpLeft",
               "browOuterUpRight", "cheekPuff", "tongueOut")
# cheekSquint's lift and push forward of the cheek (x the setup's width unit wg) and eyeSquint's lower-lid rise (x the
# lid gap): 0.06 / 0 / 0.35 gave 2.8 mm / 1.8 mm, and the smile review (expr_r2) saw "no cheek raise, no squint". A
# Duchenne smile lifts the cheek 5-8 mm and bunches it forward; the lower lid rises 2-4 mm.
CHEEK_RAISE = (0.13, 0.04)
SMILE_PROTO = ("happy", 2.0)  # mouthSmile / cheekSquint: GNM expression model's class prototype x amount
LIP_CLEAR = 0.0008  # m (GNM frame) a lip is kept in front of the teeth by (_clear_teeth)
SOFT_ROUNDS = 80  # _soft_edge's averaging rounds
SOFT_EDGE = 0.7  # _soft_edge: moves under this share of the shape's largest are blended toward their averaged field
SMILE_SIDE_MM = 6.0  # mm over which a side's smile fades across the midline (tanh)
SQUINT_LOWER = 0.8  # (0.55: 2.8 mm, "eyes unchanged" in the smile, expr_r3)
# the rest of ARKit's 52 (Audio2Face drives eyeWide/eyeSquint/cheekSquint/noseSneer a little; eyeLook* turn the
# eyeballs, which only the eyes' own part carries)
EXTRA = ("eyeWideLeft", "eyeWideRight", "eyeSquintLeft", "eyeSquintRight", "cheekSquintLeft", "cheekSquintRight",
         "noseSneerLeft", "noseSneerRight", "eyeLookUpLeft", "eyeLookUpRight", "eyeLookDownLeft", "eyeLookDownRight",
         "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight")
ALL = REQUIRED + RECOMMENDED + EXTRA
# Correctives (not ARKit names): their weight is a function of other weights, set by the player, never authored.
# ARKit's mouthClose means "lips closed against an OPEN jaw"; Audio2Face drives it to 1.0 with the jaw shut, so a
# mouthClose that closed a full jawOpen's gap on its own pushed the lower lip 29 mm up through the upper lip. Now
# mouthClose alone only seals the lips (a light press), and the closing lives in jawOpen_mouthClose, weighted
# min(jawOpen, mouthClose): the lips meet whatever the jaw does, and an engine that ignores it just shows parted lips.
# (r31) jawOpen_mouthSmile, min(jawOpen, mouthSmile (the sides' mean)): under a smile the upper lip is held up by the
# smile itself, so jawOpen's direct lip lift (JAW_LIP_LIFT, there to bare the incisors of an open jaw) is taken back
# x SMILE_JAW_CANCEL. Without it a smile with the jaw a little open (x45 smileteeth, jawOpen 0.2) bared the gums: the
# inner upper lip 5.6% io above the corner line vs the reference's 2.0.
CORRECTIVES = {"jawOpen_mouthClose": ("min", "jawOpen", "mouthClose"), "jawOpen_mouthSmile": ("min", "jawOpen", "mouthSmile")}
SMILE_JAW_CANCEL = 1.0  # (r33: ON with ROLL_TUCK_COMBINED: sweep19 lmy (with _LM 1) st band 2.6 -> 0.7, st in_up -7.0 -> -5.0 proxy, no dash; c1n (old tuck) had the dash) (r31: OFF. 1.0 in the calibrated proxy (sweep17 c1): st in_up -8.2 -> -6.9 (proxy; ~1.3% io of the
# 3.6 wanted) but a dark / red dash opened in the upper lip's middle above the incisors (a fold where the vermilion is
# pulled down under the jaw solve's own landmark lift): not shipped. 0 = the corrective is not exported)
SMILE_JAW_CANCEL_LM = 1.0  # (r33: 1, sweep19 lmy) (r32) jawOpen_mouthSmile also takes back this share of jawOpen's upper-lip landmark lift
NO_COEFFS = ("cheekPuff",)  # shape_coeffs: a designed offset GNM's expression can't make; set_expression refuses it
CLOSE_LOWER = 0.8  # jawOpen_mouthClose: the lower lip's share of closing the gap jawOpen makes
CLOSE_SEAL = 0.3  # mouthClose alone: how firmly the closed lips push forward (no vertical travel)


def _weight_of(weights: dict, name: str) -> float:
    """A weight by name; a sided pair's base name (mouthSmile) = the mean of its Left / Right."""
    if name in weights:
        return float(weights[name])
    return 0.5 * (float(weights.get(name + "Left", 0.0)) + float(weights.get(name + "Right", 0.0)))


def playback(weights: dict) -> dict:
    """ARKit weights -> the weights to set on the export's morph targets (the correctives filled in)."""
    out = dict(weights)
    for name, (op, a, b) in CORRECTIVES.items():
        if op == "min":
            out[name] = min(_weight_of(weights, a), _weight_of(weights, b))
    return out
# Named expressions = mixes of the exported ARKit shapes (Joe 2026-10-18: "just use the expression parameters"; never
# per-character sculpted deltas). smile: the controls-only mix that read as a mild real smile and beat every
# hand-made smile in a blind review (/mnt/data/hifipushie/happy/NOTES.md); limits accepted (teeth band 81% vs the
# photo's 62%, weak exported squints) unless Joe reopens them. The others are plain starting mixes, not reviewed:
# set_expression takes any mix of the same names.
EXPRESSION_PRESETS = {
    "smile": {"mouthSmileLeft": 0.8, "mouthSmileRight": 0.8, "cheekSquintLeft": 1.0, "cheekSquintRight": 1.0,
                   "eyeSquintLeft": 0.5, "eyeSquintRight": 0.5, "mouthDimpleLeft": 0.6, "mouthDimpleRight": 0.6,
                   "mouthPressLeft": 0.2, "mouthPressRight": 0.2, "mouthUpperUpLeft": 0.108, "mouthUpperUpRight": 0.108},
    "open_mouth": {"jawOpen": 0.6},
    "frown": {"mouthFrownLeft": 0.7, "mouthFrownRight": 0.7, "browDownLeft": 0.5, "browDownRight": 0.5},
    "surprise": {"jawOpen": 0.35, "browInnerUp": 0.8, "browOuterUpLeft": 0.7, "browOuterUpRight": 0.7,
                 "eyeWideLeft": 0.6, "eyeWideRight": 0.6},
    "blink": {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0},
}


def expression(mix) -> dict:
    """An expression's ARKit weights: a preset name (EXPRESSION_PRESETS) or a {shape: weight} mix. Every key must be
    an exported ARKit shape and every weight in [0, 1]: an expression is a parameter mix, nothing else."""
    if isinstance(mix, str) and mix not in EXPRESSION_PRESETS:
        raise ValueError(f"expression: no preset {mix!r}: one of {', '.join(EXPRESSION_PRESETS)}, or a mix {{shape: weight}}")
    w = dict(EXPRESSION_PRESETS[mix]) if isinstance(mix, str) else dict(mix)
    known = set(REQUIRED) | set(RECOMMENDED) | set(EXTRA)
    bad = sorted(k for k in w if k not in known)
    if bad:
        raise ValueError(f"expression: {bad} are not ARKit shapes the export makes (an expression is a mix of them)")
    out = [k for k, v in w.items() if not 0.0 <= float(v) <= 1.0]
    if out:
        raise ValueError(f"expression: weights outside [0, 1]: {out}")
    return {k: float(v) for k, v in w.items()}


# viseme-like combinations for review sheets (oxidegen's presets are its own)
COMBOS = {"AA": {"jawOpen": 0.6, "mouthFunnel": 0.2}, "OO": {"mouthPucker": 0.8, "jawOpen": 0.2},
          "MBP": {"mouthPressLeft": 0.7, "mouthPressRight": 0.7, "mouthRollLower": 0.2, "mouthRollUpper": 0.2},
          "open+close": {"jawOpen": 1.0, "mouthClose": 1.0},
          "EE": {"mouthStretchLeft": 0.5, "mouthStretchRight": 0.5, "jawOpen": 0.25, "mouthSmileLeft": 0.3,
                 "mouthSmileRight": 0.3},
          "FV": {"mouthRollLower": 0.6, "mouthUpperUpLeft": 0.3, "mouthUpperUpRight": 0.3, "jawOpen": 0.1},
          "smile": {"mouthSmileLeft": 1.0, "mouthSmileRight": 1.0, "cheekPuff": 0.2, "browInnerUp": 0.2},
          # Audio2Face's co-activations (oxidegen rig report 2026-10-02: mean weights when both > 0.3), its worst
          # frame on the GNM human, and the full-face channels added for it
          "RL+SL": {"mouthRollLower": 0.64, "mouthShrugLower": 0.48},
          "PK+RL": {"mouthPucker": 0.61, "mouthRollLower": 0.55},
          "PK+CL+JO": {"mouthPucker": 0.6, "mouthClose": 0.56, "jawOpen": 0.46},
          "JO+RL": {"jawOpen": 0.46, "mouthRollLower": 0.49},
          "CL alone": {"mouthClose": 1.0, "jawOpen": 0.04},
          "warm f31": {"mouthClose": 1.0, "mouthPucker": 1.0, "mouthRollLower": 1.0, "jawOpen": 0.58,
                       "mouthShrugLower": 0.55, "mouthFrownLeft": 0.25, "mouthFrownRight": 0.25, "cheekPuff": 0.2,
                       "browInnerUp": 0.15},
          "wide+sneer": {"eyeWideLeft": 0.5, "eyeWideRight": 0.5, "noseSneerLeft": 0.3, "noseSneerRight": 0.3,
                         "browInnerUp": 0.3},
          "squint+look": {"eyeSquintLeft": 0.6, "eyeSquintRight": 0.6, "cheekSquintLeft": 0.6, "cheekSquintRight": 0.6,
                          "eyeLookOutLeft": 0.8, "eyeLookInRight": 0.8, "eyeLookUpLeft": 0.3, "eyeLookUpRight": 0.3}}


def _ss(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _bump(t, a, b):
    """1 up to a, smoothly 0 at b."""
    return 1.0 - _ss((t - a) / np.maximum(b - a, 1e-9))


def _unit(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def _rodrigues(axis: np.ndarray, ang: np.ndarray, v: np.ndarray) -> np.ndarray:
    """v (n, 3) turned about the unit axis (3,) by per-point angles (n,) (radians)."""
    c, s = np.cos(ang)[:, None], np.sin(ang)[:, None]
    return v * c + np.cross(axis, v) * s + axis * (v @ axis)[:, None] * (1 - c)


def vertex_normals(V: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals of a triangle mesh."""
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


UNEVEN_LIMIT = 0.2   # worst `unevenness` over which the export log warns (the lid seal's sawtooth read 0.21 / 0.38,
#                      the same blinks unsealed and repaired 0.05-0.09)
UNEVEN_COUNT = 0.05  # vertices over this are counted

SHAPE_SCULPT = __import__("os").environ.get("HP_SHAPE_SCULPT", "")  # (r48) hand-sculpted shape deltas (npz)


ALLOW_SCULPT_ENV = "HIFIPUSHIE_ALLOW_SHAPE_SCULPT"  # =1: the one explicit opt-out (logged as a WARNING), for research


def refuse_sculpt(path: str, where: str = "HP_SHAPE_SCULPT", log: list | None = None):
    """Expressions are parameter mixes only (Joe 2026-10-18; codified 2026-10-19): a hand-sculpted shape delta file
    raises, wherever it comes from (environment or base.head.face_fits.sculpt). Search the ARKit / GNM mix instead
    (EXPRESSION_PRESETS). Opt-out only with HIFIPUSHIE_ALLOW_SHAPE_SCULPT=1, and then it is a WARNING in the log."""
    import os
    if path and os.environ.get(ALLOW_SCULPT_ENV) == "1":
        msg = (f"WARNING face shapes: {where}={path}: hand-sculpted expression deltas applied under "
               f"{ALLOW_SCULPT_ENV}=1 (refused by default: expressions are parameter mixes)")
        print(msg, flush=True)
        if log is not None:
            log.append(msg)
        return
    if path:
        raise ValueError(f"face shapes: {where}={path}: hand-sculpted expression deltas are refused (an expression is "
                         "a mix of the ARKit / GNM expression parameters, e.g. Tess's smile = mouthSmile .8 + cheekSquint 1 "
                         "+ eyeSquint .5 + ...; search the mix, never sculpt per-character deltas)")


# ---- GNM heads (base.head.source "gnm") ---------------------------------------------------------------------------

# Each ARKit shape on a grafted GNM head is GNM's own expression basis, solved like base_identity.pose_expression: the least
# change of the regional expression components that moves some of the 68 landmarks as said and holds the rest.
# Moves are in GNM's frame (x = the head's left, y up, z forward), in units of the mouth's width (corner to corner);
# ".L" lists name the head's left landmarks and mirror (x flips) for the right. Landmarks: jaw line 0-16 (8 the
# chin), brows 17-21 right / 22-26 left, eyes 36-41 right / 42-47 left (upper lid 37, 38 / 43, 44; lower 41, 40 /
# 47, 46), outer lips 48-59 (48 right corner, 51 upper middle, 54 left corner, 57 lower middle), inner 60-67.
JAW = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
CHIN = [5, 6, 7, 8, 9, 10, 11]
LOWER_LIP = [55, 56, 57, 58, 59, 65, 66, 67]
UPPER_LIP = [49, 50, 51, 52, 53, 61, 62, 63]
LEFT = {"corner": 54, "inner_corner": 64, "upper": [52, 53, 63], "lower": [55, 56, 65], "upper_mid": [51, 62],
        "lower_mid": [57, 66], "brow_inner": [22, 23], "brow_mid": [24], "brow_outer": [25, 26],
        "lid_upper": [(43, 47), (44, 46)], "jaw_side": [12, 13, 14]}
MOUTH_REACH = (0.12, 0.155)  # m from the mouth: the shapes (not the jaw's) fade to 0 over this, unless near the eyes
EYE_REACH = (0.09, 0.115)  # m from between the eyes
JAW_SHAPES = ("jawOpen", "jawForward", "jawLeft", "jawRight", "tongueOut")
HOLD = 0.5   # the weight of holding a landmark a shape doesn't move
LID_SEAL = True   # blinks: both lids' margins brought onto one smooth line on the low poly (GnmFace._lid_seal)
LID_OVER = 0.0008  # m the upper lid's margin goes past that line (0.3 mm left Tess a 0.5-0.75 mm slit, eyegap.py v12)
LID_SAG = 0.0012  # m the closed lids' line dips at mid-eye below its ends (the line over the globe)
LID_BAND = 0.0015  # m either side of the line squeezed onto each lid's own side
LID_REACH = (0.009, 0.004)  # m from its margin (as posed) over which a lid's skin takes the seal: upper, lower
LID_EDGE = (0.0025, 0.0015)  # m from its lid's posed edge within which a vertex counts as margin: upper, lower
LID_OVER_FADE = True  # the upper lid's overlap fades out toward the corners (one skin there, not two sheets)
LID_FADE = (0.44, 0.5)  # of the eye's width from its middle: where that fade starts and ends
LID_PINCH = 3     # how hard that band is drawn to the line: linear (1) parked the margins ~0.5 mm either side of it, a 1.2 mm slit
TONGUE_SINK = 0.003  # (r29: 6 -> 3 with TONGUE_DROP 0: tonguefacing.py, jawOpen: tongue share 0.31 -> 0.41 of the opening, its -n.y (facing the camera) median 0.50 -> 0.57; the reference's tongue fills the opening's lower half lit as a dome, ours rendered a flat dark panel, lum plateau 45 vs the reference's ramp 30 -> 110) m: jawOpen also lowers the whole tongue (its dome kept: flattening alone made a boxy panel
# with vertical sides, expr_r8)
TONGUE_DOME = (0.0, 0.003)  # (r33: back raised 3 mm, a RENDER test: the offset reaches the vertices (|d| 6 mm at the back for 6 mm) and the raster (visible tongue verts move 1.9 mm, normals 7 deg), but the flat proxy is not calibrated on the tongue (v46 jaw ramp: render 75 77 100 142 112, proxy 61 75 75 79 68), so only a render can judge it) (r32) m: jawOpen's tongue front rolled down this much at the tip (top surface, quadratic over the front half); the back raised this much, linear to 0 at the tip (the dorsum tilted to face the camera)
TONGUE_DROP = 0.0  # (r29: 0 with TONGUE_SINK 3 mm: the dome kept, see TONGUE_SINK) (r28: back to 6 with JAW_TONGUE off: expr_r23 sank the tongue to a dark sliver behind the lower row, r22 showed a pale papillae dorsum) (r26: 2 with JAW_TONGUE's bow, which lowers the tip itself; 6 before) (11 with no sink, v22) m: jawOpen flattens the tongue's top this much (its lowest point stays with the jaw); 7 mm
# still filled the opening up to the upper incisors (m20 albedo); the reference shows the dorsum about mid-opening
JAW_TONGUE = (0.0, 0.0, 0.0)  # (r28: off again; (0.002, 0.0, 0.003) with the 52-68 mm ramp read darker / lower than r22 in expr_r23) (r26 fast path: 4 mm down hid the front 50 mm behind the lower row, tongue 0.17 of the opening; 2 mm: 0.29) m (world): jawOpen's tongue SHAPE from GNM's own tongue components (min-norm, like
# tongueOut): tip down, tip back, dorsum mid-line bowed up over its sides (r25: "a flat panel, no tip behind the lower
# teeth, no curved top"; GNM's tongue_mean / 001 / 002 raise the tip and bow the top, 000 pushes it out)
JAW_LIP_LIFT = 0.010  # (r22: 6 mm left two thirds of the upper crowns under the lip, inner landmark lift 0.18 saturates; 7.5 showed a gum band over the crowns, expr_r7) m: jawOpen's direct lift of the upper vermilion (feathered), so the incisors show; 4.5 mm
# left ~4 of the crowns' 7 mm under the lip (m20), the reference shows whole upper crowns with the lip at the gum line
JAW_CORNER_OUT = 0.55  # (r35 with GNM_OPEN 20: sweep35c jd, proxy mouth width 80.9 -> 89.6% io (reference 89.8), opening 61.1 -> 56.2 (55.8), inner w/h 1.2 -> 1.5 (1.5); 0.3 alone gave +3.8 width only) (r24: 0.09 -> 0.11 with the arch, width kept)  # (r17: 0.09 with the smooth sock walls, no pinch; 0.06: a squared opening with pinched corners, expr_r9; 0.04: "a narrow tall O", r10) mouth widths: jawOpen draws each corner out (the lips stretch thin round a wide oval, as in
# an open "ah"; without it the corners only followed the jaw and the opening read as a pursed, everted "O": expr_r7)
JAW_LOWER_BACK = 0.07  # (0.04: still rolled out and sagging, expr_r9) mouth widths: the lower lip's outer edge held back toward the teeth (the rigid turn everted it)
JAW_UPPER_LIFT = (0.26, 0.16)  # (r24: with JAW_ARCH; was (0.18, 0.10))  # (r22: inner 0.12 showed 2.8 mm of the central crowns (reference: whole crowns); outer 0.06 showed ~4 upper teeth in jawOpen, the corners over the laterals; reference 6-8) mouth widths, inner / outer: jawOpen lifts the upper lip's inner edge, the incisors show
JAW_ARCH = 0.9  # (r24: 15% width 0.91 -> 0.79, ref 0.76; upper teeth seen 262 -> 294 mm^2 with the lifts below, fast path)  # jawOpen's upper-lip lifts (JAW_UPPER_LIFT, JAW_LIP_LIFT) taper toward the corners: x (1 - JAW_ARCH u^2),
# u = distance from the mouth's middle over half its width (0: a flat lift, the squared top of r23: 15% width 0.91, ref 0.76)
JAW_ARCH_POW = 3.0  # the taper's power of u (higher: the lift held further out, dropping only near the corners)
GNM_OPEN = 20.0  # (r35: 22 -> 20 with JAW_CORNER_OUT 0.55, the reference "ah" is wider and less tall) deg: jawOpen at 1.0, about the line through the ears' landmarks (0, 16). (14 opened the incisors
# ~17 mm: "the jaw barely drops", review expr_r1; ARKit's jawOpen 1 is a wide open mouth. 22 with JAW_PRIOR: chin
# down 30 mm, the inner lips 24 mm apart, two creases past 120 deg on GNM's skin.)
JAW_PRIOR = 1e-4  # ridge on the GNM coefficients of the jaw shapes (jawOpen, jawForward / Left /
# Right, tongueOut). A rigid turn of the jaw's landmarks is not a move GNM's lower-face basis makes: the near-free
# solve (SOLVE_RIDGE) met it with coefficients to 6-10 sd (norm 12-20) and folded the lips' rolls into shards (37
# creases past 120 deg at 22 deg; 31 flipped triangles at 14). At 1e-4: norm 5.7, the chin drops further, 2 creases.
SOLVE_RIDGE = 1e-6  # the other shapes' solve (as before)
JAW_PRIORED = ("jawOpen", "jawForward", "jawLeft", "jawRight", "tongueOut")
# (not jawOpen_mouthClose: it holds the jaw line still while the lips close, and with the prior that hold slipped:
# A2F's "warm f31" pushed the chin 7 mm forward)
def lid_seal_options(v) -> dict:
    """spec.face_shapes.lid_seal -> {"amount" 0..1, "over", "band", "reach": (upper, lower)} (m). None / True: the
    defaults; False or 0: no seal; a number: that share of it; a dict: any of the four."""
    o = {"amount": 1.0, "over": LID_OVER, "band": LID_BAND, "reach": LID_REACH}
    if v is None or v is True:
        return o
    if v is False:
        return {**o, "amount": 0.0}
    if isinstance(v, (int, float)):
        v = {"amount": v}
    if not isinstance(v, dict) or set(v) - set(o):
        raise SpecError("face_shapes.lid_seal: false, an amount 0..1, or {\"amount\", \"over\", \"band\", "
                        f"\"reach\": [upper, lower]}} in metres (got {v!r})")
    o.update(v)
    r = o["reach"]
    o["reach"] = (float(r), float(r)) if isinstance(r, (int, float)) else (float(r[0]), float(r[1]))
    o["amount"] = float(np.clip(o["amount"], 0.0, 1.0))
    o["over"], o["band"] = float(o["over"]), max(float(o["band"]), 1e-5)
    return o


def _mirror_ids(ids, side):
    """Left landmark ids -> the same on `side` (iBUG 68 numbering mirrors in pairs)."""
    if side == "Left":
        return ids
    pairs = {**{i: 16 - i for i in range(17)}, **{17 + i: 26 - i for i in range(5)}, **{22 + i: 21 - i for i in range(5)},
             36: 45, 37: 44, 38: 43, 39: 42, 40: 47, 41: 46, 42: 39, 43: 38, 44: 37, 45: 36, 46: 41, 47: 40,
             48: 54, 49: 53, 50: 52, 52: 50, 53: 49, 54: 48, 55: 59, 56: 58, 58: 56, 59: 55, 60: 64, 61: 63,
             63: 61, 64: 60, 65: 67, 67: 65, 51: 51, 57: 57, 62: 62, 66: 66,
             27: 27, 28: 28, 29: 29, 30: 30, 31: 35, 32: 34, 33: 33, 34: 32, 35: 31}
    return [pairs[i] for i in ids]


LIP_MEET = 0.0002  # m: (one mesh, own quads) the lips' contact vertices pass the halfway point by this: they touch
LIPS_MEET = True  # (one mesh, own quads) close the neutral's lips on GNM's contact ring (else the landmark close)
# (r44, coordinator 2026-10-16) NEUTRAL_PARTED: the export's neutral keeps the APPROVED head's lips as they are (tp_k19's
# part 0.6-1.3 mm): the close the neutral used to bake in (basis close + lips_meet + corners + rolls_behind, which moved the
# outer lips up to 6 mm and the chin 0.3 mm off the approved head) becomes part of mouthClose instead (sealing is what
# mouthClose / the visemes are for). One mesh, own quads only (index given); a kit face keeps its sealed neutral.
NEUTRAL_PARTED = __import__("os").environ.get("HP_NEUTRAL_PARTED", "1") != "0"
# (r36, fitted shapes) SMILE_FIT: a .npy of GNM's 383 expression coefficients FITTED to a reference smile photo with the
# identity held (assembly/fitexpr.py: face_ruler_solve.read, per-picture expression over a population PCA prior of GNM's face
# expression space; the fitted neutral photo's expression subtracted). Set: mouthSmile = its lower-face components on
# each side (faded across the midline), cheekSquint = its eye components on that side; none of the smile's hand
# constants (SMILE_PROTO / holds / lifts / corner pull / fold) apply. Interior handling (teeth clear / wrap, sock, tucks) stays.
SMILE_FIT = __import__("os").environ.get("HP_SMILE_FIT", "")
# (r37) the fitted smile's two halves (mouthSmile = lower-face components, cheekSquint = eye components) skip the family
# region masks (mouth_mask fades the mouth family out from 35% of the way nose -> lower lid, eye_mask fades the eye family
# in from the nose base): those were made for the hand prototypes' stray moves, and cut the fitted cheek apples
SMILE_FIT_MASK = False
# (r38) JAW_FIT: the same for jawOpen: a .npy of GNM's expression coefficients fitted to the reference jaw-open photo (minus
# the fitted neutral's; assembly/fitexpr.py + fx_inner.py, the lips' visible inner edges read). jawOpen = its lower-face
# components (both sides), teeth cleared; the lower row and the tongue ride it rigidly (_rigid_lower_row), the upper row
# stays (base.head.teeth_place places it). None of jawOpen's hand constants (JAW_CORNER_OUT / LOWER_BACK / lip lifts) apply.
JAW_FIT = __import__("os").environ.get("HP_JAW_FIT", "")
# (r42) the fitted jaw's opening x this (x54-x56 rendered 53.1 against the photo's 55.5 mm: 1.045)
JAW_FIT_GAIN = float(__import__("os").environ.get("HP_JAW_FIT_GAIN", "1.0"))
# (r42) the lips' inner rolls (GNM's lip vertices off the exterior skin) tucked back toward the teeth by this share of the
# mouth's width at a full jawOpen, scaled by each vertex's own opening travel (full from 20% of the width down): the fitted
# jaw turned the rolls toward the camera and stretched them 1.6x, a thick red rim round the opening (r40 rim.py, reviews x54-x56)
JAW_ROLL_TUCK = float(__import__("os").environ.get("HP_JAW_ROLL_TUCK", "0.0"))
JAW_TUCK_FADE = float(__import__("os").environ.get("HP_JAW_TUCK_FADE", "3"))  # (r43) JAW_ROLL_TUCK smoothed over x 0.5 mm
JAW_WIDEN = float(__import__("os").environ.get("HP_JAW_WIDEN", "0.0"))  # (r43) the fitted jawOpen's lips stretched out
# sideways by this share of their distance from the mouth's middle (x a lip / sock weight feathered 6 rounds)
SMILE_FIT_FADE = 0.2  # (r38) with SMILE_FIT_MASK off, the fitted halves still fade over this share of the nose-base -> lower-lid
# height: mouthSmile to 0 AT the lower lids (the apples kept up to just under them; the family rule test_gnm_head_shapes
# holds); cheekSquint is family "mid", which never had a mask. None = no fade (the r37 behaviour)
SMILE_FIT_CARRY = True  # (r39) what SMILE_FIT_FADE takes off mouthSmile (its lower-face components' share AT the lower
# lids: the squint's lid rise and the apples' top, pushed up from below) goes to cheekSquint on the same side instead of
# being dropped: mouthSmile + cheekSquint at 1 = the whole fitted smile again (x53 rendered eye apertures -17.5 / -14.1 % io
# against the fit's own -30 / -20 and the photo's -25 / -19: the fade had cut the squint)
SMILE_FIT_EYE_GAIN = float(__import__("os").environ.get("HP_SMILE_FIT_EYE_GAIN", 1.0))  # (r40) the fitted smile's EYE
# components (cheekSquint's own share) times this. Traced r40 (assembly/r40/lidpos.py, ID pass at the eye's centre columns,
# the same eyeballs): the export carries the fit's lid travel within 0.15 mm (upper -1.27 / lower +1.13 mm vs the GNM head's
# -1.25 / +1.25 on the left), but the export head's neutral opening is 1.3 mm taller than the GNM head's (9.9 vs 8.6 mm: both
# margins ~0.7 mm further out along the whole eye), so the same travel is a smaller share of the aperture (-24 vs -29 %), and
# MediaPipe reads the rendered squint at -17.7 / -13.9 % io against the photo's -25.1 / -18.8. The fit holds the lids (its
# prior), the agent finishes: a gain on the eye components only (the mouth half unchanged). 1 = as fitted
SMILE_LOWLID_GAIN = float(__import__("os").environ.get("HP_SMILE_LOWLID_GAIN", 1.0))  # (r43) the fitted smile's LOWER
# lid travel x this (centre most, corners not): the fit lifts it ~60% of the photo's (lidshape: +3.0 / +2.5 % chord vs +4.7 / +4.5)
SMILE_FIT_FOLD = float(__import__("os").environ.get("HP_SMILE_FIT_FOLD", 0.0))  # (r44) with SMILE_FIT: the hand smile's


# nasolabial fold + cheek mass (SMILE_FOLD, CHEEK_LIFT; not its corner lift: the fit owns the corners) carried on top of the
# fitted smile x this. The fitted smile has no fold and its apples lift +2.6 / +4.6 % io (photo +9.3 / -0.5): every
# blind review since r38 "cheeks don't lift, no fold from the nose wing". 0 = off (the r43 behaviour)
SMILE_FIT_SOFT = 80  # (r37) _soft_edge rounds on the fitted smile's halves (SOFT_ROUNDS for the hand shapes)


def env_fits() -> dict:
    """The per-CHARACTER face-shape inputs set from the environment ({name: file}): fitted expression coefficients
    (HP_SMILE_FIT, HP_JAW_FIT: fitted to one person's photos) and hand sculpts (HP_SHAPE_SCULPT). They apply to WHATEVER
    head is exported, so a shell left with Tess's settings gives Garrett her fitted smile without a word; the export logs
    each one as a WARNING (2026-10-18, the Garrett assembly)."""
    return {k: v for k, v in (("HP_SMILE_FIT", SMILE_FIT), ("HP_JAW_FIT", JAW_FIT), ("HP_SHAPE_SCULPT", SHAPE_SCULPT)) if v}


FIT_KEYS = {"smile": "SMILE_FIT", "jaw": "JAW_FIT", "sculpt": "SHAPE_SCULPT"}  # spec base.head.face_fits key -> global


@__import__("contextlib").contextmanager
def character_fits(spec: dict, log=None, base_dir=None):
    """The per-CHARACTER face-shape inputs from the SPEC: base.head.face_fits = {"smile": .npy, "jaw": .npy, "sculpt":
    .npz} (paths; relative ones from the model's folder). Inside the block SMILE_FIT / JAW_FIT / SHAPE_SCULPT are the
    spec's: a key the spec gives replaces the environment's; one it doesn't is cleared, unless the spec has no face_fits
    at all (then the environment stays, and each value set there is logged as a WARNING: it belongs to whoever set it).
    Restored on exit. (2026-10-18, the Garrett assembly: Tess's fitted smile / jaw sat in env vars and applied to any head.)"""
    import os
    from pathlib import Path
    g = globals()
    old = {v: g[v] for v in FIT_KEYS.values()}
    ff = (((spec.get("base") or {}).get("head") or {}).get("face_fits"))
    say = log.append if log is not None else (lambda m: None)
    try:
        if ff is None:
            refuse_sculpt(SHAPE_SCULPT, log=log)
            for k, v in env_fits().items():
                say(f"WARNING: face shapes: {k}={v} (a per-character fit / sculpt from the environment, applied to THIS "
                    f"head; put it in base.head.face_fits instead)")
        else:
            bad = set(ff) - set(FIT_KEYS)
            if bad:
                raise ValueError(f"base.head.face_fits: unknown keys {sorted(bad)} (known: {sorted(FIT_KEYS)})")
            for k, var in FIT_KEYS.items():
                v = ff.get(k) or ""
                if v and not os.path.isabs(v) and base_dir is not None:
                    v = str(Path(base_dir) / v)
                if k == "sculpt":
                    refuse_sculpt(v, "base.head.face_fits.sculpt", log)
                if v and not os.path.exists(v):
                    raise FileNotFoundError(f"base.head.face_fits.{k}: {v} not found")
                g[var] = v
                if v:
                    say(f"face shapes: {k} fit from the spec: {v}")
        yield
    finally:
        g.update(old)


SMILE_FOLD = (0.0024, 0.0022, 0.002, 0.008)  # (r30: 1.2 -> 2.4 mm with SMILE_FOLD_CORNER 9 mm: x44's fold dip -0.157 / -0.164 vs the reference -0.21 / -0.33 at 1.2 mm) (r24: depth 1.5 -> 1.2 mm with FOLD_PAST 0.15: corners 0 back faces)  # m: the smile's nasolabial crease depth, width; the cheek's push, reach
SMILE_LIFT = (0.001, 0.008)  # (r28: 2 -> 1 mm with SMILE_CORNER_UP 0.6: Tess's corners rose 20.1 / 18.8% io vs the reference 12.1 / 14.1 (lidlift.py); 3D 21.6 / 20.3 -> 15.4 / 14.1) m: the smile lifts each mouth corner this much, fading over this radius
SMILE_UPPER_HOLD = 1.0  # (r35: sweep35c h6 with SMILE_LOWER_HOLD 0.8 and the smile pose smile 0.92 / upperUp 0.3 / lowerDown 0.15: proxy philtrum 12.5 -> 19.3% io (reference 20.0), upper vermilion 15.0 -> 10.1 (10.3), lower 19.6 -> 15.8 (14.2); proxy darkline 1 segment 335+29 where the tree had none: close-up item) (r35) share of SMILE_PROTO's own rise of the upper lip's OUTER edge (landmarks 50-52, half at 49 / 53) taken back in the solve: the philtrum kept (reference smile: philtrum 90% of neutral, ours 52%; the upper lip thins rather than climbs to the nose)
SMILE_LOWER_HOLD = 0.8  # (r35, see SMILE_UPPER_HOLD) share of SMILE_PROTO's own drop of the lower lip's OUTER edge (landmarks 56-58, half at 55 / 59) taken back: the lower lip thinner, not everted (reference lower vermilion 92% of neutral in the smile, ours 118%)
SMILE_CORNER_UP = 0.6  # share of SMILE_PROTO's own mouth-corner rise kept (landmarks 48 / 54 held down by the rest, solved)
SMILE_UPPER_LIFT = (0.003, 1.0, 2.0)  # (r33 REVERTED to 3 mm after expr_r30: with slack -0.3 the smile and smileteeth upper lip split into a hanging centre flap between two dark slots (review MAJOR, review/expr_r30 pair_7 / pair_8); the proxy only showed a short dark segment) (r33: was 3 -> 2 mm with ROLL_TUCK_SLACK -0.3 mm: sweep18d s3u2 proxy smile band 2.7 -> 1.0, smile in_up -4.1 -> -3.1, st band 2.6 -> 1.8, st in_up -8.0 -> -7.0; same faint lip-teeth line as s3 alone) (r29: lipcurve / teethshape: the reference smile's visible teeth top arches UP in the middle (0.7% io above the corner line, no red band); x43's sags 4.4% io below it under a 4% io red inner-lip band: the "slit" read) m: the smile lifts the upper vermilion this much at the middle, x (1 - arch u^power) toward the corners (both sides' halves sum to it)
CHEEK_LIFT = (0.004, 0.012, 0.001, 0.4)  # (r28: the reference smile's cheek highlight rises 0.07 / 0.12 io under the lid, ours 0.02 / 0.04 (cheekprof.py); 4 mm ~ the 0.05-0.08 io short) m: the smile's cheek mass raised this much (Gaussian of this radius, pushed out the
# third; centred this share of the way from the lower lid to the mouth corner), faded to 0 at the lower lid
SMILE_EDGE_LIFT = (0.0, 2, 2.0)  # (r30 REVERTED after x45: the render's band at 0.4 / 0.6 grew 2.3 / 2.8 -> 3.0 / 3.5% io, teeth top +0.6 / +1.1 -> +0.8 / +1.4; the fast path's face-on share did not predict the render) (r30: 1.5 mm with SMILE_UPPER_LIFT 3 mm: fast path smile interior face-on 0.27 -> 0.22, teeth 0.63 -> 0.69, 0 torn; with the vermilion lift at 1.5 mm the edge passes it: 3-4% back faces) (r30) (m, rings, power): the smile lifts the upper lip's EDGE (contact ring + inner rolls, fading over this many rings outward) by m at the middle x (1 - u^power) to 0 at the corners: SMILE_UPPER_LIFT raised the vermilion but its underside rolled forward over the teeth (the band); the edge itself has to ride up the incisors
SMILE_FOLD_CORNER = 0.009  # (r30 sweep14: with it the crease 1.2 -> 3.0 mm all give 0 corner back faces, edge-on 0.45 / 0.55 -> 0.44 / 0.50 at 2.4 mm) m: (r30) the crease and the cheek's push fade to 0 at the mouth corner over this radius (smoothstep), so a deeper fold stays off the corner (r29 sweep12: 1.8+ mm tore it)
SMILE_FOLD_PAST = 0.15  # (r24: 0.35 ran the crease into the corner: 5-7% back faces within 6 mm of each corner -> 0)  # the fold's line runs past the mouth corner by this share of nose-wing-to-corner
ROLL_TUCK_COMBINED = True  # (r33) a corrective's inner rolls tucked against its inputs + itself (the posed rings), not alone
ROLL_TUCK = True  # mouth shapes: the inner rolls kept behind their lip's edge from the front (_rolls_tucked)
ROLL_TUCK_SLACK = 0.0  # (r33 REVERTED to 0 with SMILE_UPPER_LIFT 3 mm, expr_r30 flap; untested which of the two made it) (r33 was: -0.3 mm, sweep18 s3: proxy smile band 2.7 -> 1.2, clean; with SMILE_UPPER_LIFT 2 mm, s3u2) (r31: 0.3 -> 0 with the jawOpen_mouthSmile corrective, calibrated proxy sweep17 t0: smile red band 3.3 -> 2.8 (proxy; render est 2.8 -> 2.3% io), st in_up -6.9 -> -6.7, 0.5 = ~2 sigma of the averaged measure) (r29: 0.3 mm WITH SMILE_UPPER_LIFT 3 mm: fast path smile teeth top at mid +1.9 -> +0.8 mm, teeth shown 6.0 -> 7.0 mm (reference ~6.8), band 1.0 -> 1.5, 0 torn, corner edge-on 0.54 / 0.58 -> 0.45 / 0.55; sweep13 tk3) (r24: 0.3 mm flipped the smile's upper inner lip: 3.6% of the opening back faces -> 0)  # m a roll may hang past its lip's edge
WRAP_TEETH = True  # mouth shapes: the inner lips onto the dental arch (_wrap_teeth)
WRAP_SHAPES = ("jawOpen", "mouthSmile", "mouthUpperUp", "mouthLowerDown", "mouthFunnel", "mouthStretch",
               "mouthDimple")
WRAP_KEEP = 1.0  # share of its rest stand-off a wrapped vertex may keep (1: never further off than at rest)
WRAP_OFFSET = 0.0006  # m: the inner lip's surface this far outside the teeth / gums (the mucosa's own film)
WRAP_REACH = 0.005    # m: a lip standing off the arch by up to this is pulled onto it
WRAP_INSIDE = 0.002   # m: a lip inside the arch by up to this is pushed out onto it
WRAP_ANGLE = 0.0015   # m: across (along the arch) and in height, the teeth a vertex reads
WRAP_CENTRE = 0.022   # m behind the upper incisors' front: the arch's centre (radial directions)
WRAP_RINGS = (-2, 0)  # lip ring levels wrapped, from the sock's 2nd ring in to the contact ring (+ 0)
WRAP_SPREAD = 0.03    # m from the mouth's middle: the wrap's moves fade to 0 by here
WRAP_ROUNDS = 40      # graph-harmonic rounds spreading the moves
SOCK_SMOOTH_REL = True  # _smooth_sock: only what the shape adds (the rest's own smoothing subtracted)
SOCK_SMOOTH = 40      # (r20: back to 40: x32 (0) baked dark-red shards onto the closed upper lip, x31 (40) none; 0 in r17: with retopo.SOCK_FALLOFF the walls are smooth unironed; ironed they stood as flat planes edge-on) Taubin passes over the mouth sock's posed shape in mouth shapes (0: off; _smooth_sock)
SEAM_SHOWING = 0.05  # mm^2: the closed mouth's inside seen from the front over this (neutral, eyeBlink) warns
ROLL_BEHIND = 0.0003  # m: (one mesh, own quads) the closed lips' inner rolls kept this far behind the contact line


def basemod_lip_ring() -> int:
    from . import base as basemod
    return basemod.LIP_RING
ROLL_SMOOTH, ROLL_PASSES = float(__import__("os").environ.get("HIFIPUSHIE_ROLL_SMOOTH", 0.85)), 12  # the lip rings smoothed along themselves at the corners
CORNER_TUCK, TUCK_SPAN = 0.006, 0.3  # (one mesh) m the inner rolls sink back at the corners (the contact ring a third),
# over this share of the mouth's width from each corner: they stood out through the lips as lumps (reduced, not cured)
CORNER_CLOSE, LIP_CORNER = 1.0, 0.2  # (one mesh) the rings in front of the contact ring close at the corners
LIP_TAPER = 0.04  # share of the mouth's width over which the close tapers to nothing at each corner
LIP_HOLD, LIP_FADE = 2, 4  # rings past the contact ring that ride with it fully (the lip's front), then fade out over


def family(name: str) -> str:
    """Which part of the face a shape belongs to: "mouth" (jaw, mouth, cheekPuff, tongue, the corrective), "eye"
    (lids, brows), "mid" (noseSneer, cheekSquint: between the two), "look" (the eyeballs)."""
    if name.startswith(("eyeBlink", "eyeWide", "eyeSquint", "brow")):
        return "eye"
    if name.startswith(("noseSneer", "cheekSquint")):
        return "mid"
    if name.startswith("eyeLook"):
        return "look"
    return "mouth"


# The modules this one was split into (C417). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("faceshapes_face", "faceshapes_apply", "faceshapes_gnm", "faceshapes_gnm_solve", "faceshapes_gnm_moves",
           "faceshapes_gnm_mouth", "faceshapes_gnm_lids", "faceshapes_gnm_lips")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
