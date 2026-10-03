"""Triangle focus for the export's decimation: space magnified round a few spheres before the collapse and put back
after it, so the quadric error there counts k times more and the collapse leaves more triangles (the lids and lips
of a face with face shapes: a blink moves the lid an eye radius, and on the plain low poly the skin round it showed
facets). Blender's Decimate vertex group was tried first: any weight protects its vertices outright (measured on a
subdivided Suzanne: factor 0.01 kept all 6569 of them and broke the ratio), so it can't grade.

Each sphere [x, y, z, R, k] is a radial map r -> r (1 + (k - 1) exp(-(r / R)^2)) about its centre, monotonic for
k < 3.2; spheres are applied in turn (each centre taken where the previous ones moved it) and undone in reverse,
each by Newton on the radius. numpy only: blender_asset.py imports this too.

The focus's triangles come ON TOP of the export's budget (blender_asset.lowpoly): the parts' budgets are shared out
by what each would have taken unfocused (`gain`, `unfocused`), then a focused part gets its focus multiplier on top.
Shared out by the focused counts, the face took its extra from everything else (Garrett: jacket 2,771 -> 2,035
triangles at a higher budget)."""

from __future__ import annotations

import numpy as np


def _g(r, R, k):
    return 1 + (k - 1) * np.exp(-(r / R) ** 2)


def centres(spheres) -> list:
    """Each sphere's centre in the space it is applied in (moved by the spheres before it)."""
    out = []
    for i, s in enumerate(spheres):
        c = np.asarray(s[:3], float)[None]
        for (cx, cy, cz), (_, _, _, R, k) in zip(out, spheres[:i]):
            q = c - [cx, cy, cz]
            r = np.linalg.norm(q, axis=1)
            c = [cx, cy, cz] + q * _g(r, R, k)[:, None]
        out.append(np.asarray(c, float).ravel())
    return out


def warp(P: np.ndarray, spheres) -> np.ndarray:
    P = np.asarray(P, np.float64).copy()
    for c, (_, _, _, R, k) in zip(centres(spheres), spheres):
        q = P - c
        r = np.linalg.norm(q, axis=1)
        P = c + q * _g(r, R, k)[:, None]
    return P


def unwarp(P: np.ndarray, spheres) -> np.ndarray:
    P = np.asarray(P, np.float64).copy()
    for c, (_, _, _, R, k) in reversed(list(zip(centres(spheres), spheres))):
        q = P - c
        rp = np.linalg.norm(q, axis=1)
        r = rp / k  # Newton on f(r) = r g(r) - rp, from inside
        r = np.minimum(r, rp)
        for _ in range(40):
            e = np.exp(-(r / R) ** 2)
            f = r * (1 + (k - 1) * e) - rp
            df = 1 + (k - 1) * e * (1 - 2 * (r / R) ** 2)
            r = r - f / df
        P = c + q * (r / np.maximum(rp, 1e-15))[:, None]
    return P


def gain(Pw: np.ndarray, F: np.ndarray, spheres) -> np.ndarray:
    """Each triangle's linear magnification (sqrt of its area warped / put back): 1 away from the spheres."""
    Pw = np.asarray(Pw, np.float64)
    Pu = unwarp(Pw, spheres)

    def area(P):
        return 0.5 * np.linalg.norm(np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]), axis=1)
    return np.sqrt(np.maximum(area(Pw), 1e-30) / np.maximum(area(Pu), 1e-30))


def unfocused(gains: np.ndarray) -> float:
    """How many triangles these would have been without the focus: at one quadric error a surface magnified g x
    takes ~g x the triangles (area g^2, curvature 1/g, edge length ~ sqrt(error / curvature)), so each counts 1/g."""
    return float(np.sum(1.0 / np.clip(gains, 1.0, None)))
