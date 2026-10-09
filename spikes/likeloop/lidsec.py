"""lidsec.py <out.png> <label=base.json|model>...: a side section through the right upper lid at the pupil (vertices
within 0.8 mm of the plane x = pupil x, eye centre -> brow): y (depth, forward = left) against z, one colour per head,
2 px = 0.1 mm; plus, per head, the template quads in the lid region that turned over against the first head's
(normal flipped) and the section's fold count (the profile's z running back down while going up the lid)."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import humanfit, store

COLS = [(40, 40, 40), (220, 40, 40), (40, 90, 220), (30, 160, 60)]
heads = []
for a in sys.argv[2:]:
    lab, src = a.split("=", 1)
    base = json.load(open(src)) if src.endswith(".json") else store.load(src)["base"]
    st = humanfit.state(base)
    heads.append((lab, np.asarray(st["tpl"]["P"], float), np.asarray(st["tpl"]["L"]).reshape(-1, 4), np.asarray(st["L"])))
lab0, P0, Q, L0 = heads[0]
pup = 0.5 * (L0[37] + L0[38])
brow = L0[19]
sel = (np.abs(P0[:, 0] - pup[0]) < 0.0018) & (P0[:, 2] > pup[2] - 0.004) & (P0[:, 2] < brow[2] + 0.004) & (P0[:, 1] < pup[1] + 0.012)
reg = (np.abs(P0[:, 0] - pup[0]) < 0.016) & (P0[:, 2] > pup[2] - 0.003) & (P0[:, 2] < brow[2] + 0.003) & (P0[:, 1] < pup[1] + 0.012)
quads = Q[reg[Q].all(1)]


def nrm(P):
    return np.cross(P[quads[:, 2]] - P[quads[:, 0]], P[quads[:, 3]] - P[quads[:, 1]])


n0 = nrm(P0)
S = 10.0 / 0.0005   # px per m (2 px = 0.1 mm)
ys, zs = P0[sel][:, 1], P0[sel][:, 2]
y0, z0 = ys.min() - 0.004, zs.min() - 0.001
W, H = int((ys.max() - ys.min() + 0.012) * S), int((zs.max() - zs.min() + 0.002) * S)
im = Image.new("RGB", (W, H), (250, 250, 250))
d = ImageDraw.Draw(im)
for mm in range(0, int((zs.max() - zs.min()) * 1000) + 2):
    yy = H - (mm / 1000 + zs.min() - z0) * S
    d.line([(0, yy), (6, yy)], fill=(150, 150, 150))
for k, (lab, P, _, L) in enumerate(heads):
    p = P[sel]
    o = np.argsort(p[:, 2])
    pts = [((q[1] - y0) * S, H - (q[2] - z0) * S) for q in p[o]]
    d.line(pts, fill=COLS[k % 4], width=2)
    d.text((8, 8 + 14 * k), lab, fill=COLS[k % 4])
    fl = int(((nrm(P) * n0).sum(1) < 0).sum())
    print(f"{lab}: lid-region quads turned over vs {lab0}: {fl} of {len(quads)}; section points {sel.sum()}; "
          f"max depth change {1000 * float(np.abs(P[sel][:, 1] - P0[sel][:, 1]).max()):.2f} mm")
im.save(sys.argv[1])
