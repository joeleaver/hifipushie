"""The study's fitter: cameras + GNM identity (+ a per-picture expression) from points and outlines in pictures,
as one weighted least-squares problem with an explicit Gaussian prior, so every method in the table is a choice of
evidence, noise model and prior, not a different code path.

  identity prior: c ~ N(mu, 1) per component (GNM's components are in standard deviations) x lam
  a point: sigma in mm at the face (turned into pixels by the camera's scale)
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

import rs
from hifipushie import humanfit


def points_lm(ids=None):
    """The 68 landmarks + eye centres as a point set (GNM's own definitions)."""
    g = rs.gnm()
    ids = np.arange(70) if ids is None else np.asarray(ids)
    return {"X0": g["L0"][ids], "XB": g["LB"][:, ids], "W": g["W"][ids]}


def points_tri(vid, w):
    """Points given as weights on three vertices each."""
    g = rs.gnm()
    X0 = (g["V0"][vid] * w[..., None]).sum(1)
    XB = (g["IB"][:, vid] * w[None, ..., None]).sum(2)
    return {"X0": X0, "XB": XB, "vid": vid, "w": w}


def _expr_basis():
    """Expression components a picture may use: (ke, V, 3) world, as base.pose_expression's choice."""
    if "eb" not in rs._C:
        g = rs.gnm()["raw"]
        names = [str(n) for n in g["expression_names"]]
        comps = ([i for i, n in enumerate(names) if n.startswith("lower_face")][:40]
                 + [i for i, n in enumerate(names) if n.startswith("left_eye")][:25]
                 + [i for i, n in enumerate(names) if n.startswith("right_eye")][:25])
        rs._C["eb"] = rs.to_world(np.asarray(g["expression_basis"])[comps].astype(np.float32))
    return rs._C["eb"]


def _pts_expr(pts):
    EB = _expr_basis()
    if "W" in pts:
        return np.einsum("ln,cnd->cld", pts["W"], EB)
    return (EB[:, pts["vid"]] * pts["w"][None, ..., None]).sum(2)


def _init_cam(view, X):
    w, h = view["size"]
    uv = view["uv"]
    f0 = float(view.get("focal") or 2.0 * max(w, h))
    z0 = f0 * np.ptp(X, axis=0).max() / max(np.ptp(uv, axis=0).max(), 1.0)
    uc = uv.mean(0)
    return {"r": [0.0, 0.0, 0.0], "t": [(uc[0] - w / 2) / f0 * z0, (uc[1] - h / 2) / f0 * z0, z0], "f": f0, "size": [w, h],
            "centre": rs.gnm()["L0"][:68].mean(0).tolist(), "yaw": float(view.get("yaw", 0.0))}


def fit_cam(cam, X, uv, wt, focal=None, f_prior=None, line=None):
    """Pose (+ focal unless given) of one camera on points. f_prior = (f px, relative sigma): a soft lens guess."""
    def unpack(p):
        return {**cam, "r": p[:3], "t": p[3:6], "f": float(focal) if focal else float(p[6])}

    def res(p):
        c = unpack(p)
        r = ((humanfit.project(c, X) - uv) * wt[:, None]).ravel()
        if line is not None:   # outline pixels against their silhouette vertices, along the outline's normal
            r = np.r_[r, ((humanfit.project(c, line[0]) - line[1]) * line[2]).sum(1) * line[3]]
        if f_prior is not None and not focal:
            r = np.r_[r, np.log(c["f"] / f_prior[0]) / f_prior[1]]
        return r
    x0 = np.r_[cam["r"], cam["t"], cam["f"]]
    sol = least_squares(res, x0, x_scale=[0.1, 0.1, 0.1, 0.05, 0.05, 0.3, 500.0], loss="soft_l1", f_scale=3.0)
    c = unpack(sol.x)
    return {**c, "r": [float(v) for v in c["r"]], "t": [float(v) for v in c["t"]]}


def _dudX(cam, X):
    Rc = humanfit._cam_rot(cam)
    Xc = rs.cam_xform(cam, X)
    z = Xc[:, 2]
    J = np.zeros((len(X), 2, 3))
    J[:, 0, 0] = cam["f"] / z
    J[:, 0, 2] = -cam["f"] * Xc[:, 0] / z ** 2
    J[:, 1, 1] = cam["f"] / z
    J[:, 1, 2] = -cam["f"] * Xc[:, 1] / z ** 2
    return J @ Rc, z


def silhouette(V, cam, ears=True):
    """Vertices on the head's occluding contours through a camera (exterior skin)."""
    g = rs.gnm()
    key = "sil_T" + str(ears)
    if key not in rs._C:
        m = g["ext"].copy()
        if not ears:
            m &= ~g["gr"]["ears"]
        T = g["T"][m[g["T"]].all(1)]
        E = np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1)
        fid = np.tile(np.arange(len(T)), 3)
        o = np.lexsort((E[:, 1], E[:, 0]))
        E, fid = E[o], fid[o]
        same = (E[1:] == E[:-1]).all(1)
        rs._C[key] = (T, E[:-1][same], fid[:-1][same], fid[1:][same])
    T, E, fa, fb = rs._C[key]
    Xc = rs.cam_xform(cam, V)
    n = np.cross(Xc[T[:, 1]] - Xc[T[:, 0]], Xc[T[:, 2]] - Xc[T[:, 0]])
    front = (n * Xc[T].mean(1)).sum(1) < 0
    return np.unique(E[front[fa] != front[fb]])


