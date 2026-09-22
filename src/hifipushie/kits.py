"""Kits: parametric body parts that expand into ordinary joints, bones and blobs.

A kit is stored under spec["kits"][name] = {"type": "hand" | "face", ...}. It expands before mirroring,
so a kit named "hand.L" generates ".L" elements (hand_f2_1.L, hand_palm.L, ...) and the right side
follows automatically; a centre kit ("face") generates centre elements plus ".L" pairs (eyes, brows).
Generated names start with the kit's base name ("hand", "face") and can be used anywhere a joint,
bone or blob name can: measure along them, hang blobs on them, focus on them.

Every numeric parameter defaults to something proportioned to the anchor joint's radius, so
{"type": "hand", "wrist": "wrist.L"} alone makes a plausible hand.

hand: {"wrist": joint, "dir": [x,y,z] fingers point (default: along the bone ending at the wrist),
       "palm": [x,y,z] the palm faces (default -X, toward the body for a left hand),
       "size": [length, width, thickness] of the palm, "fingers": count, "length": longest finger,
       "lengths": per-finger ratios (index first), "r": finger radius at the knuckle, "taper": tip/base,
       "spread": fan angle across all fingers (deg), "curl": bend at each finger joint (deg, or a list
       per finger), "thumb": false | {"length", "r", "angle": deg out from the palm, "curl"}, "blend"}

face: {"head": joint (anchor); feature positions "at" are offsets from it in world axes (left side for
       paired features), seated onto the head's actual surface along "dir" (default [0,-1,0], i.e. seen
       from the front). The head is everything except kits, so seating follows edits to the skull.
       Paired features: eyes, brows, cheeks. Centre: nose, mouth, chin. Omit a feature to leave it out.
  eyes:   {"at", "r", "sink": fraction of r the ball's centre sits below the skin (0.25),
           "upper"/"lower": how much each lid covers, 0..1 (0.35 / 0.15; both 0 = no lids),
           "width": eye-corner half-width / r (0.85), "lid": thickness, "tilt": deg (outer corner up),
           "socket": radius ratio of a carved socket (0 = none), "dir"}
  brows:  {"at", "size": [half-length, depth, half-height], "angle": deg (outer end up), "proud", "dir"}
  cheeks: {"at", "size", "proud", "dir"}          chin: {"at", "size", "proud"}
  nose:   {"at": root on the surface, "length", "droop": deg below "dir", "r": tip radius,
           "bridge": root radius, "wings": nostril-wing size ratio (0 = none), "nostrils": bool}
  mouth:  {"at": centre, "width", "smile": corner lift (m, negative = frown), "open": gap (m),
           "upper"/"lower": lip radius, "pout": how far lips stand out (fraction of radius, 0.35),
           "depth": of the cavity behind an open mouth}
  "blend": default blend for face parts. Layers: skin features 0, lids and lips 1, eyeballs 2.
"""

from __future__ import annotations

import copy
import math

import numpy as np

from .spec import SpecError

TYPES = ("hand", "face")


class KitError(SpecError):
    pass


def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    if n < 1e-9:
        raise KitError(f"zero-length direction {v.tolist()}")
    return v / n


def _euler(R: np.ndarray) -> list[float]:
    """Inverse of spec.euler_matrix (R = Rz @ Ry @ Rx), in degrees."""
    ry = math.asin(max(-1.0, min(1.0, -R[2, 0])))
    rx = math.atan2(R[2, 1], R[2, 2])
    rz = math.atan2(R[1, 0], R[0, 0])
    return [round(math.degrees(a), 3) for a in (rx, ry, rz)]


def _rot_about(axis: np.ndarray, deg: float) -> np.ndarray:
    a = _unit(axis)
    t = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def _r(v) -> list[float]:
    return [round(float(x), 5) for x in v]


def _base(name: str) -> tuple[str, str]:
    return (name[:-2], ".L") if name.endswith(".L") else (name, "")


