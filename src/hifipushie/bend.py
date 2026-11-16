"""Bending masses along a path, as a modeller bends clay (Blender's curve modifier, ZBrush's bend curve).

A bend {"of": [masses], "path": [[x, y, z], ...]} carries the named masses along the path: the path's first point
is where the bending starts, and its first direction is the line the masses lie along there. Everything before
the start stays where it is; clay a distance s past the start along that line goes to the point s along the path
(arc length: clay is not stretched), keeping its offset from the line in a frame that turns with the path (a
rotation-minimising frame). Past the path's end the clay carries on straight. So the thickness is kept and a tight
curve squeezes the inside of the bend into a crease, as clay does; a gentle one gives a round rim.

Evaluation (sdf_shapes.sd_csg via deform.undeform): a point of the world is taken back to where it was before the
bend, exactly, through the nearest point of the path (no fixed-point steps: a fold of 120 degrees is far past what
those survive). The field is NOT divided by the bend's squeeze (as for grabs, deform.py says why): the squeeze goes
on Prim.lip, where the mesher widens its band.

Why: an ear made of two cones meeting at a knuckle always peaked at the fold (blind runs e13 to e17); the concept's
ear is one thick lump bent over round a broad curve, with a cup inside the bend. A bend is how a modeller makes
that, and it is the same move for a tail, a horn, a trunk, a finger or a brim.
"""
from __future__ import annotations

import numpy as np

SAMPLES = 24  # path samples per control span
SQUEEZE = 0.75  # the inside of a bend tighter than this (offset x curvature) is a crease: lip stops growing


