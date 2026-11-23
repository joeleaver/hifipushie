"""Hard surface from the point cloud: the fused sculpt as a SOLID you can ask "is this point inside?".

The fused sculpt (oxidegen make_point_cloud's mesh_ply, or any watertight mesh) is voxelised once into an occupancy grid
by z-column ray parity (numba): every column's crossings with the surface, sorted, filled between pairs. After that
`inside(P)` is a lookup, so the fitters can ask millions of points (votes round an axis, across a width) in a second.

- `Solid(mesh_or_path, step=0.003)`: the grid; `inside(P)` -> bool per point (outside the grid = False).
- `section_mask(axis, value, window, step)`: occupancy of the plane axis=value over a 2D window of the other two axes.
- `votes(origin, axis, t0, t1, rmax, step, angles, sector)`: fraction of angles round an axis at which each (t, r) cell
  is solid (the turned-part fit's evidence).
- `width_vote(axis, values, window, step)`: fraction of parallel sections in which each cell is solid (a sweep's evidence).
- helpers: `basis(n)`, `circle_fit_2d(P)`.
Units are the sculpt's (metres once framed). The sculpt must be closed: an open mesh voxelises with streaks (check
`Mesh.edges_open() == 0`)."""
from __future__ import annotations

import math

import numpy as np
from numba import njit

from .artretopo_mesh import Mesh


def basis(n):
    """an orthonormal frame (n, u, v) round a direction; u is horizontal unless n is near vertical"""
    n = np.asarray(n, float); n = n / np.linalg.norm(n)
    u = np.cross(n, [0, 0, 1] if abs(n[2]) < 0.9 else [1, 0, 0]); u /= np.linalg.norm(u); v = np.cross(n, u)
    return n, u, v


def circle_fit_2d(p):
    """least-squares circle through 2D points -> (centre (2,), radius, mean abs error)"""
    p = np.asarray(p, float)
    A = np.c_[2 * p, np.ones(len(p))]; b = (p ** 2).sum(1)
    c = np.linalg.lstsq(A, b, rcond=None)[0]; r = math.sqrt(max(c[2] + c[0] ** 2 + c[1] ** 2, 0.0))
    return c[:2], r, float(np.abs(np.linalg.norm(p - c[:2], axis=1) - r).mean())


@njit(cache=True)
def _column_hits(T, x0, y0, s, nx, ny):
    """for every triangle, the z where each column centre (inside its xy footprint) crosses it.
    Two passes: count per column, then fill a flat array (CSR by column)."""
    cnt = np.zeros(nx * ny, np.int64)
    ex, ey = 0.37e-4 * s, 0.53e-4 * s           # column centres nudged off the exact grid: no ties on shared edges
    for pas in range(2):
        if pas == 1:
            start = np.zeros(nx * ny + 1, np.int64)
            for k in range(nx * ny): start[k + 1] = start[k] + cnt[k]
            zs = np.empty(start[-1], np.float64); fillp = start[:-1].copy()
        for t in range(T.shape[0]):
            ax, ay, az = T[t, 0, 0], T[t, 0, 1], T[t, 0, 2]
            bx, by, bz = T[t, 1, 0], T[t, 1, 1], T[t, 1, 2]
            cx, cy, cz = T[t, 2, 0], T[t, 2, 1], T[t, 2, 2]
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-18: continue
            i0 = max(int(math.floor((min(ax, bx, cx) - x0) / s - 0.5)), 0); i1 = min(int(math.ceil((max(ax, bx, cx) - x0) / s - 0.5)), nx - 1)
            j0 = max(int(math.floor((min(ay, by, cy) - y0) / s - 0.5)), 0); j1 = min(int(math.ceil((max(ay, by, cy) - y0) / s - 0.5)), ny - 1)
            for i in range(i0, i1 + 1):
                px = x0 + (i + 0.5) * s + ex
                for j in range(j0, j1 + 1):
                    py = y0 + (j + 0.5) * s + ey
                    w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
                    w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
                    w2 = 1.0 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0: continue
                    k = i * ny + j
                    if pas == 0: cnt[k] += 1
                    else:
                        zs[fillp[k]] = w0 * az + w1 * bz + w2 * cz; fillp[k] += 1
    return start, zs


