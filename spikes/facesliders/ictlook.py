"""ictlook.py <out.png> [modes, default 0,1,2,5,10,20,50]: ICT FaceKit identity modes at -3 / +3 sd on ICT's own neutral
mesh (left pair) and carried onto GNM's mean head (right pair, ictreg.py's ict_modes.npz), front and 3/4, clay (perc.py's
renderer). Judges the registration / carry: the two pairs should show the same change."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import ictreg  # noqa: E402
import perc  # noqa: E402
from hifipushie import likeness  # noqa: E402

out = sys.argv[1]
modes = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "0,1,2,5,10,20,50").split(",")]
z = np.load(ictreg.OUT / "ict_modes.npz")
s, R, t = float(z["s"]), z["R"], z["t"]
V0, M, T = ictreg.load_ict()
Vi = s * V0 @ R.T + t
Mi = s * M.astype(float) @ R.T
MG = z["modes"].astype(float)
A = 3.0
PX = perc.PX


def render_ict(V, yaw):
    W = perc.world(V)
    L = W[ictreg.ICT_LM68]
    cen = L[[36, 45, 48, 54]].mean(0)
    half = 0.095
    cam = {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.8], "f": PX / 2 * 0.8 / half, "size": [PX, PX],
           "centre": list(map(float, cen)), "yaw": yaw}
    mesh = {"V": W, "F": T.astype(np.int64), "eyes": [], "L": L}
    return likeness.render(mesh, cam, (0, 0, PX, PX), px=PX, brows=False)[0]


c0 = np.zeros(len(perc.ID_NAMES))
rows = []
for k in modes:
    tiles = []
    for yaw in (0.0, -35.0):
        tiles += [render_ict(Vi - A * Mi[k], yaw), render_ict(Vi + A * Mi[k], yaw)]
        tiles += [perc.render(perc.verts(c0, D=-A * MG[k]), yaw), perc.render(perc.verts(c0, D=A * MG[k]), yaw)]
    rows.append((k, tiles))
sheet = Image.new("RGB", (60 + 8 * (PX + 2), 20 + len(rows) * (PX + 2)), "white")
d = ImageDraw.Draw(sheet)
for j, lab in enumerate(["ICT -3", "ICT +3", "GNM -3", "GNM +3"] * 2):
    d.text((60 + j * (PX + 2) + 4, 4), lab + (" (3/4)" if j >= 4 else ""), fill=(0, 0, 0))
for i, (k, tiles) in enumerate(rows):
    d.text((4, 20 + i * (PX + 2) + PX // 2), f"mode {k}", fill=(0, 0, 0))
    for j, im in enumerate(tiles):
        sheet.paste(im, (60 + j * (PX + 2), 20 + i * (PX + 2)))
sheet.save(out)
print("wrote", out, sheet.size)
