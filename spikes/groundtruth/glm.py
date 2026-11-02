"""glm.py <tag> [fit=p1eb3]: the dense-landmark network (denselm, trained on our renders only) on pictures of a REAL
head whose shape and cameras are known: the sim-to-real landmark error. Truth = the Part 1 direct fit's GNM vertices
(identity + expression: the mouth and lids as the scan has them) carried into the model's world and projected through
each picture's TRUE camera (gmk.py's gt_<k>_T). CAVEAT: a surface fit pins a vertex ACROSS the surface (0.4 mm), not
ALONG it, so the "truth" itself may slide a millimetre or two on smooth skin (cheeks, forehead); edges (lids, lips,
nostrils, jaw line) are pinned better. Reads: every skin landmark the camera sees (z-buffer of the fitted head), and
the ones the solve would use (the network's own sigma <= face_ruler.DENSE_MAX_MM). -> out/dense_<k>.json, a table on
stdout and out/dense_<k>.png (truth red, network green, joined)."""
import json
import sys
import numpy as np
from PIL import Image, ImageDraw
import gt, rast, draw
from gmk import SHORT
from hifipushie import denselm, face_ruler as fr, humanfit, store

tag = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
k = SHORT[tag]
fj = json.loads((gt.WORK / tag / f"fit_{kw.get('fit', 'p1eb3')}.json").read_text())
fb = json.loads((gt.WORK / tag / "fit_p1b3.json").read_text())
sim = lambda j: (j["S"]["s"], np.asarray(j["S"]["R"]), np.asarray(j["S"]["t"]))
Mj = json.loads((gt.WORK / tag / "model_world.json").read_text())["M"]
M = (Mj["s"], np.asarray(Mj["R"]), np.asarray(Mj["t"]))
# GNM world of this fit -> the scan -> GNM world of p1b3 -> the model's world
X = gt.compose(M, gt.compose(sim(fb), gt.inverse(sim(fj))))
G = gt.gnm()
V = gt.apply(X, gt.verts(np.asarray(fj["c"]), None if fj["e"] is None else np.asarray(fj["e"])))
L68 = G["WL"] @ V
Lm = denselm.landmarks()
gid = np.asarray(Lm["gnm"], int)
ns = len(gid)
reg = np.asarray(Lm["region"])[:ns]
rj = json.loads((store.HOME / f"gt_{k}_T" / "human_refs.json").read_text())
rows, tiles, allv, widths = [], [], [], []
for v, cam in zip(rj["views"], rj["cameras"]):
    img = Image.open(v["image"]).convert("RGB")
    _, q68 = fr._cam_points(cam, L68)
    pred = denselm.predict(img, q68)
    Xc, P = fr._cam_points(cam, V)
    mm = Xc[gid, 2] / cam["f"] * 1000
    # seen: the vertex is the nearest surface along its pixel's ray (the fitted head's own z-buffer) and faces the camera
    vis = rast.visibility(V, G["F"], cam)
    px = np.clip(P[gid].astype(int), 0, [cam["size"][0] - 1, cam["size"][1] - 1])
    zb = vis["z"][px[:, 1], px[:, 0]]
    vn = gt.vertex_normals(V, G["F"]) @ humanfit._cam_rot(cam).T
    seen = (np.abs(zb - Xc[gid, 2]) < 0.004) & (vn[gid, 2] < -0.15)
    d = (pred["xy"][:ns] - P[gid]) * mm[:, None]
    e = np.linalg.norm(d, axis=1)
    sg = pred["sigma"][:ns] * mm
    used = seen & (sg <= fr.DENSE_MAX_MM)
    for r in sorted(set(reg)):
        m = reg == r
        for name, sel in (("seen", seen & m), ("used", used & m)):
            if sel.sum() >= 3:
                rows.append({"view": v["name"], "region": r, "set": name, "n": int(sel.sum()), "mean": float(e[sel].mean()), "median": float(np.median(e[sel])),
                             "dx": float(d[sel, 0].mean()), "dy": float(d[sel, 1].mean()), "ratio": float(np.sqrt(((e[sel] / np.maximum(sg[sel], 1e-6)) ** 2).mean() / 2))})
    for name, sel in (("seen", seen), ("used", used)):
        rows.append({"view": v["name"], "region": "ALL", "set": name, "n": int(sel.sum()), "mean": float(e[sel].mean()), "median": float(np.median(e[sel])),
                     "dx": float(d[sel, 0].mean()), "dy": float(d[sel, 1].mean()), "ratio": float(np.sqrt(((e[sel] / np.maximum(sg[sel], 1e-6)) ** 2).mean() / 2)),
                     "share_used": float(used.sum() / max(seen.sum(), 1)), "turn": float(abs(fr.view_yaw(cam)))})
    allv.append((v["name"], e, seen, used, reg))
    # is the network's nose WIDE, are its lips the average's? widths across mirror pairs and heights, network - truth (mm),
    # in the picture's plane (front-ish views only: a width is foreshortened in a turned one)
    if abs(fr.view_yaw(cam)) < 30:
        mir = np.asarray(Lm["mirror"], int)[:ns]
        for r in ("nose", "lips", "mouth", "eyes", "chin", "cheeks"):
            jj = [j for j in np.flatnonzero((reg == r) & seen) if mir[j] > j and mir[j] < ns and seen[mir[j]]]
            if len(jj) < 3:
                continue
            jj = np.asarray(jj)
            tw = np.abs(P[gid[jj], 0] - P[gid[mir[jj]], 0]) * mm[jj]
            pw = np.abs(pred["xy"][jj, 0] - pred["xy"][mir[jj], 0]) * mm[jj]
            wide = tw >= np.percentile(tw, 60)
            m = (reg == r) & seen
            th = np.ptp(P[gid[m], 1]) * mm[m].mean()
            ph = np.ptp(pred["xy"][:ns][m, 1]) * mm[m].mean()
            widths.append({"view": v["name"], "region": r, "pairs": int(wide.sum()), "truth_width": float(tw[wide].mean()), "d_width": float((pw - tw)[wide].mean()),
                           "d_width_all": float((pw - tw).mean()), "truth_height": float(th), "d_height": float(ph - th)})
    im = img.copy()
    dr = ImageDraw.Draw(im)
    for j in np.flatnonzero(seen):
        a, b = P[gid[j]], pred["xy"][j]
        col = (0, 255, 0) if used[j] else (255, 200, 0)
        dr.line([tuple(a), tuple(b)], fill=col, width=1)
        dr.ellipse([a[0] - 1.5, a[1] - 1.5, a[0] + 1.5, a[1] + 1.5], fill=(255, 0, 0))
        dr.ellipse([b[0] - 1.5, b[1] - 1.5, b[0] + 1.5, b[1] + 1.5], fill=col)
    x0, y0, x1, y1 = denselm.box_of(q68)
    t = im.crop((int(x0), int(y0), int(x1), int(y1))).resize((900, 900), Image.LANCZOS)
    A = [r for r in rows if r["view"] == v["name"] and r["region"] == "ALL"]
    tiles.append(draw.label(t, f"{v['name']} (turn {abs(fr.view_yaw(cam)):.0f}): seen {A[0]['mean']:.1f} mm, used {A[1]['mean']:.1f} mm ({100 * A[1]['share_used']:.0f} %)", sz=30))
