"""Hypothesis c: is the detector's 3D (MediaPipe returns x, y AND a relative z for its 478 points) a usable depth
prior? On the calibration heads' front pictures, for the points whose place on GNM's surface is known (calib.npz):
the detector's point cloud and the MEAN head's are each similarity-aligned to the true head's points; what is left
along the camera's depth is compared. If the detector's depth followed the person, its residual would beat the
mean head's, and its depth deviations would correlate with the true ones."""
import numpy as np

import calib
import rs


def main():
    g = rs.gnm()
    z = np.load(rs.D / "calib.npz")
    meta, imgs = calib.calib_set()
    det = rs.detect(imgs)
    reg_of = {}
    for cname, ci in (("front", 0), ("tq", 1)):
        ok = z["sd"][ci] < 2.5
        vid, w = z["vid"][ci][ok], z["w"][ci][ok]
        X0 = (g["V0"][vid] * w[..., None]).sum(1)
        lab = np.full(len(vid), "other", dtype=object)
        for rn in ("chin", "nose", "eyes", "brow", "cheeks", "lips", "forehead", "jaw"):
            lab[np.isin(vid[:, 0], g["regions"][rn])] = rn
        R_mp, R_mean, dev_mp, dev_true = [], [], [], []
        for (k, V, cam, zb), d in zip(meta, det):
            if k != cname or d is None:
                continue
            Xt = rs.cam_xform(cam, (V[vid] * w[..., None]).sum(1)) * 1000   # truth, camera frame, mm
            Xm = rs.cam_xform(cam, X0) * 1000                                # the mean head through the same camera
            P = d["P"][ok]
            s, R, t = rs.similarity(P, Xt)
            A_mp = s * P @ R.T + t
            s2, R2, t2 = rs.similarity(Xm, Xt)
            A_mean = s2 * Xm @ R2.T + t2
            R_mp.append(A_mp - Xt)
            R_mean.append(A_mean - Xt)
            dev_mp.append((A_mp - A_mean)[:, 2])
            dev_true.append((Xt - A_mean)[:, 2])
        R_mp, R_mean = np.array(R_mp), np.array(R_mean)
        dev_mp, dev_true = np.array(dev_mp), np.array(dev_true)
        print(f"\n{cname}: {len(R_mp)} heads, {ok.sum()} points. Residual after similarity alignment to the true head (mm rms):")
        print(f"{'region':9s} {'n':>4s} | {'detector xy':>11s} {'mean xy':>8s} | {'detector z':>10s} {'mean z':>7s} | corr(z dev) gain")
        for rn in ("ALL", "nose", "chin", "lips", "eyes", "brow", "cheeks", "forehead", "jaw", "other"):
            m = np.ones(len(lab), bool) if rn == "ALL" else lab == rn
            if m.sum() < 3:
                continue
            f = lambda E, ax: float(np.sqrt((E[:, m][..., ax] ** 2).mean()))  # noqa: E731
            a, b = dev_mp[:, m].ravel(), dev_true[:, m].ravel()
            cc = float(np.corrcoef(a, b)[0, 1])
            gain = float((a @ b) / (a @ a))
            print(f"{rn:9s} {m.sum():4d} | {f(R_mp, [0, 1]):11.2f} {f(R_mean, [0, 1]):8.2f} | {f(R_mp, [2]):10.2f} {f(R_mean, [2]):7.2f} | {cc:5.2f} {gain:5.2f}")


if __name__ == "__main__":
    main()
