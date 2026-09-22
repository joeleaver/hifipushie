"""Creature spec: a skeleton of joints and bones with SDF blobs hung on it.

Coordinates are Blender's: Z up, the creature faces -Y, and its left side is +X.
Anything named with a ".L" suffix is auto-mirrored to ".R" across X when
symmetry is on, so the stored spec only ever holds the centre line and the left side.

Spec shape (all lengths in metres):

    {
      "symmetry": true,
      "blend": 0.03,                        # default smooth-union radius
      "joints": {"hip.L": {"pos": [x, y, z], "r": 0.06}},
      "bones":  {"thigh.L": {"a": "hip.L", "b": "knee.L",
                             "r_a": null, "r_b": null,   # override joint radii
                             "flat": [1, 1],             # cross-section scale (width, height)
                             "blend": null, "op": "add", "layer": 0,
                             "group": null, "join": 0}},  # a group is joined first (smooth by
                                                          # "join", 0 = hard min), then blended in once
      "blobs":  {"haunch.L": {"at": "hip.L" | [x, y, z] | {"bone": "thigh.L", "t": 0.3},
                              "offset": [0, 0, 0], "size": [rx, ry, rz], "rot": [0, 0, 0],
                              "blend": null, "op": "add" | "subtract", "layer": 0}},
      "strokes": {"biceps.L": {"op": "clay", "path": [...], ...}}   # see strokes.py
    }

Elements are combined in layer order; within a layer adds come first, then subtracts, then modifiers
(strokes: they displace or plane whatever the layer has built so far).
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import numpy as np

KINDS = ("joints", "bones", "blobs", "kits", "strokes")


def empty_spec() -> dict:
    return {"symmetry": True, "blend": 0.03, "joints": {}, "bones": {}, "blobs": {}}


def mirror_name(name: str) -> str | None:
    return name[:-2] + ".R" if name.endswith(".L") else None


def _mname(name: str) -> str:
    return mirror_name(name) or name


def _mirror_vec(v):
    return [-v[0], v[1], v[2]]


def _mirror_rot(r):
    # Reflecting across X: S·R(rx,ry,rz)·S == R(rx,-ry,-rz) for XYZ euler.
    return [r[0], -r[1], -r[2]]


def expand_mirror(spec: dict) -> dict:
    """Return a copy of spec with kits and strokes expanded and every ".L" element mirrored to ".R"."""
    from . import kits, strokes
    spec = strokes.expand(kits.expand(spec))
    out = copy.deepcopy(spec)
    for kind in KINDS:
        out.setdefault(kind, {})
    if not spec.get("symmetry", True):
        return out

    for name, j in spec.get("joints", {}).items():
        if (m := mirror_name(name)) and m not in spec["joints"]:
            out["joints"][m] = {**copy.deepcopy(j), "pos": _mirror_vec(j["pos"])}

    for name, b in spec.get("bones", {}).items():
        m = mirror_name(name)
        if m and m not in spec["bones"]:
            out["bones"][m] = {**copy.deepcopy(b), "a": _mname(b["a"]), "b": _mname(b["b"])}
            if b.get("up"):
                out["bones"][m]["up"] = _mirror_vec(b["up"])
            if b.get("group"):
                out["bones"][m]["group"] = _mname(b["group"])

    for name, bl in spec.get("blobs", {}).items():
        m = mirror_name(name)
        if not m or m in spec["blobs"]:
            continue
        nb = copy.deepcopy(bl)
        at = bl.get("at")
        if isinstance(at, str):
            nb["at"] = _mname(at)
        elif isinstance(at, dict):
            nb["at"] = {**at, "bone": _mname(at["bone"])}
        elif at is not None:
            nb["at"] = _mirror_vec(at)
        if "offset" in bl:
            nb["offset"] = _mirror_vec(bl["offset"])
        if "rot" in bl:
            nb["rot"] = _mirror_rot(bl["rot"])
        for key in ("pts", "nrm"):  # sweeps (strokes)
            if key in bl:
                nb[key] = [_mirror_vec(v) for v in bl[key]]
        if bl.get("group"):
            nb["group"] = _mname(bl["group"])
        out["blobs"][m] = nb
    return out


def euler_matrix(deg) -> np.ndarray:
    rx, ry, rz = (math.radians(a) for a in deg)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def bone_frame(a: np.ndarray, b: np.ndarray, up=None) -> np.ndarray:
    """Rows are (width, axis, height) unit vectors for a bone from a to b. The height axis points as
    close to `up` as it can (default world Z, or -Y for near-vertical bones)."""
    axis = b - a
    axis = axis / np.linalg.norm(axis)
    ref = None if up is None else np.asarray(up, float)
    if ref is None or np.linalg.norm(np.cross(axis, ref)) < 1e-6 * np.linalg.norm(ref):
        ref = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([0.0, -1.0, 0.0])
    w = np.cross(axis, ref)
    w /= np.linalg.norm(w)
    h = np.cross(w, axis)
    return np.stack([w, axis, h])


@dataclass
class Prim:
    name: str
    kind: str  # "cone" | "ellipsoid" | "lids" | "box" | "displace" | "flatten"
    op: str  # "add" | "subtract" | "modify"
    blend: float
    layer: int
    lo: np.ndarray  # AABB
    hi: np.ndarray
    params: dict = field(default_factory=dict)
    reach: float | np.ndarray = 0.0  # how far past the AABB (per axis) it can still change the blended field
    inert: float = 0.0  # where its own value is at least this, it leaves the blended field unchanged
    group: str | None = None  # consecutive members are joined first (by `join`), then blended in once
    join: float = 0.0
    lip: float = 1.0  # modifiers: how much steeper than a distance field they can make the field


class SpecError(ValueError):
    pass


def resolve_point(spec: dict, at) -> np.ndarray:
    if isinstance(at, str):  # a joint, or a blob's centre (e.g. a kit feature like face_nose_wing.L)
        if at in spec["joints"]:
            return np.array(spec["joints"][at]["pos"], float)
        bl = spec.get("blobs", {}).get(at)
        if bl is None or bl.get("at") == at:
            raise SpecError(f"unknown joint or blob {at!r}")
        return resolve_point(spec, bl.get("at", [0, 0, 0])) + np.array(bl.get("offset", [0, 0, 0]), float)
    if isinstance(at, dict):
        bone = spec["bones"].get(at["bone"])
        if bone is None:
            raise SpecError(f"unknown bone {at['bone']!r}")
        a, b = (resolve_point(spec, bone[k]) for k in ("a", "b"))
        return a + (b - a) * float(at.get("t", 0.5))
    return np.array(at, float)


def compile_prims(spec: dict) -> list[Prim]:
    """Mirror, resolve and turn a spec into an ordered list of SDF primitives."""
    s = expand_mirror(spec)
    k_default = float(s.get("blend", 0.03))
    prims: list[Prim] = []

    for name, b in s["bones"].items():
        for end in ("a", "b"):
            if b[end] not in s["joints"]:
                raise SpecError(f"bone {name!r}: unknown joint {b[end]!r}")
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        if np.linalg.norm(bb - a) < 1e-6:
            raise SpecError(f"bone {name!r} has zero length")
        ra = float(b.get("r_a") or s["joints"][b["a"]].get("r", 0.05))
        rb = float(b.get("r_b") or s["joints"][b["b"]].get("r", 0.05))
        flat = b.get("flat") or [1.0, 1.0]
        k = float(b["blend"]) if b.get("blend") is not None else k_default
        R = max(ra, rb) * max(1.0, *flat)
        lo, hi = np.minimum(a, bb) - R, np.maximum(a, bb) + R
        prims.append(Prim(name, "cone", b.get("op", "add"), k, int(b.get("layer", 0)), lo, hi,
                          {"a": a, "frame": bone_frame(a, bb, b.get("up")), "len": float(np.linalg.norm(bb - a)),
                           "ra": ra, "rb": rb, "flat": [float(f) for f in flat]},
                          # sd_cone scales distances by min(flat, 1), so a blend reaches that much further
                          reach=1.0 / min(*flat, 1.0)))

    for name, bl in s["blobs"].items():
        c = resolve_point(s, bl.get("at", [0, 0, 0])) + np.array(bl.get("offset", [0, 0, 0]), float)
        size = np.array(bl.get("size", [0.05] * 3), float)
        rot = euler_matrix(bl.get("rot", [0, 0, 0]))
        k = float(bl["blend"]) if bl.get("blend") is not None else k_default
        if bl.get("shape", "ellipsoid") == "lids":
            prims.append(_lids(name, bl, c, rot, k))
            continue
        if bl.get("shape") in ("displace", "flatten"):
            prims.append(_modifier(name, bl, c))
            continue
        ext = np.abs(rot) @ size  # AABB of the rotated ellipsoid (or box)
        if bl.get("shape") == "box":
            rnd = min(float(bl.get("round", 0.0)), float(size.min()))
            prims.append(Prim(name, "box", bl.get("op", "add"), k, int(bl.get("layer", 0)), c - ext, c + ext,
                              {"c": c, "size": size, "rot": rot, "round": rnd}, reach=1.0))  # exact distance
            continue
        prims.append(Prim(name, "ellipsoid", bl.get("op", "add"), k, int(bl.get("layer", 0)),
                          c - ext, c + ext, {"c": c, "size": size, "rot": rot},
                          # sd_ellipsoid >= (k0 - 1) * min(size), so it only drops below a blend radius k
                          # inside the ellipsoid scaled by 1 + k / min(size)
                          reach=ext / size.min()))

    for p, el in zip(prims, [*s["bones"].values(), *s["blobs"].values()]):
        p.group, p.join = el.get("group"), float(el.get("join", 0.0))
    prims.sort(key=lambda p: (p.layer, {"add": 0, "subtract": 1, "modify": 2}[p.op], p.group or ""))
    _set_reach(prims)
    return prims


def _lids(name: str, bl: dict, c: np.ndarray, rot: np.ndarray, k: float) -> Prim:
    """Eyelids blob: {"shape": "lids", "at", "rot", "r": eyeball radius, "thickness", "upper"/"lower": how
    much of the eye each lid covers (0..1, from its own edge), "width": corner half-width / r}."""
    r = float(bl["r"])
    ro = r + float(bl.get("thickness", 0.25 * r))
    hu = r * (1 - 2 * float(bl.get("upper", 0.35)))    # margin heights at the middle
    hl = -r * (1 - 2 * float(bl.get("lower", 0.15)))
    w = r * float(bl.get("width", 0.85))
    params = {"c": c, "rot": rot, "r": r, "ro": ro, "round": 0.5 * (ro - r), "closed": hu - hl < 0.02 * r}
    if not params["closed"]:
        zc = 0.35 * hu + 0.65 * hl                      # corners sit low, so the upper lid arches more
        au, al = hu - zc, zc - hl
        cu = (au * au - w * w) / (2 * au)               # circle through both corners and the margin's middle
        cl = (al * al - w * w) / (2 * al)
        params.update(cu=zc + cu, Ru=au - cu, cl=zc - cl, Rl=al - cl)
    return Prim(name, "lids", bl.get("op", "add"), k, int(bl.get("layer", 0)), c - ro, c + ro, params, reach=1.0)


def _modifier(name: str, bl: dict, c: np.ndarray) -> Prim:
    """Stroke output: {"shape": "displace", "pts", "nrm", "width", "depth" (per point), "profile"} or
    {"shape": "flatten", "pts": 1-2 plane points, "nrm": [normal], "width", "soft", "height", "blend"}.
    Modifiers reshape everything combined before them (layer order), only inside their box."""
    P = np.asarray(bl["pts"], float) + c
    N = np.asarray(bl["nrm"], float)
    if bl["shape"] == "flatten":
        w, soft, height = float(bl["width"]), float(bl["soft"]), float(bl["height"])
        R = w + soft
        params = {"pts": P, "nrm": N / np.linalg.norm(N, axis=1, keepdims=True), "width": w, "soft": soft,
                  "height": height, "blend": float(bl.get("blend", 0.0))}
        lo, hi = P.min(0) - R, P.max(0) + R
        lip = 1.0 + 1.5 / soft * 2 * height
    else:
        W, D = np.asarray(bl["width"], float), np.asarray(bl["depth"], float)
        if not (len(P) == len(N) == len(W) == len(D)) or np.any(W <= 0):
            raise SpecError(f"stroke {name!r}: needs one nrm/width/depth per point, widths > 0")
        prof = bl.get("profile", "soft")
        from .sdf import PROFILES
        if prof not in PROFILES:
            raise SpecError(f"stroke {name!r}: unknown profile {prof!r} (have {', '.join(PROFILES)})")
        reach = float(max(W.max(), 2 * np.abs(D).max()))
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1) if len(P) > 1 else np.zeros(0)
        ds = np.concatenate([seg, [0.0]]) / 2 + np.concatenate([[0.0], seg]) / 2  # arc length per sample
        v = np.linspace(-1, 1, 2001)
        norm = float(np.trapezoid(PROFILES[prof][0](np.abs(v)), v))  # a dab's integral along a straight trail
        params = {"pts": P, "nrm": N / np.linalg.norm(N, axis=1, keepdims=True), "width": W, "depth": D,
                  "profile": prof, "reach": reach, "ds": ds, "norm": norm}
        R = float(max(W.max(), 2 * reach))
        lo, hi = P.min(0) - R, P.max(0) + R
        lip = 1.0 + float((np.abs(D) / W).max()) * PROFILES[prof][1] + float(np.abs(D).max()) * 1.5 / reach
    return Prim(name, bl["shape"], "modify", 0.0, int(bl.get("layer", 0)), lo, hi, params, lip=lip)


def _set_reach(prims: list[Prim]) -> None:
    """Turn each primitive's reach-per-unit-blend (set above) into a distance past its AABB beyond which
    it can be skipped without changing the combined field. That needs its value to stay out of its own
    blend and out of the blend of every later primitive that overlaps it (a fillet from a later part
    rounds toward everything already combined), plus k/4 for the dip smooth union adds."""
    scale = [np.broadcast_to(np.asarray(p.reach, float), (3,)) for p in prims]
    for i in range(len(prims) - 1, -1, -1):
        p, k = prims[i], prims[i].blend
        if p.op == "modify":  # applied exactly within its box, not blended: nothing to widen
            p.reach, p.inert = 0.0, 0.0
            continue
        for q in prims[i + 1:]:
            if q.op != "modify" and q.blend * 1.25 > k and np.all(p.lo - scale[i] * q.blend * 1.25 <= q.hi + q.reach) \
                    and np.all(q.lo - q.reach <= p.hi + scale[i] * q.blend * 1.25):
                k = q.blend * 1.25
        p.reach, p.inert = scale[i] * k, k


def summarize(spec: dict) -> str:
    """Plain-text readout: extents, proportions, bone lengths."""
    s = expand_mirror(spec)
    lines = []
    try:
        prims = compile_prims(spec)
    except SpecError as e:
        return f"SPEC ERROR: {e}"
    adds = [p for p in prims if p.op == "add"]
    if adds:
        lo = np.min([p.lo for p in adds], axis=0)
        hi = np.max([p.hi for p in adds], axis=0)
        d = hi - lo
        lines.append(f"approx bounds: width(X) {d[0]:.3f}  length(Y) {d[1]:.3f}  height(Z) {d[2]:.3f}"
                     f"  | min {np.round(lo, 3).tolist()} max {np.round(hi, 3).tolist()}")
    lines.append(f"{len(spec.get('joints', {}))} joints, {len(spec.get('bones', {}))} bones, "
                 f"{len(spec.get('blobs', {}))} blobs stored ({len(prims)} primitives after mirroring)")
    for name, b in spec.get("bones", {}).items():
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        lines.append(f"  bone {name}: {b['a']} -> {b['b']}  len {np.linalg.norm(bb - a):.3f}")
    if spec.get("strokes"):
        n = sum(int((st.get("repeat") or {}).get("count", 1)) for st in spec["strokes"].values())
        lines.append(f"  {len(spec['strokes'])} strokes ({n} with repeats): " + ", ".join(spec["strokes"]))
    if spec.get("kits"):
        from . import kits
        for name, k in spec["kits"].items():
            gen = kits.expand({**spec, "kits": {name: k}})
            new = {kind: [n for n in gen[kind] if n not in spec.get(kind, {})] for kind in ("joints", "bones", "blobs")}
            lines.append(f"  kit {name} ({k.get('type')}): generates {len(new['joints'])} joints, "
                         f"{len(new['bones'])} bones, {len(new['blobs'])} blobs (\".L\" ones mirror)")
            for kind in ("joints", "blobs"):
                if new[kind]:
                    lines.append(f"    {kind}: " + ", ".join(new[kind]))
    return "\n".join(lines)
