"""foldread.py <out.json> <label=image> ...: lidfold.read_lid on photos (the 478 detector finds the eyes; scale from
the iris, 11.7 mm). Prints per eye per column tps / bfs / dark / width, writes the table and annotated eye crops
(out/fold_<label>.png: the lash line green, the fold line red, the brow blue, per column)."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import likeness, lidfold
from hifipushie.likeness_eyes import eye_box, frame

out = sys.argv[1]
rows = {}
for arg in sys.argv[2:]:
    lab, p = arg.split("=", 1)
    im = Image.open(p).convert("RGB")
    d = likeness.detect([im])[0]
    if d is None:
        print(lab, "no face")
        continue
    P = np.asarray(d, float)[:, :2]
    r = lidfold.read_lid(im, P)
    rows[lab] = r
    for s, cols in zip(("R", "L"), r):
        print(f"{lab:>28} {s}: " + "  ".join(f"tps {c['tps']:5.2f} bfs {c['bfs']:5.2f} dark {c['dark']:.2f} w {c['width']}"
                                               for c in cols))
    # annotate
    ex, ey = frame(P)
    ex, ey = np.asarray(ex), np.asarray(ey)
    x0, y0, x1, y1 = eye_box(P)
    dr = ImageDraw.Draw(im)
    for s, cols in zip((0, 1), r):
        k = lidfold.IRIS_MM / (2 * np.mean([np.linalg.norm(P[i] - P[lidfold.IRIS_C[s]]) for i in lidfold.IRIS_RIM[s]]))
        pi, po = P[lidfold.INNER[s]], P[lidfold.OUTER[s]]
        span = float((po - pi) @ ex)
        for f, c in zip((0.25, 0.5, 0.75), cols):
            t = f * span
            lid = lidfold._interp_curve(P, lidfold.UPPER[s], t, ex, ey, pi)
            base = pi + t * ex + lid * ey
            dr.ellipse([*(base - 1.5), *(base + 1.5)], fill=(0, 255, 0))
            if np.isfinite(c["tps"]):
                q = base - c["tps"] / k * ey
                dr.line([tuple(q - 4 * ex), tuple(q + 4 * ex)], fill=(255, 0, 0), width=1)
                b = base - c["brow"] / k * ey
                dr.line([tuple(b - 4 * ex), tuple(b + 4 * ex)], fill=(0, 120, 255), width=1)
    cr = im.crop(tuple(int(v) for v in (x0, y0, x1, y1)))
    cr.resize((900, int(900 * cr.height / cr.width)), Image.LANCZOS).save(f"/mnt/data/hifipushie/eyedetail/out/fold_{lab}.png")
json.dump(rows, open(out, "w"), indent=1, default=float)
