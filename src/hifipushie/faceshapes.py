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

spec["face_shapes"] (optional, stripped from geometry): {"amount": {name: scale (1 = default, 0 = flat)},
  "jaw": {"pivot": joint | [x, y, z], "open": deg at jawOpen 1.0 (18), "depth": m below the parting line where the
  jaw stops (0.75 x head radius)}}
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
ALL = REQUIRED + RECOMMENDED
# viseme-like combinations for review sheets (oxidegen's presets are its own)
COMBOS = {"AA": {"jawOpen": 0.6, "mouthFunnel": 0.2}, "OO": {"mouthPucker": 0.8, "jawOpen": 0.2},
          "MBP": {"mouthPressLeft": 0.7, "mouthPressRight": 0.7, "mouthRollLower": 0.2, "mouthRollUpper": 0.2},
          "open+close": {"jawOpen": 1.0, "mouthClose": 1.0},
          "EE": {"mouthStretchLeft": 0.5, "mouthStretchRight": 0.5, "jawOpen": 0.25, "mouthSmileLeft": 0.3,
                 "mouthSmileRight": 0.3},
          "FV": {"mouthRollLower": 0.6, "mouthUpperUpLeft": 0.3, "mouthUpperUpRight": 0.3, "jawOpen": 0.1},
          "smile": {"mouthSmileLeft": 1.0, "mouthSmileRight": 1.0, "cheekPuff": 0.2, "browInnerUp": 0.2}}


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
        slit = prims[f"{fb}_mouth_slit"]
        self.slit_u = np.clip(((slit.params["P"] - self.M) @ self.side) / self.W2, 0, None)
        self.slit_h = np.asarray(slit.params["V"]["u1"], float)
        self.slit = 2 * float(self.slit_h[0])
        self.slit_part = slit.part
        bag = prims[f"{fb}_mouth_bag"]
        self.bag = np.asarray(bag.params["size"], float)
        self.thick = float(((self.M - bag.params["c"]) @ self.out) - self.bag[1])  # lip front to the bag's front
        self.parts_teeth = {p.part for n, p in prims.items() if n.startswith(f"{fb}_teeth_")}
        self.parts_tongue = {p.part for n, p in prims.items() if n == f"{fb}_tongue"}
        self.tongue = prims.get(f"{fb}_tongue")
        # the nose is bone: mouth shapes leave it where it is (a goblin's nose hangs over its upper lip)
        self.nose = [p for n, p in prims.items() if n.startswith(f"{fb}_nose") and p.op == "add"]
        jaw = opts.get("jaw") or {}
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

    def voxels(self) -> dict:
        """{part: voxel}: the export meshes the slit's part at least this fine, so the slit (2+ voxels across) and
        the lips' inner faces are real surfaces."""
        return {self.slit_part: round(self.slit / 2.2, 5)}

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
        lat = _bump(L["u"], self.slit_u[-1], self.slit_u[-1] + 0.12)
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
                      lower: np.ndarray | None = None) -> dict:
        """{shape: (n, 3) move} for one part's vertices: Xm where they were meshed (weights), Xn the neutral
        (geometry), nrm its vertex normals. kind: "skin" (a part with the face), "teeth" (`lower`: the vertices of
        the lower row), "tongue"."""
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
        still = np.ones(n)
        if self.nose and kind == "skin":
            from . import sdf
            still *= 1 - _bump(sdf.field_at(self.nose, Xm), 0.001, 0.25 * self.lip + 0.004)
        for ev in self.eyes.values():
            still *= _ss((np.linalg.norm(Xm - ev["c"], axis=1) - 1.01 * ev["r"]) / (0.05 * ev["r"]))
        jo = self._jaw_move(Xn, wj, self.open)
        # the lower lip's travel at jawOpen, per point (sampled on the parting line at the point's u): mouthClose
        # moves both lips half of it toward each other
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
            return sel[:, None] * (-out * 0.9 * lip_r + up * sense * 0.45 * lip_r)

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
                d = -0.5 * jo * ll[:, None] + 0.5 * delta * (lu * wjp)[:, None]
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
                hh = half(s)
                d = hh[:, None] * (lu[:, None] * (-up * 0.3 * self.ru) + ll[:, None] * (up * 0.3 * self.rl)
                                   - lips[:, None] * out * 0.03 * w + lips[:, None] * side * sg * 0.02 * w)
            elif name.startswith("mouthLowerDown"):
                d = (half(s) * ll)[:, None] * (-up * 0.1 * w + out * 0.02 * w)
            elif name.startswith("mouthUpperUp"):
                d = (half(s) * lu)[:, None] * (up * 0.1 * w + out * 0.02 * w)
            elif name.startswith("eyeBlink"):
                d = self._blink(s, Xm, Xn) if (kind == "skin" and s in self.eyes) else zero
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
            d = d * (self.amount.get(name, 1.0) * still)[:, None]
            res[name] = d
        return res

    def _blink(self, s: str, Xm: np.ndarray, Xn: np.ndarray) -> np.ndarray:
        """The upper lid turned down over the eyeball about the eye's own left-right axis (so it slides on the
        ball), the lower lid up a quarter of the way; the corners stay, the skin round the eye follows less."""
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
        ang = (upper * th_u - (1 - upper) * th_l) * lat * reach
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
    if face_shapes is True:
        return list(ALL)
    if isinstance(face_shapes, str):
        face_shapes = [face_shapes]
    names = list(face_shapes or [])
    bad = [n for n in names if n not in ALL]
    if bad:
        raise SpecError(f"face_shapes: unknown shape(s) {bad} (have the ARKit names {', '.join(ALL)})")
    return names


def apply(spec: dict, parts: dict, face_shapes, log: list) -> dict:
    """Close the neutral's mouth and give the moving parts their shapes, in place on the export's low-poly parts
    ({part: {"verts", "corner_vert", "normal", "tangent", ...}}, Blender axes). Each moving part gets
    p["shapes"] = {name: (delta (verts, 3), vertex normal before (verts, 3), after (verts, 3))}, in the order of
    `names`; normals and tangents per corner turn with the close. Returns {part: [names]}."""
    names = names_of(face_shapes)
    face = Face(spec)
    if "eyeBlinkLeft" in names and not face.eyes:
        log.append("face shapes: no lids on the face kit's eyes: eyeBlink shapes are flat")
    got = {}
    for pn, p in parts.items():
        base = pn.split("/")[-1].split("~")[0]
        kind = "teeth" if base in face.parts_teeth else "tongue" if base in face.parts_tongue else "skin"
        Xm = np.asarray(p["verts"], np.float64)
        if kind == "skin":
            if any(e.get("part") == base for e in face.eyes.values()):
                continue  # the eyeballs' own part: they don't move
            near = np.linalg.norm(Xm - face.M, axis=1) < 3 * face.width + 2 * face.R
            if not near.any():
                continue
        T = p["corner_vert"].reshape(-1, 3)
        Xn = Xm + (face.close(face.local(Xm)) if kind == "skin" else 0.0)
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
        D = face.displacements(Xm, Xn, n0, kind, names, lower)
        if not any(np.abs(d).max() > 1e-7 for d in D.values()):
            continue
        p["verts"] = Xn.astype(p["verts"].dtype)
        p["shapes"] = {nm: (d, n0, vertex_normals(Xn + d, T)) for nm, d in D.items()}
        got[pn] = list(D)
        moved = sum(int((np.linalg.norm(d, axis=1) > 1e-6).any()) for d in D.values())
        log.append(f"face shapes: {pn} ({kind}) {len(D)} targets ({moved} move it), max "
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
