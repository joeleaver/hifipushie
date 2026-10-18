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
base.pose_expression does), carried from the head's skin vertices onto the export's (inverse distance over the
nearest few; the bag, teeth and tongue, away from the skin, take the jaw's rigid motion fitted to the jaw line). It
needs base.head.interior (the kit's slit/bag/teeth/tongue behind the head's lips, base.mouth_interior) and
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
"""

from __future__ import annotations

import numpy as np

from . import spec as specmod
from .spec import SpecError

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


class Face:
    """The face kit's anatomy, read from the kit-expanded spec: mouth frame and parting line, slit, bag, teeth and
    tongue parts, jaw pivot, eyes (lids), brows, cheeks."""

    def __init__(self, spec: dict):
        kits = spec.get("kits") or {}
        faces = [(n, k) for n, k in kits.items() if k.get("type") == "face"]
        if not faces:
            raise SpecError("face_shapes needs a face kit (kits: {\"face\": {\"type\": \"face\", ...}})")
        name, k = faces[0]
        fb = name[:-2] if name.endswith(".L") else name
        m = k.get("mouth")
        if not m or not m.get("interior"):
            raise SpecError(f"face_shapes needs a mouth that can open: kits.{name}.mouth.interior (true, or "
                            "{\"teeth\": true, \"tongue\": true}): a slit between the lips and a mouth bag behind them")
        opts = spec.get("face_shapes") or {}
        self.amount = {str(a): float(v) for a, v in (opts.get("amount") or {}).items()}
        self.skin_parts = {str(p) for p in (opts.get("parts") or [])}
        bad = [a for a in self.amount if a not in ALL]
        if bad:
            raise SpecError(f"face_shapes.amount: unknown shape(s) {bad} (have the ARKit names {', '.join(ALL)})")
        e = specmod.expand_mirror(spec)
        J, B = e["joints"], e["blobs"]
        prims = {p.name: p for p in specmod.compile_prims(spec)}
        self.H = np.asarray(spec["joints"][k.get("head", "head")]["pos"], float)
        self.R = float(spec["joints"][k.get("head", "head")].get("r", 0.05))
        R = self.R
        self.out = _unit(m.get("dir", [0, -1, 0]))
        up = np.array([0.0, 0.0, 1.0])
        self.up = _unit(up - self.out * (up @ self.out))
        self.side = np.cross(-self.out, self.up)  # the creature's left (+X when it faces -Y)
        self.width = float(m.get("width", 0.9 * R))
        self.W2 = self.width / 2
        self.ru, self.rl = float(m.get("upper", 0.07 * R)), float(m.get("lower", 0.08 * R))
        self.lip = max(self.ru, self.rl)
        line = [np.asarray(J[f"{fb}_mouth_line_0"]["pos"], float)] + [
            np.asarray(J[f"{fb}_mouth_line_{i}.L"]["pos"], float) for i in range(1, 6)]
        corner = np.asarray(J[f"{fb}_mouth_corner.L"]["pos"], float)
        self.M = line[0]
        pts = np.array(line + [corner]) - self.M
        self.su = np.clip(pts @ self.side / self.W2, 0, None)
        self.sz = pts @ self.up            # the parting line's height (the smile) by u
        self.sf = pts @ self.out           # and how far forward it is (the lips' front)
        self.corners = {"Left": corner, "Right": corner - 2 * self.side * ((corner - self.M) @ self.side)}
        self._mouth_parts(prims, fb)
        # the nose is bone: mouth shapes leave it where it is (a goblin's nose hangs over its upper lip)
        self.nose = [p for n, p in prims.items() if n.startswith(f"{fb}_nose") and p.op == "add"]
        # noseSneer lifts the wings (levator labii superioris alaeque nasi): it holds only the bridge and ball
        self.nose_bone = [p for n, p in prims.items() if n.startswith(f"{fb}_nose") and p.op == "add"
                          and "_wing" not in n and "nostril" not in n]
        jaw = opts.get("jaw") or {}
        self.lid_seal = lid_seal_options(opts.get("lid_seal"))  # (GNM heads; validated here too)
        self.eyes = {}
        for s, sfx in (("Left", ".L"), ("Right", ".R")):
            lp = prims.get(f"{fb}_lids{sfx}")
            if lp is None or lp.params.get("closed"):
                continue
            bl = B[f"{fb}_lids{sfx}"]
            r = float(lp.params["r"])
            hu, hl = lp.params["cu"] + lp.params["Ru"], lp.params["cl"] - lp.params["Rl"]
            self.eyes[s] = {"c": lp.params["c"], "rot": lp.params["rot"], "r": r, "ro": lp.params["ro"],
                            "hu": hu, "hl": hl, "zc": 0.35 * hu + 0.65 * hl, "w": r * float(bl.get("width", 0.85)),
                            "part": prims[f"{fb}_eye{sfx}"].part if f"{fb}_eye{sfx}" in prims else None}
        if "pivot" in jaw:
            self.P = np.asarray(specmod.resolve_point(e, jaw["pivot"]), float)
        else:  # in front of the ear: back level with the head's centre, half way up from the mouth to the eyes
            eye_z = np.mean([(v["c"] - self.M) @ self.up for v in self.eyes.values()]) if self.eyes else 0.8 * R
            back = (self.M - self.H) @ self.out + 0.1 * R
            self.P = self.M - self.out * back + self.up * 0.5 * eye_z
        self.open = np.radians(float(jaw.get("open", 18.0)))
        self.depth = float(jaw.get("depth", 0.75 * R))
        self.brows = {}
        for s, sfx in (("Left", ".L"), ("Right", ".R")):
            bp = prims.get(f"{fb}_brow{sfx}")
            if bp is not None:
                ax = bp.params["rot"][:, 0] * bp.params["size"][0]
                ends = [bp.params["c"] + ax, bp.params["c"] - ax]
                inner = min(ends, key=lambda q: abs((q - self.M) @ self.side))
                outer = max(ends, key=lambda q: abs((q - self.M) @ self.side))
                self.brows[s] = {"c": bp.params["c"], "inner": inner, "outer": outer, "half": float(bp.params["size"][0])}
            elif s in self.eyes:  # no brow blob: the skin above the eye
                ev = self.eyes[s]
                c = ev["c"] + self.up * 1.6 * ev["r"] + self.out * 0.6 * ev["r"]
                d = self.side * (1 if s == "Left" else -1) * ev["r"]
                self.brows[s] = {"c": c, "inner": c - d, "outer": c + d, "half": float(ev["r"])}
        self.cheeks = {}
        for s, sfx in (("Left", ".L"), ("Right", ".R")):
            cp = prims.get(f"{fb}_cheek{sfx}")
            sg = 1 if s == "Left" else -1
            if cp is not None:
                self.cheeks[s] = (cp.params["c"], float(np.max(cp.params["size"])))
            else:
                c = self.corners[s] + self.side * sg * 0.25 * self.width + self.up * 0.1 * self.width
                self.cheeks[s] = (c - self.out * 0.15 * self.width, 0.3 * self.width)
        self.sneer = {}
        for s, sfx in (("Left", ".L"), ("Right", ".R")):
            wp = prims.get(f"{fb}_nose_wing{sfx}")
            ball = prims.get(f"{fb}_nose_ball")
            if wp is not None or ball is not None:
                p0 = wp if wp is not None else ball
                c, r = np.asarray(p0.params["c"], float), float(np.max(p0.params["size"]))
                if wp is None:
                    c = c + self.side * (1 if s == "Left" else -1) * r
                self.sneer[s] = (c + self.side * (1 if s == "Left" else -1) * r, 1.5 * r)

    def _mouth_parts(self, prims: dict, fb: str):
        """The interior the kit made (kits._interior): slit, bag, teeth and tongue parts."""
        slit = prims[f"{fb}_mouth_slit"]
        self.slit_u = np.clip(((slit.params["P"] - self.M) @ self.side) / self.W2, 0, None)
        self.slit_h = np.asarray(slit.params["V"]["u1"], float)
        self.slit = 2 * float(self.slit_h[0])
        self.slit_part = slit.part
        bag = prims[f"{fb}_mouth_bag"]
        self.bag = np.asarray(bag.params["size"], float)
        self.thick = float(((self.M - bag.params["c"]) @ self.out) - self.bag[1])  # lip front to the bag's front
        self.parts_teeth = {p.part for n, p in prims.items() if n.startswith(f"{fb}_teeth_")}
        rows = [p for n, p in prims.items() if n.startswith(f"{fb}_teeth_")]
        self.teeth_t = min((float(np.min(p.params["V"]["n1"] - p.params["V"]["n0"])) for p in rows), default=1.0)
        self.parts_tongue = {p.part for n, p in prims.items() if n == f"{fb}_tongue"}
        self.tongue = prims.get(f"{fb}_tongue")

    def inside_mouth(self, X: np.ndarray, prims) -> np.ndarray:
        """Which points (n, 3) lie in the mouth's interior (the slit's walls, the bag): within the mouth's box and
        with the slit's own part (`prims`, its field) standing in FRONT of them, the lips. The export's mesh report
        leaves these out of its tear alarm: a bag's corners at a game budget fold, behind closed lips."""
        from . import sdf
        X = np.asarray(X, np.float64).reshape(-1, 3)
        if not len(X):
            return np.zeros(0, bool)
        q = X - self.M
        box = (np.abs(q @ self.side) < 1.3 * self.W2) & (np.abs(q @ self.up) < 2.0 * self.bag[2] + 0.01) \
            & (-(q @ self.out) < self.thick + 2 * self.bag[1] + 0.01)
        out = np.zeros(len(X), bool)
        idx = np.flatnonzero(box)
        far = self.thick + 2 * self.bag[1] + 0.004  # (from the bag's back wall the lips are this far in front)
        for t in np.linspace(0.002, far, max(6, int(np.ceil(far / 0.002)))):
            if not len(idx):
                break
            hit = sdf.field_at(prims, X[idx] + t * self.out, clip=False) < -3e-4
            out[idx[hit]] = True
            idx = idx[~hit]
        return out

    def neutral(self, Xm: np.ndarray, kind: str, index=None) -> np.ndarray:
        """The neutral's move for a part's meshed vertices: the slit closed (the lips only)."""
        return self.close(self.local(Xm)) if kind == "skin" else np.zeros_like(Xm)

    SEAL_BINS = 0.05  # seal(): how far across (of the half width) and
    SEAL_BACK = 0.001  # how far back (m) the gap at a point is measured
    SEAL_PASSES = 3  # measured and closed again on the result
    SEAL_SMOOTH = 8  # passes of smoothing the gap over the mesh
    SEAL_POCKET = 0.85  # past this (of the half width) the gap is closed at every depth (the corners' pockets)
    SEAL_OVERLAP = 0.0002  # the lips pressed this much past touching (met exactly, the low poly's edges left pinholes)

    def seal(self, Xm: np.ndarray, Xc: np.ndarray, T: np.ndarray) -> np.ndarray:
        """The neutral's last step on the skin: whatever gap `neutral` left between the lips, measured on this low
        poly (Xm meshed, Xc closed, T its triangles), closed. Across the mouth (bins of SEAL_BINS half widths, out
        past the corners), the upper lip's lowest point and the lower lip's highest in front of the bag (points over
        each lip's triangles; sides by the parting line at the meshed position, heights at the closed one) leave a
        gap r; each lip moves r/2 toward the other there, fading over a few lip radii up and down, behind the bag's
        front and past the corners (u 1, where the skin is one surface). GNM's basis close met only at the middle: the lips stayed ~1 mm apart and the corners
        open 5-7 mm (dark pockets on Garrett, s0urc3 2026-10-03). Returns the move."""
        D = np.zeros_like(Xm)
        for k in range(self.SEAL_PASSES):  # (each pass closes what the last left: edges that don't line up across)
            D += self._seal_pass(Xm, Xc + D, T)
            if k == 0:
                first = self.sealed
        self.sealed = first
        return D

    def _seal_pass(self, Xm: np.ndarray, Xc: np.ndarray, T: np.ndarray) -> np.ndarray:
        L = self.local(Xm)
        h0c = self.local(Xc)["h0"]  # heights over the parting line at the closed position
        up = L["h0"] >= 0
        front = 0.5 * self.thick  # the gap is measured (and closed in full) in front of this: what shows
        # the lips near where they meet (a goblin's nose over its upper lip and its chin, at the same depth, measured
        # a 4 cm "gap")
        cand = (L["u"] < 1.3) & (L["back"] < front) & (L["back"] > -2 * self.lip) & (np.abs(h0c) < 2 * self.lip)
        xs = L["xs"] / self.W2
        tc = T[cand[T].all(1)]
        side = up[tc]
        tc, side = tc[side.all(1) | (~side).all(1)], side[side.all(1) | (~side).all(1)]  # (one lip's own)
        # points over each triangle (barycentric grid): across, how far back, height at the closed position
        g = np.array([(i, j, 6 - i - j) for i in range(7) for j in range(7 - i)], float) / 6
        px, pb, ph = ((v[tc] @ g.T).ravel() for v in (xs, L["back"], h0c))
        pu = np.repeat(side[:, 0], len(g))
        # the gap r at each point (across, back): the upper lip's lowest point near it minus the lower's highest
        # (a corner's pocket is deeper inside than at its front: per column alone, its back wall hid the front gap)
        from scipy.spatial import cKDTree
        sx, sb = self.SEAL_BINS, self.SEAL_BACK
        tr = [cKDTree(np.c_[px[m] / sx, pb[m] / sb]) for m in (pu, ~pu)]
        hs = [ph[pu], ph[~pu]]

        def gap(qx, qb):
            q = np.c_[qx / sx, qb / sb]
            hit = [t.query_ball_point(q, 1.0) for t in tr]
            out = np.full((len(q), 2), np.nan)  # the gap, and the height half way across it
            for k, (iu, il) in enumerate(zip(*hit)):
                if iu and il:
                    a, b = hs[0][iu].min(), hs[1][il].max()
                    out[k] = a - b, 0.5 * (a + b)
            return out
        mids = np.arange(-1.2, 1.2 + 1e-9, 0.5 * sx)
        r1, z1 = gap(mids, np.zeros_like(mids)).T  # along the lips' front: the profile logged
        self.sealed = (mids, np.clip(np.nan_to_num(r1), 0.0, 2 * self.lip))
        z1 = np.interp(mids, mids[np.isfinite(z1)], z1[np.isfinite(z1)]) if np.isfinite(z1).any() else np.zeros_like(mids)
        zm = np.interp(xs, mids, z1)  # where the lips meet: each point's own, else its column's front
        rv = np.zeros(len(Xm))
        sel = np.flatnonzero(cand & (L["u"] < 1.2))
        if len(sel) == 0 or not len(pu):
            return np.zeros_like(Xm)
        rs, zs = gap(xs[sel], np.clip(L["back"][sel], -2 * self.lip, front)).T
        if np.isnan(rs).all():
            return np.zeros_like(Xm)
        ok = np.isfinite(rs)  # (no lip on one side near it: the nearest measured gap)
        if (~ok).any():
            near = cKDTree(np.c_[xs[sel][ok] / sx, L["back"][sel][ok] / sb]).query(
                np.c_[xs[sel][~ok] / sx, L["back"][sel][~ok] / sb])[1]
            rs[~ok], zs[~ok] = rs[ok][near], zs[ok][near]
        # (zm stays the column's: per point, an upper and a lower point met at different heights and crossed)
        rs = np.minimum(rs, 2 * self.lip)  # (more than that is no gap between lips)
        # inside the corners, behind the front only what the front left: closing the slit's walls by their own
        # (wider) gap pressed the lips together all through and A2F's lip combos (roll + shrug, pucker + roll) then
        # pushed the lower lip up in front of the upper 3-5 mm; the corners' pockets are closed by their own gap
        u_s = L["u"][sel]
        rs = np.where(u_s > self.SEAL_POCKET, rs, np.minimum(rs, np.interp(xs[sel], mids, self.sealed[1])))
        rv[sel] = (np.maximum(rs, 0.0) + self.SEAL_OVERLAP) * _bump(np.abs(xs[sel]), 1.0, 1.15)
        # the rest of the lips (beyond the band the gap was measured in) take the nearest column's front gap
        rest = np.flatnonzero(~np.isin(np.arange(len(Xm)), sel) & (L["u"] < 1.2))
        rv[rest] = (np.interp(xs[rest], mids, self.sealed[1]) + self.SEAL_OVERLAP) * _bump(np.abs(xs[rest]), 1.0, 1.15)
        # smoothed over the mesh (each point's own gap differs from its neighbours': a jagged lip edge), never below
        # the front gap of its column
        e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
        e = np.r_[e, e[:, ::-1]]
        floor = np.where(L["u"] < 1.2, np.interp(xs, mids, self.sealed[1]) * _bump(np.abs(xs), 1.0, 1.15), 0.0)
        for _ in range(self.SEAL_SMOOTH):
            acc = np.bincount(e[:, 0], rv[e[:, 1]], len(Xm)) + rv
            cnt = np.bincount(e[:, 0], minlength=len(Xm)) + 1
            rv = np.where(rv > 0, np.maximum(acc / cnt, floor), rv)
        lat = _bump(L["u"], 1.0, 1.2)
        deep = _bump(L["back"], front, self.thick + 0.6 * self.bag[1])
        hu = _bump(h0c, 0.5 * rv + 1.2 * self.ru, 0.5 * rv + 3.0 * self.ru)
        hl = _bump(-h0c, 0.5 * rv + 1.2 * self.rl, 0.5 * rv + 3.0 * self.rl)
        dz = 0.5 * rv * lat * deep * np.where(up, -hu, hl)
        # never past where the lips meet (+ the overlap): at a corner a lip's last vertices sit near it while the
        # pocket beside them is millimetres open, and its gap carried them across each other
        o = 0.5 * self.SEAL_OVERLAP
        dz = np.where(up, np.maximum(dz, np.minimum(zm - h0c - o, 0.0)), np.minimum(dz, np.maximum(zm - h0c + o, 0.0)))
        return dz[:, None] * self.up

    def off_margins(self, name: str, X: np.ndarray) -> np.ndarray | None:
        """Where `unevenness` judges a shape: everywhere, except a blink's own lid margins (the skin within 3 mm
        of the eyeball). There a blink is uneven on purpose: each margin vertex is brought to the lid line from
        its own height."""
        if not name.startswith("eyeBlink") or not self.eyes:
            return None
        return np.min([np.linalg.norm(X - np.asarray(ev["c"], float), axis=1) - float(ev["r"])
                       for ev in self.eyes.values()], axis=0) > 0.003

    def owns(self, part: str) -> bool:
        """Whether a part takes the skin's face shapes: the face's own skin (the part the lips are in) and any listed
        in spec.face_shapes.parts (a beard or brow shell). Clothes never do: transferred by distance, the jaw
        shapes moved Garrett's collar 31 mm and his jacket's lapel trim 21 mm."""
        return part == self.slit_part or part in self.skin_parts

    LOOK = {"Up": 20.0, "Down": 20.0, "In": 25.0, "Out": 25.0}  # deg at 1.0

    def eye_part(self, Xm: np.ndarray, names) -> dict:
        """The eyeballs' own part: eyeLook<Dir><Side> turns that side's eyeball about its centre (Up/Down about the
        left-right axis, In = toward the nose); every other shape leaves them still."""
        res = {}
        side_of = None
        if self.eyes:
            cs = {s: ev["c"] for s, ev in self.eyes.items()}
            ks = list(cs)
            dist = np.stack([np.linalg.norm(Xm - cs[k], axis=1) for k in ks])
            side_of = np.array(ks)[np.argmin(dist, 0)]
        for name in names:
            d = np.zeros_like(Xm)
            if name.startswith("eyeLook") and side_of is not None:
                s = "Left" if name.endswith("Left") else "Right"
                dr = name[len("eyeLook"):-len(s)]
                if s in self.eyes:
                    c = self.eyes[s]["c"]
                    sg = 1.0 if s == "Left" else -1.0
                    t = {"Up": self.up, "Down": -self.up, "In": -sg * self.side, "Out": sg * self.side}[dr]
                    axis = _unit(np.cross(self.out, t))
                    m = side_of == s
                    rel = Xm[m] - c
                    ang = np.full(m.sum(), np.radians(self.LOOK[dr]) * self.amount.get(name, 1.0))
                    d[m] = _rodrigues(axis, ang, rel) - rel
            res[name] = d
        return res

    def voxels(self) -> dict:
        """{part: voxel}: the export meshes the slit's part at least this fine, so the slit (2+ voxels across) and
        the lips' inner faces are real surfaces."""
        out = {} if getattr(self, "own_quads", False) else {self.slit_part: round(self.slit / 2.2, 5)}
        # (one mesh on its own quads: GNM's lips and sock are the mouth's surfaces, the field's slit isn't meshed)
        for pn in self.parts_teeth:  # a tooth row's thickness 3 voxels across (at a big body's scene voxel the
            # lower row came out in shreds)
            out[pn] = min(out.get(pn, 1.0), round(self.teeth_t / 3, 5))
        return out

    def tri_focus(self, k: float = 2.0) -> list:
        """Spheres the export's decimation magnifies k x (focuswarp.py: more triangles there): each eye's lids (a
        blink moves them an eye radius: on the plain low poly the skin round them showed facets) and the lips."""
        out = [[*map(float, ev["c"]), float(ev["ro"] + 0.3 * ev["r"]), k] for ev in self.eyes.values()]
        return out + [[*map(float, self.M - self.out * 0.5 * self.thick), float(0.45 * self.width), 1 + 0.5 * (k - 1)]]

    # ---- the parting line and the regions -------------------------------------------------------------------

    def local(self, X: np.ndarray) -> dict:
        """Mouth coordinates of points X (n, 3): u (|across| / half width), the height over the parting line h0,
        how far behind the lips' front, the jaw boundary's height h (rising toward the pivot past the corners)."""
        q = X - self.M
        xs = q @ self.side
        u = np.abs(xs) / self.W2
        uc = np.minimum(u, self.su[-1])
        zs = np.interp(uc, self.su, self.sz)
        back = np.interp(uc, self.su, self.sf) - q @ self.out
        h0 = q @ self.up - zs
        pz = (self.P - self.M) @ self.up
        pb = (self.M - self.P) @ self.out
        t = np.clip(back / pb, 0, 1) * _ss((u - 0.9) / 0.7)
        h = h0 - (pz - zs) * t
        return {"xs": xs, "u": u, "h0": h0, "back": back, "h": h, "pb": pb}

    def jaw_weight(self, L: dict) -> np.ndarray:
        """How much of the jaw's motion a point takes: below the parting line (a crisp step across the slit, wider
        past the corners and deep in the bag, so the cheeks and the bag's back wall stretch), in front of the pivot,
        above where the jaw ends under the chin."""
        band = 0.45 * self.slit + 0.5 * self.W2 * np.clip(L["u"] - 0.85, 0, None) \
            + 0.2 * np.clip(L["back"] - self.thick, 0, None)
        below = 1.0 - _ss((L["h"] + band) / (2 * band))
        front = _ss((L["pb"] - L["back"]) / (0.3 * self.R))
        neck = _bump(-L["h0"], self.depth, self.depth + 0.4 * self.R)
        return below * front * neck

    def lips(self, L: dict) -> tuple[np.ndarray, np.ndarray]:
        """The upper and lower lip (weights): either side of the parting line, a few lip radii high, out to the
        corners, from the front to the bag's front wall."""
        b0 = 0.45 * self.slit
        above = _ss((L["h0"] + b0) / (2 * b0))
        deep = _bump(L["back"], self.thick, 1.5 * self.thick)
        lat = _bump(L["u"], 0.95, 1.45)
        up = above * _bump(L["h0"], 1.4 * self.ru, 3.4 * self.ru) * deep * lat
        lo = (1 - above) * _bump(-L["h0"], 1.4 * self.rl, 3.4 * self.rl) * deep * lat
        return up, lo

    def close(self, L: dict) -> np.ndarray:
        """The neutral's move: each lip half the slit toward the parting line (the slit's own height at u)."""
        hs = np.interp(np.minimum(L["u"], self.slit_u[-1]), self.slit_u, self.slit_h)
        b0 = 0.45 * self.slit
        above = _ss((L["h0"] + b0) / (2 * b0))
        lat = _bump(L["u"], 0.75 * self.slit_u[-1], self.slit_u[-1] + 0.04)  # (to the end cap, a flap at the corner)
        deep = _bump(L["back"], self.thick, self.thick + 0.6 * self.bag[1])
        hu = _bump(L["h0"], hs + 1.2 * self.ru, hs + 3.0 * self.ru)
        hl = _bump(-L["h0"], hs + 1.2 * self.rl, hs + 3.0 * self.rl)
        dz = hs * lat * deep * (-above * hu + (1 - above) * hl)
        return dz[:, None] * self.up

    # ---- shapes ----------------------------------------------------------------------------------------------

    def _jaw_move(self, Xn: np.ndarray, wj: np.ndarray, ang: float) -> np.ndarray:
        axis = np.cross(self.up, self.out)
        rel = Xn - self.P
        return wj[:, None] * (_rodrigues(axis, np.full(len(Xn), ang), rel) - rel)

    def displacements(self, Xm: np.ndarray, Xn: np.ndarray, nrm: np.ndarray, kind: str, names,
                      lower: np.ndarray | None = None, index=None) -> dict:
        """{shape: (n, 3) move} for one part's vertices: Xm where they were meshed (weights), Xn the neutral
        (geometry), nrm its vertex normals. kind: "skin" (a part with the face), "teeth" (`lower`: the vertices of
        the lower row), "tongue"."""
        if kind == "eyes":
            return self.eye_part(Xm, names)
        L = self.local(Xm)
        n = len(Xm)
        zero = np.zeros((n, 3))
        out, up, side = self.out, self.up, self.side
        w = self.width
        if kind == "skin":
            wj = self.jaw_weight(L)
            lu, ll = self.lips(L)
        else:
            lu = ll = np.zeros(n)
            if kind == "tongue":
                wj = np.ones(n)
            else:  # teeth: the lower row rides the jaw, rigidly
                wj = np.zeros(n) if lower is None else lower.astype(float)
        # eyeball surfaces of the skin's own part (eyes not given a part of their own) never move, nor does the nose
        eyes_still = np.ones(n)
        for ev in self.eyes.values():
            eyes_still *= _ss((np.linalg.norm(Xm - ev["c"], axis=1) - 1.01 * ev["r"]) / (0.05 * ev["r"]))
        still, sneer_still = eyes_still.copy(), eyes_still.copy()
        if self.nose and kind == "skin":
            from . import sdf
            hold = lambda prims: 1 - _bump(sdf.field_at(prims, Xm), 0.001, 0.25 * self.lip + 0.004)  # noqa: E731
            still *= hold(self.nose)
            if self.nose_bone:
                sneer_still *= hold(self.nose_bone)
        jo = self._jaw_move(Xn, wj, self.open)
        # the lower lip's travel at jawOpen, per point (sampled on the parting line at the point's u): mouthClose
        # closes the gap, the lower lip doing most of it (CLOSE_LOWER)
        seam = self.M + side[None] * L["xs"][:, None] + up * np.interp(np.minimum(L["u"], self.su[-1]), self.su,
                                                                       self.sz)[:, None]
        delta = self._jaw_move(seam, np.ones(n), self.open)
        mreg = _bump(L["u"], 1.15, 2.0) * _bump(np.abs(L["h0"]), 2.5 * self.lip, 6 * self.lip) \
            * _bump(L["back"], self.thick, 2 * self.thick)
        lips = lu + ll
        ctr = _bump(L["u"], 0.0, 1.0)  # 1 at the middle of the mouth, 0 at the corners
        sgn = np.sign(L["xs"])
        res = {}

        def corner(s, a=0.15, b=0.55):
            d = np.linalg.norm(Xm - self.corners[s], axis=1)
            return _bump(d, a * w, b * w) * _bump(L["back"], self.thick, 2 * self.thick) * (kind == "skin")

        def half(s):  # the left / right half of the mouth, soft across the middle
            return _ss((L["xs"] * (1 if s == "Left" else -1)) / (0.6 * self.W2) + 0.5)

        def lip_roll(sel, lip_r, sense):
            """A lip drawn in over the teeth: back into the mouth and toward the parting line (sense +1 the lower
            lip, -1 the upper). A turn about the lip's axis tore where its weight fell off; a move can't."""
            return sel[:, None] * (-out * 0.6 * lip_r + up * sense * 0.45 * lip_r)  # (0.9 back: into the teeth)

        def press(s):
            hh = half(s)
            return hh[:, None] * (lu[:, None] * (-up * 0.3 * self.ru) + ll[:, None] * (up * 0.3 * self.rl)
                                  - lips[:, None] * out * 0.03 * w + lips[:, None] * side * sg_of(s) * 0.02 * w)

        def sg_of(s):
            return 1.0 if s == "Left" else -1.0

        # the upper lip's half of mouthClose follows the jaw weight of the point mirrored below the parting line
        # (at the corners the jaw takes less of the lower lip, and the upper lip must meet it there)
        if kind == "skin":
            Lp = self.local(Xm - 2 * L["h0"][:, None] * up)
            wjp = self.jaw_weight(Lp)
        else:
            wjp = np.zeros(n)

        for name in names:
            s = "Left" if name.endswith("Left") else "Right" if name.endswith("Right") else None
            sg = 1.0 if s == "Left" else -1.0
            if name == "jawOpen":
                d = jo
            elif name == "jawForward":
                d = wj[:, None] * out * 0.08 * w
            elif name in ("jawLeft", "jawRight"):
                d = wj[:, None] * side * sg * 0.08 * w
            elif name == "mouthClose":
                # alone (A2F drives it with the jaw shut): the closed lips firmed forward a little, never into each
                # other (a vertical press here intersected the human's lips on 70 of 765 A2F frames); the closing
                # against an open jaw is the corrective's
                d = lips[:, None] * out * CLOSE_SEAL * 0.03 * w
            elif name == "jawOpen_mouthClose":
                # against a full jawOpen: the lips meet, the lower lip doing most of it (meeting half way, the upper
                # lip hung like a curtain)
                d = -CLOSE_LOWER * jo * ll[:, None] + (1 - CLOSE_LOWER) * delta * (lu * wjp)[:, None]
            elif name == "jawOpen_mouthSmile":  # (the GNM path's corrective; nothing on the older template path)
                d = np.zeros((len(lips), 3))
            elif name == "mouthFunnel":
                c = (1 - 0.6 * np.minimum(L["u"], 1) ** 2)
                d = lips[:, None] * out * 0.09 * w * c[:, None] + (lu - ll)[:, None] * up * 0.06 * w * c[:, None] \
                    - (lips * sgn * np.minimum(L["u"], 1))[:, None] * side * 0.1 * self.W2
            elif name == "mouthPucker":
                c = (1 - 0.5 * np.minimum(L["u"], 1) ** 2)
                d = lips[:, None] * out * 0.12 * w * c[:, None] \
                    - (mreg * L["xs"] * 0.35 * _bump(L["u"], 1.0, 2.0))[:, None] * side \
                    + (ll - lu)[:, None] * up * 0.15 * self.slit
            elif name in ("mouthLeft", "mouthRight"):
                d = mreg[:, None] * side * sg * 0.15 * w
            elif name.startswith("mouthSmile"):
                d = corner(s)[:, None] * (up * 0.1 * w + side * sg * 0.06 * w - out * 0.05 * w)
            elif name.startswith("mouthFrown"):
                d = corner(s)[:, None] * (-up * 0.09 * w + side * sg * 0.02 * w)
            elif name.startswith("mouthDimple"):
                d = corner(s)[:, None] * (side * sg * 0.05 * w - out * 0.06 * w)
            elif name.startswith("mouthStretch"):
                d = corner(s, 0.2, 0.7)[:, None] * (side * sg * 0.09 * w - up * 0.04 * w)
            elif name == "mouthRollLower":
                d = lip_roll(ll, self.rl, 1.0)
            elif name == "mouthRollUpper":
                d = lip_roll(lu, self.ru, -1.0)
            elif name == "mouthShrugLower":
                chin = (1 - _ss((L["h"] + 0.45 * self.slit) / (0.9 * self.slit))) * _bump(-L["h0"], 0.3 * w, 0.8 * w) \
                    * _bump(L["u"], 0.9, 1.6) * _bump(L["back"], self.thick, 1.5 * self.thick) * (kind == "skin")
                d = chin[:, None] * (up * 0.05 * w + out * 0.03 * w)
            elif name == "mouthShrugUpper":
                d = lu[:, None] * (up * 0.05 * w + out * 0.03 * w)
            elif name.startswith("mouthPress"):
                d = press(s)
            elif name.startswith("mouthLowerDown"):
                d = (half(s) * ll)[:, None] * (-up * 0.1 * w + out * 0.02 * w)
            elif name.startswith("mouthUpperUp"):
                d = (half(s) * lu)[:, None] * (up * 0.1 * w + out * 0.02 * w)
            elif name.startswith("eyeBlink"):
                d = self._blink(s, Xm, Xn) if (kind == "skin" and s in self.eyes) else zero
            elif name.startswith("eyeWide"):  # the upper lid up a third of a blink's travel, the lower a little down
                d = self._blink(s, Xm, Xn, -0.35, -0.3) if (kind == "skin" and s in self.eyes) else zero
            elif name.startswith("eyeSquint") or name.startswith("cheekSquint"):
                d = zero.copy()
                if kind == "skin" and name.startswith("eyeSquint") and s in self.eyes:  # the lower lid up
                    d = self._blink(s, Xm, Xn, 0.1, 1.4)
                if kind == "skin" and s in self.cheeks:  # the cheek under the eye up (a squint takes some)
                    c, r = self.cheeks[s]
                    m = _bump(np.linalg.norm(Xm - c, axis=1), 0.5 * r, 1.5 * r) * (1 - lips)
                    d = d + (m * (0.3 if name.startswith("eyeSquint") else 1.0))[:, None] * up * 0.06 * self.R
            elif name.startswith("noseSneer"):  # the skin beside the nose's wing up and out (the nose stays)
                d = zero
                if kind == "skin" and self.sneer:
                    c, r = self.sneer[s]
                    m = _bump(np.linalg.norm(Xm - c, axis=1), 0.4 * r, 1.6 * r) * (1 - lips)
                    d = m[:, None] * (up * 0.05 * self.R + side * sg * 0.015 * self.R)
            elif name.startswith("eyeLook"):
                d = zero  # (the eyeballs' own part turns: eye_part)
            elif name.startswith("browDown") or name.startswith("browOuterUp") or name == "browInnerUp":
                d = self._brow(name, s, Xm) if kind == "skin" else zero
            elif name == "cheekPuff":
                m = np.zeros(n)
                for c, r in self.cheeks.values():
                    m = np.maximum(m, _bump(np.linalg.norm(Xm - c, axis=1), 0.6 * r, 1.7 * r))
                d = (m * (1 - lips) * (kind == "skin"))[:, None] * nrm * 0.1 * w
            elif name == "tongueOut":
                d = 0.35 * jo
                if kind == "tongue" and self.tongue is not None:
                    tc, ts = self.tongue.params["c"], self.tongue.params["size"]
                    along = np.clip(((Xm - tc) @ out + ts[1]) / (2 * ts[1]), 0, 1)
                    reach = ((self.M - tc) @ out) - ts[1] + 0.25 * w
                    d = d + (_ss(along) * reach)[:, None] * out - (along ** 2 * 0.25 * reach)[:, None] * up
            else:
                raise SpecError(f"face_shapes: unknown shape {name!r}")
            d = d * (self.amount.get(name, 1.0) * (sneer_still if name.startswith("noseSneer") else still))[:, None]
            res[name] = d
        return res

    def _blink(self, s: str, Xm: np.ndarray, Xn: np.ndarray, ku: float = 1.0, kl: float = 1.0) -> np.ndarray:
        """The upper lid turned down over the eyeball about the eye's own left-right axis (so it slides on the
        ball), the lower lid up a quarter of the way; the corners stay, the skin round the eye follows less.
        ku / kl scale the upper / lower lid's turn (eyeWide: negative, eyeSquint: the lower lid more)."""
        ev = self.eyes[s]
        c, rot, r, ro = ev["c"], ev["rot"], ev["r"], ev["ro"]
        q = (Xm - c) @ rot
        dist = np.linalg.norm(q, axis=1)
        zp = q[:, 2] * r / np.maximum(dist, 1e-9)
        xp = q[:, 0] * r / np.maximum(dist, 1e-9)
        hu, hl, zc = ev["hu"], ev["hl"], ev["zc"]
        zt = hl + 0.25 * (hu - hl)
        th_u = np.arcsin(np.clip(hu / r, -1, 1)) - np.arcsin(np.clip(zt / r, -1, 1))
        th_l = np.arcsin(np.clip(zt / r, -1, 1)) - np.arcsin(np.clip(hl / r, -1, 1))
        upper = _ss((zp - zc) / (0.3 * r) + 0.5)
        lat = _ss(1 - (xp / (1.15 * ev["w"])) ** 2)
        # the lid turns; the skin round it follows the lid's outer surface, taking the move of the point under it on
        # that surface (turning it about the eye's centre instead swung a lever as long as its distance: it tore),
        # fading over most of an eye radius (the low poly is coarse there: a tight fade made facets)
        reach = _ss((dist - 1.01 * r) / (0.05 * r)) * _bump(dist, ro, ro + 1.1 * r) \
            * _bump(q[:, 1], 0.1 * r, 0.6 * r)
        ang = (upper * th_u * ku - (1 - upper) * th_l * kl) * lat * reach
        qn = (Xn - c) @ rot
        dn = np.linalg.norm(qn, axis=1, keepdims=True)
        on = qn * np.minimum(ro / np.maximum(dn, 1e-9), 1.0)  # on the lid's outer sphere (the lid itself: as is)
        moved = _rodrigues(np.array([1.0, 0.0, 0.0]), ang, on) - on
        return moved @ rot.T

    def _brow(self, name: str, s: str | None, Xm: np.ndarray) -> np.ndarray:
        d = np.zeros_like(Xm)
        for side, b in self.brows.items():
            if s is not None and side != s:
                continue
            hb = b["half"]
            # keep the eye itself still: the brow's pull fades over the upper lid
            if name == "browInnerUp":
                m = _bump(np.linalg.norm(Xm - b["inner"], axis=1), 0.5 * hb, 1.5 * hb)
                d += m[:, None] * self.up * 0.09 * self.R
            elif name.startswith("browOuterUp"):
                m = _bump(np.linalg.norm(Xm - b["outer"], axis=1), 0.5 * hb, 1.4 * hb)
                d += m[:, None] * self.up * 0.08 * self.R
            else:  # browDown: down, toward the middle, a little forward
                m = _bump(np.linalg.norm(Xm - b["c"], axis=1), 0.8 * hb, 1.7 * hb)
                toward = -self.side * (1 if side == "Left" else -1)
                d += m[:, None] * (-self.up * 0.06 * self.R + toward * 0.03 * self.R + self.out * 0.015 * self.R)
        for ev in self.eyes.values():
            d *= _ss((np.linalg.norm(Xm - ev["c"], axis=1) - 1.01 * ev["r"]) / (0.05 * ev["r"]))[:, None]
        return d


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