class _Out:
    """Collects generated elements and refuses to shadow anything already in the spec."""

    def __init__(self, spec: dict, kit: str):
        self.spec, self.kit = spec, kit
        self.joints, self.bones, self.blobs = {}, {}, {}

    def _put(self, kind: str, store: dict, name: str, value: dict):
        if name in self.spec.get(kind, {}) or name in store:
            raise KitError(f"kit {self.kit!r}: generated {kind[:-1]} {name!r} already exists")
        store[name] = value

    def joint(self, name, pos, r):
        self._put("joints", self.joints, name, {"pos": _r(pos), "r": round(float(r), 5)})

    def bone(self, name, a, b, **kw):
        self._put("bones", self.bones, name, {"a": a, "b": b, **kw})

    def blob(self, name, **kw):
        self._put("blobs", self.blobs, name, kw)


def expand(spec: dict) -> dict:
    """Return a copy of spec with every kit replaced by the elements it generates."""
    kits = spec.get("kits") or {}
    if not kits:
        return spec
    out = copy.deepcopy(spec)
    out.pop("kits")
    base = copy.deepcopy(out)  # the body without kits: what face features are seated on
    for name, kit in kits.items():
        o = _Out(out, name)
        match kit.get("type"):
            case "hand":
                _hand(out, name, kit, o)
            case "face":
                _face(base, name, kit, o)
            case other:
                raise KitError(f"kit {name!r}: unknown type {other!r} (have {', '.join(TYPES)})")
        for kind in ("joints", "bones", "blobs"):
            out.setdefault(kind, {}).update(getattr(o, kind))
    return out


def _joint(spec: dict, kit: str, name) -> tuple[np.ndarray, float]:
    j = spec.get("joints", {}).get(name)
    if j is None:
        raise KitError(f"kit {kit!r}: unknown joint {name!r}")
    return np.array(j["pos"], float), float(j.get("r", 0.05))


# ---------------------------------------------------------------- hand

FINGER_RATIOS = {1: [1.0], 2: [1.0, 0.9], 3: [0.95, 1.0, 0.88], 4: [0.9, 1.0, 0.95, 0.78],
                 5: [0.88, 1.0, 0.96, 0.85, 0.72]}
SEGMENTS = (0.45, 0.31, 0.24)  # proximal, middle, distal share of finger length


def _hand(spec: dict, name: str, k: dict, o: _Out):
    base, sfx = _base(name)
    wrist = k.get("wrist") or f"wrist{sfx}"
    W, rw = _joint(spec, name, wrist)
    if "dir" in k:
        a = _unit(k["dir"])
    else:
        into = [b for b in spec.get("bones", {}).values() if b.get("b") == wrist]
        if not into:
            raise KitError(f"kit {name!r}: give \"dir\" (no bone ends at {wrist!r})")
        a = _unit(W - np.array(spec["joints"][into[0]["a"]]["pos"], float))
    n = np.asarray(k.get("palm", [-1.0, 0.0, 0.0]), float)
    n = _unit(n - a * (n @ a))  # palm normal, square to the fingers
    t = np.cross(n, a)          # across the palm, toward the thumb

    L, Wd, T = k.get("size") or [2.3 * rw, 2.3 * rw, 1.2 * rw]
    nf = int(k.get("fingers", 4))
    flen = float(k.get("length", 2.5 * rw))
    ratios = k.get("lengths") or FINGER_RATIOS.get(nf) or [1.0] * nf
    if len(ratios) != nf:
        raise KitError(f"kit {name!r}: {nf} fingers but {len(ratios)} lengths")
    fr = float(k.get("r", min(0.4 * rw, 0.8 * Wd / max(nf, 1) / 2.6)))
    taper = float(k.get("taper", 0.75))
    spread = float(k.get("spread", 12.0))
    curl = k.get("curl", 10.0)
    curls = curl if isinstance(curl, list) else [curl] * nf
    kb = float(k.get("blend", 0.5 * fr))

    R = np.stack([t, a, -n], 1)  # palm blob axes: across, along, through
    o.blob(f"{base}_palm{sfx}", at=_r(W + a * L * 0.5), size=_r([Wd / 2, L / 2, T / 2]), rot=_euler(R),
           blend=round(0.6 * T, 5))

    for i in range(nf):
        frac = 0.5 if nf == 1 else i / (nf - 1)       # 0 = index (thumb side), 1 = little finger
        across = (0.5 - frac) * Wd * 0.72
        d = _rot_about(n, spread * (0.5 - frac)) @ a  # fan out within the palm plane
        _digit(o, f"{base}_f{i + 1}", sfx, W + a * L * 0.82 + t * across, d, n, flen * float(ratios[i]),
               SEGMENTS, float(curls[i]) * len(SEGMENTS), fr, fr * taper, kb)

    th = k.get("thumb", {})
    if th is not False:
        th = th or {}
        tlen = float(th.get("length", 0.75 * flen))
        tr = float(th.get("r", fr * 1.1))
        ang = float(th.get("angle", 35.0))
        d = _unit(_rot_about(n, ang) @ a + 0.35 * n)  # out to the thumb side and a little palm-ward
        _digit(o, f"{base}_th", sfx, W + a * L * 0.2 + t * Wd * 0.38, d, n, tlen, (0.4, 0.33, 0.27),
               float(th.get("curl", 10.0)) * 2, tr * 1.25, tr * taper, kb)


