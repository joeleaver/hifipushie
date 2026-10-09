"""sheet.py <out.png> [names,...|all] [front|tq]: each face slider at -1 / 0 / +1 on the template adult (one mesh, no
identity), clay through a fixed camera at the subject's left eye, 1 mm ticks up from the upper lid margin (red = the
margin, every 5th tick long). Prints, per slider, the max move (mm) and the template quads turned over against 0."""
import copy
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import faceslide, humanfit, humans, likeness

out = sys.argv[1]
names = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] != "all" else list(faceslide.NAMES)
view = sys.argv[3] if len(sys.argv) > 3 else "front"
sp = humans.spec(age=40, sex=1.0, seed=None, skin=False, source="human")
b0 = sp["base"]


def st_of(sl):
    b = copy.deepcopy(b0)
    if sl:
        b.setdefault("head", {})["sliders"] = sl
    return humanfit.state(b)


st0 = st_of({})
L0 = np.asarray(st0["L"])
eyeL = 0.5 * (L0[42] + L0[45])
cam = {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.5], "f": 4000.0, "size": [2000, 2000], "centre": eyeL.tolist(),
       "yaw": 0.0 if view == "front" else -35.0}
c = humanfit.project(cam, eyeL[None])[0]
print("eye L at", c, "eye R at", humanfit.project(cam, (0.5 * (L0[36] + L0[39]))[None])[0])
box = (c[0] - 260, c[1] - 230, c[0] + 260, c[1] + 160)
PX = 420
Q0 = np.asarray(st0["tpl"]["L"]).reshape(-1, 4)


def turned(P0, P1):
    n0 = np.cross(P0[Q0[:, 2]] - P0[Q0[:, 0]], P0[Q0[:, 3]] - P0[Q0[:, 1]])
    n1 = np.cross(P1[Q0[:, 2]] - P1[Q0[:, 0]], P1[Q0[:, 3]] - P1[Q0[:, 1]])
    return int(((n0 * n1).sum(1) < 0).sum())


def tile(st, label):
    im, k = likeness.render(likeness.model_mesh_from_state(st), cam, box, px=PX, brows=False)
    im = im.convert("RGB")
    d = ImageDraw.Draw(im)
    Ls = np.asarray(st["L"])
    m = 0.5 * (Ls[43] + Ls[44])
    for i in range(0, 16):
        p = humanfit.project(cam, (m + np.array([0, 0, 1.0]) * i * 0.001)[None])[0]
        x, y = (p[0] - box[0]) * k - 60, (p[1] - box[1]) * k
        d.line([(x, y), (x + (14 if i % 5 == 0 else 7), y)], fill=(200, 0, 0) if i == 0 else (40, 40, 40), width=1)
    d.text((6, 4), label, fill=(0, 0, 0))
    return im


rows = []
for nm in names:
    tiles = []
    for v in (-1, 0, 1):
        st = st_of({nm: v} if v else {})
        P0, P1 = np.asarray(st0["tpl"]["P"]), np.asarray(st["tpl"]["P"])
        if v:
            print(f"{nm} {v:+d}: max move {1000 * np.linalg.norm(P1 - P0, axis=1).max():.2f} mm, "
                  f"quads turned {turned(P0, P1)}")
        tiles.append(tile(st, f"{nm} {v:+d}"))
    row = Image.new("RGB", (sum(t.width for t in tiles), tiles[0].height), (255, 255, 255))
    x = 0
    for t in tiles:
        row.paste(t, (x, 0))
        x += t.width
    rows.append(row)
sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), (255, 255, 255))
y = 0
for r in rows:
    sheet.paste(r, (0, y))
    y += r.height
sheet.save(out)
print(out, sheet.size)