def unevenness(V: np.ndarray, T: np.ndarray, d: np.ndarray, sel: np.ndarray | None = None) -> tuple[float, int, int]:
    """How jagged a shape's move is over the mesh: per vertex, how far its move lies OUTSIDE the range of its edge
    neighbours' moves (per axis; 0 for any vertex between its neighbours, however steep the field), per metre of
    its mean edge: (worst, vertices over UNEVEN_COUNT, vertices with 4+ neighbours). A smooth field reads ~0 (a lid
    travelling 8 mm over 5 mm of skin is steep, not jagged); a vertex that goes further than everything round it
    is a spike, and several of them a sawtooth in whatever is painted there. Vertices at a tear (the lips' slit:
    neighbours moving opposite ways) are left out. V, T welded (no uv-seam duplicates:
    `weld`); sel limits the count to those vertices."""
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    e = e[e[:, 0] != e[:, 1]]
    L = np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1)
    n = len(V)
    lo, hi = np.full((n, 3), np.inf), np.full((n, 3), -np.inf)
    ls, cnt = np.zeros(n), np.zeros(n)
    # a tear is not unevenness: the two lips meet along the slit and at its corners, and part (neighbours going
    # opposite ways, both by more than a millimetre)
    mv = np.linalg.norm(d, axis=1)
    apart = ((d[e[:, 0]] * d[e[:, 1]]).sum(1) < 0) & (np.minimum(mv[e[:, 0]], mv[e[:, 1]]) > 1e-3)
    torn = np.zeros(n, bool)
    torn[e[apart].ravel()] = True
    for a, b in ((0, 1), (1, 0)):
        np.minimum.at(lo, e[:, a], d[e[:, b]])
        np.maximum.at(hi, e[:, a], d[e[:, b]])
        np.add.at(ls, e[:, a], L)
        np.add.at(cnt, e[:, a], 1)
    ok = (cnt >= 4) & ~torn
    if sel is not None:
        ok &= sel
    if not ok.any():
        return 0.0, 0, 0
    r = np.maximum(np.maximum(lo[ok] - d[ok], d[ok] - hi[ok]), 0.0)
    q = np.linalg.norm(r, axis=1) / np.maximum(ls[ok] / cnt[ok], 2e-3)  # (a mesh finer than 2 mm: per 2 mm)
    return float(q.max()), int((q > UNEVEN_COUNT).sum()), int(ok.sum())


def weld(V: np.ndarray, T: np.ndarray, tol: float = 1e-6):
    """(index of each welded vertex's first copy, triangles on welded indices, welded index of every vertex)."""
    key = np.round(np.asarray(V, float) / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    Tw = inv[T]
    return first, Tw[(Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])], inv


