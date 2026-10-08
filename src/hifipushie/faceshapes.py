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
CORRECTIVES = {"jawOpen_mouthClose": ("min", "jawOpen", "mouthClose")}
CLOSE_LOWER = 0.8  # jawOpen_mouthClose: the lower lip's share of closing the gap jawOpen makes
CLOSE_SEAL = 0.3  # mouthClose alone: how firmly the closed lips push forward (no vertical travel)


def playback(weights: dict) -> dict:
    """ARKit weights -> the weights to set on the export's morph targets (the correctives filled in)."""
    out = dict(weights)
    for name, (op, a, b) in CORRECTIVES.items():
        if op == "min":
            out[name] = min(float(weights.get(a, 0.0)), float(weights.get(b, 0.0)))
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
    return names + [c for c, (_, *ins) in CORRECTIVES.items() if all(i in names for i in ins)]


def apply(spec: dict, parts: dict, face_shapes, log: list) -> dict:
    """Close the neutral's mouth and give the moving parts their shapes, in place on the export's low-poly parts
    ({part: {"verts", "corner_vert", "normal", "tangent", ...}}, Blender axes). Each moving part gets
    p["shapes"] = {name: (delta (verts, 3), vertex normal before (verts, 3), after (verts, 3))}, in the order of
    `names`; normals and tangents per corner turn with the close. Returns {part: [names]}."""
    names = names_of(face_shapes)
    face = face_of(spec)
    if "eyeBlinkLeft" in names and not face.eyes:
        log.append("face shapes: no lids on the face kit's eyes: eyeBlink shapes are flat")
    got = {}
    for pn, p in parts.items():
        base = pn.split("/")[-1].split("~")[0]
        kind = "teeth" if base in face.parts_teeth else "tongue" if base in face.parts_tongue else "skin"
        if any(e.get("part") == base for e in face.eyes.values()):
            kind = "eyes"  # the eyeballs' own part: only the eyeLook shapes turn them
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
        if kind == "skin" and base == face.slit_part and idx is None:
            Xn = Xn + face.seal(Xm, Xn, T)
        n0m, n0 = vertex_normals(Xm, T), vertex_normals(Xn, T)
        if kind == "skin":  # the close turns the corners' normals and tangents with it
            cv = p["corner_vert"]
            p["normal"] = turn(np.asarray(p["normal"], np.float64), n0m[cv], n0[cv]).astype(p["normal"].dtype)
            p["tangent"] = turn(np.asarray(p["tangent"], np.float64), n0m[cv], n0[cv]).astype(p["tangent"].dtype)
        lower = None
        if kind == "teeth":  # each connected piece whose middle is under the parting line is the lower row
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
            _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (len(Xm),) * 2),
                                          directed=False)
            h0 = face.local(Xm)["h0"]
            mid = np.bincount(lab, h0) / np.maximum(np.bincount(lab), 1)
            lower = mid[lab] < 0
        D = face.displacements(Xm, Xn, n0, kind, names, lower, idx)
        if not any(np.abs(d).max() > 1e-7 for d in D.values()):
            continue
        p["verts"] = Xn.astype(p["verts"].dtype)
        p["shapes"] = {nm: (d, n0, vertex_normals(Xn + d, T)) for nm, d in D.items()}
        got[pn] = list(D)
        moved = sum(int((np.linalg.norm(d, axis=1) > 1e-6).any()) for d in D.values())
        log.append(f"face shapes: {pn} ({kind}) {len(D)} targets ({moved} move it), max "
                   f"{max(np.linalg.norm(d, axis=1).max() for d in D.values()) * 1000:.1f} mm")
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
JAW_SHAPES = ("jawOpen", "jawForward", "jawLeft", "jawRight", "tongueOut")
HOLD = 0.5   # the weight of holding a landmark a shape doesn't move
LID_SEAL = True   # blinks: both lids' margins brought onto one smooth line on the low poly (GnmFace._lid_seal)
LID_OVER = 0.0003  # m the upper lid's margin goes past that line
LID_BAND = 0.0015  # m either side of the line squeezed onto each lid's own side
LID_REACH = (0.009, 0.004)  # m from its margin (as posed) over which a lid's skin takes the seal: upper, lower
LID_EDGE = (0.0025, 0.0015)  # m from its lid's posed edge within which a vertex counts as margin: upper, lower
LID_PINCH = 3     # how hard that band is drawn to the line: linear (1) parked the margins ~0.5 mm either side of it, a 1.2 mm slit
GNM_OPEN = 14.0  # deg: jawOpen at 1.0, about the line through the ears' landmarks (0, 16)


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


