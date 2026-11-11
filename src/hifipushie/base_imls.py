"""Mesh helpers and the implicit surface: Catmull-Clark, normals and edge lengths, the IMLS field over a point set. Part of base (base.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import retopo
from .base import FAR, K, SEAM

def _catmull_clark(V, faces):
    """One Catmull-Clark step on a closed polygon mesh: (verts, quads)."""
    V = np.asarray(V, float)
    nv = len(V)
    fp = np.array([V[f].mean(0) for f in faces])
    edge_id, efaces, ends = {}, [], []
    fe = []
    for fi, f in enumerate(faces):
        ids = []
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            key = (min(a, b), max(a, b))
            if key not in edge_id:
                edge_id[key] = len(ends)
                ends.append(key)
                efaces.append([])
            efaces[edge_id[key]].append(fi)
            ids.append(edge_id[key])
        fe.append(ids)
    ends = np.array(ends)
    ep = np.array([(V[a] + V[b] + fp[fs].sum(0)) / (2 + len(fs)) if len(fs) == 2 else (V[a] + V[b]) / 2
                   for (a, b), fs in zip(ends, efaces)])
    # vertex points: (F + 2R + (n - 3) P) / n
    n = np.zeros(nv)
    Fsum = np.zeros_like(V)
    for fi, f in enumerate(faces):
        for v in f:
            Fsum[v] += fp[fi]
            n[v] += 1
    Rsum = np.zeros_like(V)
    m = np.zeros(nv)
    mid = (V[ends[:, 0]] + V[ends[:, 1]]) / 2
    for k in range(2):
        np.add.at(Rsum, ends[:, k], mid)
        np.add.at(m, ends[:, k], 1)
    vp = (Fsum / n[:, None] + 2 * Rsum / m[:, None] + (n[:, None] - 3) * V) / n[:, None]
    newV = np.r_[vp, ep, fp]
    e0, f0 = nv, nv + len(ep)
    quads = []
    for fi, f in enumerate(faces):
        L = len(f)
        for k in range(L):
            quads.append([f[k], e0 + fe[fi][k], f0 + fi, e0 + fe[fi][k - 1]])
    return newV, quads


def _normals_and_h(V, faces):
    T = np.array([(f[0], f[j], f[j + 1]) for f in faces for j in range(1, len(f) - 1)])
    N = retopo._vnormals(V, T)
    e = np.array(sorted({(min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)])) for f in faces
                         for k in range(len(f))}))
    ln = np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1)
    s = np.zeros(len(V))
    c = np.zeros(len(V))
    for k in range(2):
        np.add.at(s, e[:, k], ln)
        np.add.at(c, e[:, k], 1)
    return N, s / np.maximum(c, 1)


def _unit(v):
    return v / np.linalg.norm(v)


def _imls(X, pr, k=K):
    """IMLS over one surface's vertices at points X (n, 3)."""
    d, i = pr["tree"].query(X, k=k)
    P, N, h = pr["verts"][i], pr["normals"][i], pr["h"][i]
    # the kernel widens with distance (h at least 0.7 x the nearest vertex's distance): off the surface the field
    # is a plane fit over a patch as wide as the distance, so shells (clothes, 5-15 mm out) are smooth offsets
    # (with a fixed h the far field was the distance to the nearest vertex: a shirt came out dimpled)
    h = np.maximum(h, 0.7 * d[:, :1])
    s = ((X[:, None, :] - P) * N).sum(-1)
    q = np.clip(d / (2 * h), 0.0, 1.0)  # Wendland C2, support 2 h: compact, so a vertex entering or leaving the
    w = (1 - q) ** 4 * (4 * q + 1)      # k nearest carries no weight (a Gaussian's tail there speckled the creases)
    if pr.get("wt") is not None:  # per-point weights (a grafted head's seam)
        w = w * pr["wt"][i]
    ws = w.sum(1)
    imls = (w * s).sum(1) / np.maximum(ws, 1e-300)
    far = np.sign(imls) * np.maximum(d[:, 0] - pr["hmax"], 0.0)
    if pr.get("far_fit"):  # garments: their regions reach many cm off the cloth, and where the nearest vertex was
        # nearer than the mesh's largest face the far value was exactly 0 (slabs of the region's box in the air
        # before a loose tee). There the plane fit itself, never more than half the nearest vertex's distance
        far = np.where(far == 0, np.sign(imls) * np.minimum(np.abs(imls), 0.5 * d[:, 0]), far)
    t = np.clip((d[:, 0] - FAR) / FAR, 0.0, 1.0)  # past FAR from every vertex: conservative distance, for culling
    return np.where(ws > 1e-12, (1 - t) * imls + t * far, far)


def _sd_body(p: np.ndarray, pr: dict) -> np.ndarray:
    X = p.reshape(-1, 3)
    if pr.get("seam") is None:
        return _imls(X, pr).reshape(p.shape[:-1])
    # near a head graft's seam the two point sets overlap with ramped weights; there the k nearest must reach both
    # (the head's points are twice as dense: 32 nearest were all one set's, and the surface stepped where it switched)
    c, pn, r = pr["seam"]
    near = np.abs((X - c) @ pn) < 2 * SEAM
    near &= np.linalg.norm(np.cross(X - c, pn), axis=1) < r
    out = np.empty(len(X))
    if (~near).any():
        out[~near] = _imls(X[~near], pr)
    if near.any():
        out[near] = _imls(X[near], pr, k=4 * K)
    return out.reshape(p.shape[:-1])
