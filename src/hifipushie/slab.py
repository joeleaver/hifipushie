"""Slab: a flat outline of clay with rounded edges, folded over along a line: a pig's or dog's ear, a tab, a fin.

How a modeller makes one: draw the outline flat (a triangle with rounded corners), give it a thickness that thins
toward the tip, round its edges, then fold its top over. Blob keys (the `flap` tool writes them):

    {"shape": "slab", "at", "offset",            # the middle of its base (where it grows from)
     "rise": [x, y, z],                           # the way it stands (unit; ".R" mirrors it)
     "face": [x, y, z],                           # the way its broad face looks (made square to rise)
     "length": m, "width": m,                     # base to tip laid flat; across the base
     "tip_width": m,                              # across the tip end (0 a point, = width a strip)
     "thickness": m, "tip_thickness": m,          # through it at the base and at the tip
     "fold": degrees, "fold_at": 0..1}            # its top folds toward its face, at that part of its length

The outline is an isosceles trapezoid (base width to tip width over the length), every corner rounded by the
local half thickness, so its edge is a rounded rim; the section is that trapezoid swept through its thickness.
The fold: the flat slab's top part is turned by `fold` about a hinge line across the slab at fold_at, the hinge on
the face side's surface, so the folded part lies on the face side and a 180 degree fold lays it flat against the
standing part. A point is unfolded before the flat slab is measured: below the hinge it stays, past the folded
part's start it is turned back, and in the wedge between them (the knuckle) it is unrolled round the hinge, which
keeps the clay's full thickness round the bend (a swept sheet thinned and tore there).
"""
from __future__ import annotations

import numpy as np


def params(c, rise, face, length, width, tip_width, thickness, tip_thickness, fold, fold_at) -> tuple[dict, np.ndarray, np.ndarray]:
    """(params, lo, hi) for a slab whose base middle is c."""
    R = np.asarray(rise, float)
    R = R / np.linalg.norm(R)
    F = np.asarray(face, float) - (np.asarray(face, float) @ R) * R
    if np.linalg.norm(F) < 0.2:
        raise ValueError("a slab's face has to look away from the way it rises")
    F = F / np.linalg.norm(F)
    U = np.cross(R, F)
    # the base is sunk into the mass it grows from by its own thickness, so its corners meet a curved head instead
    # of standing off it (the outline widens on below the base at its own slope)
    sink = float(thickness)
    L = float(length) + sink
    w0 = float(width) / 2 + (float(width) - float(tip_width)) / 2 * sink / float(length)
    t0 = float(thickness) / 2 + (float(thickness) - float(tip_thickness)) / 2 * sink / float(length)
    pr = {"c": np.asarray(c, float) - sink * R, "M": np.stack([U, R, F]), "L": L, "w0": w0,
          "w1": float(tip_width) / 2, "t0": t0, "t1": float(tip_thickness) / 2,
          "th": float(np.radians(fold)), "vf": float(fold_at) * float(length) + sink}
    ext = float(length) + float(width) + float(thickness)
    return pr, pr["c"] - ext, pr["c"] + ext


def _flat(u, v, n, pr):
    """The flat slab: trapezoid outline in (u, v), v from 0 (base) to L, rounded rim, tapering thickness."""
    L, w0, w1 = pr["L"], pr["w0"], pr["w1"]
    s = np.clip(v / L, 0.0, 1.0)
    t = pr["t0"] + (pr["t1"] - pr["t0"]) * s  # half thickness here
    # the outline shrunk by the rim's radius (t), then grown back round: a rounded rim all round
    he = L / 2
    py = v - he
    px = np.abs(u)
    r1, r2 = max(w0 - pr["t0"], 1e-4), max(w1 - pr["t1"], 1e-4)
    he_c = max(he - 0.5 * (pr["t0"] + pr["t1"]), 1e-4)
    # iq's isosceles trapezoid (r1 at y = -he, r2 at y = +he)
    k1 = np.array([r2, he_c])
    k2 = np.array([r2 - r1, 2.0 * he_c])
    cax = np.stack([px - np.minimum(px, np.where(py < 0, r1, r2)), np.abs(py) - he_c], -1)
    q = np.stack([px, py], -1)
    h = np.clip(((k1 - q) @ k2) / (k2 @ k2), 0.0, 1.0)
    cb = q - k1 + h[..., None] * k2
    sgn = np.where((cb[..., 0] < 0) & (cax[..., 1] < 0), -1.0, 1.0)
    d2 = sgn * np.sqrt(np.minimum((cax ** 2).sum(-1), (cb ** 2).sum(-1)))
    # the section: the shrunk outline swept by a ball of radius t (a rounded slab of half thickness t)
    return np.hypot(np.maximum(d2, 0.0), n) - t


def sd_slab(p: np.ndarray, pr: dict) -> np.ndarray:
    q = (p - pr["c"]) @ pr["M"].T  # (u, v, n)
    u, v, n = q[..., 0], q[..., 1], q[..., 2]
    th, vf = pr["th"], pr["vf"]
    if th < 1e-6:
        return _flat(u, v, n, pr)
    # the hinge: across the slab at v = vf, on the face side's surface there
    tf = pr["t0"] + (pr["t1"] - pr["t0"]) * min(vf / pr["L"], 1.0)
    av, an = vf, tf
    dv, dn = v - av, n - an
    c, s = np.cos(th), np.sin(th)
    # three pieces, each the flat slab cut by its own half-space, joined: the standing part (below the hinge), the
    # folded part (turned back by -th about the hinge, past it) and the knuckle (unrolled round the hinge). (Telling a
    # point's piece by its region alone misses a fold past 90 degrees, whose folded part lies below the hinge too.)
    bv, bn = c * dv + s * dn, -s * dv + c * dn
    # each piece cut by planes through the hinge, so the three meet exactly along them: the knuckle is the wedge
    # between the standing part's cut (dv = 0) and the folded part's (bv = 0). (Cut by an angle penalty, or overlapped
    # and joined smoothly, the seams showed as dotted lines and raised beads.)
    standing = np.maximum(_flat(u, v, n, pr), dv)
    folded = np.maximum(_flat(u, av + bv, an + bn, pr), -bv)
    rho = np.hypot(dv, dn)
    knuckle = np.maximum(np.maximum(_flat(u, np.full_like(v, av), an - rho, pr), -dv), bv)
    return np.minimum(np.minimum(standing, folded), knuckle)
