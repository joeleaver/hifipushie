"""Ceilings for dense surface evidence: (1) the identity basis's reach (truth projected on 120 components with the
prior), (2) the TRUE surface pushed through the generated-mesh pipeline (perfect mesh, unknown scale / pose),
alone and with the front detector points.   run.sh oracle_mesh.py"""
import numpy as np

import fitlib
import fits
import fits2
import mm
import rs
import subjects
import tmesh


class TrueMesh(tmesh.Mesh):
    def __init__(self, V, seed=0):
        from scipy.spatial import cKDTree
        g = rs.gnm()
        ext = g["ext"]
        T = g["T"][ext[g["T"]].all(1)]
        # denser than GNM's vertices: face centres and edge midpoints too
        P = np.r_[V, V[T].mean(1), (V[T[:, 0]] + V[T[:, 1]]) / 2, (V[T[:, 1]] + V[T[:, 2]]) / 2]
        n = mm.vnormals(V)
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        fn /= np.linalg.norm(fn, axis=1, keepdims=True)
        N = np.r_[n, fn, fn, fn]
        keep = np.r_[ext, np.ones(len(P) - len(V), bool)]
        rng = np.random.default_rng(seed)
        s, yaw = rng.uniform(1.5, 3.0), rng.uniform(-0.2, 0.2)
        R = tmesh._rz(yaw)
        self.V = (P[keep] @ R.T) * s + rng.normal(0, 0.1, 3)
        self.N = N[keep] @ R.T
        self.tree = cKDTree(self.V)
        self.T = None
        self.name = "true"


def reach(s):
    g = rs.gnm()
    Vt = fits.truth(s)["V"]
    idx = np.flatnonzero(g["ext"])[::3]
    c = np.zeros(rs.K_FIT)
    for _ in range(3):
        H = rs.head(c)
        sc, R, t = rs.similarity(Vt[g["regions"]["face"]], H[g["regions"]["face"]])
        Y = sc * Vt @ R.T + t
        A = g["IB"][:rs.K_FIT, idx].reshape(rs.K_FIT, -1).T.astype(float) / 0.001
        y = (Y[idx] - g["V0"][idx]).ravel() / 0.001
        c = np.linalg.solve(A.T @ A + np.eye(rs.K_FIT), A.T @ y)
    return c


def true_mesh_fit(s, lm=False):
    me = TrueMesh(fits.truth(s)["V"], seed=abs(hash(s)) % 1000)
    idx, sg = fits2.mesh_idx(s)
    ev = fits.evs(s, ["front"]) if lm else []
    f = fitlib.fit(ev, robust=True) if ev else {"c": np.zeros(rs.K_FIT)}
    tmesh.align(me, rs.head(f["c"]))
    for _ in range(20):
        R = tmesh.rows(me, f["c"], idx, np.full(len(idx), 1.0))
        f = fitlib.fit(ev, robust=True, rows=R, c_init=f["c"]) if ev else {"c": np.linalg.solve(R[0].T @ R[0] + np.eye(rs.K_FIT), R[0].T @ R[1])}
    return f


M = {"O0 the basis's reach: truth projected on 120 components": reach,
     "O1 TRUE surface through the mesh pipeline, alone (1 mm)": true_mesh_fit,
     "O2 front lm + TRUE surface through the mesh pipeline": lambda s: true_mesh_fit(s, True)}
if __name__ == "__main__":
    fits.run(M, out="fits")
