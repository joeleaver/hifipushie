"""Vegetation meshes: branch tubes from a grown skeleton.

Tubes: one per axis, rings at its nodes (parallel-transported frames), sides by the axis's girth. A branch is seated
on its parent: its first ring is a flared collar whose vertices are carried back along the branch onto the parent's
surface (the fork's saddle line), so the branch grows out of the wood instead of poking through it (`weld`). Shoot
ends taper (`tip`). Per vertex: `axis`, `order`, `along` (0 at the axis's root, 1 at its tip), `radius`, `tan` (the
branch's direction) and `uv` (u round the branch in whole repeats of the bark tile, v along it in tiles; a seam
column is doubled): what wind data, LODs and bark are built from.
"""

from __future__ import annotations

import math

import numpy as np


def tubes(tree: dict, sides=(3, 12), min_radius: float = 0.0, collar: float = 1.9, weld: bool = True,
          tip: float = 0.45, tile=(0.5, 1.0)) -> dict:
    P, par, rad, ax, order = tree["pos"], tree["parent"], tree["radius"], tree["axis"], tree["order"]
    n = len(P)
    idx = np.argsort(ax[1:], kind="stable") + 1  # nodes by axis, in growth order within one
    bounds = np.flatnonzero(np.diff(ax[idx], prepend=-1, append=-2))
    rmax = float(rad[1:].max()) if n > 1 else 1.0
    ends = tree.get("ends")
    Vs, Fs, At, Ts, Us = [], [], [], [], []
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
        if ends is not None and ends[nodes[-1]] and tip < 1:  # a shoot's end tapers
            rr[-1] *= tip
        seated = False
        if collar and root > 0 and order[nodes[0]] > 0:  # a collar: the branch swells into its parent
            d0 = pts[1] - pts[0]
            L0 = np.linalg.norm(d0)
            rp = rad[root]
            s1 = min(rp * 1.05, 0.45 * L0)
            s2 = min(rp * 1.05 + 2.5 * r0, 0.8 * L0)
            if s2 > s1 > 1e-6:
                pts = np.vstack([pts[0], pts[0] + d0 * (s1 / L0), pts[0] + d0 * (s2 / L0), pts[1:]])
                rr = np.concatenate([[min(rp, r0 * collar)], [min(rp, r0 * (1 + 0.55 * (collar - 1)))], [r0 * 1.04], rr[1:]])
                seated = weld
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
        ang = np.arange(k + 1) * (2 * math.pi / k)  # (the last column doubles the first: the uv seam)
        ring = U[:, None, :] * np.cos(ang)[None, :, None] + W[:, None, :] * np.sin(ang)[None, :, None]
        V = pts[:, None, :] + ring * rr[:, None, None]
        if seated:  # carry the first ring back along the branch onto the parent's surface
            pa = P[root] - P[par[root]]
            ln = np.linalg.norm(pa)
            pa = pa / ln if ln > 1e-9 else np.array([0, 0, 1.0])
            d = tan[0]
            rp = rad[root] * 0.97
            q = V[0] - P[root]
            qp = q - np.outer(q @ pa, pa)  # across the parent's axis
            dp = d - pa * (d @ pa)
            A = dp @ dp
            if A > 1e-6:  # |qp + s dp| = rp, the root nearer the parent's far side is behind us: take the larger
                B = 2 * (qp @ dp)
                C = np.einsum("ij,ij->i", qp, qp) - rp * rp
                disc = B * B - 4 * A * C
                s = np.where(disc > 0, (-B + np.sqrt(np.maximum(disc, 0))) / (2 * A), 0.0)
                s = np.clip(s, -2 * rad[root], np.linalg.norm(pts[1] - pts[0]) * 0.9)
                V[0] = V[0] + s[:, None] * d
        V = np.vstack([V.reshape(-1, 3), pts[-1] + tan[-1] * rr[-1] * 1.5])  # + a tip point
        kk = k + 1
        i0 = (np.arange(m - 1)[:, None] * kk + np.arange(k)[None, :])
        quads = np.stack([i0, i0 + 1, i0 + 1 + kk, i0 + kk], -1).reshape(-1, 4)
        last = (m - 1) * kk
        tipf = np.stack([last + np.arange(k), last + np.arange(k) + 1, np.full(k, m * kk)], 1)
        Fs.append(np.vstack([quads[:, [0, 1, 2]], quads[:, [0, 2, 3]], tipf]) + base)
        seg = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        at = np.empty((m * kk + 1, 4))
        at[:-1, 0] = ax[nodes[0]]
        at[:-1, 1] = order[nodes[0]]
        at[:-1, 2] = np.repeat(seg / max(seg[-1], 1e-9), kk)
        at[:-1, 3] = np.repeat(rr, kk)
        at[-1] = [ax[nodes[0]], order[nodes[0]], 1.0, rr[-1]]
        # whole bark tiles round the branch, counted at its base (by its mean radius a long limb's thick end got one
        # tile stretched round it: bark scales the size of cobbles)
        nu_ = max(1, int(round(2 * math.pi * float(r0) / tile[0])))
        uv = np.empty((m * kk + 1, 2))
        uv[:-1, 0] = np.tile(np.arange(kk) / k * nu_, m)
        uv[:-1, 1] = np.repeat(seg / tile[1], kk) + (ax[nodes[0]] * 0.37) % 1.0
        uv[-1] = [0.5 * nu_, seg[-1] / tile[1]]
        Vs.append(V)
        At.append(at)
        Us.append(uv)
        Ts.append(np.vstack([np.repeat(tan, kk, axis=0), tan[-1:]]))
        base += len(V)
    if not Vs:
        return {"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "axis": np.zeros(0), "order": np.zeros(0),
                "along": np.zeros(0), "radius": np.zeros(0), "tan": np.zeros((0, 3)), "uv": np.zeros((0, 2))}
    At = np.vstack(At)
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "axis": At[:, 0], "order": At[:, 1], "along": At[:, 2],
            "radius": At[:, 3], "tan": np.vstack(Ts), "uv": np.vstack(Us)}
