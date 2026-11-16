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

Blob shapes: "ellipsoid" (default), "box" / "cylinder" (+ "round"), "blade", "lids", "collar", "sweep", and the
soft primary forms (softforms.py): "super" (a superellipsoid, "squareness" 2 = ellipsoid rising toward a box, no band
where a plane turns into an edge) and "loft" (ONE seamless mass through cross-sections: a head and body as one pear);
"sheet" (sheet.py: one seamless thick sheet along a spine curve, tapering, folding without seams: ears, leaves, flaps).

Elements are combined in layer order; within a layer adds come first, then subtracts, then modifiers
(strokes: they displace or plane whatever the layer has built so far).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at spec.NAME: C422). spec_hands: A modeller's hands, compiled: masses fused into one (`_fuse`), a direction
by word (`_aim`), clay grabbed and moved (`_grabs`), cuts and trims, and csg groups (`_csg`). spec_parts: parts and
their shapes, compiled: `_parts`, sweeps and lids, a profile and its norm, modifiers, and the reach of each primitive
(`_set_reach`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import sheet, softforms
from . import moved

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
    skip = ("paint", "skin", "plan", "story", "rig", "hair", "cloth", "face_shapes")  # hair: curve locks, cloth: simulated
    # garment meshes (cloth.py): both live in the Blender scene, not the field; face_shapes: export morph targets
    unshaped = ("paint", "look", "sheet")  # a paint style, a look preset, the sheet's name shape nothing either
    st = spec.get("style") or {}
    if not any(k in spec for k in skip) and not any(k in st for k in unshaped):
        return spec
    out = {k: v for k, v in spec.items() if k not in skip}
    if (spec.get("skin") or {}).get("folds"):  # the one thing of the skin that IS shape: its folds as relief
        from . import skin_folds  # (skin_folds_geometry.prims); None unless a fold has an amount and the relief is geometry
        tis = skin_folds.geometry_key(spec["skin"])
        if tis:
            out["tissue"] = tis
    if any(k in st for k in unshaped):
        out["style"] = {k: v for k, v in st.items() if k not in unshaped}
    return out


def expand_mirror(spec: dict) -> dict:
    """Return a copy of spec with kits and strokes expanded and every ".L" element mirrored to ".R"."""
    from . import spec_hands
    from . import anatomy, kits, strokes
    spec = strokes.expand(strokes.seat_joints(anatomy.expand(kits.expand(geometry(spec)))))
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
        if isinstance(bl.get("aim"), dict):
            nb["aim"] = spec_hands._mirror_aim(bl["aim"])
        for key in ("rise", "face"):  # a slab's directions
            if isinstance(bl.get(key), (list, tuple)):
                nb[key] = _mirror_vec(bl[key])
        for key in ("pts", "nrm", "path", "N", "U", "spine"):  # sweeps (strokes, sweep blobs), sheets
            if key in bl:
                nb[key] = [_mirror_vec(v) for v in bl[key]]
        if bl.get("shape") == "sheet":  # the normal (tangent x width axis) flips under a reflection: keep its side
            if "width_axis" in bl:
                nb["width_axis"] = _mirror_vec(bl["width_axis"])
            nb["hand"] = -float(bl.get("hand", 1.0))
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
    kind: str  # "cone" | "ellipsoid" | "super" | "loft" | "lids" | "box" | "displace" | "flatten" | "shell"
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
    lip: float = 1.0  # modifiers and grabbed masses: how much steeper than a distance their field can be
    part: str = "body"  # which separate mesh it belongs to; parts are fields of their own, hard-unioned
    instance: str | None = None  # the prefab instance it came from (assemble); export shares their meshes
    cut_boxes: tuple = ()  # (fingerprint, lo, hi) of each targeted cut folded into it: where a moved cut changes it
    sides: tuple | None = None  # a fuse whose fill differs by side: (centre, size, ((axis, sign, part of the fill), ...))


BLOB_SHAPES = ("ellipsoid", "box", "cylinder", "blade", "sheet", "slab", "loft", "super", "sweep", "collar", "lids",
               "displace", "flatten")


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
    from . import spec_hands, spec_parts
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
                           "cut": spec_hands._cut(name, b)},
                          # sd_cone scales distances by min(flat, 1), so a blend reaches that much further
                          reach=1.0 / min(*flat, 1.0)))

    for name, bl in s["blobs"].items():
        c = resolve_point(s, bl.get("at", [0, 0, 0])) + np.array(bl.get("offset", [0, 0, 0]), float)
        size = np.array(bl.get("size", [0.05] * 3), float)
        rot = spec_hands._aim(name, bl, size) if bl.get("aim") is not None else euler_matrix(bl.get("rot", [0, 0, 0]))
        k = float(bl["blend"]) if bl.get("blend") is not None else k_default
        if bl.get("shape", "ellipsoid") not in BLOB_SHAPES:  # (it fell through to an ellipsoid without a word)
            raise SpecError(f"blob {name!r}: unknown shape {bl.get('shape')!r} (have {', '.join(BLOB_SHAPES)}; "
                            "kit_reference describes each)")
        if bl.get("shape", "ellipsoid") == "lids":
            prims.append(spec_parts._lids(name, bl, c, rot, k))
            continue
        if bl.get("shape") in ("displace", "flatten"):
            prims.append(spec_parts._modifier(name, bl, c))
            continue
        ext = np.abs(rot) @ size  # AABB of the rotated ellipsoid (or box, or cylinder)
        if bl.get("shape") == "cylinder":
            rnd = min(float(bl.get("round", 0.0)), float(size.min()))
            prims.append(Prim(name, "cylinder", bl.get("op", "add"), k, int(bl.get("layer", 0)), c - ext, c + ext,
                              {"c": c, "size": size, "rot": rot, "round": rnd},
                              reach=max(size[0], size[1]) / min(size[0], size[1])))  # exact when round
            continue
        if bl.get("shape") == "blade":
            W, L, T = (float(v) for v in size)
            cup, bend = float(bl.get("cup", 0.0)), float(bl.get("bend", 0.0))
            if T <= 0 or T * 2 > min(W, L):
                raise SpecError(f"blob {name!r}: a blade's size is [half width, half length, half thickness], "
                                f"thickness under the width and length")
            lip = float(np.sqrt(1 + (2 * cup / W) ** 2 + (bend / L) ** 2))
            ext = np.abs(rot) @ (size + np.array([0.0, 0.0, abs(cup) + abs(bend)]))
            prims.append(Prim(name, "blade", bl.get("op", "add"), k, int(bl.get("layer", 0)), c - ext, c + ext,
                              {"c": c, "size": size, "rot": rot, "taper": float(bl.get("taper", 0.0)), "cup": cup,
                               "bend": bend, "lip": lip},
                              reach=lip * max(W, L) / T))  # a thin sheet under-reports distance off its edge
            continue
        if bl.get("shape") == "collar":  # a folded shirt collar round a neck (sdf_shapes.sd_collar)
            rx, ry, hs = (float(v) for v in size)
            cp = {"c": c, "rot": rot, "rx": rx, "ry": ry, "stand": hs, "t": float(bl.get("thickness", 0.0025)),
                  "lean": float(bl.get("lean", 0.004)), "fall": float(bl.get("fall", 0.035)),
                  "points": float(bl.get("points", 0.02)), "spread": float(bl.get("spread", 55.0)),
                  "spread_back": float(bl.get("spread_back", bl.get("spread", 30.0))),
                  "gap": float(bl.get("gap", 14.0)), "stand_gap": float(bl.get("stand_gap", 8.0)), "lip": 1.3}
            R = max(rx, ry) + cp["lean"] + 2 * cp["t"] + cp["fall"] + cp["points"]
            ext = np.abs(rot) @ np.array([R, R, max(R, hs + 2 * cp["t"])])
            prims.append(Prim(name, "collar", bl.get("op", "add"), k, int(bl.get("layer", 0)), c - ext, c + ext,
                              cp, reach=4.0))
            continue
        if bl.get("shape") == "sweep":  # a profile swept along a path (sdf_shapes.sd_sweep): collars, plackets, necklines
            prims.append(spec_parts._sweep(name, bl, k))
            continue
        if bl.get("shape") == "super":
            pr, reach = softforms.super_params(name, bl, c, rot, size, SpecError)
            prims.append(Prim(name, "super", bl.get("op", "add"), k, int(bl.get("layer", 0)), c - ext, c + ext,
                              pr, reach=reach))
            continue
        if bl.get("shape") == "sheet":
            pr, lo, hi = sheet.sheet_params(name, bl, c, SpecError)
            prims.append(Prim(name, "sheet", bl.get("op", "add"), k, int(bl.get("layer", 0)), lo, hi, pr, reach=3.0))
            continue
        if bl.get("shape") == "loft":
            pr, lo, hi = softforms.loft_params(name, bl, c, rot, SpecError)
            prims.append(Prim(name, "loft", bl.get("op", "add"), k, int(bl.get("layer", 0)), lo, hi, pr, reach=3.0))
            continue
        if bl.get("shape") == "slab":  # a flat outline of clay folded over (slab.py; the flap tool writes it)
            from . import slab
            need = [key for key in ("rise", "face", "length", "width", "thickness") if key not in bl]
            if need:
                raise SpecError(f"blob {name!r}: a slab needs {', '.join(need)} (the flap tool writes them)")
            try:
                pr, lo, hi = slab.params(c, bl["rise"], bl["face"], bl["length"], bl["width"], bl.get("tip_width", 0.0),
                                         bl["thickness"], bl.get("tip_thickness", bl["thickness"]), bl.get("fold", 0.0),
                                         bl.get("fold_at", 0.6))
            except ValueError as e:
                raise SpecError(f"blob {name!r}: {e}") from None
            prims.append(Prim(name, "slab", bl.get("op", "add"), k, int(bl.get("layer", 0)), lo, hi, pr, reach=1.5))
            continue
        if bl.get("shape") == "box":
            rnd =min(float(bl.get("round", 0.0)), float(size.min()))
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
    prims, els = spec_hands._fuse(prims, els)
    first: dict = {}  # a group blends into the body once, by its first member's blend and join: every member carries
    for p in prims:  # them, or a chunk that culls the first member blends by another's (seams at chunk edges)
        if p.group:
            g = first.setdefault(p.group, p)
            p.blend = g.blend
            if not p.group.startswith("fuse:"):  # (a fused mass keeps its own fill: _fuse)
                p.join = g.join
    prims = spec_hands._csg(s, prims, els)
    if s.get("base"):  # the base mesh first: everything else unions onto it
        prims.insert(0, _base(s, k_default))
        prims[1:1] = _gnm_mouth(s, prims[0].part)
    prims = _deform(s, prims)
    prims = spec_hands._grabs(s, prims)
    prims = spec_hands._trims(s, prims)
    out = spec_parts._parts(prims, s.get("parts") or {}, k_default, s.get("joints"))
    if s.get("base"):  # the upper lids' fold (base.head.fold, lidfold.py): modifiers right after the base, seated on
        # the base as it is finally built (seated on the base as first made, the lines stood 4 mm off the meshed lid)
        from . import lidfold
        bi = next((i for i, p in enumerate(out) if p.kind == "base"), None)
        if bi is not None:
            fp = lidfold.prims(s, out[bi])
            for p in fp:
                p.reach, p.inert = 0.0, 0.0
            out[bi + 1:bi + 1] = fp
    if s.get("tissue"):  # skin.folds as geometry (skin_folds.py): modifiers after everything else of the skin's part
        # that is not a region cut, seated on that part's field without them
        from . import skin_folds_geometry
        part = s["tissue"].get("part", "body")
        idx = [i for i, p in enumerate(out) if p.part == part]
        if idx:
            fp = skin_folds_geometry.prims(s, [out[i] for i in idx])
            for p in fp:
                p.reach, p.inert = 0.0, 0.0
            at = max(i for i in idx if out[i].op != "intersect") + 1
            out[at:at] = fp
    return out


