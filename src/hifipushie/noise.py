"""Solid 3D value noise (world space: no UV seams), shared by paint and by lumpy surfaces in the field."""

from __future__ import annotations

import numpy as np


def _hash(ix, iy, iz, seed: int) -> np.ndarray:
    """Pseudo-random 0..1 per integer lattice point."""
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = h.astype(np.uint64)
    h ^= h >> np.uint64(13)
    h *= np.uint64(0x5bd1e995)
    h ^= h >> np.uint64(15)
    return (h & np.uint64(0xFFFFFF)).astype(np.float64) / float(0xFFFFFF)


def _value_noise(p: np.ndarray, seed: int) -> np.ndarray:
    i = np.floor(p).astype(np.int64)
    f = p - i
    u = f * f * f * (f * (f * 6 - 15) + 10)  # quintic fade: no creases at lattice planes
    out = np.zeros(len(p))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (np.where(dx, u[:, 0], 1 - u[:, 0]) * np.where(dy, u[:, 1], 1 - u[:, 1])
                     * np.where(dz, u[:, 2], 1 - u[:, 2]))
                out += w * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out


def _rotations(n: int) -> list[np.ndarray]:
    rng = np.random.default_rng(7)
    out = []
    for _ in range(n):
        q, r = np.linalg.qr(rng.normal(size=(3, 3)))
        out.append(q * np.sign(np.diag(r)))
    return out


_ROT = _rotations(8)


def fbm(p: np.ndarray, scale: float, octaves: int = 3, seed: int = 0) -> np.ndarray:
    """Fractal value noise in 0..1 (mean ~0.5) with features about `scale` across."""
    out, amp, total = np.zeros(len(p)), 1.0, 0.0
    q = p / scale
    for o in range(max(1, octaves)):  # each octave on its own rotated lattice: no axis-aligned blocks
        out += amp * _value_noise(q @ _ROT[o % len(_ROT)] * (2 ** o), seed + 101 * o)
        total += amp
        amp *= 0.5
    # summed octaves bunch up around 0.5; stretch back to roughly 0..1
    return np.clip(0.5 + (out / total - 0.5) * (1.0 + 0.6 * (octaves - 1)), 0, 1)
