"""sc_table.py <tag> [heads=abcdeg]: THE STAGE-1 REGION TABLE: the detector at the TRUTH on solvecams' known heads (4
GNM-native heads x 9 known cameras + head e: dark skin under a hard top light, head g: hair): per view kind and region
the error against the truth's own vertex (rms per axis = what solvecams' DENSE_REGION_SIG holds for the pilot, the
bias, the network's own sigma and its honesty), the WIDTH scale of the lower face (predicted / true spread about the
mid-line: 1 = right; the pilot answered a narrow jaw with the average one), and the CAMERA the network's points imply
on the true head (yaw / pitch / distance error of the best camera for its landmarks: a true profile read as 75-87
deg, the front pitch bias, the far camera), beside its own distance output. -> out/sc_<tag>.json + a text table.
WS=main; HIFIPUSHIE_DENSELM = the weights."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.optimize import least_squares

from hifipushie import blockin as bi, denselm, face_ruler as fr, store

tag = sys.argv[1]
heads = sys.argv[2] if len(sys.argv) > 2 else "abcdeg"
KIND = {"f": "front", "fu": "front", "fd": "front", "fn": "front", "ff": "front", "q23": "3q", "q45": "3q", "s72": "side72", "s90": "side90"}
REG = ("lids", "eyes", "brows", "nose", "lips", "mouth", "chin", "cheeks", "forehead", "ears", "scalp_neck")
L1 = denselm.landmarks()
reg = L1["region"][:L1["n_skin"]]
acc, cams, width = {}, [], []
for h in heads:
    name = f"sc_{h}_T"
    if not (store.HOME / name / "spec.json").exists():
        continue
    rj = json.loads((store.HOME / name / "human_refs.json").read_text())
    head = fr.model_head(store.load(name))
    for v, cam in zip(rj["views"], rj["cameras"]):
        vn = v.get("name") or Path(v["image"]).stem.split("_")[-1]
        img = Image.open(v["image"]).convert("RGB")
        _, q68 = fr._cam_points(cam, np.asarray(head["L"], float)[:68])
        pr = denselm.predict(img, q68)
        if "dense_v" not in head:
            fr._dense_obs(head, {"cam": cam, "kind": "front"}, pr)
        hv = head["dense_v"]
        X = head["V"][hv]
        Xc, Q = fr._cam_points(cam, X)
        mm1 = float(cam["t"][2]) / cam["f"] * 1000.0
        P = pr["xy"][:len(hv)]
        d = (P - Q) * mm1
        sg = pr["sigma"][:len(hv)] * mm1
        kind = KIND.get(vn, fr.kind_of(fr.view_yaw(cam)))
        key = (kind, "hard top, dark skin" if h == "e" else "hair" if h == "g" else "plain")
        a = acc.setdefault(key, {"d": [], "sg": [], "reg": []})
        a["d"].append(d), a["sg"].append(sg), a["reg"].append(reg)
        # the camera its landmarks imply on the TRUE head (face regions it is sure of)
        use = np.isin(reg, ("lids", "eyes", "brows", "nose", "lips", "mouth", "chin", "cheeks", "forehead")) & (sg < 4.0)

        def res(p):
            c2 = fr.cam_moved(cam, dx=p[0], dy=p[1], sc=p[2], roll=p[3], yaw=p[4], pitch=p[5], dist=p[6])
            _, q = fr._cam_points(c2, X[use])
            return (((P[use] - q) * mm1) / np.maximum(sg[use], 0.3)[:, None]).ravel()
        s = least_squares(res, np.zeros(7), x_scale=[1, 1, 1, 1, 2, 2, 20], bounds=([-30, -30, -20, -20, -40, -40, -120], [30, 30, 20, 20, 40, 40, 160])).x
        dist_true = float(np.linalg.norm(np.asarray(cam["t"], float)))
        dn = pr.get("distance")
        cams.append({"head": h, "view": vn, "kind": kind, "yaw_true": round(abs(fr.view_yaw(cam)), 1), "yaw_err": round(float(s[4]), 2), "pitch_err": round(float(s[5]), 2),
                     "dist_err_pct": round(float(np.expm1(0.01 * s[6]) * 100), 1), "scale_pct": round(float(s[2]), 2), "dist_true_m": round(dist_true, 2),
                     "dist_head_m": None if dn is None else round(dn[0], 2)})
        if kind == "front":
            x0 = Q[:, 0].mean()
            row = {"head": h, "view": vn}
            for r in ("chin", "cheeks", "lips", "nose", "eyes"):
                k = reg == r
                a_, b_ = Q[k, 0] - x0, P[k, 0] - x0
                row[r] = round(float(a_ @ b_ / (a_ @ a_)), 3)
            jaw = np.isin(reg, ("chin", "cheeks"))
            row["lower_face_width_mm"] = round(float((np.ptp(P[jaw, 0]) - np.ptp(Q[jaw, 0])) * mm1), 2)
            width.append(row)
out = {"regions": {}, "cameras": cams, "width": width}
print(f"REGION TABLE {tag} (mm at the face; rms per axis | bias x, y | median sigma | honesty = mean d^2 / (2 sigma^2))")
for (kind, cond), a in sorted(acc.items()):
    d, sg, rg = np.concatenate(a["d"]), np.concatenate(a["sg"]), np.concatenate(a["reg"])
    print(f"-- {kind} / {cond} ({len(a['d'])} pictures)")
    for r in REG:
        m = rg == r
        if not m.any():
            continue
        e2 = (d[m] ** 2).sum(1)
        row = {"rms_axis": round(float(np.sqrt((d[m] ** 2).mean())), 2), "bias_x": round(float(d[m, 0].mean()), 2), "bias_y": round(float(d[m, 1].mean()), 2),
               "sigma": round(float(np.median(sg[m])), 2), "honesty": round(float((e2 / (2 * sg[m] ** 2)).mean()), 2)}
        out["regions"][f"{kind}|{cond}|{r}"] = row
        print(f"   {r:11s} {row['rms_axis']:5.2f} | {row['bias_x']:+5.2f} {row['bias_y']:+5.2f} | {row['sigma']:5.2f} | {row['honesty']:5.2f}")
print("\nCAMERA the landmarks imply on the true head (error against the true camera)")
for kind in ("front", "3q", "side72", "side90"):
    cs = [c for c in cams if c["kind"] == kind]
    if cs:
        f = lambda k: np.array([c[k] for c in cs], float)
        dh = [abs(c["dist_head_m"] / c["dist_true_m"] - 1) * 100 for c in cs if c["dist_head_m"]]
        print(f"   {kind:7s} n {len(cs):2d}: yaw {f('yaw_err').mean():+5.2f} (rms {np.sqrt((f('yaw_err') ** 2).mean()):.2f}) deg; pitch {f('pitch_err').mean():+5.2f} (rms {np.sqrt((f('pitch_err') ** 2).mean()):.2f}); "
              f"distance {np.median(f('dist_err_pct')):+6.1f} % (median; range {f('dist_err_pct').min():+.0f} .. {f('dist_err_pct').max():+.0f})"
              + (f"; the distance OUTPUT: median |error| {np.median(dh):.0f} %" if dh else ""))
for c in cams:
    if c["kind"] in ("front", "side90"):
        print("     ", c)
print("\nWIDTH in the front views (x scale predicted / true about the mid-line; lower-face width error mm)")
for r in width:
    print("   ", r)
Path("/mnt/data/hifipushie/denselm/out").mkdir(exist_ok=True)
json.dump(out, open(f"/mnt/data/hifipushie/denselm/out/sc_{tag}.json", "w"))
