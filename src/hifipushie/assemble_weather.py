"""Weather on instances and elements. Part of assemble (assemble.py has the spec)."""
from __future__ import annotations

import copy

import numpy as np

from .spec import euler_matrix
from .assemble import _euler_of, _r

def _weathered(insts: dict, weather: list) -> dict:
    insts = copy.deepcopy(insts)
    for d in insts.values():  # "on" instances may give only [x, y]: their z is found later
        at = d.get("at")
        if isinstance(at, list) and len(at) == 2:
            d["at"] = [*at, 0.0]
    for i, w in enumerate(weather):
        _weather_instances(insts, w, i)
    return insts


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
