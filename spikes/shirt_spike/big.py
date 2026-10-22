"""big.py <tag> [diag]: large close-ups of the collar (front, three-quarter, side) at 900 px: clay, and diag modes."""
import sys, pickle, os
import numpy as np
from PIL import Image
from hifipushie import cloth, resources
D = "/mnt/data/hifipushie/shirt_spike/"; t = sys.argv[1]; dg = sys.argv[2].split(",") if len(sys.argv) > 2 else None
d = pickle.load(open(f"{D}{t}.pkl", "rb")); X = np.asarray(d["A"], float); M = d["mesh"]; F = np.asarray(M["F"])
body = {"name": "body", "V": d["bodyV"], "F": d["bodyF"], "color": "#c4bcb4"}
objs = [body, {"name": "shirt", "V": X, "F": F, "mesh": M, "layer": 0, "color": "#c9ccd2"}] if dg else \
       [body, {"name": "shirt", "V": X, "F": F, "color": "#c9ccd2", "thickness": 0.0004, "offset": 0.0}]
box = [[-0.12, -0.2, 1.43], [0.12, 0.1, 1.6]]
views = [{"name": "bf", "dir": [0, -1, 0.1]}, {"name": "bq", "dir": [-0.6, -0.8, 0.1]}, {"name": "bs", "dir": [-1, 0, 0.05]}]
with resources.heavy(f"big {t}", gb=4.0, gpu=True):
    ps = cloth.render(objs, f"{D}{t}_big{'_' + '_'.join(dg) if dg else ''}", views=views, resolution=900, box=box, diag=dg)
ims = [Image.open(p).convert("RGB") for p in ps]; H = 520
ims = [i.resize((int(i.size[0] * H / i.size[1]), H)) for i in ims]
sh = Image.new("RGB", (sum(i.size[0] for i in ims), H), "white"); x = 0
for i in ims: sh.paste(i, (x, 0)); x += i.size[0]
out = f"{D}{t}_big{'_' + '_'.join(dg) if dg else ''}.png"; sh.save(out); print(out)