def _digit(o: _Out, prefix: str, sfx: str, p: np.ndarray, d: np.ndarray, palm: np.ndarray, length: float,
           shares, bend: float, r0: float, r1: float, blend: float, sub: int = 3):
    """A finger as a smooth arc curling toward the palm by `bend` degrees in total, radius tapering
    linearly with length. Built from short segments joined by hard min in one group, so there are no
    blend bulges and no visible kinks. Joints prefix_0..prefix_N mark the knuckles; prefix_S_m are the
    in-between points."""
    axis = np.cross(d, palm)
    step_turn = bend / (len(shares) * sub)
    along = 0.0
    names = [f"{prefix}_0{sfx}"]
    o.joint(names[0], p, r0)
    for s, share in enumerate(shares):
        for m in range(1, sub + 1):
            d = _rot_about(axis, step_turn) @ d  # toward the palm
            p = p + d * length * share / sub
            along += share / sub
            names.append(f"{prefix}_{s + 1}{sfx}" if m == sub else f"{prefix}_{s}_{m}{sfx}")
            o.joint(names[-1], p, r0 + (r1 - r0) * along / sum(shares))
            o.bone(f"{prefix}_{s + 1}{'abc'[m - 1] if sub <= 3 else m}{sfx}", names[-2], names[-1],
                   blend=round(blend, 5), group=f"{prefix}{sfx}")


# ---------------------------------------------------------------- face

class _Surface:
    """Raycasts against a fixed set of primitives (the head without the face kit)."""

    def __init__(self, spec: dict):
        from .spec import compile_prims
        self.prims = compile_prims(spec)

    def seat(self, point: np.ndarray, facing: np.ndarray, what: str) -> tuple[np.ndarray, np.ndarray]:
        """First surface point hit coming in along -facing toward `point`, and the outward normal there."""
        from . import sdf
        span = 0.6
        ts = np.linspace(0.0, 2 * span, 600)
        ray = point + facing * span - ts[:, None] * facing
        f = sdf.field_at(self.prims, ray)
        hit = np.flatnonzero(f < 0)
        if not len(hit) or hit[0] == 0:
            raise KitError(f"{what}: no surface along {_r(-facing)} through {_r(point)}")
        lo, hi = ts[hit[0] - 1], ts[hit[0]]
        for _ in range(30):
            mid = (lo + hi) / 2
            if sdf.field_at(self.prims, (point + facing * span - mid * facing)[None])[0] < 0:
                hi = mid
            else:
                lo = mid
        s = point + facing * span - hi * facing
        g = sdf.gradient(self.prims, s[None], 1e-4)[0]
        return s, _unit(g)


def _frame(facing: np.ndarray, spin: float = 0.0) -> np.ndarray:
    """Columns: local x (the creature's left, +X), y (into the head), z (up); spun about y by -spin deg,
    so a positive spin raises the local +x end."""
    y = -facing
    up = np.array([0.0, 0.0, 1.0])
    z = up - y * (up @ y)
    if np.linalg.norm(z) < 1e-6:
        z = np.array([0.0, 1.0, 0.0]) - y * y[1]
    z = _unit(z)
    x = np.cross(y, z)
    return np.stack([x, y, z], 1) @ _rot_about([0, 1, 0], -spin)


