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

Where the code is (split by responsibility, C417): this module holds the shape names, presets, combos and small maths.
faceshapes_consts: a GNM head's constants and the per-character fits (SMILE_FIT, JAW_FIT, SHAPE_SCULPT and LID_SEAL are
rebound at run time: read them as faceshapes_consts.NAME). faceshapes_face: class Face (a kit face). faceshapes_gnm:
class GnmFace, with its methods in mixins by responsibility: faceshapes_gnm_solve (frame, solve, carry),
faceshapes_gnm_moves (jaw, smile, lip lifts), faceshapes_gnm_mouth (teeth, sock, cheeks), faceshapes_gnm_lids (the
blink's seal), faceshapes_gnm_lips (rings, corners, rolls, the seam). faceshapes_apply: apply, read_glb, face_of.
"""
from __future__ import annotations

import numpy as np

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
