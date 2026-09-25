"""Repetition: prefabs placed as instances, and arrays of elements. Both expand into ordinary joints, bones and
blobs before kits and mirroring, so everything downstream (strokes, paint, parts, export) sees plain elements.

  "prefabs":   {name: {"joints": {...}, "bones": {...}, "blobs": {...}, "symmetry": false}}
               a reusable piece in its own local frame (metres, its origin where it's placed; e.g. a chair
               with its origin on the floor under the seat centre, facing -Y). "symmetry": true mirrors its
               own ".L" elements across its local X first.
  "instances": {name: {"use": prefab, "at": [x, y, z], "rot": [deg x, y, z] (0), "scale": s (1),
                       "part": name | {prefab part: part} (keep the prefab's), "tags": [...],
                       "on": element | tag | instance | [names], "lift": m}}
               a placed copy. Its elements are named "<instance>/<element>" and tagged with the instance
               and prefab names, so paint "near", "targets" and deletes can take "chair1" or "chair" for all
               of them. An instance named ".L" is mirrored whole (a pair of bedside tables).
               "on": set the instance down on those elements' top surface at its x, y (its z is ignored; "lift"
               raises it): a cup "on": "table1/top", a jar on "shelf#1", books on "bookshelf1/shelf#2" (an
               element's name means that element: "shelf" is an array's first copy; a tag, all it tags). Found
               after everything else is placed (on instances too, in order), and again whenever the support
               moves, so props stay put on furniture that's moved or resized. Prefab origins go on the floor.
  "array" on a bone or blob: {"count": n, "offset": [dx, dy, dz] (per copy), "rot": [deg] (per copy, about
               "pivot", default the element's own centre), "jitter": {"offset": [jx, jy, jz], "rot": [deg],
               "size": fraction}, "seed": 0}, or a list of those for a grid (each applied to all copies so far).
               Per copy, "vary": {key: [lo, hi]} draws any numeric field (lists per component) from a range:
               {"r_a": [0.13, 0.17], "r_b": [0.10, 0.13], "bow": [[-0.02, -0.01], [0.02, 0.01]]}; "flip":
               "alternate" | "random" turns a bone end for end (butt ends alternating course by course).
               Copy 0 keeps the element's name; the others are "<name>#<i>" (".L" stays at the end); all are
               tagged with the element's name. Logs, planks, shingles, fence posts, a ring of stones.

"weather": [{"tags": [...], "jitter": {"offset": m | [x, y, z], "rot": deg | [x, y, z], "size": fraction},
              "settle": m (sinks up to that much), "lean": deg | [x, y] (tilts), "sag": m (bones bow down in the
              middle), "lumpy": {...}, "chips": {...}, "seed"}, ...]
             time and use applied to everything carrying those tags (or names). Instances (by instance, prefab or
             instance tag) move as a whole: a chair pushed askew, a table sunk into a soft floor. Write one
             entry per event in the story ("the porch settled", "the ridge beam sags", "the chairs get pushed
             around"). Deterministic per seed.

"walls": {name: {"path": [[x, y], ...], "height": m (2.4), "thickness": m (0.1), "base": z (0), "style": "boards"
             (vertical boards, "board": width 0.15, each a little different) | "solid", "part", "tags", "lumpy",
             "openings": [{"at": metres along the path | [x, y] (the nearest point of the path), "width" (0.9),
             "height" (2.0 for doors), "sill" (0: a doorway; 0.9 for a window), "name", "frame": prefab (origin
             at the bottom centre of the opening, facing -Y), "window": prefab (origin at the opening's centre),
             "door": prefab (hinge at its origin, the leaf along local +X), "hinge": "left" | "right" (the end
             nearer the path's start or its end), "swing": "left" | "right" (the side of the wall it opens to,
             walking along the path), "open": deg (0 closed)}]}}
             a partition or plain wall in one entry: boards (or a box) along each straight run, a box cut per
             opening targeted at this wall only, and the frame, window and door placed and turned to fit. The
             pieces are ordinary elements and instances ("<wall>_<opening>_door", tagged with the wall and the
             opening) and check walks a person through every door opening. Log walls stay arrays of bones with
             their own cuts.
"between" on a bone: {"between": array, "depth": m, "inset": m, "part", "tags", "lumpy"} fills the seam between
             neighbouring copies of a bone array (course above course): one flat bone per pair along their
             mid-line, bowed as they are and as tall as their gap, `depth` either side of it (default 3/4 of their
             radius: recessed). Chinking between logs, mortar between rails. "inset" stops it short of the ends.

"tags": [...] on any bone or blob groups elements under names of your choice ("logs", "furniture"). Anywhere a
list of element names is taken (paint "near", a cut's "targets", delete with "tag") a tag stands for its members.
"""

from __future__ import annotations

import copy
import math

import numpy as np

from .spec import SpecError, euler_matrix


def _euler_of(R: np.ndarray) -> list[float]:
    """XYZ euler angles (deg) of a rotation matrix, as euler_matrix builds them (Rz @ Ry @ Rx)."""
    sy = -R[2, 0]
    if abs(sy) < 0.999999:
        ry = math.asin(sy)
        rx = math.atan2(R[2, 1], R[2, 2])
        rz = math.atan2(R[1, 0], R[0, 0])
    else:  # gimbal lock
        ry = math.copysign(math.pi / 2, sy)
        rx = math.atan2(-R[1, 2], R[1, 1])
        rz = 0.0
    return [round(math.degrees(a), 6) for a in (rx, ry, rz)]


def _r(v) -> list[float]:
    return [round(float(x), 7) for x in v]


_CACHE: dict[str, dict] = {}
_ON: dict[str, dict] = {}  # expand's content key -> {instance: its resolved "at"} for instances placed "on"
_SCATTERED: dict[str, dict] = {}  # expand's content key -> the instances spec["scatter"] generated
NOTES: dict[str, list] = {}  # expand's content key -> things worth telling (scatter that didn't all fit)


def expand(spec: dict) -> dict:
    """The spec with instances and arrays expanded (a new dict; the input is left alone). Cached by content."""
    if not spec.get("instances") and not _has_arrays(spec) and not spec.get("weather") and not spec.get("walls") \
            and not (spec.get("style") or {}).get("shape") and not spec.get("scatter"):
        return spec
    import hashlib
    import json
    key = hashlib.sha1(json.dumps(spec, sort_keys=True, default=float).encode()).hexdigest()
    if key not in _CACHE:
        if len(_CACHE) > 16:
            k = next(iter(_CACHE))
            _CACHE.pop(k)
            _ON.pop(k, None)
            _SCATTERED.pop(k, None)
            NOTES.pop(k, None)
        s = copy.deepcopy(spec)
        _walls(s)
        _style_shape(s)
        weather = s.pop("weather", None) or []
        insts = s.get("instances") or {}
        insts = _weathered(insts, weather)  # instances are weathered whole (a chair leans, its legs don't wander)
        for inst, d in insts.items():
            if "on" not in d:
                _place(s, inst, d)
        s = _arrays(s)
        _SCATTERED[key] = _scatter(s, insts)
        insts = {**insts, **_weathered(_SCATTERED[key], weather)}
        _ON[key] = _place_on(s, {i: d for i, d in insts.items() if "on" in d}, insts)
        s.pop("instances", None)
        s.pop("scatter", None)
        s.pop("prefabs", None)
        s.pop("_arrays_of", None)
        NOTES[key] = s.pop("_notes", [])
        whole = set()
        for inst, d in insts.items():
            whole |= {inst[:-2] if inst.endswith(".L") else inst, d.get("use"), *d.get("tags", [])}
        for i, w in enumerate(weather):
            tags = w.get("tags") or []
            bad = [t for t in ([tags] if isinstance(tags, str) else tags) if t not in whole and not any(
                e == t or t in (el.get("tags") or []) for k in ("bones", "blobs") for e, el in s.get(k, {}).items())]
            if bad:
                raise SpecError(f"weather[{i}]: tags {bad} match no element, instance, prefab or tag")
            _weather_elements(s, w, i, whole)
        _CACHE[key] = s
    return copy.deepcopy(_CACHE[key])


