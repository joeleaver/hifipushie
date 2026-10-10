"""ictreg.py: register ICT FaceKit Light (asset pack "ictfacekit", MIT) to GNM's head (faces4 M1) and carry ICT's 100
identity modes onto GNM's vertices.

1. ICT's neutral and its 100 identity meshes (OBJ; identity weights are N(0, 1) in ICT's own sampler, mode k =
   identity_k - neutral), face + head / neck + eye sockets.
2. Similarity ICT -> GNM frame on the inner 68 landmarks (ICT's README indices, GNM's lm68 rows; jaw 0-16 left out).
3. Non-rigid: GNM's template + identity c (170 comps, ridge prior) fitted to ICT's neutral surface (point-to-plane
   against a dense sample of ICT's triangles), then a smooth residual (Laplacian-regularised steps) so GNM's skin lies on
   ICT's surface.
4. Binding: each GNM exterior skin vertex -> the nearest point on ICT's surface (triangle + barycentric) when within
   BIND_MAX and on the face / head; carried modes = barycentric interpolation of each mode, rotated / scaled into GNM's
   frame. Unbound vertices take the harmonic extension (faceext.fill-like) so nothing tears at the coverage's edge.
5. Report per mode: rms / max mm (GNM frame), the share GNM's 170 identity comps make of it over the WHOLE head (and
   the sd they need), and where the rest (the residual) lives by region.
Writes /mnt/data/hifipushie/faces4/out/ict_modes.npz {modes (100, n, 3) m per sd, bound (n,), fit_rms, ...}."""
import os
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree

from hifipushie import assets, base as basemod

OUT = Path(os.environ.get("OUT", "/mnt/data/hifipushie/faces4/out"))
BIND_MAX = float(os.environ.get("BIND_MAX", "0.003"))
ICT_LM68 = [1225, 1888, 1052, 367, 1719, 1722, 2199, 1447, 966, 3661, 4390, 3927, 3924, 2608, 3272, 4088, 3443, 268, 493,
            1914, 2044, 1401, 3615, 4240, 4114, 2734, 2509, 978, 4527, 4942, 4857, 1140, 2075, 1147, 4269, 3360, 1507,
            1542, 1537, 1528, 1518, 1511, 3742, 3751, 3756, 3721, 3725, 3732, 5708, 5695, 2081, 0, 4275, 6200, 6213,
            6346, 6461, 5518, 5957, 5841, 5702, 5711, 5533, 6216, 6207, 6470, 5517, 5966]
NV_SURF = 11248          # face [0:9408] + head and neck [9409:11247]


def read_obj(p, faces=False):
    vs, fs = [], []
    with open(p) as f:
        for ln in f:
            if ln.startswith("v "):
                vs.append(ln.split()[1:4])
            elif faces and ln.startswith("f "):
                fs.append([int(t.split("/")[0]) - 1 for t in ln.split()[1:]])
    V = np.asarray(vs, float)
    return (V, fs) if faces else V


def load_ict():
    d = assets.pack("ictfacekit") / "FaceXModel"
    cache = OUT / "ict_raw.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        return z["V0"], z["M"], z["T"]
    V0, F = read_obj(d / "generic_neutral_mesh.obj", faces=True)
    tri = []
    for f in F:
        if max(f) < NV_SURF:
            for k in range(1, len(f) - 1):
                tri.append([f[0], f[k], f[k + 1]])
    M = np.stack([read_obj(d / f"identity{k:03d}.obj")[:NV_SURF] - V0[:NV_SURF] for k in range(100)])
    np.savez(cache, V0=V0[:NV_SURF], M=M.astype(np.float32), T=np.asarray(tri, int))
    return V0[:NV_SURF], M, np.asarray(tri, int)


def umeyama(A, B):
    """s, R, t with B ~ s A R^T + t."""
    ca, cb = A.mean(0), B.mean(0)
    U, S, Vt = np.linalg.svd((B - cb).T @ (A - ca))
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(U @ Vt))])
    R = U @ D @ Vt
    s = float(np.trace(np.diag(S) @ D) / ((A - ca) ** 2).sum())
    return s, R, cb - s * ca @ R.T


def surface_sample(V, T, per=12):
    """dense points on the triangles: (P, tri index, bary)."""
    rng = np.random.default_rng(0)
    u = rng.random((len(T), per, 2))
    flip = u.sum(-1) > 1
    u[flip] = 1 - u[flip]
    b = np.concatenate([1 - u.sum(-1, keepdims=True), u], -1)          # (t, per, 3)
    P = np.einsum("tpk,tkd->tpd", b, V[T])
    # + the vertices themselves
    return P.reshape(-1, 3), np.repeat(np.arange(len(T)), per), b.reshape(-1, 3)


