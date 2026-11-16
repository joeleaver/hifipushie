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
         pointed: float, lobe_thickness: float | None = None, tip=None, flare: float = 0.0) -> dict:
    """{"joints", "bones", "face", "rise", "hinge", "tip"} (world positions) for the module's flap.
    lobe_thickness: the folded part's own thickness (a pig's ear: a fat rolled lobe on a thinner stalk).
    tip: [x, y, z] where the tip should hang: the fold's direction, angle and the folded part's length follow from
    it (fold is then ignored). face None with a tip: the broad face turns toward the tip (the fold bends square to
    it); face given with a tip: the standing part keeps that face and the fold leans off it toward the tip (e15
    could not have both: an ear broad from the front whose tip hangs forward AND out).
    flare: metres the root swells into what it grows from, a soft collar of clay round its foot (0 none): a clay
    ear's root is smoothed into the head, not stuck on as a stalk (e15).
    (Blind runs e9 to e12 asked for both. They also asked for a base broad from the side, a wedge: that was a
    misreading of the side view, where the broad shape is the lobe hanging forward and the root is the ear's edge;
    built, it made the root long front to back, the opposite of the concept, e13 / e14. Removed.)"""
    R = np.asarray(rise, float)
    R = R / np.linalg.norm(R)
    hinge = np.asarray(base, float) + fold_at * length * R
    L2 = (1 - fold_at) * length
    if tip is not None:
        v = np.asarray(tip, float) - hinge
        if np.linalg.norm(v) < 1e-3:
            raise ValueError("tip is where the tip hangs: put it away from the fold")
        D0 = v / np.linalg.norm(v)
        perp = D0 - (D0 @ R) * R
        if np.linalg.norm(perp) < 0.05:
            raise ValueError("tip lies straight up the way the flap rises: then it isn't folded (leave tip out, fold=0)")
        L2 = float(np.linalg.norm(v))
        fold = float(np.degrees(np.arccos(np.clip(D0 @ R, -1, 1))))
        if face is None:
            face = perp
    if face is None:
        face = [0.0, -1.0, 0.0]
    F = np.asarray(face, float) - (np.asarray(face, float) @ R) * R
    if np.linalg.norm(F) < 0.2:
        raise ValueError("face is where the flap's broad face looks: it has to be away from the way it rises (an ear "
                         "rising up looks forward, not up)")
    F = F / np.linalg.norm(F)
    th = np.radians(float(fold))
    ra = width / 2.0
    flat = [1.0, float(thickness) / float(width)]
    flat2 = [1.0, (float(lobe_thickness) / float(width)) if lobe_thickness else 0.75 * flat[1]]
    rf = ra * (1 - 0.45 * pointed)
    rt = max(ra * (1 - 0.9 * pointed), 0.15 * ra)
    root = np.asarray(base, float) - SINK * ra * flat[1] * R
    if tip is not None:
        D = D0  # the folded part goes where the tip was put
        A = np.cross(R, D)
        up2 = np.cross(A / np.linalg.norm(A), D)  # its thickness: square to it, in the plane it bent in
        up2 = up2 / np.linalg.norm(up2)
    else:
        D = np.cos(th) * R + np.sin(th) * F  # the folded part's direction
        up2 = -np.sin(th) * R + np.cos(th) * F  # its thickness direction, turned with it
    tip = hinge + max(L2, 1.2 * rt) * D
    # a round cone's end cap is not flattened: it stands rf past its joint along the bone, and two of them met at the
    # fold as a ball. Each part ends short of the fold by what its cap overshoots the clay's own thickness there.
    end1, start2 = hinge - (1 - flat[1]) * rf * R, hinge + (1 - flat2[1]) * rf * D
    stem, J, top = parts(mass)
    side = mass[-2:] if mass.endswith((".L", ".R")) else ""
    r3 = lambda p: [round(float(x), 4) for x in p]  # noqa: E731
    joints = {J["root"]: {"pos": r3(root), "r": round(ra, 4)}, J["fold"]: {"pos": r3(end1), "r": round(rf, 4)},
              J["top"]: {"pos": r3(start2), "r": round(rf, 4)}, J["tip"]: {"pos": r3(tip), "r": round(rt, 4)}}
    group = f"flap:{stem}{side}"
    join = round(0.6 * rf * max(flat[1], flat2[1]), 4)
    bones = {mass: {"a": J["root"], "b": J["fold"], "r_a": round(ra, 4), "r_b": round(rf, 4), "flat": flat,
                    "up": r3(F), "group": group, "join": join},
             top: {"a": J["top"], "b": J["tip"], "r_a": round(rf, 4), "r_b": round(rt, 4), "flat": flat2,
                   "up": r3(up2), "group": group, "join": join}}
    if flare > 0:  # a low collar round the foot, blended in on its own (a group blends in by one blend only)
        top_c = np.asarray(base, float) + 0.25 * fold_at * length * R
        joints[f"{stem}_foot{side}"] = {"pos": r3(root), "r": round(ra, 4)}
        joints[f"{stem}_collar{side}"] = {"pos": r3(top_c), "r": round(ra * 0.9, 4)}
        bones[f"{stem}_foot{side}"] = {"a": f"{stem}_foot{side}", "b": f"{stem}_collar{side}", "r_a": round(ra, 4),
                                       "r_b": round(0.85 * ra, 4), "flat": [1.0, min(1.0, 1.15 * flat[1])],
                                       "up": r3(F), "blend": round(float(flare), 4)}
    return {"joints": joints, "bones": bones, "face": F, "rise": R, "hinge": hinge, "tip": tip, "toward": D,
            "fold": float(fold), "lengths": (float(np.linalg.norm(hinge - np.asarray(base, float))),
                                             float(np.linalg.norm(tip - hinge)))}