def basemod_lip_ring() -> int:
    from . import base as basemod
    return basemod.LIP_RING
CORNER_CLOSE, LIP_CORNER = 1.0, 0.2  # (one mesh) the rings in front of the contact ring close at the corners
LIP_TAPER = 0.04  # share of the mouth's width over which the close tapers to nothing at each corner
LIP_HOLD, LIP_FADE = 2, 4  # rings past the contact ring that ride with it fully (the lip's front), then fade out over

class GnmFace(Face):
    """A grafted GNM head (base.py): its mouth from the landmarks (base.mouth_lips), its interior from
    base.head.interior (kits._interior), its shapes from GNM's expression basis carried onto the export."""

    def __init__(self, spec: dict):
        from . import base as basemod
        b = spec["base"]
        hd = b["head"]
        if not hd.get("interior"):
            raise SpecError("face_shapes on a GNM head needs a mouth that can open: base.head.interior (true, or "
                            "{\"teeth\": true, \"tongue\": true}) and base.head.mouth_gap >= 0.002 (the lips parted "
                            "while modelling; the export closes them)")
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
        e = specmod.expand_mirror(spec)
        prims = {p.name: p for p in specmod.compile_prims(spec)}
        head = basemod.head_of({"joints": e["joints"]}, b)
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
        self._mouth_parts(prims, "face")
        self.nose = []
        self.nose_bone = []
        self.eyes = {s: {"c": np.asarray(c, float), "r": float(head["eye_r"]), "ro": 1.3 * float(head["eye_r"]),
                         "part": b.get("eyes")} for s, c in zip(("Left", "Right"), head["eyes"])}
        self.brows, self.cheeks = {}, {}
        jaw = opts.get("jaw") or {}
        self.P = (np.asarray(specmod.resolve_point(e, jaw["pivot"]), float) if "pivot" in jaw
                  else 0.5 * (lm[0] + lm[16]))
        self.open = np.radians(float(jaw.get("open", GNM_OPEN)))
        self.depth = float(jaw.get("depth", 0.75 * self.R))
        self.lid_seal = lid_seal_options(opts.get("lid_seal"))
        self._gnm = {}

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

    def _solve(self, moves: dict, region: str, hold: float = HOLD) -> np.ndarray:
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
        cf = np.linalg.solve(Aw.T @ Aw + 1e-6 * np.eye(len(comps)), Aw.T @ (t * w))
        return np.tensordot(cf, B, 1)

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
        if name == "jawOpen":
            return self._jaw_moves(self.open), "mouth"
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
            # down the rest
            jo = self._jaw_moves(self.open)
            for i in LOWER_LIP:
                mv[i] = -CLOSE_LOWER * jo[i]
            for u, l in zip(UPPER_LIP, [59, 58, 57, 56, 55, 67, 66, 65]):
                mv[u] = (1 - CLOSE_LOWER) * jo[l]
            for i in JAW:
                mv[i] = np.zeros(3)
            return mv, "mouth"
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
            put(mv, [54], [0.08, 0.15, -0.05]), put(mv, [53, 55, 64], [0.04, 0.08, -0.03])
            return mv, "mouth"
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
        if name.startswith("mouthLowerDown"):
            put(mv, [55, 56, 65], [0, -0.09, 0.02]), put(mv, [57, 66], [0, -0.045, 0.01])
            return mv, "mouth"
        if name.startswith("mouthUpperUp"):
            put(mv, [52, 53, 63], [0, 0.09, 0.02]), put(mv, [51, 62], [0, 0.045, 0.01])
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
            ku, kl = (-0.35, -0.15) if name.startswith("eyeWide") else (0.1, 0.35)
            for up_i, lo_i in LEFT["lid_upper"]:
                u, lo = side([up_i])[0], side([lo_i])[0]
                gap = (X0[lo] - X0[u]) / self._setup()["wg"]
                mv[u] = ku * gap * np.array([0, 1.0, 0.0])
                mv[lo] = -kl * gap * np.array([0, 1.0, 0.0])
            return mv, "eyes"
        if name.startswith("cheekSquint"):
            return self._cheek_raise(s), None
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

    def _cheek_raise(self, s: str) -> np.ndarray:
        """cheekSquint: the cheek under the eye up (GNM's zygomatic and infraorbital regions, feathered)."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        k = "left" if s == "Left" else "right"
        w = np.clip(g["groups"][f"{k}_zygomatic_region"] + 0.7 * g["groups"][f"{k}_infraorbital_region"], 0, 1)
        w = self._feather(w)
        out = np.zeros_like(V)
        out[:, 1] = 0.06 * G["wg"] * w  # GNM frame: y up
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
        ends = _bump(np.abs(u), 0.5 * width, 0.62 * width) * amount  # (fades out past the corners)
        d = d.copy()
        for sel, cur, tgt, reach, sgn in ((zone & upper, lo_u, line - over, o["reach"][0], 1.0),
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
        hp = h0 + d @ up
        t = np.clip((hp - (ln - band)) / (2 * band), 0.0, 1.0)
        for sel, new in ((zone & upper & (hp < ln + band), ln - over + t ** LID_PINCH * (band + over)),
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
        if kind != "skin":
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
        D, a = self._onto(Xm, self._gnm["close"])
        D = D * a[:, None]
        if index is not None:  # (one mesh, own quads) GNM's own vertices take GNM's own offsets
            D = self._indexed(D, index, self._gnm["close_dV"])
            if LIPS_MEET:  # what the basis leaves between the lips closed on GNM's own contact ring
                M = self._lips_meet(Xm + D, index)
                self._gnm["meet"] = (Xm.shape, M)  # (a shape that parts the lips takes it back: displacements)
                D = D + M
                D = D + self._corners_meet(Xm + D, index)  # (kept by every shape: the commissure stays sealed)
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
            out["outer"] = {k: halves(k) for k in range(ring + 1, ring + LIP_HOLD + 2)}
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
        if not R["ok"]:
            return D
        from . import base as basemod
        ring = basemod.LIP_RING
        row = {int(v): i for i, v in enumerate(np.asarray(index, int)) if v >= 0}
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
            wk = 1 - (k - ring - 1) / (LIP_HOLD + 1)
            for P, s, Q, sq, verts in ((Pu, su, Pl, sl, u), (Pl, sl, Pu, su, l)):
                other = np.column_stack([np.interp(s, sq, Q[:, j]) for j in range(3)])
                edge = np.minimum(P[:, 0] - P[:, 0].min(), P[:, 0].max() - P[:, 0])
                wc = CORNER_CLOSE * wk * (1 - _ss(np.clip(edge / (LIP_CORNER * span), 0, 1)))
                for j, v in enumerate(verts):
                    D[row[v]] += wc[j] * 0.5 * (other[j] - P[j])
        return D

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
        D[own] = self._by_index(dV)[idx[own]]
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
                dVs.append(mv if region is None else self._solve(mv, region))
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
        for name in names:
            if family(name) == "look":  # (the eyeballs' part turns; the skin stays)
                res[name] = np.zeros_like(Xm)
                continue
            dW = G["dW"][name]
            if name in JAW_SHAPES:
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
                d = D * near[:, None] + rigid * ((1 - near) * wj)[:, None]
                fam = family(name)
                if fam == "mouth":
                    d *= mouth_mask[:, None]
                elif fam == "eye":
                    d *= eye_mask[:, None]
                if name.startswith("eyeBlink") and LID_SEAL and self.lid_seal["amount"] > 0 and index is None:
                    # (by index the lids are GNM's own, which close: the seal is for a decimated low poly's margins)
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
            else:
                d = rigid * wj[:, None]
            if name == "tongueOut" and kind == "tongue" and self.tongue is not None:
                tc, ts = self.tongue.params["c"], self.tongue.params["size"]
                along = np.clip(((Xm - tc) @ self.out + ts[1]) / (2 * ts[1]), 0, 1)
                reach = ((self.M - tc) @ self.out) - ts[1] + 0.3 * self.width
                d = d + (_ss(along) * reach)[:, None] * self.out - (along ** 2 * 0.2 * reach)[:, None] * self.up
            res[name] = d * self.amount.get(name, 1.0)
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
