"""real_gt.py <tag> [scan tags = HSR0040-Body-023 HSR0112-Body-018]: the detector on REAL PHOTOGRAPHS WITH SCAN TRUTH
(the groundtruth agent's sets, HSRD-100, CC BY 4.0: rig photos of scanned people; truth = its direct GNM fit to the
scan, projected through the rig's calibrated cameras), exactly as readmix's gmix.py scores the pilot (the same truth,
the same visibility test, the same per-view 2D similarity: gt / rast / gmk are the groundtruth agent's modules, read
from its worktree through PYTHONPATH; nothing of theirs is written), for ANY of our networks and with the network's own
SIGMA: per region and view class the per-axis rms mm RAW / AFTER the detector's own 2D similarity (the solve's cameras
are free: the second is what a read's sigma should be), the bias, the median sigma, and the honesty (mean d^2 /
(2 sigma^2), 1 = exact; on the after-similarity residual). + mouth width and alar width (signed, mm).
CAVEATS (readmix's): a surface fit pins a vertex across the surface, not along it (smooth skin slides 1-2 mm in the
truth itself); the vermilion border is a colour edge the scan fit never saw (the truth's upper border lies ~1.5 mm
above the photo's lip edge on h40); two heads.  -> out/realgt_<tag>.json; run through real_gt.sh."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import gt
import rast
from gmk import SHORT
from hifipushie import denselm, face_ruler as fr, humanfit, store

tag = sys.argv[1]
scans = sys.argv[2:] or ["HSR0040-Body-023", "HSR0112-Body-018"]
REG = ("lids", "eyes", "brows", "nose", "nose_base", "philtrum", "lips", "lip_border_upper", "lip_border_lower", "lip_seam", "mouth", "chin",
       "cheeks", "forehead", "ears")
KIND = {"f": "front", "fu": "front", "q23": "q23", "q45": "q45", "s72": "s72", "s90": "s90"}


def sim_fit(A, B):
    ma, mb = A.mean(0), B.mean(0)
    a_, b_ = A - ma, B - mb
    z = ((a_[:, 0] * b_[:, 0] + a_[:, 1] * b_[:, 1]).sum() + 1j * (a_[:, 0] * b_[:, 1] - a_[:, 1] * b_[:, 0]).sum()) / (a_ ** 2).sum()
    return lambda Q: np.stack([(z * ((Q[:, 0] - ma[0]) + 1j * (Q[:, 1] - ma[1]))).real + mb[0], (z * ((Q[:, 0] - ma[0]) + 1j * (Q[:, 1] - ma[1]))).imag + mb[1]], 1)


acc, widths = {}, []
for t in scans:
    k = SHORT[t]
    fj = json.loads((gt.WORK / t / "fit_p1eb3.json").read_text())
    fb = json.loads((gt.WORK / t / "fit_p1b3.json").read_text())
    sim = lambda j: (j["S"]["s"], np.asarray(j["S"]["R"]), np.asarray(j["S"]["t"]))
    Mj = json.loads((gt.WORK / t / "model_world.json").read_text())["M"]
    X = gt.compose((Mj["s"], np.asarray(Mj["R"]), np.asarray(Mj["t"])), gt.compose(sim(fb), gt.inverse(sim(fj))))
    G = gt.gnm()
    V = gt.apply(X, gt.verts(np.asarray(fj["c"]), None if fj["e"] is None else np.asarray(fj["e"])))
    L68 = G["WL"] @ V
    rj = json.loads((store.HOME / f"gt_{k}_T" / "human_refs.json").read_text())
    for v, cam in zip(rj["views"], rj["cameras"]):
        img = Image.open(v["image"]).convert("RGB")
        Xc, P = fr._cam_points(cam, V)
        _, q68 = fr._cam_points(cam, L68)
        vis = rast.visibility(V, G["F"], cam)
        vn = gt.vertex_normals(V, G["F"]) @ humanfit._cam_rot(cam).T
        pred = denselm.predict(img, q68)
        Ls = pred.get("set") or denselm.landmarks()
        ids_all = np.asarray(Ls.get("gnm_all", Ls["gnm"]), int)
        rg_all = np.asarray(Ls["region"])[:len(ids_all)]
        keep = ~np.isin(rg_all, ("teeth_upper", "teeth_lower", "tongue", "eyeball", "scalp_neck"))
        gid, reg = ids_all[keep], rg_all[keep]
        px = np.clip(P[gid].astype(int), 0, [cam["size"][0] - 1, cam["size"][1] - 1])
        seen = (np.abs(vis["z"][px[:, 1], px[:, 0]] - Xc[gid, 2]) < 0.004) & (vn[gid, 2] < -0.15)
        mmd = Xc[gid, 2] / cam["f"] * 1000
        xy = pred["xy"][:len(ids_all)][keep]
        dd = (xy - P[gid]) * mmd[:, None]
        sg = pred["sigma"][:len(ids_all)][keep] * mmd
        used = seen & (sg <= fr.DENSE_MAX_MM)
        din = used & np.isin(reg, ("lips", "mouth", "nose", "lids", "eyes"))
        dsim = dd.copy()
        if din.sum() >= 20:
            dsim = (sim_fit(xy[din], P[gid][din])(xy) - P[gid]) * mmd[:, None]
        kind = KIND.get(v["name"], "other")
        for r in REG:
            m = used & (reg == r)
            if m.sum() >= 2:
                a = acc.setdefault((kind, r), {"d": [], "ds": [], "sg": [], "all": 0, "seen": 0})
                a["d"].append(dd[m]), a["ds"].append(dsim[m]), a["sg"].append(sg[m])
            if (reg == r).any():
                a = acc.setdefault((kind, r), {"d": [], "ds": [], "sg": [], "all": 0, "seen": 0})
                a["all"] += int((seen & (reg == r)).sum())
                a["seen"] += int(m.sum())
        if kind == "front":
            o68 = pred["xy"][np.asarray(Ls["lm68"])]
            mm0 = float(np.median(mmd))
            widths.append({"head": k, "view": v["name"], "mouth_width": round(float((np.linalg.norm(o68[54] - o68[48]) - np.linalg.norm(q68[54] - q68[48])) * mm0), 2),
                           "alar_width": round(float((np.linalg.norm(o68[35] - o68[31]) - np.linalg.norm(q68[35] - q68[31])) * mm0), 2),
                           "distance_read_m": None if pred.get("distance") is None else round(pred["distance"][0], 2),
                           "distance_true_m": round(float(np.linalg.norm(np.asarray(cam["t"], float))), 2)})
out = {"cells": {}, "widths": widths}
cols = ["front", "q23", "q45", "s72", "s90"]
rms1 = lambda d: float(np.sqrt((d ** 2).sum(1).mean() / 2))
print(f"REAL PHOTOS WITH SCAN TRUTH ({', '.join(SHORT[t] for t in scans)}), weights {tag}: per-axis rms mm RAW / AFTER a 2D similarity (n) [median sigma; honesty after the similarity]")
print("| region | " + " | ".join(cols) + " |")
print("|---|" + "---|" * len(cols))
for r in REG:
    cs = []
    for c in cols:
        a = acc.get((c, r))
        if not a or not a["d"]:
            cs.append("-")
            continue
        d, ds, sg = np.concatenate(a["d"]), np.concatenate(a["ds"]), np.concatenate(a["sg"])
        hon = float(((ds ** 2).sum(1) / (2 * sg ** 2)).mean())
        out["cells"][f"{c}|{r}"] = {"raw": round(rms1(d), 2), "sim": round(rms1(ds), 2), "n": int(len(d)), "sigma": round(float(np.median(sg)), 2), "honesty": round(hon, 2),
                                    "bias_x": round(float(d[:, 0].mean()), 2), "bias_y": round(float(d[:, 1].mean()), 2), "used_share": round(a["seen"] / max(a["all"], 1), 2)}
        cs.append(f"{rms1(d):.2f} / {rms1(ds):.2f} ({len(d)}) [{np.median(sg):.2f}; {hon:.1f}]")
    if any(x != "-" for x in cs):
        print(f"| {r} | " + " | ".join(cs) + " |")
print("signed widths, ours - truth, mm (front views):", widths)
Path("/mnt/data/hifipushie/denselm/out").mkdir(exist_ok=True)
json.dump(out, open(f"/mnt/data/hifipushie/denselm/out/realgt_{tag}.json", "w"))
