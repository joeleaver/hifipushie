"""One-off, after make_table.py / make_axes.py: MakeHuman's heads as DISPLACEMENT FIELDS on GNM's own vertices, stored as
package data (src/hifipushie/head_fields.npz), so a GNM head can take MakeHuman's whole shape for an age / sex / weight
(not only what 426 sampled points and a smooth warp carry) without the MakeHuman pack at runtime.

    uv run python spikes/headfit/make_field.py [check.png]

How: GNM's mean head is registered onto MakeHuman's reference head (25 years, sex 0.5): a first guess from the table's
pairs (RBF), then a few rounds of closest point on MakeHuman's surface (facing the same way) for the outer skin, each
round's displacement smoothed over GNM's mesh (least squares with a Laplacian term), so the lids, lips, nostrils, ears
and everything inside ride along instead of being projected. Each skin vertex then has a point ON MakeHuman's surface
(triangle + barycentric weights); MakeHuman's topology is fixed, so the same weights read every other head.

Stored, in interocular units round the eye midpoint, GNM's frame (x left, y up, z forward), float16:
  ref      (verts, 3)                GNM's mean head -> MakeHuman's reference head
  age_sex  (ages, 2, verts, 3)       the reference head -> the head at each age for sex 0 / 1 (weight 0.5)
  weight   (2, 2, verts, 3)          [sex][light 0.1, heavy 0.9] minus that sex's weight-0.5 head, at age 30
  ages
"""
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import factorized
from scipy.spatial import cKDTree

from hifipushie import base, headfit, makehuman

AGES = [1, 3, 6, 9, 12, 15, 18, 25, 35, 50, 65, 80, 90]
LAM = 12.0  # smoothing of a displacement field over the mesh
LIPS = 0.2
REACH = 0.3  # interoculars a vertex may be from its point on MakeHuman's surface


def mh_frame(params):
    """MakeHuman's vertices in GNM's frame (interoculars round the eye midpoint) and its quads."""
    b = makehuman.body(params)
    P = np.asarray(b["P"], float)
    el = np.array(b["face"]["landmarks"]["eye.L"], float)
    io = 2 * abs(el[0])
    X = P - el * [0, 1, 1]
    return np.c_[X[:, 0], X[:, 2], -X[:, 1]] / io, np.asarray(b["L"]).reshape(-1, 4)


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


