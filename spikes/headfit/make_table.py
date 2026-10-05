"""One-off: the MakeHuman base mesh's vertices at GNM's 68 face landmarks (+ cranium points), written to
src/hifipushie/makehuman_lm68.json. MakeHuman's topology is fixed, so the table holds for every shaped body.
The two neutral heads are aligned (eye centres, then similarity ICP on the face, then a local ICP per feature) and each
landmark takes the nearest MakeHuman vertex; pairs are forced symmetric. Check the picture it writes.

    uv run python spikes/headfit/make_table.py table.png
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from hifipushie import base, makehuman

REF = {"age": 25, "sex": 0.5, "weight": 0.5, "muscle": 0.5}
R = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # GNM (Y up, facing +Z) -> Z up, facing -Y
# dlib 68 mirror pairs
PAIRS = [(0, 16), (1, 15), (2, 14), (3, 13), (4, 12), (5, 11), (6, 10), (7, 9), (17, 26), (18, 25), (19, 24), (20, 23),
         (21, 22), (36, 45), (37, 44), (38, 43), (39, 42), (40, 47), (41, 46), (31, 35), (32, 34), (48, 54), (49, 53),
         (50, 52), (59, 55), (58, 56), (60, 64), (61, 63), (67, 65)]
CENTRE = (8, 27, 28, 29, 30, 33, 51, 57, 62, 66)
FEATURES = {"jaw": range(0, 17), "brows": range(17, 27), "nose": range(27, 36), "eyes": range(36, 48), "mouth": range(48, 68)}


def similarity(A, B):
    """s, Rm, t with s * A @ Rm.T + t ~ B (Umeyama)."""
    ca, cb = A.mean(0), B.mean(0)
    H = (A - ca).T @ (B - cb)
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    Rm = Vt.T @ np.diag([1, 1, d]) @ U.T
    s = (S * [1, 1, d]).sum() / ((A - ca) ** 2).sum()
    return s, Rm, cb - s * ca @ Rm.T


def main():
    g = base._gnm_data()
    V = g["template_vertex_positions"].astype(float)
    J = g["template_joint_positions"].astype(float)
    lm = np.array([sum(float(w) * V[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])
    skin = g["skin"]
    G = V[skin] @ R.T
    lm = lm @ R.T
    ge = J[2:4] @ R.T
    t = makehuman.body(REF)
    P = np.asarray(t["P"], float)
    el = np.array(t["face"]["landmarks"]["eye.L"], float)
    me = np.array([el, el * [-1, 1, 1]])
    s0 = np.linalg.norm(me[0] - me[1]) / np.linalg.norm(ge[0] - ge[1])
    tr = lambda X: (X - ge.mean(0)) * s0 + me.mean(0)
    G, lm = tr(G), tr(lm)
    io = np.linalg.norm(me[0] - me[1])
    head = P[:, 2] > me[0][2] - 2.4 * io
    idx = np.flatnonzero(head)
    tree = cKDTree(P[idx])
    face = (G[:, 1] < me[0][1] + 1.0 * io) & (G[:, 2] > me[0][2] - 2.0 * io)  # GNM's face front
    X, L = G.copy(), lm.copy()
    for _ in range(40):
        d, j = tree.query(X[face])
        ok = d < np.percentile(d, 85)
        s, Rm, tt = similarity(X[face][ok], P[idx][j][ok])
        X, L = s * X @ Rm.T + tt, s * L @ Rm.T + tt
    print("global ICP: median distance mm", round(float(np.median(tree.query(X[face])[0]) * 1000), 2), "eye scale", round(float(s0), 4))
    out = {}
    for name, ids in FEATURES.items():  # a local similarity per feature: the two faces' features sit mm apart
        ids = list(ids)
        c = L[ids].mean(0)
        r = 1.6 * np.linalg.norm(L[ids] - c, axis=1).max() + 0.01
        loc = np.linalg.norm(X - c, axis=1) < r
        Xl, Ll = X[loc].copy(), L[ids].copy()
        for _ in range(20):
            d, j = tree.query(Xl)
            ok = d < np.percentile(d, 85)
            s, Rm, tt = similarity(Xl[ok], P[idx][j][ok])
            if abs(s - 1) > 0.25:
                break
            Xl, Ll = s * Xl @ Rm.T + tt, s * Ll @ Rm.T + tt
        d, j = tree.query(Ll)
        print(name, "landmark -> vertex mm", np.round(d * 1000, 1).tolist())
        for i, jj in zip(ids, j):
            out[i] = int(idx[jj])
    mtree = cKDTree(P)
    for a, b in PAIRS:  # symmetric: the right side = the mirror of the left's (+x) vertex
        l, r = (a, b) if P[out[a]][0] > P[out[b]][0] else (b, a)
        out[r] = int(mtree.query(P[out[l]] * [-1, 1, 1])[1])
    cand = np.flatnonzero((np.abs(P[:, 0]) < 1e-4) & head)
    for i in CENTRE:  # centre-line landmarks onto x = 0
        out[i] = int(cand[np.argmin(np.linalg.norm(P[cand] - P[out[i]], axis=1))])
    hv = idx[P[idx][:, 2] > me[0][2]]
    extra = {"top": int(hv[np.argmax(P[hv][:, 2])]), "back": int(hv[np.argmax(P[hv][:, 1])]),
             "side.L": int(hv[np.argmax(P[hv][:, 0])])}
    extra["side.R"] = int(mtree.query(P[extra["side.L"]] * [-1, 1, 1])[1])
    gi = np.flatnonzero(skin)  # GNM's own cranium points (vertex ids in its full mesh), for the same measures there
    up = np.flatnonzero(X[:, 2] > me[0][2])
    gx = {"top": int(gi[up[np.argmax(X[up][:, 2])]]), "back": int(gi[up[np.argmax(X[up][:, 1])]]),
          "side.L": int(gi[up[np.argmax(X[up][:, 0])]]), "side.R": int(gi[up[np.argmin(X[up][:, 0])]])}
    dest = Path(base.__file__).with_name("makehuman_lm68.json")
    dest.write_text(json.dumps({"reference": REF, "vertices": len(P), "lm68": [out[i] for i in range(68)], "extra": extra,
                                "gnm_extra": gx}))
    print("wrote", dest, extra, gx)
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (2000, 1100), "white")
    dr = ImageDraw.Draw(im)
    k = 3600.0
    for n, (u, w, sel, sg) in enumerate(((0, 2, head & (P[:, 1] < me[0][1] + 0.5 * io), 1), (1, 2, head & (P[:, 0] > -0.002), 1))):
        cx, cz = 500 + 1000 * n, 520
        to = lambda p: (cx + sg * k * (p[u] - me.mean(0)[u]), cz - k * (p[w] - me.mean(0)[2] + 0.02))
        for p in P[sel]:
            x, y = to(p)
            dr.point((x, y), fill=(150, 150, 150))
        for i in range(68):
            x, y = to(P[out[i]])
            dr.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(220, 0, 0))
            dr.text((x + 4, y - 5), str(i), fill=(0, 0, 0))
        for v in extra.values():
            x, y = to(P[v])
            dr.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(0, 0, 220))
    im.save(sys.argv[1] if len(sys.argv) > 1 else "table.png")


if __name__ == "__main__":
    main()
