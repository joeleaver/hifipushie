"""A flap made as a modeller makes a clay ear: a thick, tapering lump standing on its base, its top bent over.

The lump: it grows from `base` (a point on the mass it grows from) along `rise`, `length` metres long laid flat,
`width` across at its base and `thickness` through it there, narrowing toward the tip by `pointed`. Its broad
face looks toward `face` (made square to `rise`). It is one bone, "<mass>", on joints "<stem>_root" and
"<stem>_tip" (the tip as if it stood straight).

The fold is a bend (bend.py), "flap:<mass>": from `fold_at` of its length the lump is carried round an arc of
`fold` degrees toward its face, of radius `round` (the bend's softness: the rim over the top; default 0.6 of the thickness, so the inside
of the fold is a cup, not a crease), and the rest goes
on straight. Bending keeps the clay's thickness and squeezes the inside of the fold into a cup.

Why: two cones meeting at a knuckle peaked at the fold every time (blind runs e13 to e17); before that, three points
of an arch made an upside-down U with a hole under it (p6 to p9), and a thin sheet folded hard read as a strap.
A modeller blocks the ear's lump straight, then bends its top over.
"""
from __future__ import annotations

import numpy as np

SINK = 0.6  # the root goes this part of its own radius into the mass it grows from
ARC_POINTS = 7


def parts(mass: str) -> tuple[str, dict, str]:
    """(stem, joint names, the bend's label) for a flap called `mass` ("ear.L" -> "ear", ... ".L")."""
    side = mass[-2:] if mass.endswith((".L", ".R")) else ""
    stem = mass[:-2] if side else mass
    return stem, {k: f"{stem}_{k}{side}" for k in ("root", "tip")}, f"flap:{mass}"


def lump(mass: str, base, rise, face, length: float, width: float, thickness: float, fold_at: float, fold: float,
         pointed: float, round_: float | None = None, flare: float = 0.0) -> dict:
    """{"joints", "bones", "bend" (None unfolded), "face", "rise", "hinge", "end", "round"} for the module's flap."""
    from . import bend
    R = np.asarray(rise, float)
    R = R / np.linalg.norm(R)
    F = np.asarray(face, float) - (np.asarray(face, float) @ R) * R
    if np.linalg.norm(F) < 0.2:
        raise ValueError("face is where the flap's broad face looks: it has to be away from the way it rises (an ear "
                         "rising up looks forward, not up)")
    F = F / np.linalg.norm(F)
    b0 = np.asarray(base, float)
    ra = width / 2.0
    flat = [1.0, float(thickness) / float(width)]
    rt = max(ra * (1 - 0.9 * pointed), 0.15 * ra)
    root = b0 - SINK * ra * flat[1] * R
    top = b0 + length * R - rt * R  # the tip's round cap reaches the full length
    stem, J, label = parts(mass)
    side = mass[-2:] if mass.endswith((".L", ".R")) else ""
    r3 = lambda p: [round(float(x), 4) for x in p]  # noqa: E731
    joints = {J["root"]: {"pos": r3(root), "r": round(ra, 4)}, J["tip"]: {"pos": r3(top), "r": round(rt, 4)}}
    bones = {mass: {"a": J["root"], "b": J["tip"], "r_a": round(ra, 4), "r_b": round(rt, 4), "flat": flat, "up": r3(F)}}
    if flare > 0:  # a low collar round the foot, blended in on its own
        top_c = b0 + 0.15 * length * R
        joints[f"{stem}_foot{side}"] = {"pos": r3(root), "r": round(ra, 4)}
        joints[f"{stem}_collar{side}"] = {"pos": r3(top_c), "r": round(ra * 0.9, 4)}
        bones[f"{stem}_foot{side}"] = {"a": f"{stem}_foot{side}", "b": f"{stem}_collar{side}", "r_a": round(ra, 4),
                                       "r_b": round(0.85 * ra, 4), "flat": [1.0, min(1.0, 1.15 * flat[1])],
                                       "up": r3(F), "blend": round(float(flare), 4)}
    hinge = b0 + fold_at * length * R
    rest = (1 - fold_at) * length
    th = np.radians(float(fold))
    out = {"joints": joints, "bones": bones, "bend": None, "face": F, "rise": R, "hinge": hinge,
           "end": b0 + length * R, "round": 0.0, "toward": R}
    if th <= 1e-3:
        return out
    rr = float(round_) if round_ is not None else 0.6 * float(thickness)
    rr = min(rr, 0.8 * rest / th)  # the arc can't be longer than what there is to bend
    ts = np.linspace(0.0, th, ARC_POINTS)
    path = [hinge - 0.2 * rr * R] + [hinge + rr * np.sin(t) * R + rr * (1 - np.cos(t)) * F for t in ts]  # (a first
    # step along the lump's own line: the path's start direction is its first step, and the arc's first chord leans)
    D = np.cos(th) * R + np.sin(th) * F
    path.append(path[-1] + 0.25 * max(rest - rr * th, 0.01) * D)  # a little straight on: the path's end turned
    g = bend.geometry(path, normal=F)
    out["bend"] = {"of": [mass], "path": [r3(p) for p in path], "normal": r3(F)}
    out["end"] = bend.forward(g, (b0 + length * R)[None])[0]
    out["round"] = rr
    out["toward"] = D
    return out