def _base(s: dict, k_default: float) -> Prim:
    from . import base_surface
    b = s["base"]
    surf = base_surface.surface(s, b)
    V = surf["verts"] if surf["head"] is None else np.r_[surf["verts"], surf["head"]["verts"]]
    pad = float(surf["h"].max()) * 2
    return Prim("base", "base", "add", float(b["blend"]) if b.get("blend") is not None else k_default,
                int(b.get("layer", 0)), V.min(0) - pad, V.max(0) + pad,
                {"verts": V, "normals": surf["normals"], "h": surf["h"], "hmax": surf["hmax"], "tree": surf["tree"],
                 "wt": surf.get("wt"), "seam": surf.get("seam"),
                 "key": surf["key"], "head": surf["head"]},
                reach=1.0, part=b.get("part", "body"))


def _gnm_mouth(s: dict, body_part: str) -> list[Prim]:
    """GNM's own mouth for a GNM head (base_gnm_parts.mouth_mode "gnm"): teeth + gums and tongue as parts of their own
    (base_gnm_parts.gnm_mouth_field; the bag is in the head's own field: base_gnm_parts.sock_points)."""
    from . import base_gnm_parts, base_measures
    b = s["base"]
    if base_gnm_parts.mouth_mode(b) != "gnm":
        return []
    head = base_measures.head_of(s, b)
    if head is None or base_gnm_parts.mouth_mode(b, head) != "gnm":
        return []
    return [Prim(e["name"], e["kind"], e["op"], e["blend"], e["layer"], e["lo"], e["hi"], e["params"], reach=1.0,
                 part=e["part"] or body_part) for e in base_gnm_parts.gnm_mouth_field(head)]


