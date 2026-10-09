import numpy as np

def slice_mesh(V, F, x0, ez, ey):
    """forward-most y of the mesh's cut at x = x0, per z bin (0.1 mm) over the eye."""
    T = np.array([(f[0], f[j], f[j + 1]) for f in F for j in range(1, len(f) - 1)])
    s = V[T][..., 0] - x0
    keep = (s.min(1) < 0) & (s.max(1) > 0)
    T = T[keep]
    P = V[T]
    s = P[..., 0] - x0
    pts = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        m = (s[:, a] * s[:, b]) < 0
        t = s[m, a] / (s[m, a] - s[m, b])
        pts.append(P[m, a] + t[:, None] * (P[m, b] - P[m, a]))
    Q = np.concatenate(pts)
    Q = Q[(Q[:, 1] < ey) & (Q[:, 1] > ey - 0.04) & (Q[:, 2] > ez - 0.01) & (Q[:, 2] < ez + 0.03)]
    # sort along the polyline by z: front-most per bin
    zs = np.arange(ez - 0.005, ez + 0.025, 0.0001)
    out = np.full(len(zs), np.nan)
    for i, z in enumerate(zs):
        m = np.abs(Q[:, 2] - z) < 0.0004
        if m.any():
            # interpolate y at z from the two nearest by z
            q = Q[m]
            out[i] = np.interp(z, *zip(*sorted(zip(q[:, 2], q[:, 1])))) if len(q) > 1 else q[0, 1]
    return zs, out
