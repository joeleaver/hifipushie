"""measured.py: MEASURED macros from one front picture (item C). Regress each of humanmacro's 37 macros from what a
picture gives: the detector's 478 points (Procrustes-aligned), the head's silhouette (widths by level, from the mask)
and shading (luminance at the detector's points, against the face's mean), on renders of sampled heads with random
pose / lens / light / look / expression: the calibrate-on-renders trick of the 478 table.
  run.sh measured.py train [n]     build the training set (cached in $D2/measured_train.npz), fit, print held-out
                                   accuracy per macro per feature set, save $D2/measured_model.npz
  run.sh measured.py truth         the same model on the 10 truth heads (never seen) vs the MAP fit's own macros and
                                   a simulated said read; then the fit rows (face mm) with measured macros
"""
import json
import os
import sys

import numpy as np

import exp2
import fitlib
import rs
import subjects
import table as tb
from hifipushie import humanmacro as hm

D2 = os.environ.get("D2", "/mnt/data/hifipushie/refstudy2")
LEVELS = np.linspace(-0.9, 1.5, 17)     # silhouette levels: 0 = the eye line, 1 = the chin (detector point 152)
IRIS = (468, 473)
CHIN, NASION = 152, 168


def features(img, zb, d):
    """{"pts": aligned xy of the 478 (956,), "sil": widths by level / interocular, "shade": luminance at the points}"""
    P = d["P"][:, :2]
    e0, e1 = P[IRIS[0]], P[IRIS[1]]
    io = np.linalg.norm(e1 - e0)
    mid = 0.5 * (e0 + e1)
    ax = (e1 - e0) / io
    if ax[0] < 0:
        ax = -ax
    up = np.array([-ax[1], ax[0]])
    if (P[CHIN] - mid) @ up < 0:
        up = -up                        # `up` points DOWN the face (toward the chin)
    Q = np.c_[(P - mid) @ ax, (P - mid) @ up] / io
    hgt = Q[CHIN, 1]
    m = np.isfinite(zb)
    h, w = m.shape
    sil = []
    for lv in LEVELS:                    # the mask's extent along the eye axis at this level, left and right of the mid-line
        c = mid + up * (lv * hgt * io)
        t = np.arange(-2.2 * io, 2.2 * io)
        xy = c[None] + t[:, None] * ax[None]
        u, v = np.round(xy[:, 0]).astype(int), np.round(xy[:, 1]).astype(int)
        ok = (u >= 0) & (u < w) & (v >= 0) & (v < h)
        on = np.zeros(len(t), bool)
        on[ok] = m[v[ok], u[ok]]
        if on.any():
            sil += [-t[on].min() / io, t[on].max() / io]
        else:
            sil += [0.0, 0.0]
    g = np.asarray(img, float).mean(2)
    u = np.clip(np.round(P[:, 0]).astype(int), 0, w - 1)
    v = np.clip(np.round(P[:, 1]).astype(int), 0, h - 1)
    # a 5 px box mean at each point, against the mean over all points (the light's level drops out)
    from scipy import ndimage
    gs = ndimage.uniform_filter(g, 5)
    lum = gs[v, u]
    return {"pts": Q.ravel(), "sil": np.array(sil + [hgt]), "shade": lum / max(lum.mean(), 1e-6) - 1.0}


