"""surfaces.py <tag>: fill band + collar between the outline chains (fixed) with the smoothest spanning surface on each
piece's own pattern mesh (Laplace, edge weights from the flat), then keep the collar outside the band by a layer."""
import sys, pickle
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
D = "/mnt/data/hifipushie/folds_ab/D/"; t = sys.argv[1]
o = pickle.load(open(f"{D}{t}_outline.pkl", "rb")); X = o["X"].copy(); M = o["mesh"]; F = np.asarray(M["F"]); uv = M["uv"]; pc = M["piece"]; nm = M["names"]
fixed = set(int(v) for k_, ord_ in o["orders"].items() for v in ord_)
if not (len(sys.argv) > 2 and sys.argv[2] == "noturn"):          # the fold's turn: up the band, over a half circle, down outside
    iS_, iC_ = nm.index("stand"), nm.index("collar"); r_t = 0.0012
    neckc_ = np.asarray(o["orders"]["neck_c"]); rollc_ = np.asarray(o["orders"]["roll"]); sbo = np.asarray(o["orders"]["neckline"])
    S_ = X[neckc_]; kbx = cKDTree(uv[sbo, :1]); Bb = X[sbo[kbx.query(uv[neckc_, :1])[1]]]
    tg = np.gradient(S_, axis=0); tg /= np.linalg.norm(tg, axis=1)[:, None]
    up = S_ - Bb; up -= tg * np.einsum("ij,ij->i", up, tg)[:, None]; up /= np.linalg.norm(up, axis=1)[:, None]
    nn = np.cross(tg, up); yax_ = (o["at"]["cf_neck"][1] + o["at"]["cb_neck"][1]) / 2
    nn *= np.sign(np.einsum("ij,ij->i", nn[:, :2], np.c_[S_[:, 0], S_[:, 1] - yax_]))[:, None]
    kn2 = cKDTree(uv[neckc_]); t_roll = float(np.median(kn2.query(uv[rollc_])[0]))
    L1 = max(t_roll - np.pi * r_t / 2, 0.0005); t_end = L1 + np.pi * r_t
    cvs = np.where(pc == iC_)[0]; dt, ji = kn2.query(uv[cvs]); sel = dt <= t_end
    for v, tt_, i in zip(cvs[sel], dt[sel], ji[sel]):
        if v in set(neckc_): continue
        if tt_ <= L1: X[v] = S_[i] + up[i] * tt_ + nn[i] * 0.0003
        else:
            ph = (tt_ - L1) / r_t; C_ = S_[i] + up[i] * L1 + nn[i] * (r_t + 0.0003)
            X[v] = C_ - nn[i] * r_t * np.cos(ph) + up[i] * r_t * np.sin(ph)
        fixed.add(int(v))
    for v in rollc_: fixed.add(int(v))
    print(f"fold turn: {sel.sum()} vertices on the turn (crown at the roll line, {t_roll*1e3:.1f} mm up; radius {r_t*1e3:.1f} mm)")
for piece in (nm.index("stand"), nm.index("collar")):
    Fp = F[np.all(pc[F] == piece, axis=1)]; ids = np.unique(Fp); li = {v: i for i, v in enumerate(ids)}
    ed = np.unique(np.sort(np.r_[Fp[:, [0, 1]], Fp[:, [1, 2]], Fp[:, [2, 0]]], axis=1), axis=0)
    w = 1.0 / np.maximum(np.linalg.norm(uv[ed[:, 0]] - uv[ed[:, 1]], axis=1), 1e-5)
    a, b = np.array([li[v] for v in ed[:, 0]]), np.array([li[v] for v in ed[:, 1]]); n = len(ids)
    L = sp.coo_matrix((np.r_[w, w], (np.r_[a, b], np.r_[b, a])), shape=(n, n)).tocsr(); L = sp.diags(np.asarray(L.sum(1)).ravel()) - L
    fx = np.array([v in fixed for v in ids]); fr = ~fx
    A = L[fr][:, fr].tocsc(); rhs = -L[fr][:, fx] @ X[ids[fx]]
    X[ids[fr]] = np.column_stack([spsolve(A, rhs[:, k]) for k in range(3)])
    print(f"{nm[piece]}: {fx.sum()} chain vertices fixed, {fr.sum()} filled")
# the collar's fall stays a layer outside the band (it lies over it)
iS, iC = nm.index("stand"), nm.index("collar")
Fs = F[np.all(pc[F] == iS, axis=1)]; sv = np.unique(Fs); kd = cKDTree(X[sv])
VN = np.zeros_like(X); fn = np.cross(X[Fs[:, 1]] - X[Fs[:, 0]], X[Fs[:, 2]] - X[Fs[:, 0]])
for k in range(3): np.add.at(VN, Fs[:, k], fn)
VN /= np.maximum(np.linalg.norm(VN, axis=1), 1e-12)[:, None]
cen = np.array([0, (o["at"]["cf_neck"][1] + o["at"]["cb_neck"][1]) / 2, 0])
outw = np.sign(np.einsum("ij,ij->i", VN[sv][:, :2], (X[sv] - cen)[:, :2]))[:, None]; VN[sv] *= outw
neckc = np.asarray(o["orders"]["neck_c"]); rollc = np.asarray(o["orders"]["roll"])
kn_ = cKDTree(uv[neckc]); dr_ = np.median(kn_.query(uv[rollc])[0])
cv = np.array([v for v in np.where(pc == iC)[0] if v not in fixed])
inturn = np.zeros(len(cv), bool)                              # the fold's own turn wraps the band: leave it
Fc = F[np.all(pc[F] == iC, axis=1)]; idsC = np.unique(Fc); liC = {v: i for i, v in enumerate(idsC)}
edC = np.unique(np.sort(np.r_[Fc[:, [0, 1]], Fc[:, [1, 2]], Fc[:, [2, 0]]], axis=1), axis=0)
nbr = [[] for _ in idsC]
for a_, b_ in edC: nbr[liC[a_]].append(b_); nbr[liC[b_]].append(a_)
npush = 0
for it in range(30):                                                    # push out gently, re-smooth, repeat
    dd, j = kd.query(X[cv]); q = X[sv[j]]; nq = VN[sv[j]]
    sd = np.einsum("ij,ij->i", X[cv] - q, nq); push = (sd < 0.0015) & (dd < 0.01) & ~inturn
    npush = max(npush, int(push.sum()))
    X[cv[push]] += 0.5 * nq[push] * (0.0015 - sd[push])[:, None]
    Xn = X.copy()
    for k_, v in enumerate(cv):
        if inturn[k_]: continue
        Xn[v] = 0.5 * X[v] + 0.5 * X[nbr[liC[v]]].mean(0)
    X = Xn
print(f"collar: up to {npush} vertices pushed outside the band (gently, re-smoothed); {inturn.sum()} in the fold's turn left as filled")
pickle.dump({"A": X, "mesh": M, "bodyV": o["bodyV"], "bodyF": o["bodyF"], "at": o["at"]}, open(f"{D}{t}S.pkl", "wb")); print("saved", t + "S")
