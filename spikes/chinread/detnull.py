"""detnull.py <truth model> ...: the DIFFERENTIAL ANCHORS' NULL: the detector on a known head's dressed picture minus the
same detector on our clay render of THAT head through the TRUE camera (what face_ruler._anchor_obs compares; truth 0),
per landmark group, x and y, mm, front and 3/4: the chin's three (lm 7 / 8 / 9), brows, eyes, nose, mouth."""
import os, sys
import numpy as np
from PIL import Image
from hifipushie import face_ruler as fr, blockin as bi, likeness, store

G = {"chin 7-9": range(7, 10), "brows 17-26": range(17, 27), "nose 27-35": range(27, 36), "eyes 36-47": range(36, 48), "mouth 48-67": range(48, 68)}
acc = {}
for T in sys.argv[1:]:
    rj = bi._refs(T)
    head = fr.model_head(store.load(T))
    for vi in (0, 1):
        v, cam = rj["views"][vi], rj["cameras"][vi]
        f = v["image"]
        if not os.path.basename(f).startswith(("cz_", "sx_")):
            f = f"/mnt/data/hifipushie/solvereads/synth/{T[:-2]}_{vi}.png"
        img = Image.open(f).convert("RGB")
        P = np.asarray(fr._cam_points(cam, np.asarray(head["L"], float)[:68])[1], float)
        pts = {f"lm{i}": P[i].tolist() for i in range(17, 68)}
        box = likeness._box(pts, img.size)
        Pd = likeness.detect_region(img, box)
        Pm = fr._detect_model(head, cam, box)
        if Pd is None or Pm is None:
            print(T, vi, "no detection")
            continue
        mm = float(cam["t"][2]) / cam["f"] * 1000.0
        line = f"{T} view {vi}:"
        for g, r in G.items():
            d = np.array([(np.asarray(Pd, float)[likeness.MP68[i]][:2] - Pm[likeness.MP68[i]][:2]) * mm for i in r])
            acc.setdefault((vi, g), []).append(d.mean(0))
            line += f" {g} x {d[:, 0].mean():+.1f} y {d[:, 1].mean():+.1f};"
        print(line, flush=True)
print("\nover the heads (mean, sd of the per-head means; y + = the picture's point lies LOWER than the render's):")
for (vi, g), v in sorted(acc.items()):
    a = np.array(v)
    print(f"  {'front' if vi == 0 else '3/4  '} {g:12s} x {a[:, 0].mean():+.1f} +-{a[:, 0].std():.1f}   y {a[:, 1].mean():+.1f} +-{a[:, 1].std():.1f}   (n {len(a)})")
