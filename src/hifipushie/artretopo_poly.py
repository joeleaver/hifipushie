"""Artist retopo: 2D outlines (a slice of the sculpt in its own plane). Plain numpy, no shapely.

A `Poly` is one filled region of a slice: an exterior loop and any holes, each an (n, 2) array (not repeated at the
end). The cage tools ask it four things: does it hold a point, how far is a point, where is its centroid, and where
does a ray from a point first leave its exterior. `even` resamples the exterior by length (ring_even).
`polygons(loops)` sorts a slice's closed loops into regions: a loop inside an odd number of others is a hole of the
smallest loop round it."""
from __future__ import annotations

import numpy as np


def area(loop: np.ndarray) -> float:
    """signed (counter-clockwise > 0)"""
    x, y = loop[:, 0], loop[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def inside(loop: np.ndarray, p) -> bool:
    """even-odd test of a point against one loop"""
    x, y = loop[:, 0], loop[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    px, py = float(p[0]), float(p[1])
    cross = (y > py) != (y2 > py)
    with np.errstate(divide="ignore", invalid="ignore"):
        xi = x + (py - y) * (x2 - x) / (y2 - y)
    return bool(np.count_nonzero(cross & (px < xi)) % 2)


def seg_dist(loop: np.ndarray, p) -> float:
    """distance from a point to a loop's edges"""
    a = loop; b = np.roll(loop, -1, axis=0); p = np.asarray(p, float)
    ab = b - a; L2 = np.maximum((ab * ab).sum(1), 1e-30)
    t = np.clip(((p - a) * ab).sum(1) / L2, 0, 1)
    q = a + ab * t[:, None]
    return float(np.sqrt(((q - p) ** 2).sum(1)).min())


def _centroid_area(loop):
    x, y = loop[:, 0], loop[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cr = x * y2 - x2 * y
    A = cr.sum() / 2
    if abs(A) < 1e-30:
        return loop.mean(0), 0.0
    return np.array([((x + x2) * cr).sum(), ((y + y2) * cr).sum()]) / (6 * A), A


class Poly:
    def __init__(self, exterior: np.ndarray, holes=()):
        self.exterior = np.asarray(exterior, float)
        self.holes = [np.asarray(h, float) for h in holes]

    @property
    def area(self) -> float:
        return abs(area(self.exterior)) - sum(abs(area(h)) for h in self.holes)

    @property
    def centroid(self) -> np.ndarray:
        c, A = _centroid_area(self.exterior); A = abs(A); acc = c * A; tot = A
        for h in self.holes:
            ch, Ah = _centroid_area(h); Ah = abs(Ah); acc = acc - ch * Ah; tot -= Ah
        return acc / tot if tot > 1e-30 else c

    def contains(self, p) -> bool:
        return inside(self.exterior, p) and not any(inside(h, p) for h in self.holes)

    def distance(self, p) -> float:
        """0 inside, else the distance to the nearest edge (exterior or hole)"""
        if self.contains(p):
            return 0.0
        return min([seg_dist(self.exterior, p)] + [seg_dist(h, p) for h in self.holes])

    def ray_exit(self, c, d, reach: float = 5.0):
        """the exterior crossing nearest to c along the ray c + t d (t in [0, reach]); None if it misses"""
        c = np.asarray(c, float); d = np.asarray(d, float); d = d / np.linalg.norm(d)
        a = self.exterior; b = np.roll(a, -1, axis=0); e = b - a
        den = d[0] * e[:, 1] - d[1] * e[:, 0]            # cross(d, e)
        w = a - c
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (w[:, 0] * e[:, 1] - w[:, 1] * e[:, 0]) / den
            s = (w[:, 0] * d[1] - w[:, 1] * d[0]) / den
        ok = (np.abs(den) > 1e-18) & (t >= 0) & (t <= reach) & (s >= 0) & (s <= 1)
        if not ok.any():
            return None
        return c + d * t[ok].min()

    def even(self, n: int, start_dir, ccw: bool = True) -> np.ndarray:
        """n points evenly by length round the exterior, from where it lies furthest along start_dir, counter-
        clockwise (ccw) in the plane's (u, v)"""
        ring = self.exterior
        if (area(ring) > 0) != ccw:
            ring = ring[::-1]
        k0 = int(np.argmax((ring - ring.mean(0)) @ np.asarray(start_dir, float)))
        ring = np.vstack([ring[k0:], ring[:k0], ring[k0:k0 + 1]])
        seg = np.sqrt((np.diff(ring, axis=0) ** 2).sum(1)); cum = np.concatenate([[0], np.cumsum(seg)])
        out = []
        for k in range(n):
            s = cum[-1] * k / n; i = min(int(np.searchsorted(cum, s, side="right")) - 1, len(seg) - 1)
            f = (s - cum[i]) / seg[i] if seg[i] > 0 else 0.0
            out.append(ring[i] + f * (ring[i + 1] - ring[i]))
        return np.asarray(out)


def polygons(loops: list[np.ndarray]) -> list[Poly]:
    """closed loops of one slice -> filled regions (holes go to the smallest loop round them)"""
    loops = [np.asarray(l, float) for l in loops if len(l) >= 3]
    A = [abs(area(l)) for l in loops]
    parents = []
    for i, l in enumerate(loops):
        p = l[0]
        parents.append([j for j, m in enumerate(loops) if j != i and A[j] > A[i] and inside(m, p)])
    out, holes = {}, {}
    for i, ps in enumerate(parents):
        if len(ps) % 2 == 0:
            out[i] = []
    for i, ps in enumerate(parents):
        if len(ps) % 2 == 1:
            host = min((j for j in ps if j in out), key=lambda j: A[j], default=None)
            if host is not None:
                out[host].append(loops[i])
    return [Poly(loops[i], hs) for i, hs in out.items()]


def _selftest():
    sq = np.array([[0, 0], [2, 0], [2, 2], [0, 2]], float)
    hole = np.array([[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5]], float)
    P = polygons([sq, hole])
    assert len(P) == 1 and len(P[0].holes) == 1 and abs(P[0].area - 3) < 1e-12
    assert P[0].contains((0.2, 0.2)) and not P[0].contains((1, 1))
    assert np.allclose(P[0].ray_exit((1, 0.2), (1, 0)), (2, 0.2))
    assert np.allclose(P[0].even(4, (1, 0))[0], (2, 0)) or np.allclose(P[0].even(4, (1, 0))[0], (2, 2))
