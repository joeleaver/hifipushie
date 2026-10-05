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


PROTECT = 0.25


def _rdp(pts, eps, rr) -> np.ndarray:
    """Indices of a polyline's points kept by Douglas-Peucker with a tolerance per point; a stretch is also split where
    the radius has strayed 20% from a straight taper."""
    keep = np.zeros(len(pts), bool)
    keep[[0, -1]] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        d = pts[b] - pts[a]
        L = np.linalg.norm(d)
        q = pts[a + 1:b] - pts[a]
        t = np.clip(q @ d / max(L * L, 1e-12), 0, 1)
        off = np.linalg.norm(q - t[:, None] * d, axis=1)
        dr = np.abs(rr[a + 1:b] - (rr[a] + t * (rr[b] - rr[a]))) / np.maximum(rr[a + 1:b], 1e-6)
        score = np.maximum(off / eps[a + 1:b], dr / 0.2)
        i = int(np.argmax(score))
        if score[i] > 1:
            keep[a + 1 + i] = True
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return np.flatnonzero(keep)


def tubes(tree: dict, sides=(3, 12), min_radius: float = 0.0, collar: float = 1.9, weld: bool = True,
          tip: float = 0.45, tile=(0.5, 1.0), protect=None, simplify: float = 0.0) -> dict:
    P, par, rad, ax, order = tree["pos"], tree["parent"], tree["radius"], tree["axis"], tree["order"]
    n = len(P)
    idx = np.argsort(ax[1:], kind="stable") + 1  # nodes by axis, in growth order within one
    bounds = np.flatnonzero(np.diff(ax[idx], prepend=-1, append=-2))
    rmax = float(rad[1:].max()) if n > 1 else 1.0
    ends = tree.get("ends")
    dead = tree.get("dead")
    roots = (tree.get("spec") or {}).get("roots")
    rkey = int((tree.get("spec") or {}).get("seed", 1))
    Vs, Fs, At, Ts, Us = [], [], [], [], []
    base = 0
    for a, b in zip(bounds[:-1], bounds[1:]):
        nodes = idx[a:b]
        r0 = rad[nodes[0]]
        if r0 < min_radius * (PROTECT if protect is not None and protect[nodes[0]] else 1.0):
            continue  # (`protect`: per node, axes a budget keeps down to a quarter of the cut-off: dead antlers, drawn limbs)
        k = int(np.clip(round(sides[0] + (sides[1] - sides[0]) * math.sqrt(r0 / rmax)), sides[0], sides[1]))
        root = par[nodes[0]]
        pts = np.vstack([P[root], P[nodes]])
        rr = np.concatenate([[min(r0 * 1.15, rad[root]) if root > 0 else r0], rad[nodes]])
        nid = np.concatenate([[nodes[0]], nodes])  # the node each ring belongs to (wind weights, per-node data)
        if simplify > 0 and len(pts) > 2:  # fewer rings: drop nodes the axis runs nearly straight through (within
            keep_ = _rdp(pts, simplify * np.clip(rr, 0.004, 0.12), rr)  # `simplify` x its radius), and keep its taper
            pts, rr, nid = pts[keep_], rr[keep_], nid[keep_]
        foot = root == 0 and order[nodes[0]] == 0
        n_under = 0
        if foot:  # the trunk goes into the ground (a foot on a slope shows no gap), with rings enough for its root flares
            hr = float((roots or {}).get("height", 0.0))
            zs = [z_ for z_ in (0.12 * hr, 0.3 * hr, 0.55 * hr, 0.8 * hr) if 1e-3 < z_ < pts[1][2] - 1e-3] if roots else []
            d0 = pts[1] - pts[0]
            ins = [pts[0] + d0 * (z_ / max(d0[2], 1e-6)) for z_ in zs]
            ri = [rr[0] + (rr[1] - rr[0]) * (z_ / max(d0[2], 1e-6)) for z_ in zs]
            under = float((roots or {}).get("under", 0.5 if roots else 0.3))
            pts = np.vstack([pts[0] - [0, 0, under], pts[0], *ins, pts[1:]]) if ins else np.vstack([pts[0] - [0, 0, under], pts])
            rr = np.concatenate([[rr[0] * 1.05], [rr[0]], ri, rr[1:]])
            nid = np.concatenate([[0], [0], np.zeros(len(ri), nid.dtype), nid[1:]])
            n_under = 1
            if roots:
                k = max(k, min(6 * int(roots.get("count", 5)), 40))
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
                nid = np.concatenate([[root, root, nid[0]], nid[1:]])
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
        if foot and roots:  # root flares: the section swells toward each root, most at the ground, fading up the trunk
            cnt = int(roots.get("count", 5))
            rng = np.random.default_rng(rkey + 77)
            th = (np.arange(cnt) + rng.uniform(-0.3, 0.3, cnt)) * (2 * math.pi / cnt) + rng.uniform(0, 6.28)
            st = rng.uniform(0.6, 1.0, cnt)
            d_ = np.angle(np.exp(1j * (ang[:, None] - th[None, :])))
            lobe = (np.exp(-(d_ / (0.9 / cnt * math.pi)) ** 2) * st[None, :]).max(1)
            lobe[-1] = lobe[0]
            zz = np.clip(pts[:, 2] - P[0][2], None, None)
            w_ = np.where(zz > 0, np.exp(-3.0 * zz / max(float(roots.get("height", 0.8)), 1e-6)), 1.0 + 0.6 * np.clip(-zz, 0, 1))
            f_ = 1 + (float(roots.get("spread", 2.0)) - 1) * w_[:, None] * lobe[None, :]
            V = pts[:, None, :] + ring * (rr[:, None] * f_)[:, :, None]
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
        at = np.empty((m * kk + 1, 6))
        at[:-1, 5] = np.repeat(nid, kk)
        at[-1, 5] = nid[-1]
        at[:, 4] = float(dead[nodes[0]]) if dead is not None else 0.0
        at[:-1, 0] = ax[nodes[0]]
        at[:-1, 1] = order[nodes[0]]
        at[:-1, 2] = np.repeat(seg / max(seg[-1], 1e-9), kk)
        at[:-1, 3] = np.repeat(rr, kk)
        at[-1, :4] = [ax[nodes[0]], order[nodes[0]], 1.0, rr[-1]]
        # whole bark tiles round the branch, counted at its base (by its mean radius a long limb's thick end got one
        # tile stretched round it: bark scales the size of cobbles)
        # ... and never fewer than 3: a thin branch's bark is finer in proportion (one 0.45 m tile round a 10 cm limb
        # was scales 5 cm across), the pattern kept square by the same factor along it
        girth = 2 * math.pi * float(r0)
        nu_ = max(3, int(round(girth / tile[0])))
        tv = tile[1] * min(1.0, girth / (nu_ * tile[0]) * 1.5)
        uv = np.empty((m * kk + 1, 2))
        uv[:-1, 0] = np.tile(np.arange(kk) / k * nu_, m)
        uv[:-1, 1] = np.repeat(seg / tv, kk) + (ax[nodes[0]] * 0.37) % 1.0
        uv[-1] = [0.5 * nu_, seg[-1] / tv]
        Vs.append(V)
        At.append(at)
        Us.append(uv)
        Ts.append(np.vstack([np.repeat(tan, kk, axis=0), tan[-1:]]))
        base += len(V)
    if not Vs:
        return {"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "axis": np.zeros(0), "order": np.zeros(0),
                "along": np.zeros(0), "dead": np.zeros(0), "node": np.zeros(0, np.int64), "radius": np.zeros(0), "tan": np.zeros((0, 3)), "uv": np.zeros((0, 2))}
    At = np.vstack(At)
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "axis": At[:, 0], "order": At[:, 1], "along": At[:, 2],
            "dead": At[:, 4], "node": At[:, 5].astype(np.int64), "radius": At[:, 3], "tan": np.vstack(Ts), "uv": np.vstack(Us)}