def _spline(P: np.ndarray) -> np.ndarray:
    """Points along a centripetal Catmull-Rom curve through P (n >= 2)."""
    if len(P) == 2:
        return np.linspace(P[0], P[1], SAMPLES + 1)
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        t0 = 0.0
        t1 = t0 + max(np.linalg.norm(p1 - p0), 1e-6) ** 0.5
        t2 = t1 + max(np.linalg.norm(p2 - p1), 1e-6) ** 0.5
        t3 = t2 + max(np.linalg.norm(p3 - p2), 1e-6) ** 0.5
        for t in np.linspace(t1, t2, SAMPLES, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(P[-1])
    return np.asarray(out)


def geometry(path, normal=None) -> dict:
    """The path's samples with arc length and a turning frame (T along, N and B across). normal: a direction across
    the start (default: toward where the path goes, so N lies in the bend's plane)."""
    P = np.asarray(path, float)
    if P.ndim != 2 or P.shape[1] != 3 or len(P) < 2:
        raise ValueError("a bend's path is two or more points [[x, y, z], ...]")
    C = _spline(P)
    seg = np.diff(C, axis=0)
    ln = np.linalg.norm(seg, axis=1)
    keep = np.concatenate([[True], ln > 1e-7])
    C = C[keep]
    seg = np.diff(C, axis=0)
    ln = np.linalg.norm(seg, axis=1)
    if len(C) < 2 or ln.sum() < 1e-4:
        raise ValueError("a bend's path must go somewhere: its points are all in one place")
    S = np.concatenate([[0.0], np.cumsum(ln)])
    Ts = seg / ln[:, None]
    T = np.vstack([Ts[:1], (Ts[:-1] + Ts[1:]) / 2, Ts[-1:]])
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    n0 = np.asarray(normal, float) if normal is not None else (C[-1] - C[0])
    n0 = n0 - (n0 @ T[0]) * T[0]
    if np.linalg.norm(n0) < 1e-6:
        n0 = np.cross(T[0], [0.0, 0.0, 1.0] if abs(T[0][2]) < 0.9 else [1.0, 0.0, 0.0])
    N = [n0 / np.linalg.norm(n0)]
    for i in range(len(C) - 1):  # double reflection (Wang et al. 2008): the frame turns no more than the path does
        v1 = C[i + 1] - C[i]
        c1 = v1 @ v1
        rL = N[i] - (2 / c1) * (v1 @ N[i]) * v1
        tL = T[i] - (2 / c1) * (v1 @ T[i]) * v1
        v2 = T[i + 1] - tL
        c2 = v2 @ v2
        n = rL - (2 / c2) * (v2 @ rL) * v2 if c2 > 1e-12 else rL
        n = n - (n @ T[i + 1]) * T[i + 1]
        N.append(n / np.linalg.norm(n))
    N = np.asarray(N)
    B = np.cross(T, N)
    k = np.linalg.norm(np.diff(T, axis=0), axis=1) / np.maximum(ln, 1e-9)
    return {"C": C, "S": S, "T": T, "N": N, "B": B, "L": float(S[-1]), "kmax": float(k.max(initial=0.0))}


def _frame(g: dict, i: np.ndarray, t: np.ndarray):
    """Point and frame at parameter t (unclamped at the two ends) of segment i."""
    C, T, N, B = g["C"], g["T"], g["N"], g["B"]
    tc = np.clip(t, 0.0, 1.0)[:, None]
    seg = C[i + 1] - C[i]
    c = C[i] + t[:, None] * seg  # (past the ends: straight on)

    def lerp(F):
        f = F[i] * (1 - tc) + F[i + 1] * tc
        return f / np.linalg.norm(f, axis=1, keepdims=True)
    return c, lerp(T), lerp(N), lerp(B)


def inverse(g: dict, p: np.ndarray, chunk: int = 20000) -> np.ndarray:
    """Where each world point was before the bend (n, 3)."""
    p = np.asarray(p, float)
    C, S = g["C"], g["S"]
    A, D = C[:-1], np.diff(C, axis=0)
    dd = np.maximum((D * D).sum(1), 1e-18)
    out = np.empty_like(p)
    m = len(A)
    for a in range(0, len(p), chunk):
        q = p[a:a + chunk]
        t = np.clip(np.einsum("nmk,mk->nm", q[:, None, :] - A[None], D) / dd[None], 0.0, 1.0)
        d2 = ((q[:, None, :] - (A[None] + t[..., None] * D[None])) ** 2).sum(-1)
        i = np.argmin(d2, axis=1)
        tu = ((q - A[i]) * D[i]).sum(1) / dd[i]  # unclamped: before the start and past the end it goes straight
        tt = np.where(i == 0, np.minimum(tu, 1.0), np.where(i == m - 1, np.maximum(tu, 0.0), np.clip(tu, 0.0, 1.0)))
        tt = np.where((i == 0) & (i == m - 1), tu, tt)
        c, _, Nf, Bf = _frame(g, i, tt)
        s = S[i] + tt * np.sqrt(dd[i])
        o = q - c
        u, v = (o * Nf).sum(1), (o * Bf).sum(1)
        out[a:a + chunk] = C[0] + s[:, None] * g["T"][0] + u[:, None] * g["N"][0] + v[:, None] * g["B"][0]
    return out


def field(g: dict, f, p: np.ndarray, prev=None) -> tuple[np.ndarray, np.ndarray]:
    """(field, rest point) of clay with field f (a function of rest points) bent by g: the union of the clay before
    the start, unbent, and the bent image of the clay past it. A rule "a point before the start plane is unbent"
    sliced off a lobe bent past 90 degrees, which hangs back below that plane (e18). prev: earlier warps' undo."""
    p = np.asarray(p, float)
    und = prev or (lambda x: x)
    xb = und(p)
    db = np.maximum(f(xb), (p - g["C"][0]) @ g["T"][0])  # the unbent part, cut at the start plane
    q = inverse(g, p)
    xa = und(q)
    da = np.maximum(f(xa), -((q - g["C"][0]) @ g["T"][0]))  # the bent part, from the start plane on
    near = da < db
    return np.where(near, da, db), np.where(near[:, None], xa, xb)


def forward(g: dict, x: np.ndarray) -> np.ndarray:
    """Where each point of the unbent clay goes (n, 3): for boxes and for saying where a mass's end lands."""
    x = np.asarray(x, float)
    r = x - g["C"][0]
    s = r @ g["T"][0]
    u, v = r @ g["N"][0], r @ g["B"][0]
    S = g["S"]
    j = np.clip(np.searchsorted(S, np.clip(s, 0.0, g["L"])) - 1, 0, len(S) - 2)
    t = (np.clip(s, 0.0, g["L"]) - S[j]) / np.maximum(S[j + 1] - S[j], 1e-12)
    c, T, N, B = _frame(g, j, t)
    c = c + np.maximum(s - g["L"], 0.0)[:, None] * T
    out = c + u[:, None] * N + v[:, None] * B
    return np.where((s < 0)[:, None], x, out)


def squeeze(g: dict, radius: float) -> float:
    """lip: how much steeper than a distance the bent field of clay reaching `radius` off the path can be."""
    return float(1.0 / (1.0 - min(radius * g["kmax"], SQUEEZE)))
