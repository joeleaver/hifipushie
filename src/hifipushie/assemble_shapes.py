"""Shapes: walls and their openings, a style's shape, deformed blobs. Part of assemble (assemble.py has the spec)."""
from __future__ import annotations

import numpy as np

from . import assemble
from .spec import SpecError
from .assemble import _r

def _walls(s: dict) -> None:
    """spec["walls"] -> ordinary blobs (a box, or a row of boards, per straight run), box cuts for the openings
    (targeted at the wall only) and instances: a frame and a window in each opening, a door hung on its hinge.
    Everything is tagged with the wall's name; openings are named "<wall>_<name or i>"."""
    walls = s.pop("walls", None) or {}
    for wn, w in walls.items():
        where = f"wall {wn!r}"
        bad = set(w) - assemble.WALL_KEYS
        if bad:
            raise SpecError(f"{where}: unknown keys {sorted(bad)} (allowed: {sorted(assemble.WALL_KEYS)})")
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
    bad = set(op) - assemble.OPENING_KEYS
    if bad:
        raise SpecError(f"{where}: unknown keys {sorted(bad)} (allowed: {sorted(assemble.OPENING_KEYS)})")
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
    bad = set(st) - set(assemble.STYLE_SHAPE)
    if bad:
        raise SpecError(f"style.shape: unknown keys {sorted(bad)} (have {', '.join(assemble.STYLE_SHAPE)})")
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