def sample(n, seed0=7000):
    rng = np.random.default_rng(11)
    imgs, meta = [], []
    for s in range(n):
        c = np.random.default_rng(seed0 + s).normal(0, 1.0, rs.K_TRUE)
        V = rs.head(c)
        z = hm.read(V=V)
        Vv = V
        if s % 3 == 1:
            a = rng.uniform(0.3, 1.2)
            Vv = V + rs.expression({"lid_upper": 0.0018 * a, "lid_lower": 0.0008 * a, "smile": 0.004 * a * rng.uniform(-0.3, 1), "brow_inner": -0.002 * a})
        cam = rs.make_cam(V, yaw=rng.normal(0, 4), pitch=rng.normal(0, 5), roll=rng.normal(0, 2.5), lens=float(rng.choice([35, 50, 70, 85])),
                          fill=rng.uniform(0.5, 0.68), off=(rng.normal(0, 0.01), rng.normal(0, 0.01)))
        light = [-0.35 + rng.normal(0, 0.25), -0.45 + rng.normal(0, 0.15), -0.82]
        img, zb = rs.render(Vv, cam, light=light, albedo=rs.skinned_albedo(s) if s % 2 == 0 else None)
        imgs.append(img)
        meta.append((zb, np.array([z[k] for k in hm.NAMES])))
    det = rs.detect(imgs)
    F, Z = {"pts": [], "sil": [], "shade": []}, []
    for img, (zb, z), d in zip(imgs, meta, det):
        if d is None:
            continue
        f = features(img, zb, d)
        for k in F:
            F[k].append(f[k])
        Z.append(z)
    return {k: np.array(v) for k, v in F.items()}, np.array(Z)


SETS = {"points": ("pts",), "points + silhouette": ("pts", "sil"), "points + shading": ("pts", "shade"), "all": ("pts", "sil", "shade")}
NPC = {"pts": 70, "sil": 20, "shade": 30}


def fit_model(F, Z, keys, alpha=None):
    """Per block: standardise, PCA; ridge on the stacked scores. Returns the model dict."""
    blocks, X = {}, []
    for k in keys:
        mu, sd = F[k].mean(0), F[k].std(0) + 1e-9
        A = (F[k] - mu) / sd
        _, s, vt = np.linalg.svd(A, full_matrices=False)
        n = min(NPC[k], len(s))
        B = vt[:n].T / (s[:n] / np.sqrt(len(A)))
        blocks[k] = (mu, sd, B)
        X.append(A @ B)
    X = np.hstack(X)
    X1 = np.c_[X, np.ones(len(X))]
    alpha = 3.0 if alpha is None else alpha
    R = np.eye(X1.shape[1]) * alpha
    R[-1, -1] = 0
    W = np.linalg.solve(X1.T @ X1 + R, X1.T @ Z)
    return {"keys": keys, "blocks": blocks, "W": W}


def predict(M, F):
    X = np.hstack([((F[k] - M["blocks"][k][0]) / M["blocks"][k][1]) @ M["blocks"][k][2] for k in M["keys"]])
    return np.c_[X, np.ones(len(X))] @ M["W"]


def cv(F, Z, keys, folds=5):
    n = len(Z)
    idx = np.random.default_rng(3).permutation(n)
    P = np.zeros_like(Z)
    for f in range(folds):
        te = idx[f::folds]
        tr = np.setdiff1d(idx, te)
        M = fit_model({k: v[tr] for k, v in F.items()}, Z[tr], keys)
        P[te] = predict(M, {k: v[te] for k, v in F.items()})
    return P


def train(n=600):
    f = f"{D2}/measured_train_{n}.npz"
    if os.path.exists(f):
        z = np.load(f)
        F, Z = {k: z[k] for k in ("pts", "sil", "shade")}, z["Z"]
    else:
        F, Z = sample(n)
        np.savez_compressed(f, Z=Z, **F)
    print(f"{len(Z)} of {n} training pictures detected")
    res = {}
    for name, keys in SETS.items():
        P = cv(F, Z, keys)
        res[name] = np.sqrt(((P - Z) ** 2).mean(0))
    print("held-out rms error (population sigmas; 1.0 = knows nothing) per macro, by feature set:")
    print(f"{'':18s}" + "".join(f"{k[:14]:>16s}" for k in SETS))
    order = np.argsort(res["all"])
    for i in order:
        print(f"{hm.NAMES[i]:18s}" + "".join(f"{res[k][i]:16.2f}" for k in SETS))
    print(f"{'mean':18s}" + "".join(f"{res[k].mean():16.2f}" for k in SETS))
    M = fit_model(F, Z, SETS["all"])
    import pickle
    pickle.dump({"M": M, "rms": res["all"], "names": hm.NAMES}, open(f"{D2}/measured_model.pkl", "wb"))
    json.dump({hm.NAMES[i]: {k: round(float(res[k][i]), 3) for k in SETS} for i in order}, open(f"{D2}/measured_cv.json", "w"), indent=1)


