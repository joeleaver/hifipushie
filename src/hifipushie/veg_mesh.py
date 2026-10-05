"""Vegetation meshes: branch tubes from a grown skeleton, and the stand-in leaf shapes instanced on it.

Tubes: one per axis, rings at its nodes (parallel-transported frames), sides by the axis's girth, starting at the
node it grew from (inside the parent's tube). Per vertex: `axis`, `order`, `along` (0 at the axis's root, 1 at its
tip), `radius`: what wind data, LODs and bark UVs are built from later.
"""

from __future__ import annotations

import math

import numpy as np


def tubes(tree: dict, sides=(3, 12), min_radius: float = 0.0) -> dict:
    P, par, rad, ax, order = tree["pos"], tree["parent"], tree["radius"], tree["axis"], tree["order"]
    n = len(P)
    idx = np.argsort(ax[1:], kind="stable") + 1  # nodes by axis, in growth order within one
    bounds = np.flatnonzero(np.diff(ax[idx], prepend=-1, append=-2))
    rmax = float(rad[1:].max()) if n > 1 else 1.0
    Vs, Fs, At = [], [], []
    base = 0
    for a, b in zip(bounds[:-1], bounds[1:]):
        nodes = idx[a:b]
        r0 = rad[nodes[0]]
        if r0 < min_radius:
            continue
        k = int(np.clip(round(sides[0] + (sides[1] - sides[0]) * math.sqrt(r0 / rmax)), sides[0], sides[1]))
        root = par[nodes[0]]
        pts = np.vstack([P[root], P[nodes]])
        rr = np.concatenate([[min(r0 * 1.15, rad[root]) if root > 0 else r0], rad[nodes]])
        m = len(pts)
        t = np.diff(pts, axis=0)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
        tan = np.vstack([t[0], t[:-1] + t[1:], t[-1]]) if m > 2 else np.vstack([t[0], t[-1]])
        tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-12)
        ref = np.array([1.0, 0, 0]) if abs(tan[0, 2]) > 0.9 else np.array([0, 0, 1.0])
        u = np.cross(tan[0], ref)
        u /= np.linalg.norm(u)
        U = np.empty((m, 3))
        U[0] = u
        for i in range(1, m):  # parallel transport
            u = u - tan[i] * (u @ tan[i])
            nu = np.linalg.norm(u)
            u = u / nu if nu > 1e-9 else U[i - 1]
            U[i] = u
        W = np.cross(tan, U)
        ang = np.arange(k) * (2 * math.pi / k)
        ring = U[:, None, :] * np.cos(ang)[None, :, None] + W[:, None, :] * np.sin(ang)[None, :, None]
        V = pts[:, None, :] + ring * rr[:, None, None]
        V = np.vstack([V.reshape(-1, 3), pts[-1] + tan[-1] * rr[-1] * 1.5])  # + a tip point
        i0 = (np.arange(m - 1)[:, None] * k + np.arange(k)[None, :])
        i1 = (np.arange(m - 1)[:, None] * k + (np.arange(k)[None, :] + 1) % k)
        quads = np.stack([i0, i1, i1 + k, i0 + k], -1).reshape(-1, 4)
        last = (m - 1) * k
        tip = np.stack([last + np.arange(k), last + (np.arange(k) + 1) % k, np.full(k, m * k)], 1)
        Fs.append(np.vstack([quads[:, [0, 1, 2]], quads[:, [0, 2, 3]], tip]) + base)
        seg = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        al = np.repeat(seg / max(seg[-1], 1e-9), k)
        at = np.empty((m * k + 1, 4))
        at[:-1, 0] = ax[nodes[0]]
        at[:-1, 1] = order[nodes[0]]
        at[:-1, 2] = al
        at[:-1, 3] = np.repeat(rr, k)
        at[-1] = [ax[nodes[0]], order[nodes[0]], 1.0, rr[-1]]
        Vs.append(V)
        At.append(at)
        base += len(V)
    if not Vs:
        return {"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "axis": np.zeros(0), "order": np.zeros(0),
                "along": np.zeros(0), "radius": np.zeros(0)}
    At = np.vstack(At)
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "axis": At[:, 0], "order": At[:, 1], "along": At[:, 2],
            "radius": At[:, 3]}


def leaf_proto(kind: str) -> tuple[np.ndarray, np.ndarray]:
    """Stand-in leaf shapes (unit length along +y, flat side up +z) until stage 2 makes real leaves and twigs."""
    if kind == "broad":
        V = np.array([[0, 0, 0], [-0.3, 0.35, 0.05], [0, 0.4, 0], [0.3, 0.35, 0.05], [-0.22, 0.75, 0.03], [0.22, 0.75, 0.03],
                      [0, 1.0, -0.04], [0, 0.75, -0.02]], float)
        F = np.array([[0, 2, 1], [0, 3, 2], [1, 2, 7], [1, 7, 4], [2, 3, 5], [2, 5, 7], [4, 7, 6], [7, 5, 6]])
        return V, F
    if kind == "strap":
        ys = np.linspace(0, 1, 5)
        w = 0.07 * np.sin(np.pi * np.clip(ys * 0.9 + 0.08, 0, 1))
        z = -0.25 * ys ** 2
        V = np.vstack([np.c_[-w, ys, z], np.c_[w, ys, z]])
        F = []
        for i in range(4):
            F += [[i, i + 5, i + 6], [i, i + 6, i + 1]]
        return V, np.array(F)
    if kind in ("needle_tuft", "needle_spray"):
        V, F = [], []
        rng = np.random.default_rng(5)
        cnt = 26 if kind == "needle_tuft" else 24
        for j in range(cnt):
            if kind == "needle_tuft":  # a bottle brush round the shoot
                a = 2 * math.pi * j / cnt * 3.1
                y0 = 0.15 + 0.7 * j / cnt
                d = np.array([math.cos(a) * 0.75, 0.65, math.sin(a) * 0.75])
            else:  # a flat comb either side of the shoot
                y0 = 0.05 + 0.9 * (j // 2) / (cnt // 2)
                d = np.array([(1 if j % 2 else -1) * 0.8, 0.55, -0.1 + 0.1 * rng.random()])
            d /= np.linalg.norm(d)
            side = np.cross(d, [0, 1, 0.3])
            side /= np.linalg.norm(side)
            p0 = np.array([0, y0, 0])
            L, w = 0.32, 0.02
            b = len(V)
            V += [p0 - side * w, p0 + side * w, p0 + d * L]
            F += [[b, b + 1, b + 2]]
        V += [[-0.02, 0, 0], [0.02, 0, 0], [0, 1, 0]]
        F += [[len(V) - 3, len(V) - 2, len(V) - 1]]
        return np.array(V, float), np.array(F)
    raise ValueError(f"leaf type {kind!r}: broad, strap, needle_tuft or needle_spray")


def leaf_frames(L: dict) -> np.ndarray:
    """Each leaf's 3x3 frame (columns x, y = its long axis, z = its upper side)."""
    y = L["dir"]
    z = L["normal"]
    x = np.cross(y, z)
    x /= np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)
    z = np.cross(x, y)
    return np.stack([x, y, z], axis=2)
