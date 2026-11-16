"""`expand`: a spec's prefabs, instances, arrays, walls and scatter made into its own blobs; placements. Part of assemble (assemble.py has the spec)."""
from __future__ import annotations

import copy

import numpy as np

from . import assemble, outline
from .spec import SpecError, euler_matrix
from .assemble_arrays import _arrays, _place
from .assemble_place import _place_on, _scatter
from .assemble_shapes import _deformed, _style_shape, _walls
from .assemble_weather import _weather_elements, _weathered

def expand(spec: dict) -> dict:
    """The spec with instances and arrays expanded (a new dict; the input is left alone). Cached by content."""
    if not spec.get("instances") and not _has_arrays(spec) and not spec.get("weather") and not spec.get("walls") \
            and not (spec.get("style") or {}).get("shape") and not spec.get("scatter") and not _has_text(spec):
        return spec
    import hashlib
    import json
    key = hashlib.sha1(json.dumps(spec, sort_keys=True, default=float).encode()).hexdigest()
    if key not in assemble._CACHE:
        if len(assemble._CACHE) > 16:
            k = next(iter(assemble._CACHE))
            assemble._CACHE.pop(k)
            assemble._ON.pop(k, None)
            assemble._SCATTERED.pop(k, None)
            assemble.NOTES.pop(k, None)
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
        outline.expand_text(s)  # a "text" blob set as one "outline" blob per letter
        assemble._SCATTERED[key] = _scatter(s, insts)
        insts = {**insts, **_weathered(assemble._SCATTERED[key], weather)}
        assemble._ON[key] = _place_on(s, {i: d for i, d in insts.items() if "on" in d}, insts)
        s.pop("instances", None)
        s.pop("scatter", None)
        s.pop("prefabs", None)
        s.pop("_arrays_of", None)
        assemble.NOTES[key] = s.pop("_notes", [])
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
        assemble._CACHE[key] = s
    return copy.deepcopy(assemble._CACHE[key])


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
        on = assemble._ON.get(key, {})
        extra.update(copy.deepcopy(assemble._SCATTERED.get(key, {})))
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


def _has_text(spec: dict) -> bool:
    return any(el.get("shape") == "text" for el in (spec.get("blobs") or {}).values())


def _has_arrays(spec: dict) -> bool:
    return any("array" in el or "between" in el for kind in ("bones", "blobs") for el in (spec.get(kind) or {}).values())
