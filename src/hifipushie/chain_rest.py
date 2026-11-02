"""REST: a stiff ring comes to rest on the body (C280). The band's start ring is drawn through the neck's landmarks (the
tape loop up the neck); the band is longer than that loop, so drawn there it floats round the neck: level, up to the jaw,
and holding the shirt's centre-front neck high (the front edge under it read +2.7 % off its cut). A stiff ring longer than
the neck slides down it until it rests on the high points (the trapezius at the sides, the collarbones in front): the
lowest pose, as a rigid body, that keeps every point at least `gap` off the body: dropped, and tipped front-down about
the line through the side necks (on cf_shirt: tipped 16 deg, CF 21 mm lower, CB 13 mm higher; the top line 11 -> 27 deg,
README 31). Rigid: the ring's own shape and lengths
are untouched; only where it sits changes."""
from __future__ import annotations

import numpy as np

DROP_MAX = 0.08  # m: how far the ring may slide down from its start
TILT_MAX = 40.0  # deg: front down about the side necks, at most (the neck base's own tilt is ~30; README collar top line 31)


def pose(B: np.ndarray, pivot: np.ndarray, drop: float, tilt: float) -> np.ndarray:
    """B rotated front-down by `tilt` (rad) about the x axis through `pivot`, then lowered by `drop` (m)."""
    r = B - pivot
    c, s = np.cos(tilt), np.sin(tilt)
    return pivot + np.c_[r[:, 0], r[:, 1] * c - r[:, 2] * s, r[:, 2] * c + r[:, 1] * s] - [0.0, 0.0, drop]


def rest_ring(B: np.ndarray, contact, gap: float, pivot: np.ndarray, step: float = 0.002) -> tuple[np.ndarray, dict]:
    """The rest pose of the rigid ring B (n x 3) on the body: least mean height over (drop, tilt about `pivot`) with every
    point >= gap off the body (or as far off as the start already was, if that is less: the caller's solve then pushes it
    out). A start inside the body is returned as it is."""
    g0 = float(contact.query(B)[0].min())
    if g0 <= 0:
        return B, {"rested": False, "why": "start inside the body"}
    gap = min(gap, g0)
    best, bz, bd, bt = B, float(B[:, 2].mean()), 0.0, 0.0
    for t in np.radians(np.arange(0.0, TILT_MAX + 0.1, 1.0)):
        for d in np.arange(0.0, DROP_MAX + 1e-9, step):
            P = pose(B, pivot, d, t)
            if contact.query(P)[0].min() < gap:
                break  # lower still only goes further in
            if P[:, 2].mean() < bz - 1e-6:
                best, bz, bd, bt = P, float(P[:, 2].mean()), float(d), float(t)
    return best, {"rested": True, "gap_mm": round(gap * 1e3, 1), "drop_mm": round(bd * 1e3, 1), "tilt_deg": round(float(np.degrees(bt)), 1)}
