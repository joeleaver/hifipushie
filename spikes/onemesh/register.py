"""GNM's mean head registered onto MakeHuman's reference head (25 years, sex 0.5), as spikes/headfit/make_field.py does
it (table pairs as a first guess, rounds of closest point on MakeHuman's surface facing the same way, each round's
displacement smoothed over GNM's mesh), but returning the correspondence itself: for one human mesh (make_asset.py)
every GNM skin vertex is BOUND to a point of MakeHuman's surface, so any MakeHuman shape carries the head with it."""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import factorized
from scipy.spatial import cKDTree

from hifipushie import base, headfit, makehuman

LAM = 12.0
LIPS = 0.2
REACH = 0.3


def closest_on_tris(p, a, b, c):
    """Closest points of triangles (a, b, c) to points p (Ericson), and their barycentric weights."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = np.maximum(va + vb + vc, 1e-30)
    v, w = vb / den, vc / den
    u = 1 - v - w
    W = np.c_[u, v, w]
    m = (d1 <= 0) & (d2 <= 0); W[m] = [1, 0, 0]
    m = (d3 >= 0) & (d4 <= d3); W[m] = [0, 1, 0]
    m = (d6 >= 0) & (d5 <= d6); W[m] = [0, 0, 1]
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0); t = d1 / np.maximum(d1 - d3, 1e-30); W[m] = np.c_[1 - t, t, 0 * t][m]
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0); t = d2 / np.maximum(d2 - d6, 1e-30); W[m] = np.c_[1 - t, 0 * t, t][m]
    m = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0); t = (d4 - d3) / np.maximum((d4 - d3) + (d5 - d6), 1e-30); W[m] = np.c_[0 * t, 1 - t, t][m]
    return W[:, :1] * a + W[:, 1:2] * b + W[:, 2:] * c, W


def vnormals(V, T):
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    out = np.zeros_like(V)
    for k in range(3):
        np.add.at(out, T[:, k], n)
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def frames():
    """MakeHuman's reference body and the maps between its world frame (m, Z up, facing -Y) and GNM's (interoculars
    round the eye midpoint, x left, y up, z forward)."""
    b = makehuman.body(headfit.table()["reference"])
    el = np.array(b["face"]["landmarks"]["eye.L"], float)
    io = 2 * abs(el[0])
    o = el * [0, 1, 1]

    def to_gnm(P):
        X = np.asarray(P, float) - o
        return np.c_[X[:, 0], X[:, 2], -X[:, 1]] / io

    def to_world(X):
        X = np.asarray(X, float) * io
        return np.c_[X[:, 0], -X[:, 2], X[:, 1]] + o
    return b, to_gnm, to_world, io


def gnm_mesh():
    g = base._gnm_data()
    hg = headfit._gnm()
    V0 = g["template_vertex_positions"].astype(float)
    Jm = hg["J0"].mean(0)
    io_g = float(abs(hg["J0"][0][0] - hg["J0"][1][0]))
    return g, hg, V0, Jm, io_g


def register(log=print):
    """{"Xg": GNM's mean head (io units), "d": its displacement onto MakeHuman's reference head, "tri": each vertex's
    MakeHuman triangle (3 body vertex ids; -1 rows where not valid), "bary", "valid", "skin", "outer"}."""
    g, hg, V0, Jm, io_g = gnm_mesh()
    Xg = (V0 - Jm) / io_g
    quads = np.asarray(g["quads"])
    Tg = np.r_[quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]]
    G = {k: np.asarray(v, float) > 0.5 for k, v in g["groups"].items()}
    skin = np.asarray(g["skin"], bool)
    outer = skin & G["skin_exterior"] & ~G["ears"] & ~G["eye_sockets"] & ~G["mouth_sock"] & ~G["eye_interiors"]
    n = len(V0)
    e = np.r_[quads[:, [0, 1]], quads[:, [1, 2]], quads[:, [2, 3]], quads[:, [3, 0]]]
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)).tocsr()
    A = ((A + A.T) > 0).astype(float)
    deg = np.asarray(A.sum(1)).ravel()
    L = sp.diags(np.where(deg > 0, 1.0, 0.0)) - sp.diags(1 / np.maximum(deg, 1)) @ A
    LtL = (L.T @ L).tocsc()
    lips = G["upper_lip"] | G["lower_lip"]

    def smoother(valid):
        w = valid * np.where(lips, LIPS, 1.0)
        solve = factorized((sp.diags(w) + LAM * LtL + 1e-9 * sp.identity(n)).tocsc())
        loose = ~skin
        tree = cKDTree(Xg[skin])

        def run(D):
            d = np.column_stack([solve(w * np.where(valid, D[:, k], 0.0)) for k in range(3)])
            dist, idx = tree.query(Xg[loose], k=8)
            ww = 1 / np.maximum(dist, 1e-6) ** 2
            d[loose] = (d[skin][idx] * ww[..., None]).sum(1) / ww.sum(1, keepdims=True)
            return d
        return run

    b, to_gnm, to_world, io = frames()
    Xm = to_gnm(b["P"])
    mq = np.asarray(b["L"]).reshape(-1, 4)
    Tm = np.r_[mq[:, [0, 1, 2]], mq[:, [0, 2, 3]]]
    Tm = Tm[(Xm[Tm][:, :, 1] > Xg[skin][:, 1].min() - 0.6).all(1) & (np.abs(Xm[Tm][:, :, 0]) < 2.2).all(1)]
    nm = np.cross(Xm[Tm[:, 1]] - Xm[Tm[:, 0]], Xm[Tm[:, 2]] - Xm[Tm[:, 0]])
    nm /= np.maximum(np.linalg.norm(nm, axis=1, keepdims=True), 1e-12)
    bw = np.array([[i, j, 4 - i - j] for i in range(5) for j in range(5 - i)], float) / 4
    S = np.einsum("sk,tkc->tsc", bw, Xm[Tm]).reshape(-1, 3)
    St = np.repeat(np.arange(len(Tm)), len(bw))
    stree = cKDTree(S)

    def project(X, mask=outer, reach=REACH, facing=0.35):
        ng = vnormals(X, Tg)
        dist, idx = stree.query(X, k=12)
        tri = np.full(len(X), -1)
        best = np.full(len(X), np.inf)
        P, Wb = X.copy(), np.zeros((len(X), 3))
        for k in range(12):
            t = St[idx[:, k]]
            ok = ((nm[t] * ng).sum(1) > facing) & mask
            p, wb = closest_on_tris(X, Xm[Tm[t, 0]], Xm[Tm[t, 1]], Xm[Tm[t, 2]])
            dd = np.linalg.norm(p - X, axis=1)
            take = ok & (dd < best) & (dd < reach)
            tri[take], best[take], P[take], Wb[take] = t[take], dd[take], p[take], wb[take]
        return tri, P, Wb

    G0 = (hg["L0"] - Jm) / io_g
    ref_pts = headfit.axes()["ref"]
    sg = 0.7
    K = np.exp(-((G0[:, None] - G0[None]) ** 2).sum(-1) / (2 * sg * sg))
    coef = np.linalg.solve(K + 0.05 * np.eye(len(G0)), ref_pts - G0)
    d = np.zeros((n, 3))
    for a in range(0, n, 4096):
        d[a:a + 4096] = np.exp(-((Xg[a:a + 4096, None] - G0[None]) ** 2).sum(-1) / (2 * sg * sg)) @ coef
    for it in range(4):
        tri, P, Wb = project(Xg + d)
        valid = tri >= 0
        d = smoother(valid)(P - Xg)
        res = np.linalg.norm((Xg + d - P)[valid], axis=1)
        log(f"register round {it}: {valid.sum()} of {outer.sum()} outer skin vertices on MakeHuman's surface, "
            f"residual rms {np.sqrt((res ** 2).mean()) * io * 1000:.2f} mm, max {res.max() * io * 1000:.1f} mm")
    # the final binding: where the registered head lies on MakeHuman's surface
    tri, P, Wb = project(Xg + d)
    valid = tri >= 0
    return {"Xg": Xg, "d": d, "tri": np.where(valid[:, None], Tm[np.maximum(tri, 0)], -1), "bary": Wb, "valid": valid,
            "skin": skin, "outer": outer, "quads": quads, "groups": G, "body": b, "to_gnm": to_gnm, "to_world": to_world,
            "io": io, "io_g": io_g, "Jm": Jm, "Tm": Tm, "project": project, "LtL": LtL}
