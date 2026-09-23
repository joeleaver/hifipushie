"""Repetition: prefabs placed as instances, and arrays of elements. Both expand into ordinary joints, bones and
blobs before kits and mirroring, so everything downstream (strokes, paint, parts, export) sees plain elements.

  "prefabs":   {name: {"joints": {...}, "bones": {...}, "blobs": {...}, "symmetry": false}}
               a reusable piece in its own local frame (metres, its origin where it's placed; e.g. a chair
               with its origin on the floor under the seat centre, facing -Y). "symmetry": true mirrors its
               own ".L" elements across its local X first.
  "instances": {name: {"use": prefab, "at": [x, y, z], "rot": [deg x, y, z] (0), "scale": s (1),
                       "part": name | {prefab part: part} (keep the prefab's), "tags": [...]}}
               a placed copy. Its elements are named "<instance>/<element>" and tagged with the instance
               and prefab names, so paint "near", "targets" and deletes can take "chair1" or "chair" for all
               of them. An instance named ".L" is mirrored whole (a pair of bedside tables).
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


def expand(spec: dict) -> dict:
    """The spec with instances and arrays expanded (a new dict; the input is left alone). Cached by content."""
    if not spec.get("instances") and not _has_arrays(spec) and not spec.get("weather"):
        return spec
    import hashlib
    import json
    key = hashlib.sha1(json.dumps(spec, sort_keys=True, default=float).encode()).hexdigest()
    if key not in _CACHE:
        if len(_CACHE) > 16:
            _CACHE.pop(next(iter(_CACHE)))
        s = copy.deepcopy(spec)
        weather = s.pop("weather", None) or []
        insts = s.get("instances") or {}
        insts = _weathered(insts, weather)  # instances are weathered whole (a chair leans, its legs don't wander)
        for inst, d in insts.items():
            _place(s, inst, d)
        s.pop("instances", None)
        s.pop("prefabs", None)
        s = _arrays(s)
        whole = set()
        for inst, d in insts.items():
            whole |= {inst[:-2] if inst.endswith(".L") else inst, d.get("use"), *d.get("tags", [])}
        for i, w in enumerate(weather):
            _weather_elements(s, w, i, whole)
        _CACHE[key] = s
    return copy.deepcopy(_CACHE[key])


def _weathered(insts: dict, weather: list) -> dict:
    insts = copy.deepcopy(insts)
    for i, w in enumerate(weather):
        _weather_instances(insts, w, i)
    return insts


def placements(spec: dict) -> dict:
    """Every placed instance after weathering: {instance: {"use": prefab, "at", "rot", "scale", "mirror": bool}}.
    An instance named ".L" also places its mirror image ".R" (mirror: reflected across X after the placement)."""
    out = {}
    for inst, d in _weathered(spec.get("instances") or {}, spec.get("weather") or []).items():
        pl = {"use": d["use"], "at": d.get("at", [0, 0, 0]), "rot": d.get("rot", [0, 0, 0]),
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
    return any("array" in el for kind in ("bones", "blobs") for el in (spec.get(kind) or {}).values())


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
    if local["symmetry"]:
        local = expand_mirror({**local, "symmetry": True})
    if any("on" in j for j in local["joints"].values()):
        raise SpecError(f"prefab {d['use']!r}: seated joints (\"on\") aren't supported inside prefabs")
    at = np.asarray(d.get("at", [0, 0, 0]), float)
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
                    c["size"] = _r(np.asarray(base.get("size", [0.05] * 3), float) * f)
                    c["rot"] = _euler_of(R @ euler_matrix(base.get("rot", [0, 0, 0])))
                    s["blobs"][cn] = c
    return s


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
        if any(n in s.get(k, {}) for k in kinds):
            out.append(n)
            continue
        hits = [e for k in kinds for e, el in s.get(k, {}).items() if n in (el.get("tags") or [])]
        out += hits if hits else [n]
    return list(dict.fromkeys(out))