def fit(views, K=rs.K_FIT, lam=1.0, mu=None, rounds=8, clip=None, step=0.0, focal=None, f_prior=None, expr=False, lam_e=1.0, rows=None,
        c_init=None, sig_floor=0.0, robust=False, log=None, outline_from=1, outline_ears=True):
    """views: [{"pts": point set, "uv": (n, 2), "sig": mm per point (or a number), "size", "yaw" hint,
                "outline": (m, 2) pixels | None, "sig_o": mm, "expr": bool (may this picture have an expression)}]
    rows: extra linear evidence on c: (A (m, K), y (m,)) already divided by its sigma (macro priors, holds).
    Returns {"c", "cams", "e": [per view offsets | None], "post": posterior covariance of c (K, K)}."""
    g = rs.gnm()
    c = np.zeros(K) if c_init is None else np.asarray(c_init, float)[:K].copy()
    mu = np.zeros(K) if mu is None else np.asarray(mu, float)[:K]
    prec = (np.full(K, float(lam)) if np.isscalar(lam) else np.asarray(lam, float)[:K])
    EBs = [(_pts_expr(v["pts"]) if (expr and v.get("expr", True)) else None) for v in views]
    ke = _expr_basis().shape[0] if expr else 0
    es = [np.zeros(ke) for _ in views]
    cams = [None] * len(views)
    lines = [None] * len(views)
    H = None
    for it in range(rounds):
        A_all, y_all = [], []
        ne = sum(ke for EB in EBs if EB is not None)
        V = None
        eo = 0
        for vi, v in enumerate(views):
            pts = v["pts"]
            X = pts["X0"] + np.tensordot(c, pts["XB"][:K], 1)
            if EBs[vi] is not None:
                X = X + np.tensordot(es[vi], EBs[vi], 1)
            sig = np.broadcast_to(np.asarray(v.get("sig", 1.0), float), (len(X),))
            cam = cams[vi] or _init_cam(v, X)
            mmpx0 = cam["t"][2] / cam["f"] * 1000
            fo = v.get("focal", focal)
            cam = fit_cam(cam, X, v["uv"], mmpx0 / np.maximum(sig, 1e-3), focal=fo, f_prior=v.get("f_prior", f_prior), line=lines[vi])
            cams[vi] = cam
            J, z = _dudX(cam, X)
            mmpx = z / cam["f"] * 1000
            wt = mmpx / np.sqrt(sig ** 2 + sig_floor ** 2)   # px -> units of sigma
            r = (v["uv"] - humanfit.project(cam, X)) * wt[:, None]
            if robust:   # Huber at 2.5 sigma
                a = np.linalg.norm(r, axis=1)
                hw = np.where(a > 2.5, np.sqrt(2.5 / np.maximum(a, 1e-9)), 1.0)
                wt, r = wt * hw, r * hw[:, None]
            Ac = np.einsum("nij,knj->nik", J, pts["XB"][:K]) * wt[:, None, None]
            blk = np.zeros((len(X) * 2, K + ne))
            blk[:, :K] = Ac.reshape(-1, K)
            if EBs[vi] is not None:
                Ae = np.einsum("nij,knj->nik", J, EBs[vi]) * wt[:, None, None]
                blk[:, K + eo:K + eo + ke] = Ae.reshape(-1, ke)
            # the residual is linear about the current point: A x ~ A x_cur + r
            xc = np.r_[c, np.concatenate([es[j] for j, EB in enumerate(EBs) if EB is not None]) if ne else np.zeros(0)]
            A_all.append(blk)
            y_all.append(blk @ xc + r.ravel())
            if v.get("outline") is not None and it >= outline_from:
                if V is None:
                    V = rs.head(c)
                sv = silhouette(V, cam, ears=outline_ears)
                P = humanfit.project(cam, V[sv])
                o = v["outline"]
                d, j = cKDTree(P).query(o)
                # the outline's normal from its own neighbours (pixels in no order: PCA of the 8 nearest)
                _, nb = cKDTree(o).query(o, k=min(8, len(o)))
                Q = o[nb] - o[nb].mean(1, keepdims=True)
                _, _, vt = np.linalg.svd(Q, full_matrices=False)
                nrm = vt[:, -1, :]
                ok = d < 0.05 * max(cam["size"])
                vs, nrm, oo = sv[j[ok]], nrm[ok], o[ok]
                Jo, zo = _dudX(cam, V[vs])
                wo = (zo / cam["f"] * 1000) / float(v.get("sig_o", 1.5))
                # many outline pixels per vertex: weigh so the outline counts as ~1 point per 3 mm of its length
                dens = max(len(oo) * float(np.median(zo / cam["f"] * 1000)) / 3.0, 1.0) / max(len(oo), 1)
                wo = wo * np.sqrt(min(dens * 3.0, 1.0))
                ro = ((oo - P[j[ok]]) * nrm).sum(1) * wo
                if robust:
                    hw = np.where(np.abs(ro) > 2.0, np.sqrt(2.0 / np.maximum(np.abs(ro), 1e-9)), 1.0)
                    wo, ro = wo * hw, ro * hw
                lines[vi] = (V[vs], oo, nrm, wo / (zo / cam["f"] * 1000) * mmpx0)
                Ao = np.einsum("ni,nij,knj->nk", nrm, Jo, g["IB"][:K, vs]) * wo[:, None]
                blk = np.zeros((len(oo), K + ne))
                blk[:, :K] = Ao
                A_all.append(blk)
                y_all.append(blk[:, :K] @ c + ro)
            if EBs[vi] is not None:
                eo += ke
        n = K + ne
        A = np.vstack(A_all)
        y = np.concatenate(y_all)
        Hm = A.T @ A
        b = A.T @ y
        Hm[np.arange(K), np.arange(K)] += prec
        b[:K] += prec * mu
        if ne:
            Hm[np.arange(K, n), np.arange(K, n)] += lam_e
        if rows is not None:
            Hm[:K, :K] += rows[0].T @ rows[0]
            b[:K] += rows[0].T @ rows[1]
        if step:   # today's solver: each round's step is ridged
            Hm[np.arange(K), np.arange(K)] += step ** 2
            b[:K] += step ** 2 * c
        x = np.linalg.solve(Hm, b)
        c = x[:K]
        if clip:
            c = np.clip(c, -clip, clip)
        eo = 0
        for vi, EB in enumerate(EBs):
            if EB is not None:
                es[vi] = x[K + eo:K + eo + ke]
                eo += ke
        H = Hm
        if log is not None:
            log.append(float(np.sqrt((c ** 2).mean())))
    return {"c": c, "cams": cams, "es": es, "H": H, "K": K}


def cranium_rows(K, w_mm=4.0, cheeks=True):
    """humanfit's holds as evidence rows: skull points (and the cheeks' fronts) stay at the mean's, sigma w_mm."""
    g = rs.gnm()
    idx = g["regions"]["cranium"][::12]
    if cheeks:
        idx = np.r_[idx, g["regions"]["cheeks"][::6]]
    A = g["IB"][:K, idx].reshape(K, -1).T.astype(float) * 1000.0 / w_mm
    return A, np.zeros(len(A))
