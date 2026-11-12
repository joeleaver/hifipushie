"""Prefabs and arrays: placing a prefab's instance, arrays between and along, steps. Part of assemble (assemble.py has the spec)."""
from __future__ import annotations

import copy

import numpy as np

from .spec import SpecError, euler_matrix
from .assemble import _euler_of, _r, select
from .assemble_shapes import _deformed

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
