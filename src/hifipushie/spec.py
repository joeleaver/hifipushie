"""Creature spec: a skeleton of joints and bones with SDF blobs hung on it.

Coordinates are Blender's: Z up, the creature faces -Y, and its left side is +X.
Anything named with a ".L" suffix is auto-mirrored to ".R" across X when
symmetry is on, so the stored spec only ever holds the centre line and the left side.

Spec shape (all lengths in metres):

    {
      "symmetry": true,
      "blend": 0.03,                        # default smooth-union radius
      "joints": {"hip.L": {"pos": [x, y, z], "r": 0.06}},   # or {"on": surface address (see strokes.py),
                                                            #     "lift", "shift", "r"}: seated on the model
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
import zlib
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


def _mirror_local(el: dict, out: dict) -> None:
    """A mirrored instance element: its instance is the ".R" one, and its prefab frame reflects across X."""
    if el.get("instance"):
        out["instance"] = _mname(el["instance"])
    if el.get("local"):
        lc = el["local"]
        out["local"] = {**lc, "m": [[-r[0], r[1], r[2]] for r in lc["m"]]}


def _tree_copy(x):
    """Copy the dict/list structure but share leaf lists of numbers (points, sizes, paths): nothing downstream
    mutates those in place, and deep-copying a model with dozens of expanded strokes dominated compile time."""
    if isinstance(x, dict):
        return {k: _tree_copy(v) for k, v in x.items()}
    if isinstance(x, list) and any(isinstance(v, (dict, list)) and not _numeric(v) for v in x):
        return [_tree_copy(v) for v in x]
    return x


def _numeric(v) -> bool:
    return isinstance(v, list) and all(isinstance(e, (int, float)) or _numeric(e) for e in v)


def geometry(spec: dict) -> dict:
    """The spec without what doesn't shape the surface (paint, plan, story), so editing those doesn't rebuild or
    re-seat anything."""
    skip = ("paint", "plan", "story")
    if not any(k in spec for k in skip) and not (spec.get("style") or {}).get("paint"):
        return spec
    out = {k: v for k, v in spec.items() if k not in skip}
    if (spec.get("style") or {}).get("paint"):  # a paint style doesn't shape anything either
        out["style"] = {k: v for k, v in spec["style"].items() if k != "paint"}
    return out


def expand_mirror(spec: dict) -> dict:
    """Return a copy of spec with kits and strokes expanded and every ".L" element mirrored to ".R"."""
    from . import kits, strokes
    spec = strokes.expand(strokes.seat_joints(kits.expand(geometry(spec))))
    out = _tree_copy(spec)
    for kind in KINDS:
        out.setdefault(kind, {})
    if not spec.get("symmetry", True):
        return out

    for name, j in spec.get("joints", {}).items():
        if (m := mirror_name(name)) and m not in spec["joints"]:
            out["joints"][m] = {**_tree_copy(j), "pos": _mirror_vec(j["pos"])}

    for name, b in spec.get("bones", {}).items():
        m = mirror_name(name)
        if m and m not in spec["bones"]:
            out["bones"][m] = {**_tree_copy(b), "a": _mname(b["a"]), "b": _mname(b["b"])}
            if b.get("up"):
                out["bones"][m]["up"] = _mirror_vec(b["up"])
            if b.get("group"):
                out["bones"][m]["group"] = _mname(b["group"])
            if b.get("targets"):
                out["bones"][m]["targets"] = [_mname(t) for t in b["targets"]]
            _mirror_local(b, out["bones"][m])

    for name, bl in spec.get("blobs", {}).items():
        m = mirror_name(name)
        if not m or m in spec["blobs"]:
            continue
        nb = _tree_copy(bl)
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
        if bl.get("targets"):
            nb["targets"] = [_mname(t) for t in bl["targets"]]
        _mirror_local(bl, nb)
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
    kind: str  # "cone" | "ellipsoid" | "lids" | "box" | "displace" | "flatten" | "shell"
    op: str  # "add" | "subtract" | "intersect" | "modify"
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
    part: str = "body"  # which separate mesh it belongs to; parts are fields of their own, hard-unioned
    instance: str | None = None  # the prefab instance it came from (assemble); export shares their meshes
    cut_boxes: tuple = ()  # (fingerprint, lo, hi) of each targeted cut folded into it: where a moved cut changes it


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


_COMPILED: dict[str, list] = {}


def compile_prims(spec: dict) -> list[Prim]:
    """Mirror, resolve and turn a spec into an ordered list of SDF primitives. Cached by content: one edit
    and look compiles the same spec several times (validate, summarise, bounds, build), and kits and strokes
    raycast the body to seat themselves. Treat the result as read-only."""
    import hashlib
    import json
    spec = geometry(spec)
    key = hashlib.sha1(json.dumps(spec, sort_keys=True, default=float).encode()).hexdigest()
    if key not in _COMPILED:
        if len(_COMPILED) > 32:
            _COMPILED.pop(next(iter(_COMPILED)))
        _COMPILED[key] = _compile(spec)
    return _COMPILED[key]


def _compile(spec: dict) -> list[Prim]:
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
        bow = b.get("bow") or [0.0, 0.0]
        bow = [0.0, float(bow)] if isinstance(bow, (int, float)) else [float(bow[0]), float(bow[1])]
        R = max(ra, rb) * max(1.0, *flat) + float(np.hypot(*bow))
        lo, hi = np.minimum(a, bb) - R, np.maximum(a, bb) + R
        prims.append(Prim(name, "cone", b.get("op", "add"), k, int(b.get("layer", 0)), lo, hi,
                          {"a": a, "frame": bone_frame(a, bb, b.get("up")), "len": float(np.linalg.norm(bb - a)),
                           "ra": ra, "rb": rb, "flat": [float(f) for f in flat], "bow": tuple(bow),
                           "cut": _cut(name, b)},
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
        ext = np.abs(rot) @ size  # AABB of the rotated ellipsoid (or box, or cylinder)
        if bl.get("shape") == "cylinder":
            rnd = min(float(bl.get("round", 0.0)), float(size.min()))
            prims.append(Prim(name, "cylinder", bl.get("op", "add"), k, int(bl.get("layer", 0)), c - ext, c + ext,
                              {"c": c, "size": size, "rot": rot, "round": rnd},
                              reach=max(size[0], size[1]) / min(size[0], size[1])))  # exact when round
            continue
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

    els = [*s["bones"].values(), *s["blobs"].values()]
    for p, el in zip(prims, els):
        p.group, p.join = el.get("group"), float(el.get("join", 0.0))
        p.part = el.get("part") or "body"
        p.instance = el.get("instance")
    prims = _csg(s, prims, els)
    return _parts(prims, s.get("parts") or {}, k_default)


def _cut(name: str, b: dict) -> float:
    """Flat ends for a bone ("ends": "flat" or {"flat": edge radius}): 0 = the usual round caps."""
    e = b.get("ends")
    if e in (None, "round"):
        return 0.0
    if e == "flat":
        return 0.004
    if isinstance(e, dict) and "flat" in e:
        return max(float(e["flat"]), 1e-4)
    raise SpecError(f"bone {name!r}: ends is \"round\", \"flat\" or {{\"flat\": edge radius}}")


def _csg(s: dict, prims: list[Prim], els: list[dict]) -> list[Prim]:
    """Element-level solids: "hollow": t keeps only a wall t thick inside an element's surface, and a subtract
    or intersect with "targets": [names or tags] shapes only those elements (a pot's opening doesn't bite
    the shelf it stands on). Both wrap the target primitive (kind "csg"); the cut isn't a primitive itself."""
    from .assemble import select
    wrapped: dict[str, Prim] = {}

    def wrap(p: Prim) -> Prim:
        if p.kind != "csg":
            p.params = {"kind": p.kind, "p": p.params, "hollow": 0.0, "cuts": []}
            p.kind = "csg"
        return p

    by_name = {p.name: p for p in prims}
    out = []
    for p, el in zip(prims, els):
        lc = el.get("local")  # an instance's element: noise in its prefab's frame, seeded by the prefab element
        frame = None
        if lc and (el.get("lumpy") or el.get("chips")):
            m = np.asarray(lc["m"], float)
            frame = (m, np.asarray(lc["t"], float), float(abs(np.linalg.det(m)) ** (-1 / 3)))
        seed0 = zlib.crc32((lc["name"] if lc else p.name).encode()) % 9973
        if el.get("lumpy"):
            lp = el["lumpy"]
            lp = {"amount": float(lp)} if isinstance(lp, (int, float)) else lp
            amt = float(lp.get("amount", 0.004))
            sc = float(lp.get("scale", max(8 * amt, 0.02)))
            if p.kind not in SHAPES:
                raise SpecError(f"{p.name!r}: lumpy works on bones and shaped blobs")
            wrap(p).params["lumpy"] = (amt, sc, int(lp.get("seed", seed0)), int(lp.get("octaves", 3)))
            grow = amt * (frame[2] if frame else 1.0)
            p.lo, p.hi = p.lo - grow, p.hi + grow
        if el.get("chips"):
            ch = el["chips"]
            ch = {"depth": float(ch)} if isinstance(ch, (int, float)) else ch
            depth = float(ch.get("depth", 0.006))
            sc = float(ch.get("scale", max(6 * depth, 0.02)))
            cover = min(max(float(ch.get("amount", 0.15)), 0.0), 0.9)  # roughly the fraction of surface chipped
            lo = 0.5 + 0.35 * (1 - 2 * cover)
            w = max(0.03, 1.5 * depth / sc)  # keeps the carved field's slope near 1
            if p.kind not in SHAPES:
                raise SpecError(f"{p.name!r}: chips work on bones and shaped blobs")
            where = ch.get("where", "edges")
            if where not in ("edges", "all"):
                raise SpecError(f"{p.name!r}: chips where is \"edges\" or \"all\"")
            wrap(p).params["chips"] = (depth, sc, lo, w, int(ch.get("seed", seed0) + 7), where == "edges")
        if frame is not None:
            p.params["frame"] = frame
        if el.get("hollow"):
            if p.kind not in SHAPES:
                raise SpecError(f"{p.name!r}: hollow works on bones and shaped blobs")
            wrap(p).params["hollow"] = float(el["hollow"])
    for p, el in zip(prims, els):
        if not el.get("targets"):
            out.append(p)
            continue
        if p.op not in ("subtract", "intersect"):
            raise SpecError(f"{p.name!r}: \"targets\" is for op subtract or intersect")
        names = select(s, el["targets"])
        missing = [n for n in names if n not in by_name]
        if missing:
            raise SpecError(f"{p.name!r}: targets {missing} aren't bones, blobs or tags")
        for n in names:
            q = by_name[n]
            m = max(float(p.blend), float(q.blend)) + 0.01
            if p.op == "subtract" and (np.any(p.lo - m > q.hi) or np.any(p.hi + m < q.lo)):
                continue  # a cut nowhere near this target can't shape it: leave it out (and its fingerprint alone,
                # so moving a window re-meshes only the logs around it)
            t = wrap(q)
            t.params["cuts"].append((p.op, p.kind, p.params, float(p.blend)))
            from .sdf import fingerprint
            t.cut_boxes = (*t.cut_boxes, (fingerprint(p), p.lo - m, p.hi + m))
            wrapped[n] = t
    return out


