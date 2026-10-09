"""Where on GNM's surface does each of the detector's 478 points land, per kind of view, and how steadily?
Calibration heads (seeds the truth set doesn't use) are rendered, detected, each detected pixel dropped onto the
head's own surface and carried to the template. Writes D/calib.npz:
  vid (4 classes, 478, 3) vertex ids, w (…, 3) weights  -> a detected point as a linear function of the vertices
  sd (4, 478) mm: scatter of that surface point over heads (the detector's semantic noise + sliding)
  z_gain / z_r (4, 478): how the detector's depth follows a head's own depth at that point (see mpdepth.py)
Also prints the 68's bias: the repo's MP68 table against GNM's own 68 landmark definitions."""
import numpy as np
from scipy.spatial import cKDTree

import rs

CLASSES = {"front": 0.0, "tq": 40.0, "profile": 88.0, "tq2": -38.0}
N = 36


def run():
    g = rs.gnm()
    rng = np.random.default_rng(7)
    ext = np.flatnonzero(g["ext"] | g["gr"]["eyes"])
    recs = {k: [] for k in CLASSES}
    imgs, meta = [], []
    for s in range(N):
        c = np.random.default_rng(5000 + s).normal(0, 1.0, rs.K_TRUE)
        V = rs.head(c)
        for k, yaw in CLASSES.items():
            cam = rs.make_cam(V, yaw=yaw + rng.normal(0, 4), pitch=rng.normal(0, 5), roll=rng.normal(0, 2.5),
                              lens=float(rng.choice([50, 70, 85])), fill=rng.uniform(0.5, 0.68))
            img, zb = rs.render(V, cam, albedo=rs.skinned_albedo(s) if s % 2 else None)
            imgs.append(img)
            meta.append((k, V, cam, zb))
    det = rs.detect(imgs)
    miss = {k: 0 for k in CLASSES}
    lm_err = {k: [] for k in CLASSES}
    for (k, V, cam, zb), d in zip(meta, det):
        if d is None:
            miss[k] += 1
            continue
        X = rs.unproject(cam, d["P"][:, :2], zb)
        ok = np.isfinite(X[:, 0])
        vis = rs.visible(V, cam, ext, zb)
        tree = cKDTree(V[ext[vis]])
        dd, jj = tree.query(np.nan_to_num(X), k=3)
        ids = ext[vis][jj]
        w = 1.0 / np.maximum(dd, 1e-5)
        w /= w.sum(1, keepdims=True)
        tpl = (g["V0"][ids] * w[..., None]).sum(1)
        tpl[~ok] = np.nan
        mmpx = rs.cam_xform(cam, V[g["regions"]["face"]])[:, 2].mean() / cam["f"] * 1000
        recs[k].append((tpl, d["P"], mmpx, cam, V))
        Lp = rs.humanfit.project(cam, rs.landmarks(V))
        lm_err[k].append((d["P"][rs.LM_FROM_MP, :2] - Lp) * mmpx)
    out_vid = np.zeros((4, 478, 3), np.int64)
    out_w = np.zeros((4, 478, 3))
    out_sd = np.full((4, 478), np.inf)
    tree0 = cKDTree(g["V0"][ext])
    for ci, k in enumerate(CLASSES):
        T = np.array([r[0] for r in recs[k]])   # (heads, 478, 3) template positions
        med = np.nanmedian(T, 0)
        sd = np.sqrt(np.nanmean(((T - med) ** 2).sum(-1), 0)) * 1000
        frac = np.isfinite(T[..., 0]).mean(0)
        sd[frac < 0.9] = np.inf
        dd, jj = tree0.query(np.nan_to_num(med), k=3)
        w = 1.0 / np.maximum(dd, 1e-5)
        out_vid[ci], out_w[ci], out_sd[ci] = ext[jj], w / w.sum(1, keepdims=True), sd
        e = np.array(lm_err[k])   # (heads, 70, 2) mm in the picture
        bias, noise = e.mean(0), e.std(0)
        grp = {"jaw 0-16": range(0, 17), "brows": range(17, 27), "nose": range(27, 36), "eyes": range(36, 48), "mouth": range(48, 68), "iris": (68, 69)}
        print(f"\n{k}: detected {len(recs[k])}/{N}; usable 478-points (scatter < 2.5 mm): {(sd < 2.5).sum()}, median scatter {np.median(sd[np.isfinite(sd)]):.2f} mm")
        print("   the 68 through the MP68 table vs GNM's own landmark definitions (mm in the picture):")
        for gn, ii in grp.items():
            ii = list(ii)
            print(f"     {gn:9s} bias |mean| {np.linalg.norm(bias[ii], axis=1).mean():5.2f}   noise sd {np.linalg.norm(noise[ii], axis=1).mean():5.2f}")
    np.savez(rs.D / "calib.npz", vid=out_vid, w=out_w, sd=out_sd, classes=list(CLASSES))


if __name__ == "__main__":
    run()
