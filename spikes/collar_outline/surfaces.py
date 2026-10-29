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
ci = np.array([v for v in np.where(pc == iC)[0] if v not in fixed]); dd, j = kd.query(X[ci]); q = X[sv[j]]; nq = VN[sv[j]]
sd = np.einsum("ij,ij->i", X[ci] - q, nq); push = (sd < 0.0015) & (dd < 0.01)
X[ci[push]] += nq[push] * (0.0015 - sd[push])[:, None]; print(f"collar: {push.sum()} vertices kept outside the band")
pickle.dump({"A": X, "mesh": M, "bodyV": o["bodyV"], "bodyF": o["bodyF"], "at": o["at"]}, open(f"{D}{t}S.pkl", "wb")); print("saved", t + "S")
