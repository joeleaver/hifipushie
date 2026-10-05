"""Vegetation meshes: branch tubes from a grown skeleton, and the stand-in leaf shapes instanced on it.

Tubes: one per axis, rings at its nodes (parallel-transported frames), sides by the axis's girth, starting at the
node it grew from (inside the parent's tube). Per vertex: `axis`, `order`, `along` (0 at the axis's root, 1 at its
tip), `radius`: what wind data, LODs and bark UVs are built from later.
"""

from __future__ import annotations

import math

import numpy as np


def tubes(tree: dict, sides=(3, 12), min_radius: float = 0.0, collar: float = 1.9) -> dict:
    P, par, rad, ax, order = tree["pos"], tree["parent"], tree["radius"], tree["axis"], tree["order"]
    n = len(P)
    idx = np.argsort(ax[1:], kind="stable") + 1  # nodes by axis, in growth order within one
    bounds = np.flatnonzero(np.diff(ax[idx], prepend=-1, append=-2))
    rmax = float(rad[1:].max()) if n > 1 else 1.0
    Vs, Fs, At, Ts = [], [], [], []
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
        if collar and root > 0 and order[nodes[0]] > 0:  # a collar: the branch swells into its parent
            d0 = pts[1] - pts[0]
            L0 = np.linalg.norm(d0)
            rp = rad[root]
            s1 = min(rp * 1.05, 0.45 * L0)
            s2 = min(rp * 1.05 + 2.5 * r0, 0.8 * L0)
            if s2 > s1 > 1e-6:
                pts = np.vstack([pts[0], pts[0] + d0 * (s1 / L0), pts[0] + d0 * (s2 / L0), pts[1:]])
                rr = np.concatenate([[min(rp, r0 * collar)], [min(rp, r0 * (1 + 0.55 * (collar - 1)))], [r0 * 1.04], rr[1:]])
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
        Ts.append(np.vstack([np.repeat(tan, k, axis=0), tan[-1:]]))
        base += len(V)
    if not Vs:
        return {"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "axis": np.zeros(0), "order": np.zeros(0),
                "along": np.zeros(0), "radius": np.zeros(0), "tan": np.zeros((0, 3))}
    At = np.vstack(At)
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "axis": At[:, 0], "order": At[:, 1], "along": At[:, 2],
            "radius": At[:, 3], "tan": np.vstack(Ts)}
