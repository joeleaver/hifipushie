import sys as _s; _s.path.insert(0, "/mnt/data/hifipushie/folds_ab/D")
from joined import joined
"""look.py <tag>: collar close-ups (front, 3/4, side, back) clay, beside nothing: judge against the trace by eye."""
import sys, pickle
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import cloth, resources
D = "/mnt/data/hifipushie/folds_ab/D/"; t = sys.argv[1]
d = pickle.load(open(f"{D}{t}.pkl", "rb")); X = np.asarray(d["A"], float); M = d["mesh"]; F = np.asarray(M["F"])
body = {"name": "body", "V": d["bodyV"], "F": d["bodyF"], "color": "#c4bcb4"}
clay = [body, {"name": "shirt", "V": X, "F": joined(X, M, np.asarray(d["bodyV"], float), np.asarray(d["bodyF"])), "color": "#c9ccd2", "thickness": 0.0004, "offset": 0.0}]
R = {"front": ([[-0.12, -0.2, 1.40], [0.12, 0.12, 1.64]], [0, -1, 0.12]),
     "q": ([[-0.14, -0.2, 1.40], [0.14, 0.12, 1.64]], [-0.6, -0.8, 0.12]),
     "side": ([[-0.12, -0.2, 1.40], [0.12, 0.12, 1.64]], [-1, 0, 0.05]),
     "back": ([[-0.12, -0.12, 1.40], [0.12, 0.2, 1.64]], [0, 1, 0.25])}
ims = []
with resources.heavy(f"look {t}", gb=3.0, gpu=True):
    for nmv, (box, dirv) in R.items():
        a = cloth.render(clay, f"{D}{t}_{nmv}", views=[{"name": nmv, "dir": dirv}], resolution=480, box=box)[0]
        ims.append((nmv, Image.open(a).convert("RGB")))
H = 420; sc = lambda im: im.resize((int(im.size[0] * H / im.size[1]), H))
W = sum(sc(a).size[0] for _, a in ims); sh = Image.new("RGB", (W, H + 22), "white"); x = 0; dr = ImageDraw.Draw(sh)
for nmv, a in ims:
    a = sc(a); sh.paste(a, (x, 22)); dr.text((x + 4, 5), f"{t} {nmv}", fill="black"); x += a.size[0]
sh.save(f"{D}{t}_look.png"); print(f"{D}{t}_look.png")