(gt.OUT / f"dense_{k}.json").write_text(json.dumps({"rows": rows, "widths": widths}))
draw.vstack([draw.hstack(tiles[:3]), draw.hstack(tiles[3:])]).save(gt.OUT / f"dense_{k}.png")
views = [v["name"] for v in rj["views"]]
print(f"\n#### {tag}: dense network vs the projected Part 1 fit, mean mm (landmarks the solve would USE: sigma <= {fr.DENSE_MAX_MM} mm; in brackets: every landmark the camera sees)\n")
print("| region | " + " | ".join(views) + " |")
print("|---|" + "---|" * len(views))
for r in sorted(set(reg)) + ["ALL"]:
    cells = []
    for vn in views:
        u = [x for x in rows if x["view"] == vn and x["region"] == r and x["set"] == "used"]
        s = [x for x in rows if x["view"] == vn and x["region"] == r and x["set"] == "seen"]
        cells.append((f"{u[0]['mean']:.1f}" if u else "-") + (f" ({s[0]['mean']:.1f})" if s else ""))
    print(f"| {r} | " + " | ".join(cells) + " |")
A = [x for x in rows if x["region"] == "ALL" and x["set"] == "used"]
print("| share used | " + " | ".join(f"{100 * x['share_used']:.0f} %" for x in A) + " |")
print("| error / the network's own sigma (1 = honest) | " + " | ".join(f"{x['ratio']:.1f}" for x in A) + " |")
print("| mean offset x, y mm | " + " | ".join(f"{x['dx']:+.1f}, {x['dy']:+.1f}" for x in A) + " |")
print(f"\n{tag}: the network's WIDTHS and HEIGHTS against the truth, front-ish views (network - truth, mm; widths = the widest 40 % of mirror pairs)\n")
print("| view | region | truth width | network - truth | all pairs | truth height | network - truth |")
print("|---|---|---|---|---|---|---|")
for x in widths:
    print(f"| {x['view']} | {x['region']} | {x['truth_width']:.1f} | {x['d_width']:+.1f} | {x['d_width_all']:+.1f} | {x['truth_height']:.1f} | {x['d_height']:+.1f} |")
