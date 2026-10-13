"""gmix.py <tag> [<tag> ..] [fit=p1eb3] [corr=<mp_gnm.json>]: BOTH detectors on pictures of REAL heads whose shape and
cameras are known (groundtruth's sets: gt_<k>_T; h40 / h112 = HSRD-100 rig photos, lps = the textured scan drawn by us):
per face region and view the error in mm of
  (i)  MediaPipe's points through the learned correspondence (mpcorr.py: a GNM triangle + barycentric weights a point)
  (ii) the pilot dense network (denselm hm18), its skin landmarks
against the projection of the scan-fitted GNM (Part 1's direct fit, identity + expression) through each TRUE camera.
After groundtruth's glm.py (same truth, same visibility test). CAVEAT (glm.py's): a surface fit pins a vertex ACROSS the
surface, not ALONG it: on smooth skin the truth slides 1-2 mm; and a vermilion border is a COLOUR edge the 3D fit never
saw. Both detectors are scored against the same truth; the tiles (out/gmix_<k>.png) are for looking at the lips / nose.
-> out/gmix_<k>.json, out/gmix_<k>.png, a table on stdout (per-axis rms mm = what a sigma should be)."""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import gt, rast, draw
from gmk import SHORT
from hifipushie import denselm, face_ruler as fr, humanfit, likeness, store

RM = Path(os.environ.get("HIFIPUSHIE_READMIX", "/mnt/data/hifipushie/readmix"))
kw = dict(a.split("=") for a in sys.argv[1:] if "=" in a)
tags = [a for a in sys.argv[1:] if "=" not in a]
CORR = json.loads(Path(kw.get("corr", RM / "corr" / "mp_gnm.json")).read_text())
YB = CORR["yaw_bins"]
# feature groups of MediaPipe points (finer than GNM's regions): what the brief asks about
ALAR = [129, 358, 98, 327, 64, 294, 48, 278, 219, 439, 49, 279, 102, 331, 240, 460, 235, 455, 59, 289, 75, 305, 60, 290, 99, 328, 97, 326, 2, 94, 141, 370, 242, 462, 20, 250, 79, 309, 166, 392, 218, 438, 237, 457, 239, 459, 238, 458, 241, 461, 125, 354, 44, 274, 19]
TIP = [1, 4, 5, 45, 275, 220, 440, 51, 281, 195, 3, 248, 115, 344, 131, 360, 134, 363, 198, 420, 236, 456]
BRIDGE = [6, 197, 168, 122, 351, 196, 419, 174, 399, 188, 412, 114, 343, 245, 465, 193, 417]


def feature(pt):
    m, s = pt["mp"], pt["set"]
    if m in (61, 291, 78, 308):
        return "commissures"
    if s == "lip_outer":
        return "vermilion border"
    if s == "lip_inner":
        return "lip seam"
    if s in ("eye_l", "eye_r"):
        return "eye contour"
    if s in ("brow_l", "brow_r"):
        return "brow line"
    if s == "oval":
        return "face oval"
    if m in ALAR:
        return "alar / nostril base"
    if m in TIP:
        return "nose tip / dorsum"
    if m in BRIDGE:
        return "nasal bridge"
    return {"lips": "lip surface", "mouth": "round the mouth", "nose": "nose other", "lids": "lids other", "eyes": "orbit",
            "brows": "brow region", "chin": "chin", "cheeks": "cheeks", "forehead": "forehead"}.get(pt["region"], pt["region"])


DFEAT = {"lips": "lip surface", "mouth": "round the mouth", "nose": "nose (all)", "lids": "lids", "eyes": "orbit", "brows": "brow region",
         "chin": "chin", "cheeks": "cheeks", "forehead": "forehead"}


def bias_of(pt, yaw):
    for b0, b1 in zip(YB[:-1], YB[1:]):
        if b0 <= yaw < b1 and f"{b0}:{b1}" in pt["bins"]:
            return np.array(pt["bins"][f"{b0}:{b1}"]["bias"]), pt["bins"][f"{b0}:{b1}"]
    return np.zeros(2), None


def rms1(d):
    return float(np.sqrt((d ** 2).sum(1).mean() / 2)) if len(d) else np.nan