def _deform(s: dict, prims: list[Prim]) -> list[Prim]:
    """style.shape.deform: every primitive of the building (not prefab instances, not strokes or shells) is
    evaluated through the deformation (deform.py), inside the csg wrapper so cuts and noise bend with it; boxes
    grow by the largest displacement, and the field is divided by the deformation's stretch."""
    ops = ((s.get("style") or {}).get("shape") or {}).get("deform")
    if not ops:
        return prims
    from . import deform
    deform.validate(ops)
    todo = [p for p in prims if p.instance is None and p.op in ("add", "subtract", "intersect")
            and p.kind in SHAPES]
    if not todo:
        return prims
    lo = np.min([p.lo for p in todo], 0) - 0.5
    hi = np.max([p.hi for p in todo], 0) + 0.5
    lip, reach = deform.stretch(ops, lo, hi)
    for p in todo:
        if p.kind != "csg":
            p.params = {"kind": p.kind, "p": p.params, "hollow": 0.0, "cuts": []}
            p.kind = "csg"
        p.params["warp"] = (ops, lip)
        p.lo, p.hi = p.lo - reach, p.hi + reach
        p.reach = np.asarray(p.reach, float) * lip
    return prims


FUSE_SIDES = {"front": (1, -1), "back": (1, 1), "left": (0, 1), "right": (0, -1), "up": (2, 1), "down": (2, -1)}

AIM_WORDS = {"up": (0, 0, 1), "down": (0, 0, -1), "forward": (0, -1, 0), "front": (0, -1, 0), "back": (0, 1, 0),
             "backward": (0, 1, 0), "out": (1, 0, 0), "left": (1, 0, 0), "in": (-1, 0, 0), "right": (-1, 0, 0)}

SHAPES = ("cone", "ellipsoid", "box", "cylinder", "blade", "lids", "csg", "collar", "sweep", "super", "loft", "sheet",
          "slab")


OP_ORDER = {"add": 0, "subtract": 1, "intersect": 2, "modify": 3}

SWEEP_KEYS = {"collar": ("t", "stand", "lean", "fall", "phi", "sink", "point"),
              "band": ("n0", "n1", "u0", "u1", "round")}

_NORMS: dict[str, float] = {}
_TREES: dict[bytes, object] = {}


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


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("spec_hands", "spec_parts")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
