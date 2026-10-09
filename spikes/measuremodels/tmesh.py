"""A generated head mesh (image-to-3D: TRELLIS.2 through Oxidegen) as a measurement: lay it on a head in GNM's
topology (similarity + ICP on the face), read signed surface offsets at the head's vertices, turn them into
evidence rows for fitlib's MAP."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

import mm
import rs

TR = mm.MM / "trellis"


class Mesh:
    def __init__(self, name):
        z = np.load(TR / f"{name}.npz")
        self.name = name
        self.V = z["V"].astype(float)
        F = z["F"]
        fn = np.cross(self.V[F[:, 1]] - self.V[F[:, 0]], self.V[F[:, 2]] - self.V[F[:, 0]])
        n = np.zeros_like(self.V)
        for c in range(3):
            np.add.at(n, F[:, c], fn)
        self.N = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
        self.F = F
        self.tree = cKDTree(self.V)
        self.T = None    # (s, R, t): mesh -> head frame

    def near(self, X, T=None):
        """For head-frame points X: nearest mesh point and normal, in the head frame."""
        s, R, t = T or self.T
        Xm = ((X - t) @ R) / s
        d, j = self.tree.query(Xm)
        return s * self.V[j] @ R.T + t, self.N[j] @ R.T, d * s

    def placed(self):
        s, R, t = self.T
        return s * self.V @ R.T + t, self.N @ R.T


def _rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def _icp(mesh, X, T, iters, trim=0.8, wplane=True):
    for _ in range(iters):
        q, nq, d = mesh.near(X, T)
        keep = d <= np.quantile(d, trim)
        # similarity taking the MESH points onto the head's points (pairs fixed this round)
        s, R, t = T
        qm = ((q[keep] - t) @ R) / s
        T = rs.similarity(qm, X[keep])
    q, nq, d = mesh.near(X, T)
    return T, float(np.sort(d)[: int(len(d) * trim)].mean())


def align(mesh, H, idx=None, yaw_hint=None, T0=None, scale=True):
    """Lay the mesh on head H (GNM topology, world): similarity by ICP from the head's face vertices to the mesh.
    Without T0: starts over yaws (the generator keeps the picture's view as its front) and scales; the best wins."""
    g = rs.gnm()
    f = g["regions"]["face"] if idx is None else idx
    X = H[f]
    if T0 is not None:
        T, e = _icp(mesh, X, T0, 25)
        mesh.T = T
        return e
    hz = H[g["regions"]["head"]]
    top = hz[:, 2].max()
    hh = top - rs.landmarks(H)[8, 2]           # chin to crown
    best = None
    yaws = [0, 40, -40, 88, -88] if yaw_hint is None else [yaw_hint, yaw_hint + 20, yaw_hint - 20]
    sub = X[:: max(len(X) // 600, 1)]
    for yw in yaws:
        R = _rz(np.radians(yw))                 # turns the mesh so its face looks along -y
        Vr = mesh.V @ R.T
        mtop = Vr[:, 2].max()
        for frac in (0.3, 0.38, 0.46, 0.56, 0.68):   # the head (chin to crown) as a share of the mesh's height
            s = hh / (frac * np.ptp(Vr[:, 2]))
            up = Vr[:, 2] > mtop - frac * np.ptp(Vr[:, 2])
            c = Vr[up]
            t = np.array([H[f, 0].mean() - s * c[:, 0].mean(), H[f, 1].min() - s * c[:, 1].min(), top - s * mtop])
            T, e = _icp(mesh, sub, (s, R, t), 12)
            if best is None or e < best[1]:
                best = (T, e, yw, frac)
    T, e = _icp(mesh, X, best[0], 30)
    mesh.T = T
    mesh.start = best[2:]
    return e


def offsets(mesh, H, idx):
    """Signed offset (m) of the mesh's surface from head vertices idx, along the mesh's normal there (+ = the mesh
    lies outside the head), and whether the pair is believable (near, facing the same way)."""
    q, nq, d = mesh.near(H[idx])
    nh = mm.vnormals(H)[idx]
    a = ((q - H[idx]) * nq).sum(1)
    ok = (d < 0.02) & ((nq * nh).sum(1) > 0.3)
    return a, ok, q, nq


def rows(mesh, c, idx, sig_mm, K=rs.K_FIT, huber=2.5, realign=True):
    """Evidence rows on the identity c from the mesh: at head vertices idx (current head = head(c)), the mesh's
    surface point q and normal n: n . (V0 + IB c - q) = 0, sigma sig_mm (array per idx)."""
    g = rs.gnm()
    H = rs.head(c)
    if realign:
        align(mesh, H, T0=mesh.T)
    a, ok, q, nq = offsets(mesh, H, idx)
    sg = np.broadcast_to(np.asarray(sig_mm, float), (len(idx),)) / 1000.0
    A = np.einsum("nd,knd->nk", nq, g["IB"][:K, idx].astype(float)) / sg[:, None]
    y = (nq * (q - g["V0"][idx])).sum(1) / sg
    r = a / sg
    w = np.where(np.abs(r) > huber, np.sqrt(huber / np.maximum(np.abs(r), 1e-9)), 1.0) * ok
    return A * w[:, None], y * w


def fit_alone(mesh, idx, sig_mm, K=rs.K_FIT, rounds=6, c0=None):
    """GNM's identity laid on the mesh alone (prior 1 per sigma): the mesh read as a head."""
    c = np.zeros(K) if c0 is None else c0.copy()
    if mesh.T is None:
        align(mesh, rs.head(c))
    for _ in range(rounds):
        A, y = rows(mesh, c, idx, sig_mm, K)
        c = np.linalg.solve(A.T @ A + np.eye(K), A.T @ y)
    return c