WALL_KEYS = {"path", "height", "thickness", "base", "style", "board", "part", "tags", "openings", "lumpy", "round",
             "seed", "blend", "chips"}
OPENING_KEYS = {"at", "width", "height", "sill", "door", "hinge", "open", "swing", "frame", "window", "part", "name"}


def _walls(s: dict) -> None:
    """spec["walls"] -> ordinary blobs (a box, or a row of boards, per straight run), box cuts for the openings
    (targeted at the wall only) and instances: a frame and a window in each opening, a door hung on its hinge.
    Everything is tagged with the wall's name; openings are named "<wall>_<name or i>"."""
    walls = s.pop("walls", None) or {}
    for wn, w in walls.items():
        where = f"wall {wn!r}"
        bad = set(w) - WALL_KEYS
        if bad:
            raise SpecError(f"{where}: unknown keys {sorted(bad)} (allowed: {sorted(WALL_KEYS)})")
        path = np.asarray(w.get("path") or [], float)
        if path.ndim != 2 or len(path) < 2 or path.shape[1] < 2:
            raise SpecError(f"{where}: path is [[x, y], [x, y], ...] (2+ points)")
        path = path[:, :2]
        H, T = float(w.get("height", 2.4)), float(w.get("thickness", 0.1))
        z0 = float(w.get("base", 0.0))
        style = w.get("style", "boards")
        if style not in ("boards", "solid"):
            raise SpecError(f"{where}: style is \"boards\" or \"solid\"")
        part, tags = w.get("part", "body"), [*w.get("tags", []), wn]
        common = {k: w[k] for k in ("lumpy", "round", "blend", "chips") if k in w}
        seglen = np.linalg.norm(np.diff(path, axis=0), axis=1)
        if np.any(seglen < 1e-6):
            raise SpecError(f"{where}: two path points in the same place")
        starts = np.concatenate([[0.0], np.cumsum(seglen)])
        for i, L in enumerate(seglen):
            u = (path[i + 1] - path[i]) / L
            ang = float(np.degrees(np.arctan2(u[1], u[0])))
            en = f"{wn}" if len(seglen) == 1 else f"{wn}_{i}"
            if style == "solid":
                mid = (path[i] + path[i + 1]) / 2
                s.setdefault("blobs", {})[en] = {"shape": "box", "at": _r([*mid, z0 + H / 2]),
                                                  "size": _r([L / 2 + T / 2, T / 2, H / 2]), "rot": [0, 0, round(ang, 4)],
                                                  "part": part, "tags": tags, **common}
            else:
                bw = float(w.get("board", 0.15))
                n = max(1, int(round(L / bw)))
                step = L / n
                c0 = path[i] + u * step / 2
                s.setdefault("blobs", {})[en] = {
                    "shape": "box", "at": _r([*c0, z0 + H / 2]), "size": _r([step / 2 - 0.001, T / 2, H / 2]),
                    "rot": [0, 0, round(ang, 4)], "part": part, "tags": tags, "round": w.get("round", 0.005),
                    **{k: v for k, v in common.items() if k != "round"},
                    "array": {"count": n, "offset": _r([*(u * step), 0]), "seed": int(w.get("seed", 0)) + i,
                              "vary": {"size": [_r([step / 2 - 0.004, T / 2 * 0.94, H / 2 - 0.004]),
                                                _r([step / 2 - 0.001, T / 2, H / 2])]}}}
        for k, op in enumerate(w.get("openings") or []):
            _opening(s, wn, w, k, op, path, seglen, starts, H, T, z0, part)


def _opening(s, wn, w, k, op, path, seglen, starts, H, T, z0, part) -> None:
    where = f"wall {wn!r} opening {k}"
    bad = set(op) - OPENING_KEYS
    if bad:
        raise SpecError(f"{where}: unknown keys {sorted(bad)} (allowed: {sorted(OPENING_KEYS)})")
    at = op.get("at")
    if isinstance(at, (int, float)):
        d = float(at)
    elif isinstance(at, list) and len(at) >= 2:  # the nearest point of the path to [x, y]
        best = None
        for i, L in enumerate(seglen):
            u = (path[i + 1] - path[i]) / L
            t = float(np.clip((np.asarray(at[:2], float) - path[i]) @ u, 0, L))
            dist = np.linalg.norm(path[i] + u * t - np.asarray(at[:2], float))
            if best is None or dist < best[0]:
                best = (dist, starts[i] + t)
        d = best[1]
    else:
        raise SpecError(f"{where}: at is metres along the wall's path, or [x, y] near it")
    i = int(np.clip(np.searchsorted(starts, d, side="right") - 1, 0, len(seglen) - 1))
    u = (path[i + 1] - path[i]) / seglen[i]
    nrm = np.array([-u[1], u[0]])  # the wall's left side, walking along the path
    ang = float(np.degrees(np.arctan2(u[1], u[0])))
    c = path[i] + u * (d - starts[i])
    door = op.get("door")
    width = float(op.get("width", 0.9))
    height = float(op.get("height", 2.0 if door or op.get("sill") is None else 1.0))
    sill = float(op.get("sill", 0.0))
    if not (0 <= sill and sill + height <= H + 1e-6):
        raise SpecError(f"{where}: sill {sill} + height {height} doesn't fit the wall's height {H}")
    on = f"{wn}_{op.get('name', k)}"
    s.setdefault("blobs", {})[f"cut_{on}"] = {
        "shape": "box", "at": _r([*c, z0 + sill + height / 2]), "size": _r([width / 2, T / 2 + 0.05, height / 2]),
        "rot": [0, 0, round(ang, 4)], "op": "subtract", "blend": 0, "targets": [wn]}
    insts = s.setdefault("instances", {})
    tags = [wn, on]
    if op.get("frame"):
        insts[f"{on}_frame"] = {"use": op["frame"], "at": _r([*c, z0 + sill]), "rot": [0, 0, round(ang, 4)], "tags": tags,
                                "from_wall": [wn, k, "frame"]}
    if op.get("window"):
        insts[f"{on}_window"] = {"use": op["window"], "at": _r([*c, z0 + sill + height / 2]),
                                 "rot": [0, 0, round(ang, 4)], "tags": tags, "from_wall": [wn, k, "window"]}
    if door:
        hinge = op.get("hinge", "left")
        swing = op.get("swing", "left")
        if hinge not in ("left", "right") or swing not in ("left", "right"):
            raise SpecError(f"{where}: hinge and swing are \"left\" or \"right\": the hinge at the opening's end "
                            f"nearer the path's start (left) or end (right); the door opens towards the wall's left "
                            f"or right side, walking along the path")
        # the door prefab: hinge at its origin, the leaf along local +x, closed across the opening
        side = 1.0 if swing == "left" else -1.0
        if hinge == "left":
            hp, base_ang, turn = c - u * (width / 2), ang, side
        else:
            hp, base_ang, turn = c + u * (width / 2), ang + 180.0, -side
        a = float(op.get("open", 0.0))
        # an open door stands in front of the face it swings into (and of its frame's jambs), its leaf (~2 cm
        # half-thick) clear of them
        face = T / 2
        fp = (s.get("prefabs") or {}).get(op.get("frame") or "")
        for b in ((fp or {}).get("blobs") or {}).values():
            if isinstance(b.get("at"), list) and b.get("op", "add") == "add":
                face = max(face, abs(float(b["at"][1])) + float(np.asarray(b.get("size", [0, 0, 0]), float)[1]))
        hp = hp + nrm * side * ((face + 0.025) if a else 0.0)
        insts[f"{on}_door"] = {"use": door, "at": _r([*hp, z0 + sill + 0.005]),
                               "rot": [0, 0, round(base_ang + turn * a, 4)], "tags": [*tags, "doors"],
                               "from_wall": [wn, k, "door", round(base_ang, 4), turn]}


