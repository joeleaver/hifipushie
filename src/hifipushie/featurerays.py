"""Rays through a model's field from a matched camera (matched.py's format): the first surface each pixel sees, as
a depth image, and a grey relief of it. featuresee.py measures features with these; a flat reference view and a
fitted perspective camera are the same kind of camera here.

`first_hit` samples the field every 0.7 voxel along each ray and interpolates the crossing. The compiled kernel
(numba) and the numpy march below it are the same sampling; HIFIPUSHIE_JIT=0 or no numba uses numpy, some 10-50 x
slower (the march was three quarters of a feature report's time).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import matched, sdf

CHUNK = 2500  # rays per numpy lookup


def rays(cam: dict, xy: np.ndarray):
    D, Fw, R, U = matched.axes(cam["az"], cam["el"], cam["roll"])
    C = np.asarray(cam["aim"], float) + cam["dist"] * D
    W, H = cam["size"]
    f = cam["f_px"]
    return C, Fw[None] + ((xy[:, 0] - W / 2) / f)[:, None] * R[None] - ((xy[:, 1] - H / 2) / f)[:, None] * U[None], Fw


_MARCH = None


def _march_kernel():
    """The compiled ray march (numba), or False without numba / with HIFIPUSHIE_JIT=0: the numpy march below is
    the same sampling, some 50 x slower (a 40-feature report: minutes instead of seconds)."""
    global _MARCH
    if _MARCH is None:
        import os
        _MARCH = False
        if os.environ.get("HIFIPUSHIE_JIT", "1") != "0":
            try:
                from numba import njit

                @njit(cache=True)
                def march(field, origin, voxel, C, d, zs, out):
                    nx, ny, nz = field.shape
                    for r in range(d.shape[0]):
                        pf, pz, hit = 1.0, zs[0], np.inf
                        for k in range(zs.shape[0]):
                            z = zs[k]
                            x = (C[0] + z * d[r, 0] - origin[0]) / voxel
                            y = (C[1] + z * d[r, 1] - origin[1]) / voxel
                            w = (C[2] + z * d[r, 2] - origin[2]) / voxel
                            if x < 0 or y < 0 or w < 0 or x > nx - 1 or y > ny - 1 or w > nz - 1:
                                f = 1.0
                            else:
                                i, j, m = min(int(x), nx - 2), min(int(y), ny - 2), min(int(w), nz - 2)
                                a, b, c = x - i, y - j, w - m
                                f = ((field[i, j, m] * (1 - a) + field[i + 1, j, m] * a) * (1 - b)
                                     + (field[i, j + 1, m] * (1 - a) + field[i + 1, j + 1, m] * a) * b) * (1 - c) + (
                                    (field[i, j, m + 1] * (1 - a) + field[i + 1, j, m + 1] * a) * (1 - b)
                                    + (field[i, j + 1, m + 1] * (1 - a) + field[i + 1, j + 1, m + 1] * a) * b) * c
                            if f < 0:
                                hit = z if k == 0 else pz + min(max(pf / max(pf - f, 1e-9), 0.0), 1.0) * (z - pz)
                                break
                            pf, pz = f, z
                        out[r] = hit
                _MARCH = march
            except Exception:  # noqa: BLE001  (no numba, or it can't compile here: the numpy march)
                _MARCH = False
    return _MARCH


def first_hit(grid: sdf.Grid, cam: dict, xy: np.ndarray) -> np.ndarray:
    """Camera depth of the first surface along each pixel's ray through the grid (inf: none), to a fraction of a voxel."""
    C, d, Fw = rays(cam, xy)
    n = np.array(grid.field.shape)
    corners = grid.origin + grid.voxel * (n - 1) * np.array([[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
    z = (corners - C) @ Fw
    zs = np.arange(max(z.min() - grid.voxel, 1e-3), z.max() + grid.voxel, grid.voxel * 0.7)
    out = np.full(len(xy), np.inf)
    march = _march_kernel() if min(grid.field.shape) >= 2 else False
    if march:
        march(np.ascontiguousarray(grid.field, np.float64), np.asarray(grid.origin, np.float64), float(grid.voxel),
              np.asarray(C, np.float64), np.ascontiguousarray(d, np.float64), zs, out)
        return out
    for a in range(0, len(xy), CHUNK):
        P = C + zs[None, :, None] * d[a:a + CHUNK, None, :]
        idx = ((P - grid.origin) / grid.voxel).reshape(-1, 3).T
        f = ndimage.map_coordinates(grid.field, idx, order=1, mode="constant", cval=1.0).reshape(P.shape[:2])
        inside = f < 0
        hit = inside.any(1)
        k = inside.argmax(1)
        i = np.where(hit)[0]
        k0 = np.maximum(k[i] - 1, 0)
        f0, f1 = f[i, k0], f[i, k[i]]
        t = np.where(k[i] > 0, f0 / np.maximum(f0 - f1, 1e-9), 1.0)
        out[a + i] = zs[k0] + np.clip(t, 0, 1) * (zs[k[i]] - zs[k0])
    return out


def depth_image(grid: sdf.Grid, cam: dict, box=None) -> np.ndarray:
    W, H = cam["size"]
    x0, y0, x1, y1 = box or (0, 0, W, H)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    return first_hit(grid, cam, np.stack([xs.ravel() + 0.5, ys.ravel() + 0.5], 1)).reshape(ys.shape)


def relief(depth: np.ndarray, m_per_px: float) -> np.ndarray:
    """A grey shaded picture (H, W, uint8) of a depth image, lit from the upper left front; white where empty."""
    d = np.where(np.isfinite(depth), depth, np.nan)
    fill = np.where(np.isnan(d), np.nanmax(d) if np.isfinite(d).any() else 0.0, d)
    fill = ndimage.gaussian_filter(fill, 0.8)
    gy, gx = np.gradient(fill)
    n = np.dstack([gx / m_per_px, -gy / m_per_px, -np.ones_like(fill)])   # camera frame: right, up, toward the eye = -z
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    light = np.array([-0.45, 0.55, -0.70])
    light /= np.linalg.norm(light)
    sh = 0.25 + 0.75 * np.clip(n @ light, 0, 1)
    out = np.where(np.isnan(d), 255, 40 + 190 * sh)
    return out.astype(np.uint8)
