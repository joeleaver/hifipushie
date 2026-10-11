"""lidmap.py: the upper lid as ONE surface on GNM's own mesh topology (library).
GNM's skin round the eye is a quad grid of closed RINGS round the opening: ring 0 = the lid margin (skin next to the
socket lining), ring k = k edges out; negative rings go into the socket lining. Each ring is ordered round the eye, so
(ring, position along it) is a grid on which any head with GNM's vertex order can be compared vertex for vertex.
All lengths in mm, in the EYE FRAME: origin = the eyeball's centre, u toward the subject's left (the left eye's outer
corner), v up, w forward (GNM frame x, y, z)."""
import numpy as np

from hifipushie import gnm_controls as gc

_C = {}
NR = 14     # rings out from the margin
NI = 5      # rings into the socket


def topo():
    """{"ring": per GNM vertex ring index of the LEFT eye (-NI..NR, 99 elsewhere), "loops": {k: ordered vertex ids}}."""
    if "t" in _C:
        return _C["t"]
    g = gc.gnm()
    Q = g["quads"]
    gr = g["groups"]
    T = g["T"]
    n = len(T)
    skin, sock = gr["skin"], gr["eye_sockets"]
    E = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
    E = E[skin[E].all(1)]
    nb = [[] for _ in range(n)]
    for a, b in E:
        nb[a].append(b)
        nb[b].append(a)
    cl = g["J"][2]
    m = (sock[E[:, 0]] != sock[E[:, 1]])
    r0 = np.unique(np.where(sock[E[m, 0]], E[m, 1], E[m, 0]))
    r0 = r0[np.linalg.norm(T[r0] - cl, axis=1) < 0.03]
    ring = np.full(n, 99)
    ring[r0] = 0
    # outward: skin that is not lining; inward: lining
    for sgn, ok, lim in ((1, ~sock, NR), (-1, sock, NI)):
        cur = list(r0)
        for k in range(1, lim + 1):
            nxt = []
            for a in cur:
                for b in nb[a]:
                    if ring[b] == 99 and ok[b]:
                        ring[b] = sgn * k
                        nxt.append(b)
            cur = nxt
    loops = {}
    for k in range(-NI, NR + 1):
        ids = np.flatnonzero(ring == k)
        if len(ids) < 4:
            continue
        P = T[ids] - cl
        ang = np.arctan2(P[:, 1], P[:, 0])           # 0 = outer corner (left eye, +x), +90 = top
        loops[k] = ids[np.argsort(ang)]
    _C["t"] = {"ring": ring, "loops": loops, "nb": nb}
    return _C["t"]


def eye_frame_raw(c=None):
    """GNM's own left eyeball: (centre, radius) in GNM's frame, mm (the sclera's sphere; the joint is its centre)."""
    g = gc.gnm()
    V = gc.vertices(c, None) * 1000
    m = g["groups"]["left_eye"] & g["groups"]["scleras"]
    P = V[m]
    A = np.c_[2 * P, np.ones(len(P))]
    sol = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    ctr = sol[:3]
    return ctr, float(np.sqrt(sol[3] + ctr @ ctr))


def column(V, ctr, u=0.0, upper=True):
    """The lid's rows at the column u (mm from the eye centre): per ring k, the point where the ring's upper (lower)
    half crosses x = u: rows [(k, v, w)] from the deepest lining ring to the brow."""
    t = topo()
    g = gc.gnm()
    TUP = g["T"][:, 1] > g["J"][2][1] + 0.0003
    out = []
    for k in sorted(t["loops"]):
        ids = t["loops"][k]
        P = V[ids] - ctr
        nn = len(ids)
        best = None
        for i in range(nn):
            a, b = P[i], P[(i + 1) % nn]
            if (a[0] - u) * (b[0] - u) > 0 or a[0] == b[0]:
                continue
            f = (u - a[0]) / (b[0] - a[0])
            p = a + f * (b - a)
            if np.linalg.norm(b - a) > 8:
                continue
            if k >= 0 and (TUP[ids[i]] and TUP[ids[(i + 1) % nn]]) != upper:   # the half by the TEMPLATE (a low margin stays upper)
                continue
            if k < 0:      # lining: pick the half by its own margin side later (keep both, choose by v sign of ring 0)
                if (p[1] > -1.0) != upper:
                    continue
            if best is None or (upper and p[1] > best[1]) or (not upper and p[1] < best[1]):
                best = p
        if best is not None:
            out.append((k, float(best[1]), float(best[2])))
    return out


def grid(V, ctr, n=41, rings=range(0, NR + 1)):
    """The upper lid as a (ring, column) grid: each ring's upper half resampled at n columns between its own x extremes
    of ring 0 (u from the inner to the outer end of the margin). Returns (U, P): U (n,) u in mm, P (rings, n, 3)."""
    t = topo()
    r0 = V[t["loops"][0]] - ctr
    U = np.linspace(r0[:, 0].min() + 0.5, r0[:, 0].max() - 0.5, n)
    out = np.full((len(list(rings)), n, 3), np.nan)
    for j, k in enumerate(rings):
        for i, u in enumerate(U):
            col = [r for r in column(V, ctr, u) if r[0] == k]
            if col:
                out[j, i] = (u, col[0][1], col[0][2])
    return U, out


def stage_mesh(name):
    """(verts, normals, faces) of the dressed stage's skin mesh (the scene cache's biggest), world, metres."""
    import glob

    from hifipushie import store
    best = None
    for f in glob.glob(str(store.HOME / f"_g3_{name}" / "scene_cache" / "*.npz")):
        if "_" in f.split("/")[-1].replace(".npz", ""):
            continue
        z = np.load(f, allow_pickle=True)
        if "verts" in z.files and (best is None or len(z["verts"]) > len(best[0])):
            best = (np.asarray(z["verts"], float), np.asarray(z["normals"], float), np.asarray(z["faces"]))
    return best


def to_stage(name, ht, Vs):
    """The rigid move (R, t: X_stage = X @ R.T + t) from the template-pose head (head_template) to the stage's world:
    from the spec's landmark joints, refined by a few closest-point rounds on the face's front."""
    from scipy.spatial import cKDTree

    from hifipushie import base as basemod, skin_look, store
    J = skin_look._J(store.load(name))
    A, B = [], []
    for k, i in basemod.LANDMARKS.items():
        if k in J:
            A.append(ht["lm68"][i])
            B.append(J[k])
    A, B = np.array(A), np.array(B)

    def rigid(A, B):
        ca, cb = A.mean(0), B.mean(0)
        U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
        d = np.sign(np.linalg.det(U @ Vt))
        R = (U @ np.diag([1, 1, d]) @ Vt).T
        return R, cb - ca @ R.T
    R, t = rigid(A, B)
    g = gc.gnm()
    sk = skin_ids()
    m = (g["groups"]["hockey_mask"] & g["groups"]["skin_exterior"])[sk]
    W = np.asarray(ht["verts"], float)[:len(sk)][m]
    tree = cKDTree(Vs)
    for _ in range(8):
        X = W @ R.T + t
        d, j = tree.query(X)
        ok = d < np.percentile(d, 80)
        R, t = rigid(W[ok], Vs[j[ok]])
    return R, t, float(np.median(d))


def skin_ids():
    """GNM vertex ids of base.gnm_head's skin, in the order of head_template()["verts"]."""
    from hifipushie import base as basemod
    return np.flatnonzero(np.asarray(basemod._gnm_data()["skin"]))