def measured(sub, mdl, view="front"):
    d = tb.det(sub["name"], view)
    if d is None:
        return None
    zb = np.load(subjects.OUT / f"{sub['name']}_{view}_zb.npy")
    f = features(subjects.image(sub["name"], view), zb, d)
    return predict(mdl["M"], {k: v[None] for k, v in f.items()})[0]


def truth():
    import pickle
    mdl = pickle.load(open(f"{D2}/measured_model.pkl", "rb"))
    subs = [subjects.load(n) for n in subjects.names()]
    Zt, Zm, Zf, Zr = [], [], [], []
    for s in subs:
        zt = hm.read(V=s["V"])
        Zt.append([zt[k] for k in hm.NAMES])
        Zm.append(measured(s, mdl))
        f = fitlib.fit(exp2.ev(s, ["front"]), robust=True)
        zf = hm.read(f["c"])
        Zf.append([zf[k] for k in hm.NAMES])
        rd = exp2.reader(s)
        Zr.append([rd[k][0] if k in rd else 0.0 for k in hm.NAMES])
    Zt, Zm, Zf, Zr = map(np.array, (Zt, Zm, Zf, Zr))
    e = lambda A: np.sqrt(((A - Zt) ** 2).mean(0))  # noqa: E731
    em, ef, er, e0 = e(Zm), e(Zf), e(Zr), np.sqrt((Zt ** 2).mean(0))
    print("the 10 truth heads (never seen): rms error in sigmas per macro")
    print(f"{'':18s}{'truth sd':>10s}{'measured':>10s}{'MAP fit':>10s}{'said read':>10s}{'CV rms':>10s}   who knows it")
    for i in np.argsort(em):
        who = "picture" if em[i] < min(0.6, ef[i] - 0.05) else ("fit" if ef[i] < 0.6 else ("read only" if hm.NAMES[i] in exp2.READABLE else "nobody"))
        print(f"{hm.NAMES[i]:18s}{e0[i]:10.2f}{em[i]:10.2f}{ef[i]:10.2f}{er[i]:10.2f}{mdl['rms'][i]:10.2f}   {who}")
    print(f"{'mean':18s}{e0.mean():10.2f}{em.mean():10.2f}{ef.mean():10.2f}{er.mean():10.2f}{mdl['rms'].mean():10.2f}")

    def mrows(s, cut=0.8, scale=1.0):
        z = measured(s, mdl)
        rd = {hm.NAMES[i]: (float(z[i]), float(max(mdl["rms"][i], 0.25) * scale)) for i in range(len(z)) if mdl["rms"][i] < cut and hm.NAMES[i] not in hm.table()["weak"]}
        return hm.prior_rows(rd)

    METHODS = {
        "C0 front, detector MAP": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True),
        "C1 + said read (noisy reader)": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True, rows=hm.prior_rows(exp2.reader(s))),
        "C2 + MEASURED macros (cv rms as sigma)": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True, rows=mrows(s)),
        "C3 + measured, sigma x2 (errors not independent)": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True, rows=mrows(s, scale=2.0)),
        "C4 + measured (x2) + said read": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True, rows=exp2.stack(mrows(s, scale=2.0), hm.prior_rows(exp2.reader(s)))),
        "C5 + macros exact (ceiling)": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True, rows=hm.prior_rows(exp2.reader(s, exact=True))),
    }
    res = {}
    for m, fn in METHODS.items():
        res[m] = {}
        for s in subs:
            f = fn(s)
            sc = rs.score(rs.head(f["c"]), s["V"])
            sc["sigma"] = float(np.sqrt((np.asarray(f["c"]) ** 2).mean()))
            res[m][s["name"]] = sc
        tb.show(res, [m])
    json.dump(res, open(f"{D2}/measured_table.json", "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "train":
        train(int(sys.argv[2]) if len(sys.argv) > 2 else 600)
    else:
        truth()
