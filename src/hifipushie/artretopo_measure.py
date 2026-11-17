"""Artist retopo: measuring the sculpt (numbers to write the cage from; retopo_measure / retopo_fit_cylinder).

- `extreme(lo, hi, direction)`: the sculpt's furthest vertex along a direction inside a box (a horn's or an ear's
  real tip: close the tube to it).
- `ray(origin, direction)`: every surface hit along a ray, nearest first (how thick, where a surface is behind another).
- `thickness(point)`: from the surface point nearest `point`, inward along the normal to the far side: a part's local
  thickness (ears and horn tips under ~3 cm bake from both sides: the bake's thin pass is for them).
- `fit_cylinder(axis, at, pick)`: slice across the axis at each station, fit a circle to the region nearest `pick`:
  the centre line, radius, rms and per-slice radii (a held prop rebuilt as a cylinder: canister, cup, tube).
- `colour_at(point, radius)`: the mean vertex colour near a point (pick an eye's white for retopo_fit)."""
from __future__ import annotations

import numpy as np

from .artretopo_sculpt import Sculpt


def extreme(s: Sculpt, lo, hi, direction) -> dict:
    p = s.extreme(lo, hi, direction)
    return {"point": [round(float(x), 4) for x in p]}


def ray(s: Sculpt, origin, direction) -> dict:
    d = np.asarray(direction, float); d = d / np.linalg.norm(d)
    t = s.m.rays(origin, d)
    o = np.asarray(origin, float)
    return {"hits": [{"t": round(float(x), 4), "point": [round(float(v), 4) for v in o + d * x]} for x in t]}


def thickness(s: Sculpt, point) -> dict:
    q, tri = s.m.closest([point]); q = q[0]; n = s.m.face_normals[tri[0]]
    t = s.m.rays(q - n * 1e-4, -n)
    if not len(t):
        return {"surface": q.round(4).tolist(), "normal": n.round(3).tolist(), "thickness": None}
    return {"surface": q.round(4).tolist(), "normal": n.round(3).tolist(), "thickness": round(float(t[0]), 4),
            "far_side": (q - n * t[0]).round(4).tolist()}


def _circle(P):
    A = np.c_[2 * P, np.ones(len(P))]; b = (P ** 2).sum(1)
    x, *_ = np.linalg.lstsq(A, b, rcond=None); c = x[:2]; R = float(np.sqrt(x[2] + c @ c))
    return c, R, float(np.sqrt(((np.linalg.norm(P - c, axis=1) - R) ** 2).mean()))


AX = {"x": ((1, 0, 0), (0, 1, 0), (0, 0, 1)), "y": ((0, 1, 0), (1, 0, 0), (0, 0, 1)), "z": ((0, 0, 1), (1, 0, 0), (0, 1, 0))}


def fit_cylinder(s: Sculpt, axis: str, at, pick) -> dict:
    """axis x|y|z; at: stations along it; pick: (u, v) in the cross-section plane near the prop's centre
    (for axis x: (y, z); y: (x, z); z: (x, y))"""
    n, u, v = AX[axis]; k = "xyz".index(axis)
    rows, C, Rs = [], [], []
    for a in at:
        o = [0.0, 0.0, 0.0]; o[k] = float(a)
        ps = s.slice(o, n, u, v)
        if not ps:
            rows.append({"at": a, "region": None}); continue
        p = min(ps, key=lambda q: q.distance(pick))
        c, R, rms = _circle(p.exterior)
        rows.append({"at": a, "centre": [round(float(x), 4) for x in c], "R": round(R, 4), "rms": round(rms, 5)})
        C.append(c); Rs.append(R)
    if not C:
        raise ValueError("no cross-section found at any station: check axis, at and pick")
    c2 = np.mean(C, axis=0); centre = [0.0, 0.0, 0.0]
    oth = [i for i in range(3) if i != k]; centre[oth[0]], centre[oth[1]] = float(c2[0]), float(c2[1])
    centre[k] = float(np.mean([r["at"] for r in rows if "R" in r]))
    return {"axis": axis, "c": [round(x, 4) for x in centre], "R": round(float(np.median(Rs)), 4),
            "R_spread": round(float(np.max(Rs) - np.min(Rs)), 4), "slices": rows}


def colour_at(s: Sculpt, point, radius=0.01) -> dict:
    if s.m.C is None:
        return {"rgb": None}
    sel = np.linalg.norm(s.m.V - np.asarray(point, float), axis=1) < radius
    if not sel.any():
        return {"rgb": None, "points": 0}
    return {"rgb": s.m.C[sel, :3].mean(0).round().astype(int).tolist(), "points": int(sel.sum())}
