"""ground.gd's pictures measured: per view (distance, azimuth) each GLB against the FIRST one (the full plant's LOD 0):
covered pixels (area ratio), IoU of the two silhouettes, mean colour of what is drawn (sRGB 0..1) and its difference;
plus a contact sheet: per view one row of crops round the clump (the union of all silhouettes), scaled up alike.

  python spikes/godot_veg/ground_measure.py <prefix> <sheet.png> <distances m,..> <azimuths deg,..> <label> ...
"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

prefix, sheet = sys.argv[1], sys.argv[2]
dists = [float(x) for x in sys.argv[3].split(",")]
azs = [int(float(x)) for x in sys.argv[4].split(",")]
labels = sys.argv[5:]


def load(lab, d, az):
    a = np.asarray(Image.open(f"{prefix}_{lab}_d{int(round(d * 10))}_a{az}.png").convert("RGB"), float) / 255
    # covered = at least about half the plant (an MSAA edge pixel mostly magenta is not): magenta has min(r, b) - g = 1
    m = (np.minimum(a[..., 0], a[..., 2]) - a[..., 1]) < 0.3
    return a, m


rows, table = [], []
for d in dists:
    for az in azs:
        ims = [load(lab, d, az) for lab in labels]
        ref_a, ref_m = ims[0]
        union = np.any([m for _, m in ims], axis=0)
        if not union.any():
            continue
        ys, xs = np.nonzero(union)
        pad = 4
        y0, y1, x0, x1 = max(ys.min() - pad, 0), ys.max() + pad + 1, max(xs.min() - pad, 0), xs.max() + pad + 1
        clean = lambda a, m: m & (np.minimum(a[..., 0], a[..., 2]) - a[..., 1] < 0.0)  # (colour from pixels with no magenta in them)
        rc = ref_a[clean(ref_a, ref_m)].mean(0) if clean(ref_a, ref_m).any() else np.zeros(3)
        for lab, (a, m) in zip(labels, ims):
            inter, uni = (m & ref_m).sum(), (m | ref_m).sum()
            c = a[clean(a, m)].mean(0) if clean(a, m).any() else np.zeros(3)
            table.append({"label": lab, "d": d, "az": az, "px": int(m.sum()), "area": round(float(m.sum()) / max(ref_m.sum(), 1), 3),
                          "iou": round(float(inter) / max(uni, 1), 3), "colour": [round(float(x), 3) for x in c],
                          "dcol": round(float(np.abs(c - rc).mean()), 3)})
        crops = [Image.fromarray((a[y0:y1, x0:x1] * 255).astype(np.uint8)) for a, _ in ims]
        rows.append((d, az, crops))

# summary by distance: mean over azimuths
print(f"{'label':<14}{'d m':>6}{'area':>8}{'iou':>8}{'dcol':>8}{'px':>8}")
for lab in labels:
    for d in dists:
        r = [t for t in table if t["label"] == lab and t["d"] == d]
        if r:
            print(f"{lab:<14}{d:>6.1f}{np.mean([t['area'] for t in r]):>8.2f}{np.mean([t['iou'] for t in r]):>8.2f}"
                  f"{np.mean([t['dcol'] for t in r]):>8.3f}{np.mean([t['px'] for t in r]):>8.0f}")
json.dump(table, open(sheet.rsplit(".", 1)[0] + ".json", "w"), indent=0)

cell = 220
W = cell * len(labels)
img = Image.new("RGB", (W + 90, 24 + cell * len(rows)), (30, 30, 30))
dr = ImageDraw.Draw(img)
for j, lab in enumerate(labels):
    dr.text((90 + j * cell + 4, 4), lab, fill=(255, 255, 255))
for i, (d, az, crops) in enumerate(rows):
    dr.text((4, 24 + i * cell + 4), f"{d:g} m\naz {az}", fill=(255, 255, 255))
    for j, c in enumerate(crops):
        s = cell / max(c.size)
        c2 = c.resize((max(1, int(c.size[0] * s)), max(1, int(c.size[1] * s))), Image.NEAREST)
        img.paste(c2, (90 + j * cell, 24 + i * cell))
img.save(sheet)
print("sheet", sheet)
