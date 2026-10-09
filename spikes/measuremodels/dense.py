"""A dense model's depth / normals as evidence in fitlib's MAP, calibrated on renders.

Calibration (per model, per view class, per GNM vertex, on the calibration heads, smoothed over ~1 cm of surface):
  gain  g: truth's deviation from the mean head ~ g x the model's deviation from the mean head
  sigma s: what is left (mm for depth, unit-vector components for normals)
so a model that exaggerates relief (gain 0.5) or sees nothing somewhere (s ~ the population's own spread) is used
for exactly what it is worth.   run.sh dense.py calib <model> [inverse]
"""
import sys

import numpy as np
from scipy.spatial import cKDTree

import mm
import rs

VC = {"front": 0, "tq": 1, "profile": 2, "tq2": 3}
_C = {}


def picture_devs(pr, it, inverse=False, H=None, cam=None, vis=None):
    """Per visible vertex: the model's and (when H is the truth) the head's deviation from the mean head.
    Depth: mm along the camera's depth. Normals: camera-frame vectors.  it = mm.item (truth) or a dict with the
    same keys built from a fitted head."""
    out = {}
    Xm, nm = mm.mean_head(it)
    zt = it["Xc"][:, 2] * 1000
    if "depth" in pr or "points" in pr:
        D = pr["depth"] if "depth" in pr else pr["points"][..., 2]
        D = np.nan_to_num(np.where(np.isfinite(D), D, 0.0)).astype(float)
        z = mm.fit_z(mm.sample(D, it["pix"]), zt, it["face"].astype(float), inverse=inverse)
        out["dm_z"] = z - Xm[:, 2] * 1000
        out["dt_z"] = zt - Xm[:, 2] * 1000
    if "normal" in pr:
        n = mm.sample(pr["normal"].astype(float), it["pix"]) * np.asarray(pr.get("flip", (1, 1, 1)), float)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        out["dm_n"] = n - nm
        out["dt_n"] = it["n"] - nm
    out["nm"], out["zm"] = nm, Xm[:, 2] * 1000
    return out


def _nbr(k=40):
    if "nbr" not in _C:
        g = rs.gnm()
        V0 = g.get("V0_gnm", g["V0"])
        _C["nbr"] = cKDTree(V0).query(V0, k=k)[1]
    return _C["nbr"]


def calibrate(model, inverse=False, flip=(1, 1, 1)):
    g = rs.gnm()
    nv = len(g["V0"])
    out = {}
    for vw, ci in VC.items():
        S = {k: np.zeros(nv) for k in ("n", "mt_z", "mm_z", "tt_z", "mt_n", "mm_n", "tt_n")}
        for iid in mm.ids("cal", vw):
            pr = mm.pred(model, iid)
            if pr is None:
                continue
            pr["flip"] = flip
            it = mm.item(iid)
            d = picture_devs(pr, it, inverse)
            i = it["idx"]
            S["n"][i] += 1
            if "dm_z" in d:
                S["mt_z"][i] += d["dm_z"] * d["dt_z"]
                S["mm_z"][i] += d["dm_z"] ** 2
                S["tt_z"][i] += d["dt_z"] ** 2
            if "dm_n" in d:
                S["mt_n"][i] += (d["dm_n"] * d["dt_n"]).sum(1)
                S["mm_n"][i] += (d["dm_n"] ** 2).sum(1)
                S["tt_n"][i] += (d["dt_n"] ** 2).sum(1)
        nb = _nbr()
        P = {k: v[nb].sum(1) for k, v in S.items()}          # pooled over each vertex's neighbourhood
        ok = P["n"] >= 40 * 6
        for q, dim in (("z", 1), ("n", 2)):
            gq = np.where(P["mm_" + q] > 0, P["mt_" + q] / np.maximum(P["mm_" + q], 1e-12), 0.0)
            gq = np.clip(gq, 0.0, 1.5)
            left = np.maximum(P["tt_" + q] - 2 * gq * P["mt_" + q] + gq ** 2 * P["mm_" + q], 0) / np.maximum(P["n"], 1) / dim
            out[f"g_{q}_{ci}"] = np.where(ok, gq, 0.0).astype(np.float32)
            out[f"s_{q}_{ci}"] = np.where(ok, np.sqrt(left), np.inf).astype(np.float32)
            out[f"p_{q}_{ci}"] = np.sqrt(P["tt_" + q] / np.maximum(P["n"], 1) / dim).astype(np.float32)   # the population's own spread
        reg, _ = mm.region_of()
        print(f"{model} {vw}: calibrated vertices {ok.sum()}")
        for k in mm.REG[1:]:
            m = ok & (reg == k)
            if m.sum() < 30:
                continue
            print(f"   {k:9s} depth gain {np.median(out[f'g_z_{ci}'][m]):4.2f} left {np.median(out[f's_z_{ci}'][m]):5.2f} mm of {np.median(out[f'p_z_{ci}'][m]):5.2f} | "
                  f"normal gain {np.median(out[f'g_n_{ci}'][m]):4.2f} left {np.degrees(np.median(out[f's_n_{ci}'][m])):5.2f} deg of {np.degrees(np.median(out[f'p_n_{ci}'][m])):5.2f}")
    np.savez(mm.MM / f"dense_{model}.npz", inverse=inverse, flip=np.asarray(flip), **out)