def turn(vecs: np.ndarray, n0: np.ndarray, n1: np.ndarray) -> np.ndarray:
    """vecs (m, 3) turned by the rotation taking unit n0 to unit n1 (per row), the least rotation."""
    axis = np.cross(n0, n1)
    s = np.linalg.norm(axis, axis=1)
    c = np.clip((n0 * n1).sum(1), -1, 1)
    ang = np.arctan2(s, c)
    k = axis / np.maximum(s, 1e-12)[:, None]
    cs, sn = np.cos(ang)[:, None], np.sin(ang)[:, None]
    out = vecs * cs + np.cross(k, vecs) * sn + k * (k * vecs).sum(1, keepdims=True) * (1 - cs)
    return np.where((s > 1e-9)[:, None], out, vecs)


def names_of(face_shapes) -> list[str]:
    """The targets an export carries: the ARKit names asked for (True: all 52), plus each corrective whose inputs
    are all there."""
    if face_shapes is True:
        names = list(ALL)
    else:
        if isinstance(face_shapes, str):
            face_shapes = [face_shapes]
        names = list(face_shapes or [])
        bad = [n for n in names if n not in ALL]
        if bad:
            raise SpecError(f"face_shapes: unknown shape(s) {bad} (have the ARKit names {', '.join(ALL)})")
    return names + [c for c, (_, *ins) in CORRECTIVES.items() if all(i in names or i + "Left" in names for i in ins)
                    and (c != "jawOpen_mouthSmile" or SMILE_JAW_CANCEL or SMILE_JAW_CANCEL_LM)]


SHAPE_SCULPT = __import__("os").environ.get("HP_SHAPE_SCULPT", "")  # (r48) hand-sculpted shape deltas (npz)


def _sculpted(D: dict, part: str, n: int, log: list) -> dict:
    """(r48) Add hand-sculpted corrective deltas to a part's shapes: SHAPE_SCULPT is an npz of "<part>|<shape>" ->
    (verts, 3) offsets in the export's frame (Blender axes, m), sculpted against the reference on the posed export mesh
    (the solve is the base, the artist finishes). Only the shapes move; the neutral is untouched. Checked by vertex count:
    a mesh that changed since the sculpt is skipped with a WARNING, never applied to the wrong vertices."""
    z = np.load(SHAPE_SCULPT)
    out = dict(D)
    for k in z.files:
        pn, nm = k.split("|", 1)
        if pn != part or nm not in out:
            continue
        d = np.asarray(z[k], np.float64)
        if d.shape != (n, 3):
            log.append(f"WARNING face shapes: sculpt {k} has {d.shape[0]} vertices, the part {n}: not applied")
            continue
        out[nm] = out[nm] + d
        log.append(f"face shapes: {part} {nm} + sculpt, max {np.linalg.norm(d, axis=1).max() * 1000:.1f} mm")
    return out


def apply(spec: dict, parts: dict, face_shapes, log: list) -> dict:
    """Close the neutral's mouth and give the moving parts their shapes, in place on the export's low-poly parts
    ({part: {"verts", "corner_vert", "normal", "tangent", ...}}, Blender axes). Each moving part gets
    p["shapes"] = {name: (delta (verts, 3), vertex normal before (verts, 3), after (verts, 3))}, in the order of
    `names`; normals and tangents per corner turn with the close. Returns {part: [names]}."""
    names = names_of(face_shapes)
    face = face_of(spec)
    if "eyeBlinkLeft" in names and not face.eyes:
        log.append("face shapes: no lids on the face kit's eyes: eyeBlink shapes are flat")
    if isinstance(face, GnmFace):
        if face.note:
            log.append("WARNING " + face.note)
        log.append("face shapes: the mouth is " + ("GNM's own (bag, teeth and gums, tongue: each moved by its own share of "
                                                    "every shape's GNM expression coefficients)" if face.gnm_mouth else
                                                    "the face kit's (base.head.interior: teeth and tongue ride the jaw rigidly)"))
    got, kinds = {}, {}
    for pn, p in parts.items():
        if p.get("lash_root") is not None:  # the lashes (lashes.py) follow the lids' shapes, below
            continue
        base = pn.split("/")[-1].split("~")[0]
        kind = "teeth" if base in face.parts_teeth else "tongue" if base in face.parts_tongue else "skin"
        if any(e.get("part") in (base, base[:-len("_cornea")] if base.endswith("_cornea") else None)
               for e in face.eyes.values()):
            kind = "eyes"  # the eyeballs' own part (and a clear cornea's lens, base.clear_cornea): only the eyeLook
            # shapes turn them
        Xm = np.asarray(p["verts"], np.float64)
        if kind == "skin":
            if not face.owns(base):  # clothes and everything else: no face shapes
                continue
            near = np.linalg.norm(Xm - face.M, axis=1) < 3 * face.width + 2 * face.R
            if not near.any():
                continue
        T = p["corner_vert"].reshape(-1, 3)
        idx = p.get("gnm_index") if kind == "skin" else None  # (one mesh, own quads: GNM's vertices by index)
        Xn = Xm + face.neutral(Xm, kind, idx)
        moved_rest = False
        if SHAPE_SCULPT and kind == "teeth":  # (r48) a sculpted rest for the teeth (levelled incisal edges)
            z = np.load(SHAPE_SCULPT)
            if f"{base}|_neutral" in z.files and z[f"{base}|_neutral"].shape == Xn.shape:
                Xn = Xn + np.asarray(z[f"{base}|_neutral"], np.float64); moved_rest = True
                log.append(f"face shapes: {pn} rest + sculpt, max {np.abs(z[f'{base}|_neutral']).max() * 1000:.1f} mm")
        if kind == "skin" and base == face.slit_part and idx is None:
            Xn = Xn + face.seal(Xm, Xn, T)
        n0m, n0 = vertex_normals(Xm, T), vertex_normals(Xn, T)
        if kind == "skin":  # the close turns the corners' normals and tangents with it
            cv = p["corner_vert"]
            p["normal"] = turn(np.asarray(p["normal"], np.float64), n0m[cv], n0[cv]).astype(p["normal"].dtype)
            p["tangent"] = turn(np.asarray(p["tangent"], np.float64), n0m[cv], n0[cv]).astype(p["tangent"].dtype)
        lower = None
        if kind == "teeth" and getattr(face, "gnm_mouth", False):  # GNM's rows are parts of their own
            from . import base as basemod
            lower = np.full(len(Xm), base == basemod.TEETH_PARTS[1])
        elif kind == "teeth":  # each connected piece whose middle is under the parting line is the lower row
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
            _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (len(Xm),) * 2),
                                          directed=False)
            h0 = face.local(Xm)["h0"]
            mid = np.bincount(lab, h0) / np.maximum(np.bincount(lab), 1)
            lower = mid[lab] < 0
        D = face.displacements(Xm, Xn, n0, kind, names, lower, idx)
        if SHAPE_SCULPT:
            D = _sculpted(D, pn, len(Xm), log)
        if moved_rest:  # (r48) its corners' normals turned with the sculpted rest
            cv = p["corner_vert"]; n1 = vertex_normals(Xn, T)
            p["normal"] = turn(np.asarray(p["normal"], np.float64), n0m[cv], n1[cv]).astype(p["normal"].dtype)
            p["verts"] = Xn.astype(p["verts"].dtype)
        if not any(np.abs(d).max() > 1e-7 for d in D.values()):
            continue
        p["verts"] = Xn.astype(p["verts"].dtype)
        p["shapes"] = {nm: (d, n0, vertex_normals(Xn + d, T)) for nm, d in D.items()}
        got[pn] = list(D)
        kinds[pn] = kind
        moved = sum(int((np.linalg.norm(d, axis=1) > 1e-6).any()) for d in D.values())
        log.append(f"face shapes: {pn} ({kind}) {len(D)} targets ({moved} move it), max "
                   f"{max(np.linalg.norm(d, axis=1).max() for d in D.values()) * 1000:.1f} mm")
        if kind == "skin" and idx is not None and isinstance(face, GnmFace):  # the closed lips' seam, as seen
            # from the front (an orthographic mask along -out): no inner lip / sock face in front at neutral or blink
            sealed = "mouthClose" if face._gnm.get("parted") is not None else ""  # (r44) parted rest: mouthClose seals
            got_ = {nm: face.seam_showing(Xn + (D[nm] if nm else 0.0), T, idx)
                    for nm in (sealed, "eyeBlinkLeft") if not nm or nm in D}
            if any(v is not None for v in got_.values()):
                bad = {nm: v for nm, v in got_.items() if v is not None and v > SEAM_SHOWING}
                log.append(("WARNING " if bad else "") + f"face shapes: {pn} closed lips' seam (inner lip / mouth "
                           f"seen from the front, mm^2, limit {SEAM_SHOWING}): " + ", ".join(
                               f"{nm or 'neutral'} {v:.3f}" for nm, v in got_.items() if v is not None))
                p["seam_showing"] = {nm or "neutral": round(float(v), 4) for nm, v in got_.items() if v is not None}
        if kind == "skin":  # a shape whose move jumps from vertex to vertex shears whatever is painted there
            first, Tw, _ = weld(Xn, T)
            un = {nm: unevenness(Xn[first], Tw, d[first], face.off_margins(nm, Xn[first])) for nm, d in D.items()}
            p["shape_unevenness"] = {nm: round(u[0], 3) for nm, u in un.items() if u[0] > UNEVEN_COUNT}
            top = sorted(un, key=lambda nm: -un[nm][0])[:3]
            log.append(f"face shapes: {pn} unevenness (a vertex's move outside its neighbours', per m of edge; "
                       f"smooth ~0, limit {UNEVEN_LIMIT}): " + ", ".join(f"{nm} {un[nm][0]:.2f}" for nm in top))
            for nm in un:  # (mouth shapes part the lips at the slit's ends: steps there are the shape, not a fault;
                # measured, the kit's read 0.2-1.6 on a handful of vertices at the corners. Listed, not warned.)
                if un[nm][0] > UNEVEN_LIMIT and family(nm.split("_")[0]) != "mouth":
                    log.append(f"WARNING face shapes: {pn} {nm} moves unevenly ({un[nm][0]:.2f}, {un[nm][1]} "
                               f"vertices over {UNEVEN_COUNT}): neighbouring vertices go different ways, which "
                               "shears painted detail into a sawtooth. Look at it posed (rig(glb=, shapes=))")
    skin = [(np.asarray(parts[q]["verts"], np.float64), {nm: np.asarray(x[0]) for nm, x in parts[q]["shapes"].items()})
            for q in got if kinds.get(q) == "skin"]
    for pn, p in parts.items():  # the lashes: each lash turned rigidly with its root's lid (lashes.shapes_from_lids)
        if p.get("lash_root") is None or not skin:
            continue
        from . import lashes as lashmod
        D = lashmod.shapes_from_lids(p, skin, names)
        if not any(np.abs(d).max() > 1e-7 for d in D.values()):
            continue
        T = p["corner_vert"].reshape(-1, 3)
        X0 = np.asarray(p["verts"], np.float64)
        n0 = vertex_normals(X0, T)
        p["shapes"] = {nm: (d, n0, vertex_normals(X0 + d, T)) for nm, d in D.items()}
        got[pn] = list(D)
        log.append(f"face shapes: {pn} (lashes, riding the lids) {len(D)} targets, max "
                   f"{max(np.linalg.norm(d, axis=1).max() for d in D.values()) * 1000:.1f} mm")
    return got


def read_glb(path) -> dict:
    """The face shapes in a GLB, decoded (sparse accessors too): {mesh name: {"names": targetNames, "count":
    vertices, "weights", "targets": [{"POSITION": (count, 3), "NORMAL": (count, 3)}] per primitive 0}}. For checks
    and tests (the export round trip), not for engines."""
    import json
    import struct
    from pathlib import Path
    raw = Path(path).read_bytes()
    jl = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20 + jl])
    bl = struct.unpack_from("<I", raw, 20 + jl)[0]
    binary = raw[28 + jl:28 + jl + bl]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    dtype = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}

    def view(bv, ctype, n, k):
        v = doc["bufferViews"][bv]
        return np.frombuffer(binary, dtype[ctype], n * k, v.get("byteOffset", 0)).reshape(n, k) if k > 1 else \
            np.frombuffer(binary, dtype[ctype], n, v.get("byteOffset", 0))

    def acc(i):
        a = doc["accessors"][i]
        k = width[a["type"]]
        out = (view(a["bufferView"], a["componentType"], a["count"], k).astype(np.float64)
               if "bufferView" in a else np.zeros((a["count"], k)))
        if "sparse" in a:
            sp = a["sparse"]
            idx = view(sp["indices"]["bufferView"], sp["indices"]["componentType"], sp["count"], 1)
            out = out.copy()
            out[idx] = view(sp["values"]["bufferView"], a["componentType"], sp["count"], k)
        return out
    res = {}
    for m in doc["meshes"]:
        pr = m["primitives"][0]
        res[m["name"]] = {"names": (m.get("extras") or {}).get("targetNames", []), "weights": m.get("weights", []),
                          "count": doc["accessors"][pr["attributes"]["POSITION"]]["count"],
                          "targets": [{k: acc(v) for k, v in t.items()} for t in pr.get("targets", [])]}
    return res


# ---- GNM heads (base.head.source "gnm") ---------------------------------------------------------------------------

# Each ARKit shape on a grafted GNM head is GNM's own expression basis, solved like base.pose_expression: the least
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
# identity held (assembly/fitexpr.py: face_ruler.read, per-picture expression over a population PCA prior of GNM's face
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