STYLE_SHAPE = ("round", "lumpy", "chips", "blend", "bow", "chunk", "deform")


def _style_shape(s: dict) -> None:
    """spec["style"]["shape"]: how far the whole model leaves realism, applied to every element (prefabs' too)
    before arrays and weather: "round" x every box and cylinder's edge radius (capped just under its smallest
    half-size: soft, toy-like edges), "lumpy" {"amount": x, "scale": x} (0 amount: smooth), "chips" x depth
    (0: none), "blend" x every element's own blend (softer joins), "bow" x every bone's bow and array bow ranges
    (wonkier logs and beams), "chunk" k: thin things thicken: every box or cylinder half-size and every bone
    radius under 6 cm grows by up to k, never past 6 cm (chair legs, table tops, rails, handles, boards: toy-like
    furniture), in place."""
    st = (s.get("style") or {}).get("shape") or {}
    if not st:
        return
    bad = set(st) - set(STYLE_SHAPE)
    if bad:
        raise SpecError(f"style.shape: unknown keys {sorted(bad)} (have {', '.join(STYLE_SHAPE)})")
    kr, kb, kw = float(st.get("round", 1.0)), float(st.get("blend", 1.0)), float(st.get("bow", 1.0))
    lp = st.get("lumpy") or {}
    ka, ks = float(lp.get("amount", 1.0)), float(lp.get("scale", 1.0))
    kc = float(st.get("chips", 1.0))

    kc_ = float(st.get("chunk", 1.0))

    def thick(v: float) -> float:
        return v if v >= 0.06 or kc_ <= 1 else min(v * kc_, max(v, 0.06))

    def one(el: dict, kind: str) -> None:
        if kc_ > 1 and (el.get("op", "add") == "add" or el.get("targets")):  # openings grow with their vessels
            if kind == "blobs" and el.get("shape") in ("box", "cylinder") and "size" in el:
                el["size"] = [round(thick(float(v)), 5) for v in el["size"]]
                if (el.get("array") or {}) and not isinstance(el["array"], list) and "size" in (el["array"].get("vary") or {}):
                    el["array"]["vary"]["size"] = [[round(thick(float(v)), 5) for v in b] for b in el["array"]["vary"]["size"]]
                for stp in (el["array"] if isinstance(el.get("array"), list) else []):
                    if "size" in (stp.get("vary") or {}):
                        stp["vary"]["size"] = [[round(thick(float(v)), 5) for v in b] for b in stp["vary"]["size"]]
            if kind == "bones":
                for k in ("r_a", "r_b"):
                    if el.get(k) is not None:
                        el[k] = round(thick(float(el[k])), 5)
        if kind == "blobs" and el.get("shape") in ("box", "cylinder") and el.get("op", "add") == "add":
            size = np.asarray(el.get("size", [0.05] * 3), float)
            r = float(el.get("round") or (0.004 if kr > 1 else 0.0)) * kr  # sharp boxes get softened too
            el["round"] = round(min(r, 0.95 * float(size.min())), 5)
        if el.get("blend") is not None and el.get("op", "add") == "add" and float(el["blend"]) > 0:
            el["blend"] = float(el["blend"]) * kb
        lu = el.get("lumpy")
        if lu:
            lu = {"amount": float(lu)} if isinstance(lu, (int, float)) else dict(lu)
            if ka == 0:
                el.pop("lumpy")
            else:
                lu["amount"] = float(lu.get("amount", 0.004)) * ka
                if "scale" in lu:
                    lu["scale"] = float(lu["scale"]) * ks
                else:
                    lu["scale"] = max(8 * float(lu["amount"]) / ka, 0.02) * ks
                el["lumpy"] = lu
        ch = el.get("chips")
        if ch:
            if kc == 0:
                el.pop("chips")
            else:
                ch = {"depth": float(ch)} if isinstance(ch, (int, float)) else dict(ch)
                ch["depth"] = float(ch.get("depth", 0.006)) * kc
                el["chips"] = ch
        if kind == "bones" and kw != 1.0:
            if el.get("bow") is not None:
                el["bow"] = (np.asarray(el["bow"], float) * kw).tolist() if isinstance(el["bow"], list) else float(el["bow"]) * kw
            for stp in (el.get("array") if isinstance(el.get("array"), list) else [el["array"]] if el.get("array") else []):
                if "bow" in (stp.get("vary") or {}):
                    stp["vary"]["bow"] = (np.asarray(stp["vary"]["bow"], float) * kw).tolist()

    for kind in ("bones", "blobs"):
        for el in (s.get(kind) or {}).values():
            one(el, kind)
    for pf in (s.get("prefabs") or {}).values():
        for kind in ("bones", "blobs"):
            for el in (pf.get(kind) or {}).values():
                one(el, kind)
    if kc_ > 1:  # bones take their radii from their joints unless they give r_a / r_b
        for sp in [s, *(s.get("prefabs") or {}).values()]:
            for j in (sp.get("joints") or {}).values():
                if "r" in j:
                    j["r"] = round(thick(float(j["r"])), 5)


def _deformed(spec: dict, at) -> np.ndarray:
    """Where a rigid instance's origin goes under the style deformation (deform.py): it rides the bend."""
    ops = ((spec.get("style") or {}).get("shape") or {}).get("deform")
    at = np.asarray(at, float)
    if not ops:
        return at
    from .deform import displacement
    return at + displacement(ops, at[None])[0]


SCATTER_KEYS = {"use", "on", "count", "area", "spacing", "rot", "scale", "seed", "tags", "part"}