def table(model):
    if model not in _C:
        _C[model] = dict(np.load(mm.MM / f"dense_{model}.npz"))
    return _C[model]


def normal_jac(K):
    """d(vertex normal)/d(component) about the mean head, world frame: (K, V, 3)."""
    key = f"nj{K}"
    if key not in _C:
        f = mm.MM / f"normal_jac_{K}.npy"
        if f.exists():
            _C[key] = np.load(f)
        else:
            g = rs.gnm()
            n0 = mm.vnormals(g["V0"])
            J = np.zeros((K, len(n0), 3), np.float32)
            for k in range(K):
                c = np.zeros(K)
                c[k] = 0.5
                J[k] = (mm.vnormals(rs.head(c)) - n0) / 0.5
            np.save(f, J)
            _C[key] = J
    return _C[key]


def fitted_item(c, cam, view, hair=None):
    """The same per-vertex record as mm.item, for a FITTED head through its fitted camera (no truth used)."""
    from scipy import ndimage
    g = rs.gnm()
    H = rs.head(c)
    _, zb = rs.render(H, cam)
    w, h = cam["size"]
    P = rs.humanfit.project(cam, H)
    Xc = rs.cam_xform(cam, H)
    ok = g["ext"] & (P[:, 0] > 2) & (P[:, 0] < w - 2) & (P[:, 1] > 2) & (P[:, 1] < h - 2)
    u, v = np.clip(P[:, 0].astype(int), 0, w - 1), np.clip(P[:, 1].astype(int), 0, h - 1)
    ok &= Xc[:, 2] < zb[v, u] + 0.003
    m = np.isfinite(zb)
    edge = (ndimage.maximum_filter(np.where(m, zb, -1e9), 7) - ndimage.minimum_filter(np.where(m, zb, 1e9), 7) > 0.012) | ~ndimage.binary_erosion(m, iterations=4)
    ok &= ~edge[v, u]
    if hair is not None:
        ok &= ~hair[v, u]
    Rc = rs.humanfit._cam_rot(cam)
    n = mm.vnormals(H) @ Rc.T
    ok &= n[:, 2] < -0.15
    idx = np.flatnonzero(ok)
    reg, face = mm.region_of()
    return {"V": H, "cam": cam, "idx": idx, "pix": P[idx], "Xc": Xc[idx], "n": n[idx], "reg": reg[idx], "face": face[idx], "view": view, "Rc": Rc}


def rows(model, pr, c, cam, view, K=rs.K_FIT, hair=None, use=("z", "n"), infl=2.0, step=4, regions=None, cut=0.9):
    """Evidence rows (A, y) on c from one picture's prediction, about the current fit (c, cam).
    A vertex is used where calibration says the model leaves less than `cut` of the population's own spread;
    every `step`-th such vertex, sigma inflated by `infl` (neighbouring pixels' errors are not independent)."""
    t = table(model)
    ci = VC[view]
    g = rs.gnm()
    it = fitted_item(c, cam, view, hair)
    if it["face"].sum() < 50:
        return np.zeros((0, K)), np.zeros(0)
    pr = dict(pr)
    pr["flip"] = t["flip"]
    d = picture_devs(pr, it, bool(t["inverse"]))
    i = it["idx"]
    reg = it["reg"]
    A, y = [], []
    Rc = it["Rc"]
    V0 = g.get("V0_gnm", g["V0"])
    f = i[it["face"]]
    s, R, tt = rs.similarity(V0[f], it["V"][f])
    M = s * V0 @ R.T + tt
    if "z" in use and "dm_z" in d:
        gz, sz, pz = t[f"g_z_{ci}"][i], t[f"s_z_{ci}"][i], t[f"p_z_{ci}"][i]
        ok = np.isfinite(sz) & (sz < cut * pz) & (gz > 0.05)
        if regions:
            ok &= np.isin(reg, regions)
        j = np.flatnonzero(ok)[::step]
        sg = sz[j] * infl / 1000.0
        Az = np.einsum("d,knd->nk", Rc[2], g["IB"][:K, i[j]].astype(float))
        yz = gz[j] * d["dm_z"][j] / 1000.0 - (g["V0"][i[j]] - M[i[j]]) @ Rc[2]
        r = (Az @ c - yz) / sg
        w = np.where(np.abs(r) > 2.5, np.sqrt(2.5 / np.maximum(np.abs(r), 1e-9)), 1.0)
        A.append(Az / sg[:, None] * w[:, None])
        y.append(yz / sg * w)
    if "n" in use and "dm_n" in d:
        gn, sn, pn = t[f"g_n_{ci}"][i], t[f"s_n_{ci}"][i], t[f"p_n_{ci}"][i]
        ok = np.isfinite(sn) & (sn < cut * pn) & (gn > 0.05)
        if regions:
            ok &= np.isin(reg, regions)
        j = np.flatnonzero(ok)[::step]
        Jw = normal_jac(K)[:, i[j]].astype(float)                 # (K, n, 3) world
        Jc = np.einsum("knd,ed->kne", Jw, Rc)                      # camera frame
        target = d["nm"][j] + gn[j, None] * d["dm_n"][j]
        target /= np.maximum(np.linalg.norm(target, axis=1, keepdims=True), 1e-9)
        res = target - it["n"][j]                                  # what the head's normals should change by
        sg = sn[j] * infl
        for e in (0, 1):                                           # the two image-plane components
            An = Jc[:, :, e].T
            yn = res[:, e] + An @ c
            r = res[:, e] / sg
            w = np.where(np.abs(r) > 2.5, np.sqrt(2.5 / np.maximum(np.abs(r), 1e-9)), 1.0)
            A.append(An / sg[:, None] * w[:, None])
            y.append(yn / sg * w)
    if not A:
        return np.zeros((0, K)), np.zeros(0)
    return np.vstack(A), np.concatenate(y)


