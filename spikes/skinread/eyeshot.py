"""eyeshot.py <model> <tag>: the model's eyes (front reference camera), lit by the picture's light and flat (albedo),
side by side at 4 px a picture pixel -> $G/out/eye_<tag>.png"""
import os, sys
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr, blockin as bi, humanfit, resources, store
from hifipushie import blockin_clay, blockin_models, humanfit_views, skin_read_frames

m, tag = sys.argv[1:3]
rj = blockin_models._refs(m)
vi = blockin_clay._front(rj)
cam = rj["cameras"][vi]
L = humanfit.state(store.load(m)["base"])["L"]
P = humanfit_views.project(cam, L)
w = float(np.linalg.norm(P[45] - P[36]))
c = P[36:48].mean(0)
box = [c[0] - 0.75 * w, c[1] - 0.45 * w, c[0] + 0.75 * w, c[1] + 1.05 * w]   # square 1.5 w
with resources.heavy(f"skinread eyeshot {m}", gb=6):
    sn = skin_read_frames.stage(m, log=lambda s: None)
    fr = [skin_read_frames.fitted_frame(cam, box, "v")]
    a = skin_read_frames.shoot(sn, fr, skin_read_frames.lighting(m, vi), size=1200)["v"]
    b = skin_read_frames.shoot(sn, fr, None, size=1200, flat=True)["v"]
W = np.concatenate([a[:560, :, :3], b[:560, :, :3]], 0)
out = f"{os.environ['G']}/out/eye_{tag}.png"
Image.fromarray(W).save(out); print(out)
