"""clay.py <model> ...: the fast clay raster of the subject's left eye through the fitted camera (AO + shadow), the
margin ring (blue), lm68 eye points (red), the visible-eyeball edge; out/clay_<model>.png"""
import os
import sys

import numpy as np
from PIL import ImageDraw

from hifipushie import blockin_brows as bb, eye_ruler as er, humanfit, likeness, store

G = os.environ["G"] + "/out"
q = bb._inputs("gd_T12")
mm, cam = q["mm"], q["cam"]
for name in sys.argv[1:]:
    spec = store.load(name)
    st = humanfit.state(spec["base"])
    ht = st["head"]
    mesh = likeness.model_mesh_from_state(st)
    c = np.asarray(max(ht["eyes"], key=lambda e: e[0]), float)
    pc = humanfit.project(cam, c[None])[0]
    half = 17.0 / mm
    box = (pc[0] - half, pc[1] - half * 0.7, pc[0] + half, pc[1] + half * 0.7)
    im, k = likeness.render(mesh, cam, box, px=1500, brows=False, ao=True, shadow=True)[:2]
    d = ImageDraw.Draw(im)
    ring, _ = er._ring(ht, c)
    P = (humanfit.project(cam, np.asarray(ht["verts"])[ring]) - box[:2]) * k
    for p in P:
        d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=(60, 110, 255))
    Lp = (humanfit.project(cam, st["L"][42:48]) - box[:2]) * k
    for p in Lp:
        d.ellipse([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5], outline=(255, 0, 0), width=2)
    d.line([(20, 20), (20 + 5 / mm * k, 20)], fill=(0, 0, 0), width=3)
    im.save(f"{G}/clay_{name}.png")
    print(name, "saved", im.size)