@njit(cache=True)
def _fill(start, zs, z0, s, nx, ny, nz, occ):
    for i in range(nx):
        for j in range(ny):
            k = i * ny + j; a, b = start[k], start[k + 1]
            if b - a < 2: continue
            z = np.sort(zs[a:b])
            for q in range(0, (b - a) - 1, 2):
                k0 = max(int(math.ceil((z[q] - z0) / s - 0.5)), 0); k1 = min(int(math.floor((z[q + 1] - z0) / s - 0.5)), nz - 1)
                for kk in range(k0, k1 + 1): occ[i, j, kk] = True


class Solid:
    def __init__(self, mesh, step: float = 0.003, pad: float = 0.01):
        m = mesh if isinstance(mesh, Mesh) else Mesh.load(mesh)
        self.mesh = m; self.step = s = float(step)
        lo, hi = m.bounds(); self.lo = lo - pad
        self.n = np.ceil((hi + pad - self.lo) / s).astype(int)
        if int(np.prod(self.n)) > 400_000_000:
            raise ValueError(f"occupancy grid {self.n.tolist()} at step {s} is too big: coarsen the step")
        T = m.V[m.F].astype(np.float64)
        start, zs = _column_hits(T, self.lo[0], self.lo[1], s, int(self.n[0]), int(self.n[1]))
        self.occ = np.zeros(tuple(self.n), np.bool_)
        _fill(start, zs, self.lo[2], s, int(self.n[0]), int(self.n[1]), int(self.n[2]), self.occ)
        odd = int(((start[1:] - start[:-1]) % 2 == 1).sum())
        self.odd_columns = odd                      # columns with an odd crossing count: holes in the mesh (should be ~0)

    def inside(self, P) -> np.ndarray:
        P = np.asarray(P, float); shp = P.shape[:-1]; P = P.reshape(-1, 3)
        ijk = np.floor((P - self.lo) / self.step).astype(np.int64)
        ok = np.all((ijk >= 0) & (ijk < self.n), 1); out = np.zeros(len(P), bool)
        out[ok] = self.occ[ijk[ok, 0], ijk[ok, 1], ijk[ok, 2]]
        return out.reshape(shp)

    # ---- the evidence the fitters read
    def section_mask(self, axis: str, value: float, window, step: float = 0.003):
        """occupancy of the plane axis=value over window (a0, a1, b0, b1) of the other two axes (in xyz order).
        Returns (A, B, M, (i, j, k)): the sample positions along each in-plane axis, the bool mask, the axis indices."""
        i = "xyz".index(axis); j, k = [q for q in range(3) if q != i]
        A = np.arange(window[0], window[1], step); B = np.arange(window[2], window[3], step)
        G = np.zeros((len(A), len(B), 3)); G[..., i] = value; G[..., j] = A[:, None]; G[..., k] = B[None, :]
        return A, B, self.inside(G), (i, j, k)

    def width_vote(self, axis: str, values, window, step: float = 0.006):
        """mean occupancy over several parallel sections (a sweep's profile: what most of the width agrees on)"""
        acc = None
        for v in values:
            A, B, M, ax = self.section_mask(axis, v, window, step)
            acc = M.astype(float) if acc is None else acc + M
        return A, B, acc / len(values), ax

    def votes(self, origin, axis, t0, t1, rmax, step=0.003, angles=36, sector=None):
        """fraction of `angles` directions round the axis at which each (t, r) cell is solid"""
        n, u, v = basis(axis); o = np.asarray(origin, float)
        ts = np.arange(t0, t1 + 1e-9, step); rs = np.arange(step / 2, rmax, step)
        a0, a1 = (0.0, 2 * np.pi) if sector is None else (math.radians(sector[0]), math.radians(sector[1]))
        an = np.linspace(a0, a1, angles, endpoint=sector is not None)
        T, Rr, A = np.meshgrid(ts, rs, an, indexing="ij")
        P = o + T[..., None] * n + Rr[..., None] * (np.cos(A)[..., None] * u + np.sin(A)[..., None] * v)
        return ts, rs, self.inside(P).mean(2)