def footprint(pf: dict) -> float:
    """A prefab's rough radius across the floor (m): how far its pieces reach from its origin, sideways."""
    r = 0.02
    for b in (pf.get("blobs") or {}).values():
        if b.get("op", "add") != "add" or not isinstance(b.get("at"), list):
            continue
        size = np.asarray(b.get("size", [0.05] * 3), float)
        reach = float(np.hypot(*b["at"][:2])) + float(max(size[:2]))
        for st in (b["array"] if isinstance(b.get("array"), list) else [b["array"]] if b.get("array") else []):
            reach += float(np.hypot(*np.asarray(st.get("offset", [0, 0, 0]), float)[:2])) * (int(st.get("count", 1)) - 1)
        r = max(r, reach)
    for j in (pf.get("joints") or {}).values():
        if isinstance(j.get("pos"), list):
            r = max(r, float(np.hypot(*j["pos"][:2])) + float(j.get("r", 0.02)))
    return r


def _scatter(s: dict, insts: dict) -> dict:
    """spec["scatter"]: {name: {"use": prefab | [prefabs] | {prefab: weight}, "on": support, "count": n,
    "area": [[x0, y0], [x1, y1]] (default: the support's extent), "spacing": m (clear gap between pieces, 0.01),
    "rot": [lo, hi] deg about Z (0..360), "scale": [lo, hi], "seed", "tags", "part"}} -> instances "<name>#i", each
    set down "on" the support where all of its footprint is over it (nothing hangs off an edge), apart from each
    other and from what already stands there. Fewer than `count` if they don't fit (the log says so)."""
    out = {}
    for name in sorted(s.get("scatter") or {}):
        sc = s["scatter"][name]
        where = f"scatter {name!r}"
        bad = set(sc) - SCATTER_KEYS
        if bad:
            raise SpecError(f"{where}: unknown keys {sorted(bad)} (allowed: {sorted(SCATTER_KEYS)})")
        use = sc.get("use")
        if isinstance(use, str):
            use = {use: 1.0}
        elif isinstance(use, list):
            use = {u: 1.0 for u in use}
        if not use or not isinstance(use, dict):
            raise SpecError(f"{where}: use is a prefab, a list of prefabs or {{prefab: weight}}")
        pfs = s.get("prefabs") or {}
        missing = [u for u in use if u not in pfs]
        if missing:
            raise SpecError(f"{where}: no prefab {missing}")
        if "on" not in sc:
            raise SpecError(f"{where}: needs \"on\" (a support: an element, tag or instance)")
        names = [sc["on"]] if isinstance(sc["on"], str) else list(sc["on"])
        rng = np.random.default_rng(int(sc.get("seed", 0)) + 7919)
        kinds, weights = list(use), np.asarray([float(w) for w in use.values()])
        weights = weights / weights.sum()
        rad = {u: footprint(pfs[u]) for u in kinds}
        lo_s, hi_s = sc.get("scale", [1.0, 1.0])
        r0, r1 = sc.get("rot", [0.0, 360.0])
        gap = float(sc.get("spacing", 0.01))
        if sc.get("area"):
            (x0, y0), (x1, y1) = np.sort(np.asarray(sc["area"], float)[:, :2], axis=0)
        else:
            els = {**s.get("bones", {}), **s.get("blobs", {})}
            members = [m for n in names for m in ([n] if n in els else select(s, [n])) if m in els]
            if not members:
                raise SpecError(f"{where}: \"on\" {names} names nothing")
            box = _support_box(s, members)
            (x0, y0), (x1, y1) = box[0][:2], box[1][:2]
        # what already stands on this support
        taken = []
        for d in insts.values():
            if d.get("on") == sc["on"] and isinstance(d.get("at"), list):
                taken.append((float(d["at"][0]), float(d["at"][1]), rad.get(d.get("use"), footprint(pfs.get(d.get("use"), {})))))
        clear = _Clearance(s, names, (x0, y0), (x1, y1))
        n, tries = int(sc.get("count", 1)), 0
        made = 0
        while made < n and tries < 60 * n:
            tries += 1
            u = kinds[int(rng.choice(len(kinds), p=weights))]
            k = float(rng.uniform(lo_s, hi_s))
            r = rad[u] * k
            x, y = float(rng.uniform(x0 + r, x1 - r)) if x1 - x0 > 2 * r else (x0 + x1) / 2, \
                float(rng.uniform(y0 + r, y1 - r)) if y1 - y0 > 2 * r else (y0 + y1) / 2
            if any(np.hypot(x - tx, y - ty) < r + tr + gap for tx, ty, tr in taken):
                continue
            try:  # over the support at its centre and all round its footprint, at one height (not across a step)
                zs = [top_of(s, names, x + dx, y + dy, where, bent=False) for dx, dy in
                      [(0, 0)] + [(0.8 * r * np.cos(a), 0.8 * r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)]]
            except SpecError:
                continue
            if max(zs) - min(zs) > 0.02:
                continue
            if not clear.free(x, y, zs[0], r, height(pfs[u]) * k):  # a plate rack, a lamp, the wall behind
                continue
            taken.append((x, y, r))
            d = {"use": u, "at": [round(x, 4), round(y, 4)], "rot": [0, 0, round(float(rng.uniform(r0, r1)), 2)],
                 "on": sc["on"], "tags": [name, *sc.get("tags", [])]}
            if k != 1.0:
                d["scale"] = round(k, 4)
            if sc.get("part"):
                d["part"] = sc["part"]
            out[f"{name}#{made}"] = d
            made += 1
        if made < n:
            s.setdefault("_notes", []).append(f"{where}: {made} of {n} fitted on {names}")
    return out


def height(pf: dict) -> float:
    """A prefab's rough height above its origin (m)."""
    h = 0.02
    for b in (pf.get("blobs") or {}).values():
        if b.get("op", "add") == "add" and isinstance(b.get("at"), list):
            h = max(h, float(b["at"][2]) + float(np.asarray(b.get("size", [0.05] * 3), float)[2]))
    for j in (pf.get("joints") or {}).values():
        if isinstance(j.get("pos"), list):
            h = max(h, float(j["pos"][2]) + float(j.get("r", 0.02)))
    return h