rows = []
for tag in tags:
    k = SHORT[tag]
    fj = json.loads((gt.WORK / tag / f"fit_{kw.get('fit', 'p1eb3')}.json").read_text())
    fb = json.loads((gt.WORK / tag / "fit_p1b3.json").read_text())
    sim = lambda j: (j["S"]["s"], np.asarray(j["S"]["R"]), np.asarray(j["S"]["t"]))
    Mj = json.loads((gt.WORK / tag / "model_world.json").read_text())["M"]
    M = (Mj["s"], np.asarray(Mj["R"]), np.asarray(Mj["t"]))
    X = gt.compose(M, gt.compose(sim(fb), gt.inverse(sim(fj))))
    G = gt.gnm()
    V = gt.apply(X, gt.verts(np.asarray(fj["c"]), None if fj["e"] is None else np.asarray(fj["e"])))
    L68 = G["WL"] @ V
    Lm = denselm.landmarks()
    gid = np.asarray(Lm["gnm"], int)
    ns = len(gid)
    reg = np.asarray(Lm["region"])[:ns]
    rj = json.loads((store.HOME / f"gt_{k}_T" / "human_refs.json").read_text())
    tiles = []
    for v, cam in zip(rj["views"], rj["cameras"]):
        img = Image.open(v["image"]).convert("RGB")
        Xc, P = fr._cam_points(cam, V)
        _, q68 = fr._cam_points(cam, L68)
        # the camera's yaw in the correspondence's convention (+ = the camera on the subject's left (+X))
        eye_dir = -humanfit._cam_rot(cam).T @ np.array([0.0, 0.0, 1.0])       # from the head toward the camera, world
        yawc = float(np.degrees(np.arctan2(eye_dir[0], -eye_dir[1])))
        turn = abs(fr.view_yaw(cam))
        vis = rast.visibility(V, G["F"], cam)
        vn = gt.vertex_normals(V, G["F"]) @ humanfit._cam_rot(cam).T

        def seen_at(p2, z, nz):
            px = np.clip(p2.astype(int), 0, [cam["size"][0] - 1, cam["size"][1] - 1])
            return (np.abs(vis["z"][px[:, 1], px[:, 0]] - z) < 0.004) & (nz < -0.15)
        # (i) MediaPipe
        box = likeness._box({f"lm{i}": q68[i] for i in range(68)}, img.size)
        Pd = likeness.detect_region(img, box)
        mp_rows = []
        if Pd is not None:
            for pt in CORR["points"]:
                tri, w = pt["tri"], np.array(pt["w"])
                p2 = w @ P[tri]
                z, nz = float(w @ Xc[tri, 2]), float(w @ vn[tri, 2])
                mm = z / cam["f"] * 1000
                b, bn = bias_of(pt, yawc)
                d = (Pd[pt["mp"]] - p2) * mm
                mp_rows.append((feature(pt), pt["region"], d, d - b, bool(seen_at(p2[None], np.array([z]), np.array([nz]))[0]), pt["mp"], p2, Pd[pt["mp"]],
                                None if bn is None else bn["rms"]))
        # the detector's own placement taken out: a 2D similarity (shift, scale, turn) of its seen inner-face points onto the
        # truth, per view: the solve's cameras are free, so what is left after it is what a read's sigma should be
        def sim_fit(A, B):
            ma, mb = A.mean(0), B.mean(0)
            a_, b_ = A - ma, B - mb
            z = (a_[:, 0] * b_[:, 0] + a_[:, 1] * b_[:, 1]).sum() + 1j * (a_[:, 0] * b_[:, 1] - a_[:, 1] * b_[:, 0]).sum()
            z = z / (a_ ** 2).sum()
            return lambda Q: np.stack([(z * ((Q[:, 0] - ma[0]) + 1j * (Q[:, 1] - ma[1]))).real + mb[0], (z * ((Q[:, 0] - ma[0]) + 1j * (Q[:, 1] - ma[1]))).imag + mb[1]], 1)
        inner = [i for i, r in enumerate(mp_rows) if r[4] and r[0] not in ("face oval", "forehead", "cheeks", "chin", "brow line", "brow region")]
        mp_sim = {}
        if len(inner) >= 20:
            fn_ = sim_fit(np.array([mp_rows[i][7] for i in inner]), np.array([mp_rows[i][6] for i in inner]))
            for i, r in enumerate(mp_rows):
                mp_sim[i] = (fn_(np.asarray(r[7])[None])[0] - r[6]) * (np.linalg.norm(r[2]) / max(np.linalg.norm(np.asarray(r[7]) - r[6]), 1e-9))
        # (ii) dense
        pred = denselm.predict(img, q68)
        mmd = Xc[gid, 2] / cam["f"] * 1000
        seen = seen_at(P[gid], Xc[gid, 2], vn[gid, 2])
        dd = (pred["xy"][:ns] - P[gid]) * mmd[:, None]
        sg = pred["sigma"][:ns] * mmd
        used = seen & (sg <= fr.DENSE_MAX_MM)
        din = used & np.isin(reg, ("lips", "mouth", "nose", "lids", "eyes"))
        dsim = dd.copy()
        if din.sum() >= 20:
            fn_ = sim_fit(pred["xy"][:ns][din], P[gid][din])
            dsim = (fn_(pred["xy"][:ns]) - P[gid]) * mmd[:, None]
        for f_ in sorted({r[0] for r in mp_rows}):
            ii_ = [i for i, r in enumerate(mp_rows) if r[0] == f_ and r[4]]
            sel = [mp_rows[i] for i in ii_]
            if len(sel) >= 2:
                D0, D1 = np.array([r[2] for r in sel]), np.array([r[3] for r in sel])
                rows.append({"head": k, "view": v["name"], "turn": turn, "det": "mp", "feature": f_, "n": len(sel), "rms": rms1(D0), "rms_corr": rms1(D1),
                             "rms_sim": rms1(np.array([mp_sim[i] for i in ii_])) if mp_sim else np.nan,
                             "dx": float(D0[:, 0].mean()), "dy": float(D0[:, 1].mean()), "learned": float(np.mean([r[8] or np.nan for r in sel]))})
        for r_ in sorted(set(reg)):
            sel = used & (reg == r_)
            if sel.sum() >= 2 and r_ in DFEAT:
                rows.append({"head": k, "view": v["name"], "turn": turn, "det": "dense", "feature": DFEAT[r_], "n": int(sel.sum()), "rms": rms1(dd[sel]),
                             "rms_corr": rms1(dd[sel]), "rms_sim": rms1(dsim[sel]), "dx": float(dd[sel, 0].mean()), "dy": float(dd[sel, 1].mean())})
        # MediaPipe's points by GNM region too (like for like with the dense regions)
        for r_ in sorted(DFEAT):
            ii_ = [i for i, r in enumerate(mp_rows) if r[1] == r_ and r[4] and r[0] != "face oval"]
            sel = [mp_rows[i] for i in ii_]
            if len(sel) >= 2:
                D0, D1 = np.array([r[2] for r in sel]), np.array([r[3] for r in sel])
                rows.append({"head": k, "view": v["name"], "turn": turn, "det": "mp_region", "feature": DFEAT[r_], "n": len(sel), "rms": rms1(D0),
                             "rms_sim": rms1(np.array([mp_sim[i] for i in ii_])) if mp_sim else np.nan,
                             "rms_corr": rms1(D1), "dx": float(D0[:, 0].mean()), "dy": float(D0[:, 1].mean())})
        # signed feature measures in the picture (mm): mouth width (commissures), alar width, both detectors vs the truth
        def width(pa, pb, mm_):
            return float(np.linalg.norm(np.asarray(pa) - np.asarray(pb)) * mm_)
        if Pd is not None:
            byid = {r[5]: r for r in mp_rows}
            mm0 = float(np.median(mmd))
            for nm, (a, b) in (("mouth width (61-291)", (61, 291)), ("alar width (129-358)", (129, 358)), ("nostril base (98-327)", (98, 327)),
                               ("alar wings (64-294)", (64, 294))):
                if a in byid and b in byid:
                    rows.append({"head": k, "view": v["name"], "turn": turn, "det": "mp", "feature": "W: " + nm, "n": 2,
                                 "rms": width(byid[a][7], byid[b][7], mm0) - width(byid[a][6], byid[b][6], mm0), "rms_corr": np.nan, "dx": 0.0, "dy": 0.0,
                                 "truth": width(byid[a][6], byid[b][6], mm0)})
        # tile: the mouth + nose, truth red, MediaPipe (through the correspondence: where it says the truth point is) cyan, dense green
        im = img.copy()
        dr = ImageDraw.Draw(im)
        for r in mp_rows:
            if r[4] and r[0] in ("vermilion border", "lip seam", "commissures", "alar / nostril base", "nose tip / dorsum", "eye contour"):
                a, b = r[6], r[7]
                dr.line([tuple(a), tuple(b)], fill=(0, 255, 255), width=1)
                dr.ellipse([a[0] - 2, a[1] - 2, a[0] + 2, a[1] + 2], fill=(255, 0, 0))
                dr.ellipse([b[0] - 2, b[1] - 2, b[0] + 2, b[1] + 2], fill=(0, 255, 255))
        for j in np.flatnonzero(used & np.isin(reg, ("lips", "nose", "mouth"))):
            a, b = P[gid[j]], pred["xy"][j]
            dr.line([tuple(a), tuple(b)], fill=(0, 255, 0), width=1)
            dr.ellipse([a[0] - 2, a[1] - 2, a[0] + 2, a[1] + 2], fill=(255, 0, 0))
            dr.ellipse([b[0] - 2, b[1] - 2, b[0] + 2, b[1] + 2], fill=(0, 255, 0))
        c = q68[[30, 48, 54, 57, 27]].mean(0)
        h = 0.55 * np.linalg.norm(q68[36] - q68[45]) * 1.6
        t = im.crop((int(c[0] - h), int(c[1] - h), int(c[0] + h), int(c[1] + h))).resize((900, 900), Image.LANCZOS)
        tiles.append(draw.label(t, f"{k} {v['name']} (turn {turn:.0f}): truth red, MediaPipe cyan, dense green" + ("" if Pd is not None else "  NO MP FACE"), sz=26))
    draw.vstack([draw.hstack(tiles[:3]), draw.hstack(tiles[3:])]).save(RM / "out" / f"gmix_{k}.png")