SHAPES = ("cone", "ellipsoid", "box", "cylinder", "lids", "csg")


OP_ORDER = {"add": 0, "subtract": 1, "intersect": 2, "modify": 3}


def _parts(prims: list[Prim], defs: dict, k_default: float) -> list[Prim]:
    """Order primitives part by part (body first, shells after the part they follow), each part sorted and
    clipped on its own. A shell part ({"shell": base, "offset", "thickness"?}) is its base part's surface pushed
    out by offset (solid; or only a layer `thickness` deep), cut to the union of its own layer-0 additive
    primitives (its region); its higher-layer adds (buttons, a buckle) and its strokes go on top."""
    by_part: dict[str, list[Prim]] = {}
    for p in prims:
        by_part.setdefault(p.part, []).append(p)
    for name, d in defs.items():
        if d.get("shell"):
            by_part.setdefault(name, [])
    done: dict[str, list[Prim]] = {}
    pending = sorted(by_part, key=lambda n: (n != "body", n))
    while pending:
        progressed = False
        for name in list(pending):
            d = defs.get(name) or {}
            base = d.get("shell")
            if base and base not in done:
                if base not in by_part:
                    raise SpecError(f"part {name!r}: shell of unknown part {base!r}")
                continue
            ps = list(by_part[name])
            if base:
                off, th = float(d.get("offset", 0.006)), float(d.get("thickness") or 0.0)
                bp = done[base]
                badds = [q for q in bp if q.op == "add"]
                pad = off
                shell = Prim(f"{name}:shell", "shell", "add", k_default, 0,
                             np.min([q.lo for q in badds], 0) - pad, np.max([q.hi for q in badds], 0) + pad,
                             {"prims": bp, "offset": off, "thickness": th}, part=name)
                for q in ps:  # the region: layer-0 adds, unioned (by `blend`) then intersected with the shell
                    if q.op == "add" and q.layer == 0:
                        q.op, q.group, q.join = "intersect", f"region:{name}", float(d.get("blend", 0.01))
                ps.insert(0, shell)
            ps.sort(key=lambda p: (p.layer, OP_ORDER[p.op], p.group or ""))
            _set_reach(ps)
            done[name] = ps
            pending.remove(name)
            progressed = True
        if not progressed:
            raise SpecError(f"parts {pending}: shells form a cycle")
    return [p for ps in done.values() for p in ps]


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


