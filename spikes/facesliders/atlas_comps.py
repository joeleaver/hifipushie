"""atlas_comps.py <out.png> [first] [count]: GNM's identity components one at a time, -2 / mean / +2 sigma, front and
profile (clay, the template's head, PIL renderer), with what each moves most (humanmacro's macros, sigmas)."""
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import humanmacro, likeness

out = sys.argv[1]
first = int(sys.argv[2]) if len(sys.argv) > 2 else 0
count = int(sys.argv[3]) if len(sys.argv) > 3 else 12
sp = humanmacro.space()
gr = sp["gr"]
keep = (gr["skin_exterior"] | gr["eyes"]) & ~gr["mouth_sock"]
T = sp["T"][keep[sp["T"]].all(1)]
L0 = sp["L0"]
ctr = L0[:68].mean(0)
cams = [{"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.6], "f": 2600.0, "size": [600, 600], "centre": ctr.tolist(), "yaw": y}
        for y in (0.0, 90.0)]
box = (75, 40, 525, 560)
z0 = humanmacro.read(np.zeros(humanmacro.K))
rows = []
for k in range(first, first + count):
    tiles = []
    for v in (-2.0, 0.0, 2.0):
        c = np.zeros(humanmacro.K)
        c[k] = v
        V = humanmacro.head(c)
        mesh = {"V": V, "F": T.astype(np.int64), "eyes": []}
        for cam in cams:
            im, _ = likeness.render(mesh, cam, box, px=220, brows=False)
            tiles.append(im.convert("RGB"))
    c = np.zeros(humanmacro.K)
    c[k] = 1.0
    z1 = humanmacro.read(c)
    top = sorted(((abs(z1[m] - z0[m]), m, z1[m] - z0[m]) for m in z0), reverse=True)[:4]
    row = Image.new("RGB", (sum(t.size[0] for t in tiles), tiles[0].size[1] + 16), (255, 255, 255))
    x = 0
    for t in tiles:
        row.paste(t, (x, 16))
        x += t.size[0]
    ImageDraw.Draw(row).text((4, 2), f"comp {k} (-2 | 0 | +2 sigma; front, profile): " +
                             ", ".join(f"{m} {d:+.2f}" for _, m, d in top), fill=(0, 0, 0))
    rows.append(row)
S = Image.new("RGB", (rows[0].size[0], sum(r.size[1] for r in rows)), (255, 255, 255))
y = 0
for r in rows:
    S.paste(r, (0, y))
    y += r.size[1]
S.save(out)
print(out, S.size)
