"""Light: the transfer per texel, the key's basis, the fitted light; our own albedo. Part of the skin projection (skin_project.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_project
from .skin_project_atlas import interp

# ---------------------------------------------------------------- light
def _dirs(n: int = skin_project.N_DIRS) -> np.ndarray:
    k = np.arange(n) + 0.5
    th = np.arccos(1 - 2 * k / n)
    ph = np.pi * (1 + 5 ** 0.5) * k
    return np.c_[np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]


def transfer(mesh: dict, X: np.ndarray, N: np.ndarray, sub: np.ndarray | None = None, n_dirs: int = skin_project.N_DIRS) -> dict:
    """The head's light transport at points: {"T" (n, 9): irradiance per unit of each order-2 SH coefficient of the
    light, through each point's own visibility (self-shadow and occlusion in it), "ao" (n,), "D" (directions),
    "sub_vis" (D, m) the visibility of the points `sub` per direction (the key light's search)}."""
    from . import likeness_render
    Vo, Fo = likeness_render._occluders(mesh)
    D = _dirs(n_dirs)
    Yk = likeness_render.sh9(D)
    T = np.zeros((len(X), 9), np.float32)
    num, den = np.zeros(len(X), np.float32), np.zeros(len(X), np.float32)
    sv = np.zeros((n_dirs, len(sub)), bool) if sub is not None else None
    pos = np.full(len(X), -1)
    if sub is not None:
        pos[sub] = np.arange(len(sub))
    for k, d in enumerate(D):
        c = N @ d
        up = np.flatnonzero(c > 0)
        if not len(up):
            continue
        dm = likeness_render._DepthMap(Vo, Fo, d, skin_project.VIS_MM)
        vis = dm.lit(X[up], N[up])
        cv = (c[up] * vis).astype(np.float32)
        T[up] += cv[:, None] * Yk[k].astype(np.float32)
        num[up] += cv
        den[up] += c[up].astype(np.float32)
        if sv is not None:
            q = pos[up]
            sv[k, q[q >= 0]] = vis[q >= 0]
    T *= 4.0 / n_dirs
    return {"T": T, "ao": num / np.maximum(den, 1e-6), "D": D, "sub_vis": sv}


def key_basis(mesh: dict, X: np.ndarray, N: np.ndarray, d, disc: float = skin_project.KEY_DISC) -> np.ndarray:
    """A soft key light's irradiance at points (cos x the share of its disc that sees the point)."""
    from . import likeness_render
    Vo, Fo = likeness_render._occluders(mesh)
    d = np.asarray(d, float) / np.linalg.norm(d)
    a = np.cross(d, [1.0, 0, 0] if abs(d[0]) < 0.9 else [0, 1.0, 0])
    a /= np.linalg.norm(a)
    b = np.cross(d, a)
    r = np.tan(np.radians(disc)) * 0.75
    ds = [d] + [d + r * (np.cos(t) * a + np.sin(t) * b) for t in np.arange(8) * np.pi / 4]
    c = np.clip(N @ d, 0, None)
    up = np.flatnonzero(c > 0)
    v = np.zeros(len(up))
    for q in ds:
        v += likeness_render._DepthMap(Vo, Fo, q / np.linalg.norm(q), skin_project.VIS_MM).lit(X[up], N[up])
    out = np.zeros(len(X), np.float32)
    out[up] = c[up] * v / len(ds)
    return out


def _irls(A: np.ndarray, r: np.ndarray, w: np.ndarray, rounds: int = 6, k: float = 0.12, ridge: float = 1e-4) -> tuple:
    """Robust weighted least squares r ~ A x (Huber on the residual relative to the prediction). (x, rms)."""
    ww = w.copy()
    x = np.zeros(A.shape[1])
    for _ in range(rounds):
        Aw = A * ww[:, None]
        x = np.linalg.solve(A.T @ Aw + ridge * np.eye(A.shape[1]) * float(ww.sum()), Aw.T @ r)
        p = A @ x
        e = (r - p) / np.maximum(np.abs(p), 0.05 * float(np.median(np.abs(r))))
        ww = w * np.where(np.abs(e) <= k, 1.0, k / np.maximum(np.abs(e), 1e-9))
    p = A @ x
    e = (r - p) / np.maximum(np.abs(p), 0.05 * float(np.median(np.abs(r))))
    return x, float(np.sqrt(np.sum(ww * e ** 2) / max(float(ww.sum()), 1e-9)))


def fit_light(view: dict, target: np.ndarray, fit: np.ndarray, key: bool = True, key_dir=None, mesh=None, colour_w: np.ndarray | None = None) -> dict:
    """One picture's light against a target albedo: view = {"rgb", "T", "sub", "sub_vis", "D", "X", "N"}; target
    (n, 3) linear albedo; fit: indices of the texels fitted (trusted plain skin). Returns {"sh" (3, 9), "key":
    {"dir", "rgb"} | None, "S" (n, 3) the shading at every texel, "rms": relative residual on luminance, "rms0":
    without the key, "ambient" / "directional": shares}."""
    T = view["T"]
    r = view["rgb"][fit] / np.maximum(target[fit], 1e-4)
    rY = r @ skin_project.Y
    w = np.ones(len(fit))
    A = T[fit].astype(float)
    x0, rms0 = _irls(A, rY, w)
    kd, kb_fit, best = None, None, rms0
    if key_dir is not None:
        kd = np.asarray(key_dir, float)
    elif key and view.get("sub_vis") is not None:
        # the search: each direction of the set as a soft key (its neighbours' visibility averaged), on the fit texels
        pos = np.full(len(T), -1)
        pos[view["sub"]] = np.arange(len(view["sub"]))
        q = pos[fit]
        has = q >= 0
        if has.sum() > 500:
            D = view["D"]
            sv = view["sub_vis"][:, q[has]]
            Nf = view["N"][fit][has]
            Af, rf = A[has], rY[has]
            G = Af.T @ Af + 1e-4 * np.eye(9) * has.sum()
            base = float(np.sum((rf - Af @ np.linalg.solve(G, Af.T @ rf)) ** 2))
            cosn = np.cos(np.radians(2.2 * skin_project.KEY_DISC))
            res = []
            for k, d in enumerate(D):
                nb = np.flatnonzero(D @ d > cosn)
                b = sv[nb].mean(0) * np.clip(Nf @ d, 0, None)
                if b.sum() < 0.02 * len(b):
                    res.append(np.inf)
                    continue
                A2 = np.c_[Af, b]
                x = np.linalg.solve(A2.T @ A2 + 1e-4 * np.eye(10) * has.sum(), A2.T @ rf)
                res.append(float(np.sum((rf - A2 @ x) ** 2)) if x[9] > 0 else np.inf)
            k = int(np.argmin(res))
            if res[k] < (1 - skin_project.KEY_GAIN) ** 2 * base:
                # refine between the set's directions: the residual-weighted mean of the best few neighbours
                nb = np.flatnonzero(D @ D[k] > np.cos(np.radians(16)))
                wq = np.array([max(base - res[j], 0.0) if np.isfinite(res[j]) else 0.0 for j in nb]) ** 2
                kd = (D[nb] * wq[:, None]).sum(0)
                kd /= np.linalg.norm(kd)
    kb = None
    if kd is not None:
        kb = view["key_b"] if view.get("key_b") is not None and view.get("key_dir") is not None and np.allclose(view["key_dir"], kd) else key_basis(mesh, view["X"], view["N"], kd)
        view["key_b"], view["key_dir"] = kb, kd
        kb_fit = kb[fit].astype(float)
        A2 = np.c_[A, kb_fit]
        x1, rms1 = _irls(A2, rY, w)
        share = float(np.median(kb_fit) * x1[9]) / max(float(np.median(A2 @ x1)), 1e-9)
        if x1[9] <= 0 or (key_dir is None and (rms1 > (1 - skin_project.KEY_GAIN) * rms0 or share < skin_project.KEY_SHARE)):
            kd, kb = None, None
            view["key_dir"] = None
        else:
            best = rms1
    sh, krgb = np.zeros((3, 9)), np.zeros(3)
    Af = A if kd is None else np.c_[A, kb_fit]
    # the light's COLOUR is fitted only where the skin is the tone it is taken to be: colour_w (per fit texel) is 0 on
    # the beard zones (a beard's shadow is greyer and bluer than the tone: with it in the fit a front view's light came
    # out cyan and the head, rendered under that light, green beside a neutral photograph)
    wc = w if colour_w is None or float(np.sum(colour_w)) < 1500 else w * colour_w
    for c in range(3):
        x, _ = _irls(Af, r[:, c], wc)
        sh[c] = x[:9]
        if kd is not None:
            krgb[c] = max(x[9], 0.0)
    S = T.astype(float) @ sh.T
    amb = float(np.median((T[fit].astype(float) @ sh.T) @ skin_project.Y))
    if kd is not None:
        S = S + kb[:, None].astype(float) * krgb
    direct = float(np.median(kb_fit) * (krgb @ skin_project.Y)) if kd is not None else 0.0
    return {"sh": sh, "key": {"dir": [round(float(v), 4) for v in kd], "rgb": [round(float(v), 4) for v in krgb]} if kd is not None else None,
            "S": S, "rms": best, "rms0": rms0, "ambient_share": round(amb / max(amb + direct, 1e-9), 3)}


# ---------------------------------------------------------------- ours
def ours_albedo(at: dict, spec: dict, stride: int = 4, log=print) -> np.ndarray:
    """OUR skin's albedo (the model's own paint layers, no projection) at the atlas' texels: evaluated on every
    `stride`-th texel (skin_read_frames.Albedo, in Python) and interpolated: (n, 3) linear."""
    import copy
    from scipy import ndimage
    from . import likeness_render
    from . import skin_read_frames
    sp = copy.deepcopy(spec)
    (sp.get("skin") or {}).pop("projection", None)
    # nor the measured STACK (made from an earlier atlas): taken as "ours", each new atlas was retoned to the last stack's
    # colour, and a head re-projected after a form change drifted greyer every pass (an older head's g / b 1.13 -> 1.10 -> 1.08;
    # the photo's 1.17)
    (sp.get("skin") or {}).pop("stack", None)
    (sp.get("skin") or {}).pop("only", None)
    st = skin_read_frames.stage_spec(sp)
    H, W = at["shape"]
    sel = np.flatnonzero((at["ii"] % stride == stride // 2) & (at["jj"] % stride == stride // 2))
    V = at["V"]
    X = interp(at, V)[sel]
    Nv = likeness_render._vertex_normals(V, at["T"])
    N = interp(at, Nv)[sel]
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    A = skin_read_frames.Albedo(st, X, N, log=log)()
    h, w = (H + stride - 1) // stride, (W + stride - 1) // stride
    C = np.zeros((h, w, 3))
    M = np.zeros((h, w), bool)
    ci, cj = at["ii"][sel] // stride, at["jj"][sel] // stride
    C[ci, cj] = A
    M[ci, cj] = True
    idx = ndimage.distance_transform_edt(~M, return_distances=False, return_indices=True)
    C = C[idx[0], idx[1]]
    yy = (at["ii"] - stride // 2) / stride
    xx = (at["jj"] - stride // 2) / stride
    return np.stack([ndimage.map_coordinates(C[..., c], [yy, xx], order=1, mode="nearest") for c in range(3)], 1)