(RM / "out" / f"gmix_{'_'.join(SHORT[t] for t in tags)}.json").write_text(json.dumps(rows))

# ---- the table: per feature, by view class, both detectors, over the heads (per-axis rms mm; brackets: after the learned bias)
KIND = {"f": "front", "fu": "front", "q23": "q23", "q45": "q45", "s72": "s72", "s90": "s90"}
cols = ["front", "q23", "q45", "s72", "s90"]


def cell(det, feat, col, key="rms"):
    sel = [r for r in rows if r["det"] == det and r["feature"] == feat and KIND[r["view"]] == col]
    if not sel:
        return None
    n = np.array([r["n"] for r in sel], float)
    return float(np.sqrt((n * np.array([r[key] for r in sel]) ** 2).sum() / n.sum())), int(n.sum())


print(f"\n### per-axis rms mm against the projected scan fit, heads {', '.join(SHORT[t] for t in tags)} (n reads): raw / after the detector's own 2D similarity per view\n")
print("| feature | detector | " + " | ".join(cols) + " |")
print("|---|---|" + "---|" * len(cols))
for feat in sorted({r["feature"] for r in rows if not r["feature"].startswith("W: ")}):
    for det in ("mp", "mp_region", "dense"):
        cs = []
        for c in cols:
            a = cell(det, feat, c)
            b = cell(det, feat, c, "rms_corr")
            c_ = cell(det, feat, c, "rms_sim")
            cs.append("-" if a is None else f"{a[0]:.2f} / {c_[0]:.2f} n{a[1]}")
        if any(x != "-" for x in cs):
            print(f"| {feat} | {det} | " + " | ".join(cs) + " |")
print("\n### signed widths, MediaPipe through the correspondence minus the truth, mm (per head and view)\n")
for r in rows:
    if r["feature"].startswith("W: ") and KIND[r["view"]] in ("front", "q23"):
        print(f"- {r['head']} {r['view']}: {r['feature'][3:]}: {r['rms']:+.2f} (truth {r['truth']:.1f})")
