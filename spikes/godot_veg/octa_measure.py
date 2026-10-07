"""octa.gd's pictures: per elevation / azimuth, the impostor against the mesh LOD (pixels not magenta = the plant):
coverage (impostor / mesh), mean luma of the plant's pixels (impostor / mesh), outline IoU; and a contact sheet.

    python spikes/godot_veg/octa_measure.py <out prefix> [sheet.png]"""
import glob
import re
import sys

import numpy as np
from PIL import Image

prefix = sys.argv[1]
rows = []
for f in sorted(glob.glob(prefix + "_mesh_el*_az*.png")):
    m = re.search(r"_el(\d+)_az(\d+)\.png$", f)
    g = f.replace("_mesh_", "_impostor_")
    A = np.asarray(Image.open(f).convert("RGB"), float) / 255
    B = np.asarray(Image.open(g).convert("RGB"), float) / 255
    ma = ~((A[..., 0] > 0.9) & (A[..., 1] < 0.1) & (A[..., 2] > 0.9))
    mb = ~((B[..., 0] > 0.9) & (B[..., 1] < 0.1) & (B[..., 2] > 0.9))
    lum = lambda X, k: float((X[..., :3] @ [0.2126, 0.7152, 0.0722])[k].mean()) if k.any() else 0.0
    rows.append((int(m.group(1)), int(m.group(2)), mb.sum() / max(ma.sum(), 1), lum(B, mb) / max(lum(A, ma), 1e-6),
                 (ma & mb).sum() / max((ma | mb).sum(), 1), f, g))
print("elev  az   coverage  luma   IoU   (impostor / mesh LOD)")
for el, az, cov, lu, iou, *_ in rows:
    print(f"{el:4d} {az:4d}   {cov:6.3f}  {lu:6.3f}  {iou:5.3f}")
for el in sorted({r[0] for r in rows}):
    R = [r for r in rows if r[0] == el]
    print(f"elevation {el}: coverage {np.mean([r[2] for r in R]):.3f}, luma {np.mean([r[3] for r in R]):.3f}, IoU {np.mean([r[4] for r in R]):.3f}")
if len(sys.argv) > 2:
    ims = []
    for r in rows:
        a, b = Image.open(r[5]).convert("RGB"), Image.open(r[6]).convert("RGB")
        w, h = a.size
        s = 240 / h
        a, b = a.resize((int(w * s), 240)), b.resize((int(w * s), 240))
        t = Image.new("RGB", (2 * a.width + 4, 240), "white")
        t.paste(a, (0, 0))
        t.paste(b, (a.width + 4, 0))
        ims.append(t)
    cols = 3
    W, Hh = ims[0].width, ims[0].height
    S = Image.new("RGB", (cols * (W + 10), ((len(ims) + cols - 1) // cols) * (Hh + 10)), "white")
    for i, t in enumerate(ims):
        S.paste(t, ((i % cols) * (W + 10), (i // cols) * (Hh + 10)))
    S.save(sys.argv[2])