def main():
    g = basemod._gnm_data()
    TPL = np.asarray(g["template_vertex_positions"], float)
    n = len(TPL)
    names = [str(x) for x in g["identity_names"]]
    hc = [i for i, x in enumerate(names) if x.startswith("head")]
    IB = np.asarray(g["vertex_identity_basis"], float)[hc]          # (170, n, 3)
    ext = np.asarray(g["groups"]["skin_exterior"], float) > 0.5
    rows = g["lm68"]
    Wlm = np.zeros((68, n))
    for i, r in enumerate(rows):
        for v, w in zip(r[0::2], r[1::2]):
            Wlm[i, int(v)] += float(w)
    V0, M, T = load_ict()
    # 2. similarity on the inner landmarks
    inner = list(range(17, 68))
    s, R, t = umeyama(V0[[ICT_LM68[i] for i in inner]], (Wlm @ TPL)[inner])
    Vi = s * V0 @ R.T + t                                             # ICT neutral in GNM's frame
    Mi = s * M @ R.T                                                  # modes, GNM frame, per sd
    print(f"similarity scale {s:.5f}; landmark rms after: "
          f"{np.sqrt(((Vi[[ICT_LM68[i] for i in inner]] - (Wlm @ TPL)[inner]) ** 2).sum(1).mean()) * 1e3:.2f} mm")
    P, ti, bb = surface_sample(Vi, T)
    tree = cKDTree(P)
    # ICT vertex normals (for point-to-plane)
    fn = np.cross(Vi[T[:, 1]] - Vi[T[:, 0]], Vi[T[:, 2]] - Vi[T[:, 0]])
    vn = np.zeros_like(Vi)
    for k in range(3):
        np.add.at(vn, T[:, k], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
    Pn = np.einsum("pk,pkd->pd", bb, vn[T[ti]])
    Pn /= np.maximum(np.linalg.norm(Pn, axis=1, keepdims=True), 1e-15)
    sk = np.flatnonzero(ext)
    # 3a. identity fit (point-to-plane, ridge), a few ICP rounds
    c = np.zeros(len(hc))
    lam = float(os.environ.get("LAM", "1e-6"))
    for it in range(8):
        X = TPL + np.tensordot(c, IB, 1)
        dist, j = tree.query(X[sk])
        ok = dist < 0.01
        rows_ = sk[ok]
        nn = Pn[j[ok]]
        r = np.einsum("ij,ij->i", P[j[ok]] - X[rows_], nn)
        A = np.einsum("kid,id->ik", IB[:, rows_], nn)                 # (m, 170)
        c = c + np.linalg.solve(A.T @ A + lam * np.eye(len(hc)), A.T @ r - lam * c)
        print(f"  identity ICP {it}: rms {np.sqrt((r ** 2).mean()) * 1e3:.2f} mm on {ok.sum()} verts, |c| {np.linalg.norm(c):.1f}",
              flush=True)
    X = TPL + np.tensordot(c, IB, 1)
    # 3b. smooth residual: Laplacian-regularised steps onto ICT's surface
    q = np.asarray(g["quads"], int)
    e = np.r_[q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]]
    Aj = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)).tocsr()
    Aj = ((Aj + Aj.T) > 0).astype(float)
    deg = np.maximum(np.asarray(Aj.sum(1)).ravel(), 1)
    L = (sp.eye(n) - sp.diags(1 / deg) @ Aj).tocsr()
    mu = float(os.environ.get("MU", "2.0"))
    for it in range(int(os.environ.get("NR", "6"))):
        dist, j = tree.query(X)
        w = (ext & (dist < 0.006)).astype(float)
        tgt = P[j]
        nn = Pn[j]
        # step: minimise sum w ((x + u - tgt) . n)^2 + mu |L u|^2  (per axis approx: target the plane's foot)
        foot = X + np.einsum("ij,ij->i", tgt - X, nn)[:, None] * nn
        Wd = sp.diags(w)
        Hs = (Wd + mu * (L.T @ L) + 1e-6 * sp.eye(n)).tocsc()
        U = np.column_stack([spsolve(Hs, Wd @ (foot - X)[:, k]) for k in range(3)])
        X = X + U
        print(f"  residual step {it}: mean dist {dist[w > 0].mean() * 1e3:.2f} mm, p95 {np.percentile(dist[w > 0], 95) * 1e3:.2f}",
              flush=True)
    # 4. binding: nearest point on ICT's surface
    dist, j = tree.query(X)
    bound = ext & (dist < BIND_MAX)
    Mb = np.zeros((100, n, 3))
    bi = np.flatnonzero(bound)
    TT = T[ti[j[bi]]]
    bw = bb[j[bi]]
    for k in range(100):
        Mb[k][bi] = np.einsum("pk,pkd->pd", bw, Mi[k][TT])
    # unbound skin: harmonic extension from the bound skin (the rest of GNM's mesh: zero)
    skin = np.asarray(g["groups"]["skin"], float) > 0.5
    free = skin & ~bound
    fixed = ~free
    Lff = (L[free][:, free] + 1e-9 * sp.eye(int(free.sum()))).tocsc()
    Lfx = L[free][:, fixed]
    from scipy.sparse.linalg import splu
    lu = splu(Lff)
    for k in range(100):
        for a in range(3):
            Mb[k][free, a] = lu.solve(-(Lfx @ Mb[k][fixed, a]))
    report(Mb, IB, g, hc, sk)
    np.savez(OUT / "ict_modes.npz", modes=Mb.astype(np.float32), bound=bound, X_fit=X, c_fit=c, s=s, R=R, t=t)