def _face(base: dict, name: str, k: dict, o: _Out):
    fb, _ = _base(name)
    H, R = _joint(base, name, k.get("head", "head"))
    kb = float(k.get("blend", 0.12 * R))
    surf = _Surface(base)

    def seat(feat: dict, default_at, what, surface=surf):
        facing = _unit(feat.get("dir", [0, -1, 0]))
        return (*surface.seat(H + np.asarray(feat.get("at", default_at), float), facing, what), facing)

    def blob_on(bname, feat, default_at, default_size, what, **kw):
        size = np.asarray(feat.get("size", default_size), float)
        s, _, facing = seat(feat, default_at, what)
        proud = float(feat.get("proud", 0.5))
        c = s - facing * (1 - proud) * size[1]
        o.blob(bname, at=_r(c), size=_r(size), rot=_euler(_frame(facing, float(feat.get("angle", 0)))),
               blend=round(float(feat.get("blend", kb)), 5), **kw)

    # skin features first (layer 0); they become part of the surface eyes and lips sit on
    if (f := k.get("cheeks")) is not None:
        blob_on(f"{fb}_cheek.L", f, [0.55 * R, 0, -0.35 * R], [0.3 * R, 0.25 * R, 0.25 * R], "cheeks")
    if (f := k.get("chin")) is not None:
        blob_on(f"{fb}_chin", f, [0, 0, -0.75 * R], [0.3 * R, 0.2 * R, 0.2 * R], "chin")
    if (f := k.get("brows")) is not None:
        blob_on(f"{fb}_brow.L", f, [0.35 * R, 0, 0.4 * R], [0.32 * R, 0.14 * R, 0.1 * R], "brows")
    skin = copy.deepcopy(base)
    skin["blobs"] = {**skin.get("blobs", {}), **o.blobs}
    surf2 = _Surface(skin)

    if (f := k.get("nose")) is not None:
        s, _, facing = seat(f, [0, 0, 0.05 * R], "nose")
        F = _frame(facing)
        br = float(f.get("bridge", 0.14 * R))
        tr = float(f.get("r", 0.2 * R))
        length = float(f.get("length", 0.5 * R))
        droop = float(f.get("droop", 25.0))
        d = _rot_about(F[:, 0], droop) @ facing
        root = s - facing * br * 0.6
        tip = root + d * length
        o.joint(f"{fb}_nose_root", root, br)
        o.joint(f"{fb}_nose_tip", tip, tr * 0.8)
        o.bone(f"{fb}_nose", f"{fb}_nose_root", f"{fb}_nose_tip", blend=round(kb, 5))
        o.blob(f"{fb}_nose_ball", at=f"{fb}_nose_tip", size=_r([tr, tr, tr * 0.9]), blend=round(0.5 * tr, 5))
        down, side = -F[:, 2], F[:, 0]
        if (w := float(f.get("wings", 0.55))) > 0:
            o.blob(f"{fb}_nose_wing.L", at=f"{fb}_nose_tip",
                   offset=_r(side * tr * 0.85 + down * tr * 0.35 - d * tr * 0.55),
                   size=_r([w * tr * 0.7] * 3), blend=round(0.5 * tr, 5))
        if f.get("nostrils", True):
            o.blob(f"{fb}_nostril.L", at=f"{fb}_nose_tip",
                   offset=_r(side * tr * 0.42 + down * tr * 0.8 - d * tr * 0.25),
                   size=_r([0.2 * tr, 0.28 * tr, 0.16 * tr]), op="subtract", blend=round(0.12 * tr, 5))

    if (f := k.get("mouth")) is not None:
        _mouth(f, H, R, surf, o, fb)

    if (f := k.get("eyes")) is not None:
        r = float(f.get("r", 0.2 * R))
        s, _, facing = seat(f, [0.4 * R, 0, 0.15 * R], "eyes", surf2)
        c = s - facing * r * float(f.get("sink", 0.25))
        F = _frame(facing, float(f.get("tilt", 0.0)))
        o.blob(f"{fb}_eye.L", at=_r(c), size=_r([r] * 3), layer=2, blend=round(0.3 * r, 5))
        if (sock := float(f.get("socket", 0.0))) > 0:
            o.blob(f"{fb}_socket.L", at=_r(c), size=_r([sock * r] * 3), op="subtract",
                   blend=round(0.25 * r, 5))
        upper, lower = float(f.get("upper", 0.35)), float(f.get("lower", 0.15))
        if upper > 0 or lower > 0:
            o.blob(f"{fb}_lids.L", shape="lids", at=_r(c), r=round(r, 5),
                   thickness=round(float(f.get("lid", 0.25 * r)), 5), upper=upper, lower=lower,
                   width=float(f.get("width", 0.85)), rot=_euler(F), layer=1, blend=round(0.35 * r, 5))


