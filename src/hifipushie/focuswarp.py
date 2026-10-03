"""Triangle focus for the export's decimation: space magnified round a few spheres before the collapse and put back
after it, so the quadric error there counts k times more and the collapse leaves more triangles (the lids and lips
of a face with face shapes: a blink moves the lid an eye radius, and on the plain low poly the skin round it showed
facets). Blender's Decimate vertex group was tried first: any weight protects its vertices outright (measured on a
subdivided Suzanne: factor 0.01 kept all 6569 of them and broke the ratio), so it can't grade.

Each sphere [x, y, z, R, k] is a radial map r -> r (1 + (k - 1) exp(-(r / R)^2)) about its centre, monotonic for
k < 3.2; spheres are applied in turn (each centre taken where the previous ones moved it) and undone in reverse,
each by Newton on the radius. numpy only: blender_asset.py imports this too.

The focus's triangles come ON TOP of the export's budget (blender_asset.lowpoly): the joint collapse is run a second
time on the mesh put back, only to count what each part takes unfocused; budgets are shared out by those counts, then
a focused part gets its focused / unfocused ratio on top. Shared out by the focused counts, the face took its extra
from everything else (Garrett: jacket 2,771 -> 1,532 triangles at 15k). (A per-triangle estimate from the warp's
magnification, sum of 1 / gain, missed most of it.)"""

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

