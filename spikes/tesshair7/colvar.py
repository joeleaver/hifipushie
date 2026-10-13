"""colvar.py <model> [tiles=<dir with s_<model>_v{0,1,2}.png>]: the hair's COLOUR VARIATION, hers | ours, like with like
(hair.colour_bands with mm_px -> colour_variation): per reference view, over the dense hair both have (her picture's
dark non-backdrop pixels AND our render's, eroded), at OUR tile's pixel size (her picture is resized to it: strand
contrast depends on the pixel). No Blender. Prints one block a view and the mean over views."""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from hifipushie import hair, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
TOUT = os.environ["TOUT"]
tiles = kw.get("tiles", TOUT)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())


def hairmask(im, bg_tol=26):
    a = np.asarray(im.convert("RGB"), float)
    bg = np.median(a[:40, :40].reshape(-1, 3), 0)
    lum = a @ [0.2126, 0.7152, 0.0722]
    return (np.abs(a - bg).max(-1) > bg_tol) & (lum < 0.52 * (bg @ [0.2126, 0.7152, 0.0722]))


keys = ("L_sd", "strand_sd", "ribbon_sd", "mass_sd", "chroma_sd", "hue_sd")
acc = {"hers": [], "ours": []}
out = {}
for i in (0, 1, 2):
    f = f"{tiles}/s_{m}_v{i}.png"
    if not os.path.exists(f):
        continue
    ours = Image.open(f).convert("RGB")
    n = ours.size[0]
    cam = refs["cameras"][i]
    mm = float(cam["t"][2]) / float(cam["f"]) * 1000.0 * max(cam["size"]) / n
    pic = hair.ref_square(Image.open(refs["views"][i]["image"]).convert("RGB"), n)
    # (the face's dark pixels are not hair: only the mask's largest piece, eroded 2 mm)
    both = ndi.binary_opening(hairmask(pic) & hairmask(ours), iterations=2)
    lab, k = ndi.label(both)
    if k == 0:
        continue
    both = lab == (1 + int(np.argmax(ndi.sum(both, lab, range(1, k + 1)))))
    dense = ndi.binary_erosion(both, iterations=max(1, int(round(2.0 / mm))))
    r = {"hers": hair.colour_bands(pic, dense, mm), "ours": hair.colour_bands(ours, dense, mm)}
    out[f"v{i}"] = r
    print(f"v{i}  {mm:.2f} mm/px, {int(dense.sum())} px      hers | ours")
    for b in ("mean", "shadow", "highlight"):
        print(f"   {b:9s} L* {r['hers'][b]['L']:5.1f} | {r['ours'][b]['L']:5.1f}   chroma {r['hers'][b]['chroma']:4.1f} | {r['ours'][b]['chroma']:4.1f}"
              f"   hue {r['hers'][b]['hue']:5.1f} | {r['ours'][b]['hue']:5.1f}")
    vh, vo = r["hers"]["variation"], r["ours"]["variation"]
    for k_ in keys:
        print(f"   {k_:10s} {vh[k_]:5.2f} | {vo[k_]:5.2f}")
    print(f"   light ribbons: share {vh['ribbons']['share']:.3f} | {vo['ribbons']['share']:.3f}   lift L* {vh['ribbons']['contrast']:.1f} | {vo['ribbons']['contrast']:.1f}")
    acc["hers"].append([vh[k_] for k_ in keys] + [vh["ribbons"]["share"], vh["ribbons"]["contrast"]])
    acc["ours"].append([vo[k_] for k_ in keys] + [vo["ribbons"]["share"], vo["ribbons"]["contrast"]])
if acc["hers"]:
    a, b = np.mean(acc["hers"], 0), np.mean(acc["ours"], 0)
    print(m, "MEAN over views, hers | ours: " + "  ".join(f"{k_} {x:.2f}|{y:.2f}" for k_, x, y in zip(keys + ("rib_share", "rib_lift"), a, b)))
json.dump(out, open(f"{TOUT}/colvar_{m}.json", "w"), indent=1)
