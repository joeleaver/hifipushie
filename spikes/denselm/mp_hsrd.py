"""mp_hsrd.py <photos tag> [out tag=mediapipe]: MediaPipe Face Landmarker beside real_hsrd.py: the SAME HSRD-100 held-out
photos (out/realhsrd_<photos tag>.json's list), turned upright the same way, cropped round the truth's 68 (x1.6, 768 px);
scored against the groundtruth agent's "mp" labels (readmix's MediaPipe -> GNM surface points, by MediaPipe index;
P.good = visible + on measured skin) per mp_region x view class: per-axis rms mm RAW / AFTER a 2D similarity on the inner
face. Runs in MediaPipe's own venv (/mnt/data/hifipushie/facerefs_venv; Apache 2.0); hsrdset needs numpy + PIL only.
-> out/realhsrd_<out tag>.txt / .json (same layout as real_hsrd.py, no sigma)."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision

import hsrdset as H

src, tag = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "mediapipe")
photos = json.load(open(f"/mnt/data/hifipushie/denselm/out/realhsrd_{src}.json"))["photos"]
det = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
    base_options=mpt.BaseOptions(model_asset_path="/mnt/data/hifipushie/facerefs_venv/face_landmarker.task"), num_faces=1))
INNER = ("lips", "mouth", "nose", "lids", "eyes")


def sim_fit(A, B):
    ma, mb = A.mean(0), B.mean(0)
    a_, b_ = A - ma, B - mb
    z = ((a_[:, 0] * b_[:, 0] + a_[:, 1] * b_[:, 1]).sum() + 1j * (a_[:, 0] * b_[:, 1] - a_[:, 1] * b_[:, 0]).sum()) / (a_ ** 2).sum()
    return lambda Q: np.stack([(z * ((Q[:, 0] - ma[0]) + 1j * (Q[:, 1] - ma[1]))).real + mb[0], (z * ((Q[:, 0] - ma[0]) + 1j * (Q[:, 1] - ma[1]))).imag + mb[1]], 1)


def upright(img, pts, roll):
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


rms1 = lambda d: float(np.sqrt((d ** 2).sum(1).mean() / 2))
acc, miss = {}, 0
poses = {}
for ph in photos:
    P = poses.setdefault(ph["pose"], H.Pose(ph["pose"]))
    cam, col = ph["cam"], ph["col"]
    K = P.camera(cam)
    l68, _, _ = P.labels(cam, "lm68")
    xy, vis, q = P.labels(cam, "mp")
    ok = P.good(cam, "mp")
    img, f = upright(P.image(cam), l68, K.get("roll_deg", 0.0))
    T68, T = f(l68), f(xy)
    c0 = T68.mean(0)
    half = 0.8 * max(np.ptp(T68[:, 0]), np.ptp(T68[:, 1]))
    box = (c0[0] - half, c0[1] - half, c0[0] + half, c0[1] + half)
    crop = img.crop(tuple(int(round(v)) for v in box)).resize((768, 768), Image.BICUBIC)
    r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(crop)))
    if not r.face_landmarks:
        miss += 1
        continue
    Q = np.array([[p.x * 768, p.y * 768] for p in r.face_landmarks[0]])
    Q = Q / 768 * (2 * half) + np.array(box[:2])
    ids = np.asarray(P.lab["mp_id"], int)
    reg = np.asarray(P.lab["mp_region"]).astype(str)
    pr = Q[ids]
    mmpx = 1.0 / K["px_per_mm"]
    d = (pr - T) * mmpx
    din = ok & np.isin(reg, INNER)
    ds = (sim_fit(pr[din], T[din])(pr) - T) * mmpx if din.sum() >= 20 else d
    for rg in np.unique(reg):
        m = ok & (reg == rg)
        if m.sum() >= 2:
            a = acc.setdefault((col, rg), {"d": [], "ds": []})
            a["d"].append(d[m]), a["ds"].append(ds[m])
    if col == "front":
        acc.setdefault(("front", "_widths"), {"mw": []})["mw"].append(
            float((np.linalg.norm(Q[291] - Q[61]) - np.linalg.norm(f(xy)[list(ids).index(291)] - f(xy)[list(ids).index(61)])) * mmpx) if 61 in ids and 291 in ids else np.nan)
out = {"cells": {}, "missed": miss, "n_photos": len(photos)}
lines = [f"MediaPipe on the same HSRD held-out photos ({len(photos)}, no face found on {miss}): per-axis rms mm RAW / AFTER a 2D similarity (n)",
         "| mp region | front | 3q | profile |", "|---|---|---|---|"]
for rg in ("lids", "eyes", "brows", "nose", "lips", "mouth", "chin", "cheeks", "forehead"):
    cs = []
    for col in ("front", "3q", "profile"):
        a = acc.get((col, rg))
        if not a:
            cs.append("-")
            continue
        d, ds = np.concatenate(a["d"]), np.concatenate(a["ds"])
        out["cells"][f"{col}|{rg}"] = {"raw": round(rms1(d), 2), "sim": round(rms1(ds), 2), "n": int(len(d))}
        cs.append(f"{rms1(d):.2f} / {rms1(ds):.2f} ({len(d)})")
    lines.append(f"| {rg} | " + " | ".join(cs) + " |")
mw = np.array(acc.get(("front", "_widths"), {"mw": []})["mw"], float)
if len(mw):
    lines.append(f"front: mouth width (61-291) ours - truth median {np.nanmedian(mw):+.2f} mm (n {np.isfinite(mw).sum()})")
print("\n".join(lines))
Path(f"/mnt/data/hifipushie/denselm/out/realhsrd_{tag}.txt").write_text("\n".join(lines) + "\n")
json.dump(out, open(f"/mnt/data/hifipushie/denselm/out/realhsrd_{tag}.json", "w"))