_NORMS: dict[str, float] = {}
_TREES: dict[bytes, object] = {}


def _profile_norm(prof: str) -> float:
    """A dab's integral along a straight trail (per unit width), which normalises a stroke to its depth."""
    if prof not in _NORMS:
        from .sdf import PROFILES
        v = np.linspace(-1, 1, 2001)
        _NORMS[prof] = float(np.trapezoid(PROFILES[prof][0](np.abs(v)), v))
    return _NORMS[prof]


def _tree(P: np.ndarray):
    """KD-tree over a stroke's samples, reused while the stroke doesn't move."""
    import hashlib
    from scipy.spatial import cKDTree
    key = hashlib.sha1(np.ascontiguousarray(P).tobytes()).digest()
    if key not in _TREES:
        if len(_TREES) > 2000:
            _TREES.clear()
        _TREES[key] = cKDTree(P)
    return _TREES[key]


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
        # full strength within `reach` of the path along the normal, fading to nothing at twice that: enough to
        # cover the displaced surface (|depth| away) with a gentle fade, without reaching through thin parts
        reach = float(max(2 * np.abs(D).max(), 0.25 * W.max(), 1e-3))
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1) if len(P) > 1 else np.zeros(0)
        ds = np.concatenate([seg, [0.0]]) / 2 + np.concatenate([[0.0], seg]) / 2  # arc length per sample
        norm = _profile_norm(prof)
        radius = float(np.hypot(W.max(), 2 * reach))  # a dab can reach a point this far away, at most
        step = float(ds[ds > 0].min()) if (ds > 0).any() else 1.0
        params = {"pts": P, "nrm": N / np.linalg.norm(N, axis=1, keepdims=True), "width": W, "depth": D,
                  "profile": prof, "reach": reach, "ds": ds, "norm": norm,
                  "radius": radius, "k": int(min(len(P), 2 * radius / step + 4))}
        params["tree"] = _tree(P)
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
    from .realism import summary as story_summary
    lines.append(story_summary(spec))
    lines.append(f"{len(spec.get('joints', {}))} joints, {len(spec.get('bones', {}))} bones, "
                 f"{len(spec.get('blobs', {}))} blobs stored ({len(prims)} primitives after mirroring)")
    for name, b in spec.get("bones", {}).items():
        if "between" in b:
            lines.append(f"  bone {name}: between the copies of {b['between']}")
            continue
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