NOISE = float(os.environ.get("NOISE", "0.0003"))   # m per coordinate: the MAP fit's noise (ridge = NOISE^2)


def report(Mb, IB, g, hc, sk0):
    """per mode over the FACE (GNM's *_region groups): the share GNM's identity makes unconstrained (lstsq) and as a MAP
    fit (prior N(0, I), noise NOISE per coordinate), the MAP's |c|, and where the MAP residual lives."""
    regs = {r: np.asarray(g["groups"][r], float) > 0.5 for r in g["groups"] if r.endswith("_region")}
    face = np.zeros(len(Mb[0]), bool)
    for m in regs.values():
        face |= m
    sk = np.intersect1d(sk0, np.flatnonzero(face))
    Bf = IB[:, sk].reshape(len(hc), -1)
    G = Bf @ Bf.T
    reg = {r: m[sk] for r, m in regs.items()}
    lines, shares = [], []
    for k in range(len(Mb)):
        y = Mb[k][sk].ravel()
        c_ls = np.linalg.solve(G + 1e-12 * np.eye(len(G)), Bf @ y)
        sh_ls = 1 - ((y - Bf.T @ c_ls) ** 2).sum() / max((y ** 2).sum(), 1e-30)
        ck = np.linalg.solve(G + NOISE ** 2 * np.eye(len(G)), Bf @ y)
        res = (y - Bf.T @ ck).reshape(-1, 3)
        sh = 1 - (res ** 2).sum() / max((y ** 2).sum(), 1e-30)
        shares.append((sh_ls, sh, float(np.linalg.norm(ck))))
        e2 = (res ** 2).sum(1)
        top = sorted(((e2[m].sum() / max(e2.sum(), 1e-30), r) for r, m in reg.items()), reverse=True)[:3]
        mm_ = np.linalg.norm(Mb[k][sk], axis=1)
        lines.append(f"mode {k:3d}: face rms {np.sqrt((mm_ ** 2).mean()) * 1e3:5.2f} max {mm_.max() * 1e3:5.2f} mm | GNM "
                     f"lstsq {sh_ls:.2f}, MAP {sh:.2f} at |c| {np.linalg.norm(ck):4.1f} | MAP residual rms "
                     f"{np.sqrt(e2.mean()) * 1e3:.2f} mm in " + ", ".join(f"{r.replace('_region', '')} {f:.2f}" for f, r in top))
    sh = np.array(shares)
    lines.append(f"ALL: lstsq share median {np.median(sh[:, 0]):.2f}; MAP share median {np.median(sh[:, 1]):.2f} "
                 f"(modes 0-9 {np.median(sh[:10, 1]):.2f}, 10-49 {np.median(sh[10:50, 1]):.2f}, 50-99 "
                 f"{np.median(sh[50:, 1]):.2f}); MAP |c| median {np.median(sh[:, 2]):.1f}")
    txt = "\n".join(lines)
    (OUT / "ict_modes.txt").write_text(txt)
    print(txt)
    np.save(OUT / "ict_shares.npy", sh)


def report_only():
    g = basemod._gnm_data()
    names = [str(x) for x in g["identity_names"]]
    hc = [i for i, x in enumerate(names) if x.startswith("head")]
    IB = np.asarray(g["vertex_identity_basis"], float)[hc]
    ext = np.asarray(g["groups"]["skin_exterior"], float) > 0.5
    report(np.load(OUT / "ict_modes.npz")["modes"].astype(float), IB, g, hc, np.flatnonzero(ext))


if __name__ == "__main__":
    report_only() if "report" in sys.argv[1:] else main()
