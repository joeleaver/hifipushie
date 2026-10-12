"""nval.py <model>...: is the parser's NOSE class a usable occluding contour in a 3/4 view? On the dressed 3/4 shot of a
known head (as pval.py, painted background): the model's own nose silhouette vertices (an edge between a face turned
to the camera and one turned away, in GNM's nose_region, visible) against the nearest point of BiSeNet's nose-class
boundary: distance in mm (truth 0). Saves out/nval_<model>.png."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree
from hifipushie import blockin as bi, face_ruler as fr, faceparse as fp, store

OUT = "/mnt/data/hifipushie/refread/out"
SHOTS = "/mnt/data/hifipushie/reruns/out"
allv = []
for m in sys.argv[1:]:
    spec, rj = store.load(m), bi._refs(m)
    head = fr.model_head(spec)
    nose = fr._gnm()["gr"]["nose_region"]
    gid = np.asarray(head["gid"], int)
    isn = (gid >= 0) & nose[np.maximum(gid, 0)]
    for vi, (v, cam, box) in enumerate(zip(rj["views"], rj["cameras"], rj["blockin"]["boxes"])):
        if fr.kind_of(v.get("yaw", 0)) != "3q" or not os.path.exists(f"{SHOTS}/d_{m}_{vi}.png"):
            continue
        shot = Image.open(f"{SHOTS}/d_{m}_{vi}.png").convert("RGB")
        n = shot.size[0]
        ib = [int(round(x)) for x in box]
        sc = n / float(ib[2] - ib[0])
        sv, Xc, P = fr._silhouette_vertices(head, cam)
        Pi = (P - ib[:2]) * sc
        view = {"cam": cam, "kind": "3q", "img": shot, "scale": sc, "origin": (ib[0], ib[1])}
        _, ps = fr._clay_crop(head, view)
        zb = ps["zb"]
        k = zb.shape[0] / n
        q = np.clip((Pi[sv] * k).astype(int), 0, zb.shape[0] - 1)
        vis = np.abs(zb[q[:, 1], q[:, 0]] - Xc[sv, 2]) < 0.003
        # an OCCLUDING contour: just outside it (away from the nose) the surface is much further from the camera
        sel = sv[vis & isn[sv]]
        _, _, full = fp.masks(shot, cam, head, origin=(ib[0], ib[1]), scale=sc, model="bisenet")
        cv = fr._curve(full["nose"] > 0.5)
        if cv is None or not len(sel):
            print(m, "no nose curve / no silhouette vertices"); continue
        cv = fr._resample(cv, 0.5)
        d, j = cKDTree(cv).query(Pi[sel])
        mm = float(np.median(Xc[sel, 2]) / cam["f"] * 1000.0) / sc
        d = d * mm
        allv.append(d)
        print(f"{m} 3/4: {len(sel)} nose silhouette vertices; distance to the parser's nose boundary: median {np.median(d):.2f} mm, "
              f"rms {np.sqrt((d ** 2).mean()):.2f}, p90 {np.percentile(d, 90):.2f}; under 1 mm: {100 * (d < 1).mean():.0f} %")
        t = shot.copy()
        dr = ImageDraw.Draw(t)
        dr.line([tuple(p) for p in cv], fill=(0, 255, 0), width=1)
        for p in Pi[sel]:
            dr.ellipse([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=(255, 0, 0))
        t.save(f"{OUT}/nval_{m}.png")
if allv:
    d = np.concatenate(allv)
    print(f"ALL: n {len(d)}  median {np.median(d):.2f}  rms {np.sqrt((d ** 2).mean()):.2f}  p90 {np.percentile(d, 90):.2f} mm; under 1 mm {100 * (d < 1).mean():.0f} %")