class GnmFace(Face):
    """A GNM head (base.py): its mouth from the landmarks (base.mouth_lips); its interior GNM's OWN (base.mouth_mode
    "gnm", the default: mouth bag, teeth and tongue, each moved by its own share of a shape's expression coefficients)
    or the face kit's (base.head.interior: kits._interior, moved rigidly with the jaw); its shapes from GNM's
    expression basis carried onto the export."""

    def __init__(self, spec: dict):
        from . import base as basemod
        b = spec["base"]
        hd = b["head"]
        e = specmod.expand_mirror(spec)
        head = basemod.head_of({"joints": e["joints"]}, b)
        mode = basemod.mouth_mode(b, head)
        self.gnm_mouth = mode == "gnm"
        self.note = basemod.mouth_note(b, head)
        if mode == "none":
            raise SpecError("face_shapes on a GNM head needs a mouth that can open: GNM's own (the default; "
                            + (self.note or "base.head.mouth is \"none\" here")
                            + ") or the face kit's (base.head.interior: true, or {\"teeth\": true, \"tongue\": true}), and, "
                            "unless the body is the one mesh on its own quads, base.head.mouth_gap >= 0.002 (the lips "
                            "parted while modelling; the export closes them)")
        one = (b.get("body") or {}).get("source") == "human"  # (one mesh: GNM's own lips, never zipped unasked)
        self.own_quads = one and ((spec.get("parts") or {}).get("body") or {}).get("topology") == "wrap"
        if (float(hd.get("mouth_gap") or 0) < 0.0015) and not (one and hd.get("mouth_gap") is None):
            raise SpecError("face_shapes on a GNM head: base.head.mouth_gap must part the lips (>= 0.002 m): closed "
                            "lips are zipped into one seam and can't open")
        opts = spec.get("face_shapes") or {}
        self.amount = {str(a): float(v) for a, v in (opts.get("amount") or {}).items()}
        self.skin_parts = {str(p) for p in (opts.get("parts") or [])}
        bad = [a for a in self.amount if a not in ALL]
        if bad:
            raise SpecError(f"face_shapes.amount: unknown shape(s) {bad} (have the ARKit names {', '.join(ALL)})")
        prims = {p.name: p for p in specmod.compile_prims(spec)}
        self.head = head
        m = basemod.mouth_lips(head)
        lm = head["lm68"]
        self.M, self.out, self.up, self.side = m["M"], m["out"], m["up"], m["side"]
        self.width = m["width"]
        self.W2 = self.width / 2
        self.ru, self.rl = m["ru"], m["rl"]
        self.lip = max(self.ru, self.rl)
        pts = m["pts"] - self.M
        self.su, self.sz, self.sf = m["knots"], pts @ self.up, pts @ self.out
        self.corners = {"Left": lm[54], "Right": lm[48]}
        self.R = 0.5 * float(np.linalg.norm(lm[16] - lm[0]))
        if self.gnm_mouth:
            self._gnm_mouth_parts(m, b)
        else:
            self._mouth_parts(prims, "face")
        self.nose = []
        self.nose_bone = []
        self.eyes = {s: {"c": np.asarray(c, float), "r": float(head["eye_r"]), "ro": 1.3 * float(head["eye_r"]),
                         "part": b.get("eyes")} for s, c in zip(("Left", "Right"), head["eyes"])}
        eg = head.get("eye_gnm")
        if eg and b.get("cornea") is not False:  # GNM's own eyeball: its corneal sphere stands proud of the ball, and
            # a lid must clear it too (displacements): centre on the gaze line, as base.inject places the bulge
            for s, sfx in (("Left", ".L"), ("Right", ".R")):
                if f"eye_front{sfx}" in e["joints"]:
                    c = self.eyes[s]["c"]
                    gz = _unit(np.asarray(e["joints"][f"eye_front{sfx}"]["pos"], float) - c)
                    self.eyes[s]["cornea"] = (c + (float(eg["apex"]) - float(eg["cornea_r"])) * gz, float(eg["cornea_r"]))
        self.brows, self.cheeks = {}, {}
        jaw = opts.get("jaw") or {}
        self.P = (np.asarray(specmod.resolve_point(e, jaw["pivot"]), float) if "pivot" in jaw
                  else 0.5 * (lm[0] + lm[16]))
        self.open = np.radians(float(jaw.get("open", GNM_OPEN)))
        self.depth = float(jaw.get("depth", 0.75 * self.R))
        self.lid_seal = lid_seal_options(opts.get("lid_seal"))
        self._gnm = {}

    def _gnm_mouth_parts(self, m: dict, b: dict):
        """GNM's own mouth (base.gnm_mouth): the numbers the kit's slit and bag gave (the lips' depth, the bag's
        half sizes in the mouth's frame, how fine the teeth are meshed), and the pieces' own vertices."""
        from . import base as basemod
        mp = basemod.gnm_mouth(self.head)
        self.slit = max(float(m["gap"]), 0.001)
        self.slit_part = b.get("part", "body")
        self.slit_u = np.array([0.0, 0.92])
        self.slit_h = np.array([0.5 * self.slit, 0.25 * 0.5 * self.slit])
        self.thick = 2.2 * self.lip
        g = basemod._gnm_data()
        own = np.asarray(g["groups"]["mouth_sock"])[mp["sock"]["ids"]] > 0.5
        P = (mp["sock"]["verts"][own] - self.M) @ np.stack([self.side, self.out, self.up], 1)
        self.bag = 0.5 * (P.max(0) - P.min(0))
        self.parts_teeth, self.parts_tongue = set(basemod.TEETH_PARTS), {"tongue"}
        self.teeth_t = 3 * float(basemod.MOUTH_PARTS["teeth"]["voxel"])
        self.tongue = None

    # ---- GNM's frame, the solve, the carry ---------------------------------------------------------------------

    def _setup(self):
        if self._gnm:
            return self._gnm
        from scipy.spatial import cKDTree

        from . import base as basemod
        g = basemod._gnm_data()
        c = self.head["carry"]
        V = c["V"]
        Wlm = np.zeros((68, len(V)))
        for i, r in enumerate(g["lm68"]):
            for v, w in zip(r[0::2], r[1::2]):
                Wlm[i, int(v)] += float(w)
        names = [str(n) for n in g["expression_names"]]
        regions = {k: [i for i, n in enumerate(names) if n.startswith(k)] for k in ("lower_face", "left_eye", "right_eye")}
        X0 = Wlm @ V
        wg = float(X0[54, 0] - X0[48, 0])
        self._gnm = {"g": g, "c": c, "Wlm": Wlm, "regions": regions, "X0": X0, "wg": wg,
                     "tree": cKDTree(self.head["verts"])}
        return self._gnm

    def _solve(self, moves: dict, region: str, hold: float = HOLD, prior: float = SOLVE_RIDGE) -> np.ndarray:
        """GNM vertex offsets (its frame) that move landmarks by `moves` ({id: [x, y, z] in mouth widths}) holding
        the rest: ridge least squares over the region's expression components (linear in them, as pose_expression)."""
        G = self._setup()
        comps = G["regions"]["lower_face"] if region == "mouth" else G["regions"]["left_eye"] + G["regions"]["right_eye"]
        B = G["g"]["expression_basis"][comps]
        A = np.einsum("ln,cnd->ldc", G["Wlm"], B).reshape(68 * 3, len(comps))
        t = np.zeros((68, 3))
        w = np.full((68, 3), hold)
        for i, d in moves.items():
            t[i] += np.asarray(d, float) * G["wg"]
            w[i] = 1.0
        w, t = w.ravel(), t.ravel()
        Aw = A * w[:, None]
        cf = np.linalg.solve(Aw.T @ Aw + prior * np.eye(len(comps)), Aw.T @ (t * w))
        self._last = dict(zip(comps, cf))  # (shape_coeffs: a shape IS these expression coefficients)
        return np.tensordot(cf, B, 1)

    TONGUE_OUT = 0.006  # m (world): how far past the lips' front the tongue's tip comes at tongueOut 1
    TONGUE_COMPS = 6    # GNM's leading tongue components used (000 = out, 001 / 002 = up, 003 = sideways ...)

    def _tongue_out(self) -> tuple:
        """GNM's own tongue pushed out: the least change of its leading tongue components (GNM frame offsets of
        every vertex, and the coefficients) that brings the tongue's front TONGUE_OUT past the lips, a little down."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        names = [str(n) for n in g["expression_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("tongue_") and n != "tongue_mean"][:self.TONGUE_COMPS]
        tg = np.flatnonzero(np.asarray(g["groups"]["tongue"]) > 0.5)
        front = tg[V[tg, 2] > np.percentile(V[tg, 2], 92)]
        A = np.stack([g["expression_basis"][i][front].mean(0) for i in comps], 1).astype(float)  # (3, n)
        X0 = G["X0"]
        reach = float(max(X0[51][2], X0[57][2]) - V[front, 2].mean()) + self.TONGUE_OUT / float(G["c"]["s"])
        t = np.array([0.0, -0.2 * reach, reach])
        cf = A.T @ np.linalg.solve(A @ A.T + 1e-9 * np.eye(3), t)  # (min norm)
        return np.tensordot(cf, g["expression_basis"][comps], 1), dict(zip(comps, cf))

    def _tongue_shape(self, down: float, back: float, bow: float) -> np.ndarray:
        """GNM's own tongue reshaped (GNM-frame offsets of every vertex): the least change of its leading tongue
        components that moves the tip (front 10%) down / back and bows the dorsum's mid-line up over its sides."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        names = [str(n) for n in g["expression_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("tongue_") and n != "tongue_mean"][:self.TONGUE_COMPS]
        tg = np.flatnonzero(np.asarray(g["groups"]["tongue"]) > 0.5)
        T = V[tg]; z0, z1 = T[:, 2].min(), T[:, 2].max(); L = z1 - z0; w = np.ptp(T[:, 0]); xm = np.median(T[:, 0])
        tip = T[:, 2] > z1 - 0.1 * L; top = (T[:, 1] > np.percentile(T[:, 1], 60)) & ~tip & (T[:, 2] > z0 + 0.3 * L)
        mid = top & (np.abs(T[:, 0] - xm) < 0.12 * w); side = top & (np.abs(T[:, 0] - xm) > 0.28 * w)
        B = np.asarray(g["expression_basis"])[comps][:, tg]  # (n, k, 3)
        A = np.stack([B[:, tip, 1].mean(1), B[:, tip, 2].mean(1), B[:, mid, 1].mean(1) - B[:, side, 1].mean(1)], 0)
        t = np.array([-down, -back, bow]) / float(G["c"]["s"])
        cf = A.T @ np.linalg.solve(A @ A.T + 1e-9 * np.eye(3), t)
        return np.tensordot(cf, np.asarray(g["expression_basis"])[comps], 1)

    def shape_coeffs(self, name: str) -> dict:
        """A shape as GNM EXPRESSION COEFFICIENTS {component name: value}: what base.head.expression takes to pose the
        model in that shape (every component then follows: skin, lower teeth, tongue). Shapes the basis has no
        landmarks for (cheekPuff, cheekSquint) and the eyeLook turns have none: {}."""
        g = self._setup()["g"]
        names = [str(n) for n in g["expression_names"]]
        if family(name) == "look":
            return {}
        mv, region = self._gnm_moves(name)
        if region is None:
            return {}
        self._solve(mv, region, prior=JAW_PRIOR if name in JAW_PRIORED else SOLVE_RIDGE)
        out = {names[i]: float(v) for i, v in self._last.items()}
        if name == "tongueOut" and self.gnm_mouth:
            out.update({names[i]: float(v) for i, v in self._tongue_out()[1].items()})
        return {k: round(v * self.amount.get(name, 1.0), 5) for k, v in out.items() if abs(v) > 1e-6}

    def _piece_onto(self, X: np.ndarray, dV: np.ndarray, kind: str, lower=None) -> np.ndarray:
        """World offsets of a GNM mouth part's export vertices X (kind "teeth" | "tongue" | "sock") from GNM's own
        offsets dV: inverse distance over the 4 nearest vertices of the GNM piece the vertex belongs to (teeth:
        `lower` (per vertex, True = the lower row) when the part says which row it is, else the nearest piece: a
        tooth row never takes the other row's move)."""
        from scipy.spatial import cKDTree

        from . import base as basemod
        G = self._setup()
        mp = basemod.gnm_mouth(self.head)
        dW = self._by_index(dV)  # (a piece takes an expression's offsets as the skin does: base._gnm_pieces)
        names = {"teeth": ("teeth_upper", "teeth_lower"), "tongue": ("tongue",), "sock": ("sock",)}[kind]
        trees = G.setdefault("piece_trees", {})
        for n in names:
            if n not in trees:
                trees[n] = cKDTree(mp[n]["verts"])
        if kind == "teeth" and lower is not None:
            best = np.asarray(lower, bool).astype(int)
        elif len(names) > 1:
            best = np.argmin(np.stack([trees[n].query(X)[0] for n in names]), 0)
        else:
            best = np.zeros(len(X), int)
        out = np.zeros_like(X)
        for j, n in enumerate(names):
            m = best == j
            if m.any():
                d, i = trees[n].query(X[m], k=4)
                out[m] = (dW[mp[n]["ids"][i]] * self._idw(d)[..., None]).sum(1)
        return out

    # ---- GNM's frame, the solve, the carry ---------------------------------------------------------------------

    def _jaw_moves(self, ang: float = None, shift=None) -> dict:
        """The jaw's landmarks (jaw line, lower lip; the corners half) turned about the ear line or shifted."""
        G = self._setup()
        X0 = G["X0"]
        Pg = 0.5 * (X0[0] + X0[16])
        out = {}
        for ids, k in ((JAW + LOWER_LIP, 1.0), ([2, 14, 48, 54, 60, 64], 0.5)):
            for i in ids:
                if ang is not None:
                    q = X0[i] - Pg
                    moved = _rodrigues(np.array([1.0, 0.0, 0.0]), np.array([k * ang]), q[None])[0]
                    out[i] = (moved - q) / G["wg"]
                else:
                    out[i] = k * np.asarray(shift, float)
        return out

    def _gnm_moves(self, name: str):
        """(landmark moves, region) for a shape, or (vertex offsets, None) for those the basis has no landmarks for."""
        s = "Left" if name.endswith("Left") else "Right" if name.endswith("Right") else None
        sx = 1.0 if s in (None, "Left") else -1.0
        side = (lambda ids: _mirror_ids(ids, s)) if s else (lambda ids: ids)

        def hold(mv, ids):  # these landmarks stay (moved by 0, at full weight)
            for i in ids:
                mv.setdefault(i, np.zeros(3))

        def put(mv, ids, d, k=1.0):
            for i in side(ids):
                mv[i] = np.asarray(mv.get(i, np.zeros(3)), float) + k * np.asarray([d[0] * sx, d[1], d[2]], float)
        mv = {}
        if name == "jawOpen" and JAW_FIT:
            return self._jaw_fit(), None
        if name == "jawOpen":  # the upper lip held (left at HOLD the solve dragged it 5 mm down with the jaw, over the
            # upper teeth: expr_r4 "upper teeth hidden"), its inner edge a little up off the incisors
            mv = self._jaw_moves(self.open)
            X0 = self._setup()["X0"]
            mid = 0.5 * (X0[48, 0] + X0[54, 0])
            mv.update(self._jaw_upper_lift())
            for i in (48, 54, 60, 64):
                mv[i] = mv[i] + np.array([np.sign(X0[i, 0] - mid) * JAW_CORNER_OUT, 0.0, 0.0])
            for i in (55, 56, 57, 58, 59):
                mv[i] = mv[i] + np.array([0.0, 0.0, -JAW_LOWER_BACK])
            # the basis can't lift the upper lip off the incisors while the jaw drops (landmarks reach -0.5 mm of
            # +6): v16's upper lip edge sat 1.3 mm BELOW the incisal edge, "no upper teeth" (expr_r6). Lifted
            # directly: the vermilion (GNM's upper_lip group) JAW_LIP_LIFT up, feathered into the skin above.
            return self._solve(mv, "mouth", prior=JAW_PRIOR) + self._jaw_lip_lift(), None
        if name == "jawForward":
            return self._jaw_moves(shift=[0, 0, 0.12]), "mouth"
        if name in ("jawLeft", "jawRight"):
            return self._jaw_moves(shift=[0.12 * sx, 0, 0]), "mouth"
        if name == "mouthClose":  # alone: the closed lips firmed forward a little, never into each other (the
            # closing against an open jaw is jawOpen_mouthClose's)
            put(mv, UPPER_LIP + LOWER_LIP, [0, 0, CLOSE_SEAL * 0.05])
            hold(mv, CHIN)
            return mv, "mouth"
        if name == "jawOpen_mouthClose":  # against a full jawOpen: the lower lip back up most of the way, the upper
            # down the rest. Against jawOpen as SOLVED (its prior leaves the lips short of the rigid turn): against
            # the turn itself, the lips closed past each other (A2F's warm f31: 4.2 mm)
            G = self._setup()
            dVj = self._solve(self._jaw_moves(self.open), "mouth", prior=JAW_PRIOR)
            Lj = np.einsum("ln,nd->ld", G["Wlm"], dVj) / G["wg"]
            # the GAP it opened (its lower lip's move less its upper lip's: the solve moves the upper lip a little too)
            pair = dict(zip([59, 58, 57, 56, 55, 67, 66, 65], UPPER_LIP))
            gap = {i: Lj[i] - (Lj[pair[i]] if i in pair else 0.0) for i in range(68)}
            for i in LOWER_LIP:
                mv[i] = -CLOSE_LOWER * gap[i]
            for lo_, up_ in pair.items():
                mv[up_] = (1 - CLOSE_LOWER) * gap[lo_]
            for i in JAW:
                mv[i] = np.zeros(3)
            return self._solve(mv, "mouth") - self._jaw_lip_lift(), None  # (jawOpen's direct lip lift taken back)
        if name == "jawOpen_mouthSmile":  # (r31) jawOpen's direct lip lift taken back under a smile (CORRECTIVES);
            # (r32) and its landmark lift (JAW_UPPER_LIFT) too, x SMILE_JAW_CANCEL_LM: the same solve as jawOpen's with
            # only the upper lip's lifts as targets (the solve is linear: this is exactly their share of jawOpen)
            d = -SMILE_JAW_CANCEL * self._jaw_lip_lift()
            if SMILE_JAW_CANCEL_LM:
                lift = self._jaw_upper_lift()
                mv = {i: np.zeros(3) for i in self._jaw_moves(self.open)}
                mv.update({i: -SMILE_JAW_CANCEL_LM * v for i, v in lift.items()})
                for i in (48, 54, 60, 64, 55, 56, 57, 58, 59):
                    mv.setdefault(i, np.zeros(3))
                d = d + self._solve(mv, "mouth", prior=JAW_PRIOR)
            return d, None
        if name == "mouthFunnel":
            put(mv, [48, 54], [0, 0, 0]), put(mv, [54], [-0.08, 0, 0.06]), put(mv, [48], [0.08, 0, 0.06])
            put(mv, UPPER_LIP[:5], [0, 0.07, 0.1]), put(mv, LOWER_LIP[:5], [0, -0.07, 0.1])
            put(mv, [61, 62, 63], [0, 0.07, 0.06]), put(mv, [65, 66, 67], [0, -0.07, 0.06])
            return mv, "mouth"
        if name == "mouthPucker":  # (the chin held: pucker + rollLower + shrugLower, A2F's usual mix, bulged it 10 mm)
            put(mv, [54], [-0.14, 0, 0.07]), put(mv, [48], [0.14, 0, 0.07])
            put(mv, [53, 55], [-0.07, 0, 0.1]), put(mv, [49, 59], [0.07, 0, 0.1])
            put(mv, [50, 51, 52, 56, 57, 58, 61, 62, 63, 65, 66, 67], [0, 0, 0.1])
            hold(mv, CHIN)
            return mv, "mouth"
        if name in ("mouthLeft", "mouthRight"):
            for i in range(48, 68):
                mv[i] = np.array([0.12 * sx, 0, 0])
            return mv, "mouth"
        if name.startswith("mouthSmile"):
            # GNM's own smile: its expression model's "happy" prototype (lower-face components) on this side, the
            # inner lips closed again (parting is mouthUpperUp / LowerDown's). The landmark solve (corners out / up)
            # read "pinched corners, cheek pouches, no nasolabial fold, eyes unchanged" (expr_r4 / r5); the prototype
            # pulls the corners up AND back into a crescent, the cheeks bunch and the folds form.
            if SMILE_FIT:
                return self._smile_fit(s, "lower"), None
            return self._smile_proto(s, "lower"), None
        if name.startswith("mouthFrown"):
            put(mv, [54], [0.0, -0.09, 0.0]), put(mv, [55, 64], [0, -0.04, 0])
            return mv, "mouth"
        if name.startswith("mouthDimple"):
            put(mv, [54], [0.05, 0.0, -0.06]), put(mv, [64], [0.03, 0, -0.03])
            return mv, "mouth"
        if name.startswith("mouthStretch"):
            put(mv, [54], [0.1, -0.04, -0.02]), put(mv, [55, 56, 65], [0.03, -0.04, 0])
            return mv, "mouth"
        if name == "mouthRollLower":
            # mostly back (tucked under the upper lip), little up: with less back travel, A2F's stacks (pucker +
            # rollLower + the sealed jaw + shrug) pushed the lower lip up INTO the upper one
            put(mv, [56, 57, 58], [0, 0.02, -0.1]), put(mv, [65, 66, 67], [0, 0.01, -0.09])
            hold(mv, CHIN)
            return mv, "mouth"
        if name == "mouthRollUpper":
            put(mv, [50, 51, 52], [0, -0.04, -0.08]), put(mv, [61, 62, 63], [0, -0.02, -0.07])
            return mv, "mouth"
        if name == "mouthShrugLower":  # the lower lip and chin pushed up (mentalis), not out
            put(mv, LOWER_LIP, [0, 0.03, 0.015]), put(mv, [7, 8, 9], [0, 0.02, 0])
            hold(mv, [5, 6, 10, 11])
            return mv, "mouth"
        if name == "mouthShrugUpper":
            put(mv, UPPER_LIP, [0, 0.05, 0.03])
            return mv, "mouth"
        if name.startswith("mouthPress"):
            put(mv, LEFT["upper"] + [51, 62], [0, -0.02, -0.02], 1.0), put(mv, LEFT["lower"] + [57, 66], [0, 0.02, -0.02])
            put(mv, [54], [0.03, 0, -0.01])
            return mv, "mouth"
        # (not forward off the teeth: forward, the parted lips showed their pink inner rolls where the reference shows
        # teeth, expr_r7; back, the teeth cut through the seam, expr_r8. The centre as far as the side: at 0.045 the
        # smile's closed inner lips held, "no teeth" in a smile with upperUp 0.5, expr_r8)
        if name.startswith("mouthLowerDown"):
            put(mv, [55, 56, 65], [0, -0.11, 0.0]), put(mv, [57, 66], [0, -0.09, 0.0])
            return mv, "mouth"
        if name.startswith("mouthUpperUp"):
            put(mv, [52, 53, 63], [0, 0.11, 0.0]), put(mv, [51, 62], [0, 0.09, 0.0])
            return mv, "mouth"
        if name.startswith("eyeBlink"):
            X0 = self._setup()["X0"]
            for up_i, lo_i in LEFT["lid_upper"]:
                u, lo = side([up_i])[0], side([lo_i])[0]
                gap = (X0[lo] - X0[u]) / self._setup()["wg"]
                # down (and a little forward: over the ball), meeting the lower lid a little past it (at 0.8/0.2
                # the inner corner stayed open a crack); the eyeball push keeps the lids out of the ball
                mv[u] = 0.9 * gap * np.array([0, 1.0, 0.3])
                mv[lo] = -0.25 * gap * np.array([0, 1.0, 0.3])
            return mv, "eyes"
        if name.startswith("eyeWide") or name.startswith("eyeSquint"):
            X0 = self._setup()["X0"]
            ku, kl = (-0.35, -0.15) if name.startswith("eyeWide") else (0.1, SQUINT_LOWER)
            for up_i, lo_i in LEFT["lid_upper"]:
                u, lo = side([up_i])[0], side([lo_i])[0]
                gap = (X0[lo] - X0[u]) / self._setup()["wg"]
                mv[u] = ku * gap * np.array([0, 1.0, 0.0])
                mv[lo] = -kl * gap * np.array([0, 1.0, 0.0])
            return mv, "eyes"
        if name.startswith("cheekSquint"):  # the cheek up, plus the smile prototype's own eye share on this side
            if SMILE_FIT:
                return self._smile_fit(s, "eyes"), None
            return self._cheek_raise(s) + self._smile_proto(s, "eyes"), None
        if name.startswith("noseSneer"):  # the nostril's wing and the skin beside it up
            put(mv, [35], [0.0, 0.07, 0.0]), put(mv, [34], [0.0, 0.04, 0.0])
            put(mv, [33], [0, 0.015, 0])
            return mv, "mouth"
        if name == "browInnerUp":
            for ss in ("Left", "Right"):
                for i in _mirror_ids([22, 23], ss):
                    mv[i] = np.array([0, 0.1, 0])
                for i in _mirror_ids([24], ss):
                    mv[i] = np.array([0, 0.04, 0])
            return mv, "eyes"
        if name.startswith("browDown"):
            put(mv, [22, 23, 24, 25, 26], [-0.02, -0.08, 0.01])
            return mv, "eyes"
        if name.startswith("browOuterUp"):
            put(mv, [25, 26], [0, 0.1, 0]), put(mv, [24], [0, 0.05, 0])
            return mv, "eyes"
        if name == "cheekPuff":
            return self._cheek_puff(), None
        if name == "tongueOut":
            jo = self._jaw_moves(0.35 * self.open)
            return jo, "mouth"
        raise SpecError(f"face_shapes: unknown shape {name!r}")

    def _smile_fit(self, s: str, part: str) -> np.ndarray:
        """GNM offsets (its frame, every vertex) of the FITTED smile (SMILE_FIT) on side s: "lower" = its lower-face
        components faded across the midline (SMILE_SIDE_MM), teeth cleared; "eyes" = its components of that side's eye."""
        G = self._setup()
        key = ("smile_fit", s, part, SMILE_FIT, SMILE_FIT_SOFT, SMILE_FIT_EYE_GAIN, SMILE_LOWLID_GAIN)
        if key in G:
            return G[key]
        EB = G["g"]["expression_basis"]
        e = np.asarray(np.load(SMILE_FIT), float)
        reg = G["regions"]
        if part == "eyes":
            ids = [i for i in reg["left_eye" if s == "Left" else "right_eye"] if i < len(e)]
            dE = SMILE_FIT_EYE_GAIN * self._soft_edge(np.tensordot(e[ids], EB[ids], 1), SMILE_FIT_SOFT)
            if SMILE_LOWLID_GAIN != 1.0:  # (r43) the lower lid's travel x gain (the fit lifts ~60% of the photo's)
                w = self._lower_lid_weight(dE)
                dE = dE * (1.0 + (SMILE_LOWLID_GAIN - 1.0) * w)[:, None]
            G[key] = dE
            return G[key]
        ids = [i for i in reg["lower_face"] if i < len(e)]
        dS = self._clear_teeth(self._soft_edge(np.tensordot(e[ids], EB[ids], 1), SMILE_FIT_SOFT))
        X0 = G["X0"]
        mid = float(np.mean(X0[[27, 28, 29, 30, 33, 51, 57, 62, 66], 0]))
        x = np.asarray(G["c"]["V"], float)[:, 0] - mid
        w = 0.5 * (1 + np.tanh(x / (SMILE_SIDE_MM * 0.001 / float(G["c"].get("s", 1.0)))))
        G[key] = dS * (w if s == "Left" else 1 - w)[:, None]
        return G[key]

    def _lower_lid_weight(self, dE: np.ndarray) -> np.ndarray:
        """(r43) 0..1 per GNM vertex: the lower lid of the eye that dE moves, from 1 mm above its margin (lm68's corners and
        two lower points, piecewise linear) to 3 mm below at 1, fading to 0 at 2 mm above / 7 mm below (as shares of a 30 mm
        chord), and along the chord as sin(pi t): the centre gains most, the corners not at all (less cupped)."""
        G = self._setup()
        V = np.asarray(G["c"]["V"], float)[:len(dE)]
        X = G["Wlm"][:, :len(V)] @ V if G["Wlm"].shape[1] != len(V) else G["Wlm"] @ V
        mag = np.linalg.norm(dE, axis=1)
        cen = (V * mag[:, None]).sum(0) / max(mag.sum(), 1e-12)
        eyes = ([36, 41, 40, 39], [45, 46, 47, 42])  # corner, lower, lower, corner (iBUG)
        lo = min(eyes, key=lambda q: abs(X[q, 0].mean() - cen[0]))
        P = X[lo]
        if P[0, 0] > P[-1, 0]:
            P = P[::-1]
        ch = float(np.linalg.norm(P[-1, [0, 1]] - P[0, [0, 1]]))
        t = (V[:, 0] - P[0, 0]) / max(P[-1, 0] - P[0, 0], 1e-12)
        my = np.interp(V[:, 0], P[:, 0], P[:, 1])
        below = (my - V[:, 1]) / ch * 30.0  # mm (on a 30 mm chord) under the margin; < 0 above it
        def ss(a, b, x):
            return _ss(np.clip((x - a) / (b - a), 0.0, 1.0))
        wb = ss(-2.0, -1.0, below) * (1.0 - ss(3.0, 7.0, below))
        wu = np.where((t > 0) & (t < 1), np.sin(np.pi * np.clip(t, 0, 1)), 0.0)
        near = np.abs(V[:, 2] - P[:, 2].mean()) < 0.5 * ch  # (GNM frame: z forward) the lid, not the skull behind
        return wb * wu * near * (mag > 0)

    def _jaw_fit(self) -> np.ndarray:
        """GNM offsets (its frame, every vertex) of the FITTED jaw opening (JAW_FIT): its lower-face components, teeth cleared."""
        G = self._setup()
        key = ("jaw_fit", JAW_FIT, JAW_FIT_GAIN, JAW_ROLL_TUCK, JAW_TUCK_FADE, JAW_WIDEN)
        if key not in G:
            e = JAW_FIT_GAIN * np.asarray(np.load(JAW_FIT), float)
            ids = [i for i in G["regions"]["lower_face"] if i < len(e)]
            d = np.tensordot(e[ids], G["g"]["expression_basis"][ids], 1)
            if JAW_ROLL_TUCK:
                gr = {k: np.asarray(v) > 0.5 for k, v in G["g"]["groups"].items()}
                V = np.asarray(G["c"]["V"], float)
                n = min(len(V), len(d), len(gr["skin_exterior"]))
                # the rolls: GNM's skin rings from the sock to the contact ring (skin_features.inner_lip_values = 1, the
                # same rings the export paints as wet lip), the sock itself left where the fit put it
                from . import skin_features as sfe
                iv = sfe.inner_lip_values(self.head)
                roll = np.zeros(len(d), bool)
                if iv is not None:
                    m_ = min(len(iv), n)
                    roll[:m_] = (np.asarray(iv, float)[:m_] > 0.99) & ~gr["mouth_sock"][:m_]
                print(f"faceshapes: jawOpen tucks {int(roll.sum())} inner-roll vertices back (JAW_ROLL_TUCK {JAW_ROLL_TUCK})", flush=True)
                ext = np.zeros(len(d), bool)
                ext[:n] = ((gr["upper_lip"] | gr["lower_lip"]) & gr["skin_exterior"])[:n]
                f = V[ext[:len(V)]].mean(0) - V[np.flatnonzero(gr["mouth_sock"][:n])].mean(0)
                f[1] = 0.0  # (GNM frame: y up) the lips' outward direction, level
                f /= np.linalg.norm(f)
                s = np.clip(np.abs(d[roll, 1]) / (0.2 * G["wg"]), 0.0, 1.0)
                a = np.zeros(len(d))
                a[roll] = s if not JAW_TUCK_FADE else 1.0  # (r43) per-vertex travel left one roll vertex (GNM 10766, travel
                # under the 20%-width cap while its neighbours sat at it) 1.4 mm less tucked than the ring round it
                if JAW_TUCK_FADE:  # (r43) the tuck smoothed in space (Gaussian, JAW_TUCK_FADE x 0.5 mm): on the rolls alone
                    # one lower-lip vertex (GNM 10766, outside GNM's quads graph, so a quad feather can't reach it) went
                    # 1.75 mm past its neighbours (jawOpen uneven 0.53 > UNEVEN_LIMIT, test_onemesh); the rolls' mean kept
                    from scipy.spatial import cKDTree
                    sig = JAW_TUCK_FADE * 0.0005 / float(G["c"].get("s", 1.0))
                    P = np.zeros((len(d), 3))
                    P[:n] = V[:n]
                    near = np.flatnonzero(cKDTree(P[roll]).query(P, distance_upper_bound=4 * sig)[0] < np.inf)
                    tr = cKDTree(P[near])
                    K = []
                    for i, nb in zip(near, tr.query_ball_point(P[near], 3 * sig)):
                        nb = near[nb]
                        w_ = np.exp(-((P[nb] - P[i]) ** 2).sum(1) / (2 * sig * sig))
                        K.append((i, nb, w_ / w_.sum()))

                    def smooth(a):
                        af = np.zeros(len(d))
                        for i, nb, w_ in K:
                            af[i] = (w_ * a[nb]).sum()
                        return af
                    af = smooth(a)
                    a = af * (a[roll].mean() / max(af[roll].mean(), 1e-12))
                    amt = JAW_ROLL_TUCK * G["wg"]
                    for _ in range(8):  # where the teeth stop the tuck (_clear_teeth pushes those vertices back out, one
                        # by one: GNM 10766 sat 1.8 mm proud of its ring), the tuck gives way, smoothly
                        dt = d - (amt * a)[:, None] * f[None]
                        push = np.clip(((self._clear_teeth(dt) - dt) @ f), 0.0, None)
                        a = smooth(np.clip(a - push / amt, 0.0, None))
                d -= (JAW_ROLL_TUCK * G["wg"] * a)[:, None] * f[None]
            if JAW_WIDEN:  # (r43) the opening wider: the lips, their rings and the sock stretched out from the mouth's middle
                # (in the shape, so x its weight; review r42: "about 10% narrower and shorter")
                gr = {k: np.asarray(v) > 0.5 for k, v in G["g"]["groups"].items()}
                V = np.asarray(G["c"]["V"], float)
                n = min(len(V), len(d))
                lw = np.zeros(len(d))
                lw[:n] = (gr["upper_lip"] | gr["lower_lip"] | gr["mouth_sock"])[:n]
                lw = np.clip(self._feather(lw, 6) * 1.5, 0.0, 1.0)
                X0 = G["X0"]
                mid = float(np.mean(X0[[51, 57, 62, 66], 0]))
                d[:n, 0] += JAW_WIDEN * (V[:n, 0] - mid) * lw[:n]
            G[key] = self._clear_teeth(d)
        return G[key]

    def _smile_proto(self, s: str, part: str) -> np.ndarray:
        """GNM offsets (its frame, every vertex) of SMILE_PROTO on side s ("Left" = +x): part "lower" = the prototype's
        lower-face components, faded across the midline (SMILE_SIDE_MM), plus a solve that closes the inner lips it
        parts; "eyes" = its components of that side's eye region."""
        G = self._setup()
        key = ("smile_proto", s, part, SMILE_UPPER_LIFT, SMILE_CORNER_UP, SMILE_UPPER_HOLD, SMILE_LOWER_HOLD)
        if key in G:
            return G[key]
        from . import gnm_sampler
        g = G["g"]
        EB = g["expression_basis"]
        e = SMILE_PROTO[1] * np.asarray(gnm_sampler.expression()(np.zeros(64), gnm_sampler.ex_label(SMILE_PROTO[0]))[0], float)
        reg = G["regions"]
        if part == "eyes":
            ids = [i for i in reg["left_eye" if s == "Left" else "right_eye"] if i < len(e)]
            out = self._soft_edge(np.tensordot(e[ids], EB[ids], 1))
            G[key] = out
            return out
        ids = [i for i in reg["lower_face"] if i < len(e)]
        dS = np.tensordot(e[ids], EB[ids], 1)
        L = G["Wlm"] @ dS / G["wg"]
        mv = {}
        if SMILE_CORNER_UP != 1.0:  # the corners' rise scaled (Tess: corners 5-8% io above the reference smile)
            for c in (48, 54):
                mv[c] = np.array([0.0, -(1.0 - SMILE_CORNER_UP) * float(L[c][1]), 0.0])
        for hold, ids_ in ((SMILE_UPPER_HOLD, {50: 1.0, 51: 1.0, 52: 1.0, 49: 0.5, 53: 0.5}),
                           (SMILE_LOWER_HOLD, {56: 1.0, 57: 1.0, 58: 1.0, 55: 0.5, 59: 0.5})):
            if hold:  # (r35) the outer lip edges' vertical travel taken back (the inner edges still part over the teeth)
                for c, f in ids_.items():
                    mv[c] = np.array([0.0, -hold * f * float(L[c][1]), 0.0])
        for u, lo in ((61, 67), (62, 66), (63, 65)):  # the inner lips back together (half each)
            gap = float((L[u] - L[lo])[1])
            mv[u], mv[lo] = np.array([0.0, -0.5 * gap, 0.0]), np.array([0.0, 0.5 * gap, 0.0])
        for _ in range(3):  # (the solve reaches ~80% a round: 17 -> 3.3 mm in one; the rest let the lower tips through)
            dC = self._solve(mv, "mouth")
            L2 = G["Wlm"] @ (dS + dC) / G["wg"]
            left = 0.0
            for u, lo in ((61, 67), (62, 66), (63, 65)):
                gap = float((L2[u] - L2[lo])[1])
                left = max(left, abs(gap))
                mv[u] = mv[u] + np.array([0.0, -0.5 * gap, 0.0])
                mv[lo] = mv[lo] + np.array([0.0, 0.5 * gap, 0.0])
            if left * G["wg"] < 3e-4:
                break
        dS = dS + self._solve(mv, "mouth")
        if SMILE_UPPER_LIFT[0]:  # the upper lip's middle up off the incisors: the opening's top an arch (a crescent)
            lift = self._jaw_lip_lift(SMILE_UPPER_LIFT[0], SMILE_UPPER_LIFT[1], SMILE_UPPER_LIFT[2])
            dS = dS + lift
            if SMILE_UPPER_HOLD:  # (r35) the lift's own rise of the outer edge taken back too, the inner edge (61-63) kept
                Ll = G["Wlm"] @ lift / G["wg"]
                mv2 = {c: np.array([0.0, -SMILE_UPPER_HOLD * f * float(Ll[c][1]), 0.0])
                       for c, f in {50: 1.0, 51: 1.0, 52: 1.0, 49: 0.5, 53: 0.5}.items()}
                mv2.update({c: np.zeros(3) for c in (61, 62, 63)})
                dS = dS + self._solve(mv2, "mouth")
        dS = self._clear_teeth(self._soft_edge(dS))
        X0 = G["X0"]
        mid = float(np.mean(X0[[27, 28, 29, 30, 33, 51, 57, 62, 66], 0]))
        x = np.asarray(G["c"]["V"], float)[:, 0] - mid
        w = 0.5 * (1 + np.tanh(x / (SMILE_SIDE_MM * 0.001 / float(G["c"].get("s", 1.0)))))
        w = w if s == "Left" else 1 - w
        out = dS * w[:, None]
        G[key] = out
        return out

    def _jaw_upper_lift(self) -> dict:
        """jawOpen's landmark targets for the upper lip ({id: move}, mouth widths): its inner edge up off the incisors,
        tapered toward the corners (JAW_UPPER_LIFT, JAW_ARCH)"""
        X0 = self._setup()["X0"]
        mid, half = 0.5 * (X0[48, 0] + X0[54, 0]), 0.5 * abs(X0[54, 0] - X0[48, 0])

        def arch(i):
            return max(1.0 - JAW_ARCH * abs((X0[i, 0] - mid) / half) ** JAW_ARCH_POW, 0.0)
        mv = {i: np.array([0.0, JAW_UPPER_LIFT[1] * arch(i), 0.0]) for i in UPPER_LIP[:5]}
        mv.update({i: np.array([0.0, JAW_UPPER_LIFT[0] * arch(i), 0.0]) for i in UPPER_LIP[5:]})
        return mv

    def _jaw_lip_lift(self, amount: float | None = None, arch: float | None = None, power: float | None = None) -> np.ndarray:
        """jawOpen's direct lift of the upper lip (GNM offsets): the vermilion (GNM's upper_lip group) JAW_LIP_LIFT up,
        feathered into the skin above (0.4 of upper_lip_region). amount / arch / power override JAW_LIP_LIFT /
        JAW_ARCH / JAW_ARCH_POW (the smile's SMILE_UPPER_LIFT uses it with its own arch)."""
        G = self._setup()
        JAW_LIP_LIFT = globals()["JAW_LIP_LIFT"] if amount is None else amount
        JAW_ARCH = globals()["JAW_ARCH"] if arch is None else arch
        JAW_ARCH_POW = globals()["JAW_ARCH_POW"] if power is None else power
        key = ("jaw_lip_lift", JAW_LIP_LIFT, JAW_ARCH, JAW_ARCH_POW)
        if key not in G:
            gr = G["g"]["groups"]
            w = self._feather(np.clip(np.asarray(gr["upper_lip"], float) + 0.4 * np.asarray(gr["upper_lip_region"], float), 0, 1), 3)
            w = w / max(float(w.max()), 1e-9)
            if JAW_ARCH:  # tapered toward the corners (the opening's top an arch, not a flat bar)
                V0, X0 = np.asarray(G["c"]["V"], float), G["X0"]
                mid, half = 0.5 * (X0[48, 0] + X0[54, 0]), 0.5 * abs(X0[54, 0] - X0[48, 0])
                w = w * np.clip(1.0 - JAW_ARCH * np.abs((V0[:, 0] - mid) / half) ** JAW_ARCH_POW, 0.0, 1.0)
            lift = np.zeros_like(np.asarray(G["c"]["V"], float))
            lift[:, 1] = JAW_LIP_LIFT / float(G["c"].get("s", 1.0)) * w
            G[key] = lift
        return G[key]

    def _clear_teeth(self, dV: np.ndarray) -> np.ndarray:
        """GNM offsets with the lips kept in front of the teeth: a prototype made on an average face pulled Tess's
        lips back THROUGH her upper incisors (the smile x2: 33 front points of the upper row ahead of the lips, 3.5 mm;
        "teeth fragments along the lip line", expr_r6). Each skin vertex of the lips and the skin round them that sits
        behind a tooth's front at its height (GNM frame: z forward), within 1.5 mm across, is pushed forward to
        LIP_CLEAR in front of it; the push is spread over the skin's quads so it reads as the lip riding the teeth."""
        from scipy.spatial import cKDTree
        from . import base as basemod
        G = self._setup()
        g = G["g"]
        V = np.asarray(G["c"]["V"], float) + dV
        mp = basemod.gnm_mouth(self.head)
        T = np.concatenate([V[np.asarray(mp[k]["ids"])] for k in ("teeth_upper", "teeth_lower")])
        gr = g["groups"]
        lips = np.clip(sum(np.asarray(gr[k], float) for k in ("upper_lip", "lower_lip", "upper_lip_region",
                                                              "lower_lip_region")), 0, 1) > 0.5
        lips &= np.asarray(g["skin"], bool)
        ids = np.flatnonzero(lips)
        tree = cKDTree(T[:, :2])
        r = 0.0015 / float(G["c"].get("s", 1.0))
        push = np.zeros(len(V))
        for k, near in zip(ids, tree.query_ball_point(V[ids, :2], r)):
            if near:
                front = T[near, 2].max()
                if V[k, 2] < front + LIP_CLEAR and V[k, 2] > front - 0.012:  # (behind it, not the far side of the head)
                    push[k] = front + LIP_CLEAR - V[k, 2]
        if not push.any():
            return dV
        Q = g["quads"]
        cnt = np.zeros(len(V))
        for k in range(4):
            np.add.at(cnt, Q[:, k], 1)
        sp = push.copy()
        for _ in range(4):  # spread: each vertex takes the larger of its own push and its quads' mean
            acc = np.zeros(len(V))
            m = sp[Q].mean(1)
            for k in range(4):
                np.add.at(acc, Q[:, k], m)
            sp = np.maximum(push, np.where(cnt > 0, acc / np.maximum(cnt, 1), 0))
        out = np.array(dV, float)
        out[:, 2] += sp * np.asarray(g["skin"], bool)
        return out

    def _mouth_graph(self):
        """GNM's skin + mouth sock as a vertex graph (index pairs both ways), cached."""
        G = self._setup()
        if "mouth_graph" not in G:
            g = G["g"]
            Q = np.asarray(g["quads"])
            keep = np.asarray(g["skin"], bool) | (np.asarray(g["groups"]["mouth_sock"]) > 0.5)
            Q = Q[keep[Q].all(1)]
            e = np.concatenate([Q[:, [k, (k + 1) % 4]] for k in range(4)])
            e = np.unique(np.sort(e, 1), axis=0)
            G["mouth_graph"] = np.concatenate([e, e[:, ::-1]])
        return G["mouth_graph"]

    def _relax(self, F: np.ndarray, fixed: np.ndarray, free: np.ndarray, rounds: int) -> np.ndarray:
        """Jacobi rounds of the graph Laplacian on F (n, k): `free` vertices take their neighbours' mean, the rest
        stay (fixed values, or outside the region: their own)."""
        E = self._mouth_graph()
        n = len(F)
        deg = np.bincount(E[:, 0], minlength=n).astype(float)
        mv = free & ~fixed & (deg > 0)
        F = F.copy()
        for _ in range(rounds):
            acc = np.zeros_like(F)
            np.add.at(acc, E[:, 0], F[E[:, 1]])
            F[mv] = acc[mv] / deg[mv, None]
        return F

    def _wrap_teeth(self, dV: np.ndarray, measure: bool = False):
        """GNM offsets with the lips WRAPPING the teeth: real lips lie on the dental arch and slide over it as the
        mouth opens or smiles; ours stood off it and opened as a hole cut in the face (expr_r7..r12: "teeth small,
        floating", "the lips don't roll over the teeth"). Each vertex of the inner lip (the rolls and the contact
        ring) and the first sock rings, with a tooth or gum at its height within WRAP_ANGLE of its direction from the
        arch's centre, goes onto the arch's outer surface + WRAP_OFFSET: pulled in from up to WRAP_REACH outside, or
        out from up to WRAP_INSIDE inside (_clear_teeth's case). The moves spread smoothly (graph-harmonic) over the
        lips and sock round them, fading to nothing WRAP_SPREAD from the mouth's middle."""
        from scipy.spatial import cKDTree
        from . import base as basemod
        G = self._setup()
        g = G["g"]
        s_ = float(G["c"].get("s", 1.0))
        V0 = np.asarray(G["c"]["V"], float)
        V = V0 + (0.0 if self._gnm.get("parted") is not None else self._gnm.get("close_dV", 0.0)) + dV  # (r44: the rest parted)
        R = self._lip_rings()
        if not R["ok"]:
            return dV
        ring = basemod.LIP_RING
        mp = basemod.gnm_mouth(self.head)
        tid = np.concatenate([np.asarray(mp[k]["ids"]) for k in ("teeth_upper", "teeth_lower")])
        Tt = V[tid]
        up_ids = np.asarray(mp["teeth_upper"]["ids"])
        front = float(V[up_ids, 2].max())
        C = np.array([float(np.median(V[up_ids, 0])), 0.0, front - WRAP_CENTRE / s_])

        def polar(P):
            q = P - C
            return np.arctan2(q[:, 0], q[:, 2]), np.hypot(q[:, 0], q[:, 2])
        ta, tr = polar(Tt)
        wv = np.array([v for v, lv in R["lev"].items() if WRAP_RINGS[0] <= lv <= ring + WRAP_RINGS[1]], int)
        if not len(wv):
            return dV
        va, vr = polar(V[wv])
        tree = cKDTree(np.column_stack([ta * WRAP_CENTRE / s_, Tt[:, 1]]))
        near = tree.query_ball_point(np.column_stack([va * WRAP_CENTRE / s_, V[wv, 1]]), WRAP_ANGLE / s_)
        gaps = np.full(len(wv), np.nan)
        for j, nb in enumerate(near):
            if nb:
                gaps[j] = vr[j] - (float(tr[nb].max()) + WRAP_OFFSET / s_)
        if measure:
            return wv, gaps
        # relative to the rest (the closed mouth as GNM rests it): a vertex keeps the stand-off it has at rest, never
        # more (shapes add: wrapping each to the arch outright would pull the resting lips in once per shape)
        w0, g0 = self._wrap_teeth(np.zeros_like(dV), measure=True) if "wrap_rest" not in G else G["wrap_rest"]
        G["wrap_rest"] = (w0, g0)
        rest = dict(zip(w0.tolist(), g0.tolist()))
        mv = np.zeros((len(V), 3))
        fixed = np.zeros(len(V), bool)
        for j, k in enumerate(wv):
            gap = gaps[j]
            if not np.isfinite(gap) or not (-WRAP_INSIDE / s_ < gap < WRAP_REACH / s_):
                continue
            r0 = rest.get(int(k), np.nan)
            keep = WRAP_KEEP * max(0.0, r0) if np.isfinite(r0) else 0.0
            new = gap if 0.0 <= gap <= keep else (keep if gap > keep else 0.0)
            if new == gap:
                continue
            mv[k, 0] = (new - gap) * np.sin(va[j])
            mv[k, 2] = (new - gap) * np.cos(va[j])
            fixed[k] = True
        if not fixed.any():
            return dV
        skin_or_sock = np.asarray(g["skin"], bool) | (np.asarray(g["groups"]["mouth_sock"]) > 0.5)
        M0 = 0.5 * (G["X0"][62] + G["X0"][66])
        region = skin_or_sock & (np.linalg.norm(V0 - M0, axis=1) < WRAP_SPREAD / s_)
        teeth = np.zeros(len(V), bool)
        teeth[tid] = True
        region &= ~teeth
        return dV + self._relax(mv, fixed, region, WRAP_ROUNDS)

    def _smooth_sock(self, Xn: np.ndarray, d: np.ndarray, index, rest: bool = False) -> np.ndarray:
        """(one mesh, own quads) A shape's offsets with the mouth sock's POSED shape smoothed (Taubin, no shrinking)
        over GNM's quads, the skin held: the export's sock is tucked in behind the lips (retopo._with_mouth_sock
        narrows it 45% within 4 mm of the lips' loop), and opened by a shape that fold folds into crumpled walls
        beside the teeth (clay: faceted folds lit pink with dark voids between, "torn lining", expr_r7..r13). The
        rest pose's own shape is the smoothing's zero: only what the shape adds to the sock's unevenness goes; the
        rest itself is ironed by the neutral (rest=True: the folds were the tuck's, opened by every mouth shape)."""
        G = self._setup()
        g = G["g"]
        idx = np.asarray(index, int)
        sock = (np.asarray(g["groups"]["mouth_sock"]) > 0.5) & ~np.asarray(g["skin"], bool)
        ok = (idx >= 0) & (idx < len(sock))  # (gnmloops' own vertices are numbered past GNM's)
        rows = np.flatnonzero(ok)
        on = np.zeros(len(sock), bool)
        on[idx[rows]] = True
        mv = sock & on
        if not mv.any() or not (rest or np.abs(d[ok][sock[idx[ok]]]).max() > 1e-7):
            return d

        def taubin(P):
            for _ in range(SOCK_SMOOTH):
                P = P + 0.5 * (self._relax(P, ~mv, mv & on, 1) - P)
                P = P - 0.53 * (self._relax(P, ~mv, mv & on, 1) - P)
            return P
        A = np.zeros((len(sock), 3))
        B = np.zeros((len(sock), 3))
        A[idx[rows]] = Xn[rows]
        B[idx[rows]] = Xn[rows] + d[rows]
        dA, dB = (taubin(A) - A if SOCK_SMOOTH_REL and not rest else 0.0), taubin(B) - B  # (the rest's own subtracted)
        out = np.array(d, float)
        sel = rows[sock[idx[rows]]]
        out[sel] += (dB - dA)[idx[sel]]
        return out

    def _soft_edge(self, dV: np.ndarray, rounds: int | None = None) -> np.ndarray:
        """GNM offsets with the regional basis's hard edge melted: GNM's lower-face components stop dead ~60 mm out
        on the cheek (x2 the smile prototype left 3 mm against 0 there: a terraced crease at the cheekbone,
        expr_r6 / r7). Where the move is small next to its largest (under SOFT_EDGE of it) the offsets are
        averaged over the skin's quads `rounds` times, blended in by that ratio."""
        G = self._setup()
        Q = G["g"]["quads"]
        rounds = SOFT_ROUNDS if rounds is None else rounds
        S = np.array(dV, float)
        cnt = np.zeros(len(S))
        for k in range(4):
            np.add.at(cnt, Q[:, k], 1)
        for _ in range(rounds):
            acc = np.zeros_like(S)
            m = S[Q].mean(1)
            for k in range(4):
                np.add.at(acc, Q[:, k], m)
            S = np.where(cnt[:, None] > 0, acc / np.maximum(cnt, 1)[:, None], S)
        mag = np.linalg.norm(dV, axis=1)
        b = 1 - _ss(mag / (SOFT_EDGE * max(float(mag.max()), 1e-9)))
        return dV * (1 - b[:, None]) + S * b[:, None]

    def _cheek_raise(self, s: str) -> np.ndarray:
        """cheekSquint: the cheek under the eye up (GNM's zygomatic and infraorbital regions, feathered)."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        k = "left" if s == "Left" else "right"
        w = np.clip(g["groups"][f"{k}_zygomatic_region"] + 0.7 * g["groups"][f"{k}_infraorbital_region"], 0, 1)
        w = self._feather(w)
        out = np.zeros_like(V)
        out[:, 1] = CHEEK_RAISE[0] * G["wg"] * w  # GNM frame: y up, z forward
        out[:, 2] = CHEEK_RAISE[1] * G["wg"] * w
        return out

    def _feather(self, w: np.ndarray, rounds: int = 8) -> np.ndarray:
        Q = self._setup()["g"]["quads"]
        for _ in range(rounds):
            acc, cnt = np.zeros(len(w)), np.zeros(len(w))
            for k in range(4):
                np.add.at(acc, Q[:, k], w[Q].mean(1))
                np.add.at(cnt, Q[:, k], 1)
            w = acc / np.maximum(cnt, 1)
        return w

    def _cheek_puff(self) -> np.ndarray:
        """The cheeks blown out along their normals (no landmark there for the basis to aim at)."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        Q = g["quads"]
        N = vertex_normals(V, np.r_[Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]])
        w = np.clip(g["groups"]["left_cheek_region"] + g["groups"]["right_cheek_region"]
                    + 0.5 * (g["groups"]["left_parotid_region"] + g["groups"]["right_parotid_region"]), 0, 1)
        w = w * (1 - np.clip(g["groups"]["upper_lip_region"] + g["groups"]["lower_lip_region"], 0, 1))
        # feathered across the quads (the regions have hard edges)
        for _ in range(8):
            acc = np.zeros(len(V))
            cnt = np.zeros(len(V))
            for k in range(4):
                np.add.at(acc, Q[:, k], w[Q].mean(1))
                np.add.at(cnt, Q[:, k], 1)
            w = acc / np.maximum(cnt, 1)
        return N * (0.09 * G["wg"]) * w[:, None]

    def _carried(self, *dVs: np.ndarray) -> list:
        """GNM offsets (its frame, every GNM vertex) -> offsets of the head mesh's vertices (head["verts"]): the eye
        scaling's local magnification, the head's narrowing, the placement (scale, turn), then Catmull-Clark as the
        skin was (linear in the positions: all the offsets go through one subdivision side by side)."""
        from . import base as basemod
        c = self._setup()["c"]
        cols = []
        for dV in dVs:
            d = dV * c["esc"][:, None]
            if c.get("fade") is not None:  # (onemesh.py) one human mesh: nothing moves at the neck's stitch
                d = d * np.asarray(c["fade"], float)[:, None]
            d[:, 0] *= c["narrow"]
            dW = c["s"] * d[c["skin"]] @ c["R"].T
            if c["skin_index"] is not None:  # (zipped lips: never with face shapes, they need the lips apart)
                dW = dW[c["skin_index"] >= 0]
            cols.append(dW)
        D, faces = np.concatenate(cols, 1), c["faces"]
        for _ in range(c["subdivide"]):
            D, faces = basemod._catmull_clark(D, faces)
        return [D[:, 3 * k:3 * k + 3] for k in range(len(dVs))]

    def _carried_scalar(self, f: np.ndarray) -> np.ndarray:
        """A per-GNM-vertex value (a vertex group) on the head mesh's vertices, subdivided like the positions."""
        from . import base as basemod
        c = self._setup()["c"]
        v = np.asarray(f, float)[c["skin"]]
        if c["skin_index"] is not None:
            v = v[c["skin_index"] >= 0]
        D, faces = np.repeat(v[:, None], 3, 1), c["faces"]
        for _ in range(c["subdivide"]):
            D, faces = basemod._catmull_clark(D, faces)
        return D[:, 0]

    def _onto(self, X: np.ndarray, dW: np.ndarray):
        """Head-mesh offsets onto points X: inverse-distance over the 6 nearest head-mesh vertices, and how near the
        head mesh each point is (1 within 2 mm, 0 from 6 mm: the bag, teeth and tongue go by the jaw instead). Between the lips a point takes only its own lip's vertices: the parted lips are ~3 mm
        apart, so the nearest six mixed both lips and the jaw's opening tore the slit's walls into shards."""
        G = self._setup()
        if "sides" not in G:  # which lip each head vertex is: GNM's lip groups (the inner rolls curl past the
            # parting line's height, so height alone put lower-lip vertices in the upper lip), else its height
            from scipy.spatial import cKDTree
            W = np.asarray(self.head["verts"], float)
            gr = G["g"]["groups"]
            up_w, lo_w = self._carried_scalar(gr["upper_lip"]), self._carried_scalar(gr["lower_lip"])
            above = np.where(np.maximum(up_w, lo_w) > 0.3, up_w > lo_w, self.local(W)["h0"] >= 0)
            G["sides"] = [(np.flatnonzero(m), cKDTree(W[m])) for m in (above, ~above)]
        d, i = G["tree"].query(X, k=6)
        L = self.local(X)
        lips = _bump(L["u"], 0.95, 1.3) * _bump(L["back"], self.thick + 0.004, self.thick + 0.012) \
            * _bump(np.abs(L["h0"]), 3 * self.lip, 6 * self.lip)
        out = (dW[i] * self._idw(d)[..., None]).sum(1)
        sel = lips > 0
        if sel.any():
            sided = np.zeros((sel.sum(), 3))
            up = L["h0"][sel] >= 0
            for (idx, tree), m in zip(G["sides"], (up, ~up)):
                if m.any():
                    ds, js = tree.query(X[sel][m], k=6)
                    sided[m] = (dW[idx[js]] * self._idw(ds)[..., None]).sum(1)
            out[sel] = out[sel] * (1 - lips[sel, None]) + sided * lips[sel, None]
        return out, _bump(d[:, 0], 0.002, 0.006)

    def _lid_seal(self, s: str, Xn: np.ndarray, d: np.ndarray) -> np.ndarray:
        """A blink's lids brought onto ONE smooth line, on the low poly. The basis closes the eye (no ball shows), but
        each low-poly vertex of a lid's margin lands at its own height: a wavy line with dark slots between the
        margins. Across the eye in bins: the upper lid's lowest and the lower lid's highest front vertex as posed; the
        line = a parabola through the lower lid's; each lid is moved onto it (the upper LID_OVER past it). How much
        of that a vertex takes falls off with its posed DISTANCE from its lid's margin (`_lid_share`): a field that
        is smooth over the skin and zero on the cheek and the brow. (It was the vertex's share of its margin's blink
        travel: the lower lid travels ~1 mm, so on the cheek under it that ratio was noise, 0 on one vertex and 1
        on the next: s0urc3's sawtooth in the under-eye shadow, 7-22 mm below the eye.)
        spec.face_shapes.lid_seal: false | amount 0..1 | {"amount", "over", "band", "reach": [upper, lower] m}."""
        o = self.lid_seal
        amount, over, band = o["amount"], o["over"], o["band"]
        ev = self.eyes[s]
        c, r = np.asarray(ev["c"], float), float(ev["r"])
        lm = np.asarray(self.head["lm68"], float)
        ci, co = _mirror_ids([42, 45], s)  # the eye's inner and outer corners
        pairs = [(a_, b_) for a_, b_ in zip(_mirror_ids([43, 44], s), _mirror_ids([47, 46], s))]
        side = lm[co] - lm[ci]
        width = float(np.linalg.norm(side))
        side = side / width
        up = self.up - side * (self.up @ side)
        up /= np.linalg.norm(up)
        out = np.cross(side, up)
        out = out if out @ self.out > 0 else -out
        mid = 0.5 * (lm[ci] + lm[co])
        R0 = Xn - mid
        u, h0, f0 = R0 @ side, R0 @ up, (Xn - c) @ out
        # the opening's centre line at rest: through the corners and half way between each pair of lid landmarks
        ku = [-0.5 * width] + [float((0.5 * (lm[a_] + lm[b_]) - mid) @ side) for a_, b_ in pairs] + [0.5 * width]
        kh = [0.0] + [float((0.5 * (lm[a_] + lm[b_]) - mid) @ up) for a_, b_ in pairs] + [0.0]
        order = np.argsort(ku)
        hc = np.interp(u, np.array(ku)[order], np.array(kh)[order])
        rad = np.linalg.norm(Xn - c, axis=1)
        zone = (np.abs(u) < 0.62 * width) & (rad < 1.9 * r) & (f0 > 0.3 * r)
        front = zone & (rad > r + 2e-4)  # (the skin behind the margins, on the ball, is not a margin)
        upper = h0 > hc
        dh = d @ up
        hp = h0 + dh
        nb = 14
        edges = np.linspace(-0.5 * width, 0.5 * width, nb + 1)
        bc = 0.5 * (edges[1:] + edges[:-1])
        bi = np.clip(np.searchsorted(edges, u) - 1, 0, nb - 1)
        lo_u, hi_l = (np.full(nb, np.nan) for _ in range(2))
        # which vertices ARE a margin: those within a little of their lid's edge as posed (`_lid_edge`). A coarse
        # low poly has a few dozen vertices round the eye and most bins hold no margin vertex: the "highest lower-lid
        # vertex" of such a bin was a cheek vertex 13 mm under the eye, which was then lifted to the line.
        inside = np.abs(u) < 0.5 * width
        cu, cl = front & upper & (dh < -5e-4), front & ~upper
        mu_all = cu & self._lid_edge(u, hp, cu & inside, -1.0, LID_EDGE[0])
        ml_all = cl & self._lid_edge(u, hp, cl & inside, 1.0, LID_EDGE[1])
        for k in range(nb):
            mu = np.flatnonzero(mu_all & (bi == k))
            ml = np.flatnonzero(ml_all & (bi == k))
            if len(mu):
                lo_u[k] = hp[mu].min()
            if len(ml):
                hi_l[k] = hp[ml].max()
        ok = np.isfinite(lo_u) & np.isfinite(hi_l)
        if ok.sum() < 4:
            return d

        def fill(a_):
            return np.interp(bc, bc[np.isfinite(a_)], a_[np.isfinite(a_)])
        lo_u, hi_l = fill(lo_u), fill(hi_l)
        line = np.polyval(np.polyfit(bc, hi_l, 2), bc)
        # a closed eye's lid line arcs DOWN over the globe (lowest mid-eye); through the lower lid's points alone it
        # read "almost straight, a strip pasted across the eye" (expr_r5)
        # (the UPPER lid's target only: lowering the lower lid with it moved the skin under the eye, test
        # test_blink_seal_leaves_the_cheek; the upper lid is the line one sees, passing in front of the lower)
        sag = LID_SAG * np.clip(1 - (2 * bc / width) ** 2, 0, 1)
        # the upper lid goes `over` past the line only where the lids are two sheets: toward the corners they are one
        # skin, and the overlap turned over the small triangles there that have a vertex on each lid (Garrett's 20k
        # export, right eye blinked: 3 triangles at the inner corner, a dark notch; 1 of 0.9 mm2 left)
        if LID_OVER_FADE:
            over_b = over * _ss((LID_FADE[1] * width - np.abs(bc)) / ((LID_FADE[1] - LID_FADE[0]) * width))
            over = over * _ss((LID_FADE[1] * width - np.abs(u)) / ((LID_FADE[1] - LID_FADE[0]) * width))
        else:
            over_b = np.full(nb, over)
        ends = _bump(np.abs(u), 0.5 * width, 0.62 * width) * amount  # (fades out past the corners)
        d = d.copy()
        for sel, cur, tgt, reach, sgn in ((zone & upper, lo_u, line - over_b - sag, o["reach"][0], 1.0),
                                          (zone & ~upper, hi_l, line, o["reach"][1], -1.0)):
            if not sel.any():
                continue
            shift = np.interp(u[sel], bc, np.convolve(np.pad(tgt - cur, 1, mode="edge"), [0.25, 0.5, 0.25], "valid"))
            away = sgn * (hp[sel] - np.interp(u[sel], bc, cur))  # how far from its lid's margin, as posed
            d[sel] += (np.clip(shift, -0.004, 0.004) * self._lid_share(away, reach) * ends[sel])[:, None] * up
        # then no vertex of a lid is left across the line: the band either side of it is squeezed onto its own
        # lid's side (bins put each margin NEAR the line; its vertices still sat a little over and under it,
        # which is the wavy edge)
        ln = np.interp(u, bc, line)
        lu = ln - np.interp(u, bc, sag)  # (the upper lid's own line: dipped mid-eye)
        hp = h0 + d @ up
        t = np.clip((hp - (ln - band)) / (2 * band), 0.0, 1.0)
        tu = np.clip((hp - (lu - band)) / (2 * band), 0.0, 1.0)
        for sel, new in ((zone & upper & (hp < lu + band), lu - over + tu ** LID_PINCH * (band + over)),
                         (zone & ~upper & (hp > ln - band), ln - band * (1 - t) ** LID_PINCH)):
            if sel.any():
                d[sel] += ((new[sel] - hp[sel]) * ends[sel])[:, None] * up
        return d

    @staticmethod
    def _lid_edge(u: np.ndarray, h: np.ndarray, cand: np.ndarray, sgn: float, tol: float) -> np.ndarray:
        """Which vertices lie on a lid's edge: within `tol` m of the candidates' envelope across the eye (sgn +1:
        their upper envelope, the lower lid's margin; -1: the lower one), a parabola fitted with the points on the
        far side of it counting 2%."""
        idx = np.flatnonzero(cand)
        if len(idx) < 4:
            return np.zeros(len(u), bool)
        x, y = u[idx], sgn * h[idx]
        w = np.ones(len(idx))
        for _ in range(20):
            co = np.polyfit(x, y, 2, w=np.sqrt(w))
            w = np.where(y >= np.polyval(co, x), 1.0, 0.02)
        return sgn * h >= np.polyval(co, u) - tol

    @staticmethod
    def _lid_share(away: np.ndarray, reach: float) -> np.ndarray:
        """How much of its margin's correction a lid vertex takes: all of it at the margin (and past it), none
        from `reach` m away, eased between."""
        return 1.0 - _ss(np.clip(away / max(reach, 1e-6), 0.0, 1.0))

    @staticmethod
    def _idw(d):
        w = 1 / np.maximum(d, 1e-5) ** 2
        return w / w.sum(1, keepdims=True)

    def _rigid_lower_row(self, dV: np.ndarray):
        """The jaw as GNM's lower tooth row moves under offsets dV: a turn about the ear line (landmarks 0 / 16, the
        line jawOpen turns about) by the angle that best fits the row, then the row's mean remaining shift (world):
        (rotation, origin, t), applied as (X - origin) @ R.T + t. (A free Procrustes on the row, a short arc that
        GNM also bends 2.6 mm, swung the tongue's root UP 4.5 mm.)"""
        from . import base as basemod
        mp = basemod.gnm_mouth(self.head)
        ids = np.asarray(mp["teeth_lower"]["ids"])
        P0 = np.asarray(mp["teeth_lower"]["verts"], float)
        D = self._by_index(dV)[ids]
        lm = np.asarray(self.head["lm68"], float)
        o = 0.5 * (lm[0] + lm[16])
        ax = _unit(lm[16] - lm[0])
        best = None
        for ang in np.radians(np.linspace(-40, 40, 321)):
            Rr = _rodrigues(ax, np.array([ang]), np.eye(3))
            Q = (P0 - o) @ Rr.T + o
            t = (P0 + D - Q).mean(0)
            err = float(((Q + t - P0 - D) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, Rr, t)
        _, Rr, t = best
        return Rr, o, o + t

    def _rigid_jaw(self, dW: np.ndarray):
        """The jaw's rigid motion in a shape (Procrustes on the jaw line's landmarks, world): (rotation, origin, t)."""
        lm = self.head["lm68"]
        ids = [4, 5, 6, 7, 8, 9, 10, 11, 12]
        P0 = lm[ids]
        D, _ = self._onto(P0, dW)
        P1 = P0 + D
        a, b = P0.mean(0), P1.mean(0)
        U, _, Vt = np.linalg.svd((P0 - a).T @ (P1 - b))
        Rr = (U @ Vt).T
        if np.linalg.det(Rr) < 0:
            Vt[-1] *= -1
            Rr = (U @ Vt).T
        return Rr, a, b

    def neutral(self, Xm: np.ndarray, kind: str, index=None) -> np.ndarray:
        """The lips closed: the inner lips' landmarks moved half the gap each, solved in the basis and carried."""
        if kind != "skin" and not (self.gnm_mouth and kind in ("teeth", "tongue")):
            return np.zeros_like(Xm)
        if "close" not in self._gnm:
            G = self._setup()
            X0 = G["X0"]
            mv = {}
            for u, l in ((61, 67), (62, 66), (63, 65)):
                gap = (X0[l] - X0[u]) / G["wg"]
                mv[u], mv[l] = 0.5 * gap, -0.5 * gap
            dV = self._solve(mv, "mouth", hold=0.2)
            dW, = self._carried(dV)
            # the basis gets most of the way (holding the outer lips); scaled so the inner lips' midpoints meet
            lm = self.head["lm68"]
            D, _ = self._onto(lm[[62, 66]], dW)
            want = float((lm[66] - lm[62]) @ self.up)
            got = float((D[0] - D[1]) @ self.up)
            k = float(np.clip(-want / got, 1.0, 2.0) if got * want < 0 else 1.0)
            self._gnm["close"] = dW * k
            self._gnm["close_dV"] = dV * k
        if kind != "skin":  # GNM's own teeth / tongue: their own share of the same closing expression
            return self._piece_onto(Xm, self._gnm["close_dV"], kind)
        D, a = self._onto(Xm, self._gnm["close"])
        D = D * a[:, None]
        if index is not None:  # (one mesh, own quads) GNM's own vertices take GNM's own offsets
            D = self._indexed(D, index, self._gnm["close_dV"])
            if LIPS_MEET:  # what the basis leaves between the lips closed on GNM's own contact ring
                M = self._lips_meet(Xm + D, index)
                self._gnm["meet"] = (Xm.shape, M)  # (a shape that parts the lips takes it back: displacements)
                D = D + self._corners_meet(Xm + D + M, index)  # (kept by every shape: the commissure stays sealed)
                B = self._rolls_behind(Xm + D + M, index)  # the rolls behind the closed seam (taken back with M)
                self._gnm["meet"] = (Xm.shape, M + B)
                D = D + M + B
            if SOCK_SMOOTH and self.gnm_mouth:  # the rest's sock ironed too (hidden here; every shape opens onto it)
                D = self._smooth_sock(Xm, D, index, rest=True)
        if NEUTRAL_PARTED and index is not None:  # the approved lips kept; the close is mouthClose's (displacements)
            self._gnm["parted"] = (Xm.shape, D)
            self._gnm["meet"] = None
            return np.zeros_like(Xm)
        return D

    def _lip_rings(self) -> dict:
        """GNM's lips as rings (its index space): the skin's open mouth loop (where the sock joins), ring k out
        from it; the contact ring (base.LIP_RING out: the inner-lip landmarks sit on it) split in an upper and a
        lower half by its corners."""
        if "rings" in self._gnm:
            return self._gnm["rings"]
        import collections
        from . import base as basemod
        G = self._setup()
        g = G["g"]
        skin = np.asarray(g["skin"], bool)
        Q = np.asarray(g["quads"])
        Q = Q[skin[Q].all(1)]
        cnt = collections.Counter()
        adj = collections.defaultdict(set)
        for q in Q:
            for k in range(4):
                a, b = int(q[k]), int(q[(k + 1) % 4])
                cnt[(min(a, b), max(a, b))] += 1
                adj[a].add(b)
                adj[b].add(a)
        V = np.asarray(G["c"]["V"], float)
        X0 = G["X0"]
        seam = 0.5 * (X0[62] + X0[66])
        reach = 3.0 * float(np.linalg.norm(X0[54] - X0[48]))
        loop = {v for (a, b), c in cnt.items() if c == 1 for v in (a, b)
                if np.linalg.norm(V[a] - seam) < reach and np.linalg.norm(V[b] - seam) < reach}
        lev = {v: 0 for v in loop}
        dq = collections.deque(lev)
        while dq:
            v = dq.popleft()
            if lev[v] >= basemod.LIP_RING + LIP_HOLD + LIP_FADE:
                continue
            for w in adj[v]:
                if w not in lev:
                    lev[w] = lev[v] + 1
                    dq.append(w)
        ring = basemod.LIP_RING
        def halves(k):
            """Ring k as an (upper, lower) pair of vertex lists from corner to corner, or None."""
            rv = [v for v, lv in lev.items() if lv == k]
            rs = set(rv)
            nb = {v: [w for w in adj[v] if w in rs] for v in rv}
            if not rv or any(len(n) != 2 for n in nb.values()):
                return None
            lp, prev = [rv[0]], None
            while True:
                nx = [w for w in nb[lp[-1]] if w != prev]
                prev = lp[-1]
                if nx[0] == lp[0]:
                    break
                lp.append(nx[0])
            if len(lp) != len(rv):
                return None
            x = V[lp, 0]
            i0, i1, m = int(np.argmin(x)), int(np.argmax(x)), len(lp)
            a = [lp[(i0 + j) % m] for j in range((i1 - i0) % m + 1)]
            b = [lp[(i1 + j) % m] for j in range((i0 - i1) % m + 1)][::-1]
            return (a, b) if V[a, 1].mean() > V[b, 1].mean() else (b, a)  # (GNM's frame: Y up)
        out = {"lev": lev, "ok": False}
        h = halves(ring)
        if h:
            out.update(ok=True, up=h[0], lo=h[1])
            out["outer"] = {k: halves(k) for k in list(range(0, ring)) + list(range(ring + 1, ring + LIP_HOLD + 2))}
        # the mouth sock, ring by ring in from the loop (negative levels): it rides with the lips' close, fading
        # (left still, the loop's ring stretched against it in every shape that takes the close back)
        sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
        sadj = collections.defaultdict(set)
        for q in np.asarray(g["quads"]):
            if (sock[q] | skin[q]).all() and sock[q].any():
                for k in range(4):
                    a, b = int(q[k]), int(q[(k + 1) % 4])
                    sadj[a].add(b)
                    sadj[b].add(a)
        dq = collections.deque(v for v in loop)
        sl = {v: 0 for v in loop}
        while dq:
            v = dq.popleft()
            if sl[v] >= LIP_FADE:
                continue
            for w in sadj[v]:
                if w not in sl and sock[w] and not skin[w]:
                    sl[w] = sl[v] + 1
                    dq.append(w)
        for v, k in sl.items():
            if k > 0:
                lev[v] = -k
        if out["ok"]:  # which lip each ring vertex belongs to: GNM's own lip groups, else the nearer half of the
            # contact ring (by distance alone an inner-roll vertex at a corner went to the other lip: a 3 mm spike)
            cu, cl = V[out["up"]], V[out["lo"]]
            gu, gl = np.asarray(g["groups"]["upper_lip"], float), np.asarray(g["groups"]["lower_lip"], float)
            out["side"] = {v: (gu[v] > gl[v]) if max(gu[v], gl[v]) > 0.3 else
                           (np.linalg.norm(cu - V[v], axis=1).min() <= np.linalg.norm(cl - V[v], axis=1).min())
                           for v in lev}
            for v in out["up"]:
                out["side"][v] = True
            for v in out["lo"]:
                out["side"][v] = False
        self._gnm["rings"] = out
        return out

    def _corners_meet(self, X: np.ndarray, index) -> np.ndarray:
        """(one mesh, own quads) The rings in front of the contact ring drawn together at the mouth's corners (the
        commissure): each ring's upper and lower halves, by CORNER_CLOSE of the way at the corner, fading to nothing
        over LIP_CORNER of the mouth's width and over the rings outward. Left open, every corner was a pocket with
        the rolls showing; taken back with the lips' close in shapes, it tore jawOpen's rolls (so it stays)."""
        R = self._lip_rings()
        D = np.zeros_like(X)
        Tk = np.zeros(len(X))
        if not R["ok"]:
            return D
        from . import base as basemod
        ring = basemod.LIP_RING
        row = {int(v): i for i, v in enumerate(np.asarray(index, int)) if v >= 0}
        # first the rings themselves near the corners: a fitted identity with a narrow mouth bunches the inner rolls
        # there (each ring a zigzag: lumps and tatters at both corners of the neutral, on every export of Garrett);
        # each half ring is smoothed along itself, by how near the corner it is, its ends held
        X0, X = X, X.copy()
        rings_ = dict(R.get("outer") or {})
        rings_[ring] = (R["up"], R["lo"])
        for k, hk in rings_.items():
            if k > ring + 2 or not hk or not all(v in row for v in hk[0] + hk[1]):
                continue
            for verts in hk:
                ids = [row[v] for v in verts]
                P = X[ids].copy()
                if len(P) < 5:
                    continue
                span_ = max(float(P[:, 0].max() - P[:, 0].min()), 1e-9)
                edge_ = np.minimum(P[:, 0] - P[:, 0].min(), P[:, 0].max() - P[:, 0])
                w_ = ROLL_SMOOTH * (1 - _ss(np.clip(edge_ / (TUCK_SPAN * span_), 0, 1)))
                for _ in range(ROLL_PASSES):
                    P[1:-1] += w_[1:-1, None] * (0.5 * (P[:-2] + P[2:]) - P[1:-1])
                X[ids] = P
        for k, hk in (R.get("outer") or {}).items():
            if not hk or not all(v in row for v in hk[0] + hk[1]):
                continue
            u, l = hk
            Pu, Pl = X[[row[v] for v in u]], X[[row[v] for v in l]]

            def arc(P):
                d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
                return d / max(float(d[-1]), 1e-12)
            su, sl = arc(Pu), arc(Pl)
            span = max(float(Pu[:, 0].max() - Pu[:, 0].min()), 1e-9)
            wk = 1.0 if k < ring else 1 - (k - ring - 1) / (LIP_HOLD + 1)  # (the rolls inside the contact ring too)
            for P, s, Q, sq, verts in ((Pu, su, Pl, sl, u), (Pl, sl, Pu, su, l)):
                other = np.column_stack([np.interp(s, sq, Q[:, j]) for j in range(3)])
                edge = np.minimum(P[:, 0] - P[:, 0].min(), P[:, 0].max() - P[:, 0])
                wc = CORNER_CLOSE * wk * (1 - _ss(np.clip(edge / (LIP_CORNER * span), 0, 1)))
                for j, v in enumerate(verts):
                    D[row[v]] += wc[j] * 0.5 * (other[j] - P[j])
                if k <= ring and CORNER_TUCK:   # the rolls (and a share of the contact ring) sink back at the corners:
                    tk = CORNER_TUCK * (ring + 1 - k) / (ring + 1) * (1 - _ss(np.clip(edge / (TUCK_SPAN * span), 0, 1)))
                    for j, v in enumerate(verts):   # bunched there, they stood out through the lips as lumps
                        Tk[row[v]] = max(Tk[row[v]], float(tk[j]))   # (a corner vertex is in both halves: once)
        return (X - X0) + D - Tk[:, None] * self.out

    def _rolls_behind(self, X: np.ndarray, index) -> np.ndarray:
        """(one mesh, own quads) The rings inside the contact ring (the inner rolls, the loop, the sock) pushed back
        behind the closed lips' contact line by ROLL_BEHIND, along `out`. Closing on the contact ring with the rolls
        riding along folded the upper roll FORWARD past the seam where the open-mouthed low poly's rolls stood
        proud of it (Tess: 1 mm at 6-9 mm either side of the midline): a flap of wet inner lip on the closed mouth
        (expr_r8..r12, "notch", "pink sliver", "jagged seam"). Displacements; vertices already behind are kept."""
        R = self._lip_rings()
        D = np.zeros_like(X)
        if not R["ok"] or not ROLL_BEHIND:
            return D
        from . import base as basemod
        ring = basemod.LIP_RING
        idx = np.asarray(index, int)
        row = {int(v): i for i, v in enumerate(idx) if v >= 0}
        cont = [row[v] for v in R["up"] + R["lo"] if v in row]
        if len(cont) < 4:
            return D
        P = X[cont]
        xs = P @ self.side
        o = np.argsort(xs)
        xs, dep = xs[o], ((P - self.M) @ self.out)[o]
        inner = np.array([row[v] for v, lv in R["lev"].items() if lv < ring and v in row], int)
        if not len(inner):
            return D
        xi = X[inner] @ self.side
        lim = np.interp(np.clip(xi, xs[0], xs[-1]), xs, dep) - ROLL_BEHIND
        over = (X[inner] - self.M) @ self.out - lim
        D[inner] = -np.maximum(over, 0.0)[:, None] * self.out[None]
        return D

    def seam_showing(self, X: np.ndarray, T: np.ndarray, index, px: float = 0.0001, tilt: float = 0.0,
                     normals: np.ndarray | None = None) -> float | None:
        """(one mesh, own quads) The area (mm^2) of the mouth's inside seen from the front on a closed mouth: an
        orthographic z-buffer along -out over the lips (px m per pixel), counting pixels whose front-most triangle
        has a vertex inside the contact ring (inner rolls, loop, sock: lev -1). 0 = the lips close on one seam. None if the
        rings aren't found."""
        R = self._lip_rings()
        if not R["ok"]:
            return None
        from . import base as basemod
        ring = basemod.LIP_RING
        idx = np.asarray(index, int)
        lev = np.full(len(X), 99)
        for i, v in enumerate(idx):
            if v >= 0 and int(v) in R["lev"]:
                lev[i] = R["lev"][int(v)]
        cont = lev == ring
        if cont.sum() < 4:
            return None
        # the sock (GNM's mouth-lining vertices that aren't skin) is inside too: the rings' search runs over the skin
        # only, so the sock read 99 (outside) and a crumpled sock through the seal counted nothing (x32: "dark-red
        # shards along the whole lip line" at seam_showing 0.000)
        g = self._setup()["g"]
        sock = (np.asarray(g["groups"]["mouth_sock"]) > 0.5) & ~np.asarray(g["skin"], bool)
        ins = (idx >= 0) & (idx < len(sock))
        lev[ins & sock[np.clip(idx, 0, len(sock) - 1)]] = -1
        Q = X - self.M
        ca, sa = np.cos(tilt), np.sin(tilt)  # the view tilted about `side` (radians, + = from above)
        up, out = ca * self.up - sa * self.out, ca * self.out + sa * self.up
        u, h, d = Q @ self.side, Q @ up, Q @ out
        u0, u1 = float(u[cont].min()), float(u[cont].max())
        h0, h1 = float(h[cont].min()) - 0.004, float(h[cont].max()) + 0.004
        T = np.asarray(T, int)
        tu, th = u[T], h[T]
        sel = (tu.max(1) >= u0) & (tu.min(1) <= u1) & (th.max(1) >= h0) & (th.min(1) <= h1)
        nu, nh = int(np.ceil((u1 - u0) / px)) + 1, int(np.ceil((h1 - h0) / px)) + 1
        zb = np.full((nh, nu), -np.inf)
        inner = np.zeros((nh, nu), bool)
        facing = np.ones((nh, nu))  # the shading normal (as exported) along the view, where a front face is
        bad_t = (lev[T] < ring).any(1)
        for t in np.where(sel)[0]:
            a, b, c = T[t]
            ax, ay, bx, by, cx, cy = u[a], h[a], u[b], h[b], u[c], h[c]
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-14:
                continue
            i0, i1 = max(0, int((min(ax, bx, cx) - u0) / px)), min(nu - 1, int((max(ax, bx, cx) - u0) / px) + 1)
            j0, j1 = max(0, int((min(ay, by, cy) - h0) / px)), min(nh - 1, int((max(ay, by, cy) - h0) / px) + 1)
            if i1 < i0 or j1 < j0:
                continue
            gx, gy = np.meshgrid(u0 + np.arange(i0, i1 + 1) * px, h0 + np.arange(j0, j1 + 1) * px)
            l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
            l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
            l3 = 1 - l1 - l2
            on = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
            z = l1 * d[a] + l2 * d[b] + l3 * d[c]
            sub = zb[j0:j1 + 1, i0:i1 + 1]
            win = on & (z > sub)
            sub[win] = z[win]
            inner[j0:j1 + 1, i0:i1 + 1][win] = bad_t[t]
            if normals is not None:
                nf = (l1[..., None] * normals[a] + l2[..., None] * normals[b] + l3[..., None] * normals[c]) @ out
                facing[j0:j1 + 1, i0:i1 + 1][win] = nf[win]
        self._seam_mask = (inner, zb, u0, h0, px)  # (for diagnostics)
        self._seam_facing = facing
        # a one-pixel line is the seam itself (the contact faces edge-on), not a gap: counted where 3 rows are inside
        core = inner[1:-1] & inner[:-2] & inner[2:]
        return float(core.sum()) * (px * 1000) ** 2

    def _rolls_tucked(self, Xn: np.ndarray, d: np.ndarray, index) -> np.ndarray:
        """(one mesh, own quads) A mouth shape's offsets with each lip's inner roll (rings inside the contact ring)
        kept behind its own lip's edge as seen from the front: an upper-roll vertex no lower than the upper contact
        ring at its x (less ROLL_TUCK_SLACK), a lower one no higher than the lower contact ring. Parted (smile, upper
        up, jawOpen) the upper roll hung below the vermilion as a wet pink band over the teeth, "the inner lip shows,
        not dry lip edges against the teeth" (expr_r11..r13). At rest the rolls already turn up / down behind the
        seam: no change there."""
        R = self._lip_rings()
        if not R["ok"]:
            return d
        from . import base as basemod
        ring = basemod.LIP_RING
        idx = np.asarray(index, int)
        row = {int(v): i for i, v in enumerate(idx) if v >= 0}
        P = Xn + d
        out = np.array(d, float)
        for half, sgn in ((R["up"], 1.0), (R["lo"], -1.0)):
            c = [row[v] for v in half if v in row]
            if len(c) < 4:
                continue
            xs, hs = P[c] @ self.side, (P[c] - self.M) @ self.up
            o = np.argsort(xs)
            xs, hs = xs[o], hs[o]
            rv = np.array([row[v] for v, lv in R["lev"].items() if 0 <= lv < ring and v in row
                           and bool(R["side"].get(v, True)) == (sgn > 0)], int)
            if not len(rv):
                continue
            lim = np.interp(np.clip(P[rv] @ self.side, xs[0], xs[-1]), xs, hs) - sgn * ROLL_TUCK_SLACK
            h = (P[rv] - self.M) @ self.up
            short = np.maximum(sgn * (lim - h), 0.0)  # how far it hangs past its lip's edge
            out[rv] += (sgn * short)[:, None] * self.up[None]
        return out

    def _smile_edge(self, Xn: np.ndarray, d: np.ndarray, index, side: str) -> np.ndarray:
        """(one mesh, own quads) SMILE_EDGE_LIFT: the upper lip's edge (its contact ring and the inner rolls, fading
        over SMILE_EDGE_LIFT[1] rings outward) lifted up the incisors, arched (full at the middle, 0 at the corners),
        this side's half faded across the midline like the prototype (SMILE_SIDE_MM)."""
        A, E, pw = SMILE_EDGE_LIFT
        R = self._lip_rings()
        if not R["ok"]:
            return d
        from . import base as basemod
        ring = basemod.LIP_RING
        row = {int(v): i for i, v in enumerate(np.asarray(index, int)) if v >= 0}
        P = Xn + d
        c = [row[v] for v in R["up"] if v in row]
        if len(c) < 4:
            return d
        xs = P[c] @ self.side
        mid, half = 0.5 * (xs.min() + xs.max()), 0.5 * (xs.max() - xs.min())
        out = np.array(d, float)
        sg = 1.0 if side == "Left" else -1.0
        E = int(E)
        for k in range(0, ring + E + 1):
            hv = R["up"] if k == ring else (R["outer"].get(k) or (None,))[0]
            if not hv:
                continue
            wl = 1.0 if k <= ring else 1.0 - (k - ring) / (E + 1.0)
            rv = np.array([row[v] for v in hv if v in row], int)
            if not len(rv):
                continue
            x = P[rv] @ self.side - mid
            arch = np.clip(1.0 - np.abs(x / half) ** pw, 0.0, 1.0)
            sw = 0.5 * (1 + np.tanh(sg * x / (SMILE_SIDE_MM * 0.001)))
            out[rv] += (A * wl * arch * sw)[:, None] * self.up[None]
        return out

    def _smile_fold(self, X: np.ndarray, nrm: np.ndarray, side: str, corner: bool = True) -> np.ndarray:
        """The nasolabial fold a smile makes (GNM's happy prototype on Tess raised no fold and no cheek: "no nasolabial
        crease, cheeks don't rise", expr_r11..r14): along the line from the nose wing's base past the mouth corner
        (landmarks 35 -> 54 on the head's left, 31 -> 48 right, carried SMILE_FOLD_PAST of the mouth's width beyond
        the corner and down), a crease SMILE_FOLD[0] deep and SMILE_FOLD[1] wide into the skin, and the cheek on
        its outer side pushed out SMILE_FOLD[2] fading over SMILE_FOLD[3]; both fade out toward the line's ends. And
        the mouth's corner lifted SMILE_LIFT[0], fading over SMILE_LIFT[1] ("corners pulled sideways, not up")."""
        lm = np.asarray(self.head["lm68"], float)
        a, c = (lm[35], lm[54]) if side == "Left" else (lm[31], lm[48])
        b = c + (c - a) * SMILE_FOLD_PAST
        depth, width, bulge, reach = SMILE_FOLD
        ab = b - a
        L = float(np.linalg.norm(ab))
        t = np.clip((X - a) @ ab / L ** 2, 0, 1)
        Q = a + t[:, None] * ab
        r = X - Q
        r = r - (r @ self.out)[:, None] * self.out  # across the line, in the face's plane
        dist = np.linalg.norm(r, axis=1)
        sgn_out = np.sign(r @ _unit(np.cross(self.out, ab) if side == "Left" else np.cross(ab, self.out)))
        ends = np.sin(np.pi * t) ** 0.7 * (np.abs((X - Q) @ self.out) < 0.02)
        if SMILE_FOLD_CORNER:  # held off the mouth corner (the lips' seam tears under a deep crease)
            ends = ends * _ss(np.clip(np.linalg.norm(X - c, axis=1) / SMILE_FOLD_CORNER, 0, 1))
        crease = -depth * np.exp(-(dist / width) ** 2)
        cheek = bulge * np.where(sgn_out > 0, np.exp(-(np.maximum(dist - width, 0) / reach) ** 2) *
                                 (1 - np.exp(-(dist / width) ** 2)), 0.0)
        lift = SMILE_LIFT[0] * np.exp(-(np.linalg.norm(X - c, axis=1) / SMILE_LIFT[1]) ** 2) * float(corner)  # the corner up
        push = np.zeros(len(X))
        if CHEEK_LIFT[0] or CHEEK_LIFT[2]:  # the cheek mass up (and out) under the eye, held at the lower lid
            lid = lm[[46, 47] if side == "Left" else [40, 41]].mean(0)
            C = lid + CHEEK_LIFT[3] * (c - lid)
            g = np.exp(-(np.linalg.norm(X - C, axis=1) / CHEEK_LIFT[1]) ** 2)
            below = (lid - X) @ self.up
            g = g * _ss(np.clip(below / max(0.5 * float((lid - C) @ self.up), 1e-4), 0, 1))
            lift = lift + CHEEK_LIFT[0] * g
            push = CHEEK_LIFT[2] * g
        return ((crease + cheek) * ends + push)[:, None] * np.asarray(nrm, float) + lift[:, None] * self.up[None]

    def _meet_share(self, D: np.ndarray, M: np.ndarray, index) -> float:
        """How much of the neutral's lip close a shape takes back: 0 if it keeps the lips together, 1 once it parts
        them by the gap that was closed (the contact ring's halves, along the close's own direction)."""
        R = self._lip_rings()
        if not R["ok"]:
            return 0.0
        row = {int(v): i for i, v in enumerate(np.asarray(index, int)) if v >= 0}
        up = [row[v] for v in R["up"] if v in row]
        lo = [row[v] for v in R["lo"] if v in row]
        closed = float(np.mean(M[up] @ self.up) - np.mean(M[lo] @ self.up))  # how far the close drew them together
        if closed > -1e-5:
            return 0.0
        opened = float(np.mean(D[up] @ self.up) - np.mean(D[lo] @ self.up))
        return float(np.clip(opened / -closed, 0.0, 1.0))

    def _lips_meet(self, X: np.ndarray, index) -> np.ndarray:
        """(one mesh, own quads) What the basis's close leaves between the lips, closed on GNM's own rings: each
        contact-ring vertex moved to halfway between its lip and the other lip at the same arc length (LIP_MEET past
        it: they touch), the rings inside the lips (the rolls, the loop) riding with their contact vertex, the rings
        outside fading over three. The decimated path's Face.seal does this on bins; here the topology is GNM's."""
        R = self._lip_rings()
        D = np.zeros_like(X)
        if not R["ok"]:
            return D
        from . import base as basemod
        idx = np.asarray(index, int)
        row = {int(v): i for i, v in enumerate(idx) if v >= 0}
        up = [v for v in R["up"] if v in row]
        lo = [v for v in R["lo"] if v in row]
        if len(up) < 3 or len(lo) < 3:
            return D

        def arc(P):
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(X[[row[v] for v in P]], axis=0), axis=1))]
            return d / max(float(d[-1]), 1e-12)
        su, sl = arc(up), arc(lo)
        Pu, Pl = X[[row[v] for v in up]], X[[row[v] for v in lo]]
        mv = {}
        for P, s, Q, sq, verts, sgn in ((Pu, su, Pl, sl, up, 1.0), (Pl, sl, Pu, su, lo, -1.0)):
            other = np.column_stack([np.interp(s, sq, Q[:, j]) for j in range(3)])
            mid = 0.5 * (P + other)
            gap = other - P
            n = np.linalg.norm(gap, axis=1, keepdims=True)
            push = np.where(n > 1e-9, gap / np.maximum(n, 1e-9), 0.0) * LIP_MEET
            for k, v in enumerate(verts):
                mv[v] = mid[k] + push[k] - P[k]
        ring = basemod.LIP_RING
        # the close as a SMOOTH function of x along each lip (per vertex pairs, it stepped between the columns of
        # the rolls: a sawtooth in every shape that takes it back), tapered to nothing at the corners
        fx = {}
        for half, verts in ((True, up), (False, lo)):
            P = X[[row[v] for v in verts]]
            o = np.argsort(P[:, 0])
            xs = P[o, 0]
            M = np.array([mv[verts[k]] for k in o])
            for _ in range(3):
                M[1:-1] = 0.25 * M[:-2] + 0.5 * M[1:-1] + 0.25 * M[2:]
            span = max(float(xs[-1] - xs[0]), 1e-9)
            fx[half] = (xs, M, span)
        for v, lv in R["lev"].items():
            if v not in row:
                continue
            fw = (1.0 if lv <= ring + LIP_HOLD else max(0.0, 1.0 - (lv - ring - LIP_HOLD) / LIP_FADE)) if lv >= 0 \
                else max(0.0, 1.0 + lv / (LIP_FADE + 1.0))  # (in the sock: fading toward the throat)
            if fw <= 0:
                continue
            xs, M, span = fx[bool(R["side"][v])]
            x = float(X[row[v], 0])
            taper = float(_ss(np.clip((min(x - xs[0], xs[-1] - x)) / (LIP_TAPER * span), 0, 1)))
            D[row[v]] = fw * taper * np.array([np.interp(x, xs, M[:, j]) for j in range(3)])
        return D

    def _by_index(self, dV: np.ndarray) -> np.ndarray:
        """GNM offsets (its frame, every GNM vertex) -> world offsets of every GNM vertex, as the head places them
        (the one mesh: no subdivision, the stitch's fade)."""
        c = self._setup()["c"]
        d = dV * np.asarray(c["esc"], float)[:, None]
        if c.get("fade") is not None:
            d = d * np.asarray(c["fade"], float)[:, None]
        d[:, 0] *= c["narrow"]
        return c["s"] * d @ np.asarray(c["R"], float).T

    def _indexed(self, D: np.ndarray, index, dV: np.ndarray) -> np.ndarray:
        idx = np.asarray(index, int)
        own = idx >= 0
        D = np.array(D, float)
        from . import gnmloops  # (the lids' new vertices, ids >= GNM's count: their parents' mean)
        D[own] = gnmloops.take(self._by_index(dV), idx[own])
        return D

    def displacements(self, Xm, Xn, nrm, kind, names, lower=None, index=None) -> dict:
        if kind == "eyes":
            return self.eye_part(Xm, names)
        G = self._setup()
        L = self.local(Xm)
        n = len(Xm)
        wj = self.jaw_weight(L) if kind == "skin" else (np.ones(n) if kind == "tongue" else
                                                        (np.zeros(n) if lower is None else lower.astype(float)))
        res = {}
        todo = [nm for nm in names if nm not in G.setdefault("dW", {}) and family(nm) != "look"]
        if todo:  # every shape's GNM offsets, then one subdivision for all of them
            dVs = []
            for name in todo:
                mv, region = self._gnm_moves(name)
                dV = mv if region is None else self._solve(mv, region,
                                                           prior=JAW_PRIOR if name in JAW_PRIORED else SOLVE_RIDGE)
                if name == "tongueOut" and self.gnm_mouth:  # GNM's own tongue components on top of the jaw's opening
                    dV = dV + self._tongue_out()[0]
                if self.gnm_mouth and WRAP_TEETH and name.split("Left")[0].split("Right")[0] in WRAP_SHAPES:
                    dV = self._wrap_teeth(dV)
                dVs.append(dV)
            G["dW"].update(zip(todo, self._carried(*dVs)))
            G.setdefault("dV", {}).update(zip(todo, dVs))
        # regions: the basis's lower-face components reach up to the lids and its eye components down the cheek;
        # each family fades out past its own region (jawOpen moved the forehead, brows tugged the cheek)
        lm = self.head["lm68"]
        h = (Xm - self.M) @ self.up
        hn = float((lm[33] - self.M) @ self.up)                   # the nose's base
        hl = float(np.mean([(lm[i] - self.M) @ self.up for i in (40, 41, 46, 47)]))  # the lower lids
        mouth_mask = 1 - _ss((h - (hn + 0.35 * (hl - hn))) / (0.55 * (hl - hn)))
        eye_mask = _ss((h - hn) / (0.5 * (hl - hn)))
        carry = {}
        if SMILE_FIT_FADE:
            fw = SMILE_FIT_FADE * (hl - hn)
            fit_mouth = 1 - _ss((h - (hl - fw)) / fw)
        for name in names:
            if family(name) == "look":  # (the eyeballs' part turns; the skin stays)
                res[name] = np.zeros_like(Xm)
                continue
            dW = G["dW"][name]
            if self.gnm_mouth and kind in ("teeth", "tongue"):
                # GNM's own teeth and tongue: the shape's expression coefficients on THEIR vertices (the lower row
                # and the tongue go with the lower-face components, the tongue with its own; the upper row stays)
                if kind == "tongue" and name in JAW_SHAPES:  # the tongue rides the lower row rigidly (its own share
                    # of the jaw's coefficients left it up in the opening: expr_r4's "red mass"), tongueOut adds its own
                    Rr, a, b = self._rigid_lower_row(G["dV"][name])
                    d = (Xn - a) @ Rr.T + b - Xn
                    if name == "tongueOut":
                        d = d + self._piece_onto(Xn, self._tongue_out()[0], "tongue")
                    if name == "jawOpen" and any(JAW_TONGUE):  # GNM's own tongue shape: tip down behind the
                        # lower teeth, the top bowed (r25)
                        d = d + self._piece_onto(Xn, self._tongue_shape(*JAW_TONGUE), "tongue")
                    if name == "jawOpen":  # the dorsum flattens as the floor of the mouth drops (it rose into the
                        # opening, "a red mass", expr_r4..r6): each point down by its height share over the tongue
                        hh = (Xn - Xn.min(0)) @ self.up
                        d = d - (TONGUE_SINK + TONGUE_DROP * (hh / max(float(hh.max()), 1e-9)))[:, None] * self.up[None]
                        if any(TONGUE_DOME):  # (r32) a sagittal dome: the front half rolls down toward the tip
                            # (quadratic in its share of the front half: its top then faces the camera and catches
                            # light, the back stays flat under the palate's shadow) and the whole tongue rises a little
                            fz = Xn @ self.out; q0, q1 = np.percentile(fz, 50), fz.max()
                            sh = np.clip((fz - q0) / max(q1 - q0, 1e-9), 0, 1)
                            top = np.clip((hh / max(float(hh.max()), 1e-9) - 0.3) / 0.4, 0, 1)
                            tl = np.clip((q1 - fz) / max(q1 - fz.min(), 1e-9), 0, 1)  # 1 at the back, 0 at the tip
                            d = d + (TONGUE_DOME[1] * tl - TONGUE_DOME[0] * sh ** 2 * top)[:, None] * self.up[None]
                    res[name] = d * self.amount.get(name, 1.0)
                    continue
                if (SMILE_FIT and kind == "teeth" and name.startswith("mouthSmile")) or (JAW_FIT and kind == "teeth" and name == "jawOpen"):  # (r36) the fitted smile's jaw share
                    # moves the lower row RIGIDLY (its own coefficients on the teeth bent the rows: f36a), the upper row stays
                    Rr, a, b = self._rigid_lower_row(G["dV"][name])
                    lw = np.zeros(len(Xn)) if lower is None else np.asarray(lower, float)
                    res[name] = ((Xn - a) @ Rr.T + b - Xn) * lw[:, None] * self.amount.get(name, 1.0)
                    continue
                res[name] = self._piece_onto(Xn, G["dV"][name], kind, lower) * self.amount.get(name, 1.0)
                continue
            if self.gnm_mouth:  # what isn't near the skin's own vertices is GNM's mouth sock: its own offsets
                rigid = self._piece_onto(Xn, G["dV"][name], "sock") if kind == "skin" else np.zeros_like(Xn)
            elif name in JAW_SHAPES:
                Rr, a, b = self._rigid_jaw(dW)
                rigid = (Xn - a) @ Rr.T + b - Xn  # the jaw's own move, for what isn't skin (bag, teeth, tongue)
            else:  # (the jaw line hardly moves: its fit is noise, and moved the teeth in a smile)
                rigid = np.zeros_like(Xn)
            if kind == "skin":
                D, near = self._onto(Xm, dW)
                if index is not None:  # (one mesh, own quads) GNM's vertices move as GNM moves them: no projection
                    # (the lips' inner rolls and the mouth sock are its own; nearest-six mixed the parted lips)
                    D = self._indexed(D, index, G["dV"][name])
                    near = np.where(np.asarray(index) >= 0, 1.0, near)
                    mt = self._gnm.get("meet")
                    if mt is not None and mt[0] == Xm.shape:  # the neutral's lips were closed past GNM's own (its
                        # basis leaves them parted): a shape that parts them takes that close back in proportion
                        # (left in, jawOpen tore the inner rolls into shards against the closed contact ring)
                        D = D - self._meet_share(D, mt[1], index) * mt[1]
                # (headbody, 2026-10-12) the jaw's rigid move in full is for GNM's own TEETH and TONGUE only: on the skin
                # it gave every vertex away from the face (the whole body under the neck) jawOpen's 26 mm, and
                # rigid_near then weighted all of it 1.0 to the Head bone (the chest turned with the head)
                d = D * near[:, None] + rigid * ((1 - near) * (1.0 if self.gnm_mouth and kind != "skin" else wj))[:, None]
                if index is not None and kind == "skin":  # (one mesh) the body under the stitch: GNM's shapes fade to
                    # 0 at the seam ring, so nothing below it moves
                    d[np.asarray(index) < 0] = 0.0
                fam = family(name)
                if index is not None and kind == "skin" and fam == "mouth" and SOCK_SMOOTH and self.gnm_mouth:
                    d = self._smooth_sock(Xn, d, index)
                if index is not None and kind == "skin" and name.startswith("mouthSmile") and SMILE_EDGE_LIFT[0] and not SMILE_FIT:
                    d = self._smile_edge(Xn, d, index, "Left" if name.endswith("Left") else "Right")
                if index is not None and kind == "skin" and fam == "mouth" and ROLL_TUCK:
                    ins = [] if not (ROLL_TUCK_COMBINED and name in CORRECTIVES) else [
                        j for i in CORRECTIVES[name][1:] for j in ((i,) if i in res else (i + "Left", i + "Right"))]
                    if ins and all(i in res for i in ins):  # (r33) a corrective's rolls tucked against the COMBINED
                        # pose (its inputs at full + itself), not its own offsets alone: jawOpen's tuck is for its lifted
                        # lip, so a corrective that lowers the vermilion left the roll hanging below it (a dark dash)
                        base = sum(res[i] for i in ins)
                        d = self._rolls_tucked(Xn, base + d, index) - base
                    else:
                        d = self._rolls_tucked(Xn, d, index)
                fit_free = bool(SMILE_FIT) and not SMILE_FIT_MASK and name.startswith(("mouthSmile", "cheekSquint"))
                if fit_free:  # (r37) the fitted smile's halves as fitted (see SMILE_FIT_MASK), (r38) faded at the family
                    if SMILE_FIT_FADE and fam == "mouth":  # border only (SMILE_FIT_FADE; cheekSquint is "mid": no family mask)
                        if SMILE_FIT_CARRY:
                            carry[name.replace("mouthSmile", "cheekSquint")] = d * (1 - fit_mouth)[:, None]
                        d *= fit_mouth[:, None]
                elif fam == "mouth":  # (the smile's cheek "terraces" in expr_r6 were Blender's split-normal seams, not
                    # this mask: blender_game imports with merge_vertices now; the lids stay cheekSquint's)
                    d *= mouth_mask[:, None]
                elif fam == "eye":
                    d *= eye_mask[:, None]
                if name not in JAW_SHAPES and self.eyes:  # (GNM's expression prototypes behind the smile and
                    # cheekSquint moved the back of the head and the neck 0.4 mm: test_gnm_head_shapes) faded out past
                    # MOUTH_REACH from the mouth and EYE_REACH from between the eyes
                    rr = np.linalg.norm(Xm - self.M, axis=1)
                    ec = np.mean([np.asarray(e["c"], float) for e in self.eyes.values()], 0)
                    re = np.linalg.norm(Xm - ec, axis=1)
                    keep = np.maximum(1 - _ss((rr - MOUTH_REACH[0]) / (MOUTH_REACH[1] - MOUTH_REACH[0])),
                                      1 - _ss((re - EYE_REACH[0]) / (EYE_REACH[1] - EYE_REACH[0])))
                    d *= keep[:, None]
                if kind == "skin" and name.startswith("mouthSmile") and SMILE_FOLD and not SMILE_FIT:
                    d = d + self._smile_fold(Xn, nrm, "Left" if name.endswith("Left") else "Right")
                elif kind == "skin" and name.startswith("mouthSmile") and SMILE_FOLD and SMILE_FIT and SMILE_FIT_FOLD:
                    d = d + SMILE_FIT_FOLD * self._smile_fold(Xn, nrm, "Left" if name.endswith("Left") else "Right", corner=False)
                if name.startswith("eyeBlink") and LID_SEAL and self.lid_seal["amount"] > 0:
                    # (by index too: GNM's own blink left Tess's lids 2.75 mm apart mid-eye and ~2 mm at the corners,
                    # measured by rays from the front on the export (assembly/eyegap.py): a pale sliver under the
                    # lashes and red slits at the corners in every skin round)
                    for sd in self.eyes:
                        if name.endswith(sd):
                            d = self._lid_seal(sd, Xn, d)
                # nothing may sink into an eyeball (a blink's lid slides over it), but no deeper than where the
                # neutral already has it: pushed out to a fixed clearance, the lower lids (a hair inside it in the
                # neutral) took the same 3-6 mm offset in EVERY shape, and A2F's sums dragged them 10-27 mm
                for ev in self.eyes.values():
                    r0 = np.linalg.norm(Xn - ev["c"], axis=1)
                    q = Xn + d - ev["c"]
                    r = np.linalg.norm(q, axis=1)
                    lim = np.minimum(ev["r"] + 0.0006, r0)
                    inside = (r < lim) & (r0 < 1.6 * ev["r"])
                    d[inside] += q[inside] * ((lim[inside] - r[inside]) / np.maximum(r[inside], 1e-9))[:, None]
                    if ev.get("cornea"):  # GNM's corneal bulge: the closing UPPER lid rides over it, as over the ball
                        cc, rc = ev["cornea"]
                        r0c = np.linalg.norm(Xn - cc, axis=1)
                        qc = Xn + d - cc
                        rr = np.linalg.norm(qc, axis=1)
                        limc = np.minimum(rc + 0.0001, r0c)
                        # (the upper lid only: it does the closing. Pushing the lower lid's few vertices that reach
                        # the cap made the skin under the eye jagged on a decimated face: unevenness 0.14 > 0.12)
                        ins = (rr < limc) & (r0c < 1.4 * rc) & ((Xn - ev["c"]) @ self.up > -0.15 * ev["r"])
                        d[ins] += qc[ins] * ((limc[ins] - rr[ins]) / np.maximum(rr[ins], 1e-9))[:, None]
                        # (pushed off the cornea a vertex may have slid a hair back into the ball: the ball's limit again)
                        q = Xn + d - ev["c"]
                        r = np.linalg.norm(q, axis=1)
                        inside = (r < lim) & (r0 < 1.6 * ev["r"])
                        d[inside] += q[inside] * ((lim[inside] - r[inside]) / np.maximum(r[inside], 1e-9))[:, None]
            else:
                d = rigid * wj[:, None]
            if name == "tongueOut" and kind == "tongue" and self.tongue is not None:
                tc, ts = self.tongue.params["c"], self.tongue.params["size"]
                along = np.clip(((Xm - tc) @ self.out + ts[1]) / (2 * ts[1]), 0, 1)
                reach = ((self.M - tc) @ self.out) - ts[1] + 0.3 * self.width
                d = d + (_ss(along) * reach)[:, None] * self.out - (along ** 2 * 0.2 * reach)[:, None] * self.up
            res[name] = d * self.amount.get(name, 1.0)
        for name, d in carry.items():  # (r39) SMILE_FIT_CARRY
            if name in res:
                res[name] = res[name] + d * self.amount.get(name, 1.0)
        pt = self._gnm.get("parted")
        if kind == "skin" and index is not None and "mouthClose" in res and pt is not None and pt[0] == Xm.shape:
            res["mouthClose"] = res["mouthClose"] + pt[1] * self.amount.get("mouthClose", 1.0)  # (r44) NEUTRAL_PARTED
        return res


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


def face_of(spec: dict) -> Face:
    """The face shapes' anatomy for a model: a GNM head (base.head.source "gnm") or the face kit."""
    hd = ((spec.get("base") or {}).get("head") or {})
    if hd and hd.get("source", "gnm") == "gnm" and not any(
            k.get("type") == "face" for k in (spec.get("kits") or {}).values()):
        return GnmFace(spec)
    return Face(spec)
