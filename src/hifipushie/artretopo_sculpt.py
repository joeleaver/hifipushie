"""Artist retopo: the sculpt the cage is drawn on, with the questions an artist asks of it.

`Sculpt(path)` wraps artretopo_mesh.Mesh. Coordinates are the sculpt's own: z up, the character faces -y, its left is
+x, mirror plane x = 0, metres-ish (a fused concept spans about one unit).
- `slice(origin, normal, u, v)`: the regions where a plane cuts it, in (u, v) (artretopo_poly.Poly).
- `hit(origin, d, last=False)`: the first (or last) surface point along a ray; ValueError if it misses.
- `front(x, z)` / `back(x, z)` / `top(x, y)` / `bottom(x, y)` / `side(sign, y, z)`: the first surface met looking
  from outside along an axis (from beyond the bounding box).
- `crease(x, z_lo, z_hi)`: the deepest point of a crease on the front at x (a lip line under an overhanging lip).
- `centre_of(z, pick)`: the centre (0, y) of the horizontal region nearest pick: a body ring's centre on the mirror plane.
- `closest(points)`, `normal_at(point)`: nearest surface point(s) / that triangle's outward normal.
- `extreme(lo, hi, direction)`: the vertex furthest along a direction inside a box: where a horn or an ear REALLY ends.
- `fit_sphere(points)`: centre, radius, rms of a least-squares sphere (eyes rebuilt as primitives)."""
from __future__ import annotations

import numpy as np

from .artretopo_mesh import Mesh


class Sculpt:
    def __init__(self, path_or_mesh):
        self.m = path_or_mesh if isinstance(path_or_mesh, Mesh) else Mesh.load(path_or_mesh)
        lo, hi = self.m.bounds(); self.lo, self.hi = lo, hi
        self.far = float(np.linalg.norm(hi - lo)) + 1.0          # rays start this far outside

    # ---- slices
    def slice(self, origin, normal, u, v):
        return self.m.section(origin, normal, u, v)

    def centre_of(self, z, pick=(0.0, 0.0)):
        from .artretopo_poly import Poly  # noqa: F401  (regions are Polys)
        ps = self.slice((0, 0, z), (0, 0, 1), (1, 0, 0), (0, 1, 0))
        if not ps:
            raise ValueError(f"no slice at z={z}")
        return (0.0, float(min(ps, key=lambda p: p.distance(pick)).centroid[1]))

    # ---- rays
    def hit(self, origin, d, last=False):
        t = self.m.rays(origin, d)
        if not len(t):
            raise ValueError(f"ray {tuple(np.round(origin, 4))} {tuple(np.round(d, 3))} misses the sculpt")
        d = np.asarray(d, float); d = d / np.linalg.norm(d)
        return np.asarray(origin, float) + d * (t[-1] if last else t[0])

    def front(self, x, z):
        return self.hit((x, self.lo[1] - self.far, z), (0, 1, 0))

    def back(self, x, z):
        return self.hit((x, self.hi[1] + self.far, z), (0, -1, 0))

    def top(self, x, y):
        return self.hit((x, y, self.hi[2] + self.far), (0, 0, -1))

    def bottom(self, x, y):
        return self.hit((x, y, self.lo[2] - self.far), (0, 0, 1))

    def side(self, sign, y, z):
        """from beyond +x (sign 1) or -x (sign -1), looking in"""
        return self.hit((sign * (max(abs(self.lo[0]), abs(self.hi[0])) + self.far), y, z), (-sign, 0, 0))

    def crease(self, x, z_lo, z_hi):
        """the deepest point of a horizontal crease on the FRONT in the plane x = const between heights z_lo and z_hi
        (a lip line under an overhanging upper lip, a chin fold): where the front profile reaches furthest back (+y)"""
        zm = (z_lo + z_hi) / 2; fy = self.front(x, zm)[1]
        polys = self.slice((x, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        P = min(polys, key=lambda p: p.distance((fy, zm))).exterior
        sel = P[(P[:, 1] >= z_lo) & (P[:, 1] <= z_hi) & (P[:, 0] < fy + 0.06)]
        if not len(sel):
            raise ValueError(f"no front profile at x = {x} between z {z_lo} and {z_hi}")
        q = sel[np.argmax(sel[:, 0])]
        return np.array([x, q[0], q[1]])

    # ---- nearest
    def closest(self, pts):
        return self.m.closest(pts)[0]

    def normal_at(self, p):
        _, tri = self.m.closest([p])
        return self.m.face_normals[tri[0]]

    def extreme(self, lo_box, hi_box, direction):
        V = self.m.V; lo_, hi_ = np.asarray(lo_box), np.asarray(hi_box)
        sel = np.all((V >= lo_) & (V <= hi_), axis=1)
        if not sel.any():
            raise ValueError(f"no sculpt vertex in the box {lo_box} .. {hi_box}")
        return V[sel][np.argmax(V[sel] @ np.asarray(direction, float))]

    # ---- colour (eyes, props: pick their vertices by colour)
    def verts_near(self, centre, radius, rgb=None, tol=60):
        """sculpt vertices within radius of centre, optionally only those whose colour is within tol of rgb (0-255)"""
        V = self.m.V; sel = np.linalg.norm(V - np.asarray(centre, float), axis=1) < radius
        if rgb is not None and self.m.C is not None:
            sel &= np.abs(self.m.C[:, :3].astype(int) - np.asarray(rgb)).max(1) < tol
        return V[sel]


def fit_sphere(points):
    """(centre, radius, rms) of the least-squares sphere through points"""
    P = np.asarray(points, float)
    if len(P) < 4:
        raise ValueError("fit_sphere needs at least 4 points")
    A = np.c_[2 * P, np.ones(len(P))]; b = (P ** 2).sum(1)
    x, *_ = np.linalg.lstsq(A, b, rcond=None); c = x[:3]; R = float(np.sqrt(x[3] + c @ c))
    rms = float(np.sqrt(((np.linalg.norm(P - c, axis=1) - R) ** 2).mean()))
    return c, R, rms
