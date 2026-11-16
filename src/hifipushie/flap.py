"""A flap made as a modeller makes a clay ear: a thick, tapering lump standing on its base, its top folded over.

The lump: it grows from `base` (a point on the mass it grows from) along `rise`, `length` metres long laid flat,
`width` across at its base and `thickness` through it there (clay ears are thick: 0.6 of the width by default),
narrowing toward the tip by `pointed`. Its broad face looks toward `face` (made square to `rise`). The fold: at
`fold_at` (0..1) of its length the top bends over toward its face by `fold` degrees.

It is two round cones with an oval cross-section (bones, "flat" and "up"), base to fold and fold to tip, joined
as one group: the fold is the round knuckle where they meet. Joints "<stem>_root", "<stem>_fold", "<stem>_top", "<stem>_tip";
bones "<mass>" (the standing part, which carries the tool's own numbers under "flap") and "<stem>_top" (the
folded part). Why: three points of an arch (root, over, tip) made every ear an upside-down U with a hole under
it (blind trials p6 to p9), and a thin sheet folded hard read as a strap and tore at its crease; a modeller
blocks the ear's lump, then folds it.
"""
from __future__ import annotations

import numpy as np

SINK = 0.6  # the root goes this part of its own radius into the mass it grows from


def parts(mass: str) -> tuple[str, dict, str]:
    """(stem, joint names, the folded part's bone name) for a flap called `mass` ("ear.L" -> "ear", ... ".L")."""
    side = mass[-2:] if mass.endswith((".L", ".R")) else ""
    stem = mass[:-2] if side else mass
    return stem, {k: f"{stem}_{k}{side}" for k in ("root", "fold", "top", "tip")}, f"{stem}_top{side}"


def lump(mass: str, base, rise, face, length: float, width: float, thickness: float, fold_at: float, fold: float,
         pointed: float) -> dict:
    """{"joints", "bones", "face", "rise", "hinge", "tip"} (world positions) for the module's flap."""
    R = np.asarray(rise, float)
    R = R / np.linalg.norm(R)
    F = np.asarray(face, float) - (np.asarray(face, float) @ R) * R
    if np.linalg.norm(F) < 0.2:
        raise ValueError("face is where the flap's broad face looks: it has to be away from the way it rises (an ear "
                         "rising up looks forward, not up)")
    F = F / np.linalg.norm(F)
    th = np.radians(float(fold))
    ra = width / 2.0
    flat = [1.0, float(thickness) / float(width)]
    rf = ra * (1 - 0.45 * pointed)
    rt = max(ra * (1 - 0.9 * pointed), 0.15 * ra)
    root = np.asarray(base, float) - SINK * ra * flat[1] * R
    hinge = np.asarray(base, float) + max(fold_at * length - rf * flat[1], 0.3 * length) * R
    D = np.cos(th) * R + np.sin(th) * F  # the folded part's direction
    up2 = -np.sin(th) * R + np.cos(th) * F  # its thickness direction, turned with it
    tip = hinge + max((1 - fold_at) * length, 1.2 * rt) * D
    # a round cone's end cap is not flattened: it stands rf past its joint along the bone, and two of them met at the
    # fold as a ball. Each part ends short of the fold by what its cap overshoots the clay's own thickness there.
    over = (1 - flat[1]) * rf
    end1, start2 = hinge - over * R, hinge + over * D
    stem, J, top = parts(mass)
    r3 = lambda p: [round(float(x), 4) for x in p]  # noqa: E731
    joints = {J["root"]: {"pos": r3(root), "r": round(ra, 4)}, J["fold"]: {"pos": r3(end1), "r": round(rf, 4)},
              J["top"]: {"pos": r3(start2), "r": round(rf, 4)}, J["tip"]: {"pos": r3(tip), "r": round(rt, 4)}}
    group = f"flap:{stem}{mass[-2:] if mass.endswith(('.L', '.R')) else ''}"
    bones = {mass: {"a": J["root"], "b": J["fold"], "r_a": round(ra, 4), "r_b": round(rf, 4), "flat": flat,
                    "up": r3(F), "group": group, "join": round(0.6 * rf * flat[1], 4)},
             top: {"a": J["top"], "b": J["tip"], "r_a": round(rf, 4), "r_b": round(rt, 4), "flat": flat,
                   "up": r3(up2), "group": group, "join": round(0.6 * rf * flat[1], 4)}}
    return {"joints": joints, "bones": bones, "face": F, "rise": R, "hinge": hinge, "tip": tip}