def main():
    g = base._gnm_data()
    hg = headfit._gnm()
    V0 = g["template_vertex_positions"].astype(float)
    Jm = hg["J0"].mean(0)
    io_g = float(abs(hg["J0"][0][0] - hg["J0"][1][0]))
    Xg = (V0 - Jm) / io_g
    quads = np.asarray(g["quads"])
    Tg = np.r_[quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]]
    G = {k: np.asarray(v, float) > 0.5 for k, v in g["groups"].items()}
    skin = np.asarray(g["skin"], bool)
    outer = skin & G["skin_exterior"] & ~G["ears"] & ~G["eye_sockets"] & ~G["mouth_sock"] & ~G["eye_interiors"]
    n = len(V0)
    # the mesh's Laplacian (uniform), and one factorisation per weight set
    e = np.r_[quads[:, [0, 1]], quads[:, [1, 2]], quads[:, [2, 3]], quads[:, [3, 0]]]
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)).tocsr()
    A = ((A + A.T) > 0).astype(float)
    deg = np.asarray(A.sum(1)).ravel()
    L = sp.diags(np.where(deg > 0, 1.0, 0.0)) - sp.diags(1 / np.maximum(deg, 1)) @ A
    LtL = (L.T @ L).tocsc()

    lips = G["upper_lip"] | G["lower_lip"]

    def smoother(valid):
        w = valid * np.where(lips, LIPS, 1.0)  # the lips mostly ride: projected in full, their corners pinched
        solve = factorized((sp.diags(w) + LAM * LtL + 1e-9 * sp.identity(n)).tocsc())
        loose = ~skin  # eyeballs, teeth, tongue: pieces of their own, carried by the skin beside them
        tree = cKDTree(Xg[skin])

        def run(D):
            d = np.column_stack([solve(w * np.where(valid, D[:, k], 0.0)) for k in range(3)])
            dist, idx = tree.query(Xg[loose], k=8)
            ww = 1 / np.maximum(dist, 1e-6) ** 2
            d[loose] = (d[skin][idx] * ww[..., None]).sum(1) / ww.sum(1, keepdims=True)
            return d
        return run

    Xm, mq = mh_frame(headfit.table()["reference"])
    Tm = np.r_[mq[:, [0, 1, 2]], mq[:, [0, 2, 3]]]
    Tm = Tm[(Xm[Tm][:, :, 1] > Xg[skin][:, 1].min() - 0.6).all(1) & (np.abs(Xm[Tm][:, :, 0]) < 2.2).all(1)]
    nm = np.cross(Xm[Tm[:, 1]] - Xm[Tm[:, 0]], Xm[Tm[:, 2]] - Xm[Tm[:, 0]])
    nm /= np.maximum(np.linalg.norm(nm, axis=1, keepdims=True), 1e-12)
    # samples on MakeHuman's triangles to find candidate triangles
    bw = np.array([[i, j, 4 - i - j] for i in range(5) for j in range(5 - i)], float) / 4
    S = np.einsum("sk,tkc->tsc", bw, Xm[Tm]).reshape(-1, 3)
    St = np.repeat(np.arange(len(Tm)), len(bw))
    stree = cKDTree(S)

    def project(X):
        ng = vnormals(X, Tg)
        dist, idx = stree.query(X, k=12)
        tri = np.full(n, -1)
        best = np.full(n, np.inf)
        P, Wb = X.copy(), np.zeros((n, 3))
        for k in range(12):
            t = St[idx[:, k]]
            ok = ((nm[t] * ng).sum(1) > 0.35) & outer
            p, wb = closest_on_tris(X, Xm[Tm[t, 0]], Xm[Tm[t, 1]], Xm[Tm[t, 2]])
            dd = np.linalg.norm(p - X, axis=1)
            take = ok & (dd < best) & (dd < REACH)
            tri[take], best[take], P[take], Wb[take] = t[take], dd[take], p[take], wb[take]
        return tri, P, Wb

    # first guess: the table's pairs
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
        print(f"round {it}: {valid.sum()} of {outer.sum()} outer skin vertices on MakeHuman's surface, residual rms {np.sqrt((res ** 2).mean()):.4f} io, "
              f"max {res.max():.3f}")
    run = smoother(valid)
    corr = Tm[np.maximum(tri, 0)]

    def carried(params):
        Y, _ = mh_frame(params)
        return (Wb[:, :1] * Y[corr[:, 0]] + Wb[:, 1:2] * Y[corr[:, 1]] + Wb[:, 2:] * Y[corr[:, 2]])

    T_ref = carried(headfit.table()["reference"])
    ref = run(T_ref - Xg)
    out_as = []
    for a in AGES:
        out_as.append([run(carried({"age": a, "sex": s, "weight": 0.5, "muscle": 0.5, "growth": False}) - T_ref) for s in (0.0, 1.0)])
        print("age", a, "rms move", [round(float(np.sqrt((x[skin] ** 2).sum(1).mean())), 4) for x in out_as[-1]], flush=True)
    out_w = []
    for s in (0.0, 1.0):
        mid = carried({"age": 30, "sex": s, "weight": 0.5, "muscle": 0.5, "growth": False})
        out_w.append([run(carried({"age": 30, "sex": s, "weight": w, "muscle": 0.5}) - mid) for w in (0.1, 0.9)])
    dest = Path(headfit.__file__).with_name("head_fields.npz")
    np.savez_compressed(dest, ages=np.array(AGES, float), ref=ref.astype(np.float16), age_sex=np.array(out_as).astype(np.float16),
                        weight=np.array(out_w).astype(np.float16), valid=valid)
    print("wrote", dest, dest.stat().st_size // 1024, "kB")


if __name__ == "__main__":
    main()