def _mouth(f: dict, H: np.ndarray, R: float, surf: _Surface, o: _Out, fb: str):
    """Lips as two soft masses blended broadly into the face, with a groove where they meet.

    They follow one smooth arc: the skin depth is sampled across the mouth (on the head without cheeks,
    so cheek bulges don't print through) and fitted with depth = a + b u^2 (u = 0 middle, 1 corner).
    Each half-lip is a chain of short segments, so direction changes are tiny and joints don't bulge."""
    width = float(f.get("width", 0.9 * R))
    smile = float(f.get("smile", 0.0))
    gap = float(f.get("open", 0.0))
    ru, rl = float(f.get("upper", 0.07 * R)), float(f.get("lower", 0.08 * R))
    pout = float(f.get("pout", 0.35))
    depth = float(f.get("depth", 0.25 * R))
    at0 = np.asarray(f.get("at", [0, 0, -0.45 * R]), float)
    facing = _unit(f.get("dir", [0, -1, 0]))
    F = _frame(facing)
    side, up = F[:, 0], F[:, 2]

    def line(u):  # the lips' meeting line, in front of the anchor, before seating
        return H + at0 + side * u * width / 2 + up * smile * u * u

    us = np.linspace(0.0, 1.0, 7)
    depths = np.array([(surf.seat(line(u), facing, "mouth")[0] - line(u)) @ facing for u in us])
    a, b = np.linalg.lstsq(np.stack([np.ones_like(us), us * us], 1), depths, rcond=None)[0]

    def on_skin(u, dz, out):  # a point on the fitted arc, `out` in front of the skin
        return line(u) + up * dz + facing * (a + b * u * u + out)

    corner = f"{fb}_mouth_corner.L"
    o.joint(corner, on_skin(1.0, 0.0, 0.0), 0.35 * min(ru, rl))
    for lip, r, sgn in (("upper", ru, 1), ("lower", rl, -1)):
        names = []
        for i, u in enumerate(us[:-1]):
            rr = r * (1 - 0.55 * u * u)
            dz = sgn * (gap / 2 + 0.8 * r) * (1 - u * u) ** 0.7
            names.append(f"{fb}_mouth_{lip}_{i}" + (".L" if i else ""))
            o.joint(names[-1], on_skin(u, dz, -rr * (1 - pout)), rr)
        names.append(corner)
        for i in range(len(names) - 1):
            o.bone(f"{fb}_mouth_{lip}_{i + 1}.L", names[i], names[i + 1], blend=round(0.8 * r, 5), layer=1,
                   group=f"{fb}_mouth_{lip}")

    # the parting line: a thin groove along the seam, fading out before the corners
    rg = 0.3 * min(ru, rl) + gap / 2
    names = []
    for i, u in enumerate(us[:-1]):
        names.append(f"{fb}_mouth_line_{i}" + (".L" if i else ""))
        front = pout * min(ru, rl)
        o.joint(names[-1], on_skin(u, 0.0, front * (1 - u * u)), rg * (1 - 0.6 * u * u))
    for i in range(len(names) - 1):
        o.bone(f"{fb}_mouth_line_{i + 1}.L", names[i], names[i + 1], op="subtract", layer=1,
               blend=round(0.5 * rg, 5), group=f"{fb}_mouth_line")
    if gap > 0:
        o.blob(f"{fb}_mouth_cavity", at=_r(on_skin(0.0, 0.0, -depth * 0.5)),
               size=_r([width * 0.4, depth * 0.7, gap / 2]), op="subtract", layer=1,
               blend=round(0.5 * min(ru, rl), 5))