class _Clearance:
    """Is the room above a spot on a support free (nothing else there: the rest of a dresser, a wall, a
    lamp)? The elements around the support's area, compiled once per scatter entry."""

    def __init__(self, s: dict, names: list, lo, hi, pad: float = 0.6):
        from .spec import compile_prims
        els = {**s.get("bones", {}), **s.get("blobs", {})}
        support = {m for n in names for m in ([n] if n in els else select(s, [n])) if m in els}
        joints = s.get("joints", {})

        def xy(el):
            if isinstance(el.get("at"), list):
                return [el["at"][:2]]
            if "a" in el:
                return [joints[j]["pos"][:2] for j in (el["a"], el["b"]) if isinstance(joints.get(j, {}).get("pos"), list)]
            return []
        near = {k: el for k, el in els.items() if k not in support and el.get("op", "add") == "add"
                and any(lo[0] - pad - 3 <= p[0] <= hi[0] + pad + 3 and lo[1] - pad - 3 <= p[1] <= hi[1] + pad + 3
                        for p in xy(el))}
        mini = {"joints": joints, "parts": s.get("parts") or {}, "symmetry": False, "blend": s.get("blend", 0.03),
                "bones": {k: {kk: v for kk, v in el.items() if kk != "targets"} for k, el in near.items() if "a" in el},
                "blobs": {k: {kk: v for kk, v in el.items() if kk != "targets"} for k, el in near.items() if "a" not in el}}
        self.prims = [p for p in compile_prims(mini) if p.op == "add"] if near else []

    def free(self, x: float, y: float, z: float, r: float, h: float) -> bool:
        if not self.prims:
            return True
        from .sdf import field_at
        ring = [(0.0, 0.0)] + [(0.85 * r * np.cos(a), 0.85 * r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
        pts = np.array([[x + dx, y + dy, z + dz] for dx, dy in ring for dz in np.linspace(0.015, max(h, 0.03), 4)])
        return bool(field_at(self.prims, pts).min() > 0.004)


def _support_box(s: dict, members: list) -> tuple:
    from .spec import compile_prims
    mini = {"joints": s.get("joints", {}), "bones": {m: s["bones"][m] for m in members if m in s.get("bones", {})},
            "blobs": {m: {k: v for k, v in s["blobs"][m].items() if k != "targets"} for m in members if m in s.get("blobs", {})},
            "parts": s.get("parts") or {}, "symmetry": False, "blend": s.get("blend", 0.03)}
    ps = [p for p in compile_prims(mini) if p.op == "add"]
    return np.min([p.lo for p in ps], 0), np.max([p.hi for p in ps], 0)


def _place_on(s: dict, todo: dict, insts: dict | None = None) -> dict:
    """Place instances given "on": set down on the top of the named elements (or tags, instances) at their x, y,
    in dependency order (a cup on a table that is itself an instance), after everything else and arrays.
    Returns {instance: its origin in the world (after any style deformation)}.
    Under a style deformation a prop on an instance rides with it as one rigid piece (the plates carried with the
    dresser), and a prop on the building (a shelf, the counter, the ground) lands where the bend puts it."""
    placed = {}
    insts = insts or {}
    bent = bool(((s.get("style") or {}).get("shape") or {}).get("deform"))
    while todo:
        ready = [i for i, d in todo.items() if not any(
            n in todo or n.split("/")[0] in todo for n in ([d["on"]] if isinstance(d["on"], str) else d["on"]))]
        if not ready:
            raise SpecError(f"instances {sorted(todo)}: \"on\" goes round in a circle")
        for inst in ready:
            d = dict(todo.pop(inst))
            at = [float(v) for v in d.get("at", [0, 0, 0])]
            lift = float(d.get("lift", 0.0))
            who = f"instance {inst!r}"
            names = [d["on"]] if isinstance(d["on"], str) else list(d["on"])
            els = {**s.get("bones", {}), **s.get("blobs", {})}  # props placed this pass (a bowl for its apples) too
            members = [m for n in names for m in ([n] if n in els else select(s, [n])) if m in els]
            carriers = {els[m].get("instance") for m in members}
            if bent and len(carriers) == 1 and None not in carriers:
                sup = carriers.pop()  # carried by an instance: its displacement, rigidly
                if sup in placed:
                    src = insts.get(sup, {}).get("at", [0, 0, 0])
                    carry = np.asarray(placed[sup], float) - _pad3(src)
                else:
                    src = _pad3(insts.get(sup, {}).get("at", [0, 0, 0]))
                    carry = _deformed(s, src) - src
                wx, wy = at[0] + carry[0], at[1] + carry[1]
                world = [wx, wy, top_of(s, names, wx, wy, who) + lift]
            elif bent:
                zu = _solve_on(s, names, at[0], at[1], lift, who)
                world = _deformed(s, [at[0], at[1], zu]).tolist()
            else:
                world = [at[0], at[1], top_of(s, names, at[0], at[1], who) + lift]
            d["at"] = [float(v) for v in world]
            d["_world"] = True  # already where it stands: no further deformation
            placed[inst] = d["at"]
            _place(s, inst, d)
        _arrays(s)
    return placed


def _pad3(at) -> np.ndarray:
    a = [float(v) for v in at]
    return np.asarray(a + [0.0] * (3 - len(a)))


def _solve_on(s: dict, names, x: float, y: float, lift: float, who: str) -> float:
    """The (undeformed) height of a prop set down on `names` at x, y. Under a style deformation the prop lands
    where its origin is bent to, and the support is bent too (or, an instance, carried rigidly): look where it
    lands and solve for the height that bends onto the top found, from a few starting heights (the lookup must
    hit a narrow shelf, whose bent position depends on its height)."""
    if not ((s.get("style") or {}).get("shape") or {}).get("deform"):
        return top_of(s, names, x, y, who) + lift
    err = None
    for z0 in (None, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5):
        try:
            zu = (top_of(s, names, x, y, who, bent=False) + lift) if z0 is None else z0
            for _ in range(4):
                pd = _deformed(s, [x, y, zu])
                zu = top_of(s, names, float(pd[0]), float(pd[1]), who) + lift - (float(pd[2]) - zu)
            return zu
        except SpecError as e:
            err = e
    raise err


def top_of(s: dict, names, x: float, y: float, who: str = "", bent: bool = True) -> float:
    """The top surface of the named elements (tags, instances) at (x, y), cuts into them included: the highest
    point where a vertical line there leaves them. s: a spec with instances placed and arrays expanded."""
    from .sdf import field_at
    from .spec import compile_prims
    names = [names] if isinstance(names, str) else list(names)
    els = {**s.get("bones", {}), **s.get("blobs", {})}
    # an element's own name means that element (an array's copy 0 is named like the array, whose name also tags
    # every copy: "shelf" is the first shelf, not all of them); anything else is a tag or an instance
    members = [m for n in names for m in ([n] if n in els else select(s, [n])) if m in els]
    if not members:
        raise SpecError(f"{who}: \"on\" {names} names no element, tag or instance")
    mset = set(members)
    mini = {"joints": s.get("joints", {}), "bones": {}, "blobs": {}, "parts": s.get("parts") or {},
            "symmetry": False, "blend": s.get("blend", 0.03)}
    dfm = ((s.get("style") or {}).get("shape") or {}).get("deform")
    if dfm and bent:  # the support as it stands, bent (its elements' own style changes are already applied)
        mini["style"] = {"shape": {"deform": dfm}}
    for kind in ("bones", "blobs"):
        for n, el in (s.get(kind) or {}).items():
            cuts_it = el.get("targets") and mset & set(select(s, el["targets"]))
            if n in mset or cuts_it:
                mini[kind][n] = {k: v for k, v in el.items() if k not in ("array",)}
                if cuts_it:  # only what it cuts among the support (the rest isn't in this small spec)
                    mini[kind][n]["targets"] = sorted(cuts_it)
                at = el.get("at")
                if isinstance(at, dict) and at.get("bone") in s.get("bones", {}):
                    mini["bones"].setdefault(at["bone"], s["bones"][at["bone"]])
    prims = [p for p in compile_prims(mini) if p.name in mset]
    lo = np.min([p.lo for p in prims], 0)
    hi = np.max([p.hi for p in prims], 0)
    zs = np.arange(hi[2] + 0.02, lo[2] - 0.02, -0.002)
    f = field_at(prims, np.stack([np.full_like(zs, x), np.full_like(zs, y), zs], 1))
    inside = np.flatnonzero(f < 0)
    if not len(inside):
        raise SpecError(f"{who}: ({x:.3f}, {y:.3f}) isn't over {names} (they span x {lo[0]:.2f}..{hi[0]:.2f}, "
                        f"y {lo[1]:.2f}..{hi[1]:.2f})")
    k = inside[0]  # first sample inside, coming down: refine between it and the one above
    if k == 0:
        return float(zs[0])
    return float(zs[k - 1] + (zs[k] - zs[k - 1]) * f[k - 1] / (f[k - 1] - f[k]))


def _weathered(insts: dict, weather: list) -> dict:
    insts = copy.deepcopy(insts)
    for d in insts.values():  # "on" instances may give only [x, y]: their z is found later
        at = d.get("at")
        if isinstance(at, list) and len(at) == 2:
            d["at"] = [*at, 0.0]
    for i, w in enumerate(weather):
        _weather_instances(insts, w, i)
    return insts


def placements(spec: dict) -> dict:
    """Every placed instance after weathering: {instance: {"use": prefab, "at", "rot", "scale", "mirror": bool}}.
    An instance named ".L" also places its mirror image ".R" (mirror: reflected across X after the placement).
    Includes what walls place (doors, frames, windows) and what spec["scatter"] lays out."""
    out = {}
    on = {}
    extra = {}
    if spec.get("walls"):  # doors, frames and windows the walls place
        w = {"walls": copy.deepcopy(spec["walls"]), "blobs": {}, "instances": {}}
        _walls(w)
        extra.update(w["instances"])
    if spec.get("scatter") or any("on" in d for d in (spec.get("instances") or {}).values()) or \
            any("on" in d for d in extra.values()):
        import hashlib
        import json
        key = hashlib.sha1(json.dumps(spec, sort_keys=True, default=float).encode()).hexdigest()
        expand(spec)  # one expansion of this spec: where "on" props landed, what scatter laid out
        on = _ON.get(key, {})
        extra.update(copy.deepcopy(_SCATTERED.get(key, {})))
    spec = {**spec, "instances": {**extra, **(spec.get("instances") or {})}}
    for inst, d in _weathered(spec.get("instances") or {}, spec.get("weather") or []).items():
        pl = {"use": d["use"], "at": list(on[inst]) if inst in on else _deformed(spec, d.get("at", [0, 0, 0])).tolist(),
              "from_wall": d.get("from_wall"), "rot": d.get("rot", [0, 0, 0]),
              "scale": float(d.get("scale", 1.0)), "mirror": False}
        out[inst] = pl
        if inst.endswith(".L"):
            out[inst[:-2] + ".R"] = {**pl, "mirror": True}
    return out


def world_of(pl: dict) -> np.ndarray:
    """4x4 local -> world matrix (Blender axes) of a placement from `placements`."""
    M = np.eye(4)
    M[:3, :3] = euler_matrix(pl["rot"]) * pl["scale"]
    M[:3, 3] = pl["at"]
    if pl["mirror"]:
        M = np.diag([-1.0, 1, 1, 1]) @ M
    return M


def _has_arrays(spec: dict) -> bool:
    return any("array" in el or "between" in el for kind in ("bones", "blobs") for el in (spec.get(kind) or {}).values())


# ---- prefabs ---------------------------------------------------------------------------------------------------

def _place(s: dict, inst: str, d: dict) -> None:
    from .spec import expand_mirror
    pf = (s.get("prefabs") or {}).get(d.get("use"))
    if pf is None:
        raise SpecError(f"instance {inst!r}: no prefab {d.get('use')!r} (have {sorted(s.get('prefabs') or {})})")
    local = {"joints": {}, "bones": {}, "blobs": {}, **copy.deepcopy(pf)}
    local["symmetry"] = bool(pf.get("symmetry", False))
    for k in ("kits", "strokes"):
        if local.get(k):
            raise SpecError(f"prefab {d['use']!r}: {k} aren't supported inside prefabs yet")
    local = _arrays(local) or local
    local.pop("_arrays_of", None)
    if local["symmetry"]:
        local = expand_mirror({**local, "symmetry": True})
    if any("on" in j for j in local["joints"].values()):
        raise SpecError(f"prefab {d['use']!r}: seated joints (\"on\") aren't supported inside prefabs")
    at = np.asarray(d.get("at", [0, 0, 0]), float)
    if not d.get("_world"):
        at = _deformed(s, at)
    R = euler_matrix(d.get("rot", [0, 0, 0]))
    sc = float(d.get("scale", 1.0))
    stem, sfx = (inst[:-2], ".L") if inst.endswith(".L") else (inst, "")
    nm = (lambda n: f"{stem}/{n}{sfx}")
    parts = d.get("part")
    tags = [stem, d["use"], *d.get("tags", [])]

    def T(p):
        return at + R @ (sc * np.asarray(p, float))

    # world -> prefab frame, so noise on the element (lumpy, chips) is the same on every instance
    m, t = R.T / sc, -R.T @ at / sc

    def frame_of(n):
        return {"name": f"{d['use']}/{n}", "m": [_r(r) for r in m], "t": _r(t)}

    def part_of(el):
        p = el.get("part", "body")
        if isinstance(parts, str):
            return parts
        if isinstance(parts, dict):
            return parts.get(p, p)
        return p

    for jn, j in local["joints"].items():
        s["joints"][nm(jn)] = {**j, "pos": _r(T(j["pos"])), "r": float(j.get("r", 0.05)) * sc}
    for bn, b in local["bones"].items():
        nb = {**b, "a": nm(b["a"]), "b": nm(b["b"]), "part": part_of(b), "tags": [*b.get("tags", []), *tags],
              "instance": inst, "local": frame_of(bn)}
        for k in ("r_a", "r_b", "blend", "join", "hollow"):
            if b.get(k) is not None:
                nb[k] = float(b[k]) * sc
        if b.get("up"):
            nb["up"] = _r(R @ np.asarray(b["up"], float))
        if b.get("group"):
            nb["group"] = nm(b["group"])
        if b.get("targets"):
            nb["targets"] = [nm(t) for t in b["targets"]]
        s["bones"][nm(bn)] = nb
    for bn, bl in local["blobs"].items():
        nb = {**bl, "part": part_of(bl), "tags": [*bl.get("tags", []), *tags], "instance": inst, "local": frame_of(bn)}
        a = bl.get("at", [0, 0, 0])
        if isinstance(a, str):
            nb["at"] = nm(a)
        elif isinstance(a, dict):
            nb["at"] = {**a, "bone": nm(a["bone"])}
        else:
            nb["at"] = _r(T(a))
        if "offset" in bl:
            nb["offset"] = _r(R @ (sc * np.asarray(bl["offset"], float)))
        nb["size"] = _r(sc * np.asarray(bl.get("size", [0.05] * 3), float))
        nb["rot"] = _euler_of(R @ euler_matrix(bl.get("rot", [0, 0, 0])))
        for k in ("blend", "join", "round", "hollow"):
            if bl.get(k) is not None:
                nb[k] = float(bl[k]) * sc
        if bl.get("group"):
            nb["group"] = nm(bl["group"])
        if bl.get("targets"):
            nb["targets"] = [nm(t) for t in bl["targets"]]
        s["blobs"][nm(bn)] = nb


# ---- arrays ----------------------------------------------------------------------------------------------------

def _arrays(s: dict):
    """Expand every element's "array" in place (joints get copies for arrayed bones). Returns s."""
    from .spec import resolve_point
    for kind in ("bones", "blobs"):
        for name, el in list(s.get(kind, {}).items()):
            if "array" not in el:
                continue
            steps = el["array"] if isinstance(el["array"], list) else [el["array"]]
            s.setdefault("_arrays_of", {})[name] = steps
            base = {k: v for k, v in el.items() if k != "array"}
            base["tags"] = [*el.get("tags", []), name]
            stem, sfx = (name[:-2], name[-2:]) if name.endswith((".L", ".R")) else (name, "")
            if kind == "bones":
                if not all("pos" in (s["joints"].get(j) or {}) for j in (el["a"], el["b"])):
                    raise SpecError(f"bone {name!r}: an array needs both joints placed by \"pos\"")
                a0, b0 = resolve_point(s, el["a"]), resolve_point(s, el["b"])
                copies = [(np.eye(3), np.zeros(3), 1.0)]
                centre = (a0 + b0) / 2
            else:
                centre = _blob_centre(s, name, el)
                copies = [(np.eye(3), np.zeros(3), 1.0)]
            for st in steps:
                copies = _step(name, st, copies, centre)
            vary = {k: v for st in steps for k, v in (st.get("vary") or {}).items()}
            flip = next((st["flip"] for st in steps if st.get("flip")), None)
            rng = np.random.default_rng(int(steps[0].get("seed", 0)) + 1000)
            s[kind][name] = base
            for i, (R, t, f) in enumerate(copies):
                cn = name if i == 0 else f"{stem}#{i}{sfx}"
                varied = {k: _draw(rng, lo_hi, name, k) for k, lo_hi in vary.items()}
                flipped = flip == "alternate" and i % 2 == 1 or flip == "random" and rng.random() < 0.5
                if kind == "bones":
                    ja, jb = s["joints"][el["a"]], s["joints"][el["b"]]
                    pa, pb = (centre + R @ (p - centre) + t for p in (a0, b0))
                    ra = float(base["r_a"]) if base.get("r_a") is not None else float(ja.get("r", 0.05))
                    rb = float(base["r_b"]) if base.get("r_b") is not None else float(jb.get("r", 0.05))
                    c = {**base, "r_a": ra * f, "r_b": rb * f, **varied}
                    if base.get("up"):
                        c["up"] = _r(R @ np.asarray(base["up"], float))
                    if flipped:  # butt end the other way: swap the ends and their radii
                        pa, pb = pb, pa
                        c["r_a"], c["r_b"] = c["r_b"], c["r_a"]
                    na, nbn = (f"{stem}~a{sfx}", f"{stem}~b{sfx}") if i == 0 else (f"{stem}#{i}~a{sfx}",
                                                                                  f"{stem}#{i}~b{sfx}")
                    if i == 0 and not vary and not flipped:
                        continue  # the element as written
                    s["joints"][na] = {**ja, "pos": _r(pa), "r": c["r_a"]}
                    s["joints"][nbn] = {**jb, "pos": _r(pb), "r": c["r_b"]}
                    s["bones"][cn] = {**c, "a": na, "b": nbn}
                else:
                    if i == 0:
                        if varied:
                            s["blobs"][name] = {**base, **varied}
                        continue
                    c = {**base, **varied}
                    moved = centre + t  # rotations turn about the centre (or pivot, folded into t)
                    c["at"] = _r(moved)
                    c.pop("offset", None)
                    c["size"] = _r(np.asarray(c.get("size", [0.05] * 3), float) * f)  # varied size, if any
                    c["rot"] = _euler_of(R @ euler_matrix(base.get("rot", [0, 0, 0])))
                    s["blobs"][cn] = c
    for name, el in list((s.get("bones") or {}).items()):
        if "between" in el:
            _between(s, name, el)
    return s


def _between(s: dict, name: str, el: dict) -> None:
    """A bone {"between": array, "depth": m, "inset": m, ...} becomes one flat bone per pair of neighbouring
    copies of that array (neighbours along its first step's offset: stacked logs course by course): along the
    mid-line of the pair, bowed as they are on average, as tall as the gap between their axes and `depth` deep
    either side of it (a recessed seam: chinking, mortar between rails, the gap between boards). `inset`
    trims each end (stop at the corner posts)."""
    from .spec import bone_frame, resolve_point
    src = s["bones"].get(el["between"])
    members = [n for n in select(s, [el["between"]]) if n in s["bones"] and "between" not in s["bones"][n]]
    if src is None and not members:
        raise SpecError(f"bone {name!r}: between {el['between']!r} names no bone array")
    steps = (s.get("_arrays_of") or {}).get(el["between"])
    if not steps:
        raise SpecError(f"bone {name!r}: {el['between']!r} isn't an array of bones")
    off = np.asarray((steps if isinstance(steps, list) else [steps])[0].get("offset", [0, 0, 0]), float)
    logs = []
    for n in members:
        b = s["bones"][n]
        pa, pb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        ra = float(b.get("r_a") or s["joints"][b["a"]].get("r", 0.05))
        rb = float(b.get("r_b") or s["joints"][b["b"]].get("r", 0.05))
        F = bone_frame(pa, pb, b.get("up"))
        bow = b.get("bow") or [0.0, 0.0]
        bow = [0.0, float(bow)] if isinstance(bow, (int, float)) else [float(bow[0]), float(bow[1])]
        mid = bow[0] * F[0] + bow[1] * F[2]  # where the bow puts the axis half-way, in world space
        logs.append([pa, pb, ra, rb, mid])
    d0 = logs[0][1] - logs[0][0]
    for L in logs:  # all one way round (flipped copies too)
        if (L[1] - L[0]) @ d0 < 0:
            L[0], L[1], L[2], L[3] = L[1], L[0], L[3], L[2]
    cen = np.array([(L[0] + L[1]) / 2 for L in logs])
    base = {k: v for k, v in el.items() if k not in ("between", "depth", "inset", "array")}
    base["tags"] = [*el.get("tags", []), name]
    inset = float(el.get("inset", 0.0))
    made = 0
    del s["bones"][name]
    for k, L in enumerate(logs):
        target = cen[k] + off
        j = int(np.argmin(np.linalg.norm(cen - target, axis=1)))
        if j == k or np.linalg.norm(cen[j] - target) > 0.5 * np.linalg.norm(off):
            continue
        M = logs[j]
        a, b = (L[0] + M[0]) / 2, (L[1] + M[1]) / 2
        ax = (b - a) / np.linalg.norm(b - a)
        a, b = a + inset * ax, b - inset * ax
        F = bone_frame(a, b)
        h = F[2]
        ra = abs((M[0] - L[0]) @ h) / 2
        rb = abs((M[1] - L[1]) @ h) / 2
        if min(ra, rb) < 1e-4:
            continue
        mid = (L[4] + M[4]) / 2
        depth = float(el.get("depth", 0.75 * (L[2] + L[3]) / 2))
        r = (ra + rb) / 2
        cn = name if made == 0 else f"{name}#{made}"
        ra, rb = round(float(ra), 6), round(float(rb), 6)
        s["joints"][f"{cn}~a"] = {"pos": _r(a), "r": ra}
        s["joints"][f"{cn}~b"] = {"pos": _r(b), "r": rb}
        s["bones"][cn] = {**base, "a": f"{cn}~a", "b": f"{cn}~b", "r_a": ra, "r_b": rb,
                          "flat": [round(float(depth / r), 4), 1.0], "bow": [round(float(mid @ F[0]), 6),
                                                                            round(float(mid @ F[2]), 6)]}
        made += 1
    if not made:
        raise SpecError(f"bone {name!r}: no neighbouring copies of {el['between']!r} to fill between")


def _draw(rng, lo_hi, name: str, key: str):
    """A value uniformly between lo and hi (numbers, or lists of numbers drawn per component)."""
    if not (isinstance(lo_hi, list) and len(lo_hi) == 2):
        raise SpecError(f"{name!r}: array vary {key!r} is [lo, hi]")
    lo, hi = lo_hi
    if isinstance(lo, list):
        return [round(float(rng.uniform(a, b)), 6) for a, b in zip(lo, hi)]
    return round(float(rng.uniform(lo, hi)), 6)


def _blob_centre(s: dict, name: str, el: dict) -> np.ndarray:
    from .spec import resolve_point
    try:
        return resolve_point(s, el.get("at", [0, 0, 0])) + np.asarray(el.get("offset", [0, 0, 0]), float)
    except SpecError as e:
        raise SpecError(f"blob {name!r}: an array needs its position resolvable from plain joints ({e})")


def _step(name: str, st: dict, copies: list, centre: np.ndarray) -> list:
    """Each copy so far (rotation R0 about the element's centre, centre moved by t0, size factor f0) times
    this step's n copies: turned by i * rot about the pivot, shifted by i * offset, then jittered."""
    n = int(st.get("count", 1))
    if n < 1:
        raise SpecError(f"{name!r}: array count must be at least 1")
    off = np.asarray(st.get("offset", [0, 0, 0]), float)
    rot = np.asarray(st.get("rot", [0, 0, 0]), float)
    pivot = np.asarray(st.get("pivot", centre), float)
    jit = st.get("jitter") or {}
    jo, jr = np.asarray(jit.get("offset", [0, 0, 0]), float), np.asarray(jit.get("rot", [0, 0, 0]), float)
    js = float(jit.get("size", 0.0))
    rng = np.random.default_rng(int(st.get("seed", 0)))
    out = []
    for R0, t0, f0 in copies:
        for i in range(n):
            Rr = euler_matrix(rot * i)
            c = pivot + Rr @ (centre + t0 - pivot) + off * i
            Rj, fi = np.eye(3), 1.0
            if jit and i:  # the first copy stays where the element is
                c = c + rng.uniform(-1, 1, 3) * jo
                Rj = euler_matrix(rng.uniform(-1, 1, 3) * jr)
                fi = 1.0 + rng.uniform(-1, 1) * js
            out.append((Rj @ Rr @ R0, c - centre, f0 * fi))
    return out


# ---- weather ---------------------------------------------------------------------------------------------------

def _rng(w: dict, i: int, name: str):
    import zlib
    return np.random.default_rng([int(w.get("seed", 0)), i, zlib.crc32(name.encode())])


def _u(rng, amp) -> np.ndarray:
    return rng.uniform(-1, 1, 3) * np.broadcast_to(np.asarray(amp, float), (3,))


def _weather_instances(insts: dict, w: dict, i: int) -> None:
    tags = w.get("tags") or []
    for inst, d in insts.items():
        stem = inst[:-2] if inst.endswith(".L") else inst
        if not ({stem, d.get("use"), *d.get("tags", [])} & set(tags)):
            continue
        rng = _rng(w, i, inst)
        at = np.asarray(d.get("at", [0, 0, 0]), float)
        rot = np.asarray(d.get("rot", [0, 0, 0]), float)
        j = w.get("jitter") or {}
        at = at + _u(rng, j.get("offset", 0.0))
        rot = rot + _u(rng, j.get("rot", 0.0))
        if w.get("settle"):
            at[2] -= abs(float(rng.uniform(0, float(w["settle"]))))
        if w.get("lean"):
            rot[:2] += _u(rng, w["lean"])[:2]
        d["at"], d["rot"] = _r(at), _r(rot)


def _weather_elements(s: dict, w: dict, i: int, instance_names: set) -> None:
    """Element-level weathering, for elements carrying the tags (not those that came from weathered instances:
    their instance moved as a whole)."""
    tags = set(w.get("tags") or [])
    skip = {n for n in instance_names}
    joint_users: dict[str, int] = {}
    for b in s["bones"].values():
        for e in ("a", "b"):
            joint_users[b[e]] = joint_users.get(b[e], 0) + 1
    for kind in ("bones", "blobs"):
        for n, el in s.get(kind, {}).items():
            et = set(el.get("tags") or []) | {n}
            if not (et & tags) or (et & skip and not (tags - skip) & et):
                continue
            rng = _rng(w, i, n)
            j = w.get("jitter") or {}
            for k in ("lumpy", "chips"):
                if w.get(k) and k not in el:
                    el[k] = copy.deepcopy(w[k])
            if kind == "blobs":
                el["offset"] = _r(np.asarray(el.get("offset", [0, 0, 0]), float) + _u(rng, j.get("offset", 0.0))
                                  - np.array([0, 0, abs(float(rng.uniform(0, float(w.get("settle", 0.0)))))]))
                if j.get("rot") or w.get("lean"):
                    extra = _u(rng, j.get("rot", 0.0)) + np.r_[_u(rng, w.get("lean", 0.0))[:2], 0.0]
                    el["rot"] = _euler_of(euler_matrix(extra) @ euler_matrix(el.get("rot", [0, 0, 0])))
                if j.get("size"):
                    el["size"] = _r(np.asarray(el.get("size", [0.05] * 3), float) * (1 + rng.uniform(-1, 1) * float(j["size"])))
            else:
                if w.get("sag"):  # bows downward in the middle, by up to `sag`
                    bw, bh = el.get("bow", [0.0, 0.0]) if not isinstance(el.get("bow"), (int, float)) else [0.0, el["bow"]]
                    el["bow"] = [float(bw), float(bh) - float(rng.uniform(0.5, 1.0)) * float(w["sag"])]
                off = _u(rng, j.get("offset", 0.0)) - np.array([0, 0, abs(float(rng.uniform(0, float(w.get("settle", 0.0)))))])
                own = all(joint_users.get(el[e], 0) == 1 and "pos" in s["joints"].get(el[e], {}) for e in ("a", "b"))
                if np.any(off) and own:  # only a bone with its own joints moves (shared joints hold a skeleton)
                    for e in ("a", "b"):
                        s["joints"][el[e]]["pos"] = _r(np.asarray(s["joints"][el[e]]["pos"], float) + off)
                if j.get("size"):
                    f = 1 + rng.uniform(-1, 1) * float(j["size"])
                    for e, rk in (("a", "r_a"), ("b", "r_b")):
                        r = el.get(rk) if el.get(rk) is not None else s["joints"][el[e]].get("r", 0.05)
                        el[rk] = round(float(r) * f, 6)


# ---- selection -------------------------------------------------------------------------------------------------

def select(s: dict, names, kinds=("bones", "blobs")) -> list[str]:
    """Element names for a list of names: each an element, or a tag (instances, arrays and "tags"), in `s`
    (an expanded spec). Unknown names are returned as they are, for the caller to report."""
    out = []
    for n in ([names] if isinstance(names, str) else names):
        # an array's first copy keeps the array's name, which is also the tag of every copy: take both
        hits = [e for k in kinds for e, el in s.get(k, {}).items() if e == n or n in (el.get("tags") or [])]
        out += hits if hits else [n]
    return list(dict.fromkeys(out))