if __name__ == "__main__":
    if sys.argv[1] == "calib":
        import score_geo
        b = score_geo.best_flip(sys.argv[2])
        calibrate(sys.argv[2], "inverse" in sys.argv[3:], b[1] if b else (1, 1, 1))


# ---- a few numbers per picture instead of a field: the depth of feature patches against the face ----------------------

def _patch_means(d, it, H):
    import score_mesh
    fs = score_mesh.feature_sets(H)
    pos = -np.ones(len(H), int)
    pos[it["idx"]] = np.arange(len(it["idx"]))
    out = {}
    for k, v in fs.items():
        j = pos[v][pos[v] >= 0]
        if len(j) > 5:
            out[k] = (j, float(d["dm_z"][j].mean()), float(d["dt_z"][j].mean()) if "dt_z" in d else 0.0)
    return out


def calibrate_feat(model):
    t = table(model)
    res = {}
    for vw in VC:
        acc = {}
        for iid in mm.ids("cal", vw):
            pr = mm.pred(model, iid)
            if pr is None:
                continue
            it = mm.item(iid)
            d = picture_devs(pr, it, bool(t["inverse"]))
            for k, (j, a, b) in _patch_means(d, it, it["V"]).items():
                acc.setdefault(k, []).append((a, b))
        for k, ab in acc.items():
            ab = np.array(ab)
            if len(ab) < 10:
                continue
            gq = float((ab[:, 0] @ ab[:, 1]) / max(ab[:, 0] @ ab[:, 0], 1e-9))
            left = float(np.sqrt(((ab[:, 1] - gq * ab[:, 0]) ** 2).mean()))
            pop = float(np.sqrt((ab[:, 1] ** 2).mean()))
            res[f"{vw}/{k}"] = (gq, left, pop, len(ab))
            print(f"{model} {vw:8s} {k:16s} n {len(ab):2d} gain {gq:5.2f}  left {left:5.2f} mm of {pop:5.2f}")
    import json
    (mm.MM / f"dense_feat_{model}.json").write_text(json.dumps(res))


def rows_feat(model, pr, c, cam, view, K=rs.K_FIT, hair=None, cut=0.8, infl=1.3):
    import json
    key = "feat" + model
    if key not in _C:
        _C[key] = json.loads((mm.MM / f"dense_feat_{model}.json").read_text())
    cal = _C[key]
    t = table(model)
    g = rs.gnm()
    it = fitted_item(c, cam, view, hair)
    if it["face"].sum() < 50:
        return np.zeros((0, K)), np.zeros(0)
    d = picture_devs(dict(pr), it, bool(t["inverse"]))
    i = it["idx"]
    V0 = g.get("V0_gnm", g["V0"])
    f = i[it["face"]]
    s, R, tt = rs.similarity(V0[f], it["V"][f])
    M = s * V0 @ R.T + tt
    Rc = it["Rc"]
    A, y = [], []
    for k, (j, a, _) in _patch_means(d, it, it["V"]).items():
        if f"{view}/{k}" not in cal:
            continue
        gq, left, pop, n = cal[f"{view}/{k}"]
        if left > cut * pop or gq <= 0.05:
            continue
        sg = left * infl / 1000.0
        Ak = np.einsum("d,kd->k", Rc[2], g["IB"][:K, i[j]].astype(float).mean(1))
        yk = gq * a / 1000.0 - ((g["V0"][i[j]] - M[i[j]]) @ Rc[2]).mean()
        A.append(Ak / sg)
        y.append(yk / sg)
    if not A:
        return np.zeros((0, K)), np.zeros(0)
    return np.array(A), np.array(y)


if __name__ == "__main__" and sys.argv[1] == "feat":
    calibrate_feat(sys.argv[2])
