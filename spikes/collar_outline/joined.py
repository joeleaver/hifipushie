"""joined(X, M, bV, bF): the garment's faces with sewn vertices shared and every piece facing out, so seams shade as cloth."""
import numpy as np
from scipy.spatial import cKDTree
def joined(X, M, bV, bF):
    F = np.asarray(M["F"]).copy(); pc = np.asarray(M["piece"]); par = np.arange(len(X))
    def find(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    for a, b in np.asarray(M["sew"]).reshape(-1, 2):
        if np.linalg.norm(X[a] - X[b]) < 0.002: par[find(int(a))] = find(int(b))
    N = np.zeros_like(bV); fn = np.cross(bV[bF[:, 1]] - bV[bF[:, 0]], bV[bF[:, 2]] - bV[bF[:, 0]])
    for k in range(3): np.add.at(N, bF[:, k], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]; kd = cKDTree(bV)
    for p in np.unique(pc):
        fi = np.where(pc[F[:, 0]] == p)[0]; c = X[F[fi]].mean(1); n = np.cross(X[F[fi, 1]] - X[F[fi, 0]], X[F[fi, 2]] - X[F[fi, 0]])
        if np.einsum("ij,ij->i", n, N[kd.query(c)[1]]).sum() < 0: F[fi] = F[fi][:, [0, 2, 1]]
    root = np.array([find(i) for i in range(len(X))]); return root[F]
