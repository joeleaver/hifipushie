"""real_hsrd.py <tag> [split=heldout] [max photos per pose and view class=6]: the detector on HSRD-100's REAL rig
photographs with scan truth through the groundtruth agent's labelled set (hsrdset.py; labels "dl3" = OUR landmark set
v3 projected from its GNM fit to each scan; P.good = visible AND on measured skin within 1.5 mm). Scored on the
HELD-OUT PEOPLE only (HSR0023, HSR0027, HSR0102: the split is the groundtruth agent's, fixed). CC BY 4.0, attribution
in hsrdset.index()["attribution"]; nothing of these photos goes into git or a shared sheet.
Per region x view class (front |az| < 30, 3q 30-70, profile 70-115; rear skipped): per-axis rms mm RAW / AFTER the
detector's own 2D similarity (fitted on lips, mouth, nose, lids, eyes), median sigma, honesty (mean d^2 / (2 sigma^2) on
the after-similarity residual, 1 = exact), bias. Front: mouth width and alar width (ours - truth, mm), the distance read.
The photos are turned upright by the head's roll first (the rig mounts many cameras sideways). The crop starts from the
truth's 68 (as real_gt.py), then predict's second pass re-crops on the network's own 68.
CAVEATS (the groundtruth agent's): a surface fit pins a label ACROSS the skin, not ALONG it (smooth skin: 1-3 mm); the
vermilion-border labels are the lip's FORM, not its colour edge. -> out/realhsrd_<tag>.json / .txt"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import hsrdset as H
from hifipushie import denselm

tag = sys.argv[1]
split = sys.argv[2] if len(sys.argv) > 2 else "heldout"
cap = int(sys.argv[3]) if len(sys.argv) > 3 else 6
# [photos=<tag>]: exactly the photos of out/realhsrd_<tag>.json
FIXED = None
if len(sys.argv) > 4 and sys.argv[4].startswith("photos="):
    FIXED = {(p["pose"], p["cam"], p["col"]) for p in json.load(open(f"/mnt/data/hifipushie/denselm/out/realhsrd_{sys.argv[4][7:]}.json"))["photos"]}
REG = ("lids", "eyes", "brows", "nose", "nose_base", "philtrum", "lips", "lip_border_upper", "lip_border_lower", "lip_seam", "mouth", "chin",
       "cheeks", "forehead", "ears")
COLS = (("front", 0, 30), ("3q", 30, 70), ("profile", 70, 115))
INNER = ("lips", "mouth", "nose", "lids", "eyes")


def sim_fit(A, B):
    ma, mb = A.mean(0), B.mean(0)
    a_, b_ = A - ma, B - mb
    z = ((a_[:, 0] * b_[:, 0] + a_[:, 1] * b_[:, 1]).sum() + 1j * (a_[:, 0] * b_[:, 1] - a_[:, 1] * b_[:, 0]).sum()) / (a_ ** 2).sum()
    return lambda Q: np.stack([(z * ((Q[:, 0] - ma[0]) + 1j * (Q[:, 1] - ma[1]))).real + mb[0], (z * ((Q[:, 0] - ma[0]) + 1j * (Q[:, 1] - ma[1]))).imag + mb[1]], 1)


def upright(img, pts, roll):
    """the photo turned by -roll about its centre (expand), and points with it; the sign is chosen so that the eyes
    lie above the mouth (lm68: eyes 36-47, mouth 48-67)."""
    best = None
    for s in (1.0, -1.0):
        im = img.rotate(s * roll, expand=True, resample=Image.BICUBIC)
        w, h = img.size
        W, Hh = im.size
        a = np.deg2rad(s * roll)
        c, si = np.cos(a), np.sin(a)
        f = lambda P, c=c, si=si, w=w, h=h, W=W, Hh=Hh: np.c_[c * (P[:, 0] - w / 2) + si * (P[:, 1] - h / 2) + W / 2, -si * (P[:, 0] - w / 2) + c * (P[:, 1] - h / 2) + Hh / 2]
        q = f(pts)
        up = q[48:68, 1].mean() - q[36:48, 1].mean()
        if best is None or up > best[0]:
            best = (up, im, f)
    return best[1], best[2]


Ls = denselm.landmarks_v3()
L68 = np.asarray(Ls["lm68"])
reg_all = np.asarray(Ls["region"])
acc, widths, used_photos = {}, [], []
rms1 = lambda d: float(np.sqrt((d ** 2).sum(1).mean() / 2))
for pose in (sorted({p for p, _, _ in FIXED}) if FIXED is not None else H.poses(split)):
    P = H.Pose(pose)
    lab_reg = np.asarray(P.lab["dl3_region"]).astype(str)
    assert len(lab_reg) == Ls["n"] and (lab_reg == reg_all).all(), "the labelled set is not our v3"
    for col, lo, hi in COLS:
        cams = [c for c in P.photos() if lo <= abs(P.camera(c)["az"]) < hi]
        cams = sorted(cams, key=lambda c: -P.good(c, "dl3").sum())[:cap]
        if FIXED is not None:                     # the same photos as an earlier run (the set grows as poses are added)
            cams = [c for c in P.photos() if (pose, c, col) in FIXED]
        for cam in cams:
            K = P.camera(cam)
            xy, vis, q = P.labels(cam, "dl3")
            ok = P.good(cam, "dl3")
            if ok.sum() < 60:
                continue
            img, f = upright(P.image(cam), xy, K.get("roll_deg", 0.0))
            T = f(xy)
            pred = denselm.predict(img, T[L68])
            mmpx = 1.0 / K["px_per_mm"]
            n = Ls["n"]
            Lp = pred.get("set") or denselm.landmarks()
            if Lp["n"] != n:                      # an older network (the pilot: set v1): only the skin rows are v3's rows
                k = Lp["n_skin"]
                ok = ok & (np.arange(n) < k)
                pred = {**pred, "xy": np.r_[pred["xy"][:k], np.zeros((n - k, 2))], "sigma": np.r_[pred["sigma"][:k], np.ones(n - k)]}
            d = (pred["xy"][:n] - T) * mmpx
            sg = pred["sigma"][:n] * mmpx
            din = ok & np.isin(reg_all, INNER)
            ds = d.copy()
            if din.sum() >= 20:
                ds = (sim_fit(pred["xy"][:n][din], T[din])(pred["xy"][:n]) - T) * mmpx
            used_photos.append({"pose": pose, "cam": cam, "col": col, "az": round(K["az"], 1), "good": int(ok.sum()), "px_per_mm": round(K["px_per_mm"], 2),
                                "inner_raw_mm": round(rms1(d[din]), 2), "inner_sim_mm": round(rms1(ds[din]), 2),
                                "inner_shift_mm": [round(float(v), 2) for v in np.median(d[din], 0)]})
            print("   ", used_photos[-1], flush=True)
            for r in REG:
                m = ok & (reg_all == r)
                if m.sum() >= 2:
                    a = acc.setdefault((col, r), {"d": [], "ds": [], "sg": []})
                    a["d"].append(d[m]), a["ds"].append(ds[m]), a["sg"].append(sg[m])
            if col == "front":
                o, t = pred["xy"][L68], T[L68]
                widths.append({"pose": pose, "cam": cam,
                               "mouth_width": round(float((np.linalg.norm(o[54] - o[48]) - np.linalg.norm(t[54] - t[48])) * mmpx), 2),
                               "alar_width": round(float((np.linalg.norm(o[35] - o[31]) - np.linalg.norm(t[35] - t[31])) * mmpx), 2),
                               "distance_read_m": None if pred.get("distance") is None else round(pred["distance"][0], 2),
                               "distance_true_m": round(float(K.get("dist_m", np.nan)), 2)})
        print(f"{pose} {col}: {len(cams)} photos", flush=True)

rms1 = lambda d: float(np.sqrt((d ** 2).sum(1).mean() / 2))
out = {"cells": {}, "widths": widths, "photos": used_photos, "split": split, "attribution": H.index()["attribution"]}
lines = [f"HSRD-100 REAL PHOTOS, {split} people ({len({p['pose'] for p in used_photos})} poses, {len(used_photos)} photos), weights {tag}: per-axis rms mm RAW / AFTER a 2D similarity (n labels) [median sigma; honesty]",
         "| region | " + " | ".join(c for c, _, _ in COLS) + " |", "|---|" + "---|" * len(COLS)]
for r in REG:
    cs = []
    for c, _, _ in COLS:
        a = acc.get((c, r))
        if not a:
            cs.append("-")
            continue
        d, ds, sg = np.concatenate(a["d"]), np.concatenate(a["ds"]), np.concatenate(a["sg"])
        hon = float(((ds ** 2).sum(1) / (2 * sg ** 2)).mean())
        out["cells"][f"{c}|{r}"] = {"raw": round(rms1(d), 2), "sim": round(rms1(ds), 2), "n": int(len(d)), "sigma": round(float(np.median(sg)), 2),
                                    "honesty": round(hon, 2), "bias_x": round(float(d[:, 0].mean()), 2), "bias_y": round(float(d[:, 1].mean()), 2)}
        cs.append(f"{rms1(d):.2f} / {rms1(ds):.2f} ({len(d)}) [{np.median(sg):.2f}; {hon:.1f}]")
    if any(x != "-" for x in cs):
        lines.append(f"| {r} | " + " | ".join(cs) + " |")
if widths:
    mw, aw = np.array([w["mouth_width"] for w in widths]), np.array([w["alar_width"] for w in widths])
    lines.append(f"front: mouth width ours - truth median {np.median(mw):+.2f} mm (range {mw.min():+.1f} .. {mw.max():+.1f}); alar width {np.median(aw):+.2f} ({aw.min():+.1f} .. {aw.max():+.1f}); n {len(widths)}")
    dr = [(w["distance_read_m"], w["distance_true_m"]) for w in widths if w["distance_read_m"]]
    if dr:
        lines.append("front: distance read / true (m): " + ", ".join(f"{a:.2f}/{b:.2f}" for a, b in dr[:12]))
lines.append("Attribution: " + out["attribution"])
print("\n".join(lines))
Path("/mnt/data/hifipushie/denselm/out").mkdir(exist_ok=True)
json.dump(out, open(f"/mnt/data/hifipushie/denselm/out/realhsrd_{tag}.json", "w"))
Path(f"/mnt/data/hifipushie/denselm/out/realhsrd_{tag}.txt").write_text("\n".join(lines) + "\n")
